# Bug-to-Immunity Pipeline — V7

## Overview

The **Bug-to-Immunity pipeline** converts a confirmed `BUG_DETECTED` finding into a pattern library entry. It runs 8 evidence-gated stages in sequence. Each stage has an **acceptance gate** — the stage must PASS before the pipeline advances.

The canonical implementation is **`ImmunityOrchestratorV7`** in `backend/app/immunity/orchestrator_v7.py`.

## Pipeline Stages

```
PENDING
  │
  ▼ run_pipeline() called
RUNNING
  │
  ▼
REPRODUCING ──── ReproduceStageV7
  │
  │ gate: bug must reproduce deterministically
  ▼
ROOT_CAUSE ───── RootCauseStageV7
  │
  │ gate: at least one VERIFIED hypothesis
  ▼
FIXING ─────────── FixStageV7  ←──────────────────────────────┐
  │                                                             │
  │ gate: patch applied cleanly                                │
  ▼                                                             │
VERIFYING ──────── VerifyStageV7                               │
  │                                                             │
  │ gate: patched code passes targeted tests                   │
  ▼                                                             │
REGRESSION_TESTING ── RegressionTestStageV7                    │
  │                                                             │
  │ gate: full test suite passes (no regressions)              │
  │       FAILED → retry FIXING (up to MAX_FIX_RETRIES=3) ───►┘
  ▼
SIBLING_HUNT ───── SiblingHuntStageV7
  │
  ▼
DOCUMENTING ────── DocumentationStageV7
  │
  ▼
PATTERN_EVALUATION ── PatternStage
  │
  ▼
IMMUNITY_COMPLETE
```

## Terminal States

| State | Meaning |
|-------|---------|
| `IMMUNITY_COMPLETE` | All 8 stages passed; pattern registered |
| `BLOCKED` | Required evidence/prerequisite missing; automation cannot continue |
| `ESCALATED` | Contradiction detected or automation unsafe; human required |
| `FAILED` | Fix rejected after all retries; pipeline stops |

## Stage Acceptance Gates

Each stage gate must be **explicitly PASSED** before the pipeline advances. Clean execution alone is not sufficient.

| Stage | Acceptance Gate |
|-------|----------------|
| Reproduce | Bug reproduces in isolated workspace — `exit_code != 0` |
| RootCause | At least one VERIFIED hypothesis (traceback + independent test confirmation) |
| Fix | Patch applied successfully; diff recorded |
| Verify | Patched workspace passes targeted tests |
| RegressionTest | Full test suite passes with no new failures |
| SiblingHunt | Completed (partial findings allowed; BLOCKED if escalation detected) |
| Documentation | Documentation stage completed (doc update or no-op) |
| Pattern | Pattern signature created and stored in library |

## Stage: ReproduceStageV7

- Runs pytest in an isolated workspace copy
- Gate: `exit_code != 0` (test must fail)
- Evidence: exact command, stdout, stderr, exit code, failing test names
- If tests all PASS → `BLOCKED` (bug is not reproducible)
- If execution error → `ESCALATED`

## Stage: RootCauseStageV7

- Extracts failing test names and traceback from reproduction evidence
- Creates hypotheses (one per traceback location, one per failing test)
- Verifies hypotheses that have concrete traceback evidence
- Calls `HypothesisTracker.verify(hypothesis_id, evidence, verified_by)`
- Gate: `resolution_status() == "VERIFIED"` (exactly one verified hypothesis, no conflicts)
- If multiple verified hypotheses → `ESCALATED` (conflicting root causes)
- If no verified hypothesis → `BLOCKED`
- Fault localization alone **cannot** verify a hypothesis

## Stage: FixStageV7

- Calls `AdaptiveFixPlanner.select_strategy()` with root-cause evidence
- Creates a fresh isolated workspace for each fix attempt
- Applies the selected fix strategy
- Gate: `FixResult.success == True` (diff must exist)
- If no applicable strategy → `BLOCKED`
- Each failed strategy is recorded; planner never retries same strategy
- After `MAX_FIX_RETRIES=3` attempts → `BLOCKED`

## Stage: VerifyStageV7

- Runs pytest in the patched workspace
- Gate: `exit_code == 0` for targeted tests
- FAILED → retry loop: increment `fix_attempt_count`; if `< MAX_FIX_RETRIES` → return to FIXING
- PatchCheckpoint rolls back files before retrying

## Stage: RegressionTestStageV7

- Runs the full test suite (not just targeted tests)
- Gate: `exit_code == 0` (no new failures)
- FAILED → retry loop (same as Verify): up to `MAX_FIX_RETRIES`
- BLOCKED if no tests exist

## Stage: SiblingHuntStageV7

- Uses AST/structural similarity to find code similar to the buggy location
- Records all findings as `POTENTIAL_MATCH` — never confirmed defects
- A sibling finding requires independent verification to become a confirmed bug
- BLOCKED advances pipeline with reason recorded (not a hard stop)

## Stage: DocumentationStageV7

- Checks whether the bug warrants a documentation note
- If documentation update needed, appends a note to relevant file
- Gate: completion (doc update or explicit no-op decision)

## Stage: PatternStage

- Creates a `PatternLibraryEntry` from the verified fix
- Pattern signature: derived from error type, affected file, and fix type
- Stores regression test reference (failing test name from reproduce stage)
- Gate: `PatternLibraryEntry` persisted

## HypothesisTracker

Tracks root-cause hypotheses through their lifecycle.

```python
# Phase 7 hypothesis lifecycle
OPEN → VERIFIED (with concrete evidence + independent confirmation)
     → REJECTED (with refuting evidence)
```

### Rules
- **Fault localization alone cannot verify** a hypothesis — it is a ranking signal only
- A hypothesis is VERIFIED only when the traceback explicitly confirms the location AND a test failure confirms the symptom
- Contradictory verified hypotheses → `ESCALATED`
- No verified hypotheses → `BLOCKED`

### API
```python
tracker = HypothesisTracker(pipeline_id)
h = tracker.add("description", source_strategy="fault_localization")
tracker.verify(h.hypothesis_id, evidence="traceback shows line 42", verified_by="traceback_analysis")
tracker.reject(h.hypothesis_id, refuting="could not reproduce at line 42")
status = tracker.resolution_status()  # "VERIFIED" | "CONFLICTED" | "BLOCKED" | "OPEN"
```

## PatchCheckpoint (Rollback)

Before any fix is applied, `FixStageV7` creates a `PatchCheckpoint` — a snapshot of the original file content.

If the patched code fails verification or regression tests, the checkpoint is used to restore the original file before retrying with a different fix strategy.

```python
# Each file that will be modified gets a checkpoint record
checkpoint = PatchCheckpoint(fix_candidate_id, pipeline_id)
checkpoint.save_file(file_path)  # stores original content
# ... apply fix ...
checkpoint.restore()  # restores original if fix failed
```

## Fix Retry Loop

```
FixStageV7 applied → VerifyStageV7 → FAILED?
    │
    ├─ fix_attempt_count < MAX_FIX_RETRIES (3)?
    │       └─ YES → rollback via checkpoint
    │                → increment attempt count
    │                → return to FixStageV7 (next strategy)
    │
    └─ NO → pipeline → BLOCKED
```

Each retry:
- Uses a **fresh workspace** (context.`_replace_workspace()` creates a new temp copy)
- Prevents contamination from a failed partial fix
- Records the failed strategy so `AdaptiveFixPlanner` never retries it

## Persistence

The following tables track V7 pipeline state:

| Table | Description |
|-------|-------------|
| `immunity_pipeline` | Pipeline record with status + current_stage |
| `immunity_stage` | Per-stage result (status, evidence JSON, timing) |
| `pipeline_state_transition` | Every state change with from/to/reason/timestamp |
| `immunity_hypothesis` | Hypothesis lifecycle (OPEN→VERIFIED/REJECTED) |
| `fix_candidate` | Fix attempt record (PENDING→APPLIED→VERIFIED/REJECTED/ROLLED_BACK) |
| `immunity_checkpoint` | File snapshots for rollback |
| `sibling_finding` | AST similarity candidates (always POTENTIAL_MATCH) |
| `pattern_library_entry` | Registered fix patterns |

## Demo Result (actual, 2026-09-26)

The demo ran with `demo/repository/` (accumulator reset bug):

```
stage=reproduce   status=PASSED   (0 ms)
stage=root_cause  status=ESCALATED (0 ms)
```

Pipeline status: **ESCALATED at Root Cause**

The Root Cause stage was escalated because the HypothesisTracker could not produce a `VERIFIED` resolution — the traceback analysis produced conflicting or insufficient hypothesis evidence for this demo run. This is correct fail-closed behavior: the system did not proceed to the Fix stage without a verified root cause.
