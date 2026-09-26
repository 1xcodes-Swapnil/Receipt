"""
Strategy base interface and registry.

BaseStrategy  — interface all strategies must implement
StrategyResult — what a strategy execution returns
StrategyRegistry — registry for looking up strategies by name
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot


# ---------------------------------------------------------------------------
# StrategyResult
# ---------------------------------------------------------------------------

@dataclass
class StrategyResult:
    """
    The result of executing a strategy.

    result          : PASS | FAIL | INSUFFICIENT | ERROR
    evidence_items  : list of raw evidence dicts to be converted to Evidence objects
    claims_addressed: list of claim IDs this strategy addresses
    confidence      : 0.0–1.0
    raw_output      : combined stdout/stderr
    command         : command that was run (if any)
    """
    result: str
    evidence_items: list[dict] = field(default_factory=list)
    claims_addressed: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_output: str = ""
    command: Optional[str] = None
    file_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# BaseStrategy
# ---------------------------------------------------------------------------

class BaseStrategy(abc.ABC):
    """
    All strategies must implement this interface.

    name : unique identifier (snake_case)
    cost : 1-10 scale (lower = cheaper to run first)
    """

    name: str = "base"
    cost: int = 5

    @abc.abstractmethod
    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        """Return True if this strategy can be applied to the snapshot."""
        ...

    def prerequisites_met(self, snapshot: "RepositorySnapshot", context: dict) -> tuple[bool, str]:
        """
        Check if prerequisites are satisfied.
        Returns (True, "") if met, or (False, reason) if not.
        Default: always met.
        """
        return True, ""

    @abc.abstractmethod
    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        """
        Execute the strategy and return a StrategyResult.

        Must NEVER fabricate evidence.
        Must return result=ERROR on exception.
        """
        ...


# ---------------------------------------------------------------------------
# StrategyRegistry
# ---------------------------------------------------------------------------

class StrategyRegistry:
    """Simple registry for looking up strategies by name."""

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> Optional[BaseStrategy]:
        return self._strategies.get(name)

    def all(self) -> list[BaseStrategy]:
        return list(self._strategies.values())

    def sorted_by_cost(self) -> list[BaseStrategy]:
        return sorted(self._strategies.values(), key=lambda s: s.cost)
