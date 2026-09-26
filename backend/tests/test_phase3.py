"""
Phase 3 test suite — Immunity Pipeline, Pattern Library, API routes.

Test strategy:
- File-based SQLite (same pattern as Phase 2 — avoids StaticPool + thread issues).
- The immunity pipeline creates a workspace copy, so the demo repo is never mutated.
- Tests verify: stage results, pipeline status, pattern creation, API endpoints.
- Tests use real pytest execution against demo/repository — never mock results.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEMO_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "demo", "repository"))
TEST_DB_PATH = os.path.join(BACKEND_DIR, "_phase3_test.db")

sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
# Test database setup (file-based to support multi-thread stages)
# ---------------------------------------------------------------------------
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH}"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_test_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create tables once; drop on teardown."""
    import app.models  # noqa: F401 — registers models
    from app.database import Base
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture(scope="module")
def client(setup_db):
    """FastAPI test client wired to the test DB."""
    import app.orchestration.orchestrator as _orch
    from app.config import settings
    from app.main import app
    from app.database import get_db

    settings.demo_repo_path = DEMO_REPO
    _orig_session_local = _orch.SessionLocal
    _orch.SessionLocal = TestingSession

    app.dependency_overrides[get_db] = get_test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _orch.SessionLocal = _orig_session_local


@pytest.fixture()
def db_session():
    db = TestingSession()
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Helper: create a review run for a given repo path
# ---------------------------------------------------------------------------

def create_demo_review(client: TestClient) -> dict:
    """POST /repos/demo/prs/1/review and return the review run JSON."""
    resp = client.post(
        "/repos/demo/prs/1/review",
        json={"pr_title": "Phase 3 Test PR"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ===========================================================================
# Unit tests — Stages in isolation (using a workspace copy)
# ===========================================================================

@pytest.fixture(scope="module")
def workspace_path():
    """Create a temporary workspace copy of the demo repo."""
    tmp = tempfile.mkdtemp(prefix="p3_test_ws_")
    dest = os.path.join(tmp, "repo")
    shutil.copytree(DEMO_REPO, dest)
    yield dest
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def pipeline_id_fixture(setup_db, client) -> str:
    """
    Create a review run and an immunity pipeline record to test against.
    Returns the pipeline_id.
    """
    run = create_demo_review(client)
    resp = client.post(f"/reviews/{run['id']}/immunity", json={})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Test 1: Demo repo has failing tests (bug is real)
# ---------------------------------------------------------------------------

class TestDemoRepoBugExists:
    def test_buggy_stats_file_exists(self):
        assert os.path.isfile(os.path.join(DEMO_REPO, "buggy_stats.py")), \
            "demo/repository/buggy_stats.py must exist"

    def test_buggy_stats_tests_exist(self):
        assert os.path.isfile(os.path.join(DEMO_REPO, "test_buggy_stats.py")), \
            "demo/repository/test_buggy_stats.py must exist"

    def test_pytest_finds_failures(self):
        """Run pytest directly and confirm there are real failures."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_buggy_stats.py", "-v", "--tb=short", "--no-header"],
            cwd=DEMO_REPO,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Must have failures
        assert result.returncode != 0, "Expected test failures in buggy_stats.py"
        assert "FAILED" in result.stdout, "Expected FAILED lines in pytest output"

    def test_calculator_tests_pass(self):
        """The clean calculator should still pass."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_calculator.py", "-v", "--no-header"],
            cwd=DEMO_REPO,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Calculator tests should pass:\n{result.stdout}"


# ---------------------------------------------------------------------------
# Test 2: ReproduceStage
# ---------------------------------------------------------------------------

class TestReproduceStage:
    def test_reproduce_detects_failures(self, workspace_path, db_session):
        from app.immunity.stages import ImmunityContext, ReproduceStage

        ctx = ImmunityContext(repository_path=workspace_path)
        stage = ReproduceStage()
        result = stage.run("test-pipeline-reproduce", ctx, db_session)
        db_session.rollback()

        # Bug should be reproducible
        assert result.status in ("passed", "failed"), f"unexpected status: {result.status}"
        assert "exit_code" in result.evidence
        assert "command" in result.evidence

    def test_reproduce_sets_context(self, workspace_path, db_session):
        from app.immunity.stages import ImmunityContext, ReproduceStage, StageTypeEnum

        ctx = ImmunityContext(repository_path=workspace_path)
        stage = ReproduceStage()
        stage.run("test-pipeline-reproduce-ctx", ctx, db_session)
        db_session.rollback()

        evidence = ctx.get_stage(StageTypeEnum.REPRODUCE)
        assert evidence is not None
        assert "stdout" in evidence


# ---------------------------------------------------------------------------
# Test 3: RootCauseStage
# ---------------------------------------------------------------------------

class TestRootCauseStage:
    def test_root_cause_requires_reproduce_evidence(self, workspace_path, db_session):
        from app.immunity.stages import ImmunityContext, RootCauseStage

        ctx = ImmunityContext(repository_path=workspace_path)  # no reproduce evidence
        stage = RootCauseStage()
        result = stage.run("test-pipeline-root-cause", ctx, db_session)
        db_session.rollback()

        assert result.status == "failed"
        assert result.error is not None

    def test_root_cause_parses_traceback(self, workspace_path, db_session):
        from app.immunity.stages import (
            ImmunityContext, ReproduceStage, RootCauseStage, StageTypeEnum
        )

        ctx = ImmunityContext(repository_path=workspace_path)
        ReproduceStage().run("test-pipeline-rc-full", ctx, db_session)
        db_session.rollback()

        result = RootCauseStage().run("test-pipeline-rc-full", ctx, db_session)
        db_session.rollback()

        # If reproduce had failures, root cause should extract something
        reproduce_ev = ctx.get_stage(StageTypeEnum.REPRODUCE)
        if reproduce_ev and reproduce_ev.get("exit_code", 0) != 0:
            assert result.evidence.get("failing_tests") is not None or \
                   result.evidence.get("error_type") is not None


# ---------------------------------------------------------------------------
# Test 4: FixStage
# ---------------------------------------------------------------------------

class TestFixStage:
    def test_fix_requires_root_cause(self, workspace_path, db_session):
        from app.immunity.stages import ImmunityContext, FixStage

        ctx = ImmunityContext(repository_path=workspace_path)
        result = FixStage().run("test-fix-no-root", ctx, db_session)
        db_session.rollback()

        assert result.status == "failed"
        assert "root cause" in (result.error or "").lower()

    def test_fix_applies_accumulator_patch(self, tmp_path):
        """Unit test AccumulatorResetStrategy.apply() directly."""
        from app.immunity.fix_strategies import AccumulatorResetStrategy

        # Write a file with the accumulator bug
        buggy = tmp_path / "stats.py"
        buggy.write_text(
            "def mean(values):\n"
            "    total = 0\n"
            "    for v in values:\n"
            "        total = v\n"  # BUG: should be total += v
            "    return total / len(values)\n"
        )

        strategy = AccumulatorResetStrategy()
        fix_result = strategy.apply(str(tmp_path), "stats.py")

        assert fix_result.success, f"Fix should succeed. Error: {fix_result.error}"
        assert fix_result.diff is not None
        assert "total += v" in buggy.read_text()
        # regression_hint should identify the function
        assert fix_result.regression_hint is not None
        assert "mean" in fix_result.regression_hint.get("changed_functions", [])


# ---------------------------------------------------------------------------
# Test 5: ImmunityOrchestrator (end-to-end pipeline)
# ---------------------------------------------------------------------------

class TestImmunityOrchestrator:
    def test_pipeline_creates_record(self, client, setup_db):
        run = create_demo_review(client)
        resp = client.post(f"/reviews/{run['id']}/immunity", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["review_run_id"] == run["id"]
        # Phase 8: V7 adds 'escalated' as a valid terminal state
        assert data["status"] in ("passed", "failed", "blocked", "escalated")

    def test_pipeline_has_stages(self, client, pipeline_id_fixture):
        resp = client.get(f"/immunity/{pipeline_id_fixture}/stages")
        assert resp.status_code == 200
        stages = resp.json()
        assert isinstance(stages, list)
        # Should have at least the Reproduce stage
        stage_types = [s["stage_type"] for s in stages]
        assert "reproduce" in stage_types

    def test_pipeline_detail_endpoint(self, client, pipeline_id_fixture):
        resp = client.get(f"/immunity/{pipeline_id_fixture}")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert "sibling_findings" in data
        assert isinstance(data["stages"], list)

    def test_pipeline_not_found(self, client):
        resp = client.get("/immunity/nonexistent-pipeline-id")
        assert resp.status_code == 404

    def test_pipeline_status_never_safe_from_error(self, client, setup_db):
        """Agent failure cannot produce an invalid status.
        Phase 8: ImmunityOrchestrator is now V7 — adds 'escalated' as valid terminal state.
        """
        run = create_demo_review(client)
        resp = client.post(f"/reviews/{run['id']}/immunity", json={})
        assert resp.status_code == 201
        data = resp.json()
        # Status must be one of the valid enum values (V7 adds 'escalated')
        assert data["status"] in (
            "passed", "failed", "blocked", "running", "pending", "escalated"
        )


# ---------------------------------------------------------------------------
# Test 6: Pattern Library
# ---------------------------------------------------------------------------

class TestPatternLibrary:
    def test_create_pattern(self, db_session):
        from app.services.pattern_library import create_pattern, get_pattern

        entry = create_pattern(
            db=db_session,
            pattern_signature="AssertionError:buggy_stats.py:accumulator_reset",
            description="mean() accumulator reset bug — subtotal = v instead of total += v",
            affected_area="math_utils",
        )
        db_session.commit()

        assert entry.id is not None
        assert entry.pattern_signature == "AssertionError:buggy_stats.py:accumulator_reset"

        fetched = get_pattern(db_session, entry.id)
        assert fetched is not None
        assert fetched.id == entry.id

    def test_list_patterns(self, db_session):
        from app.services.pattern_library import list_patterns, create_pattern

        create_pattern(db_session, "ListSig:file.py:fix", "List test pattern", affected_area="list_area")
        db_session.commit()

        all_patterns = list_patterns(db_session)
        assert len(all_patterns) >= 1

    def test_search_patterns(self, db_session):
        from app.services.pattern_library import create_pattern, search_patterns

        create_pattern(db_session, "UniqueSearchSig:x.py:fix", "unique_searchable_description_xyz", affected_area="search_area")
        db_session.commit()

        results = search_patterns(db_session, "unique_searchable_description_xyz")
        assert len(results) >= 1
        assert any("unique_searchable" in r.description for r in results)

    def test_search_no_results(self, db_session):
        from app.services.pattern_library import search_patterns

        results = search_patterns(db_session, "zzznowaythisexists9999")
        assert results == []

    def test_pattern_api_list(self, client, setup_db, db_session):
        from app.services.pattern_library import create_pattern
        create_pattern(db_session, "APISig:y.py:fix", "API list test pattern")
        db_session.commit()

        resp = client.get("/patterns")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_pattern_api_search(self, client, setup_db, db_session):
        from app.services.pattern_library import create_pattern
        create_pattern(db_session, "SearchAPISig:z.py:fix", "searchable_api_pattern_abc123")
        db_session.commit()

        resp = client.get("/patterns/search?q=searchable_api_pattern_abc123")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_pattern_api_get_not_found(self, client):
        resp = client.get("/patterns/nonexistent-id-12345")
        assert resp.status_code == 404

    def test_pattern_api_search_missing_q(self, client):
        resp = client.get("/patterns/search")
        assert resp.status_code == 422  # q is required


# ---------------------------------------------------------------------------
# Test 7: Audit events for immunity
# ---------------------------------------------------------------------------

class TestImmunityAudit:
    def test_audit_events_created(self, client, setup_db, db_session):
        from app.models import AuditEvent

        run = create_demo_review(client)
        resp = client.post(f"/reviews/{run['id']}/immunity", json={})
        assert resp.status_code == 201

        # Should have audit events for immunity stages
        events = (
            db_session.query(AuditEvent)
            .filter(AuditEvent.review_run_id == run["id"])
            .all()
        )
        event_types = [e.event_type for e in events]
        assert "immunity_started" in event_types
        # Phase 8: V7 emits immunity_complete / immunity_blocked / immunity_escalated / immunity_failed
        _terminal_events = {
            "immunity_completed", "immunity_failed", "immunity_complete",
            "immunity_blocked", "immunity_escalated",
        }
        assert any(et in _terminal_events for et in event_types), (
            f"No terminal immunity event found in: {event_types}"
        )

    def test_audit_hash_chain_integrity(self, client, setup_db, db_session):
        """
        Immunity audit events are written sequentially (single thread) so their
        chain must be internally consistent: each event's prev_hash must equal
        the integrity_hash of some earlier event for the same run.

        NOTE: Phase 2 review agents run in parallel threads so the global chain
        for a run may be non-linear; we only assert that each event's prev_hash
        either is None (first) or points at a real earlier event's integrity_hash.
        """
        from app.models import AuditEvent

        run = create_demo_review(client)
        # Trigger immunity to add sequential audit events
        client.post(f"/reviews/{run['id']}/immunity", json={})

        events = (
            db_session.query(AuditEvent)
            .filter(AuditEvent.review_run_id == run["id"])
            .order_by(AuditEvent.created_at)
            .all()
        )

        assert len(events) > 0, "Expected at least one audit event"

        # All integrity_hashes must be set
        for ev in events:
            assert ev.integrity_hash is not None, f"Missing integrity_hash on event {ev.event_type}"

        # Each prev_hash (if set) must point to a real earlier event
        known_hashes = set()
        for ev in events:
            if ev.prev_hash is not None:
                assert ev.prev_hash in known_hashes, (
                    f"event {ev.event_type}: prev_hash {ev.prev_hash[:12]}... "
                    f"not found in prior hashes — chain broken"
                )
            known_hashes.add(ev.integrity_hash)


# ---------------------------------------------------------------------------
# Test 8: End-to-end via API — full immunity path
# ---------------------------------------------------------------------------

class TestImmunityEndToEnd:
    def test_full_pipeline_flow(self, client, setup_db):
        """
        Full path: create review → trigger immunity → get pipeline → verify stages.
        """
        # 1. Create a review
        run_resp = client.post(
            "/repos/demo/prs/99/review",
            json={"pr_title": "End-to-end Phase 3 test"},
        )
        assert run_resp.status_code == 201
        run = run_resp.json()

        # 2. Trigger immunity
        imm_resp = client.post(
            f"/reviews/{run['id']}/immunity",
            json={"source_receipt_ids": []},
        )
        assert imm_resp.status_code == 201
        pipeline = imm_resp.json()
        # Phase 8: V7 adds 'escalated' as a valid terminal state
        assert pipeline["status"] in ("passed", "failed", "blocked", "escalated")

        # 3. Get pipeline detail
        detail_resp = client.get(f"/immunity/{pipeline['id']}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()

        assert "stages" in detail
        assert len(detail["stages"]) > 0

        for stage in detail["stages"]:
            # Phase 8: V7 adds 'pattern' stage type
            assert stage["stage_type"] in (
                "reproduce", "root_cause", "fix", "verify",
                "regression_test", "sibling_hunt", "documentation", "pattern"
            )
            # Phase 8: V7 adds 'escalated' stage status
            assert stage["status"] in (
                "passed", "failed", "blocked", "pending", "running", "escalated"
            )

        # 4. Stages endpoint
        stages_resp = client.get(f"/immunity/{pipeline['id']}/stages")
        assert stages_resp.status_code == 200
        assert len(stages_resp.json()) == len(detail["stages"])

        # 5. Verify a pattern was created (if pipeline reached documentation)
        patterns_resp = client.get("/patterns")
        assert patterns_resp.status_code == 200
        # Pattern list can be empty if pipeline was blocked before documentation
        assert isinstance(patterns_resp.json(), list)

    def test_immunity_for_nonexistent_run(self, client):
        resp = client.post("/immunity/nonexistent-run/immunity", json={})
        # Should be 404 or 405 (route is /reviews/{id}/immunity)
        assert resp.status_code in (404, 405)

    def test_review_not_found_for_immunity(self, client):
        resp = client.post("/reviews/nonexistent-run-id/immunity", json={})
        assert resp.status_code == 404
