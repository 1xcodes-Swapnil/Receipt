# Audit and Security — Receipts

## Audit Chain

Every significant event in the Receipts system produces an **audit event** persisted in `audit_event` with a **SHA-256 hash chain** linking each event to the previous one.

### Hash Algorithm

```
integrity_hash = SHA256(prev_hash + ":" + event_type + ":" + canonical_payload)
```

Where `canonical_payload` is the event payload serialized as JSON with **sorted keys and no extra whitespace** — this ensures deterministic hashing regardless of key insertion order.

The **first event** in a chain has `prev_hash = None`.

### Chain Structure

```
Event 1: prev_hash=None,     integrity_hash=H1
Event 2: prev_hash=H1,       integrity_hash=H2
Event 3: prev_hash=H2,       integrity_hash=H3
...
```

Any modification to event payload, hash, or ordering breaks the chain and is detected by `verify_chain()`.

### Audit Event Fields

| Field | Description |
|-------|-------------|
| `id` | UUID |
| `review_run_id` | Optional FK to review run |
| `event_type` | e.g. `review_started`, `immunity_started` |
| `payload` | Raw payload (for display) |
| `canonical_payload` | Deterministic JSON used in hash computation |
| `integrity_hash` | SHA-256 hash of this event |
| `prev_hash` | Hash of the previous event in chain |
| `entity_ref` | Optional reference (e.g. `review_run:abc`) |
| `sequence` | Monotonically-increasing integer (ordering authority) |
| `created_at` | Timestamp |

**Important**: `sequence` (not `created_at`) is the authoritative ordering for the hash chain. Parallel threads may commit with equal timestamps; sequence numbers are assigned under a lock and are always unique and monotonic.

### Event Types

| Event Type | Emitted By |
|-----------|-----------|
| `review_started` | ReviewOrchestrator |
| `agent_started` | Per-agent worker |
| `agent_completed` | Per-agent worker |
| `receipt_created` | Per-agent worker |
| `verdict_created` | ReviewOrchestrator |
| `immunity_started` | ImmunityOrchestratorV7 |
| `immunity_stage_started` | V7 stage runner |
| `immunity_stage_completed` | V7 stage runner |
| `immunity_complete` | ImmunityOrchestratorV7 (success) |
| `immunity_blocked` | ImmunityOrchestratorV7 (blocked) |
| `immunity_escalated` | ImmunityOrchestratorV7 (escalated) |
| `immunity_failed` | ImmunityOrchestratorV7 (unhandled error) |
| `immunity_fix_retry` | Fix retry loop |
| `immunity_rollback` | Checkpoint restore |
| `immunity_workspace_refresh` | Fresh workspace created |

### Verification

```python
from app.audit.service import verify_chain

result = verify_chain(db, review_run_id)
# result.valid: bool
# result.total_events: int
# result.errors: list[dict]  — event_id + error description for each broken link
```

The verifier:
1. Loads all events for the run in sequence order
2. Recomputes each `integrity_hash` from `prev_hash + event_type + canonical_payload`
3. Confirms it matches the stored hash
4. Confirms each `prev_hash` matches the hash of the preceding event

## Concurrency Model

### Process-Local Lock

```python
_audit_lock = threading.Lock()   # module-level, process-local
```

The `record_event()` function acquires `_audit_lock` before:
1. Looking up the current chain head (most recent integrity_hash)
2. Assigning the next sequence number
3. Computing and storing the new event

This serializes all audit writes within the process, ensuring a consistent hash chain regardless of how many concurrent agent threads are writing.

### Limitation

This lock is **process-local**. Multi-process deployments (e.g. multiple `uvicorn` workers) would require database-level serialization (e.g. a PostgreSQL advisory lock or a dedicated audit service). The current SQLite deployment is always single-process.

## Workspace Isolation (Security)

### Replay Workspaces

Each replay case runs in an **isolated temporary workspace**:

```
receipts_replay_ws_{uuid}/
    repo/
        <only the files declared in included_files>
```

- If `included_files` is set: **only those files** are copied — SAFE cases never see buggy files from the same source directory
- If `included_files` is None: the entire `repository_path` is copied
- Symlinks are **never followed** (`symlinks=False` in `shutil.copytree`)
- Workspace is always cleaned up after the case, regardless of outcome

### Strategy Workspaces

Each advanced strategy execution uses an `IsolatedWorkspace`:
- Creates a temp directory with prefix `receipts_strategy_ws_`
- Context manager guarantees cleanup even on exception
- Workspace path is always within the system temp directory

### Fix Workspaces

Each fix attempt in the immunity pipeline uses a fresh workspace:
- Created by `_create_temp_workspace(original_repo)` before each attempt
- Original repo is never modified
- Fresh workspace prevents cross-contamination between fix attempts

## Path Traversal Protection

### Replay Engine

```python
norm = os.path.normpath(rel_path)
if norm.startswith("..") or os.path.isabs(norm):
    logger.warning("skipping unsafe path: %s", rel_path)
    continue
```

### Repository Snapshot

The `RepositorySnapshot` rejects any relative path containing `..` and follows no symlinks.

## Secret Filtering

`RepositorySnapshot` redacts file content matching these patterns before passing it to strategies:

```python
_SECRET_PATTERNS = [
    "secret", "token", "password", "passwd", "key",
    "api_key", "auth", "credential", "private", "jwt", "bearer"
]
```

File names matching these patterns have their content replaced with `[REDACTED]`.

## Fail-Closed Invariants

| Situation | System Behavior |
|-----------|----------------|
| Agent execution error | ESCALATE — never SAFE |
| Agent timeout | ESCALATE — never SAFE |
| Missing evidence after budget | ESCALATE |
| Contradictory evidence | ESCALATE |
| Stage gate not satisfied | BLOCKED or ESCALATED — never advance |
| Audit write failure | Exception propagated — event not silently lost |
| Workspace cleanup failure | Logged as WARNING — pipeline continues |
| Path traversal attempt | Request silently rejected + logged |

## Demo Audit Result (actual, 2026-09-26)

```
valid=True  total_events=21  error_count=0
```

The audit chain for the demo review run was intact: 21 events verified, hash chain unbroken.
