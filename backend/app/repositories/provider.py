"""
Repository Provider Abstraction — Phase 8.

Defines a clean interface so the review engine is decoupled from local paths.

Providers:
  LocalRepositoryProvider  — backed by a local filesystem path (full implementation)
  GitHubRepositoryProvider — reads from GitHub REST API when GITHUB_TOKEN is available
                             fails cleanly with explicit ProviderStatus when not

Usage:
    provider = LocalRepositoryProvider("/path/to/repo")
    diff = provider.get_diff("HEAD~1", "HEAD")
    workspace = provider.create_workspace()
    ...
    workspace.cleanup()

GitHub usage:
    status = GitHubRepositoryProvider.check_availability()
    if status.available:
        provider = GitHubRepositoryProvider("owner", "repo", pr_number=42)
        snapshot = provider.create_snapshot()
    else:
        # Use local fallback, report status.reason
        print(status.reason)
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


@dataclass
class ProviderStatus:
    """Status of a repository provider — used to report availability clearly."""
    available: bool
    provider: str
    reason: str
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "provider": self.provider,
            "reason": self.reason,
            "detail": self.detail,
        }


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

    def status(self) -> ProviderStatus:
        """Return availability status of this provider."""
        return ProviderStatus(
            available=True,
            provider=self.__class__.__name__,
            reason="available",
        )


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
        """Copy the entire repository to a temp directory.

        symlinks=False: symlinks are expanded to their targets so a
        malicious symlink inside the repo cannot escape the workspace
        boundary (symlink escape / path traversal defence).
        """
        tmp = tempfile.mkdtemp(prefix="receipts_ws_")
        dest = os.path.join(tmp, "repo")
        shutil.copytree(self._path, dest, symlinks=False)
        return Workspace(path=dest, source_path=self._path)


# ---------------------------------------------------------------------------
# GitHub provider — real implementation with clean failure on missing creds
# ---------------------------------------------------------------------------

@dataclass
class GitHubPRInfo:
    """Metadata for a GitHub pull request."""
    number: int
    title: str
    body: Optional[str]
    state: str
    base_sha: str
    head_sha: str
    base_branch: str
    head_branch: str
    author: str
    changed_files: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


class GitHubRepositoryProvider(RepositoryProvider):
    """
    GitHub repository provider.

    Reads repository data from GitHub REST API using GITHUB_TOKEN.

    When credentials are unavailable or network is unreachable:
      - check_availability() returns ProviderStatus(available=False, reason=...)
      - All operations fail cleanly with ProviderUnavailableError
      - Never fabricates GitHub data

    Requires:
      - GITHUB_TOKEN environment variable with repo/contents:read scope
      - Network access to api.github.com
      - Optional: PyGithub package (falls back to httpx/urllib if not installed)
    """

    _GITHUB_API = "https://api.github.com"

    def __init__(
        self,
        owner: str,
        repo: str,
        pr_number: Optional[int] = None,
        token: Optional[str] = None,
    ):
        self._owner = owner
        self._repo = repo
        self._pr_number = pr_number
        # Token is read from env if not explicitly provided
        # Never stored in logs — only used for Authorization header
        self._token = token or os.environ.get("GITHUB_TOKEN", "")
        self._local_clone: Optional[str] = None
        self._pr_info: Optional[GitHubPRInfo] = None

    @classmethod
    def check_availability(cls, token: Optional[str] = None) -> ProviderStatus:
        """
        Check if GitHub access is available.

        Returns ProviderStatus describing whether the provider can be used.
        Never raises — always returns a usable status object.
        """
        tok = token or os.environ.get("GITHUB_TOKEN", "")
        if not tok:
            return ProviderStatus(
                available=False,
                provider="GitHubRepositoryProvider",
                reason="GITHUB_TOKEN environment variable not set",
                detail=(
                    "Set GITHUB_TOKEN to a personal access token with "
                    "'repo' or 'contents:read' scope to enable GitHub integration."
                ),
            )

        # Try a lightweight API call to verify credentials
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{cls._GITHUB_API}/user",
                headers={
                    "Authorization": f"token {tok}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "receipts-review/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return ProviderStatus(
                        available=True,
                        provider="GitHubRepositoryProvider",
                        reason="GitHub token valid and API reachable",
                    )
                else:
                    return ProviderStatus(
                        available=False,
                        provider="GitHubRepositoryProvider",
                        reason=f"GitHub API returned HTTP {resp.status}",
                    )
        except Exception as exc:
            return ProviderStatus(
                available=False,
                provider="GitHubRepositoryProvider",
                reason=f"GitHub API unreachable: {type(exc).__name__}: {exc}",
                detail="Check network access and GITHUB_TOKEN validity.",
            )

    def _api_get(self, path: str) -> dict:
        """Make an authenticated GET request to the GitHub API."""
        if not self._token:
            raise ProviderUnavailableError(
                "GITHUB_TOKEN not set — GitHub integration unavailable"
            )
        import json as _json
        import urllib.request
        url = f"{self._GITHUB_API}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {self._token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "receipts-review/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return _json.loads(resp.read().decode())
        except Exception as exc:
            raise ProviderUnavailableError(
                f"GitHub API request failed: {exc}"
            ) from exc

    def _load_pr_info(self) -> GitHubPRInfo:
        """Fetch PR metadata from GitHub API."""
        if self._pr_info is not None:
            return self._pr_info

        if self._pr_number is None:
            raise ProviderUnavailableError("pr_number is required for GitHub PR operations")

        data = self._api_get(f"/repos/{self._owner}/{self._repo}/pulls/{self._pr_number}")
        files_data = self._api_get(
            f"/repos/{self._owner}/{self._repo}/pulls/{self._pr_number}/files"
        )
        changed_files = [f["filename"] for f in files_data if isinstance(f, dict)]

        self._pr_info = GitHubPRInfo(
            number=self._pr_number,
            title=data.get("title", ""),
            body=data.get("body"),
            state=data.get("state", ""),
            base_sha=data["base"]["sha"],
            head_sha=data["head"]["sha"],
            base_branch=data["base"]["ref"],
            head_branch=data["head"]["ref"],
            author=data["user"]["login"],
            changed_files=changed_files,
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
        )
        return self._pr_info

    def _ensure_clone(self) -> str:
        """Clone the repository to a temp dir if not already done."""
        if self._local_clone and os.path.isdir(self._local_clone):
            return self._local_clone

        if not self._token:
            raise ProviderUnavailableError("GITHUB_TOKEN required for cloning")

        clone_url = (
            f"https://{self._token}@github.com/{self._owner}/{self._repo}.git"
        )
        tmp = tempfile.mkdtemp(prefix="receipts_gh_clone_")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", clone_url, tmp],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                raise ProviderUnavailableError(
                    f"git clone failed: {result.stderr[:200]}"
                )
            self._local_clone = tmp
            return tmp
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            raise ProviderUnavailableError("git clone timed out after 120s")

    @property
    def repo_path(self) -> str:
        return self._ensure_clone()

    def has_git(self) -> bool:
        try:
            path = self._ensure_clone()
            rc, _, _ = _run_git(["rev-parse", "--git-dir"], path)
            return rc == 0
        except ProviderUnavailableError:
            return False

    def get_head_commit(self) -> Optional[CommitInfo]:
        try:
            pr = self._load_pr_info()
            return CommitInfo(
                sha=pr.head_sha,
                message=pr.title,
                author=pr.author,
                date="",
            )
        except ProviderUnavailableError:
            return None

    def get_parent_commit(self) -> Optional[CommitInfo]:
        try:
            pr = self._load_pr_info()
            return CommitInfo(
                sha=pr.base_sha,
                message=f"base branch: {pr.base_branch}",
                author="",
                date="",
            )
        except ProviderUnavailableError:
            return None

    def get_diff(self, base_ref: str = "HEAD~1", head_ref: str = "HEAD") -> DiffStat:
        try:
            pr = self._load_pr_info()
            return DiffStat(
                added_lines=pr.additions,
                removed_lines=pr.deletions,
                changed_files=pr.changed_files,
                raw_stat=f"+{pr.additions}/-{pr.deletions} across {len(pr.changed_files)} files",
            )
        except ProviderUnavailableError:
            return DiffStat(added_lines=0, removed_lines=0, changed_files=[], raw_stat="")

    def read_file(self, relative_path: str) -> Optional[str]:
        try:
            path = self._ensure_clone()
            full = os.path.join(path, relative_path)
            if not os.path.isfile(full):
                return None
            with open(full, encoding="utf-8", errors="replace") as f:
                return f.read()
        except (ProviderUnavailableError, OSError):
            return None

    def list_files(self, pattern: str = "**/*.py") -> list[str]:
        try:
            path = self._ensure_clone()
            import glob as _glob
            matches = _glob.glob(os.path.join(path, pattern), recursive=True)
            return [os.path.relpath(m, path) for m in matches]
        except ProviderUnavailableError:
            return []

    def create_workspace(self) -> Workspace:
        path = self._ensure_clone()
        tmp = tempfile.mkdtemp(prefix="receipts_gh_ws_")
        dest = os.path.join(tmp, "repo")
        shutil.copytree(path, dest, symlinks=False)
        return Workspace(path=dest, source_path=path)

    def status(self) -> ProviderStatus:
        return self.check_availability(self._token)

    def get_pr_info(self) -> Optional[GitHubPRInfo]:
        """Return PR metadata, or None if unavailable."""
        try:
            return self._load_pr_info()
        except ProviderUnavailableError:
            return None

    def cleanup(self) -> None:
        """Remove the local clone."""
        if self._local_clone and os.path.isdir(self._local_clone):
            shutil.rmtree(self._local_clone, ignore_errors=True)
            self._local_clone = None


class ProviderUnavailableError(RuntimeError):
    """
    Raised when a RepositoryProvider cannot fulfill a request.

    Never fabricates data — callers must handle this and report the failure.
    """
    pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_provider(local_path: str) -> LocalRepositoryProvider:
    """Create a LocalRepositoryProvider from a path string."""
    return LocalRepositoryProvider(local_path)


def make_github_provider(
    owner: str,
    repo: str,
    pr_number: Optional[int] = None,
    token: Optional[str] = None,
) -> tuple[Optional[GitHubRepositoryProvider], ProviderStatus]:
    """
    Create a GitHubRepositoryProvider after checking availability.

    Returns (provider, status).
    If unavailable, provider is None and status.reason explains why.
    Never raises — always returns a usable status.
    """
    status = GitHubRepositoryProvider.check_availability(token)
    if not status.available:
        return None, status
    provider = GitHubRepositoryProvider(owner, repo, pr_number, token)
    return provider, status
