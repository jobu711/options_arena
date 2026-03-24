"""Tests for ADX/ATR%/RSI condition dimensions on OutcomeWithContext.

Covers the new classifier functions and extended OutcomeWithContext fields
added in Task #779, and the enriched mining/rule generation from Task #780.
"""

from __future__ import annotations

import math

import pytest

from options_arena.learning.strategy_book import (
    MIN_CELL_SAMPLES,
    OutcomeWithContext,
    PatternCell,
    _classify_adx,
    _classify_atr_pct,
    generate_rules,
    mine_patterns,
    render_learned_patterns,
)
from options_arena.models import ConditionOperator, RuleStatus, StrategyRule

# ---------------------------------------------------------------------------
# TestClassifyAdx
# ---------------------------------------------------------------------------


class TestClassifyAdx:
    """Tests for ``_classify_adx()`` bucket classification."""

    @pytest.mark.parametrize(
        ("adx", "expected"),
        [
            (10.0, "weak"),
            (20.0, "moderate"),
            (25.0, "moderate"),
            (35.0, "strong"),
            (None, None),
        ],
    )
    def test_classify_adx(self, adx: float | None, expected: str | None) -> None:
        assert _classify_adx(adx) == expected

    def test_boundary_zero(self) -> None:
        """ADX of 0.0 falls in 'weak' bucket."""
        assert _classify_adx(0.0) == "weak"

    def test_boundary_30(self) -> None:
        """ADX of 30.0 falls in 'strong' bucket (lower-bound inclusive)."""
        assert _classify_adx(30.0) == "strong"

    def test_overflow_above_100(self) -> None:
        """ADX above 100 falls through to last bucket fallback."""
        assert _classify_adx(150.0) == "strong"


# ---------------------------------------------------------------------------
# TestClassifyAtrPct
# ---------------------------------------------------------------------------


class TestClassifyAtrPct:
    """Tests for ``_classify_atr_pct()`` bucket classification."""

    @pytest.mark.parametrize(
        ("atr_pct", "expected"),
        [
            (0.5, "low"),
            (1.5, "medium"),
            (2.0, "medium"),
            (4.0, "high"),
            (None, None),
        ],
    )
    def test_classify_atr_pct(self, atr_pct: float | None, expected: str | None) -> None:
        assert _classify_atr_pct(atr_pct) == expected

    def test_boundary_zero(self) -> None:
        """ATR% of 0.0 falls in 'low' bucket."""
        assert _classify_atr_pct(0.0) == "low"

    def test_boundary_3(self) -> None:
        """ATR% of 3.0 falls in 'high' bucket (lower-bound inclusive)."""
        assert _classify_atr_pct(3.0) == "high"

    def test_overflow_above_100(self) -> None:
        """ATR% above 100 falls through to last bucket fallback."""
        assert _classify_atr_pct(200.0) == "high"


# ---------------------------------------------------------------------------
# TestOutcomeWithContextExtension
# ---------------------------------------------------------------------------


class TestOutcomeWithContextExtension:
    """Tests for backward compatibility and new fields on OutcomeWithContext."""

    def test_backward_compatible_construction(self) -> None:
        """Existing construction without new fields works."""
        outcome = OutcomeWithContext(
            sector="Information Technology",
            iv_level=50.0,
            dte_at_entry=30,
            direction="bullish",
            return_pct=5.0,
            is_winner=True,
        )
        assert outcome.sector == "Information Technology"
        assert outcome.adx is None
        assert outcome.atr_pct is None
        assert outcome.rsi is None

    def test_new_fields_populated(self) -> None:
        """Construction with adx, atr_pct, rsi works."""
        outcome = OutcomeWithContext(
            sector="Energy",
            iv_level=40.0,
            dte_at_entry=20,
            direction="bearish",
            return_pct=-3.0,
            is_winner=False,
            adx=25.0,
            atr_pct=2.5,
            rsi=45.0,
        )
        assert outcome.adx == pytest.approx(25.0)
        assert outcome.atr_pct == pytest.approx(2.5)
        assert outcome.rsi == pytest.approx(45.0)

    def test_new_fields_default_none(self) -> None:
        """New fields default to None."""
        outcome = OutcomeWithContext(
            sector="Financials",
            iv_level=30.0,
            dte_at_entry=50,
            direction="bullish",
            return_pct=1.0,
            is_winner=True,
        )
        assert outcome.adx is None
        assert outcome.atr_pct is None
        assert outcome.rsi is None

    def test_rejects_nan_adx(self) -> None:
        """NaN adx is rejected by validator."""
        with pytest.raises(ValueError, match="context field must be finite"):
            OutcomeWithContext(
                sector="Tech",
                iv_level=50.0,
                dte_at_entry=30,
                direction="bullish",
                return_pct=1.0,
                is_winner=True,
                adx=float("nan"),
            )

    def test_rejects_inf_atr_pct(self) -> None:
        """Inf atr_pct is rejected by validator."""
        with pytest.raises(ValueError, match="context field must be finite"):
            OutcomeWithContext(
                sector="Tech",
                iv_level=50.0,
                dte_at_entry=30,
                direction="bullish",
                return_pct=1.0,
                is_winner=True,
                atr_pct=math.inf,
            )

    def test_rejects_neg_inf_rsi(self) -> None:
        """Negative inf rsi is rejected by validator."""
        with pytest.raises(ValueError, match="context field must be finite"):
            OutcomeWithContext(
                sector="Tech",
                iv_level=50.0,
                dte_at_entry=30,
                direction="bullish",
                return_pct=1.0,
                is_winner=True,
                rsi=float("-inf"),
            )

    def test_frozen_immutability(self) -> None:
        """OutcomeWithContext is frozen — new fields cannot be mutated."""
        outcome = OutcomeWithContext(
            sector="Tech",
            iv_level=50.0,
            dte_at_entry=30,
            direction="bullish",
            return_pct=1.0,
            is_winner=True,
            adx=25.0,
        )
        with pytest.raises(Exception):  # noqa: B017
            outcome.adx = 30.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Helper: build N identical outcomes for mining tests
# ---------------------------------------------------------------------------


def _make_outcomes(
    n: int,
    *,
    sector: str = "Information Technology",
    iv_level: float = 40.0,
    dte_at_entry: int = 20,
    direction: str = "bullish",
    return_pct: float = 5.0,
    is_winner: bool = True,
    adx: float | None = None,
    atr_pct: float | None = None,
) -> list[OutcomeWithContext]:
    """Factory for N identical outcomes with optional ADX/ATR% values."""
    return [
        OutcomeWithContext(
            sector=sector,
            iv_level=iv_level,
            dte_at_entry=dte_at_entry,
            direction=direction,
            return_pct=return_pct,
            is_winner=is_winner,
            adx=adx,
            atr_pct=atr_pct,
        )
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# TestMineWithConditions (#780)
# ---------------------------------------------------------------------------


class TestMineWithConditions:
    """Tests for mine_patterns() with ADX/ATR% condition dimensions."""

    def test_groups_by_adx_bucket(self) -> None:
        """Outcomes with different ADX values produce separate pattern cells."""
        # 20 weak (adx=10) + 20 strong (adx=35) -> 2 cells
        outcomes = _make_outcomes(MIN_CELL_SAMPLES, adx=10.0) + _make_outcomes(
            MIN_CELL_SAMPLES, adx=35.0
        )
        cells = mine_patterns(outcomes)
        assert len(cells) == 2
        adx_buckets = {c.adx_bucket for c in cells}
        assert adx_buckets == {"weak", "strong"}

    def test_unknown_adx_separate_group(self) -> None:
        """Outcomes with adx=None are grouped under 'unknown' bucket."""
        outcomes = _make_outcomes(MIN_CELL_SAMPLES, adx=None) + _make_outcomes(
            MIN_CELL_SAMPLES, adx=25.0
        )
        cells = mine_patterns(outcomes)
        assert len(cells) == 2
        adx_buckets = {c.adx_bucket for c in cells}
        assert adx_buckets == {"unknown", "moderate"}

    def test_min_samples_enforced(self) -> None:
        """Cells with < MIN_CELL_SAMPLES outcomes are excluded."""
        # 20 of one type, 5 of another -> only 1 cell returned
        outcomes = _make_outcomes(MIN_CELL_SAMPLES, adx=10.0) + _make_outcomes(5, adx=35.0)
        cells = mine_patterns(outcomes)
        assert len(cells) == 1
        assert cells[0].adx_bucket == "weak"

    def test_backward_compatible_without_conditions(self) -> None:
        """Outcomes without adx/atr_pct still mine correctly (all 'unknown')."""
        outcomes = _make_outcomes(MIN_CELL_SAMPLES)
        cells = mine_patterns(outcomes)
        assert len(cells) == 1
        assert cells[0].adx_bucket == "unknown"
        assert cells[0].atr_bucket == "unknown"

    def test_groups_by_atr_bucket(self) -> None:
        """Outcomes with different ATR% values produce separate pattern cells."""
        outcomes = _make_outcomes(MIN_CELL_SAMPLES, atr_pct=0.5) + _make_outcomes(
            MIN_CELL_SAMPLES, atr_pct=4.0
        )
        cells = mine_patterns(outcomes)
        assert len(cells) == 2
        atr_buckets = {c.atr_bucket for c in cells}
        assert atr_buckets == {"low", "high"}

    def test_combined_adx_atr_grouping(self) -> None:
        """ADX and ATR% combine to form distinct cells."""
        outcomes = (
            _make_outcomes(MIN_CELL_SAMPLES, adx=10.0, atr_pct=0.5)
            + _make_outcomes(MIN_CELL_SAMPLES, adx=10.0, atr_pct=4.0)
            + _make_outcomes(MIN_CELL_SAMPLES, adx=35.0, atr_pct=0.5)
        )
        cells = mine_patterns(outcomes)
        assert len(cells) == 3
        combos = {(c.adx_bucket, c.atr_bucket) for c in cells}
        assert combos == {("weak", "low"), ("weak", "high"), ("strong", "low")}

    def test_pattern_cell_carries_adx_atr_fields(self) -> None:
        """PatternCell includes adx_bucket and atr_bucket from mining."""
        outcomes = _make_outcomes(MIN_CELL_SAMPLES, adx=25.0, atr_pct=2.0)
        cells = mine_patterns(outcomes)
        assert len(cells) == 1
        cell = cells[0]
        assert cell.adx_bucket == "moderate"
        assert cell.atr_bucket == "medium"

    def test_many_small_cells_filtered(self) -> None:
        """Many unique 6-tuples with few samples each are all filtered out."""
        # Each unique (adx, atr_pct) combo creates a different cell with only 5 samples
        outcomes: list[OutcomeWithContext] = []
        for adx_val in [5.0, 15.0, 25.0, 35.0]:
            for atr_val in [0.5, 2.0, 4.0]:
                outcomes.extend(_make_outcomes(5, adx=adx_val, atr_pct=atr_val))
        cells = mine_patterns(outcomes)
        assert len(cells) == 0


# ---------------------------------------------------------------------------
# TestGenerateRulesWithConditions (#780)
# ---------------------------------------------------------------------------


class TestGenerateRulesWithConditions:
    """Tests for generate_rules() with ADX/ATR% condition dimensions."""

    def _make_cell(
        self,
        *,
        adx_bucket: str = "unknown",
        atr_bucket: str = "unknown",
        win_rate: float = 0.85,
    ) -> PatternCell:
        """Factory for a PatternCell with configurable ADX/ATR buckets."""
        return PatternCell(
            sector="Information Technology",
            iv_bucket="mid_low",
            dte_bucket="short",
            direction="bullish",
            adx_bucket=adx_bucket,
            atr_bucket=atr_bucket,
            win_rate=win_rate,
            avg_return=5.0,
            sample_size=30,
        )

    def test_adx_condition_in_rule(self) -> None:
        """Rule includes StrategyCondition for adx_bucket when not 'unknown'."""
        cell = self._make_cell(adx_bucket="strong")
        rules = generate_rules([cell])
        assert len(rules) == 1
        adx_conditions = [c for c in rules[0].conditions if c.field == "adx_bucket"]
        assert len(adx_conditions) == 1
        assert adx_conditions[0].operator == ConditionOperator.EQ
        assert adx_conditions[0].value == "strong"

    def test_atr_condition_in_rule(self) -> None:
        """Rule includes StrategyCondition for atr_bucket when not 'unknown'."""
        cell = self._make_cell(atr_bucket="medium")
        rules = generate_rules([cell])
        assert len(rules) == 1
        atr_conditions = [c for c in rules[0].conditions if c.field == "atr_bucket"]
        assert len(atr_conditions) == 1
        assert atr_conditions[0].operator == ConditionOperator.EQ
        assert atr_conditions[0].value == "medium"

    def test_unknown_bucket_excluded_from_conditions(self) -> None:
        """'unknown' ADX/ATR buckets produce no ADX/ATR conditions in rule."""
        cell = self._make_cell(adx_bucket="unknown", atr_bucket="unknown")
        rules = generate_rules([cell])
        assert len(rules) == 1
        condition_fields = {c.field for c in rules[0].conditions}
        assert "adx_bucket" not in condition_fields
        assert "atr_bucket" not in condition_fields

    def test_pattern_text_includes_conditions(self) -> None:
        """Pattern text includes ADX and ATR bucket labels when present."""
        cell = self._make_cell(adx_bucket="strong", atr_bucket="high")
        rules = generate_rules([cell])
        assert len(rules) == 1
        assert "ADX:strong" in rules[0].pattern
        assert "ATR:high" in rules[0].pattern

    def test_pattern_text_excludes_unknown(self) -> None:
        """Pattern text does not include ADX/ATR labels when 'unknown'."""
        cell = self._make_cell(adx_bucket="unknown", atr_bucket="unknown")
        rules = generate_rules([cell])
        assert len(rules) == 1
        assert "ADX:" not in rules[0].pattern
        assert "ATR:" not in rules[0].pattern

    def test_both_adx_and_atr_conditions(self) -> None:
        """Rule includes both ADX and ATR conditions when both are classified."""
        cell = self._make_cell(adx_bucket="moderate", atr_bucket="low")
        rules = generate_rules([cell])
        assert len(rules) == 1
        condition_fields = [c.field for c in rules[0].conditions]
        assert "adx_bucket" in condition_fields
        assert "atr_bucket" in condition_fields

    def test_existing_conditions_preserved(self) -> None:
        """Sector, IV, DTE, direction conditions are still present with new conditions."""
        cell = self._make_cell(adx_bucket="strong", atr_bucket="medium")
        rules = generate_rules([cell])
        assert len(rules) == 1
        condition_fields = [c.field for c in rules[0].conditions]
        assert "sector" in condition_fields
        assert "iv_rank_min" in condition_fields
        assert "iv_rank_max" in condition_fields
        assert "dte_min" in condition_fields
        assert "dte_max" in condition_fields
        assert "direction" in condition_fields
        assert "adx_bucket" in condition_fields
        assert "atr_bucket" in condition_fields


# ---------------------------------------------------------------------------
# TestRenderWithConditions (#780)
# ---------------------------------------------------------------------------


class TestRenderWithConditions:
    """Tests for render_learned_patterns() with condition-enriched rules."""

    def test_condition_enriched_rules_render(self) -> None:
        """Rules with condition dimensions render in <<<LEARNED_PATTERNS>>> block."""
        from datetime import UTC, datetime

        rule = StrategyRule(
            rule_id="rule_test_001",
            pattern=(
                "Information Technology | IV:mid_low | DTE:short | bullish"
                " | ADX:strong | ATR:medium -> 85% win rate"
            ),
            conditions=[],
            win_rate=0.85,
            avg_return=5.0,
            sample_size=30,
            status=RuleStatus.APPROVED,
            confidence=0.9,
            created_at=datetime.now(UTC),
        )
        text = render_learned_patterns([rule])
        assert "<<<LEARNED_PATTERNS>>>" in text
        assert "<<<END_LEARNED_PATTERNS>>>" in text
        assert "ADX:strong" in text
        assert "ATR:medium" in text
        assert "Strong pattern:" in text
        assert "85.0%" in text

    def test_multiple_enriched_rules_render(self) -> None:
        """Multiple condition-enriched rules render correctly."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        rules = [
            StrategyRule(
                rule_id="rule_test_002",
                pattern="Energy | IV:high | DTE:medium | bearish | ADX:weak -> 70% win rate",
                conditions=[],
                win_rate=0.70,
                avg_return=-2.0,
                sample_size=25,
                status=RuleStatus.APPROVED,
                confidence=0.5,
                created_at=now,
            ),
            StrategyRule(
                rule_id="rule_test_003",
                pattern=(
                    "Financials | IV:low | DTE:long | bullish"
                    " | ADX:moderate | ATR:low -> 90% win rate"
                ),
                conditions=[],
                win_rate=0.90,
                avg_return=8.0,
                sample_size=40,
                status=RuleStatus.APPROVED,
                confidence=0.85,
                created_at=now,
            ),
        ]
        text = render_learned_patterns(rules)
        assert "ADX:weak" in text
        assert "ADX:moderate" in text
        assert "ATR:low" in text

    def test_unapproved_enriched_rules_excluded(self) -> None:
        """Candidate rules with condition dimensions are not rendered."""
        from datetime import UTC, datetime

        rule = StrategyRule(
            rule_id="rule_test_004",
            pattern="Energy | IV:high | DTE:short | bullish | ADX:strong -> 80% win rate",
            conditions=[],
            win_rate=0.80,
            avg_return=3.0,
            sample_size=30,
            status=RuleStatus.CANDIDATE,
            confidence=0.7,
            created_at=datetime.now(UTC),
        )
        text = render_learned_patterns([rule])
        assert text == ""
