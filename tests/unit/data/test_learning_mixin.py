"""Tests for LearningMixin — strategy rule CRUD."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data import Database, Repository
from options_arena.models import (
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
# Confidence Decay Persistence (migration 038)
# ---------------------------------------------------------------------------


class TestLearningMixinConfidence:
    """Tests for confidence, last_validated, and validation_count persistence."""

    @pytest.mark.asyncio
    async def test_save_and_read_rule_with_confidence(self, repo: Repository) -> None:
        """Verify confidence fields survive save/get roundtrip."""
        rule = _make_rule(
            confidence=0.85,
            last_validated=_LATER,
            validation_count=5,
        )
        await repo.save_strategy_rule(rule)

        rules = await repo.get_strategy_rules()
        assert len(rules) == 1
        assert rules[0].confidence == pytest.approx(0.85, rel=1e-4)
        assert rules[0].last_validated == _LATER
        assert rules[0].validation_count == 5

    @pytest.mark.asyncio
    async def test_save_rule_default_confidence(self, repo: Repository) -> None:
        """Verify rule saved without explicit confidence gets default 0.5."""
        rule = _make_rule()  # no confidence/last_validated/validation_count overrides
        await repo.save_strategy_rule(rule)

        rules = await repo.get_strategy_rules()
        assert len(rules) == 1
        assert rules[0].confidence == pytest.approx(0.5, rel=1e-4)
        assert rules[0].last_validated is None
        assert rules[0].validation_count == 0

    @pytest.mark.asyncio
    async def test_update_rule_confidence(self, repo: Repository) -> None:
        """Verify update_rule_confidence modifies all three fields."""
        await repo.save_strategy_rule(_make_rule("r1"))

        updated = await repo.update_rule_confidence(
            rule_id="r1",
            confidence=0.92,
            last_validated=_LATER,
            validation_count=10,
        )
        assert updated is True

        rules = await repo.get_strategy_rules()
        assert rules[0].confidence == pytest.approx(0.92, rel=1e-4)
        assert rules[0].last_validated == _LATER
        assert rules[0].validation_count == 10

    @pytest.mark.asyncio
    async def test_update_rule_confidence_nonexistent(self, repo: Repository) -> None:
        """Verify update_rule_confidence returns False for unknown rule_id."""
        updated = await repo.update_rule_confidence(
            rule_id="nonexistent",
            confidence=0.8,
            last_validated=_NOW,
            validation_count=1,
        )
        assert updated is False

    @pytest.mark.asyncio
    async def test_update_rule_status_and_confidence(self, repo: Repository) -> None:
        """Verify atomic update of status + confidence."""
        await repo.save_strategy_rule(_make_rule("r1"))

        updated = await repo.update_rule_status_and_confidence(
            rule_id="r1",
            status=RuleStatus.APPROVED,
            confidence=0.95,
        )
        assert updated is True

        rules = await repo.get_strategy_rules()
        assert rules[0].status == RuleStatus.APPROVED
        assert rules[0].confidence == pytest.approx(0.95, rel=1e-4)

    @pytest.mark.asyncio
    async def test_update_rule_status_and_confidence_nonexistent(self, repo: Repository) -> None:
        """Verify update_rule_status_and_confidence returns False for unknown rule_id."""
        updated = await repo.update_rule_status_and_confidence(
            rule_id="nonexistent",
            status=RuleStatus.APPROVED,
            confidence=0.8,
        )
        assert updated is False

    @pytest.mark.asyncio
    async def test_last_validated_none_roundtrip(self, repo: Repository) -> None:
        """Verify last_validated=None persists and reads back as None."""
        rule = _make_rule(confidence=0.7, last_validated=None, validation_count=3)
        await repo.save_strategy_rule(rule)

        rules = await repo.get_strategy_rules()
        assert rules[0].last_validated is None
        assert rules[0].confidence == pytest.approx(0.7, rel=1e-4)
        assert rules[0].validation_count == 3

    @pytest.mark.asyncio
    async def test_update_confidence_clears_last_validated(self, repo: Repository) -> None:
        """Verify setting last_validated back to None via update works."""
        await repo.save_strategy_rule(
            _make_rule("r1", confidence=0.8, last_validated=_NOW, validation_count=2)
        )

        # Update with None last_validated
        updated = await repo.update_rule_confidence(
            rule_id="r1",
            confidence=0.6,
            last_validated=None,
            validation_count=3,
        )
        assert updated is True

        rules = await repo.get_strategy_rules()
        assert rules[0].last_validated is None
        assert rules[0].confidence == pytest.approx(0.6, rel=1e-4)
        assert rules[0].validation_count == 3

    @pytest.mark.asyncio
    async def test_migration_038_runs_cleanly(self, db: Database) -> None:
        """Verify migration 038 applies without error on a fresh DB."""
        # The db fixture already runs all migrations (including 038).
        # Verify the columns exist by querying PRAGMA.
        conn = db.conn
        async with conn.execute("PRAGMA table_info(strategy_rules)") as cursor:
            rows = await cursor.fetchall()

        column_names = {row[1] for row in rows}
        assert "confidence" in column_names
        assert "last_validated" in column_names
        assert "validation_count" in column_names

    @pytest.mark.asyncio
    async def test_upsert_preserves_confidence_fields(self, repo: Repository) -> None:
        """Verify upserting a rule with confidence fields replaces old values."""
        await repo.save_strategy_rule(
            _make_rule("r1", confidence=0.5, last_validated=None, validation_count=0)
        )
        await repo.save_strategy_rule(
            _make_rule("r1", confidence=0.9, last_validated=_LATER, validation_count=7)
        )

        rules = await repo.get_strategy_rules()
        assert len(rules) == 1
        assert rules[0].confidence == pytest.approx(0.9, rel=1e-4)
        assert rules[0].last_validated == _LATER
        assert rules[0].validation_count == 7
