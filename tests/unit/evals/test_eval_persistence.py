"""Tests for EvalMixin persistence layer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data import Database, Repository
from options_arena.models.enums import (
    DeskType,
    EvalType,
    GraderType,
    SignalDirection,
)
from options_arena.models.eval import EvalDefinition, EvalRun


@pytest_asyncio.fixture
async def db() -> Database:
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    return Repository(db)


def _make_eval_definition(**overrides: object) -> EvalDefinition:
    defaults: dict[str, object] = {
        "name": "test_trend_bullish",
        "eval_type": EvalType.CAPABILITY,
        "target_desk": DeskType.TREND,
        "description": "Bullish trend eval",
        "grader_type": GraderType.CODE,
        "market_context_fixture": "tests/fixtures/trend.json",
        "expected_direction": SignalDirection.BULLISH,
        "expected_confidence_min": 0.5,
        "expected_confidence_max": 0.9,
    }
    defaults.update(overrides)
    return EvalDefinition(**defaults)  # type: ignore[arg-type]


def _make_eval_run(**overrides: object) -> EvalRun:
    defaults: dict[str, object] = {
        "eval_name": "test_trend_bullish",
        "timestamp": datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
        "passed": True,
        "attempts": 3,
        "successes": 2,
        "model_used": "code_grader",
        "duration_ms": 150,
        "details": '{"checks": 5}',
    }
    defaults.update(overrides)
    return EvalRun(**defaults)  # type: ignore[arg-type]


class TestEvalDefinitionCRUD:
    """Test save/get/list for eval definitions."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, repo: Repository) -> None:
        defn = _make_eval_definition()
        await repo.save_eval_definition(defn)

        result = await repo.get_eval_definition("test_trend_bullish")
        assert result is not None
        assert result.name == "test_trend_bullish"
        assert result.eval_type == EvalType.CAPABILITY
        assert result.target_desk == DeskType.TREND
        assert result.grader_type == GraderType.CODE
        assert result.expected_direction == SignalDirection.BULLISH
        assert result.expected_confidence_min == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, repo: Repository) -> None:
        result = await repo.get_eval_definition("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all(self, repo: Repository) -> None:
        await repo.save_eval_definition(_make_eval_definition(name="eval_a"))
        await repo.save_eval_definition(_make_eval_definition(name="eval_b"))
        await repo.save_eval_definition(_make_eval_definition(name="eval_c"))

        definitions = await repo.get_eval_definitions()
        assert len(definitions) == 3
        names = [d.name for d in definitions]
        assert "eval_a" in names
        assert "eval_b" in names
        assert "eval_c" in names

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self, repo: Repository) -> None:
        await repo.save_eval_definition(_make_eval_definition(description="original"))
        await repo.save_eval_definition(_make_eval_definition(description="updated"))

        result = await repo.get_eval_definition("test_trend_bullish")
        assert result is not None
        assert result.description == "updated"

    @pytest.mark.asyncio
    async def test_null_target_desk(self, repo: Repository) -> None:
        defn = _make_eval_definition(name="synthesis_eval", target_desk=None)
        await repo.save_eval_definition(defn)

        result = await repo.get_eval_definition("synthesis_eval")
        assert result is not None
        assert result.target_desk is None

    @pytest.mark.asyncio
    async def test_null_direction(self, repo: Repository) -> None:
        defn = _make_eval_definition(name="no_direction", expected_direction=None)
        await repo.save_eval_definition(defn)

        result = await repo.get_eval_definition("no_direction")
        assert result is not None
        assert result.expected_direction is None

    @pytest.mark.asyncio
    async def test_custom_assertions_roundtrip(self, repo: Repository) -> None:
        defn = _make_eval_definition(
            name="with_assertions",
            custom_assertions=["check_iv", "check_delta"],
        )
        await repo.save_eval_definition(defn)

        result = await repo.get_eval_definition("with_assertions")
        assert result is not None
        assert result.custom_assertions == ["check_iv", "check_delta"]


class TestEvalRunCRUD:
    """Test save/get for eval runs."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, repo: Repository) -> None:
        # Must save definition first (FK constraint)
        await repo.save_eval_definition(_make_eval_definition())

        run = _make_eval_run()
        row_id = await repo.save_eval_run(run)
        assert row_id > 0

        runs = await repo.get_eval_runs(eval_name="test_trend_bullish")
        assert len(runs) == 1
        assert runs[0].eval_name == "test_trend_bullish"
        assert runs[0].passed is True
        assert runs[0].attempts == 3
        assert runs[0].successes == 2
        assert runs[0].duration_ms == 150

    @pytest.mark.asyncio
    async def test_get_all_runs(self, repo: Repository) -> None:
        await repo.save_eval_definition(_make_eval_definition(name="eval_a"))
        await repo.save_eval_definition(_make_eval_definition(name="eval_b"))

        await repo.save_eval_run(_make_eval_run(eval_name="eval_a"))
        await repo.save_eval_run(_make_eval_run(eval_name="eval_b"))

        runs = await repo.get_eval_runs()
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_runs_ordered_by_timestamp_desc(self, repo: Repository) -> None:
        await repo.save_eval_definition(_make_eval_definition())

        await repo.save_eval_run(
            _make_eval_run(
                timestamp=datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_eval_run(
            _make_eval_run(
                timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
            )
        )

        runs = await repo.get_eval_runs()
        assert runs[0].timestamp > runs[1].timestamp

    @pytest.mark.asyncio
    async def test_get_latest_eval_runs(self, repo: Repository) -> None:
        await repo.save_eval_definition(_make_eval_definition(name="eval_a"))
        await repo.save_eval_definition(_make_eval_definition(name="eval_b"))

        # Two runs for eval_a, one for eval_b
        await repo.save_eval_run(
            _make_eval_run(
                eval_name="eval_a",
                timestamp=datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC),
                passed=False,
            )
        )
        await repo.save_eval_run(
            _make_eval_run(
                eval_name="eval_a",
                timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
                passed=True,
            )
        )
        await repo.save_eval_run(
            _make_eval_run(
                eval_name="eval_b",
                timestamp=datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC),
            )
        )

        latest = await repo.get_latest_eval_runs()
        assert len(latest) == 2
        names = {r.eval_name for r in latest}
        assert names == {"eval_a", "eval_b"}

        # eval_a should have the latest run (passed=True)
        eval_a_run = next(r for r in latest if r.eval_name == "eval_a")
        assert eval_a_run.passed is True

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, repo: Repository) -> None:
        runs = await repo.get_eval_runs()
        assert runs == []

        latest = await repo.get_latest_eval_runs()
        assert latest == []

    @pytest.mark.asyncio
    async def test_limit_parameter(self, repo: Repository) -> None:
        await repo.save_eval_definition(_make_eval_definition())

        for i in range(5):
            await repo.save_eval_run(
                _make_eval_run(
                    timestamp=datetime(2026, 3, 20 + i, 12, 0, 0, tzinfo=UTC),
                )
            )

        runs = await repo.get_eval_runs(limit=3)
        assert len(runs) == 3
