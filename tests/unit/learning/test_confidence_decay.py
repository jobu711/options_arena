"""Tests for confidence decay and auto-promote/demote in learning/confidence_decay.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from options_arena.learning.confidence_decay import (
    _DEMOTE_CONFIDENCE_THRESHOLD,
    _PROMOTE_CONFIDENCE_THRESHOLD,
    _PROMOTE_VALIDATION_COUNT,
    auto_promote_demote,
    decay_confidence,
    run_confidence_decay,
    validate_rules_against_outcomes,
)
from options_arena.learning.strategy_book import OutcomeWithContext
from options_arena.models import ConditionOperator, RuleStatus, StrategyCondition, StrategyRule

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    rule_id: str = "rule_test",
    status: RuleStatus = RuleStatus.CANDIDATE,
    confidence: float = 0.5,
    created_at: datetime = _NOW,
    last_validated: datetime | None = None,
    validation_count: int = 0,
    win_rate: float = 0.70,
    avg_return: float = 0.12,
    sample_size: int = 40,
    sector: str = "Information Technology",
    direction: str = "bullish",
) -> StrategyRule:
    conditions = [
        StrategyCondition(
            field="sector",
            operator=ConditionOperator.EQ,
            value=sector,
        ),
        StrategyCondition(
            field="direction",
            operator=ConditionOperator.EQ,
            value=direction,
        ),
    ]
    return StrategyRule(
        rule_id=rule_id,
        pattern=f"{sector} | {direction} -> {win_rate:.0%} win rate",
        conditions=conditions,
        win_rate=win_rate,
        avg_return=avg_return,
        sample_size=sample_size,
        status=status,
        created_at=created_at,
        confidence=confidence,
        last_validated=last_validated,
        validation_count=validation_count,
    )


def _make_outcome(
    sector: str = "Information Technology",
    direction: str = "bullish",
    is_winner: bool = True,
    return_pct: float = 0.15,
    iv_level: float = 60.0,
    dte_at_entry: int = 45,
) -> OutcomeWithContext:
    return OutcomeWithContext(
        sector=sector,
        iv_level=iv_level,
        dte_at_entry=dte_at_entry,
        direction=direction,
        return_pct=return_pct,
        is_winner=is_winner,
    )


# ---------------------------------------------------------------------------
# decay_confidence
# ---------------------------------------------------------------------------


class TestDecayConfidence:
    def test_no_decay_when_just_validated(self) -> None:
        """Zero months since validation -> no decay."""
        rule = _make_rule(confidence=0.5, last_validated=_NOW, validation_count=1)
        result = decay_confidence(rule, _NOW)
        assert result == pytest.approx(0.5, abs=0.001)

    def test_one_month_decay(self) -> None:
        """1-month decay: 0.5 * 0.95 ~ 0.475."""
        one_month_ago = _NOW - timedelta(days=30, hours=10, minutes=33, seconds=36)
        rule = _make_rule(
            confidence=0.5,
            last_validated=one_month_ago,
            validation_count=1,
        )
        result = decay_confidence(rule, _NOW)
        assert result == pytest.approx(0.475, abs=0.005)

    def test_three_month_decay(self) -> None:
        """3-month decay: 0.5 * 0.95^3 ~ 0.429."""
        three_months_ago = _NOW - timedelta(days=91, hours=7, minutes=40, seconds=48)
        rule = _make_rule(
            confidence=0.5,
            last_validated=three_months_ago,
            validation_count=1,
        )
        result = decay_confidence(rule, _NOW)
        expected = 0.5 * (0.95**3)
        assert result == pytest.approx(expected, abs=0.005)

    def test_never_validated_penalty(self) -> None:
        """50% penalty for never-validated rules."""
        one_month_ago = _NOW - timedelta(days=30, hours=10, minutes=33, seconds=36)
        rule = _make_rule(
            confidence=0.5,
            created_at=one_month_ago,
            last_validated=None,
            validation_count=0,
        )
        result = decay_confidence(rule, _NOW)
        # 0.5 * 0.95^1 * 0.5 ~ 0.2375
        expected = 0.5 * 0.95 * 0.5
        assert result == pytest.approx(expected, abs=0.005)

    def test_decay_clamped_to_zero(self) -> None:
        """Very old rules don't go negative."""
        very_old = _NOW - timedelta(days=3650)  # ~10 years ago
        rule = _make_rule(
            confidence=0.01,
            created_at=very_old,
            last_validated=None,
            validation_count=0,
        )
        result = decay_confidence(rule, _NOW)
        assert result >= 0.0

    def test_high_confidence_no_months_stays_same(self) -> None:
        """confidence=1.0 with 0 months stays 1.0."""
        rule = _make_rule(confidence=1.0, last_validated=_NOW, validation_count=1)
        result = decay_confidence(rule, _NOW)
        assert result == pytest.approx(1.0, abs=0.001)

    def test_uses_created_at_when_no_last_validated(self) -> None:
        """Falls back to created_at for reference date."""
        created = _NOW - timedelta(days=60)
        rule = _make_rule(
            confidence=0.8,
            created_at=created,
            last_validated=None,
            validation_count=1,  # has validation count but no last_validated timestamp
        )
        result = decay_confidence(rule, _NOW)
        # ~2 months of decay: 0.8 * 0.95^2 ~ 0.722
        expected = 0.8 * (0.95**2)
        assert result == pytest.approx(expected, abs=0.02)

    def test_future_date_no_decay(self) -> None:
        """If now < reference_date, return original confidence."""
        future = _NOW + timedelta(days=30)
        rule = _make_rule(confidence=0.7, last_validated=future, validation_count=1)
        result = decay_confidence(rule, _NOW)
        assert result == pytest.approx(0.7, abs=0.001)

    def test_result_clamped_to_one(self) -> None:
        """Confidence never exceeds 1.0 even with floating point drift."""
        rule = _make_rule(confidence=1.0, last_validated=_NOW, validation_count=3)
        result = decay_confidence(rule, _NOW)
        assert result <= 1.0

    def test_never_validated_with_count_zero_gets_penalty(self) -> None:
        """Only applies penalty when both last_validated is None AND validation_count == 0."""
        one_month_ago = _NOW - timedelta(days=30, hours=10, minutes=33, seconds=36)
        # Has validation count > 0 but no last_validated: no penalty
        rule_with_count = _make_rule(
            confidence=0.5,
            created_at=one_month_ago,
            last_validated=None,
            validation_count=3,
        )
        result_with_count = decay_confidence(rule_with_count, _NOW)

        # Has validation count == 0 and no last_validated: penalty
        rule_no_count = _make_rule(
            confidence=0.5,
            created_at=one_month_ago,
            last_validated=None,
            validation_count=0,
        )
        result_no_count = decay_confidence(rule_no_count, _NOW)

        # The penalized result should be roughly half
        assert result_no_count == pytest.approx(result_with_count * 0.5, abs=0.005)


# ---------------------------------------------------------------------------
# validate_rules_against_outcomes
# ---------------------------------------------------------------------------


class TestValidateRulesAgainstOutcomes:
    def test_validates_matching_outcomes(self) -> None:
        """Rule is validated when matching outcomes have sufficient win rate."""
        rule = _make_rule(win_rate=0.6, sector="Tech", direction="bullish")
        outcomes = [
            _make_outcome(sector="Tech", direction="bullish", is_winner=True) for _ in range(8)
        ] + [_make_outcome(sector="Tech", direction="bullish", is_winner=False) for _ in range(2)]
        result = validate_rules_against_outcomes([rule], outcomes)
        assert len(result) == 1
        assert result[0] == (rule.rule_id, True)  # 80% >= 60% * 80% = 48%

    def test_not_validated_low_win_rate(self) -> None:
        """Rule not validated when outcome win rate is below threshold."""
        rule = _make_rule(win_rate=0.9, sector="Tech", direction="bullish")
        outcomes = [
            _make_outcome(sector="Tech", direction="bullish", is_winner=True) for _ in range(3)
        ] + [_make_outcome(sector="Tech", direction="bullish", is_winner=False) for _ in range(7)]
        result = validate_rules_against_outcomes([rule], outcomes)
        assert len(result) == 1
        # 30% < 90% * 80% = 72% -> not validated
        assert result[0] == (rule.rule_id, False)

    def test_no_matching_outcomes_not_validated(self) -> None:
        """Rule not validated when no outcomes match its conditions."""
        rule = _make_rule(sector="Tech", direction="bullish")
        outcomes = [_make_outcome(sector="Energy", direction="bearish")]
        result = validate_rules_against_outcomes([rule], outcomes)
        assert result[0] == (rule.rule_id, False)

    def test_empty_outcomes(self) -> None:
        """No outcomes means no validation."""
        rule = _make_rule()
        result = validate_rules_against_outcomes([rule], [])
        assert result[0] == (rule.rule_id, False)

    def test_empty_rules(self) -> None:
        """Empty rules returns empty results."""
        outcomes = [_make_outcome()]
        result = validate_rules_against_outcomes([], outcomes)
        assert result == []

    def test_multiple_rules(self) -> None:
        """Multiple rules produce one result per rule."""
        rule_a = _make_rule(rule_id="a", sector="Tech", direction="bullish", win_rate=0.5)
        rule_b = _make_rule(rule_id="b", sector="Energy", direction="bearish", win_rate=0.5)
        outcomes = [
            _make_outcome(sector="Tech", direction="bullish", is_winner=True) for _ in range(10)
        ]
        result = validate_rules_against_outcomes([rule_a, rule_b], outcomes)
        assert len(result) == 2
        results_dict = dict(result)
        assert results_dict["a"] is True
        assert results_dict["b"] is False

    def test_sector_match_direction_mismatch(self) -> None:
        """Only sector matches but direction doesn't -> no match."""
        rule = _make_rule(sector="Tech", direction="bullish")
        outcomes = [_make_outcome(sector="Tech", direction="bearish", is_winner=True)]
        result = validate_rules_against_outcomes([rule], outcomes)
        assert result[0] == (rule.rule_id, False)

    def test_boundary_win_rate_tolerance(self) -> None:
        """Win rate exactly at tolerance boundary should validate."""
        # rule win_rate=0.5, threshold = 0.5 * 0.8 = 0.4
        # outcomes: 40% win rate -> exactly at threshold
        rule = _make_rule(win_rate=0.5, sector="Tech", direction="bullish")
        outcomes = [
            _make_outcome(sector="Tech", direction="bullish", is_winner=True) for _ in range(4)
        ] + [_make_outcome(sector="Tech", direction="bullish", is_winner=False) for _ in range(6)]
        result = validate_rules_against_outcomes([rule], outcomes)
        # 40% >= 50% * 80% = 40% -> True (boundary)
        assert result[0] == (rule.rule_id, True)


# ---------------------------------------------------------------------------
# auto_promote_demote
# ---------------------------------------------------------------------------


class TestAutoPromoteDemote:
    def test_promote_high_confidence_candidate(self) -> None:
        """CANDIDATE with confidence >= 0.8 and count >= 5 -> promoted."""
        rule = _make_rule(
            status=RuleStatus.CANDIDATE,
            confidence=_PROMOTE_CONFIDENCE_THRESHOLD,
            validation_count=_PROMOTE_VALIDATION_COUNT,
        )
        promote, demote = auto_promote_demote([rule])
        assert rule.rule_id in promote
        assert rule.rule_id not in demote

    def test_no_promote_low_count(self) -> None:
        """CANDIDATE with confidence >= 0.8 but count < 5 -> not promoted."""
        rule = _make_rule(
            status=RuleStatus.CANDIDATE,
            confidence=0.9,
            validation_count=_PROMOTE_VALIDATION_COUNT - 1,
        )
        promote, demote = auto_promote_demote([rule])
        assert rule.rule_id not in promote

    def test_no_promote_low_confidence(self) -> None:
        """CANDIDATE with count >= 5 but confidence < 0.8 -> not promoted."""
        rule = _make_rule(
            status=RuleStatus.CANDIDATE,
            confidence=0.79,
            validation_count=10,
        )
        promote, demote = auto_promote_demote([rule])
        assert rule.rule_id not in promote

    def test_no_promote_approved_rule(self) -> None:
        """Already APPROVED rules not in promote list."""
        rule = _make_rule(
            status=RuleStatus.APPROVED,
            confidence=0.9,
            validation_count=10,
        )
        promote, _demote = auto_promote_demote([rule])
        assert rule.rule_id not in promote

    def test_demote_low_confidence_candidate(self) -> None:
        """CANDIDATE with confidence < 0.3 -> demoted."""
        rule = _make_rule(
            status=RuleStatus.CANDIDATE,
            confidence=_DEMOTE_CONFIDENCE_THRESHOLD - 0.01,
        )
        promote, demote = auto_promote_demote([rule])
        assert rule.rule_id in demote
        assert rule.rule_id not in promote

    def test_demote_low_confidence_approved(self) -> None:
        """APPROVED with confidence < 0.3 -> demoted."""
        rule = _make_rule(
            status=RuleStatus.APPROVED,
            confidence=0.1,
        )
        _promote, demote = auto_promote_demote([rule])
        assert rule.rule_id in demote

    def test_no_demote_rejected(self) -> None:
        """Already REJECTED rules not in demote list."""
        rule = _make_rule(
            status=RuleStatus.REJECTED,
            confidence=0.1,
        )
        promote, demote = auto_promote_demote([rule])
        assert rule.rule_id not in demote
        assert rule.rule_id not in promote

    def test_empty_rules(self) -> None:
        """Empty input -> empty lists."""
        promote, demote = auto_promote_demote([])
        assert promote == []
        assert demote == []

    def test_boundary_demote_exactly_030(self) -> None:
        """Confidence exactly at 0.3 -> NOT demoted (threshold is <, not <=)."""
        rule = _make_rule(
            status=RuleStatus.CANDIDATE,
            confidence=_DEMOTE_CONFIDENCE_THRESHOLD,
        )
        _promote, demote = auto_promote_demote([rule])
        assert rule.rule_id not in demote

    def test_boundary_promote_exactly_080(self) -> None:
        """Confidence exactly at 0.8 with count >= 5 -> promoted."""
        rule = _make_rule(
            status=RuleStatus.CANDIDATE,
            confidence=_PROMOTE_CONFIDENCE_THRESHOLD,
            validation_count=_PROMOTE_VALIDATION_COUNT,
        )
        promote, _demote = auto_promote_demote([rule])
        assert rule.rule_id in promote

    def test_mixed_rules(self) -> None:
        """Multiple rules with mixed states produce correct lists."""
        to_promote = _make_rule(
            rule_id="p",
            status=RuleStatus.CANDIDATE,
            confidence=0.9,
            validation_count=10,
        )
        to_demote = _make_rule(
            rule_id="d",
            status=RuleStatus.APPROVED,
            confidence=0.1,
        )
        stays = _make_rule(
            rule_id="s",
            status=RuleStatus.CANDIDATE,
            confidence=0.5,
            validation_count=2,
        )
        rejected = _make_rule(
            rule_id="r",
            status=RuleStatus.REJECTED,
            confidence=0.05,
        )
        promote, demote = auto_promote_demote([to_promote, to_demote, stays, rejected])
        assert promote == ["p"]
        assert demote == ["d"]


# ---------------------------------------------------------------------------
# run_confidence_decay (orchestration)
# ---------------------------------------------------------------------------


class TestRunConfidenceDecay:
    @pytest.mark.asyncio
    async def test_run_confidence_decay_never_raises(self) -> None:
        """Orchestration wrapper catches exceptions."""
        repo = MagicMock()
        repo.get_strategy_rules = AsyncMock(side_effect=RuntimeError("DB error"))

        # Should not raise
        await run_confidence_decay(repo)

    @pytest.mark.asyncio
    async def test_run_confidence_decay_updates_confidence(self) -> None:
        """Decay pipeline updates rule confidence in DB."""
        # Rule created 2 months ago with no validation
        two_months_ago = _NOW - timedelta(days=61)
        rule = _make_rule(
            rule_id="r1",
            status=RuleStatus.CANDIDATE,
            confidence=0.6,
            created_at=two_months_ago,
            last_validated=None,
            validation_count=1,
        )

        repo = MagicMock()
        repo.get_strategy_rules = AsyncMock(return_value=[rule])
        repo.update_rule_confidence = AsyncMock(return_value=True)
        repo.update_rule_status_and_confidence = AsyncMock(return_value=True)

        await run_confidence_decay(repo)

        # Verify update_rule_confidence was called
        repo.update_rule_confidence.assert_called_once()
        call_kwargs = repo.update_rule_confidence.call_args
        assert call_kwargs[1]["rule_id"] == "r1"
        # Confidence should have decayed
        assert call_kwargs[1]["confidence"] < 0.6

    @pytest.mark.asyncio
    async def test_run_confidence_decay_promotes_eligible(self) -> None:
        """Eligible rules get promoted during decay run."""
        # Rule with high confidence and enough validations (no decay needed)
        rule = _make_rule(
            rule_id="promote_me",
            status=RuleStatus.CANDIDATE,
            confidence=0.85,
            last_validated=_NOW - timedelta(seconds=1),
            validation_count=10,
        )

        repo = MagicMock()
        repo.get_strategy_rules = AsyncMock(return_value=[rule])
        repo.update_rule_confidence = AsyncMock(return_value=True)
        repo.update_rule_status_and_confidence = AsyncMock(return_value=True)

        await run_confidence_decay(repo)

        # Should have called update_rule_status_and_confidence for promotion
        promote_calls = [
            c
            for c in repo.update_rule_status_and_confidence.call_args_list
            if c[1].get("status") == RuleStatus.APPROVED
            or (len(c[0]) > 1 and c[0][1] == RuleStatus.APPROVED)
        ]
        assert len(promote_calls) >= 1

    @pytest.mark.asyncio
    async def test_run_confidence_decay_demotes_eligible(self) -> None:
        """Low confidence rules get demoted."""
        # Rule with very low confidence
        old_date = _NOW - timedelta(days=365)
        rule = _make_rule(
            rule_id="demote_me",
            status=RuleStatus.CANDIDATE,
            confidence=0.3,
            created_at=old_date,
            last_validated=None,
            validation_count=0,
        )

        repo = MagicMock()
        repo.get_strategy_rules = AsyncMock(return_value=[rule])
        repo.update_rule_confidence = AsyncMock(return_value=True)
        repo.update_rule_status_and_confidence = AsyncMock(return_value=True)

        await run_confidence_decay(repo)

        # After decay (0.3 * 0.95^12 * 0.5 ~ 0.087), should be demoted
        demote_calls = [
            c
            for c in repo.update_rule_status_and_confidence.call_args_list
            if c[1].get("status") == RuleStatus.REJECTED
            or (len(c[0]) > 1 and c[0][1] == RuleStatus.REJECTED)
        ]
        assert len(demote_calls) >= 1

    @pytest.mark.asyncio
    async def test_run_skips_rejected_rules(self) -> None:
        """Rejected rules are filtered out and not processed."""
        rejected_rule = _make_rule(
            rule_id="rejected",
            status=RuleStatus.REJECTED,
            confidence=0.5,
        )

        repo = MagicMock()
        repo.get_strategy_rules = AsyncMock(return_value=[rejected_rule])
        repo.update_rule_confidence = AsyncMock(return_value=True)
        repo.update_rule_status_and_confidence = AsyncMock(return_value=True)

        await run_confidence_decay(repo)

        # No confidence updates should happen for rejected rules
        repo.update_rule_confidence.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_no_active_rules(self) -> None:
        """No active rules logs info and returns without error."""
        repo = MagicMock()
        repo.get_strategy_rules = AsyncMock(return_value=[])
        repo.update_rule_confidence = AsyncMock(return_value=True)

        await run_confidence_decay(repo)

        repo.update_rule_confidence.assert_not_called()
