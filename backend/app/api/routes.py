"""
FastAPI route handlers for Receipts Phase 2 + 3 + 4.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.events import event_bus
from app.models import (
    AgentExecution,
    AuditEvent,
    EvidenceGap,
    EvidenceItem,
    ImmunityPipeline,
    PatternLibraryEntry,
    Receipt,
    ReplayCase,
    ReplayResult,
    ReplayRun,
    ReviewClaim,
    ReviewEvent,
    ReviewRun,
    SiblingFinding,
    StrategyTraceEntry,
)
from app.orchestration import ReviewOrchestrator
from app.schemas import (
    AgentExecutionOut,
    AuditEventOut,
    AuditVerificationOut,
    EvidenceGapOut,
    EvidenceItemOut,
    HealthOut,
    ImmunityPipelineDetail,
    ImmunityPipelineOut,
    ImmunityRequest,
    ImmunityStageOut,
    PatternLibraryEntryOut,
    ReplayCaseOut,
    ReplayRequest,
    ReplayResultOut,
    ReplayRunOut,
    ReceiptOut,
    ReviewClaimOut,
    ReviewEventOut,
    ReviewRequest,
    ReviewRunDetail,
    ReviewRunOut,
    SiblingFindingOut,
    StrategyTraceEntryOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _receipt_with_agent(receipt: Receipt, agent_type: str) -> ReceiptOut:
    """Build a ReceiptOut and populate the denormalized agent field."""
    out = ReceiptOut.model_validate(receipt)
    out.agent = agent_type
    return out


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthOut, tags=["system"])
def health():
    return HealthOut(status="ok", version=settings.app_version)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

@router.post(
    "/repos/{repo}/prs/{number}/review",
    response_model=ReviewRunOut,
    status_code=201,
    tags=["reviews"],
)
def create_review(
    repo: str = Path(...),
    number: int = Path(...),
    body: ReviewRequest = Body(default_factory=ReviewRequest),
    db: Session = Depends(get_db),
):
    """Trigger a review. Runs all four agents in parallel."""
    # Security: validate repo name before it is used in path construction
    from app.security import validate_repo_name
    try:
        repo = validate_repo_name(repo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    orchestrator = ReviewOrchestrator()
    try:
        run = orchestrator.run_review(
            db=db,
            repo_name=repo,
            pr_number=number,
            pr_title=body.pr_title,
            author=body.author,
            base_branch=body.base_branch,
            head_branch=body.head_branch,
            commit_sha=body.commit_sha,
        )
    except Exception as exc:
        logger.exception("Orchestrator failed for repo=%s pr=%d", repo, number)
        raise HTTPException(status_code=500, detail=f"Review orchestration failed: {exc}") from exc

    return ReviewRunOut.model_validate(run)


@router.get("/reviews/{run_id}", response_model=ReviewRunDetail, tags=["reviews"])
def get_review(run_id: str, db: Session = Depends(get_db)):
    """Get a review run with its agent executions and receipts."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")

    detail = ReviewRunDetail.model_validate(run)
    detail.agent_executions = [
        AgentExecutionOut.model_validate(ae) for ae in run.agent_executions
    ]
    detail.receipts = [
        _receipt_with_agent(r, ae.agent_type)
        for ae in run.agent_executions
        for r in ae.receipts
    ]
    return detail


@router.get("/reviews/{run_id}/receipts", response_model=list[ReceiptOut], tags=["reviews"])
def get_receipts(run_id: str, db: Session = Depends(get_db)):
    """Get all evidence receipts for a review run."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    receipts = db.query(Receipt).filter(Receipt.review_run_id == run_id).all()
    return [_receipt_with_agent(r, r.agent_execution.agent_type) for r in receipts]


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@router.get("/reviews/{run_id}/stream", tags=["reviews"])
async def stream_review(run_id: str, db: Session = Depends(get_db)):
    """
    Server-Sent Events stream for a review run.
    Emits: review.started, agent.started, agent.progress, receipt.created,
           agent.completed, agent.failed, review.completed, keepalive.

    If the review is already complete, replays persisted events then closes.
    """
    # Validate the run exists
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        # If already completed, replay stored events and close immediately
        if run.status == "completed":
            events = (
                db.query(ReviewEvent)
                .filter(ReviewEvent.review_run_id == run_id)
                .order_by(ReviewEvent.created_at)
                .all()
            )
            for ev in events:
                payload = {}
                if ev.payload:
                    try:
                        payload = json.loads(ev.payload)
                    except Exception:
                        pass
                data = json.dumps({
                    "event_type": ev.event_type,
                    "review_run_id": run_id,
                    "agent_type": ev.agent_type,
                    "timestamp": ev.created_at.isoformat(),
                    **payload,
                })
                yield f"data: {data}\n\n"
            yield "data: {\"event_type\": \"stream.end\"}\n\n"
            return

        # Live: subscribe to the bus and yield events as they arrive
        try:
            async for event in event_bus.stream(run_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.warning("SSE stream error for run %s: %s", run_id, exc)
        finally:
            yield "data: {\"event_type\": \"stream.end\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Review Events (history)
# ---------------------------------------------------------------------------

@router.get("/reviews/{run_id}/events", response_model=list[ReviewEventOut], tags=["reviews"])
def get_review_events(run_id: str, db: Session = Depends(get_db)):
    """Get all persisted events for a review run."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    events = (
        db.query(ReviewEvent)
        .filter(ReviewEvent.review_run_id == run_id)
        .order_by(ReviewEvent.created_at)
        .all()
    )
    return [ReviewEventOut.model_validate(ev) for ev in events]


# ---------------------------------------------------------------------------
# Immunity Pipeline — Phase 3
# ---------------------------------------------------------------------------

@router.post(
    "/reviews/{run_id}/immunity",
    response_model=ImmunityPipelineOut,
    status_code=201,
    tags=["immunity"],
)
def start_immunity(
    run_id: str,
    body: ImmunityRequest = Body(default_factory=ImmunityRequest),
    db: Session = Depends(get_db),
):
    """
    Trigger the Bug-to-Immunity pipeline (Phase 7 canonical — V7 orchestrator).

    Pipeline:
    Reproduce → RootCause → Fix → Verify → RegressionTest → SiblingHunt
    → Documentation → Pattern → IMMUNITY_COMPLETE | BLOCKED | ESCALATED

    Uses ImmunityOrchestratorV7 with explicit state machine, hypothesis tracking,
    AdaptiveFixPlanner (12 strategies), checkpoint/rollback, and evidence gates.
    """
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")

    # Resolve repository path
    repo_path: Optional[str] = None
    if run.pull_request and run.pull_request.repository:
        repo_path = run.pull_request.repository.local_path
    if not repo_path:
        repo_path = settings.demo_repo_path

    import os
    if not os.path.isdir(repo_path):
        raise HTTPException(
            status_code=400,
            detail=f"Repository path not found: {repo_path}",
        )

    # Use canonical V7 orchestrator
    from app.immunity.orchestrator_v7 import ImmunityOrchestratorV7
    orchestrator = ImmunityOrchestratorV7()
    try:
        pipeline = orchestrator.run_pipeline(
            db=db,
            review_run_id=run_id,
            repository_path=repo_path,
            source_receipt_ids=body.source_receipt_ids,
        )
    except Exception as exc:
        logger.exception("Immunity orchestrator failed for run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=f"Immunity pipeline failed: {exc}") from exc

    return ImmunityPipelineOut.model_validate(pipeline)


@router.get(
    "/immunity/{pipeline_id}",
    response_model=ImmunityPipelineDetail,
    tags=["immunity"],
)
def get_immunity_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    """Get a full immunity pipeline with stages and sibling findings."""
    pipeline = db.query(ImmunityPipeline).filter(ImmunityPipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")

    detail = ImmunityPipelineDetail.model_validate(pipeline)
    detail.stages = [ImmunityStageOut.model_validate(s) for s in pipeline.stages]
    detail.sibling_findings = [SiblingFindingOut.model_validate(f) for f in pipeline.sibling_findings]
    return detail


@router.get(
    "/immunity/{pipeline_id}/stages",
    response_model=list[ImmunityStageOut],
    tags=["immunity"],
)
def get_immunity_stages(pipeline_id: str, db: Session = Depends(get_db)):
    """Get all stages for an immunity pipeline."""
    pipeline = db.query(ImmunityPipeline).filter(ImmunityPipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
    return [ImmunityStageOut.model_validate(s) for s in pipeline.stages]


# ---------------------------------------------------------------------------
# Pattern Library — Phase 3
# ---------------------------------------------------------------------------

@router.get("/patterns", response_model=list[PatternLibraryEntryOut], tags=["patterns"])
def list_patterns(
    affected_area: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List all pattern library entries, optionally filtered by affected_area."""
    from app.services.pattern_library import list_patterns as _list
    entries = _list(db, affected_area=affected_area, limit=limit, offset=offset)
    return [PatternLibraryEntryOut.model_validate(e) for e in entries]


@router.get("/patterns/search", response_model=list[PatternLibraryEntryOut], tags=["patterns"])
def search_patterns(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search pattern library by signature, description, or affected area."""
    from app.services.pattern_library import search_patterns as _search
    entries = _search(db, query=q, limit=limit)
    return [PatternLibraryEntryOut.model_validate(e) for e in entries]


@router.get("/patterns/{pattern_id}", response_model=PatternLibraryEntryOut, tags=["patterns"])
def get_pattern(pattern_id: str, db: Session = Depends(get_db)):
    """Get a single pattern library entry."""
    from app.services.pattern_library import get_pattern as _get
    entry = _get(db, pattern_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Pattern '{pattern_id}' not found")
    return PatternLibraryEntryOut.model_validate(entry)


# ---------------------------------------------------------------------------
# Replay Engine — Phase 4
# ---------------------------------------------------------------------------

@router.get("/replay/cases", response_model=list[ReplayCaseOut], tags=["replay"])
def list_replay_cases(
    include_invalid: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List all replay cases. Excludes invalid cases by default."""
    q = db.query(ReplayCase)
    if not include_invalid:
        q = q.filter(ReplayCase.is_valid == True)  # noqa: E712
    return [ReplayCaseOut.model_validate(c) for c in q.order_by(ReplayCase.created_at).all()]


@router.get("/replay/cases/{case_id}", response_model=ReplayCaseOut, tags=["replay"])
def get_replay_case(case_id: str, db: Session = Depends(get_db)):
    """Get a single replay case."""
    case = db.query(ReplayCase).filter(ReplayCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Replay case '{case_id}' not found")
    return ReplayCaseOut.model_validate(case)


@router.get("/replay/cases/{case_id}/results", response_model=list[ReplayResultOut], tags=["replay"])
def get_case_results(case_id: str, db: Session = Depends(get_db)):
    """Get all results for a replay case."""
    case = db.query(ReplayCase).filter(ReplayCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Replay case '{case_id}' not found")
    results = db.query(ReplayResult).filter(ReplayResult.replay_case_id == case_id).all()
    return [ReplayResultOut.model_validate(r) for r in results]


@router.post("/replay/run", response_model=ReplayRunOut, status_code=201, tags=["replay"])
def run_replay(
    body: ReplayRequest = Body(default_factory=ReplayRequest),
    db: Session = Depends(get_db),
):
    """
    Execute replay cases through the production review pipeline and score results.
    If case_ids is empty/None, runs all valid cases.
    """
    from app.replay.engine import ReplayEngine
    engine = ReplayEngine()
    try:
        replay_run = engine.run_cases(
            db=db,
            case_ids=body.case_ids or None,
            label=body.label,
        )
    except Exception as exc:
        logger.exception("Replay run failed")
        raise HTTPException(status_code=500, detail=f"Replay run failed: {exc}") from exc
    return ReplayRunOut.model_validate(replay_run)


@router.get("/replay/runs/{run_id}", response_model=ReplayRunOut, tags=["replay"])
def get_replay_run(run_id: str, db: Session = Depends(get_db)):
    """Get a replay run result."""
    run = db.query(ReplayRun).filter(ReplayRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Replay run '{run_id}' not found")
    return ReplayRunOut.model_validate(run)


@router.post("/replay/seed", response_model=list[ReplayCaseOut], status_code=201, tags=["replay"])
def seed_replay_cases(db: Session = Depends(get_db)):
    """Seed demo replay cases into the database."""
    from app.replay.demo_cases import seed_demo_cases
    cases = seed_demo_cases(db, demo_repo_path=settings.demo_repo_path)
    return [ReplayCaseOut.model_validate(c) for c in cases]


@router.post("/replay/validate", response_model=dict, tags=["replay"])
def validate_replay_cases(db: Session = Depends(get_db)):
    """Validate all replay cases and mark invalid ones."""
    from app.replay.engine import ReplayEngine
    engine = ReplayEngine()
    return engine.validate_cases(db)


# ---------------------------------------------------------------------------
# Audit Verification — Phase 4
# ---------------------------------------------------------------------------

@router.get(
    "/reviews/{run_id}/audit",
    response_model=list[AuditEventOut],
    tags=["audit"],
)
def get_audit_events(run_id: str, db: Session = Depends(get_db)):
    """Get all audit events for a review run, in chain order."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.review_run_id == run_id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )
    return [AuditEventOut.model_validate(ev) for ev in events]


@router.get(
    "/reviews/{run_id}/audit/verify",
    response_model=AuditVerificationOut,
    tags=["audit"],
)
def verify_audit_chain(run_id: str, db: Session = Depends(get_db)):
    """
    Verify the SHA-256 hash chain for a review run's audit events.
    Returns valid=True if the chain is intact, with error details if not.
    """
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    from app.audit.service import verify_chain
    result = verify_chain(db, run_id)
    return AuditVerificationOut(**result.to_dict())


# ---------------------------------------------------------------------------
# Adaptive Evidence Core — Phase 5 (New)
# ---------------------------------------------------------------------------

@router.get(
    "/reviews/{run_id}/evidence",
    response_model=list[EvidenceItemOut],
    tags=["evidence"],
)
def get_evidence(run_id: str, db: Session = Depends(get_db)):
    """Get all evidence items for a review run."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    items = db.query(EvidenceItem).filter(EvidenceItem.review_run_id == run_id).all()
    return [EvidenceItemOut.model_validate(item) for item in items]


@router.get(
    "/reviews/{run_id}/claims",
    response_model=list[ReviewClaimOut],
    tags=["evidence"],
)
def get_claims(run_id: str, db: Session = Depends(get_db)):
    """Get all review claims for a review run."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    claims = db.query(ReviewClaim).filter(ReviewClaim.review_run_id == run_id).all()
    return [ReviewClaimOut.model_validate(c) for c in claims]


@router.get(
    "/reviews/{run_id}/evidence-gaps",
    response_model=list[EvidenceGapOut],
    tags=["evidence"],
)
def get_evidence_gaps(run_id: str, db: Session = Depends(get_db)):
    """Get all evidence gaps for a review run."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    gaps = db.query(EvidenceGap).filter(EvidenceGap.review_run_id == run_id).all()
    return [EvidenceGapOut.model_validate(g) for g in gaps]


@router.get(
    "/reviews/{run_id}/strategy-trace",
    response_model=list[StrategyTraceEntryOut],
    tags=["evidence"],
)
def get_strategy_trace(run_id: str, db: Session = Depends(get_db)):
    """Get the strategy execution trace for a review run."""
    run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run '{run_id}' not found")
    entries = (
        db.query(StrategyTraceEntry)
        .filter(StrategyTraceEntry.review_run_id == run_id)
        .order_by(StrategyTraceEntry.step_number)
        .all()
    )
    return [StrategyTraceEntryOut.model_validate(e) for e in entries]
