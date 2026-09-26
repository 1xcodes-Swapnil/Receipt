"""
ChangeFailureAnalyzer — deterministic analysis of a snapshot to identify
what kinds of claims need to be established.

No external LLM. No speculation. Only examines the snapshot structure.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from app.evidence.claims import Claim

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot


class ChangeFailureAnalyzer:
    """
    Analyzes a RepositorySnapshot to determine what claims need to be proven.

    Returns a list of Claim objects that the planner will try to resolve.

    Deterministic: same snapshot → same claims.
    """

    def analyze(self, snapshot: "RepositorySnapshot") -> list[Claim]:
        """
        Generate claims based on snapshot analysis.

        Always generates a code_correctness claim.
        May generate test_coverage and documentation claims.
        """
        claims: list[Claim] = []

        # Always: code correctness is authoritative
        claims.append(Claim.create(
            claim_type="code_correctness",
            claim_text="The code changes do not introduce regressions or bugs.",
            verdict_contribution="AUTHORITATIVE",
        ))

        # If Python files exist, check test coverage
        py_files = [f for f in snapshot.all_files if f.endswith(".py")]
        if py_files:
            test_files = [f for f in py_files
                          if "test" in os.path.basename(f).lower()]
            if test_files:
                claims.append(Claim.create(
                    claim_type="test_coverage",
                    claim_text="Existing tests provide sufficient coverage of changed code.",
                    verdict_contribution="AUTHORITATIVE",
                ))

        # Documentation is advisory only
        claims.append(Claim.create(
            claim_type="documentation",
            claim_text="Documentation is present and up to date.",
            verdict_contribution="ADVISORY",
        ))

        return claims
