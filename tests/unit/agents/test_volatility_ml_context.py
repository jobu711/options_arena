"""Tests for ML volatility forecast rendering in volatility context.

Validates that ``render_volatility_context()`` correctly renders GARCH forecast
and IV-vs-GARCH spread data when present on ``MarketContext``, and omits them
when the data is absent (None or non-finite).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from options_arena.agents._parsing import render_volatility_context
from options_arena.models.analysis import MarketContext
from options_arena.models.enums import ExerciseStyle, MacdSignal, SignalDirection


def _make_context(**overrides: object) -> MarketContext:
    """Build a minimal MarketContext with optional field overrides."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.00"),
        "price_52w_high": Decimal("200.00"),
        "price_52w_low": Decimal("150.00"),
        "rsi_14": 55.0,
        "macd_signal": MacdSignal.NEUTRAL,
        "sector": "Technology",
        "next_earnings": None,
        "dte_target": 45,
        "target_strike": Decimal("190.00"),
        "target_delta": 0.35,
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime.now(UTC),
        "composite_score": 65.0,
        "direction_signal": SignalDirection.BULLISH,
    }
    defaults.update(overrides)
    return MarketContext(**defaults)  # type: ignore[arg-type]


class TestGARCHForecastRendering:
    """Test GARCH forecast lines in render_volatility_context()."""

    def test_garch_forecast_rendered_when_present(self) -> None:
        """GARCH forecast line appears when vol_forecast_garch is set."""
        ctx = _make_context(vol_forecast_garch=0.25)
        output = render_volatility_context(ctx)
        assert "GARCH FORECAST (ANN.): 25.0%" in output

    def test_garch_forecast_not_rendered_when_none(self) -> None:
        """GARCH forecast line absent when vol_forecast_garch is None."""
        ctx = _make_context(vol_forecast_garch=None)
        output = render_volatility_context(ctx)
        assert "GARCH FORECAST" not in output

    def test_garch_forecast_not_rendered_when_nan(self) -> None:
        """GARCH forecast line absent when vol_forecast_garch is NaN."""
        ctx = _make_context(vol_forecast_garch=float("nan"))
        output = render_volatility_context(ctx)
        assert "GARCH FORECAST" not in output

    def test_garch_forecast_not_rendered_when_inf(self) -> None:
        """GARCH forecast line absent when vol_forecast_garch is Inf."""
        ctx = _make_context(vol_forecast_garch=float("inf"))
        output = render_volatility_context(ctx)
        assert "GARCH FORECAST" not in output


class TestIVSpreadRendering:
    """Test IV-vs-GARCH forecast spread lines in render_volatility_context()."""

    def test_iv_spread_rendered_when_present(self) -> None:
        """IV spread line appears when iv_vs_forecast_spread is set."""
        ctx = _make_context(iv_vs_forecast_spread=0.05)
        output = render_volatility_context(ctx)
        assert "IV VS GARCH FORECAST SPREAD: 5.0%" in output

    def test_iv_spread_not_rendered_when_none(self) -> None:
        """IV spread line absent when iv_vs_forecast_spread is None."""
        ctx = _make_context(iv_vs_forecast_spread=None)
        output = render_volatility_context(ctx)
        assert "IV VS GARCH FORECAST SPREAD" not in output

    def test_negative_spread_rendered_correctly(self) -> None:
        """Negative IV spread rendered correctly (IV cheap vs GARCH)."""
        ctx = _make_context(iv_vs_forecast_spread=-0.03)
        output = render_volatility_context(ctx)
        assert "IV VS GARCH FORECAST SPREAD: -3.0%" in output


class TestCombinedRendering:
    """Test both GARCH and IV spread rendered together."""

    def test_both_fields_rendered(self) -> None:
        """Both GARCH forecast and IV spread rendered when available."""
        ctx = _make_context(vol_forecast_garch=0.25, iv_vs_forecast_spread=0.05)
        output = render_volatility_context(ctx)
        assert "GARCH FORECAST (ANN.): 25.0%" in output
        assert "IV VS GARCH FORECAST SPREAD: 5.0%" in output

    def test_garch_without_spread(self) -> None:
        """GARCH rendered alone when spread is None."""
        ctx = _make_context(vol_forecast_garch=0.25, iv_vs_forecast_spread=None)
        output = render_volatility_context(ctx)
        assert "GARCH FORECAST (ANN.): 25.0%" in output
        assert "IV VS GARCH FORECAST SPREAD" not in output

    def test_no_ml_data_no_rendering(self) -> None:
        """No ML lines rendered when both fields are None."""
        ctx = _make_context(vol_forecast_garch=None, iv_vs_forecast_spread=None)
        output = render_volatility_context(ctx)
        assert "GARCH" not in output
        assert "IV VS GARCH" not in output
