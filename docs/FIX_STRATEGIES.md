# Fix Strategies — AdaptiveFixPlanner

## Overview

The `AdaptiveFixPlanner` manages a portfolio of **12 deterministic fix strategies** used during the Bug-to-Immunity Fix stage. Strategies apply targeted, bounded code patches based on the root-cause evidence.

## Core Principle

A fix is accepted only when:
1. Verification tests pass in the patched workspace
2. The full regression suite passes with no new failures

A patch that applies cleanly but fails tests is **always rejected and rolled back**.

## Fix Strategy Contract

Every `FixStrategy` implements:

```python
class FixStrategy(abc.ABC):
    @property
    def name(self) -> str:  ...          # machine-readable name

    def can_apply(
        self,
        source_snippet: str,
        error_message: str,
        affected_file: str,
    ) -> bool: ...                       # True if strategy is applicable

    def apply(
        self, repo_path: str, affected_file: str
    ) -> FixResult: ...                  # apply the fix, return FixResult
```

### FixResult

```python
@dataclass
class FixResult:
    success: bool                        # True only if a real change was made
    description: str                     # strategy name
    diff: Optional[str]                  # patch lines (if success)
    error: Optional[str]                 # reason for failure
    regression_hint: Optional[dict]      # concrete assertion values for regression test
```

## Strategy Portfolio (12 Strategies)

### 1. `accumulator_reset`
- **Pattern**: loop body contains `accumulator = loop_var` instead of `accumulator += loop_var`
- **Detection**: variable with accumulator-like name (`total`, `sum`, `acc`, `subtotal`, `count`, `result`, `running`) assigned (not accumulated) inside a loop
- **Fix**: rewrites `X = v` → `X += v` for matching lines
- **Regression hint**: extracts function name, accumulator variable, loop variable, and line number
- **Status**: fully implemented, production-tested

### 2. `boundary_condition`
- **Pattern**: off-by-one errors, `IndexError`, range boundary mistakes
- **Detection**: `IndexError`, `off-by-one`, `list index`, `range error` in error message or source
- **Fix**: identified but **not auto-applied** — conservative approach requires manual review
- **Returns**: `success=False` with pattern-identified note
- **Status**: detection implemented; auto-fix deferred (conservative)

### 3. `null_handling`
- **Pattern**: `AttributeError`, `TypeError`, `NoneType` errors from missing None guards
- **Fix**: adds `if x is not None:` guards before attribute access
- **Status**: detection implemented; conservative

### 4. `exception_handling`
- **Pattern**: `UnhandledException`, bare `except:` clauses, missing exception types
- **Fix**: narrows bare `except:` to specific exception types
- **Status**: detection implemented

### 5. `state_initialization`
- **Pattern**: `NameError`, `UnboundLocalError` — variable used before assignment
- **Fix**: adds initialization before first use
- **Status**: detection implemented

### 6. `state_reset`
- **Pattern**: stateful object not reset between test calls / test pollution
- **Fix**: identifies `setUp`/`tearDown` or class-level state; adds reset call
- **Status**: detection implemented

### 7. `api_contract`
- **Pattern**: return type mismatch, missing required field, API contract violation
- **Fix**: adds missing return value / default
- **Status**: detection implemented; conservative

### 8. `validation`
- **Pattern**: missing input validation leading to downstream failures
- **Fix**: adds guard clause at function entry point
- **Status**: detection implemented

### 9. `type_handling`
- **Pattern**: `TypeError`, implicit type conversion failures, `int`/`str`/`float` mismatches
- **Fix**: adds explicit type conversion
- **Status**: detection implemented

### 10. `resource_cleanup`
- **Pattern**: `ResourceWarning`, file/connection not closed, context manager missing
- **Fix**: wraps in `with` statement or adds explicit close
- **Status**: detection implemented

### 11. `configuration`
- **Pattern**: hardcoded values that should be configurable, incorrect defaults
- **Fix**: extracts to configuration variable
- **Status**: detection implemented

### 12. `test_only_repair`
- **Pattern**: test isolation failure — test modifies shared state affecting other tests
- **Fix**: adds teardown or fixture reset
- **Status**: detection implemented

## AdaptiveFixPlanner Selection Algorithm

```python
def select_strategy(
    root_cause_evidence: dict,
    attempted_strategies: list[str],
    attempt_number: int,
) -> Optional[FixStrategy]:
```

Selection logic:
1. Extract `error_message`, `source_snippet`, `affected_file` from root-cause evidence
2. For each strategy (not yet attempted), call `can_apply()`
3. Return first applicable strategy
4. If none applicable → return `None` → Fix stage → `BLOCKED`

The planner **never retries** a strategy that previously returned `FixResult(success=False)`.

## Workspace Isolation Per Retry

Each fix retry uses a **fresh workspace**:

```python
# orchestrator_v7.py — fix retry loop
for attempt in range(1, MAX_FIX_RETRIES + 1):
    # Create fresh workspace — never reuse a contaminated workspace
    fresh_ws = _create_temp_workspace(original_repo)
    context._replace_workspace(fresh_ws)
    
    result = FixStageV7().run(pipeline_id, context, db)
    if result.passed():
        break
    # rollback via checkpoint before next attempt
    checkpoint.restore()
```

This ensures a failed partial fix from attempt N cannot contaminate attempt N+1.

## Checkpoint Rollback

Before any fix is applied, a `PatchCheckpoint` saves the original file content:

```python
checkpoint = PatchCheckpoint(fix_candidate_id=..., pipeline_id=...)
checkpoint.save_file(affected_file)   # store original content in DB
# ... apply fix ...
# if verification fails:
checkpoint.restore()                   # restore file from DB snapshot
```

The checkpoint is stored in the `immunity_checkpoint` table.

## Budget

`MAX_FIX_ATTEMPTS = 3` — after 3 failed fix+verify cycles, the pipeline transitions to `BLOCKED`.
