"""
Immunity Orchestrator — Phase 3.

Runs the Bug-to-Immunity pipeline sequentially:

    Reproduce → RootCause → Fix → Verify → RegressionTest → SiblingHunt → Documentation

Design principles:
- Sequential execution (each stage depends on the previous stage's evidence).
- Evidence flows through ImmunityContext.
- Any stage failure is recorded; the pipeline continues to collect evidence
  unless explicitly blocked.
- Never converts a failure into PASSED.
- Audit events are recorded at each stage transition.
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
)
from app.immunity.stages import (
    ImmunityContext,
    ReproduceStage,
    RootCauseStage,
    FixStage,
    VerifyStage,
    RegressionTestStage,
    SiblingHuntStage,
    DocumentationStage,
    BaseStage,
)

logger = logging.getLogger(__name__)

# Audit event constants for immunity
EVT_IMMUNITY_STARTED = "immunity_started"
EVT_IMMUNITY_STAGE_STARTED = "immunity_stage_started"
EVT_IMMUNITY_STAGE_COMPLETED = "immunity_stage_completed"
EVT_IMMUNITY_COMPLETED = "immunity_completed"
EVT_IMMUNITY_FAILED = "immunity_failed"


class ImmunityOrchestrator:
    """
    Runs the 7-stage Bug-to-Immunity pipeline for a given review run.

    The pipeline uses an isolated copy (workspace) of the repository so the
    original demo repo is never mutated.
    """

    # Ordered pipeline — stages run in this sequence
    PIPELINE: list[type[BaseStage]] = [
        ReproduceStage,
        RootCauseStage,
        FixStage,
        VerifyStage,
        RegressionTestStage,
        SiblingHuntStage,
        DocumentationStage,
    ]

    def run_pipeline(
        self,
        db: Session,
        review_run_id: str,
        repository_path: str,
        source_receipt_ids: Optional[list[str]] = None,
    ) -> ImmunityPipeline:
        """
        Create and execute the full immunity pipeline.
        Returns the completed ImmunityPipeline record.
        """
        # Create pipeline record
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

        audit.record_event(
            db,
            EVT_IMMUNITY_STARTED,
            review_run_id=review_run_id,
            payload={"pipeline_id": pipeline.id, "repository": repository_path},
        )

        # Create an isolated workspace copy
        workspace_path = self._create_workspace(repository_path)
        logger.info("immunity: workspace created at %s for pipeline %s", workspace_path, pipeline.id)

        try:
            context = ImmunityContext(
                repository_path=workspace_path,
                source_receipt={"receipt_ids": source_receipt_ids or []},
            )
            final_status = self._execute_pipeline(db, pipeline, context)
        except Exception as exc:
            logger.exception("immunity: pipeline %s raised unexpected exception", pipeline.id)
            final_status = ImmunityStatusEnum.FAILED
            pipeline.current_stage = None
            audit.record_event(
                db, EVT_IMMUNITY_FAILED,
                review_run_id=review_run_id,
                payload={"pipeline_id": pipeline.id, "error": str(exc)},
            )
        finally:
            self._cleanup_workspace(workspace_path)

        # Finalise pipeline record
        pipeline.status = final_status
        pipeline.current_stage = None
        pipeline.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(pipeline)

        audit.record_event(
            db,
            EVT_IMMUNITY_COMPLETED,
            review_run_id=review_run_id,
            payload={"pipeline_id": pipeline.id, "status": final_status},
        )
        logger.info("immunity: pipeline %s completed with status=%s", pipeline.id, final_status)
        return pipeline

    def _execute_pipeline(
        self,
        db: Session,
        pipeline: ImmunityPipeline,
        context: ImmunityContext,
    ) -> str:
        """
        Run each stage in order.
        Returns final ImmunityStatusEnum value.
        """
        overall_passed = True

        for stage_class in self.PIPELINE:
            stage = stage_class()
            stage_type = stage.stage_type

            # Update pipeline current stage
            pipeline.current_stage = stage_type
            pipeline.updated_at = datetime.utcnow()
            db.commit()

            audit.record_event(
                db, EVT_IMMUNITY_STAGE_STARTED,
                review_run_id=pipeline.review_run_id,
                payload={"pipeline_id": pipeline.id, "stage": stage_type},
            )

            logger.info("immunity: running stage %s for pipeline %s", stage_type, pipeline.id)

            try:
                result = stage.run(pipeline.id, context, db)
            except Exception as exc:
                logger.exception(
                    "immunity: stage %s raised exception for pipeline %s", stage_type, pipeline.id
                )
                # Record as failed stage — do NOT skip to next
                from app.immunity.stages import StageResult
                result = StageResult(
                    stage_type=stage_type,
                    status=ImmunityStatusEnum.FAILED,
                    error=f"Stage exception: {exc}",
                )
                stage._persist(db, pipeline.id, result)
                overall_passed = False

            audit.record_event(
                db, EVT_IMMUNITY_STAGE_COMPLETED,
                review_run_id=pipeline.review_run_id,
                payload={
                    "pipeline_id": pipeline.id,
                    "stage": stage_type,
                    "status": result.status,
                },
            )

            if result.failed():
                logger.warning(
                    "immunity: stage %s FAILED for pipeline %s — error: %s",
                    stage_type, pipeline.id, result.error
                )
                # Critical blocking stages: if these fail, stop the pipeline
                if stage_type in (StageTypeEnum.REPRODUCE, StageTypeEnum.ROOT_CAUSE):
                    overall_passed = False
                    # Cannot proceed without reproduction or root cause
                    return ImmunityStatusEnum.BLOCKED
                # Non-critical stages: record failure, continue collecting evidence
                overall_passed = False
            else:
                logger.info(
                    "immunity: stage %s PASSED for pipeline %s",
                    stage_type, pipeline.id
                )

        return ImmunityStatusEnum.PASSED if overall_passed else ImmunityStatusEnum.FAILED

    def _create_workspace(self, repository_path: str) -> str:
        """Create an isolated copy of the repository."""
        tmp = tempfile.mkdtemp(prefix="receipts_immunity_")
        dest = os.path.join(tmp, "repo")
        shutil.copytree(repository_path, dest)
        return dest

    def _cleanup_workspace(self, workspace_path: str):
        """Remove the workspace directory."""
        parent = os.path.dirname(workspace_path)
        if os.path.isdir(parent):
            shutil.rmtree(parent, ignore_errors=True)


