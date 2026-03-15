"""Tests for valuation model definitions (models/valuation.py).

Covers frozen immutability, JSON roundtrip, validator bounds, UTC enforcement,
and NaN/Inf rejection on float fields.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from options_arena.models.enums import ValuationSignal
from options_arena.models.valuation import CompositeValuation, ValuationModelResult

# ---------------------------------------------------------------------------
# ValuationModelResult tests
# ---------------------------------------------------------------------------


class TestValuationModelResult:
    """Tests for the per-model valuation result model."""

    def test_frozen(self) -> None:
        """ValuationModelResult is immutable (frozen=True)."""
        result = ValuationModelResult(
            methodology="owner_earnings_dcf",
            fair_value=150.0,
            margin_of_safety=0.25,
            confidence=0.8,
            data_quality_notes=["all data present"],
        )
        with pytest.raises(ValidationError):
            result.fair_value = 200.0  # type: ignore[misc]

    def test_none_fair_value_allowed(self) -> None:
        """fair_value and margin_of_safety can be None."""
        result = ValuationModelResult(
            methodology="three_stage_dcf",
            fair_value=None,
            margin_of_safety=None,
            confidence=0.0,
            data_quality_notes=["insufficient data"],
        )
        assert result.fair_value is None
        assert result.margin_of_safety is None

    def test_confidence_validator_lower_bound(self) -> None:
        """Confidence below 0.0 raises ValidationError."""
        with pytest.raises(ValidationError, match="confidence"):
            ValuationModelResult(
                methodology="test",
                fair_value=100.0,
                margin_of_safety=0.1,
                confidence=-0.1,
                data_quality_notes=["test"],
            )

    def test_confidence_validator_upper_bound(self) -> None:
        """Confidence above 1.0 raises ValidationError."""
        with pytest.raises(ValidationError, match="confidence"):
            ValuationModelResult(
                methodology="test",
                fair_value=100.0,
                margin_of_safety=0.1,
                confidence=1.5,
                data_quality_notes=["test"],
            )

    def test_nan_fair_value_rejected(self) -> None:
        """NaN on fair_value raises ValidationError."""
        with pytest.raises(ValidationError, match="fair_value"):
            ValuationModelResult(
                methodology="test",
                fair_value=float("nan"),
                margin_of_safety=0.1,
                confidence=0.5,
                data_quality_notes=["test"],
            )

    def test_inf_margin_of_safety_rejected(self) -> None:
        """Inf on margin_of_safety raises ValidationError."""
        with pytest.raises(ValidationError, match="margin_of_safety"):
            ValuationModelResult(
                methodology="test",
                fair_value=100.0,
                margin_of_safety=float("inf"),
                confidence=0.5,
                data_quality_notes=["test"],
            )

    def test_nan_confidence_rejected(self) -> None:
        """NaN on confidence raises ValidationError."""
        with pytest.raises(ValidationError, match="confidence"):
            ValuationModelResult(
                methodology="test",
                fair_value=100.0,
                margin_of_safety=0.1,
                confidence=float("nan"),
                data_quality_notes=["test"],
            )


# ---------------------------------------------------------------------------
# CompositeValuation tests
# ---------------------------------------------------------------------------


class TestCompositeValuation:
    """Tests for the composite valuation model."""

    def _make_composite(self) -> CompositeValuation:
        """Create a valid CompositeValuation for testing."""
        model_result = ValuationModelResult(
            methodology="owner_earnings_dcf",
            fair_value=150.0,
            margin_of_safety=0.25,
            confidence=0.8,
            data_quality_notes=["all data present"],
        )
        return CompositeValuation(
            ticker="AAPL",
            current_price=120.0,
            composite_fair_value=150.0,
            composite_margin_of_safety=0.2,
            valuation_signal=ValuationSignal.UNDERVALUED,
            models=[model_result],
            weights_used={"owner_earnings_dcf": 1.0},
            computed_at=datetime.now(UTC),
        )

    def test_json_roundtrip(self) -> None:
        """CompositeValuation serializes to JSON and back without data loss."""
        original = self._make_composite()
        json_str = original.model_dump_json()
        restored = CompositeValuation.model_validate_json(json_str)
        assert restored.ticker == original.ticker
        assert restored.current_price == pytest.approx(original.current_price)
        assert restored.composite_fair_value == pytest.approx(original.composite_fair_value)
        assert restored.composite_margin_of_safety == pytest.approx(
            original.composite_margin_of_safety
        )
        assert restored.valuation_signal == original.valuation_signal
        assert len(restored.models) == len(original.models)

    def test_utc_validator_rejects_naive(self) -> None:
        """Non-UTC datetime on computed_at raises ValidationError."""
        with pytest.raises(ValidationError, match="computed_at"):
            CompositeValuation(
                ticker="AAPL",
                current_price=120.0,
                composite_fair_value=None,
                composite_margin_of_safety=None,
                valuation_signal=None,
                models=[],
                weights_used={},
                computed_at=datetime(2026, 1, 1),  # naive — no tzinfo
            )

    def test_utc_validator_rejects_non_utc(self) -> None:
        """Non-UTC timezone on computed_at raises ValidationError."""
        from datetime import timedelta as td

        with pytest.raises(ValidationError, match="computed_at"):
            CompositeValuation(
                ticker="AAPL",
                current_price=120.0,
                composite_fair_value=None,
                composite_margin_of_safety=None,
                valuation_signal=None,
                models=[],
                weights_used={},
                computed_at=datetime(2026, 1, 1, tzinfo=timezone(td(hours=-5))),
            )

    def test_nan_composite_fair_value_rejected(self) -> None:
        """NaN on composite_fair_value raises ValidationError."""
        with pytest.raises(ValidationError, match="composite_fair_value"):
            CompositeValuation(
                ticker="AAPL",
                current_price=120.0,
                composite_fair_value=float("nan"),
                composite_margin_of_safety=None,
                valuation_signal=None,
                models=[],
                weights_used={},
                computed_at=datetime.now(UTC),
            )

    def test_inf_composite_margin_rejected(self) -> None:
        """Inf on composite_margin_of_safety raises ValidationError."""
        with pytest.raises(ValidationError, match="composite_margin_of_safety"):
            CompositeValuation(
                ticker="AAPL",
                current_price=120.0,
                composite_fair_value=150.0,
                composite_margin_of_safety=float("inf"),
                valuation_signal=None,
                models=[],
                weights_used={},
                computed_at=datetime.now(UTC),
            )

    def test_negative_current_price_rejected(self) -> None:
        """Negative current_price raises ValidationError."""
        with pytest.raises(ValidationError, match="current_price"):
            CompositeValuation(
                ticker="AAPL",
                current_price=-10.0,
                composite_fair_value=None,
                composite_margin_of_safety=None,
                valuation_signal=None,
                models=[],
                weights_used={},
                computed_at=datetime.now(UTC),
            )

    def test_none_composite_fields_allowed(self) -> None:
        """All composite fields can be None when all models fail."""
        cv = CompositeValuation(
            ticker="XYZ",
            current_price=50.0,
            composite_fair_value=None,
            composite_margin_of_safety=None,
            valuation_signal=None,
            models=[],
            weights_used={},
            computed_at=datetime.now(UTC),
        )
        assert cv.composite_fair_value is None
        assert cv.valuation_signal is None


# ---------------------------------------------------------------------------
# ValuationSignal enum tests
# ---------------------------------------------------------------------------


class TestValuationSignalEnum:
    """Tests for the ValuationSignal StrEnum."""

    def test_exactly_three_values(self) -> None:
        """ValuationSignal has exactly three members."""
        assert len(ValuationSignal) == 3

    def test_member_values(self) -> None:
        """ValuationSignal members have expected string values."""
        assert ValuationSignal.UNDERVALUED == "undervalued"
        assert ValuationSignal.FAIRLY_VALUED == "fairly_valued"
        assert ValuationSignal.OVERVALUED == "overvalued"

    def test_is_str_enum(self) -> None:
        """ValuationSignal is a StrEnum subclass."""
        from enum import StrEnum

        assert issubclass(ValuationSignal, StrEnum)
