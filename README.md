# Receipts — Evidence-First Code Review & Bug Immunity

> **NO EVIDENCE, NO FLAG.** Every finding must be backed by concrete, verifiable evidence.

## Overview

Receipts is a code review platform built around the principle that every bug finding must be backed by real, executable evidence — not AI speculation. Each review produces cryptographically-auditable receipts containing the exact commands run, their output, and the verdict derived from that output.

## Phase 1 — Foundation

Phase 1 implements the core evidence loop:

```
React → FastAPI → Review Orchestrator → Test Runner → Evidence Receipt → SQLite → React
```

### What works in Phase 1

- Trigger a review via the PR Review UI
- Test Runner executes against a demo repository
- Receipt created and stored in SQLite
- Verdict calculated from real test output
- UI displays the evidence receipt

### What is stubbed (coming in later phases)

- Catching Test agent
- Documentation Check agent
- History Check agent
- GitHub integration
- Bug-to-Immunity pipeline
- Replay engine
- Advanced risk scoring

## Stack

| Layer    | Technology                        |
|----------|-----------------------------------|
| Frontend | React, TypeScript, Vite, Tailwind |
| Backend  | Python, FastAPI, SQLAlchemy       |
| Database | SQLite (PostgreSQL-ready)         |
| Testing  | pytest                            |

## Getting Started

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Demo Flow

1. Navigate to **PR Review**
2. The demo repository (demo/repository) is pre-selected
3. Click **Run Review**
4. The backend executes `pytest` against the demo tests
5. The receipt is displayed with real command output

## API Endpoints

| Method | Path                            | Description              |
|--------|--------------------------------|--------------------------|
| GET    | /health                         | Health check             |
| POST   | /repos/{repo}/prs/{number}/review | Trigger a review       |
| GET    | /reviews/{run_id}               | Get review run details   |
| GET    | /reviews/{run_id}/receipts      | Get receipts for a run   |

## Project Structure

```
frontend/          React + TypeScript + Vite
backend/           FastAPI + SQLAlchemy
database/          SQLite file + migrations
demo/              Demo repository with test suite
.bob/              IBM Bob configuration
AGENTS.md          Project invariants
README.md          This file
```

## Core Invariant

**NO EVIDENCE, NO FLAG.**

See [AGENTS.md](AGENTS.md) for the full list of project invariants.
