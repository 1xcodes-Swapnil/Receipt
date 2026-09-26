"""
HistoryAnalysisStrategy — wraps HistoryCheckAgent as a strategy.

Advisory only — FAIL from this strategy never causes BUG_DETECTED.
cost=5 (requires git history access).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)


class HistoryAnalysisStrategy(BaseStrategy):
    """
    Analyze git history for relevant bug patterns.

    This is an advisory strategy — its FAIL result contributes advisory
    evidence only and does NOT directly cause BUG_DETECTED.
    """

    name = "history_analysis"
    cost = 5

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        return True

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            from app.agents import HistoryCheckAgent
            agent = HistoryCheckAgent()
            evidence = agent.run(snapshot.repository_path)

            if evidence.result == "PASS":
                result = "PASS"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.6
            elif evidence.result == "FAIL":
                result = "FAIL"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.6
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
            logger.exception("HistoryAnalysisStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Strategy exception: {exc}",
            )
