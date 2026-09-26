"""
StaticASTAnalysisStrategy — analyzes Python AST for obvious issues.

Does not execute code. Returns INSUFFICIENT when no clear bugs are found
(lack of static errors is not a PASS — tests must confirm correctness).
cost=2 (cheap, no execution).
"""
from __future__ import annotations

import ast
import logging
import os
from typing import TYPE_CHECKING

from app.strategies.base import BaseStrategy, StrategyResult

if TYPE_CHECKING:
    from app.evidence.snapshot import RepositorySnapshot

logger = logging.getLogger(__name__)


class StaticASTAnalysisStrategy(BaseStrategy):
    """
    Parse Python files and look for obvious AST-level issues.

    IMPORTANT: No tests = INSUFFICIENT, not FAIL.
    Static analysis alone cannot confirm correctness — it only finds
    obvious structural problems. Absence of static errors → INSUFFICIENT.
    """

    name = "static_ast"
    cost = 2

    def is_applicable(self, snapshot: "RepositorySnapshot", context: dict) -> bool:
        return len(snapshot.all_files) > 0

    def execute(self, snapshot: "RepositorySnapshot", context: dict) -> StrategyResult:
        try:
            repo_path = snapshot.repository_path
            py_files = list(snapshot.all_files)

            if not py_files:
                return StrategyResult(
                    result="INSUFFICIENT",
                    confidence=0.0,
                    raw_output="No Python files to analyze.",
                )

            syntax_errors: list[str] = []
            analyzed = 0

            for rel_path in py_files[:50]:  # cap at 50 files
                abs_path = os.path.join(repo_path, rel_path)
                try:
                    with open(abs_path, encoding="utf-8", errors="replace") as fh:
                        source = fh.read()
                    ast.parse(source, filename=rel_path)
                    analyzed += 1
                except SyntaxError as se:
                    syntax_errors.append(f"{rel_path}:{se.lineno}: {se.msg}")
                except OSError:
                    pass

            output_lines = [
                f"AST analysis: {analyzed} files parsed",
                f"Syntax errors: {len(syntax_errors)}",
            ]
            if syntax_errors:
                output_lines += ["", "Syntax errors found:"] + [f"  {e}" for e in syntax_errors]

            raw_output = "\n".join(output_lines)

            if syntax_errors:
                return StrategyResult(
                    result="FAIL",
                    confidence=0.95,
                    raw_output=raw_output,
                )

            # No syntax errors found — but static analysis alone cannot confirm
            # correctness. Return INSUFFICIENT so the planner tries test execution.
            return StrategyResult(
                result="INSUFFICIENT",
                confidence=0.0,
                raw_output=raw_output + "\nNo syntax errors — test execution required to confirm correctness.",
            )

        except Exception as exc:
            logger.exception("StaticASTAnalysisStrategy failed")
            return StrategyResult(
                result="ERROR",
                confidence=0.0,
                raw_output=f"Strategy exception: {exc}",
            )
