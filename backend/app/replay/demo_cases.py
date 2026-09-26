"""
Demo replay cases — Phase 5 (workspace-isolated).

Each case specifies:
  - repository_path: where the source files live
  - included_files: JSON list of files to copy into the isolated workspace
    (None → copy the whole directory)

Using ``included_files`` ensures SAFE cases never see buggy files that happen
to live in the same source directory.

Ground truth is RECEIPTS-verified (real pytest runs — not fabricated).

GOOD cases (ground_truth=BUG): 3 cases from demo/repository
  1. buggy_stats_accumulator_reset    — mean() wrong accumulator variable
  2. buggy_stats_variance             — variance() depends on the broken mean()
  3. buggy_stats_full_suite           — full demo/repository (all 4 failures)

SAFE cases (ground_truth=SAFE): 3 cases from demo/clean_repo (no buggy files)
  1. clean_string_utils               — string_utils.py + tests (33 pass)
  2. clean_math_utils                 — math_utils.py + tests (16 pass)
  3. clean_repo_full                  — all of demo/clean_repo (33 pass)

Note: 5–8 cases each are not reliably achievable with the current single demo
repository because the only buggy module is buggy_stats.py. Adding more BUG
cases from the same file would be redundant (same defect). To reach 5+ reliable
BUG cases a second independently-buggy module would be needed — deferred.
"""
from __future__ import annotations

import json
import os
from typing import Optional


DEMO_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "demo", "repository")
)

CLEAN_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "demo", "clean_repo")
)

# ---------------------------------------------------------------------------
# Case definitions
# ---------------------------------------------------------------------------

DEMO_CASES: list[dict] = [
    # ------------------------------------------------------------------
    # BUG cases — demo/repository (buggy_stats.py present)
    # ------------------------------------------------------------------
    {
        "label": "buggy_stats_accumulator_reset",
        "description": (
            "buggy_stats.py mean() uses `subtotal = v` instead of `total += v`. "
            "test_buggy_stats.py has 4 failing tests."
        ),
        "repository_path": DEMO_REPO,
        "included_files": json.dumps([
            "buggy_stats.py",
            "test_buggy_stats.py",
            "pyproject.toml",
        ]),
        "ground_truth": "BUG",
        "ground_truth_source": "RECEIPTS",
        "ground_truth_notes": (
            "Verified: pytest demo/repository/test_buggy_stats.py → exit code 1, 4 FAILs. "
            "Deterministic and reproducible."
        ),
    },
    {
        "label": "buggy_stats_variance_propagation",
        "description": (
            "variance() calls mean() which is broken. test_buggy_stats.py::test_variance_basic fails."
        ),
        "repository_path": DEMO_REPO,
        "included_files": json.dumps([
            "buggy_stats.py",
            "test_buggy_stats.py",
            "pyproject.toml",
        ]),
        "ground_truth": "BUG",
        "ground_truth_source": "RECEIPTS",
        "ground_truth_notes": (
            "Same defect as buggy_stats_accumulator_reset but framed from the variance() perspective. "
            "test_variance_basic fails because variance() internally calls mean()."
        ),
    },
    {
        "label": "buggy_stats_full_suite",
        "description": (
            "Full demo/repository — buggy_stats.py + calculator.py. "
            "test_buggy_stats.py has 4 FAILs; test_calculator.py has 14 PASSes. "
            "Overall: FAIL (BUG_DETECTED)."
        ),
        "repository_path": DEMO_REPO,
        "included_files": None,   # copy entire demo/repository
        "ground_truth": "BUG",
        "ground_truth_source": "RECEIPTS",
        "ground_truth_notes": (
            "Verified: pytest demo/repository → exit code 1, 4 FAILs. "
            "calculator tests pass but buggy_stats tests fail."
        ),
    },
    # ------------------------------------------------------------------
    # SAFE cases — demo/clean_repo (no buggy files, all tests pass)
    # ------------------------------------------------------------------
    {
        "label": "clean_string_utils",
        "description": (
            "string_utils.py has correct implementation. "
            "All 18 tests in test_string_utils.py pass. No known defects."
        ),
        "repository_path": CLEAN_REPO,
        "included_files": json.dumps([
            "string_utils.py",
            "test_string_utils.py",
            "pyproject.toml",
            "README.md",
        ]),
        "ground_truth": "SAFE",
        "ground_truth_source": "RECEIPTS",
        "ground_truth_notes": (
            "Verified: pytest demo/clean_repo/test_string_utils.py → exit code 0, 18 pass."
        ),
    },
    {
        "label": "clean_math_utils",
        "description": (
            "math_utils.py has correct implementation. "
            "All 15 tests in test_math_utils.py pass. No known defects."
        ),
        "repository_path": CLEAN_REPO,
        "included_files": json.dumps([
            "math_utils.py",
            "test_math_utils.py",
            "pyproject.toml",
            "README.md",
        ]),
        "ground_truth": "SAFE",
        "ground_truth_source": "RECEIPTS",
        "ground_truth_notes": (
            "Verified: pytest demo/clean_repo/test_math_utils.py → exit code 0, 15 pass."
        ),
    },
    {
        "label": "clean_repo_full",
        "description": (
            "Full demo/clean_repo — string_utils.py + math_utils.py. "
            "All 33 tests pass. No known defects."
        ),
        "repository_path": CLEAN_REPO,
        "included_files": None,   # copy entire clean_repo
        "ground_truth": "SAFE",
        "ground_truth_source": "RECEIPTS",
        "ground_truth_notes": (
            "Verified: pytest demo/clean_repo → exit code 0, 33 pass."
        ),
    },
]


def seed_demo_cases(db, demo_repo_path: Optional[str] = None) -> list:
    """
    Seed demo replay cases into the database if they don't already exist.
    Returns list of created/existing ReplayCase objects.

    ``demo_repo_path`` is kept for backward compatibility but is ignored —
    each case definition now carries its own ``repository_path``.
    """
    from app.models import ReplayCase, GroundTruthEnum, ReplayAgentEnum

    created = []

    for case_def in DEMO_CASES:
        existing = db.query(ReplayCase).filter(
            ReplayCase.label == case_def["label"]
        ).first()
        if existing:
            created.append(existing)
            continue

        case = ReplayCase(
            label=case_def["label"],
            description=case_def["description"],
            repository_path=case_def.get("repository_path"),
            included_files=case_def.get("included_files"),
            ground_truth=case_def["ground_truth"],
            ground_truth_source=case_def["ground_truth_source"],
            ground_truth_notes=case_def.get("ground_truth_notes"),
            is_valid=True,
        )
        db.add(case)
        created.append(case)

    db.commit()
    return created
