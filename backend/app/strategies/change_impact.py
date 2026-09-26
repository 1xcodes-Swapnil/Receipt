"""
ChangeImpactStrategy — analyzes which files changed and estimates blast radius.

Does not execute code. Produces INSUFFICIENT if there are no changed files.
cost=1 (very cheap, pure analysis).
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)


class ChangeImpactStrategy(BaseStrategy):
    """
    Analyze the scope of changed files to assess risk.

    This is a pure static analysis — no code execution.
    It produces PASS (low impact), INSUFFICIENT (unknown), or FAIL (high risk).
    """

    name = "change_impact"
    cost = 1

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        return True

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            changed = list(snapshot.changed_files)
            all_files = list(snapshot.all_files)

            if not changed:
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output="No changed files detected in snapshot.",
                )

            # Categorize changed files
            py_changed = [f for f in changed if f.endswith(".py")]
            test_changed = [f for f in py_changed
                            if "test" in os.path.basename(f).lower()
                            or "test" in f.replace(os.sep, "/").lower().split("/")[0]]
            src_changed = [f for f in py_changed if f not in test_changed]

            output_lines = [
                f"Changed files: {len(changed)}",
                f"Python changed: {len(py_changed)}",
                f"Test files changed: {len(test_changed)}",
                f"Source files changed: {len(src_changed)}",
                "",
                "Changed files:",
            ] + [f"  {f}" for f in changed[:20]]

            raw_output = "\n".join(output_lines)

            if not py_changed:
                # No Python changes — low risk
                return StrategyResult(
                    result="PASS",
                    confidence=0.5,
                    raw_output=raw_output + "\nNo Python files changed — low risk.",
                )

            # Has Python source changes — needs test execution
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output=raw_output + "\nPython source changes detected — test execution required.",
            )

        except Exception as exc:
            logger.exception("ChangeImpactStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Strategy exception: {exc}",
            )
