"""
Evidence Sufficiency Evaluator and Gap Analyzer.

EvidenceSufficiencyEvaluator — decides whether the ledger has enough evidence
                                to resolve all claims
EvidenceGapAnalyzer          — identifies specific gaps in evidence
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.evidence.claims import Claim, EvidenceLedger


# ---------------------------------------------------------------------------
# Gap descriptor
# ---------------------------------------------------------------------------

@dataclass
class GapDescriptor:
    """
    Describes a specific gap in the evidence.

    gap_type          : MISSING | CONFLICTING | STALE | FAILED_STRATEGY
    claim_id          : which claim has the gap (if applicable)
    description       : human-readable explanation
    suggested_strategy: strategy that could fill the gap
    """
    gap_type: str
    claim_id: Optional[str]
    description: str
    suggested_strategy: Optional[str] = None


# ---------------------------------------------------------------------------
# EvidenceSufficiencyEvaluator
# ---------------------------------------------------------------------------

class EvidenceSufficiencyEvaluator:
    """
    Evaluates whether the accumulated evidence is sufficient to render a verdict.

    Rules:
    - All AUTHORITATIVE claims must be PASS or FAIL (not INSUFFICIENT or CONFLICT)
    - At least one piece of independent evidence must exist
    - Contradictions (CONFLICT) are never sufficient
    """

    def is_sufficient(self, ledger: EvidenceLedger, claims: list[Claim]) -> bool:
        """Return True if evidence is sufficient to resolve all authoritative claims."""
        authoritative = [c for c in claims if c.verdict_contribution == "AUTHORITATIVE"]
        if not authoritative:
            return False
        independent_items = [e for e in ledger.items if e.is_independent]
        if not independent_items:
            return False
        for claim in authoritative:
            result = ledger.claim_result(claim.claim_id)
            if result in ("INSUFFICIENT", "CONFLICT"):
                return False
        return True

    def overall_result(self, ledger: EvidenceLedger, claims: list[Claim]) -> str:
        """
        Return the aggregate evidence result.

        PASS         — all authoritative claims pass
        FAIL         — any authoritative claim fails
        INSUFFICIENT — any authoritative claim is unresolved
        CONFLICT     — any authoritative claim has conflicting evidence
        """
        authoritative = [c for c in claims if c.verdict_contribution == "AUTHORITATIVE"]
        if not authoritative:
            return "INSUFFICIENT"
        results = {ledger.claim_result(c.claim_id) for c in authoritative}
        if "CONFLICT" in results:
            return "CONFLICT"
        if "INSUFFICIENT" in results:
            return "INSUFFICIENT"
        if "FAIL" in results:
            return "FAIL"
        return "PASS"


# ---------------------------------------------------------------------------
# EvidenceGapAnalyzer
# ---------------------------------------------------------------------------

class EvidenceGapAnalyzer:
    """
    Identifies specific gaps in the evidence ledger.

    Used by the StrategyPlanner to decide which strategy to try next.
    """

    def find_gaps(
        self,
        ledger: EvidenceLedger,
        claims: list[Claim],
        attempted_strategies: Optional[list[str]] = None,
    ) -> list[GapDescriptor]:
        """
        Return a list of gaps in the evidence.

        attempted_strategies: strategies already tried (to suggest alternatives)
        """
        attempted = set(attempted_strategies or [])
        gaps: list[GapDescriptor] = []

        for claim in claims:
            if claim.verdict_contribution == "NONE":
                continue
            result = ledger.claim_result(claim.claim_id)
            if result == "INSUFFICIENT":
                # Check if any strategy was tried and failed
                items_for_claim = ledger.for_claim(claim.claim_id)
                failed_strats = {e.strategy_name for e in items_for_claim if e.result in ("INSUFFICIENT", "ERROR")}
                if failed_strats and failed_strats.issubset(attempted):
                    gaps.append(GapDescriptor(
                        gap_type="FAILED_STRATEGY",
                        claim_id=claim.claim_id,
                        description=f"Claim '{claim.claim_text}' — all attempted strategies insufficient: {failed_strats}",
                        suggested_strategy=None,
                    ))
                else:
                    gaps.append(GapDescriptor(
                        gap_type="MISSING",
                        claim_id=claim.claim_id,
                        description=f"No sufficient evidence for claim: {claim.claim_text}",
                        suggested_strategy="existing_tests",
                    ))
            elif result == "CONFLICT":
                gaps.append(GapDescriptor(
                    gap_type="CONFLICTING",
                    claim_id=claim.claim_id,
                    description=f"Conflicting evidence for claim: {claim.claim_text}",
                    suggested_strategy="targeted_testing",
                ))

        return gaps

    def has_gaps(
        self,
        ledger: EvidenceLedger,
        claims: list[Claim],
        attempted_strategies: Optional[list[str]] = None,
    ) -> bool:
        return len(self.find_gaps(ledger, claims, attempted_strategies)) > 0
