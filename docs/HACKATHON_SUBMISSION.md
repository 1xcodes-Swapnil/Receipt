# IBM Hackathon Submission — Receipts

## Project Name
**Receipts: Evidence-First AI Code Review & Bug Immunity**

## Team
IBM Bob Hackathon Submission

## Problem Statement

Current AI code review tools produce findings based on model predictions — but predictions without verifiable evidence cannot be trusted in production. Developers need a system that:

- Only flags bugs when it has **concrete, reproducible evidence**
- Traces every finding to the **exact test output or analysis that proved it**
- Can not only detect bugs but **autonomously repair and immunize** a codebase

## Solution

Receipts is an evidence-driven code review backend where **no finding is ever generated without a receipt** — a cryptographically-auditable record containing the exact command run, its real stdout/stderr, and the verdict derived from it.

### Core Invariant

```
NO EVIDENCE, NO FLAG.
```

Every verdict flows from real execution. Agents orchestrate. Strategies perform. Evidence decides.

## Architecture

```
PR / Repository
       │
       ▼
ReviewOrchestrator
       │
   ┌───┴──────────────────────────────────┐
   │ 4 Parallel Agents                    │
   │  TestRunner  CatchingTest            │
   │  DocCheck    HistoryCheck            │
   └───┬──────────────────────────────────┘
       │
       ▼
Adaptive Planner ← Evidence Ledger ← Claim/Gap Analysis
       │
   ┌───┴──────────────────────────────────┐
   │ 14 Strategies (Phase 5 + 6)          │
   │  ExistingTests   ChangeImpact        │
   │  StaticAST       Differential        │
   │  PropertyBased   Mutation            │
   │  FaultLocalize   Metamorphic         │
   │  Fuzzing         Counterexample      │
   │  SemanticSibling ...                 │
   └───┬──────────────────────────────────┘
       │
       ▼
Evidence Receipt → Verdict (SAFE / BUG_DETECTED / ESCALATE)
       │
       ▼ (on BUG_DETECTED)
ImmunityOrchestratorV7 (Phase 7)
       │
   8 Evidence-Gated Stages:
   Reproduce → RootCause → Fix → Verify →
   RegressionTest → SiblingHunt → Document → Pattern
       │
       ▼
IMMUNITY_COMPLETE  (or BLOCKED / ESCALATED)
       │
       ▼
Pattern Library Entry + Regression Test Registered
```

## IBM Bob Integration

This project was built using **IBM Bob** as the primary development agent. Bob was used to:

- Scaffold all 8 phases of the backend architecture
- Implement the 14 strategy portfolio
- Author the Phase 7 state machine and evidence-gated stages
- Write 217+ focused tests
- Produce all documentation

See [BOB_INTEGRATION.md](BOB_INTEGRATION.md) for details.

## Key Technical Differentiators

| Feature | Receipts | Typical AI Review |
|---------|----------|-------------------|
| Evidence before finding | ✅ Always | ❌ Often speculative |
| Cryptographic audit chain | ✅ SHA-256 hash chain | ❌ None |
| Bug-to-Immunity pipeline | ✅ 8-stage automated | ❌ None |
| Advanced testing strategies | ✅ 7 (Phase 6) | ❌ None |
| Replay benchmark | ✅ Ground-truth scored | ❌ None |
| Fail-closed on missing evidence | ✅ ESCALATE | ❌ Guess |

## Test Results (Baseline)

| Phase | Tests | Pass |
|-------|-------|------|
| Phase 2 (Core Agents) | 22 | ✅ |
| Phase 3 (Immunity) | 18 | ✅ |
| Phase 4 (Replay) | 24 | ✅ |
| Phase 5 (Hardening) | 43 | ✅ |
| Phase 6 (Adaptive) | 31 | ✅ |
| Phase 6 Advanced | 72 | ✅ |
| Phase 7 (V7 Immunity) | 71 | ✅ |
| **Total** | **217+** | **✅** |

## Quick Start

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt

# One-command demo
cd ..
python demo/run_demo.py

# Run all tests
cd backend
pytest tests/ -q
```

## Artifacts

- `demo/logs/latest/` — structured logs from last demo run
- `demo/run_demo.py` — one-command deterministic demo
- `backend/demo_cli.py` — interactive CLI
- `docs/DEMO_GUIDE.md` — step-by-step demo instructions
- `docs/BENCHMARK.md` — replay benchmark methodology

## Files Changed (Phase 8)

| File | Change |
|------|--------|
| `backend/app/immunity/__init__.py` | V7 canonical alias |
| `backend/app/immunity/orchestrator_v7.py` | Fresh workspace per retry |
| `backend/app/immunity/stages.py` | `_replace_workspace()` |
| `backend/app/repositories/provider.py` | Full GitHub provider |
| `backend/app/models.py` | ReplayResult + planner trace fields |
| `backend/app/schemas.py` | ReplayResultOut + trace fields |
| `backend/app/replay/engine.py` | Capture planner/strategy trace |
| `demo/run_demo.py` | One-command demo with structured logging |
| `docs/` | Hackathon documentation |
| `.env.example` | Environment configuration template |
