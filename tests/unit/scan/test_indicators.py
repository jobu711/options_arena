"""Tests for scan.indicators — data-driven indicator dispatch.

Covers:
  - InputShape enum membership and values.
  - INDICATOR_REGISTRY: size, field-name validity, callability, name mappings.
  - ohlcv_to_dataframe: Decimal->float, DatetimeIndex, column names, sort order.
  - compute_indicators: happy path, NaN->None, isolated failure, result type.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.trend import roc
from options_arena.models.market_data import OHLCV
from options_arena.models.scan import IndicatorSignals
from options_arena.scan.indicators import (
    INDICATOR_REGISTRY,
    IndicatorSpec,
    InputShape,
    compute_indicators,
    ohlcv_to_dataframe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ohlcv(n: int = 300) -> list[OHLCV]:
    """Generate *n* days of synthetic OHLCV data for testing.

    Produces a simple oscillating price walk around 100 with volume
    starting at 1 000 000 and increasing linearly.  300 bars exceeds
    the warmup of every indicator in the registry.
    """
    bars: list[OHLCV] = []
    base_price = 100.0
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        close = base_price + (i % 10) - 5
        bars.append(
            OHLCV(
                ticker="TEST",
                date=d,
                open=Decimal(str(round(close - 0.5, 2))),
                high=Decimal(str(round(close + 1.0, 2))),
                low=Decimal(str(round(close - 1.0, 2))),
                close=Decimal(str(round(close, 2))),
                adjusted_close=Decimal(str(round(close, 2))),
                volume=1_000_000 + i * 1000,
            )
        )
        base_price = close
    return bars


# ---------------------------------------------------------------------------
# InputShape enum tests
# ---------------------------------------------------------------------------


class TestInputShape:
    """InputShape StrEnum has exactly 5 members with lowercase values."""

    def test_member_count(self) -> None:
        assert len(InputShape) == 5

    def test_values_are_lowercase_strings(self) -> None:
        for member in InputShape:
            assert isinstance(member.value, str)
            assert member.value == member.value.lower()

    def test_specific_members(self) -> None:
        assert InputShape.CLOSE == "close"
        assert InputShape.HLC == "hlc"
        assert InputShape.CLOSE_VOLUME == "close_volume"
        assert InputShape.HLCV == "hlcv"
        assert InputShape.VOLUME == "volume"

    def test_is_str_enum(self) -> None:
        for member in InputShape:
            assert isinstance(member, str)


# ---------------------------------------------------------------------------
# INDICATOR_REGISTRY tests
# ---------------------------------------------------------------------------


class TestIndicatorRegistry:
    """INDICATOR_REGISTRY: 14 entries, all valid IndicatorSpec tuples."""

    def test_exactly_14_entries(self) -> None:
        assert len(INDICATOR_REGISTRY) == 14

    def test_all_are_indicator_spec(self) -> None:
        for spec in INDICATOR_REGISTRY:
            assert isinstance(spec, IndicatorSpec)

    def test_all_field_names_match_indicator_signals(self) -> None:
        signal_fields = set(IndicatorSignals.model_fields.keys())
        for spec in INDICATOR_REGISTRY:
            assert spec.field_name in signal_fields, (
                f"{spec.field_name!r} is not a field on IndicatorSignals"
            )

    def test_no_duplicate_field_names(self) -> None:
        names = [spec.field_name for spec in INDICATOR_REGISTRY]
        assert len(names) == len(set(names))

    def test_all_functions_are_callable(self) -> None:
        for spec in INDICATOR_REGISTRY:
            assert callable(spec.func)

    def test_all_input_shapes_are_valid(self) -> None:
        for spec in INDICATOR_REGISTRY:
            assert isinstance(spec.input_shape, InputShape)

    # --- Verify the 4 name mappings that differ from function names ---

    def test_stoch_rsi_maps_to_stochastic_rsi(self) -> None:
        from options_arena.indicators.oscillators import stoch_rsi

        spec = next(s for s in INDICATOR_REGISTRY if s.field_name == "stochastic_rsi")
        assert spec.func is stoch_rsi

    def test_atr_percent_maps_to_atr_pct(self) -> None:
        from options_arena.indicators.volatility import atr_percent

        spec = next(s for s in INDICATOR_REGISTRY if s.field_name == "atr_pct")
        assert spec.func is atr_percent

    def test_obv_trend_maps_to_obv(self) -> None:
        from options_arena.indicators.volume import obv_trend

        spec = next(s for s in INDICATOR_REGISTRY if s.field_name == "obv")
        assert spec.func is obv_trend

    def test_ad_trend_maps_to_ad(self) -> None:
        from options_arena.indicators.volume import ad_trend

        spec = next(s for s in INDICATOR_REGISTRY if s.field_name == "ad")
        assert spec.func is ad_trend

    def test_registry_covers_all_expected_fields(self) -> None:
        """The 14 OHLCV-based fields are all present; 4 options-specific are absent."""
        ohlcv_fields = {
            "rsi",
            "stochastic_rsi",
            "williams_r",
            "adx",
            "roc",
            "supertrend",
            "bb_width",
            "atr_pct",
            "keltner_width",
            "obv",
            "relative_volume",
            "ad",
            "sma_alignment",
            "vwap_deviation",
        }
        registry_fields = {spec.field_name for spec in INDICATOR_REGISTRY}
        assert registry_fields == ohlcv_fields

    def test_options_specific_fields_not_in_registry(self) -> None:
        """Options-specific fields must NOT be in the registry."""
        options_fields = {"iv_rank", "iv_percentile", "put_call_ratio", "max_pain_distance"}
        registry_fields = {spec.field_name for spec in INDICATOR_REGISTRY}
        assert options_fields.isdisjoint(registry_fields)


# ---------------------------------------------------------------------------
# ohlcv_to_dataframe tests
# ---------------------------------------------------------------------------


class TestOhlcvToDataframe:
    """ohlcv_to_dataframe converts OHLCV models to an indicator-ready DataFrame."""

    def test_decimal_to_float_conversion(self) -> None:
        bars = make_ohlcv(5)
        df = ohlcv_to_dataframe(bars)
        for col in ("open", "high", "low", "close"):
            assert df[col].dtype == np.float64, f"{col} should be float64"
            for val in df[col]:
                assert isinstance(val, float)

    def test_datetime_index(self) -> None:
        bars = make_ohlcv(5)
        df = ohlcv_to_dataframe(bars)
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_column_names(self) -> None:
        bars = make_ohlcv(5)
        df = ohlcv_to_dataframe(bars)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_no_adjusted_close_or_ticker(self) -> None:
        bars = make_ohlcv(5)
        df = ohlcv_to_dataframe(bars)
        assert "adjusted_close" not in df.columns
        assert "ticker" not in df.columns

    def test_sort_ascending_by_date(self) -> None:
        bars = make_ohlcv(10)
        # Reverse so input is descending
        reversed_bars = list(reversed(bars))
        df = ohlcv_to_dataframe(reversed_bars)
        dates = df.index.tolist()
        assert dates == sorted(dates)

    def test_volume_is_int(self) -> None:
        bars = make_ohlcv(5)
        df = ohlcv_to_dataframe(bars)
        for val in df["volume"]:
            assert isinstance(val, (int, np.integer))

    def test_row_count_matches_input(self) -> None:
        bars = make_ohlcv(42)
        df = ohlcv_to_dataframe(bars)
        assert len(df) == 42

    def test_close_values_match_input(self) -> None:
        bars = make_ohlcv(5)
        df = ohlcv_to_dataframe(bars)
        for bar, close_val in zip(bars, df["close"], strict=True):
            assert close_val == pytest.approx(float(bar.close), rel=1e-9)


# ---------------------------------------------------------------------------
# compute_indicators tests
# ---------------------------------------------------------------------------


class TestComputeIndicators:
    """compute_indicators dispatches registry entries and returns IndicatorSignals."""

    def test_returns_indicator_signals_type(self) -> None:
        bars = make_ohlcv(300)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, INDICATOR_REGISTRY)
        assert isinstance(result, IndicatorSignals)

    def test_happy_path_all_14_populated(self) -> None:
        """With 300 bars all 14 OHLCV indicators should produce non-None values."""
        bars = make_ohlcv(300)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, INDICATOR_REGISTRY)

        ohlcv_fields = [spec.field_name for spec in INDICATOR_REGISTRY]
        for field in ohlcv_fields:
            value = getattr(result, field)
            assert value is not None, f"{field} should not be None with 300 bars"
            assert isinstance(value, float), f"{field} should be float"

    def test_options_specific_fields_remain_none(self) -> None:
        """Options-specific fields are not in registry and must stay None."""
        bars = make_ohlcv(300)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, INDICATOR_REGISTRY)

        assert result.iv_rank is None
        assert result.iv_percentile is None
        assert result.put_call_ratio is None
        assert result.max_pain_distance is None

    def test_nan_converted_to_none(self) -> None:
        """An indicator that returns all NaN should produce None for its field."""

        def always_nan(close: pd.Series) -> pd.Series:
            return pd.Series(np.nan, index=close.index)

        nan_registry = [IndicatorSpec("rsi", always_nan, InputShape.CLOSE)]
        bars = make_ohlcv(50)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, nan_registry)
        assert result.rsi is None

    def test_isolated_failure_does_not_crash_others(self) -> None:
        """A failing indicator sets its field to None; others still populate."""
        call_count = 0

        def exploding_func(close: pd.Series) -> pd.Series:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        # Create a 2-entry registry: one that explodes and one real one
        mixed_registry = [
            IndicatorSpec("rsi", exploding_func, InputShape.CLOSE),
            IndicatorSpec("roc", roc, InputShape.CLOSE),
        ]
        bars = make_ohlcv(300)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, mixed_registry)

        assert result.rsi is None  # exploding func -> None
        assert result.roc is not None  # real indicator still works
        assert call_count == 1

    def test_isolated_failure_logs_warning(self) -> None:
        """A failing indicator is logged at WARNING level."""

        def exploding_func(close: pd.Series) -> pd.Series:
            raise ValueError("test explosion")

        registry = [IndicatorSpec("rsi", exploding_func, InputShape.CLOSE)]
        bars = make_ohlcv(50)
        df = ohlcv_to_dataframe(bars)

        with patch("options_arena.scan.indicators.logger") as mock_logger:
            compute_indicators(df, registry)
            mock_logger.warning.assert_called_once()

    def test_empty_registry_returns_all_none(self) -> None:
        bars = make_ohlcv(50)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, [])
        # All 18 fields should be None
        for field_name in IndicatorSignals.model_fields:
            assert getattr(result, field_name) is None

    def test_values_are_finite_floats(self) -> None:
        """All non-None values from a happy-path run must be finite."""
        bars = make_ohlcv(300)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, INDICATOR_REGISTRY)

        for spec in INDICATOR_REGISTRY:
            value = getattr(result, spec.field_name)
            if value is not None:
                assert math.isfinite(value), f"{spec.field_name} is not finite: {value}"

    def test_custom_single_indicator_close(self) -> None:
        """A single-indicator CLOSE registry dispatches correctly."""

        def fake_rsi(close: pd.Series) -> pd.Series:
            return pd.Series(42.0, index=close.index)

        registry = [IndicatorSpec("rsi", fake_rsi, InputShape.CLOSE)]
        bars = make_ohlcv(10)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, registry)
        assert result.rsi == pytest.approx(42.0)

    def test_custom_single_indicator_hlc(self) -> None:
        """A single-indicator HLC registry dispatches high/low/close correctly."""

        def fake_adx(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
            return pd.Series(25.0, index=close.index)

        registry = [IndicatorSpec("adx", fake_adx, InputShape.HLC)]
        bars = make_ohlcv(10)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, registry)
        assert result.adx == pytest.approx(25.0)

    def test_custom_single_indicator_close_volume(self) -> None:
        """A CLOSE_VOLUME registry dispatches close and volume correctly."""

        def fake_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
            return pd.Series(1234.0, index=close.index)

        registry = [IndicatorSpec("obv", fake_obv, InputShape.CLOSE_VOLUME)]
        bars = make_ohlcv(10)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, registry)
        assert result.obv == pytest.approx(1234.0)

    def test_custom_single_indicator_hlcv(self) -> None:
        """An HLCV registry dispatches high/low/close/volume correctly."""

        def fake_ad(
            high: pd.Series,
            low: pd.Series,
            close: pd.Series,
            volume: pd.Series,
        ) -> pd.Series:
            return pd.Series(-99.0, index=close.index)

        registry = [IndicatorSpec("ad", fake_ad, InputShape.HLCV)]
        bars = make_ohlcv(10)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, registry)
        assert result.ad == pytest.approx(-99.0)

    def test_custom_single_indicator_volume(self) -> None:
        """A VOLUME registry dispatches only the volume column."""

        def fake_rvol(volume: pd.Series) -> pd.Series:
            return pd.Series(1.5, index=volume.index)

        registry = [IndicatorSpec("relative_volume", fake_rvol, InputShape.VOLUME)]
        bars = make_ohlcv(10)
        df = ohlcv_to_dataframe(bars)
        result = compute_indicators(df, registry)
        assert result.relative_volume == pytest.approx(1.5)
