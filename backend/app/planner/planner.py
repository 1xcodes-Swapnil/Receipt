"""
StrategyPlanner — deterministic adaptive planner for evidence collection.

Selection algorithm:
1. Analyze snapshot → identify claim types (via ChangeFailureAnalyzer)
2. For each claim, find applicable strategies sorted by (cost, expected_value)
3. Execute cheapest applicable strategy first
4. Evaluate evidence gap after each execution
5. If gap filled → mark claim resolved
6. If gap remains → try next strategy
7. Stop when: all claims resolved OR budget exhausted OR diminishing returns
8. Return evidence as AgentEvidence objects for existing verdict engine

Budget: max 5 strategies per review, max 120s total

NO external LLM. Deterministic. Same input → same output.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.agents.base import AgentEvidence
from app.evidence.claims import Claim, Evidence, EvidenceLedger
from app.evidence.sufficiency import EvidenceSufficiencyEvaluator, EvidenceGapAnalyzer
from app.planner.analyzer import ChangeFailureAnalyzer
from app.planner.trace import PlannerDecision, StrategyTrace
from app.strategies.base import BaseStrategy, StrategyRegistry

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)

# Planner budget
MAX_STRATEGIES = 5
MAX_ELAPSED_SECONDS = 120

# Advisory strategy names — their FAIL result is never authoritative
_ADVISORY_STRATEGIES = {"documentation_analysis", "history_analysis"}

# Phase 6 advanced strategy names — expensive, skip unless evidence gap remains
_ADVANCED_STRATEGIES = {
    "property_based_testing",
    "mutation_testing",
    "fault_localization",
    "metamorphic_testing",
    "fuzzing",
    "counterexample_shrinking",
    "semantic_sibling_analysis",
}

# Phase 6 advanced strategies max budget (separate from base 5)
MAX_STRATEGIES_WITH_ADVANCED = 9


def _strategy_result_to_agent_evidence(
    strategy_name: str,
    claim: Optional[Claim],
    strat_result,
) -> AgentEvidence:
    """
    Convert a StrategyResult into an AgentEvidence for the existing verdict engine.

    Advisory strategies: their FAIL is preserved but the agent name maps
    to "documentation_check" so _calculate_verdict() treats it correctly.
    """
    # Map strategy name to agent name for verdict calculation
    strategy_to_agent = {
        "existing_tests": "test_runner",
        "differential_testing": "catching_test",
        "documentation_analysis": "documentation_check",
        "history_analysis": "history_check",
        "change_impact": "change_impact",
        "static_ast": "static_ast",
        "targeted_testing": "targeted_testing",
        # Phase 6 strategies
        "property_based_testing": "test_runner",
        "mutation_testing": "catching_test",
        "fault_localization": "test_runner",
        "metamorphic_testing": "catching_test",
        "fuzzing": "test_runner",
        "counterexample_shrinking": "catching_test",
        "semantic_sibling_analysis": "documentation_check",
    }
    agent_name = strategy_to_agent.get(strategy_name, strategy_name)

    # Map strategy result to agent result
    result_map = {
        "PASS": "PASS",
        "FAIL": "FAIL",
        "INSUFFICIENT": "INSUFFICIENT_EVIDENCE",
        "ERROR": "ERROR",
        "CONFLICT": "INSUFFICIENT_EVIDENCE",
    }
    agent_result = result_map.get(strat_result.result, "INSUFFICIENT_EVIDENCE")

    title = f"{strategy_name} — {strat_result.result}"
    if claim:
        title = f"{strategy_name} [{claim.claim_type}] — {strat_result.result}"

    return AgentEvidence(
        agent=agent_name,
        command=strat_result.command,
        result=agent_result,
        evidence=strat_result.raw_output or "",
        confidence=strat_result.confidence,
        file_ref=strat_result.file_ref,
        title=title,
    )


class StrategyPlanner:
    """
    Deterministic adaptive planner.

    plan()             → list of PlannerDecisions (dry-run, no execution)
    execute_adaptive() → execute strategies, return AgentEvidence list
    """

    def __init__(self, registry: Optional[StrategyRegistry] = None) -> None:
        if registry is None:
            from app.strategies import build_default_registry
            registry = build_default_registry()
        self._registry = registry
        self._analyzer = ChangeFailureAnalyzer()
        self._sufficiency = EvidenceSufficiencyEvaluator()
        self._gap_analyzer = EvidenceGapAnalyzer()

    def plan(
        self,
        snapshot: "RepositorySnapshot",
        claims: list[Claim],
        available_strategies: list[BaseStrategy],
        budget: int = MAX_STRATEGIES,
    ) -> list[PlannerDecision]:
        """
        Dry-run: produce a plan without executing anything.

        Returns list of PlannerDecisions in execution order.
        """
        decisions: list[PlannerDecision] = []
        attempted: set[str] = set()
        step = 0

        # Sort by cost ascending (cheapest first)
        sorted_strategies = sorted(available_strategies, key=lambda s: s.cost)

        # For each authoritative claim, find the cheapest applicable strategy
        for claim in claims:
            if claim.verdict_contribution == "NONE":
                continue
            if step >= budget:
                break
            for strategy in sorted_strategies:
                if strategy.name in attempted:
                    continue
                if not strategy.is_applicable(snapshot, {}):
                    continue
                prereq_ok, prereq_reason = strategy.prerequisites_met(snapshot, {})
                decision = PlannerDecision.create(
                    step_number=step,
                    strategy_name=strategy.name,
                    selection_reason=f"Cheapest applicable for claim '{claim.claim_type}'",
                    claim_id=claim.claim_id,
                    prerequisites_met=prereq_ok,
                )
                decisions.append(decision)
                attempted.add(strategy.name)
                step += 1
                break  # one strategy per claim in the plan

        return decisions

    def execute_adaptive(
        self,
        snapshot: "RepositorySnapshot",
        db: Optional[Session],
        run_id: str,
    ) -> list[AgentEvidence]:
        """
        Execute strategies adaptively and return AgentEvidence objects
        for the existing verdict engine.

        Persists EvidenceItem, ReviewClaim, EvidenceGap, StrategyTraceEntry
        to the DB if db is provided.
        """
        trace = StrategyTrace.create(run_id)
        ledger = EvidenceLedger()
        claims = self._analyzer.analyze(snapshot)

        # Persist claims
        if db is not None:
            self._persist_claims(db, run_id, claims)

        attempted_strategies: list[str] = []
        agent_evidences: list[AgentEvidence] = []
        start_time = time.monotonic()
        step = 0

        sorted_strategies = self._registry.sorted_by_cost()

        for strategy in sorted_strategies:
            # Advanced Phase 6 strategies only run when there are evidence gaps
            # and we are within the extended budget
            if strategy.name in _ADVANCED_STRATEGIES:
                if step >= MAX_STRATEGIES_WITH_ADVANCED:
                    trace.stopping_reason = "budget_exhausted"
                    trace.budget_exhausted = True
                    break
                # Skip advanced strategy if no gaps remain
                current_gaps = self._gap_analyzer.find_gaps(
                    ledger, claims, attempted_strategies
                )
                if not current_gaps:
                    decision = PlannerDecision.create(
                        step_number=step,
                        strategy_name=strategy.name,
                        selection_reason="Skipped: no evidence gaps remain",
                        prerequisites_met=True,
                    )
                    decision.execution_result = "SKIPPED"
                    decision.stopping_reason = "no_gaps_remaining"
                    trace.add_decision(decision)
                    attempted_strategies.append(strategy.name)
                    continue
            elif step >= MAX_STRATEGIES:
                trace.stopping_reason = "budget_exhausted"
                trace.budget_exhausted = True
                break

            elapsed = time.monotonic() - start_time
            if elapsed > MAX_ELAPSED_SECONDS:
                trace.stopping_reason = "time_budget_exhausted"
                trace.budget_exhausted = True
                break

            if strategy.name in attempted_strategies:
                continue

            if not strategy.is_applicable(snapshot, {}):
                continue

            prereq_ok, prereq_reason = strategy.prerequisites_met(snapshot, {})

            decision = PlannerDecision.create(
                step_number=step,
                strategy_name=strategy.name,
                selection_reason=self._select_reason(strategy, claims, ledger),
                prerequisites_met=prereq_ok,
            )

            if not prereq_ok:
                decision.execution_result = "SKIPPED"
                decision.stopping_reason = f"Prerequisites not met: {prereq_reason}"
                trace.add_decision(decision)
                attempted_strategies.append(strategy.name)
                step += 1
                continue

            # Execute
            decision.started_at = datetime.utcnow()
            strat_result = strategy.execute(snapshot, {})
            decision.completed_at = datetime.utcnow()
            decision.execution_result = strat_result.result
            attempted_strategies.append(strategy.name)

            # Add evidence to ledger
            is_advisory = strategy.name in _ADVISORY_STRATEGIES
            # Find applicable claims for this strategy
            applicable_claims = self._find_applicable_claims(strategy, claims)
            claim_id = applicable_claims[0].claim_id if applicable_claims else None

            evidence = Evidence.create(
                strategy_name=strategy.name,
                claim_id=claim_id,
                result=strat_result.result if strat_result.result != "INSUFFICIENT" else "INSUFFICIENT",
                confidence=strat_result.confidence,
                raw_output=strat_result.raw_output or "",
                command=strat_result.command,
                file_ref=strat_result.file_ref,
                is_independent=not is_advisory,
            )
            ledger.add(evidence)
            decision.evidence_item_id = evidence.evidence_id

            # Persist evidence item
            if db is not None:
                self._persist_evidence_item(db, run_id, evidence, strategy.name)

            # Convert to AgentEvidence for the existing verdict engine
            agent_ev = _strategy_result_to_agent_evidence(
                strategy.name, applicable_claims[0] if applicable_claims else None, strat_result
            )
            agent_evidences.append(agent_ev)

            # Persist trace entry
            if db is not None:
                self._persist_trace_entry(db, run_id, step, decision)

            trace.add_decision(decision)
            step += 1

            # Check if all authoritative claims are resolved
            if self._sufficiency.is_sufficient(ledger, claims):
                trace.all_claims_resolved = True
                trace.stopping_reason = "all_claims_resolved"
                break

            # Check if diminishing returns (all remaining strategies would not help)
            gaps = self._gap_analyzer.find_gaps(ledger, claims, attempted_strategies)
            if not gaps:
                trace.stopping_reason = "no_gaps_remaining"
                break

        # If nothing was produced, escalate
        if not agent_evidences:
            agent_evidences.append(AgentEvidence(
                agent="test_runner",
                command=None,
                result="INSUFFICIENT_EVIDENCE",
                evidence="Adaptive planner produced no evidence.",
                confidence=0.0,
                title="Adaptive Planner — No Evidence",
            ))

        # Persist gaps
        if db is not None:
            gaps = self._gap_analyzer.find_gaps(ledger, claims, attempted_strategies)
            self._persist_gaps(db, run_id, gaps)

        return agent_evidences

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _select_reason(
        self, strategy: BaseStrategy, claims: list[Claim], ledger: EvidenceLedger
    ) -> str:
        applicable = self._find_applicable_claims(strategy, claims)
        if applicable:
            return f"Lowest cost strategy for claim '{applicable[0].claim_type}' (cost={strategy.cost})"
        return f"General coverage strategy (cost={strategy.cost})"

    def _find_applicable_claims(
        self, strategy: BaseStrategy, claims: list[Claim]
    ) -> list[Claim]:
        """Map strategy to applicable claims based on strategy name/type."""
        strategy_claim_map = {
            "existing_tests": ["code_correctness", "test_coverage"],
            "change_impact": ["code_correctness"],
            "differential_testing": ["code_correctness"],
            "targeted_testing": ["code_correctness", "test_coverage"],
            "static_ast": ["code_correctness"],
            "history_analysis": ["code_correctness"],
            "documentation_analysis": ["documentation"],
            # Phase 6
            "property_based_testing": ["code_correctness", "test_coverage"],
            "mutation_testing": ["test_coverage"],
            "fault_localization": ["code_correctness"],
            "metamorphic_testing": ["code_correctness"],
            "fuzzing": ["code_correctness"],
            "counterexample_shrinking": ["code_correctness"],
            "semantic_sibling_analysis": ["code_correctness"],
        }
        target_types = strategy_claim_map.get(strategy.name, ["code_correctness"])
        return [c for c in claims if c.claim_type in target_types]

    # ------------------------------------------------------------------
    # DB persistence helpers
    # ------------------------------------------------------------------

    def _persist_claims(self, db: Session, run_id: str, claims: list[Claim]) -> None:
        from app.models import ReviewClaim
        for claim in claims:
            db_claim = ReviewClaim(
                id=claim.claim_id,
                review_run_id=run_id,
                claim_type=claim.claim_type,
                claim_text=claim.claim_text,
                status=claim.status,
                verdict_contribution=claim.verdict_contribution,
            )
            db.add(db_claim)
        try:
            db.commit()
        except Exception:
            db.rollback()

    def _persist_evidence_item(
        self, db: Session, run_id: str, evidence: Evidence, strategy_name: str
    ) -> None:
        from app.models import EvidenceItem
        item = EvidenceItem(
            id=evidence.evidence_id,
            review_run_id=run_id,
            claim_id=evidence.claim_id,
            strategy_name=strategy_name,
            result=evidence.result,
            confidence=evidence.confidence,
            command=evidence.command,
            raw_output=evidence.raw_output,
            file_ref=evidence.file_ref,
            is_independent=evidence.is_independent,
            depends_on_evidence_id=evidence.depends_on,
        )
        db.add(item)
        try:
            db.commit()
        except Exception:
            db.rollback()

    def _persist_trace_entry(
        self, db: Session, run_id: str, step: int, decision: PlannerDecision
    ) -> None:
        from app.models import StrategyTraceEntry
        entry = StrategyTraceEntry(
            id=str(uuid.uuid4()),
            review_run_id=run_id,
            step_number=step,
            claim_id=decision.claim_id,
            strategy_name=decision.strategy_name,
            selection_reason=decision.selection_reason,
            prerequisites_met=decision.prerequisites_met,
            execution_result=decision.execution_result,
            evidence_item_id=decision.evidence_item_id,
            next_decision=decision.next_decision,
            stopping_reason=decision.stopping_reason,
            started_at=decision.started_at,
            completed_at=decision.completed_at,
        )
        db.add(entry)
        try:
            db.commit()
        except Exception:
            db.rollback()

    def _persist_gaps(self, db: Session, run_id: str, gaps) -> None:
        from app.models import EvidenceGap
        for gap in gaps:
            db_gap = EvidenceGap(
                review_run_id=run_id,
                claim_id=gap.claim_id,
                gap_type=gap.gap_type,
                description=gap.description,
                suggested_strategy=gap.suggested_strategy,
                resolved=False,
            )
            db.add(db_gap)
        try:
            db.commit()
        except Exception:
            db.rollback()
