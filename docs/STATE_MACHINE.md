# State Machine — Phase 7

## Overview

Phase 7 introduced an **explicit state machine** for the Bug-to-Immunity pipeline. Every state transition is:
- Validated (invalid transitions are rejected with `ValueError`)
- Persisted to `pipeline_state_transition` table with timestamp and reason
- Audited via the audit chain

The state machine prevents:
- Skipping stages
- Advancing from a gate failure without a retry decision
- Silent state changes

## Stage State Machine

Each immunity stage has its own `StageStateMachine`.

### Stage States

| State | Meaning |
|-------|---------|
| `PENDING` | Not yet started |
| `RUNNING` | Currently executing |
| `PASSED` | Acceptance gate satisfied — terminal |
| `FAILED` | Acceptance gate not satisfied |
| `BLOCKED` | Prerequisite missing — terminal |
| `ESCALATED` | Automation unsafe — terminal |

### Valid Stage Transitions

```
PENDING → RUNNING
PENDING → BLOCKED          (prerequisite check failed before start)
RUNNING → PASSED
RUNNING → FAILED
RUNNING → BLOCKED
RUNNING → ESCALATED
FAILED  → RUNNING          (retry)
FAILED  → BLOCKED          (retry budget exhausted)
```

All other transitions raise `ValueError`.

## Pipeline State Machine

The `PipelineStateMachine` tracks overall pipeline progress.

### Pipeline States (13)

| State | Type | Description |
|-------|------|-------------|
| `PENDING` | initial | Pipeline created, not started |
| `RUNNING` | active | Pipeline executing |
| `REPRODUCING` | active | In ReproduceStage |
| `ROOT_CAUSE` | active | In RootCauseStage |
| `FIXING` | active | In FixStage |
| `VERIFYING` | active | In VerifyStage |
| `REGRESSION_TESTING` | active | In RegressionTestStage |
| `SIBLING_HUNT` | active | In SiblingHuntStage |
| `DOCUMENTING` | active | In DocumentationStage |
| `PATTERN_EVALUATION` | active | In PatternStage |
| `IMMUNITY_COMPLETE` | terminal | All gates passed; pattern registered |
| `BLOCKED` | terminal | Prerequisite/gate failure; cannot continue |
| `ESCALATED` | terminal | Unsafe to continue; human required |
| `FAILED` | terminal | Unrecoverable failure |

### Valid Pipeline Transitions

```
PENDING → RUNNING
RUNNING → REPRODUCING
REPRODUCING → ROOT_CAUSE | BLOCKED | ESCALATED
ROOT_CAUSE → FIXING | BLOCKED | ESCALATED
FIXING → VERIFYING | BLOCKED
VERIFYING → REGRESSION_TESTING | FIXING        (retry)
REGRESSION_TESTING → SIBLING_HUNT | FIXING     (retry)
SIBLING_HUNT → DOCUMENTING | ESCALATED
DOCUMENTING → PATTERN_EVALUATION
PATTERN_EVALUATION → IMMUNITY_COMPLETE | BLOCKED
Any active → FAILED                            (unhandled exception)
```

Any unlisted transition raises `ValueError` and the pipeline is set to `FAILED`.

## State Transition Persistence

Every transition is recorded in `pipeline_state_transition`:

```python
PipelineStateTransition(
    pipeline_id=...,
    stage_name=...,         # e.g. "reproduce", "fix"
    from_state=...,         # e.g. "RUNNING"
    to_state=...,           # e.g. "PASSED"
    timestamp=datetime.utcnow(),
    reason=...,             # human-readable reason
    evidence_ref=...,       # optional reference to evidence
    execution_id=...,       # optional execution context
)
```

Transitions are **never deleted or modified**. They form a complete audit history of the pipeline.

## Usage

```python
# Create state machine
sm = PipelineStateMachine(pipeline_id="abc-123", db=db)

# Advance state
sm.transition(
    stage_name="reproduce",
    from_state=PipelineState.REPRODUCING,
    to_state=PipelineState.ROOT_CAUSE,
    reason="Reproduction confirmed: exit_code=1, 3 failing tests",
)

# Invalid transition raises ValueError immediately
sm.transition(
    stage_name="reproduce",
    from_state=PipelineState.PENDING,   # invalid: can't go PENDING→ROOT_CAUSE
    to_state=PipelineState.ROOT_CAUSE,
    reason="skip",
)
# → ValueError: Invalid transition PENDING→ROOT_CAUSE for stage reproduce
```

## StageStateMachine

```python
# Per-stage machine
stage_sm = StageStateMachine(stage_name="fix")

stage_sm.transition(StageState.PENDING, StageState.RUNNING, reason="starting")
stage_sm.transition(StageState.RUNNING, StageState.FAILED, reason="no applicable strategy")
stage_sm.transition(StageState.FAILED, StageState.RUNNING, reason="retry attempt 2")
stage_sm.transition(StageState.RUNNING, StageState.BLOCKED, reason="max retries reached")
```

## Relationship to ImmunityStatusEnum

The `ImmunityStatusEnum` in `models.py` maps to stage/pipeline terminal states for DB persistence:

| Enum Value | State Machine Equivalent |
|------------|--------------------------|
| `pending` | PENDING |
| `running` | RUNNING |
| `passed` | PASSED / IMMUNITY_COMPLETE |
| `failed` | FAILED |
| `blocked` | BLOCKED |
| `escalated` | ESCALATED |
