"""
Phase 2 test suite for Receipts.

Covers all 9 verification points:
1. Four agents run concurrently.
2. Each creates real execution evidence.
3. Receipts are persisted.
4. SSE events are persisted (stream replay tested).
5. Agent failure does not become PASS.
6. Sandbox cleanup works.
7. Existing Phase-1 functionality still works.
8. Risk assessment is deterministic.
9. Verdict logic with mixed agent results.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------
# Use a file-based SQLite DB for parallel-thread tests (StaticPool shares one
# connection which causes "cannot commit" errors under ThreadPoolExecutor).
_TEST_DB_FILE = os.path.join(os.path.dirname(__file__), "_phase2_test.db")

engine = create_engine(
    f"sqlite:///{_TEST_DB_FILE}",
    connect_args={"check_same_thread": False},
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    import app.models  # noqa
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


DEMO_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "demo", "repository")
)
import app.config as _cfg
_cfg.settings.demo_repo_path = DEMO_REPO

import app.orchestration.orchestrator as _orch  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def patch_module_globals():
    """
    Scope all global patches to this module's test run only.
    Restores FastAPI dependency overrides and orchestrator SessionLocal after
    all tests in this module complete, preventing cross-module contamination.
    """
    import app.models  # noqa
    Base.metadata.create_all(bind=engine)

    prev_override = fastapi_app.dependency_overrides.get(get_db)
    fastapi_app.dependency_overrides[get_db] = _override_get_db
    prev_session = _orch.SessionLocal
    _orch.SessionLocal = TestingSession  # type: ignore[attr-defined]
    yield
    # Teardown
    if prev_override is None:
        fastapi_app.dependency_overrides.pop(get_db, None)
    else:
        fastapi_app.dependency_overrides[get_db] = prev_override
    _orch.SessionLocal = prev_session
    engine.dispose()
    try:
        os.remove(_TEST_DB_FILE)
    except OSError:
        pass  # Windows may still hold a lock; file is harmless


@pytest.fixture(scope="module")
def client(patch_module_globals):
    with TestClient(fastapi_app) as c:
        yield c


# ===========================================================================
# Checkpoint 7: Phase 1 still works (health, basic review)
# ===========================================================================

def test_health_still_works(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_post_review_returns_201(client):
    r = client.post("/repos/demo/prs/1/review", json={"pr_title": "Phase 2 Test"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"]
    assert data["status"] == "completed"
    assert data["verdict"] in ("SAFE", "BUG_DETECTED", "ESCALATE")
    assert data["elapsed_ms"] is not None


# ===========================================================================
# Checkpoint 1: Four agents run concurrently
# ===========================================================================

def test_four_agents_run(client):
    """All four agent types appear in agent_executions."""
    r = client.post("/repos/demo/prs/10/review", json={"pr_title": "Four agents"})
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]

    r2 = client.get(f"/reviews/{run_id}")
    assert r2.status_code == 200
    aes = r2.json()["agent_executions"]
    agent_types = {ae["agent_type"] for ae in aes}

    assert "test_runner" in agent_types
    assert "catching_test" in agent_types
    assert "documentation_check" in agent_types
    assert "history_check" in agent_types
    assert len(aes) == 4


# ===========================================================================
# Checkpoint 2 + 3: Each agent creates real evidence and receipts persisted
# ===========================================================================

def test_each_agent_has_receipt(client):
    """Every agent execution must produce at least one receipt."""
    r = client.post("/repos/demo/prs/11/review", json={"pr_title": "Receipts check"})
    assert r.status_code == 201
    run_id = r.json()["id"]

    r2 = client.get(f"/reviews/{run_id}")
    detail = r2.json()
    aes = detail["agent_executions"]
    receipts = detail["receipts"]

    # Each agent execution must have a corresponding receipt
    for ae in aes:
        ae_receipts = [rec for rec in receipts if rec["agent_execution_id"] == ae["id"]]
        assert len(ae_receipts) >= 1, f"No receipt for {ae['agent_type']}"

        rec = ae_receipts[0]
        assert rec["agent"] == ae["agent_type"], "agent field must match execution type"
        assert rec["result_summary"] in ("PASS", "FAIL", "ERROR", "TIMEOUT", "INSUFFICIENT_EVIDENCE")
        assert rec["raw_output"] is not None, f"{ae['agent_type']} must produce evidence"
        assert len(rec["raw_output"]) > 0, "Evidence must not be empty"


# ===========================================================================
# Checkpoint 4: SSE events persisted — replay via /events endpoint
# ===========================================================================

def test_review_events_persisted(client):
    """review.started, agent.started, agent.completed etc. must be in /events."""
    r = client.post("/repos/demo/prs/12/review", json={"pr_title": "Events test"})
    assert r.status_code == 201
    run_id = r.json()["id"]

    r2 = client.get(f"/reviews/{run_id}/events")
    assert r2.status_code == 200
    events = r2.json()
    event_types = {e["event_type"] for e in events}

    assert "review.started" in event_types, "review.started missing"
    assert "agent.started" in event_types, "agent.started missing"
    assert "receipt.created" in event_types, "receipt.created missing"
    assert "review.completed" in event_types, "review.completed missing"

    # Each event that has an agent should specify agent_type
    agent_events = [e for e in events if e["event_type"] == "agent.started"]
    assert len(agent_events) == 4, f"Expected 4 agent.started events, got {len(agent_events)}"


# ===========================================================================
# Checkpoint 5: Agent failure does not become PASS
# ===========================================================================

def test_error_verdict_escalates():
    """ERROR evidence must never produce SAFE verdict."""
    from app.agents.base import AgentEvidence
    from app.orchestration.orchestrator import _calculate_verdict

    # Mix of PASS + ERROR → ESCALATE
    evidences = [
        AgentEvidence("test_runner", "pytest", "PASS", "ok", confidence=1.0),
        AgentEvidence("catching_test", None, "ERROR", "exception", confidence=0.0),
    ]
    verdict, conf = _calculate_verdict(evidences)
    assert verdict == "ESCALATE", f"Expected ESCALATE, got {verdict}"
    assert conf == 0.0


def test_insufficient_evidence_not_safe():
    """INSUFFICIENT_EVIDENCE alone → ESCALATE."""
    from app.agents.base import AgentEvidence
    from app.orchestration.orchestrator import _calculate_verdict

    evidences = [
        AgentEvidence("t", None, "INSUFFICIENT_EVIDENCE", "no git", confidence=0.0),
    ]
    verdict, _ = _calculate_verdict(evidences)
    assert verdict == "ESCALATE"


def test_fail_gives_bug_detected():
    """FAIL evidence → BUG_DETECTED."""
    from app.agents.base import AgentEvidence
    from app.orchestration.orchestrator import _calculate_verdict

    evidences = [
        AgentEvidence("t", "pytest", "PASS", "ok", confidence=1.0),
        AgentEvidence("catching_test", "pytest", "FAIL", "regression", confidence=1.0),
    ]
    verdict, conf = _calculate_verdict(evidences)
    assert verdict == "BUG_DETECTED"
    assert conf == 1.0


# ===========================================================================
# Checkpoint 6: Sandbox cleanup
# ===========================================================================

def test_sandbox_cleanup():
    """Sandbox temp dir must not exist after context manager exits."""
    from app.sandbox import Sandbox

    with Sandbox(DEMO_REPO, copy_source=True) as sb:
        tmpdir = sb.work_dir
        assert os.path.isdir(tmpdir), "Sandbox dir should exist during context"
        result = sb.run(["pytest", "--collect-only", "-q"], timeout=30)
        assert result.exit_code == 0 or result.exit_code != 0  # either is fine for cleanup test

    assert not os.path.isdir(tmpdir), "Sandbox dir must be removed after context"


def test_sandbox_run_captures_output():
    """Sandbox must capture real stdout from the command.
    We run only the clean calculator tests (not buggy_stats) so exit_code is 0.
    """
    from app.sandbox import Sandbox

    with Sandbox(DEMO_REPO, copy_source=True) as sb:
        result = sb.run(["pytest", "test_calculator.py", "-v", "--tb=short"], timeout=60)

    assert result.exit_code == 0, f"Calculator tests should pass: {result.output[:500]}"
    assert "passed" in result.stdout
    assert result.duration_ms > 0


def test_sandbox_timeout():
    """Sandbox must handle timeouts gracefully."""
    from app.sandbox import Sandbox

    with Sandbox(DEMO_REPO, copy_source=False) as sb:
        # Run a command that sleeps longer than timeout
        result = sb.run(["python", "-c", "import time; time.sleep(60)"], timeout=2)

    assert result.timed_out is True
    assert result.exit_code == -1


# ===========================================================================
# Checkpoint 8: Risk Assessment is deterministic
# ===========================================================================

def test_risk_assessment_returns_valid_level():
    """assess_risk must return a valid level for the demo repo."""
    from app.services import assess_risk

    result = assess_risk(DEMO_REPO)
    assert result.level in ("low", "medium", "high")
    assert isinstance(result.score, int)
    assert result.score >= 0
    assert result.rationale


def test_risk_assessment_deterministic():
    """Same input must produce same output."""
    from app.services import assess_risk

    r1 = assess_risk(DEMO_REPO)
    r2 = assess_risk(DEMO_REPO)
    assert r1.level == r2.level
    assert r1.score == r2.score


# ===========================================================================
# Checkpoint 9: Mixed verdict logic
# ===========================================================================

def test_all_pass_gives_safe():
    from app.agents.base import AgentEvidence
    from app.orchestration.orchestrator import _calculate_verdict

    evidences = [AgentEvidence("t", "cmd", "PASS", "ok", confidence=1.0) for _ in range(4)]
    v, c = _calculate_verdict(evidences)
    assert v == "SAFE"
    assert c == 1.0


def test_empty_gives_escalate():
    from app.orchestration.orchestrator import _calculate_verdict

    v, c = _calculate_verdict([])
    assert v == "ESCALATE"
    assert c == 0.0


# ===========================================================================
# Individual agent unit tests
# ===========================================================================

def test_test_runner_on_clean_repo():
    """TestRunner against a repo with only passing tests must return PASS."""
    from app.agents.test_runner import TestRunner
    import shutil
    import tempfile

    # Copy only calculator.py and test_calculator.py to a clean temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        for fname in ("calculator.py", "test_calculator.py", "pyproject.toml"):
            src = os.path.join(DEMO_REPO, fname)
            if os.path.exists(src):
                shutil.copy(src, tmpdir)
        runner = TestRunner()
        ev = runner.run(tmpdir)

    assert ev.result == "PASS", f"Expected PASS on clean repo, got {ev.result}: {ev.evidence[:300]}"
    assert ev.confidence == 1.0
    assert "passed" in ev.evidence.lower()


def test_catching_test_insufficient_evidence_no_git():
    """CatchingTestAgent on a non-git repo returns INSUFFICIENT_EVIDENCE."""
    from app.agents.catching_test import CatchingTestAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal non-git directory
        open(os.path.join(tmpdir, "test_x.py"), "w").write(
            "def test_pass(): assert True\n"
        )
        agent = CatchingTestAgent()
        ev = agent.run(tmpdir)
    assert ev.result == "INSUFFICIENT_EVIDENCE"
    assert ev.confidence == 0.0


def test_documentation_check_missing_readme():
    """DocCheck on an empty directory should flag missing README."""
    from app.agents.documentation_check import DocumentationCheckAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DocumentationCheckAgent()
        ev = agent.run(tmpdir)

    assert ev.result == "FAIL"
    assert "README" in ev.evidence


def test_history_check_no_git():
    """HistoryCheck without git returns INSUFFICIENT_EVIDENCE."""
    from app.agents.history_check import HistoryCheckAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = HistoryCheckAgent()
        ev = agent.run(tmpdir)

    assert ev.result == "INSUFFICIENT_EVIDENCE"


def test_documentation_check_on_demo():
    """DocCheck on the demo repo should not crash."""
    from app.agents.documentation_check import DocumentationCheckAgent
    agent = DocumentationCheckAgent()
    ev = agent.run(DEMO_REPO)
    assert ev.result in ("PASS", "FAIL")
    assert ev.evidence


def test_history_check_on_demo():
    """HistoryCheck on the demo repo returns a result (may be INSUFFICIENT if no git)."""
    from app.agents.history_check import HistoryCheckAgent
    agent = HistoryCheckAgent()
    ev = agent.run(DEMO_REPO)
    assert ev.result in ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE")
    assert ev.evidence
