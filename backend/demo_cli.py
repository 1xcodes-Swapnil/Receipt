#!/usr/bin/env python
"""
Receipts Demo CLI — Phase 5.

Demonstrates the full backend pipeline by importing and running app modules
directly (no HTTP server required).

Commands:
  health    — verify DB connection and model availability
  review    — run demo review against demo/repository, show agents + verdict
  bug       — show the BUG_DETECTED receipt from the last review
  immunity  — run the immunity pipeline on the last BUG_DETECTED review
  replay    — seed + run replay cases, show metrics
  audit     — verify audit chain for the last review run
  all       — run all commands in order

Usage:
  cd f:\\Bobproject\\backend
  .venv\\Scripts\\python.exe demo_cli.py health
  .venv\\Scripts\\python.exe demo_cli.py all

Exit code: 0 on success, non-zero on failure.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap

# ------------------------------------------------------------------
# Ensure backend/app is on sys.path so imports work when invoked
# directly (not via pytest).
# ------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sep(char: str = "─", width: int = 60) -> None:
    print(char * width)


def _h1(title: str) -> None:
    _sep("═")
    print(f"  {title}")
    _sep("═")


def _h2(title: str) -> None:
    _sep()
    print(f"  {title}")
    _sep()


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠  {msg}")


def _err(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)


def _get_db():
    """Open a database session using the app's SessionLocal."""
    from app.database import Base, SessionLocal, engine
    import app.models  # noqa: F401 — register all models
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------

def cmd_health() -> int:
    """Check DB connection and model availability."""
    _h1("HEALTH CHECK")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun
        count = db.query(ReviewRun).count()
        _ok(f"Database connected — {count} review run(s) in DB")
        db.close()
    except Exception as exc:
        _err(f"Database error: {exc}")
        errors += 1

    try:
        from app.config import settings
        _ok(f"Config loaded — demo_repo_path={settings.demo_repo_path}")
    except Exception as exc:
        _err(f"Config error: {exc}")
        errors += 1

    try:
        demo_repo = os.path.abspath(
            os.path.join(_BACKEND_DIR, "..", "demo", "repository")
        )
        assert os.path.isdir(demo_repo), f"not a directory: {demo_repo}"
        _ok(f"demo/repository found: {demo_repo}")
    except Exception as exc:
        _err(f"Demo repo missing: {exc}")
        errors += 1

    try:
        clean_repo = os.path.abspath(
            os.path.join(_BACKEND_DIR, "..", "demo", "clean_repo")
        )
        assert os.path.isdir(clean_repo), f"not a directory: {clean_repo}"
        _ok(f"demo/clean_repo found: {clean_repo}")
    except Exception as exc:
        _err(f"Clean repo missing: {exc}")
        errors += 1

    try:
        escalate_repo = os.path.abspath(
            os.path.join(_BACKEND_DIR, "..", "demo", "escalate_repo")
        )
        assert os.path.isdir(escalate_repo), f"not a directory: {escalate_repo}"
        _ok(f"demo/escalate_repo found: {escalate_repo}")
    except Exception as exc:
        _err(f"Escalate repo missing: {exc}")
        errors += 1

    if errors:
        _err(f"{errors} health check(s) failed")
    else:
        _ok("All health checks passed")
    return errors


_last_run_id: list[str] = []   # module-level state shared between commands


def cmd_review() -> int:
    """Run demo review against demo/repository, display agents + verdict."""
    _h1("DEMO REVIEW")
    errors = 0

    demo_repo = os.path.abspath(
        os.path.join(_BACKEND_DIR, "..", "demo", "repository")
    )

    try:
        db = _get_db()
        from app.orchestration.orchestrator import ReviewOrchestrator

        print(f"  Repository: {demo_repo}")
        print("  Running review (4 agents in parallel)...")
        orch = ReviewOrchestrator()
        run = orch.run_review(
            db=db,
            repo_name="demo",
            pr_number=1,
            pr_title="Demo PR Review",
            repository_path_override=demo_repo,
        )

        _last_run_id.clear()
        _last_run_id.append(run.id)

        _h2("Result")
        print(f"  Run ID   : {run.id}")
        print(f"  Verdict  : {run.verdict}")
        print(f"  Risk     : {run.risk_level}")
        print(f"  Elapsed  : {run.elapsed_ms} ms")
        print()

        _h2("Agent Executions")
        for ae in run.agent_executions:
            print(f"  {ae.agent_type:30s}  status={ae.status}")

        _h2("Receipts")
        for ae in run.agent_executions:
            for r in ae.receipts:
                print(f"  [{r.severity:8s}] {r.title}")

        if run.verdict == "BUG_DETECTED":
            _ok("Verdict: BUG_DETECTED — pipeline working correctly")
        elif run.verdict == "SAFE":
            _warn("Verdict: SAFE — no bugs detected")
        else:
            _warn(f"Verdict: {run.verdict}")

        db.close()
    except Exception as exc:
        _err(f"Review failed: {exc}")
        import traceback; traceback.print_exc()
        errors += 1

    return errors


def cmd_bug() -> int:
    """Show BUG_DETECTED receipt from last review (or run a new one)."""
    _h1("BUG RECEIPT")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun, Receipt, VerdictEnum

        if _last_run_id:
            run = db.query(ReviewRun).filter(ReviewRun.id == _last_run_id[0]).first()
        else:
            run = (
                db.query(ReviewRun)
                .filter(ReviewRun.verdict == VerdictEnum.BUG_DETECTED)
                .order_by(ReviewRun.started_at.desc())
                .first()
            )

        if not run:
            _warn("No BUG_DETECTED review found — run 'review' first")
            db.close()
            return 1

        receipts = (
            db.query(Receipt)
            .filter(Receipt.review_run_id == run.id)
            .all()
        )
        bug_receipts = [r for r in receipts if r.result_summary == "FAIL"]

        if not bug_receipts:
            _warn(f"No FAIL receipts found in run {run.id}")
            db.close()
            return 1

        for r in bug_receipts:
            _h2(f"Receipt: {r.title}")
            print(f"  ID       : {r.id}")
            print(f"  Agent    : {r.agent_execution.agent_type}")
            print(f"  Result   : {r.result_summary}")
            print(f"  Severity : {r.severity}")
            print(f"  Command  : {r.command}")
            print(f"  Bob ref  : {r.bob_evidence_ref or '(not set — extension point only)'}")
            print()
            if r.raw_output:
                output_preview = r.raw_output[:500]
                print("  Output (first 500 chars):")
                for line in output_preview.splitlines():
                    print(f"    {line}")

        db.close()
    except Exception as exc:
        _err(f"Bug command failed: {exc}")
        errors += 1

    return errors


def cmd_immunity() -> int:
    """Run the immunity pipeline on the last BUG_DETECTED review."""
    _h1("IMMUNITY PIPELINE")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun, VerdictEnum
        from app.immunity import ImmunityOrchestrator
        from app.config import settings

        if _last_run_id:
            run = db.query(ReviewRun).filter(ReviewRun.id == _last_run_id[0]).first()
        else:
            run = (
                db.query(ReviewRun)
                .filter(ReviewRun.verdict == VerdictEnum.BUG_DETECTED)
                .order_by(ReviewRun.started_at.desc())
                .first()
            )

        if not run:
            _warn("No BUG_DETECTED review found — run 'review' first")
            db.close()
            return 1

        demo_repo = os.path.abspath(
            os.path.join(_BACKEND_DIR, "..", "demo", "repository")
        )

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
        print()

        _h2("Stages (7)")
        for stage in pipeline.stages:
            elapsed = ""
            if stage.started_at and stage.completed_at:
                ms = int((stage.completed_at - stage.started_at).total_seconds() * 1000)
                elapsed = f"  ({ms} ms)"
            print(f"  {stage.stage_type:20s}  {stage.status}{elapsed}")

        _h2("Sibling Findings")
        if pipeline.sibling_findings:
            for sf in pipeline.sibling_findings:
                print(f"  {sf.candidate_location}  confidence={sf.confidence:.2f}  "
                      f"status={sf.verification_status}")
        else:
            print("  (none)")

        db.close()
    except Exception as exc:
        _err(f"Immunity failed: {exc}")
        import traceback; traceback.print_exc()
        errors += 1

    return errors


def cmd_replay() -> int:
    """Seed replay cases, run them, display metrics."""
    _h1("REPLAY ENGINE")
    errors = 0

    try:
        db = _get_db()
        from app.replay.demo_cases import seed_demo_cases
        from app.replay.engine import ReplayEngine

        print("  Seeding demo cases...")
        cases = seed_demo_cases(db)
        print(f"  {len(cases)} case(s) seeded")

        # Validate
        engine = ReplayEngine()
        validation = engine.validate_cases(db)
        print(f"  Validation: {validation['valid']} valid, {validation['invalid']} invalid")

        valid_cases = [c for c in cases if c.is_valid]
        if not valid_cases:
            _err("No valid replay cases — cannot run replay")
            db.close()
            return 1

        print(f"\n  Running {len(valid_cases)} valid case(s)...")
        replay_run = engine.run_cases(db)

        _h2("Replay Results")
        print(f"  Run ID     : {replay_run.id}")
        print(f"  Status     : {replay_run.status}")
        print(f"  Cases run  : {replay_run.cases_run}")
        print(f"  Cases failed: {replay_run.cases_failed}")
        print()

        if replay_run.metrics_json:
            m = json.loads(replay_run.metrics_json)
            _h2("Metrics")
            print(f"  Bug cases     : {m['bug_cases']}")
            print(f"  Safe cases    : {m['safe_cases']}")
            print(f"  Caught bugs   : {m['caught_bugs']}")
            print(f"  Missed bugs   : {m['missed_bugs']}")
            print(f"  False alarms  : {m['false_alarms']}")
            print(f"  Escalated     : {m['escalated']}")
            print(f"  Catch rate    : {m['catch_rate']}")
            print(f"  False alarm % : {m['false_alarm_rate']}")
            print(f"  Accuracy      : {m['accuracy']}")

        # Show per-case result
        _h2("Per-case Results")
        from app.models import ReplayResult, ReplayCase
        for case in valid_cases:
            results = (
                db.query(ReplayResult)
                .filter(ReplayResult.replay_case_id == case.id)
                .order_by(ReplayResult.created_at.desc())
                .first()
            )
            if results:
                verdict = results.verdict or "?"
                correct = "✓" if results.correct else ("✗" if results.correct is False else "?")
                fa = " FALSE_ALARM" if results.false_alarm else ""
                print(f"  {correct}  {case.label:40s}  verdict={verdict}{fa}")
            else:
                print(f"  ?  {case.label:40s}  (no result)")

        false_alarms = m.get('false_alarms', 0) if replay_run.metrics_json else 0
        if false_alarms == 0:
            _ok("No false alarms detected")
        else:
            _warn(f"{false_alarms} false alarm(s) — SAFE cases incorrectly flagged")
            errors += 1

        db.close()
    except Exception as exc:
        _err(f"Replay failed: {exc}")
        import traceback; traceback.print_exc()
        errors += 1

    return errors


def cmd_audit() -> int:
    """Verify audit chain for the last review run."""
    _h1("AUDIT CHAIN VERIFICATION")
    errors = 0

    try:
        db = _get_db()
        from app.models import ReviewRun
        from app.audit.service import verify_chain

        if _last_run_id:
            run = db.query(ReviewRun).filter(ReviewRun.id == _last_run_id[0]).first()
        else:
            run = (
                db.query(ReviewRun)
                .order_by(ReviewRun.started_at.desc())
                .first()
            )

        if not run:
            _warn("No review runs in database — run 'review' first")
            db.close()
            return 1

        print(f"  Verifying audit chain for run {run.id} ...")
        result = verify_chain(db, run.id)

        _h2("Verification Result")
        print(f"  Valid        : {result.valid}")
        print(f"  Total events : {result.total_events}")
        print(f"  Errors       : {len(result.errors)}")

        if result.errors:
            for e in result.errors:
                _err(f"  Event {e['event_id']}: {e['error']}")
            errors += 1
        else:
            _ok("Audit chain is intact — all hashes verified")

        db.close()
    except Exception as exc:
        _err(f"Audit verification failed: {exc}")
        errors += 1

    return errors


def cmd_all() -> int:
    """Run all commands in order."""
    _h1("RECEIPTS FULL DEMO")
    total_errors = 0

    commands = [
        ("health", cmd_health),
        ("review", cmd_review),
        ("bug", cmd_bug),
        ("immunity", cmd_immunity),
        ("replay", cmd_replay),
        ("audit", cmd_audit),
    ]

    for name, fn in commands:
        print()
        rc = fn()
        if rc:
            _warn(f"Command '{name}' completed with {rc} error(s)")
            total_errors += rc
        else:
            _ok(f"Command '{name}' succeeded")

    _sep("═")
    if total_errors:
        _err(f"Demo completed with {total_errors} total error(s)")
    else:
        _ok("Full demo completed successfully")
    _sep("═")
    return total_errors


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

_COMMANDS = {
    "health": cmd_health,
    "review": cmd_review,
    "bug": cmd_bug,
    "immunity": cmd_immunity,
    "replay": cmd_replay,
    "audit": cmd_audit,
    "all": cmd_all,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        print("Usage: python demo_cli.py <command>")
        print()
        print("Commands:")
        for name, fn in _COMMANDS.items():
            doc = (fn.__doc__ or "").strip().splitlines()[0]
            print(f"  {name:12s}  {doc}")
        sys.exit(1)

    cmd = sys.argv[1]
    rc = _COMMANDS[cmd]()
    sys.exit(rc)


if __name__ == "__main__":
    main()
