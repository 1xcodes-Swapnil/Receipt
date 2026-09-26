"""
CounterexampleShrinkingStrategy — Phase 6.

Starts only from a verified failing generated input.
Minimizes the input while preserving the same failure/property violation.
Records original + minimized counterexample.

EvidenceContract:
  PASS        — minimization successful (smaller reproducer found)
  FAIL        — minimization produced the same failure (recorded)
  INSUFFICIENT — no verified failing input available from context
  ERROR        — unexpected exception (fail-closed)

The minimized case must reproduce the original failure to be valid.

Cost = 4 (relatively cheap — requires a failing input from context)
"""
from __future__ import annotations

import logging
import os
import traceback
from typing import TYPE_CHECKING, Any, Optional

from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.infrastructure import (
    BoundedExecutionContext,
    CounterexampleRecord,
    IsolatedWorkspace,
)

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)

_MAX_SHRINK_STEPS = 40
_MAX_SECONDS = 15.0


# ---------------------------------------------------------------------------
# Shrinking helpers
# ---------------------------------------------------------------------------

def _shrink_inputs(inputs: list) -> list[list]:
    """
    Generate candidate smaller inputs derived from the original.

    Tries removing elements, replacing with simpler values, etc.
    """
    candidates: list[list] = []
    n = len(inputs)

    # Try removing one element at a time
    for i in range(n):
        smaller = inputs[:i] + inputs[i + 1:]
        candidates.append(smaller)

    # Try replacing each element with a simpler value
    for i, val in enumerate(inputs):
        simpler_vals: list[Any] = []
        if isinstance(val, int) and val != 0:
            simpler_vals = [0, 1, -1, val // 2]
        elif isinstance(val, float) and val != 0.0:
            simpler_vals = [0.0, 1.0, -1.0, val / 2]
        elif isinstance(val, str) and val:
            simpler_vals = ["", val[:max(1, len(val) // 2)], "a"]
        elif isinstance(val, list) and val:
            simpler_vals = [[], val[:max(1, len(val) // 2)]]
        elif val is not None:
            simpler_vals = [None]

        for sv in simpler_vals:
            candidate = list(inputs)
            candidate[i] = sv
            candidates.append(candidate)

    return candidates


def _execute_and_check(
    func_name: str, inputs: list, source_root: str, rel_file: str,
    expected_exc_type: Optional[str],
) -> bool:
    """
    Execute func_name(*inputs) and check if it produces the same exception type.

    Returns True if the same failure is reproduced.
    """
    abs_path = os.path.join(source_root, rel_file)
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        ns: dict = {"__builtins__": __builtins__}
        exec(compile(source, abs_path, "exec"), ns)  # noqa: S102
        func = ns.get(func_name)
        if not callable(func):
            return False
        func(*inputs)
        return False  # No exception → not the same failure
    except Exception as exc:  # noqa: BLE001
        exc_name = type(exc).__name__
        if expected_exc_type is None:
            return True  # Any exception counts
        return exc_name == expected_exc_type


class CounterexampleShrinkingStrategy(BaseStrategy):
    """
    Minimize a verified failing input to find the smallest reproducer.

    Only starts from a context-provided failing input.
    Records original + minimized counterexample.
    """

    name = "counterexample_shrinking"
    cost = 4

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        # Only applicable when a failing input is provided in context
        return bool(context.get("failing_input"))

    def prerequisites_met(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> tuple[bool, str]:
        if not context.get("failing_input"):
            return False, "No failing input in context — shrinking requires a verified failure"
        if not context.get("failing_func"):
            return False, "No failing function name in context"
        if not context.get("failing_file"):
            return False, "No failing file in context"
        return True, ""

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            return self._execute_inner(snapshot, context)
        except Exception as exc:
            logger.exception("CounterexampleShrinkingStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"CounterexampleShrinking exception: {exc}\n{traceback.format_exc()}",
            )

    def _execute_inner(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> StrategyResult:
        failing_input: list = context["failing_input"]
        func_name: str = context["failing_func"]
        rel_file: str = context["failing_file"]
        expected_exc: Optional[str] = context.get("expected_exception")
        seed: int = context.get("seed", 0)

        repo_path = snapshot.repository_path
        budget = BoundedExecutionContext(
            max_iterations=_MAX_SHRINK_STEPS,
            max_seconds=_MAX_SECONDS,
        )

        output_lines = [
            f"CounterexampleShrinking: func={func_name}, file={rel_file}",
            f"Original input: {failing_input!r}",
        ]

        with IsolatedWorkspace(repo_path) as ws:
            source_root = os.path.join(ws.root, "source")
            if not os.path.isdir(source_root):
                source_root = ws.root

            # Verify original failure
            original_fails = _execute_and_check(
                func_name, failing_input, source_root, rel_file, expected_exc
            )
            if not original_fails:
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output="\n".join(output_lines)
                    + "\nOriginal input did not reproduce the failure — cannot shrink.",
                )

            # Shrink
            current = list(failing_input)
            steps = 0

            while budget.should_continue():
                candidates = _shrink_inputs(current)
                improved = False

                for candidate in candidates:
                    if not budget.should_continue():
                        break
                    budget.tick()
                    steps += 1

                    if _execute_and_check(
                        func_name, candidate, source_root, rel_file, expected_exc
                    ):
                        # Smaller input still fails → keep it
                        if len(str(candidate)) < len(str(current)):
                            current = candidate
                            improved = True
                            break

                if not improved:
                    break  # Fixed point reached

        record = CounterexampleRecord(
            strategy_name=self.name,
            property_description=f"{func_name}({rel_file})",
            original_input=failing_input,
            minimized_input=current,
            failure_reason=expected_exc or "exception",
            seed=seed,
            is_minimized=current != failing_input,
        )

        output_lines.append(f"Minimized input: {current!r}")
        output_lines.append(f"Shrink steps: {steps}")
        output_lines.append(
            f"Minimized: {'yes' if record.is_minimized else 'no (already minimal)'}"
        )

        return StrategyResult(
            result="PASS" if record.is_minimized else "FAIL",
            confidence=0.8,
            raw_output="\n".join(output_lines),
            command=f"counterexample_shrinking func={func_name}",
            evidence_items=[record.to_dict()],
        )
