"""
Adaptive Evidence Core — evidence package.

Exports: RepositorySnapshot, Claim, Evidence, EvidenceContract,
         EvidenceLedger, EvidenceSufficiencyEvaluator, EvidenceGapAnalyzer
"""
from app.evidence.snapshot import RepositorySnapshot
from app.evidence.claims import Claim, Evidence, EvidenceContract, EvidenceLedger
from app.evidence.sufficiency import EvidenceSufficiencyEvaluator, EvidenceGapAnalyzer

__all__ = [
    "RepositorySnapshot",
    "Claim",
    "Evidence",
    "EvidenceContract",
    "EvidenceLedger",
    "EvidenceSufficiencyEvaluator",
    "EvidenceGapAnalyzer",
]
