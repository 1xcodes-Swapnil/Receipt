
<img width="1376" height="768" alt="Cover Image" src="https://github.com/user-attachments/assets/52dd5209-c890-4cd6-b36d-454c4161052a" />


# Receipts — Evidence-First AI Code Review & Bug Immunity
> **NO EVIDENCE, NO FLAG.** Every finding is backed by real, executable evidence — never AI speculation.
Built with **IBM Bob**.

---
## What is Receipts?
Receipts is a backend system that treats code review as an **evidence collection problem**, not a prediction problem.

Every bug finding produces a **receipt** — a cryptographically-auditable record containing:
- The exact command executed (e.g. `pytest test_buggy_stats.py -v`)
- Real stdout/stderr output
- The verdict derived from that output

When evidence is missing, the system returns `ESCALATE`. It never guesses `SAFE`.

---

## Quick Start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### Run all tests

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/ -q
```

### Run the demo (first time only)

```bash
# From project root
python demo/run_demo.py
```

Structured logs are written to `demo/logs/latest/`.

### Start the API server

```bash
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

---

## Architecture

```
Pull Request / Repository
          │
          ▼
   ReviewOrchestrator
   (4 parallel agents: TestRunner, CatchingTest, DocCheck, HistoryCheck)
          │
          ▼
   Adaptive Planner
   (Claim / Evidence Gap → Strategy Selection → Execute → Evidence)
   14 strategies: 7 Phase 5 (cost 1–4) + 7 Phase 6 (cost 4–7)
          │
          ▼
   Verdict: SAFE / BUG_DETECTED / ESCALATE
   (with cryptographic audit receipt)
          │
          │ on BUG_DETECTED
          ▼
   ImmunityOrchestratorV7
   8 evidence-gated stages:
   Reproduce → RootCause → Fix → Verify →
   RegressionTest → SiblingHunt → Document → Pattern
          │
          ▼
   IMMUNITY_COMPLETE (or BLOCKED / ESCALATED)
```

---

## Core Invariants

- **NO EVIDENCE, NO FLAG** — verdicts come from real execution, not prediction
- **Agent failure → ESCALATE** — missing evidence is never converted to SAFE
- **Stage gate must PASS** — pipeline never advances without gate satisfaction
- **Hypothesis requires independent verification** — fault localization alone is not root cause proof
- **Fix requires verification** — a patch that applies but fails tests is always rejected

See [AGENTS.md](AGENTS.md) for the full invariant list.

---

## Phase 6 Advanced Strategies

When the base strategy set leaves an evidence gap, the planner may select:

| Strategy | Cost | What it does |
|---------|------|--------------|
| `semantic_sibling_analysis` | 4 | AST-based similar-code detection |
| `fault_localization` | 5 | Ochiai-coefficient suspicious ranking |
| `property_based_testing` | 6 | Bounded property generation |
| `metamorphic_testing` | 6 | Input transformation + relation check |
| `fuzzing` | 6 | Deterministic bounded input generation |
| `mutation_testing` | 7 | Mutant creation + kill classification |
| `counterexample_shrinking` | — | Minimize failing inputs (requires failing input) |

---

## Demo Results (actual, 2026-09-26)

| Metric | Value |
|--------|-------|
| Review verdict | **BUG_DETECTED** (confidence 1.0) |
| Strategies used | 5 (change_impact, existing_tests, static_ast, differential_testing, documentation_analysis) |
| Fail receipts | 2 |
| Immunity status | **ESCALATED at Root Cause** (correct fail-closed behavior) |
| Replay: 6 cases | catch_rate=1.0, false_alarm_rate=0.0, accuracy=1.0 |
| Audit chain | valid, 21 events |

These are demo results on purpose-built repositories, not a real-world benchmark.

---

## Test Results (Phase 8)

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/ -q
# 371 passing (as of Phase 8 commit 4755f48)
```

| Suite | Focus |
|-------|-------|
| `test_receipts.py` | Basic evidence, verdict |
| `test_phase2.py` | 4 agents, SSE |
| `test_phase3.py` | Immunity pipeline, pattern library |
| `test_phase4.py` | Replay engine |
| `test_phase5.py` | Workspace isolation, audit chain, security |
| `test_phase6.py` | Adaptive evidence, planner |
| `test_phase6_advanced.py` | All 7 advanced strategies |
| `test_phase7.py` | V7 state machine, hypotheses, fix planner |
| `test_phase8.py` | V7 canonicalization, GitHub provider, replay trace |

---

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/repos/{repo}/prs/{n}/review` | Trigger review |
| GET | `/reviews/{run_id}` | Get review run |
| GET | `/reviews/{run_id}/receipts` | Get evidence receipts |
| GET | `/reviews/{run_id}/stream` | SSE live progress |
| POST | `/reviews/{run_id}/immunity` | Start immunity pipeline |
| GET | `/immunity/{pipeline_id}` | Get pipeline detail |
| POST | `/replay/run` | Run replay benchmark |
| GET | `/audit/verify/{run_id}` | Verify audit chain |

Full reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

---

## Configuration

```bash
cp .env.example .env
# edit .env
```

| Key | Default | Description |
|-----|---------|-------------|
| `DATABASE_URL` | SQLite | Database connection |
| `GITHUB_TOKEN` | — | For GitHubRepositoryProvider (optional) |
| `STRATEGY_MAX_ITERATIONS` | 50 | Fuzzing/property budget |
| `IMMUNITY_MAX_FIX_RETRIES` | 3 | Fix+verify retry cycles |

---

## Documentation

| File | Contents |
|------|----------|
| [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | What the system does and doesn't do |
| [FLOW.md](docs/FLOW.md) | End-to-end review flow diagrams |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component architecture |
| [EVIDENCE_AND_RECEIPTS.md](docs/EVIDENCE_AND_RECEIPTS.md) | Receipt, Claim, Evidence structures |
| [STRATEGIES.md](docs/STRATEGIES.md) | All 14 strategies with contracts |
| [BUG_TO_IMMUNITY.md](docs/BUG_TO_IMMUNITY.md) | V7 pipeline with stage gates |
| [STATE_MACHINE.md](docs/STATE_MACHINE.md) | Pipeline state machine |
| [FIX_STRATEGIES.md](docs/FIX_STRATEGIES.md) | 12 fix strategies |
| [REPLAY_AND_BENCHMARK.md](docs/REPLAY_AND_BENCHMARK.md) | Replay engine and demo results |
| [AUDIT_AND_SECURITY.md](docs/AUDIT_AND_SECURITY.md) | SHA-256 chain, workspace isolation |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Full API reference |
| [DATA_MODEL.md](docs/DATA_MODEL.md) | All DB tables and columns |
| [REPOSITORY_PROVIDERS.md](docs/REPOSITORY_PROVIDERS.md) | Local + GitHub providers |
| [TESTING.md](docs/TESTING.md) | Test suites and patterns |
| [DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | Step-by-step demo |
| [CURRENT_LIMITATIONS.md](docs/CURRENT_LIMITATIONS.md) | Known limitations (honest) |
| [DECISION_LOG.md](docs/DECISION_LOG.md) | Architecture decisions |
| [ROADMAP.md](docs/ROADMAP.md) | Future phases (deferred) |
| [BOB_INTEGRATION.md](docs/BOB_INTEGRATION.md) | IBM Bob's role |
| [HACKATHON_SUBMISSION.md](docs/HACKATHON_SUBMISSION.md) | Hackathon submission |
| [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | Directory structure |

---

## IBM Bob

This project was built entirely using **IBM Bob** as the development agent across 8 phases.

See [docs/BOB_INTEGRATION.md](docs/BOB_INTEGRATION.md) for details.

---

**NO EVIDENCE, NO FLAG.**  
See [AGENTS.md](AGENTS.md) for all project invariants.
