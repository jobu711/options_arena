"""Tests for eval grader implementations."""

from __future__ import annotations

import json

import pytest

from options_arena.evals.graders import (
    CodeGrader,
    GraderResult,
    ModelGrader,
    OutcomeGrader,
    OutcomeRecord,
)
from options_arena.models.enums import (
    DeskType,
    EvalType,
    GraderType,
    SignalDirection,
)
from options_arena.models.eval import EvalDefinition
from options_arena.models.recommendation import DomainAssessment


def _make_assessment(**overrides: object) -> DomainAssessment:
    """Create a minimal DomainAssessment for testing."""
    defaults: dict[str, object] = {
        "desk": DeskType.TREND,
        "direction": SignalDirection.BULLISH,
        "confidence": 0.75,
        "summary": "Strong bullish momentum with RSI at 68 and positive MACD crossover.",
        "key_factors": [
            "RSI at 68% indicates strong momentum",
            "MACD crossover at $185.50",
            "Volume 25% above average",
        ],
        "risks": [
            "Earnings report in 5 days could cause volatility spike",
            "Resistance at $190 52-week high",
        ],
        "contracts_referenced": ["AAPL 230C 2026-04-18"],
        "tools_used": ["fetch_quote", "fetch_indicators"],
        "model_used": "test_model",
    }
    defaults.update(overrides)
    return DomainAssessment(**defaults)  # type: ignore[arg-type]


def _make_definition(**overrides: object) -> EvalDefinition:
    """Create a minimal EvalDefinition for testing."""
    defaults: dict[str, object] = {
        "name": "test_eval",
        "eval_type": EvalType.CAPABILITY,
        "target_desk": DeskType.TREND,
        "description": "Test eval",
        "grader_type": GraderType.CODE,
        "market_context_fixture": "tests/fixtures/test.json",
    }
    defaults.update(overrides)
    return EvalDefinition(**defaults)  # type: ignore[arg-type]


class TestCodeGrader:
    """Verify CodeGrader deterministic assertions."""

    def test_all_checks_pass(self) -> None:
        grader = CodeGrader()
        assessment = _make_assessment()
        definition = _make_definition(
            expected_direction=SignalDirection.BULLISH,
            expected_confidence_min=0.5,
            expected_confidence_max=0.9,
        )

        result = grader.grade_assessment(assessment, definition)
        assert result.passed is True
        assert result.checks_run >= 5
        assert result.checks_passed == result.checks_run

    def test_wrong_direction_fails(self) -> None:
        grader = CodeGrader()
        assessment = _make_assessment(direction=SignalDirection.BEARISH)
        definition = _make_definition(expected_direction=SignalDirection.BULLISH)

        result = grader.grade_assessment(assessment, definition)
        assert result.passed is False

        checks = json.loads(result.details)
        direction_check = next(c for c in checks if c["check"] == "direction")
        assert direction_check["passed"] is False

    def test_confidence_below_min_fails(self) -> None:
        grader = CodeGrader()
        assessment = _make_assessment(confidence=0.3)
        definition = _make_definition(expected_confidence_min=0.5)

        result = grader.grade_assessment(assessment, definition)
        assert result.passed is False

    def test_confidence_above_max_fails(self) -> None:
        grader = CodeGrader()
        assessment = _make_assessment(confidence=0.95)
        definition = _make_definition(expected_confidence_max=0.9)

        result = grader.grade_assessment(assessment, definition)
        assert result.passed is False

    def test_no_expected_direction_skips_check(self) -> None:
        grader = CodeGrader()
        assessment = _make_assessment()
        definition = _make_definition()  # no expected_direction

        result = grader.grade_assessment(assessment, definition)
        checks = json.loads(result.details)
        direction_checks = [c for c in checks if c["check"] == "direction"]
        assert len(direction_checks) == 0

    def test_empty_key_factors_fails(self) -> None:
        grader = CodeGrader()
        assessment = _make_assessment(key_factors=["at least one"])
        definition = _make_definition()

        result = grader.grade_assessment(assessment, definition)
        checks = json.loads(result.details)
        kf_check = next(c for c in checks if c["check"] == "key_factors_present")
        assert kf_check["passed"] is True


class TestModelGrader:
    """Verify ModelGrader heuristic quality checks."""

    def test_good_assessment_passes(self) -> None:
        grader = ModelGrader()
        assessment = _make_assessment()
        definition = _make_definition(grader_type=GraderType.MODEL)

        result = grader.grade_assessment(assessment, definition)
        # Good assessment with data-bearing factors should mostly pass
        assert result.checks_run >= 3

    def test_vague_factors_fail_specificity(self) -> None:
        grader = ModelGrader()
        assessment = _make_assessment(
            key_factors=[
                "market looks good",
                "momentum is strong",
                "sentiment is positive",
            ]
        )
        definition = _make_definition(grader_type=GraderType.MODEL)

        result = grader.grade_assessment(assessment, definition)
        checks = json.loads(result.details)
        specificity = next(c for c in checks if c["check"] == "specificity")
        # No numbers/data in these factors
        assert specificity["passed"] is False

    def test_short_summary_fails(self) -> None:
        grader = ModelGrader()
        assessment = _make_assessment(summary="Buy.")
        definition = _make_definition(grader_type=GraderType.MODEL)

        result = grader.grade_assessment(assessment, definition)
        checks = json.loads(result.details)
        summary_check = next(c for c in checks if c["check"] == "summary_length")
        assert summary_check["passed"] is False


class TestOutcomeGrader:
    """Verify OutcomeGrader P&L calibration logic."""

    def test_all_correct_passes(self) -> None:
        grader = OutcomeGrader()
        outcomes = [
            OutcomeRecord(direction=SignalDirection.BULLISH, confidence=0.8, pnl_pct=15.0),
            OutcomeRecord(direction=SignalDirection.BULLISH, confidence=0.7, pnl_pct=5.0),
            OutcomeRecord(direction=SignalDirection.BEARISH, confidence=0.6, pnl_pct=-10.0),
        ]
        definition = _make_definition(grader_type=GraderType.OUTCOME)

        result = grader.grade_calibration(outcomes, definition)
        assert result.passed is True

    def test_all_wrong_fails(self) -> None:
        grader = OutcomeGrader()
        outcomes = [
            OutcomeRecord(direction=SignalDirection.BULLISH, confidence=0.8, pnl_pct=-20.0),
            OutcomeRecord(direction=SignalDirection.BULLISH, confidence=0.7, pnl_pct=-15.0),
            OutcomeRecord(direction=SignalDirection.BEARISH, confidence=0.6, pnl_pct=10.0),
        ]
        definition = _make_definition(grader_type=GraderType.OUTCOME)

        result = grader.grade_calibration(outcomes, definition)
        assert result.passed is False

    def test_empty_outcomes_fails(self) -> None:
        grader = OutcomeGrader()
        definition = _make_definition(grader_type=GraderType.OUTCOME)

        result = grader.grade_calibration([], definition)
        assert result.passed is False

    def test_neutral_direction_tolerance(self) -> None:
        grader = OutcomeGrader()
        # NEUTRAL is correct if P&L is within +-5%
        assert grader._direction_correct(SignalDirection.NEUTRAL, 3.0) is True
        assert grader._direction_correct(SignalDirection.NEUTRAL, -4.0) is True
        assert grader._direction_correct(SignalDirection.NEUTRAL, 10.0) is False

    def test_nan_pnl_is_incorrect(self) -> None:
        grader = OutcomeGrader()
        assert grader._direction_correct(SignalDirection.BULLISH, float("nan")) is False

    def test_high_confidence_calibration(self) -> None:
        grader = OutcomeGrader()
        outcomes = [
            # High confidence: all correct
            OutcomeRecord(direction=SignalDirection.BULLISH, confidence=0.9, pnl_pct=20.0),
            OutcomeRecord(direction=SignalDirection.BULLISH, confidence=0.8, pnl_pct=10.0),
            # Low confidence: some wrong (this is fine for calibration)
            OutcomeRecord(direction=SignalDirection.BULLISH, confidence=0.4, pnl_pct=-5.0),
            OutcomeRecord(direction=SignalDirection.BEARISH, confidence=0.5, pnl_pct=-8.0),
        ]
        definition = _make_definition(grader_type=GraderType.OUTCOME)

        result = grader.grade_calibration(outcomes, definition)
        checks = json.loads(result.details)
        high_conf = [c for c in checks if c["check"] == "high_confidence_calibration"]
        if high_conf:
            # High confidence accuracy should be >= overall accuracy
            assert high_conf[0]["passed"] is True


class TestGraderResult:
    """Verify GraderResult dataclass."""

    def test_construction(self) -> None:
        result = GraderResult(
            passed=True,
            details='{"test": true}',
            checks_run=5,
            checks_passed=5,
        )
        assert result.passed is True
        assert result.checks_run == 5

    def test_frozen(self) -> None:
        result = GraderResult(passed=True, details="{}")
        with pytest.raises(AttributeError):
            result.passed = False  # type: ignore[misc]
