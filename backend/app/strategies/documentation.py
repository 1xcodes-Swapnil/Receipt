"""
DocumentationAnalysisStrategy — wraps DocumentationCheckAgent as a strategy.

CRITICAL: This strategy is ADVISORY ONLY.
A FAIL from documentation_check NEVER causes BUG_DETECTED.
It only contributes advisory evidence.
cost=3.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)


class DocumentationAnalysisStrategy(BaseStrategy):
    """
    Check documentation quality.

    ADVISORY ONLY — FAIL from this strategy does NOT cause BUG_DETECTED.
    This preserves the critical invariant that documentation issues are
    informational only (from AGENTS.md / Phase 5 preserved behaviors).
    """

    name = "documentation_analysis"
    cost = 3

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        return True

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            from app.agents import DocumentationCheckAgent
            agent = DocumentationCheckAgent()
            evidence = agent.run(snapshot.repository_path)

            # Documentation check: result is always advisory
            # Map result but preserve the FAIL so callers can treat it as advisory
            if evidence.result == "PASS":
                result = "PASS"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.5
            elif evidence.result == "FAIL":
                # ADVISORY: a FAIL here is informational only
                result = "FAIL"
                confidence = evidence.confidence if evidence.confidence > 0 else 0.4
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
            logger.exception("DocumentationAnalysisStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Strategy exception: {exc}",
            )
