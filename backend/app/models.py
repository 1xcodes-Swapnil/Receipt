"""
SQLAlchemy ORM models for Receipts — Phase 4 upgraded.

All models are imported by app/database.py so they are registered
with Base.metadata before create_all() is called.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class VerdictEnum(str, enum.Enum):
    SAFE = "SAFE"
    BUG_DETECTED = "BUG_DETECTED"
    ESCALATE = "ESCALATE"


class ReviewStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AgentTypeEnum(str, enum.Enum):
    TEST_RUNNER = "test_runner"
    CATCHING_TEST = "catching_test"
    DOCUMENTATION_CHECK = "documentation_check"
    HISTORY_CHECK = "history_check"


class SeverityEnum(str, enum.Enum):
    PASS = "PASS"
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskLevelEnum(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImmunityStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class StageTypeEnum(str, enum.Enum):
    REPRODUCE = "reproduce"
    ROOT_CAUSE = "root_cause"
    FIX = "fix"
    VERIFY = "verify"
    REGRESSION_TEST = "regression_test"
    SIBLING_HUNT = "sibling_hunt"
    DOCUMENTATION = "documentation"


class VerificationStatusEnum(str, enum.Enum):
    POTENTIAL_MATCH = "potential_match"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Core review models
# ---------------------------------------------------------------------------

class Repository(Base):
    __tablename__ = "repository"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repository")


class PullRequest(Base):
    __tablename__ = "pull_request"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_id: Mapped[str] = mapped_column(ForeignKey("repository.id"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="PR Review")
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    head_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")
    review_runs: Mapped[list["ReviewRun"]] = relationship(back_populates="pull_request")


class ReviewRun(Base):
    __tablename__ = "review_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    pr_id: Mapped[str] = mapped_column(ForeignKey("pull_request.id"), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(Enum(RiskLevelEnum), nullable=False, default=RiskLevelEnum.MEDIUM)
    status: Mapped[str] = mapped_column(Enum(ReviewStatusEnum), nullable=False, default=ReviewStatusEnum.PENDING)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verdict: Mapped[str | None] = mapped_column(Enum(VerdictEnum), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pull_request: Mapped["PullRequest"] = relationship(back_populates="review_runs")
    agent_executions: Mapped[list["AgentExecution"]] = relationship(back_populates="review_run")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="review_run")
    immunity_pipelines: Mapped[list["ImmunityPipeline"]] = relationship(back_populates="review_run")


class AgentExecution(Base):
    __tablename__ = "agent_execution"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_run_id: Mapped[str] = mapped_column(ForeignKey("review_run.id"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(Enum(AgentTypeEnum), nullable=False)
    status: Mapped[str] = mapped_column(Enum(AgentStatusEnum), nullable=False, default=AgentStatusEnum.PENDING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    review_run: Mapped["ReviewRun"] = relationship(back_populates="agent_executions")
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="agent_execution")


class Receipt(Base):
    """
    Evidence receipt produced by an agent.

    ``bob_evidence_ref``: nullable extension point for Bob artifact references.

    Bob artifacts (session transcripts, skill outputs, etc.) are not
    programmatically accessible from Python — there is no API to retrieve
    them by session ID.  This field is an extension point only: a human or
    an external integration can populate it with a Bob session reference
    after the fact.  The application never auto-populates this field and
    never fabricates Bob session IDs.

    Format (when populated externally):
      {"session_id": "<uuid>", "artifact_type": "...", "note": "..."}
    """
    __tablename__ = "receipt"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_run_id: Mapped[str] = mapped_column(ForeignKey("review_run.id"), nullable=False, index=True)
    agent_execution_id: Mapped[str] = mapped_column(ForeignKey("agent_execution.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    command: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    test_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_summary: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    severity: Mapped[str] = mapped_column(Enum(SeverityEnum), nullable=False, default=SeverityEnum.INFO)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Bob evidence reference — extension point only, never auto-populated.
    # See class docstring for the limitation.
    bob_evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    review_run: Mapped["ReviewRun"] = relationship()
    agent_execution: Mapped["AgentExecution"] = relationship(back_populates="receipts")


# ---------------------------------------------------------------------------
# Review Events (SSE / live progress)
# ---------------------------------------------------------------------------

class ReviewEvent(Base):
    __tablename__ = "review_event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_run_id: Mapped[str] = mapped_column(ForeignKey("review_run.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_run_id: Mapped[str | None] = mapped_column(ForeignKey("review_run.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # payload: raw (non-canonical) payload for display
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    # canonical_payload: deterministic JSON used in hash computation (sorted keys, no whitespace)
    canonical_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    integrity_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # entity: optional reference (e.g. "review_run:abc", "pipeline:xyz")
    entity_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # sequence: monotonically-increasing integer assigned under _audit_lock.
    # This is the authoritative ordering for the hash chain — do NOT use created_at
    # for chain ordering because parallel threads may commit with equal timestamps.
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    review_run: Mapped["ReviewRun | None"] = relationship(back_populates="audit_events")


# ---------------------------------------------------------------------------
# Immunity Pipeline — Phase 3
# ---------------------------------------------------------------------------

class ImmunityPipeline(Base):
    __tablename__ = "immunity_pipeline"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_run_id: Mapped[str] = mapped_column(ForeignKey("review_run.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Enum(ImmunityStatusEnum), nullable=False, default=ImmunityStatusEnum.PENDING
    )
    # JSON list of receipt IDs that triggered this pipeline
    source_receipt_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    review_run: Mapped["ReviewRun"] = relationship(back_populates="immunity_pipelines")
    stages: Mapped[list["ImmunityStage"]] = relationship(
        back_populates="pipeline", order_by="ImmunityStage.created_at"
    )
    sibling_findings: Mapped[list["SiblingFinding"]] = relationship(back_populates="pipeline")
    pattern_entries: Mapped[list["PatternLibraryEntry"]] = relationship(back_populates="pipeline")


class ImmunityStage(Base):
    __tablename__ = "immunity_stage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("immunity_pipeline.id"), nullable=False, index=True)
    stage_type: Mapped[str] = mapped_column(Enum(StageTypeEnum), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ImmunityStatusEnum), nullable=False, default=ImmunityStatusEnum.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # JSON blob of stage evidence (command, stdout, diff, etc.)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reference to a file artifact (e.g. test path, diff path)
    artifact_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pipeline: Mapped["ImmunityPipeline"] = relationship(back_populates="stages")


class SiblingFinding(Base):
    __tablename__ = "sibling_finding"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("immunity_pipeline.id"), nullable=False, index=True)
    candidate_location: Mapped[str] = mapped_column(String(512), nullable=False)
    similarity_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Always POTENTIAL_MATCH unless explicitly reproduced
    verification_status: Mapped[str] = mapped_column(
        Enum(VerificationStatusEnum), nullable=False,
        default=VerificationStatusEnum.POTENTIAL_MATCH
    )
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pipeline: Mapped["ImmunityPipeline"] = relationship(back_populates="sibling_findings")


class PatternLibraryEntry(Base):
    __tablename__ = "pattern_library_entry"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    pattern_signature: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_pipeline_id: Mapped[str | None] = mapped_column(
        ForeignKey("immunity_pipeline.id"), nullable=True, index=True
    )
    regression_test_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    affected_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # JSON metadata
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pipeline: Mapped["ImmunityPipeline | None"] = relationship(back_populates="pattern_entries")


# ---------------------------------------------------------------------------
# Replay (Phase 4 — tables exist, not yet implemented)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Replay Engine Enums — Phase 4
# ---------------------------------------------------------------------------

class ReplayCaseStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALID = "invalid"


class GroundTruthEnum(str, enum.Enum):
    """Expected outcome for a replay case."""
    BUG = "BUG"          # Known bug — system should find it
    SAFE = "SAFE"        # Known clean code — system should say SAFE
    AMBIGUOUS = "AMBIGUOUS"  # Ground truth unclear


class ReplayAgentEnum(str, enum.Enum):
    """Who produced the ground truth label."""
    HUMAN = "HUMAN"
    BOB_BUILTIN = "BOB_BUILTIN"
    RECEIPTS = "RECEIPTS"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ReplayCase(Base):
    """
    A single replay case: one repository state + expected ground truth.
    Cases are validated before execution. Only cases with reliable ground truth
    are used for scoring.

    ``included_files``: optional JSON list of file paths (relative to
    repository_path) to copy into the isolated workspace.  When set, ONLY
    those files are used — this prevents SAFE cases from seeing buggy files
    that happen to live in the same source directory.
    """
    __tablename__ = "replay_case"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Human-readable label (e.g. "calc_divide_by_zero", "buggy_stats_accumulator")
    label: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Repository path or identifier used for this case
    repository_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Optional JSON list of file paths (relative to repository_path) for isolation
    included_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ground truth
    ground_truth: Mapped[str] = mapped_column(Enum(GroundTruthEnum), nullable=False)
    ground_truth_source: Mapped[str] = mapped_column(Enum(ReplayAgentEnum), nullable=False)
    ground_truth_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Case validity — cases marked INVALID are not used for scoring
    is_valid: Mapped[bool] = mapped_column(default=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    results: Mapped[list["ReplayResult"]] = relationship(back_populates="replay_case")


class ReplayResult(Base):
    """
    Result of running the Receipts review pipeline on a replay case.
    Stores the actual verdict, evidence summary, and scoring breakdown.
    """
    __tablename__ = "replay_result"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    replay_case_id: Mapped[str] = mapped_column(ForeignKey("replay_case.id"), nullable=False, index=True)
    # Actual verdict produced by the review pipeline
    verdict: Mapped[str | None] = mapped_column(Enum(VerdictEnum), nullable=True)
    # Was the verdict correct given the ground truth?
    correct: Mapped[bool | None] = mapped_column(nullable=True)
    # Scoring fields
    caught_bug: Mapped[bool | None] = mapped_column(nullable=True)       # True when BUG ground truth + BUG_DETECTED
    false_alarm: Mapped[bool | None] = mapped_column(nullable=True)      # True when SAFE ground truth + BUG_DETECTED
    missed_bug: Mapped[bool | None] = mapped_column(nullable=True)       # True when BUG ground truth + SAFE
    escalated: Mapped[bool | None] = mapped_column(nullable=True)
    execution_failed: Mapped[bool] = mapped_column(default=False)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Review run created during replay
    review_run_id: Mapped[str | None] = mapped_column(ForeignKey("review_run.id"), nullable=True)
    # Raw output summary
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    replay_case: Mapped["ReplayCase"] = relationship(back_populates="results")
    review_run: Mapped["ReviewRun | None"] = relationship()


class ReplayRun(Base):
    """
    Aggregated result of running multiple replay cases in one batch.
    Stores aggregate scoring metrics.
    """
    __tablename__ = "replay_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(Enum(ReplayCaseStatusEnum), nullable=False,
                                        default=ReplayCaseStatusEnum.PENDING)
    # Aggregate metrics (JSON)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    cases_run: Mapped[int] = mapped_column(Integer, default=0)
    cases_failed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
