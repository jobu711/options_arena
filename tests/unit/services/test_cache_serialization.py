"""Tests for cache serialization helpers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.services.helpers import (
    cache_bytes_to_contracts,
    contracts_to_cache_bytes,
)
from tests.factories import make_option_contract


class TestContractsCacheRoundTrip:
    """Round-trip serialization via contracts_to_cache_bytes / cache_bytes_to_contracts."""

    def test_single_contract_round_trip(self) -> None:
        """A single contract survives serialize -> deserialize."""
        original = make_option_contract()
        data = contracts_to_cache_bytes([original])
        restored = cache_bytes_to_contracts(data)

        assert len(restored) == 1
        assert restored[0] == original

    def test_multiple_contracts_round_trip(self) -> None:
        """Multiple contracts with different parameters survive round-trip."""
        contracts = [
            make_option_contract(ticker="AAPL", strike=Decimal("150.00")),
            make_option_contract(
                ticker="MSFT",
                option_type=OptionType.PUT,
                strike=Decimal("400.00"),
                bid=Decimal("12.30"),
                ask=Decimal("12.80"),
            ),
            make_option_contract(
                ticker="GOOG",
                strike=Decimal("175.50"),
                volume=0,
                open_interest=10,
            ),
        ]
        data = contracts_to_cache_bytes(contracts)
        restored = cache_bytes_to_contracts(data)

        assert len(restored) == len(contracts)
        for orig, rest in zip(contracts, restored, strict=True):
            assert rest == orig

    def test_empty_list_round_trip(self) -> None:
        """An empty list serializes and deserializes to an empty list."""
        data = contracts_to_cache_bytes([])
        restored = cache_bytes_to_contracts(data)

        assert restored == []

    def test_return_type_bytes(self) -> None:
        """contracts_to_cache_bytes returns bytes."""
        result = contracts_to_cache_bytes([make_option_contract()])
        assert isinstance(result, bytes)

    def test_return_type_list_of_contracts(self) -> None:
        """cache_bytes_to_contracts returns list[OptionContract]."""
        data = contracts_to_cache_bytes([make_option_contract()])
        result = cache_bytes_to_contracts(data)

        assert isinstance(result, list)
        assert all(isinstance(c, OptionContract) for c in result)

    def test_decimal_precision_survives_round_trip(self) -> None:
        """Decimal fields retain exact precision through serialization."""
        contract = make_option_contract(
            strike=Decimal("185.50"),
            bid=Decimal("3.15"),
            ask=Decimal("3.45"),
            last=Decimal("3.30"),
        )
        data = contracts_to_cache_bytes([contract])
        restored = cache_bytes_to_contracts(data)

        assert restored[0].strike == Decimal("185.50")
        assert restored[0].bid == Decimal("3.15")
        assert restored[0].ask == Decimal("3.45")
        assert restored[0].last == Decimal("3.30")

    def test_greeks_none_round_trip(self) -> None:
        """Contracts with greeks=None round-trip correctly."""
        contract = make_option_contract()
        assert contract.greeks is None  # factory default

        data = contracts_to_cache_bytes([contract])
        restored = cache_bytes_to_contracts(data)

        assert restored[0].greeks is None
        assert restored[0] == contract

    def test_greeks_populated_round_trip(self) -> None:
        """Contracts with populated Greeks survive round-trip."""
        from options_arena.models.enums import PricingModel

        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.05,
            vega=0.12,
            rho=0.01,
            pricing_model=PricingModel.BAW,
        )
        contract = make_option_contract(greeks=greeks)

        data = contracts_to_cache_bytes([contract])
        restored = cache_bytes_to_contracts(data)

        assert restored[0].greeks is not None
        assert restored[0].greeks.delta == pytest.approx(0.45, rel=1e-4)
        assert restored[0].greeks.gamma == pytest.approx(0.03, rel=1e-4)
        assert restored[0].greeks.theta == pytest.approx(-0.05, rel=1e-4)
        assert restored[0].greeks.vega == pytest.approx(0.12, rel=1e-4)
        assert restored[0].greeks.rho == pytest.approx(0.01, rel=1e-4)

    def test_exercise_style_survives_round_trip(self) -> None:
        """ExerciseStyle enum survives serialization."""
        contract = make_option_contract(exercise_style=ExerciseStyle.AMERICAN)
        data = contracts_to_cache_bytes([contract])
        restored = cache_bytes_to_contracts(data)

        assert restored[0].exercise_style == ExerciseStyle.AMERICAN

    def test_option_type_survives_round_trip(self) -> None:
        """OptionType enum survives serialization for both calls and puts."""
        call = make_option_contract(option_type=OptionType.CALL)
        put = make_option_contract(option_type=OptionType.PUT)

        data = contracts_to_cache_bytes([call, put])
        restored = cache_bytes_to_contracts(data)

        assert restored[0].option_type == OptionType.CALL
        assert restored[1].option_type == OptionType.PUT
