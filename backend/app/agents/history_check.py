"""
History Check Agent — Phase 2.

Inspects Git history for modified files in the PR.

Looks for:
  - Previous fixes to the same files (commit messages containing fix/hotfix/revert)
  - Files that have been modified many times recently (churn)
  - Reverts

History context is INFORMATIONAL only — it does not create a BUG finding.
A BUG requires concrete execution evidence from another agent.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Optional

from app.agents.base import AgentEvidence, BaseAgent

logger = logging.getLogger(__name__)

_FIX_PATTERNS = re.compile(
    r"\b(fix|hotfix|bugfix|revert|regression|broken|crash|error)\b",
    re.IGNORECASE,
)
_HIGH_CHURN_THRESHOLD = 5   # commits to the same file in last 90 days


def _git_log_file(repo_path: str, filepath: str, max_commits: int = 20) -> list[dict]:
    """Return last N commits touching filepath."""
    try:
        r = subprocess.run(
            ["git", "log", f"-{max_commits}", "--pretty=format:%H|%s|%ad", "--date=short",
             "--follow", "--", filepath],
            cwd=repo_path, capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return []
        commits = []
        for line in r.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"sha": parts[0][:8], "subject": parts[1], "date": parts[2]})
        return commits
    except Exception as exc:
        logger.debug("git log failed for %s: %s", filepath, exc)
        return []


def _get_changed_files(repo_path: str) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return [f for f in r.stdout.splitlines() if f.strip()]
    except Exception:
        pass
    return []


class HistoryCheckAgent(BaseAgent):
    """
    Analyses Git history of files changed in the PR.
    Provides informational context only — never creates BUG findings alone.
    """

    @property
    def agent_type(self) -> str:
        return "history_check"

    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        repo_path = os.path.abspath(repository_path)

        if not os.path.isdir(repo_path):
            return AgentEvidence(
                agent=self.agent_type, command=None, result="ERROR",
                evidence=f"Repository path not found: {repo_path}",
                title="History Check — Repository Not Found",
            )

        # Check git availability
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=repo_path, capture_output=True, timeout=5,
            )
            if r.returncode != 0:
                raise RuntimeError("not a git repo")
        except Exception:
            return AgentEvidence(
                agent=self.agent_type, command=None,
                result="INSUFFICIENT_EVIDENCE",
                evidence="No git repository found — history check requires git.",
                title="History Check — No Git Repository",
                severity="INFO", confidence=0.0,
            )

        changed_files = _get_changed_files(repo_path)
        if not changed_files:
            return AgentEvidence(
                agent=self.agent_type, command="git log",
                result="PASS",
                evidence="No changed files detected (single-commit or initial repo).",
                title="History Check — No Changed Files",
                severity="INFO", confidence=0.5,
            )

        evidence_parts: list[str] = [f"Analysing {len(changed_files)} changed file(s):\n"]
        high_churn_files: list[str] = []
        fix_commit_files: list[str] = []

        for filepath in changed_files[:10]:  # limit to avoid long runtime
            commits = _git_log_file(repo_path, filepath)
            if not commits:
                continue

            fix_commits = [c for c in commits if _FIX_PATTERNS.search(c["subject"])]
            churn = len(commits)

            evidence_parts.append(f"  {filepath}: {churn} commit(s) in history")
            if fix_commits:
                evidence_parts.append(f"    → {len(fix_commits)} fix-related commit(s):")
                for fc in fix_commits[:3]:
                    evidence_parts.append(f"      [{fc['date']}] {fc['sha']}: {fc['subject']}")
                fix_commit_files.append(filepath)
            if churn >= _HIGH_CHURN_THRESHOLD:
                high_churn_files.append(filepath)
                evidence_parts.append(f"    → HIGH CHURN: {churn} modifications")

        evidence = "\n".join(evidence_parts)

        # History context alone → PASS with informational notes
        # Never create a BUG_DETECTED from history alone
        if high_churn_files or fix_commit_files:
            summary_parts = []
            if high_churn_files:
                summary_parts.append(f"high-churn files: {', '.join(high_churn_files[:3])}")
            if fix_commit_files:
                summary_parts.append(f"previously fixed: {', '.join(fix_commit_files[:3])}")
            title = f"History Check — Notable History ({'; '.join(summary_parts)})"
            return AgentEvidence(
                agent=self.agent_type,
                command="git log",
                result="PASS",
                evidence=evidence,
                title=title,
                severity="INFO",
                confidence=0.7,
            )

        return AgentEvidence(
            agent=self.agent_type,
            command="git log",
            result="PASS",
            evidence=evidence,
            title="History Check — No Notable History",
            severity="PASS",
            confidence=1.0,
        )
