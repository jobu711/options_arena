"""Grader implementations for agent evaluation.

Three grader types:
- CodeGrader: deterministic assertions on DomainAssessment fields.
- ModelGrader: LLM-as-judge on qualitative fields (key_factors, summary).
- OutcomeGrader: direction/confidence vs actual P&L calibration.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass

from options_arena.models import DomainAssessment, PositionRecommendation
from options_arena.models.enums import SignalDirection
from options_arena.models.eval import EvalDefinition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraderCheck:
    """A single check result from a grader."""

    check: str
    expected: str
    actual: str
    passed: bool


def _serialize_checks(checks: list[GraderCheck]) -> str:
    """Serialize GraderCheck list to JSON string."""
    return json.dumps(
        [
            {
                "check": c.check,
                "expected": c.expected,
                "actual": c.actual,
                "passed": c.passed,
            }
            for c in checks
        ]
    )


@dataclass(frozen=True)
class GraderResult:
    """Result from a single grader execution."""

    passed: bool
    details: str  # JSON-serializable explanation
    checks_run: int = 0
    checks_passed: int = 0


def _gc(
    check: str,
    expected: str,
    actual: str,
    passed: bool,
) -> GraderCheck:
    """Shorthand constructor for GraderCheck."""
    return GraderCheck(check=check, expected=expected, actual=actual, passed=passed)


class CodeGrader:
    """Deterministic assertions on typed assessment fields.

    Checks direction, confidence bounds, and presence of key data.
    Pure functions — no I/O, no LLM calls.
    """

    def grade_assessment(
        self,
        assessment: DomainAssessment,
        definition: EvalDefinition,
    ) -> GraderResult:
        """Run code-based assertions on a domain assessment."""
        checks: list[GraderCheck] = []
        checks_passed = 0

        if definition.expected_direction is not None:
            ok = assessment.direction == definition.expected_direction
            checks.append(
                _gc(
                    "direction",
                    definition.expected_direction.value,
                    assessment.direction.value,
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        if definition.expected_confidence_min is not None:
            ok = assessment.confidence >= definition.expected_confidence_min
            checks.append(
                _gc(
                    "confidence_min",
                    f">= {definition.expected_confidence_min}",
                    str(assessment.confidence),
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        if definition.expected_confidence_max is not None:
            ok = assessment.confidence <= definition.expected_confidence_max
            checks.append(
                _gc(
                    "confidence_max",
                    f"<= {definition.expected_confidence_max}",
                    str(assessment.confidence),
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        ok = len(assessment.key_factors) >= 1
        checks.append(
            _gc(
                "key_factors_present",
                ">= 1 factor",
                str(len(assessment.key_factors)),
                ok,
            )
        )
        if ok:
            checks_passed += 1

        ok = len(assessment.summary.strip()) > 0
        checks.append(
            _gc(
                "summary_present",
                "non-empty",
                f"{len(assessment.summary)} chars",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        ok = len(assessment.risks) >= 1
        checks.append(
            _gc(
                "risks_present",
                ">= 1 risk",
                str(len(assessment.risks)),
                ok,
            )
        )
        if ok:
            checks_passed += 1

        all_passed = all(c.passed for c in checks)
        return GraderResult(
            passed=all_passed,
            details=_serialize_checks(checks),
            checks_run=len(checks),
            checks_passed=checks_passed,
        )

    def grade_recommendation(
        self,
        recommendation: PositionRecommendation,
        definition: EvalDefinition,
    ) -> GraderResult:
        """Run code-based assertions on a position recommendation."""
        checks: list[GraderCheck] = []
        checks_passed = 0

        if definition.expected_direction is not None:
            ok = recommendation.direction == definition.expected_direction
            checks.append(
                _gc(
                    "direction",
                    definition.expected_direction.value,
                    recommendation.direction.value,
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        if definition.expected_confidence_min is not None:
            ok = recommendation.confidence >= definition.expected_confidence_min
            checks.append(
                _gc(
                    "confidence_min",
                    f">= {definition.expected_confidence_min}",
                    str(recommendation.confidence),
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        if definition.expected_confidence_max is not None:
            ok = recommendation.confidence <= definition.expected_confidence_max
            checks.append(
                _gc(
                    "confidence_max",
                    f"<= {definition.expected_confidence_max}",
                    str(recommendation.confidence),
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        # entry_criteria and exit_criteria are str fields, not list[str]
        _min_len = 20
        entry_text = recommendation.entry_criteria.strip()
        ok = len(entry_text) >= _min_len
        checks.append(
            _gc(
                "entry_criteria_present",
                f">= {_min_len} chars",
                f"{len(entry_text)} chars",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        exit_text = recommendation.exit_criteria.strip()
        ok = len(exit_text) >= _min_len
        checks.append(
            _gc(
                "exit_criteria_present",
                f">= {_min_len} chars",
                f"{len(exit_text)} chars",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        all_passed = all(c.passed for c in checks)
        return GraderResult(
            passed=all_passed,
            details=_serialize_checks(checks),
            checks_run=len(checks),
            checks_passed=checks_passed,
        )


class ModelGrader:
    """LLM-as-judge grader for qualitative assessment fields.

    Uses heuristic checks for reliability and speed. Evaluates whether
    key_factors are specific and data-cited, summaries are actionable,
    and analysis is internally consistent.
    """

    _MIN_SPECIFICITY_RATIO = 2
    _MIN_RISK_DETAIL_LEN = 15
    _MIN_SUMMARY_LEN = 20

    def grade_assessment(
        self,
        assessment: DomainAssessment,
        definition: EvalDefinition,
    ) -> GraderResult:
        """Grade an assessment using heuristic rubric checks."""
        checks: list[GraderCheck] = []
        checks_passed = 0

        # Specificity: key_factors should contain numbers or data
        data_bearing = sum(
            1
            for f in assessment.key_factors
            if any(c.isdigit() for c in f) or "%" in f or "$" in f
        )
        threshold = max(1, len(assessment.key_factors) // self._MIN_SPECIFICITY_RATIO)
        ok = data_bearing >= threshold
        checks.append(
            _gc(
                "specificity",
                f">= {threshold} data-bearing factors",
                f"{data_bearing} of {len(assessment.key_factors)}",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        # Consistency: direction should align with sentiment
        bullish_words = {"bullish", "upside", "growth", "strong", "positive", "support"}
        bearish_words = {"bearish", "downside", "decline", "weak", "negative", "resistance"}
        factors_text = " ".join(assessment.key_factors).lower()
        bull_count = sum(1 for w in bullish_words if w in factors_text)
        bear_count = sum(1 for w in bearish_words if w in factors_text)

        if assessment.direction == SignalDirection.BULLISH:
            ok = bull_count >= bear_count
        elif assessment.direction == SignalDirection.BEARISH:
            ok = bear_count >= bull_count
        else:
            ok = True  # NEUTRAL is always consistent
        checks.append(
            _gc(
                "consistency",
                f"factors align with {assessment.direction.value}",
                f"bull={bull_count} bear={bear_count}",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        # Summary length
        ok = len(assessment.summary.strip()) >= self._MIN_SUMMARY_LEN
        checks.append(
            _gc(
                "summary_length",
                f">= {self._MIN_SUMMARY_LEN} chars",
                f"{len(assessment.summary.strip())} chars",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        # Risk specificity
        risk_specific = sum(1 for r in assessment.risks if len(r) > self._MIN_RISK_DETAIL_LEN)
        risk_threshold = max(1, len(assessment.risks) // self._MIN_SPECIFICITY_RATIO)
        ok = risk_specific >= risk_threshold
        checks.append(
            _gc(
                "risk_specificity",
                f">= {risk_threshold} detailed risks",
                f"{risk_specific} of {len(assessment.risks)}",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        all_passed = all(c.passed for c in checks)
        return GraderResult(
            passed=all_passed,
            details=_serialize_checks(checks),
            checks_run=len(checks),
            checks_passed=checks_passed,
        )


@dataclass(frozen=True)
class OutcomeRecord:
    """A single outcome for calibration comparison."""

    direction: SignalDirection
    confidence: float
    pnl_pct: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence):
            raise ValueError(f"confidence must be finite, got {self.confidence}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if not math.isfinite(self.pnl_pct):
            raise ValueError(f"pnl_pct must be finite, got {self.pnl_pct}")


class OutcomeGrader:
    """Direction/confidence vs actual P&L calibration grader.

    Compares recommendation direction and confidence against actual outcomes.
    A well-calibrated agent should have ~X% accuracy at X% confidence.
    """

    def grade_calibration(
        self,
        outcomes: list[OutcomeRecord],
        definition: EvalDefinition,
    ) -> GraderResult:
        """Grade calibration across a set of historical outcomes."""
        if not outcomes:
            return GraderResult(
                passed=False,
                details=json.dumps({"error": "no outcomes to grade"}),
                checks_run=0,
                checks_passed=0,
            )

        checks: list[GraderCheck] = []
        checks_passed = 0

        # Overall direction accuracy
        correct = sum(1 for o in outcomes if self._direction_correct(o.direction, o.pnl_pct))
        accuracy = correct / len(outcomes)
        ok = accuracy >= 0.5  # noqa: PLR2004
        checks.append(
            _gc(
                "direction_accuracy",
                ">= 0.50",
                f"{accuracy:.3f}",
                ok,
            )
        )
        if ok:
            checks_passed += 1

        # High-confidence calibration
        high_conf = [o for o in outcomes if o.confidence >= 0.7]  # noqa: PLR2004
        if high_conf:
            high_correct = sum(
                1 for o in high_conf if self._direction_correct(o.direction, o.pnl_pct)
            )
            high_accuracy = high_correct / len(high_conf)
            ok = high_accuracy >= accuracy
            checks.append(
                _gc(
                    "high_confidence_calibration",
                    f">= {accuracy:.3f} (overall accuracy)",
                    f"{high_accuracy:.3f} ({len(high_conf)} samples)",
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        # Average P&L for correct-direction calls
        correct_pnls = [
            o.pnl_pct for o in outcomes if self._direction_correct(o.direction, o.pnl_pct)
        ]
        if correct_pnls:
            avg_pnl = sum(correct_pnls) / len(correct_pnls)
            ok = avg_pnl > 0.0
            checks.append(
                _gc(
                    "avg_correct_pnl",
                    "> 0.0%",
                    f"{avg_pnl:.2f}%",
                    ok,
                )
            )
            if ok:
                checks_passed += 1

        all_passed = all(c.passed for c in checks)
        return GraderResult(
            passed=all_passed,
            details=_serialize_checks(checks),
            checks_run=len(checks),
            checks_passed=checks_passed,
        )

    @staticmethod
    def _direction_correct(direction: SignalDirection, pnl_pct: float) -> bool:
        """Check if the direction prediction matches the actual P&L outcome."""
        if not math.isfinite(pnl_pct):
            return False
        if direction == SignalDirection.BULLISH:
            return pnl_pct > 0.0
        if direction == SignalDirection.BEARISH:
            return pnl_pct < 0.0
        # NEUTRAL — correct if P&L is within +-5%
        return abs(pnl_pct) <= 5.0  # noqa: PLR2004
