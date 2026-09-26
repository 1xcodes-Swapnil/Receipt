# Benchmark Methodology — Receipts Replay Engine

## Overview

The Receipts Replay Engine provides a ground-truth scored benchmark for measuring the accuracy of the review pipeline. It runs a fixed set of known-outcome cases through the live production pipeline and scores each verdict.

## Benchmark Cases

The default benchmark uses 6 cases seeded by `demo/replay/demo_cases.py`:

| Case | Ground Truth | Repository | Expected Verdict |
|------|-------------|------------|-----------------|
| buggy_accumulator | BUG | demo/repository | BUG_DETECTED |
| calc_divide_by_zero | BUG | demo/repository | BUG_DETECTED |
| stats_reset_fault | BUG | demo/repository | BUG_DETECTED |
| clean_accumulator | SAFE | demo/clean_repo | SAFE |
| clean_calculator | SAFE | demo/clean_repo | SAFE |
| escalate_no_tests | AMBIGUOUS | demo/escalate_repo | ESCALATE |

## Scoring Rules

| Ground Truth | Verdict | Score |
|-------------|---------|-------|
| BUG | BUG_DETECTED | ✅ caught_bug |
| BUG | SAFE | ❌ missed_bug |
| BUG | ESCALATE | ⚠ escalated |
| SAFE | SAFE | ✅ correct |
| SAFE | BUG_DETECTED | ❌ false_alarm |
| SAFE | ESCALATE | ⚠ escalated |
| AMBIGUOUS | any | not scored |

## Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| Catch rate | caught_bugs / bug_cases | ≥ 1.0 |
| False alarm rate | false_alarms / safe_cases | = 0.0 |
| Accuracy | correct / scored | ≥ 1.0 |

## Workspace Isolation

Each replay case runs in an **isolated temporary workspace** containing only the files declared in `included_files`. This prevents a SAFE case from seeing buggy files that may share the same source directory.

The isolation rules are:
- If `included_files` is set → only those files are copied
- If `included_files` is None → the entire `repository_path` is copied
- Temp workspaces are removed after each case regardless of outcome
- Original `repository_path` is never mutated

## Phase 8: Planner/Strategy Trace Capture

Each `ReplayResult` now stores:

| Field | Description |
|-------|-------------|
| `planner_trace_json` | JSON list of strategy execution steps |
| `strategies_used` | Comma-separated unique strategy names |
| `strategy_count` | Total strategy steps executed |

This allows benchmark analysis to answer:
- Which strategies were most valuable for bug detection?
- Did the planner select appropriate strategies given the evidence gap?
- Were expensive strategies (Mutation, Fuzzing) called when simpler ones would suffice?

## Running the Benchmark

```bash
# Quick benchmark (no server required)
cd backend
.venv\Scripts\python.exe demo_cli.py replay

# Full benchmark with structured output
cd ..
python demo/run_demo.py
# → results in demo/logs/latest/replay.log
```

## API

```bash
# Seed and run all cases
POST /replay/run
{}

# List results
GET /replay/runs

# Get a specific run with metrics
GET /replay/runs/{run_id}

# Get results for a run
GET /replay/runs/{run_id}/results
```

## Adding Custom Cases

To add a case to the benchmark, create a `ReplayCase` row:

```python
from app.models import ReplayCase, GroundTruthEnum, ReplayAgentEnum

case = ReplayCase(
    label="my_test_case",
    description="Description of what this case tests",
    repository_path="/absolute/path/to/repo",
    included_files='["relevant_file.py", "test_relevant.py"]',
    ground_truth=GroundTruthEnum.BUG,
    ground_truth_source=ReplayAgentEnum.HUMAN,
    ground_truth_notes="Known bug introduced in commit abc123",
    is_valid=True,
)
db.add(case)
db.commit()
```

## Limitations

- Benchmark accuracy depends on the quality of ground-truth labels
- AMBIGUOUS cases are not scored — they are informational only
- The benchmark measures verdict accuracy, not evidence quality
- A perfect catch rate with false alarms is not a good result
- Replay cases must use stable, version-controlled repositories for reproducibility
- Each benchmark run creates new DB rows — old runs are not overwritten
