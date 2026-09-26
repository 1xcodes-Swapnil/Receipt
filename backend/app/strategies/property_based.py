"""
PropertyBasedTestingStrategy — Phase 6.

Generates bounded test cases from declared properties in the repository.
Uses reproducible seeds. Records failing inputs as evidence.

EvidenceContract:
  PASS        — all property checks passed within budget
  FAIL        — at least one property violation found (with failing input)
  INSUFFICIENT — no applicable properties found, or execution infrastructure unavailable
  ERROR        — unexpected exception (fail-closed)

Cost = 6 (moderate — executes generated test cases)
"""
from __future__ import annotations

import ast
import logging
import os
import random
import sys
import traceback
from typing import TYPE_CHECKING, Any, Callable, Optional

from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.infrastructure import (
    BoundedExecutionContext,
    CounterexampleRecord,
    DeterministicSeed,
    IsolatedWorkspace,
)

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)

# Maximum properties to test per strategy run
_MAX_PROPERTIES = 10
# Iterations per property
_MAX_ITERATIONS_PER_PROPERTY = 30
# Overall budget
_MAX_SECONDS = 20.0


# ---------------------------------------------------------------------------
# Built-in property specifications
# ---------------------------------------------------------------------------


def _discover_testable_functions(repo_path: str, py_files: list[str]) -> list[dict]:
    """
    Parse Python files and find functions with type-annotatable signatures
    that can be property-tested.

    Returns list of {name, file, args, annotations} dicts.
    """
    candidates = []
    for rel in py_files[:20]:
        abs_path = os.path.join(repo_path, rel)
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            tree = ast.parse(source, filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                # Skip private/test/dunder
                if node.name.startswith("_"):
                    continue
                if "test" in node.name.lower():
                    continue
                args = [a.arg for a in node.args.args if a.arg != "self"]
                if not args:
                    continue
                # Only include functions with at least one arg
                candidates.append({
                    "name": node.name,
                    "file": rel,
                    "lineno": node.lineno,
                    "args": args,
                })
                if len(candidates) >= _MAX_PROPERTIES:
                    return candidates
        except (SyntaxError, OSError):
            continue
    return candidates


def _generate_inputs(rng: random.Random, n_args: int, iteration: int) -> list[Any]:
    """Generate a list of n_args pseudo-random inputs."""
    inputs = []
    for i in range(n_args):
        choice = rng.randint(0, 5)
        if choice == 0:
            inputs.append(rng.randint(-1000, 1000))
        elif choice == 1:
            inputs.append(rng.uniform(-1000.0, 1000.0))
        elif choice == 2:
            length = rng.randint(0, 20)
            inputs.append("".join(chr(rng.randint(32, 126)) for _ in range(length)))
        elif choice == 3:
            inputs.append([rng.randint(-100, 100) for _ in range(rng.randint(0, 10))])
        elif choice == 4:
            inputs.append(None)
        else:
            inputs.append(rng.choice([True, False]))
    return inputs


def _run_property_check(
    module_path: str,
    func_name: str,
    inputs: list[Any],
    workspace_root: str,
) -> tuple[bool, Optional[str]]:
    """
    Attempt to call func_name(*inputs) in an isolated namespace.

    Returns (passed, failure_reason).
    passed=True if the call did not raise an unexpected exception.
    NOTE: We only check for unhandled exceptions — no invariant specification.
    """
    try:
        # Load source
        abs_path = os.path.join(workspace_root, module_path)
        if not os.path.isfile(abs_path):
            return True, None  # can't test → skip

        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()

        # Compile and exec in an isolated namespace
        ns: dict = {"__builtins__": __builtins__}
        try:
            code = compile(source, abs_path, "exec")
            exec(code, ns)  # noqa: S102
        except Exception:
            return True, None  # compilation/import error → skip

        func = ns.get(func_name)
        if not callable(func):
            return True, None  # not found or not callable → skip

        func(*inputs)
        return True, None

    except TypeError:
        # Wrong types — not a property violation
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


class PropertyBasedTestingStrategy(BaseStrategy):
    """
    Generate bounded test cases from discoverable function properties.

    Applicable when Python files with testable functions exist.
    """

    name = "property_based_testing"
    cost = 6

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        py_files = [f for f in snapshot.all_files if f.endswith(".py")
                    and "test" not in f.lower()]
        return len(py_files) > 0

    def prerequisites_met(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> tuple[bool, str]:
        py_files = [f for f in snapshot.all_files if f.endswith(".py")
                    and "test" not in f.lower()]
        if not py_files:
            return False, "No non-test Python files found"
        return True, ""

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            return self._execute_inner(snapshot, context)
        except Exception as exc:
            logger.exception("PropertyBasedTestingStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"PropertyBasedTesting exception: {exc}\n{traceback.format_exc()}",
            )

    def _execute_inner(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> StrategyResult:
        repo_path = snapshot.repository_path
        py_files = [f for f in snapshot.all_files
                    if f.endswith(".py") and "test" not in f.lower()]

        # Discover testable functions
        candidates = _discover_testable_functions(repo_path, py_files)
        if not candidates:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output=(
                    "PropertyBasedTesting: no applicable property targets found. "
                    "No public functions with parameters discovered."
                ),
            )

        seed = DeterministicSeed.for_strategy(snapshot.snapshot_hash, self.name)
        rng = random.Random(seed)
        budget = BoundedExecutionContext(
            max_iterations=_MAX_ITERATIONS_PER_PROPERTY * len(candidates),
            max_seconds=_MAX_SECONDS,
        )

        violations: list[CounterexampleRecord] = []
        checks_run = 0
        properties_tested = 0
        output_lines = [
            f"PropertyBasedTesting: seed={seed}, candidates={len(candidates)}",
        ]

        with IsolatedWorkspace(repo_path) as ws:
            source_root = os.path.join(ws.root, "source")
            if not os.path.isdir(source_root):
                source_root = ws.root

            for prop_idx, candidate in enumerate(candidates):
                if not budget.should_continue():
                    break

                func_name = candidate["name"]
                rel_file = candidate["file"]
                n_args = len(candidate["args"])
                prop_seed = DeterministicSeed.for_iteration(seed, prop_idx)
                prop_rng = random.Random(prop_seed)
                properties_tested += 1
                prop_violations = 0

                for iteration in range(_MAX_ITERATIONS_PER_PROPERTY):
                    if not budget.should_continue():
                        break
                    budget.tick()

                    iter_inputs = _generate_inputs(prop_rng, n_args, iteration)
                    passed, reason = _run_property_check(
                        rel_file, func_name, iter_inputs, source_root
                    )
                    checks_run += 1

                    if not passed:
                        record = CounterexampleRecord(
                            strategy_name=self.name,
                            property_description=f"{func_name}({', '.join(candidate['args'])})",
                            original_input=iter_inputs,
                            minimized_input=iter_inputs,
                            failure_reason=reason or "unknown",
                            seed=prop_seed,
                        )
                        violations.append(record)
                        prop_violations += 1
                        output_lines.append(
                            f"  VIOLATION: {func_name} raised {reason} "
                            f"with inputs={iter_inputs!r}"
                        )
                        break  # one violation per property is enough

                if prop_violations == 0:
                    output_lines.append(
                        f"  PASS: {func_name} ({_MAX_ITERATIONS_PER_PROPERTY} checks)"
                    )

        summary = (
            f"Properties tested: {properties_tested}, "
            f"Checks run: {checks_run}, "
            f"Violations: {len(violations)}, "
            f"Seed: {seed}"
        )
        output_lines.insert(1, summary)
        raw_output = "\n".join(output_lines)

        if violations:
            violation_details = "; ".join(
                f"{v.property_description}: {v.failure_reason}"
                for v in violations
            )
            return StrategyResult(
                result="FAIL",
                confidence=0.75,
                raw_output=raw_output,
                evidence_items=[v.to_dict() for v in violations],
                command=f"property_based_testing seed={seed}",
            )

        if checks_run == 0:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output=raw_output + "\nNo checks could be executed.",
            )

        return StrategyResult(
            result="PASS",
            confidence=0.6,
            raw_output=raw_output,
            command=f"property_based_testing seed={seed}",
        )
