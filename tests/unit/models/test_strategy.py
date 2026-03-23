"""Tests for strategy mining models: StrategyCondition, StrategyRule."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import (
    ConditionOperator,
    RuleStatus,
    StrategyCondition,
    StrategyRule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


def _make_condition(**overrides: object) -> StrategyCondition:
    defaults: dict[str, object] = {
        "field": "sector",
        "operator": ConditionOperator.EQ,
        "value": "Information Technology",
    }
    defaults.update(overrides)
    return StrategyCondition(**defaults)  # type: ignore[arg-type]


def _make_rule(**overrides: object) -> StrategyRule:
    defaults: dict[str, object] = {
        "rule_id": "rule_tech_high_iv_short",
        "pattern": "Technology + High IV + Short DTE -> Bullish",
        "conditions": [_make_condition()],
        "win_rate": 0.65,
        "avg_return": 0.12,
        "sample_size": 50,
        "status": RuleStatus.CANDIDATE,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return StrategyRule(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ConditionOperator enum
# ---------------------------------------------------------------------------


class TestConditionOperator:
    def test_member_count(self) -> None:
        assert len(ConditionOperator) == 6

    def test_values(self) -> None:
        expected = {"eq", "gt", "lt", "gte", "lte", "in"}
        assert {m.value for m in ConditionOperator} == expected

    def test_is_strenum(self) -> None:
        assert isinstance(ConditionOperator.EQ, str)


# ---------------------------------------------------------------------------
# RuleStatus enum
# ---------------------------------------------------------------------------


class TestRuleStatus:
    def test_member_count(self) -> None:
        assert len(RuleStatus) == 3

    def test_values(self) -> None:
        expected = {"candidate", "approved", "rejected"}
        assert {m.value for m in RuleStatus} == expected

    def test_is_strenum(self) -> None:
        assert isinstance(RuleStatus.CANDIDATE, str)


# ---------------------------------------------------------------------------
# StrategyCondition
# ---------------------------------------------------------------------------


class TestStrategyCondition:
    def test_construction(self) -> None:
        cond = _make_condition()
        assert cond.field == "sector"
        assert cond.operator == ConditionOperator.EQ
        assert cond.value == "Information Technology"

    def test_frozen(self) -> None:
        cond = _make_condition()
        with pytest.raises(ValidationError):
            cond.field = "other"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        cond = _make_condition()
        restored = StrategyCondition.model_validate_json(cond.model_dump_json())
        assert restored == cond

    def test_numeric_value(self) -> None:
        cond = _make_condition(field="iv_rank", operator=ConditionOperator.GTE, value=75.0)
        assert cond.value == 75.0


# ---------------------------------------------------------------------------
# StrategyRule
# ---------------------------------------------------------------------------


class TestStrategyRule:
    def test_construction(self) -> None:
        rule = _make_rule()
        assert rule.rule_id == "rule_tech_high_iv_short"
        assert rule.win_rate == 0.65
        assert rule.avg_return == 0.12
        assert rule.sample_size == 50
        assert rule.status == RuleStatus.CANDIDATE
        assert len(rule.conditions) == 1

    def test_frozen(self) -> None:
        rule = _make_rule()
        with pytest.raises(ValidationError):
            rule.status = RuleStatus.APPROVED  # type: ignore[misc]

    def test_win_rate_bounds_low(self) -> None:
        with pytest.raises(ValidationError, match="win_rate"):
            _make_rule(win_rate=-0.1)

    def test_win_rate_bounds_high(self) -> None:
        with pytest.raises(ValidationError, match="win_rate"):
            _make_rule(win_rate=1.1)

    def test_win_rate_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_rule(win_rate=float("nan"))

    def test_win_rate_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_rule(win_rate=float("inf"))

    def test_avg_return_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_rule(avg_return=float("nan"))

    def test_avg_return_negative_allowed(self) -> None:
        rule = _make_rule(avg_return=-0.05)
        assert rule.avg_return == -0.05

    def test_sample_size_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sample_size"):
            _make_rule(sample_size=-1)

    def test_sample_size_zero_allowed(self) -> None:
        rule = _make_rule(sample_size=0)
        assert rule.sample_size == 0

    def test_created_at_naive_rejected(self) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            _make_rule(created_at=datetime(2026, 1, 1))

    def test_created_at_non_utc_rejected(self) -> None:
        from datetime import timedelta as td

        non_utc = datetime(2026, 1, 1, tzinfo=timezone(offset=td(hours=5)))
        with pytest.raises(ValidationError, match="UTC"):
            _make_rule(created_at=non_utc)

    def test_empty_conditions_allowed(self) -> None:
        rule = _make_rule(conditions=[])
        assert rule.conditions == []

    def test_win_rate_boundary_zero(self) -> None:
        rule = _make_rule(win_rate=0.0)
        assert rule.win_rate == 0.0

    def test_win_rate_boundary_one(self) -> None:
        rule = _make_rule(win_rate=1.0)
        assert rule.win_rate == 1.0

    def test_json_roundtrip(self) -> None:
        rule = _make_rule()
        restored = StrategyRule.model_validate_json(rule.model_dump_json())
        assert restored == rule

    def test_status_default(self) -> None:
        rule = StrategyRule(
            rule_id="r1",
            pattern="test",
            conditions=[],
            win_rate=0.5,
            avg_return=0.0,
            sample_size=20,
            created_at=_NOW,
        )
        assert rule.status == RuleStatus.CANDIDATE


# ---------------------------------------------------------------------------
# StrategyRule — Confidence / Validation Fields (Issue #675)
# ---------------------------------------------------------------------------


class TestStrategyRuleConfidenceFields:
    """Tests for the confidence, last_validated, and validation_count fields."""

    def test_default_confidence_is_half(self) -> None:
        rule = _make_rule()
        assert rule.confidence == 0.5

    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_confidence_accepts_valid_range(self, value: float) -> None:
        rule = _make_rule(confidence=value)
        assert rule.confidence == value

    def test_confidence_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_rule(confidence=float("nan"))

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_confidence_rejects_out_of_range(self, value: float) -> None:
        with pytest.raises(ValidationError, match="confidence"):
            _make_rule(confidence=value)

    def test_confidence_rejects_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_rule(confidence=float("inf"))

    def test_confidence_rejects_neg_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_rule(confidence=float("-inf"))

    def test_last_validated_default_none(self) -> None:
        rule = _make_rule()
        assert rule.last_validated is None

    def test_last_validated_accepts_utc(self) -> None:
        ts = datetime(2026, 3, 21, 15, 30, 0, tzinfo=UTC)
        rule = _make_rule(last_validated=ts)
        assert rule.last_validated == ts

    def test_last_validated_rejects_naive(self) -> None:
        with pytest.raises(ValidationError, match="last_validated must be UTC"):
            _make_rule(last_validated=datetime(2026, 3, 21, 15, 30, 0))

    def test_last_validated_rejects_non_utc(self) -> None:
        from datetime import timedelta as td

        non_utc = datetime(2026, 3, 21, 15, 30, 0, tzinfo=timezone(offset=td(hours=-5)))
        with pytest.raises(ValidationError, match="last_validated must be UTC"):
            _make_rule(last_validated=non_utc)

    def test_validation_count_default_zero(self) -> None:
        rule = _make_rule()
        assert rule.validation_count == 0

    def test_validation_count_accepts_positive(self) -> None:
        rule = _make_rule(validation_count=42)
        assert rule.validation_count == 42

    def test_validation_count_accepts_zero(self) -> None:
        rule = _make_rule(validation_count=0)
        assert rule.validation_count == 0

    def test_validation_count_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="validation_count"):
            _make_rule(validation_count=-1)

    def test_json_roundtrip_with_new_fields(self) -> None:
        ts = datetime(2026, 3, 21, 15, 30, 0, tzinfo=UTC)
        rule = _make_rule(confidence=0.85, last_validated=ts, validation_count=7)
        restored = StrategyRule.model_validate_json(rule.model_dump_json())
        assert restored == rule
        assert restored.confidence == 0.85
        assert restored.last_validated == ts
        assert restored.validation_count == 7

    def test_json_roundtrip_with_none_last_validated(self) -> None:
        rule = _make_rule(confidence=0.3, last_validated=None, validation_count=0)
        restored = StrategyRule.model_validate_json(rule.model_dump_json())
        assert restored == rule
        assert restored.last_validated is None

    def test_backward_compat_without_new_fields(self) -> None:
        """StrategyRule can be constructed without providing the new fields."""
        rule = StrategyRule(
            rule_id="r_compat",
            pattern="backward compat test",
            conditions=[],
            win_rate=0.5,
            avg_return=0.0,
            sample_size=20,
            created_at=_NOW,
        )
        assert rule.confidence == 0.5
        assert rule.last_validated is None
        assert rule.validation_count == 0

    def test_frozen_new_fields(self) -> None:
        """New fields are frozen along with the rest of the model."""
        rule = _make_rule(confidence=0.8, validation_count=3)
        with pytest.raises(ValidationError):
            rule.confidence = 0.9  # type: ignore[misc]
        with pytest.raises(ValidationError):
            rule.validation_count = 4  # type: ignore[misc]
        with pytest.raises(ValidationError):
            rule.last_validated = _NOW  # type: ignore[misc]
