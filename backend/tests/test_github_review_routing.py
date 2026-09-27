"""
Routing between local and GitHub repository reviews, and GitHub credential hygiene.

- demo / demo_repo and registered local repositories must never reach the GitHub provider.
- "owner/repo" and github.com URLs must use the GitHub provider.
- A missing GITHUB_TOKEN must produce a clear 400.
- The token must never be written into a cloned repository.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CLEAN_REPO = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "demo", "clean_repo"))

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import app.repositories.provider as provider_mod  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.security import is_github_repo_reference, parse_github_repo_input  # noqa: E402

_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_github_routing_test.db")
engine = create_engine(f"sqlite:///{_TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

_FAKE_TOKEN = "fake-test-token-never-persist-0123456789"


def _get_test_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def _setup_test_db():
    import app.models  # noqa: F401
    import app.database as _db
    import app.orchestration.orchestrator as _orch

    Base.metadata.create_all(bind=engine)
    prev_override = fastapi_app.dependency_overrides.get(get_db)
    prev_orch_session, prev_db_session = _orch.SessionLocal, _db.SessionLocal
    fastapi_app.dependency_overrides[get_db] = _get_test_db
    _orch.SessionLocal = TestingSession  # type: ignore[attr-defined]
    _db.SessionLocal = TestingSession  # type: ignore[attr-defined]

    yield

    if prev_override is None:
        fastapi_app.dependency_overrides.pop(get_db, None)
    else:
        fastapi_app.dependency_overrides[get_db] = prev_override
    _orch.SessionLocal = prev_orch_session
    _db.SessionLocal = prev_db_session
    engine.dispose()
    try:
        os.unlink(_TEST_DB_PATH)
    except OSError:
        pass


@pytest.fixture()
def client():
    return TestClient(fastapi_app)


class _ForbiddenGitHubProvider:
    """Fails the test if a local review ever constructs the GitHub provider."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("GitHub provider must not be used for local repositories")


class _FakeGitHubProvider:
    """Stands in for GitHub: records construction and serves a copy of demo/clean_repo."""

    instances: list["_FakeGitHubProvider"] = []

    def __init__(self, owner, repo, pr_number=None, token=None):
        self.owner, self.repo, self.pr_number, self.token = owner, repo, pr_number, token
        self.cleaned_up = False
        _FakeGitHubProvider.instances.append(self)

    def get_pr_info(self):
        return None

    def create_workspace(self):
        tmp = tempfile.mkdtemp(prefix="receipts_fake_gh_ws_")
        dest = os.path.join(tmp, "repo")
        shutil.copytree(_CLEAN_REPO, dest)
        return provider_mod.Workspace(path=dest, source_path=_CLEAN_REPO)

    def cleanup(self):
        self.cleaned_up = True


@pytest.fixture()
def fake_github(monkeypatch):
    _FakeGitHubProvider.instances = []
    monkeypatch.setattr(provider_mod, "GitHubRepositoryProvider", _FakeGitHubProvider)
    monkeypatch.setattr(settings, "github_token", SecretStr(_FAKE_TOKEN))
    return _FakeGitHubProvider


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestRepoReferenceClassification:
    @pytest.mark.parametrize("name", ["demo", "demo_repo", "e2e_safe_1234abcd", "my-repo.v2"])
    def test_local_names_are_not_github(self, name):
        assert not is_github_repo_reference(name)

    @pytest.mark.parametrize("ref", [
        "AsthaPatil-akp/Aaranya",
        "https://github.com/AsthaPatil-akp/Aaranya",
        "https://github.com/AsthaPatil-akp/Aaranya.git",
    ])
    def test_github_references(self, ref):
        assert is_github_repo_reference(ref)
        assert parse_github_repo_input(ref) == ("AsthaPatil-akp", "Aaranya")

    @pytest.mark.parametrize("ref", [
        "https://evil.example.com/owner/repo",
        "https://user:secret@github.com/owner/repo",
        "../etc",
        "a/b/c",
        "owner/re po",
    ])
    def test_unsafe_github_references_rejected(self, ref):
        with pytest.raises(ValueError):
            parse_github_repo_input(ref)


# ---------------------------------------------------------------------------
# Local reviews never touch GitHub
# ---------------------------------------------------------------------------

class TestLocalReviews:
    @pytest.fixture(autouse=True)
    def _forbid_github(self, monkeypatch):
        monkeypatch.setattr(provider_mod, "GitHubRepositoryProvider", _ForbiddenGitHubProvider)
        monkeypatch.setattr(settings, "github_token", SecretStr(""))

    def test_demo_repo_review_works(self, client):
        r = client.post("/repos/demo_repo/prs/1/review", json={"pr_title": "demo"})
        assert r.status_code == 201, r.text
        assert r.json()["verdict"] == "BUG_DETECTED"

    def test_demo_repo_review_with_frontend_payload(self, client):
        r = client.post("/repos/demo_repo/prs/1/review", json={"repo_name": "demo_repo", "pr_title": "demo"})
        assert r.status_code == 201, r.text

    def test_registered_local_repository_review_works(self, client):
        from app.models import Repository
        name = f"local_{uuid.uuid4().hex[:8]}"
        db = TestingSession()
        db.add(Repository(id=str(uuid.uuid4()), name=name, local_path=_CLEAN_REPO))
        db.commit()
        db.close()

        r = client.post(f"/repos/{name}/prs/1/review", json={"repo_name": name, "pr_title": "local"})
        assert r.status_code == 201, r.text
        assert r.json()["verdict"] == "SAFE"

    @pytest.mark.parametrize("bad", ["bad\\name", "..", "bad name"])
    def test_invalid_local_names_still_rejected(self, client, bad):
        r = client.post("/repos/x/prs/1/review", json={"repo_name": bad})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GitHub reviews
# ---------------------------------------------------------------------------

class TestGitHubReviews:
    @pytest.mark.parametrize("ref", ["AsthaPatil-akp/Aaranya", "https://github.com/AsthaPatil-akp/Aaranya"])
    def test_github_reference_uses_github_provider(self, client, fake_github, ref):
        r = client.post("/repos/x/prs/7/review", json={"repo_name": ref, "pr_title": "gh"})
        assert r.status_code == 201, r.text

        assert len(fake_github.instances) == 1
        gh = fake_github.instances[0]
        assert (gh.owner, gh.repo, gh.pr_number) == ("AsthaPatil-akp", "Aaranya", 7)
        assert gh.token == _FAKE_TOKEN
        assert gh.cleaned_up
        assert _FAKE_TOKEN not in r.text

    def test_github_path_param_uses_github_provider(self, client, fake_github):
        r = client.post("/repos/AsthaPatil-akp/Aaranya/prs/3/review", json={"pr_title": "gh"})
        assert r.status_code == 201, r.text
        assert fake_github.instances[0].owner == "AsthaPatil-akp"

    def test_missing_token_gives_clear_error(self, client, fake_github, monkeypatch):
        monkeypatch.setattr(settings, "github_token", SecretStr(""))
        r = client.post("/repos/x/prs/1/review", json={"repo_name": "AsthaPatil-akp/Aaranya"})
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "GITHUB_TOKEN is not configured" in detail
        assert "backend/.env" in detail
        assert fake_github.instances == []

    @pytest.mark.parametrize("bad", ["../etc", "a/b/c", "https://evil.example.com/o/r"])
    def test_unsafe_github_references_rejected_before_provider(self, client, fake_github, bad):
        r = client.post("/repos/x/prs/1/review", json={"repo_name": bad})
        assert r.status_code == 400
        assert "Invalid repository specification" in r.json()["detail"]
        assert fake_github.instances == []


# ---------------------------------------------------------------------------
# Credential hygiene of the real clone path
# ---------------------------------------------------------------------------

def _make_source_repo(path: str) -> None:
    os.makedirs(path)
    with open(os.path.join(path, "mod.py"), "w", encoding="utf-8") as f:
        f.write("def f():\n    return 1\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(git + ["-C", path, "add", "."], check=True)
    subprocess.run(git + ["-C", path, "commit", "-q", "-m", "init"], check=True)


def _assert_no_credentials(git_dir: str, secrets: list[str]) -> None:
    for root, _dirs, files in os.walk(git_dir):
        for name in files:
            with open(os.path.join(root, name), "rb") as f:
                data = f.read()
            for secret in secrets:
                assert secret.encode() not in data, f"credential found in {os.path.join(root, name)}"


def test_clone_authenticates_without_persisting_token(monkeypatch, tmp_path):
    """
    Runs the provider's real git clone, redirected to a local repository via git's
    url.<base>.insteadOf so no network is needed; git still stores the original
    https://github.com URL in .git/config, exactly as for a real clone.
    """
    source = str(tmp_path / "source")
    _make_source_repo(source)
    source_uri = "file:///" + source.replace("\\", "/").lstrip("/")
    github_url = "https://github.com/octo/demo.git"

    real_run = subprocess.run
    calls: list[tuple[list[str], dict]] = []

    def spy_run(args, *a, **kw):
        env = kw.get("env")
        calls.append((list(args), dict(env) if env else {}))
        if env and list(args[:2]) == ["git", "clone"]:
            env = dict(env)
            n = int(env.get("GIT_CONFIG_COUNT", "0"))
            env[f"GIT_CONFIG_KEY_{n}"] = f"url.{source_uri}.insteadOf"
            env[f"GIT_CONFIG_VALUE_{n}"] = github_url
            env["GIT_CONFIG_COUNT"] = str(n + 1)
            kw["env"] = env
        return real_run(args, *a, **kw)

    monkeypatch.setattr(provider_mod.subprocess, "run", spy_run)

    gh = provider_mod.GitHubRepositoryProvider("octo", "demo", pr_number=None, token=_FAKE_TOKEN)
    basic = base64.b64encode(f"x-access-token:{_FAKE_TOKEN}".encode()).decode()
    ws = None
    try:
        ws = gh.create_workspace()

        clone_args, clone_env = next(c for c in calls if c[0][:2] == ["git", "clone"])
        assert github_url in clone_args, "clone URL must be the plain https URL"
        assert all(_FAKE_TOKEN not in arg for args, _ in calls for arg in args), "token leaked into argv"
        assert clone_env.get("GIT_CONFIG_VALUE_0") == f"AUTHORIZATION: basic {basic}", "auth header not supplied"

        for repo_dir in (gh._local_clone, ws.path):
            with open(os.path.join(repo_dir, ".git", "config"), encoding="utf-8") as f:
                config = f.read()
            assert github_url in config
            assert "extraheader" not in config.lower()
            _assert_no_credentials(os.path.join(repo_dir, ".git"), [_FAKE_TOKEN, basic])
    finally:
        if ws is not None:
            shutil.rmtree(os.path.dirname(ws.path), ignore_errors=True)
        gh.cleanup()
