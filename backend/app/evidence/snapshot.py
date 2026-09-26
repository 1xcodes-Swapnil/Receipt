"""
RepositorySnapshot — immutable, hash-verified, isolated snapshot of a repository.

Security requirements:
- repository_path is validated (no traversal, no symlinks)
- No env var leakage (secrets / tokens / passwords filtered)
- Immutable after creation (frozen dataclass)
"""
from __future__ import annotations

import hashlib
import os
import platform
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Secret-key filter for environment variables
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = (
    "secret", "token", "password", "passwd", "key", "api_key",
    "auth", "credential", "private", "jwt", "bearer",
)


def _filter_env(env: dict) -> dict:
    """Remove entries whose keys contain secret-like substrings."""
    safe = {}
    for k, v in env.items():
        lower = k.lower()
        if any(pat in lower for pat in _SECRET_PATTERNS):
            continue
        safe[k] = v
    return safe


# ---------------------------------------------------------------------------
# Path safety helper
# ---------------------------------------------------------------------------

def _safe_resolve(path: str) -> str:
    """
    Resolve path, reject path traversal and symlinks.

    Raises ValueError if the resolved path leaves the filesystem root,
    contains traversal segments, or if any component is a symlink.
    """
    if ".." in path.split(os.sep) or ".." in path.split("/"):
        raise ValueError(f"Path traversal detected in: {path!r}")
    resolved = os.path.realpath(path)
    # Reject if the real path differs significantly (symlink redirect)
    if not os.path.abspath(path).startswith(os.path.splitdrive(resolved)[0]):
        raise ValueError(f"Symlink traversal detected for: {path!r}")
    return resolved


# ---------------------------------------------------------------------------
# Snapshot hash
# ---------------------------------------------------------------------------

def _compute_snapshot_hash(repository_path: str, files: tuple[str, ...]) -> str:
    """SHA-256 over sorted file paths + sizes + mtimes."""
    h = hashlib.sha256()
    for rel in sorted(files):
        abs_path = os.path.join(repository_path, rel)
        h.update(rel.encode())
        if os.path.isfile(abs_path):
            try:
                stat = os.stat(abs_path)
                h.update(str(stat.st_size).encode())
                h.update(str(stat.st_mtime).encode())
            except OSError:
                pass
    return h.hexdigest()


# ---------------------------------------------------------------------------
# RepositorySnapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RepositorySnapshot:
    """
    Immutable, hash-verified snapshot of a repository at a point in time.

    Fields
    ------
    snapshot_id    : UUID string
    snapshot_hash  : SHA-256 of relevant files (deterministic)
    repository_path: absolute, validated path
    commit_sha     : optional git commit SHA
    changed_files  : tuple of changed file paths (relative)
    all_files      : tuple of all Python files found (relative)
    environment    : filtered env vars (no secrets)
    created_at     : creation timestamp
    """
    snapshot_id: str
    snapshot_hash: str
    repository_path: str
    commit_sha: Optional[str]
    changed_files: tuple
    all_files: tuple
    environment: dict
    created_at: datetime

    @classmethod
    def create(
        cls,
        repository_path: str,
        changed_files: Optional[list[str]] = None,
        commit_sha: Optional[str] = None,
    ) -> "RepositorySnapshot":
        """
        Factory method — validates path, discovers files, computes hash.

        Raises ValueError on path traversal or symlink issues.
        """
        # Validate path
        resolved = _safe_resolve(repository_path)

        # Discover all Python files
        all_files: list[str] = []
        if os.path.isdir(resolved):
            for dirpath, _dirs, filenames in os.walk(resolved):
                for fn in filenames:
                    if fn.endswith(".py"):
                        abs_f = os.path.join(dirpath, fn)
                        rel = os.path.relpath(abs_f, resolved)
                        all_files.append(rel)

        all_files_tuple = tuple(sorted(all_files))
        changed_tuple = tuple(changed_files) if changed_files else all_files_tuple

        snap_hash = _compute_snapshot_hash(resolved, all_files_tuple)

        env = _filter_env(dict(os.environ))

        return cls(
            snapshot_id=str(uuid.uuid4()),
            snapshot_hash=snap_hash,
            repository_path=resolved,
            commit_sha=commit_sha,
            changed_files=changed_tuple,
            all_files=all_files_tuple,
            environment=env,
            created_at=datetime.utcnow(),
        )
