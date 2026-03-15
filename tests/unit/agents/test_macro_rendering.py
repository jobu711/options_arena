"""Tests for render_macro_context in agents/_parsing.py.

Tests:
1. Full macro data -> all 4 lines rendered
2. Partial data -> only available lines rendered
3. No macro data -> returns None
4. NaN/Inf guards -> non-finite values skipped
5. Formatting correctness
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from options_arena.agents._parsing import render_macro_context
from options_arena.models import (
    ExerciseStyle,
    MacdSignal,
    MarketContext,
)


def _make_context(**overrides: object) -> MarketContext:
    """Create a minimal MarketContext with optional overrides."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.50"),
        "price_52w_high": Decimal("199.62"),
        "price_52w_low": Decimal("164.08"),
        "rsi_14": 50.0,
        "macd_signal": MacdSignal.NEUTRAL,
        "next_earnings": None,
        "dte_target": 45,
        "target_strike": Decimal("190.00"),
        "target_delta": 0.35,
        "sector": "Technology",
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime(2026, 3, 15, 14, 30, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return MarketContext(**defaults)  # type: ignore[arg-type]


class TestFullMacroData:
    """Tests when all 4 macro fields are present."""

    def test_all_fields_rendered(self) -> None:
        """All 4 macro fields should appear in output."""
        ctx = _make_context(
            macro_regime="expansionary",
            yield_spread=0.0105,
            fed_funds_rate=0.0425,
            vix_level=15.3,
        )
        result = render_macro_context(ctx)
        assert result is not None
        assert "MACRO REGIME: EXPANSIONARY" in result
        assert "YIELD SPREAD (10Y-2Y): 0.0105" in result
        assert "FED FUNDS RATE: 0.0425" in result
        assert "VIX LEVEL: 15.3" in result

    def test_section_header(self) -> None:
        """Output should include the '## Macro Environment' header."""
        ctx = _make_context(
            macro_regime="contractionary",
            yield_spread=-0.005,
            fed_funds_rate=0.055,
            vix_level=28.5,
        )
        result = render_macro_context(ctx)
        assert result is not None
        assert "## Macro Environment" in result

    def test_regime_uppercased(self) -> None:
        """Regime label should be uppercased for agent readability."""
        ctx = _make_context(macro_regime="transitional")
        result = render_macro_context(ctx)
        assert result is not None
        assert "MACRO REGIME: TRANSITIONAL" in result


class TestPartialData:
    """Tests when only some macro fields are present."""

    def test_only_regime(self) -> None:
        """Only macro_regime -> just one line."""
        ctx = _make_context(macro_regime="expansionary")
        result = render_macro_context(ctx)
        assert result is not None
        assert "MACRO REGIME: EXPANSIONARY" in result
        assert "YIELD SPREAD" not in result
        assert "FED FUNDS" not in result
        assert "VIX LEVEL" not in result

    def test_only_yield_spread(self) -> None:
        """Only yield_spread -> just one line."""
        ctx = _make_context(yield_spread=0.015)
        result = render_macro_context(ctx)
        assert result is not None
        assert "YIELD SPREAD (10Y-2Y): 0.0150" in result
        assert "MACRO REGIME" not in result

    def test_only_vix_level(self) -> None:
        """Only vix_level -> just one line."""
        ctx = _make_context(vix_level=22.7)
        result = render_macro_context(ctx)
        assert result is not None
        assert "VIX LEVEL: 22.7" in result

    def test_regime_and_vix_only(self) -> None:
        """macro_regime + vix_level -> two lines."""
        ctx = _make_context(macro_regime="contractionary", vix_level=30.0)
        result = render_macro_context(ctx)
        assert result is not None
        assert "MACRO REGIME: CONTRACTIONARY" in result
        assert "VIX LEVEL: 30.0" in result
        assert "YIELD SPREAD" not in result
        assert "FED FUNDS" not in result


class TestNoData:
    """Tests when no macro fields are populated."""

    def test_all_none_returns_none(self) -> None:
        """No macro fields -> returns None."""
        ctx = _make_context()
        result = render_macro_context(ctx)
        assert result is None

    def test_other_fields_populated(self) -> None:
        """Other MarketContext fields populated but no macro -> returns None."""
        ctx = _make_context(
            iv_rank=45.0,
            adx=28.0,
            pe_ratio=18.5,
        )
        result = render_macro_context(ctx)
        assert result is None


class TestNaNGuards:
    """Tests for NaN/Inf safety in rendering."""

    def test_nan_yield_spread_skipped(self) -> None:
        """NaN yield_spread should be rejected at model level by validator."""
        # NaN yield_spread would be caught by validate_optional_finite on MarketContext
        with pytest.raises(ValueError, match="must be finite"):
            _make_context(yield_spread=float("nan"))

    def test_inf_vix_level_skipped(self) -> None:
        """Inf vix_level should be rejected at model level by validator."""
        with pytest.raises(ValueError, match="must be finite"):
            _make_context(vix_level=float("inf"))

    def test_negative_inf_fed_rate_skipped(self) -> None:
        """Negative Inf fed_funds_rate should be rejected at model level by validator."""
        with pytest.raises(ValueError, match="must be finite"):
            _make_context(fed_funds_rate=float("-inf"))

    def test_only_regime_when_numerics_none(self) -> None:
        """macro_regime is str, not subject to isfinite check."""
        ctx = _make_context(macro_regime="transitional")
        result = render_macro_context(ctx)
        assert result is not None
        assert "MACRO REGIME: TRANSITIONAL" in result


class TestFormatting:
    """Tests for correct number formatting."""

    def test_yield_spread_4_decimals(self) -> None:
        """Yield spread rendered with 4 decimal places."""
        ctx = _make_context(yield_spread=0.0123)
        result = render_macro_context(ctx)
        assert result is not None
        assert "0.0123" in result

    def test_fed_funds_4_decimals(self) -> None:
        """Fed funds rate rendered with 4 decimal places."""
        ctx = _make_context(fed_funds_rate=0.0525)
        result = render_macro_context(ctx)
        assert result is not None
        assert "0.0525" in result

    def test_vix_1_decimal(self) -> None:
        """VIX level rendered with 1 decimal place."""
        ctx = _make_context(vix_level=16.78)
        result = render_macro_context(ctx)
        assert result is not None
        assert "VIX LEVEL: 16.8" in result

    def test_negative_yield_spread(self) -> None:
        """Negative yield spread (inverted curve) renders correctly."""
        ctx = _make_context(yield_spread=-0.005)
        result = render_macro_context(ctx)
        assert result is not None
        assert "YIELD SPREAD (10Y-2Y): -0.0050" in result

    def test_zero_yield_spread(self) -> None:
        """Zero yield spread (flat curve) renders correctly."""
        ctx = _make_context(yield_spread=0.0)
        result = render_macro_context(ctx)
        assert result is not None
        assert "YIELD SPREAD (10Y-2Y): 0.0000" in result
