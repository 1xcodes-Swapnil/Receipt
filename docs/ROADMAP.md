# Roadmap — Receipts

This document records deferred features and potential future phases. Features listed here are **not implemented** in the current codebase.

Phase 8 is the current completed phase. The following is exploratory planning only — no implementation commitments.

---

## Current State (Phase 8 Complete)

| Component | Status |
|-----------|--------|
| 4 review agents | ✅ Implemented |
| Adaptive strategy planner | ✅ Implemented |
| 14 strategies (7 Phase 5 + 7 Phase 6) | ✅ Implemented |
| V7 Bug-to-Immunity (8 stages) | ✅ Implemented |
| SHA-256 audit chain | ✅ Implemented |
| Replay benchmark (6 demo cases) | ✅ Implemented |
| LocalRepositoryProvider | ✅ Implemented |
| GitHubRepositoryProvider | ✅ Implemented (not in production flow) |
| Demo runner + structured logging | ✅ Implemented |

---

## Phase 9 Candidates — Production Hardening

### Authentication
- Add API key or OAuth2 authentication to all endpoints
- Current state: API is open, no authentication

### Multi-process Audit Safety
- Replace process-local `threading.Lock` with PostgreSQL advisory lock or dedicated audit microservice
- Required for multi-worker deployments

### PostgreSQL Deployment
- Test full suite against PostgreSQL
- Add Alembic migration support for schema changes
- Current state: schema is PostgreSQL-compatible but not CI-tested

### Containerization
- Add Dockerfile + docker-compose
- Current state: runs directly from Python venv

---

## Phase 10 Candidates — Richer Bug Coverage

### Full Fix Strategy Completion
- Implement auto-apply for `BoundaryConditionStrategy`, `NullHandlingStrategy`, etc.
- Current state: detection implemented; auto-apply deferred for safety
- Requires: bounded patch scope, mandatory verification, rollback guarantee

### Broader Root Cause Evidence
- Extend `RootCauseStageV7` to handle cases where traceback points to a library, not user code
- Extend hypothesis verification to use coverage data + fault localization together

---

## Phase 11 Candidates — Real-World Benchmark

### Diverse Benchmark Cases
- Add real-world labeled cases from open-source repositories
- Current state: 6 demo cases on purpose-built repositories
- Required for meaningful accuracy claims

### Case Independence Validation
- Check that benchmark cases are independently labeled
- Check that SAFE cases and BUG cases come from different codebase states

### Benchmark Persistence
- Store benchmark results across runs for trend analysis
- Requires stable case identifiers (not re-seeded each run)

---

## Phase 12 Candidates — GitHub Integration

### PR Review via GitHub API
- Wire `GitHubRepositoryProvider` into `ReviewOrchestrator`
- Current state: provider implemented, not in production review flow
- Requires: token management, PR comment posting, webhook support

### GitHub Webhook Trigger
- Trigger review automatically on PR open/update
- Post review verdict as a PR check or comment

---

## Deferred / Out of Scope

The following were explicitly excluded from all phases:

| Feature | Status |
|---------|--------|
| Paperclip | ❌ Excluded — per AGENTS.md |
| watsonx / Granite | ❌ Excluded — per AGENTS.md |
| External LLM planner | ❌ Excluded — per AGENTS.md |
| Automatic PR merge | ❌ Excluded — unsafe |
| Fabricated evidence | ❌ Excluded — core invariant |

---

## Non-Goals (Permanent)

These are not future roadmap items — they contradict the core design:

- Predicting bugs without running tests (speculation without evidence)
- Emitting `SAFE` when evidence is missing
- Using model output as authoritative verdict without execution evidence
- Modifying production code automatically without human review gate
