"""Tests for IV smoothing integration in compute_greeks().

Verifies that ``compute_greeks()`` correctly groups contracts by
(strike, expiration), applies ``smooth_iv_parity()`` when both call
and put exist, persists the smoothed IV on the output contract, and
sets ``greeks_source`` appropriately.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    OptionType,
    PricingModel,
)
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.scoring.contracts import compute_greeks
from tests.factories import make_option_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPIRY = datetime.now(UTC).date() + timedelta(days=45)
_SPOT = 150.0
_RATE = 0.05
_DIV = 0.005

_FAKE_GREEKS = OptionGreeks(
    delta=0.35,
    gamma=0.05,
    theta=-0.05,
    vega=0.10,
    rho=0.01,
    pricing_model=PricingModel.BAW,
)


def _make_call(
    strike: str = "150.00",
    market_iv: float = 0.30,
    bid: str = "5.00",
    ask: str = "5.50",
) -> OptionContract:
    """Create a call contract with configurable strike/IV/prices."""
    return make_option_contract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal(strike),
        expiration=_EXPIRY,
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal("5.25"),
        volume=100,
        open_interest=500,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=market_iv,
    )


def _make_put(
    strike: str = "150.00",
    market_iv: float = 0.32,
    bid: str = "4.50",
    ask: str = "5.00",
) -> OptionContract:
    """Create a put contract with configurable strike/IV/prices."""
    return make_option_contract(
        ticker="AAPL",
        option_type=OptionType.PUT,
        strike=Decimal(strike),
        expiration=_EXPIRY,
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal("4.75"),
        volume=80,
        open_interest=400,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=market_iv,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSmoothingIntegration:
    """Tests for IV smoothing integration in compute_greeks()."""

    @pytest.mark.critical
    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_pair_smoothed(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """Call+put at same strike -> smoothed IV used for both."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        call = _make_call(market_iv=0.30)
        put = _make_put(market_iv=0.32)

        result = compute_greeks([call, put], _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        assert len(result) == 2
        # Both should have smoothed_iv populated (a value between 0.30 and 0.32)
        for c in result:
            assert c.smoothed_iv is not None
            assert math.isfinite(c.smoothed_iv)
            assert 0.29 < c.smoothed_iv < 0.33

    @pytest.mark.critical
    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_single_side_no_smoothing(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """Only call present (no put at same strike) -> raw IV, COMPUTED source."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        call = _make_call(market_iv=0.30)

        result = compute_greeks([call], _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        assert len(result) == 1
        assert result[0].smoothed_iv is None
        assert result[0].greeks_source == GreeksSource.COMPUTED

    @pytest.mark.critical
    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_smoothing_disabled(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """use_parity_smoothing=False -> all contracts use raw IV."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        call = _make_call(market_iv=0.30)
        put = _make_put(market_iv=0.32)

        result = compute_greeks([call, put], _SPOT, _RATE, _DIV, use_parity_smoothing=False)

        assert len(result) == 2
        for c in result:
            assert c.smoothed_iv is None
            assert c.greeks_source == GreeksSource.COMPUTED

    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_tier1_unaffected(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """Contracts with pre-existing Greeks (Tier 1) -> preserved, no smoothing applied."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        # Create a contract that already has Greeks (Tier 1)
        call_with_greeks = make_option_contract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("150.00"),
            expiration=_EXPIRY,
            bid=Decimal("5.00"),
            ask=Decimal("5.50"),
            last=Decimal("5.25"),
            volume=100,
            open_interest=500,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.30,
            greeks=_FAKE_GREEKS,
        )
        put = _make_put(market_iv=0.32)

        result = compute_greeks(
            [call_with_greeks, put], _SPOT, _RATE, _DIV, use_parity_smoothing=True
        )

        assert len(result) == 2
        # Tier 1 contract should be preserved with no smoothed_iv
        tier1_result = result[0]
        assert tier1_result.greeks is not None
        assert tier1_result.greeks.delta == pytest.approx(0.35)
        # Tier 1 gets MARKET source (since greeks_source was None initially)
        assert tier1_result.greeks_source == GreeksSource.MARKET

    @pytest.mark.critical
    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_smoothed_iv_persisted(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """smoothed_iv field is populated on output contract when smoothing applied."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        call = _make_call(market_iv=0.30)
        put = _make_put(market_iv=0.32)

        result = compute_greeks([call, put], _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        # Both should have smoothed_iv
        for c in result:
            assert c.smoothed_iv is not None
            assert c.smoothed_iv > 0
            assert math.isfinite(c.smoothed_iv)

    @pytest.mark.critical
    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_greeks_source_smoothed(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """greeks_source=SMOOTHED when smoothing is applied successfully."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        call = _make_call(market_iv=0.30)
        put = _make_put(market_iv=0.32)

        result = compute_greeks([call, put], _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        assert len(result) == 2
        for c in result:
            assert c.greeks_source == GreeksSource.SMOOTHED

    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_greeks_source_computed_no_pair(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """greeks_source=COMPUTED when no pair exists at same strike/expiration."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        # Call at 150, put at 155 — different strikes, no pair
        call = _make_call(strike="150.00", market_iv=0.30)
        put = _make_put(strike="155.00", market_iv=0.32)

        result = compute_greeks([call, put], _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        assert len(result) == 2
        for c in result:
            assert c.greeks_source == GreeksSource.COMPUTED
            assert c.smoothed_iv is None

    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_invalid_other_iv_no_smoothing(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """Other side has IV=0 -> no smoothing applied, greeks_source=COMPUTED."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        call = _make_call(market_iv=0.30)
        # Put with IV=0 (invalid — smooth_iv_parity requires positive IV)
        put = _make_put(market_iv=0.0)

        result = compute_greeks([call, put], _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        # Call should not be smoothed since the put's IV is invalid
        call_result = [c for c in result if c.option_type == OptionType.CALL]
        assert len(call_result) == 1
        assert call_result[0].smoothed_iv is None
        assert call_result[0].greeks_source == GreeksSource.COMPUTED

    @pytest.mark.critical
    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_contract_count_unchanged(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """Output count matches input Tier 2 count (smoothing doesn't drop contracts)."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        contracts = [
            _make_call(strike="145.00", market_iv=0.28),
            _make_put(strike="145.00", market_iv=0.30),
            _make_call(strike="150.00", market_iv=0.30),
            _make_put(strike="150.00", market_iv=0.32),
            _make_call(strike="155.00", market_iv=0.35),  # no put pair
        ]

        result = compute_greeks(contracts, _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        assert len(result) == 5

    @patch("options_arena.scoring.contracts.option_second_order_greeks")
    @patch("options_arena.scoring.contracts.option_greeks")
    def test_smoothed_iv_value_between_call_and_put(
        self,
        mock_greeks: object,
        mock_second: object,
    ) -> None:
        """Smoothed IV should be between (or equal to) the call and put IVs."""
        mock_greeks.return_value = _FAKE_GREEKS  # type: ignore[union-attr]
        mock_second.side_effect = ValueError("skip second order")  # type: ignore[union-attr]

        call = _make_call(market_iv=0.25, bid="5.00", ask="5.50")
        put = _make_put(market_iv=0.35, bid="4.00", ask="4.50")

        result = compute_greeks([call, put], _SPOT, _RATE, _DIV, use_parity_smoothing=True)

        assert len(result) == 2
        for c in result:
            assert c.smoothed_iv is not None
            # Smoothed IV should be between the min and max of the two raw IVs
            assert c.smoothed_iv >= 0.25 - 1e-9
            assert c.smoothed_iv <= 0.35 + 1e-9
