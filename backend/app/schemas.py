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
    created_at: datetime


# ---------------------------------------------------------------------------
# Audit Event
# ---------------------------------------------------------------------------

class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_run_id: Optional[str] = None
    event_type: str
    payload: Optional[str] = None
    integrity_hash: Optional[str] = None
    prev_hash: Optional[str] = None
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
