"""
Base interface for all Receipts agents.

Phase 2+ agents (CatchingTest, DocumentationCheck, HistoryCheck) must implement this interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AgentEvidence:
    """
    Structured evidence produced by an agent.
    This is the canonical receipt payload before DB persistence.
    """
    agent: str
    command: Optional[str]
    result: str            # "PASS" | "FAIL" | "ERROR" | "TIMEOUT" | "INSUFFICIENT_EVIDENCE"
    evidence: str          # Real stdout/stderr — never invented
    exit_code: Optional[int] = None
    file_ref: Optional[str] = None
    severity: str = "INFO"
    confidence: float = 0.0
    duration_ms: Optional[int] = None
    title: str = "Agent Result"
    test_ref: Optional[str] = None


class BaseAgent(abc.ABC):
    """All agents must implement run()."""

    @property
    @abc.abstractmethod
    def agent_type(self) -> str:
        """Return the AgentTypeEnum value string."""
        ...

    @abc.abstractmethod
    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        """
        Execute the agent against the given repository path.

        Must never return invented results.
        Must capture real command output.
        On exception: return AgentEvidence with result="ERROR".
        """
        ...
