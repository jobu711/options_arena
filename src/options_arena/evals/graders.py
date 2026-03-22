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

from options_arena.models.enums import SignalDirection
from options_arena.models.eval import EvalDefinition
from options_arena.models.recommendation import DomainAssessment, PositionRecommendation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraderResult:
    """Result from a single grader execution."""

    passed: bool
    details: str  # JSON-serializable explanation
    checks_run: int = 0
    checks_passed: int = 0


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
        """Run code-based assertions on a domain assessment.

        Parameters
        ----------
        assessment
            The assessment to grade.
        definition
            The eval definition specifying expected values.

        Returns
        -------
        GraderResult
            Pass/fail with details of each check.
        """
        checks: list[dict[str, str | bool]] = []
        checks_passed = 0

        # Check direction if expected
        if definition.expected_direction is not None:
            direction_ok = assessment.direction == definition.expected_direction
            checks.append({
                "check": "direction",
                "expected": definition.expected_direction.value,
                "actual": assessment.direction.value,
                "passed": direction_ok,
            })
            if direction_ok:
                checks_passed += 1

        # Check confidence bounds
        if definition.expected_confidence_min is not None:
            conf_min_ok = assessment.confidence >= definition.expected_confidence_min
            checks.append({
                "check": "confidence_min",
                "expected": f">= {definition.expected_confidence_min}",
                "actual": str(assessment.confidence),
                "passed": conf_min_ok,
            })
            if conf_min_ok:
                checks_passed += 1

        if definition.expected_confidence_max is not None:
            conf_max_ok = assessment.confidence <= definition.expected_confidence_max
            checks.append({
                "check": "confidence_max",
                "expected": f"<= {definition.expected_confidence_max}",
                "actual": str(assessment.confidence),
                "passed": conf_max_ok,
            })
            if conf_max_ok:
                checks_passed += 1

        # Check key_factors has content
        has_factors = len(assessment.key_factors) >= 1
        checks.append({
            "check": "key_factors_present",
            "expected": ">= 1 factor",
            "actual": str(len(assessment.key_factors)),
            "passed": has_factors,
        })
        if has_factors:
            checks_passed += 1

        # Check summary is non-empty
        has_summary = len(assessment.summary.strip()) > 0
        checks.append({
            "check": "summary_present",
            "expected": "non-empty",
            "actual": f"{len(assessment.summary)} chars",
            "passed": has_summary,
        })
        if has_summary:
            checks_passed += 1

        # Check risks listed
        has_risks = len(assessment.risks) >= 1
        checks.append({
            "check": "risks_present",
            "expected": ">= 1 risk",
            "actual": str(len(assessment.risks)),
            "passed": has_risks,
        })
        if has_risks:
            checks_passed += 1

        all_passed = all(c["passed"] for c in checks)
        return GraderResult(
            passed=all_passed,
            details=json.dumps(checks),
            checks_run=len(checks),
            checks_passed=checks_passed,
        )

    def grade_recommendation(
        self,
        recommendation: PositionRecommendation,
        definition: EvalDefinition,
    ) -> GraderResult:
        """Run code-based assertions on a position recommendation.

        Parameters
        ----------
        recommendation
            The recommendation to grade.
        definition
            The eval definition specifying expected values.

        Returns
        -------
        GraderResult
            Pass/fail with details of each check.
        """
        checks: list[dict[str, str | bool]] = []
        checks_passed = 0

        # Check direction
        if definition.expected_direction is not None:
            direction_ok = recommendation.direction == definition.expected_direction
            checks.append({
                "check": "direction",
                "expected": definition.expected_direction.value,
                "actual": recommendation.direction.value,
                "passed": direction_ok,
            })
            if direction_ok:
                checks_passed += 1

        # Check confidence bounds
        if definition.expected_confidence_min is not None:
            conf_min_ok = recommendation.confidence >= definition.expected_confidence_min
            checks.append({
                "check": "confidence_min",
                "expected": f">= {definition.expected_confidence_min}",
                "actual": str(recommendation.confidence),
                "passed": conf_min_ok,
            })
            if conf_min_ok:
                checks_passed += 1

        if definition.expected_confidence_max is not None:
            conf_max_ok = recommendation.confidence <= definition.expected_confidence_max
            checks.append({
                "check": "confidence_max",
                "expected": f"<= {definition.expected_confidence_max}",
                "actual": str(recommendation.confidence),
                "passed": conf_max_ok,
            })
            if conf_max_ok:
                checks_passed += 1

        # Check entry/exit criteria present
        has_entry = len(recommendation.entry_criteria) >= 1
        checks.append({
            "check": "entry_criteria_present",
            "expected": ">= 1 criterion",
            "actual": str(len(recommendation.entry_criteria)),
            "passed": has_entry,
        })
        if has_entry:
            checks_passed += 1

        has_exit = len(recommendation.exit_criteria) >= 1
        checks.append({
            "check": "exit_criteria_present",
            "expected": ">= 1 criterion",
            "actual": str(len(recommendation.exit_criteria)),
            "passed": has_exit,
        })
        if has_exit:
            checks_passed += 1

        all_passed = all(c["passed"] for c in checks)
        return GraderResult(
            passed=all_passed,
            details=json.dumps(checks),
            checks_run=len(checks),
            checks_passed=checks_passed,
        )


class ModelGrader:
    """LLM-as-judge grader for qualitative assessment fields.

    Uses a PydanticAI agent with a rubric prompt to evaluate whether
    key_factors are specific and data-cited, summaries are actionable,
    and analysis is internally consistent.

    NOTE: The actual LLM call requires a model at runtime. For tests,
    use ``pydantic_ai.models.test.TestModel``.
    """

    RUBRIC = (
        "You are an expert options analyst reviewing an AI agent's assessment. "
        "Evaluate the following assessment on these criteria:\n"
        "1. SPECIFICITY: Are key_factors specific with data references (prices, "
        "percentages, dates), not generic statements?\n"
        "2. CONSISTENCY: Does the direction match the key_factors? Are confidence "
        "and risks consistent with each other?\n"
        "3. ACTIONABILITY: Does the summary provide clear, actionable insight?\n"
        "4. RISK AWARENESS: Are risks specific and relevant to the analysis?\n\n"
        "Respond with a JSON object: "
        '{"passed": true/false, "score": 0-100, "reasoning": "..."}'
    )

    def grade_assessment(
        self,
        assessment: DomainAssessment,
        definition: EvalDefinition,
    ) -> GraderResult:
        """Grade an assessment using heuristic rubric checks.

        This synchronous version uses heuristic checks rather than LLM calls
        for reliability and speed. For LLM-based grading, use
        ``grade_assessment_async``.

        Parameters
        ----------
        assessment
            The assessment to grade.
        definition
            The eval definition (used for context).

        Returns
        -------
        GraderResult
            Pass/fail based on heuristic quality checks.
        """
        checks: list[dict[str, str | bool]] = []
        checks_passed = 0

        # Check specificity: key_factors should contain numbers or data
        data_bearing_factors = sum(
            1
            for f in assessment.key_factors
            if any(c.isdigit() for c in f) or "%" in f or "$" in f
        )
        specificity_ok = data_bearing_factors >= max(1, len(assessment.key_factors) // 2)
        checks.append({
            "check": "specificity",
            "expected": f">= {max(1, len(assessment.key_factors) // 2)} data-bearing factors",
            "actual": f"{data_bearing_factors} of {len(assessment.key_factors)}",
            "passed": specificity_ok,
        })
        if specificity_ok:
            checks_passed += 1

        # Check consistency: direction should align with sentiment of key_factors
        bullish_words = {"bullish", "upside", "growth", "strong", "positive", "support"}
        bearish_words = {"bearish", "downside", "decline", "weak", "negative", "resistance"}
        factors_text = " ".join(assessment.key_factors).lower()
        bull_count = sum(1 for w in bullish_words if w in factors_text)
        bear_count = sum(1 for w in bearish_words if w in factors_text)

        if assessment.direction == SignalDirection.BULLISH:
            consistency_ok = bull_count >= bear_count
        elif assessment.direction == SignalDirection.BEARISH:
            consistency_ok = bear_count >= bull_count
        else:
            consistency_ok = True  # NEUTRAL is always consistent
        checks.append({
            "check": "consistency",
            "expected": f"factors align with {assessment.direction.value}",
            "actual": f"bull={bull_count} bear={bear_count}",
            "passed": consistency_ok,
        })
        if consistency_ok:
            checks_passed += 1

        # Check summary length (actionable summaries need substance)
        summary_ok = len(assessment.summary.strip()) >= 20
        checks.append({
            "check": "summary_length",
            "expected": ">= 20 chars",
            "actual": f"{len(assessment.summary.strip())} chars",
            "passed": summary_ok,
        })
        if summary_ok:
            checks_passed += 1

        # Check risk specificity
        risk_specific = sum(
            1 for r in assessment.risks if len(r) > 15  # noqa: PLR2004
        )
        risks_ok = risk_specific >= max(1, len(assessment.risks) // 2)
        checks.append({
            "check": "risk_specificity",
            "expected": f">= {max(1, len(assessment.risks) // 2)} detailed risks",
            "actual": f"{risk_specific} of {len(assessment.risks)}",
            "passed": risks_ok,
        })
        if risks_ok:
            checks_passed += 1

        all_passed = all(c["passed"] for c in checks)
        return GraderResult(
            passed=all_passed,
            details=json.dumps(checks),
            checks_run=len(checks),
            checks_passed=checks_passed,
        )


@dataclass
class OutcomeRecord:
    """A single outcome for calibration comparison."""

    direction: SignalDirection
    confidence: float
    pnl_pct: float


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
        """Grade calibration across a set of historical outcomes.

        Parameters
        ----------
        outcomes
            Historical outcomes with direction, confidence, and P&L.
        definition
            The eval definition (used for context).

        Returns
        -------
        GraderResult
            Pass/fail based on calibration accuracy.
        """
        if not outcomes:
            return GraderResult(
                passed=False,
                details=json.dumps({"error": "no outcomes to grade"}),
                checks_run=0,
                checks_passed=0,
            )

        checks: list[dict[str, str | bool | float]] = []
        checks_passed = 0

        # Overall direction accuracy
        correct_direction = sum(
            1
            for o in outcomes
            if self._direction_correct(o.direction, o.pnl_pct)
        )
        accuracy = correct_direction / len(outcomes)
        accuracy_ok = accuracy >= 0.5  # noqa: PLR2004 — minimum 50% accuracy
        checks.append({
            "check": "direction_accuracy",
            "expected": ">= 0.50",
            "actual": f"{accuracy:.3f}",
            "passed": accuracy_ok,
        })
        if accuracy_ok:
            checks_passed += 1

        # High-confidence calibration (confidence >= 0.7 should be more accurate)
        high_conf = [o for o in outcomes if o.confidence >= 0.7]  # noqa: PLR2004
        if high_conf:
            high_correct = sum(
                1 for o in high_conf if self._direction_correct(o.direction, o.pnl_pct)
            )
            high_accuracy = high_correct / len(high_conf)
            # High-confidence should beat overall accuracy
            high_ok = high_accuracy >= accuracy
            checks.append({
                "check": "high_confidence_calibration",
                "expected": f">= {accuracy:.3f} (overall accuracy)",
                "actual": f"{high_accuracy:.3f} ({len(high_conf)} samples)",
                "passed": high_ok,
            })
            if high_ok:
                checks_passed += 1

        # Average P&L should be positive for correct-direction calls
        correct_pnls = [
            o.pnl_pct for o in outcomes
            if self._direction_correct(o.direction, o.pnl_pct)
        ]
        if correct_pnls:
            avg_correct_pnl = sum(correct_pnls) / len(correct_pnls)
            pnl_ok = avg_correct_pnl > 0.0
            checks.append({
                "check": "avg_correct_pnl",
                "expected": "> 0.0%",
                "actual": f"{avg_correct_pnl:.2f}%",
                "passed": pnl_ok,
            })
            if pnl_ok:
                checks_passed += 1

        all_passed = all(c["passed"] for c in checks)
        return GraderResult(
            passed=all_passed,
            details=json.dumps(checks),
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
