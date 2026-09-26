"""
Evidence claims — structured evidence objects for the adaptive planner.

Claim       — something we want to prove/disprove about the repository
Evidence    — a single piece of evidence addressing a claim
EvidenceContract — contract / expectation on what a strategy should produce
EvidenceLedger   — collection of evidence, with conflict/dependency detection
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """
    A claim is something the planner is trying to establish or refute.

    claim_type : e.g. "code_correctness", "test_coverage", "documentation"
    claim_text : human-readable description
    verdict_contribution: "AUTHORITATIVE" | "ADVISORY" | "NONE"
    """
    claim_id: str
    claim_type: str
    claim_text: str
    verdict_contribution: str = "AUTHORITATIVE"
    status: str = "OPEN"  # OPEN | SUPPORTED | REFUTED | INSUFFICIENT | CONFLICTED

    @classmethod
    def create(
        cls,
        claim_type: str,
        claim_text: str,
        verdict_contribution: str = "AUTHORITATIVE",
    ) -> "Claim":
        return cls(
            claim_id=str(uuid.uuid4()),
            claim_type=claim_type,
            claim_text=claim_text,
            verdict_contribution=verdict_contribution,
        )


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """
    A single piece of evidence, produced by a strategy, addressing a claim.

    result       : PASS | FAIL | INSUFFICIENT | CONFLICT | ERROR
    confidence   : 0.0–1.0
    is_independent: False if derived from another piece of evidence
    depends_on   : evidence_id this depends on (if not independent)
    """
    evidence_id: str
    strategy_name: str
    claim_id: Optional[str]
    result: str           # PASS | FAIL | INSUFFICIENT | CONFLICT | ERROR
    confidence: float
    raw_output: str
    command: Optional[str] = None
    file_ref: Optional[str] = None
    line_ref: Optional[int] = None
    is_independent: bool = True
    depends_on: Optional[str] = None

    @classmethod
    def create(
        cls,
        strategy_name: str,
        claim_id: Optional[str],
        result: str,
        confidence: float,
        raw_output: str,
        command: Optional[str] = None,
        file_ref: Optional[str] = None,
        line_ref: Optional[int] = None,
        is_independent: bool = True,
        depends_on: Optional[str] = None,
    ) -> "Evidence":
        return cls(
            evidence_id=str(uuid.uuid4()),
            strategy_name=strategy_name,
            claim_id=claim_id,
            result=result,
            confidence=confidence,
            raw_output=raw_output,
            command=command,
            file_ref=file_ref,
            line_ref=line_ref,
            is_independent=is_independent,
            depends_on=depends_on,
        )


# ---------------------------------------------------------------------------
# EvidenceContract
# ---------------------------------------------------------------------------

@dataclass
class EvidenceContract:
    """
    What a strategy is expected to produce for a given claim.
    Used by the sufficiency evaluator to determine if a gap exists.
    """
    claim_id: str
    required_result: str          # PASS | FAIL | INSUFFICIENT
    min_confidence: float = 0.5
    strategy_name: Optional[str] = None


# ---------------------------------------------------------------------------
# EvidenceLedger
# ---------------------------------------------------------------------------

class EvidenceLedger:
    """
    Accumulates evidence across strategy executions.

    Key guarantees:
    - Tracks which claim each piece addresses
    - Detects contradictions (PASS + FAIL for same claim from independent sources)
    - Does NOT inflate confidence by counting dependent evidence twice
    """

    def __init__(self) -> None:
        self._items: list[Evidence] = []

    def add(self, evidence: Evidence) -> None:
        self._items.append(evidence)

    @property
    def items(self) -> list[Evidence]:
        return list(self._items)

    def for_claim(self, claim_id: str) -> list[Evidence]:
        return [e for e in self._items if e.claim_id == claim_id]

    def independent_for_claim(self, claim_id: str) -> list[Evidence]:
        return [e for e in self.for_claim(claim_id) if e.is_independent]

    def has_contradiction(self, claim_id: str) -> bool:
        """True if independent evidence for a claim has both PASS and FAIL results."""
        independent = self.independent_for_claim(claim_id)
        results = {e.result for e in independent}
        return "PASS" in results and "FAIL" in results

    def best_confidence(self, claim_id: str) -> float:
        """
        Return the maximum confidence from INDEPENDENT evidence only.
        Dependent evidence is intentionally excluded to prevent inflation.
        """
        independent = self.independent_for_claim(claim_id)
        if not independent:
            return 0.0
        return max(e.confidence for e in independent)

    def claim_result(self, claim_id: str) -> str:
        """
        Derive the overall result for a claim from accumulated evidence.

        Returns: PASS | FAIL | INSUFFICIENT | CONFLICT
        """
        independent = self.independent_for_claim(claim_id)
        if not independent:
            return "INSUFFICIENT"
        if self.has_contradiction(claim_id):
            return "CONFLICT"
        results = {e.result for e in independent}
        if "FAIL" in results:
            return "FAIL"
        if "PASS" in results:
            return "PASS"
        if "INSUFFICIENT" in results:
            return "INSUFFICIENT"
        return "INSUFFICIENT"

    def all_claims_resolved(self, claims: list[Claim]) -> bool:
        """True if every authoritative claim has PASS or FAIL (not INSUFFICIENT/CONFLICT)."""
        for claim in claims:
            if claim.verdict_contribution == "NONE":
                continue
            result = self.claim_result(claim.claim_id)
            if result in ("INSUFFICIENT", "CONFLICT"):
                return False
        return True
