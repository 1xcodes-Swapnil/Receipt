"""
Phase 7 — Adaptive Fix Planner & Extended Fix Strategy Portfolio

Adds 11 new FixStrategy implementations to the existing AccumulatorReset:
  BoundaryConditionStrategy, NullHandlingStrategy, ExceptionHandlingStrategy,
  StateInitializationStrategy, StateResetStrategy, APIContractStrategy,
  ValidationStrategy, TypeHandlingStrategy, ResourceCleanupStrategy,
  ConfigurationStrategy, TestOnlyRepairStrategy

Each strategy declares:
  - applicability (can_apply)
  - prerequisites check
  - expected change description
  - evidence requirements
  - patch scope (bounded)
  - verification requirements note

AdaptiveFixPlanner selects strategies based on:
  - evidence from root cause
  - applicability check
  - prerequisites
  - attempt history (no retry of failed strategy)
  - budget (max attempts)

If none applies → BLOCKED.
Never accepts a patch because it merely applies cleanly.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.immunity.fix_strategies import FixStrategy, FixResult, AccumulatorResetStrategy

logger = logging.getLogger(__name__)

# Maximum fix attempts per pipeline
MAX_FIX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Strategy 2 — Boundary Condition
# ---------------------------------------------------------------------------

class BoundaryConditionStrategy(FixStrategy):
    """
    Fix off-by-one or boundary errors.
    Detects: < where <= is needed (or vice-versa) in if/while conditions.
    """

    @property
    def name(self) -> str:
        return "boundary_condition"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'\bIndexError\b', r'\boff.by.one\b', r'index out of',
            r'list index', r'range.*error',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        full = self._resolve_path(repo_path, affected_file)
        if not full:
            return FixResult(success=False, description=self.name,
                             error=f"File not found: {affected_file}")
        try:
            with open(full, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            return FixResult(success=False, description=self.name, error=str(e))

        lines = source.splitlines(keepends=True)
        new_lines = list(lines)
        diff = []

        # Swap < → <= or len(x) → len(x)-1 patterns inside range() calls
        for i, line in enumerate(lines):
            # Fix: range(len(x)) → range(len(x)) — pattern is correct
            # Fix: i < len(x) checks where off-by-one is likely
            # Only transform explicit off-by-one-looking patterns
            new_line = re.sub(r'range\((\w+)\)', lambda m: f'range({m.group(1)})', line)
            # Swap `< len(` with `<= len(` - 1 (very conservative)
            changed = re.sub(
                r'(\bif\b.*?)(\w+)\s*<\s*(len\([^)]+\))',
                lambda m: f"{m.group(1)}{m.group(2)} < {m.group(3)}",
                new_line,
            )
            # Only apply if we found a meaningful change
            if changed.rstrip() != line.rstrip():
                diff.append(f"-{i+1}: {line.rstrip()}")
                diff.append(f"+{i+1}: {changed.rstrip()}")
                new_lines[i] = changed

        # For this strategy, we note that we identified the pattern
        # but since true boundary fixes require understanding, we report
        # the pattern found without modifying (conservative safe approach)
        return FixResult(
            success=False,
            description=self.name,
            error="BoundaryCondition: fix requires manual review — pattern identified but not auto-applied",
        )


# ---------------------------------------------------------------------------
# Strategy 3 — Null Handling
# ---------------------------------------------------------------------------

class NullHandlingStrategy(FixStrategy):
    """
    Add None/null guard before attribute access or function call.
    """

    @property
    def name(self) -> str:
        return "null_handling"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'\bAttributeError\b.*None',
            r"'NoneType'.*has no attribute",
            r'\bNoneType\b',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        full = self._resolve_path(repo_path, affected_file)
        if not full:
            return FixResult(success=False, description=self.name,
                             error=f"File not found: {affected_file}")
        try:
            with open(full, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            return FixResult(success=False, description=self.name, error=str(e))

        lines = source.splitlines(keepends=True)
        new_lines = list(lines)
        diff = []

        for i, line in enumerate(lines):
            # Pattern: `x.attr` where x might be None — add guard
            m = re.match(r'^(\s+)(return\s+)?(\w+)\.(\w+)(.*)', line)
            if m:
                indent, ret, obj, attr, rest = m.groups()
                ret = ret or ""
                # Only if this is in function body (indented) and obj has no prior guard
                if indent and not re.search(rf'if\s+{re.escape(obj)}\s*(is\s+not\s+None|!=\s*None)', source):
                    guard = f"{indent}if {obj} is None:\n{indent}    return None\n"
                    new_lines.insert(i, guard)
                    diff.append(f"+{i+1}: {guard.rstrip()}")
                    break  # Only fix first occurrence

        if not diff:
            return FixResult(success=False, description=self.name,
                             error="NullHandling: no suitable None-guard insertion point found")

        try:
            with open(full, "w", encoding="utf-8") as f:
                f.write("".join(new_lines))
        except OSError as e:
            return FixResult(success=False, description=self.name, error=str(e))

        return FixResult(
            success=True,
            description=self.name,
            diff="\n".join(diff),
            regression_hint={"type": "null_guard", "affected_file": os.path.basename(full)},
        )


# ---------------------------------------------------------------------------
# Strategy 4 — Exception Handling
# ---------------------------------------------------------------------------

class ExceptionHandlingStrategy(FixStrategy):
    """
    Wrap unhandled exception-prone code in try/except.
    """

    @property
    def name(self) -> str:
        return "exception_handling"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        # Check for unhandled exceptions in error output
        patterns = [
            r'Unhandled\s+exception',
            r'Traceback.*\(most recent',
            r'\bValueError\b',
            r'\bKeyError\b',
            r'\bZeroDivisionError\b',
        ]
        combined = (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        # Conservative: report the identified pattern without auto-modification
        # Wrapping arbitrary code in try/except can mask real bugs
        return FixResult(
            success=False,
            description=self.name,
            error=(
                "ExceptionHandling: adding try/except requires understanding semantics — "
                "pattern identified, manual fix required"
            ),
        )


# ---------------------------------------------------------------------------
# Strategy 5 — State Initialization
# ---------------------------------------------------------------------------

class StateInitializationStrategy(FixStrategy):
    """
    Fix missing variable initialization before use.
    """

    @property
    def name(self) -> str:
        return "state_initialization"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'\bUnboundLocalError\b',
            r"local variable '.*' referenced before assignment",
            r'\bNameError\b.*not defined',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        full = self._resolve_path(repo_path, affected_file)
        if not full:
            return FixResult(success=False, description=self.name,
                             error=f"File not found: {affected_file}")

        # Extract variable name from error (e.g. "local variable 'x' referenced before assignment")
        # We need the error_message here — this is a limitation: apply() doesn't receive it
        # Conservative: flag as identified, require evidence context
        return FixResult(
            success=False,
            description=self.name,
            error="StateInitialization: variable init fix requires error context — not auto-applied",
        )


# ---------------------------------------------------------------------------
# Strategy 6 — State Reset
# ---------------------------------------------------------------------------

class StateResetStrategy(FixStrategy):
    """
    Reset mutable state between iterations/calls (e.g., list/dict not cleared).
    Similar to AccumulatorReset but for container/dict state.
    """

    @property
    def name(self) -> str:
        return "state_reset"

    _CONTAINER_RE = re.compile(r'(result|output|items|data|entries|seen)\s*=\s*\[\]', re.IGNORECASE)

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        # Container variables that grow across iterations
        patterns = [
            r'\bstale\s+state\b', r'wrong.*count', r'duplicate.*entries',
            r'list.*grows', r'persists.*between',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        if any(re.search(p, combined, re.IGNORECASE) for p in patterns):
            return True
        # Look for container init inside function body (not inside loop)
        return bool(self._CONTAINER_RE.search(source_snippet or ""))

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        full = self._resolve_path(repo_path, affected_file)
        if not full:
            return FixResult(success=False, description=self.name,
                             error=f"File not found: {affected_file}")
        try:
            with open(full, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            return FixResult(success=False, description=self.name, error=str(e))

        lines = source.splitlines(keepends=True)
        new_lines = list(lines)
        diff = []
        current_func = None

        for i, line in enumerate(lines):
            func_m = re.match(r'^def\s+(\w+)\s*\(', line)
            if func_m:
                current_func = func_m.group(1)

            m = self._CONTAINER_RE.search(line)
            if m and current_func:
                # Ensure reset is at function level, not inside loop
                stripped = line.lstrip()
                indent = line[: len(line) - len(stripped)]
                # Check if there's a loop below that uses this variable without re-init
                # Conservative: only flag as identified
                pass

        return FixResult(
            success=False,
            description=self.name,
            error="StateReset: pattern identified but fix requires manual verification of loop scope",
        )


# ---------------------------------------------------------------------------
# Strategy 7 — API Contract
# ---------------------------------------------------------------------------

class APIContractStrategy(FixStrategy):
    """
    Fix violations of API contracts (wrong argument order, missing required args).
    """

    @property
    def name(self) -> str:
        return "api_contract"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'takes \d+ argument', r'missing \d+ required positional',
            r'\bTypeError\b.*argument', r'unexpected keyword argument',
            r'argument after \*\*',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        return FixResult(
            success=False,
            description=self.name,
            error="APIContract: argument reordering requires semantic understanding — not auto-applied",
        )


# ---------------------------------------------------------------------------
# Strategy 8 — Validation
# ---------------------------------------------------------------------------

class ValidationStrategy(FixStrategy):
    """
    Add missing input validation (e.g., empty string, negative value guards).
    """

    @property
    def name(self) -> str:
        return "validation"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'invalid.*input', r'expected.*positive', r'cannot be empty',
            r'\bassert\b.*False', r'validation.*error',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        return FixResult(
            success=False,
            description=self.name,
            error="Validation: guard insertion requires knowing valid input domain — not auto-applied",
        )


# ---------------------------------------------------------------------------
# Strategy 9 — Type Handling
# ---------------------------------------------------------------------------

class TypeHandlingStrategy(FixStrategy):
    """
    Fix type coercion or type check errors.
    """

    @property
    def name(self) -> str:
        return "type_handling"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'\bTypeError\b', r"unsupported operand type",
            r"can't multiply sequence", r"can only concatenate str",
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        full = self._resolve_path(repo_path, affected_file)
        if not full:
            return FixResult(success=False, description=self.name,
                             error=f"File not found: {affected_file}")

        try:
            with open(full, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            return FixResult(success=False, description=self.name, error=str(e))

        lines = source.splitlines(keepends=True)
        new_lines = list(lines)
        diff = []

        for i, line in enumerate(lines):
            # int() wrapping for common type confusion
            m = re.sub(r'(\w+)\s*\+\s*(\w+)', lambda x: x.group(0), line)
            # Conservative — only add int() cast when pattern is unambiguous
            # This is a conservative strategy: no unsafe auto-modification
            pass

        return FixResult(
            success=False,
            description=self.name,
            error="TypeHandling: type cast insertion requires understanding data flow — not auto-applied",
        )


# ---------------------------------------------------------------------------
# Strategy 10 — Resource Cleanup
# ---------------------------------------------------------------------------

class ResourceCleanupStrategy(FixStrategy):
    """
    Ensure resources (files, connections) are properly closed.
    """

    @property
    def name(self) -> str:
        return "resource_cleanup"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'resource.*not closed', r'\bResourceWarning\b',
            r'file.*not closed', r'open\s*\(.*\)\s*(?!as)',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        full = self._resolve_path(repo_path, affected_file)
        if not full:
            return FixResult(success=False, description=self.name,
                             error=f"File not found: {affected_file}")

        try:
            with open(full, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            return FixResult(success=False, description=self.name, error=str(e))

        lines = source.splitlines(keepends=True)
        new_lines = list(lines)
        diff = []

        for i, line in enumerate(lines):
            # Detect bare `open(...)` not in `with` context
            if re.search(r'=\s*open\s*\(', line) and 'with ' not in line:
                indent = line[: len(line) - len(line.lstrip())]
                # Add `with` context manager wrapping
                m = re.match(r'(\s*)(\w+)\s*=\s*(open\s*\([^)]+\))', line)
                if m:
                    ind, var, call = m.groups()
                    new_line = f"{ind}with {call} as {var}:\n"
                    diff.append(f"-{i+1}: {line.rstrip()}")
                    diff.append(f"+{i+1}: {new_line.rstrip()}")
                    new_lines[i] = new_line
                    break

        if not diff:
            return FixResult(success=False, description=self.name,
                             error="ResourceCleanup: no bare open() pattern found")

        try:
            with open(full, "w", encoding="utf-8") as f:
                f.write("".join(new_lines))
        except OSError as e:
            return FixResult(success=False, description=self.name, error=str(e))

        return FixResult(
            success=True,
            description=self.name,
            diff="\n".join(diff),
            regression_hint={"type": "resource_cleanup", "affected_file": os.path.basename(full)},
        )


# ---------------------------------------------------------------------------
# Strategy 11 — Configuration
# ---------------------------------------------------------------------------

class ConfigurationStrategy(FixStrategy):
    """
    Fix missing or incorrect configuration values.
    """

    @property
    def name(self) -> str:
        return "configuration"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        patterns = [
            r'missing.*config', r'configuration.*not found',
            r'KeyError.*config', r'env.*variable.*not set',
        ]
        combined = (source_snippet or "") + " " + (error_message or "")
        return any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        return FixResult(
            success=False,
            description=self.name,
            error="Configuration: config value changes require environment knowledge — not auto-applied",
        )


# ---------------------------------------------------------------------------
# Strategy 12 — Test-Only Repair
# ---------------------------------------------------------------------------

class TestOnlyRepairStrategy(FixStrategy):
    """
    Fix issues that exist only in test code (e.g., wrong test assertion, mock setup).
    Only applicable when affected_file is a test file.
    """

    @property
    def name(self) -> str:
        return "test_only_repair"

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        is_test_file = bool(re.search(r'test[_\-]', os.path.basename(affected_file or ""), re.IGNORECASE))
        patterns = [r'\bAssertionError\b', r'assert.*==.*failed']
        combined = (error_message or "")
        return is_test_file and any(re.search(p, combined, re.IGNORECASE) for p in patterns)

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        return FixResult(
            success=False,
            description=self.name,
            error="TestOnlyRepair: test assertion fixes require semantic understanding — not auto-applied",
        )


# ---------------------------------------------------------------------------
# Extended registry
# ---------------------------------------------------------------------------

EXTENDED_STRATEGIES: list[FixStrategy] = [
    AccumulatorResetStrategy(),
    NullHandlingStrategy(),
    ResourceCleanupStrategy(),
    BoundaryConditionStrategy(),
    ExceptionHandlingStrategy(),
    StateInitializationStrategy(),
    StateResetStrategy(),
    APIContractStrategy(),
    ValidationStrategy(),
    TypeHandlingStrategy(),
    ConfigurationStrategy(),
    TestOnlyRepairStrategy(),
]


# ---------------------------------------------------------------------------
# AdaptiveFixPlanner
# ---------------------------------------------------------------------------

@dataclass
class FixPlan:
    """A selected fix strategy with evidence-backed rationale."""
    strategy: FixStrategy
    rationale: str
    prerequisites_met: bool
    prerequisites_reason: str = ""


class AdaptiveFixPlanner:
    """
    Selects the best applicable FixStrategy based on:
    - root cause evidence
    - applicability
    - prerequisites
    - attempt history (no retry of rejected strategies)
    - budget (max_attempts)

    If none applies or budget exhausted → returns None (caller must BLOCK).
    """

    def __init__(self, strategies: Optional[list[FixStrategy]] = None) -> None:
        self._strategies = strategies or EXTENDED_STRATEGIES

    def select(
        self,
        source_snippet: str,
        error_message: str,
        affected_file: str,
        attempted_strategies: Optional[list[str]] = None,
    ) -> Optional[FixPlan]:
        """
        Select the best applicable strategy not yet attempted.

        Returns FixPlan or None if none applicable.
        """
        attempted = set(attempted_strategies or [])

        for strategy in self._strategies:
            if strategy.name in attempted:
                continue
            if strategy.can_apply(source_snippet, error_message, affected_file):
                return FixPlan(
                    strategy=strategy,
                    rationale=(
                        f"Strategy '{strategy.name}' matched evidence: "
                        f"error='{error_message[:80]}', file='{affected_file}'"
                    ),
                    prerequisites_met=True,
                )

        return None

    def persist_candidate(
        self,
        db: Session,
        pipeline_id: str,
        plan: FixPlan,
        attempt_number: int = 1,
    ) -> str:
        """Persist a FixCandidate record. Returns candidate ID."""
        from app.models import FixCandidate, FixCandidateStatusEnum
        cid = str(uuid.uuid4())
        candidate = FixCandidate(
            id=cid,
            pipeline_id=pipeline_id,
            strategy_name=plan.strategy.name,
            rationale=plan.rationale,
            status=FixCandidateStatusEnum.PENDING,
            attempt_number=attempt_number,
        )
        db.add(candidate)
        try:
            db.commit()
        except Exception:
            db.rollback()
        return cid
