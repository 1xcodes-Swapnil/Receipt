"""
Replay Engine — Phase 5 (workspace isolation).

Each replay case executes in an isolated temporary workspace that contains ONLY
the files belonging to that case.  This prevents a SAFE case from seeing buggy
files that live in the same demo repository.

Isolation rules:
  - If ``included_files`` is set on the case, only those files are copied.
  - If ``included_files`` is None, the entire ``repository_path`` is copied.
  - Temp workspaces are cleaned up after each case regardless of outcome.
  - Original repository_path is NEVER mutated.

Scoring:
  GOOD cases (ground_truth=BUG):
    BUG_DETECTED → caught_bug=True  (correct)
    SAFE         → missed_bug=True   (incorrect)
    ESCALATE     → escalated=True    (uncertain)

  BAD cases (ground_truth=SAFE):
    SAFE         → correct=True
    BUG_DETECTED → false_alarm=True  (incorrect)
    ESCALATE     → escalated=True    (uncertain)

NOT_AVAILABLE ground truth is never used for scoring.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    GroundTruthEnum,
    ReplayCaseStatusEnum,
    ReplayCase,
    ReplayResult,
    ReplayRun,
    VerdictEnum,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _score_result(ground_truth: str, verdict: Optional[str]) -> dict:
    """
    Compute scoring booleans for a single case result.
    Returns dict with: correct, caught_bug, false_alarm, missed_bug, escalated.
    """
    gt = ground_truth
    v = verdict

    if gt == GroundTruthEnum.BUG:
        if v == VerdictEnum.BUG_DETECTED:
            return {"correct": True, "caught_bug": True, "false_alarm": False,
                    "missed_bug": False, "escalated": False}
        elif v == VerdictEnum.SAFE:
            return {"correct": False, "caught_bug": False, "false_alarm": False,
                    "missed_bug": True, "escalated": False}
        else:  # ESCALATE or None
            return {"correct": False, "caught_bug": False, "false_alarm": False,
                    "missed_bug": False, "escalated": True}

    elif gt == GroundTruthEnum.SAFE:
        if v == VerdictEnum.SAFE:
            return {"correct": True, "caught_bug": False, "false_alarm": False,
                    "missed_bug": False, "escalated": False}
        elif v == VerdictEnum.BUG_DETECTED:
            return {"correct": False, "caught_bug": False, "false_alarm": True,
                    "missed_bug": False, "escalated": False}
        else:  # ESCALATE
            return {"correct": False, "caught_bug": False, "false_alarm": False,
                    "missed_bug": False, "escalated": True}

    # AMBIGUOUS — no scoring
    return {"correct": None, "caught_bug": None, "false_alarm": None,
            "missed_bug": None, "escalated": None}


def _compute_metrics(results: list[ReplayResult], cases: list[ReplayCase]) -> dict:
    """Compute aggregate metrics from a list of replay results."""
    valid_cases = {c.id: c for c in cases if c.is_valid}
    scored = [r for r in results if r.replay_case_id in valid_cases
              and not r.execution_failed]

    total = len(cases)
    valid = len(valid_cases)
    executed = len(results)
    failed = sum(1 for r in results if r.execution_failed)

    bug_cases = [c for c in valid_cases.values() if c.ground_truth == GroundTruthEnum.BUG]
    safe_cases = [c for c in valid_cases.values() if c.ground_truth == GroundTruthEnum.SAFE]

    bug_results = [r for r in scored
                   if valid_cases[r.replay_case_id].ground_truth == GroundTruthEnum.BUG]
    safe_results = [r for r in scored
                    if valid_cases[r.replay_case_id].ground_truth == GroundTruthEnum.SAFE]

    caught = sum(1 for r in bug_results if r.caught_bug)
    missed = sum(1 for r in bug_results if r.missed_bug)
    false_alarms = sum(1 for r in safe_results if r.false_alarm)
    escalated = sum(1 for r in scored if r.escalated)
    correct = sum(1 for r in scored if r.correct)

    catch_rate = caught / len(bug_cases) if bug_cases else None
    false_alarm_rate = false_alarms / len(safe_cases) if safe_cases else None
    accuracy = correct / len(scored) if scored else None

    return {
        "total_cases": total,
        "valid_cases": valid,
        "executed": executed,
        "failed": failed,
        "bug_cases": len(bug_cases),
        "safe_cases": len(safe_cases),
        "caught_bugs": caught,
        "missed_bugs": missed,
        "false_alarms": false_alarms,
        "escalated": escalated,
        "correct": correct,
        "catch_rate": round(catch_rate, 3) if catch_rate is not None else None,
        "false_alarm_rate": round(false_alarm_rate, 3) if false_alarm_rate is not None else None,
        "accuracy": round(accuracy, 3) if accuracy is not None else None,
    }


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------

def _create_isolated_workspace(repository_path: str, included_files: Optional[list[str]]) -> str:
    """
    Create a temporary directory containing only the files for this replay case.

    If ``included_files`` is a non-empty list, only those file names (relative
    to repository_path) are copied — nothing else.  This prevents a SAFE case
    from seeing buggy files that happen to live in the same source directory.

    If ``included_files`` is None or empty, the entire repository_path tree is
    copied (symlinks are NOT followed — ``symlinks=False``).

    Returns the path to the isolated workspace.  The caller is responsible for
    removing it with ``shutil.rmtree``.
    """
    repo_path = os.path.abspath(repository_path)
    tmp = tempfile.mkdtemp(prefix="receipts_replay_ws_")
    dest = os.path.join(tmp, "repo")
    os.makedirs(dest)

    if included_files:
        # Copy only the specified files
        for rel_path in included_files:
            # Safety: reject any path component that tries to escape
            norm = os.path.normpath(rel_path)
            if norm.startswith("..") or os.path.isabs(norm):
                logger.warning(
                    "Replay workspace: skipping unsafe included_file path: %s", rel_path
                )
                continue
            src = os.path.join(repo_path, norm)
            dst = os.path.join(dest, norm)
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            else:
                logger.warning(
                    "Replay workspace: included_file not found, skipping: %s", src
                )
    else:
        # Copy the entire tree without following symlinks
        shutil.copytree(repo_path, dest, symlinks=False, dirs_exist_ok=True)

    return tmp  # caller removes this tmpdir


def _cleanup_workspace(tmpdir: str) -> None:
    """Remove a temporary replay workspace."""
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to clean up replay workspace %s: %s", tmpdir, exc)


# ---------------------------------------------------------------------------
# Replay Engine
# ---------------------------------------------------------------------------

class ReplayEngine:
    """
    Runs replay cases through the production review pipeline and scores results.
    Uses the same ReviewOrchestrator as the normal review flow.

    Each case runs in an isolated workspace so SAFE cases are never contaminated
    by buggy files that may live in the same source repository.
    """

    def run_cases(
        self,
        db: Session,
        case_ids: Optional[list[str]] = None,
        label: Optional[str] = None,
    ) -> ReplayRun:
        """
        Execute replay cases and persist aggregate results.
        If case_ids is None, runs all valid cases.
        Returns completed ReplayRun.
        """
        # Fetch cases
        q = db.query(ReplayCase).filter(ReplayCase.is_valid == True)  # noqa: E712
        if case_ids:
            q = q.filter(ReplayCase.id.in_(case_ids))
        cases = q.all()

        replay_run = ReplayRun(
            id=str(uuid.uuid4()),
            label=label or f"replay_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            status=ReplayCaseStatusEnum.RUNNING,
            total_cases=len(cases),
            cases_run=0,
            cases_failed=0,
            started_at=datetime.utcnow(),
        )
        db.add(replay_run)
        db.commit()
        db.refresh(replay_run)

        results: list[ReplayResult] = []

        for case in cases:
            result = self._run_single_case(db, case)
            results.append(result)
            replay_run.cases_run += 1
            if result.execution_failed:
                replay_run.cases_failed += 1
            db.commit()

        # Compute and persist metrics
        metrics = _compute_metrics(results, cases)
        replay_run.metrics_json = json.dumps(metrics, default=str)
        replay_run.status = ReplayCaseStatusEnum.COMPLETED
        replay_run.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(replay_run)

        logger.info(
            "replay_run id=%s label=%s cases=%d caught=%d missed=%d false_alarms=%d",
            replay_run.id, replay_run.label,
            metrics["executed"], metrics["caught_bugs"],
            metrics["missed_bugs"], metrics["false_alarms"],
        )
        return replay_run

    def _run_single_case(self, db: Session, case: ReplayCase) -> ReplayResult:
        """
        Run the review pipeline on one case and score the result.

        Each case executes in an isolated temporary workspace created from
        case.repository_path + case.included_files.  The workspace is always
        cleaned up after the case completes, regardless of outcome.
        """
        from app.orchestration.orchestrator import ReviewOrchestrator

        start_ts = time.monotonic()
        result = ReplayResult(
            id=str(uuid.uuid4()),
            replay_case_id=case.id,
            execution_failed=False,
        )
        db.add(result)
        db.commit()

        tmpdir: Optional[str] = None
        try:
            # --- Build isolated workspace ---
            if not case.repository_path or not os.path.isdir(case.repository_path):
                raise ValueError(
                    f"repository_path missing or not a directory: {case.repository_path!r}"
                )

            # Parse included_files from JSON if stored as a string
            included_files: Optional[list[str]] = None
            if case.included_files:  # type: ignore[attr-defined]
                try:
                    included_files = json.loads(case.included_files)  # type: ignore[attr-defined]
                except Exception:
                    included_files = None

            tmpdir = _create_isolated_workspace(case.repository_path, included_files)
            workspace_repo = os.path.join(tmpdir, "repo")

            orch = ReviewOrchestrator()
            run = orch.run_review(
                db=db,
                repo_name=f"replay_{case.label}",
                pr_number=1,
                pr_title=f"Replay: {case.label}",
                repository_path_override=workspace_repo,
            )
            elapsed = int((time.monotonic() - start_ts) * 1000)
            result.review_run_id = run.id
            result.verdict = run.verdict
            result.elapsed_ms = elapsed

            # Score
            scores = _score_result(case.ground_truth, run.verdict)
            result.correct = scores["correct"]
            result.caught_bug = scores["caught_bug"]
            result.false_alarm = scores["false_alarm"]
            result.missed_bug = scores["missed_bug"]
            result.escalated = scores["escalated"]
            result.output = f"verdict={run.verdict} confidence={run.confidence}"

        except Exception as exc:
            elapsed = int((time.monotonic() - start_ts) * 1000)
            result.execution_failed = True
            result.elapsed_ms = elapsed
            result.error = str(exc)[:500]
            logger.exception("Replay case %s (%s) execution failed", case.id, case.label)

        finally:
            if tmpdir:
                _cleanup_workspace(tmpdir)

        db.commit()
        db.refresh(result)
        return result

    def validate_cases(self, db: Session) -> dict:
        """
        Validate all replay cases and mark invalid ones.
        Returns a summary of validation results.
        """
        cases = db.query(ReplayCase).all()
        valid = 0
        invalid = 0

        for case in cases:
            error = None
            if not case.repository_path:
                error = "repository_path is required"
            elif not os.path.isdir(case.repository_path):
                error = f"repository_path does not exist: {case.repository_path}"
            elif case.ground_truth not in (
                GroundTruthEnum.BUG, GroundTruthEnum.SAFE, GroundTruthEnum.AMBIGUOUS
            ):
                error = f"invalid ground_truth: {case.ground_truth}"

            if error:
                case.is_valid = False
                case.validation_error = error
                invalid += 1
            else:
                case.is_valid = True
                case.validation_error = None
                valid += 1

        db.commit()
        return {"valid": valid, "invalid": invalid, "total": len(cases)}
