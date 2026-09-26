"""
MutationTestingStrategy — Phase 6.

Creates bounded, relevant mutants in changed/targeted Python code,
runs applicable tests, classifies KILLED/SURVIVED/INVALID.

EvidenceContract:
  PASS        — all mutants killed (tests caught all mutations)
  FAIL        — surviving mutants found (test weakness evidence)
  INSUFFICIENT — no mutable code or no applicable tests
  ERROR        — unexpected exception (fail-closed)

Surviving mutant ≠ automatic bug. It is evidence of test weakness.
All mutants are cleaned up unconditionally via MutantCleanupRegistry.

Cost = 7 (expensive — modifies and re-runs code)
"""
from __future__ import annotations

import ast
import logging
import os
import random
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.infrastructure import (
    BoundedExecutionContext,
    DeterministicSeed,
    IsolatedWorkspace,
    MutantCleanupRegistry,
)

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)

# Bounded limits
_MAX_MUTANTS = 15
_MAX_SECONDS = 25.0
_TEST_TIMEOUT = 15  # per mutant test run


# ---------------------------------------------------------------------------
# Mutation operators
# ---------------------------------------------------------------------------

@dataclass
class Mutant:
    """Represents a single code mutation."""
    file_path: str       # absolute path
    rel_path: str        # relative to repo root
    lineno: int
    operator: str
    original_code: str
    mutated_code: str
    status: str = "PENDING"  # PENDING | KILLED | SURVIVED | INVALID


class _MutationVisitor(ast.NodeVisitor):
    """Collect mutation sites from a Python AST."""

    # Arithmetic operator swaps
    _ARITH_OPS = {
        ast.Add: ast.Sub,
        ast.Sub: ast.Add,
        ast.Mult: ast.Div,
        ast.Div: ast.Mult,
    }
    # Comparison operator swaps
    _CMP_OPS = {
        ast.Gt: ast.Lt,
        ast.Lt: ast.Gt,
        ast.GtE: ast.LtE,
        ast.LtE: ast.GtE,
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
    }

    def __init__(self) -> None:
        self.sites: list[tuple[int, str, str]] = []  # (lineno, operator, description)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        for orig, _ in self._ARITH_OPS.items():
            if isinstance(node.op, orig):
                self.sites.append((node.lineno, "ARITH_OP", f"line {node.lineno}: swap {orig.__name__}"))
                break
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op in node.ops:
            for orig, _ in self._CMP_OPS.items():
                if isinstance(op, orig):
                    self.sites.append((node.lineno, "CMP_OP", f"line {node.lineno}: swap {orig.__name__}"))
                    break
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None:
            self.sites.append((node.lineno, "RETURN_NONE", f"line {node.lineno}: return None"))
        self.generic_visit(node)


def _collect_mutation_sites(source: str) -> list[tuple[int, str, str]]:
    """Parse source and collect mutation sites."""
    try:
        tree = ast.parse(source)
        visitor = _MutationVisitor()
        visitor.visit(tree)
        return visitor.sites
    except SyntaxError:
        return []


def _apply_mutation(source: str, lineno: int, operator: str) -> Optional[str]:
    """
    Apply a mutation to source at the given line.

    Returns mutated source, or None if mutation fails.
    Uses text-level line substitution for simplicity and safety.
    """
    lines = source.splitlines(keepends=True)
    if lineno < 1 or lineno > len(lines):
        return None

    idx = lineno - 1
    original_line = lines[idx]

    if operator == "ARITH_OP":
        # Swap + ↔ - and * ↔ /
        for a, b in [(" + ", " - "), (" - ", " + "), (" * ", " / "), (" / ", " * ")]:
            if a in original_line:
                lines[idx] = original_line.replace(a, b, 1)
                return "".join(lines)
        return None

    elif operator == "CMP_OP":
        for a, b in [(" > ", " < "), (" < ", " > "), (" >= ", " <= "), (" <= ", " >= "),
                     (" == ", " != "), (" != ", " == ")]:
            if a in original_line:
                lines[idx] = original_line.replace(a, b, 1)
                return "".join(lines)
        return None

    elif operator == "RETURN_NONE":
        stripped = original_line.lstrip()
        if stripped.startswith("return "):
            indent = original_line[: len(original_line) - len(original_line.lstrip())]
            lines[idx] = f"{indent}return None\n"
            return "".join(lines)
        return None

    return None


class MutationTestingStrategy(BaseStrategy):
    """
    Create bounded mutants in changed code, run tests, classify results.

    Surviving mutants → evidence of test weakness (not automatic bug).
    All mutants cleaned up unconditionally.
    """

    name = "mutation_testing"
    cost = 7

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        # Need both non-test Python files and test files
        py_files = list(snapshot.all_files)
        non_test = [f for f in py_files if f.endswith(".py") and "test" not in f.lower()]
        test_files = [f for f in py_files if f.endswith(".py") and "test" in f.lower()]
        return len(non_test) > 0 and len(test_files) > 0

    def prerequisites_met(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> tuple[bool, str]:
        py_files = list(snapshot.all_files)
        test_files = [f for f in py_files if f.endswith(".py") and "test" in f.lower()]
        if not test_files:
            return False, "No test files found — mutation testing requires a test suite"
        non_test = [f for f in py_files if f.endswith(".py") and "test" not in f.lower()]
        if not non_test:
            return False, "No non-test Python files to mutate"
        return True, ""

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            return self._execute_inner(snapshot, context)
        except Exception as exc:
            logger.exception("MutationTestingStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"MutationTesting exception: {exc}\n{traceback.format_exc()}",
            )

    def _execute_inner(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> StrategyResult:
        repo_path = snapshot.repository_path
        py_files = list(snapshot.all_files)
        non_test = [f for f in py_files
                    if f.endswith(".py") and "test" not in f.lower()]

        seed = DeterministicSeed.for_strategy(snapshot.snapshot_hash, self.name)
        rng = random.Random(seed)
        budget = BoundedExecutionContext(
            max_iterations=_MAX_MUTANTS,
            max_seconds=_MAX_SECONDS,
        )

        mutants: list[Mutant] = []
        output_lines = [f"MutationTesting: seed={seed}"]

        # Work inside an isolated copy of the repo
        with IsolatedWorkspace(repo_path) as ws:
            source_root = os.path.join(ws.root, "source")
            if not os.path.isdir(source_root):
                source_root = ws.root

            cleanup = MutantCleanupRegistry()

            # Collect mutation sites across changed/target files
            site_pool: list[tuple[str, str, int, str]] = []  # (abs, rel, lineno, op)
            target_files = non_test[:10]
            for rel in target_files:
                abs_path = os.path.join(source_root, rel)
                if not os.path.isfile(abs_path):
                    continue
                try:
                    with open(abs_path, encoding="utf-8", errors="replace") as fh:
                        source = fh.read()
                    sites = _collect_mutation_sites(source)
                    for lineno, op, _ in sites:
                        site_pool.append((abs_path, rel, lineno, op))
                except OSError:
                    continue

            if not site_pool:
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output="MutationTesting: no mutable sites found in target files.",
                )

            # Shuffle deterministically and cap
            rng.shuffle(site_pool)
            selected_sites = site_pool[: _MAX_MUTANTS]

            # Pre-run tests to establish baseline
            baseline_ok = self._run_tests(source_root, timeout=_TEST_TIMEOUT)
            if not baseline_ok:
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output=(
                        "MutationTesting: baseline test run failed — "
                        "cannot establish mutation results against a broken baseline."
                    ),
                )

            try:
                for abs_path, rel, lineno, op in selected_sites:
                    if not budget.should_continue():
                        break
                    budget.tick()

                    # Read current (unmutated) source
                    try:
                        with open(abs_path, encoding="utf-8", errors="replace") as fh:
                            original_source = fh.read()
                    except OSError:
                        continue

                    mutated = _apply_mutation(original_source, lineno, op)
                    if mutated is None:
                        mutant = Mutant(
                            file_path=abs_path, rel_path=rel,
                            lineno=lineno, operator=op,
                            original_code=original_source,
                            mutated_code="",
                            status="INVALID",
                        )
                        mutants.append(mutant)
                        continue

                    # Write mutation
                    cleanup.backup(abs_path)
                    try:
                        with open(abs_path, "w", encoding="utf-8") as fh:
                            fh.write(mutated)

                        tests_passed = self._run_tests(source_root, timeout=_TEST_TIMEOUT)
                        status = "SURVIVED" if tests_passed else "KILLED"
                    finally:
                        cleanup.restore_all()

                    mutant = Mutant(
                        file_path=abs_path, rel_path=rel,
                        lineno=lineno, operator=op,
                        original_code=original_source,
                        mutated_code=mutated,
                        status=status,
                    )
                    mutants.append(mutant)
                    output_lines.append(
                        f"  [{status}] {rel}:{lineno} operator={op}"
                    )

            finally:
                # Guarantee cleanup even if something goes wrong
                cleanup.restore_all()

        # Classify results
        killed = [m for m in mutants if m.status == "KILLED"]
        survived = [m for m in mutants if m.status == "SURVIVED"]
        invalid = [m for m in mutants if m.status == "INVALID"]

        summary = (
            f"Mutants: total={len(mutants)}, killed={len(killed)}, "
            f"survived={len(survived)}, invalid={len(invalid)}, "
            f"seed={seed}"
        )
        output_lines.insert(1, summary)

        if not mutants or (killed + survived) == []:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output="\n".join(output_lines) + "\nNo valid mutants could be tested.",
            )

        kill_rate = len(killed) / max(len(killed) + len(survived), 1)

        if survived:
            surviving_detail = "; ".join(
                f"{m.rel_path}:{m.lineno}({m.operator})" for m in survived
            )
            return StrategyResult(
                result="FAIL",
                confidence=0.7,
                raw_output="\n".join(output_lines),
                command=f"mutation_testing seed={seed}",
                evidence_items=[{
                    "type": "mutation_testing",
                    "kill_rate": round(kill_rate, 3),
                    "surviving_mutants": surviving_detail,
                    "seed": seed,
                    "note": "Surviving mutants indicate test weakness, not a confirmed bug.",
                }],
            )

        return StrategyResult(
            result="PASS",
            confidence=min(0.5 + kill_rate * 0.4, 0.9),
            raw_output="\n".join(output_lines),
            command=f"mutation_testing seed={seed}",
        )

    def _run_tests(self, work_dir: str, timeout: int) -> bool:
        """
        Run pytest in work_dir. Returns True if tests pass (exit code 0).
        Returns False on failure or timeout.
        """
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--tb=no", "-q"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False
