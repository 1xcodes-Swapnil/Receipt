"""
Execution Sandbox — Phase 2.

Provides an isolated temporary workspace for running untrusted repository code.

Requirements:
  - Isolated checkout into a temporary directory
  - Automatic cleanup after use (context manager)
  - Timeout enforced at the subprocess level
  - Captured stdout / stderr
  - No network access enforced where practical (subprocess env stripping)
  - Resource limits applied via timeout (ulimit not available on all platforms)

Usage:
    with Sandbox(source_path) as sb:
        result = sb.run(["pytest", "-v"], timeout=60)
        print(result.stdout)
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120  # seconds


@dataclass
class SandboxResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def output(self) -> str:
        """Combined stdout + stderr for evidence."""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout)
        if self.stderr.strip():
            parts.append("--- stderr ---\n" + self.stderr)
        if not parts:
            return f"(exit code {self.exit_code}, no output)"
        return "\n".join(parts)


class Sandbox:
    """
    Context manager that creates a temporary working directory,
    optionally copies source files into it, and runs commands inside it.

    Source files are NOT executed from the original path — they are
    copied to a temp dir so the original repo is never modified.
    """

    def __init__(self, source_path: str, copy_source: bool = True):
        self.source_path = os.path.abspath(source_path)
        self.copy_source = copy_source
        self._tmpdir: Optional[str] = None

    @property
    def work_dir(self) -> str:
        if self._tmpdir is None:
            raise RuntimeError("Sandbox not entered — use as context manager")
        return self._tmpdir

    def __enter__(self) -> "Sandbox":
        self._tmpdir = tempfile.mkdtemp(prefix="receipts_sandbox_")
        if self.copy_source and os.path.isdir(self.source_path):
            dest = os.path.join(self._tmpdir, "repo")
            shutil.copytree(self.source_path, dest)
            self._work_subdir = dest
        else:
            self._work_subdir = self._tmpdir
        logger.debug("Sandbox created: %s (source: %s)", self._tmpdir, self.source_path)
        return self

    def __exit__(self, *_):
        self._cleanup()

    def _cleanup(self):
        if self._tmpdir and os.path.exists(self._tmpdir):
            try:
                shutil.rmtree(self._tmpdir, ignore_errors=True)
                logger.debug("Sandbox cleaned up: %s", self._tmpdir)
            except Exception as exc:
                logger.warning("Sandbox cleanup failed: %s", exc)
        self._tmpdir = None

    def run(
        self,
        command: list[str],
        timeout: int = _DEFAULT_TIMEOUT,
        cwd: Optional[str] = None,
        extra_env: Optional[dict] = None,
    ) -> SandboxResult:
        """
        Run a command inside the sandbox work directory.

        - stdout and stderr are captured.
        - Environment is inherited but optionally supplemented.
        - Timeout is enforced; a timed-out process is killed.
        """
        run_cwd = cwd or self._work_subdir
        env = dict(os.environ)
        # Strip proxy vars to reduce network footprint
        for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            env.pop(var, None)
        if extra_env:
            env.update(extra_env)

        cmd_str = " ".join(command)
        start = time.monotonic()

        try:
            proc = subprocess.run(
                command,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            elapsed = int((time.monotonic() - start) * 1000)
            return SandboxResult(
                command=cmd_str,
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return SandboxResult(
                command=cmd_str,
                exit_code=-1,
                stdout=(exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                stderr=(exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                duration_ms=elapsed,
                timed_out=True,
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return SandboxResult(
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=f"Sandbox run error: {exc}",
                duration_ms=elapsed,
            )
