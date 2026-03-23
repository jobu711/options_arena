"""Tests for eval data models and enums."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from options_arena.models.enums import (
    DeskType,
    EvalType,
    EvalVerdict,
    GraderType,
    SignalDirection,
)
from options_arena.models.eval import (
    EvalBaseline,
    EvalDefinition,
    EvalOutcome,
    EvalReport,
    EvalRun,
)


class TestEvalEnums:
    """Verify eval-related StrEnum definitions."""

    def test_eval_type_members(self) -> None:
        assert len(EvalType) == 2
        assert EvalType.CAPABILITY == "capability"
        assert EvalType.REGRESSION == "regression"

    def test_grader_type_members(self) -> None:
        assert len(GraderType) == 3
        assert GraderType.CODE == "code"
        assert GraderType.MODEL == "model"
        assert GraderType.OUTCOME == "outcome"

    def test_eval_verdict_members(self) -> None:
        assert len(EvalVerdict) == 3
        assert EvalVerdict.SHIP == "ship"
        assert EvalVerdict.NEEDS_WORK == "needs_work"
        assert EvalVerdict.BLOCKED == "blocked"

    def test_all_are_str_enum(self) -> None:
        from enum import StrEnum

        assert issubclass(EvalType, StrEnum)
        assert issubclass(GraderType, StrEnum)
        assert issubclass(EvalVerdict, StrEnum)


class TestEvalDefinition:
    """Verify EvalDefinition model construction and validation."""

    def test_happy_path(self) -> None:
        defn = EvalDefinition(
            name="trend_bullish_clear",
            eval_type=EvalType.CAPABILITY,
            target_desk=DeskType.TREND,
            description="Clear bullish trend with RSI > 60",
            grader_type=GraderType.CODE,
            market_context_fixture="tests/fixtures/trend_bullish.json",
            expected_direction=SignalDirection.BULLISH,
            expected_confidence_min=0.6,
            expected_confidence_max=0.9,
        )
        assert defn.name == "trend_bullish_clear"
        assert defn.target_desk == DeskType.TREND
        assert defn.expected_direction == SignalDirection.BULLISH

    def test_synthesis_agent_target(self) -> None:
        defn = EvalDefinition(
            name="synthesis_consensus",
            eval_type=EvalType.CAPABILITY,
            target_desk=None,
            description="Synthesis with desk consensus",
            grader_type=GraderType.CODE,
            market_context_fixture="tests/fixtures/consensus.json",
        )
        assert defn.target_desk is None

    def test_frozen(self) -> None:
        defn = EvalDefinition(
            name="test",
            eval_type=EvalType.CAPABILITY,
            description="test",
            grader_type=GraderType.CODE,
            market_context_fixture="test.json",
        )
        with pytest.raises(ValidationError):
            defn.name = "changed"  # type: ignore[misc]

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            EvalDefinition(
                name="  ",
                eval_type=EvalType.CAPABILITY,
                description="test",
                grader_type=GraderType.CODE,
                market_context_fixture="test.json",
            )

    def test_confidence_bounds_validation(self) -> None:
        with pytest.raises(ValidationError, match="confidence bound must be in"):
            EvalDefinition(
                name="test",
                eval_type=EvalType.CAPABILITY,
                description="test",
                grader_type=GraderType.CODE,
                market_context_fixture="test.json",
                expected_confidence_min=1.5,
            )

    def test_nan_confidence_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            EvalDefinition(
                name="test",
                eval_type=EvalType.CAPABILITY,
                description="test",
                grader_type=GraderType.CODE,
                market_context_fixture="test.json",
                expected_confidence_min=float("nan"),
            )

    def test_json_roundtrip(self) -> None:
        defn = EvalDefinition(
            name="test_roundtrip",
            eval_type=EvalType.REGRESSION,
            target_desk=DeskType.VOLATILITY,
            description="Regression test",
            grader_type=GraderType.MODEL,
            market_context_fixture="fixture.json",
            expected_direction=SignalDirection.BEARISH,
            expected_confidence_min=0.3,
            expected_confidence_max=0.7,
            custom_assertions=["check_iv_regime"],
        )
        restored = EvalDefinition.model_validate_json(defn.model_dump_json())
        assert restored == defn


class TestEvalRun:
    """Verify EvalRun model construction and validation."""

    def test_happy_path(self) -> None:
        run = EvalRun(
            eval_name="trend_bullish",
            timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
            passed=True,
            attempts=3,
            successes=2,
            model_used="code_grader",
            duration_ms=150,
            details='{"checks": 5}',
        )
        assert run.passed is True
        assert run.attempts == 3
        assert run.successes == 2

    def test_utc_required(self) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            EvalRun(
                eval_name="test",
                timestamp=datetime(2026, 3, 22, 12, 0, 0),  # naive
                passed=True,
                attempts=1,
                successes=1,
                model_used="test",
                duration_ms=100,
                details="{}",
            )

    def test_negative_attempts_rejected(self) -> None:
        with pytest.raises(ValidationError, match=">= 0"):
            EvalRun(
                eval_name="test",
                timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
                passed=True,
                attempts=-1,
                successes=0,
                model_used="test",
                duration_ms=100,
                details="{}",
            )

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duration_ms must be >= 0"):
            EvalRun(
                eval_name="test",
                timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
                passed=True,
                attempts=1,
                successes=1,
                model_used="test",
                duration_ms=-100,
                details="{}",
            )


class TestEvalReport:
    """Verify EvalReport model construction and validation."""

    def test_happy_path(self) -> None:
        report = EvalReport(
            runs=[],
            pass_at_1=0.8,
            pass_at_3=0.95,
            regressions=[],
            verdict=EvalVerdict.SHIP,
        )
        assert report.pass_at_1 == pytest.approx(0.8)
        assert report.verdict == EvalVerdict.SHIP

    def test_pass_rate_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="pass_rate"):
            EvalReport(
                runs=[],
                pass_at_1=1.5,
                pass_at_3=0.5,
                regressions=[],
                verdict=EvalVerdict.SHIP,
            )

    def test_nan_pass_rate_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            EvalReport(
                runs=[],
                pass_at_1=float("nan"),
                pass_at_3=0.5,
                regressions=[],
                verdict=EvalVerdict.SHIP,
            )


class TestEvalBaseline:
    """Verify EvalBaseline model construction."""

    def test_happy_path(self) -> None:
        baseline = EvalBaseline(
            eval_results=[
                EvalOutcome(eval_name="trend_bullish", passed=True),
                EvalOutcome(eval_name="vol_high", passed=False),
            ],
            pass_at_1=0.5,
            pass_at_3=0.75,
            timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
        )
        assert baseline.eval_results[0].passed is True
        assert baseline.pass_at_1 == pytest.approx(0.5)

    def test_utc_required(self) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            EvalBaseline(
                eval_results=[],
                pass_at_1=0.0,
                pass_at_3=0.0,
                timestamp=datetime(2026, 3, 22, 12, 0, 0),  # naive
            )
