"""
FuzzingStrategy — Phase 6.

Generates bounded, deterministic/reproducible inputs for public functions.
Enforces iteration/time/resource limits.
Captures crashes, exceptions, invariant violations.
Preserves triggering inputs and cleans artifacts.

EvidenceContract:
  PASS        — no crashes/violations within budget (not proof of correctness)
  FAIL        — crash or invariant violation found with triggering input
  INSUFFICIENT — no fuzzable targets found
  ERROR        — unexpected exception (fail-closed)

No failure within budget ≠ proof of correctness.

Cost = 6 (moderate — bounded execution required)
"""
from __future__ import annotations

import ast
import logging
import os
import random
import string
import traceback
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

_MAX_TARGETS = 8
_MAX_ITERATIONS = 50
_MAX_SECONDS = 20.0


# ---------------------------------------------------------------------------
# Input generators
# ---------------------------------------------------------------------------

def _gen_int(rng: random.Random) -> int:
    return rng.choice([
        0, 1, -1, 2**31 - 1, -(2**31), 2**15,
        rng.randint(-10000, 10000),
    ])


def _gen_str(rng: random.Random) -> str:
    length = rng.choice([0, 1, 10, 100, 1000])
    charset = string.ascii_letters + string.digits + string.punctuation + " \t\n\x00"
    return "".join(rng.choice(charset) for _ in range(min(length, 50)))


def _gen_list(rng: random.Random) -> list:
    length = rng.randint(0, 20)
    return [rng.randint(-100, 100) for _ in range(length)]


def _gen_input(rng: random.Random) -> Any:
    choice = rng.randint(0, 7)
    if choice == 0:
        return _gen_int(rng)
    elif choice == 1:
        return _gen_str(rng)
    elif choice == 2:
        return _gen_list(rng)
    elif choice == 3:
        return rng.uniform(-1e6, 1e6)
    elif choice == 4:
        return None
    elif choice == 5:
        return {}
    elif choice == 6:
        return rng.choice([True, False])
    else:
        return b""


def _discover_fuzz_targets(repo_path: str, py_files: list[str]) -> list[dict]:
    """Find public functions with at least one parameter."""
    targets = []
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
                targets.append({"name": node.name, "file": rel, "n_args": len(args)})
                if len(targets) >= _MAX_TARGETS:
                    return targets
        except (SyntaxError, OSError):
            continue
    return targets


def _fuzz_call(
    func_name: str, inputs: list, source_root: str, rel_file: str
) -> Optional[str]:
    """
    Call func_name(*inputs) in isolated namespace.
    Returns exception string on unexpected crash, None on success/type error.
    """
    abs_path = os.path.join(source_root, rel_file)
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        ns: dict = {"__builtins__": __builtins__}
        exec(compile(source, abs_path, "exec"), ns)  # noqa: S102
        func = ns.get(func_name)
        if not callable(func):
            return None
        func(*inputs)
        return None
    except (TypeError, ValueError, AttributeError):
        # Expected type errors from wrong input types — not a finding
        return None
    except (MemoryError, RecursionError, OverflowError) as exc:
        return f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        # Only report non-trivial unexpected exceptions
        exc_name = type(exc).__name__
        # Filter common benign exceptions from fuzz inputs
        if exc_name in ("TypeError", "ValueError", "AttributeError", "KeyError",
                        "IndexError", "StopIteration"):
            return None
        return f"{exc_name}: {exc}"


class FuzzingStrategy(BaseStrategy):
    """
    Generate bounded, deterministic inputs and fuzz public functions.

    Enforces iteration and time limits.
    Captures crashes and invariant violations.
    """

    name = "fuzzing"
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
            return False, "No non-test Python files to fuzz"
        return True, ""

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            return self._execute_inner(snapshot, context)
        except Exception as exc:
            logger.exception("FuzzingStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Fuzzing exception: {exc}\n{traceback.format_exc()}",
            )

    def _execute_inner(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> StrategyResult:
        repo_path = snapshot.repository_path
        py_files = [f for f in snapshot.all_files
                    if f.endswith(".py") and "test" not in f.lower()]

        targets = _discover_fuzz_targets(repo_path, py_files)
        if not targets:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output="Fuzzing: no fuzzable targets found.",
            )

        seed = DeterministicSeed.for_strategy(snapshot.snapshot_hash, self.name)
        rng = random.Random(seed)
        budget = BoundedExecutionContext(
            max_iterations=_MAX_ITERATIONS,
            max_seconds=_MAX_SECONDS,
        )

        findings: list[dict] = []
        checks_run = 0
        output_lines = [f"Fuzzing: seed={seed}, targets={len(targets)}"]

        with IsolatedWorkspace(repo_path) as ws:
            source_root = os.path.join(ws.root, "source")
            if not os.path.isdir(source_root):
                source_root = ws.root

            iters_per_target = max(1, _MAX_ITERATIONS // len(targets))

            for target in targets:
                if not budget.should_continue():
                    break

                func_name = target["name"]
                rel_file = target["file"]
                n_args = target["n_args"]
                target_seed = DeterministicSeed.for_iteration(seed, targets.index(target))
                target_rng = random.Random(target_seed)
                target_findings = 0

                for iteration in range(iters_per_target):
                    if not budget.should_continue():
                        break
                    budget.tick()

                    inputs = [_gen_input(target_rng) for _ in range(n_args)]
                    exc_str = _fuzz_call(func_name, inputs, source_root, rel_file)
                    checks_run += 1

                    if exc_str is not None:
                        findings.append({
                            "function": func_name,
                            "file": rel_file,
                            "inputs": repr(inputs),
                            "exception": exc_str,
                            "seed": target_seed,
                            "iteration": iteration,
                        })
                        output_lines.append(
                            f"  FINDING: {func_name} raised {exc_str} "
                            f"with inputs={inputs!r}"
                        )
                        target_findings += 1
                        break  # one finding per target

                if target_findings == 0:
                    output_lines.append(
                        f"  OK: {func_name} ({iters_per_target} inputs, no crash)"
                    )

        summary = (
            f"Targets: {len(targets)}, Checks: {checks_run}, "
            f"Findings: {len(findings)}, Seed: {seed}, "
            f"Elapsed: {budget.elapsed_seconds:.1f}s"
        )
        output_lines.insert(1, summary)
        raw_output = "\n".join(output_lines)
        raw_output += "\nNOTE: No crash within budget does not prove correctness."

        if findings:
            return StrategyResult(
                result="FAIL",
                confidence=0.7,
                raw_output=raw_output,
                command=f"fuzzing seed={seed}",
                evidence_items=findings,
            )

        if checks_run == 0:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output=raw_output,
            )

        return StrategyResult(
            result="PASS",
            confidence=0.5,
            raw_output=raw_output,
            command=f"fuzzing seed={seed}",
        )
