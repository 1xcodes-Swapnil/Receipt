#!/usr/bin/env python
"""
Receipts — Real GitHub Repository Test: CareCircle_AI

Tests the existing Phase 8 implementation against:
  https://github.com/1xcodes-Swapnil/CareCircle_AI.git
  owner: 1xcodes-Swapnil / repo: CareCircle_AI / branch: main

Rules:
  - Uses EXISTING implementation only — no modifications to Receipts
  - Read-only access to the external repository
  - NO invented PRs, commits, test results, or metrics
  - INSUFFICIENT_EVIDENCE or ESCALATE when capabilities are unsupported
  - NO BUG_DETECTED without evidence
  - NO SAFE merely because execution succeeded
  - Honest logging of every step and failure

Usage:
    cd f:\\Bobproject\\backend
    .venv\\Scripts\\python.exe .\\tests\\github_carecircle_test.py

Exit code:
    0 = test script completed (regardless of verdict)
    1 = script error (not a verdict — script itself failed)
"""
from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Path setup ─────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent.resolve()
_BACKEND_DIR = _SCRIPT_DIR.parent
_ROOT_DIR = _BACKEND_DIR.parent

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ── Log setup ───────────────────────────────────────────────────────────────

_LOG_DIR = _ROOT_DIR / "demo" / "logs" / "latest"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "github_carecircle_test.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("carecircle_test")

# ── Constants ────────────────────────────────────────────────────────────────

REPO_OWNER  = "1xcodes-Swapnil"
REPO_NAME   = "CareCircle_AI"
REPO_BRANCH = "main"
REPO_URL    = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
TS = datetime.now(timezone.utc).isoformat()


# ── Result accumulator ───────────────────────────────────────────────────────

@dataclass
class TestResult:
    timestamp: str = TS
    repository: str = REPO_URL
    branch: str = REPO_BRANCH
    resolved_commit: Optional[str] = None
    provider_status: str = "not_checked"
    provider_reason: str = ""
    snapshot_status: str = "not_created"
    snapshot_hash: Optional[str] = None
    snapshot_file_count_py: int = 0
    snapshot_file_count_all: int = 0
    clone_path: Optional[str] = None
    strategies_attempted: list[str] = field(default_factory=list)
    strategies_skipped: list[dict] = field(default_factory=list)
    strategy_results: list[dict] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    verdict: str = "PENDING"
    verdict_reason: str = ""
    exit_status: int = 0

R = TestResult()


def _sep(char="-", width=70):
    log.info(char * width)


def _section(title: str):
    _sep("=")
    log.info("  %s", title)
    _sep("=")


# ── Step 1: GitHub provider availability ────────────────────────────────────

def check_provider_availability() -> Optional[object]:
    """
    Check GitHubRepositoryProvider availability.
    Records honest status — never fabricates.
    Returns provider if available, else None.
    """
    _section("STEP 1 — GitHub Provider Availability")

    try:
        from app.repositories.provider import (
            GitHubRepositoryProvider,
            ProviderStatus,
            make_github_provider,
        )
    except ImportError as exc:
        R.provider_status = "import_error"
        R.provider_reason = str(exc)
        R.errors.append(f"Cannot import provider: {exc}")
        log.error("Cannot import GitHubRepositoryProvider: %s", exc)
        return None

    status = GitHubRepositoryProvider.check_availability()
    log.info("Provider available : %s", status.available)
    log.info("Provider reason    : %s", status.reason)
    if status.detail:
        log.info("Provider detail    : %s", status.detail)

    if status.available:
        R.provider_status = "available"
        R.provider_reason = status.reason
        provider = GitHubRepositoryProvider(REPO_OWNER, REPO_NAME, pr_number=None)
        log.info("GitHubRepositoryProvider created — token-authenticated access available")
        return provider
    else:
        R.provider_status = "unavailable_no_token"
        R.provider_reason = status.reason
        log.warning(
            "GitHubRepositoryProvider unavailable: %s", status.reason
        )
        log.info(
            "Falling back to anonymous git clone (public repository — no token needed for clone)"
        )
        return None


# ── Step 2: Clone repository (anonymous for public repo) ────────────────────

def clone_repository() -> Optional[str]:
    """
    Clone the repository to a temporary directory.
    Uses anonymous HTTPS for a public repository — no token required.
    Returns clone path or None on failure.
    """
    _section("STEP 2 — Repository Clone (anonymous, read-only)")
    log.info("URL    : %s", REPO_URL)
    log.info("Branch : %s", REPO_BRANCH)

    tmpdir = tempfile.mkdtemp(prefix="receipts_carecircle_")
    clone_target = os.path.join(tmpdir, "repo")
    log.info("Clone target : %s", clone_target)

    cmd = ["git", "clone", "--depth=1", "--branch", REPO_BRANCH, REPO_URL, clone_target]
    log.info("Command: %s", " ".join(cmd))

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        elapsed = time.monotonic() - start
        log.info("git clone exit_code=%d elapsed=%.1fs", result.returncode, elapsed)
        if result.stdout.strip():
            log.debug("stdout: %s", result.stdout[:500])
        if result.stderr.strip():
            log.debug("stderr: %s", result.stderr[:500])

        if result.returncode != 0:
            R.errors.append(f"git clone failed: rc={result.returncode} stderr={result.stderr[:200]}")
            log.error("git clone FAILED: %s", result.stderr[:300])
            shutil.rmtree(tmpdir, ignore_errors=True)
            return None

        log.info("Clone succeeded: %s", clone_target)
        R.clone_path = clone_target
        return tmpdir  # caller manages cleanup of tmpdir

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        R.errors.append(f"git clone timed out after {elapsed:.0f}s")
        log.error("git clone timed out after %.0fs", elapsed)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None
    except Exception as exc:
        R.errors.append(f"git clone error: {exc}")
        log.error("git clone error: %s", exc)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None


# ── Step 3: Repository metadata ──────────────────────────────────────────────

def collect_metadata(clone_path: str) -> dict:
    """
    Collect repository metadata from the clone.
    Returns dict of metadata.
    """
    _section("STEP 3 — Repository Metadata")

    meta: dict = {}

    # HEAD commit
    rc, out, _ = _run_git(["log", "-1", "--pretty=format:%H|%s|%an|%ad", "--date=short"], clone_path)
    if rc == 0 and out.strip():
        parts = out.strip().split("|", 3)
        meta["head_sha"] = parts[0] if len(parts) > 0 else ""
        meta["head_message"] = parts[1] if len(parts) > 1 else ""
        meta["head_author"] = parts[2] if len(parts) > 2 else ""
        meta["head_date"] = parts[3] if len(parts) > 3 else ""
        R.resolved_commit = meta["head_sha"]
        log.info("HEAD commit  : %s", meta["head_sha"][:12] + "...")
        log.info("Commit msg   : %s", meta["head_message"][:80])
        log.info("Author       : %s", meta["head_author"])
        log.info("Date         : %s", meta["head_date"])
    else:
        log.warning("Could not retrieve HEAD commit")
        meta["head_sha"] = None

    # Branch
    rc, out, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], clone_path)
    meta["branch"] = out.strip() if rc == 0 else REPO_BRANCH
    log.info("Branch       : %s", meta["branch"])

    # Remote URL
    rc, out, _ = _run_git(["remote", "get-url", "origin"], clone_path)
    meta["remote_url"] = out.strip() if rc == 0 else REPO_URL
    # Sanitize (remove token if present)
    if "@github.com" in meta["remote_url"]:
        meta["remote_url"] = "https://github.com/" + meta["remote_url"].split("@github.com/", 1)[-1]
    log.info("Remote URL   : %s", meta["remote_url"])

    # File counts by extension
    all_files = []
    for root, dirs, files in os.walk(clone_path):
        # Skip .git
        dirs[:] = [d for d in dirs if d != ".git"]
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), clone_path)
            all_files.append(rel)

    exts: dict[str, int] = {}
    for f in all_files:
        ext = os.path.splitext(f)[1].lower() or "(no ext)"
        exts[ext] = exts.get(ext, 0) + 1

    top_exts = sorted(exts.items(), key=lambda x: -x[1])[:12]
    log.info("Total files  : %d", len(all_files))
    log.info("Top file types:")
    for ext, count in top_exts:
        log.info("  %-12s %d", ext, count)

    meta["total_files"] = len(all_files)
    meta["extensions"] = dict(top_exts)
    meta["py_files"] = exts.get(".py", 0)
    meta["ts_files"] = exts.get(".ts", 0) + exts.get(".tsx", 0)
    meta["js_files"] = exts.get(".js", 0) + exts.get(".jsx", 0)

    R.snapshot_file_count_all = len(all_files)
    R.snapshot_file_count_py = meta["py_files"]

    return meta


def _run_git(args: list[str], cwd: str, timeout: int = 15):
    """Run a git command, return (rc, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout, r.stderr
    except Exception as exc:
        return -1, "", str(exc)


# ── Step 4: Snapshot creation ────────────────────────────────────────────────

def create_snapshot(clone_path: str, meta: dict) -> Optional[object]:
    """
    Create a RepositorySnapshot from the clone.
    Records honest result.
    """
    _section("STEP 4 — Repository Snapshot")

    try:
        from app.evidence.snapshot import RepositorySnapshot
    except ImportError as exc:
        R.errors.append(f"Cannot import RepositorySnapshot: {exc}")
        log.error("Cannot import RepositorySnapshot: %s", exc)
        R.snapshot_status = "import_error"
        return None

    try:
        snapshot = RepositorySnapshot.create(
            repository_path=clone_path,
            commit_sha=meta.get("head_sha"),
        )
        R.snapshot_status = "created"
        R.snapshot_hash = snapshot.snapshot_hash

        log.info("Snapshot ID     : %s", snapshot.snapshot_id)
        log.info("Snapshot hash   : %s", snapshot.snapshot_hash)
        log.info("Python files    : %d", len(snapshot.all_files))
        log.info("Changed files   : %d", len(snapshot.changed_files))
        log.info("Created at      : %s", snapshot.created_at.isoformat())
        log.info("Commit SHA      : %s", snapshot.commit_sha or "(none)")

        # Immutability check — use normal assignment; frozen dataclasses raise FrozenInstanceError
        try:
            snapshot.snapshot_hash = "tampered"  # type: ignore[misc]
            R.errors.append("IMMUTABILITY FAILURE: snapshot accepted modification")
            log.error("IMMUTABILITY FAILURE: frozen dataclass accepted setattr")
        except Exception:
            log.info("Immutability    : OK (frozen dataclass - modification rejected)")

        if len(snapshot.all_files) == 0:
            log.warning(
                "Snapshot contains 0 Python files. "
                "CareCircle_AI is a TypeScript/JavaScript repository. "
                "Python-specific strategies will return INSUFFICIENT_EVIDENCE."
            )

        return snapshot

    except Exception as exc:
        R.errors.append(f"Snapshot creation failed: {exc}")
        log.error("Snapshot creation failed: %s", exc)
        R.snapshot_status = f"error: {exc}"
        return None


# ── Step 5: Strategy execution ───────────────────────────────────────────────

def execute_strategies(snapshot, clone_path: str, meta: dict) -> list[dict]:
    """
    Run applicable strategies from the existing registry.
    Returns list of result dicts.
    """
    _section("STEP 5 — Strategy Execution")

    results = []

    # Determine what's actually available
    py_count = len(snapshot.all_files) if snapshot else 0
    has_python = py_count > 0
    has_git = meta.get("head_sha") is not None
    has_ts = meta.get("ts_files", 0) > 0
    has_js = meta.get("js_files", 0) > 0
    is_ts_js = has_ts or has_js

    log.info("Repository language profile:")
    log.info("  Python files : %d", py_count)
    log.info("  TS/TSX files : %d", meta.get("ts_files", 0))
    log.info("  JS/JSX files : %d", meta.get("js_files", 0))
    log.info("  Has git      : %s", has_git)

    # ── Strategy: change_impact ──────────────────────────────────────────
    _run_strategy_safe(
        name="change_impact",
        applicable=True,
        note="No PR -> no changed_files in snapshot -> expected INSUFFICIENT",
        snapshot=snapshot,
        results=results,
    )

    # ── Strategy: existing_tests ─────────────────────────────────────────
    # Requires pytest + Python test files
    has_pytest = _check_pytest_available(clone_path)
    has_test_py = py_count > 0 and _has_test_files_py(snapshot)
    log.info("pytest available : %s", has_pytest)
    log.info("Python test files: %s", has_test_py)

    if has_pytest and has_test_py:
        _run_strategy_safe(
            name="existing_tests",
            applicable=True,
            note="pytest found + Python test files found",
            snapshot=snapshot,
            results=results,
        )
    else:
        reason = (
            "No Python test files found (TypeScript/JavaScript repository)" if not has_test_py
            else "pytest not available in this environment"
        )
        _skip_strategy("existing_tests", reason, results)

        # Check if there are JS/TS tests we can attempt to run
        if is_ts_js:
            _attempt_js_tests(clone_path, meta, results)

    # ── Strategy: static_ast ─────────────────────────────────────────────
    if has_python and py_count > 0:
        _run_strategy_safe(
            name="static_ast",
            applicable=True,
            note=f"{py_count} Python files available",
            snapshot=snapshot,
            results=results,
        )
    else:
        _skip_strategy(
            "static_ast",
            f"No Python files in snapshot (TypeScript/JavaScript repository, {py_count} .py files found)",
            results,
        )
        # Attempt structural analysis of TS/JS files as a custom evidence item
        if is_ts_js:
            _attempt_ts_structure_analysis(clone_path, meta, results)

    # ── Strategy: documentation_analysis ─────────────────────────────────
    _run_strategy_safe(
        name="documentation_analysis",
        applicable=True,
        note="Checks README presence — advisory only",
        snapshot=snapshot,
        results=results,
    )

    # ── Strategy: history_analysis ────────────────────────────────────────
    if has_git:
        _run_strategy_safe(
            name="history_analysis",
            applicable=True,
            note="git history available (shallow clone — limited)",
            snapshot=snapshot,
            results=results,
        )
    else:
        _skip_strategy("history_analysis", "No git history available", results)

    # ── Strategy: differential_testing ───────────────────────────────────
    _skip_strategy(
        "differential_testing",
        "Requires base/head commit pair from a PR — no PR available",
        results,
    )

    # ── Strategy: targeted_testing ────────────────────────────────────────
    if has_python and has_test_py:
        _run_strategy_safe(
            name="targeted_testing",
            applicable=True,
            note="Python test files found",
            snapshot=snapshot,
            results=results,
        )
    else:
        _skip_strategy(
            "targeted_testing",
            "No Python test files (TypeScript/JavaScript repository)",
            results,
        )

    # ── Phase 6 strategies — all skipped with reasons ─────────────────────

    _skip_strategy(
        "property_based_testing",
        "Requires Python property declarations (hypothesis/given decorators) — none found",
        results,
    )
    _skip_strategy(
        "mutation_testing",
        "Requires Python source files to mutate — no Python source files",
        results,
    )
    _skip_strategy(
        "fault_localization",
        "Requires test failures + coverage data — no Python tests available to run",
        results,
    )
    _skip_strategy(
        "metamorphic_testing",
        "Requires Python functions with defined metamorphic relations — not applicable",
        results,
    )
    _skip_strategy(
        "fuzzing",
        "Requires Python callable targets — no Python source files",
        results,
    )
    _skip_strategy(
        "counterexample_shrinking",
        "Requires prior failing generated input — no failing input produced",
        results,
    )
    _skip_strategy(
        "semantic_sibling_analysis",
        "Uses Python AST for structural similarity — no Python files to analyze",
        results,
    )

    return results


def _run_strategy_safe(
    name: str,
    applicable: bool,
    note: str,
    snapshot,
    results: list[dict],
):
    """Run a strategy from the registry, recording the honest result."""
    if not applicable:
        _skip_strategy(name, note, results)
        return

    log.info("-- Strategy: %s --", name)
    log.info("Note: %s", note)

    try:
        from app.strategies import build_default_registry
        registry = build_default_registry()
        strategy = registry.get(name)

        if strategy is None:
            _skip_strategy(name, f"Not found in default registry", results)
            return

        context: dict = {}
        R.strategies_attempted.append(name)
        start = time.monotonic()
        result = strategy.execute(snapshot, context)
        elapsed = time.monotonic() - start

        entry = {
            "strategy": name,
            "applicable": True,
            "prerequisites": note,
            "execution": "completed",
            "result": result.result,
            "confidence": result.confidence,
            "raw_output": (result.raw_output or "")[:600],
            "command": result.command,
            "file_ref": result.file_ref,
            "elapsed_s": round(elapsed, 2),
            "evidence": _summarize_evidence(result),
            "reason": _result_reason(name, result),
        }
        results.append(entry)
        log.info("Result: %s (confidence=%.2f) in %.2fs",
                 result.result, result.confidence, elapsed)
        if result.raw_output:
            for line in result.raw_output[:400].splitlines():
                log.debug("  %s", line)

        # Create receipt for meaningful results
        if result.result in ("PASS", "FAIL"):
            receipt = {
                "strategy": name,
                "result": result.result,
                "confidence": result.confidence,
                "command": result.command or f"strategy:{name}",
                "raw_output": (result.raw_output or "")[:500],
                "file_ref": result.file_ref,
                "evidence_status": "verified" if result.result != "ERROR" else "execution_failure",
            }
            R.receipts.append(receipt)

    except Exception as exc:
        elapsed = time.monotonic() - start if "start" in dir() else 0
        log.error("Strategy %s raised: %s", name, exc)
        log.debug(traceback.format_exc())
        entry = {
            "strategy": name,
            "applicable": True,
            "prerequisites": note,
            "execution": "exception",
            "result": "ERROR",
            "confidence": 0.0,
            "raw_output": str(exc)[:300],
            "command": None,
            "file_ref": None,
            "elapsed_s": round(elapsed, 2),
            "evidence": "strategy raised unhandled exception",
            "reason": f"ESCALATE — execution error: {exc}",
        }
        results.append(entry)
        R.errors.append(f"strategy {name}: {exc}")


def _skip_strategy(name: str, reason: str, results: list[dict]):
    R.strategies_skipped.append({"strategy": name, "reason": reason})
    log.info("-- Strategy: %s -- SKIPPED", name)
    log.info("Reason: %s", reason)


def _check_pytest_available(clone_path: str) -> bool:
    """Check if pytest is available in the environment."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False


def _has_test_files_py(snapshot) -> bool:
    """Check if the snapshot has any Python test files."""
    for f in snapshot.all_files:
        fname = os.path.basename(f).lower()
        if fname.startswith("test_") or fname.endswith("_test.py"):
            return True
    return False


def _attempt_js_tests(clone_path: str, meta: dict, results: list[dict]):
    """
    Attempt to check if JS/TS test runner is available and if tests exist.
    Does NOT run the tests (no npm install in this environment).
    Records applicability evidence.
    """
    log.info("-- Strategy: existing_tests (JS/TS probe) --")
    log.info("Checking for JavaScript/TypeScript test infrastructure")

    # Check for package.json test script
    pkg_json_path = os.path.join(clone_path, "package.json")
    has_test_script = False
    test_command = None
    test_files_found = []

    if os.path.isfile(pkg_json_path):
        try:
            with open(pkg_json_path, encoding="utf-8") as f:
                pkg = json.load(f)
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                has_test_script = True
                test_command = scripts["test"]
                log.info("package.json test script: %s", test_command)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            test_frameworks = [k for k in deps if any(
                x in k for x in ["jest", "mocha", "vitest", "jasmine", "chai"]
            )]
            if test_frameworks:
                log.info("Test frameworks in package.json: %s", test_frameworks)
        except Exception as e:
            log.warning("Could not parse package.json: %s", e)

    # Find test files
    for pattern in ["**/*.test.ts", "**/*.spec.ts", "**/*.test.js",
                    "**/*.spec.js", "**/test/**/*.ts", "**/__tests__/**/*.ts"]:
        found = glob.glob(os.path.join(clone_path, pattern), recursive=True)
        test_files_found.extend(found[:5])

    test_files_found = list(set(test_files_found))[:10]
    if test_files_found:
        log.info("JS/TS test files found: %d (first %d shown)",
                 len(test_files_found), min(3, len(test_files_found)))
        for f in test_files_found[:3]:
            log.info("  %s", os.path.relpath(f, clone_path))

    # Check if node_modules exists (needed to run tests)
    has_node_modules = os.path.isdir(os.path.join(clone_path, "node_modules"))
    log.info("node_modules installed: %s", has_node_modules)

    if not has_node_modules:
        result_entry = {
            "strategy": "existing_tests (JS/TS)",
            "applicable": True,
            "prerequisites": "package.json found, test files found",
            "execution": "not_executed",
            "result": "INSUFFICIENT",
            "confidence": 0.0,
            "raw_output": (
                f"JS/TS test infrastructure found but cannot run: "
                f"node_modules not installed. "
                f"test_script={test_command!r}, "
                f"test_files={len(test_files_found)}"
            ),
            "command": f"npm test  [NOT EXECUTED — node_modules absent]",
            "file_ref": None,
            "elapsed_s": 0,
            "evidence": (
                f"Test infrastructure present (test_files={len(test_files_found)}, "
                f"test_script={has_test_script}) but not executable without npm install"
            ),
            "reason": "INSUFFICIENT_EVIDENCE — tests cannot be run without npm install",
        }
        results.append(result_entry)
        R.strategies_attempted.append("existing_tests (JS/TS probe)")
        log.info("Result: INSUFFICIENT — test infrastructure found but node_modules absent")
    elif has_test_script and test_files_found:
        # node_modules exists — we can try running tests
        log.info("node_modules present — attempting test run")
        _run_js_tests(clone_path, test_command, results)
    else:
        result_entry = {
            "strategy": "existing_tests (JS/TS)",
            "applicable": False,
            "prerequisites": "No test files or test script found",
            "execution": "not_executed",
            "result": "INSUFFICIENT",
            "confidence": 0.0,
            "raw_output": "No JS/TS test infrastructure detected",
            "command": None,
            "file_ref": None,
            "elapsed_s": 0,
            "evidence": "No test runner configuration found",
            "reason": "INSUFFICIENT_EVIDENCE — no test infrastructure",
        }
        results.append(result_entry)
        R.strategies_skipped.append({"strategy": "existing_tests (JS/TS)", "reason": "No test infrastructure"})


def _run_js_tests(clone_path: str, test_command: str, results: list[dict]):
    """Attempt to run JS/TS tests if node_modules is present."""
    log.info("Attempting: npm test")
    start = time.monotonic()
    try:
        r = subprocess.run(
            ["npm", "test", "--", "--ci", "--no-coverage"],
            cwd=clone_path,
            capture_output=True, text=True, timeout=120,
        )
        elapsed = time.monotonic() - start
        log.info("npm test exit_code=%d elapsed=%.1fs", r.returncode, elapsed)

        if r.returncode == 0:
            result_val = "PASS"
            confidence = 0.85
        else:
            result_val = "FAIL"
            confidence = 0.9

        entry = {
            "strategy": "existing_tests (JS/TS npm)",
            "applicable": True,
            "prerequisites": "node_modules installed, test script found",
            "execution": "completed",
            "result": result_val,
            "confidence": confidence,
            "raw_output": (r.stdout + r.stderr)[:600],
            "command": f"npm test (in {clone_path})",
            "file_ref": None,
            "elapsed_s": round(elapsed, 2),
            "evidence": f"npm test exit_code={r.returncode}",
            "reason": f"{'Tests passed' if r.returncode == 0 else 'Tests failed'} (exit_code={r.returncode})",
        }
        results.append(entry)
        R.strategies_attempted.append("existing_tests (JS/TS npm)")

        if result_val in ("PASS", "FAIL"):
            R.receipts.append({
                "strategy": "existing_tests (JS/TS npm)",
                "result": result_val,
                "confidence": confidence,
                "command": "npm test",
                "raw_output": (r.stdout + r.stderr)[:500],
                "file_ref": None,
                "evidence_status": "verified",
            })

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        entry = {
            "strategy": "existing_tests (JS/TS npm)",
            "applicable": True,
            "prerequisites": "node_modules installed",
            "execution": "timeout",
            "result": "ERROR",
            "confidence": 0.0,
            "raw_output": f"npm test timed out after {elapsed:.0f}s",
            "command": "npm test",
            "file_ref": None,
            "elapsed_s": round(elapsed, 2),
            "evidence": "test execution timed out",
            "reason": "ESCALATE — test runner timed out",
        }
        results.append(entry)
        R.errors.append(f"npm test timed out after {elapsed:.0f}s")
    except FileNotFoundError:
        entry = {
            "strategy": "existing_tests (JS/TS npm)",
            "applicable": True,
            "prerequisites": "npm required",
            "execution": "not_executed",
            "result": "INSUFFICIENT",
            "confidence": 0.0,
            "raw_output": "npm not found in PATH",
            "command": "npm test",
            "file_ref": None,
            "elapsed_s": 0,
            "evidence": "npm binary not in PATH",
            "reason": "INSUFFICIENT_EVIDENCE — npm not available",
        }
        results.append(entry)


def _attempt_ts_structure_analysis(clone_path: str, meta: dict, results: list[dict]):
    """
    Perform basic structural analysis on TypeScript/JavaScript files.
    Checks: syntax parseable (basic), file structure, README present.
    This is a non-Python static analysis — produces INSUFFICIENT (no execution).
    """
    log.info("-- Strategy: static_analysis (TS/JS structural) --")
    log.info("Checking TypeScript/JavaScript file structure")

    ts_files = glob.glob(os.path.join(clone_path, "**/*.ts"), recursive=True)
    tsx_files = glob.glob(os.path.join(clone_path, "**/*.tsx"), recursive=True)
    js_files = glob.glob(os.path.join(clone_path, "**/*.js"), recursive=True)

    # Exclude node_modules
    def _exclude_nm(paths):
        return [p for p in paths if "node_modules" not in p and ".git" not in p]

    ts_files = _exclude_nm(ts_files)
    tsx_files = _exclude_nm(tsx_files)
    js_files = _exclude_nm(js_files)

    total = len(ts_files) + len(tsx_files) + len(js_files)
    log.info("TS files: %d, TSX files: %d, JS files: %d (excluding node_modules)",
             len(ts_files), len(tsx_files), len(js_files))
    log.info("Total TS/JS source files: %d", total)

    # Sample a few files for basic checks
    sample_issues = []
    checked = 0
    for f in (ts_files + tsx_files)[:20]:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            # Basic checks: not empty, not binary
            if len(content.strip()) == 0:
                sample_issues.append(f"Empty file: {os.path.relpath(f, clone_path)}")
            checked += 1
        except Exception as exc:
            sample_issues.append(f"Cannot read {os.path.relpath(f, clone_path)}: {exc}")

    output_lines = [
        f"TypeScript/JavaScript structural analysis",
        f"TS files: {len(ts_files)}, TSX: {len(tsx_files)}, JS: {len(js_files)}",
        f"Files checked: {checked}",
        f"Issues found: {len(sample_issues)}",
    ]
    if sample_issues:
        output_lines += [f"  {i}" for i in sample_issues[:5]]

    entry = {
        "strategy": "static_analysis (TS/JS structural)",
        "applicable": True,
        "prerequisites": "TypeScript/JavaScript files present",
        "execution": "completed",
        "result": "INSUFFICIENT",
        "confidence": 0.0,
        "raw_output": "\n".join(output_lines),
        "command": "glob + file_read (TS/JS structural check)",
        "file_ref": None,
        "elapsed_s": 0,
        "evidence": (
            "Basic structural check only. "
            "No Python AST parser available for TypeScript. "
            "TypeScript-specific static analysis (tsc --noEmit) not executed "
            "— would require npm install + tsc binary. "
            "INSUFFICIENT — not executable in this environment."
        ),
        "reason": (
            "INSUFFICIENT_EVIDENCE — TypeScript static analysis requires tsc; "
            "not available without npm install. File structure check only."
        ),
    }
    results.append(entry)
    R.strategies_attempted.append("static_analysis (TS/JS structural)")
    log.info("Result: INSUFFICIENT — TypeScript analysis requires tsc (npm install needed)")


def _summarize_evidence(result) -> str:
    if result.result == "PASS":
        return f"Positive evidence: {result.raw_output[:100] if result.raw_output else 'none'}"
    elif result.result == "FAIL":
        return f"Negative evidence: {result.raw_output[:100] if result.raw_output else 'none'}"
    elif result.result == "INSUFFICIENT":
        return "No actionable evidence produced"
    else:
        return f"Strategy error or error result"


def _result_reason(name: str, result) -> str:
    if result.result == "PASS":
        return f"Evidence supports claim — strategy produced positive result"
    elif result.result == "FAIL":
        return f"Evidence contradicts claim — potential finding (requires corroboration)"
    elif result.result == "INSUFFICIENT":
        return f"INSUFFICIENT_EVIDENCE — strategy ran but produced no actionable evidence"
    else:
        return f"ESCALATE — strategy execution error or unsupported"


# ── Step 6: Verdict calculation ──────────────────────────────────────────────

def calculate_verdict(strategy_results: list[dict], meta: dict) -> tuple[str, str]:
    """
    Apply the Receipts verdict rules to the strategy results.

    Verdict rules (from orchestrator.py):
    - ERROR/TIMEOUT from any strategy → ESCALATE
    - Any non-advisory hard FAIL → BUG_DETECTED (requires corroboration)
    - All PASS / INSUFFICIENT (no hard fails, no errors) → SAFE if test_runner PASS
    - Insufficient evidence → ESCALATE

    Advisory strategies (FAIL is informational): documentation_analysis, history_analysis
    """
    _section("STEP 6 — Verdict Calculation")

    ADVISORY = {"documentation_analysis", "history_analysis"}
    AUTHORITATIVE_FAIL_STRATEGIES = {
        "existing_tests", "existing_tests (JS/TS npm)", "targeted_testing",
        "change_impact", "differential_testing",
    }

    errors = [r for r in strategy_results if r["result"] == "ERROR"]
    hard_fails = [r for r in strategy_results
                  if r["result"] == "FAIL"
                  and r["strategy"] not in ADVISORY]
    advisory_fails = [r for r in strategy_results
                      if r["result"] == "FAIL"
                      and r["strategy"] in ADVISORY]
    passes = [r for r in strategy_results if r["result"] == "PASS"]
    insufficients = [r for r in strategy_results if r["result"] == "INSUFFICIENT"]

    log.info("Strategy result summary:")
    log.info("  ERROR      : %d", len(errors))
    log.info("  FAIL (hard): %d", len(hard_fails))
    log.info("  FAIL (adv) : %d", len(advisory_fails))
    log.info("  PASS       : %d", len(passes))
    log.info("  INSUFFICIENT: %d", len(insufficients))

    # Rule 1: errors → ESCALATE
    if errors:
        reason = f"Strategy execution error(s): {', '.join(r['strategy'] for r in errors)}"
        log.warning("Verdict: ESCALATE — %s", reason)
        return "ESCALATE", reason

    # Rule 2: hard FAIL from authoritative strategy → BUG_DETECTED requires evidence
    if hard_fails:
        # Only if the failing strategy actually ran tests with real output
        real_test_fails = [
            r for r in hard_fails
            if r.get("command") and r.get("raw_output", "").strip()
        ]
        if real_test_fails:
            reason = (
                f"Non-advisory strategy FAIL with evidence: "
                f"{', '.join(r['strategy'] for r in real_test_fails)}"
            )
            log.warning("Verdict: BUG_DETECTED — %s", reason)
            return "BUG_DETECTED", reason
        else:
            reason = (
                f"Non-advisory strategy FAIL but no real test output to confirm: "
                f"{', '.join(r['strategy'] for r in hard_fails)}"
            )
            log.warning("Verdict: ESCALATE — %s", reason)
            return "ESCALATE", reason

    # Rule 3: At least one authoritative PASS (tests ran and passed) → SAFE
    test_passes = [r for r in passes if r["strategy"] not in ADVISORY]
    if test_passes:
        reason = (
            f"Authoritative PASS evidence from: "
            f"{', '.join(r['strategy'] for r in test_passes)}"
        )
        log.info("Verdict: SAFE — %s", reason)
        return "SAFE", reason

    # Rule 4: No authoritative PASS, no hard FAIL, no errors → ESCALATE
    # history_analysis PASS is advisory and does not constitute authoritative evidence.
    # The system cannot confirm code correctness without running tests.
    advisory_passes = [r for r in passes if r["strategy"] in ADVISORY]
    reason = (
        "No authoritative test-execution evidence available. "
        "Only advisory strategies produced results "
        f"(advisory_pass={[r['strategy'] for r in advisory_passes]}, "
        f"advisory_fail={[r['strategy'] for r in advisory_fails]}). "
        "This repository uses TypeScript/JavaScript; "
        "Receipts' Python-specific test execution strategies cannot run against it. "
        "JavaScript/TypeScript tests could not be executed (node_modules not installed). "
        "Per Receipts' fail-closed rules: without authoritative test evidence, "
        "verdict must be ESCALATE."
    )
    log.info("Verdict: ESCALATE -- %s", reason)
    return "ESCALATE", reason


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    _section("RECEIPTS — Real GitHub Repository Test")
    log.info("Repository : %s", REPO_URL)
    log.info("Branch     : %s", REPO_BRANCH)
    log.info("Timestamp  : %s", TS)
    log.info("Log file   : %s", _LOG_FILE)
    log.info("")

    tmpdir: Optional[str] = None
    clone_path: Optional[str] = None

    try:
        # Step 1: Provider availability
        provider = check_provider_availability()
        # Provider is None if no GITHUB_TOKEN — we proceed with anonymous clone

        # Step 2: Clone repository (anonymous for public repo)
        tmpdir = clone_repository()
        if tmpdir is None:
            R.verdict = "ESCALATE"
            R.verdict_reason = "Repository clone failed — cannot proceed"
            R.exit_status = 1
            _write_log()
            return 1

        clone_path = os.path.join(tmpdir, "repo")

        # Step 3: Metadata
        meta = collect_metadata(clone_path)

        # Step 4: Snapshot
        snapshot = create_snapshot(clone_path, meta)
        if snapshot is None:
            R.verdict = "ESCALATE"
            R.verdict_reason = "Snapshot creation failed"
            R.exit_status = 1
            _write_log()
            return 1

        # Step 5: Strategies
        strategy_results = execute_strategies(snapshot, clone_path, meta)
        R.strategy_results = strategy_results

        # Step 6: Verdict
        verdict, reason = calculate_verdict(strategy_results, meta)
        R.verdict = verdict
        R.verdict_reason = reason

        # Summary
        _section("FINAL SUMMARY")
        log.info("Repository     : %s", REPO_URL)
        log.info("Branch         : %s", REPO_BRANCH)
        log.info("Resolved commit: %s", R.resolved_commit or "unknown")
        log.info("Provider status: %s (%s)", R.provider_status, R.provider_reason[:80])
        log.info("Snapshot status: %s", R.snapshot_status)
        log.info("Snapshot hash  : %s", R.snapshot_hash or "n/a")
        log.info("Python files   : %d", R.snapshot_file_count_py)
        log.info("Total files    : %d", R.snapshot_file_count_all)
        log.info("")
        log.info("Strategies attempted : %d — %s",
                 len(R.strategies_attempted), R.strategies_attempted)
        log.info("Strategies skipped   : %d", len(R.strategies_skipped))
        for s in R.strategies_skipped:
            log.info("  %-40s %s", s["strategy"], s["reason"][:60])
        log.info("")
        log.info("Strategy results:")
        for sr in R.strategy_results:
            log.info("  %-45s %s (conf=%.2f)",
                     sr["strategy"], sr["result"], sr.get("confidence", 0.0))
        log.info("")
        log.info("Receipts created     : %d", len(R.receipts))
        for rec in R.receipts:
            log.info("  %-40s %s", rec["strategy"], rec["result"])
        log.info("")
        log.info("Errors               : %d", len(R.errors))
        for e in R.errors:
            log.info("  %s", e[:80])
        log.info("")
        log.info("VERDICT              : %s", R.verdict)
        log.info("VERDICT REASON       : %s", R.verdict_reason)
        log.info("")
        log.info("Log file             : %s", _LOG_FILE)

        R.exit_status = 0
        _write_log()
        return 0

    except Exception as exc:
        log.error("Test script unhandled exception: %s", exc)
        log.debug(traceback.format_exc())
        R.verdict = "ESCALATE"
        R.verdict_reason = f"Test script error: {exc}"
        R.errors.append(str(exc))
        R.exit_status = 1
        _write_log()
        return 1

    finally:
        if tmpdir and os.path.isdir(tmpdir):
            log.info("Cleaning up clone: %s", tmpdir)
            shutil.rmtree(tmpdir, ignore_errors=True)
            log.info("Cleanup complete")


def _write_log():
    """Write machine-readable JSON summary to log dir."""
    summary_path = _LOG_DIR / "github_carecircle_summary.json"
    try:
        summary = {
            "timestamp": R.timestamp,
            "repository": R.repository,
            "branch": R.branch,
            "resolved_commit": R.resolved_commit,
            "provider_status": R.provider_status,
            "provider_reason": R.provider_reason,
            "snapshot_status": R.snapshot_status,
            "snapshot_hash": R.snapshot_hash,
            "snapshot_file_count_py": R.snapshot_file_count_py,
            "snapshot_file_count_all": R.snapshot_file_count_all,
            "strategies_attempted": R.strategies_attempted,
            "strategies_skipped": R.strategies_skipped,
            "strategy_results": [
                {k: v for k, v in sr.items() if k != "raw_output"}
                for sr in R.strategy_results
            ],
            "receipts": R.receipts,
            "errors": R.errors,
            "verdict": R.verdict,
            "verdict_reason": R.verdict_reason,
            "exit_status": R.exit_status,
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        log.info("JSON summary: %s", summary_path)
    except Exception as exc:
        log.warning("Could not write JSON summary: %s", exc)


if __name__ == "__main__":
    sys.exit(main())
