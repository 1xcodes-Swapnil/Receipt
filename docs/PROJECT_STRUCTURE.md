# Project Structure — Receipts

```
Bobproject/                          ← workspace root
│
├── .env.example                     ← environment configuration template
├── .gitignore
├── AGENTS.md                        ← project invariants (enforced)
├── README.md                        ← project overview and quick start
│
├── .bob/                            ← IBM Bob workspace configuration
│
├── backend/                         ← Python backend (FastAPI + SQLAlchemy)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  ← FastAPI app, CORS, startup
│   │   ├── config.py                ← Settings (Pydantic BaseSettings)
│   │   ├── database.py              ← SQLAlchemy engine, Base, SessionLocal
│   │   ├── models.py                ← All ORM models (30+ tables)
│   │   ├── schemas.py               ← Pydantic request/response schemas
│   │   ├── security.py              ← Path traversal protection, validate_repo_name
│   │   │
│   │   ├── api/
│   │   │   └── routes.py            ← All FastAPI route handlers
│   │   │
│   │   ├── agents/                  ← 4 review agents
│   │   │   ├── base.py              ← BaseAgent abstract class
│   │   │   ├── test_runner.py       ← pytest execution, receipt creation
│   │   │   ├── catching_test.py     ← differential test analysis
│   │   │   ├── documentation_check.py ← README/docstring checks
│   │   │   └── history_check.py     ← git blame / commit history
│   │   │
│   │   ├── audit/
│   │   │   └── service.py           ← SHA-256 audit chain, verify_chain()
│   │   │
│   │   ├── evidence/
│   │   │   ├── claims.py            ← Claim, Evidence, EvidenceLedger
│   │   │   └── snapshot.py          ← RepositorySnapshot (immutable, hash-verified)
│   │   │
│   │   ├── immunity/
│   │   │   ├── __init__.py          ← V7 canonical exports + legacy compat
│   │   │   ├── orchestrator_v7.py   ← ImmunityOrchestratorV7 (canonical)
│   │   │   ├── orchestrator.py      ← Phase 3 orchestrator (legacy compat only)
│   │   │   ├── stages.py            ← Phase 3 stage runners + ImmunityContext
│   │   │   ├── stages_v7.py         ← Phase 7 evidence-gated stage handlers (8 stages)
│   │   │   ├── state_machine.py     ← PipelineStateMachine, StageStateMachine
│   │   │   ├── hypothesis.py        ← HypothesisTracker, Hypothesis
│   │   │   ├── adaptive_fix.py      ← AdaptiveFixPlanner + 11 fix strategies
│   │   │   └── fix_strategies.py    ← FixStrategy base + AccumulatorResetStrategy
│   │   │
│   │   ├── orchestration/
│   │   │   └── orchestrator.py      ← ReviewOrchestrator (Phase 2)
│   │   │
│   │   ├── planner/
│   │   │   └── planner.py           ← StrategyPlanner (adaptive, gap-gating)
│   │   │
│   │   ├── replay/
│   │   │   ├── engine.py            ← ReplayEngine (workspace isolation + scoring)
│   │   │   └── demo_cases.py        ← Default 6 benchmark cases
│   │   │
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   └── provider.py          ← LocalRepositoryProvider + GitHubRepositoryProvider
│   │   │
│   │   ├── sandbox/
│   │   │   └── sandbox.py           ← Sandbox execution wrapper
│   │   │
│   │   ├── services/
│   │   │   ├── pattern_library.py   ← Pattern CRUD
│   │   │   └── risk_assessment.py   ← Deterministic risk scoring
│   │   │
│   │   ├── strategies/              ← 14 strategy implementations
│   │   │   ├── __init__.py          ← build_default_registry(), build_shrinking_registry()
│   │   │   ├── base.py              ← BaseStrategy, StrategyResult, StrategyRegistry
│   │   │   ├── infrastructure.py    ← DeterministicSeed, BoundedExecutionContext,
│   │   │   │                            IsolatedWorkspace, MutantCleanupRegistry
│   │   │   ├── change_impact.py
│   │   │   ├── existing_tests.py
│   │   │   ├── static_ast.py
│   │   │   ├── differential.py
│   │   │   ├── documentation.py
│   │   │   ├── history.py
│   │   │   ├── targeted.py
│   │   │   ├── property_based.py
│   │   │   ├── mutation_testing.py
│   │   │   ├── fault_localization.py
│   │   │   ├── metamorphic.py
│   │   │   ├── fuzzing.py
│   │   │   ├── counterexample_shrinking.py
│   │   │   └── semantic_sibling.py
│   │   │
│   │   └── events/
│   │       └── __init__.py          ← In-process SSE event bus
│   │
│   ├── tests/
│   │   ├── test_receipts.py
│   │   ├── test_phase2.py
│   │   ├── test_phase3.py
│   │   ├── test_phase4.py
│   │   ├── test_phase5.py
│   │   ├── test_phase6.py
│   │   ├── test_phase6_advanced.py
│   │   ├── test_phase7.py
│   │   ├── test_phase8.py
│   │   └── final_verify.py          ← Standalone sanity check
│   │
│   ├── demo_cli.py                  ← Interactive CLI (health/review/bug/immunity/replay/audit/all)
│   ├── pyproject.toml               ← pytest config
│   └── requirements.txt             ← Python dependencies
│
├── database/
│   └── receipts.db                  ← SQLite database (production)
│
├── demo/
│   ├── repository/                  ← Buggy demo repo (accumulator reset bug)
│   │   ├── buggy_stats.py           ← Bug: subtotal = v instead of total += v
│   │   ├── test_buggy_stats.py
│   │   └── calculator.py
│   │
│   ├── clean_repo/                  ← Clean demo repo (all tests pass)
│   │   └── ...
│   │
│   ├── escalate_repo/               ← Escalate demo repo (no tests)
│   │   └── ...
│   │
│   ├── run_demo.py                  ← One-command demo runner (Phase 8)
│   │
│   └── logs/
│       └── latest/                  ← Structured logs from last demo run
│           ├── demo_run.log         ← Full run log
│           ├── demo_run.jsonl       ← Machine-readable event log
│           ├── review.log
│           ├── strategy_trace.log
│           ├── evidence.log
│           ├── verdict.log
│           ├── immunity.log
│           ├── replay.log
│           ├── audit.log
│           └── errors.log
│
├── docs/                            ← Documentation
│   ├── PROJECT_OVERVIEW.md
│   ├── FLOW.md
│   ├── ARCHITECTURE.md
│   ├── DECISION_LOG.md
│   ├── EVIDENCE_AND_RECEIPTS.md
│   ├── STRATEGIES.md
│   ├── BUG_TO_IMMUNITY.md
│   ├── STATE_MACHINE.md
│   ├── FIX_STRATEGIES.md
│   ├── REPLAY_AND_BENCHMARK.md
│   ├── AUDIT_AND_SECURITY.md
│   ├── API_REFERENCE.md
│   ├── DATA_MODEL.md
│   ├── REPOSITORY_PROVIDERS.md
│   ├── TESTING.md
│   ├── DEMO_GUIDE.md
│   ├── BOB_INTEGRATION.md
│   ├── HACKATHON_SUBMISSION.md
│   ├── PROJECT_STRUCTURE.md         ← this file
│   ├── CURRENT_LIMITATIONS.md
│   └── ROADMAP.md
│
└── frontend/                        ← Phase 1 React frontend (not active in current backend)
    └── ...
```

## Key Entry Points

| Entry Point | Description |
|-------------|-------------|
| `backend/app/main.py` | FastAPI application factory |
| `backend/demo_cli.py` | Interactive CLI demo |
| `demo/run_demo.py` | One-command demo runner |
| `backend/tests/` | All test suites |

## Import Paths

From within `backend/` (after `sys.path.insert(0, "backend")`):

```python
from app.main import app
from app.models import ReviewRun, VerdictEnum
from app.orchestration.orchestrator import ReviewOrchestrator
from app.immunity import ImmunityOrchestrator      # → V7 (canonical alias)
from app.immunity import ImmunityOrchestratorV7    # → V7 (explicit)
from app.strategies import build_default_registry
from app.replay.engine import ReplayEngine
from app.audit.service import record_event, verify_chain
from app.repositories.provider import LocalRepositoryProvider, GitHubRepositoryProvider
```
