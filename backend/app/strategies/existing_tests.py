"""
ExistingTestsStrategy — runs the existing test suite against the repository.

Wraps the existing TestRunner agent as a strategy.
cost=2 (cheapest execution — already have the tests).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)


class ExistingTestsStrategy(BaseStrategy):
    """
    Run the existing test suite via TestRunner agent.

    Applicable: always (cost=2, try this first).
    PASS → tests pass (PASS evidence)
    FAIL → tests fail (FAIL evidence)
    No tests found → INSUFFICIENT evidence
    """

    name = "existing_tests"
    cost = 2

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        return True

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            from app.agents import TestRunner
            agent = TestRunner()
            evidence = agent.run(snapshot.repository_path)

            # Map agent result to strategy result
            if evidence.result == "PASS":
                result = "PASS"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.9
            elif evidence.result == "FAIL":
                result = "FAIL"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.9
            elif evidence.result == "INSUFFICIENT_EVIDENCE":
                result = "INSUFFICIENT"
                confidence = 0.0
            else:
                # ERROR or TIMEOUT
                result = "ERROR"
                confidence = 0.0

            return StrategyResult(
                result=result,
                confidence=confidence,
                raw_output=evidence.evidence or "",
                command=evidence.command,
                file_ref=evidence.file_ref,
            )
        except Exception as exc:
            logger.exception("ExistingTestsStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Strategy exception: {exc}",
            )
