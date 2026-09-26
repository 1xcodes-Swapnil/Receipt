"""
Phase 6 Testing Infrastructure — shared utilities for advanced strategies.

Provides:
  - DeterministicSeed         : reproducible seed management
  - BoundedExecutionContext    : timeout + iteration caps
  - IsolatedWorkspace          : temp workspace with guaranteed cleanup
  - MutantCleanupRegistry     : track and clean mutated files
  - CounterexampleRecord       : store original + minimized counterexamples
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DeterministicSeed
# ---------------------------------------------------------------------------

class DeterministicSeed:
    """
    Reproducible seed derived from snapshot hash + strategy name.

    Same snapshot + same strategy → same seed → same test cases.
    """

    @staticmethod
    def for_strategy(snapshot_hash: str, strategy_name: str) -> int:
        """Derive a deterministic integer seed."""
        combined = f"{snapshot_hash}:{strategy_name}".encode()
        digest = hashlib.sha256(combined).hexdigest()
        # Use first 8 hex chars as seed (32-bit integer range)
        return int(digest[:8], 16)

    @staticmethod
    def for_iteration(base_seed: int, iteration: int) -> int:
        """Derive a per-iteration seed from a base seed."""
        return (base_seed + iteration * 6364136223846793005) & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# BoundedExecutionContext
# ---------------------------------------------------------------------------

@dataclass
class BoundedExecutionContext:
    """
    Enforces iteration and time limits for bounded strategy execution.

    max_iterations : cap on generated test cases / mutations
    max_seconds    : wall-clock timeout
    """
    max_iterations: int = 50
    max_seconds: float = 30.0

    def __post_init__(self) -> None:
        self._start = time.monotonic()
        self._count = 0
        self._timed_out = False

    def should_continue(self) -> bool:
        """Return True if execution should continue."""
        if self._count >= self.max_iterations:
            return False
        elapsed = time.monotonic() - self._start
        if elapsed >= self.max_seconds:
            self._timed_out = True
            return False
        return True

    def tick(self) -> None:
        """Record one iteration."""
        self._count += 1

    @property
    def iterations_used(self) -> int:
        return self._count

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start

    @property
    def timed_out(self) -> bool:
        return self._timed_out


# ---------------------------------------------------------------------------
# IsolatedWorkspace
# ---------------------------------------------------------------------------

class IsolatedWorkspace:
    """
    Context manager that creates an isolated temp directory and guarantees cleanup.

    Optionally copies source files. Generated artifacts cannot escape the
    workspace root because all paths are validated against the temp root.
    """

    def __init__(self, source_path: Optional[str] = None, prefix: str = "receipts_p6_"):
        self.source_path = os.path.abspath(source_path) if source_path else None
        self._prefix = prefix
        self._root: Optional[str] = None

    @property
    def root(self) -> str:
        if self._root is None:
            raise RuntimeError("IsolatedWorkspace not entered")
        return self._root

    def safe_path(self, *parts: str) -> str:
        """Join parts under workspace root; raises ValueError on traversal."""
        candidate = os.path.realpath(os.path.join(self.root, *parts))
        root_real = os.path.realpath(self.root)
        if not (candidate == root_real or candidate.startswith(root_real + os.sep)):
            raise ValueError(f"Path escape detected: {parts!r}")
        return candidate

    def __enter__(self) -> "IsolatedWorkspace":
        self._root = tempfile.mkdtemp(prefix=self._prefix)
        if self.source_path and os.path.isdir(self.source_path):
            dest = os.path.join(self._root, "source")
            shutil.copytree(self.source_path, dest, symlinks=False)
        return self

    def __exit__(self, *_) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        if self._root and os.path.exists(self._root):
            try:
                shutil.rmtree(self._root, ignore_errors=True)
            except Exception:
                pass
        self._root = None


# ---------------------------------------------------------------------------
# MutantCleanupRegistry
# ---------------------------------------------------------------------------

class MutantCleanupRegistry:
    """
    Tracks mutated files so they can be restored even on failure.

    Always call restore_all() in a finally block.
    """

    def __init__(self) -> None:
        self._originals: dict[str, str] = {}  # abs_path → original content

    def backup(self, abs_path: str) -> None:
        """Save original file content before mutation."""
        if abs_path not in self._originals:
            try:
                with open(abs_path, encoding="utf-8", errors="replace") as fh:
                    self._originals[abs_path] = fh.read()
            except OSError:
                self._originals[abs_path] = ""

    def restore_all(self) -> None:
        """Restore all backed-up files to their original content."""
        for abs_path, content in self._originals.items():
            try:
                with open(abs_path, "w", encoding="utf-8") as fh:
                    fh.write(content)
            except OSError:
                pass
        self._originals.clear()


# ---------------------------------------------------------------------------
# CounterexampleRecord
# ---------------------------------------------------------------------------

@dataclass
class CounterexampleRecord:
    """
    Records the original failing input and its minimized form.

    Both must reproduce the same failure for the record to be valid.
    """
    strategy_name: str
    property_description: str
    original_input: object
    minimized_input: object
    failure_reason: str
    seed: int
    is_minimized: bool = False

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "property_description": self.property_description,
            "original_input": repr(self.original_input),
            "minimized_input": repr(self.minimized_input) if self.is_minimized else None,
            "failure_reason": self.failure_reason,
            "seed": self.seed,
            "is_minimized": self.is_minimized,
        }
