"""
Immunity Pipeline — Phase 7 canonical.

ImmunityOrchestratorV7 is the canonical orchestrator.
ImmunityOrchestrator (Phase 3) remains as a compatibility wrapper.
"""
# Phase 7 canonical orchestrator — use this everywhere
from app.immunity.orchestrator_v7 import ImmunityOrchestratorV7

# Phase 3 orchestrator kept for backward compatibility only
from app.immunity.orchestrator import ImmunityOrchestrator

# Re-export Phase 7 as the canonical name
ImmunityOrchestrator = ImmunityOrchestratorV7  # canonical alias

from app.immunity.stages import (
    ReproduceStage,
    RootCauseStage,
    FixStage,
    VerifyStage,
    RegressionTestStage,
    SiblingHuntStage,
    DocumentationStage,
)
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
from app.immunity.hypothesis import HypothesisTracker
from app.immunity.adaptive_fix import AdaptiveFixPlanner
from app.immunity.state_machine import PipelineStateMachine, StageStateMachine

__all__ = [
    # Canonical (V7)
    "ImmunityOrchestratorV7",
    "ImmunityOrchestrator",   # alias → V7
    "ReproduceStageV7",
    "RootCauseStageV7",
    "FixStageV7",
    "VerifyStageV7",
    "RegressionTestStageV7",
    "SiblingHuntStageV7",
    "DocumentationStageV7",
    "PatternStage",
    "HypothesisTracker",
    "AdaptiveFixPlanner",
    "PipelineStateMachine",
    "StageStateMachine",
    # Legacy (Phase 3) — compatibility only
    "ReproduceStage",
    "RootCauseStage",
    "FixStage",
    "VerifyStage",
    "RegressionTestStage",
    "SiblingHuntStage",
    "DocumentationStage",
]
