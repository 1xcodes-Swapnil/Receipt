"""
Risk Assessment Service — Phase 2.

Uses deterministic, explainable inputs:
  - number of changed files (from git diff --stat)
  - diff size (lines added + removed)
  - sensitive path patterns (config, secrets, CI, migrations)
  - test / configuration changes

Returns LOW | MEDIUM | HIGH with a brief rationale string.
"""
from __future__ import annotations

import os
import re
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Patterns whose presence pushes risk toward HIGH
_SENSITIVE_PATTERNS = [
    r"\.env",
    r"settings\.(py|yml|yaml|json|toml)",
    r"config[/\\]",
    r"migrations?[/\\]",
    r"Dockerfile",
    r"\.github[/\\]",
    r"requirements.*\.txt",
    r"pyproject\.toml",
    r"setup\.(py|cfg)",
    r"security",
    r"auth",
    r"password",
    r"secret",
    r"token",
    r"key\.",
]

_COMPILED_SENSITIVE = [re.compile(p, re.IGNORECASE) for p in _SENSITIVE_PATTERNS]


@dataclass
class RiskAssessment:
    level: str          # "low" | "medium" | "high"
    score: int          # 0–100 numeric score used internally
    rationale: str
    changed_files: int
    diff_lines: int
    sensitive_hits: list[str]


def assess_risk(repo_path: str, base_ref: str = "HEAD~1", head_ref: str = "HEAD") -> RiskAssessment:
    """
    Compute a deterministic risk level for the diff between base_ref and head_ref.

    Falls back gracefully if git is not available or the repo has no history.
    """
    repo_path = os.path.abspath(repo_path)
    changed_files: list[str] = []
    added_lines = 0
    removed_lines = 0

    # --- collect diff stat -------------------------------------------------
    try:
        stat_result = subprocess.run(
            ["git", "diff", "--stat", base_ref, head_ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if stat_result.returncode == 0 and stat_result.stdout.strip():
            for line in stat_result.stdout.splitlines():
                # "path/to/file.py | 12 ++++----"
                if "|" in line:
                    file_part = line.split("|")[0].strip()
                    changed_files.append(file_part)
    except Exception as exc:
        logger.debug("git diff --stat failed: %s", exc)

    # --- collect diff numstat for line counts ------------------------------
    try:
        num_result = subprocess.run(
            ["git", "diff", "--numstat", base_ref, head_ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if num_result.returncode == 0:
            for line in num_result.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    try:
                        added_lines += int(parts[0]) if parts[0] != "-" else 0
                        removed_lines += int(parts[1]) if parts[1] != "-" else 0
                    except ValueError:
                        pass
    except Exception as exc:
        logger.debug("git diff --numstat failed: %s", exc)

    # --- if no git history, fall back to listing files --------------------
    if not changed_files:
        try:
            for root, _, files in os.walk(repo_path):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), repo_path)
                    changed_files.append(rel)
                    # break early – we only need enough for risk scoring
                    if len(changed_files) >= 20:
                        break
                if len(changed_files) >= 20:
                    break
        except Exception:
            pass

    # --- sensitive path matching ------------------------------------------
    sensitive_hits: list[str] = []
    for f in changed_files:
        for pattern in _COMPILED_SENSITIVE:
            if pattern.search(f):
                sensitive_hits.append(f)
                break  # one hit per file is enough

    # --- score computation ------------------------------------------------
    score = 0
    diff_lines = added_lines + removed_lines

    # File count contribution (0–30)
    n_files = len(changed_files)
    if n_files >= 20:
        score += 30
    elif n_files >= 10:
        score += 20
    elif n_files >= 5:
        score += 10
    elif n_files >= 2:
        score += 5

    # Diff size contribution (0–40)
    if diff_lines >= 500:
        score += 40
    elif diff_lines >= 200:
        score += 30
    elif diff_lines >= 50:
        score += 20
    elif diff_lines >= 10:
        score += 10

    # Sensitive paths (0–30)
    if len(sensitive_hits) >= 3:
        score += 30
    elif len(sensitive_hits) >= 1:
        score += 20

    # --- level assignment -------------------------------------------------
    if score >= 60:
        level = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"

    # --- rationale --------------------------------------------------------
    parts = [f"{n_files} file(s) changed"]
    if diff_lines:
        parts.append(f"{diff_lines} line(s) modified")
    if sensitive_hits:
        parts.append(f"sensitive path(s): {', '.join(sensitive_hits[:3])}")
    rationale = "; ".join(parts) + f" → score {score}"

    return RiskAssessment(
        level=level,
        score=score,
        rationale=rationale,
        changed_files=n_files,
        diff_lines=diff_lines,
        sensitive_hits=sensitive_hits,
    )
