"""Tests for IV surface mispricing rendering in render_volatility_context().

Verifies that the volatility-intelligence surface mispricing classification
and R-squared rendering work correctly in the volatility agent's context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from options_arena.agents._parsing import render_volatility_context
from options_arena.models import ExerciseStyle, MacdSignal, MarketContext, SignalDirection


def _make_context(**overrides: object) -> MarketContext:
    """Build a MarketContext with sensible defaults, accepting field overrides."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.50"),
        "price_52w_high": Decimal("199.62"),
        "price_52w_low": Decimal("164.08"),
        "iv_rank": 45.2,
        "iv_percentile": 52.1,
        "atm_iv_30d": 28.5,
        "rsi_14": 62.3,
        "macd_signal": MacdSignal.BULLISH_CROSSOVER,
        "put_call_ratio": 0.85,
        "next_earnings": None,
        "dte_target": 45,
        "target_strike": Decimal("190.00"),
        "target_delta": 0.35,
        "sector": "Information Technology",
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime(2026, 3, 7, 14, 30, 0, tzinfo=UTC),
        "composite_score": 72.5,
        "direction_signal": SignalDirection.BULLISH,
    }
    defaults.update(overrides)
    return MarketContext(**defaults)


class TestRenderVolatilityContextSurface:
    """Tests for IV surface mispricing rendering in vol context."""

    def test_overpriced_rendering(self) -> None:
        """z > 0.5 renders 'overpriced' in output."""
        ctx = _make_context(iv_surface_residual=1.2)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: +1.20 std devs (overpriced)" in text

    def test_underpriced_rendering(self) -> None:
        """z < -0.5 renders 'underpriced' in output."""
        ctx = _make_context(iv_surface_residual=-0.8)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: -0.80 std devs (underpriced)" in text

    def test_fair_rendering(self) -> None:
        """|z| < 0.5 renders 'fair' in output."""
        ctx = _make_context(iv_surface_residual=0.3)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: +0.30 std devs (fair)" in text

    def test_fair_rendering_negative_small(self) -> None:
        """|z| < 0.5 (negative) renders 'fair' in output."""
        ctx = _make_context(iv_surface_residual=-0.1)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: -0.10 std devs (fair)" in text

    def test_significantly_overpriced(self) -> None:
        """z > 2.0 renders 'significantly overpriced'."""
        ctx = _make_context(iv_surface_residual=2.5)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: +2.50 std devs (significantly overpriced)" in text

    def test_significantly_underpriced(self) -> None:
        """z < -2.0 renders 'significantly underpriced'."""
        ctx = _make_context(iv_surface_residual=-3.1)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: -3.10 std devs (significantly underpriced)" in text

    def test_none_residual_omitted(self) -> None:
        """iv_surface_residual=None produces no IV VS SURFACE line."""
        ctx = _make_context(iv_surface_residual=None)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE" not in text

    def test_r2_rendered(self) -> None:
        """surface_fit_r2 rendered with 2 decimal places."""
        ctx = _make_context(surface_fit_r2=0.95)
        text = render_volatility_context(ctx)

        assert "SURFACE R\u00b2: 0.95" in text

    def test_r2_none_omitted(self) -> None:
        """surface_fit_r2=None produces no SURFACE R-squared line."""
        ctx = _make_context(surface_fit_r2=None)
        text = render_volatility_context(ctx)

        assert "SURFACE R" not in text

    def test_surface_section_appears_with_residual_only(self) -> None:
        """HV & Vol Surface section appears even when only residual is set."""
        ctx = _make_context(
            iv_surface_residual=1.0,
            hv_yang_zhang=None,
            skew_25d=None,
            smile_curvature=None,
            prob_above_current=None,
            surface_fit_r2=None,
        )
        text = render_volatility_context(ctx)

        assert "## HV & Vol Surface" in text
        assert "IV VS SURFACE: +1.00 std devs (overpriced)" in text

    def test_boundary_exactly_0_5(self) -> None:
        """z = 0.5 is NOT > 0.5, so it is classified as 'fair'."""
        ctx = _make_context(iv_surface_residual=0.5)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: +0.50 std devs (fair)" in text

    def test_boundary_exactly_negative_0_5(self) -> None:
        """z = -0.5 is NOT < -0.5, so it is classified as 'fair'."""
        ctx = _make_context(iv_surface_residual=-0.5)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: -0.50 std devs (fair)" in text

    def test_boundary_exactly_2_0(self) -> None:
        """z = 2.0 is NOT > 2.0, so classified as 'overpriced' not 'significantly'."""
        ctx = _make_context(iv_surface_residual=2.0)
        text = render_volatility_context(ctx)

        assert "IV VS SURFACE: +2.00 std devs (overpriced)" in text
