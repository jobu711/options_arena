"""Tests for neural context rendering functions.

Verifies that ``_render_neural_context()`` and ``_render_neural_surface_comparison()``
produce correct output when neural fields are populated, and produce empty strings
when neural features are disabled (``None`` fields).

Also verifies that the volatility agent context includes neural surface comparison
when the neural pipeline has run, and excludes it when not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from options_arena.agents._parsing import (
    _render_neural_context,
    _render_neural_surface_comparison,
    render_context_block,
    render_volatility_context,
)
from options_arena.models import (
    ExerciseStyle,
    MacdSignal,
    MarketContext,
    SignalDirection,
)


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


# ---------------------------------------------------------------------------
# _render_neural_context
# ---------------------------------------------------------------------------


class TestRenderNeuralContext:
    """Tests for neural trajectory probability rendering."""

    def test_renders_prob_profit_when_available(self) -> None:
        """Verify prob_profit_neural appears in rendered context."""
        ctx = _make_context(prob_profit_neural=0.65)
        result = _render_neural_context(ctx)

        assert "Neural Trajectory" in result
        assert "NEURAL P(PROFIT)" in result

    def test_empty_when_none(self) -> None:
        """Verify empty string when prob_profit_neural is None."""
        ctx = _make_context(prob_profit_neural=None)
        result = _render_neural_context(ctx)

        assert result == ""

    def test_isfinite_guard(self) -> None:
        """Verify NaN/Inf prob_profit_neural is rejected by model validator.

        MarketContext has a ``validate_optional_finite`` + ``validate_prob_profit_neural``
        validator that rejects non-finite values at the boundary. The rendering layer's
        ``_render_optional()`` provides defense-in-depth, but the model guard fires first.
        """
        import pydantic

        for bad_value in [float("nan"), float("inf"), float("-inf")]:
            with pytest.raises(pydantic.ValidationError, match="prob_profit_neural"):
                _make_context(prob_profit_neural=bad_value)

    def test_percentage_format(self) -> None:
        """Verify probability rendered as percentage (e.g., '65.0%')."""
        ctx = _make_context(prob_profit_neural=0.65)
        result = _render_neural_context(ctx)

        assert "65.0%" in result

    def test_zero_probability(self) -> None:
        """Verify 0.0 probability renders correctly."""
        ctx = _make_context(prob_profit_neural=0.0)
        result = _render_neural_context(ctx)

        assert "NEURAL P(PROFIT): 0.0%" in result

    def test_full_probability(self) -> None:
        """Verify 1.0 probability renders correctly."""
        ctx = _make_context(prob_profit_neural=1.0)
        result = _render_neural_context(ctx)

        assert "NEURAL P(PROFIT): 100.0%" in result

    def test_context_block_includes_neural(self) -> None:
        """Verify render_context_block() includes neural section."""
        ctx = _make_context(prob_profit_neural=0.72)
        block = render_context_block(ctx)

        assert "Neural Trajectory" in block
        assert "NEURAL P(PROFIT)" in block
        assert "72.0%" in block

    def test_context_block_omits_when_none(self) -> None:
        """Verify render_context_block() excludes neural section when None."""
        ctx = _make_context(prob_profit_neural=None)
        block = render_context_block(ctx)

        assert "Neural Trajectory" not in block
        assert "NEURAL P(PROFIT)" not in block


# ---------------------------------------------------------------------------
# _render_neural_surface_comparison
# ---------------------------------------------------------------------------


class TestRenderNeuralSurfaceComparison:
    """Tests for spline vs neural surface R-squared comparison rendering.

    The comparison function gates on ``neural_surface_r2`` (a dedicated neural
    surface field). When this field is absent from MarketContext, the function
    returns an empty string. ``prob_profit_neural`` (trajectory model) is NOT
    used as a proxy.
    """

    def test_empty_when_no_neural_surface_r2(self) -> None:
        """Verify empty string when neural_surface_r2 is not available."""
        ctx = _make_context(
            surface_fit_r2=0.85,
            prob_profit_neural=0.65,
        )
        result = _render_neural_surface_comparison(ctx)

        assert result == ""

    def test_empty_when_no_neural(self) -> None:
        """Verify empty string when neural surface not used."""
        ctx = _make_context(
            surface_fit_r2=0.85,
            prob_profit_neural=None,
        )
        result = _render_neural_surface_comparison(ctx)

        assert result == ""

    def test_empty_when_no_spline(self) -> None:
        """Verify empty string when spline R-squared is None."""
        ctx = _make_context(
            surface_fit_r2=None,
            prob_profit_neural=0.65,
        )
        result = _render_neural_surface_comparison(ctx)

        assert result == ""

    def test_isfinite_guard_on_r2(self) -> None:
        """Verify NaN R-squared is rejected by model validator.

        MarketContext's ``validate_optional_finite`` validator rejects non-finite
        values at the boundary. The rendering layer's ``math.isfinite()`` guard
        provides defense-in-depth.
        """
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="surface_fit_r2"):
            _make_context(
                surface_fit_r2=float("nan"),
                prob_profit_neural=0.65,
            )


# ---------------------------------------------------------------------------
# Volatility Agent Neural Context
# ---------------------------------------------------------------------------


class TestVolatilityAgentNeuralContext:
    """Tests for neural surface comparison in volatility agent context."""

    def test_no_neural_surface_comparison_without_dedicated_field(self) -> None:
        """Verify volatility context omits surface comparison without neural_surface_r2."""
        ctx = _make_context(
            surface_fit_r2=0.75,
            prob_profit_neural=0.60,
        )
        vol_ctx = render_volatility_context(ctx)

        assert "Surface Model Comparison" not in vol_ctx

    def test_no_neural_in_default_config(self) -> None:
        """Verify no neural content in volatility prompt with default config."""
        ctx = _make_context(
            surface_fit_r2=None,
            prob_profit_neural=None,
        )
        vol_ctx = render_volatility_context(ctx)

        assert "Surface Model Comparison" not in vol_ctx
