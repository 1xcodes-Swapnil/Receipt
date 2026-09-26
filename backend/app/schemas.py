"""
Pydantic schemas for request/response serialisation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Pull Request
# ---------------------------------------------------------------------------

class PullRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repo_id: str
    number: int
    title: str
    author: Optional[str] = None
    base_branch: str
    head_branch: Optional[str] = None
    commit_sha: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Review Run
# ---------------------------------------------------------------------------

class ReviewRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pr_id: str
    risk_level: str
    status: str
    confidence: Optional[float] = None
    verdict: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_ms: Optional[int] = None


class ReviewRunDetail(ReviewRunOut):
    """Review run with nested relationships."""
    pull_request: Optional[PullRequestOut] = None
    agent_executions: list[AgentExecutionOut] = []
    receipts: list[ReceiptOut] = []


# ---------------------------------------------------------------------------
# Agent Execution
# ---------------------------------------------------------------------------

class AgentExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    agent_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------

class BobEvidenceRef(BaseModel):
    """
    Extension point for a Bob artifact reference on a Receipt.

    Bob artifacts (session transcripts, skill outputs) are not programmatically
    accessible from Python — no API exists to retrieve them by session ID.
    This schema is an extension point only.  The application NEVER auto-populates
    bob_evidence_ref and NEVER fabricates Bob session IDs.

    A human or external integration may supply this value after the fact.
    """
    session_id: Optional[str] = None
    artifact_type: Optional[str] = None
    note: Optional[str] = None


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    agent_execution_id: str
    agent: Optional[str] = None   # denormalized from agent_execution.agent_type
    title: str
    command: Optional[str] = None
    test_ref: Optional[str] = None
    result_summary: str
    raw_output: Optional[str] = None
    file_ref: Optional[str] = None
    severity: str
    confidence: float
    # Bob evidence reference — extension point only, never auto-populated.
    # See BobEvidenceRef docstring for limitation details.
    bob_evidence_ref: Optional[str] = None
    created_at: datetime


class ReceiptTicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    agent_execution_id: str
    agent: Optional[str] = None
    title: str
    command: Optional[str] = None
    test_ref: Optional[str] = None
    result_summary: str
    raw_output: Optional[str] = None
    file_ref: Optional[str] = None
    severity: str
    confidence: float
    bob_evidence_ref: Optional[str] = None
    created_at: Optional[datetime] = None

    # Related review run details
    repo: Optional[str] = None
    pr_number: Optional[int] = None
    verdict: Optional[str] = None
    risk_level: Optional[str] = None
    phase_source: Optional[str] = "Phase 3 — Bug Evidence Receipt"


# ---------------------------------------------------------------------------
# Audit Event (Phase 1 base — upgraded schema is in Phase 4 section below)
# ---------------------------------------------------------------------------

class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: Optional[str] = None
    event_type: str
    payload: Optional[str] = None
    canonical_payload: Optional[str] = None
    integrity_hash: Optional[str] = None
    prev_hash: Optional[str] = None
    entity_ref: Optional[str] = None
    sequence: Optional[int] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    """Optional body for POST /repos/{repo}/prs/{number}/review."""
    pr_title: str = "PR Review"
    author: Optional[str] = None
    base_branch: str = "main"
    head_branch: Optional[str] = None
    commit_sha: Optional[str] = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthOut(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# Review Event
# ---------------------------------------------------------------------------

class ReviewEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    event_type: str
    agent_type: Optional[str] = None
    payload: Optional[str] = None
    created_at: datetime


# Resolve forward references
ReviewRunDetail.model_rebuild()


# ---------------------------------------------------------------------------
# Immunity Pipeline — Phase 3
# ---------------------------------------------------------------------------

class ImmunityStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pipeline_id: str
    stage_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    evidence: Optional[str] = None   # JSON string
    error: Optional[str] = None
    artifact_ref: Optional[str] = None
    created_at: datetime


class SiblingFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pipeline_id: str
    candidate_location: str
    similarity_reason: Optional[str] = None
    confidence: float
    verification_status: str
    evidence: Optional[str] = None
    created_at: datetime


class ImmunityPipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    status: str
    source_receipt_ids: Optional[str] = None
    current_stage: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ImmunityPipelineDetail(ImmunityPipelineOut):
    """Pipeline with nested stages and siblings."""
    stages: list[ImmunityStageOut] = []
    sibling_findings: list[SiblingFindingOut] = []


# ---------------------------------------------------------------------------
# Pattern Library — Phase 3
# ---------------------------------------------------------------------------

class PatternLibraryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pattern_signature: str
    description: str
    source_pipeline_id: Optional[str] = None
    regression_test_ref: Optional[str] = None
    affected_area: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Immunity request body
# ---------------------------------------------------------------------------

class ImmunityRequest(BaseModel):
    """Body for POST /reviews/{run_id}/immunity."""
    source_receipt_ids: Optional[list[str]] = None


# Resolve forward references for detail schemas
ImmunityPipelineDetail.model_rebuild()


# ---------------------------------------------------------------------------
# Replay Engine — Phase 4
# ---------------------------------------------------------------------------

class ReplayCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    description: Optional[str] = None
    repository_path: Optional[str] = None
    included_files: Optional[str] = None   # JSON list of relative file paths for isolation
    ground_truth: str
    ground_truth_source: str
    ground_truth_notes: Optional[str] = None
    is_valid: bool
    validation_error: Optional[str] = None
    created_at: datetime


class ReplayResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    replay_case_id: str
    verdict: Optional[str] = None
    correct: Optional[bool] = None
    caught_bug: Optional[bool] = None
    false_alarm: Optional[bool] = None
    missed_bug: Optional[bool] = None
    escalated: Optional[bool] = None
    execution_failed: bool
    elapsed_ms: Optional[int] = None
    review_run_id: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    # Phase 8: planner/strategy trace metadata
    planner_trace_json: Optional[str] = None
    strategies_used: Optional[str] = None
    strategy_count: Optional[int] = None
    created_at: datetime


class ReplayRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: Optional[str] = None
    status: str
    metrics_json: Optional[str] = None
    total_cases: int
    cases_run: int
    cases_failed: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class ReplayRequest(BaseModel):
    """Body for POST /replay/run."""
    case_ids: Optional[list[str]] = None
    label: Optional[str] = None


# ---------------------------------------------------------------------------
# Audit verification — Phase 4
# ---------------------------------------------------------------------------

class AuditVerificationOut(BaseModel):
    valid: bool
    total_events: int
    error_count: int
    errors: list[dict]


# ---------------------------------------------------------------------------
# Adaptive Evidence Core — Phase 5 (New)
# ---------------------------------------------------------------------------

class EvidenceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    claim_id: Optional[str] = None
    strategy_name: str
    evidence_type: Optional[str] = None
    result: str
    confidence: float
    command: Optional[str] = None
    raw_output: Optional[str] = None
    file_ref: Optional[str] = None
    line_ref: Optional[int] = None
    is_independent: bool = True
    depends_on_evidence_id: Optional[str] = None
    created_at: datetime


class ReviewClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    claim_type: str
    claim_text: str
    status: str
    verdict_contribution: str
    created_at: datetime


class EvidenceGapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    claim_id: Optional[str] = None
    gap_type: str
    description: str
    suggested_strategy: Optional[str] = None
    resolved: bool
    created_at: datetime


class StrategyTraceEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: str
    step_number: int
    claim_id: Optional[str] = None
    strategy_name: str
    selection_reason: Optional[str] = None
    prerequisites_met: bool
    execution_result: Optional[str] = None
    evidence_item_id: Optional[str] = None
    remaining_gap: Optional[str] = None
    next_decision: Optional[str] = None
    stopping_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
