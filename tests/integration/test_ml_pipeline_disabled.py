"""Integration test: ML pipeline with default config (all disabled).

Verifies that the full scoring pipeline with default ``MLConfig`` (all
feature flags False) produces no ML indicator data. This ensures that
enabling ML features is strictly opt-in and does not regress existing
pipeline behavior.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from options_arena.models.config import MLConfig, ScanConfig
from options_arena.models.market_data import OHLCV
from options_arena.models.scan import IndicatorSignals
from options_arena.scan.indicators import (
    INDICATOR_REGISTRY,
    compute_indicators,
    ohlcv_to_dataframe,
)
from options_arena.scan.phase_scoring import _compute_ml_indicators


def _make_ohlcv_bars(n: int = 300) -> list[OHLCV]:
    """Create synthetic OHLCV bars for testing."""
    bars: list[OHLCV] = []
    base = 100.0
    for i in range(n):
        d = date(2023, 1, 2) + timedelta(days=i)
        close = base + i * 0.01
        bars.append(
            OHLCV(
                ticker="TEST",
                date=d,
                open=Decimal(str(round(close - 0.5, 2))),
                high=Decimal(str(round(close + 1.0, 2))),
                low=Decimal(str(round(close - 1.0, 2))),
                close=Decimal(str(round(close, 2))),
                adjusted_close=Decimal(str(round(close, 2))),
                volume=1_000_000,
            )
        )
    return bars


class TestMLPipelineDisabled:
    """Integration tests verifying ML indicators are absent with default config."""

    @pytest.mark.critical
    def test_default_ml_config_all_disabled(self) -> None:
        """Default MLConfig has all feature flags False."""
        config = MLConfig()
        assert config.enable_garch is False
        assert config.enable_markov is False
        assert config.enable_macro is False

    @pytest.mark.critical
    def test_default_scan_config_ml_disabled(self) -> None:
        """Default ScanConfig has ML disabled."""
        config = ScanConfig()
        assert config.ml.enable_garch is False
        assert config.ml.enable_markov is False
        assert config.ml.enable_macro is False

    @pytest.mark.asyncio
    async def test_no_ml_data_with_default_config(self) -> None:
        """Full pipeline with default config produces no ML data."""
        ohlcv_list = _make_ohlcv_bars(300)
        ohlcv_map: dict[str, list[OHLCV]] = {"TEST": ohlcv_list}

        # Step 1: Compute standard indicators
        df = ohlcv_to_dataframe(ohlcv_list)
        signals = compute_indicators(df, INDICATOR_REGISTRY)
        raw_signals: dict[str, IndicatorSignals] = {"TEST": signals}

        # Step 2: Run ML indicators with default config (all disabled)
        ml_config = MLConfig()
        await _compute_ml_indicators(
            raw_signals=raw_signals,
            ohlcv_map=ohlcv_map,
            ml_config=ml_config,
        )

        # Verify: no ML fields populated
        assert signals.vol_forecast_garch is None
        assert signals.iv_vs_forecast_spread is None
        assert signals.regime_markov_label is None
        assert signals.regime_transition_prob is None

    def test_standard_indicators_unaffected(self) -> None:
        """Standard OHLCV-based indicators are still computed normally."""
        ohlcv_list = _make_ohlcv_bars(300)
        df = ohlcv_to_dataframe(ohlcv_list)
        signals = compute_indicators(df, INDICATOR_REGISTRY)

        # At least some standard indicators should be populated
        populated_count = sum(
            1
            for field_name in [spec.field_name for spec in INDICATOR_REGISTRY]
            if getattr(signals, field_name) is not None
        )
        assert populated_count > 0, "Expected at least some standard indicators to be populated"

        # ML fields must still be None (never touched by compute_indicators)
        assert signals.vol_forecast_garch is None
        assert signals.iv_vs_forecast_spread is None
        assert signals.regime_markov_label is None
        assert signals.regime_transition_prob is None
