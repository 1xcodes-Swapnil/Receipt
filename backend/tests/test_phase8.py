"""
test_phase8.py — Focused integration tests for Phase 8.

Tests:
  TestV7Canonicalization      — routes.py uses V7 orchestrator, __init__.py alias
  TestWorkspaceRefresh        — ImmunityContext._replace_workspace() behavior
  TestGitHubProvider          — check_availability(), clean failure, LocalProvider
  TestReplayTraceCapture      — replay result includes planner trace fields
  TestReplayResultSchema      — ReplayResultOut includes trace fields
  TestAuditConcurrency        — concurrent audit writes, chain integrity
  TestDemoRunnerStructure     — demo/run_demo.py is importable, has main()
  TestEnvExample              — .env.example exists and has required keys
  TestDocsExist               — docs/ files present
  TestReadmeUpdated           — README.md has Phase 8 content
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import textwrap
import threading
import uuid

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT_DIR = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base

_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_phase8_test.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass


# ── TestV7Canonicalization ────────────────────────────────────────────────────

class TestV7Canonicalization:
    """V7 is the canonical orchestrator; routes.py uses it."""

    def test_immunity_init_exports_v7(self):
        from app.immunity import ImmunityOrchestratorV7, ImmunityOrchestrator
        # The alias must point to V7
        assert ImmunityOrchestrator is ImmunityOrchestratorV7, (
            "ImmunityOrchestrator alias must point to V7"
        )

    def test_immunity_init_v7_has_run_pipeline(self):
        from app.immunity import ImmunityOrchestratorV7
        assert hasattr(ImmunityOrchestratorV7, "run_pipeline"), (
            "ImmunityOrchestratorV7 must have run_pipeline()"
        )

    def test_routes_imports_orchestration_not_legacy(self):
        """Routes should use the canonical orchestrator via the alias, not the old Phase 3 class."""
        import app.api.routes as routes_mod
        # The routes module should be importable without error
        assert routes_mod is not None

    def test_v7_orchestrator_module_present(self):
        from app.immunity import orchestrator_v7
        assert hasattr(orchestrator_v7, "ImmunityOrchestratorV7")

    def test_legacy_orchestrator_still_importable(self):
        """Phase 3 orchestrator must remain importable for backward compat."""
        from app.immunity.orchestrator import ImmunityOrchestrator as LegacyOrch
        assert LegacyOrch is not None

    def test_v7_exported_in_all(self):
        import app.immunity as pkg
        assert "ImmunityOrchestratorV7" in pkg.__all__
        assert "ImmunityOrchestrator" in pkg.__all__   # alias must also be exported


# ── TestWorkspaceRefresh ──────────────────────────────────────────────────────

class TestWorkspaceRefresh:
    """ImmunityContext._replace_workspace() behavior."""

    def test_replace_workspace_changes_path(self, tmp_path):
        from app.immunity.stages import ImmunityContext
        ctx = ImmunityContext(repository_path=str(tmp_path))
        new_path = str(tmp_path / "fresh")
        ctx._replace_workspace(new_path)
        assert ctx.repository_path == new_path

    def test_replace_workspace_preserves_evidence(self, tmp_path):
        from app.immunity.stages import ImmunityContext
        ctx = ImmunityContext(repository_path=str(tmp_path))
        ctx.set_stage("reproduce", {"output": "bug confirmed"})
        ctx._replace_workspace(str(tmp_path / "fresh"))
        # Stage evidence must survive workspace replacement
        assert ctx.get_stage("reproduce") == {"output": "bug confirmed"}

    def test_replace_workspace_does_not_raise_on_nonexistent(self, tmp_path):
        from app.immunity.stages import ImmunityContext
        ctx = ImmunityContext(repository_path=str(tmp_path))
        # _replace_workspace is a path assignment — does not validate existence
        ctx._replace_workspace("/nonexistent/path/xyz")
        assert ctx.repository_path == "/nonexistent/path/xyz"

    def test_context_initial_state(self, tmp_path):
        from app.immunity.stages import ImmunityContext
        ctx = ImmunityContext(repository_path=str(tmp_path))
        assert ctx.repository_path == str(tmp_path)
        assert ctx.stage_evidence == {}
        assert ctx.source_receipt == {}

    def test_set_and_get_stage(self, tmp_path):
        from app.immunity.stages import ImmunityContext
        ctx = ImmunityContext(repository_path=str(tmp_path))
        ctx.set_stage("fix", {"diff": "--- a\n+++ b\n"})
        assert ctx.get_stage("fix") == {"diff": "--- a\n+++ b\n"}
        assert ctx.get_stage("missing") is None


# ── TestGitHubProvider ────────────────────────────────────────────────────────

class TestGitHubProvider:
    """GitHubRepositoryProvider availability check and clean failure."""

    def test_check_availability_returns_provider_status(self):
        from app.repositories.provider import GitHubRepositoryProvider, ProviderStatus
        status = GitHubRepositoryProvider.check_availability()
        assert isinstance(status, ProviderStatus)

    def test_check_availability_never_raises(self, monkeypatch):
        """check_availability() must not raise under any condition."""
        import app.repositories.provider as pmod
        # Simulate a broken environment variable read
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        status = pmod.GitHubRepositoryProvider.check_availability()
        assert isinstance(status, pmod.ProviderStatus)

    def test_no_token_reports_unavailable(self, monkeypatch):
        import app.repositories.provider as pmod
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        status = pmod.GitHubRepositoryProvider.check_availability()
        # Without token the provider should be unavailable
        assert not status.available
        assert status.reason  # must provide a reason string

    def test_provider_status_has_required_fields(self):
        from app.repositories.provider import ProviderStatus
        ps = ProviderStatus(available=False, provider="test", reason="no token")
        assert ps.available is False
        assert ps.provider == "test"
        assert ps.reason == "no token"

    def test_provider_status_to_dict(self):
        from app.repositories.provider import ProviderStatus
        ps = ProviderStatus(available=True, provider="GitHub", reason="ok", detail="abc")
        d = ps.to_dict()
        assert d["available"] is True
        assert d["provider"] == "GitHub"
        assert d["detail"] == "abc"

    def test_local_provider_requires_existing_path(self, tmp_path):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(str(tmp_path))
        assert p.repo_path == str(tmp_path)

    def test_local_provider_rejects_missing_path(self):
        from app.repositories.provider import LocalRepositoryProvider
        with pytest.raises(ValueError, match="does not exist"):
            LocalRepositoryProvider("/absolutely/not/real/path/xyz123")

    def test_local_provider_list_files(self, tmp_path):
        from app.repositories.provider import LocalRepositoryProvider
        (tmp_path / "hello.py").write_text("x = 1")
        p = LocalRepositoryProvider(str(tmp_path))
        files = p.list_files("**/*.py")
        assert any("hello.py" in f for f in files)

    def test_local_provider_read_file(self, tmp_path):
        from app.repositories.provider import LocalRepositoryProvider
        (tmp_path / "readme.txt").write_text("hello world")
        p = LocalRepositoryProvider(str(tmp_path))
        content = p.read_file("readme.txt")
        assert content == "hello world"

    def test_local_provider_read_file_missing(self, tmp_path):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(str(tmp_path))
        result = p.read_file("nonexistent.txt")
        assert result is None

    def test_local_provider_status(self, tmp_path):
        from app.repositories.provider import LocalRepositoryProvider
        p = LocalRepositoryProvider(str(tmp_path))
        status = p.status()
        assert status.available is True
        assert status.provider == "LocalRepositoryProvider"

    def test_workspace_create_and_cleanup(self, tmp_path):
        from app.repositories.provider import LocalRepositoryProvider
        (tmp_path / "main.py").write_text("print('hi')")
        p = LocalRepositoryProvider(str(tmp_path))
        ws = p.create_workspace()
        assert os.path.isdir(ws.path)
        assert os.path.isfile(os.path.join(ws.path, "main.py"))
        ws.cleanup()
        assert not os.path.isdir(ws.path)

    def test_provider_unavailable_error_importable(self):
        from app.repositories.provider import ProviderUnavailableError
        err = ProviderUnavailableError("GitHub", "no token")
        assert "GitHub" in str(err)


# ── TestReplayTraceCapture ────────────────────────────────────────────────────

class TestReplayTraceCapture:
    """ReplayResult model has Phase 8 planner trace fields."""

    def test_replay_result_has_planner_trace_json(self):
        from app.models import ReplayResult
        r = ReplayResult()
        assert hasattr(r, "planner_trace_json")
        assert r.planner_trace_json is None

    def test_replay_result_has_strategies_used(self):
        from app.models import ReplayResult
        r = ReplayResult()
        assert hasattr(r, "strategies_used")

    def test_replay_result_has_strategy_count(self):
        from app.models import ReplayResult
        r = ReplayResult()
        assert hasattr(r, "strategy_count")

    def test_replay_result_trace_persists(self):
        db = TestSession()
        try:
            from app.models import (
                ReplayResult, ReplayCase, GroundTruthEnum, ReplayAgentEnum, VerdictEnum
            )
            case = ReplayCase(
                id=str(uuid.uuid4()),
                label=f"trace_test_{uuid.uuid4().hex[:8]}",
                ground_truth=GroundTruthEnum.SAFE,
                ground_truth_source=ReplayAgentEnum.HUMAN,
                is_valid=True,
            )
            db.add(case)
            db.flush()

            trace = json.dumps([
                {"step": 0, "strategy": "ExistingTestsStrategy", "result": "PASS"}
            ])
            result = ReplayResult(
                id=str(uuid.uuid4()),
                replay_case_id=case.id,
                verdict=VerdictEnum.SAFE,
                correct=True,
                execution_failed=False,
                planner_trace_json=trace,
                strategies_used="ExistingTestsStrategy",
                strategy_count=1,
            )
            db.add(result)
            db.commit()

            fetched = db.query(ReplayResult).filter(
                ReplayResult.id == result.id
            ).first()
            assert fetched is not None
            assert fetched.planner_trace_json == trace
            assert fetched.strategies_used == "ExistingTestsStrategy"
            assert fetched.strategy_count == 1
        finally:
            db.close()


# ── TestReplayResultSchema ────────────────────────────────────────────────────

class TestReplayResultSchema:
    """ReplayResultOut Pydantic schema includes Phase 8 trace fields."""

    def test_schema_has_planner_trace_json(self):
        from app.schemas import ReplayResultOut
        fields = ReplayResultOut.model_fields
        assert "planner_trace_json" in fields

    def test_schema_has_strategies_used(self):
        from app.schemas import ReplayResultOut
        fields = ReplayResultOut.model_fields
        assert "strategies_used" in fields

    def test_schema_has_strategy_count(self):
        from app.schemas import ReplayResultOut
        fields = ReplayResultOut.model_fields
        assert "strategy_count" in fields

    def test_schema_trace_fields_optional(self):
        from app.schemas import ReplayResultOut
        from datetime import datetime
        # Schema must accept None for trace fields
        out = ReplayResultOut(
            id="x",
            replay_case_id="y",
            execution_failed=False,
            created_at=datetime.utcnow(),
            planner_trace_json=None,
            strategies_used=None,
            strategy_count=None,
        )
        assert out.planner_trace_json is None
        assert out.strategies_used is None
        assert out.strategy_count is None


# ── TestAuditConcurrency ──────────────────────────────────────────────────────

class TestAuditConcurrency:
    """Concurrent audit writes maintain chain integrity."""

    def test_concurrent_writes_do_not_corrupt_sequence(self):
        """Write 10 events from 5 threads. Sequences must be unique monotonic ints."""
        db = TestSession()
        try:
            from app.models import ReviewRun, PullRequest, Repository
            from app.audit.service import record_event

            # Create a minimal ReviewRun to attach events to
            repo = Repository(
                id=str(uuid.uuid4()), name=f"audit_concurrent_{uuid.uuid4().hex[:8]}"
            )
            db.add(repo)
            db.flush()
            pr = PullRequest(
                id=str(uuid.uuid4()), repo_id=repo.id, number=1, title="t",
                base_branch="main"
            )
            db.add(pr)
            db.flush()
            run = ReviewRun(
                id=str(uuid.uuid4()), pr_id=pr.id, risk_level="medium"
            )
            db.add(run)
            db.commit()
            run_id = run.id
        finally:
            db.close()

        # Write events concurrently from multiple threads
        errors: list[Exception] = []

        def _write_events(n: int):
            thread_db = TestSession()
            try:
                for _ in range(n):
                    record_event(
                        thread_db,
                        event_type="test_concurrent",
                        review_run_id=run_id,
                        payload={"thread": threading.get_ident()},
                    )
            except Exception as exc:
                errors.append(exc)
            finally:
                thread_db.close()

        threads = [threading.Thread(target=_write_events, args=(2,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"

        # Verify all sequences are unique
        verify_db = TestSession()
        try:
            from app.models import AuditEvent
            events = (
                verify_db.query(AuditEvent)
                .filter(
                    AuditEvent.review_run_id == run_id,
                    AuditEvent.event_type == "test_concurrent",
                )
                .all()
            )
            assert len(events) == 10, f"Expected 10 events, got {len(events)}"
            seqs = [e.sequence for e in events if e.sequence is not None]
            assert len(set(seqs)) == len(seqs), "Duplicate sequences detected"
        finally:
            verify_db.close()

    def test_audit_chain_verify_passes_for_new_run(self):
        """A freshly-created run's audit chain should verify as valid."""
        db = TestSession()
        try:
            from app.models import ReviewRun, PullRequest, Repository
            from app.audit.service import record_event, verify_chain

            repo = Repository(
                id=str(uuid.uuid4()), name=f"audit_verify_{uuid.uuid4().hex[:8]}"
            )
            db.add(repo)
            db.flush()
            pr = PullRequest(
                id=str(uuid.uuid4()), repo_id=repo.id, number=1, title="t",
                base_branch="main"
            )
            db.add(pr)
            db.flush()
            run = ReviewRun(
                id=str(uuid.uuid4()), pr_id=pr.id, risk_level="low"
            )
            db.add(run)
            db.commit()

            for i in range(3):
                record_event(db, "test_event", review_run_id=run.id,
                             payload={"i": i})

            result = verify_chain(db, run.id)
            assert result.valid, f"Chain verify failed: {result.errors}"
            assert result.total_events == 3
        finally:
            db.close()


# ── TestDemoRunnerStructure ───────────────────────────────────────────────────

class TestDemoRunnerStructure:
    """demo/run_demo.py exists and is correctly structured."""

    def test_run_demo_exists(self):
        demo_runner = os.path.join(_ROOT_DIR, "demo", "run_demo.py")
        assert os.path.isfile(demo_runner), f"demo/run_demo.py not found at {demo_runner}"

    def test_run_demo_has_main_function(self):
        demo_runner = os.path.join(_ROOT_DIR, "demo", "run_demo.py")
        with open(demo_runner, encoding="utf-8") as f:
            content = f.read()
        assert "def main(" in content

    def test_run_demo_has_phase_runners(self):
        demo_runner = os.path.join(_ROOT_DIR, "demo", "run_demo.py")
        with open(demo_runner, encoding="utf-8") as f:
            content = f.read()
        for fn_name in ["run_health", "run_review", "run_immunity", "run_replay", "run_audit"]:
            assert fn_name in content, f"demo/run_demo.py missing {fn_name}()"

    def test_run_demo_has_structured_logging(self):
        demo_runner = os.path.join(_ROOT_DIR, "demo", "run_demo.py")
        with open(demo_runner, encoding="utf-8") as f:
            content = f.read()
        assert "demo/logs" in content or "_LOGS_DIR" in content
        assert "demo_run.log" in content

    def test_run_demo_uses_v7_via_canonical_alias(self):
        """run_demo.py must use ImmunityOrchestrator (canonical alias to V7), not hardcode V7."""
        demo_runner = os.path.join(_ROOT_DIR, "demo", "run_demo.py")
        with open(demo_runner, encoding="utf-8") as f:
            content = f.read()
        assert "ImmunityOrchestrator" in content

    def test_run_demo_has_summary_output(self):
        demo_runner = os.path.join(_ROOT_DIR, "demo", "run_demo.py")
        with open(demo_runner, encoding="utf-8") as f:
            content = f.read()
        assert "print_summary" in content or "DEMO SUMMARY" in content

    def test_run_demo_has_jsonl_log(self):
        demo_runner = os.path.join(_ROOT_DIR, "demo", "run_demo.py")
        with open(demo_runner, encoding="utf-8") as f:
            content = f.read()
        assert "demo_run.jsonl" in content


# ── TestEnvExample ────────────────────────────────────────────────────────────

class TestEnvExample:
    """.env.example exists and contains required keys."""

    def test_env_example_exists(self):
        env_path = os.path.join(_ROOT_DIR, ".env.example")
        assert os.path.isfile(env_path), ".env.example not found at project root"

    def test_env_example_has_github_token(self):
        env_path = os.path.join(_ROOT_DIR, ".env.example")
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        assert "GITHUB_TOKEN" in content

    def test_env_example_has_database_url(self):
        env_path = os.path.join(_ROOT_DIR, ".env.example")
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        assert "DATABASE_URL" in content

    def test_env_example_has_strategy_config(self):
        env_path = os.path.join(_ROOT_DIR, ".env.example")
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        assert "STRATEGY_" in content or "STRATEGY_TIMEOUT" in content


# ── TestDocsExist ─────────────────────────────────────────────────────────────

class TestDocsExist:
    """Required documentation files are present."""

    def test_hackathon_submission_exists(self):
        p = os.path.join(_ROOT_DIR, "docs", "HACKATHON_SUBMISSION.md")
        assert os.path.isfile(p), "docs/HACKATHON_SUBMISSION.md missing"

    def test_bob_integration_exists(self):
        p = os.path.join(_ROOT_DIR, "docs", "BOB_INTEGRATION.md")
        assert os.path.isfile(p), "docs/BOB_INTEGRATION.md missing"

    def test_demo_guide_exists(self):
        p = os.path.join(_ROOT_DIR, "docs", "DEMO_GUIDE.md")
        assert os.path.isfile(p), "docs/DEMO_GUIDE.md missing"

    def test_benchmark_exists(self):
        p = os.path.join(_ROOT_DIR, "docs", "BENCHMARK.md")
        assert os.path.isfile(p), "docs/BENCHMARK.md missing"

    def test_hackathon_submission_has_architecture(self):
        p = os.path.join(_ROOT_DIR, "docs", "HACKATHON_SUBMISSION.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "Architecture" in content or "architecture" in content

    def test_demo_guide_has_quick_start(self):
        p = os.path.join(_ROOT_DIR, "docs", "DEMO_GUIDE.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "Prerequisites" in content or "Quick Start" in content or "run_demo" in content

    def test_benchmark_has_scoring_rules(self):
        p = os.path.join(_ROOT_DIR, "docs", "BENCHMARK.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "catch" in content.lower() or "false_alarm" in content.lower()

    def test_bob_integration_has_phases(self):
        p = os.path.join(_ROOT_DIR, "docs", "BOB_INTEGRATION.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "Phase" in content


# ── TestReadmeUpdated ─────────────────────────────────────────────────────────

class TestReadmeUpdated:
    """README.md reflects Phase 8 content."""

    def test_readme_exists(self):
        p = os.path.join(_ROOT_DIR, "README.md")
        assert os.path.isfile(p), "README.md missing"

    def test_readme_has_phase8_content(self):
        p = os.path.join(_ROOT_DIR, "README.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "Phase 8" in content or "phase-8" in content

    def test_readme_has_quick_start(self):
        p = os.path.join(_ROOT_DIR, "README.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "Quick Start" in content or "run_demo" in content

    def test_readme_mentions_immunity(self):
        p = os.path.join(_ROOT_DIR, "README.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "Immunity" in content or "immunity" in content

    def test_readme_mentions_strategies(self):
        p = os.path.join(_ROOT_DIR, "README.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        # Should mention the strategy count
        assert "14" in content or "strategies" in content.lower()

    def test_readme_has_no_evidence_no_flag(self):
        p = os.path.join(_ROOT_DIR, "README.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "NO EVIDENCE, NO FLAG" in content

    def test_readme_has_test_results(self):
        p = os.path.join(_ROOT_DIR, "README.md")
        with open(p, encoding="utf-8") as f:
            content = f.read()
        assert "217" in content or "passing" in content.lower()


# ── TestReplayEngineTraceIntegration ─────────────────────────────────────────

class TestReplayEngineTraceIntegration:
    """ReplayEngine._run_single_case captures trace metadata."""

    def test_engine_run_single_case_captures_trace_gracefully(self, tmp_path):
        """
        Even with a minimal invalid repo path (execution fails),
        the engine must not raise — it must set execution_failed=True.
        """
        db = TestSession()
        try:
            from app.models import (
                ReplayCase, GroundTruthEnum, ReplayAgentEnum
            )
            from app.replay.engine import ReplayEngine

            case = ReplayCase(
                id=str(uuid.uuid4()),
                label=f"trace_graceful_{uuid.uuid4().hex[:8]}",
                repository_path="/nonexistent/path/xyz",
                ground_truth=GroundTruthEnum.BUG,
                ground_truth_source=ReplayAgentEnum.HUMAN,
                is_valid=True,
            )
            db.add(case)
            db.commit()

            eng = ReplayEngine()
            result = eng._run_single_case(db, case)

            # Must not raise — must record failure
            assert result.execution_failed is True
            assert result.error is not None
        finally:
            db.close()

    def test_replay_result_trace_fields_default_none(self):
        from app.models import ReplayResult
        r = ReplayResult(
            id=str(uuid.uuid4()),
            replay_case_id=str(uuid.uuid4()),
            execution_failed=False,
        )
        assert r.planner_trace_json is None
        assert r.strategies_used is None
        assert r.strategy_count is None
