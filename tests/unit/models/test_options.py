"""Unit tests for options models: OptionGreeks, OptionContract, SpreadLeg, OptionSpread.

Tests cover:
- Happy path construction with all fields
- Frozen enforcement (attribute reassignment raises ValidationError)
- Field validation (delta range, gamma/vega non-negative)
- Computed fields (mid, spread, dte)
- Decimal precision through JSON roundtrip
- Default values (greeks defaults to None)
- Spread construction (SpreadLeg, OptionSpread)
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from options_arena.models import (
    ExerciseStyle,
    OptionContract,
    OptionGreeks,
    OptionSpread,
    OptionType,
    PositionSide,
    PricingModel,
    SpreadLeg,
    SpreadType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_greeks() -> OptionGreeks:
    """Create a valid OptionGreeks instance for reuse."""
    return OptionGreeks(
        delta=0.45,
        gamma=0.03,
        theta=-0.08,
        vega=0.15,
        rho=0.02,
        pricing_model=PricingModel.BAW,
    )


@pytest.fixture
def sample_contract() -> OptionContract:
    """Create a valid OptionContract instance for reuse."""
    return OptionContract(
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


@pytest.fixture
def sample_contract_with_greeks(
    sample_contract: OptionContract, sample_greeks: OptionGreeks
) -> OptionContract:
    """Create a valid OptionContract with greeks populated."""
    return OptionContract(
        ticker=sample_contract.ticker,
        option_type=sample_contract.option_type,
        strike=sample_contract.strike,
        expiration=sample_contract.expiration,
        bid=sample_contract.bid,
        ask=sample_contract.ask,
        last=sample_contract.last,
        volume=sample_contract.volume,
        open_interest=sample_contract.open_interest,
        exercise_style=sample_contract.exercise_style,
        market_iv=sample_contract.market_iv,
        greeks=sample_greeks,
    )


# ---------------------------------------------------------------------------
# OptionGreeks Tests
# ---------------------------------------------------------------------------


class TestOptionGreeks:
    """Tests for the OptionGreeks model."""

    def test_happy_path_construction(self, sample_greeks: OptionGreeks) -> None:
        """OptionGreeks constructs with all fields correctly assigned."""
        assert sample_greeks.delta == pytest.approx(0.45)
        assert sample_greeks.gamma == pytest.approx(0.03)
        assert sample_greeks.theta == pytest.approx(-0.08)
        assert sample_greeks.vega == pytest.approx(0.15)
        assert sample_greeks.rho == pytest.approx(0.02)

    def test_pricing_model_field_present(self, sample_greeks: OptionGreeks) -> None:
        """OptionGreeks has pricing_model field tracking which model produced values."""
        assert sample_greeks.pricing_model == PricingModel.BAW

    def test_pricing_model_bsm(self) -> None:
        """OptionGreeks accepts PricingModel.BSM."""
        greeks = OptionGreeks(
            delta=0.55,
            gamma=0.02,
            theta=-0.05,
            vega=0.12,
            rho=0.01,
            pricing_model=PricingModel.BSM,
        )
        assert greeks.pricing_model == PricingModel.BSM

    def test_delta_too_high_raises(self) -> None:
        """OptionGreeks rejects delta > 1.0 with ValidationError."""
        with pytest.raises(ValidationError, match="delta"):
            OptionGreeks(
                delta=1.5,
                gamma=0.03,
                theta=-0.08,
                vega=0.15,
                rho=0.02,
                pricing_model=PricingModel.BAW,
            )

    def test_delta_too_low_raises(self) -> None:
        """OptionGreeks rejects delta < -1.0 with ValidationError."""
        with pytest.raises(ValidationError, match="delta"):
            OptionGreeks(
                delta=-1.5,
                gamma=0.03,
                theta=-0.08,
                vega=0.15,
                rho=0.02,
                pricing_model=PricingModel.BAW,
            )

    def test_delta_boundary_positive(self) -> None:
        """OptionGreeks accepts delta = 1.0 (boundary)."""
        greeks = OptionGreeks(
            delta=1.0,
            gamma=0.0,
            theta=-0.01,
            vega=0.01,
            rho=0.0,
            pricing_model=PricingModel.BSM,
        )
        assert greeks.delta == pytest.approx(1.0)

    def test_delta_boundary_negative(self) -> None:
        """OptionGreeks accepts delta = -1.0 (boundary)."""
        greeks = OptionGreeks(
            delta=-1.0,
            gamma=0.0,
            theta=-0.01,
            vega=0.01,
            rho=0.0,
            pricing_model=PricingModel.BSM,
        )
        assert greeks.delta == pytest.approx(-1.0)

    def test_negative_gamma_raises(self) -> None:
        """OptionGreeks rejects negative gamma with ValidationError."""
        with pytest.raises(ValidationError, match="must be >= 0"):
            OptionGreeks(
                delta=0.45,
                gamma=-0.1,
                theta=-0.08,
                vega=0.15,
                rho=0.02,
                pricing_model=PricingModel.BAW,
            )

    def test_negative_vega_raises(self) -> None:
        """OptionGreeks rejects negative vega with ValidationError."""
        with pytest.raises(ValidationError, match="must be >= 0"):
            OptionGreeks(
                delta=0.45,
                gamma=0.03,
                theta=-0.08,
                vega=-0.1,
                rho=0.02,
                pricing_model=PricingModel.BAW,
            )

    def test_negative_theta_allowed(self) -> None:
        """OptionGreeks allows negative theta (time decay costs money)."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.50,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BAW,
        )
        assert greeks.theta == pytest.approx(-0.50)

    def test_frozen_enforcement(self, sample_greeks: OptionGreeks) -> None:
        """OptionGreeks is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_greeks.delta = 0.99  # type: ignore[misc]

    def test_json_roundtrip(self, sample_greeks: OptionGreeks) -> None:
        """OptionGreeks survives JSON serialization/deserialization unchanged."""
        json_str = sample_greeks.model_dump_json()
        restored = OptionGreeks.model_validate_json(json_str)
        assert restored == sample_greeks


# ---------------------------------------------------------------------------
# OptionContract Tests
# ---------------------------------------------------------------------------


class TestOptionContract:
    """Tests for the OptionContract model."""

    def test_happy_path_construction(self, sample_contract: OptionContract) -> None:
        """OptionContract constructs with all fields correctly assigned."""
        assert sample_contract.ticker == "AAPL"
        assert sample_contract.option_type == OptionType.CALL
        assert sample_contract.strike == Decimal("185.00")
        assert sample_contract.expiration == date(2025, 9, 19)
        assert sample_contract.bid == Decimal("5.20")
        assert sample_contract.ask == Decimal("5.40")
        assert sample_contract.last == Decimal("5.30")
        assert sample_contract.volume == 1500
        assert sample_contract.open_interest == 8500
        assert sample_contract.exercise_style == ExerciseStyle.AMERICAN
        assert sample_contract.market_iv == pytest.approx(0.32)

    def test_frozen_enforcement(self, sample_contract: OptionContract) -> None:
        """OptionContract is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_contract.strike = Decimal("190.00")  # type: ignore[misc]

    def test_mid_computed_field(self) -> None:
        """OptionContract mid computed field = (bid + ask) / Decimal("2")."""
        contract = OptionContract(
            ticker="SPY",
            option_type=OptionType.PUT,
            strike=Decimal("450.00"),
            expiration=date(2025, 12, 19),
            bid=Decimal("3.00"),
            ask=Decimal("3.50"),
            last=Decimal("3.25"),
            volume=500,
            open_interest=2000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.18,
        )
        expected_mid = (Decimal("3.00") + Decimal("3.50")) / Decimal("2")
        assert contract.mid == expected_mid
        assert contract.mid == Decimal("3.25")

    def test_spread_computed_field(self) -> None:
        """OptionContract spread computed field = ask - bid."""
        contract = OptionContract(
            ticker="SPY",
            option_type=OptionType.PUT,
            strike=Decimal("450.00"),
            expiration=date(2025, 12, 19),
            bid=Decimal("3.00"),
            ask=Decimal("3.50"),
            last=Decimal("3.25"),
            volume=500,
            open_interest=2000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.18,
        )
        assert contract.spread == Decimal("0.50")

    def test_dte_computed_field(self) -> None:
        """OptionContract dte computed field returns correct days to expiration.

        Mock date.today() to avoid test fragility from real calendar dates.
        """
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2025, 7, 18),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            last=Decimal("5.30"),
            volume=1500,
            open_interest=8500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.32,
        )
        # Mock date.today() in the options module where it is called
        mock_today = date(2025, 6, 15)
        with patch("options_arena.models.options.date") as mock_date:
            mock_date.today.return_value = mock_today
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            expected_dte = (date(2025, 7, 18) - mock_today).days
            assert contract.dte == expected_dte
            assert contract.dte == 33

    def test_negative_market_iv_raises(self) -> None:
        """OptionContract rejects negative market_iv with ValidationError."""
        with pytest.raises(ValidationError, match="market_iv"):
            OptionContract(
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
                market_iv=-0.1,
            )

    def test_zero_market_iv_allowed(self) -> None:
        """OptionContract accepts market_iv = 0.0 (boundary)."""
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
            market_iv=0.0,
        )
        assert contract.market_iv == pytest.approx(0.0)

    def test_greeks_defaults_to_none(self, sample_contract: OptionContract) -> None:
        """OptionContract greeks defaults to None when not provided."""
        assert sample_contract.greeks is None

    def test_greeks_populated(self, sample_contract_with_greeks: OptionContract) -> None:
        """OptionContract greeks field accepts an OptionGreeks instance."""
        assert sample_contract_with_greeks.greeks is not None
        assert sample_contract_with_greeks.greeks.delta == pytest.approx(0.45)
        assert sample_contract_with_greeks.greeks.pricing_model == PricingModel.BAW

    def test_decimal_roundtrip_via_json(self) -> None:
        """Decimal("1.05") survives JSON roundtrip as string, not float."""
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
        # Verify the JSON contains "1.05" as a string, not a float representation
        assert '"1.05"' in json_str
        restored = OptionContract.model_validate_json(json_str)
        assert restored.strike == Decimal("1.05")

    def test_json_roundtrip(self, sample_contract: OptionContract) -> None:
        """OptionContract survives JSON serialization/deserialization unchanged."""
        json_str = sample_contract.model_dump_json()
        restored = OptionContract.model_validate_json(json_str)
        assert restored.ticker == sample_contract.ticker
        assert restored.strike == sample_contract.strike
        assert restored.bid == sample_contract.bid
        assert restored.ask == sample_contract.ask
        assert restored.last == sample_contract.last

    def test_json_roundtrip_with_greeks(self, sample_contract_with_greeks: OptionContract) -> None:
        """OptionContract with greeks survives JSON roundtrip."""
        json_str = sample_contract_with_greeks.model_dump_json()
        restored = OptionContract.model_validate_json(json_str)
        assert restored.greeks is not None
        assert restored.greeks.delta == pytest.approx(
            sample_contract_with_greeks.greeks.delta  # type: ignore[union-attr]
        )


# ---------------------------------------------------------------------------
# SpreadLeg Tests
# ---------------------------------------------------------------------------


class TestSpreadLeg:
    """Tests for the SpreadLeg model."""

    def test_basic_construction(self, sample_contract: OptionContract) -> None:
        """SpreadLeg constructs with an OptionContract and PositionSide."""
        leg = SpreadLeg(
            contract=sample_contract,
            side=PositionSide.LONG,
        )
        assert leg.contract == sample_contract
        assert leg.side == PositionSide.LONG
        assert leg.quantity == 1  # default

    def test_quantity_override(self, sample_contract: OptionContract) -> None:
        """SpreadLeg accepts a custom quantity."""
        leg = SpreadLeg(
            contract=sample_contract,
            side=PositionSide.SHORT,
            quantity=5,
        )
        assert leg.quantity == 5
        assert leg.side == PositionSide.SHORT

    def test_zero_quantity_raises(self, sample_contract: OptionContract) -> None:
        """SpreadLeg rejects quantity = 0 with ValidationError."""
        with pytest.raises(ValidationError, match="quantity"):
            SpreadLeg(
                contract=sample_contract,
                side=PositionSide.LONG,
                quantity=0,
            )

    def test_negative_quantity_raises(self, sample_contract: OptionContract) -> None:
        """SpreadLeg rejects negative quantity with ValidationError."""
        with pytest.raises(ValidationError, match="quantity"):
            SpreadLeg(
                contract=sample_contract,
                side=PositionSide.LONG,
                quantity=-1,
            )


# ---------------------------------------------------------------------------
# OptionSpread Tests
# ---------------------------------------------------------------------------


class TestOptionSpread:
    """Tests for the OptionSpread model."""

    def test_empty_legs_raises(self) -> None:
        """OptionSpread rejects an empty legs list with ValidationError."""
        with pytest.raises(ValidationError, match="legs"):
            OptionSpread(
                spread_type=SpreadType.VERTICAL,
                legs=[],
                ticker="AAPL",
            )

    def test_basic_construction(self, sample_contract: OptionContract) -> None:
        """OptionSpread constructs with SpreadType and a list of legs."""
        long_leg = SpreadLeg(contract=sample_contract, side=PositionSide.LONG)
        # Create a second contract for the short leg
        short_contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("190.00"),
            expiration=date(2025, 9, 19),
            bid=Decimal("3.00"),
            ask=Decimal("3.20"),
            last=Decimal("3.10"),
            volume=800,
            open_interest=4000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.30,
        )
        short_leg = SpreadLeg(contract=short_contract, side=PositionSide.SHORT)
        spread = OptionSpread(
            spread_type=SpreadType.VERTICAL,
            legs=[long_leg, short_leg],
            ticker="AAPL",
        )
        assert spread.spread_type == SpreadType.VERTICAL
        assert len(spread.legs) == 2
        assert spread.ticker == "AAPL"
        assert spread.legs[0].side == PositionSide.LONG
        assert spread.legs[1].side == PositionSide.SHORT
