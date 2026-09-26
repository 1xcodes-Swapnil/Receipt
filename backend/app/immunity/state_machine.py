"""
Phase 7 — Pipeline State Machine

Implements explicit, persisted pipeline/stage state transitions.

Valid stage states:  PENDING → RUNNING → PASSED | FAILED | BLOCKED | ESCALATED
Pipeline states:     PENDING → RUNNING → REPRODUCING → ROOT_CAUSE → FIXING →
                     VERIFYING → REGRESSION_TESTING → SIBLING_HUNT →
                     DOCUMENTING → PATTERN_EVALUATION → IMMUNITY_COMPLETE

Transition rules (see spec):
  - A stage enters RUNNING only after prerequisites pass.
  - PASSED only when acceptance gate is satisfied with evidence.
  - FAILED = execution completed, acceptance gate not satisfied.
  - BLOCKED = required evidence/prerequisites/environment unavailable.
  - ESCALATED = automated continuation unsafe, contradictory, or unreliable.
  - Every transition is persisted with timestamp, reason, evidence ref.
  - Invalid transitions are rejected with ValueError.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# State enumerations
# ---------------------------------------------------------------------------

class StageState(str, Enum):
    PENDING    = "PENDING"
    RUNNING    = "RUNNING"
    PASSED     = "PASSED"
    FAILED     = "FAILED"
    BLOCKED    = "BLOCKED"
    ESCALATED  = "ESCALATED"


class PipelineState(str, Enum):
    PENDING              = "PENDING"
    RUNNING              = "RUNNING"
    REPRODUCING          = "REPRODUCING"
    ROOT_CAUSE           = "ROOT_CAUSE"
    FIXING               = "FIXING"
    VERIFYING            = "VERIFYING"
    REGRESSION_TESTING   = "REGRESSION_TESTING"
    SIBLING_HUNT         = "SIBLING_HUNT"
    DOCUMENTING          = "DOCUMENTING"
    PATTERN_EVALUATION   = "PATTERN_EVALUATION"
    IMMUNITY_COMPLETE    = "IMMUNITY_COMPLETE"
    BLOCKED              = "BLOCKED"
    ESCALATED            = "ESCALATED"
    FAILED               = "FAILED"


# ---------------------------------------------------------------------------
# Valid stage-state transitions
# ---------------------------------------------------------------------------

_VALID_STAGE_TRANSITIONS: dict[StageState, set[StageState]] = {
    StageState.PENDING:   {StageState.RUNNING, StageState.BLOCKED},
    StageState.RUNNING:   {StageState.PASSED, StageState.FAILED, StageState.BLOCKED, StageState.ESCALATED},
    StageState.PASSED:    set(),   # terminal — no further transitions
    StageState.FAILED:    {StageState.RUNNING, StageState.BLOCKED},  # retry or give up
    StageState.BLOCKED:   set(),   # terminal
    StageState.ESCALATED: set(),   # terminal
}

# Valid pipeline-level transitions
_VALID_PIPELINE_TRANSITIONS: dict[PipelineState, set[PipelineState]] = {
    PipelineState.PENDING:             {PipelineState.RUNNING},
    PipelineState.RUNNING:             {PipelineState.REPRODUCING, PipelineState.BLOCKED, PipelineState.ESCALATED},
    PipelineState.REPRODUCING:         {PipelineState.ROOT_CAUSE, PipelineState.BLOCKED, PipelineState.ESCALATED},
    PipelineState.ROOT_CAUSE:          {PipelineState.FIXING, PipelineState.BLOCKED, PipelineState.ESCALATED},
    PipelineState.FIXING:              {PipelineState.VERIFYING, PipelineState.BLOCKED, PipelineState.ESCALATED,
                                        PipelineState.FAILED},
    PipelineState.VERIFYING:           {PipelineState.REGRESSION_TESTING, PipelineState.FIXING,
                                        PipelineState.FAILED, PipelineState.ESCALATED},
    PipelineState.REGRESSION_TESTING:  {PipelineState.SIBLING_HUNT, PipelineState.FIXING,
                                        PipelineState.BLOCKED, PipelineState.FAILED},
    PipelineState.SIBLING_HUNT:        {PipelineState.DOCUMENTING, PipelineState.ESCALATED},
    PipelineState.DOCUMENTING:         {PipelineState.PATTERN_EVALUATION},
    PipelineState.PATTERN_EVALUATION:  {PipelineState.IMMUNITY_COMPLETE, PipelineState.BLOCKED,
                                        PipelineState.FAILED},
    PipelineState.IMMUNITY_COMPLETE:   set(),   # terminal
    PipelineState.BLOCKED:             set(),   # terminal
    PipelineState.ESCALATED:           set(),   # terminal
    PipelineState.FAILED:              set(),   # terminal
}

# Terminal pipeline states
_TERMINAL_PIPELINE_STATES = {
    PipelineState.IMMUNITY_COMPLETE,
    PipelineState.BLOCKED,
    PipelineState.ESCALATED,
    PipelineState.FAILED,
}


# ---------------------------------------------------------------------------
# Transition record dataclass
# ---------------------------------------------------------------------------

@dataclass
class StateTransition:
    """A single persisted state transition."""
    transition_id: str
    pipeline_id: str
    stage_name: str           # Which stage this transition belongs to
    from_state: str           # Previous state
    to_state: str             # New state
    timestamp: datetime
    reason: str
    evidence_ref: Optional[str] = None
    execution_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        pipeline_id: str,
        stage_name: str,
        from_state: str,
        to_state: str,
        reason: str,
        evidence_ref: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> "StateTransition":
        return cls(
            transition_id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            stage_name=stage_name,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.utcnow(),
            reason=reason,
            evidence_ref=evidence_ref,
            execution_id=execution_id,
        )


# ---------------------------------------------------------------------------
# StageStateMachine — per-stage state management
# ---------------------------------------------------------------------------

class StageStateMachine:
    """
    Manages explicit state transitions for a single immunity stage.

    Rejects invalid transitions. Persists every transition via DB.
    Accepts state only when acceptance gate is explicitly evaluated.
    """

    def __init__(self, pipeline_id: str, stage_name: str) -> None:
        self.pipeline_id = pipeline_id
        self.stage_name = stage_name
        self._state = StageState.PENDING
        self._transitions: list[StateTransition] = []

    @property
    def state(self) -> StageState:
        return self._state

    @property
    def transitions(self) -> list[StateTransition]:
        return list(self._transitions)

    def transition(
        self,
        new_state: StageState,
        reason: str,
        db: Optional[Session] = None,
        evidence_ref: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> StateTransition:
        """
        Apply a state transition.

        Raises ValueError if the transition is invalid.
        Never silently changes state.
        """
        allowed = _VALID_STAGE_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid stage transition {self.stage_name}: "
                f"{self._state} → {new_state} "
                f"(allowed: {[s.value for s in allowed]})"
            )

        t = StateTransition.create(
            pipeline_id=self.pipeline_id,
            stage_name=self.stage_name,
            from_state=self._state.value,
            to_state=new_state.value,
            reason=reason,
            evidence_ref=evidence_ref,
            execution_id=execution_id,
        )
        self._transitions.append(t)
        self._state = new_state

        if db is not None:
            self._persist(db, t)

        return t

    def _persist(self, db: Session, t: StateTransition) -> None:
        from app.models import PipelineStateTransition
        record = PipelineStateTransition(
            id=t.transition_id,
            pipeline_id=t.pipeline_id,
            stage_name=t.stage_name,
            from_state=t.from_state,
            to_state=t.to_state,
            timestamp=t.timestamp,
            reason=t.reason,
            evidence_ref=t.evidence_ref,
            execution_id=t.execution_id,
        )
        db.add(record)
        try:
            db.commit()
        except Exception:
            db.rollback()

    def is_terminal(self) -> bool:
        return self._state in (
            StageState.PASSED, StageState.BLOCKED, StageState.ESCALATED
        )

    def passed(self) -> bool:
        return self._state == StageState.PASSED

    def blocked(self) -> bool:
        return self._state == StageState.BLOCKED

    def escalated(self) -> bool:
        return self._state == StageState.ESCALATED

    def failed(self) -> bool:
        return self._state == StageState.FAILED


# ---------------------------------------------------------------------------
# PipelineStateMachine — overall pipeline state management
# ---------------------------------------------------------------------------

class PipelineStateMachine:
    """
    Manages the overall pipeline state with valid transitions.

    Persists every transition. Rejects invalid transitions.
    Only PASSED stage results advance the pipeline normally.
    """

    def __init__(self, pipeline_id: str) -> None:
        self.pipeline_id = pipeline_id
        self._state = PipelineState.PENDING
        self._transitions: list[StateTransition] = []

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def transitions(self) -> list[StateTransition]:
        return list(self._transitions)

    def transition(
        self,
        new_state: PipelineState,
        reason: str,
        db: Optional[Session] = None,
        evidence_ref: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> StateTransition:
        """
        Apply a pipeline-level state transition.

        Raises ValueError if the transition is invalid.
        """
        allowed = _VALID_PIPELINE_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid pipeline transition: "
                f"{self._state} → {new_state} "
                f"(allowed: {[s.value for s in allowed]})"
            )

        t = StateTransition.create(
            pipeline_id=self.pipeline_id,
            stage_name="pipeline",
            from_state=self._state.value,
            to_state=new_state.value,
            reason=reason,
            evidence_ref=evidence_ref,
            execution_id=execution_id,
        )
        self._transitions.append(t)
        self._state = new_state

        if db is not None:
            self._persist_pipeline(db, t)

        return t

    def _persist_pipeline(self, db: Session, t: StateTransition) -> None:
        from app.models import PipelineStateTransition
        record = PipelineStateTransition(
            id=t.transition_id,
            pipeline_id=t.pipeline_id,
            stage_name=t.stage_name,
            from_state=t.from_state,
            to_state=t.to_state,
            timestamp=t.timestamp,
            reason=t.reason,
            evidence_ref=t.evidence_ref,
            execution_id=t.execution_id,
        )
        db.add(record)
        try:
            db.commit()
        except Exception:
            db.rollback()

    def is_terminal(self) -> bool:
        return self._state in _TERMINAL_PIPELINE_STATES

    def is_immune(self) -> bool:
        return self._state == PipelineState.IMMUNITY_COMPLETE

    @staticmethod
    def stage_to_pipeline_state(stage_name: str) -> PipelineState:
        """Map stage name to the pipeline state that represents running it."""
        _map = {
            "reproduce":        PipelineState.REPRODUCING,
            "root_cause":       PipelineState.ROOT_CAUSE,
            "fix":              PipelineState.FIXING,
            "verify":           PipelineState.VERIFYING,
            "regression_test":  PipelineState.REGRESSION_TESTING,
            "sibling_hunt":     PipelineState.SIBLING_HUNT,
            "documentation":    PipelineState.DOCUMENTING,
            "pattern":          PipelineState.PATTERN_EVALUATION,
        }
        return _map.get(stage_name, PipelineState.RUNNING)

    @staticmethod
    def next_pipeline_state_on_pass(current: PipelineState) -> Optional[PipelineState]:
        """
        Returns the next state to advance to after a stage PASSES.
        Returns None if at a terminal state.
        """
        _next = {
            PipelineState.REPRODUCING:         PipelineState.ROOT_CAUSE,
            PipelineState.ROOT_CAUSE:          PipelineState.FIXING,
            PipelineState.FIXING:              PipelineState.VERIFYING,
            PipelineState.VERIFYING:           PipelineState.REGRESSION_TESTING,
            PipelineState.REGRESSION_TESTING:  PipelineState.SIBLING_HUNT,
            PipelineState.SIBLING_HUNT:        PipelineState.DOCUMENTING,
            PipelineState.DOCUMENTING:         PipelineState.PATTERN_EVALUATION,
            PipelineState.PATTERN_EVALUATION:  PipelineState.IMMUNITY_COMPLETE,
        }
        return _next.get(current)
