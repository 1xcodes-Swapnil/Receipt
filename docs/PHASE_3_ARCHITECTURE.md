# Phase 3 Architecture — Bug-to-Immunity + Pattern Intelligence

## Status: Phase 3 implementation target

---

## Audit of Phase 1/2

### What exists and works

| Component | Location | Status |
|-----------|----------|--------|
| `ReviewOrchestrator` | `app/orchestration/orchestrator.py` | ✅ Working — 4 parallel agents, ThreadPoolExecutor |
| `BaseAgent` / `AgentEvidence` | `app/agents/base.py` | ✅ Stable interface |
| `TestRunner` | `app/agents/test_runner.py` | ✅ Real subprocess |
| `CatchingTestAgent` | `app/agents/catching_test.py` | ✅ git parent comparison |
| `DocumentationCheckAgent` | `app/agents/documentation_check.py` | ✅ README/link checks |
| `HistoryCheckAgent` | `app/agents/history_check.py` | ✅ git log analysis |
| `Sandbox` | `app/sandbox/sandbox.py` | ✅ tmpdir copy, timeout, cleanup |
| `EventBus` | `app/events/bus.py` | ✅ asyncio.Queue SSE |
| `RiskAssessment` | `app/services/risk.py` | ✅ deterministic |
| `AuditService` | `app/audit/service.py` | ✅ hash-chained |
| DB models (Phase 1/2) | `app/models.py` | ✅ 12 tables, skeletal Phase 3 stubs |
| API routes | `app/api/routes.py` | ✅ /health, /review, /stream, /events |

### What was stubbed and needs implementation

| Component | Notes |
|-----------|-------|
| `ImmunityPipeline` | Exists (skeletal) — needs full fields |
| `ImmunityStage` | Exists (skeletal) — needs stage_type, evidence, error, artifact_ref |
| `SiblingFinding` | Exists (skeletal) — needs pipeline_id, similarity_reason, confidence, verification_status |
| `PatternLibraryEntry` | Exists (skeletal) — needs pattern_signature, source_pipeline_id, etc. |
| `ReplayCase` / `ReplayResult` | Schema-only, Phase 4 |

---

## Phase 3 New Components

### 1. Repository Provider Abstraction

```
RepositoryProvider (ABC)
├── LocalRepositoryProvider   ← Phase 3 implemented
└── GitHubRepositoryProvider  ← Phase 3 interface stub only
```

Agents that currently hard-code local paths will be updated to accept a `RepositoryProvider`.

### 2. Immunity Pipeline

```
POST /reviews/{run_id}/immunity
  → ImmunityOrchestrator.start_pipeline(run_id, db)
    → Reproduce
    → RootCause
    → Fix
    → Verify
    → RegressionTest
    → SiblingHunt
    → Documentation
```

Each stage is a deterministic executor that:
- Creates an `ImmunityStage` row before executing
- Requires evidence to mark PASSED
- Blocks dependent stages on failure/insufficient evidence
- Persists evidence after every stage

### 3. Stage Types

| Stage | Input | Output | Pass Condition |
|-------|-------|--------|----------------|
| Reproduce | receipt + repo | SandboxResult | exit_code != 0 (bug reproduced) |
| RootCause | reproduction + repo | analysis text + file_ref | concrete file/location identified |
| Fix | root_cause + repo | diff + changed_files | fix applied to sandbox |
| Verify | fix + sandbox | before/after exit codes | before=FAIL, after=PASS |
| RegressionTest | fix + test_path | test file + command | test fails before, passes after |
| SiblingHunt | root_cause + repo | SiblingFinding[] | always POTENTIAL_MATCH |
| Documentation | fix + repo | files_changed | any docs updated OR justified skip |

### 4. Pattern Library

- Created only after successful Verify + RegressionTest
- Linked to ImmunityPipeline
- Searchable by pattern_signature (substring match)

### 5. Audit Events (Phase 3)

New event types added to `audit/service.py`:
- `immunity.started`
- `immunity.stage.started`
- `immunity.stage.completed`
- `immunity.stage.failed`
- `immunity.stage.blocked`
- `fix.checkpoint.created`
- `fix.applied`
- `verification.completed`
- `regression_test.created`
- `pattern.created`
- `immunity.completed`

---

## Database Schema Additions

### ImmunityPipeline (extended)

```sql
id, review_run_id, status, source_receipt_ids (JSON),
current_stage, created_at, updated_at
```

### ImmunityStage (extended)

```sql
id, pipeline_id, stage_type, status,
started_at, completed_at,
evidence (TEXT/JSON), error (TEXT),
artifact_ref (VARCHAR)
```

### SiblingFinding (extended)

```sql
id, pipeline_id, candidate_location, similarity_reason,
confidence, verification_status, evidence,
created_at
```

### PatternLibraryEntry (extended)

```sql
id, pattern_signature, description,
source_pipeline_id, regression_test_ref,
affected_area, metadata (JSON),
created_at
```

---

## Evidence Propagation Chain

```
ReviewRun.receipt
  └── ImmunityPipeline.source_receipt_ids
        └── ImmunityStage.evidence  (each stage links back)
              └── ImmunityStage[verify].evidence  (before/after)
                    └── RegressionTest artifact_ref
                          └── PatternLibraryEntry.regression_test_ref
```

---

## Demo Bug

A deterministic regression is introduced into `demo/repository/`:

- `buggy_stats.py` — a `mean()` function with an off-by-one bug
- `test_buggy_stats.py` — a test that **fails** due to the bug

This causes `TestRunner` to return `FAIL` → `BUG_DETECTED` verdict.
The immunity pipeline can then reproduce, root-cause, fix, and verify this exact bug.

---

## Scope Boundary

NOT in Phase 3:
- Replay Scoreboard
- Full GitHub connector (auth/token)  
- Final hash-chained audit
- Production auth
- Frontend UI beyond keeping existing routes working
