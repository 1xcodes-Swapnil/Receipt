# API Reference — Receipts

## Base URL

```
http://localhost:8000
```

All endpoints return JSON. Error responses use FastAPI default format: `{"detail": "..."}`.

---

## Health

### `GET /health`

Returns system health status.

**Response 200**
```json
{"status": "ok", "version": "0.1.0"}
```

---

## Review Management

### `POST /repos/{repo}/prs/{number}/review`

Triggers a full review of the specified PR. Runs 4 agents in parallel (TestRunner, CatchingTest, DocumentationCheck, HistoryCheck) then runs the adaptive strategy planner.

**Path parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `repo` | str | Repository name (created if not exists) |
| `number` | int | PR number |

**Request body** (optional)
```json
{
  "pr_title": "PR Review",
  "author": null,
  "base_branch": "main",
  "head_branch": null,
  "commit_sha": null
}
```

**Response 201** → `ReviewRunOut`
```json
{
  "id": "uuid",
  "pr_id": "uuid",
  "risk_level": "medium",
  "status": "completed",
  "confidence": 1.0,
  "verdict": "BUG_DETECTED",
  "started_at": "2024-01-01T00:00:00",
  "completed_at": "2024-01-01T00:00:03",
  "elapsed_ms": 3223
}
```

Verdict values: `SAFE` | `BUG_DETECTED` | `ESCALATE`

---

### `GET /reviews/{run_id}`

Returns a review run with nested agent executions and receipts.

**Response 200** → `ReviewRunDetail`
```json
{
  "id": "uuid",
  "pr_id": "uuid",
  "risk_level": "medium",
  "status": "completed",
  "confidence": 1.0,
  "verdict": "BUG_DETECTED",
  "pull_request": {...},
  "agent_executions": [...],
  "receipts": [...]
}
```

---

### `GET /reviews/{run_id}/receipts`

Returns all evidence receipts for a review run.

**Response 200** → `list[ReceiptOut]`
```json
[{
  "id": "uuid",
  "review_run_id": "uuid",
  "agent_execution_id": "uuid",
  "agent": "test_runner",
  "title": "pytest: 3 failed",
  "command": "pytest test_buggy_stats.py -v",
  "result_summary": "FAIL",
  "raw_output": "FAILED test_buggy_stats.py::test_mean_empty_list",
  "severity": "HIGH",
  "confidence": 1.0,
  "bob_evidence_ref": null,
  "created_at": "..."
}]
```

---

### `GET /reviews/{run_id}/events`

Returns persisted review events (not SSE — returns the stored event list).

**Response 200** → `list[ReviewEventOut]`

---

### `GET /reviews/{run_id}/stream`

SSE stream for live review progress.

**Response** `text/event-stream`

Event types:
- `review.started`
- `agent.started`
- `agent.progress`
- `receipt.created`
- `agent.completed`
- `agent.failed`
- `review.completed`
- `keepalive`

If the review is already complete, past events are replayed.

---

## Immunity Pipeline

### `POST /reviews/{run_id}/immunity`

Starts the Bug-to-Immunity V7 pipeline for a BUG_DETECTED review run.

**Request body** (optional)
```json
{"source_receipt_ids": ["uuid1", "uuid2"]}
```

**Response 201** → `ImmunityPipelineOut`
```json
{
  "id": "uuid",
  "review_run_id": "uuid",
  "status": "escalated",
  "source_receipt_ids": null,
  "current_stage": "root_cause",
  "created_at": "...",
  "updated_at": "..."
}
```

Status values: `pending` | `running` | `passed` | `failed` | `blocked` | `escalated`

---

### `GET /immunity/{pipeline_id}`

Returns pipeline detail with stages and sibling findings.

**Response 200** → `ImmunityPipelineDetail`
```json
{
  "id": "uuid",
  "status": "escalated",
  "stages": [
    {"stage_type": "reproduce", "status": "passed", ...},
    {"stage_type": "root_cause", "status": "escalated", ...}
  ],
  "sibling_findings": []
}
```

---

### `GET /immunity/{pipeline_id}/stages`

Returns list of stage results for a pipeline.

**Response 200** → `list[ImmunityStageOut]`

---

## Pattern Library

### `GET /patterns`

Lists all pattern library entries.

**Response 200** → `list[PatternLibraryEntryOut]`

---

### `GET /patterns/search?q={query}`

Searches patterns by description.

**Query parameters**: `q` (required) — search string  
**Response 200** → `list[PatternLibraryEntryOut]`

---

### `GET /patterns/{pattern_id}`

Returns a single pattern entry.

**Response 200** → `PatternLibraryEntryOut`  
**Response 404** if not found

---

## Replay Engine

### `GET /replay/cases`

Lists all replay cases.

**Response 200** → `list[ReplayCaseOut]`

---

### `POST /replay/run`

Runs the replay benchmark (all valid cases, or specified case IDs).

**Request body**
```json
{"case_ids": null, "label": "my_run"}
```

**Response 201** → `ReplayRunOut`
```json
{
  "id": "uuid",
  "label": "replay_20240101_000000",
  "status": "completed",
  "metrics_json": "{\"catch_rate\": 1.0, \"false_alarm_rate\": 0.0, \"accuracy\": 1.0, ...}",
  "total_cases": 6,
  "cases_run": 6,
  "cases_failed": 0
}
```

---

### `POST /replay/validate`

Validates all replay cases (marks invalid ones, returns summary).

**Response 200** → `{"valid": 6, "invalid": 0, "total": 6}`

---

### `GET /replay/runs`

Lists all replay runs.

**Response 200** → `list[ReplayRunOut]`

---

### `GET /replay/runs/{run_id}`

Returns a specific replay run.

**Response 200** → `ReplayRunOut`

---

### `GET /replay/runs/{run_id}/results`

Returns all results for a replay run (Phase 8: includes `planner_trace_json`, `strategies_used`, `strategy_count`).

**Response 200** → `list[ReplayResultOut]`

---

## Audit

### `GET /audit/events`

Returns all audit events, optionally filtered by review run.

**Query parameters**: `run_id` (optional)  
**Response 200** → `list[AuditEventOut]`

---

### `GET /audit/verify/{run_id}`

Verifies the audit hash chain for a review run.

**Response 200** → `AuditVerificationOut`
```json
{
  "valid": true,
  "total_events": 21,
  "error_count": 0,
  "errors": []
}
```

---

## Evidence (Adaptive — Phase 5+)

### `GET /reviews/{run_id}/evidence`

Returns all evidence items collected for a review run.

**Response 200** → `list[EvidenceItemOut]`

---

### `GET /reviews/{run_id}/claims`

Returns all claims for a review run.

**Response 200** → `list[ReviewClaimOut]`

---

### `GET /reviews/{run_id}/gaps`

Returns all evidence gaps for a review run.

**Response 200** → `list[EvidenceGapOut]`

---

### `GET /reviews/{run_id}/trace`

Returns the strategy execution trace for a review run.

**Response 200** → `list[StrategyTraceEntryOut]`

---

## Common Error Codes

| Code | Description |
|------|-------------|
| 404 | Resource not found |
| 422 | Validation error (missing required field) |
| 500 | Internal server error (check logs) |
