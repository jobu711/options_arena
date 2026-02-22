"""Cross-model serialization tests for Options Arena data models.

Tests cover:
- Decimal precision: Decimal("1.05") survives JSON roundtrip without precision loss
- StrEnum values serialize to lowercase strings in JSON
- Computed fields (mid, spread, dte) appear in model_dump() output
- Nested model serialization (OptionContract with OptionGreeks)
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from options_arena.models import (
    OHLCV,
    ExerciseStyle,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    TickerInfo,
)

# ---------------------------------------------------------------------------
# Decimal Precision Tests
# ---------------------------------------------------------------------------


class TestDecimalPrecision:
    """Verify Decimal fields survive JSON roundtrip without float precision loss."""

    def test_ohlcv_decimal_roundtrip(self) -> None:
        """OHLCV Decimal("1.05") survives JSON roundtrip as "1.05"."""
        ohlcv = OHLCV(
            ticker="TEST",
            date=date(2025, 1, 1),
            open=Decimal("1.05"),
            high=Decimal("1.10"),
            low=Decimal("1.00"),
            close=Decimal("1.05"),
            volume=100,
            adjusted_close=Decimal("1.05"),
        )
        json_str = ohlcv.model_dump_json()
        restored = OHLCV.model_validate_json(json_str)
        assert restored.open == Decimal("1.05")
        assert restored.close == Decimal("1.05")
        assert str(restored.open) == "1.05"

    def test_quote_decimal_roundtrip(self) -> None:
        """Quote Decimal("1.05") survives JSON roundtrip."""
        quote = Quote(
            ticker="TEST",
            price=Decimal("1.05"),
            bid=Decimal("1.04"),
            ask=Decimal("1.06"),
            volume=50,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        json_str = quote.model_dump_json()
        restored = Quote.model_validate_json(json_str)
        assert restored.price == Decimal("1.05")
        assert str(restored.price) == "1.05"

    def test_ticker_info_decimal_roundtrip(self) -> None:
        """TickerInfo Decimal fields survive JSON roundtrip."""
        info = TickerInfo(
            ticker="TEST",
            company_name="Test Corp",
            sector="Technology",
            current_price=Decimal("1.05"),
            fifty_two_week_high=Decimal("2.10"),
            fifty_two_week_low=Decimal("0.50"),
        )
        json_str = info.model_dump_json()
        restored = TickerInfo.model_validate_json(json_str)
        assert restored.current_price == Decimal("1.05")
        assert str(restored.current_price) == "1.05"

    def test_option_contract_decimal_roundtrip(self) -> None:
        """OptionContract Decimal fields survive JSON roundtrip."""
        contract = OptionContract(
            ticker="TEST",
            option_type=OptionType.CALL,
            strike=Decimal("1.05"),
            expiration=date(2025, 12, 19),
            bid=Decimal("0.10"),
            ask=Decimal("0.15"),
            last=Decimal("0.12"),
            volume=100,
            open_interest=500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.25,
        )
        json_str = contract.model_dump_json()
        restored = OptionContract.model_validate_json(json_str)
        assert restored.strike == Decimal("1.05")
        assert restored.bid == Decimal("0.10")
        assert restored.ask == Decimal("0.15")
        assert restored.last == Decimal("0.12")
        # Ensure it is precisely "1.05", not a float approximation
        assert str(restored.strike) == "1.05"

    def test_decimal_not_float_in_json(self) -> None:
        """Decimal fields serialize as strings in JSON, not floats."""
        contract = OptionContract(
            ticker="TEST",
            option_type=OptionType.CALL,
            strike=Decimal("1.05"),
            expiration=date(2025, 12, 19),
            bid=Decimal("0.10"),
            ask=Decimal("0.15"),
            last=Decimal("0.12"),
            volume=100,
            open_interest=500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.25,
        )
        json_str = contract.model_dump_json()
        parsed = json.loads(json_str)
        # strike should be a string "1.05", not a float
        assert isinstance(parsed["strike"], str)
        assert parsed["strike"] == "1.05"


# ---------------------------------------------------------------------------
# StrEnum Serialization Tests
# ---------------------------------------------------------------------------


class TestStrEnumSerialization:
    """Verify StrEnum values serialize to lowercase strings in JSON."""

    def test_option_type_serializes_as_lowercase(self) -> None:
        """OptionType.CALL serializes as "call" in model_dump_json()."""
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            last=Decimal("5.30"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
        )
        json_str = contract.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["option_type"] == "call"

    def test_exercise_style_serializes_as_lowercase(self) -> None:
        """ExerciseStyle.AMERICAN serializes as "american" in JSON."""
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            last=Decimal("5.30"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
        )
        json_str = contract.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["exercise_style"] == "american"

    def test_pricing_model_serializes_as_lowercase(self) -> None:
        """PricingModel.BAW serializes as "baw" in JSON."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BAW,
        )
        json_str = greeks.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["pricing_model"] == "baw"


# ---------------------------------------------------------------------------
# Computed Fields in model_dump() Tests
# ---------------------------------------------------------------------------


class TestComputedFieldsSerialization:
    """Verify computed fields appear in model_dump() and model_dump_json()."""

    def test_mid_in_model_dump(self) -> None:
        """Computed field 'mid' appears in model_dump() output."""
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("5.00"),
            ask=Decimal("5.50"),
            last=Decimal("5.25"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
        )
        dump = contract.model_dump()
        assert "mid" in dump

    def test_spread_in_model_dump(self) -> None:
        """Computed field 'spread' appears in model_dump() output."""
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("5.00"),
            ask=Decimal("5.50"),
            last=Decimal("5.25"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
        )
        dump = contract.model_dump()
        assert "spread" in dump
        assert dump["spread"] == Decimal("0.50")

    def test_dte_in_model_dump(self) -> None:
        """Computed field 'dte' appears in model_dump() output."""
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("5.00"),
            ask=Decimal("5.50"),
            last=Decimal("5.25"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
        )
        dump = contract.model_dump()
        assert "dte" in dump
        assert isinstance(dump["dte"], int)


# ---------------------------------------------------------------------------
# Nested Model Serialization Tests
# ---------------------------------------------------------------------------


class TestNestedModelSerialization:
    """Verify nested models serialize and deserialize correctly."""

    def test_option_contract_with_greeks_roundtrip(self) -> None:
        """OptionContract with greeks=OptionGreeks(...) serializes/deserializes."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BAW,
        )
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            last=Decimal("5.30"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
            greeks=greeks,
        )
        json_str = contract.model_dump_json()
        restored = OptionContract.model_validate_json(json_str)
        assert restored.greeks is not None
        assert restored.greeks.delta == pytest.approx(0.45)
        assert restored.greeks.gamma == pytest.approx(0.03)
        assert restored.greeks.theta == pytest.approx(-0.08)
        assert restored.greeks.vega == pytest.approx(0.15)
        assert restored.greeks.rho == pytest.approx(0.02)
        assert restored.greeks.pricing_model == PricingModel.BAW

    def test_nested_greeks_in_model_dump(self) -> None:
        """Nested OptionGreeks appears as a dict in model_dump() output."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BAW,
        )
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            last=Decimal("5.30"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
            greeks=greeks,
        )
        dump = contract.model_dump()
        assert dump["greeks"] is not None
        assert dump["greeks"]["delta"] == pytest.approx(0.45)
        assert dump["greeks"]["pricing_model"] == PricingModel.BAW
