"""Tests for auto_tune_indicator_weights() orchestration function.

Covers: sufficient data, insufficient data, dry run, never-raises, comparison
model fields, and the sample count gate.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from options_arena.learning.weight_tuner import auto_tune_indicator_weights
from options_arena.models import IndicatorWeightComparison
from options_arena.models.scan import IndicatorSignals


def _make_pair(rsi: float, pnl: float) -> tuple[IndicatorSignals, float]:
    """Create a (signals, P&L) pair with rsi populated."""
    return (IndicatorSignals(rsi=rsi, adx=30.0), pnl)


def _make_pairs(n: int) -> list[tuple[IndicatorSignals, float]]:
    """Create n sample pairs with varying rsi and pnl."""
    return [_make_pair(50.0 + i, 0.02 * i - 0.5) for i in range(n)]


@pytest.mark.asyncio
class TestAutoTuneIndicatorWeights:
    """Tests for the async orchestration function."""

    async def test_sufficient_data_produces_comparisons(self) -> None:
        """50+ samples triggers tuning and returns comparisons."""
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(return_value=_make_pairs(60))
        repo.save_indicator_weights = AsyncMock()

        result = await auto_tune_indicator_weights(repo, window_days=90)

        assert len(result) > 0
        assert all(isinstance(r, IndicatorWeightComparison) for r in result)
        repo.save_indicator_weights.assert_awaited_once()

    async def test_insufficient_data_returns_empty(self) -> None:
        """<50 samples returns empty list."""
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(return_value=_make_pairs(10))

        result = await auto_tune_indicator_weights(repo, window_days=90)
        assert result == []

    async def test_dry_run_skips_persistence(self) -> None:
        """dry_run=True computes but does not save to DB."""
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(return_value=_make_pairs(60))
        repo.save_indicator_weights = AsyncMock()

        result = await auto_tune_indicator_weights(repo, window_days=90, dry_run=True)

        assert len(result) > 0
        repo.save_indicator_weights.assert_not_awaited()

    async def test_never_raises_on_db_error(self) -> None:
        """DB errors caught, empty list returned."""
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(side_effect=RuntimeError("DB exploded"))

        result = await auto_tune_indicator_weights(repo, window_days=90)
        assert result == []

    async def test_comparison_model_fields_populated(self) -> None:
        """Verify indicator_name, static/tuned weight, pearson_r, sample_count."""
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(return_value=_make_pairs(60))
        repo.save_indicator_weights = AsyncMock()

        result = await auto_tune_indicator_weights(repo, window_days=90)

        # Find rsi comparison — it should have data
        rsi_comp = next((r for r in result if r.indicator_name == "rsi"), None)
        assert rsi_comp is not None
        assert rsi_comp.static_weight > 0
        assert rsi_comp.tuned_weight > 0
        assert rsi_comp.sample_count >= 10

    async def test_empty_pairs_returns_empty(self) -> None:
        """No outcome data returns empty list."""
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(return_value=[])

        result = await auto_tune_indicator_weights(repo, window_days=90)
        assert result == []

    async def test_window_days_passed_to_repo(self) -> None:
        """Window days parameter forwarded to repo query."""
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(return_value=_make_pairs(60))
        repo.save_indicator_weights = AsyncMock()

        await auto_tune_indicator_weights(repo, window_days=180)

        repo.get_outcome_signal_pairs.assert_awaited_once_with(window_days=180)
