"""Tests for compute_normalization_stats() — per-indicator distribution metadata.

Covers:
  - Basic computation with multiple tickers.
  - Empty signals dict returns empty list.
  - Indicator with all None values across tickers is skipped.
  - Single ticker (min==max==median==mean).
  - Known data produces correct min, max, median, mean, std_dev, p25, p75.
  - NaN values excluded from stats computation.
"""

from __future__ import annotations

import pytest

from options_arena.models import IndicatorSignals, NormalizationStats
from options_arena.scoring.normalization import compute_normalization_stats


class TestComputeNormalizationStats:
    """Tests for compute_normalization_stats()."""

    def test_basic_computation(self) -> None:
        """Verify stats computed correctly for a set of indicator signals."""
        raw_signals: dict[str, IndicatorSignals] = {
            "AAPL": IndicatorSignals(rsi=65.0, adx=25.0),
            "MSFT": IndicatorSignals(rsi=70.0, adx=30.0),
            "GOOGL": IndicatorSignals(rsi=55.0, adx=20.0),
        }
        stats = compute_normalization_stats(raw_signals)
        assert len(stats) >= 2  # at least rsi and adx

        # Verify indicator names are present
        names = {s.indicator_name for s in stats}
        assert "rsi" in names
        assert "adx" in names

        # Verify scan_run_id is placeholder 0
        for s in stats:
            assert s.scan_run_id == 0
            assert isinstance(s, NormalizationStats)
            assert s.created_at is not None

    def test_empty_signals(self) -> None:
        """Verify empty dict returns empty list."""
        stats = compute_normalization_stats({})
        assert stats == []

    def test_all_none_indicator(self) -> None:
        """Verify indicator with all None values across tickers is skipped."""
        raw_signals: dict[str, IndicatorSignals] = {
            "AAPL": IndicatorSignals(rsi=65.0),  # iv_rank is None
            "MSFT": IndicatorSignals(rsi=70.0),  # iv_rank is None
        }
        stats = compute_normalization_stats(raw_signals)
        names = {s.indicator_name for s in stats}
        assert "iv_rank" not in names
        assert "rsi" in names

    def test_single_ticker(self) -> None:
        """Verify stats with single ticker (min==max==median==mean)."""
        raw_signals: dict[str, IndicatorSignals] = {
            "AAPL": IndicatorSignals(rsi=65.0, adx=25.0),
        }
        stats = compute_normalization_stats(raw_signals)
        rsi_stat = next(s for s in stats if s.indicator_name == "rsi")

        assert rsi_stat.ticker_count == 1
        assert rsi_stat.min_value == pytest.approx(65.0)
        assert rsi_stat.max_value == pytest.approx(65.0)
        assert rsi_stat.median_value == pytest.approx(65.0)
        assert rsi_stat.mean_value == pytest.approx(65.0)
        # std_dev is None for single value (ddof=1 undefined)
        assert rsi_stat.std_dev is None
        assert rsi_stat.p25 == pytest.approx(65.0)
        assert rsi_stat.p75 == pytest.approx(65.0)

    def test_stats_values_correct(self) -> None:
        """Verify min, max, median, mean, std_dev, p25, p75 against known data."""
        # Known data: rsi values [10, 20, 30, 40, 50]
        raw_signals: dict[str, IndicatorSignals] = {
            "A": IndicatorSignals(rsi=10.0),
            "B": IndicatorSignals(rsi=20.0),
            "C": IndicatorSignals(rsi=30.0),
            "D": IndicatorSignals(rsi=40.0),
            "E": IndicatorSignals(rsi=50.0),
        }
        stats = compute_normalization_stats(raw_signals)
        rsi_stat = next(s for s in stats if s.indicator_name == "rsi")

        assert rsi_stat.ticker_count == 5
        assert rsi_stat.min_value == pytest.approx(10.0)
        assert rsi_stat.max_value == pytest.approx(50.0)
        assert rsi_stat.median_value == pytest.approx(30.0)
        assert rsi_stat.mean_value == pytest.approx(30.0)
        # std_dev with ddof=1: sqrt(sum((x - 30)^2) / 4)
        # = sqrt((400+100+0+100+400)/4) = sqrt(250) ~ 15.811
        assert rsi_stat.std_dev == pytest.approx(15.8114, rel=1e-3)
        assert rsi_stat.p25 == pytest.approx(20.0)
        assert rsi_stat.p75 == pytest.approx(40.0)

    def test_nan_values_excluded(self) -> None:
        """Verify NaN indicator values are excluded from stats computation."""
        raw_signals: dict[str, IndicatorSignals] = {
            "AAPL": IndicatorSignals(rsi=60.0),
            "MSFT": IndicatorSignals(rsi=float("nan")),
            "GOOGL": IndicatorSignals(rsi=80.0),
        }
        stats = compute_normalization_stats(raw_signals)
        rsi_stat = next(s for s in stats if s.indicator_name == "rsi")

        # NaN should be excluded, leaving only 2 values: [60, 80]
        assert rsi_stat.ticker_count == 2
        assert rsi_stat.min_value == pytest.approx(60.0)
        assert rsi_stat.max_value == pytest.approx(80.0)
        assert rsi_stat.mean_value == pytest.approx(70.0)
        assert rsi_stat.median_value == pytest.approx(70.0)
