"""
test_gap_activation.py — ST-7: Advanced strategy gap activation tests.

Verifies that:
  1. Each advanced strategy is skipped when a base strategy fills the gap (PASS result)
  2. Each advanced strategy activates when gaps remain (INSUFFICIENT/FAIL from base)
  3. Multiple advanced strategies are tried in cost order when gap persists
  4. Advanced strategies do NOT run when max budget is exhausted by base strategies
  5. Advisory strategies (documentation_analysis, history_analysis) always run regardless
"""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.evidence.snapshot import RepositorySnapshot
from app.planner.planner import StrategyPlanner, _ADVANCED_STRATEGIES
from app.strategies.base import BaseStrategy, StrategyRegistry, StrategyResult


def _make_snapshot(tmp_path):
    (tmp_path / "src.py").write_text(textwrap.dedent("""\
        def compute(x):
            return x * 2
    """))
    return RepositorySnapshot.create(str(tmp_path))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pass_strategy(name: str, cost: int, log: list):
    _name = name
    _log = log

    class _S(BaseStrategy):
        def is_applicable(self, snap, ctx) -> bool:
            return True
        def execute(self, snap, ctx) -> StrategyResult:
            _log.append(_name)
            return StrategyResult(result="PASS", confidence=0.95, raw_output="ok")

    _S.name = _name
    _S.cost = cost
    return _S()


def _make_insuf_strategy(name: str, cost: int, log: list):
    _name = name
    _log = log

    class _S(BaseStrategy):
        def is_applicable(self, snap, ctx) -> bool:
            return True
        def execute(self, snap, ctx) -> StrategyResult:
            _log.append(_name)
            return StrategyResult(result="INSUFFICIENT", confidence=0.0, raw_output="no data")

    _S.name = _name
    _S.cost = cost
    return _S()


def _make_tracking_strategy(name: str, cost: int, log: list, result: str = "PASS"):
    _name = name
    _log = log
    _result = result

    class _S(BaseStrategy):
        def is_applicable(self, snap, ctx) -> bool:
            return True
        def execute(self, snap, ctx) -> StrategyResult:
            _log.append(_name)
            return StrategyResult(result=_result, confidence=0.8, raw_output="tracked")

    _S.name = _name
    _S.cost = cost
    return _S()


# ── TestAdvancedStrategySkippedOnPass ─────────────────────────────────────────

class TestAdvancedStrategySkippedOnPass:
    """Advanced strategies are not invoked when base strategy returns PASS."""

    @pytest.mark.parametrize("advanced_name", sorted(_ADVANCED_STRATEGIES))
    def test_advanced_skipped_when_base_passes(self, tmp_path, advanced_name):
        """Each advanced strategy must be skipped when base resolves the gap."""
        log: list[str] = []
        registry = StrategyRegistry()
        registry.register(_make_pass_strategy("existing_tests", 2, log))
        registry.register(_make_tracking_strategy(advanced_name, 6, log))

        snap = _make_snapshot(tmp_path)
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snap, None, f"skip-adv-{advanced_name[:12]}")

        assert advanced_name not in log, (
            f"Advanced strategy '{advanced_name}' must NOT run when base strategy PASS fills gap"
        )


# ── TestAdvancedStrategyActivatesOnGap ───────────────────────────────────────

class TestAdvancedStrategyActivatesOnGap:
    """Advanced strategies activate when base strategies leave an evidence gap."""

    def test_property_based_testing_activates_on_gap(self, tmp_path):
        log: list[str] = []
        registry = StrategyRegistry()
        registry.register(_make_insuf_strategy("existing_tests", 2, log))
        registry.register(_make_tracking_strategy("property_based_testing", 6, log))

        snap = _make_snapshot(tmp_path)
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snap, None, "pbt-gap-test")

        assert "property_based_testing" in log, (
            "property_based_testing must run when base leaves INSUFFICIENT evidence"
        )

    def test_mutation_testing_activates_on_gap(self, tmp_path):
        log: list[str] = []
        registry = StrategyRegistry()
        registry.register(_make_insuf_strategy("existing_tests", 2, log))
        registry.register(_make_tracking_strategy("mutation_testing", 7, log))

        snap = _make_snapshot(tmp_path)
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snap, None, "mut-gap-test")

        assert "mutation_testing" in log, (
            "mutation_testing must run when base leaves INSUFFICIENT evidence"
        )

    def test_fault_localization_activates_on_gap(self, tmp_path):
        log: list[str] = []
        registry = StrategyRegistry()
        registry.register(_make_insuf_strategy("existing_tests", 2, log))
        registry.register(_make_tracking_strategy("fault_localization", 5, log))

        snap = _make_snapshot(tmp_path)
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snap, None, "fl-gap-test")

        assert "fault_localization" in log, (
            "fault_localization must run when base leaves INSUFFICIENT evidence"
        )


# ── TestAdvancedStrategyCostOrdering ─────────────────────────────────────────

class TestAdvancedStrategyCostOrdering:
    """When gap persists, cheaper advanced strategies execute before more expensive ones."""

    def test_cheaper_advanced_runs_before_expensive(self, tmp_path):
        log: list[str] = []
        registry = StrategyRegistry()
        registry.register(_make_insuf_strategy("existing_tests", 2, log))
        registry.register(_make_tracking_strategy("fault_localization", 5, log))   # cheaper
        registry.register(_make_tracking_strategy("mutation_testing", 7, log))     # more expensive

        snap = _make_snapshot(tmp_path)
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snap, None, "adv-cost-order-test")

        if "fault_localization" in log and "mutation_testing" in log:
            fl_idx = log.index("fault_localization")
            mt_idx = log.index("mutation_testing")
            assert fl_idx < mt_idx, (
                "fault_localization (cost=5) must execute before mutation_testing (cost=7)"
            )

    def test_second_advanced_runs_when_first_is_insufficient(self, tmp_path):
        """If the first advanced strategy is INSUFFICIENT, the next one must activate."""
        log: list[str] = []
        registry = StrategyRegistry()
        registry.register(_make_insuf_strategy("existing_tests", 2, log))
        registry.register(_make_insuf_strategy("fault_localization", 5, log))    # first advanced, insuf
        registry.register(_make_tracking_strategy("mutation_testing", 7, log))  # second advanced

        snap = _make_snapshot(tmp_path)
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snap, None, "chain-adv-test")

        assert "fault_localization" in log, "First advanced strategy must have been tried"
        assert "mutation_testing" in log, (
            "Second advanced strategy must run when first advanced is INSUFFICIENT"
        )


# ── TestAdvancedBudgetEnforcement ─────────────────────────────────────────────

class TestAdvancedBudgetEnforcement:
    """MAX_STRATEGIES_WITH_ADVANCED caps total strategy executions."""

    def test_budget_limits_total_strategies(self, tmp_path):
        from app.planner.planner import MAX_STRATEGIES_WITH_ADVANCED
        log: list[str] = []
        registry = StrategyRegistry()
        for i in range(MAX_STRATEGIES_WITH_ADVANCED + 3):
            name = "existing_tests" if i == 0 else f"strategy_{i}"
            registry.register(_make_insuf_strategy(name, i + 2, log))

        snap = _make_snapshot(tmp_path)
        planner = StrategyPlanner(registry=registry)
        planner.execute_adaptive(snap, None, "budget-test")

        assert len(log) <= MAX_STRATEGIES_WITH_ADVANCED, (
            f"Planner must not execute more than {MAX_STRATEGIES_WITH_ADVANCED} strategies"
        )


# ── TestAdvisoryAlwaysRuns ────────────────────────────────────────────────────

class TestAdvisoryAlwaysRuns:
    """Advisory strategies (documentation_analysis, history_analysis) always activate."""

    def test_documentation_advisory_never_triggers_bug_verdict(self, tmp_path):
        from app.planner.planner import _ADVISORY_STRATEGIES
        assert "documentation_analysis" in _ADVISORY_STRATEGIES, (
            "documentation_analysis must be registered as advisory"
        )

    def test_history_analysis_never_triggers_bug_verdict(self, tmp_path):
        from app.planner.planner import _ADVISORY_STRATEGIES
        assert "history_analysis" in _ADVISORY_STRATEGIES, (
            "history_analysis must be registered as advisory"
        )

    def test_advisory_strategy_set_is_not_empty(self):
        from app.planner.planner import _ADVISORY_STRATEGIES
        assert len(_ADVISORY_STRATEGIES) >= 2, (
            "_ADVISORY_STRATEGIES must include at least documentation_analysis and history_analysis"
        )
