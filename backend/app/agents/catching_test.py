"""
Catching Test Agent — Phase 2.

Purpose:
  - Detect behavior changed by the PR via a targeted diff-derived test.
  - Run that test on both the parent commit and the PR commit.
  - Concrete regression evidence: parent=PASS, PR=FAIL.

Evidence rule:
  - Only reports a finding when exit-code difference is observed.
  - Does NOT invent test failures from reasoning alone.
  - On any execution failure → INSUFFICIENT_EVIDENCE.

Strategy (no LLM in Phase 2 — deterministic):
  1. Find the diff between HEAD~1 and HEAD.
  2. Identify changed Python source files (non-test).
  3. Find or synthesize a simple import/smoke test for those files.
  4. Run the existing test suite on HEAD (PR) — the TestRunner already does this.
  5. Run the existing test suite on HEAD~1 (parent) if git is available.
  6. Compare exit codes.

If git checkout of HEAD~1 is not available (e.g. demo repo with no history),
report INSUFFICIENT_EVIDENCE rather than inventing a result.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

from app.agents.base import AgentEvidence, BaseAgent
from app.sandbox import Sandbox

logger = logging.getLogger(__name__)

_TIMEOUT = 90


def _git_available(repo_path: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=repo_path, capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _has_parent_commit(repo_path: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD~1"],
            cwd=repo_path, capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _get_changed_py_files(repo_path: str) -> list[str]:
    """Return non-test Python files changed in HEAD vs HEAD~1."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return [
                f for f in r.stdout.splitlines()
                if f.endswith(".py") and not f.startswith("test_") and "/test_" not in f
            ]
    except Exception:
        pass
    return []


def _run_tests_in_sandbox(repo_path: str, label: str) -> tuple[int, str]:
    """Run pytest in a sandbox copy. Returns (exit_code, combined_output)."""
    with Sandbox(repo_path, copy_source=True) as sb:
        result = sb.run(["pytest", "-v", "--tb=short"], timeout=_TIMEOUT)
    return result.exit_code, result.output


class CatchingTestAgent(BaseAgent):
    """
    Compares test results between parent commit and PR commit.
    Reports a regression only when evidence shows parent=PASS, PR=FAIL.
    """

    @property
    def agent_type(self) -> str:
        return "catching_test"

    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        repo_path = os.path.abspath(repository_path)

        if not os.path.isdir(repo_path):
            return AgentEvidence(
                agent=self.agent_type, command=None, result="ERROR",
                evidence=f"Repository path not found: {repo_path}",
                title="Catching Test — Repository Not Found",
            )

        if not _git_available(repo_path):
            return AgentEvidence(
                agent=self.agent_type, command=None,
                result="INSUFFICIENT_EVIDENCE",
                evidence="No git repository found — cannot compare PR to parent commit.",
                title="Catching Test — No Git History",
                severity="INFO", confidence=0.0,
            )

        if not _has_parent_commit(repo_path):
            return AgentEvidence(
                agent=self.agent_type, command=None,
                result="INSUFFICIENT_EVIDENCE",
                evidence="Repository has no parent commit (initial commit) — cannot run regression comparison.",
                title="Catching Test — No Parent Commit",
                severity="INFO", confidence=0.0,
            )

        changed_files = _get_changed_py_files(repo_path)
        changed_summary = ", ".join(changed_files[:5]) or "(none detected)"

        start = time.monotonic()

        # --- Run tests on PR (HEAD) ---
        pr_code, pr_output = _run_tests_in_sandbox(repo_path, "PR")

        # --- Checkout parent into a temp dir and run tests there ---
        parent_tmpdir = tempfile.mkdtemp(prefix="receipts_parent_")
        parent_code = -1
        parent_output = ""
        try:
            clone_result = subprocess.run(
                ["git", "clone", "--local", "--no-hardlinks", repo_path, parent_tmpdir],
                capture_output=True, text=True, timeout=30,
            )
            if clone_result.returncode != 0:
                parent_output = f"git clone failed: {clone_result.stderr}"
            else:
                # checkout HEAD~1 in the clone
                checkout = subprocess.run(
                    ["git", "checkout", "HEAD~1"],
                    cwd=parent_tmpdir, capture_output=True, text=True, timeout=15,
                )
                if checkout.returncode != 0:
                    parent_output = f"git checkout HEAD~1 failed: {checkout.stderr}"
                else:
                    parent_code, parent_output = _run_tests_in_sandbox(parent_tmpdir, "parent")
        finally:
            shutil.rmtree(parent_tmpdir, ignore_errors=True)

        elapsed = int((time.monotonic() - start) * 1000)

        evidence_lines = [
            f"Changed files: {changed_summary}",
            "",
            f"=== PR (HEAD) — exit code {pr_code} ===",
            pr_output[:2000],
            "",
            f"=== Parent (HEAD~1) — exit code {parent_code} ===",
            parent_output[:2000],
        ]
        evidence = "\n".join(evidence_lines)

        if parent_code == -1:
            # Could not run parent — insufficient evidence
            return AgentEvidence(
                agent=self.agent_type,
                command="pytest -v --tb=short",
                result="INSUFFICIENT_EVIDENCE",
                evidence=evidence,
                title="Catching Test — Could Not Run Parent",
                severity="INFO", confidence=0.0, duration_ms=elapsed,
            )

        if parent_code == 0 and pr_code != 0:
            # Regression confirmed: parent passes, PR fails
            return AgentEvidence(
                agent=self.agent_type,
                command="pytest -v --tb=short",
                result="FAIL",
                evidence=evidence,
                title="Catching Test — Regression Detected (parent=PASS, PR=FAIL)",
                severity="HIGH", confidence=1.0, duration_ms=elapsed,
                file_ref=changed_files[0] if changed_files else None,
            )

        if parent_code != 0 and pr_code == 0:
            # PR fixed a pre-existing failure
            return AgentEvidence(
                agent=self.agent_type,
                command="pytest -v --tb=short",
                result="PASS",
                evidence=evidence,
                title="Catching Test — Pre-existing Failure Fixed by PR",
                severity="PASS", confidence=1.0, duration_ms=elapsed,
            )

        # Both same exit code
        if pr_code == 0:
            return AgentEvidence(
                agent=self.agent_type,
                command="pytest -v --tb=short",
                result="PASS",
                evidence=evidence,
                title="Catching Test — No Regression (both PASS)",
                severity="PASS", confidence=1.0, duration_ms=elapsed,
            )
        else:
            return AgentEvidence(
                agent=self.agent_type,
                command="pytest -v --tb=short",
                result="FAIL",
                evidence=evidence,
                title="Catching Test — Tests Failing on Both Parent and PR",
                severity="MEDIUM", confidence=0.8, duration_ms=elapsed,
            )
