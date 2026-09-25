"""
Backend test suite for Receipts Phase 1.

Tests:
- Health endpoint
- Demo review flow (POST /repos/demo/prs/1/review)
- GET /reviews/{run_id}
- GET /reviews/{run_id}/receipts
- TestRunner agent against demo repository
- Audit event creation
- Verdict logic
"""
from __future__ import annotations

import os
import sys

# Ensure backend/app is importable when running pytest from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app

# ---------------------------------------------------------------------------
# Test database — file-based SQLite (required for multi-thread agent workers).
# StaticPool + ThreadPoolExecutor = "cannot commit transaction" errors.
# ---------------------------------------------------------------------------

_TEST_DB_FILE = os.path.join(os.path.dirname(__file__), "_phase1_test.db")
TEST_DATABASE_URL = f"sqlite:///{_TEST_DB_FILE}"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    import app.models  # noqa: F401 — register models
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = override_get_db

# Point to demo repository relative to project root
DEMO_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "demo", "repository")
)

# Override demo_repo_path in settings for tests
import app.config as _cfg
_cfg.settings.demo_repo_path = DEMO_REPO

import app.orchestration.orchestrator as _orch  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create tables; drop DB file on teardown."""
    import app.models  # noqa: F401 — registers models
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    try:
        os.remove(_TEST_DB_FILE)
    except OSError:
        pass  # Windows file lock — harmless


@pytest.fixture(scope="module", autouse=True)
def patch_session_local(setup_db):
    """
    CRITICAL: patch _orch.SessionLocal for the duration of this module's tests.
    Ensures agent worker threads (ThreadPoolExecutor) write to the test DB.
    Restore after the module to not pollute other test modules.
    """
    original = _orch.SessionLocal
    _orch.SessionLocal = TestingSessionLocal  # type: ignore[attr-defined]
    yield
    _orch.SessionLocal = original


@pytest.fixture(scope="module")
def client(patch_session_local):
    with TestClient(fastapi_app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# Review flow
# ---------------------------------------------------------------------------

def test_create_review_demo(client):
    """POST /repos/demo/prs/1/review creates a run and returns a verdict."""
    resp = client.post(
        "/repos/demo/prs/1/review",
        json={"pr_title": "Test PR", "base_branch": "main"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["id"]
    assert data["status"] == "completed"
    assert data["verdict"] in ("SAFE", "BUG_DETECTED", "ESCALATE")
    assert data["elapsed_ms"] is not None


def test_get_review(client):
    """GET /reviews/{run_id} returns review with agent executions and receipts."""
    # Create a review first
    create_resp = client.post(
        "/repos/demo/prs/2/review",
        json={"pr_title": "Get Test PR"},
    )
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]

    resp = client.get(f"/reviews/{run_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == run_id
    assert len(data["agent_executions"]) >= 1
    assert len(data["receipts"]) >= 1

    # Verify receipt has real content
    receipt = data["receipts"][0]
    assert receipt["command"] is not None
    assert receipt["raw_output"] is not None
    assert len(receipt["raw_output"]) > 0
    assert receipt["result_summary"] in ("PASS", "FAIL", "ERROR", "TIMEOUT")


def test_get_review_not_found(client):
    resp = client.get("/reviews/nonexistent-id")
    assert resp.status_code == 404


def test_get_receipts(client):
    """GET /reviews/{run_id}/receipts returns a list of receipts."""
    create_resp = client.post(
        "/repos/demo/prs/3/review",
        json={"pr_title": "Receipts Test PR"},
    )
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]

    resp = client.get(f"/reviews/{run_id}/receipts")
    assert resp.status_code == 200
    receipts = resp.json()

    assert isinstance(receipts, list)
    assert len(receipts) >= 1
    for r in receipts:
        assert r["agent_execution_id"]
        assert r["result_summary"]
        assert r["confidence"] >= 0.0


# ---------------------------------------------------------------------------
# TestRunner unit test
# ---------------------------------------------------------------------------

def test_test_runner_against_demo():
    """TestRunner must produce real evidence from the demo repository.
    The demo repo now contains buggy_stats.py with deliberate failing tests (Phase 3),
    so the result may be PASS or FAIL — both are acceptable real results.
    What matters: evidence is real, command is set, and never fabricated.
    """
    from app.agents.test_runner import TestRunner

    runner = TestRunner()
    evidence = runner.run(DEMO_REPO)

    assert evidence.agent == "test_runner"
    assert evidence.command is not None
    assert evidence.result in ("PASS", "FAIL", "ERROR", "TIMEOUT")
    # Evidence must contain real output, not be empty
    assert evidence.evidence
    assert len(evidence.evidence) > 0
    # Confidence must be set for PASS/FAIL (real evidence exists)
    if evidence.result in ("PASS", "FAIL"):
        assert evidence.confidence > 0.0


def test_test_runner_missing_repo():
    """TestRunner against a non-existent path returns ERROR."""
    from app.agents.test_runner import TestRunner

    runner = TestRunner()
    evidence = runner.run("/nonexistent/path/that/does/not/exist")

    assert evidence.result == "ERROR"
    assert evidence.confidence == 0.0


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------

def test_audit_events_created(client):
    """Review run must produce review events (via /events endpoint)."""
    create_resp = client.post(
        "/repos/demo/prs/99/review",
        json={"pr_title": "Audit Test"},
    )
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]

    # Use the /events API endpoint — avoids direct DB session coupling
    events_resp = client.get(f"/reviews/{run_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    event_types = {e["event_type"] for e in events}

    assert "review.started" in event_types
    assert "agent.started" in event_types
    assert "review.completed" in event_types


# ---------------------------------------------------------------------------
# Verdict logic unit test
# ---------------------------------------------------------------------------

def test_verdict_pass():
    from app.agents.base import AgentEvidence
    from app.orchestration.orchestrator import _calculate_verdict

    evidence = AgentEvidence(agent="test_runner", command="pytest", result="PASS",
                             evidence="all good", confidence=1.0)
    verdict, conf = _calculate_verdict([evidence])
    assert verdict == "SAFE"
    assert conf == 1.0


def test_verdict_fail():
    from app.agents.base import AgentEvidence
    from app.orchestration.orchestrator import _calculate_verdict

    evidence = AgentEvidence(agent="test_runner", command="pytest", result="FAIL",
                             evidence="3 failed", confidence=1.0)
    verdict, conf = _calculate_verdict([evidence])
    assert verdict == "BUG_DETECTED"
    assert conf == 1.0


def test_verdict_error():
    from app.agents.base import AgentEvidence
    from app.orchestration.orchestrator import _calculate_verdict

    evidence = AgentEvidence(agent="test_runner", command="pytest", result="ERROR",
                             evidence="exception", confidence=0.0)
    verdict, conf = _calculate_verdict([evidence])
    assert verdict == "ESCALATE"
    assert conf == 0.0


def test_verdict_empty():
    from app.orchestration.orchestrator import _calculate_verdict

    verdict, conf = _calculate_verdict([])
    assert verdict == "ESCALATE"
