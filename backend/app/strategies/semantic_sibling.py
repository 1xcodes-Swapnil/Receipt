"""
SemanticSiblingAnalysisStrategy — Phase 6.

Find structurally/semantically similar code using AST/structural analysis.
Excludes original location. Ranks candidates by similarity score.

EvidenceContract:
  PASS        — analysis completed, candidates returned as POTENTIAL_MATCH
  FAIL        — not used (analysis is always evidence/hypothesis)
  INSUFFICIENT — no source files or no comparable code found
  ERROR        — unexpected exception (fail-closed)

Never marks a sibling as a confirmed defect without independent verification.
Candidates are returned as POTENTIAL_MATCH only.

Cost = 4 (cheap — pure AST analysis, no execution)
"""
from __future__ import annotations

import ast
import logging
import os
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)

_MAX_FUNCTIONS = 50
_MAX_CANDIDATES = 10
_SIMILARITY_THRESHOLD = 0.4


# ---------------------------------------------------------------------------
# AST fingerprinting
# ---------------------------------------------------------------------------

@dataclass
class FunctionSignature:
    """Structural fingerprint of a function."""
    name: str
    file: str
    lineno: int
    n_args: int
    n_statements: int
    n_returns: int
    n_calls: int
    has_loops: bool
    has_conditions: bool
    arg_names: tuple

    def similarity(self, other: "FunctionSignature") -> float:
        """
        Compute structural similarity score 0.0–1.0.

        Based on normalized feature matching.
        """
        if self.file == other.file and self.name == other.name:
            return 0.0  # Same function — not a sibling

        scores = []

        # Argument count similarity
        max_args = max(self.n_args, other.n_args, 1)
        scores.append(1.0 - abs(self.n_args - other.n_args) / max_args)

        # Statement count similarity (within 50%)
        max_stmts = max(self.n_statements, other.n_statements, 1)
        stmt_diff = abs(self.n_statements - other.n_statements) / max_stmts
        scores.append(max(0.0, 1.0 - stmt_diff))

        # Return count similarity
        max_ret = max(self.n_returns, other.n_returns, 1)
        scores.append(1.0 - abs(self.n_returns - other.n_returns) / max_ret)

        # Structural pattern match
        if self.has_loops == other.has_loops:
            scores.append(1.0)
        else:
            scores.append(0.0)

        if self.has_conditions == other.has_conditions:
            scores.append(1.0)
        else:
            scores.append(0.5)

        # Name similarity (prefix/suffix match)
        common = len(os.path.commonprefix([self.name, other.name]))
        max_name = max(len(self.name), len(other.name), 1)
        scores.append(common / max_name)

        return sum(scores) / len(scores)


def _fingerprint_function(node: ast.FunctionDef, rel_file: str) -> FunctionSignature:
    """Extract structural fingerprint from a function AST node."""
    n_stmts = 0
    n_returns = 0
    n_calls = 0
    has_loops = False
    has_conditions = False

    for child in ast.walk(node):
        if isinstance(child, ast.stmt):
            n_stmts += 1
        if isinstance(child, ast.Return):
            n_returns += 1
        if isinstance(child, ast.Call):
            n_calls += 1
        if isinstance(child, (ast.For, ast.While)):
            has_loops = True
        if isinstance(child, ast.If):
            has_conditions = True

    args = [a.arg for a in node.args.args if a.arg != "self"]
    return FunctionSignature(
        name=node.name,
        file=rel_file,
        lineno=node.lineno,
        n_args=len(args),
        n_statements=n_stmts,
        n_returns=n_returns,
        n_calls=n_calls,
        has_loops=has_loops,
        has_conditions=has_conditions,
        arg_names=tuple(args),
    )


def _extract_all_signatures(repo_path: str, py_files: list[str]) -> list[FunctionSignature]:
    """Extract function signatures from all Python files."""
    sigs: list[FunctionSignature] = []
    for rel in py_files:
        abs_path = os.path.join(repo_path, rel)
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.startswith("__"):
                        sigs.append(_fingerprint_function(node, rel))
                if len(sigs) >= _MAX_FUNCTIONS:
                    return sigs
        except (SyntaxError, OSError):
            continue
    return sigs


@dataclass
class SiblingCandidate:
    """A candidate sibling with similarity score."""
    location: str   # "file::function"
    file: str
    function_name: str
    lineno: int
    score: float
    reason: str
    status: str = "POTENTIAL_MATCH"  # Never CONFIRMED without independent verification


class SemanticSiblingAnalysisStrategy(BaseStrategy):
    """
    Find structurally similar functions using AST analysis.

    Returns candidates as POTENTIAL_MATCH only.
    Never marks as confirmed defect.
    """

    name = "semantic_sibling_analysis"
    cost = 4

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        py_files = [f for f in snapshot.all_files if f.endswith(".py")]
        return len(py_files) >= 2  # Need at least 2 files to find siblings

    def prerequisites_met(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> tuple[bool, str]:
        py_files = [f for f in snapshot.all_files if f.endswith(".py")]
        if len(py_files) < 2:
            return False, "Need at least 2 Python files for sibling analysis"
        return True, ""

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            return self._execute_inner(snapshot, context)
        except Exception as exc:
            logger.exception("SemanticSiblingAnalysisStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"SemanticSiblingAnalysis exception: {exc}\n{traceback.format_exc()}",
            )

    def _execute_inner(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> StrategyResult:
        repo_path = snapshot.repository_path
        py_files = list(snapshot.all_files)
        changed_files = set(snapshot.changed_files)

        # Extract signatures from all files
        all_sigs = _extract_all_signatures(repo_path, py_files)
        if not all_sigs:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output="SemanticSiblingAnalysis: no function signatures found.",
            )

        # Focus on changed files as "origin" functions
        origin_sigs = [s for s in all_sigs if s.file in changed_files]
        if not origin_sigs:
            # Fall back to all functions if no changed files
            origin_sigs = all_sigs

        output_lines = [
            f"SemanticSiblingAnalysis: {len(all_sigs)} functions analyzed, "
            f"{len(origin_sigs)} origin functions"
        ]

        # Find siblings for each origin
        candidates: list[SiblingCandidate] = []
        seen: set[str] = set()

        for origin in origin_sigs[:5]:  # Limit origins for performance
            for other in all_sigs:
                if other.file == origin.file and other.name == origin.name:
                    continue  # Skip self
                key = f"{other.file}::{other.name}"
                if key in seen:
                    continue

                score = origin.similarity(other)
                if score >= _SIMILARITY_THRESHOLD:
                    candidates.append(SiblingCandidate(
                        location=key,
                        file=other.file,
                        function_name=other.name,
                        lineno=other.lineno,
                        score=score,
                        reason=(
                            f"Similar to {origin.name} in {origin.file} "
                            f"(args={other.n_args}, stmts={other.n_statements}, "
                            f"score={score:.3f})"
                        ),
                    ))
                    seen.add(key)

        if not candidates:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output="\n".join(output_lines)
                + "\nNo structurally similar functions found above threshold.",
            )

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        top = candidates[:_MAX_CANDIDATES]

        output_lines.append(f"\nSibling candidates (POTENTIAL_MATCH only):")
        for i, c in enumerate(top, 1):
            output_lines.append(
                f"  {i}. {c.location} score={c.score:.3f} — {c.reason}"
            )

        output_lines.append(
            "\nNOTE: Candidates are POTENTIAL_MATCH only. "
            "Independent verification required before treating as defect."
        )

        return StrategyResult(
            result="PASS",  # Analysis completed — POTENTIAL_MATCH is not FAIL
            confidence=0.5,
            raw_output="\n".join(output_lines),
            command="semantic_sibling_analysis ast",
            evidence_items=[{
                "type": "semantic_sibling_analysis",
                "candidates": [
                    {
                        "location": c.location,
                        "score": round(c.score, 3),
                        "reason": c.reason,
                        "status": c.status,
                    }
                    for c in top
                ],
                "note": "POTENTIAL_MATCH only — not confirmed defects.",
            }],
            file_ref=top[0].location if top else None,
        )
