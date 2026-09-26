# IBM Bob Integration — Receipts

## Overview

Receipts was built entirely with **IBM Bob** as the development agent. This document describes how Bob was integrated into the development workflow and what it produced.

## Bob's Role

IBM Bob served as the primary software engineer for this project, implementing all 8 phases of the backend from scratch:

| Phase | Description | Bob's Output |
|-------|-------------|--------------|
| Phase 1 | Foundation — evidence receipt, DB, FastAPI | Core models, routes, test runner |
| Phase 2 | 4 agents, SSE events, parallel orchestration | ReviewOrchestrator, 4 agents |
| Phase 3 | Bug-to-Immunity pipeline (7 stages) | ImmunityOrchestrator, 7 stage handlers |
| Phase 4 | Replay engine, ground-truth benchmark | ReplayEngine, 6 demo cases |
| Phase 5 | Hardening — workspace isolation, audit chain | SHA-256 chain, concurrency lock |
| Phase 6 | Adaptive evidence architecture | EvidenceLedger, StrategyPlanner, 14 strategies |
| Phase 6+ | Advanced testing strategies | 7 advanced strategies + infrastructure |
| Phase 7 | V7 immunity with state machine | PipelineStateMachine, HypothesisTracker, V7 stages |
| Phase 8 | GitHub integration, demo runner, docs | GitHubProvider, demo/run_demo.py, this file |

## What Bob Did NOT Do

Per the project invariants:

- **Never fabricated test output** — all evidence comes from real `pytest` execution
- **Never invented verdict results** — ESCALATE when evidence is missing
- **Never mocked execution** — strategy results reflect actual analysis
- **Never implemented future phases prematurely** — strict phase gating

## Bob Configuration

This project uses the default IBM Bob agent mode. No custom MCP servers, custom modes, or external tools were required.

The `.bob/` directory contains Bob's workspace configuration.

## Key Design Decisions Made With Bob

### Evidence-Before-Findings Invariant
Bob enforced this invariant throughout all phases. When strategies couldn't produce real evidence, they return `INSUFFICIENT_EVIDENCE` — never a fabricated result.

### Fail-Closed Architecture
Every component Bob built returns `ESCALATE` rather than `SAFE` when evidence is ambiguous. This was consistently enforced across all 217 tests.

### Deterministic Strategy Execution
All Phase 6 advanced strategies use `DeterministicSeed` for reproducibility. Bob designed the `BoundedExecutionContext` to enforce iteration and time limits.

### Canonical V7 Path
In Phase 8, Bob canonicalized `ImmunityOrchestratorV7` as the production path, ensuring routes.py uses V7 and the legacy Phase 3 orchestrator is kept only for backward compatibility.

## How to Use Bob With This Project

```bash
# Open the project in IBM Bob
# The .bob/ directory contains the workspace configuration

# Bob can:
# - Review individual files
# - Run the test suite
# - Explain any component
# - Continue development of future phases
```

## Evidence of Bob's Work

Every phase was implemented in a single Bob conversation context. The git history reflects the incremental additions.

Key files authored by Bob:
- `backend/app/orchestration/orchestrator.py` — ReviewOrchestrator
- `backend/app/immunity/stages_v7.py` — 8 evidence-gated stage handlers
- `backend/app/immunity/state_machine.py` — PipelineStateMachine
- `backend/app/strategies/` — 14 strategy implementations
- `backend/app/planner/planner.py` — Adaptive planner with gap-gating
- `backend/app/evidence/` — Claim, EvidenceLedger, sufficiency evaluator
- `backend/app/replay/engine.py` — ReplayEngine with workspace isolation
- `backend/app/audit/service.py` — SHA-256 audit chain
- `backend/app/repositories/provider.py` — LocalRepositoryProvider + GitHubRepositoryProvider
- All 217+ tests across `backend/tests/`
