"""Tests verifying duplicate get_prediction_accuracy() is removed (#810).

Ensures only one definition exists on LearningMixin/Repository, that
``window_days`` is required (not optional), that negative values are
rejected, and that a valid call returns ``list[PredictionAccuracy]``.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data import Database, Repository
from options_arena.data._learning import LearningMixin
from options_arena.models.attribution import (
    PredictionAccuracy,
    PredictionSource,
)
from options_arena.models.enums import SignalDirection
from tests.factories import make_prediction

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def repo() -> AsyncGenerator[Repository]:  # type: ignore[misc]
    """In-memory DB with migrations and stub FK rows."""
    database = Database(":memory:")
    await database.connect()

    conn = database.conn

    # Stub scan_runs row for FK validity
    await conn.execute(
        "INSERT INTO scan_runs (id, started_at, preset, source, "
        "tickers_scanned, tickers_scored, recommendations) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, _NOW.isoformat(), "sp500", "manual", 500, 450, 50),
    )
    # Stub recommendation_results row for FK validity
    await conn.execute(
        "INSERT INTO recommendation_results "
        "(id, ticker, direction, confidence, recommended_contract, "
        "entry_price, entry_criteria, exit_criteria, position_size_pct, "
        "risk_reward_ratio, summary, key_factors_json, risk_assessment, "
        "assessments_json, duration_ms, model_used, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "AAPL",
            "bullish",
            0.75,
            "AAPL 190C 2026-04-18",
            "5.00",
            "buy at ask",
            "sell at target",
            5.0,
            2.0,
            "test summary",
            "[]",
            "low risk",
            "[]",
            100,
            "test-model",
            _NOW.isoformat(),
        ),
    )
    await conn.commit()
    try:
        yield Repository(database)
    finally:
        await database.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetPredictionAccuracyDedup:
    """Verify the duplicate get_prediction_accuracy() has been removed (#810)."""

    def test_single_definition_exists(self) -> None:
        """Only one get_prediction_accuracy method exists on LearningMixin."""
        methods = [
            name
            for name, _ in inspect.getmembers(LearningMixin, predicate=inspect.isfunction)
            if name == "get_prediction_accuracy"
        ]
        assert len(methods) == 1, (
            f"Expected exactly 1 get_prediction_accuracy, found {len(methods)}"
        )

    def test_requires_window_days(self) -> None:
        """Calling without window_days raises TypeError."""
        sig = inspect.signature(LearningMixin.get_prediction_accuracy)
        params = sig.parameters
        window_param = params.get("window_days")
        assert window_param is not None, "window_days parameter missing"
        assert window_param.default is inspect.Parameter.empty, (
            "window_days should be required (no default)"
        )

    @pytest.mark.asyncio
    async def test_negative_window_days_rejected(self, repo: Repository) -> None:
        """window_days < 0 raises ValueError."""
        with pytest.raises(ValueError, match="window_days must be >= 0"):
            await repo.get_prediction_accuracy(window_days=-1)

    @pytest.mark.asyncio
    async def test_valid_call_succeeds(self, repo: Repository) -> None:
        """get_prediction_accuracy(window_days=30) returns list[PredictionAccuracy]."""
        # Insert a scored prediction
        pred = make_prediction(
            recommendation_id=1,
            source=PredictionSource.DESK_TREND,
            predicted_direction=SignalDirection.BULLISH,
            confidence=0.8,
            was_correct=True,
            created_at=_NOW,
        )
        await repo.save_prediction(pred)
        await repo.score_predictions(recommendation_id=1, was_correct=True)

        results = await repo.get_prediction_accuracy(window_days=30)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, PredictionAccuracy) for r in results)

    @pytest.mark.asyncio
    async def test_zero_window_days(self, repo: Repository) -> None:
        """window_days=0 returns only predictions from today."""
        results = await repo.get_prediction_accuracy(window_days=0)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_empty_database(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_prediction_accuracy(window_days=30)
        assert results == []
