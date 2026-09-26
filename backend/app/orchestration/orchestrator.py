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
    Phase 5 verdict logic.

    The verdict is driven by EXECUTION evidence (test results).
    Documentation issues are advisory and do not affect the verdict.

    Priority order:
    1. Empty evidences → ESCALATE
    2. ERROR / TIMEOUT from any agent → ESCALATE (execution failed)
    3. FAIL from test_runner, catching_test, or unknown agents → BUG_DETECTED
       (documentation_check is explicitly excluded — doc issues are advisory)
    4. test_runner PASS (with other agents PASS/INSUFFICIENT_EVIDENCE/advisory-FAIL)
       → SAFE.  Advisory agents without git history return INSUFFICIENT_EVIDENCE;
       doc check may return FAIL for workspaces without README.  Neither blocks SAFE
       when the primary test evidence is clean.
    5. INSUFFICIENT_EVIDENCE present with no test_runner PASS → ESCALATE
    6. All PASS (no specific test_runner, e.g. unit tests of _calculate_verdict) → SAFE

    Backward compatibility (test_receipts.py, test_phase2.py, final_verify.py):
    - Solo AgentEvidence("t", ..., "PASS", ...) → SAFE      (step 6)
    - Solo AgentEvidence("t", ..., "FAIL", ...) → BUG_DETECTED  (step 3, "t" ≠ doc)
    - Solo AgentEvidence("t", ..., "ERROR", ...) → ESCALATE  (step 2)
    - Solo AgentEvidence("t", ..., "INSUFFICIENT_EVIDENCE", ...) → ESCALATE  (step 5)
    - [test_runner PASS, catching_test ERROR] → ESCALATE  (step 2)
    - [test_runner PASS, catching_test FAIL] → BUG_DETECTED  (step 3)
    """
    if not evidences:
        return VerdictEnum.ESCALATE, 0.0

    # 1. Hard execution failure: ERROR or TIMEOUT → ESCALATE
    if any(e.result in ("ERROR", "TIMEOUT") for e in evidences):
        return VerdictEnum.ESCALATE, 0.0

    # Advisory agents whose FAIL is informational and does not prove a code defect.
    _ADVISORY = {"documentation_check"}

    # 2. FAIL from non-advisory agents → BUG_DETECTED
    hard_fails = [e for e in evidences
                  if e.result == "FAIL" and e.agent not in _ADVISORY]
    if hard_fails:
        confidence = max(e.confidence for e in hard_fails)
        return VerdictEnum.BUG_DETECTED, confidence

    # 3. test_runner PASS → SAFE if no blocking failures remain
    #    Non-test_runner agents may return FAIL (advisory) or INSUFFICIENT_EVIDENCE.
    #    Both are non-blocking when the test runner confirms tests pass.
    test_runner_evidences = [e for e in evidences if e.agent == "test_runner"]
    if test_runner_evidences and all(e.result == "PASS" for e in test_runner_evidences):
        # Remaining agents must not have hard errors (already checked above)
        # INSUFFICIENT_EVIDENCE and advisory FAILs are acceptable here
        other = [e for e in evidences if e.agent != "test_runner"]
        if all(e.result in ("PASS", "INSUFFICIENT_EVIDENCE", "FAIL")
               and (e.result != "FAIL" or e.agent in _ADVISORY)
               for e in other):
            return VerdictEnum.SAFE, 1.0

    # 4. INSUFFICIENT_EVIDENCE without a clean test_runner PASS → ESCALATE
    if any(e.result == "INSUFFICIENT_EVIDENCE" for e in evidences):
        return VerdictEnum.ESCALATE, 0.0

    # 5. All PASS (covers single-evidence unit tests and multi-agent all-PASS)
    if all(e.result == "PASS" for e in evidences):
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
        repository_path_override: Optional[str] = None,
    ) -> ReviewRun:
        # 1. Create/find repository
        repo = self._get_or_create_repo(db, repo_name)

        # 2. Create PR record
        pr = self._create_pr(db, repo, pr_number, pr_title, author, base_branch, head_branch, commit_sha)

        # 3. Risk Assessment
        # repository_path_override is used by replay engine to pass an isolated workspace
        repo_path = repository_path_override or repo.local_path or settings.demo_repo_path
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

        # 6. Run adaptive planner (populates evidence/claims/trace tables;
        #    its AgentEvidence objects are intentionally discarded — the
        #    verdict is always driven by the primary agent evidences above
        #    to preserve full backward compatibility).
        try:
            from app.evidence.snapshot import RepositorySnapshot
            from app.planner.planner import StrategyPlanner
            snapshot = RepositorySnapshot.create(repo_path)
            planner = StrategyPlanner()
            planner.execute_adaptive(snapshot, db, run.id)
        except Exception as _planner_exc:
            logger.warning("Adaptive planner raised (non-fatal): %s", _planner_exc)

        # 7. Calculate verdict
        verdict, confidence = _calculate_verdict(evidences)

        # 8. Finalise run
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
        local_path = settings.demo_repo_path if name in ("demo", "demo_repo") else None
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
