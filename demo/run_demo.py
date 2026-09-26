#!/usr/bin/env python
"""
Receipts — One-command deterministic demo runner.

Usage:
    cd f:\\Bobproject
    python demo/run_demo.py

What it does (in order):
  1. Health check — DB + config + demo repos
  2. Review      — run demo/repository through the full review pipeline
  3. Bug receipt — display the BUG_DETECTED evidence receipt
  4. Immunity    — run the V7 Bug-to-Immunity pipeline
  5. Replay      — seed + run all 6 replay cases (3 BUG + 3 SAFE)
  6. Audit       — verify the SHA-256 audit chain
  7. Summary     — print a structured summary with real values

All output is written to:
  demo/logs/latest/
    demo_run.log        — full stdout mirror
    review.log          — review phase details
    strategy_trace.log  — planner + strategy trace
    evidence.log        — evidence items
    verdict.log         — verdict per phase
    immunity.log        — immunity pipeline stages
    replay.log          — replay case results + metrics
    audit.log           — audit chain verification
    errors.log          — errors only
    demo_run.jsonl      — machine-readable event log

Exit code: 0 on full success, non-zero if any phase failed.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Path setup ───────────────────────────────────────────────────────────────
_DEMO_DIR = Path(__file__).parent.resolve()
_ROOT_DIR = _DEMO_DIR.parent.resolve()
_BACKEND_DIR = _ROOT_DIR / "backend"

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ── Log directory ────────────────────────────────────────────────────────────
_LOGS_DIR = _DEMO_DIR / "logs" / "latest"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ── Logging infrastructure ────────────────────────────────────────────────────

class _MultiFileHandler(logging.Handler):
    """Routes log records to the correct log file based on a category tag."""

    def __init__(self, log_dir: Path):
        super().__init__()
        self._dir = log_dir
        self._handles: dict[str, "logging.FileHandler"] = {}

    def _get_handle(self, filename: str) -> "logging.FileHandler":
        if filename not in self._handles:
            path = self._dir / filename
            fh = logging.FileHandler(path, encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)-8s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            ))
            self._handles[filename] = fh
        return self._handles[filename]

    def emit(self, record: logging.LogRecord):
        category = getattr(record, "log_file", "demo_run.log")
        self._get_handle(category).emit(record)
        # Always mirror to demo_run.log too (unless it already is that file)
        if category != "demo_run.log":
            self._get_handle("demo_run.log").emit(record)

    def close(self):
        for fh in self._handles.values():
            fh.close()
        super().close()


_multi_handler = _MultiFileHandler(_LOGS_DIR)
_multi_handler.setLevel(logging.DEBUG)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter("  %(message)s"))
_console_handler.setLevel(logging.INFO)

logging.basicConfig(handlers=[], level=logging.DEBUG)
_root_logger = logging.getLogger()
_root_logger.handlers = [_multi_handler, _console_handler]

logger = logging.getLogger("demo")


def _log(msg: str, file: str = "demo_run.log", level: int = logging.INFO, **kw):
    """Emit a structured log record to the appropriate file."""
    extra = {"log_file": file, **kw}
    logger.log(level, msg, extra=extra)


# ── JSONL event log ──────────────────────────────────────────────────────────

_jsonl_path = _LOGS_DIR / "demo_run.jsonl"
_jsonl_fh = open(_jsonl_path, "w", encoding="utf-8")


def _emit_event(event_type: str, payload: dict):
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": event_type,
        **payload,
    }
    _jsonl_fh.write(json.dumps(record, default=str) + "\n")
    _jsonl_fh.flush()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sep(char: str = "─", width: int = 64):
    print(char * width)


def _h1(title: str):
    _sep("═")
    print(f"  {title}")
    _sep("═")


def _h2(title: str):
    _sep()
    print(f"  {title}")
    _sep()


def _ok(msg: str):
    print(f"  ✓  {msg}")
    _log(f"OK: {msg}")


def _warn(msg: str):
    print(f"  ⚠  {msg}")
    _log(f"WARN: {msg}", level=logging.WARNING)


def _err(msg: str):
    print(f"  ✗  {msg}", file=sys.stderr)
    _log(f"ERROR: {msg}", file="errors.log", level=logging.ERROR)


def _get_db():
    from app.database import Base, SessionLocal, engine
    import app.models  # noqa: F401 — register all models
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


# ── Phase runners ─────────────────────────────────────────────────────────────

def run_health() -> int:
    _h1("1 / 6  HEALTH CHECK")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun
        count = db.query(ReviewRun).count()
        _ok(f"Database connected — {count} review run(s)")
        db.close()
    except Exception as exc:
        _err(f"Database error: {exc}")
        errors += 1

    try:
        from app.config import settings
        _ok(f"Config loaded — version={settings.app_version}")
    except Exception as exc:
        _err(f"Config error: {exc}")
        errors += 1

    for name, path in [
        ("demo/repository",   _ROOT_DIR / "demo" / "repository"),
        ("demo/clean_repo",   _ROOT_DIR / "demo" / "clean_repo"),
        ("demo/escalate_repo",_ROOT_DIR / "demo" / "escalate_repo"),
    ]:
        if path.is_dir():
            _ok(f"{name} found: {path}")
        else:
            _err(f"{name} missing: {path}")
            errors += 1

    _emit_event("health", {"errors": errors})
    return errors


_state: dict = {}   # shared state across phases


def run_review() -> int:
    _h1("2 / 6  DEMO REVIEW")
    errors = 0

    demo_repo = str(_ROOT_DIR / "demo" / "repository")
    try:
        db = _get_db()
        from app.orchestration.orchestrator import ReviewOrchestrator

        print(f"  Repository: {demo_repo}")
        orch = ReviewOrchestrator()
        run = orch.run_review(
            db=db,
            repo_name="demo",
            pr_number=1,
            pr_title="Demo PR Review",
            repository_path_override=demo_repo,
        )
        _state["last_run_id"] = run.id

        _h2("Result")
        print(f"  Run ID  : {run.id}")
        print(f"  Verdict : {run.verdict}")
        print(f"  Risk    : {run.risk_level}")
        print(f"  Elapsed : {run.elapsed_ms} ms")

        # Capture strategy trace
        from app.models import StrategyTraceEntry
        traces = (
            db.query(StrategyTraceEntry)
            .filter(StrategyTraceEntry.review_run_id == run.id)
            .order_by(StrategyTraceEntry.step_number)
            .all()
        )
        _log(f"Review run={run.id} verdict={run.verdict}", file="review.log")
        _log(f"Verdict: {run.verdict}", file="verdict.log")

        for te in traces:
            _log(
                f"step={te.step_number} strategy={te.strategy_name} "
                f"result={te.execution_result} reason={te.selection_reason!r}",
                file="strategy_trace.log",
            )

        # Capture evidence items
        from app.models import EvidenceItem
        items = (
            db.query(EvidenceItem)
            .filter(EvidenceItem.review_run_id == run.id)
            .all()
        )
        for ei in items:
            _log(
                f"strategy={ei.strategy_name} result={ei.result} "
                f"confidence={ei.confidence:.2f} type={ei.evidence_type}",
                file="evidence.log",
            )

        _state["review_verdict"] = run.verdict
        _state["review_confidence"] = run.confidence
        _state["review_elapsed_ms"] = run.elapsed_ms
        _state["strategy_count"] = len(traces)
        _state["evidence_count"] = len(items)

        _emit_event("review", {
            "run_id": run.id,
            "verdict": run.verdict,
            "confidence": run.confidence,
            "elapsed_ms": run.elapsed_ms,
            "strategies": len(traces),
        })

        if run.verdict == "BUG_DETECTED":
            _ok("Verdict BUG_DETECTED — evidence pipeline working correctly")
        elif run.verdict == "SAFE":
            _warn("Verdict SAFE")
        else:
            _warn(f"Verdict {run.verdict}")

        db.close()
    except Exception as exc:
        _err(f"Review failed: {exc}")
        _log(traceback.format_exc(), file="errors.log", level=logging.ERROR)
        errors += 1

    return errors


def run_bug_receipt() -> int:
    _h1("3 / 6  BUG EVIDENCE RECEIPT")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun, Receipt, VerdictEnum

        run_id = _state.get("last_run_id")
        if run_id:
            run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
        else:
            run = (
                db.query(ReviewRun)
                .filter(ReviewRun.verdict == VerdictEnum.BUG_DETECTED)
                .order_by(ReviewRun.started_at.desc())
                .first()
            )

        if not run:
            _warn("No BUG_DETECTED run found — skipping")
            db.close()
            return 0

        receipts = db.query(Receipt).filter(Receipt.review_run_id == run.id).all()
        fail_receipts = [r for r in receipts if r.result_summary == "FAIL"]
        _state["fail_receipt_count"] = len(fail_receipts)

        for r in fail_receipts[:3]:
            print(f"  [{r.severity:8s}] {r.title}")
            if r.command:
                print(f"    command: {r.command[:80]}")
            _log(
                f"receipt id={r.id} severity={r.severity} title={r.title!r}",
                file="evidence.log",
            )

        _emit_event("bug_receipt", {"count": len(fail_receipts)})
        _ok(f"{len(fail_receipts)} FAIL receipt(s) found")
        db.close()
    except Exception as exc:
        _err(f"Bug receipt failed: {exc}")
        errors += 1

    return errors


def run_immunity() -> int:
    _h1("4 / 6  IMMUNITY PIPELINE (V7)")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun, VerdictEnum
        from app.immunity import ImmunityOrchestrator  # canonical alias → V7

        run_id = _state.get("last_run_id")
        if run_id:
            run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
        else:
            run = (
                db.query(ReviewRun)
                .filter(ReviewRun.verdict == VerdictEnum.BUG_DETECTED)
                .order_by(ReviewRun.started_at.desc())
                .first()
            )

        if not run:
            _warn("No BUG_DETECTED run found — skipping immunity")
            db.close()
            return 0

        demo_repo = str(_ROOT_DIR / "demo" / "repository")
        print(f"  Running immunity pipeline on run {run.id} ...")
        orch = ImmunityOrchestrator()
        pipeline = orch.run_pipeline(
            db=db,
            review_run_id=run.id,
            repository_path=demo_repo,
        )

        _h2("Pipeline Result")
        print(f"  Pipeline ID : {pipeline.id}")
        print(f"  Status      : {pipeline.status}")

        for stage in pipeline.stages:
            elapsed_str = ""
            if stage.started_at and stage.completed_at:
                ms = int((stage.completed_at - stage.started_at).total_seconds() * 1000)
                elapsed_str = f"  ({ms} ms)"
            print(f"  {stage.stage_type:22s}  {stage.status}{elapsed_str}")
            _log(
                f"stage={stage.stage_type} status={stage.status}{elapsed_str}",
                file="immunity.log",
            )

        _state["immunity_status"] = pipeline.status
        _state["immunity_stage_count"] = len(pipeline.stages)
        _emit_event("immunity", {
            "pipeline_id": pipeline.id,
            "status": pipeline.status,
            "stages": len(pipeline.stages),
        })
        _log(f"immunity pipeline_id={pipeline.id} status={pipeline.status}", file="verdict.log")

        db.close()
    except Exception as exc:
        _err(f"Immunity failed: {exc}")
        _log(traceback.format_exc(), file="errors.log", level=logging.ERROR)
        errors += 1

    return errors


def run_replay() -> int:
    _h1("5 / 6  REPLAY ENGINE")
    errors = 0

    try:
        db = _get_db()
        from app.replay.demo_cases import seed_demo_cases
        from app.replay.engine import ReplayEngine

        cases = seed_demo_cases(db)
        print(f"  {len(cases)} case(s) seeded")

        eng = ReplayEngine()
        validation = eng.validate_cases(db)
        print(f"  Validation: {validation['valid']} valid, {validation['invalid']} invalid")

        valid_cases = [c for c in cases if c.is_valid]
        if not valid_cases:
            _err("No valid replay cases")
            return 1

        replay_run = eng.run_cases(db)

        _h2("Replay Metrics")
        m: dict = {}
        if replay_run.metrics_json:
            m = json.loads(replay_run.metrics_json)
            print(f"  Catch rate     : {m.get('catch_rate')}")
            print(f"  False alarm %  : {m.get('false_alarm_rate')}")
            print(f"  Accuracy       : {m.get('accuracy')}")
            print(f"  Caught bugs    : {m.get('caught_bugs')}")
            print(f"  Missed bugs    : {m.get('missed_bugs')}")
            print(f"  False alarms   : {m.get('false_alarms')}")

        from app.models import ReplayResult
        for case in valid_cases:
            res = (
                db.query(ReplayResult)
                .filter(ReplayResult.replay_case_id == case.id)
                .order_by(ReplayResult.created_at.desc())
                .first()
            )
            if res:
                icon = "✓" if res.correct else ("✗" if res.correct is False else "?")
                fa = " [FALSE_ALARM]" if res.false_alarm else ""
                print(f"  {icon}  {case.label:40s}  {res.verdict or '?'}{fa}")
                _log(
                    f"case={case.label} verdict={res.verdict} correct={res.correct} "
                    f"strategies={res.strategies_used!r}",
                    file="replay.log",
                )
                if res.planner_trace_json:
                    _log(f"  trace={res.planner_trace_json}", file="replay.log")

        _state["replay_accuracy"] = m.get("accuracy")
        _state["replay_catch_rate"] = m.get("catch_rate")
        _state["replay_false_alarms"] = m.get("false_alarms", 0)
        _emit_event("replay", {
            "replay_run_id": replay_run.id,
            "metrics": m,
        })

        if m.get("false_alarms", 0) == 0:
            _ok("No false alarms")
        else:
            _warn(f"{m['false_alarms']} false alarm(s)")
            errors += 1

        db.close()
    except Exception as exc:
        _err(f"Replay failed: {exc}")
        _log(traceback.format_exc(), file="errors.log", level=logging.ERROR)
        errors += 1

    return errors


def run_audit() -> int:
    _h1("6 / 6  AUDIT CHAIN VERIFICATION")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun
        from app.audit.service import verify_chain

        run_id = _state.get("last_run_id")
        if run_id:
            run = db.query(ReviewRun).filter(ReviewRun.id == run_id).first()
        else:
            run = db.query(ReviewRun).order_by(ReviewRun.started_at.desc()).first()

        if not run:
            _warn("No review runs — skipping audit")
            return 0

        result = verify_chain(db, run.id)
        _h2("Verification")
        print(f"  Valid        : {result.valid}")
        print(f"  Total events : {result.total_events}")
        print(f"  Error count  : {len(result.errors)}")

        _log(
            f"audit run_id={run.id} valid={result.valid} "
            f"events={result.total_events} errors={len(result.errors)}",
            file="audit.log",
        )

        for e in result.errors:
            _log(f"  audit_error event_id={e.get('event_id')} msg={e.get('error')}",
                 file="audit.log", level=logging.ERROR)

        _state["audit_valid"] = result.valid
        _state["audit_events"] = result.total_events
        _emit_event("audit", {
            "valid": result.valid,
            "total_events": result.total_events,
            "error_count": len(result.errors),
        })

        if result.valid:
            _ok("Audit chain intact")
        else:
            _err(f"Audit chain broken — {len(result.errors)} error(s)")
            errors += 1

        db.close()
    except Exception as exc:
        _err(f"Audit failed: {exc}")
        errors += 1

    return errors


def print_summary(total_errors: int):
    _h1("DEMO SUMMARY")
    print(f"  Verdict         : {_state.get('review_verdict', 'N/A')}")
    print(f"  Confidence      : {_state.get('review_confidence', 'N/A')}")
    print(f"  Elapsed (review): {_state.get('review_elapsed_ms', 'N/A')} ms")
    print(f"  Strategies run  : {_state.get('strategy_count', 'N/A')}")
    print(f"  Evidence items  : {_state.get('evidence_count', 'N/A')}")
    print(f"  Immunity status : {_state.get('immunity_status', 'N/A')}")
    print(f"  Replay accuracy : {_state.get('replay_accuracy', 'N/A')}")
    print(f"  Catch rate      : {_state.get('replay_catch_rate', 'N/A')}")
    print(f"  False alarms    : {_state.get('replay_false_alarms', 'N/A')}")
    print(f"  Audit valid     : {_state.get('audit_valid', 'N/A')}")
    print(f"  Audit events    : {_state.get('audit_events', 'N/A')}")
    print()
    print(f"  Log directory   : {_LOGS_DIR}")
    print()
    if total_errors == 0:
        _ok("Full demo completed successfully")
    else:
        _err(f"Demo completed with {total_errors} error(s)")
    _sep("═")

    _emit_event("summary", {
        "total_errors": total_errors,
        "state": _state,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    _h1("RECEIPTS — Evidence-First Code Review  (Phase 8 Demo)")
    print(f"  Start time : {datetime.utcnow().isoformat()}Z")
    print(f"  Log dir    : {_LOGS_DIR}")
    print()

    phases = [
        ("health",       run_health),
        ("review",       run_review),
        ("bug_receipt",  run_bug_receipt),
        ("immunity",     run_immunity),
        ("replay",       run_replay),
        ("audit",        run_audit),
    ]

    total_errors = 0
    for name, fn in phases:
        start = time.monotonic()
        try:
            rc = fn()
        except Exception as exc:
            _err(f"Phase {name!r} raised unhandled exception: {exc}")
            _log(traceback.format_exc(), file="errors.log", level=logging.ERROR)
            rc = 1
        elapsed = int((time.monotonic() - start) * 1000)
        if rc:
            _warn(f"Phase '{name}' finished with {rc} error(s) in {elapsed} ms")
            total_errors += rc
        else:
            _ok(f"Phase '{name}' succeeded in {elapsed} ms")
        print()

    print_summary(total_errors)
    _jsonl_fh.close()
    return total_errors


if __name__ == "__main__":
    sys.exit(main())
