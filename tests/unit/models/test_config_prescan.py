"""Tests for ScanConfig pre-scan filter fields added in #285."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.models import ScanConfig


class TestMaxPrice:
    """Tests for ScanConfig.max_price field."""

    def test_max_price_default_none(self) -> None:
        """max_price defaults to None (no filtering)."""
        cfg = ScanConfig()
        assert cfg.max_price is None

    def test_max_price_accepts_positive_finite(self) -> None:
        """max_price accepts a positive finite float."""
        cfg = ScanConfig(max_price=500.0)
        assert cfg.max_price == pytest.approx(500.0)

    def test_max_price_rejects_nan(self) -> None:
        """max_price must be finite — NaN rejected via isfinite."""
        with pytest.raises(ValidationError, match="max_price must be finite"):
            ScanConfig(max_price=float("nan"))

    def test_max_price_rejects_inf(self) -> None:
        """max_price must be finite — Inf rejected."""
        with pytest.raises(ValidationError, match="max_price must be finite"):
            ScanConfig(max_price=float("inf"))

    def test_max_price_rejects_negative(self) -> None:
        """max_price must be positive."""
        with pytest.raises(ValidationError, match="max_price must be positive"):
            ScanConfig(max_price=-10.0)

    def test_max_price_rejects_zero(self) -> None:
        """max_price must be strictly positive — zero rejected."""
        with pytest.raises(ValidationError, match="max_price must be positive"):
            ScanConfig(max_price=0.0)


class TestDTEFields:
    """Tests for ScanConfig.min_dte and max_dte fields."""

    def test_min_dte_default_none(self) -> None:
        cfg = ScanConfig()
        assert cfg.min_dte is None

    def test_max_dte_default_none(self) -> None:
        cfg = ScanConfig()
        assert cfg.max_dte is None

    def test_valid_dte_range(self) -> None:
        """Both min_dte and max_dte accept positive integers."""
        cfg = ScanConfig(min_dte=7, max_dte=90)
        assert cfg.min_dte == 7
        assert cfg.max_dte == 90

    def test_min_dte_rejects_zero(self) -> None:
        with pytest.raises(ValidationError, match="DTE must be positive"):
            ScanConfig(min_dte=0)

    def test_min_dte_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="DTE must be positive"):
            ScanConfig(min_dte=-5)

    def test_max_dte_rejects_zero(self) -> None:
        with pytest.raises(ValidationError, match="DTE must be positive"):
            ScanConfig(max_dte=0)

    def test_max_dte_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="DTE must be positive"):
            ScanConfig(max_dte=-1)

    def test_single_dte_value_ok(self) -> None:
        """Setting only one of min_dte or max_dte is valid."""
        cfg = ScanConfig(min_dte=14)
        assert cfg.min_dte == 14
        assert cfg.max_dte is None


class TestCrossFieldValidation:
    """Tests for cross-field model_validator on ScanConfig."""

    def test_min_dte_exceeds_max_dte_rejected(self) -> None:
        """Cross-field: min_dte > max_dte must fail."""
        with pytest.raises(ValidationError, match="min_dte.*must not exceed.*max_dte"):
            ScanConfig(min_dte=90, max_dte=30)

    def test_min_dte_equals_max_dte_accepted(self) -> None:
        """Equal min_dte and max_dte is valid (exact DTE targeting)."""
        cfg = ScanConfig(min_dte=45, max_dte=45)
        assert cfg.min_dte == 45
        assert cfg.max_dte == 45

    def test_min_price_exceeds_max_price_rejected(self) -> None:
        """Cross-field: min_price > max_price must fail."""
        with pytest.raises(ValidationError, match="min_price.*must not exceed.*max_price"):
            ScanConfig(min_price=100.0, max_price=50.0)

    def test_min_price_equals_max_price_accepted(self) -> None:
        """Equal min_price and max_price is valid (exact price targeting)."""
        cfg = ScanConfig(min_price=50.0, max_price=50.0)
        assert cfg.min_price == pytest.approx(50.0)
        assert cfg.max_price == pytest.approx(50.0)

    def test_none_fields_skip_cross_field_validation(self) -> None:
        """When either side is None, cross-field checks are skipped."""
        cfg = ScanConfig(min_dte=90)
        assert cfg.min_dte == 90
        assert cfg.max_dte is None

        cfg2 = ScanConfig(max_price=100.0)
        assert cfg2.max_price == pytest.approx(100.0)
        # min_price has default 10.0, which is < max_price 100.0 — ok


class TestNoneSkipsValidation:
    """Tests that None values are properly handled (no validation triggered)."""

    def test_all_new_fields_none_by_default(self) -> None:
        """Default ScanConfig has all new fields as None."""
        cfg = ScanConfig()
        assert cfg.max_price is None
        assert cfg.min_dte is None
        assert cfg.max_dte is None

    def test_all_fields_populated_valid(self) -> None:
        """All new fields populated with valid values."""
        cfg = ScanConfig(max_price=1000.0, min_dte=7, max_dte=90)
        assert cfg.max_price == pytest.approx(1000.0)
        assert cfg.min_dte == 7
        assert cfg.max_dte == 90
