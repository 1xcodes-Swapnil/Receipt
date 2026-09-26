"""
Security utilities — Phase 5.

Centralises input validation and sanitisation used across the application.
"""
from __future__ import annotations

import os
import re

# Allowed characters for repo names used in path construction.
# Must be alphanumeric, hyphen, underscore, or dot.  No path separators.
_REPO_NAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{1,200}$")

# Maximum subprocess output length stored in receipts/logs (bytes / chars).
# Prevents unbounded memory use and avoids leaking huge outputs.
MAX_SUBPROCESS_OUTPUT = 65_536  # 64 KiB


def validate_repo_name(repo: str) -> str:
    """
    Validate and return ``repo`` if it is a safe name for path construction.

    Raises ValueError if the name contains path separators, traversal
    sequences, or disallowed characters.

    This is a defence-in-depth measure: even if a caller constructs a path
    using the repo name, the resulting path cannot escape the approved root.
    """
    if not repo:
        raise ValueError("repo name must not be empty")

    # Reject any path separator or traversal sequences early
    if any(ch in repo for ch in ("/", "\\", "\x00")):
        raise ValueError(f"repo name contains illegal path character: {repo!r}")

    # Normalise and check for traversal
    normalised = os.path.normpath(repo)
    if normalised in (".", "..") or normalised.startswith(".."):
        raise ValueError(f"repo name is a path traversal attempt: {repo!r}")

    if not _REPO_NAME_RE.match(repo):
        raise ValueError(
            f"repo name {repo!r} contains disallowed characters. "
            "Only alphanumeric, hyphen, underscore, and dot are allowed."
        )

    return repo


def truncate_output(output: str, max_len: int = MAX_SUBPROCESS_OUTPUT) -> str:
    """Truncate subprocess output to ``max_len`` characters."""
    if len(output) <= max_len:
        return output
    return output[:max_len] + f"\n... [truncated at {max_len} chars]"


def safe_path_join(base: str, relative: str) -> str:
    """
    Join ``base`` and ``relative``, then verify the result stays inside ``base``.

    Raises ValueError if the resolved path escapes the base directory
    (symlink attacks, ``..`` traversal, absolute ``relative`` paths).
    """
    base = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base, relative))
    if not candidate.startswith(base + os.sep) and candidate != base:
        raise ValueError(
            f"Path traversal detected: {relative!r} escapes base {base!r}"
        )
    return candidate
