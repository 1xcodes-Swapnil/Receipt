"""
Phase 5 test suite — backend hardening.

Tests:
  TestWorkspaceIsolation     — replay workspace isolation, no false alarms
  TestAuditConcurrency       — threading.Lock serialisation, chain integrity
  TestSecurityHardening      — path traversal, validate_repo_name, safe_path_join
  TestBobEvidenceRef         — schema extension point, never auto-populated
  TestEndToEndVerdicts       — SAFE / BUG_DETECTED / ESCALATE via API
  TestDemoCLI                — demo_cli.py commands exit 0
  TestReplayDemoCases        — 3 BUG + 3 SAFE, zero false alarms
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ------------------------------------------------------------------
# Ensure backend/app is importable
# ------------------------------------------------------------------
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DEMO_REPO = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "demo", "repository"))
_CLEAN_REPO = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "demo", "clean_repo"))
_ESCALATE_REPO = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "demo", "escalate_repo"))

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.database import Base, get_db
from app.main import app as fastapi_app

# ------------------------------------------------------------------
# Test database (file-based SQLite for multi-thread agent workers)
# ------------------------------------------------------------------
_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_phase5_test.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_test_db():
    import app.models  # noqa: F401 — register models
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Override FastAPI dependency
    prev_override = fastapi_app.dependency_overrides.get(get_db)
    fastapi_app.dependency_overrides[get_db] = get_test_db

    # Redirect orchestrator's per-thread SessionLocal to the test DB
    import app.orchestration.orchestrator as _orch
    prev_session = _orch.SessionLocal
    _orch.SessionLocal = TestingSession  # type: ignore[attr-defined]

    yield

    # Restore
    if prev_override is None:
        fastapi_app.dependency_overrides.pop(get_db, None)
    else:
        fastapi_app.dependency_overrides[get_db] = prev_override
    _orch.SessionLocal = prev_session

    engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.unlink(_TEST_DB_PATH)
        except OSError:
            pass  # Windows file lock — harmless


@pytest.fixture()
def client():
    return TestClient(fastapi_app)


@pytest.fixture()
def db_session():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


# ===========================================================================
# TestWorkspaceIsolation
# ===========================================================================

class TestWorkspaceIsolation:
    """Replay workspace isolation: SAFE cases must not see buggy files."""

    def test_create_isolated_workspace_included_files(self, tmp_path):
        """Only included files appear in workspace; buggy file excluded."""
        from app.replay.engine import _create_isolated_workspace, _cleanup_workspace

        # Create a fake source repo with two files
        src = tmp_path / "src"
        src.mkdir()
        (src / "clean.py").write_text("x = 1\n")
        (src / "buggy.py").write_text("raise RuntimeError('bug')\n")
        (src / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")

        tmpdir = _create_isolated_workspace(
            str(src),
            included_files=["clean.py", "pyproject.toml"],
        )
        try:
            ws = os.path.join(tmpdir, "repo")
            assert os.path.isfile(os.path.join(ws, "clean.py"))
            assert os.path.isfile(os.path.join(ws, "pyproject.toml"))
            assert not os.path.exists(os.path.join(ws, "buggy.py")), \
                "buggy.py must NOT be in the isolated workspace"
        finally:
            _cleanup_workspace(tmpdir)
        assert not os.path.exists(tmpdir), "Workspace must be cleaned up after use"

    def test_create_isolated_workspace_no_filter(self, tmp_path):
        """Without included_files, full directory is copied."""
        from app.replay.engine import _create_isolated_workspace, _cleanup_workspace

        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("")
        (src / "b.py").write_text("")

        tmpdir = _create_isolated_workspace(str(src), included_files=None)
        try:
            ws = os.path.join(tmpdir, "repo")
            assert os.path.isfile(os.path.join(ws, "a.py"))
            assert os.path.isfile(os.path.join(ws, "b.py"))
        finally:
            _cleanup_workspace(tmpdir)

    def test_create_isolated_workspace_rejects_traversal(self, tmp_path):
        """Path traversal in included_files is silently skipped (not copied)."""
        from app.replay.engine import _create_isolated_workspace, _cleanup_workspace

        src = tmp_path / "src"
        src.mkdir()
        (src / "safe.py").write_text("")

        tmpdir = _create_isolated_workspace(
            str(src),
            included_files=["../evil.py", "safe.py"],
        )
        try:
            ws = os.path.join(tmpdir, "repo")
            # evil.py must not appear in workspace (traversal skipped)
            evil = os.path.join(ws, "..", "evil.py")
            assert not os.path.exists(os.path.normpath(evil))
            # safe.py copied normally
            assert os.path.isfile(os.path.join(ws, "safe.py"))
        finally:
            _cleanup_workspace(tmpdir)

    def test_workspace_cleanup_always_runs(self, tmp_path):
        """Workspace is removed even if engine raises mid-way."""
        from app.replay.engine import _create_isolated_workspace, _cleanup_workspace

        src = tmp_path / "src"
        src.mkdir()
        tmpdir = _create_isolated_workspace(str(src), included_files=None)
        assert os.path.isdir(tmpdir)
        _cleanup_workspace(tmpdir)
        assert not os.path.exists(tmpdir)

    def test_safe_case_no_false_alarm(self, db_session):
        """
        A SAFE replay case that runs against clean_repo must NOT produce BUG_DETECTED.
        This is the core correctness test for workspace isolation.
        """
        from app.replay.engine import ReplayEngine, _create_isolated_workspace
        from app.models import ReplayCase, GroundTruthEnum, ReplayAgentEnum

        # Seed a SAFE case pointing to clean_repo
        case = ReplayCase(
            id=str(uuid.uuid4()),
            label=f"test_safe_isolation_{uuid.uuid4().hex[:8]}",
            description="SAFE isolation test",
            repository_path=_CLEAN_REPO,
            included_files=json.dumps([
                "string_utils.py",
                "test_string_utils.py",
                "pyproject.toml",
            ]),
            ground_truth=GroundTruthEnum.SAFE,
            ground_truth_source=ReplayAgentEnum.RECEIPTS,
            is_valid=True,
        )
        db_session.add(case)
        db_session.commit()

        engine = ReplayEngine()
        result = engine._run_single_case(db_session, case)

        assert not result.execution_failed, f"Execution failed: {result.error}"
        assert result.false_alarm is False, (
            f"SAFE case produced false alarm! verdict={result.verdict}. "
            "This means the workspace was not properly isolated."
        )
        assert result.verdict == "SAFE", f"Expected SAFE, got {result.verdict}"


# ===========================================================================
# TestAuditConcurrency
# ===========================================================================

class TestAuditConcurrency:
    """threading.Lock serialisation: concurrent writes produce a valid chain."""

    def test_serial_chain_valid(self, db_session):
        """Sequential writes produce a valid chain."""
        from app.audit.service import record_event, verify_chain
        from app.models import ReviewRun, ReviewStatusEnum

        run_id = str(uuid.uuid4())
        # Need a ReviewRun row for the FK
        from app.models import Repository, PullRequest
        repo = Repository(id=str(uuid.uuid4()), name=f"audit_serial_{uuid.uuid4().hex[:6]}")
        db_session.add(repo)
        db_session.flush()
        pr = PullRequest(
            id=str(uuid.uuid4()), repo_id=repo.id, number=1,
            title="t", base_branch="main",
        )
        db_session.add(pr)
        db_session.flush()
        rr = ReviewRun(
            id=run_id, pr_id=pr.id, risk_level="low",
            status=ReviewStatusEnum.COMPLETED,
        )
        db_session.add(rr)
        db_session.commit()

        for i in range(5):
            record_event(db_session, f"event_{i}", review_run_id=run_id,
                         payload={"seq": i})

        result = verify_chain(db_session, run_id)
        assert result.valid, f"Chain invalid: {result.errors}"
        assert result.total_events == 5

    def test_concurrent_writes_produce_valid_chain(self, db_session):
        """
        N concurrent threads each call record_event; final chain must be valid.
        This verifies _audit_lock serialises writes correctly.
        """
        from app.audit.service import record_event, verify_chain
        from app.models import ReviewRun, ReviewStatusEnum, Repository, PullRequest

        run_id = str(uuid.uuid4())
        repo = Repository(id=str(uuid.uuid4()), name=f"audit_conc_{uuid.uuid4().hex[:6]}")
        db_session.add(repo)
        db_session.flush()
        pr = PullRequest(
            id=str(uuid.uuid4()), repo_id=repo.id, number=1,
            title="t", base_branch="main",
        )
        db_session.add(pr)
        db_session.flush()
        rr = ReviewRun(
            id=run_id, pr_id=pr.id, risk_level="low",
            status=ReviewStatusEnum.COMPLETED,
        )
        db_session.add(rr)
        db_session.commit()

        N = 8
        errors_list: list[Exception] = []

        def _writer(idx: int):
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                record_event(db, "concurrent_event", review_run_id=run_id,
                             payload={"thread": idx})
            except Exception as exc:
                errors_list.append(exc)
            finally:
                db.close()

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors_list, f"Concurrent writes raised: {errors_list}"

        result = verify_chain(db_session, run_id)
        assert result.valid, f"Chain invalid after concurrent writes: {result.errors}"
        assert result.total_events == N

    def test_tampered_payload_detected(self, db_session):
        """verify_chain must report invalid when canonical_payload is tampered."""
        from app.audit.service import record_event, verify_chain
        from app.models import AuditEvent, ReviewRun, ReviewStatusEnum, Repository, PullRequest

        run_id = str(uuid.uuid4())
        repo = Repository(id=str(uuid.uuid4()), name=f"audit_tamper_{uuid.uuid4().hex[:6]}")
        db_session.add(repo)
        db_session.flush()
        pr = PullRequest(
            id=str(uuid.uuid4()), repo_id=repo.id, number=1,
            title="t", base_branch="main",
        )
        db_session.add(pr)
        db_session.flush()
        rr = ReviewRun(
            id=run_id, pr_id=pr.id, risk_level="low",
            status=ReviewStatusEnum.COMPLETED,
        )
        db_session.add(rr)
        db_session.commit()

        record_event(db_session, "event_a", review_run_id=run_id, payload={"v": 1})
        record_event(db_session, "event_b", review_run_id=run_id, payload={"v": 2})

        # Tamper the first event's canonical_payload
        ev = (
            db_session.query(AuditEvent)
            .filter(AuditEvent.review_run_id == run_id)
            .order_by(AuditEvent.created_at.asc())
            .first()
        )
        ev.canonical_payload = '{"v":99}'  # tampered
        db_session.commit()

        result = verify_chain(db_session, run_id)
        assert not result.valid, "Tampered payload must be detected"
        assert len(result.errors) > 0

    def test_audit_lock_is_threading_lock(self):
        """_audit_lock must be a real threading.Lock (process-local serialisation)."""
        from app.audit.service import _audit_lock
        assert isinstance(_audit_lock, type(threading.Lock())), \
            "_audit_lock must be a threading.Lock instance"


# ===========================================================================
# TestSecurityHardening
# ===========================================================================

class TestSecurityHardening:
    """Security: path traversal prevention, input validation, symlinks."""

    def test_validate_repo_name_accepts_normal(self):
        from app.security import validate_repo_name
        assert validate_repo_name("demo") == "demo"
        assert validate_repo_name("my-repo_1.0") == "my-repo_1.0"

    def test_validate_repo_name_rejects_slash(self):
        from app.security import validate_repo_name
        with pytest.raises(ValueError, match="path"):
            validate_repo_name("../../etc/passwd")

    def test_validate_repo_name_rejects_backslash(self):
        from app.security import validate_repo_name
        with pytest.raises(ValueError):
            validate_repo_name("foo\\bar")

    def test_validate_repo_name_rejects_dotdot(self):
        from app.security import validate_repo_name
        with pytest.raises(ValueError):
            validate_repo_name("..")

    def test_validate_repo_name_rejects_null_byte(self):
        from app.security import validate_repo_name
        with pytest.raises(ValueError):
            validate_repo_name("repo\x00evil")

    def test_validate_repo_name_rejects_empty(self):
        from app.security import validate_repo_name
        with pytest.raises(ValueError):
            validate_repo_name("")

    def test_validate_repo_name_rejects_special_chars(self):
        from app.security import validate_repo_name
        with pytest.raises(ValueError):
            validate_repo_name("repo;ls")

    def test_safe_path_join_normal(self, tmp_path):
        from app.security import safe_path_join
        result = safe_path_join(str(tmp_path), "subdir/file.txt")
        assert result.startswith(str(tmp_path))

    def test_safe_path_join_traversal_detected(self, tmp_path):
        from app.security import safe_path_join
        with pytest.raises(ValueError, match="traversal"):
            safe_path_join(str(tmp_path), "../../etc/passwd")

    def test_api_rejects_traversal_repo_name(self, client):
        """POST /repos/.%2F.%2Fetc/prs/1/review must return 400."""
        # FastAPI path param decodes percent-encoding, forward slash separates segments
        # We use a repo name with only disallowed chars that pass URL encoding
        r = client.post(
            "/repos/../etc/prs/1/review",
            json={"pr_title": "test"},
        )
        # FastAPI may 404 on path separator or 400 on our validation
        assert r.status_code in (400, 404, 422), \
            f"Expected 400/404/422 for traversal repo, got {r.status_code}"

    def test_api_rejects_shell_special_chars(self, client):
        """Repo name with shell special chars returns 400."""
        r = client.post(
            "/repos/foo;bar/prs/1/review",
            json={"pr_title": "test"},
        )
        # FastAPI 422 for invalid path param or 400 from our validator
        assert r.status_code in (400, 422), \
            f"Expected 400/422 for special-char repo, got {r.status_code}"

    def test_truncate_output_short(self):
        from app.security import truncate_output
        text = "hello world"
        assert truncate_output(text, max_len=100) == text

    def test_truncate_output_long(self):
        from app.security import truncate_output
        text = "x" * 1000
        result = truncate_output(text, max_len=100)
        assert len(result) < 1000
        assert "truncated" in result

    def test_sandbox_uses_no_shell(self):
        """Sandbox.run must call subprocess with a list (not shell=True)."""
        import subprocess
        calls = []
        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return original_run(["echo", "ok"], capture_output=True, text=True)

        import app.sandbox.sandbox as sb_mod
        original = sb_mod.subprocess.run
        sb_mod.subprocess.run = mock_run
        try:
            with sb_mod.Sandbox.__new__(sb_mod.Sandbox) as _:
                pass
        except Exception:
            pass
        finally:
            sb_mod.subprocess.run = original

        # Even without actually entering, verify the Sandbox code never uses shell=True
        import ast, inspect
        src = inspect.getsource(sb_mod.Sandbox.run)
        # shell=True must not appear in the source
        assert "shell=True" not in src, "Sandbox must never use shell=True"


# ===========================================================================
# TestBobEvidenceRef
# ===========================================================================

class TestBobEvidenceRef:
    """BobEvidenceRef extension point — never auto-populated."""

    def test_receipt_has_bob_evidence_ref_field(self):
        """Receipt model has bob_evidence_ref column (nullable)."""
        from app.models import Receipt
        assert hasattr(Receipt, "bob_evidence_ref")

    def test_receipt_schema_has_bob_evidence_ref(self):
        """ReceiptOut schema includes bob_evidence_ref (optional)."""
        from app.schemas import ReceiptOut
        fields = ReceiptOut.model_fields
        assert "bob_evidence_ref" in fields
        # Must be optional (default None)
        assert fields["bob_evidence_ref"].default is None

    def test_bob_evidence_ref_schema_exists(self):
        """BobEvidenceRef schema is importable and has expected fields."""
        from app.schemas import BobEvidenceRef
        schema = BobEvidenceRef(session_id="abc", artifact_type="session", note="test")
        assert schema.session_id == "abc"
        assert schema.artifact_type == "session"

    def test_review_pipeline_does_not_populate_bob_ref(self, client):
        """After a review the bob_evidence_ref on receipts is None."""
        r = client.post("/repos/demo/prs/1/review", json={"pr_title": "Bob ref test"})
        assert r.status_code == 201
        run_id = r.json()["id"]

        r2 = client.get(f"/reviews/{run_id}/receipts")
        assert r2.status_code == 200
        receipts = r2.json()
        assert len(receipts) > 0
        for receipt in receipts:
            assert receipt.get("bob_evidence_ref") is None, \
                "bob_evidence_ref must never be auto-populated by the pipeline"


# ===========================================================================
# TestEndToEndVerdicts
# ===========================================================================

class TestEndToEndVerdicts:
    """SAFE, BUG_DETECTED, ESCALATE end-to-end via API."""

    def test_bug_detected_verdict(self, client, db_session):
        """demo/repository contains buggy_stats.py → BUG_DETECTED."""
        # Temporarily seed a repo pointing to demo/repository
        from app.models import Repository
        repo_name = f"e2e_bug_{uuid.uuid4().hex[:8]}"
        repo = Repository(
            id=str(uuid.uuid4()), name=repo_name, local_path=_DEMO_REPO
        )
        db_session.add(repo)
        db_session.commit()

        r = client.post(
            f"/repos/{repo_name}/prs/1/review",
            json={"pr_title": "E2E BUG test"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["verdict"] == "BUG_DETECTED", \
            f"Expected BUG_DETECTED for demo/repository, got {data['verdict']}"

    def test_safe_verdict(self, client, db_session):
        """demo/clean_repo → SAFE (no bugs, all tests pass)."""
        from app.models import Repository
        repo_name = f"e2e_safe_{uuid.uuid4().hex[:8]}"
        repo = Repository(
            id=str(uuid.uuid4()), name=repo_name, local_path=_CLEAN_REPO
        )
        db_session.add(repo)
        db_session.commit()

        r = client.post(
            f"/repos/{repo_name}/prs/1/review",
            json={"pr_title": "E2E SAFE test"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["verdict"] == "SAFE", \
            f"Expected SAFE for demo/clean_repo, got {data['verdict']}"

    def test_escalate_verdict(self, client, db_session):
        """demo/escalate_repo (no tests) → ESCALATE."""
        from app.models import Repository
        repo_name = f"e2e_esc_{uuid.uuid4().hex[:8]}"
        repo = Repository(
            id=str(uuid.uuid4()), name=repo_name, local_path=_ESCALATE_REPO
        )
        db_session.add(repo)
        db_session.commit()

        r = client.post(
            f"/repos/{repo_name}/prs/1/review",
            json={"pr_title": "E2E ESCALATE test"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["verdict"] == "ESCALATE", \
            f"Expected ESCALATE for escalate_repo (no tests), got {data['verdict']}"

    def test_review_404_on_nonexistent_run(self, client):
        """GET /reviews/{run_id} returns 404 for unknown run."""
        r = client.get(f"/reviews/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_receipts_404_on_nonexistent_run(self, client):
        """GET /reviews/{run_id}/receipts returns 404 for unknown run."""
        r = client.get(f"/reviews/{uuid.uuid4()}/receipts")
        assert r.status_code == 404

    def test_audit_verify_valid_after_review(self, client):
        """Audit chain must be valid after a normal review."""
        r = client.post("/repos/demo/prs/1/review", json={"pr_title": "Audit E2E"})
        assert r.status_code == 201
        run_id = r.json()["id"]

        r2 = client.get(f"/reviews/{run_id}/audit/verify")
        assert r2.status_code == 200
        data = r2.json()
        assert data["valid"] is True, f"Audit chain invalid: {data}"
        assert data["total_events"] > 0


# ===========================================================================
# TestReplayDemoCases
# ===========================================================================

class TestReplayDemoCases:
    """3 BUG + 3 SAFE cases, zero false alarms."""

    def test_seed_creates_six_cases(self, client):
        """POST /replay/seed creates 6 demo cases."""
        r = client.post("/replay/seed")
        assert r.status_code == 201
        cases = r.json()
        assert len(cases) >= 6, f"Expected ≥6 cases, got {len(cases)}"

    def test_bug_cases_present(self, client):
        """At least 3 BUG cases seeded."""
        client.post("/replay/seed")
        r = client.get("/replay/cases")
        assert r.status_code == 200
        cases = r.json()
        bug_cases = [c for c in cases if c["ground_truth"] == "BUG"]
        assert len(bug_cases) >= 3, f"Expected ≥3 BUG cases, got {len(bug_cases)}"

    def test_safe_cases_present(self, client):
        """At least 3 SAFE cases seeded."""
        client.post("/replay/seed")
        r = client.get("/replay/cases")
        assert r.status_code == 200
        cases = r.json()
        safe_cases = [c for c in cases if c["ground_truth"] == "SAFE"]
        assert len(safe_cases) >= 3, f"Expected ≥3 SAFE cases, got {len(safe_cases)}"

    def test_replay_zero_false_alarms(self, client):
        """
        Run all replay cases — SAFE cases must not produce false alarms.
        This is the definitive test that workspace isolation works end-to-end.
        """
        client.post("/replay/seed")

        r = client.post("/replay/run", json={"label": "phase5_zero_false_alarms"})
        assert r.status_code == 201
        run = r.json()
        assert run["status"] == "completed"

        metrics = json.loads(run["metrics_json"])
        assert metrics["false_alarms"] == 0, (
            f"Got {metrics['false_alarms']} false alarm(s). "
            "SAFE cases incorrectly flagged as BUG_DETECTED. "
            f"Full metrics: {metrics}"
        )

    def test_replay_catches_known_bugs(self, client):
        """BUG cases must be caught (not missed)."""
        client.post("/replay/seed")

        r = client.post("/replay/run", json={"label": "phase5_catch_bugs"})
        assert r.status_code == 201
        run = r.json()

        metrics = json.loads(run["metrics_json"])
        assert metrics["caught_bugs"] >= 1, \
            f"No bugs caught. metrics={metrics}"
        assert metrics["missed_bugs"] == 0, \
            f"Some bugs missed. metrics={metrics}"


# ===========================================================================
# TestDemoCLI
# ===========================================================================

class TestDemoCLI:
    """demo_cli.py commands execute without crashing."""

    def _run_cli_fn(self, fn_name: str) -> int:
        """Import demo_cli and call the named function directly."""
        # Add backend to sys.path for demo_cli imports
        cli_path = os.path.join(_BACKEND_DIR, "demo_cli.py")
        assert os.path.isfile(cli_path), f"demo_cli.py not found at {cli_path}"

        import importlib.util
        spec = importlib.util.spec_from_file_location("demo_cli", cli_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, fn_name)
        return fn()

    def test_health_exits_zero(self):
        rc = self._run_cli_fn("cmd_health")
        assert rc == 0, f"cmd_health returned {rc}"

    def test_review_exits_zero(self):
        rc = self._run_cli_fn("cmd_review")
        assert rc == 0, f"cmd_review returned {rc}"

    def test_bug_exits_zero(self):
        # review must run first to produce a bug receipt
        self._run_cli_fn("cmd_review")
        rc = self._run_cli_fn("cmd_bug")
        assert rc == 0, f"cmd_bug returned {rc}"

    def test_audit_exits_zero(self):
        self._run_cli_fn("cmd_review")
        rc = self._run_cli_fn("cmd_audit")
        assert rc == 0, f"cmd_audit returned {rc}"

    def test_replay_exits_zero(self):
        rc = self._run_cli_fn("cmd_replay")
        assert rc == 0, f"cmd_replay returned {rc}"
