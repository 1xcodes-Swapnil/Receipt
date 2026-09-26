# Demo Guide — Receipts

## Prerequisites

```bash
# Python 3.11+
python --version

# Install backend dependencies
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
cd ..
```

## One-Command Demo

```bash
python demo/run_demo.py
```

This runs all 6 phases in order and writes structured logs to `demo/logs/latest/`.

Expected output:
```
════════════════════════════════════════════════════════════════
  RECEIPTS — Evidence-First Code Review  (Phase 8 Demo)
════════════════════════════════════════════════════════════════
  Start time : 2024-01-01T00:00:00Z
  Log dir    : .../demo/logs/latest

════════════════════════════════════════════════════════════════
  1 / 6  HEALTH CHECK
════════════════════════════════════════════════════════════════
  ✓  Database connected — 0 review run(s)
  ✓  Config loaded — version=0.8.0
  ✓  demo/repository found: ...
  ✓  demo/clean_repo found: ...
  ✓  demo/escalate_repo found: ...

  ...

════════════════════════════════════════════════════════════════
  DEMO SUMMARY
════════════════════════════════════════════════════════════════
  Verdict         : BUG_DETECTED
  Replay accuracy : 1.0
  Audit valid     : True
  ✓  Full demo completed successfully
```

## Interactive CLI Demo

```bash
cd backend

# Individual commands
.venv\Scripts\python.exe demo_cli.py health
.venv\Scripts\python.exe demo_cli.py review
.venv\Scripts\python.exe demo_cli.py bug
.venv\Scripts\python.exe demo_cli.py immunity
.venv\Scripts\python.exe demo_cli.py replay
.venv\Scripts\python.exe demo_cli.py audit

# All in sequence
.venv\Scripts\python.exe demo_cli.py all
```

## API Demo (with server running)

```bash
# Terminal 1: start server
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal 2: trigger a review
curl -X POST "http://localhost:8000/repos/demo/prs/1/review" \
     -H "Content-Type: application/json" \
     -d '{"pr_title": "Demo PR"}'

# Get the verdict
curl "http://localhost:8000/reviews/<run_id>"

# Stream live events (SSE)
curl "http://localhost:8000/reviews/<run_id>/events"
```

## Demo Repositories

| Repository | Ground Truth | Purpose |
|------------|-------------|---------|
| `demo/repository/` | BUG | Accumulator reset bug — tests fail |
| `demo/clean_repo/` | SAFE | All tests pass |
| `demo/escalate_repo/` | ESCALATE | No tests — insufficient evidence |

## Log Files (after `demo/run_demo.py`)

| File | Contents |
|------|----------|
| `demo/logs/latest/demo_run.log` | Full run log |
| `demo/logs/latest/review.log` | Review phase details |
| `demo/logs/latest/strategy_trace.log` | Planner decisions and strategy results |
| `demo/logs/latest/evidence.log` | Evidence items produced |
| `demo/logs/latest/verdict.log` | Verdict per phase |
| `demo/logs/latest/immunity.log` | Immunity pipeline stage progression |
| `demo/logs/latest/replay.log` | Replay case results and metrics |
| `demo/logs/latest/audit.log` | Audit chain verification |
| `demo/logs/latest/errors.log` | Errors only |
| `demo/logs/latest/demo_run.jsonl` | Machine-readable event log |

## What to Look For

### BUG_DETECTED Flow
1. `demo/repository/` contains an accumulator with a reset bug
2. TestRunner executes `pytest` → real test failures
3. Evidence receipt contains exact stdout with the failing test name
4. Verdict: `BUG_DETECTED` with confidence 1.0

### Immunity Pipeline
1. ReproduceStageV7 confirms the bug reproduces deterministically
2. RootCauseStageV7 performs coverage-guided fault localization
3. FixStageV7 applies a patch using the AdaptiveFixPlanner
4. VerifyStageV7 runs tests against the patched workspace
5. RegressionTestStageV7 ensures no regressions introduced
6. Each stage gate must PASS before advancing — no shortcuts

### Audit Chain
1. Every event is SHA-256 hashed and chained to the previous hash
2. `verify_chain()` recomputes all hashes and confirms integrity
3. Any tampering breaks the chain

### Replay Benchmark
- 3 BUG cases → must be detected (catch rate = 1.0)
- 3 SAFE cases → must not be flagged (false alarm rate = 0.0)

## Troubleshooting

**"No BUG_DETECTED run found"**  
The demo/repository tests all passed. Check that `demo/repository/` contains the buggy accumulator code.

**"repository_path missing or not a directory"**  
Run from the project root: `python demo/run_demo.py`

**Import errors**  
Ensure you installed dependencies: `pip install -r backend/requirements.txt`
