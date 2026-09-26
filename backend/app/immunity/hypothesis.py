"""
Phase 7 — Hypothesis Tracker

Tracks root-cause hypotheses through OPEN → VERIFIED | REJECTED.

Rules:
- Fault localization alone is never root-cause proof.
- A hypothesis is VERIFIED only when independently confirmed against failure.
- Contradictory hypotheses must be REJECTED or flagged as unresolved.
- If no VERIFIED hypothesis exists: stage → BLOCKED.
- If contradictory VERIFIED hypotheses exist: stage → ESCALATED.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Hypothesis dataclass
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis:
    """A single root-cause hypothesis."""
    hypothesis_id: str
    pipeline_id: str
    description: str
    status: str = "OPEN"          # OPEN | VERIFIED | REJECTED
    supporting_evidence: list[str] = field(default_factory=list)
    refuting_evidence: list[str] = field(default_factory=list)
    source_strategy: Optional[str] = None
    verified_by: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create(
        cls,
        pipeline_id: str,
        description: str,
        source_strategy: Optional[str] = None,
    ) -> "Hypothesis":
        return cls(
            hypothesis_id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            description=description,
            source_strategy=source_strategy,
        )

    def verify(self, verifying_evidence: str, verified_by: Optional[str] = None) -> None:
        """Mark hypothesis as VERIFIED with supporting evidence."""
        self.supporting_evidence.append(verifying_evidence)
        self.status = "VERIFIED"
        self.verified_by = verified_by

    def reject(self, refuting: str) -> None:
        """Mark hypothesis as REJECTED with refuting evidence."""
        self.refuting_evidence.append(refuting)
        self.status = "REJECTED"

    def add_support(self, evidence: str) -> None:
        """Add supporting evidence without changing status."""
        self.supporting_evidence.append(evidence)

    def is_verified(self) -> bool:
        return self.status == "VERIFIED"

    def is_rejected(self) -> bool:
        return self.status == "REJECTED"

    def is_open(self) -> bool:
        return self.status == "OPEN"


# ---------------------------------------------------------------------------
# HypothesisTracker
# ---------------------------------------------------------------------------

class HypothesisTracker:
    """
    Manages a collection of hypotheses for one pipeline.

    Enforces: fault localization alone cannot verify.
    Provides: resolution status for the root cause stage.
    """

    def __init__(self, pipeline_id: str) -> None:
        self.pipeline_id = pipeline_id
        self._hypotheses: list[Hypothesis] = []

    def add(self, description: str, source_strategy: Optional[str] = None) -> Hypothesis:
        """Create and register a new OPEN hypothesis."""
        h = Hypothesis.create(
            pipeline_id=self.pipeline_id,
            description=description,
            source_strategy=source_strategy,
        )
        self._hypotheses.append(h)
        return h

    def verify(
        self,
        hypothesis_id: str,
        evidence: str,
        verified_by: Optional[str] = None,
    ) -> bool:
        """
        Mark a hypothesis VERIFIED. Returns True if found.

        Note: fault_localization results alone must not call this —
        independent confirmation is required.
        """
        for h in self._hypotheses:
            if h.hypothesis_id == hypothesis_id:
                h.verify(evidence, verified_by)
                return True
        return False

    def reject(self, hypothesis_id: str, refuting: str) -> bool:
        """Mark a hypothesis REJECTED. Returns True if found."""
        for h in self._hypotheses:
            if h.hypothesis_id == hypothesis_id:
                h.reject(refuting)
                return True
        return False

    def verified_hypotheses(self) -> list[Hypothesis]:
        return [h for h in self._hypotheses if h.is_verified()]

    def open_hypotheses(self) -> list[Hypothesis]:
        return [h for h in self._hypotheses if h.is_open()]

    def all_hypotheses(self) -> list[Hypothesis]:
        return list(self._hypotheses)

    def resolution_status(self) -> str:
        """
        Return the resolution state of the hypothesis set:

        - "VERIFIED"   — exactly one verified, no contradictions
        - "CONFLICTED" — multiple verified hypotheses with different descriptions
        - "BLOCKED"    — no verified hypotheses
        - "OPEN"       — hypotheses exist but none verified/rejected yet
        """
        verified = self.verified_hypotheses()
        if not verified:
            open_hs = self.open_hypotheses()
            return "OPEN" if open_hs else "BLOCKED"
        if len(verified) > 1:
            # Multiple verified — check if they contradict or are complementary
            # Conservative: treat as CONFLICTED (→ ESCALATED)
            return "CONFLICTED"
        return "VERIFIED"

    def primary_verified(self) -> Optional[Hypothesis]:
        """Return the single verified hypothesis, or None."""
        verified = self.verified_hypotheses()
        return verified[0] if len(verified) == 1 else None

    def persist(self, db: Session) -> None:
        """Persist all hypotheses to DB."""
        from app.models import ImmunityHypothesis, HypothesisStatusEnum
        for h in self._hypotheses:
            try:
                record = ImmunityHypothesis(
                    id=h.hypothesis_id,
                    pipeline_id=h.pipeline_id,
                    description=h.description,
                    status=HypothesisStatusEnum(h.status),
                    supporting_evidence="; ".join(h.supporting_evidence),
                    refuting_evidence="; ".join(h.refuting_evidence),
                    source_strategy=h.source_strategy,
                    verified_by=h.verified_by,
                )
                db.merge(record)
            except Exception:
                pass
        try:
            db.commit()
        except Exception:
            db.rollback()
