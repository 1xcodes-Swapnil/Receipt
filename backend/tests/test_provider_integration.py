"""
test_provider_integration.py — ST-6: LocalRepositoryProvider → snapshot → orchestrator tests.

Tests:
  TestLocalProviderBasics         — LocalRepositoryProvider can read files, list files, create workspace
  TestLocalProviderSnapshot       — RepositorySnapshot.create() from a local provider path
  TestLocalProviderWorkspace      — workspace isolation: original path is not mutated
  TestOrchestratorWithProvider    — orchestrator accepts a LocalRepositoryProvider
"""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base

_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_provider_integration_test.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def simple_repo(tmp_path):
    """Create a minimal repository with a Python file and a test."""
    (tmp_path / "calc.py").write_text(
        textwrap.dedent("""\
        def add(a, b):
            return a + b

        def subtract(a, b):
            return a - b
        """)
    )
    (tmp_path / "test_calc.py").write_text(
        textwrap.dedent("""\
        from calc import add, subtract

        def test_add():
            assert add(1, 2) == 3

        def test_subtract():
            assert subtract(5, 3) == 2
        """)
    )
    (tmp_path / "README.md").write_text("# Simple Calc Repo\n")
    return str(tmp_path)


# ── TestLocalProviderBasics ───────────────────────────────────────────────────

class TestLocalProviderBasics:
    """LocalRepositoryProvider: read_file, list_files, repo_path."""

    def test_repo_path_is_absolute(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        assert os.path.isabs(p.repo_path), "repo_path must be absolute"

    def test_read_file_returns_content(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        content = p.read_file("calc.py")
        assert content is not None, "read_file must return content for existing file"
        assert "def add" in content

    def test_read_file_returns_none_for_missing(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        result = p.read_file("nonexistent_file.py")
        assert result is None, "read_file must return None for missing file"

    def test_list_files_finds_py_files(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        files = p.list_files("**/*.py")
        assert any("calc.py" in f for f in files), "list_files must find calc.py"
        assert any("test_calc.py" in f for f in files), "list_files must find test_calc.py"

    def test_invalid_path_raises(self, tmp_path):
        from app.repositories.provider import LocalRepositoryProvider
        with pytest.raises(ValueError):
            LocalRepositoryProvider(str(tmp_path / "no_such_dir"))

    def test_status_is_available(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        st = p.status()
        assert st.available is True
        assert st.provider == "LocalRepositoryProvider"


# ── TestLocalProviderWorkspace ────────────────────────────────────────────────

class TestLocalProviderWorkspace:
    """Workspace is isolated — original repo is not mutated by workspace ops."""

    def test_workspace_is_separate_dir(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        ws = p.create_workspace()
        try:
            assert ws.path != p.repo_path
            assert os.path.isdir(ws.path)
        finally:
            ws.cleanup()

    def test_workspace_contains_files(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        ws = p.create_workspace()
        try:
            assert os.path.isfile(os.path.join(ws.path, "calc.py"))
        finally:
            ws.cleanup()

    def test_workspace_mutation_does_not_affect_original(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        original_content = open(os.path.join(simple_repo, "calc.py")).read()
        ws = p.create_workspace()
        try:
            ws_calc = os.path.join(ws.path, "calc.py")
            with open(ws_calc, "w") as f:
                f.write("# completely replaced")
            current = open(os.path.join(simple_repo, "calc.py")).read()
            assert current == original_content, (
                "Workspace mutation must not affect the original repository"
            )
        finally:
            ws.cleanup()

    def test_cleanup_removes_workspace(self, simple_repo):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(simple_repo)
        ws = p.create_workspace()
        ws_path = ws.path
        ws.cleanup()
        assert not os.path.isdir(ws_path), "cleanup() must remove the workspace directory"


# ── TestLocalProviderSnapshot ─────────────────────────────────────────────────

class TestLocalProviderSnapshot:
    """RepositorySnapshot.create() works from a LocalRepositoryProvider path."""

    def test_snapshot_created_from_local_path(self, simple_repo):
        from app.evidence.snapshot import RepositorySnapshot
        snap = RepositorySnapshot.create(simple_repo)
        assert snap is not None

    def test_snapshot_has_python_files(self, simple_repo):
        from app.evidence.snapshot import RepositorySnapshot
        snap = RepositorySnapshot.create(simple_repo)
        py_files = [f for f in snap.all_files if f.endswith(".py")]
        assert len(py_files) >= 2, "Snapshot must include Python source files"

    def test_snapshot_has_repo_path(self, simple_repo):
        from app.evidence.snapshot import RepositorySnapshot
        snap = RepositorySnapshot.create(simple_repo)
        assert snap.repository_path == simple_repo


# ── TestOrchestratorWithProvider ─────────────────────────────────────────────

class TestOrchestratorWithProvider:
    """ReviewOrchestrator accepts repository_path_override from a LocalRepositoryProvider."""

    def _register_repo(self, db, name: str, path: str):
        from app.models import Repository
        repo = Repository(name=name, url=f"file://{path}", local_path=path)
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo.name

    def test_orchestrator_runs_with_local_path(self, simple_repo, db):
        from app.repositories.provider import LocalRepositoryProvider
        from app.orchestration.orchestrator import ReviewOrchestrator

        provider = LocalRepositoryProvider(simple_repo)
        repo_name = self._register_repo(db, f"prov_test_{os.getpid()}", simple_repo)

        orch = ReviewOrchestrator()
        run = orch.run_review(
            db=db,
            repo_name=repo_name,
            pr_number=1,
            pr_title="Provider integration test",
            repository_path_override=provider.repo_path,
        )
        assert run is not None
        assert run.verdict in ("SAFE", "BUG_DETECTED", "ESCALATE")

    def test_provider_workspace_path_produces_valid_review(self, simple_repo, db):
        """Creating an orchestrator review from a workspace path (not the original path)."""
        from app.repositories.provider import LocalRepositoryProvider
        from app.orchestration.orchestrator import ReviewOrchestrator

        provider = LocalRepositoryProvider(simple_repo)
        ws = provider.create_workspace()
        try:
            repo_name = self._register_repo(db, f"prov_ws_{os.getpid()}", ws.path)
            orch = ReviewOrchestrator()
            run = orch.run_review(
                db=db,
                repo_name=repo_name,
                pr_number=1,
                pr_title="Provider workspace test",
                repository_path_override=ws.path,
            )
            assert run is not None
            assert run.verdict in ("SAFE", "BUG_DETECTED", "ESCALATE")
        finally:
            ws.cleanup()
