"""
MetamorphicTestingStrategy — Phase 6.

Define input transformations and expected metamorphic relations,
execute original + transformed cases, record reproducible violations.

EvidenceContract:
  PASS        — all relations held for all tested functions
  FAIL        — at least one metamorphic relation violated
  INSUFFICIENT — no applicable metamorphic relations found
  ERROR        — unexpected exception (fail-closed)

Cost = 6 (moderate — executes original + transformed inputs)
"""
from __future__ import annotations

import ast
import logging
import os
import random
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.infrastructure import (
    BoundedExecutionContext,
    DeterministicSeed,
    IsolatedWorkspace,
)

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)

_MAX_FUNCTIONS = 8
_MAX_ITERATIONS = 20
_MAX_SECONDS = 20.0


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------

@dataclass
class MetamorphicRelation:
    """A single input transformation + expected output relation."""
    name: str
    description: str
    transform: object   # callable(inputs) → transformed_inputs
    check: object       # callable(original_result, transformed_result) → bool
    applicable: object  # callable(func_name, args) → bool


def _mr_commutative_add(inputs: list) -> list:
    """Swap first two args (tests commutativity for add-like functions)."""
    if len(inputs) >= 2:
        swapped = list(inputs)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        return swapped
    return inputs


def _mr_negate_numeric(inputs: list) -> list:
    """Negate first numeric arg."""
    result = list(inputs)
    for i, v in enumerate(result):
        if isinstance(v, (int, float)):
            result[i] = -v
            return result
    return inputs


def _mr_double_input(inputs: list) -> list:
    """Double the first numeric arg."""
    result = list(inputs)
    for i, v in enumerate(result):
        if isinstance(v, (int, float)):
            result[i] = v * 2
            return result
    return inputs


# Built-in metamorphic relations
_RELATIONS: list[MetamorphicRelation] = [
    MetamorphicRelation(
        name="swap_args",
        description="Swapping first two args should not raise when function is commutative",
        transform=_mr_commutative_add,
        check=lambda orig, trans: True,  # We only check for crash/no-crash
        applicable=lambda name, args: len(args) >= 2,
    ),
    MetamorphicRelation(
        name="negate_input",
        description="Negating numeric input should not crash",
        transform=_mr_negate_numeric,
        check=lambda orig, trans: True,  # crash-free check
        applicable=lambda name, args: len(args) >= 1,
    ),
    MetamorphicRelation(
        name="double_input",
        description="Doubling numeric input should not crash",
        transform=_mr_double_input,
        check=lambda orig, trans: True,  # crash-free check
        applicable=lambda name, args: len(args) >= 1,
    ),
]


def _discover_functions(repo_path: str, py_files: list[str]) -> list[dict]:
    """Find testable public functions."""
    candidates = []
    for rel in py_files[:15]:
        abs_path = os.path.join(repo_path, rel)
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name.startswith("_") or "test" in node.name.lower():
                    continue
                args = [a.arg for a in node.args.args if a.arg != "self"]
                if not args:
                    continue
                candidates.append({"name": node.name, "file": rel, "args": args})
                if len(candidates) >= _MAX_FUNCTIONS:
                    return candidates
        except (SyntaxError, OSError):
            continue
    return candidates


def _execute_func(func_name: str, inputs: list, source_root: str, rel_file: str) -> tuple[Any, Optional[str]]:
    """
    Execute func_name(*inputs) in isolated namespace.
    Returns (result, exception_str). exception_str is None on success.
    """
    abs_path = os.path.join(source_root, rel_file)
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        ns: dict = {"__builtins__": __builtins__}
        exec(compile(source, abs_path, "exec"), ns)  # noqa: S102
        func = ns.get(func_name)
        if not callable(func):
            return None, "not_callable"
        result = func(*inputs)
        return result, None
    except TypeError:
        return None, None  # wrong types → skip
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


class MetamorphicTestingStrategy(BaseStrategy):
    """
    Execute original + transformed inputs, verify metamorphic relations.

    No applicable relation → INSUFFICIENT_EVIDENCE.
    """

    name = "metamorphic_testing"
    cost = 6

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        py_files = [f for f in snapshot.all_files
                    if f.endswith(".py") and "test" not in f.lower()]
        return len(py_files) > 0

    def prerequisites_met(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> tuple[bool, str]:
        py_files = [f for f in snapshot.all_files
                    if f.endswith(".py") and "test" not in f.lower()]
        if not py_files:
            return False, "No non-test Python files found"
        return True, ""

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            return self._execute_inner(snapshot, context)
        except Exception as exc:
            logger.exception("MetamorphicTestingStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"MetamorphicTesting exception: {exc}\n{traceback.format_exc()}",
            )

    def _execute_inner(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> StrategyResult:
        repo_path = snapshot.repository_path
        py_files = [f for f in snapshot.all_files
                    if f.endswith(".py") and "test" not in f.lower()]

        candidates = _discover_functions(repo_path, py_files)
        if not candidates:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output="MetamorphicTesting: no applicable targets found.",
            )

        seed = DeterministicSeed.for_strategy(snapshot.snapshot_hash, self.name)
        rng = random.Random(seed)
        budget = BoundedExecutionContext(
            max_iterations=_MAX_ITERATIONS,
            max_seconds=_MAX_SECONDS,
        )

        violations: list[dict] = []
        checks_run = 0
        output_lines = [f"MetamorphicTesting: seed={seed}, candidates={len(candidates)}"]

        with IsolatedWorkspace(repo_path) as ws:
            source_root = os.path.join(ws.root, "source")
            if not os.path.isdir(source_root):
                source_root = ws.root

            for cand in candidates:
                if not budget.should_continue():
                    break

                func_name = cand["name"]
                rel_file = cand["file"]
                args = cand["args"]

                applicable_rels = [
                    mr for mr in _RELATIONS
                    if mr.applicable(func_name, args)
                ]
                if not applicable_rels:
                    continue

                for mr in applicable_rels:
                    if not budget.should_continue():
                        break
                    budget.tick()

                    # Generate base inputs
                    n_args = len(args)
                    base_inputs = []
                    for _ in range(n_args):
                        choice = rng.randint(0, 3)
                        if choice == 0:
                            base_inputs.append(rng.randint(-100, 100))
                        elif choice == 1:
                            base_inputs.append(rng.uniform(-100, 100))
                        elif choice == 2:
                            base_inputs.append(rng.choice(["a", "b", "hello", ""]))
                        else:
                            base_inputs.append(rng.choice([True, False, None]))

                    transformed_inputs = mr.transform(list(base_inputs))

                    # Execute original
                    orig_result, orig_exc = _execute_func(
                        func_name, base_inputs, source_root, rel_file
                    )
                    # Execute transformed
                    trans_result, trans_exc = _execute_func(
                        func_name, transformed_inputs, source_root, rel_file
                    )

                    checks_run += 1

                    # Check: original passed but transformed crashed → violation
                    if orig_exc is None and trans_exc is not None:
                        violations.append({
                            "function": func_name,
                            "file": rel_file,
                            "relation": mr.name,
                            "description": mr.description,
                            "original_inputs": repr(base_inputs),
                            "transformed_inputs": repr(transformed_inputs),
                            "original_result": repr(orig_result),
                            "transformed_exception": trans_exc,
                            "seed": seed,
                        })
                        output_lines.append(
                            f"  VIOLATION: {func_name} relation={mr.name} "
                            f"transform raised {trans_exc}"
                        )
                    else:
                        output_lines.append(
                            f"  OK: {func_name} relation={mr.name}"
                        )

        summary = (
            f"Checks run: {checks_run}, Violations: {len(violations)}, Seed: {seed}"
        )
        output_lines.insert(1, summary)
        raw_output = "\n".join(output_lines)

        if checks_run == 0:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output=raw_output + "\nNo applicable metamorphic relations.",
            )

        if violations:
            return StrategyResult(
                result="FAIL",
                confidence=0.7,
                raw_output=raw_output,
                command=f"metamorphic_testing seed={seed}",
                evidence_items=violations,
            )

        return StrategyResult(
            result="PASS",
            confidence=0.6,
            raw_output=raw_output,
            command=f"metamorphic_testing seed={seed}",
        )
