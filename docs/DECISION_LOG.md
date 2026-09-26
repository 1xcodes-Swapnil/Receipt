# Decision Log — Receipts

## Purpose

This log records the key architectural and design decisions made during development. Each entry explains the decision and the reasoning behind it.

---

## D-001: Evidence Before Findings (Phase 1)

**Decision**: Every verdict must be backed by real command output. No finding is emitted without a receipt.

**Reasoning**: AI speculation produces false alarms that erode developer trust. A finding is only valuable when it can be independently verified. The receipt contains the exact command and real output — any developer can rerun the command and verify the result.

**Consequence**: The system returns `ESCALATE` when evidence is missing, rather than guessing `SAFE`.

---

## D-002: Fail-Closed on Missing Evidence (Phase 1)

**Decision**: When evidence is insufficient, ambiguous, or execution fails → `ESCALATE`. Never `SAFE`.

**Reasoning**: A missed bug is worse than an unresolved escalation. An `ESCALATE` tells a developer "we couldn't verify this" — a false `SAFE` tells them "nothing to see here" when a bug may exist.

**Consequence**: The system is conservative. Some clean code will escalate if tests are absent.

---

## D-003: Documentation Agent is Advisory (Phase 2)

**Decision**: `documentation_check` FAIL does not trigger `BUG_DETECTED`. It is advisory only.

**Reasoning**: Missing or incomplete documentation does not constitute a code defect. Treating doc failures as authoritative would produce BUG_DETECTED for any PR without a README.

**Consequence**: Doc failures are recorded in receipts and evidence items but do not affect the code correctness verdict.

---

## D-004: File-Based SQLite for Tests (Phase 2)

**Decision**: Use file-based SQLite (`_phase{N}_test.db`) rather than in-memory for test databases.

**Reasoning**: Agent workers run in `ThreadPoolExecutor` threads, each creating their own `SessionLocal()`. SQLite in-memory databases are not shared across connections — a worker thread would see an empty database. File-based SQLite with `check_same_thread=False` works correctly.

**Consequence**: Test databases are created on disk and cleaned up after each module.

---

## D-005: Process-Local Audit Lock (Phase 5)

**Decision**: Use a `threading.Lock` for audit chain serialization.

**Reasoning**: The deployment target is a single uvicorn process. A process-local lock is sufficient, avoids external dependencies (Redis, advisory locks), and is deterministic.

**Consequence**: Multi-process deployments (multiple workers) would require database-level serialization. This is documented in CURRENT_LIMITATIONS.md.

---

## D-006: Sequence Number over created_at for Chain Ordering (Phase 5)

**Decision**: Use a monotonic `sequence` integer (assigned under lock) as the authoritative event order for the audit chain, not `created_at`.

**Reasoning**: Parallel agent threads may commit with equal timestamps. Timestamp ordering would produce ambiguous or non-deterministic chains. A sequence number assigned under `_audit_lock` is unambiguous.

---

## D-007: CounterexampleShrinking Not in Default Registry (Phase 6)

**Decision**: `CounterexampleShrinkingStrategy` is only added via `build_shrinking_registry()`, not the default registry.

**Reasoning**: CounterexampleShrinking requires a *failing input* as a prerequisite — it has no meaningful behavior without one. Adding it to the default registry would cause every review to evaluate it as INSUFFICIENT without providing value. It is only useful as a follow-on to Fuzzing or PropertyBased strategies.

---

## D-008: Surviving Mutants ≠ Bug (Phase 6)

**Decision**: Surviving mutants from mutation testing are evidence of **test weakness**, not proof of a code defect.

**Reasoning**: A mutant that survives (tests don't catch it) means tests are insufficient to catch that specific change. It does not mean the original code is buggy. Reporting surviving mutants as bugs would produce false alarms.

**Consequence**: MutationTesting produces `FAIL` only for low kill rates; the interpretation is "tests are weak" not "code is broken".

---

## D-009: Hypothesis Requires Independent Verification (Phase 7)

**Decision**: Fault localization alone cannot verify a hypothesis. A hypothesis requires traceback confirmation + test output confirmation.

**Reasoning**: Fault localization ranks suspicious locations statistically — it is a hypothesis, not proof. Using it directly to claim "the bug is here" without traceback evidence would produce confident-but-wrong root cause assertions.

**Consequence**: The Root Cause stage is ESCALATED when fault localization provides a location but the traceback cannot independently confirm it. This is correct fail-closed behavior.

---

## D-010: V7 as Canonical Orchestrator (Phase 8)

**Decision**: `ImmunityOrchestrator` (the public alias) now points to `ImmunityOrchestratorV7`. Phase 3 orchestrator remains importable as `immunity.orchestrator.ImmunityOrchestrator` for backward compatibility.

**Reasoning**: Phase 7 introduced a richer, evidence-gated pipeline with explicit state machine, hypothesis tracking, and fix retry with fresh workspaces. V7 is strictly superior to Phase 3 for production use. All new code should use the canonical alias.

---

## D-011: Fresh Workspace Per Fix Retry (Phase 8)

**Decision**: Each fix retry in the immunity pipeline uses a fresh workspace copy.

**Reasoning**: A failed partial fix (e.g. a patch that applies but introduces syntax errors) may contaminate the workspace. The next fix attempt must start from a clean, unmodified copy of the original repository.

**Consequence**: `ImmunityContext._replace_workspace()` is called before each retry. Workspace cleanup is always performed.

---

## D-012: Conservative Fix Strategies (Phase 7)

**Decision**: 11 of 12 fix strategies detect patterns but do not auto-apply changes in all cases. Only `AccumulatorResetStrategy` produces a working patch for the demo bug.

**Reasoning**: Automated code modification is high-risk. Strategies should only modify code when the pattern is unambiguous and the fix is mechanical (like replacing `=` with `+=`). For boundary conditions, null handling, and similar patterns, the evidence is structural but the correct fix is not deterministic — manual review is required.

**Consequence**: IMMUNITY_COMPLETE is only achievable for the accumulator reset pattern in the current implementation. The system correctly reports BLOCKED for other bug types rather than attempting unsafe repairs.

---

## D-013: Planner Budget Split (Phase 6)

**Decision**: The planner has two budget levels: base (5 strategies, Phase 5 only) and extended (9 strategies, Phase 5+6).

**Reasoning**: Phase 6 advanced strategies are expensive (cost 4–7) and should only run when cheaper strategies haven't resolved the evidence gap. Running mutation testing on every PR would be prohibitively slow.

**Consequence**: In practice, the Phase 8 demo showed that all 6 replay cases were resolved with Phase 5 strategies alone. Phase 6 strategies are activated only for cases where the base set is insufficient.
