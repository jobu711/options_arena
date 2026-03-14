"""Tests for Volatility Intelligence surface mispricing fields.

Issue #503: Validates the 3 new MarketContext fields (iv_surface_residual,
surface_fit_r2, surface_is_1d) and the 3 new IndicatorSignals fields
(iv_surface_residual, surface_fit_r2, surface_is_1d).

Tests cover:
- Valid construction with all 3 fields
- Default None values
- NaN rejection for iv_surface_residual
- Inf rejection for iv_surface_residual
- surface_fit_r2 range validation (rejects >1.0 and <0.0)
- surface_fit_r2 boundary values (0.0 and 1.0 pass)
- surface_is_1d accepts True/False/None
- completeness_ratio() counts surface fields
- IndicatorSignals surface field defaults
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models.analysis import MarketContext
from options_arena.models.enums import ExerciseStyle, MacdSignal
from options_arena.models.scan import IndicatorSignals

pytestmark = pytest.mark.critical


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market_context(**overrides: object) -> MarketContext:
    """Build a minimal MarketContext with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.00"),
        "price_52w_high": Decimal("200.00"),
        "price_52w_low": Decimal("140.00"),
        "macd_signal": MacdSignal.BULLISH_CROSSOVER,
        "next_earnings": date(2026, 4, 25),
        "dte_target": 45,
        "target_strike": Decimal("185.00"),
        "target_delta": 0.35,
        "sector": "Information Technology",
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime(2026, 3, 14, 14, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return MarketContext(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# MarketContext — surface mispricing fields
# ===========================================================================


class TestMarketContextSurfaceFields:
    """Verify 3 new MarketContext fields for volatility intelligence."""

    def test_valid_surface_fields(self) -> None:
        """All 3 surface fields accept valid values."""
        ctx = _make_market_context(
            iv_surface_residual=-1.5,
            surface_fit_r2=0.87,
            surface_is_1d=False,
        )
        assert ctx.iv_surface_residual == pytest.approx(-1.5)
        assert ctx.surface_fit_r2 == pytest.approx(0.87)
        assert ctx.surface_is_1d is False

    def test_none_defaults(self) -> None:
        """All 3 surface fields default to None when not provided."""
        ctx = _make_market_context()
        assert ctx.iv_surface_residual is None
        assert ctx.surface_fit_r2 is None
        assert ctx.surface_is_1d is None

    def test_nan_iv_residual_rejected(self) -> None:
        """NaN iv_surface_residual is rejected by validate_optional_finite."""
        with pytest.raises(ValidationError, match="finite"):
            _make_market_context(iv_surface_residual=float("nan"))

    def test_inf_iv_residual_rejected(self) -> None:
        """Inf iv_surface_residual is rejected by validate_optional_finite."""
        with pytest.raises(ValidationError, match="finite"):
            _make_market_context(iv_surface_residual=float("inf"))

    def test_negative_inf_iv_residual_rejected(self) -> None:
        """-Inf iv_surface_residual is rejected by validate_optional_finite."""
        with pytest.raises(ValidationError, match="finite"):
            _make_market_context(iv_surface_residual=float("-inf"))

    def test_r2_out_of_range_rejected(self) -> None:
        """surface_fit_r2 > 1.0 is rejected."""
        with pytest.raises(ValidationError, match="surface_fit_r2"):
            _make_market_context(surface_fit_r2=1.01)

    def test_negative_r2_rejected(self) -> None:
        """surface_fit_r2 < 0.0 is rejected."""
        with pytest.raises(ValidationError, match="surface_fit_r2"):
            _make_market_context(surface_fit_r2=-0.01)

    def test_r2_boundary_values(self) -> None:
        """surface_fit_r2 = 0.0 and 1.0 should both pass."""
        ctx_zero = _make_market_context(surface_fit_r2=0.0)
        assert ctx_zero.surface_fit_r2 == pytest.approx(0.0)

        ctx_one = _make_market_context(surface_fit_r2=1.0)
        assert ctx_one.surface_fit_r2 == pytest.approx(1.0)

    def test_r2_nan_rejected(self) -> None:
        """NaN surface_fit_r2 is rejected by its own range validator."""
        with pytest.raises(ValidationError, match="finite"):
            _make_market_context(surface_fit_r2=float("nan"))

    def test_surface_is_1d_bool(self) -> None:
        """surface_is_1d accepts True, False, and None."""
        ctx_true = _make_market_context(surface_is_1d=True)
        assert ctx_true.surface_is_1d is True

        ctx_false = _make_market_context(surface_is_1d=False)
        assert ctx_false.surface_is_1d is False

        ctx_none = _make_market_context(surface_is_1d=None)
        assert ctx_none.surface_is_1d is None

    def test_completeness_includes_surface(self) -> None:
        """completeness_ratio() counts iv_surface_residual and surface_fit_r2
        when a contract is present (contract_mid is set)."""
        # With contract_mid, surface fields are counted
        ctx_with_contract = _make_market_context(
            contract_mid=Decimal("5.50"),
            iv_surface_residual=0.5,
            surface_fit_r2=0.9,
        )
        ratio_with_contract = ctx_with_contract.completeness_ratio()

        # With contract, more fields are checkable (Greeks + surface) so the
        # ratio changes. The surface fields should be counted.
        # Verify that setting surface fields increases the ratio when contract exists
        ctx_with_contract_no_surface = _make_market_context(
            contract_mid=Decimal("5.50"),
        )
        ratio_no_surface = ctx_with_contract_no_surface.completeness_ratio()
        assert ratio_with_contract > ratio_no_surface

    def test_negative_residual_accepted(self) -> None:
        """iv_surface_residual can be negative (contract is 'expensive')."""
        ctx = _make_market_context(iv_surface_residual=-2.5)
        assert ctx.iv_surface_residual == pytest.approx(-2.5)

    def test_positive_residual_accepted(self) -> None:
        """iv_surface_residual can be positive (contract is 'cheap')."""
        ctx = _make_market_context(iv_surface_residual=3.1)
        assert ctx.iv_surface_residual == pytest.approx(3.1)


# ===========================================================================
# IndicatorSignals — surface mispricing fields
# ===========================================================================


class TestIndicatorSignalsSurfaceDefaults:
    """Verify 3 new IndicatorSignals fields for volatility intelligence."""

    def test_default_none(self) -> None:
        """New surface fields default to None when not provided."""
        signals = IndicatorSignals()
        assert signals.iv_surface_residual is None
        assert signals.surface_fit_r2 is None
        assert signals.surface_is_1d is None

    def test_explicit_values(self) -> None:
        """New surface fields accept valid float values."""
        signals = IndicatorSignals(
            iv_surface_residual=-0.8,
            surface_fit_r2=0.92,
            surface_is_1d=1.0,
        )
        assert signals.iv_surface_residual == pytest.approx(-0.8)
        assert signals.surface_fit_r2 == pytest.approx(0.92)
        assert signals.surface_is_1d == pytest.approx(1.0)

    def test_nan_sanitized_to_none(self) -> None:
        """NaN in surface fields is sanitized to None by model_validator."""
        signals = IndicatorSignals(
            iv_surface_residual=float("nan"),
            surface_fit_r2=float("nan"),
            surface_is_1d=float("nan"),
        )
        assert signals.iv_surface_residual is None
        assert signals.surface_fit_r2 is None
        assert signals.surface_is_1d is None

    def test_inf_sanitized_to_none(self) -> None:
        """Inf in surface fields is sanitized to None by model_validator."""
        signals = IndicatorSignals(
            iv_surface_residual=float("inf"),
            surface_fit_r2=float("-inf"),
            surface_is_1d=float("inf"),
        )
        assert signals.iv_surface_residual is None
        assert signals.surface_fit_r2 is None
        assert signals.surface_is_1d is None

    def test_json_roundtrip(self) -> None:
        """JSON serialization/deserialization preserves surface field values."""
        signals = IndicatorSignals(
            iv_surface_residual=1.2,
            surface_fit_r2=0.85,
            surface_is_1d=0.0,
        )
        restored = IndicatorSignals.model_validate_json(signals.model_dump_json())
        assert restored.iv_surface_residual == pytest.approx(1.2)
        assert restored.surface_fit_r2 == pytest.approx(0.85)
        assert restored.surface_is_1d == pytest.approx(0.0)

    def test_existing_fields_unchanged(self) -> None:
        """Existing indicator fields still work after adding surface fields."""
        signals = IndicatorSignals(
            rsi=65.0,
            hv_yang_zhang=0.25,
            iv_surface_residual=-0.5,
        )
        assert signals.rsi == pytest.approx(65.0)
        assert signals.hv_yang_zhang == pytest.approx(0.25)
        assert signals.iv_surface_residual == pytest.approx(-0.5)
