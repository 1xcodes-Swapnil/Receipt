"""
DifferentialTestingStrategy — wraps CatchingTestAgent as a strategy.

cost=3 (slightly more expensive than existing tests — generates new tests).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)


class DifferentialTestingStrategy(BaseStrategy):
    """
    Run the CatchingTest agent to generate differential tests.

    Applicable: when existing tests alone are INSUFFICIENT.
    """

    name = "differential_testing"
    cost = 3

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        return True

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            from app.agents import CatchingTestAgent
            agent = CatchingTestAgent()
            evidence = agent.run(snapshot.repository_path)

            if evidence.result == "PASS":
                result = "PASS"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.8
            elif evidence.result == "FAIL":
                result = "FAIL"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.8
            elif evidence.result == "INSUFFICIENT_EVIDENCE":
                result = "INSUFFICIENT"
                confidence = 0.0
            else:
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
            logger.exception("DifferentialTestingStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Strategy exception: {exc}",
            )
