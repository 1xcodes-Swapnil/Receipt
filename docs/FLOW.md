# Review Flow — Receipts

## End-to-End Review Flow

```
POST /repos/{repo}/prs/{number}/review
             │
             ▼
      ReviewOrchestrator.run_review()
             │
      ┌──────┴─────────────────────────────────┐
      │ Risk Assessment (deterministic)         │
      │  → risk_level: low / medium / high /   │
      │                critical                 │
      └──────┬──────────────────────────────────┘
             │
      ┌──────┴─────────────────────────────────────────────────┐
      │ 4 Agents in parallel (ThreadPoolExecutor)              │
      │                                                         │
      │  TestRunner          — runs pytest, captures output     │
      │  CatchingTestAgent   — differential test analysis       │
      │  DocumentationCheck  — README / docstring checks        │
      │  HistoryCheckAgent   — git blame / commit history       │
      └──────┬──────────────────────────────────────────────────┘
             │ Each agent → AgentEvidence (result, confidence)
             │
      ┌──────┴─────────────────────────────────┐
      │ StrategyPlanner (Adaptive Evidence)    │
      │                                         │
      │  1. Analyse snapshot → Claims          │
      │     • code_correctness                 │
      │     • test_coverage                    │
      │     • documentation                    │
      │                                         │
      │  2. For each open claim gap:            │
      │     select cheapest applicable strategy │
      │     → execute                           │
      │     → record EvidenceItem + TraceEntry │
      │     → re-evaluate gap                   │
      │                                         │
      │  3. Stop when: all claims resolved      │
      │     OR budget exhausted                 │
      │     OR diminishing returns              │
      └──────┬──────────────────────────────────┘
             │
      ┌──────┴─────────────────────────────────┐
      │ Verdict Engine                         │
      │                                         │
      │  ESCALATE  if any agent ERROR/TIMEOUT   │
      │  BUG_DETECTED if any hard FAIL          │
      │             (non-advisory)              │
      │  SAFE if test_runner PASS + no blockers │
      │  ESCALATE if insufficient evidence      │
      └──────┬──────────────────────────────────┘
             │
             ▼
      Evidence Receipts persisted in SQLite
      Audit event emitted (SHA-256 chain)
      SSE events streamed to subscribers
             │
             │  (on BUG_DETECTED)
             ▼
      POST /reviews/{run_id}/immunity
      → ImmunityOrchestratorV7
```

## Claim and Evidence Flow

```
Snapshot created (immutable, hash-verified)
         │
         ▼
   Claim generated
   ┌─────────────────────────────┐
   │ claim_type: code_correctness │
   │ claim_type: test_coverage    │
   │ claim_type: documentation    │
   └─────────────────────────────┘
         │
         ▼
   Strategy selected by planner
   (based on claim type + cost + prerequisites)
         │
         ▼
   Strategy executes against snapshot workspace
         │
         ▼
   EvidenceItem created:
   ┌─────────────────────────────────┐
   │ result: PASS|FAIL|INSUFFICIENT  │
   │ confidence: 0.0–1.0             │
   │ command: exact command run      │
   │ raw_output: real stdout/stderr  │
   └─────────────────────────────────┘
         │
         ▼
   EvidenceLedger evaluates claim:
   ┌────────────────────────────────┐
   │ status: SUPPORTED|REFUTED|     │
   │         INSUFFICIENT|CONFLICTED│
   └────────────────────────────────┘
         │
         ▼
   Sufficiency evaluator:
   - sufficient evidence? → verdict
   - gap remains? → next strategy
   - no strategy left? → ESCALATE
```

## Verdict Decision Table

| Condition | Verdict |
|-----------|---------|
| Any agent ERROR or TIMEOUT | ESCALATE |
| Any non-advisory agent FAIL | BUG_DETECTED |
| test_runner PASS, no hard failures | SAFE |
| Insufficient evidence, no test_runner PASS | ESCALATE |
| Empty evidence | ESCALATE |
| All PASS | SAFE |

**Advisory agents** (FAIL is informational, does not force BUG_DETECTED):
- `documentation_check`
- `history_check`

## Immunity Flow (on BUG_DETECTED)

See [BUG_TO_IMMUNITY.md](BUG_TO_IMMUNITY.md) for the complete V7 pipeline flow.

```
ImmunityOrchestratorV7.run_pipeline()
         │
   PENDING → RUNNING → REPRODUCING
         │
   Reproduce stage:
   - runs pytest in isolated workspace
   - confirms bug reproduces
   - gate: PASSED required to advance
         │
   ROOT_CAUSE → FIXING → VERIFYING → REGRESSION_TESTING
              → SIBLING_HUNT → DOCUMENTING
              → PATTERN_EVALUATION → IMMUNITY_COMPLETE
         │
   At any stage gate failure:
   - BLOCKED (prerequisite missing or not satisfied)
   - ESCALATED (contradiction or unsafe to continue)
   - FAILED → retry FIXING (up to MAX_FIX_RETRIES=3)
```
