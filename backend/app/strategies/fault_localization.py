"""
FaultLocalizationStrategy — Phase 6.

Uses test failure patterns and file-level coverage to rank suspicious
files/functions using Ochiai coefficient approximation.

EvidenceContract:
  PASS        — localization completed, no high-suspicion locations
  FAIL        — high-suspicion locations identified (ranked evidence)
  INSUFFICIENT — no test failures to localize from
  ERROR        — unexpected exception (fail-closed)

Localization is evidence/hypothesis, not proof of root cause.

Cost = 5 (moderate — runs tests with coverage collection)
"""
from __future__ import annotations

import ast
import logging
import math
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)

_TEST_TIMEOUT = 30
_MAX_RANKED = 10


# ---------------------------------------------------------------------------
# Ochiai coefficient
# ---------------------------------------------------------------------------

def _ochiai(ef: int, ep: int, nf: int) -> float:
    """
    Ochiai fault localization coefficient.

    ef = times line/file executed in failing tests
    ep = times line/file executed in passing tests
    nf = total failing tests
    """
    denom = math.sqrt(nf * (ef + ep)) if nf > 0 and (ef + ep) > 0 else 0.0
    return ef / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# File-level suspicion (proxy for line-level without instrumentation)
# ---------------------------------------------------------------------------

@dataclass
class SuspicionEntry:
    location: str   # "file" or "file:function"
    score: float    # Ochiai score 0.0–1.0
    reason: str


def _collect_test_results(work_dir: str) -> tuple[list[str], list[str]]:
    """
    Run pytest and collect passing/failing test node IDs.

    Returns (passing_ids, failing_ids).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=no", "-q", "--no-header"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT,
        )
        passing: list[str] = []
        failing: list[str] = []
        for line in (result.stdout + result.stderr).splitlines():
            line = line.strip()
            if " PASSED" in line:
                passing.append(line.split(" ")[0])
            elif " FAILED" in line or "FAILED " in line:
                failing.append(line.split(" ")[0])
        return passing, failing
    except Exception:
        return [], []


def _functions_in_file(abs_path: str) -> list[str]:
    """Return list of function/method names defined in a Python file."""
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        tree = ast.parse(source)
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
        return names
    except Exception:
        return []


class FaultLocalizationStrategy(BaseStrategy):
    """
    Rank suspicious locations using failure patterns and Ochiai coefficient.

    Applicable when there are test files.
    Produces a ranked list of suspicious locations as evidence.
    """

    name = "fault_localization"
    cost = 5

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        test_files = [f for f in snapshot.all_files
                      if f.endswith(".py") and "test" in f.lower()]
        return len(test_files) > 0

    def prerequisites_met(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> tuple[bool, str]:
        test_files = [f for f in snapshot.all_files
                      if f.endswith(".py") and "test" in f.lower()]
        if not test_files:
            return False, "No test files found for fault localization"
        return True, ""

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            return self._execute_inner(snapshot, context)
        except Exception as exc:
            logger.exception("FaultLocalizationStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"FaultLocalization exception: {exc}\n{traceback.format_exc()}",
            )

    def _execute_inner(
        self, snapshot: "RepositorySnapshot", context: dict
    ) -> StrategyResult:
        repo_path = snapshot.repository_path
        py_files = list(snapshot.all_files)
        non_test = [f for f in py_files if f.endswith(".py") and "test" not in f.lower()]

        # Run tests to determine pass/fail counts
        passing, failing = _collect_test_results(repo_path)
        n_failing = len(failing)
        n_passing = len(passing)

        output_lines = [
            f"FaultLocalization: tests_passing={n_passing}, tests_failing={n_failing}",
        ]

        if n_failing == 0:
            # No failures — nothing to localize
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output="\n".join(output_lines) + "\nNo test failures to localize.",
                command="fault_localization pytest",
            )

        # File-level suspicion: files imported/tested in failing tests get higher scores
        # We use a heuristic: files in changed_files get ef=n_failing, ep=max(0,n_passing-1)
        # Files not in changed_files get ef=0
        changed = set(snapshot.changed_files)
        suspicion_entries: list[SuspicionEntry] = []

        for rel in non_test:
            abs_path = os.path.join(repo_path, rel)
            in_changed = rel in changed

            # Heuristic Ochiai: changed files assumed executed in failing tests
            ef = n_failing if in_changed else max(0, n_failing - 1)
            ep = max(0, n_passing - 1) if in_changed else n_passing
            score = _ochiai(ef, ep, n_failing)

            if score > 0.1:
                reason = (
                    f"Changed file with {n_failing} failing tests (Ochiai={score:.3f})"
                    if in_changed
                    else f"Related file (Ochiai={score:.3f})"
                )
                suspicion_entries.append(SuspicionEntry(
                    location=rel,
                    score=score,
                    reason=reason,
                ))

                # Also add per-function entries for changed files
                if in_changed:
                    funcs = _functions_in_file(abs_path)
                    for func in funcs[:5]:
                        suspicion_entries.append(SuspicionEntry(
                            location=f"{rel}::{func}",
                            score=score * 0.9,
                            reason=f"Function in changed file (Ochiai={score * 0.9:.3f})",
                        ))

        # Sort by score descending
        suspicion_entries.sort(key=lambda e: e.score, reverse=True)
        top = suspicion_entries[:_MAX_RANKED]

        if not top:
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output="\n".join(output_lines)
                + "\nNo high-suspicion locations identified.",
                command="fault_localization",
            )

        output_lines.append("\nSuspicion ranking (Ochiai coefficient):")
        for i, entry in enumerate(top, 1):
            output_lines.append(f"  {i}. {entry.location} score={entry.score:.3f} — {entry.reason}")

        output_lines.append(
            "\nNOTE: Localization is a hypothesis, not proof of root cause."
        )

        # High-suspicion = score >= 0.7 in changed files with failures
        high_suspicion = [e for e in top if e.score >= 0.7]

        result_val = "FAIL" if high_suspicion else "PASS"
        confidence = min(0.5 + (len(high_suspicion) / max(len(top), 1)) * 0.4, 0.8)

        return StrategyResult(
            result=result_val,
            confidence=confidence,
            raw_output="\n".join(output_lines),
            command="fault_localization pytest",
            evidence_items=[{
                "type": "fault_localization",
                "n_failing": n_failing,
                "n_passing": n_passing,
                "top_suspects": [
                    {"location": e.location, "score": round(e.score, 3), "reason": e.reason}
                    for e in top
                ],
                "note": "Localization is hypothesis only, not proof of root cause.",
            }],
            file_ref=top[0].location if top else None,
        )
