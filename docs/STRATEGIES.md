# Strategy Reference — Receipts

## Overview

The Receipts adaptive planner selects from a **portfolio of 14 strategies** organised into two phases. Strategies are executed in cost order, cheapest first, and only when applicable.

All strategies:
- Declare an **EvidenceContract**: what evidence they will produce
- Check **applicability and prerequisites** before executing
- Enforce **bounded execution**: iteration caps and time limits
- Produce **structured results**: PASS / FAIL / INSUFFICIENT / ERROR
- **Fail closed**: unsupported or errored strategies return ERROR / INSUFFICIENT, never fabricate

## Phase 5 Strategies (Base Portfolio)

| # | Strategy | Cost | Claim Types | Description |
|---|---------|------|------------|-------------|
| 1 | `change_impact` | 1 | code_correctness | Analyses which files/functions changed |
| 2 | `existing_tests` | 2 | code_correctness, test_coverage | Runs existing pytest suite |
| 3 | `static_ast` | 2 | code_correctness | AST-based static analysis |
| 4 | `differential_testing` | 3 | code_correctness | Compares test behaviour before/after |
| 5 | `documentation_analysis` | 3 | documentation | README/docstring presence check |
| 6 | `history_analysis` | 3 | code_correctness | git blame / commit history |
| 7 | `targeted_testing` | 4 | code_correctness, test_coverage | Runs tests targeting changed files only |

`documentation_analysis` and `history_analysis` are **advisory**: their FAIL result is informational and never triggers `BUG_DETECTED` on its own.

## Phase 6 Advanced Strategies

Advanced strategies are only selected when a claim gap remains after Phase 5 strategies and the extended budget permits.

| # | Strategy | Cost | Claim Types | Description |
|---|---------|------|------------|-------------|
| 8 | `semantic_sibling_analysis` | 4 | code_correctness | AST/structural similarity search |
| 9 | `fault_localization` | 5 | code_correctness | Ochiai-coefficient suspicious ranking |
| 10 | `property_based_testing` | 6 | code_correctness, test_coverage | Bounded property generation |
| 11 | `metamorphic_testing` | 6 | code_correctness | Input transformation + relation check |
| 12 | `fuzzing` | 6 | code_correctness | Deterministic bounded input generation |
| 13 | `mutation_testing` | 7 | test_coverage | Mutant creation + kill classification |
| 14 | `counterexample_shrinking` | — | code_correctness | Minimize failing inputs |

`counterexample_shrinking` is not in the default registry — it is only added via `build_shrinking_registry()` when a failing input is already available from another strategy.

## Strategy Descriptions

### PropertyBasedTesting
- Generates bounded test cases from declared property signatures found in test files
- Uses `DeterministicSeed` for reproducibility (seed = hash of snapshot + strategy name)
- Enforces `BoundedExecutionContext`: max 50 iterations, 30s wall-clock limit
- Records failing inputs/properties as evidence
- **INSUFFICIENT_EVIDENCE** when no applicable properties are found
- **Contract**: PASS = all properties satisfied within budget; FAIL = reproducible property violation found

### MutationTesting
- Creates bounded mutants in changed/targeted code files
- Mutations: arithmetic operators (`+→-`, `-→+`), comparison operators (`<→<=`), boolean operators
- Runs applicable test suite against each mutant
- Classifies: KILLED (test caught it) / SURVIVED (test missed it) / INVALID (mutant breaks syntax)
- Records mutation effectiveness score (kill rate)
- Cleans all mutant files on completion (always, even on error)
- Surviving mutants become evidence of **test weakness**, not proof of a bug
- **Contract**: PASS = kill rate ≥ threshold; FAIL = surviving mutants indicate weak tests

### FaultLocalization
- Uses test failure information and coverage data to rank suspicious files/functions/lines
- Implements **Ochiai coefficient**: `ef / sqrt((ef+nf) * (ef+np))`
  - `ef` = failed tests covering element, `nf` = failed tests not covering it
  - `ep` = passing tests covering element, `np` = passing tests not covering it
- Records inputs, coverage basis, full ranking, and top score
- **INSUFFICIENT_EVIDENCE** when no test failures or coverage data is available
- Localization is evidence/hypothesis, **not proof of root cause**
- **Contract**: PASS = ranking produced; result includes ranked locations

### MetamorphicTesting
- Defines input transformations and expected metamorphic relations
- Executes original input + transformed input; compares outputs
- Records reproducible relation violations as evidence
- **INSUFFICIENT_EVIDENCE** when no applicable relations are found for the code
- **Contract**: PASS = all applicable relations hold; FAIL = relation violation detected and reproducible

### Fuzzing
- Generates bounded, deterministic/reproducible inputs using seeded random
- Enforces iteration limit (default 50) and time limit (default 30s)
- Captures crashes, exceptions, invariant violations, unexpected behaviour
- Preserves triggering inputs in evidence record
- Cleans artifacts on completion
- No failure within budget **does not prove correctness**
- **Contract**: PASS = no failures within budget; FAIL = failure captured with triggering input

### CounterexampleShrinking
- **Requires** a verified failing generated input (from fuzzing, property testing, or similar)
- Minimizes the input while preserving the same failure/property violation
- Tries removing elements, simplifying values, reducing complexity
- Records both original and minimized counterexample
- The minimized case must independently reproduce the original failure
- **Contract**: minimized input must reproduce failure when rerun in isolation

### SemanticSiblingAnalysis
- Finds structurally/semantically similar code using AST analysis
- Excludes the original location
- Ranks candidates by structural similarity score
- Records matching evidence (similarity score, structural reasons)
- **Never marks a sibling as a confirmed defect** — always `POTENTIAL_MATCH`
- **Contract**: PASS = candidates reproducibly identified; result includes ranked candidates

## Strategy Selection

The planner selects strategies in this order:
1. Sort applicable strategies by `(cost, expected_value)` — cheapest first
2. Execute the cheapest applicable strategy
3. Evaluate evidence gap
4. If gap resolved → stop (early termination)
5. If gap remains → try next
6. Stop when budget exhausted

### Budget

| Budget Mode | Max Strategies | Max Time |
|------------|----------------|----------|
| Base (Phase 5 only) | 5 | 120s |
| Extended (Phase 5+6) | 9 | 120s |

Phase 6 strategies are only selected when:
- An evidence gap persists after Phase 5 strategies
- Extended budget is available
- Strategy is applicable (prerequisites satisfied)

## Infrastructure

All Phase 6 strategies use shared infrastructure from [`strategies/infrastructure.py`](../backend/app/strategies/infrastructure.py):

### DeterministicSeed
```python
seed = hash(f"{snapshot_hash}:{strategy_name}") % (2**32)
```
Reproducible across runs for the same snapshot. Ensures identical random inputs on rerun.

### BoundedExecutionContext
- `max_iterations`: 50 (default)
- `max_seconds`: 30.0 (default)
- Raises `BudgetExhaustedError` when limit reached
- Time and iteration counters tracked; budget checked before each iteration

### IsolatedWorkspace
- Temporary directory created per strategy execution
- Guaranteed cleanup via context manager (`__exit__` always called)
- Workspace never escapes its temp directory (path contains `receipts_strategy_ws_`)

### MutantCleanupRegistry
- Tracks all mutated file paths
- `restore_all()` reverts every mutated file to original content
- Called in `finally` blocks — cleanup always happens even on exception

### CounterexampleRecord
- Stores original failing input + minimized version
- `is_minimized`: bool indicating whether shrinking was applied
- Persisted to `counterexample_record` table for reproducibility
