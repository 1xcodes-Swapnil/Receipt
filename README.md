# Receipts — Evidence-First AI Code Review & Bug Immunity

> **NO EVIDENCE, NO FLAG.** Every finding is backed by real, executable evidence — never AI speculation.

[![Tests](https://img.shields.io/badge/tests-217%20passing-brightgreen)](#test-results)
[![Phase](https://img.shields.io/badge/phase-8%20complete-blue)](#architecture)
[![Bob](https://img.shields.io/badge/built%20with-IBM%20Bob-0f62fe)](#ibm-bob)

---

## What is Receipts?

Receipts is a backend system that treats code review as an **evidence collection problem**, not a prediction problem. 

Every bug finding produces a **receipt** — a cryptographically-auditable record containing:
- The exact command executed
- Real stdout/stderr output
- The verdict derived from that output

When evidence is missing, the system returns `ESCALATE`. It never guesses.

---

## Quick Start

```bash
# Clone and set up
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt

# Run the one-command demo
cd ..
python demo/run_demo.py
```

The demo runs all 6 phases, produces structured logs in `demo/logs/latest/`, and prints a summary.

---

## Architecture

```
Pull Request / Repository
          │
          ▼
   ReviewOrchestrator
          │
    ┌─────┴──────────────────────────────┐
    │  4 Parallel Agents                 │
    │   TestRunner  CatchingTest         │
    │   DocCheck    HistoryCheck         │
    └─────┬──────────────────────────────┘
          │ Evidence Receipts
          ▼
   Adaptive Planner
   (Claim / Evidence Gap → Strategy Selection)
          │
    ┌─────┴──────────────────────────────┐
    │  14 Strategies                     │
    │   Phase 5: ExistingTests, ChangeImpact,   │
    │            StaticAST, Differential,        │
    │            Documentation, History,         │
    │            Targeted                        │
    │   Phase 6: PropertyBased, Mutation,        │
    │            FaultLocalization, Metamorphic, │
    │            Fuzzing, Counterexample,        │
    │            SemanticSibling                 │
    └─────┬──────────────────────────────┘
          │
          ▼
   Verdict: SAFE / BUG_DETECTED / ESCALATE
          │
          │ (on BUG_DETECTED)
          ▼
   ImmunityOrchestratorV7
   8 Evidence-Gated Stages:
   Reproduce → RootCause → Fix → Verify →
   RegressionTest → SiblingHunt → Document → Pattern
          │
          ▼
   IMMUNITY_COMPLETE + Pattern Library Entry
```

---

## Core Invariants

| Rule | Description |
|------|-------------|
| Evidence before findings | Agents must produce concrete, verifiable evidence before creating any finding |
| Never invent test results | Fabricated, simulated, or approximated outcomes are forbidden |
| Agent failure → ESCALATE | Missing evidence is never converted into SAFE |
| Agents are isolated | No shared mutable state between agents |
| Deterministic execution | Commands are reproducible given the same repository state |

---

## Features

### Phase 1–4: Foundation
- 4 parallel review agents (TestRunner, CatchingTest, DocCheck, HistoryCheck)
- SHA-256 hash chain audit trail
- Replay engine with ground-truth benchmark
- SSE live progress streaming

### Phase 5: Hardening
- Workspace isolation per replay case (no cross-contamination)
- Concurrent audit chain writes with threading.Lock
- Path traversal protection

### Phase 6: Adaptive Evidence Architecture
- **EvidenceLedger** — tracks claims, evidence, contradictions
- **StrategyPlanner** — selects strategies based on evidence gaps and budget
- **14 strategies** including 7 advanced testing techniques:
  - PropertyBasedTesting — bounded property generation with seed reproduction
  - MutationTesting — mutant creation, execution, kill classification, cleanup
  - FaultLocalization — Ochiai-based suspicious file/function ranking
  - MetamorphicTesting — input transformations and relation violation detection
  - Fuzzing — bounded deterministic input generation with failure capture
  - CounterexampleShrinking — minimize failing inputs while preserving failure
  - SemanticSiblingAnalysis — AST/structural similar-code detection

### Phase 7: V7 Bug-to-Immunity
- Explicit `PipelineStateMachine` with valid transition enforcement
- `HypothesisTracker` — OPEN → VERIFIED | REJECTED
- `AdaptiveFixPlanner` with 12-strategy fix portfolio
- `PatchCheckpoint` — file snapshots for safe rollback
- Every stage gate must PASS before advancing

### Phase 8: Integration & Demo
- V7 as canonical immunity orchestrator
- `GitHubRepositoryProvider` with `check_availability()` and clean failure
- Fresh workspace per fix retry (prevents contamination)
- Replay captures planner/strategy trace per case
- One-command demo runner with structured log files
- Hackathon documentation

---

## Test Results

| Phase | Tests | Status |
|-------|-------|--------|
| Phase 2 — Core Agents | 22 | ✅ |
| Phase 3 — Immunity | 18 | ✅ |
| Phase 4 — Replay | 24 | ✅ |
| Phase 5 — Hardening | 43 | ✅ |
| Phase 6 — Adaptive | 31 | ✅ |
| Phase 6 — Advanced Strategies | 72 | ✅ |
| Phase 7 — V7 Immunity | 71 | ✅ |
| **Total** | **217+** | **✅** |

```bash
cd backend
pytest tests/ -q
# 217 passed
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/repos/{repo}/prs/{number}/review` | Trigger a review |
| GET | `/reviews/{run_id}` | Get review run |
| GET | `/reviews/{run_id}/receipts` | Get evidence receipts |
| GET | `/reviews/{run_id}/events` | SSE live stream |
| POST | `/reviews/{run_id}/immunity` | Start immunity pipeline |
| GET | `/reviews/{run_id}/immunity` | Get immunity pipeline |
| POST | `/replay/run` | Run replay benchmark |
| GET | `/replay/runs` | List replay runs |
| GET | `/audit/events` | List audit events |
| GET | `/audit/verify/{run_id}` | Verify audit chain |

---

## Project Structure

```
backend/
  app/
    agents/           4 review agents
    api/              FastAPI routes
    audit/            SHA-256 audit chain
    evidence/         EvidenceLedger, Snapshot, Claims
    immunity/         V7 orchestrator + 8 stage handlers
    orchestration/    ReviewOrchestrator
    planner/          Adaptive strategy planner
    replay/           Replay engine + benchmark cases
    repositories/     LocalRepositoryProvider + GitHubRepositoryProvider
    strategies/       14 strategy implementations
  tests/              217+ focused tests

demo/
  repository/         Buggy demo repo (accumulator reset bug)
  clean_repo/         Clean demo repo (all tests pass)
  escalate_repo/      No-tests demo repo (ESCALATE)
  run_demo.py         One-command demo runner
  logs/latest/        Structured log files from last run

docs/
  HACKATHON_SUBMISSION.md
  BOB_INTEGRATION.md
  DEMO_GUIDE.md
  BENCHMARK.md
```

---

## IBM Bob

This project was built entirely with **IBM Bob** as the development agent across 8 phases.

See [docs/BOB_INTEGRATION.md](docs/BOB_INTEGRATION.md) for details on Bob's role and contribution.

---

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key settings:
- `DATABASE_URL` — SQLite (default) or PostgreSQL
- `GITHUB_TOKEN` — for `GitHubRepositoryProvider` (optional)
- `STRATEGY_MAX_ITERATIONS` — fuzzing/property budget
- `IMMUNITY_MAX_FIX_RETRIES` — max fix+verify cycles

---

## Demo

See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for the complete walkthrough.

---

## Core Invariant

**NO EVIDENCE, NO FLAG.**

See [AGENTS.md](AGENTS.md) for all project invariants enforced throughout the codebase.
