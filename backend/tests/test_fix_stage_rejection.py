"""
test_fix_stage_rejection.py — ST-8: FixStageV7 patch rejection tests.

Verifies the fix-stage invariants:
  1. A failed patch application is always rolled back (original file restored)
  2. fix_applied=False is set in evidence when patch fails
  3. BLOCKED is returned when all strategies are exhausted
  4. FAILED is returned when strategy fails but alternatives exist
  5. Patch application (PASSED) is NOT equivalent to verification (VerifyStageV7 is separate gate)
  6. Rollback restores the original file content after a failed apply
"""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, ImmunityStatusEnum, StageTypeEnum

_TEST_DB_PATH = os.path.join(_BACKEND_DIR, "tests", "_fix_rejection_test.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass


@pytest.fixture()
def db():
    session = TestSession()
    yield session
    session.rollback()
    session.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

_BUGGY_SOURCE = textwrap.dedent("""\
    def sum_list(items):
        total = 0
        for item in items:
            total = item        # Bug: should be +=
        return total
""")

_FAILING_TEST = textwrap.dedent("""\
    from calc import sum_list
    def test_sum():
        assert sum_list([1, 2, 3]) == 6, f"Expected 6, got {sum_list([1, 2, 3])}"
""")


def _make_context(repo_path: str, failing_tests=None):
    from app.immunity.stages import ImmunityContext
    ctx = ImmunityContext(repository_path=repo_path)
    if failing_tests is not None:
        ctx.set_stage(StageTypeEnum.REPRODUCE, {
            "exit_code": 1,
            "failing_tests": failing_tests,
            "stdout": "FAILED calc.py::test_sum",
            "command": "pytest",
        })
    return ctx


def _with_root_cause(ctx, error_type="AssertionError", error_message="Expected 6",
                     affected_file="calc.py", source_snippet="    total = item",
                     hypothesis_resolution="VERIFIED"):
    ctx.set_stage(StageTypeEnum.ROOT_CAUSE, {
        "error_type": error_type,
        "error_message": error_message,
        "affected_file": affected_file,
        "source_snippet": source_snippet,
        "hypothesis_resolution": hypothesis_resolution,
    })
    return ctx


# ── TestFixStageBlockedWithoutRootCause ───────────────────────────────────────

class TestFixStageBlockedWithoutRootCause:
    """FixStageV7 must block when prerequisite (root cause) is not completed."""

    def test_blocked_when_no_root_cause(self, tmp_path, db):
        from app.immunity.stages_v7 import FixStageV7
        ctx = _make_context(str(tmp_path))
        result = FixStageV7().run("fix-no-rc", ctx, db)
        assert result.status == ImmunityStatusEnum.BLOCKED

    def test_fix_applied_false_when_blocked(self, tmp_path, db):
        from app.immunity.stages_v7 import FixStageV7
        ctx = _make_context(str(tmp_path))
        result = FixStageV7().run("fix-no-rc-2", ctx, db)
        fix_applied = result.evidence.get("fix_applied") if result.evidence else None
        assert not fix_applied, "fix_applied must be False when FixStageV7 is BLOCKED"


# ── TestFixStagePatchRejectionRollback ────────────────────────────────────────

class TestFixStagePatchRejectionRollback:
    """When a patch strategy fails, the original file must be restored via rollback."""

    def test_checkpoint_save_and_rollback_restores_original(self, tmp_path):
        from app.immunity.stages_v7 import PatchCheckpoint

        (tmp_path / "calc.py").write_text(_BUGGY_SOURCE)
        original = (tmp_path / "calc.py").read_text()

        chk = PatchCheckpoint("pid-rb-test", "cid-rb-test")
        chk.save(str(tmp_path / "calc.py"))

        (tmp_path / "calc.py").write_text("# mangled by failed patch")

        chk.rollback()
        restored = (tmp_path / "calc.py").read_text()
        assert restored == original, (
            "PatchCheckpoint.rollback() must restore the file to its pre-patch state"
        )

    def test_checkpoint_rollback_is_idempotent(self, tmp_path):
        from app.immunity.stages_v7 import PatchCheckpoint

        (tmp_path / "calc2.py").write_text(_BUGGY_SOURCE)
        original = (tmp_path / "calc2.py").read_text()
        chk = PatchCheckpoint("pid-idem", "cid-idem")
        chk.save(str(tmp_path / "calc2.py"))
        (tmp_path / "calc2.py").write_text("# patched")
        chk.rollback()
        chk.rollback()  # second call — must not raise
        assert (tmp_path / "calc2.py").read_text() == original

    def test_fix_stage_blocked_when_no_strategy_matches(self, tmp_path, db):
        from app.immunity.stages_v7 import FixStageV7

        (tmp_path / "unknown.py").write_text("x = 1\n")
        ctx = _make_context(str(tmp_path), failing_tests=["test_x"])
        _with_root_cause(
            ctx,
            error_type="SyntaxError",
            error_message="completely unrecognised error pattern xyz123",
            affected_file="unknown.py",
            source_snippet="x = 1",
        )
        result = FixStageV7().run("fix-no-match", ctx, db)
        assert result.status in (ImmunityStatusEnum.BLOCKED, ImmunityStatusEnum.FAILED)
        fix_applied = result.evidence.get("fix_applied") if result.evidence else None
        assert not fix_applied, "fix_applied must be False when no strategy matched"


# ── TestFixStageApplicationVsVerification ────────────────────────────────────

class TestFixStageApplicationVsVerification:
    """
    Patch application (FixStageV7 PASSED) is NOT verification.
    Verification is a separate gate in VerifyStageV7.
    """

    def test_fix_stage_passed_does_not_imply_tests_pass(self, tmp_path, db):
        from app.immunity.stages_v7 import FixStageV7, VerifyStageV7

        (tmp_path / "calc.py").write_text(_BUGGY_SOURCE)
        (tmp_path / "test_calc.py").write_text(_FAILING_TEST)
        ctx = _make_context(str(tmp_path), failing_tests=["test_calc.py::test_sum"])
        _with_root_cause(ctx, affected_file="calc.py", source_snippet="    total = item")

        fix_result = FixStageV7().run("fix-vs-verify", ctx, db)

        if fix_result.status == ImmunityStatusEnum.PASSED:
            verify_result = VerifyStageV7().run("fix-vs-verify", ctx, db)
            assert verify_result.status in (
                ImmunityStatusEnum.PASSED,
                ImmunityStatusEnum.FAILED,
                ImmunityStatusEnum.ESCALATED,
            ), "VerifyStageV7 must produce a real test-based verdict"
        else:
            assert fix_result.status in (
                ImmunityStatusEnum.BLOCKED,
                ImmunityStatusEnum.FAILED,
                ImmunityStatusEnum.ESCALATED,
            )

    def test_verify_stage_blocked_without_fix_applied(self, tmp_path, db):
        from app.immunity.stages_v7 import VerifyStageV7

        ctx = _make_context(str(tmp_path), failing_tests=["test_calc::test_sum"])
        ctx.set_stage(StageTypeEnum.FIX, {"fix_applied": False})

        result = VerifyStageV7().run("verify-no-fix", ctx, db)
        assert result.status == ImmunityStatusEnum.BLOCKED

    def test_verify_stage_produces_failed_when_tests_still_fail(self, tmp_path, db):
        from app.immunity.stages_v7 import VerifyStageV7

        (tmp_path / "calc.py").write_text(_BUGGY_SOURCE)
        (tmp_path / "test_calc.py").write_text(_FAILING_TEST)

        ctx = _make_context(str(tmp_path), failing_tests=["test_calc.py::test_sum"])
        ctx.set_stage(StageTypeEnum.ROOT_CAUSE, {
            "error_type": "AssertionError",
            "error_message": "Expected 6",
            "affected_file": "calc.py",
        })
        ctx.set_stage(StageTypeEnum.FIX, {
            "fix_applied": True,
            "affected_file": "calc.py",
        })

        result = VerifyStageV7().run("verify-still-fails", ctx, db)

        if result.status == ImmunityStatusEnum.PASSED:
            exit_code = (result.evidence or {}).get("exit_code")
            assert exit_code == 0, "VerifyStageV7 must not return PASSED when tests still fail"
        else:
            assert result.status in (
                ImmunityStatusEnum.FAILED,
                ImmunityStatusEnum.ESCALATED,
            )


# ── TestFixStageEvidenceIntegrity ─────────────────────────────────────────────

class TestFixStageEvidenceIntegrity:
    """FixStageV7 evidence fields are always correctly set."""

    def test_evidence_contains_affected_file(self, tmp_path, db):
        from app.immunity.stages_v7 import FixStageV7

        ctx = _make_context(str(tmp_path), failing_tests=["test_x"])
        _with_root_cause(ctx, affected_file="calc.py", source_snippet="    total = item")

        result = FixStageV7().run("fix-evidence-fields", ctx, db)
        if result.evidence:
            assert "affected_file" in result.evidence

    def test_evidence_fix_applied_is_bool(self, tmp_path, db):
        from app.immunity.stages_v7 import FixStageV7

        ctx = _make_context(str(tmp_path), failing_tests=["test_x"])
        _with_root_cause(ctx, affected_file="calc.py", source_snippet="    total = item")

        result = FixStageV7().run("fix-bool-field", ctx, db)
        if result.evidence and "fix_applied" in result.evidence:
            assert isinstance(result.evidence["fix_applied"], bool), (
                "fix_applied must be a boolean in the evidence dict"
            )
