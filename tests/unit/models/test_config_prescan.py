"""Tests for pre-scan filter fields that moved to UniverseFilters and OptionsFilters (#285).

Originally tested on ScanConfig directly; now validates the same behavior on the
new filter models (UniverseFilters for max_price/min_price, OptionsFilters for DTE).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.models.filters import OptionsFilters, UniverseFilters


class TestMaxPrice:
    """Tests for UniverseFilters.max_price field."""

    def test_max_price_default_none(self) -> None:
        """max_price defaults to None (no filtering)."""
        cfg = UniverseFilters()
        assert cfg.max_price is None

    def test_max_price_accepts_positive_finite(self) -> None:
        """max_price accepts a positive finite float."""
        cfg = UniverseFilters(max_price=500.0)
        assert cfg.max_price == pytest.approx(500.0)

    def test_max_price_rejects_nan(self) -> None:
        """max_price must be finite — NaN rejected via isfinite."""
        with pytest.raises(ValidationError, match="max_price must be finite"):
            UniverseFilters(max_price=float("nan"))

    def test_max_price_rejects_inf(self) -> None:
        """max_price must be finite — Inf rejected."""
        with pytest.raises(ValidationError, match="max_price must be finite"):
            UniverseFilters(max_price=float("inf"))

    def test_max_price_rejects_negative(self) -> None:
        """max_price must be positive."""
        with pytest.raises(ValidationError, match="max_price must be positive"):
            UniverseFilters(max_price=-10.0)

    def test_max_price_rejects_zero(self) -> None:
        """max_price must be strictly positive — zero rejected."""
        with pytest.raises(ValidationError, match="max_price must be positive"):
            UniverseFilters(max_price=0.0)


class TestDTEFields:
    """Tests for OptionsFilters.min_dte and max_dte fields."""

    def test_min_dte_default(self) -> None:
        cfg = OptionsFilters()
        assert cfg.min_dte == 30

    def test_max_dte_default(self) -> None:
        cfg = OptionsFilters()
        assert cfg.max_dte == 365

    def test_valid_dte_range(self) -> None:
        """Both min_dte and max_dte accept valid integers."""
        cfg = OptionsFilters(min_dte=7, max_dte=90)
        assert cfg.min_dte == 7
        assert cfg.max_dte == 90

    def test_min_dte_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="min_dte must be >= 0"):
            OptionsFilters(min_dte=-5)

    def test_max_dte_rejects_zero(self) -> None:
        with pytest.raises(ValidationError, match="max_dte must be >= 1"):
            OptionsFilters(max_dte=0)

    def test_max_dte_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="max_dte must be >= 1"):
            OptionsFilters(max_dte=-1)

    def test_single_dte_value_ok(self) -> None:
        """Setting a custom min_dte is valid."""
        cfg = OptionsFilters(min_dte=14)
        assert cfg.min_dte == 14


class TestCrossFieldValidation:
    """Tests for cross-field model_validator on filter models."""

    def test_min_dte_exceeds_max_dte_rejected(self) -> None:
        """Cross-field: min_dte > max_dte must fail."""
        with pytest.raises(ValidationError, match="min_dte.*must not exceed.*max_dte"):
            OptionsFilters(min_dte=90, max_dte=30)

    def test_min_dte_equals_max_dte_accepted(self) -> None:
        """Equal min_dte and max_dte is valid (exact DTE targeting)."""
        cfg = OptionsFilters(min_dte=45, max_dte=45)
        assert cfg.min_dte == 45
        assert cfg.max_dte == 45

    def test_min_price_exceeds_max_price_rejected(self) -> None:
        """Cross-field: min_price > max_price must fail."""
        with pytest.raises(ValidationError, match="min_price.*must not exceed.*max_price"):
            UniverseFilters(min_price=100.0, max_price=50.0)

    def test_min_price_equals_max_price_accepted(self) -> None:
        """Equal min_price and max_price is valid (exact price targeting)."""
        cfg = UniverseFilters(min_price=50.0, max_price=50.0)
        assert cfg.min_price == pytest.approx(50.0)
        assert cfg.max_price == pytest.approx(50.0)

    def test_none_max_price_skips_cross_field_validation(self) -> None:
        """When max_price is None, cross-field checks are skipped."""
        cfg = UniverseFilters(min_price=90.0)
        assert cfg.min_price == pytest.approx(90.0)
        assert cfg.max_price is None

        cfg2 = UniverseFilters(max_price=100.0)
        assert cfg2.max_price == pytest.approx(100.0)
        # min_price has default 10.0, which is < max_price 100.0 — ok


class TestNoneSkipsValidation:
    """Tests that default values are properly handled."""

    def test_universe_filters_defaults(self) -> None:
        """Default UniverseFilters has max_price as None."""
        cfg = UniverseFilters()
        assert cfg.max_price is None
        assert cfg.min_price == pytest.approx(10.0)

    def test_options_filters_defaults(self) -> None:
        """Default OptionsFilters has standard DTE range."""
        cfg = OptionsFilters()
        assert cfg.min_dte == 30
        assert cfg.max_dte == 365

    def test_all_fields_populated_valid(self) -> None:
        """All fields populated with valid values."""
        uf = UniverseFilters(max_price=1000.0)
        assert uf.max_price == pytest.approx(1000.0)
        of = OptionsFilters(min_dte=7, max_dte=90)
        assert of.min_dte == 7
        assert of.max_dte == 90
