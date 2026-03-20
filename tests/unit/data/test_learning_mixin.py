"""Tests for LearningMixin — strategy rule and agent memory CRUD."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data import Database, Repository
from options_arena.models import (
    AgentMemory,
    ConditionOperator,
    RuleStatus,
    StrategyCondition,
    StrategyRule,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)
_LATER = datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def db() -> Database:  # type: ignore[misc]
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    return Repository(db)


def _make_rule(
    rule_id: str = "rule_1",
    status: RuleStatus = RuleStatus.CANDIDATE,
    created_at: datetime = _NOW,
    **overrides: object,
) -> StrategyRule:
    defaults: dict[str, object] = {
        "rule_id": rule_id,
        "pattern": "Tech + High IV -> Bullish",
        "conditions": [
            StrategyCondition(
                field="sector",
                operator=ConditionOperator.EQ,
                value="Information Technology",
            ),
            StrategyCondition(
                field="iv_rank",
                operator=ConditionOperator.GTE,
                value=75.0,
            ),
        ],
        "win_rate": 0.65,
        "avg_return": 0.12,
        "sample_size": 50,
        "status": status,
        "created_at": created_at,
    }
    defaults.update(overrides)
    return StrategyRule(**defaults)  # type: ignore[arg-type]


def _make_memory(
    memory_id: str = "mem_001",
    agent_name: str = "volatility",
    scope_type: str = "ticker",
    created_at: datetime = _NOW,
) -> AgentMemory:
    return AgentMemory(
        memory_id=memory_id,
        agent_name=agent_name,
        scope="AAPL",
        scope_type=scope_type,
        content="AAPL IV expands before earnings.",
        sample_size=10,
        win_rate=0.7,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Strategy Rule CRUD
# ---------------------------------------------------------------------------


class TestStrategyRuleCRUD:
    @pytest.mark.asyncio
    async def test_save_and_get_strategy_rule(self, repo: Repository) -> None:
        """Verify round-trip save/get for StrategyRule."""
        rule = _make_rule()
        await repo.save_strategy_rule(rule)

        rules = await repo.get_strategy_rules()
        assert len(rules) == 1
        assert rules[0].rule_id == "rule_1"
        assert rules[0].pattern == "Tech + High IV -> Bullish"
        assert rules[0].win_rate == pytest.approx(0.65, rel=1e-4)
        assert rules[0].avg_return == pytest.approx(0.12, rel=1e-4)
        assert rules[0].sample_size == 50
        assert rules[0].status == RuleStatus.CANDIDATE
        assert len(rules[0].conditions) == 2
        assert rules[0].conditions[0].field == "sector"
        assert rules[0].conditions[1].operator == ConditionOperator.GTE

    @pytest.mark.asyncio
    async def test_get_rules_by_status(self, repo: Repository) -> None:
        """Verify filtering rules by RuleStatus."""
        await repo.save_strategy_rule(_make_rule("r1", RuleStatus.CANDIDATE))
        await repo.save_strategy_rule(_make_rule("r2", RuleStatus.APPROVED, _LATER))
        await repo.save_strategy_rule(_make_rule("r3", RuleStatus.REJECTED))

        candidates = await repo.get_strategy_rules(status=RuleStatus.CANDIDATE)
        assert len(candidates) == 1
        assert candidates[0].rule_id == "r1"

        approved = await repo.get_strategy_rules(status=RuleStatus.APPROVED)
        assert len(approved) == 1
        assert approved[0].rule_id == "r2"

        all_rules = await repo.get_strategy_rules()
        assert len(all_rules) == 3

    @pytest.mark.asyncio
    async def test_update_rule_status(self, repo: Repository) -> None:
        """Verify status transition candidate -> approved."""
        await repo.save_strategy_rule(_make_rule("r1"))
        updated = await repo.update_rule_status("r1", RuleStatus.APPROVED)
        assert updated is True

        rules = await repo.get_strategy_rules()
        assert rules[0].status == RuleStatus.APPROVED

    @pytest.mark.asyncio
    async def test_update_nonexistent_rule(self, repo: Repository) -> None:
        """Verify update returns False for unknown rule_id."""
        updated = await repo.update_rule_status("nonexistent", RuleStatus.APPROVED)
        assert updated is False

    @pytest.mark.asyncio
    async def test_upsert_on_duplicate_rule_id(self, repo: Repository) -> None:
        """Verify saving a rule with the same rule_id replaces it."""
        await repo.save_strategy_rule(_make_rule("r1", win_rate=0.5))
        await repo.save_strategy_rule(_make_rule("r1", win_rate=0.8))

        rules = await repo.get_strategy_rules()
        assert len(rules) == 1
        assert rules[0].win_rate == pytest.approx(0.8, rel=1e-4)

    @pytest.mark.asyncio
    async def test_empty_state_rules(self, repo: Repository) -> None:
        """Verify get_strategy_rules returns empty list on fresh DB."""
        rules = await repo.get_strategy_rules()
        assert rules == []

    @pytest.mark.asyncio
    async def test_conditions_roundtrip(self, repo: Repository) -> None:
        """Verify conditions JSON serialization survives roundtrip."""
        conditions = [
            StrategyCondition(field="sector", operator=ConditionOperator.EQ, value="Energy"),
            StrategyCondition(field="dte", operator=ConditionOperator.LTE, value=30.0),
            StrategyCondition(field="direction", operator=ConditionOperator.EQ, value="bullish"),
        ]
        rule = _make_rule(conditions=conditions)
        await repo.save_strategy_rule(rule)

        rules = await repo.get_strategy_rules()
        assert len(rules[0].conditions) == 3
        assert rules[0].conditions[0].value == "Energy"
        assert rules[0].conditions[1].value == 30.0
        assert rules[0].conditions[2].operator == ConditionOperator.EQ


# ---------------------------------------------------------------------------
# Agent Memory CRUD
# ---------------------------------------------------------------------------


class TestAgentMemoryCRUD:
    @pytest.mark.asyncio
    async def test_save_and_get_agent_memory(self, repo: Repository) -> None:
        """Verify round-trip save/get for AgentMemory."""
        mem = _make_memory()
        await repo.save_agent_memory(mem)

        memories = await repo.get_agent_memories()
        assert len(memories) == 1
        assert memories[0].memory_id == "mem_001"
        assert memories[0].agent_name == "volatility"
        assert memories[0].content == "AAPL IV expands before earnings."
        assert memories[0].win_rate == pytest.approx(0.7, rel=1e-4)

    @pytest.mark.asyncio
    async def test_get_memories_by_agent(self, repo: Repository) -> None:
        """Verify filtering memories by agent_name."""
        await repo.save_agent_memory(_make_memory("m1", agent_name="volatility"))
        await repo.save_agent_memory(_make_memory("m2", agent_name="risk", created_at=_LATER))

        vol_mems = await repo.get_agent_memories(agent_name="volatility")
        assert len(vol_mems) == 1
        assert vol_mems[0].agent_name == "volatility"

        risk_mems = await repo.get_agent_memories(agent_name="risk")
        assert len(risk_mems) == 1

    @pytest.mark.asyncio
    async def test_get_memories_by_scope_type(self, repo: Repository) -> None:
        """Verify filtering memories by scope_type."""
        await repo.save_agent_memory(_make_memory("m1", scope_type="ticker"))
        await repo.save_agent_memory(_make_memory("m2", scope_type="sector", created_at=_LATER))

        ticker_mems = await repo.get_agent_memories(scope_type="ticker")
        assert len(ticker_mems) == 1
        assert ticker_mems[0].scope_type == "ticker"

    @pytest.mark.asyncio
    async def test_combined_filters(self, repo: Repository) -> None:
        """Verify combining agent_name and scope_type filters."""
        await repo.save_agent_memory(
            _make_memory("m1", agent_name="volatility", scope_type="ticker")
        )
        await repo.save_agent_memory(
            _make_memory("m2", agent_name="volatility", scope_type="sector", created_at=_LATER)
        )
        await repo.save_agent_memory(_make_memory("m3", agent_name="risk", scope_type="ticker"))

        result = await repo.get_agent_memories(agent_name="volatility", scope_type="ticker")
        assert len(result) == 1
        assert result[0].memory_id == "m1"

    @pytest.mark.asyncio
    async def test_empty_state_memories(self, repo: Repository) -> None:
        """Verify get_agent_memories returns empty list on fresh DB."""
        memories = await repo.get_agent_memories()
        assert memories == []

    @pytest.mark.asyncio
    async def test_upsert_on_duplicate_memory_id(self, repo: Repository) -> None:
        """Verify saving with same memory_id replaces the entry."""
        await repo.save_agent_memory(_make_memory("m1", agent_name="volatility"))
        await repo.save_agent_memory(_make_memory("m1", agent_name="risk"))

        memories = await repo.get_agent_memories()
        assert len(memories) == 1
        assert memories[0].agent_name == "risk"
