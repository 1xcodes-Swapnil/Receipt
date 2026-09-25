"""
Repository Provider Abstraction — Phase 3.

Defines a clean interface so the review engine is decoupled from local paths.
Phase 3 implements LocalRepositoryProvider.
GitHubRepositoryProvider is a stub interface only — no real GitHub calls.

Usage:
    provider = LocalRepositoryProvider("/path/to/repo")
    diff = provider.get_diff("HEAD~1", "HEAD")
    workspace = provider.create_workspace()
    ...
    provider.cleanup_workspace(workspace)
"""
from __future__ import annotations

import abc
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CommitInfo:
    sha: str
    message: str
    author: str
    date: str


@dataclass
class DiffStat:
    added_lines: int
    removed_lines: int
    changed_files: list[str]
    raw_stat: str


@dataclass
class Workspace:
    """An isolated copy of the repository for safe modification."""
    path: str
    source_path: str
    _owned: bool = True  # if True, cleanup() will remove it

    def cleanup(self):
        if self._owned and os.path.isdir(self.path):
            shutil.rmtree(self.path, ignore_errors=True)
            logger.debug("Workspace cleaned up: %s", self.path)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class RepositoryProvider(abc.ABC):
    """
    Abstract repository provider.
    All review agents should depend on this interface rather than hard-coding
    local path assumptions.
    """

    @property
    @abc.abstractmethod
    def repo_path(self) -> str:
        """Absolute path to the repository root."""
        ...

    @abc.abstractmethod
    def get_head_commit(self) -> Optional[CommitInfo]:
        """Return the current HEAD commit info."""
        ...

    @abc.abstractmethod
    def get_parent_commit(self) -> Optional[CommitInfo]:
        """Return HEAD~1 commit info, or None if no parent."""
        ...

    @abc.abstractmethod
    def get_diff(self, base_ref: str = "HEAD~1", head_ref: str = "HEAD") -> DiffStat:
        """Return diff statistics between two refs."""
        ...

    @abc.abstractmethod
    def read_file(self, relative_path: str) -> Optional[str]:
        """Read a file from the repository. Returns None if not found."""
        ...

    @abc.abstractmethod
    def list_files(self, pattern: str = "**/*.py") -> list[str]:
        """List files matching a glob pattern."""
        ...

    @abc.abstractmethod
    def create_workspace(self) -> Workspace:
        """
        Create an isolated copy of the repository for safe modification.
        Caller is responsible for calling workspace.cleanup().
        """
        ...

    @abc.abstractmethod
    def has_git(self) -> bool:
        """Return True if the repository has a .git directory."""
        ...


# ---------------------------------------------------------------------------
# Local implementation
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: str, timeout: int = 15) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout, r.stderr
    except Exception as exc:
        return -1, "", str(exc)


class LocalRepositoryProvider(RepositoryProvider):
    """
    Repository provider backed by a local filesystem path.

    Supports git operations where .git/ is available.
    Gracefully degrades when git history is unavailable.
    """

    def __init__(self, path: str):
        self._path = os.path.abspath(path)
        if not os.path.isdir(self._path):
            raise ValueError(f"Repository path does not exist: {self._path}")

    @property
    def repo_path(self) -> str:
        return self._path

    def has_git(self) -> bool:
        rc, _, _ = _run_git(["rev-parse", "--git-dir"], self._path)
        return rc == 0

    def get_head_commit(self) -> Optional[CommitInfo]:
        rc, out, _ = _run_git(
            ["log", "-1", "--pretty=format:%H|%s|%an|%ad", "--date=short"],
            self._path,
        )
        if rc != 0 or not out.strip():
            return None
        parts = out.strip().split("|", 3)
        if len(parts) < 4:
            return None
        return CommitInfo(sha=parts[0], message=parts[1], author=parts[2], date=parts[3])

    def get_parent_commit(self) -> Optional[CommitInfo]:
        rc, _, _ = _run_git(["rev-parse", "HEAD~1"], self._path)
        if rc != 0:
            return None
        rc2, out, _ = _run_git(
            ["log", "-1", "--pretty=format:%H|%s|%an|%ad", "--date=short", "HEAD~1"],
            self._path,
        )
        if rc2 != 0 or not out.strip():
            return None
        parts = out.strip().split("|", 3)
        if len(parts) < 4:
            return None
        return CommitInfo(sha=parts[0], message=parts[1], author=parts[2], date=parts[3])

    def get_diff(self, base_ref: str = "HEAD~1", head_ref: str = "HEAD") -> DiffStat:
        changed_files: list[str] = []
        added = removed = 0

        rc, stat_out, _ = _run_git(["diff", "--stat", base_ref, head_ref], self._path)
        if rc == 0:
            for line in stat_out.splitlines():
                if "|" in line:
                    changed_files.append(line.split("|")[0].strip())

        rc2, num_out, _ = _run_git(["diff", "--numstat", base_ref, head_ref], self._path)
        if rc2 == 0:
            for line in num_out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    try:
                        added += int(parts[0]) if parts[0] != "-" else 0
                        removed += int(parts[1]) if parts[1] != "-" else 0
                    except ValueError:
                        pass

        return DiffStat(
            added_lines=added,
            removed_lines=removed,
            changed_files=changed_files,
            raw_stat=stat_out,
        )

    def read_file(self, relative_path: str) -> Optional[str]:
        full = os.path.join(self._path, relative_path)
        if not os.path.isfile(full):
            return None
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return None

    def list_files(self, pattern: str = "**/*.py") -> list[str]:
        import glob as _glob
        matches = _glob.glob(os.path.join(self._path, pattern), recursive=True)
        return [os.path.relpath(m, self._path) for m in matches]

    def create_workspace(self) -> Workspace:
        """Copy the entire repository to a temp directory."""
        tmp = tempfile.mkdtemp(prefix="receipts_ws_")
        dest = os.path.join(tmp, "repo")
        shutil.copytree(self._path, dest)
        return Workspace(path=dest, source_path=self._path)


# ---------------------------------------------------------------------------
# GitHub stub (interface only — no real API calls)
# ---------------------------------------------------------------------------

class GitHubRepositoryProvider(RepositoryProvider):
    """
    GitHub repository provider — Phase 3 STUB only.

    This class defines the interface a real GitHub connector must implement.
    It does NOT make real GitHub API calls and will raise NotImplementedError
    on any operation.

    Phase 4 will implement this using the GitHub REST API.
    """

    def __init__(self, owner: str, repo: str, token: Optional[str] = None):
        self._owner = owner
        self._repo = repo
        self._token = token
        self._local_clone: Optional[str] = None

    @property
    def repo_path(self) -> str:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")

    def has_git(self) -> bool:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")

    def get_head_commit(self) -> Optional[CommitInfo]:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")

    def get_parent_commit(self) -> Optional[CommitInfo]:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")

    def get_diff(self, base_ref: str = "HEAD~1", head_ref: str = "HEAD") -> DiffStat:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")

    def read_file(self, relative_path: str) -> Optional[str]:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")

    def list_files(self, pattern: str = "**/*.py") -> list[str]:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")

    def create_workspace(self) -> Workspace:
        raise NotImplementedError("GitHubRepositoryProvider is not implemented in Phase 3")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_provider(local_path: str) -> LocalRepositoryProvider:
    """Create a LocalRepositoryProvider from a path string."""
    return LocalRepositoryProvider(local_path)
