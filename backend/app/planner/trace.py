"""
StrategyTrace and PlannerDecision — structured trace of planner decisions.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PlannerDecision:
    """
    A single decision made by the planner.

    step_number       : 0-based index in the plan
    claim_id          : which claim this decision addresses
    strategy_name     : selected strategy
    selection_reason  : why this strategy was chosen
    prerequisites_met : whether prerequisites were satisfied
    execution_result  : result after execution (PASS/FAIL/INSUFFICIENT/ERROR/None)
    evidence_item_id  : UUID of the Evidence produced (if any)
    remaining_gap     : description of remaining gap (if any)
    next_decision     : what the planner decided to do next
    stopping_reason   : why the planner stopped (if stopping)
    started_at        : when the strategy started
    completed_at      : when the strategy finished
    """
    decision_id: str
    step_number: int
    claim_id: Optional[str]
    strategy_name: str
    selection_reason: str
    prerequisites_met: bool = True
    execution_result: Optional[str] = None
    evidence_item_id: Optional[str] = None
    remaining_gap: Optional[str] = None
    next_decision: Optional[str] = None
    stopping_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def create(
        cls,
        step_number: int,
        strategy_name: str,
        selection_reason: str,
        claim_id: Optional[str] = None,
        prerequisites_met: bool = True,
    ) -> "PlannerDecision":
        return cls(
            decision_id=str(uuid.uuid4()),
            step_number=step_number,
            claim_id=claim_id,
            strategy_name=strategy_name,
            selection_reason=selection_reason,
            prerequisites_met=prerequisites_met,
            started_at=datetime.utcnow(),
        )


@dataclass
class StrategyTrace:
    """
    Full trace of all planner decisions during a review.

    Used for audit, debugging, and the /strategy-trace API endpoint.
    """
    trace_id: str
    review_run_id: str
    decisions: list[PlannerDecision] = field(default_factory=list)
    stopping_reason: Optional[str] = None
    total_strategies_run: int = 0
    budget_exhausted: bool = False
    all_claims_resolved: bool = False

    @classmethod
    def create(cls, review_run_id: str) -> "StrategyTrace":
        return cls(
            trace_id=str(uuid.uuid4()),
            review_run_id=review_run_id,
        )

    def add_decision(self, decision: PlannerDecision) -> None:
        self.decisions.append(decision)
        self.total_strategies_run += 1
