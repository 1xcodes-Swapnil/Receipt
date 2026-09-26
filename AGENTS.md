# AGENTS.md — Receipts Project Invariants

**Phase 2 active. Phase 3+ (Bug-to-Immunity, Replay, Scoreboard) deferred.**

## Core Invariants

These rules apply to every agent, every phase, every contributor.

### 1. Evidence Before Findings

An agent MUST produce concrete, verifiable evidence before creating any finding.
A receipt is only valid if it contains real command output, real test results, or real file references.
Never create a BUG_DETECTED finding from an AI statement alone.

### 2. Never Invent Test Results

Agents may not fabricate, simulate, or approximate test outcomes.
If execution fails, the result is an execution failure — not a guess.
Real stdout/stderr from a real process is required.

### 3. Agent Failure Cannot Become SAFE

If an agent errors, times out, or produces insufficient evidence, the verdict MUST be ESCALATE.
Never convert an agent failure or missing evidence into a SAFE verdict.

### 4. Keep Agents Isolated

Each agent runs independently.
Agents do not share mutable state.
Agents communicate only through structured receipts.

### 5. Prefer Deterministic, Reproducible Execution

Commands must be reproducible given the same repository state.
Avoid non-deterministic behavior. Log every command invoked.
The demo repository must always produce the same result.

### 6. Do Not Implement Future Phases Prematurely

Phase 1 scope: Test Runner, basic orchestration, receipt storage, PR Review UI. ✅ Complete.
Phase 2 scope: All four agents (TestRunner, CatchingTest, DocumentationCheck, HistoryCheck),
Risk Assessment, parallel execution, Sandbox, SSE stream, live agent cards. ✅ Complete.
Phase 3+ deferred: Bug-to-Immunity pipeline, Replay engine, Scoreboard, GitHub integration,
advanced AI reasoning, production authentication, Redis, PostgreSQL deployment.

---

## Receipt Minimum Structure

```json
{
  "agent": "test_runner",
  "command": "pytest",
  "result": "PASS",
  "evidence": "<actual stdout>",
  "file_ref": null,
  "severity": "PASS",
  "confidence": 1.0
}
```

## Verdict Rules (Phase 1)

| Evidence                     | Verdict       |
|------------------------------|---------------|
| PASS evidence                | SAFE          |
| FAIL evidence                | BUG_DETECTED  |
| Execution failure / timeout  | ESCALATE      |
| Missing evidence             | ESCALATE      |

## Agent Status Values

- `pending` — not yet started
- `running` — currently executing
- `completed` — finished with evidence
- `error` — exception during execution
- `timeout` — exceeded time limit
- `insufficient_evidence` — ran but produced no usable evidence
