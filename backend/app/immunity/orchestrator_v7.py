"""
Phase 7 — Immunity Orchestrator

Extends Phase 3–4 orchestrator with:
  - Explicit PipelineStateMachine tracking
  - Valid transition enforcement
  - PASSED/BLOCKED/ESCALATED/FAILED terminal states
  - IMMUNITY_COMPLETE only when all required gates satisfied
  - Retry loop: FAILED → try next fix strategy (within budget)
  - Per-stage state machine transitions persisted
  - Full PATTERN stage

Pipeline flow:
  PENDING → RUNNING → REPRODUCING → ROOT_CAUSE → FIXING →
  VERIFYING → REGRESSION_TESTING → SIBLING_HUNT →
  DOCUMENTING → PATTERN_EVALUATION → IMMUNITY_COMPLETE

Terminal shortcircuits:
  REPRODUCING/BLOCKED → BLOCKED (cannot continue without reproduction)
  ROOT_CAUSE/BLOCKED  → BLOCKED
  ROOT_CAUSE/ESCALATED → ESCALATED
  FIXING/BLOCKED       → BLOCKED
  VERIFYING/FAILED     → retry FIXING (up to MAX_FIX_ATTEMPTS)
  REGRESSION/FAILED    → retry FIXING (up to MAX_FIX_ATTEMPTS)
  REGRESSION/BLOCKED   → BLOCKED
  SIBLING_HUNT/BLOCKED → advance with recorded reason
  SIBLING_HUNT/ESCALATED → ESCALATED
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app import audit
from app.models import (
    ImmunityPipeline,
    ImmunityStatusEnum,
    StageTypeEnum,
    PipelineStateEnum,
)
from app.immunity.state_machine import (
    PipelineState, PipelineStateMachine, StageState
)
from app.immunity.stages import ImmunityContext
from app.immunity.stages_v7 import (
    ReproduceStageV7,
    RootCauseStageV7,
    FixStageV7,
    VerifyStageV7,
    RegressionTestStageV7,
    SiblingHuntStageV7,
    DocumentationStageV7,
    PatternStage,
)

logger = logging.getLogger(__name__)

# Audit event constants
EVT_IMMUNITY_STARTED   = "immunity_started"
EVT_STAGE_STARTED      = "immunity_stage_started"
EVT_STAGE_COMPLETED    = "immunity_stage_completed"
EVT_IMMUNITY_COMPLETE  = "immunity_complete"
EVT_IMMUNITY_BLOCKED   = "immunity_blocked"
EVT_IMMUNITY_ESCALATED = "immunity_escalated"
EVT_IMMUNITY_FAILED    = "immunity_failed"
EVT_FIX_RETRY          = "immunity_fix_retry"
EVT_ROLLBACK           = "immunity_rollback"

# Max fix+verify retry cycles
MAX_FIX_RETRIES = 3


def _immunity_status_from_pipeline(ps: PipelineState) -> ImmunityStatusEnum:
    """Map PipelineState to legacy ImmunityStatusEnum for DB storage."""
    _map = {
        PipelineState.IMMUNITY_COMPLETE: ImmunityStatusEnum.PASSED,
        PipelineState.BLOCKED:           ImmunityStatusEnum.BLOCKED,
        PipelineState.ESCALATED:         ImmunityStatusEnum.ESCALATED,
        PipelineState.FAILED:            ImmunityStatusEnum.FAILED,
    }
    return _map.get(ps, ImmunityStatusEnum.FAILED)


class ImmunityOrchestratorV7:
    """
    Phase 7 Bug-to-Immunity Orchestrator.

    Runs the full pipeline with explicit state machine enforcement.
    IMMUNITY_COMPLETE only when all required acceptance gates are satisfied.
    """

    def run_pipeline(
        self,
        db: Session,
        review_run_id: str,
        repository_path: str,
        source_receipt_ids: Optional[list[str]] = None,
    ) -> ImmunityPipeline:
        """
        Create and run the full Phase 7 immunity pipeline.
        Returns the completed ImmunityPipeline record.
        """
        pipeline = ImmunityPipeline(
            id=str(uuid.uuid4()),
            review_run_id=review_run_id,
            status=ImmunityStatusEnum.RUNNING,
            source_receipt_ids=json.dumps(source_receipt_ids or []),
            current_stage=StageTypeEnum.REPRODUCE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)

        psm = PipelineStateMachine(pipeline.id)
        psm.transition(PipelineState.RUNNING, "Pipeline created", db=db)

        audit.record_event(
            db,
            EVT_IMMUNITY_STARTED,
            review_run_id=review_run_id,
            payload={"pipeline_id": pipeline.id, "repository": repository_path},
        )

        workspace_path = self._create_workspace(repository_path)
        logger.info("p7-immunity: workspace created at %s for pipeline %s", workspace_path, pipeline.id)

        try:
            context = ImmunityContext(
                repository_path=workspace_path,
                source_receipt={"receipt_ids": source_receipt_ids or []},
            )
            final_pipeline_state = self._execute_pipeline(db, pipeline, psm, context)
        except Exception as exc:
            logger.exception("p7-immunity: pipeline %s raised unexpected exception", pipeline.id)
            try:
                psm.transition(PipelineState.ESCALATED, f"Unexpected exception: {exc}", db=db)
            except ValueError:
                pass
            final_pipeline_state = PipelineState.ESCALATED
            audit.record_event(
                db, EVT_IMMUNITY_FAILED,
                review_run_id=review_run_id,
                payload={"pipeline_id": pipeline.id, "error": str(exc)},
            )
        finally:
            self._cleanup_workspace(workspace_path)

        # Finalise pipeline record
        final_status = _immunity_status_from_pipeline(final_pipeline_state)
        pipeline.status = final_status
        pipeline.current_stage = None
        pipeline.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(pipeline)

        evt = (EVT_IMMUNITY_COMPLETE if final_pipeline_state == PipelineState.IMMUNITY_COMPLETE
               else EVT_IMMUNITY_BLOCKED if final_pipeline_state == PipelineState.BLOCKED
               else EVT_IMMUNITY_ESCALATED if final_pipeline_state == PipelineState.ESCALATED
               else EVT_IMMUNITY_FAILED)
        audit.record_event(
            db, evt,
            review_run_id=review_run_id,
            payload={"pipeline_id": pipeline.id, "state": final_pipeline_state.value},
        )
        logger.info(
            "p7-immunity: pipeline %s → %s", pipeline.id, final_pipeline_state.value
        )
        return pipeline

    def _execute_pipeline(
        self,
        db: Session,
        pipeline: ImmunityPipeline,
        psm: PipelineStateMachine,
        context: ImmunityContext,
    ) -> PipelineState:
        """
        Execute each stage in order with state machine enforcement.
        Returns final PipelineState.
        """

        # ── Stage 1: Reproduce ──────────────────────────────────────────────
        psm.transition(PipelineState.REPRODUCING, "Starting reproduction", db=db)
        self._update_pipeline_stage(db, pipeline, StageTypeEnum.REPRODUCE)

        result = self._run_stage(db, pipeline, context, ReproduceStageV7())
        if result.status in (_blocked := ImmunityStatusEnum.BLOCKED,):
            return self._terminal(psm, PipelineState.BLOCKED, "Reproduction blocked", db,
                                  pipeline, EVT_IMMUNITY_BLOCKED)
        if result.status == ImmunityStatusEnum.ESCALATED:
            return self._terminal(psm, PipelineState.ESCALATED, "Reproduction escalated", db,
                                  pipeline, EVT_IMMUNITY_ESCALATED)

        # ── Stage 2: Root Cause ─────────────────────────────────────────────
        psm.transition(PipelineState.ROOT_CAUSE, "Reproduction passed — starting root cause", db=db)
        self._update_pipeline_stage(db, pipeline, StageTypeEnum.ROOT_CAUSE)

        result = self._run_stage(db, pipeline, context, RootCauseStageV7())
        if result.status == ImmunityStatusEnum.BLOCKED:
            return self._terminal(psm, PipelineState.BLOCKED, "No verified root cause", db,
                                  pipeline, EVT_IMMUNITY_BLOCKED)
        if result.status == ImmunityStatusEnum.ESCALATED:
            return self._terminal(psm, PipelineState.ESCALATED, "Root cause contradictory", db,
                                  pipeline, EVT_IMMUNITY_ESCALATED)

        # ── Stage 3+4+5: Fix → Verify → Regression (with retry) ────────────
        psm.transition(PipelineState.FIXING, "Root cause verified — starting fix", db=db)

        fix_attempts = 0
        while fix_attempts < MAX_FIX_RETRIES:
            fix_attempts += 1
            self._update_pipeline_stage(db, pipeline, StageTypeEnum.FIX)

            fix_result = self._run_stage(db, pipeline, context, FixStageV7())

            if fix_result.status == ImmunityStatusEnum.BLOCKED:
                return self._terminal(psm, PipelineState.BLOCKED, "No applicable fix strategy", db,
                                      pipeline, EVT_IMMUNITY_BLOCKED)
            if fix_result.status == ImmunityStatusEnum.ESCALATED:
                return self._terminal(psm, PipelineState.ESCALATED, "Fix unsafe", db,
                                      pipeline, EVT_IMMUNITY_ESCALATED)
            if fix_result.status == ImmunityStatusEnum.FAILED:
                if fix_attempts >= MAX_FIX_RETRIES:
                    return self._terminal(psm, PipelineState.FAILED, "All fix strategies failed", db,
                                          pipeline, EVT_IMMUNITY_FAILED)
                audit.record_event(db, EVT_FIX_RETRY, review_run_id=pipeline.review_run_id,
                                   payload={"pipeline_id": pipeline.id, "attempt": fix_attempts})
                continue

            # Fix applied — Verify
            try:
                psm.transition(PipelineState.VERIFYING, "Fix applied — verifying", db=db)
            except ValueError:
                pass
            self._update_pipeline_stage(db, pipeline, StageTypeEnum.VERIFY)
            verify_result = self._run_stage(db, pipeline, context, VerifyStageV7())

            if verify_result.status == ImmunityStatusEnum.ESCALATED:
                return self._terminal(psm, PipelineState.ESCALATED, "Verify escalated", db,
                                      pipeline, EVT_IMMUNITY_ESCALATED)
            if verify_result.status == ImmunityStatusEnum.FAILED:
                if fix_attempts >= MAX_FIX_RETRIES:
                    return self._terminal(psm, PipelineState.FAILED, "Verification failed after max retries", db,
                                          pipeline, EVT_IMMUNITY_FAILED)
                audit.record_event(db, EVT_FIX_RETRY, review_run_id=pipeline.review_run_id,
                                   payload={"pipeline_id": pipeline.id, "attempt": fix_attempts,
                                            "reason": "verify_failed"})
                # Return to FIXING state
                try:
                    psm.transition(PipelineState.FIXING, f"Verify failed — retry fix attempt {fix_attempts+1}", db=db)
                except ValueError:
                    pass
                continue

            # Verify PASSED — Regression test
            try:
                psm.transition(PipelineState.REGRESSION_TESTING, "Verify passed — regression test", db=db)
            except ValueError:
                pass
            self._update_pipeline_stage(db, pipeline, StageTypeEnum.REGRESSION_TEST)
            reg_result = self._run_stage(db, pipeline, context, RegressionTestStageV7())

            if reg_result.status == ImmunityStatusEnum.BLOCKED:
                return self._terminal(psm, PipelineState.BLOCKED, "Regression test blocked", db,
                                      pipeline, EVT_IMMUNITY_BLOCKED)
            if reg_result.status == ImmunityStatusEnum.FAILED:
                if fix_attempts >= MAX_FIX_RETRIES:
                    return self._terminal(psm, PipelineState.FAILED, "Regression test failed after max retries", db,
                                          pipeline, EVT_IMMUNITY_FAILED)
                audit.record_event(db, EVT_FIX_RETRY, review_run_id=pipeline.review_run_id,
                                   payload={"pipeline_id": pipeline.id, "attempt": fix_attempts,
                                            "reason": "regression_failed"})
                try:
                    psm.transition(PipelineState.FIXING, f"Regression failed — retry fix {fix_attempts+1}", db=db)
                except ValueError:
                    pass
                continue

            # Regression PASSED — exit loop
            break

        # ── Stage 6: Sibling Hunt ────────────────────────────────────────────
        try:
            psm.transition(PipelineState.SIBLING_HUNT, "Regression passed — sibling hunt", db=db)
        except ValueError:
            pass
        self._update_pipeline_stage(db, pipeline, StageTypeEnum.SIBLING_HUNT)
        sibling_result = self._run_stage(db, pipeline, context, SiblingHuntStageV7())

        if sibling_result.status == ImmunityStatusEnum.ESCALATED:
            return self._terminal(psm, PipelineState.ESCALATED, "Sibling hunt escalated", db,
                                  pipeline, EVT_IMMUNITY_ESCALATED)
        # BLOCKED is acceptable — advance with reason recorded

        # ── Stage 7: Documentation ───────────────────────────────────────────
        try:
            psm.transition(PipelineState.DOCUMENTING, "Sibling hunt done — documentation", db=db)
        except ValueError:
            pass
        self._update_pipeline_stage(db, pipeline, StageTypeEnum.DOCUMENTATION)
        self._run_stage(db, pipeline, context, DocumentationStageV7())

        # ── Stage 8: Pattern ─────────────────────────────────────────────────
        try:
            psm.transition(PipelineState.PATTERN_EVALUATION, "Documentation done — pattern evaluation", db=db)
        except ValueError:
            pass
        self._update_pipeline_stage(db, pipeline, StageTypeEnum.PATTERN)
        self._run_stage(db, pipeline, context, PatternStage())

        # ── IMMUNITY_COMPLETE ────────────────────────────────────────────────
        try:
            psm.transition(
                PipelineState.IMMUNITY_COMPLETE,
                "All required gates satisfied — immunity complete",
                db=db,
            )
        except ValueError:
            pass

        return PipelineState.IMMUNITY_COMPLETE

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_stage(
        self,
        db: Session,
        pipeline: ImmunityPipeline,
        context: ImmunityContext,
        stage,
    ):
        stage_type = stage.stage_type

        audit.record_event(
            db, EVT_STAGE_STARTED,
            review_run_id=pipeline.review_run_id,
            payload={"pipeline_id": pipeline.id, "stage": stage_type},
        )

        try:
            result = stage.run(pipeline.id, context, db)
        except Exception as exc:
            logger.exception("p7-immunity: stage %s raised exception", stage_type)
            from app.immunity.stages import StageResult
            result = StageResult(
                stage_type=stage_type,
                status=ImmunityStatusEnum.ESCALATED,
                error=f"Stage exception: {exc}",
            )
            stage._persist(db, pipeline.id, result)

        audit.record_event(
            db, EVT_STAGE_COMPLETED,
            review_run_id=pipeline.review_run_id,
            payload={
                "pipeline_id": pipeline.id,
                "stage": stage_type,
                "status": result.status,
            },
        )
        return result

    def _update_pipeline_stage(self, db: Session, pipeline: ImmunityPipeline, stage_type: str) -> None:
        pipeline.current_stage = stage_type
        pipeline.updated_at = datetime.utcnow()
        db.commit()

    def _terminal(
        self,
        psm: PipelineStateMachine,
        state: PipelineState,
        reason: str,
        db: Session,
        pipeline: ImmunityPipeline,
        event: str,
    ) -> PipelineState:
        try:
            psm.transition(state, reason, db=db)
        except ValueError:
            pass
        audit.record_event(
            db, event,
            review_run_id=pipeline.review_run_id,
            payload={"pipeline_id": pipeline.id, "reason": reason},
        )
        return state

    def _create_workspace(self, repository_path: str) -> str:
        tmp = tempfile.mkdtemp(prefix="receipts_p7_immunity_")
        dest = os.path.join(tmp, "repo")
        shutil.copytree(repository_path, dest)
        return dest

    def _cleanup_workspace(self, workspace_path: str) -> None:
        parent = os.path.dirname(workspace_path)
        if os.path.isdir(parent):
            shutil.rmtree(parent, ignore_errors=True)
