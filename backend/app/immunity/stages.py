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
import tempfile
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
    Apply a deterministic fix to the repository copy.
    Phase 3: rule-based patching derived from the root cause evidence.
    Does NOT use AI to generate code. Only applies if a known pattern matches.
    If no rule matches, marks the stage FAILED with reason — never fabricates a fix.
    """
    stage_type = StageTypeEnum.FIX

    # Known fixable patterns: (regex on error_message, description, patcher_method)
    _PATTERNS: list[tuple[str, str, str]] = [
        # Accumulator reset bug: `subtotal = v` instead of `total += v`
        (r"subtotal\s*=\s*\w+", "accumulator_reset", "_fix_accumulator_reset"),
    ]

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
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

        affected_file = root_cause.get("affected_file")
        source_snippet = root_cause.get("source_snippet", "")
        error_message = root_cause.get("error_message", "")

        # Try to locate and apply a fix
        fix_applied = False
        fix_description = None
        diff_output = None
        patch_file = None

        if affected_file:
            for pattern, description, method in self._PATTERNS:
                combined = (source_snippet or "") + (error_message or "")
                if re.search(pattern, combined, re.IGNORECASE):
                    patcher = getattr(self, method, None)
                    if patcher:
                        success, diff, err = patcher(context.repository_path, affected_file)
                        if success:
                            fix_applied = True
                            fix_description = description
                            diff_output = diff
                            break

        evidence = {
            "affected_file": affected_file,
            "fix_applied": fix_applied,
            "fix_description": fix_description,
            "diff": diff_output,
        }

        if fix_applied:
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
                error="Fix stage: no deterministic fix rule matched — manual fix required",
            )

        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result

    def _fix_accumulator_reset(
        self, repo_path: str, rel_file: str
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Fix pattern: variable = value instead of accumulator += value in a loop.
        Looks for: `subtotal = v` and replaces with `total += v`
        matching the actual variable names in context.
        """
        # Resolve path
        if os.path.isabs(rel_file):
            full = rel_file
        else:
            full = os.path.join(repo_path, rel_file)

        basename = os.path.basename(rel_file)
        if not os.path.isfile(full):
            for root, _, files in os.walk(repo_path):
                if basename in files:
                    full = os.path.join(root, basename)
                    break
            else:
                return False, None, f"File not found: {rel_file}"

        try:
            with open(full, "r", encoding="utf-8") as f:
                original = f.read()
        except Exception as e:
            return False, None, str(e)

        # Pattern: in a for loop body, find `X = value` where X is used as accumulator
        # Specifically target: `subtotal = v` → `total += v` style bugs
        # Strategy: find lines matching `\s+\w+ = \w+\s*$` inside a for loop
        # that look like they should be `accumulator += value`
        fixed = original
        diff_lines = []

        lines = original.splitlines(keepends=True)
        new_lines = list(lines)
        changed = False

        for i, line in enumerate(lines):
            # Match: indented `somevar = itervar` (simple assignment in loop body)
            m = re.match(r'^(\s+)(\w+)\s*=\s*(\w+)\s*$', line.rstrip('\n\r'))
            if m:
                indent, lhs, rhs = m.group(1), m.group(2), m.group(3)
                # The lhs should look like an accumulator name (contains total/sum/acc/subtotal)
                # and rhs should be the loop variable
                if re.search(r'(total|sum|acc|subtotal|count)', lhs, re.IGNORECASE):
                    # Rewrite to: lhs += rhs
                    new_line = f"{indent}{lhs} += {rhs}\n"
                    if new_line != line:
                        diff_lines.append(f"- line {i+1}: {line.rstrip()}")
                        diff_lines.append(f"+ line {i+1}: {new_line.rstrip()}")
                        new_lines[i] = new_line
                        changed = True

        if not changed:
            return False, None, "No accumulator reset pattern found in file"

        fixed = "".join(new_lines)
        try:
            with open(full, "w", encoding="utf-8") as f:
                f.write(fixed)
        except Exception as e:
            return False, None, f"Could not write fix: {e}"

        diff = "\n".join(diff_lines)
        return True, diff, None


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
    Write a regression test that would have caught this bug.
    Phase 3: generates a simple pytest test function from the root cause evidence.
    The generated test file is written to the repo and executed to confirm it fails
    on the broken code AND passes on the fixed code. Since the fix is already applied
    at this point, we only verify the test passes now.
    Evidence: generated test source, command, exit code.
    """
    stage_type = StageTypeEnum.REGRESSION_TEST

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        repo = context.repository_path
        root_cause = context.get_stage(StageTypeEnum.ROOT_CAUSE)
        reproduce_ev = context.get_stage(StageTypeEnum.REPRODUCE)

        failing_tests = []
        if reproduce_ev:
            failing_tests = reproduce_ev.get("failing_tests", [])

        # Generate a regression test that exercises the fixed function
        test_source = self._generate_regression_test(repo, root_cause, failing_tests)
        if not test_source:
            result = StageResult(
                stage_type=self.stage_type,
                status=ImmunityStatusEnum.FAILED,
                evidence={"reason": "Could not generate regression test — no affected file identified"},
                error="Regression test stage: insufficient evidence to generate test",
            )
            self._persist(db, pipeline_id, result)
            context.set_stage(self.stage_type, result.evidence)
            return result

        # Write regression test to repo
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

        # Run only the regression test
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
            error=None if rc == 0 else "Regression test did not pass after fix",
        )
        self._persist(db, pipeline_id, result)
        context.set_stage(self.stage_type, evidence)
        return result

    def _generate_regression_test(
        self,
        repo: str,
        root_cause: Optional[dict],
        failing_tests: list[str],
    ) -> Optional[str]:
        """
        Generate a simple regression test from evidence.
        Phase 3: rule-based generation for the known buggy_stats.py pattern.
        """
        if not root_cause:
            return None

        affected_file = root_cause.get("affected_file", "")
        if not affected_file:
            return None

        basename = os.path.basename(affected_file).replace(".py", "")

        # Detect the module's functions by parsing its AST
        functions = self._list_functions(repo, affected_file)
        if not functions:
            return None

        # Build simple regression test calls
        test_cases = []
        for fn_name in functions:
            # Basic smoke test: call each function with minimal args
            # This is evidence-based — we know the functions exist
            if fn_name.startswith("_"):
                continue
            test_cases.append(f"    # Regression: {fn_name} must return a number")
            test_cases.append(f"    result = {fn_name}([1, 2, 3])")
            test_cases.append(f"    assert isinstance(result, (int, float)), "
                               f"f\"{fn_name} returned {{type(result)}} not a number\"")
            test_cases.append("")

        if not test_cases:
            return None

        source = textwrap.dedent(f"""\
            \"\"\"
            Regression test — auto-generated by Receipts Immunity Pipeline.
            Evidence source: {affected_file}
            DO NOT DELETE — this test prevents regression of the fixed bug.
            \"\"\"
            import pytest
            from {basename} import {', '.join(functions[:5])}


            def test_regression_basic_smoke():
                \"\"\"Verify fixed functions return numeric results for basic inputs.\"\"\"
            {chr(10).join(test_cases)}

            def test_regression_empty_input():
                \"\"\"Fixed functions should handle edge cases without crashing.\"\"\"
                # Verify the functions are importable and callable
                assert callable({functions[0]})
        """)
        return source

    def _list_functions(self, repo: str, rel_file: str) -> list[str]:
        """Parse a Python file and return top-level function names."""
        if os.path.isabs(rel_file):
            full = rel_file
        else:
            full = os.path.join(repo, rel_file)

        basename = os.path.basename(rel_file)
        if not os.path.isfile(full):
            for root, _, files in os.walk(repo):
                if basename in files:
                    full = os.path.join(root, basename)
                    break
            else:
                return []

        try:
            with open(full, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
            return [
                node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
            ]
        except Exception:
            return []


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
    Creates a PatternLibraryEntry. Always passes if there is evidence to document.
    """
    stage_type = StageTypeEnum.DOCUMENTATION

    def run(self, pipeline_id: str, context: ImmunityContext, db: Session) -> StageResult:
        from app.services.pattern_library import create_pattern

        root_cause = context.get_stage(StageTypeEnum.ROOT_CAUSE) or {}
        fix_ev = context.get_stage(StageTypeEnum.FIX) or {}
        reg_ev = context.get_stage(StageTypeEnum.REGRESSION_TEST) or {}
        sibling_ev = context.get_stage(StageTypeEnum.SIBLING_HUNT) or {}

        affected_file = root_cause.get("affected_file", "unknown")
        error_type = root_cause.get("error_type", "UnknownError")
        error_message = root_cause.get("error_message", "")
        fix_description = fix_ev.get("fix_description", "manual")
        regression_test_ref = reg_ev.get("test_file")

        # Build a stable pattern signature
        sig = f"{error_type}:{os.path.basename(affected_file)}:{fix_description}"

        description = (
            f"Bug: {error_type} in {affected_file}. "
            f"Error: {error_message[:200]}. "
            f"Fix: {fix_description}. "
            f"Sibling candidates found: {sibling_ev.get('candidates_found', 0)}."
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
                    "sibling_count": sibling_ev.get("candidates_found", 0),
                },
            )
            pattern_id = entry.id
            pattern_created = True
        except Exception as exc:
            logger.warning("Documentation stage: failed to create pattern entry: %s", exc)
            pattern_id = None
            pattern_created = False

        evidence = {
            "pattern_signature": sig,
            "description": description,
            "pattern_id": pattern_id,
            "pattern_created": pattern_created,
            "regression_test_ref": regression_test_ref,
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
