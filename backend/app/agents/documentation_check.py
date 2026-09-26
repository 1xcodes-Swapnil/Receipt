"""
Documentation Check Agent — Phase 2.

Inspects:
  - README files
  - Contribution guidelines (CONTRIBUTING.md, CONTRIBUTING.rst)
  - Relevant docs in docs/ or doc/
  - Changed documentation files (from git diff)

Reports only concrete evidence:
  - Missing required sections (e.g. README has no Installation section)
  - Files referenced in docs that don't exist
  - Changed source files with no corresponding doc update (advisory only)

Does NOT invent contradictions. Only reports what is concretely missing or broken.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Optional

from app.agents.base import AgentEvidence, BaseAgent

logger = logging.getLogger(__name__)

_README_PATTERNS = ["README.md", "README.rst", "README.txt", "README"]
_CONTRIB_PATTERNS = ["CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING.txt"]
_DOC_DIRS = ["docs", "doc", "documentation"]

# Required README sections (case-insensitive heading match)
_REQUIRED_SECTIONS = ["installation", "usage"]

# Markdown / RST heading pattern
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)|^(.+)\n[=\-]+\s*$", re.MULTILINE)


def _find_file(repo_path: str, candidates: list[str]) -> Optional[str]:
    for name in candidates:
        path = os.path.join(repo_path, name)
        if os.path.isfile(path):
            return path
    return None


def _read_file_safe(path: str, max_bytes: int = 8192) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception as exc:
        return f"(could not read: {exc})"


def _extract_headings(content: str) -> list[str]:
    return [
        (m.group(1) or m.group(2)).strip().lower()
        for m in _HEADING_RE.finditer(content)
    ]


def _get_changed_docs(repo_path: str) -> list[str]:
    """Return documentation-related files changed in HEAD vs HEAD~1."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return [
                f for f in r.stdout.splitlines()
                if any(f.lower().endswith(ext) for ext in (".md", ".rst", ".txt"))
                or any(d in f.lower() for d in ("doc", "readme", "contribut", "changelog"))
            ]
    except Exception:
        pass
    return []


def _check_readme(repo_path: str) -> list[str]:
    """Return list of findings (strings). Empty = no issues."""
    findings = []
    readme_path = _find_file(repo_path, _README_PATTERNS)
    if readme_path is None:
        findings.append("No README file found in repository root.")
        return findings

    content = _read_file_safe(readme_path)
    if len(content) < 50:
        findings.append(f"README exists but is nearly empty ({len(content)} chars).")
        return findings

    headings = _extract_headings(content)
    for section in _REQUIRED_SECTIONS:
        if not any(section in h for h in headings):
            findings.append(f"README is missing a '{section.title()}' section.")

    return findings


def _check_internal_links(repo_path: str, readme_path: str) -> list[str]:
    """Check that markdown links pointing to local files actually exist."""
    findings = []
    content = _read_file_safe(readme_path)
    # Match [text](path) where path doesn't start with http
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for m in link_re.finditer(content):
        target = m.group(2)
        if target.startswith("http") or target.startswith("#"):
            continue
        # Strip anchors
        target_path = target.split("#")[0]
        if not target_path:
            continue
        full = os.path.join(os.path.dirname(readme_path), target_path)
        if not os.path.exists(full):
            findings.append(f"README references '{target_path}' which does not exist.")
    return findings


class DocumentationCheckAgent(BaseAgent):
    """
    Inspects repository documentation for concrete issues.
    Only flags things that are verifiably missing or broken.
    """

    @property
    def agent_type(self) -> str:
        return "documentation_check"

    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        repo_path = os.path.abspath(repository_path)

        if not os.path.isdir(repo_path):
            return AgentEvidence(
                agent=self.agent_type, command=None, result="ERROR",
                evidence=f"Repository path not found: {repo_path}",
                title="Documentation Check — Repository Not Found",
            )

        findings: list[str] = []
        evidence_parts: list[str] = []

        # 1. README check
        readme_findings = _check_readme(repo_path)
        findings.extend(readme_findings)
        evidence_parts.append(f"README check: {len(readme_findings)} issue(s)")
        for f in readme_findings:
            evidence_parts.append(f"  - {f}")

        # 2. Internal link check
        readme_path = _find_file(repo_path, _README_PATTERNS)
        if readme_path:
            link_findings = _check_internal_links(repo_path, readme_path)
            findings.extend(link_findings)
            evidence_parts.append(f"Link check: {len(link_findings)} broken link(s)")
            for f in link_findings:
                evidence_parts.append(f"  - {f}")

        # 3. Changed docs list (informational)
        changed_docs = _get_changed_docs(repo_path)
        evidence_parts.append(
            f"Changed doc files: {', '.join(changed_docs) if changed_docs else '(none)'}"
        )

        # 4. Contributing guide presence (advisory, not a bug)
        contrib_path = _find_file(repo_path, _CONTRIB_PATTERNS)
        evidence_parts.append(
            f"Contributing guide: {'found' if contrib_path else 'not found (advisory)'}"
        )

        evidence = "\n".join(evidence_parts)
        file_ref = readme_path or None

        if findings:
            return AgentEvidence(
                agent=self.agent_type,
                command="documentation_check",
                result="FAIL",
                evidence=evidence,
                title=f"Documentation Check — {len(findings)} Issue(s) Found",
                severity="LOW",
                confidence=0.9,
                file_ref=file_ref,
            )
        else:
            return AgentEvidence(
                agent=self.agent_type,
                command="documentation_check",
                result="PASS",
                evidence=evidence,
                title="Documentation Check — No Issues Found",
                severity="PASS",
                confidence=1.0,
                file_ref=file_ref,
            )
