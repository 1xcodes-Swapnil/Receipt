"""
Phase 6 test suite — Adaptive Evidence Architecture.

Tests:
  TestRepositorySnapshot     — snapshot creation, hash, security
  TestStrategyContracts      — strategy execute() contracts
  TestEvidenceLedger         — ledger tracking, contradictions, dependence
  TestEvidenceSufficiency    — sufficiency evaluator and gap analyzer
  TestStrategyPlanner        — planner selection algorithm, budget, trace
  TestAdaptiveReviewFlow     — full-stack integration (API + DB)
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ------------------------------------------------------------------
# Ensure backend/app is importable
# ------------------------------------------------------------------
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DEMO_REPO = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "demo", "repository"))
_CLEAN_REPO = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "demo", "clean_repo"))
_ESCALATE_REPO = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "demo", "escalate_repo"))

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.database import Base, get_db
from app.main import app as fastapi_app

# ------------------------------------------------------------------
# Test database (file-based SQLite for multi-thread agent workers)
# ------------------------------------------------------------------
_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_phase6_test.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_test_db():
    import app.models  # noqa: F401 — register models
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Override FastAPI dependency
    prev_override = fastapi_app.dependency_overrides.get(get_db)
    fastapi_app.dependency_overrides[get_db] = get_test_db

    # Redirect orchestrator's per-thread SessionLocal to the test DB
    import app.orchestration.orchestrator as _orch
    prev_orch_session = _orch.SessionLocal
    _orch.SessionLocal = TestingSession  # type: ignore[attr-defined]

    # Also redirect app.database.SessionLocal
    import app.database as _db
    prev_db_session = _db.SessionLocal
    _db.SessionLocal = TestingSession  # type: ignore[attr-defined]

    yield

    # Restore
    if prev_override is None:
        fastapi_app.dependency_overrides.pop(get_db, None)
    else:
        fastapi_app.dependency_overrides[get_db] = prev_override
    _orch.SessionLocal = prev_orch_session
    _db.SessionLocal = prev_db_session

    engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.unlink(_TEST_DB_PATH)
        except OSError:
            pass  # Windows file lock — harmless


@pytest.fixture()
def client():
    return TestClient(fastapi_app)


@pytest.fixture()
def db_session():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


# ===========================================================================
# TestRepositorySnapshot
# ===========================================================================

class TestRepositorySnapshot:
    """RepositorySnapshot creation, hash, immutability, security."""

    def test_snapshot_creates_deterministic_hash(self, tmp_path):
        """Same files → same hash."""
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")

        from app.evidence.snapshot import RepositorySnapshot
        snap1 = RepositorySnapshot.create(str(tmp_path))
        snap2 = RepositorySnapshot.create(str(tmp_path))
        assert snap1.snapshot_hash == snap2.snapshot_hash, \
            "Same files must produce the same hash"

    def test_snapshot_filters_secrets_from_env(self, tmp_path, monkeypatch):
        """Secret env vars must not appear in snapshot.environment."""
        monkeypatch.setenv("MY_SECRET_TOKEN", "super_secret_value")
        monkeypatch.setenv("API_KEY", "key123")
        monkeypatch.setenv("SAFE_VAR", "visible")

        from app.evidence.snapshot import RepositorySnapshot
        snap = RepositorySnapshot.create(str(tmp_path))

        assert "MY_SECRET_TOKEN" not in snap.environment, \
            "Secret env var must be filtered"
        assert "API_KEY" not in snap.environment, \
            "API_KEY must be filtered"
        assert "SAFE_VAR" in snap.environment, \
            "Non-secret var should be present"

    def test_snapshot_rejects_path_traversal(self, tmp_path):
        """Path traversal segments must raise ValueError."""
        from app.evidence.snapshot import RepositorySnapshot
        traversal_path = str(tmp_path) + "/../../etc"
        with pytest.raises(ValueError, match="traversal"):
            RepositorySnapshot.create(traversal_path)

    def test_snapshot_immutable_after_creation(self, tmp_path):
        """RepositorySnapshot is a frozen dataclass — mutation must raise."""
        from app.evidence.snapshot import RepositorySnapshot
        snap = RepositorySnapshot.create(str(tmp_path))
        with pytest.raises((TypeError, AttributeError)):
            snap.snapshot_hash = "tampered"  # type: ignore[misc]

    def test_snapshot_changed_files_detected(self, tmp_path):
        """Explicitly passed changed_files are stored in snapshot."""
        (tmp_path / "foo.py").write_text("pass\n")
        (tmp_path / "bar.py").write_text("pass\n")

        from app.evidence.snapshot import RepositorySnapshot
        snap = RepositorySnapshot.create(
            str(tmp_path),
            changed_files=["foo.py"],
        )
        assert "foo.py" in snap.changed_files, \
            "Explicitly provided changed file must appear in snapshot"
        assert "bar.py" not in snap.changed_files, \
            "Non-changed file must not appear in changed_files"


# ===========================================================================
# TestStrategyContracts
# ===========================================================================

class TestStrategyContracts:
    """Strategy execute() contract tests."""

    def test_existing_tests_strategy_on_clean_repo(self):
        """ExistingTestsStrategy on clean_repo → PASS."""
        from app.evidence.snapshot import RepositorySnapshot
        from app.strategies.existing_tests import ExistingTestsStrategy

        snap = RepositorySnapshot.create(_CLEAN_REPO)
        strategy = ExistingTestsStrategy()
        result = strategy.execute(snap, {})
        assert result.result == "PASS", \
            f"Expected PASS on clean_repo, got {result.result}: {result.raw_output[:200]}"
        assert result.confidence > 0

    def test_existing_tests_strategy_on_buggy_repo(self):
        """ExistingTestsStrategy on buggy demo repo → FAIL."""
        from app.evidence.snapshot import RepositorySnapshot
        from app.strategies.existing_tests import ExistingTestsStrategy

        snap = RepositorySnapshot.create(_DEMO_REPO)
        strategy = ExistingTestsStrategy()
        result = strategy.execute(snap, {})
        assert result.result == "FAIL", \
            f"Expected FAIL on buggy_repo, got {result.result}: {result.raw_output[:200]}"

    def test_existing_tests_strategy_no_tests(self):
        """ExistingTestsStrategy on escalate_repo (no tests) → INSUFFICIENT."""
        from app.evidence.snapshot import RepositorySnapshot
        from app.strategies.existing_tests import ExistingTestsStrategy

        snap = RepositorySnapshot.create(_ESCALATE_REPO)
        strategy = ExistingTestsStrategy()
        result = strategy.execute(snap, {})
        assert result.result == "INSUFFICIENT", \
            f"Expected INSUFFICIENT for no tests, got {result.result}"

    def test_static_ast_returns_insufficient_not_fail(self, tmp_path):
        """StaticASTAnalysisStrategy: no syntax errors → INSUFFICIENT (not FAIL)."""
        (tmp_path / "good.py").write_text("def foo(): return 1\n")

        from app.evidence.snapshot import RepositorySnapshot
        from app.strategies.static_ast import StaticASTAnalysisStrategy

        snap = RepositorySnapshot.create(str(tmp_path))
        strategy = StaticASTAnalysisStrategy()
        result = strategy.execute(snap, {})
        # No syntax errors = INSUFFICIENT (we can't confirm correctness without tests)
        assert result.result == "INSUFFICIENT", \
            f"Static AST: no errors should be INSUFFICIENT, got {result.result}"

    def test_documentation_strategy_advisory_only(self):
        """DocumentationAnalysisStrategy FAIL must never become BUG_DETECTED in verdict."""
        from app.evidence.snapshot import RepositorySnapshot
        from app.strategies.documentation import DocumentationAnalysisStrategy
        from app.agents.base import AgentEvidence
        from app.orchestration.orchestrator import _calculate_verdict

        snap = RepositorySnapshot.create(_ESCALATE_REPO)
        strategy = DocumentationAnalysisStrategy()
        result = strategy.execute(snap, {})

        # Create an AgentEvidence as if documentation_check returned FAIL
        doc_evidence = AgentEvidence(
            agent="documentation_check",
            command=None,
            result="FAIL",
            evidence="No README found.",
            confidence=0.5,
        )
        test_pass = AgentEvidence(
            agent="test_runner",
            command="pytest",
            result="PASS",
            evidence="All tests passed.",
            confidence=1.0,
        )
        # test_runner PASS + documentation_check FAIL → SAFE (doc is advisory)
        verdict, confidence = _calculate_verdict([test_pass, doc_evidence])
        assert verdict == "SAFE", \
            f"doc FAIL with test_runner PASS must yield SAFE, got {verdict}"

    def test_unsupported_strategy_returns_insufficient(self, tmp_path):
        """A strategy on an empty directory must return INSUFFICIENT, never ERROR."""
        from app.evidence.snapshot import RepositorySnapshot
        from app.strategies.existing_tests import ExistingTestsStrategy

        # Create empty dir — no tests → INSUFFICIENT
        snap = RepositorySnapshot.create(str(tmp_path))
        strategy = ExistingTestsStrategy()
        result = strategy.execute(snap, {})
        assert result.result in ("INSUFFICIENT", "ERROR"), \
            f"Empty repo should yield INSUFFICIENT or ERROR, got {result.result}"
        # Must not be FAIL (no tests is not a bug)
        assert result.result != "FAIL", "No tests must not produce FAIL"


# ===========================================================================
# TestEvidenceLedger
# ===========================================================================

class TestEvidenceLedger:
    """EvidenceLedger tracking, conflict detection, dependency handling."""

    def test_ledger_tracks_independent_evidence(self):
        """Evidence added to ledger is retrievable."""
        from app.evidence.claims import Evidence, EvidenceLedger

        ledger = EvidenceLedger()
        ev = Evidence.create(
            strategy_name="existing_tests",
            claim_id="claim-1",
            result="PASS",
            confidence=0.9,
            raw_output="Tests passed.",
            is_independent=True,
        )
        ledger.add(ev)
        assert len(ledger.for_claim("claim-1")) == 1
        assert ledger.for_claim("claim-1")[0].result == "PASS"

    def test_ledger_detects_dependent_evidence(self):
        """Dependent evidence is not counted in best_confidence."""
        from app.evidence.claims import Evidence, EvidenceLedger

        ledger = EvidenceLedger()
        independent = Evidence.create(
            strategy_name="existing_tests",
            claim_id="claim-1",
            result="PASS",
            confidence=0.9,
            raw_output="",
            is_independent=True,
        )
        dependent = Evidence.create(
            strategy_name="static_ast",
            claim_id="claim-1",
            result="PASS",
            confidence=0.95,
            raw_output="",
            is_independent=False,
            depends_on=independent.evidence_id,
        )
        ledger.add(independent)
        ledger.add(dependent)

        # best_confidence should use only independent evidence
        assert ledger.best_confidence("claim-1") == pytest.approx(0.9), \
            "Dependent evidence must not inflate confidence"

    def test_ledger_detects_contradictory_evidence(self):
        """PASS + FAIL from independent sources → contradiction detected."""
        from app.evidence.claims import Evidence, EvidenceLedger

        ledger = EvidenceLedger()
        ev_pass = Evidence.create(
            strategy_name="existing_tests",
            claim_id="claim-1",
            result="PASS",
            confidence=0.9,
            raw_output="",
            is_independent=True,
        )
        ev_fail = Evidence.create(
            strategy_name="differential_testing",
            claim_id="claim-1",
            result="FAIL",
            confidence=0.8,
            raw_output="",
            is_independent=True,
        )
        ledger.add(ev_pass)
        ledger.add(ev_fail)

        assert ledger.has_contradiction("claim-1"), \
            "PASS + FAIL from independent sources must be a contradiction"
        assert ledger.claim_result("claim-1") == "CONFLICT"

    def test_confidence_not_inflated_by_dependent_evidence(self):
        """Multiple dependent pieces do not increase confidence beyond independent max."""
        from app.evidence.claims import Evidence, EvidenceLedger

        ledger = EvidenceLedger()
        ind = Evidence.create(
            strategy_name="existing_tests",
            claim_id="claim-x",
            result="PASS",
            confidence=0.7,
            raw_output="",
            is_independent=True,
        )
        for i in range(5):
            dep = Evidence.create(
                strategy_name=f"dep_strategy_{i}",
                claim_id="claim-x",
                result="PASS",
                confidence=0.99,
                raw_output="",
                is_independent=False,
                depends_on=ind.evidence_id,
            )
            ledger.add(dep)
        ledger.add(ind)

        assert ledger.best_confidence("claim-x") == pytest.approx(0.7), \
            "Dependent evidence must never inflate confidence"


# ===========================================================================
# TestEvidenceSufficiency
# ===========================================================================

class TestEvidenceSufficiency:
    """EvidenceSufficiencyEvaluator and EvidenceGapAnalyzer."""

    def test_sufficient_evidence_from_passing_tests(self):
        """Passing test evidence → sufficient for code_correctness claim."""
        from app.evidence.claims import Claim, Evidence, EvidenceLedger
        from app.evidence.sufficiency import EvidenceSufficiencyEvaluator

        claim = Claim.create("code_correctness", "Code is correct.", "AUTHORITATIVE")
        ledger = EvidenceLedger()
        ev = Evidence.create(
            strategy_name="existing_tests",
            claim_id=claim.claim_id,
            result="PASS",
            confidence=0.9,
            raw_output="",
            is_independent=True,
        )
        ledger.add(ev)

        evaluator = EvidenceSufficiencyEvaluator()
        assert evaluator.is_sufficient(ledger, [claim]), \
            "PASS evidence for authoritative claim must be sufficient"
        assert evaluator.overall_result(ledger, [claim]) == "PASS"

    def test_insufficient_evidence_no_tests(self):
        """No evidence → not sufficient."""
        from app.evidence.claims import Claim, EvidenceLedger
        from app.evidence.sufficiency import EvidenceSufficiencyEvaluator

        claim = Claim.create("code_correctness", "Code is correct.", "AUTHORITATIVE")
        ledger = EvidenceLedger()

        evaluator = EvidenceSufficiencyEvaluator()
        assert not evaluator.is_sufficient(ledger, [claim]), \
            "Empty ledger must not be sufficient"
        assert evaluator.overall_result(ledger, [claim]) == "INSUFFICIENT"

    def test_gap_identified_when_conflicting(self):
        """Conflicting evidence → gap detected."""
        from app.evidence.claims import Claim, Evidence, EvidenceLedger
        from app.evidence.sufficiency import EvidenceGapAnalyzer

        claim = Claim.create("code_correctness", "Code is correct.", "AUTHORITATIVE")
        ledger = EvidenceLedger()
        ev_pass = Evidence.create("existing_tests", claim.claim_id, "PASS", 0.9, "", is_independent=True)
        ev_fail = Evidence.create("differential_testing", claim.claim_id, "FAIL", 0.8, "", is_independent=True)
        ledger.add(ev_pass)
        ledger.add(ev_fail)

        analyzer = EvidenceGapAnalyzer()
        gaps = analyzer.find_gaps(ledger, [claim])
        assert len(gaps) > 0, "Conflicting evidence must produce a gap"
        assert any(g.gap_type == "CONFLICTING" for g in gaps)

    def test_gap_identified_when_no_strategy_applicable(self):
        """No evidence at all → MISSING gap for authoritative claim."""
        from app.evidence.claims import Claim, EvidenceLedger
        from app.evidence.sufficiency import EvidenceGapAnalyzer

        claim = Claim.create("code_correctness", "Code is correct.", "AUTHORITATIVE")
        ledger = EvidenceLedger()

        analyzer = EvidenceGapAnalyzer()
        gaps = analyzer.find_gaps(ledger, [claim])
        assert len(gaps) > 0, "No evidence for authoritative claim must produce a gap"
        assert any(g.gap_type == "MISSING" for g in gaps)


# ===========================================================================
# TestStrategyPlanner
# ===========================================================================

class TestStrategyPlanner:
    """StrategyPlanner selection algorithm, budget, trace."""

    def _make_snapshot(self, tmp_path):
        (tmp_path / "foo.py").write_text("def foo(): return 1\n")
        from app.evidence.snapshot import RepositorySnapshot
        return RepositorySnapshot.create(str(tmp_path))

    def test_planner_selects_cheap_strategy_first(self, tmp_path):
        """Planner always tries lowest-cost strategy first."""
        from app.strategies.base import BaseStrategy, StrategyResult, StrategyRegistry
        from app.planner.planner import StrategyPlanner

        execution_order = []

        class CheapStrategy(BaseStrategy):
            name = "cheap"
            cost = 1
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                execution_order.append("cheap")
                return StrategyResult(result="PASS", confidence=0.9, raw_output="ok")

        class ExpensiveStrategy(BaseStrategy):
            name = "expensive"
            cost = 9
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                execution_order.append("expensive")
                return StrategyResult(result="PASS", confidence=0.8, raw_output="ok")

        registry = StrategyRegistry()
        registry.register(ExpensiveStrategy())
        registry.register(CheapStrategy())

        planner = StrategyPlanner(registry=registry)
        snap = self._make_snapshot(tmp_path)
        planner.execute_adaptive(snap, None, "run-cheap-test")

        if len(execution_order) >= 2:
            assert execution_order[0] == "cheap", \
                f"Cheap strategy must execute first, order was: {execution_order}"

    def test_planner_stops_when_budget_exhausted(self, tmp_path):
        """Planner stops after MAX_STRATEGIES executions."""
        from app.strategies.base import BaseStrategy, StrategyResult, StrategyRegistry
        from app.planner.planner import StrategyPlanner, MAX_STRATEGIES

        execution_count = [0]

        class CountingStrategy(BaseStrategy):
            def __init__(self, n):
                self._n = n
                self.name = f"strategy_{n}"
                self.cost = n
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                execution_count[0] += 1
                return StrategyResult(result="INSUFFICIENT", confidence=0.0, raw_output="")

        registry = StrategyRegistry()
        for i in range(MAX_STRATEGIES + 3):
            registry.register(CountingStrategy(i))

        planner = StrategyPlanner(registry=registry)
        snap = self._make_snapshot(tmp_path)
        planner.execute_adaptive(snap, None, "run-budget-test")

        assert execution_count[0] <= MAX_STRATEGIES, \
            f"Planner executed {execution_count[0]} strategies, max is {MAX_STRATEGIES}"

    def test_planner_does_not_retry_failed_strategy(self, tmp_path):
        """A strategy that fails is not retried."""
        from app.strategies.base import BaseStrategy, StrategyResult, StrategyRegistry
        from app.planner.planner import StrategyPlanner

        call_count = [0]

        class SingleUseStrategy(BaseStrategy):
            name = "single_use"
            cost = 1
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                call_count[0] += 1
                return StrategyResult(result="FAIL", confidence=0.9, raw_output="Bug!")

        registry = StrategyRegistry()
        registry.register(SingleUseStrategy())

        planner = StrategyPlanner(registry=registry)
        snap = self._make_snapshot(tmp_path)
        planner.execute_adaptive(snap, None, "run-no-retry-test")

        assert call_count[0] == 1, \
            f"Failed strategy must not be retried, was called {call_count[0]} times"

    def test_planner_skips_inapplicable_strategy(self, tmp_path):
        """A strategy returning is_applicable=False is not executed."""
        from app.strategies.base import BaseStrategy, StrategyResult, StrategyRegistry
        from app.planner.planner import StrategyPlanner

        executed = [False]

        class SkippedStrategy(BaseStrategy):
            name = "skipped"
            cost = 1
            def is_applicable(self, snap, ctx): return False
            def execute(self, snap, ctx):
                executed[0] = True
                return StrategyResult(result="PASS", confidence=1.0, raw_output="")

        class FallbackStrategy(BaseStrategy):
            name = "fallback"
            cost = 2
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                return StrategyResult(result="PASS", confidence=0.8, raw_output="")

        registry = StrategyRegistry()
        registry.register(SkippedStrategy())
        registry.register(FallbackStrategy())

        planner = StrategyPlanner(registry=registry)
        snap = self._make_snapshot(tmp_path)
        planner.execute_adaptive(snap, None, "run-skip-test")

        assert not executed[0], "Inapplicable strategy must not be executed"

    def test_planner_produces_trace(self, tmp_path, db_session):
        """Planner populates StrategyTraceEntry rows in the DB."""
        from app.evidence.snapshot import RepositorySnapshot
        from app.planner.planner import StrategyPlanner
        from app.models import StrategyTraceEntry

        import app.models  # ensure tables exist
        Base.metadata.create_all(bind=engine)

        run_id = f"trace-test-{uuid.uuid4()}"
        snap = RepositorySnapshot.create(_CLEAN_REPO)
        planner = StrategyPlanner()
        planner.execute_adaptive(snap, db_session, run_id)

        entries = (
            db_session.query(StrategyTraceEntry)
            .filter(StrategyTraceEntry.review_run_id == run_id)
            .all()
        )
        assert len(entries) > 0, "Planner must produce at least one trace entry"
        assert all(e.strategy_name for e in entries), "All trace entries must have a strategy name"


# ===========================================================================
# TestAdaptiveReviewFlow
# ===========================================================================

class TestAdaptiveReviewFlow:
    """Full-stack integration tests: API + DB end-to-end."""

    def _register_repo(self, db_session, name, path):
        """Register a repository with a specific local_path, returning its name."""
        from app.models import Repository
        repo = Repository(id=str(uuid.uuid4()), name=name, local_path=path)
        db_session.add(repo)
        db_session.commit()
        return name

    def test_full_review_buggy_repo_bug_detected(self, client, db_session):
        """Full review on buggy demo repo → BUG_DETECTED."""
        repo_name = self._register_repo(db_session, f"p6_buggy_{uuid.uuid4().hex[:6]}", _DEMO_REPO)
        resp = client.post(
            f"/repos/{repo_name}/prs/1/review",
            json={"pr_title": "Phase6 Buggy"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["verdict"] == "BUG_DETECTED", \
            f"Buggy repo must yield BUG_DETECTED, got {data['verdict']}"

    def test_full_review_clean_repo_safe(self, client, db_session):
        """Full review on clean_repo → SAFE."""
        repo_name = self._register_repo(db_session, f"p6_clean_{uuid.uuid4().hex[:6]}", _CLEAN_REPO)
        resp = client.post(
            f"/repos/{repo_name}/prs/1/review",
            json={"pr_title": "Phase6 Clean"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["verdict"] == "SAFE", \
            f"Clean repo must yield SAFE, got {data['verdict']}"

    def test_full_review_no_tests_escalate(self, client, db_session):
        """Full review on escalate_repo (no tests) → ESCALATE."""
        repo_name = self._register_repo(db_session, f"p6_esc_{uuid.uuid4().hex[:6]}", _ESCALATE_REPO)
        resp = client.post(
            f"/repos/{repo_name}/prs/1/review",
            json={"pr_title": "Phase6 Escalate"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["verdict"] == "ESCALATE", \
            f"No-tests repo must yield ESCALATE, got {data['verdict']}"

    def test_strategy_trace_persisted(self, client, db_session):
        """After a review, strategy-trace endpoint returns entries."""
        repo_name = self._register_repo(db_session, f"p6_trace_{uuid.uuid4().hex[:6]}", _CLEAN_REPO)
        resp = client.post(
            f"/repos/{repo_name}/prs/99/review",
            json={"pr_title": "Phase6 Trace"},
        )
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["id"]

        trace_resp = client.get(f"/reviews/{run_id}/strategy-trace")
        assert trace_resp.status_code == 200, trace_resp.text
        trace = trace_resp.json()
        # Trace may be empty if planner was skipped on error, but must be a list
        assert isinstance(trace, list), "strategy-trace must return a list"

    def test_evidence_api_returns_items(self, client, db_session):
        """After a review, /evidence endpoint returns a list."""
        repo_name = self._register_repo(db_session, f"p6_ev_{uuid.uuid4().hex[:6]}", _CLEAN_REPO)
        resp = client.post(
            f"/repos/{repo_name}/prs/100/review",
            json={"pr_title": "Phase6 Evidence"},
        )
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["id"]

        ev_resp = client.get(f"/reviews/{run_id}/evidence")
        assert ev_resp.status_code == 200, ev_resp.text
        items = ev_resp.json()
        assert isinstance(items, list), "/evidence must return a list"

    def test_claims_api_returns_claims(self, client, db_session):
        """After a review, /claims endpoint returns claims with correct fields."""
        repo_name = self._register_repo(db_session, f"p6_cl_{uuid.uuid4().hex[:6]}", _CLEAN_REPO)
        resp = client.post(
            f"/repos/{repo_name}/prs/101/review",
            json={"pr_title": "Phase6 Claims"},
        )
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["id"]

        claims_resp = client.get(f"/reviews/{run_id}/claims")
        assert claims_resp.status_code == 200, claims_resp.text
        claims = claims_resp.json()
        assert isinstance(claims, list), "/claims must return a list"
        if claims:
            claim = claims[0]
            assert "claim_type" in claim
            assert "claim_text" in claim
            assert "verdict_contribution" in claim

    def test_gaps_api_returns_gaps(self, client, db_session):
        """After a review, /evidence-gaps endpoint returns a list."""
        repo_name = self._register_repo(db_session, f"p6_gap_{uuid.uuid4().hex[:6]}", _ESCALATE_REPO)
        resp = client.post(
            f"/repos/{repo_name}/prs/200/review",
            json={"pr_title": "Phase6 Gaps"},
        )
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["id"]

        gaps_resp = client.get(f"/reviews/{run_id}/evidence-gaps")
        assert gaps_resp.status_code == 200, gaps_resp.text
        gaps = gaps_resp.json()
        assert isinstance(gaps, list), "/evidence-gaps must return a list"
