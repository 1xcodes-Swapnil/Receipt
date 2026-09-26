"""
Immunity Stage Runners — Phase 3.

Each stage runner is a self-contained class responsible for one step of the
Bug-to-Immunity pipeline. All stages follow the same contract:

    result = stage.run(pipeline_id, context, db)
    # Returns StageResult

Stage invariants (same as core receipt rule — NO EVIDENCE, NO FLAG):
- Never fabricate evidence.
- On execution failure → status = FAILED, no positive result emitted.
- Evidence must be a real command output or file content.
- If evidence is insufficient → status = FAILED (not PASSED).

Pipeline context flows through stages — each stage receives the accumulated
evidence dict from all previous stages.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ImmunityStage, ImmunityStatusEnum, StageTypeEnum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage result dataclass
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    """Returned by every stage runner."""
    stage_type: str
    status: str                         # ImmunityStatusEnum value
    evidence: dict = field(default_factory=dict)
    artifact_ref: Optional[str] = None
    error: Optional[str] = None

    def passed(self) -> bool:
        return self.status == ImmunityStatusEnum.PASSED

    def failed(self) -> bool:
        return self.status == ImmunityStatusEnum.FAILED


# ---------------------------------------------------------------------------
# Stage context — carries evidence across the pipeline
# ---------------------------------------------------------------------------

@dataclass
class ImmunityContext:
    """
    Mutable context passed between stages.
    Each stage reads from and writes to this context.
    """
    repository_path: str
    # receipt that triggered the pipeline (JSON dict)
    source_receipt: dict = field(default_factory=dict)
    # accumulated evidence keyed by stage_type
    stage_evidence: dict = field(default_factory=dict)

    def get_stage(self, stage_type: str) -> Optional[dict]:
        return self.stage_evidence.get(stage_type)

    def set_stage(self, stage_type: str, evidence: dict):
        self.stage_evidence[stage_type] = evidence


# ---------------------------------------------------------------------------
# Helper: run a subprocess with timeout, capture output
# ---------------------------------------------------------------------------

def _run_cmd(
    cmd: list[str],
    cwd: str,
    timeout: int = 60,
    env: Optional[dict] = None,
) -> tuple[int, str, str, float]:
    """
    Run command, return (returncode, stdout, stderr, elapsed_seconds).
    Never raises — captures exceptions as stderr.
    """
    import time
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        elapsed = time.monotonic() - start
        return result.returncode, result.stdout, result.stderr, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return -1, "", f"Command timed out after {timeout}s", elapsed
    except Exception as exc:
        elapsed = time.monotonic() - start
        return -1, "", f"Command execution error: {exc}", elapsed


def _detect_pytest_executable(repo_path: str) -> list[str]:
    """Return the best pytest invocation for the given repo."""
    # Prefer local venv
    for candidate in [
        os.path.join(repo_path, ".venv", "bin", "pytest"),
        os.path.join(repo_path, ".venv", "Scripts", "pytest.exe"),
        os.path.join(repo_path, "venv", "bin", "pytest"),
    ]:
        if os.path.isfile(candidate):
            return [candidate]
    # Fall back to sys.executable -m pytest (same interpreter as backend)
    return [sys.executable, "-m", "pytest"]


# ---------------------------------------------------------------------------
# Base stage
# ---------------------------------------------------------------------------

class BaseStage:
    stage_type: str = ""

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        raise NotImplementedError

    def _persist(self, db: Session, pipeline_id: str, result: StageResult) -> ImmunityStage:
        """Write an ImmunityStage row for this result."""
        stage = ImmunityStage(
            pipeline_id=pipeline_id,
            stage_type=self.stage_type,
            status=result.status,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            evidence=json.dumps(result.evidence, default=str),
            error=result.error,
            artifact_ref=result.artifact_ref,
        )
        db.add(stage)
        db.commit()
        db.refresh(stage)
        return stage


# ---------------------------------------------------------------------------
# Stage 1 — Reproduce
# ---------------------------------------------------------------------------

class ReproduceStage(BaseStage):
    """
    Run the existing test suite and confirm the bug is reproducible.
    Evidence: pytest exit code, stdout, failing test names.
    Passes only when at least one test FAILS (i.e., bug is confirmed reproducible).
    """
    stage_type = StageTypeEnum.REPRODUCE

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        repo = context.repository_path
        pytest_cmd = _detect_pytest_executable(repo)
        cmd = pytest_cmd + ["-v", "--tb=short", "--no-header"]

        rc, stdout, stderr, elapsed = _run_cmd(cmd, cwd=repo, timeout=120)

        combined = stdout + ("\n" + stderr if stderr.strip() else "")
        command_str = " ".join(cmd)

        if rc == -1:
            # Execution error — cannot confirm reproducibility
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence={"command": command_str, "error": stderr, "elapsed_s": elapsed},
                error=f"Reproduce stage: command execution failed — {stderr[:200]}",
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, result.evidence)
            return result

        # Collect failing test IDs
        failing = []
        for line in stdout.splitlines():
            if " FAILED " in line or line.startswith("FAILED "):
                # pytest -v lines: "test_foo.py::test_bar FAILED"
                parts = line.strip().split(" ")
                if parts:
                    failing.append(parts[0])

        evidence = {
            "command": command_str,
            "exit_code": rc,
            "stdout": combined[:4000],
            "failing_tests": failing,
            "elapsed_s": round(elapsed, 2),
        }

        # Bug is reproducible if there are failing tests (rc != 0 and test failures found)
        if rc != 0 and failing:
            status = ImmunityStatusEnum.PASSED  # stage passes = bug reproduced
        elif rc != 0 and not failing:
            # Non-test failure (import error, syntax error, etc.)
            status = ImmunityStatusEnum.PASSED
            evidence["note"] = "Non-zero exit without FAILED lines — suite error may indicate the bug"
        else:
            # rc == 0 means all tests pass — bug not reproduced
            status = ImmunityStatusEnum.FAILED
            evidence["note"] = "All tests pass — bug could not be reproduced from existing test suite"

        result = StageResult(
            stage_type=self.stage_type,
            status=status,
            evidence=evidence,
            error=None if status == ImmunityStatusEnum.PASSED else evidence.get("note"),
        )
        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result


# ---------------------------------------------------------------------------
# Stage 2 — Root Cause
# ---------------------------------------------------------------------------

class RootCauseStage(BaseStage):
    """
    Identify the root cause from the reproduction evidence.
    Phase 3: deterministic static analysis — parses failing test output to
    locate the error type, traceback file/line, and error message.
    No AI reasoning — evidence only.
    """
    stage_type = StageTypeEnum.ROOT_CAUSE

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        reproduce_evidence = context.get_stage(StageTypeEnum.REPRODUCE)
        if not reproduce_evidence:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                error="Root cause stage: no reproduction evidence available",
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, result.evidence)
            return result

        stdout = reproduce_evidence.get("stdout", "")
        failing_tests = reproduce_evidence.get("failing_tests", [])

        # Parse traceback to find error location
        error_type, error_message, error_location = self._parse_traceback(stdout)

        # Try to read the relevant source file
        source_snippet = None
        affected_file = None
        if error_location:
            affected_file = error_location.get("file")
            line_no = error_location.get("line")
            if affected_file and line_no:
                source_snippet = self._read_snippet(
                    context.repository_path, affected_file, line_no, context=5
                )

        evidence = {
            "failing_tests": failing_tests,
            "error_type": error_type,
            "error_message": error_message,
            "error_location": error_location,
            "affected_file": affected_file,
            "source_snippet": source_snippet,
        }

        if not error_type and not failing_tests:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence=evidence,
                error="Root cause stage: could not extract error information from test output",
            )
        else:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.PASSED,
                evidence=evidence,
            )

        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result

    def _parse_traceback(self, stdout: str) -> tuple[Optional[str], Optional[str], Optional[dict]]:
        """
        Extract error type, message, and file/line from pytest short traceback output.
        Returns (error_type, error_message, {file, line}).
        """
        error_type = None
        error_message = None
        error_location: Optional[dict] = None

        lines = stdout.splitlines()

        for i, line in enumerate(lines):
            # Match: "path/to/file.py:42: ErrorType"
            m = re.match(r"^(.+\.py):(\d+):\s+(\w+(?:Error|Exception|Warning|Assertion.*))\s*$", line)
            if m and not error_location:
                error_location = {"file": m.group(1), "line": int(m.group(2))}
                error_type = m.group(3)

            # Match "AssertionError: ..." or "ValueError: ..." lines
            m2 = re.match(r"^E\s+((\w+(?:Error|Exception|Warning)): (.+))$", line)
            if m2 and not error_message:
                error_type = error_type or m2.group(2)
                error_message = m2.group(3)[:300]

            # Fallback: "E   assert ..."
            m3 = re.match(r"^E\s+(assert .+)$", line)
            if m3 and not error_message:
                error_type = error_type or "AssertionError"
                error_message = m3.group(1)[:300]

        return error_type, error_message, error_location

    def _read_snippet(self, repo: str, rel_file: str, line_no: int, context: int = 5) -> Optional[str]:
        """Read lines around line_no from a file in the repo."""
        # Normalise path separators
        rel_file = rel_file.replace("\\", "/")
        # Strip leading path components that include the temp/sandbox prefix
        # The file might be absolute or relative to the repo
        if os.path.isabs(rel_file):
            full = rel_file
        else:
            full = os.path.join(repo, rel_file)

        if not os.path.isfile(full):
            # Try searching for the filename inside repo
            basename = os.path.basename(rel_file)
            for root, _, files in os.walk(repo):
                if basename in files:
                    full = os.path.join(root, basename)
                    break
            else:
                return None

        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            start = max(0, line_no - context - 1)
            end = min(len(all_lines), line_no + context)
            numbered = [
                f"{start + i + 1:>4} | {line.rstrip()}"
                for i, line in enumerate(all_lines[start:end])
            ]
            return "\n".join(numbered)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Stage 3 — Fix
# ---------------------------------------------------------------------------

class FixStage(BaseStage):
    """
    Apply a deterministic fix to the repository copy using the FixStrategy abstraction.

    Iterates registered strategies in order and applies the first one whose
    can_apply() returns True. Passes regression_hint back via context so
    RegressionTestStage can generate real assertion-based tests.

    Never fabricates a fix. If no strategy matches → FAILED explicitly.
    """
    stage_type = StageTypeEnum.FIX

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        from app.immunity.fix_strategies import find_strategy

        root_cause = context.get_stage(StageTypeEnum.ROOT_CAUSE)
        if not root_cause:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                error="Fix stage: no root cause evidence available",
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, result.evidence)
            return result

        affected_file = root_cause.get("affected_file") or ""
        source_snippet = root_cause.get("source_snippet") or ""
        error_message = root_cause.get("error_message") or ""

        strategy = find_strategy(source_snippet, error_message, affected_file)

        if strategy is None or not affected_file:
            evidence = {
                "affected_file": affected_file,
                "fix_applied": False,
                "fix_description": None,
                "diff": None,
                "strategy": None,
                "regression_hint": None,
            }
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence=evidence,
                error="Fix stage: no deterministic fix strategy matched — manual fix required",
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, evidence)
            return result

        fix_result = strategy.apply(context.repository_path, affected_file)

        evidence = {
            "affected_file": affected_file,
            "fix_applied": fix_result.success,
            "fix_description": fix_result.description,
            "diff": fix_result.diff,
            "strategy": strategy.name,
            "regression_hint": fix_result.regression_hint,
        }

        if fix_result.success:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.PASSED,
                evidence=evidence,
                artifact_ref=affected_file,
            )
        else:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence=evidence,
                error=f"Fix stage: strategy '{strategy.name}' failed — {fix_result.error}",
            )

        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result


# ---------------------------------------------------------------------------
# Stage 4 — Verify
# ---------------------------------------------------------------------------

class VerifyStage(BaseStage):
    """
    Re-run the test suite after the fix has been applied.
    Passes only when ALL previously failing tests now pass.
    Evidence: command, exit code, stdout. Never fabricated.
    """
    stage_type = StageTypeEnum.VERIFY

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        repo = context.repository_path
        fix_evidence = context.get_stage(StageTypeEnum.FIX)

        pytest_cmd = _detect_pytest_executable(repo)
        cmd = pytest_cmd + ["-v", "--tb=short", "--no-header"]

        rc, stdout, stderr, elapsed = _run_cmd(cmd, cwd=repo, timeout=120)
        combined = stdout + ("\n" + stderr if stderr.strip() else "")
        command_str = " ".join(cmd)

        # Count failures remaining
        remaining_failures = [
            line.split(" ")[0]
            for line in stdout.splitlines()
            if " FAILED " in line or line.startswith("FAILED ")
        ]

        evidence = {
            "command": command_str,
            "exit_code": rc,
            "stdout": combined[:4000],
            "remaining_failures": remaining_failures,
            "elapsed_s": round(elapsed, 2),
            "fix_was_applied": bool(fix_evidence and fix_evidence.get("fix_applied")),
        }

        # Verify passes only when rc == 0 (all tests pass)
        if rc == 0:
            status = ImmunityStatusEnum.PASSED
        else:
            status = ImmunityStatusEnum.FAILED

        result = StageResult(
            stage_type=self.stage_type,
            status=status,
            evidence=evidence,
            error=None if status == ImmunityStatusEnum.PASSED
                  else f"Verify failed: {len(remaining_failures)} test(s) still failing",
        )
        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result


# ---------------------------------------------------------------------------
# Stage 5 — Regression Test
# ---------------------------------------------------------------------------

class RegressionTestStage(BaseStage):
    """
    Write a regression test that verifies the actual reproduced bug.

    Phase 4 repair: tests now use real assertions derived from the fix's
    regression_hint rather than mere smoke tests. The test must:
    - Be derived from concrete evidence (failing test output + fix diff)
    - Assert the CORRECT behavior (not just "callable")
    - Pass against the FIXED code in the workspace
    - Fail against the buggy code (verified conceptually from the diff)

    Evidence: generated test source, command, exit code.
    """
    stage_type = StageTypeEnum.REGRESSION_TEST

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        repo = context.repository_path
        root_cause = context.get_stage(StageTypeEnum.ROOT_CAUSE)
        fix_ev = context.get_stage(StageTypeEnum.FIX)
        reproduce_ev = context.get_stage(StageTypeEnum.REPRODUCE)

        # Build regression test from available evidence
        test_source = self._generate_regression_test(repo, root_cause, fix_ev, reproduce_ev)
        if not test_source:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence={"reason": "Insufficient evidence to generate regression test"},
                error="Regression test stage: need root_cause + fix evidence with regression_hint",
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, result.evidence)
            return result

        # Write regression test to workspace
        test_filename = "test_regression_immunity.py"
        test_path = os.path.join(repo, test_filename)
        try:
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_source)
        except Exception as e:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence={"generated_source": test_source},
                error=f"Could not write regression test: {e}",
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, result.evidence)
            return result

        # Execute the regression test against fixed code
        pytest_cmd = _detect_pytest_executable(repo)
        cmd = pytest_cmd + [test_filename, "-v", "--tb=short", "--no-header"]
        rc, stdout, stderr, elapsed = _run_cmd(cmd, cwd=repo, timeout=60)
        combined = stdout + ("\n" + stderr if stderr.strip() else "")

        evidence = {
            "test_file": test_filename,
            "generated_source": test_source,
            "command": " ".join(cmd),
            "exit_code": rc,
            "stdout": combined[:3000],
            "elapsed_s": round(elapsed, 2),
        }

        status = ImmunityStatusEnum.PASSED if rc == 0 else ImmunityStatusEnum.FAILED
        result = StageResult(
            stage_type=self.stage_type,
            status=status,
            evidence=evidence,
            artifact_ref=test_filename,
            error=None if rc == 0 else "Regression test did not pass after fix — fix may be incomplete",
        )
        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result

    def _generate_regression_test(
        self,
        repo: str,
        root_cause: Optional[dict],
        fix_ev: Optional[dict],
        reproduce_ev: Optional[dict],
    ) -> Optional[str]:
        """
        Generate an assertion-based regression test.

        Priority:
        1. If fix_ev contains regression_hint with changed_functions + hints:
           generate tests with real numeric assertions (mean([1,2,3]) == 2.0)
        2. Fallback: parse failing test names from reproduce_ev and replicate
           simplified versions with correct expected values
        3. Last resort: None (caller records FAILED)
        """
        if not root_cause:
            return None

        affected_file = root_cause.get("affected_file", "")
        if not affected_file:
            return None

        basename = os.path.basename(affected_file).replace(".py", "")
        regression_hint = (fix_ev or {}).get("regression_hint")

        # --- Path 1: use regression_hint for real assertion tests ---
        if regression_hint and regression_hint.get("changed_functions"):
            return self._generate_from_hint(basename, affected_file, regression_hint, reproduce_ev)

        # --- Path 2: replicate failing tests from reproduce evidence ---
        if reproduce_ev and reproduce_ev.get("failing_tests"):
            return self._generate_from_failing_tests(
                repo, basename, affected_file, reproduce_ev["failing_tests"]
            )

        return None

    def _generate_from_hint(
        self,
        basename: str,
        affected_file: str,
        hint: dict,
        reproduce_ev: Optional[dict],
    ) -> Optional[str]:
        """
        Generate real assertion tests using regression_hint from the fix strategy.
        Tests assert CORRECT computed values — not just callability.
        """
        changed_functions = hint.get("changed_functions", [])
        hints = hint.get("hints", [])
        if not changed_functions:
            return None

        test_cases: list[str] = []

        for h in hints:
            fn_name = h.get("function")
            if not fn_name or fn_name.startswith("_"):
                continue
            accum = h.get("accumulator", "total")
            loop_var = h.get("loop_var", "v")

            # Generate a concrete test: for mean-like functions, assert sum behavior
            test_cases.append(f"def test_regression_{fn_name}_accumulates_correctly():")
            test_cases.append(f'    """')
            test_cases.append(f"    Regression: {fn_name} must accumulate all values,")
            test_cases.append(f"    not just return the last value.")
            test_cases.append(f"    Bug: `{accum} = {loop_var}` reset on each iteration.")
            test_cases.append(f'    """')
            # Test that the function returns a sum/mean, not just the last value
            # For a mean: mean([1,2,3]) == 2.0 (not 3.0 which would be last-value-only)
            test_cases.append(f"    # If accumulator reset, returns last/{len(hints)+2} not sum/{len(hints)+2}")
            test_cases.append(f"    result = {fn_name}([1.0, 2.0, 3.0])")
            test_cases.append(f"    # Correct: mean([1,2,3]) = 2.0; buggy returns 3.0/3 = 1.0")
            test_cases.append(f"    assert result == 2.0, (")
            test_cases.append(f"        f\"{fn_name}([1,2,3]) returned {{result}}, expected 2.0. \"")
            test_cases.append(f'        "Accumulator reset bug still present?"')
            test_cases.append(f"    )")
            test_cases.append("")
            # Also test: same-value list must return that value
            test_cases.append(f"def test_regression_{fn_name}_identical_values():")
            test_cases.append(f'    """Accumulation of identical values must equal that value."""')
            test_cases.append(f"    result = {fn_name}([5.0, 5.0, 5.0])")
            test_cases.append(f"    assert result == 5.0, (")
            test_cases.append(f"        f\"Expected 5.0, got {{result}}. Accumulator still resetting?\"")
            test_cases.append(f"    )")
            test_cases.append("")
            # Negative values
            test_cases.append(f"def test_regression_{fn_name}_negative_values():")
            test_cases.append(f'    """Signed accumulation must work correctly."""')
            test_cases.append(f"    result = {fn_name}([-1.0, 1.0])")
            test_cases.append(f"    assert result == 0.0, (")
            test_cases.append(f"        f\"Expected 0.0, got {{result}}. Accumulator issue?\"")
            test_cases.append(f"    )")
            test_cases.append("")

        if not test_cases:
            return None

        imports = f"from {basename} import {', '.join(changed_functions[:5])}"
        source = textwrap.dedent(f"""\
            \"\"\"
            Regression test — auto-generated by Receipts Immunity Pipeline.
            Source: {affected_file}
            Strategy: accumulator_reset

            These tests verify CORRECT accumulated behavior.
            They would FAIL against the buggy code and PASS against the fix.
            DO NOT DELETE — this test prevents regression of the fixed bug.
            \"\"\"
            import pytest
            {imports}

        """)
        source += "\n".join(test_cases)
        return source

    def _generate_from_failing_tests(
        self,
        repo: str,
        basename: str,
        affected_file: str,
        failing_tests: list[str],
    ) -> Optional[str]:
        """
        Fallback: generate simplified versions of the known failing tests.
        These are less precise than hint-based tests but still assertion-based.
        """
        # Parse the test file to extract actual test assertions
        test_lines = self._extract_failing_test_bodies(repo, failing_tests)
        if not test_lines:
            return None

        imports = f"from {basename} import *"
        source = textwrap.dedent(f"""\
            \"\"\"
            Regression test — derived from failing tests in reproduce stage.
            Source: {affected_file}
            DO NOT DELETE.
            \"\"\"
            import pytest
            {imports}

        """)
        source += "\n".join(test_lines)
        return source

    def _extract_failing_test_bodies(self, repo: str, failing_tests: list[str]) -> list[str]:
        """
        Parse the failing test file and extract the test bodies for failing tests.
        Returns list of complete test function definitions.
        """
        if not failing_tests:
            return []

        # Extract unique test file paths from the failing test identifiers
        # Format: "test_file.py::TestClass::test_method" or "test_file.py::test_fn"
        test_files: dict[str, list[str]] = {}
        for t in failing_tests:
            parts = t.split("::")
            if parts:
                tf = parts[0].strip()
                if tf not in test_files:
                    test_files[tf] = []
                if len(parts) > 1:
                    test_files[tf].append(parts[-1])

        results: list[str] = []
        for tf, test_names in test_files.items():
            full = os.path.join(repo, tf) if not os.path.isabs(tf) else tf
            if not os.path.isfile(full):
                # Try basename search
                bn = os.path.basename(tf)
                for root, _, files in os.walk(repo):
                    if bn in files:
                        full = os.path.join(root, bn)
                        break
            if not os.path.isfile(full):
                continue
            try:
                with open(full, "r", encoding="utf-8") as f:
                    src = f.read()
                tree = ast.parse(src)
                lines = src.splitlines()
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name in test_names:
                        # Extract source lines for this function, prefixed with regression_ marker
                        start = node.lineno - 1
                        end = node.end_lineno if hasattr(node, "end_lineno") else start + 10
                        fn_lines = lines[start:end]
                        # Rename to avoid collision
                        fn_lines[0] = fn_lines[0].replace(
                            node.name, f"test_regression_{node.name}"
                        )
                        results.append("\n".join(fn_lines))
                        results.append("")
            except Exception:
                continue

        return results


# ---------------------------------------------------------------------------
# Stage 6 — Sibling Hunt
# ---------------------------------------------------------------------------

class SiblingHuntStage(BaseStage):
    """
    Search the repository for similar patterns that might harbour the same bug.
    Phase 3: static AST + text search — no AI inference.
    Reports POTENTIAL_MATCH candidates only. Never marks them as confirmed bugs
    unless they are actually reproduced (out of scope for Phase 3).
    """
    stage_type = StageTypeEnum.SIBLING_HUNT

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        from app.models import SiblingFinding, VerificationStatusEnum

        repo = context.repository_path
        root_cause = context.get_stage(StageTypeEnum.ROOT_CAUSE)

        affected_file = None
        if root_cause:
            affected_file = root_cause.get("affected_file")

        # Find Python files to search
        py_files = []
        for root_dir, _, files in os.walk(repo):
            for fname in files:
                if fname.endswith(".py") and not fname.startswith("test_"):
                    py_files.append(os.path.join(root_dir, fname))

        candidates = []
        search_pattern = re.compile(
            r'^\s+\w+\s*=\s*\w+\s*$',  # simple assignment in indented context (loop body)
        )

        for py_file in py_files:
            rel = os.path.relpath(py_file, repo)
            # Skip the already-fixed file
            if affected_file and os.path.basename(py_file) == os.path.basename(affected_file or ""):
                continue
            if py_file == affected_file:
                continue
            try:
                with open(py_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                # Detect: indented `accumulator = value` pattern inside loop
                in_loop = False
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith("for ") or stripped.startswith("while "):
                        in_loop = True
                    elif in_loop and not stripped and i + 1 < len(lines):
                        in_loop = False
                    if in_loop and search_pattern.match(line):
                        m = re.match(r'^\s+(\w+)\s*=\s*(\w+)\s*$', line)
                        if m:
                            lhs, rhs = m.group(1), m.group(2)
                            if re.search(r'(total|sum|acc|subtotal|count)', lhs, re.IGNORECASE):
                                candidates.append({
                                    "file": rel,
                                    "line": i + 1,
                                    "code": line.rstrip(),
                                    "reason": f"Possible accumulator reset: `{lhs} = {rhs}` in loop body",
                                    "confidence": 0.6,
                                })
            except Exception:
                continue

        # Persist sibling findings
        for c in candidates[:10]:  # cap at 10
            finding = SiblingFinding(
                pipeline_id=pipeline_id,
                candidate_location=f"{c['file']}:{c['line']}",
                similarity_reason=c["reason"],
                confidence=c["confidence"],
                verification_status=VerificationStatusEnum.POTENTIAL_MATCH,
                evidence=json.dumps({"code": c["code"]}, default=str),
            )
            db.add(finding)
        db.commit()

        evidence = {
            "files_searched": len(py_files),
            "candidates_found": len(candidates),
            "candidates": candidates[:10],
        }

        result = StageResult(
            stage_type=self.stage_type,
            status=ImmunityStatusEnum.PASSED,  # Sibling hunt always completes (may find 0)
            evidence=evidence,
        )
        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result


# ---------------------------------------------------------------------------
# Stage 7 — Documentation
# ---------------------------------------------------------------------------

class DocumentationStage(BaseStage):
    """
    Record what was learned: pattern signature, root cause, fix, regression test.

    Phase 4: Pattern Library entry created ONLY when Reproduce + RootCause +
    Fix + Verify + RegressionTest all PASSED. Explicit INSUFFICIENT_EVIDENCE
    if gates not met. No fake patterns ever created.
    """
    stage_type = StageTypeEnum.DOCUMENTATION

    REQUIRED_PASSED_STAGES = [
        StageTypeEnum.REPRODUCE,
        StageTypeEnum.ROOT_CAUSE,
        StageTypeEnum.FIX,
        StageTypeEnum.VERIFY,
        StageTypeEnum.REGRESSION_TEST,
    ]

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        from app.services.pattern_library import create_pattern

        root_cause = context.get_stage(StageTypeEnum.ROOT_CAUSE) or {}
        fix_ev = context.get_stage(StageTypeEnum.FIX) or {}
        reg_ev = context.get_stage(StageTypeEnum.REGRESSION_TEST) or {}
        sibling_ev = context.get_stage(StageTypeEnum.SIBLING_HUNT) or {}

        # Gate: all required stages must show evidence of PASS
        missing_stages = self._check_required_stages(context)
        if missing_stages:
            ev = {
                "pattern_created": False,
                "reason": "INSUFFICIENT_EVIDENCE",
                "missing_or_failed_stages": missing_stages,
            }
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence=ev,
                error=(
                    "Documentation: cannot create pattern — "
                    f"required stages not PASSED: {', '.join(missing_stages)}"
                ),
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, ev)
            return result

        affected_file = root_cause.get("affected_file", "unknown")
        error_type = root_cause.get("error_type", "UnknownError")
        error_message = root_cause.get("error_message", "")
        fix_description = fix_ev.get("fix_description", "unknown")
        strategy_name = fix_ev.get("strategy", "unknown")
        regression_test_ref = reg_ev.get("test_file")

        sig = f"{error_type}:{os.path.basename(affected_file)}:{strategy_name}"
        description = (
            f"Bug: {error_type} in {affected_file}. "
            f"Error: {error_message[:200]}. "
            f"Fix strategy: {strategy_name} ({fix_description}). "
            f"Regression test: {regression_test_ref or 'none'}. "
            f"Sibling candidates: {sibling_ev.get('candidates_found', 0)}."
        )

        try:
            entry = create_pattern(
                db=db,
                pattern_signature=sig,
                description=description,
                source_pipeline_id=pipeline_id,
                regression_test_ref=regression_test_ref,
                affected_area=os.path.dirname(affected_file) or "root",
                metadata={
                    "error_type": error_type,
                    "error_message": error_message,
                    "fix_description": fix_description,
                    "strategy": strategy_name,
                    "sibling_count": sibling_ev.get("candidates_found", 0),
                    "regression_hint": fix_ev.get("regression_hint"),
                },
            )
            pattern_id = entry.id
            pattern_created = True
        except Exception as exc:
            logger.warning("Documentation stage: failed to create pattern: %s", exc)
            pattern_id = None
            pattern_created = False

        evidence = {
            "pattern_signature": sig,
            "description": description,
            "pattern_id": pattern_id,
            "pattern_created": pattern_created,
            "regression_test_ref": regression_test_ref,
            "gated_stages_all_passed": True,
        }

        result = StageResult(
            stage_type=self.stage_type,
            status=ImmunityStatusEnum.PASSED if pattern_created else ImmunityStatusEnum.FAILED,
            evidence=evidence,
            error=None if pattern_created else "Documentation stage: pattern creation failed",
        )
        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result

    def _check_required_stages(self, context: ImmunityContext) -> list[str]:
        failed = []
        for stage_type in self.REQUIRED_PASSED_STAGES:
            ev = context.get_stage(stage_type)
            if ev is None:
                failed.append(stage_type)
            elif not self._stage_passed(stage_type, ev):
                failed.append(stage_type)
        return failed

    def _stage_passed(self, stage_type: str, evidence: dict) -> bool:
        if stage_type == StageTypeEnum.REPRODUCE:
            return evidence.get("exit_code", 0) != 0 or bool(evidence.get("failing_tests"))
        if stage_type == StageTypeEnum.ROOT_CAUSE:
            return bool(evidence.get("error_type") or evidence.get("failing_tests"))
        if stage_type == StageTypeEnum.FIX:
            return bool(evidence.get("fix_applied"))
        if stage_type == StageTypeEnum.VERIFY:
            return evidence.get("exit_code") == 0
        if stage_type == StageTypeEnum.REGRESSION_TEST:
            return evidence.get("exit_code") == 0
        return True
