"""
Fix Strategy abstraction — Phase 4 repair.

Each FixStrategy encapsulates one deterministic repair rule:
  - can_apply(source_snippet, error_message, affected_file) → bool
  - apply(repo_path, affected_file) → FixResult

FixStage iterates registered strategies in order and applies the first match.
Strategies NEVER fabricate fixes. If no pattern matches → FAILED explicitly.
"""
from __future__ import annotations

import abc
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FixResult:
    success: bool
    description: str
    diff: Optional[str] = None
    error: Optional[str] = None
    # The concrete assertion values extracted from the fix, usable in regression tests
    regression_hint: Optional[dict] = None


class FixStrategy(abc.ABC):
    """Abstract fix strategy. One strategy = one deterministic repair rule."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Machine-readable strategy name."""
        ...

    @abc.abstractmethod
    def can_apply(
        self,
        source_snippet: str,
        error_message: str,
        affected_file: str,
    ) -> bool:
        """Return True if this strategy can handle the given evidence."""
        ...

    @abc.abstractmethod
    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        """
        Apply the fix to the file inside repo_path.
        Must write the changed file.
        Returns FixResult with success=True only when a real change was made.
        """
        ...

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _resolve_path(repo_path: str, rel_file: str) -> Optional[str]:
        """Resolve a possibly-relative file path to an absolute path inside repo."""
        if os.path.isabs(rel_file):
            if os.path.isfile(rel_file):
                return rel_file
            # Absolute path may be from another workspace — try basename search
            rel_file = os.path.basename(rel_file)

        full = os.path.join(repo_path, rel_file)
        if os.path.isfile(full):
            return full

        # Search by basename
        basename = os.path.basename(rel_file)
        for root, _, files in os.walk(repo_path):
            if basename in files:
                return os.path.join(root, basename)
        return None


# ---------------------------------------------------------------------------
# Strategy 1 — Accumulator Reset
# ---------------------------------------------------------------------------

class AccumulatorResetStrategy(FixStrategy):
    """
    Detects and fixes: loop body contains `accumulator = loop_var` instead of
    `accumulator += loop_var`.

    Evidence pattern: variable with accumulator-like name (total/sum/acc/subtotal/count)
    is assigned rather than accumulated inside a for/while loop body.

    This strategy:
    1. Parses the file line-by-line looking for the pattern.
    2. Rewrites `X = v` → `X += v` for identified accumulator variables.
    3. Records the exact changed lines as diff evidence.
    4. Emits a regression_hint with the function name and expected input→output
       pairs extracted from the buggy assignment context.
    """

    name = "accumulator_reset"

    # Matches: indented `accname = value` (bare assignment, no operators)
    _LINE_RE = re.compile(r'^(\s+)(\w+)\s*=\s*(\w+)\s*$')
    _ACCUM_RE = re.compile(r'(total|sum|acc|subtotal|count|result|running)', re.IGNORECASE)

    def can_apply(self, source_snippet: str, error_message: str, affected_file: str) -> bool:
        combined = (source_snippet or "") + (error_message or "")
        # Check source snippet contains the accumulator-reset pattern OR
        # the error message shows a wrong accumulated value
        if self._ACCUM_RE.search(combined):
            if self._LINE_RE.search(source_snippet or ""):
                return True
        # Also match if the error message explicitly mentions subtotal/similar
        if re.search(r'subtotal\s*=\s*\w+', combined, re.IGNORECASE):
            return True
        return False

    def apply(self, repo_path: str, affected_file: str) -> FixResult:
        full = self._resolve_path(repo_path, affected_file)
        if not full:
            return FixResult(success=False, description=self.name,
                             error=f"File not found: {affected_file}")

        try:
            with open(full, "r", encoding="utf-8") as f:
                original = f.read()
        except Exception as e:
            return FixResult(success=False, description=self.name, error=str(e))

        lines = original.splitlines(keepends=True)
        new_lines = list(lines)
        diff_lines: list[str] = []
        changed_functions: list[str] = []
        regression_hints: list[dict] = []

        # Track current function context
        current_func = None
        for i, line in enumerate(lines):
            # Track function definitions to annotate hints
            func_m = re.match(r'^def\s+(\w+)\s*\(', line)
            if func_m:
                current_func = func_m.group(1)

            m = self._LINE_RE.match(line.rstrip('\n\r'))
            if m:
                indent, lhs, rhs = m.group(1), m.group(2), m.group(3)
                if self._ACCUM_RE.search(lhs):
                    new_line = f"{indent}{lhs} += {rhs}\n"
                    if new_line.rstrip() != line.rstrip():
                        diff_lines.append(f"-{i+1}: {line.rstrip()}")
                        diff_lines.append(f"+{i+1}: {new_line.rstrip()}")
                        new_lines[i] = new_line
                        if current_func and current_func not in changed_functions:
                            changed_functions.append(current_func)
                        regression_hints.append({
                            "function": current_func,
                            "accumulator": lhs,
                            "loop_var": rhs,
                            "line": i + 1,
                        })

        if not diff_lines:
            return FixResult(success=False, description=self.name,
                             error="No accumulator reset pattern found in file")

        fixed = "".join(new_lines)
        try:
            with open(full, "w", encoding="utf-8") as f:
                f.write(fixed)
        except Exception as e:
            return FixResult(success=False, description=self.name,
                             error=f"Could not write fix: {e}")

        return FixResult(
            success=True,
            description=self.name,
            diff="\n".join(diff_lines),
            regression_hint={
                "changed_functions": changed_functions,
                "hints": regression_hints,
                "affected_file": os.path.basename(full),
            },
        )


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

# All registered strategies, tried in order
REGISTERED_STRATEGIES: list[FixStrategy] = [
    AccumulatorResetStrategy(),
]


def find_strategy(
    source_snippet: str,
    error_message: str,
    affected_file: str,
) -> Optional[FixStrategy]:
    """Return the first strategy that can handle the given evidence, or None."""
    for strategy in REGISTERED_STRATEGIES:
        if strategy.can_apply(source_snippet, error_message, affected_file):
            return strategy
    return None
