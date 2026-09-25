"""
Review Orchestrator — Phase 2.

Pipeline:
  ReviewRequest
      ↓
  Risk Assessment (deterministic)
      ↓
  ┌───────────────────────┐
  │ Test Runner           │
  │ Catching Test         │  ← parallel via ThreadPoolExecutor
  │ Documentation Check   │
  │ History Check         │
  └───────────────────────┘
      ↓
  Evidence Receipts
      ↓
  Verdict

Events are emitted to the event bus throughout so SSE subscribers receive live progress.
"""
from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app import audit
from app.agents import (
    AgentEvidence,
    CatchingTestAgent,
    DocumentationCheckAgent,
    HistoryCheckAgent,
    TestRunner,
)
from app.agents.base import BaseAgent
from app.config import settings
from app.events import (
    EVT_AGENT_COMPLETED,
    EVT_AGENT_FAILED,
    EVT_AGENT_STARTED,
    EVT_RECEIPT_CREATED,
    EVT_REVIEW_COMPLETED,
    EVT_REVIEW_STARTED,
    event_bus,
)
from app.models import (
    AgentExecution,
    AgentStatusEnum,
    PullRequest,
    Receipt,
    Repository,
    ReviewEvent,
    ReviewRun,
    ReviewStatusEnum,
    SeverityEnum,
    VerdictEnum,
)
from app.services import assess_risk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database session factory for background threads
# ---------------------------------------------------------------------------
# Each parallel agent runs in its own thread and needs its own DB session.
# We import SessionLocal here to create per-thread sessions.
from app.database import SessionLocal


def _new_db() -> Session:
    return SessionLocal()


# ---------------------------------------------------------------------------
# Verdict calculation
# ---------------------------------------------------------------------------

def _calculate_verdict(evidences: list[AgentEvidence]) -> tuple[str, float]:
    """
    Phase 2 verdict logic (same rules as Phase 1, applied across all agents):

    - Any ERROR/TIMEOUT/INSUFFICIENT_EVIDENCE → ESCALATE
    - Any FAIL → BUG_DETECTED
    - All PASS → SAFE
    """
    if not evidences:
        return VerdictEnum.ESCALATE, 0.0

    results = [e.result for e in evidences]

    if any(r in ("ERROR", "TIMEOUT") for r in results):
        return VerdictEnum.ESCALATE, 0.0

    if any(r == "FAIL" for r in results):
        # Confidence = highest confidence among FAIL results
        fail_confidences = [e.confidence for e in evidences if e.result == "FAIL"]
        confidence = max(fail_confidences) if fail_confidences else 0.5
        return VerdictEnum.BUG_DETECTED, confidence

    # INSUFFICIENT_EVIDENCE without FAIL — escalate but with lower urgency
    if any(r == "INSUFFICIENT_EVIDENCE" for r in results):
        return VerdictEnum.ESCALATE, 0.0

    if all(r == "PASS" for r in results):
        return VerdictEnum.SAFE, 1.0

    return VerdictEnum.ESCALATE, 0.0


# ---------------------------------------------------------------------------
# Event persistence helper
# ---------------------------------------------------------------------------

def _persist_event(db: Session, run_id: str, event_type: str,
                   agent_type: Optional[str] = None, payload: Optional[dict] = None):
    """Write a ReviewEvent row and emit to the in-process bus."""
    payload_str = json.dumps(payload or {}, default=str)
    ev = ReviewEvent(
        id=str(uuid.uuid4()),
        review_run_id=run_id,
        event_type=event_type,
        agent_type=agent_type,
        payload=payload_str,
    )
    db.add(ev)
    db.commit()
    # Also emit to SSE bus (non-blocking)
    event_bus.emit(run_id, event_type, payload={
        "agent_type": agent_type,
        **(payload or {}),
    })


# ---------------------------------------------------------------------------
# Per-agent worker (runs in ThreadPoolExecutor)
# ---------------------------------------------------------------------------

def _run_agent_worker(
    run_id: str,
    agent: BaseAgent,
    repository_path: str,
) -> tuple[str, AgentEvidence, str]:  # (execution_id, evidence, agent_type)
    """
    Runs in a ThreadPoolExecutor thread.
    Creates its own DB session — never shares sessions across threads.
    Returns (execution_id, evidence, agent_type).
    """
    db = _new_db()
    execution_id = str(uuid.uuid4())
    try:
        # Record agent execution start
        execution = AgentExecution(
            id=execution_id,
            review_run_id=run_id,
            agent_type=agent.agent_type,
            status=AgentStatusEnum.RUNNING,
            started_at=datetime.utcnow(),
        )
        db.add(execution)
        db.commit()

        _persist_event(db, run_id, EVT_AGENT_STARTED,
                       agent_type=agent.agent_type,
                       payload={"execution_id": execution_id})
        audit.record_event(db, audit.EVT_AGENT_STARTED, review_run_id=run_id,
                           payload={"agent": agent.agent_type, "execution_id": execution_id})

        # Run the agent
        try:
            evidence = agent.run(repository_path)
        except Exception as exc:
            logger.exception("Agent %s raised unexpected exception", agent.agent_type)
            evidence = AgentEvidence(
                agent=agent.agent_type, command=None, result="ERROR",
                evidence=f"Unexpected agent exception: {exc}",
                severity="CRITICAL", confidence=0.0,
                title=f"{agent.agent_type} — Unexpected Error",
            )

        # Map result → agent status
        status_map = {
            "PASS": AgentStatusEnum.COMPLETED,
            "FAIL": AgentStatusEnum.COMPLETED,
            "ERROR": AgentStatusEnum.ERROR,
            "TIMEOUT": AgentStatusEnum.TIMEOUT,
            "INSUFFICIENT_EVIDENCE": AgentStatusEnum.INSUFFICIENT_EVIDENCE,
        }
        execution.status = status_map.get(evidence.result, AgentStatusEnum.ERROR)
        execution.completed_at = datetime.utcnow()
        db.commit()

        # Create receipt
        severity_map = {
            "PASS": SeverityEnum.PASS,
            "FAIL": SeverityEnum.HIGH,
            "ERROR": SeverityEnum.CRITICAL,
            "TIMEOUT": SeverityEnum.HIGH,
            "INSUFFICIENT_EVIDENCE": SeverityEnum.INFO,
        }
        severity = severity_map.get(evidence.result, SeverityEnum.INFO)
        receipt = Receipt(
            id=str(uuid.uuid4()),
            review_run_id=run_id,
            agent_execution_id=execution_id,
            title=evidence.title,
            command=evidence.command,
            test_ref=evidence.test_ref,
            result_summary=evidence.result,
            raw_output=evidence.evidence,
            file_ref=evidence.file_ref,
            severity=severity,
            confidence=evidence.confidence,
        )
        db.add(receipt)
        db.commit()

        event_type = EVT_AGENT_FAILED if evidence.result in ("ERROR", "TIMEOUT") else EVT_AGENT_COMPLETED
        _persist_event(db, run_id, event_type,
                       agent_type=agent.agent_type,
                       payload={"result": evidence.result, "execution_id": execution_id,
                                "receipt_id": receipt.id})
        _persist_event(db, run_id, EVT_RECEIPT_CREATED,
                       agent_type=agent.agent_type,
                       payload={"receipt_id": receipt.id, "result": evidence.result})
        audit.record_event(db, audit.EVT_AGENT_COMPLETED, review_run_id=run_id,
                           payload={"agent": agent.agent_type, "result": evidence.result})
        audit.record_event(db, audit.EVT_RECEIPT_CREATED, review_run_id=run_id,
                           payload={"receipt_id": receipt.id, "agent": agent.agent_type})

        return execution_id, evidence, agent.agent_type

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ReviewOrchestrator:
    """
    Phase 2: runs all four agents in parallel.
    New agents are added by appending to _build_agents().
    """

    def run_review(
        self,
        db: Session,
        repo_name: str,
        pr_number: int,
        pr_title: str = "PR Review",
        author: Optional[str] = None,
        base_branch: str = "main",
        head_branch: Optional[str] = None,
        commit_sha: Optional[str] = None,
    ) -> ReviewRun:
        # 1. Create/find repository
        repo = self._get_or_create_repo(db, repo_name)

        # 2. Create PR record
        pr = self._create_pr(db, repo, pr_number, pr_title, author, base_branch, head_branch, commit_sha)

        # 3. Risk Assessment
        repo_path = repo.local_path or settings.demo_repo_path
        risk_result = assess_risk(repo_path)
        risk_level = risk_result.level

        # 4. Create review_run
        run = ReviewRun(
            id=str(uuid.uuid4()),
            pr_id=pr.id,
            risk_level=risk_level,
            status=ReviewStatusEnum.RUNNING,
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        _persist_event(db, run.id, EVT_REVIEW_STARTED,
                       payload={"repo": repo_name, "pr": pr_number, "risk": risk_level,
                                "rationale": risk_result.rationale})
        audit.record_event(db, audit.EVT_REVIEW_STARTED, review_run_id=run.id,
                           payload={"repo": repo_name, "pr": pr_number, "risk": risk_level})

        # 5. Run all agents in parallel
        agents = self._build_agents()
        evidences: list[AgentEvidence] = []

        with ThreadPoolExecutor(max_workers=len(agents), thread_name_prefix="agent") as pool:
            futures = {
                pool.submit(_run_agent_worker, run.id, agent, repo_path): agent
                for agent in agents
            }
            for future in as_completed(futures):
                try:
                    _exec_id, evidence, _atype = future.result()
                    evidences.append(evidence)
                except Exception as exc:
                    logger.exception("Agent future raised: %s", exc)
                    # Create an ERROR evidence so the verdict is never falsely SAFE
                    evidences.append(AgentEvidence(
                        agent="unknown", command=None, result="ERROR",
                        evidence=f"Agent future exception: {exc}",
                        confidence=0.0,
                    ))

        # 6. Calculate verdict
        verdict, confidence = _calculate_verdict(evidences)

        # 7. Finalise run
        completed_at = datetime.utcnow()
        elapsed_ms = int((completed_at - run.started_at).total_seconds() * 1000)
        run.verdict = verdict
        run.confidence = confidence
        run.status = ReviewStatusEnum.COMPLETED
        run.completed_at = completed_at
        run.elapsed_ms = elapsed_ms
        db.commit()
        db.refresh(run)

        _persist_event(db, run.id, EVT_REVIEW_COMPLETED,
                       payload={"verdict": verdict, "confidence": confidence})
        audit.record_event(db, audit.EVT_VERDICT_CREATED, review_run_id=run.id,
                           payload={"verdict": verdict, "confidence": confidence})
        event_bus.emit_done(run.id)

        logger.info("review_run id=%s verdict=%s risk=%s elapsed_ms=%d",
                    run.id, verdict, risk_level, elapsed_ms)
        return run

    # ------------------------------------------------------------------
    # Agent pipeline
    # ------------------------------------------------------------------

    def _build_agents(self) -> list[BaseAgent]:
        """Phase 2: all four agents."""
        return [
            TestRunner(),
            CatchingTestAgent(),
            DocumentationCheckAgent(),
            HistoryCheckAgent(),
        ]

    # ------------------------------------------------------------------
    # Repo / PR helpers
    # ------------------------------------------------------------------

    def _get_or_create_repo(self, db: Session, name: str) -> Repository:
        repo = db.query(Repository).filter(Repository.name == name).first()
        if repo:
            return repo
        local_path = settings.demo_repo_path if name == "demo" else None
        repo = Repository(id=str(uuid.uuid4()), name=name, local_path=local_path)
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo

    def _create_pr(self, db, repo, number, title, author, base_branch, head_branch, commit_sha):
        pr = PullRequest(
            id=str(uuid.uuid4()),
            repo_id=repo.id, number=number, title=title, author=author,
            base_branch=base_branch, head_branch=head_branch, commit_sha=commit_sha,
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)
        return pr
