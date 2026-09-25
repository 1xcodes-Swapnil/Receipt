"""Final Phase 1 verification script."""
import sys, os
sys.path.insert(0, '.')
os.makedirs('F:/Bobproject/database', exist_ok=True)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
import app.models
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.config import settings

engine = create_engine(
    'sqlite:///F:/Bobproject/database/final_verify.db',
    connect_args={'check_same_thread': False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)
settings.demo_repo_path = 'F:/Bobproject/demo/repository'

def override():
    db = Session()
    try:
        yield db
    finally:
        db.close()

fastapi_app.dependency_overrides[get_db] = override
client = TestClient(fastapi_app)

# Health
r = client.get('/health')
assert r.status_code == 200
assert r.json()['status'] == 'ok'
print("health:         PASS")

# Run review
r = client.post('/repos/demo/prs/42/review', json={'pr_title': 'Final Verify'})
assert r.status_code == 201, r.text
run_data = r.json()
run_id = run_data['id']
verdict = run_data['verdict']
status = run_data['status']
elapsed = run_data['elapsed_ms']

print(f"review created: PASS  verdict={verdict}  status={status}  elapsed_ms={elapsed}")
assert verdict == 'SAFE', f'Expected SAFE, got {verdict}'
assert status == 'completed'

# Receipt via /receipts endpoint
r2 = client.get(f'/reviews/{run_id}/receipts')
assert r2.status_code == 200
receipts = r2.json()
assert len(receipts) == 1
rec = receipts[0]

agent_field     = rec['agent']
command_field   = rec['command']
result_field    = rec['result_summary']
severity_field  = rec['severity']
confidence      = rec['confidence']
file_ref        = rec['file_ref']
raw_output      = rec['raw_output'] or ''

print(f"receipt.agent:          {agent_field}")
print(f"receipt.command:        {command_field}")
print(f"receipt.result_summary: {result_field}")
print(f"receipt.severity:       {severity_field}")
print(f"receipt.confidence:     {confidence}")
print(f"receipt.file_ref:       {file_ref}  (null in PASS is correct)")
print(f"receipt.raw_output:     {raw_output[:80]}...")

assert agent_field == 'test_runner', f'Expected test_runner, got: {agent_field}'
assert 'pytest' in command_field
assert result_field == 'PASS'
assert severity_field == 'PASS'
assert confidence == 1.0
assert '====' in raw_output, 'Raw output must contain real pytest output'
print("receipt fields: PASS")

# Review detail endpoint
r3 = client.get(f'/reviews/{run_id}')
assert r3.status_code == 200
detail = r3.json()
assert len(detail['agent_executions']) == 1
assert len(detail['receipts']) == 1
assert detail['receipts'][0]['agent'] == 'test_runner'
print("review detail:  PASS")

# 404 for unknown run
r4 = client.get('/reviews/nonexistent')
assert r4.status_code == 404
print("404 handling:   PASS")

# Audit events
from app.models import AuditEvent
db = Session()
events = db.query(AuditEvent).filter(AuditEvent.review_run_id == run_id).all()
types = {e.event_type for e in events}
required = {'review_started','agent_started','agent_completed','receipt_created','verdict_created'}
assert types >= required, f'Missing audit event types: {required - types}'
assert all(e.integrity_hash for e in events), 'All events must have integrity_hash'
db.close()
print("audit events:   PASS")

# Verdict logic
from app.agents.base import AgentEvidence
from app.orchestration.orchestrator import _calculate_verdict
v1, _ = _calculate_verdict([AgentEvidence('t','cmd','PASS','out', confidence=1.0)])
v2, _ = _calculate_verdict([AgentEvidence('t','cmd','FAIL','out', confidence=1.0)])
v3, _ = _calculate_verdict([AgentEvidence('t','cmd','ERROR','out', confidence=0.0)])
v4, _ = _calculate_verdict([])
assert v1 == 'SAFE'
assert v2 == 'BUG_DETECTED'
assert v3 == 'ESCALATE'
assert v4 == 'ESCALATE'
print("verdict logic:  PASS  SAFE/BUG_DETECTED/ESCALATE all correct")

# Config no longer emits deprecation warning
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    from importlib import reload
    import app.config
    reload(app.config)
    pydantic_warns = [x for x in w if 'PydanticDeprecatedSince20' in str(x.category)]
    assert len(pydantic_warns) == 0, f'Pydantic deprecation warnings: {pydantic_warns}'
print("config no-warn: PASS")

print()
print("=== ALL FINAL CHECKS PASS ===")
