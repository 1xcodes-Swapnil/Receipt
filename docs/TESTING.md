# Testing Guide — Receipts

## Test Suites

All tests are in `backend/tests/`. Each suite targets a specific phase or component.

| Suite | File | Focus |
|-------|------|-------|
| Core receipts | `test_receipts.py` | Basic evidence, verdict, receipt creation |
| Phase 2 | `test_phase2.py` | 4 agents, parallel orchestration, SSE |
| Phase 3 | `test_phase3.py` | Immunity pipeline, stages, pattern library |
| Phase 4 | `test_phase4.py` | Replay engine, ground-truth benchmark |
| Phase 5 | `test_phase5.py` | Workspace isolation, audit chain, security |
| Phase 6 | `test_phase6.py` | Adaptive evidence: snapshot, planner, ledger |
| Phase 6 Advanced | `test_phase6_advanced.py` | All 7 advanced strategies |
| Phase 7 | `test_phase7.py` | V7 state machine, hypotheses, fix planner |
| Phase 8 | `test_phase8.py` | V7 canonicalization, GitHub provider, replay trace |

## Running Tests

### Full suite

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/ -q
```

### Single suite

```bash
.venv\Scripts\python.exe -m pytest tests/test_phase8.py -v
```

### With output

```bash
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

## Test Database

Each test suite uses an isolated **file-based SQLite** database to support multi-thread operations (agent workers run in `ThreadPoolExecutor`):

```python
_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_phase8_test.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"
engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
```

Test databases are created fresh and dropped after each module:

```python
@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
```

**Why file-based (not in-memory)?** Agent workers run in separate threads, each creating their own `SessionLocal()`. SQLite in-memory databases are not shared across connections, so a `:memory:` DB would appear empty to worker threads.

## What Each Suite Tests

### test_receipts.py
- Verdict calculation (SAFE / BUG_DETECTED / ESCALATE)
- Receipt persistence
- Basic review flow

### test_phase2.py
- All 4 agents run in parallel
- Each agent produces a receipt
- SSE event stream
- Verdict from multi-agent evidence

### test_phase3.py
- Phase 3 immunity stages in isolation (workspace copy)
- End-to-end immunity API
- Pattern library CRUD
- Audit events for immunity
- **Phase 8 update**: accepts V7 terminal states (`escalated`, `pattern` stage type)

### test_phase4.py
- Replay case seeding
- Replay engine execution
- Ground-truth scoring (caught/missed/false_alarm)
- Replay metrics

### test_phase5.py
- Replay workspace isolation (SAFE cases never contaminated)
- Concurrent audit writes (10 threads, chain integrity)
- Path traversal protection
- Bob evidence ref never auto-populated
- End-to-end verdicts via API
- Demo CLI commands exit 0
- Replay: 3 BUG + 3 SAFE, zero false alarms

### test_phase6.py
- RepositorySnapshot creation, hash, security
- Strategy `execute()` contracts
- EvidenceLedger tracking, contradictions, dependence
- Sufficiency evaluator and gap analyzer
- Planner selection algorithm, budget, trace
- Full-stack adaptive review integration (API + DB)

### test_phase6_advanced.py
- All 7 advanced strategies:
  - PropertyBasedTesting: bounded execution, seed reproduction, INSUFFICIENT when no properties
  - MutationTesting: mutant creation, kill/survived/invalid classification, cleanup
  - FaultLocalization: Ochiai coefficient, ranking, INSUFFICIENT when no failures
  - MetamorphicTesting: relations, violations, INSUFFICIENT when no relations
  - Fuzzing: bounded generation, failure capture, no failures ≠ proof
  - CounterexampleShrinking: minimization, reproduction
  - SemanticSiblingAnalysis: AST similarity, POTENTIAL_MATCH only
- Infrastructure: DeterministicSeed, BoundedExecutionContext, IsolatedWorkspace, MutantCleanupRegistry
- DB persistence: AdvancedStrategyExecution, AdvancedEvidenceItem, CounterexampleRecord, MutationSummary, FaultLocalizationResult
- Planner gap-gating for advanced strategies

### test_phase7.py
- Stage acceptance gates (PASSED only when gate satisfied)
- Terminal failure states (BLOCKED, ESCALATED, FAILED)
- Reproduction-before-fix invariant
- Hypothesis verification/rejection
- AdaptiveFixPlanner selection
- Patch rollback (checkpoint)
- Pre/post regression behavior
- Counterexample integration
- Sibling confirmation/rejection
- Pattern gating (no unverified patterns)
- Complete BUG→IMMUNITY flow
- State machine valid/invalid transitions
- Pipeline state machine progression

### test_phase8.py
- V7 canonicalization (`ImmunityOrchestrator` alias points to V7)
- `ImmunityContext._replace_workspace()` behavior
- `GitHubRepositoryProvider.check_availability()` — never raises, clean failure
- `LocalRepositoryProvider` — path validation, file ops, workspace
- `ProviderStatus` and `ProviderUnavailableError`
- `ReplayResult` Phase 8 trace fields (model + schema)
- Replay trace persists to DB
- Concurrent audit writes (unique sequences)
- Audit chain verify for fresh run
- `demo/run_demo.py` structure
- `.env.example` existence and keys
- `docs/` files existence and content
- README Phase 8 content

## Test Invariants

These invariants are enforced across all test suites:

1. **No fabricated test output** — all evidence comes from real pytest execution
2. **No hardcoded PASS** — tests assert on actual command output
3. **Fail-closed** — tests verify ESCALATE is returned on missing/insufficient evidence
4. **No mocking of execution** — strategies run real code
5. **Workspace isolation** — each test creates its own isolated workspace

## Test Counts (as of Phase 8)

The following counts are from actual pytest output. Do not infer counts from documentation:

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/ -q
# → see actual output for counts
```

## Demo CLI Tests

`test_phase5.py::TestDemoCLI` tests that `demo_cli.py` commands exit 0:

```bash
# Tested commands:
python demo_cli.py health
python demo_cli.py review
python demo_cli.py replay
python demo_cli.py audit
```

These run the full pipeline — they are integration tests, not unit tests.

## Configuration for Tests

Tests use `app.config.settings` with the default `demo_repo_path`. Some tests set it explicitly:

```python
from app.config import settings
settings.demo_repo_path = DEMO_REPO   # override for test
```

## Adding New Tests

Follow the pattern in `test_phase8.py`:
- Use file-based SQLite with per-module setup/teardown
- Never use `StaticPool` or in-memory SQLite
- Create test DB in `backend/tests/` with prefix `_phase{N}_test.db`
- Follow the `TestClassName::test_method_name` naming convention
- Assert on real behavior — never mock execution results
