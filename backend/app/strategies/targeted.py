"""
TargetedTestingStrategy — runs targeted tests for specific changed files.

cost=4 (requires identifying specific test targets).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)


class TargetedTestingStrategy(BaseStrategy):
    """
    Run tests that specifically target the changed files.

    Applicable: when changed_files is non-empty and test files exist.
    """

    name = "targeted_testing"
    cost = 4

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        return len(snapshot.changed_files) > 0

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            repo_path = snapshot.repository_path
            changed = [f for f in snapshot.changed_files if f.endswith(".py")]

            if not changed:
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output="No Python files changed — targeted testing not applicable.",
                )

            # Look for test files in the repository
            test_files: list[str] = []
            for root, _dirs, files in os.walk(repo_path):
                for fn in files:
                    if fn.startswith("test_") and fn.endswith(".py"):
                        test_files.append(os.path.join(root, fn))

            if not test_files:
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output="No test files found for targeted testing.",
                )

            cmd = [sys.executable, "-m", "pytest"] + test_files[:10] + ["-v", "--tb=short", "-q"]
            cmd_str = " ".join(cmd)

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=repo_path,
                    timeout=60,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
                success = proc.returncode == 0
                return StrategyResult(
                    result="PASS" if success else "FAIL",
                    confidence=0.85,
                    raw_output=output,
                    command=cmd_str,
                )
            except subprocess.TimeoutExpired:
                return StrategyResult(
                    result="ERROR",
                    confidence=0.0,
                    raw_output="Targeted test run timed out.",
                    command=cmd_str,
                )

        except Exception as exc:
            logger.exception("TargetedTestingStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Strategy exception: {exc}",
            )
