"""Test Runner agent — executes the repository's existing test suite."""
from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

from app.agents.base import AgentEvidence, BaseAgent


# Test framework detection: (detection_file, command)
_FRAMEWORK_PROBES = [
    ("pytest.ini", ["pytest", "-v", "--tb=short"]),
    ("pyproject.toml", ["pytest", "-v", "--tb=short"]),
    ("setup.cfg", ["pytest", "-v", "--tb=short"]),
    ("package.json", ["npm", "test", "--", "--watchAll=false"]),
    ("Makefile", ["make", "test"]),
]

_DEFAULT_PYTHON_CMD = ["pytest", "-v", "--tb=short"]
_TIMEOUT_SECONDS = 120


class TestRunner(BaseAgent):
    """
    Runs the repository's existing test suite and captures real output.

    Invariants:
    - Never invents test results.
    - If execution fails, returns result="ERROR" or "TIMEOUT".
    - Real stdout/stderr required for evidence.
    """

    @property
    def agent_type(self) -> str:
        return "test_runner"

    def run(self, repository_path: str, commit: Optional[str] = None) -> AgentEvidence:
        repo_path = os.path.abspath(repository_path)

        if not os.path.isdir(repo_path):
            return AgentEvidence(
                agent=self.agent_type,
                command=None,
                result="ERROR",
                evidence=f"Repository path does not exist: {repo_path}",
                severity="CRITICAL",
                confidence=0.0,
                title="Test Runner — Repository Not Found",
            )

        command = self._detect_command(repo_path)
        command_str = " ".join(command)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            captured = (exc.stdout or "") + (exc.stderr or "")
            return AgentEvidence(
                agent=self.agent_type,
                command=command_str,
                result="TIMEOUT",
                evidence=captured or f"Process timed out after {_TIMEOUT_SECONDS}s",
                severity="HIGH",
                confidence=0.0,
                duration_ms=elapsed,
                title="Test Runner — Timeout",
            )
        except Exception as exc:  # pragma: no cover
            elapsed = int((time.monotonic() - start) * 1000)
            return AgentEvidence(
                agent=self.agent_type,
                command=command_str,
                result="ERROR",
                evidence=f"Agent exception: {exc}",
                severity="CRITICAL",
                confidence=0.0,
                duration_ms=elapsed,
                title="Test Runner — Execution Error",
            )

        elapsed = int((time.monotonic() - start) * 1000)
        combined_output = self._build_output(proc)

        if proc.returncode == 0:
            return AgentEvidence(
                agent=self.agent_type,
                command=command_str,
                result="PASS",
                evidence=combined_output,
                exit_code=proc.returncode,
                severity="PASS",
                confidence=1.0,
                duration_ms=elapsed,
                title="Test Runner — All Tests Pass",
            )
        else:
            return AgentEvidence(
                agent=self.agent_type,
                command=command_str,
                result="FAIL",
                evidence=combined_output,
                exit_code=proc.returncode,
                severity="HIGH",
                confidence=1.0,
                duration_ms=elapsed,
                title="Test Runner — Tests Failed",
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_command(self, repo_path: str) -> list[str]:
        """Return the best test command for this repository."""
        for probe_file, command in _FRAMEWORK_PROBES:
            if os.path.exists(os.path.join(repo_path, probe_file)):
                return command
        # Default: try pytest
        return _DEFAULT_PYTHON_CMD

    @staticmethod
    def _build_output(proc: subprocess.CompletedProcess) -> str:
        """Combine stdout and stderr into a single evidence string."""
        parts = []
        if proc.stdout and proc.stdout.strip():
            parts.append(proc.stdout)
        if proc.stderr and proc.stderr.strip():
            parts.append("--- stderr ---\n" + proc.stderr)
        return "\n".join(parts) if parts else f"(exit code {proc.returncode}, no output)"
