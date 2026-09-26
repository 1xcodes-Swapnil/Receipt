"""
Strategies package — adaptive evidence strategies.

All strategies wrap existing agents or perform pure analysis.
Phase 6 adds advanced testing strategies: PropertyBased, Mutation,
FaultLocalization, Metamorphic, Fuzzing, CounterexampleShrinking,
SemanticSiblingAnalysis.
"""
from app.strategies.base import BaseStrategy, StrategyResult, StrategyRegistry
from app.strategies.existing_tests import ExistingTestsStrategy
from app.strategies.change_impact import ChangeImpactStrategy
from app.strategies.differential import DifferentialTestingStrategy
from app.strategies.targeted import TargetedTestingStrategy
from app.strategies.static_ast import StaticASTAnalysisStrategy
from app.strategies.history import HistoryAnalysisStrategy
from app.strategies.documentation import DocumentationAnalysisStrategy

# Phase 6 strategies
from app.strategies.property_based import PropertyBasedTestingStrategy
from app.strategies.mutation_testing import MutationTestingStrategy
from app.strategies.fault_localization import FaultLocalizationStrategy
from app.strategies.metamorphic import MetamorphicTestingStrategy
from app.strategies.fuzzing import FuzzingStrategy
from app.strategies.counterexample_shrinking import CounterexampleShrinkingStrategy
from app.strategies.semantic_sibling import SemanticSiblingAnalysisStrategy


def build_default_registry() -> StrategyRegistry:
    """Build and return the default strategy registry (Phase 5 + Phase 6 strategies)."""
    registry = StrategyRegistry()
    for strategy in [
        # Phase 5 strategies (original set)
        ChangeImpactStrategy(),
        ExistingTestsStrategy(),
        StaticASTAnalysisStrategy(),
        DifferentialTestingStrategy(),
        DocumentationAnalysisStrategy(),
        HistoryAnalysisStrategy(),
        TargetedTestingStrategy(),
        # Phase 6 advanced strategies
        SemanticSiblingAnalysisStrategy(),    # cost=4, cheap AST analysis
        FaultLocalizationStrategy(),           # cost=5, test failure ranking
        PropertyBasedTestingStrategy(),        # cost=6, property generation
        MetamorphicTestingStrategy(),          # cost=6, relation checking
        FuzzingStrategy(),                     # cost=6, input fuzzing
        MutationTestingStrategy(),             # cost=7, mutation + test re-run
        # CounterexampleShrinking not in default registry —
        # it requires a failing_input from context (see build_shrinking_registry)
    ]:
        registry.register(strategy)
    return registry


def build_shrinking_registry() -> StrategyRegistry:
    """
    Registry variant that includes CounterexampleShrinkingStrategy.
    Use when a failing input is available in context.
    """
    registry = build_default_registry()
    registry.register(CounterexampleShrinkingStrategy())
    return registry


__all__ = [
    "BaseStrategy",
    "StrategyResult",
    "StrategyRegistry",
    "ExistingTestsStrategy",
    "ChangeImpactStrategy",
    "DifferentialTestingStrategy",
    "TargetedTestingStrategy",
    "StaticASTAnalysisStrategy",
    "HistoryAnalysisStrategy",
    "DocumentationAnalysisStrategy",
    # Phase 6
    "PropertyBasedTestingStrategy",
    "MutationTestingStrategy",
    "FaultLocalizationStrategy",
    "MetamorphicTestingStrategy",
    "FuzzingStrategy",
    "CounterexampleShrinkingStrategy",
    "SemanticSiblingAnalysisStrategy",
    "build_default_registry",
    "build_shrinking_registry",
]
