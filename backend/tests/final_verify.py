"""
Final verification script — updated for Phase 5.

Verifies the core end-to-end path:
  POST /repos/demo/prs/42/review
    → review_run created
    → Test Runner executes
    → agent_execution created
    → receipt created
    → verdict generated
    → GET /reviews/{id} returns data
    → React would display result

All sessions (including agent worker threads) use the same fresh in-memory DB.
"""
import sys
import os

# Ensure backend package is importable when running from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import app.models  # noqa: F401 — register all models
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.config import settings

# ---------------------------------------------------------------------------
# Fresh file-based SQLite — file DB required for multi-thread agent workers.
# In-memory + StaticPool cannot handle concurrent commits from thread pool.
# ---------------------------------------------------------------------------
import tempfile as _tempfile
_tmp_db_fd, _tmp_db_path = _tempfile.mkstemp(suffix="_final_verify.db")
os.close(_tmp_db_fd)

_engine = create_engine(
    f"sqlite:///{_tmp_db_path}",
    connect_args={"check_same_thread": False},
)
_Session = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
Base.metadata.create_all(bind=_engine)

settings.demo_repo_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "demo", "repository")
)


def _override():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


# Patch ALL session factories so worker threads use the same DB
fastapi_app.dependency_overrides[get_db] = _override
import app.orchestration.orchestrator as _orch
import app.database as _db

_orch.SessionLocal = _Session
_db.SessionLocal = _Session

client = TestClient(fastapi_app)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
r = client.get("/health")
assert r.status_code == 200
assert r.json()["status"] == "ok"
print("health:         PASS")

# ---------------------------------------------------------------------------
# Run review against demo/repository (has buggy_stats.py → BUG_DETECTED)
# ---------------------------------------------------------------------------
r = client.post("/repos/demo/prs/42/review", json={"pr_title": "Final Verify"})
assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
run_data = r.json()
run_id = run_data["id"]
verdict = run_data["verdict"]
status = run_data["status"]
elapsed = run_data["elapsed_ms"]

print(f"review created: PASS  verdict={verdict}  status={status}  elapsed_ms={elapsed}")
assert verdict == "BUG_DETECTED", f"Expected BUG_DETECTED for demo/repository, got {verdict}"
assert status == "completed"
print("verdict:        PASS  (BUG_DETECTED as expected for demo/repository)")

# ---------------------------------------------------------------------------
# Receipts endpoint — at least one FAIL receipt from test_runner
# ---------------------------------------------------------------------------
r2 = client.get(f"/reviews/{run_id}/receipts")
assert r2.status_code == 200
receipts = r2.json()
assert len(receipts) >= 1, f"Expected ≥1 receipt, got {len(receipts)}"

# Find the test_runner receipt
tr_receipts = [rec for rec in receipts if rec.get("agent") == "test_runner"]
assert len(tr_receipts) >= 1, f"No test_runner receipt found. receipts={receipts}"
rec = tr_receipts[0]

agent_field     = rec["agent"]
command_field   = rec["command"]
result_field    = rec["result_summary"]
severity_field  = rec["severity"]
confidence      = rec["confidence"]
file_ref        = rec["file_ref"]
raw_output      = rec.get("raw_output") or ""
bob_ref         = rec.get("bob_evidence_ref")

print(f"receipt.agent:          {agent_field}")
print(f"receipt.command:        {command_field}")
print(f"receipt.result_summary: {result_field}")
print(f"receipt.severity:       {severity_field}")
print(f"receipt.confidence:     {confidence}")
print(f"receipt.file_ref:       {file_ref}  (null in FAIL is normal)")
print(f"receipt.bob_evidence_ref: {bob_ref}  (None — extension point only)")
print(f"receipt.raw_output:     {raw_output[:80]}...")

assert agent_field == "test_runner", f"Expected test_runner, got: {agent_field}"
assert "pytest" in command_field
assert result_field == "FAIL", f"Expected FAIL for demo/repository, got {result_field}"
assert severity_field in ("HIGH", "CRITICAL"), f"Expected HIGH/CRITICAL severity, got {severity_field}"
assert confidence > 0
assert "====" in raw_output, "Raw output must contain real pytest output"
assert bob_ref is None, "bob_evidence_ref must never be auto-populated"
print("receipt fields: PASS")

# ---------------------------------------------------------------------------
# Review detail endpoint
# ---------------------------------------------------------------------------
r3 = client.get(f"/reviews/{run_id}")
assert r3.status_code == 200
detail = r3.json()
assert len(detail["agent_executions"]) >= 1, "Must have ≥1 agent execution"
assert len(detail["receipts"]) >= 1, "Must have ≥1 receipt"
tr_detail_receipts = [rec for rec in detail["receipts"] if rec.get("agent") == "test_runner"]
assert len(tr_detail_receipts) >= 1, "test_runner receipt must appear in detail view"
print("review detail:  PASS")

# ---------------------------------------------------------------------------
# 404 for unknown run
# ---------------------------------------------------------------------------
r4 = client.get("/reviews/nonexistent")
assert r4.status_code == 404
print("404 handling:   PASS")

# ---------------------------------------------------------------------------
# Audit chain — valid after review
# ---------------------------------------------------------------------------
r5 = client.get(f"/reviews/{run_id}/audit/verify")
assert r5.status_code == 200
audit_result = r5.json()
assert audit_result["valid"] is True, f"Audit chain invalid: {audit_result}"
assert audit_result["total_events"] > 0, "Must have audit events"

# Verify required event types
db = _Session()
from app.models import AuditEvent
events = db.query(AuditEvent).filter(AuditEvent.review_run_id == run_id).all()
types = {e.event_type for e in events}
required = {"review_started", "agent_started", "agent_completed", "receipt_created", "verdict_created"}
assert types >= required, f"Missing audit event types: {required - types}"
assert all(e.integrity_hash for e in events), "All events must have integrity_hash"
db.close()
print("audit events:   PASS")

# ---------------------------------------------------------------------------
# Verdict logic unit test (backward-compatible)
# ---------------------------------------------------------------------------
from app.agents.base import AgentEvidence
from app.orchestration.orchestrator import _calculate_verdict

v1, _ = _calculate_verdict([AgentEvidence("t", "cmd", "PASS", "out", confidence=1.0)])
v2, _ = _calculate_verdict([AgentEvidence("t", "cmd", "FAIL", "out", confidence=1.0)])
v3, _ = _calculate_verdict([AgentEvidence("t", "cmd", "ERROR", "out", confidence=0.0)])
v4, _ = _calculate_verdict([])
assert v1 == "SAFE",         f"Expected SAFE, got {v1}"
assert v2 == "BUG_DETECTED", f"Expected BUG_DETECTED, got {v2}"
assert v3 == "ESCALATE",     f"Expected ESCALATE, got {v3}"
assert v4 == "ESCALATE",     f"Expected ESCALATE, got {v4}"
print("verdict logic:  PASS  SAFE/BUG_DETECTED/ESCALATE all correct")

# ---------------------------------------------------------------------------
# Phase 5: SAFE verdict from clean_repo
# ---------------------------------------------------------------------------
_CLEAN_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "demo", "clean_repo")
)
from app.models import Repository
db = _Session()
_clean_repo_name = f"final_verify_clean_{__import__('uuid').uuid4().hex[:8]}"
clean_repo = Repository(
    id=__import__("uuid").uuid4().hex,
    name=_clean_repo_name,
    local_path=_CLEAN_REPO,
)
db.add(clean_repo)
db.commit()
db.close()

r6 = client.post(
    f"/repos/{_clean_repo_name}/prs/1/review",
    json={"pr_title": "Final Verify — SAFE"},
)
assert r6.status_code == 201, f"Expected 201: {r6.text}"
safe_data = r6.json()
assert safe_data["verdict"] == "SAFE", (
    f"Expected SAFE for clean_repo, got {safe_data['verdict']}"
)
print("safe verdict:   PASS  (clean_repo = SAFE)")

# ---------------------------------------------------------------------------
# Config no-deprecation-warning
# ---------------------------------------------------------------------------
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    from importlib import reload
    import app.config
    reload(app.config)
    pydantic_warns = [x for x in w if "PydanticDeprecatedSince20" in str(x.category)]
    assert len(pydantic_warns) == 0, f"Pydantic deprecation warnings: {pydantic_warns}"
print("config no-warn: PASS")

print()
print("=== ALL FINAL CHECKS PASS ===")
