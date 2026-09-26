# Replay Engine and Benchmark — Receipts

## Overview

The **Replay Engine** provides a ground-truth scored benchmark for measuring the accuracy of the review pipeline. It runs a fixed set of known-outcome cases through the live production pipeline and scores each verdict against the known ground truth.

## Replay Cases

A `ReplayCase` defines a single benchmark scenario:

```python
ReplayCase(
    label="buggy_accumulator",
    description="...",
    repository_path="/path/to/repo",
    included_files='["buggy_stats.py", "test_buggy_stats.py"]',  # JSON
    ground_truth=GroundTruthEnum.BUG,
    ground_truth_source=ReplayAgentEnum.HUMAN,
    ground_truth_notes="Accumulator reset bug — subtotal = v instead of total += v",
    is_valid=True,
)
```

### Ground Truth Values

| Value | Meaning |
|-------|---------|
| `BUG` | Known bug — system should detect it |
| `SAFE` | Known clean code — system should say SAFE |
| `AMBIGUOUS` | Ground truth unclear — not used for scoring |

### Ground Truth Source

| Value | Meaning |
|-------|---------|
| `HUMAN` | Manually labeled by a human |
| `BOB_BUILTIN` | Labeled by IBM Bob |
| `RECEIPTS` | Labeled by a prior Receipts run |
| `NOT_AVAILABLE` | Source not recorded |

## Default Benchmark Cases

6 demo cases seeded by `backend/app/replay/demo_cases.py`:

| Case | Ground Truth | Repository | Expected Verdict |
|------|-------------|------------|-----------------|
| `buggy_stats_accumulator_reset` | BUG | `demo/repository` | BUG_DETECTED |
| `buggy_stats_variance_propagation` | BUG | `demo/repository` | BUG_DETECTED |
| `buggy_stats_full_suite` | BUG | `demo/repository` | BUG_DETECTED |
| `clean_string_utils` | SAFE | `demo/clean_repo` | SAFE |
| `clean_math_utils` | SAFE | `demo/clean_repo` | SAFE |
| `clean_repo_full` | SAFE | `demo/clean_repo` | SAFE |

## Scoring Rules

| Ground Truth | Verdict | Score |
|-------------|---------|-------|
| BUG | BUG_DETECTED | `caught_bug=True`, `correct=True` |
| BUG | SAFE | `missed_bug=True`, `correct=False` |
| BUG | ESCALATE | `escalated=True`, `correct=False` |
| SAFE | SAFE | `correct=True` |
| SAFE | BUG_DETECTED | `false_alarm=True`, `correct=False` |
| SAFE | ESCALATE | `escalated=True`, `correct=False` |
| AMBIGUOUS | any | not scored |

## Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| Catch rate | `caught_bugs / bug_cases` | 1.0 |
| False alarm rate | `false_alarms / safe_cases` | 0.0 |
| Accuracy | `correct / scored` | 1.0 |

## Workspace Isolation

Each replay case runs in an **isolated temporary workspace**:

```
/tmp/receipts_replay_ws_{uuid}/
    repo/
        <only the files in included_files>
```

- If `included_files` is set: only those files are copied — prevents SAFE cases seeing buggy files in the same source directory
- If `included_files` is None: entire `repository_path` is copied
- Symlinks are never followed
- Workspace cleaned up after the case regardless of outcome
- Original `repository_path` is never modified

## Phase 8: Planner/Strategy Trace Capture

Each `ReplayResult` now stores the planner trace for that run:

| Field | Description |
|-------|-------------|
| `planner_trace_json` | JSON array of strategy execution steps |
| `strategies_used` | Comma-separated unique strategy names |
| `strategy_count` | Total strategy steps executed |

### Trace Format

```json
[
  {"step": 0, "strategy": "change_impact", "reason": "Lowest cost strategy for claim 'code_correctness' (cost=1)", "result": "INSUFFICIENT", "stopping_reason": null},
  {"step": 1, "strategy": "existing_tests", "reason": "Lowest cost strategy for claim 'code_correctness' (cost=2)", "result": "FAIL", "stopping_reason": null},
  ...
]
```

This allows post-hoc analysis of:
- Which strategies were selected for each case
- Why each strategy was selected (selection reason)
- What result each strategy produced
- Where the planner stopped and why

## Demo Benchmark Results (actual, 2026-09-26)

```json
{
  "total_cases": 6,
  "valid_cases": 6,
  "executed": 6,
  "failed": 0,
  "bug_cases": 3,
  "safe_cases": 3,
  "caught_bugs": 3,
  "missed_bugs": 0,
  "false_alarms": 0,
  "escalated": 0,
  "correct": 6,
  "catch_rate": 1.0,
  "false_alarm_rate": 0.0,
  "accuracy": 1.0
}
```

**These are demo results, not a formal benchmark.** The 6 cases were designed specifically to demonstrate the system. A rigorous benchmark requires diverse, independently-labeled cases on real-world repositories.

### Strategy Trace (actual, for all 6 cases)

All 6 cases used the same 5-strategy sequence:
```
change_impact (cost=1) → INSUFFICIENT
existing_tests (cost=2) → FAIL (bug cases) or PASS (safe cases)
static_ast (cost=2) → INSUFFICIENT
differential_testing (cost=3) → INSUFFICIENT
documentation_analysis (cost=3) → FAIL or PASS
```

The planner selected Phase 5 strategies only (no Phase 6 advanced strategies were needed — existing tests provided sufficient evidence).

## API

```
POST /replay/run            — run benchmark (seed cases if needed)
GET  /replay/runs           — list all replay runs
GET  /replay/runs/{run_id}  — get run with metrics_json
GET  /replay/cases          — list all cases
GET  /replay/cases/{id}     — get a single case
POST /replay/validate       — validate all cases (marks invalid ones)
```

## Adding Custom Cases

```python
case = ReplayCase(
    label="my_bug",
    description="Description",
    repository_path="/absolute/path/to/repo",
    included_files='["relevant.py", "test_relevant.py"]',
    ground_truth=GroundTruthEnum.BUG,
    ground_truth_source=ReplayAgentEnum.HUMAN,
    ground_truth_notes="Bug introduced in commit abc123",
    is_valid=True,
)
db.add(case)
db.commit()
```

## Running the Benchmark

```bash
# Without server
cd backend
.venv\Scripts\python.exe demo_cli.py replay

# With structured logging
cd ..
python demo/run_demo.py   # note: do NOT run this again if already run

# API
curl -X POST http://localhost:8000/replay/run
```

## Limitations

- Demo cases use repositories specifically constructed to demonstrate the system
- True benchmark performance requires diverse, real-world labeled cases
- The catch rate of 1.0 reflects that demo cases were designed to be detectable
- All 6 demo cases ran the same 5-strategy sequence — more diverse cases may trigger different strategy paths
- AMBIGUOUS cases are never scored and should not be used to claim accuracy
