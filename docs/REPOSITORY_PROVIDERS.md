# Repository Providers — Receipts

## Overview

The `RepositoryProvider` abstraction in `backend/app/repositories/provider.py` decouples the review engine from specific repository backends. Currently two providers are implemented:

- **`LocalRepositoryProvider`** — backed by a local filesystem path (full implementation)
- **`GitHubRepositoryProvider`** — reads from GitHub REST API when `GITHUB_TOKEN` is set (Phase 8)

## Abstract Interface

```python
class RepositoryProvider(abc.ABC):
    @property
    def repo_path(self) -> str: ...

    def get_head_commit(self) -> Optional[CommitInfo]: ...
    def get_parent_commit(self) -> Optional[CommitInfo]: ...
    def get_diff(self, base_ref="HEAD~1", head_ref="HEAD") -> DiffStat: ...
    def read_file(self, relative_path: str) -> Optional[str]: ...
    def list_files(self, pattern: str = "**/*.py") -> list[str]: ...
    def create_workspace(self) -> Workspace: ...
    def has_git(self) -> bool: ...
    def status(self) -> ProviderStatus: ...
```

## Data Classes

### `CommitInfo`
```python
@dataclass
class CommitInfo:
    sha: str
    message: str
    author: str
    date: str
```

### `DiffStat`
```python
@dataclass
class DiffStat:
    added_lines: int
    removed_lines: int
    changed_files: list[str]
    raw_stat: str
```

### `Workspace`
```python
@dataclass
class Workspace:
    path: str           # path to the isolated workspace directory
    source_path: str    # path to the source that was copied
    _owned: bool        # if True, cleanup() will remove it

    def cleanup(self): ...
```

### `ProviderStatus`
```python
@dataclass
class ProviderStatus:
    available: bool
    provider: str
    reason: str
    detail: Optional[str] = None

    def to_dict(self) -> dict: ...
```

---

## LocalRepositoryProvider

### Usage

```python
from app.repositories.provider import LocalRepositoryProvider

p = LocalRepositoryProvider("/path/to/repo")
# raises ValueError if path does not exist

# Git operations (gracefully degrade if no .git)
head = p.get_head_commit()   # CommitInfo or None
diff = p.get_diff("HEAD~1", "HEAD")

# File operations
content = p.read_file("src/main.py")   # str or None
files = p.list_files("**/*.py")         # list of relative paths

# Workspace isolation
ws = p.create_workspace()
# ws.path is a temp directory containing a full copy
ws.cleanup()   # always call this
```

### Implementation Notes

- `create_workspace()` copies the full repository tree using `shutil.copytree(symlinks=False)` — symlinks are never followed (security)
- `list_files()` uses `glob.glob()` with the given pattern relative to `repo_path`
- `read_file()` returns `None` if the file does not exist or cannot be read
- `get_diff()` calls `git diff --stat` — returns empty `DiffStat` if git is unavailable
- All git operations have a 15-second timeout and return gracefully on error

---

## GitHubRepositoryProvider

### Availability Check

Before using `GitHubRepositoryProvider`, always call `check_availability()`:

```python
from app.repositories.provider import GitHubRepositoryProvider

status = GitHubRepositoryProvider.check_availability()
if status.available:
    provider = GitHubRepositoryProvider("owner", "repo", pr_number=42)
else:
    print(f"GitHub unavailable: {status.reason}")
    # use LocalRepositoryProvider as fallback
```

`check_availability()`:
- Returns a `ProviderStatus`
- **Never raises** — clean failure always
- Returns `available=False` when `GITHUB_TOKEN` is not set in environment
- Returns `available=False` when GitHub API is unreachable

### Configuration

Set `GITHUB_TOKEN` in environment (or `.env` file):

```
GITHUB_TOKEN=ghp_...
```

The token requires `repo` read scope for private repositories; `public_repo` for public.

### ProviderUnavailableError

When code tries to use `GitHubRepositoryProvider` methods but the provider is unavailable:

```python
from app.repositories.provider import ProviderUnavailableError

try:
    provider = GitHubRepositoryProvider("owner", "repo")
    snapshot = provider.create_workspace()
except ProviderUnavailableError as e:
    # Handle cleanly — e.g. fall back to local
    logger.warning("GitHub provider unavailable: %s", e)
```

### Current Status

**Phase 8: Implemented with clean failure path.**

- `check_availability()` is fully implemented
- `ProviderStatus`, `ProviderUnavailableError` are fully implemented
- `LocalRepositoryProvider` is fully implemented
- GitHub REST API methods (`_api_get()`, `_load_pr_info()`, `_ensure_clone()`) are implemented
- **Note**: The GitHub provider requires network access to `api.github.com` and is not tested in the CI suite (no real GitHub token available in test environment)

---

## Security Properties

### LocalRepositoryProvider
- Rejects paths that do not exist (`ValueError`)
- Workspace copy uses `symlinks=False` — no symlink traversal
- `read_file()` resolves paths relative to `repo_path` — no path traversal beyond repo root

### GitHubRepositoryProvider
- Token is never logged or stored in DB
- `check_availability()` is safe to call in any context — no side effects
- API calls use HTTPS only

---

## Example: Review with Provider

The `ReviewOrchestrator` currently uses a path-based approach (not the provider abstraction directly). The provider abstraction is available for future use and is used in Phase 8 tooling:

```python
from app.repositories.provider import LocalRepositoryProvider, GitHubRepositoryProvider

# For local repos
provider = LocalRepositoryProvider(repository_path)
ws = provider.create_workspace()
try:
    # run review in ws.path
    ...
finally:
    ws.cleanup()
```
