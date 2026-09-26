# Architecture — Receipts

## Layered Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        FastAPI HTTP Layer                       │
│          backend/app/api/routes.py                             │
└───────────────────────────┬────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────┐
│                   Orchestration Layer                           │
│                                                                 │
│   ReviewOrchestrator          ImmunityOrchestratorV7           │
│   (orchestration/             (immunity/orchestrator_v7.py)    │
│    orchestrator.py)                                            │
└───────┬───────────────────────────────┬────────────────────────┘
        │                               │
┌───────▼───────────┐   ┌──────────────▼───────────────────────┐
│   Agent Layer     │   │      Strategy / Planner Layer         │
│                   │   │                                        │
│  TestRunner       │   │  StrategyPlanner (planner/planner.py) │
│  CatchingTest     │   │  StrategyRegistry (14 strategies)     │
│  DocumentCheck    │   │  EvidenceLedger (evidence/claims.py)  │
│  HistoryCheck     │   │  RepositorySnapshot (evidence/        │
│                   │   │                      snapshot.py)     │
└───────┬───────────┘   └──────────────┬────────────────────────┘
        │                               │
┌───────▼───────────────────────────────▼────────────────────────┐
│                    Evidence / Receipt Layer                      │
│                                                                 │
│   Receipt (models.py)         EvidenceItem (models.py)         │
│   ReviewClaim (models.py)     EvidenceGap (models.py)          │
│   StrategyTraceEntry          AuditEvent (models.py)           │
└───────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────┐
│                     Persistence Layer                           │
│                                                                 │
│   SQLAlchemy ORM                SQLite (default)               │
│   database.py                   PostgreSQL-ready               │
└────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### FastAPI Routes (`backend/app/api/routes.py`)
- HTTP endpoints for review, immunity, replay, audit, patterns, evidence
- Request validation via Pydantic schemas
- Dependency injection for DB sessions

### ReviewOrchestrator (`backend/app/orchestration/orchestrator.py`)
- Creates PR + Repository records on demand
- Launches 4 agents in parallel via `ThreadPoolExecutor`
- Collects `AgentEvidence` from each agent
- Runs `StrategyPlanner` for adaptive evidence collection
- Applies verdict engine to produce final verdict
- Emits audit events and SSE events throughout

### StrategyPlanner (`backend/app/planner/planner.py`)
- Analyses repository snapshot to generate claims
- Selects strategies by cost and applicability
- Executes strategies against isolated workspaces
- Persists `EvidenceItem`, `StrategyTraceEntry`, `ReviewClaim`, `EvidenceGap`
- Evaluates sufficiency after each strategy execution
- Budget: max 5–9 strategies, max 120s total

### ImmunityOrchestratorV7 (`backend/app/immunity/orchestrator_v7.py`)
- Canonical Bug-to-Immunity pipeline (alias: `ImmunityOrchestrator`)
- Uses `PipelineStateMachine` for explicit state tracking
- Runs 8 evidence-gated stages: Reproduce → RootCause → Fix → Verify → Regression → SiblingHunt → Document → Pattern
- Fix retry loop: up to `MAX_FIX_RETRIES=3` cycles with fresh workspaces
- Persists all state transitions, hypotheses, fix candidates, checkpoints

### Agents (`backend/app/agents/`)
- **TestRunner**: runs pytest, parses output, returns `AgentEvidence`
- **CatchingTestAgent**: differential analysis (compares test behaviour)
- **DocumentationCheckAgent**: README/docstring presence
- **HistoryCheckAgent**: git history/blame analysis

### Strategies (`backend/app/strategies/`)
- 14 strategy implementations in `strategies/` directory
- All registered via `build_default_registry()`
- `CounterexampleShrinkingStrategy` only added via `build_shrinking_registry()`

### Replay Engine (`backend/app/replay/engine.py`)
- Runs known-outcome cases through live production pipeline
- Scores each result against ground truth
- Persists `ReplayResult` with planner/strategy trace (Phase 8)

### Audit Service (`backend/app/audit/service.py`)
- `record_event()`: serialized under `threading.Lock`, SHA-256 chain
- `verify_chain()`: recomputes and validates all hashes

### Repository Providers (`backend/app/repositories/provider.py`)
- `LocalRepositoryProvider`: local filesystem, git ops, workspace creation
- `GitHubRepositoryProvider`: GitHub REST API (requires `GITHUB_TOKEN`)

## Key Data Flows

### Review Flow
```
POST /review
  → ReviewOrchestrator.run_review()
  → [concurrent] 4 agents → AgentEvidence[]
  → StrategyPlanner.run()
      → Snapshot → Claims → Strategy loop → EvidenceItems
  → _calculate_verdict(evidences)
  → ReviewRun persisted
  → Audit events emitted
```

### Immunity Flow
```
POST /immunity
  → ImmunityOrchestratorV7.run_pipeline()
  → PipelineStateMachine(PENDING→RUNNING)
  → ReproduceStageV7
  → RootCauseStageV7 + HypothesisTracker
  → FixStageV7 + AdaptiveFixPlanner + PatchCheckpoint
  → VerifyStageV7 (or retry loop)
  → RegressionTestStageV7
  → SiblingHuntStageV7
  → DocumentationStageV7
  → PatternStage
  → PipelineState→IMMUNITY_COMPLETE|BLOCKED|ESCALATED
```

## Configuration

`Settings` (`backend/app/config.py`) is a Pydantic `BaseSettings` loaded from `.env`:

| Key | Default | Description |
|-----|---------|-------------|
| `app_name` | `"Receipts API"` | App name |
| `app_version` | `"0.1.0"` | Version string |
| `database_url` | `"sqlite:///./database/receipts.db"` | DB connection string |
| `db_echo` | `False` | SQLAlchemy echo mode |
| `demo_repo_path` | `"./demo/repository"` | Path to demo repository |

## Dependency Injection

FastAPI uses `get_db()` for database session injection. Tests override this with a file-based SQLite test database.

## Thread Safety

- Agent workers: each creates its own `SessionLocal()` — never shares sessions
- Audit chain: serialized under `_audit_lock` (threading.Lock)
- Replay engine: single-threaded case execution
- Strategy planner: single-threaded within a review (agents run in parallel, planner runs after)
