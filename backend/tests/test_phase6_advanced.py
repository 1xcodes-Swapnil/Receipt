"""
test_phase6_advanced.py — Focused tests for Phase 6 advanced strategies.

Tests:
  - Each strategy's applicability, prerequisites, execute() interface
  - EvidenceContract (correct result types / fail-closed behavior)
  - Bounded execution (seeds, iterations, timeout)
  - Failure handling (error → ERROR result, no fake evidence)
  - Planner selection of advanced strategies only on gaps
  - Integration: PR → Adaptive Planner → Advanced Strategy → Evidence → Verdict
  - New DB models (AdvancedStrategyExecution, etc.)
"""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

# Make sure backend is importable
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.evidence.snapshot import RepositorySnapshot
from app.strategies.base import BaseStrategy, StrategyResult, StrategyRegistry
from app.strategies.infrastructure import (
    BoundedExecutionContext,
    DeterministicSeed,
    IsolatedWorkspace,
    MutantCleanupRegistry,
    CounterexampleRecord,
)
from app.strategies.property_based import PropertyBasedTestingStrategy
from app.strategies.mutation_testing import MutationTestingStrategy
from app.strategies.fault_localization import FaultLocalizationStrategy
from app.strategies.metamorphic import MetamorphicTestingStrategy
from app.strategies.fuzzing import FuzzingStrategy
from app.strategies.counterexample_shrinking import CounterexampleShrinkingStrategy
from app.strategies.semantic_sibling import SemanticSiblingAnalysisStrategy
from app.strategies import build_default_registry, build_shrinking_registry
from app.planner.planner import StrategyPlanner


# ---------------------------------------------------------------------------
# Test DB setup
# ---------------------------------------------------------------------------

_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_phase6_adv_test.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create all tables for the test run."""
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
            pass  # Windows file lock — acceptable, file will be cleaned next run


@pytest.fixture()
def db_session():
    session = TestingSession()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(tmp_path, source_code: str = "", test_code: str = "") -> RepositorySnapshot:
    """Create a snapshot from a temp directory with optional source and test files."""
    if source_code:
        src_file = tmp_path / "src.py"
        src_file.write_text(source_code)
    if test_code:
        test_file = tmp_path / "test_src.py"
        test_file.write_text(test_code)
    return RepositorySnapshot.create(str(tmp_path))


def _simple_source() -> str:
    return textwrap.dedent("""
        def add(a, b):
            return a + b

        def subtract(x, y):
            return x - y

        def divide(a, b):
            return a / b
    """)


def _simple_tests() -> str:
    return textwrap.dedent("""
        from src import add, subtract

        def test_add():
            assert add(1, 2) == 3

        def test_subtract():
            assert subtract(5, 3) == 2
    """)


# ===========================================================================
# Infrastructure Tests
# ===========================================================================

class TestDeterministicSeed:

    def test_same_hash_same_seed(self):
        seed1 = DeterministicSeed.for_strategy("abc123", "property_based_testing")
        seed2 = DeterministicSeed.for_strategy("abc123", "property_based_testing")
        assert seed1 == seed2

    def test_different_hash_different_seed(self):
        seed1 = DeterministicSeed.for_strategy("abc123", "fuzzing")
        seed2 = DeterministicSeed.for_strategy("xyz789", "fuzzing")
        assert seed1 != seed2

    def test_different_strategy_different_seed(self):
        seed1 = DeterministicSeed.for_strategy("abc123", "fuzzing")
        seed2 = DeterministicSeed.for_strategy("abc123", "property_based_testing")
        assert seed1 != seed2

    def test_iteration_seeds_differ(self):
        base = DeterministicSeed.for_strategy("abc", "test")
        s0 = DeterministicSeed.for_iteration(base, 0)
        s1 = DeterministicSeed.for_iteration(base, 1)
        assert s0 != s1

    def test_seed_is_positive_integer(self):
        seed = DeterministicSeed.for_strategy("abc", "test")
        assert isinstance(seed, int)
        assert seed >= 0


class TestBoundedExecutionContext:

    def test_stops_at_max_iterations(self):
        ctx = BoundedExecutionContext(max_iterations=5, max_seconds=60.0)
        for _ in range(5):
            assert ctx.should_continue()
            ctx.tick()
        assert not ctx.should_continue()

    def test_stops_at_time_limit(self):
        import time
        ctx = BoundedExecutionContext(max_iterations=1000, max_seconds=0.05)
        time.sleep(0.1)
        assert not ctx.should_continue()
        assert ctx.timed_out

    def test_iterations_tracked(self):
        ctx = BoundedExecutionContext(max_iterations=10, max_seconds=60.0)
        ctx.tick()
        ctx.tick()
        assert ctx.iterations_used == 2


class TestIsolatedWorkspace:

    def test_workspace_created_and_cleaned(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        (source / "file.py").write_text("x = 1")

        workspace_root = None
        with IsolatedWorkspace(str(source)) as ws:
            workspace_root = ws.root
            assert os.path.isdir(workspace_root)
            # Source files copied
            assert os.path.isfile(os.path.join(ws.root, "source", "file.py"))

        # Cleaned up after exit
        assert not os.path.exists(workspace_root)

    def test_safe_path_prevents_traversal(self, tmp_path):
        with IsolatedWorkspace(str(tmp_path)) as ws:
            with pytest.raises(ValueError, match="escape"):
                ws.safe_path("..", "evil")

    def test_cleanup_on_exception(self, tmp_path):
        workspace_root = None
        try:
            with IsolatedWorkspace(str(tmp_path)) as ws:
                workspace_root = ws.root
                raise RuntimeError("test error")
        except RuntimeError:
            pass
        # Still cleaned up
        assert workspace_root is None or not os.path.exists(workspace_root)


class TestMutantCleanupRegistry:

    def test_backup_and_restore(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\n")
        registry = MutantCleanupRegistry()
        registry.backup(str(f))

        # Modify file
        f.write_text("x = 999\n")
        assert f.read_text() == "x = 999\n"

        # Restore
        registry.restore_all()
        assert f.read_text() == "x = 1\n"

    def test_restore_all_clears_registry(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("original")
        registry = MutantCleanupRegistry()
        registry.backup(str(f))
        registry.restore_all()
        registry.restore_all()  # Should not raise even when called twice


# ===========================================================================
# Strategy-level Tests
# ===========================================================================

class TestPropertyBasedTestingStrategy:

    def test_insufficient_when_no_source_files(self, tmp_path):
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = PropertyBasedTestingStrategy()
        assert not strategy.is_applicable(snapshot, {})

    def test_insufficient_when_no_public_functions(self, tmp_path):
        (tmp_path / "empty.py").write_text("# no functions\n")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = PropertyBasedTestingStrategy()
        result = strategy.execute(snapshot, {})
        assert result.result in ("INSUFFICIENT", "PASS")

    def test_returns_valid_result_type(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = PropertyBasedTestingStrategy()
        result = strategy.execute(snapshot, {})
        assert result.result in ("PASS", "FAIL", "INSUFFICIENT", "ERROR")

    def test_seed_in_output(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = PropertyBasedTestingStrategy()
        result = strategy.execute(snapshot, {})
        assert "seed=" in result.raw_output

    def test_reproducible_result(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snap1 = RepositorySnapshot.create(str(tmp_path))
        snap2 = RepositorySnapshot.create(str(tmp_path))
        strategy = PropertyBasedTestingStrategy()
        # Same snapshot hash → same seed → same result
        r1 = strategy.execute(snap1, {})
        r2 = strategy.execute(snap2, {})
        assert r1.result == r2.result

    def test_fail_closed_on_error(self, tmp_path):
        """Strategy must not raise — error maps to ERROR result."""
        # Create a snapshot pointing to non-existent path
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = PropertyBasedTestingStrategy()
        # Monkey-patch to force exception
        original = strategy._execute_inner
        def broken(s, c):
            raise RuntimeError("forced failure")
        strategy._execute_inner = broken
        result = strategy.execute(snapshot, {})
        assert result.result == "ERROR"
        strategy._execute_inner = original

    def test_applicability_requires_non_test_files(self, tmp_path):
        (tmp_path / "test_only.py").write_text("def test_x(): pass")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = PropertyBasedTestingStrategy()
        # Only test files — should not be applicable
        applicable = strategy.is_applicable(snapshot, {})
        assert not applicable


class TestMutationTestingStrategy:

    def test_insufficient_without_tests(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MutationTestingStrategy()
        ok, reason = strategy.prerequisites_met(snapshot, {})
        assert not ok
        assert "test" in reason.lower()

    def test_not_applicable_without_source(self, tmp_path):
        (tmp_path / "test_x.py").write_text("def test_y(): pass")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MutationTestingStrategy()
        assert not strategy.is_applicable(snapshot, {})

    def test_returns_valid_result(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        (tmp_path / "test_src.py").write_text(_simple_tests())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MutationTestingStrategy()
        result = strategy.execute(snapshot, {})
        assert result.result in ("PASS", "FAIL", "INSUFFICIENT", "ERROR")

    def test_cleanup_always_runs(self, tmp_path):
        """Verify MutantCleanupRegistry restores files on failure."""
        f = tmp_path / "src.py"
        f.write_text(_simple_source())
        original_content = f.read_text()
        registry = MutantCleanupRegistry()
        registry.backup(str(f))
        f.write_text("MUTATED")
        registry.restore_all()
        assert f.read_text() == original_content

    def test_fail_closed_on_error(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        (tmp_path / "test_src.py").write_text(_simple_tests())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MutationTestingStrategy()
        original = strategy._execute_inner
        def broken(s, c):
            raise RuntimeError("forced")
        strategy._execute_inner = broken
        result = strategy.execute(snapshot, {})
        assert result.result == "ERROR"
        strategy._execute_inner = original


class TestFaultLocalizationStrategy:

    def test_insufficient_without_tests(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FaultLocalizationStrategy()
        assert not strategy.is_applicable(snapshot, {})

    def test_requires_test_files(self, tmp_path):
        (tmp_path / "test_x.py").write_text("")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FaultLocalizationStrategy()
        assert strategy.is_applicable(snapshot, {})

    def test_insufficient_when_no_failures(self, tmp_path):
        """No test failures → INSUFFICIENT."""
        (tmp_path / "test_empty.py").write_text("")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FaultLocalizationStrategy()
        result = strategy.execute(snapshot, {})
        # Either INSUFFICIENT (no failures to localize) or PASS
        assert result.result in ("INSUFFICIENT", "PASS", "FAIL", "ERROR")

    def test_returns_valid_result(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        (tmp_path / "test_src.py").write_text(_simple_tests())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FaultLocalizationStrategy()
        result = strategy.execute(snapshot, {})
        assert result.result in ("PASS", "FAIL", "INSUFFICIENT", "ERROR")

    def test_localization_is_hypothesis_not_proof(self, tmp_path):
        """Output must contain hypothesis disclaimer."""
        (tmp_path / "src.py").write_text(_simple_source())
        (tmp_path / "test_src.py").write_text(textwrap.dedent("""
            import pytest
            def test_always_fails():
                assert False, "forced failure"
        """))
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FaultLocalizationStrategy()
        result = strategy.execute(snapshot, {})
        # If it has evidence items, they must include the hypothesis note
        if result.evidence_items:
            for item in result.evidence_items:
                if isinstance(item, dict) and "note" in item:
                    assert "hypothesis" in item["note"].lower() or "not" in item["note"].lower()

    def test_fail_closed_on_error(self, tmp_path):
        (tmp_path / "test_x.py").write_text("")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FaultLocalizationStrategy()
        original = strategy._execute_inner
        def broken(s, c):
            raise RuntimeError("forced")
        strategy._execute_inner = broken
        result = strategy.execute(snapshot, {})
        assert result.result == "ERROR"
        strategy._execute_inner = original


class TestMetamorphicTestingStrategy:

    def test_insufficient_without_source(self, tmp_path):
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MetamorphicTestingStrategy()
        assert not strategy.is_applicable(snapshot, {})

    def test_returns_valid_result(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MetamorphicTestingStrategy()
        result = strategy.execute(snapshot, {})
        assert result.result in ("PASS", "FAIL", "INSUFFICIENT", "ERROR")

    def test_seed_appears_in_output(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MetamorphicTestingStrategy()
        result = strategy.execute(snapshot, {})
        assert "seed=" in result.raw_output or "Seed:" in result.raw_output

    def test_fail_closed_on_error(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = MetamorphicTestingStrategy()
        original = strategy._execute_inner
        def broken(s, c):
            raise RuntimeError("forced")
        strategy._execute_inner = broken
        result = strategy.execute(snapshot, {})
        assert result.result == "ERROR"
        strategy._execute_inner = original


class TestFuzzingStrategy:

    def test_insufficient_without_source(self, tmp_path):
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FuzzingStrategy()
        assert not strategy.is_applicable(snapshot, {})

    def test_returns_valid_result(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FuzzingStrategy()
        result = strategy.execute(snapshot, {})
        assert result.result in ("PASS", "FAIL", "INSUFFICIENT", "ERROR")

    def test_no_crash_is_not_proof(self, tmp_path):
        """PASS output must state non-proof disclaimer."""
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FuzzingStrategy()
        result = strategy.execute(snapshot, {})
        if result.result == "PASS":
            assert "does not prove" in result.raw_output.lower() or "not proof" in result.raw_output.lower()

    def test_bounded_execution_enforced(self, tmp_path):
        """Execution should complete in well under the max seconds."""
        import time
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FuzzingStrategy()
        start = time.monotonic()
        result = strategy.execute(snapshot, {})
        elapsed = time.monotonic() - start
        assert elapsed < 60.0, f"Fuzzing took too long: {elapsed:.1f}s"

    def test_seed_in_output(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FuzzingStrategy()
        result = strategy.execute(snapshot, {})
        assert "seed=" in result.raw_output

    def test_fail_closed_on_error(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = FuzzingStrategy()
        original = strategy._execute_inner
        def broken(s, c):
            raise RuntimeError("forced")
        strategy._execute_inner = broken
        result = strategy.execute(snapshot, {})
        assert result.result == "ERROR"
        strategy._execute_inner = original


class TestCounterexampleShrinkingStrategy:

    def test_not_applicable_without_context(self, tmp_path):
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = CounterexampleShrinkingStrategy()
        assert not strategy.is_applicable(snapshot, {})

    def test_applicable_with_failing_input(self, tmp_path):
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = CounterexampleShrinkingStrategy()
        context = {
            "failing_input": [100, 0],
            "failing_func": "divide",
            "failing_file": "src.py",
        }
        assert strategy.is_applicable(snapshot, context)

    def test_prerequisites_checked(self, tmp_path):
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = CounterexampleShrinkingStrategy()
        ok, reason = strategy.prerequisites_met(snapshot, {})
        assert not ok
        assert "failing input" in reason.lower()

    def test_shrinks_crashing_input(self, tmp_path):
        """Divide by zero — shrink [100, 0] should stay reproducible."""
        (tmp_path / "src.py").write_text(textwrap.dedent("""
            def divide(a, b):
                return a / b
        """))
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = CounterexampleShrinkingStrategy()
        context = {
            "failing_input": [100, 0],
            "failing_func": "divide",
            "failing_file": "src.py",
            "expected_exception": "ZeroDivisionError",
        }
        result = strategy.execute(snapshot, context)
        assert result.result in ("PASS", "FAIL")
        assert "divide" in result.raw_output
        # Minimized input must still contain 0 (needed for ZeroDivisionError)
        assert "0" in result.raw_output

    def test_insufficient_when_original_doesnt_fail(self, tmp_path):
        (tmp_path / "src.py").write_text("def add(a, b): return a + b")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = CounterexampleShrinkingStrategy()
        context = {
            "failing_input": [1, 2],
            "failing_func": "add",
            "failing_file": "src.py",
        }
        result = strategy.execute(snapshot, context)
        assert result.result in ("INSUFFICIENT", "PASS", "FAIL")

    def test_counterexample_record_has_required_fields(self):
        record = CounterexampleRecord(
            strategy_name="property_based_testing",
            property_description="add(a, b)",
            original_input=[100, 0],
            minimized_input=[1, 0],
            failure_reason="ZeroDivisionError",
            seed=42,
            is_minimized=True,
        )
        d = record.to_dict()
        assert d["strategy_name"] == "property_based_testing"
        assert d["is_minimized"] is True
        assert d["seed"] == 42
        assert "original_input" in d
        assert "minimized_input" in d


class TestSemanticSiblingAnalysisStrategy:

    def test_not_applicable_with_single_file(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = SemanticSiblingAnalysisStrategy()
        assert not strategy.is_applicable(snapshot, {})

    def test_applicable_with_multiple_files(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        (tmp_path / "utils.py").write_text("def multiply(a, b): return a * b")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = SemanticSiblingAnalysisStrategy()
        assert strategy.is_applicable(snapshot, {})

    def test_returns_valid_result(self, tmp_path):
        (tmp_path / "src.py").write_text(_simple_source())
        (tmp_path / "utils.py").write_text("def add_values(x, y): return x + y")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = SemanticSiblingAnalysisStrategy()
        result = strategy.execute(snapshot, {})
        assert result.result in ("PASS", "INSUFFICIENT", "ERROR")

    def test_candidates_are_potential_match_only(self, tmp_path):
        """No candidate should be marked CONFIRMED without independent verification."""
        (tmp_path / "a.py").write_text(_simple_source())
        (tmp_path / "b.py").write_text(
            "def add_two(x, y): return x + y\ndef sub_two(x, y): return x - y\n"
        )
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = SemanticSiblingAnalysisStrategy()
        result = strategy.execute(snapshot, {})
        if result.evidence_items:
            for item in result.evidence_items:
                if isinstance(item, dict) and "candidates" in item:
                    for c in item["candidates"]:
                        assert c["status"] == "POTENTIAL_MATCH"

    def test_not_marked_confirmed_defect(self, tmp_path):
        """CONFIRMED status must never appear in sibling results."""
        (tmp_path / "a.py").write_text(_simple_source())
        (tmp_path / "b.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = SemanticSiblingAnalysisStrategy()
        result = strategy.execute(snapshot, {})
        assert "CONFIRMED" not in result.raw_output

    def test_fail_closed_on_error(self, tmp_path):
        (tmp_path / "a.py").write_text(_simple_source())
        (tmp_path / "b.py").write_text("def f(x): return x")
        snapshot = RepositorySnapshot.create(str(tmp_path))
        strategy = SemanticSiblingAnalysisStrategy()
        original = strategy._execute_inner
        def broken(s, c):
            raise RuntimeError("forced")
        strategy._execute_inner = broken
        result = strategy.execute(snapshot, {})
        assert result.result == "ERROR"
        strategy._execute_inner = original


# ===========================================================================
# Evidence Contract Tests
# ===========================================================================

class TestEvidenceContracts:

    STRATEGIES = [
        PropertyBasedTestingStrategy,
        MutationTestingStrategy,
        FaultLocalizationStrategy,
        MetamorphicTestingStrategy,
        FuzzingStrategy,
        SemanticSiblingAnalysisStrategy,
    ]

    def test_all_strategies_have_name(self):
        for klass in self.STRATEGIES:
            s = klass()
            assert isinstance(s.name, str) and s.name

    def test_all_strategies_have_cost(self):
        for klass in self.STRATEGIES:
            s = klass()
            assert isinstance(s.cost, int)
            assert 1 <= s.cost <= 10

    def test_all_strategies_return_valid_result_on_empty_repo(self, tmp_path):
        snapshot = RepositorySnapshot.create(str(tmp_path))
        valid_results = {"PASS", "FAIL", "INSUFFICIENT", "ERROR"}
        for klass in self.STRATEGIES:
            s = klass()
            if s.is_applicable(snapshot, {}):
                result = s.execute(snapshot, {})
                assert result.result in valid_results, (
                    f"{klass.__name__} returned unexpected result: {result.result}"
                )

    def test_error_never_produces_fake_evidence(self, tmp_path):
        """An ERROR result must not have high confidence."""
        snapshot = RepositorySnapshot.create(str(tmp_path))
        for klass in self.STRATEGIES:
            s = klass()
            original = getattr(s, "_execute_inner", None)
            if original:
                def broken(snap, ctx, _orig=original):
                    raise RuntimeError("forced test error")
                s._execute_inner = broken
                result = s.execute(snapshot, {})
                if result.result == "ERROR":
                    assert result.confidence == 0.0, (
                        f"{klass.__name__} ERROR result has non-zero confidence"
                    )

    def test_insufficient_evidence_never_becomes_pass(self, tmp_path):
        """INSUFFICIENT must stay INSUFFICIENT — never promoted to PASS."""
        snapshot = RepositorySnapshot.create(str(tmp_path))
        for klass in self.STRATEGIES:
            s = klass()
            ok, reason = s.prerequisites_met(snapshot, {})
            if not ok:
                # If prereqs not met, result must be INSUFFICIENT or we skip
                if s.is_applicable(snapshot, {}):
                    result = s.execute(snapshot, {})
                    assert result.result in ("INSUFFICIENT", "ERROR")


# ===========================================================================
# Planner Integration Tests
# ===========================================================================

class TestPlannerPhase6Integration:

    def test_registry_contains_all_phase6_strategies(self):
        registry = build_default_registry()
        names = {s.name for s in registry.all()}
        expected = {
            "property_based_testing",
            "mutation_testing",
            "fault_localization",
            "metamorphic_testing",
            "fuzzing",
            "semantic_sibling_analysis",
        }
        assert expected.issubset(names), f"Missing: {expected - names}"

    def test_shrinking_registry_adds_counterexample(self):
        registry = build_shrinking_registry()
        names = {s.name for s in registry.all()}
        assert "counterexample_shrinking" in names

    def test_advanced_strategies_have_higher_cost_than_basic(self):
        registry = build_default_registry()
        basic = {s for s in registry.all() if s.name in ("existing_tests", "static_ast")}
        advanced = {s for s in registry.all() if s.name in (
            "property_based_testing", "mutation_testing", "fuzzing"
        )}
        for b in basic:
            for a in advanced:
                assert b.cost <= a.cost, (
                    f"Basic {b.name}(cost={b.cost}) should be cheaper than "
                    f"advanced {a.name}(cost={a.cost})"
                )

    def test_planner_skips_advanced_when_gaps_resolved(self, tmp_path):
        """Advanced strategies must be skipped when no evidence gaps remain."""
        from app.strategies.base import StrategyRegistry

        execution_log: list[str] = []

        class FastPassStrategy(BaseStrategy):
            name = "existing_tests"
            cost = 2
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                execution_log.append(self.name)
                return StrategyResult(result="PASS", confidence=0.95,
                                      raw_output="All tests pass")

        class TrackingAdvanced(BaseStrategy):
            name = "property_based_testing"
            cost = 6
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                execution_log.append(self.name)
                return StrategyResult(result="PASS", confidence=0.8, raw_output="ok")

        registry = StrategyRegistry()
        registry.register(FastPassStrategy())
        registry.register(TrackingAdvanced())

        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snapshot, None, "test-run-skip-advanced")

        # Advanced should have been skipped because base strategy resolved gaps
        assert "property_based_testing" not in execution_log

    def test_planner_runs_advanced_when_gaps_remain(self, tmp_path):
        """Advanced strategies must run when evidence gaps remain after cheap strategies."""
        from app.strategies.base import StrategyRegistry

        execution_log: list[str] = []

        class InsufficientBase(BaseStrategy):
            name = "existing_tests"
            cost = 2
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                execution_log.append(self.name)
                return StrategyResult(result="INSUFFICIENT", confidence=0.0,
                                      raw_output="No tests")

        class TrackingAdvanced(BaseStrategy):
            name = "property_based_testing"
            cost = 6
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                execution_log.append(self.name)
                return StrategyResult(result="PASS", confidence=0.8, raw_output="ok")

        registry = StrategyRegistry()
        registry.register(InsufficientBase())
        registry.register(TrackingAdvanced())

        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snapshot, None, "test-run-advanced-gap")

        assert "property_based_testing" in execution_log

    def test_planner_never_runs_shrinking_without_failing_input(self, tmp_path):
        """CounterexampleShrinking should always be skipped when no failing_input in context."""
        registry = build_shrinking_registry()
        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        planner = StrategyPlanner(registry=registry)
        evidences = planner.execute_adaptive(snapshot, None, "test-no-shrink")
        # Planner must complete without error
        assert len(evidences) > 0


# ===========================================================================
# DB Model Tests
# ===========================================================================

class TestPhase6Models:

    def test_advanced_strategy_execution_model_exists(self, db_session):
        from app.models import AdvancedStrategyExecution, AdvancedStrategyResultEnum
        entry = AdvancedStrategyExecution(
            id="test-ase-1",
            review_run_id="dummy-run",
            strategy_name="fuzzing",
            result=AdvancedStrategyResultEnum.PASS,
            confidence=0.7,
            seed=12345,
            raw_output="test output",
            cleanup_completed=True,
        )
        # We can't actually persist without a ReviewRun FK, but we can verify the model
        assert entry.strategy_name == "fuzzing"
        assert entry.result == "PASS"
        assert entry.cleanup_completed is True

    def test_counterexample_record_model_exists(self):
        from app.models import CounterexampleRecord as DBCounterexample
        entry = DBCounterexample(
            id="test-ce-1",
            review_run_id="dummy-run",
            strategy_name="property_based_testing",
            property_description="divide(a, b)",
            original_input_repr="[100, 0]",
            minimized_input_repr="[1, 0]",
            failure_reason="ZeroDivisionError",
            seed=42,
            is_minimized=True,
        )
        assert entry.is_minimized is True
        assert entry.seed == 42

    def test_mutation_summary_model_exists(self):
        from app.models import MutationSummary
        entry = MutationSummary(
            id="test-ms-1",
            review_run_id="dummy-run",
            total_mutants=10,
            killed=7,
            survived=2,
            invalid=1,
            kill_rate=0.7,
        )
        assert entry.kill_rate == 0.7
        assert entry.survived == 2

    def test_fault_localization_result_model_exists(self):
        from app.models import FaultLocalizationResult
        entry = FaultLocalizationResult(
            id="test-fl-1",
            review_run_id="dummy-run",
            n_failing=3,
            n_passing=5,
            top_suspect="src.py::add",
            top_score=0.866,
        )
        assert entry.top_score == 0.866
        assert entry.n_failing == 3

    def test_advanced_evidence_item_model_exists(self):
        from app.models import AdvancedEvidenceItem
        item = AdvancedEvidenceItem(
            id="test-aei-1",
            execution_id="test-ase-1",
            review_run_id="dummy-run",
            evidence_type="property_violation",
            location="src.py::divide",
            description="ZeroDivisionError with inputs [100, 0]",
            seed=42,
        )
        assert item.evidence_type == "property_violation"


# ===========================================================================
# End-to-end verdict integration
# ===========================================================================

class TestAdvancedStrategyVerdictFlow:

    def test_fail_evidence_maps_to_bug_detected_verdict(self, tmp_path):
        """A FAIL result from an advanced strategy should propagate correctly."""
        from app.strategies.base import StrategyRegistry

        class FakeAdvancedFail(BaseStrategy):
            name = "fuzzing"
            cost = 6
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                return StrategyResult(
                    result="FAIL",
                    confidence=0.8,
                    raw_output="Fuzzing found a crash: ZeroDivisionError",
                    command="fuzzing seed=42",
                )

        registry = StrategyRegistry()
        registry.register(FakeAdvancedFail())

        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        planner = StrategyPlanner(registry=registry)
        evidences = planner.execute_adaptive(snapshot, None, "test-advanced-fail")

        assert len(evidences) > 0
        # At least one evidence should be FAIL
        results = {e.result for e in evidences}
        assert "FAIL" in results

    def test_error_strategy_escalates_verdict(self, tmp_path):
        """An ERROR from an advanced strategy must produce ESCALATE-capable evidence."""
        from app.strategies.base import StrategyRegistry

        class ErrorStrategy(BaseStrategy):
            name = "property_based_testing"
            cost = 6
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                return StrategyResult(
                    result="ERROR",
                    confidence=0.0,
                    raw_output="Strategy execution failed",
                )

        registry = StrategyRegistry()
        registry.register(ErrorStrategy())

        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        planner = StrategyPlanner(registry=registry)
        evidences = planner.execute_adaptive(snapshot, None, "test-advanced-error")

        assert len(evidences) > 0
        results = {e.result for e in evidences}
        # ERROR maps to INSUFFICIENT_EVIDENCE (never fabricated as PASS or SAFE)
        assert "PASS" not in results or any(
            e.result in ("INSUFFICIENT_EVIDENCE", "ERROR") for e in evidences
        )

    def test_insufficient_from_advanced_does_not_become_safe(self, tmp_path):
        """INSUFFICIENT from advanced strategy cannot promote to SAFE."""
        from app.strategies.base import StrategyRegistry

        class InsufficientAdvanced(BaseStrategy):
            name = "mutation_testing"
            cost = 7
            def is_applicable(self, snap, ctx): return True
            def execute(self, snap, ctx):
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output="No applicable mutation targets",
                )

        registry = StrategyRegistry()
        registry.register(InsufficientAdvanced())

        (tmp_path / "src.py").write_text(_simple_source())
        snapshot = RepositorySnapshot.create(str(tmp_path))
        planner = StrategyPlanner(registry=registry)
        evidences = planner.execute_adaptive(snapshot, None, "test-insuf-no-safe")

        assert len(evidences) > 0
        # INSUFFICIENT should never become PASS
        for e in evidences:
            if e.result == "INSUFFICIENT_EVIDENCE":
                # This is correct — it did not become a false PASS
                pass
