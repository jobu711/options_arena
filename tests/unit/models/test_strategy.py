"""Tests for strategy mining models: StrategyCondition, StrategyRule, AgentMemory."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AgentMemory,
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


def _make_memory(**overrides: object) -> AgentMemory:
    defaults: dict[str, object] = {
        "memory_id": "mem_001",
        "agent_name": "volatility",
        "scope": "AAPL",
        "scope_type": "ticker",
        "content": "AAPL IV typically expands before earnings.",
        "sample_size": 10,
        "win_rate": 0.7,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return AgentMemory(**defaults)  # type: ignore[arg-type]


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
# AgentMemory
# ---------------------------------------------------------------------------


class TestAgentMemory:
    def test_construction(self) -> None:
        mem = _make_memory()
        assert mem.memory_id == "mem_001"
        assert mem.agent_name == "volatility"
        assert mem.scope == "AAPL"
        assert mem.scope_type == "ticker"
        assert mem.sample_size == 10
        assert mem.win_rate == 0.7

    def test_frozen(self) -> None:
        mem = _make_memory()
        with pytest.raises(ValidationError):
            mem.content = "new content"  # type: ignore[misc]

    def test_win_rate_bounds(self) -> None:
        with pytest.raises(ValidationError, match="win_rate"):
            _make_memory(win_rate=1.5)

    def test_win_rate_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_memory(win_rate=float("nan"))

    def test_sample_size_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sample_size"):
            _make_memory(sample_size=-1)

    def test_created_at_utc_required(self) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            _make_memory(created_at=datetime(2026, 1, 1))

    def test_defaults(self) -> None:
        mem = AgentMemory(
            memory_id="m1",
            agent_name="risk",
            scope="global",
            scope_type="market",
            content="test",
            created_at=_NOW,
        )
        assert mem.sample_size == 0
        assert mem.win_rate == 0.0

    def test_json_roundtrip(self) -> None:
        mem = _make_memory()
        restored = AgentMemory.model_validate_json(mem.model_dump_json())
        assert restored == mem
