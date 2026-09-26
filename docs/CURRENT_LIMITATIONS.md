# Current Limitations — Receipts

This document records known limitations, partial implementations, and deferred features as of Phase 8. It is maintained honestly: no feature is claimed complete if it is stubbed, partial, or deferred.

---

## Repository Integration

### GitHub Provider (Partial)
- `GitHubRepositoryProvider.check_availability()` — **fully implemented**
- `ProviderStatus`, `ProviderUnavailableError` — **fully implemented**
- GitHub REST API methods (`_api_get()`, `_load_pr_info()`, `_ensure_clone()`) — **implemented but not tested with real token in CI**
- The provider is not used by `ReviewOrchestrator` in the current review flow — the orchestrator still accepts a `repository_path_override` string directly
- **Limitation**: GitHub PR review does not flow through the provider in production

### Git History Dependency
- `get_diff()`, `get_head_commit()`, `get_parent_commit()` require `.git/` to exist
- Demo repositories (`demo/repository/`, `demo/clean_repo/`) may not have git history
- Graceful degradation: returns empty diff / None commit, continues review

---

## Bug-to-Immunity Pipeline

### Root Cause Stage (Demo Limitation)
- In the Phase 8 demo run, the immunity pipeline was **ESCALATED at Root Cause**
- `stage=root_cause status=ESCALATED (0 ms)`
- The `HypothesisTracker` could not produce a `VERIFIED` resolution for the demo repository's accumulator bug
- This is **correct fail-closed behavior** — the system did not fabricate a root cause
- The pipeline does not advance to Fix without a verified root cause

### Fix Strategies (Conservative)
- 11 of 12 fix strategies (all except `accumulator_reset`) apply detection logic but **do not auto-apply changes** in all cases — they return `success=False` with a pattern-identified note
- Only `AccumulatorResetStrategy` produces a real `success=True` patch
- This is intentional: conservative strategies require manual review for safety
- **Implication**: IMMUNITY_COMPLETE is only achievable for the accumulator reset pattern in the current implementation

### ImmunityOrchestratorV7 — Fresh Workspace
- The retry loop creates fresh workspaces correctly (`context._replace_workspace()`)
- However, the staging from reproduction evidence to Fix requires that `RootCauseStageV7` produces a `VERIFIED` hypothesis — which currently requires traceback evidence pointing to a specific file/line
- Tricky bugs where the traceback is not informative will be ESCALATED

---

## Strategy Planner

### Phase 6 Advanced Strategies (Rarely Activated)
- All 7 Phase 6 advanced strategies are implemented and tested
- In practice, the Phase 8 demo showed that **all 6 replay cases ran only Phase 5 strategies** — Phase 6 was not needed because `existing_tests` produced sufficient evidence
- Phase 6 strategies are activated only when a claim gap remains after Phase 5 strategies
- For the current demo repositories (purpose-built to have obvious bugs/passes), the base set is always sufficient

### Advisory Strategy Results
- `documentation_analysis` returned FAIL for all 6 replay cases
- This FAIL is advisory and did not affect verdict
- The demo repositories lack README files, causing consistent documentation FAIL

---

## Audit Chain

### Process-Local Lock Only
- The audit chain uses a `threading.Lock` — correct for single-process deployments
- Multi-process deployments (multiple uvicorn workers, Gunicorn) would require database-level serialization
- Current deployment model: single uvicorn process

### No Tamper Detection at Startup
- `verify_chain()` is called on demand (via API or demo script)
- There is no automatic integrity check at application startup
- Tampering is detectable post-hoc but not prevented

---

## Replay Benchmark

### Demo Cases Only
- The 6 benchmark cases were constructed specifically to demonstrate the system
- All use the same two demo repositories: `demo/repository/` (buggy) and `demo/clean_repo/` (clean)
- All 6 cases ran the same 5-strategy sequence
- **The 1.0 accuracy is a demo result, not a real-world benchmark**
- A rigorous benchmark requires diverse, independently-labeled, real-world cases

### Replay Does Not Validate Case Diversity
- `validate_cases()` checks that `repository_path` exists and `ground_truth` is valid
- It does not check for case diversity, label independence, or coverage breadth

---

## Audit Events

### Limited Event Coverage
- Audit events cover: review_started, agent lifecycle, verdict, immunity lifecycle
- Strategy-level events (individual strategy execution) are **not** individually audited — only the overall review verdict is
- `EvidenceItem` and `StrategyTraceEntry` records exist in DB but are not hashed into the audit chain

---

## Configuration

### app_version Hardcoded
- `app_version = "0.1.0"` in `config.py` — not updated by phase
- The `.env.example` suggests `APP_VERSION=0.8.0` but the code default is `0.1.0`

### No Auto-Migration
- Schema changes require manual `Base.metadata.create_all()` on a fresh DB or `DROP TABLE` + recreate
- Phase 8 added columns to `replay_result` — existing databases need the new columns
- SQLite `ALTER TABLE ADD COLUMN` will work for additive changes; not needed for fresh installs

---

## Frontend

- The Phase 1 React frontend at `frontend/` is **not active** in the current backend architecture
- The backend is a standalone API; no UI is provided in Phase 8

---

## Production Readiness

| Concern | Status |
|---------|--------|
| Authentication | ❌ Not implemented — API is open |
| Rate limiting | ❌ Not implemented |
| PostgreSQL deployment | ⚠️ Schema is PostgreSQL-compatible; `create_all()` works; not tested in CI |
| Multi-process audit safety | ❌ Process-local lock only |
| Token/secret management | ⚠️ GITHUB_TOKEN read from env; no secret rotation |
| Error monitoring | ⚠️ Python logging only; no structured error reporting |
| Containerization | ❌ No Dockerfile provided |
| Health endpoint | ✅ `GET /health` returns status + version |

---

## Not Implemented / Deferred

The following were explicitly **deferred** per AGENTS.md:

- Phase 3+ Bug-to-Immunity in full automated production mode (root cause works for simple patterns only)
- Replay Scoreboard / leaderboard
- GitHub Actions integration for automatic PR review
- Redis / PostgreSQL production deployment configuration
- Advanced AI reasoning (Phase 9+) — no LLM planner
- Paperclip (explicitly excluded from all phases)
- watsonx / Granite (explicitly excluded from all phases)
