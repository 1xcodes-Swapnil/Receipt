"""
Agent stubs for Phase 2+.
These classes implement the BaseAgent interface but are not active in Phase 1.
"""
from __future__ import annotations

from typing import Optional

from app.agents.base import AgentEvidence, BaseAgent


class CatchingTestAgent(BaseAgent):
    """Phase 2+ — generates a targeted test to catch the reported bug."""

    @property
    def agent_type(self) -> str:
        return "catching_test"

    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        return AgentEvidence(
            agent=self.agent_type,
            command=None,
            result="INSUFFICIENT_EVIDENCE",
            evidence="CatchingTestAgent is not implemented in Phase 1.",
            severity="INFO",
            confidence=0.0,
            title="Catching Test — Not Implemented (Phase 2+)",
        )


class DocumentationCheckAgent(BaseAgent):
    """Phase 2+ — checks documentation consistency."""

    @property
    def agent_type(self) -> str:
        return "documentation_check"

    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        return AgentEvidence(
            agent=self.agent_type,
            command=None,
            result="INSUFFICIENT_EVIDENCE",
            evidence="DocumentationCheckAgent is not implemented in Phase 1.",
            severity="INFO",
            confidence=0.0,
            title="Documentation Check — Not Implemented (Phase 2+)",
        )


class HistoryCheckAgent(BaseAgent):
    """Phase 2+ — checks commit history for related issues."""

    @property
    def agent_type(self) -> str:
        return "history_check"

    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        return AgentEvidence(
            agent=self.agent_type,
            command=None,
            result="INSUFFICIENT_EVIDENCE",
            evidence="HistoryCheckAgent is not implemented in Phase 1.",
            severity="INFO",
            confidence=0.0,
            title="History Check — Not Implemented (Phase 2+)",
        )
