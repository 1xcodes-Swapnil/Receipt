# Evidence and Receipts

## The Core Invariant

> **NO EVIDENCE, NO FLAG.**

A finding is only valid when backed by a **receipt** — a record containing:
- The exact command executed
- Real stdout/stderr output
- The verdict derived from that output

The system never fabricates, simulates, or approximates test outcomes.

## Receipts

A **Receipt** is the primary evidence record produced by an agent. It is persisted in SQLite with a SHA-256 integrity hash.

### Receipt Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `review_run_id` | FK | Parent review run |
| `agent_execution_id` | FK | Agent that produced it |
| `title` | str | Human-readable description |
| `command` | str | Exact command run (e.g. `pytest test_buggy_stats.py`) |
| `test_ref` | str | Test name/path reference |
| `result_summary` | str | `PASS` or `FAIL` |
| `raw_output` | text | Real stdout+stderr, unmodified |
| `file_ref` | str | File reference (if applicable) |
| `severity` | enum | PASS / INFO / LOW / MEDIUM / HIGH / CRITICAL |
| `confidence` | float | 0.0–1.0 |
| `bob_evidence_ref` | text | Extension point — never auto-populated |
| `created_at` | datetime | Creation time |

### Bob Evidence Reference

`bob_evidence_ref` is an **extension point only**. The application never auto-populates this field and never fabricates Bob session IDs. A human or external integration may populate it after the fact with:
```json
{"session_id": "<uuid>", "artifact_type": "...", "note": "..."}
```

## Claims

A **Claim** is something the system is trying to prove or disprove about the PR. Each review generates claims before strategy execution begins.

### Claim Types

| Claim Type | Description | Verdict Contribution |
|-----------|-------------|---------------------|
| `code_correctness` | Does the code pass its tests? | AUTHORITATIVE |
| `test_coverage` | Are changed paths covered? | AUTHORITATIVE |
| `documentation` | Is documentation adequate? | ADVISORY |

### Claim Lifecycle

```
OPEN → SUPPORTED (evidence confirms)
     → REFUTED (evidence contradicts)
     → INSUFFICIENT (evidence tried, inconclusive)
     → CONFLICTED (contradictory evidence)
```

## Evidence Items

An **EvidenceItem** is a structured evidence record produced by a strategy execution.

### EvidenceItem Fields

| Field | Description |
|-------|-------------|
| `strategy_name` | Strategy that produced this item |
| `evidence_type` | e.g. "test_failure", "ast_finding", "property_violation" |
| `result` | PASS / FAIL / INSUFFICIENT / CONFLICT / ERROR |
| `confidence` | 0.0–1.0 |
| `command` | Command run (if applicable) |
| `raw_output` | Real stdout/stderr |
| `file_ref` | File reference |
| `line_ref` | Line number |
| `is_independent` | False if derived from another evidence item |
| `depends_on_evidence_id` | Parent evidence ID (if not independent) |

## Evidence Gaps

When a claim cannot be resolved because evidence is missing, conflicting, or from a failed strategy, an **EvidenceGap** is recorded.

### Gap Types

| Gap Type | Meaning |
|----------|---------|
| `MISSING` | No evidence collected for this claim |
| `CONFLICTING` | Evidence items contradict each other |
| `STALE` | Evidence from a previous run |
| `FAILED_STRATEGY` | Strategy execution failed |

## Evidence Ledger

The **EvidenceLedger** (in-memory, per review run) tracks:
- All claims and their current status
- All evidence items linked to claims
- Contradictions between evidence items
- Which claims depend on which evidence

### Sufficiency Evaluation

After each strategy execution, the planner asks: "Is the evidence sufficient to conclude?"

**Sufficient positive evidence** → `SAFE`  
**Sufficient negative evidence** → `BUG_DETECTED`  
**Insufficient after budget exhausted** → `ESCALATE`

## Repository Snapshot

Before any strategy executes, an immutable **RepositorySnapshot** is created.

### Snapshot Properties

- **Hash-verified**: SHA-256 hash of the repo content at snapshot time
- **Immutable**: frozen dataclass — no modification after creation
- **Isolated**: each strategy runs against a workspace copy, never the original
- **Secret-filtered**: keys/tokens are redacted from file content using pattern matching
  - Patterns: "secret", "token", "password", "passwd", "key", "api_key", "auth", "credential", "private", "jwt", "bearer"
- **Path-safe**: rejects path traversal (`..`) and symlinks

### Snapshot Metadata

| Field | Description |
|-------|-------------|
| `snapshot_id` | UUID |
| `repository_path` | Absolute path |
| `snapshot_hash` | SHA-256 of repo state |
| `commit_sha` | HEAD commit (if git available) |
| `files` | List of tracked file paths |
| `created_at` | Snapshot time |

## Fail-Closed Behavior

| Situation | Result |
|-----------|--------|
| Agent execution error | ESCALATE |
| Agent timeout | ESCALATE |
| Strategy raises exception | ERROR result → ESCALATE |
| Missing evidence after budget | ESCALATE |
| Contradictory evidence | ESCALATE |
| Fabricated/simulated evidence | **Never permitted** |
