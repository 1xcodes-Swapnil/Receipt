# Project Overview — Receipts

## What is Receipts?

Receipts is an **evidence-first automated code review and bug immunity backend**. It reviews pull requests not by predicting problems but by collecting verifiable evidence — running real commands against real code — and only emitting findings when that evidence exists.

The central invariant is:

> **NO EVIDENCE, NO FLAG.**

Every verdict — `SAFE`, `BUG_DETECTED`, or `ESCALATE` — is the result of real execution, never model speculation.

## Core Problem It Solves

Typical AI code review tools flag issues based on pattern-matching or model predictions. These findings cannot be independently verified, produce false alarms, and cannot be audited. Receipts inverts this: the system must produce a **receipt** (a cryptographically-auditable record containing exact commands and their real output) before any finding is reported.

If execution fails, evidence is missing, or the system cannot safely continue, the verdict is `ESCALATE` — never `SAFE`.

## What the System Does

Given a repository path and pull request number, Receipts:

1. **Runs 4 parallel review agents** against the code (test execution, diff analysis, documentation check, history check)
2. **Collects evidence** for two claims: code correctness and documentation health
3. **Assigns a verdict** (`SAFE` / `BUG_DETECTED` / `ESCALATE`) from that evidence
4. **Persists cryptographically-auditable receipts** in SQLite with a SHA-256 hash chain
5. **On BUG_DETECTED**: optionally runs the **Bug-to-Immunity pipeline** — 8 evidence-gated stages that reproduce, locate, fix, verify, and register the defect in a pattern library

## What It Does Not Do

- It does not predict bugs from code without running tests
- It does not use a language model to generate verdicts
- It does not auto-merge or modify real GitHub pull requests
- It does not store test results without running the tests
- It does not emit `SAFE` when evidence is ambiguous or execution fails

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy |
| Database | SQLite (default), PostgreSQL-ready |
| Testing | pytest |
| Demo | `demo/run_demo.py`, `backend/demo_cli.py` |
| Documentation | `docs/` |

There is no frontend for the current production backend. The Phase 1 React frontend exists at `frontend/` but is not part of the active backend architecture.

## Phase History

| Phase | Scope |
|-------|-------|
| 1 | Foundation: test runner, receipt, SQLite, basic verdict |
| 2 | 4 parallel agents, SSE events, orchestration |
| 3 | Bug-to-Immunity pipeline (7 stages, Phase 3 orchestrator) |
| 4 | Replay engine with ground-truth benchmark |
| 5 | Workspace isolation, audit chain, security hardening |
| 6 | Adaptive evidence architecture: EvidenceLedger, StrategyPlanner, 14 strategies |
| 7 | V7 Bug-to-Immunity with explicit state machine, HypothesisTracker, AdaptiveFixPlanner |
| 8 | V7 canonicalization, GitHub provider, replay trace capture, demo runner, documentation |
