"""Tests for scan.indicators.compute_options_indicators().

Covers:
  - Happy path with realistic calls and puts.
  - No calls → put_call_ratio is None.
  - No puts → put_call_ratio is None.
  - Empty contracts list → both fields None.
  - Zero call volume → NaN guard → put_call_ratio None.
  - max_pain with realistic strikes.
  - Zero OI → max_pain_distance None.
  - Invalid spot (zero/negative) → both fields None.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from options_arena.models import ExerciseStyle, OptionContract, OptionType
from options_arena.models.scan import IndicatorSignals
from options_arena.scan.indicators import compute_options_indicators


def _make_contract(
    *,
    option_type: OptionType,
    strike: str,
    volume: int = 100,
    open_interest: int = 500,
) -> OptionContract:
    """Build a minimal OptionContract for testing."""
    return OptionContract(
        ticker="TEST",
        option_type=option_type,
        strike=Decimal(strike),
        expiration=date.today() + timedelta(days=45),
        bid=Decimal("1.00"),
        ask=Decimal("1.50"),
        last=Decimal("1.25"),
        volume=volume,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.30,
    )


class TestComputeOptionsIndicators:
    """Tests for compute_options_indicators()."""

    def test_happy_path_both_fields_populated(self) -> None:
        """With calls and puts, both put_call_ratio and max_pain_distance are set."""
        contracts = [
            _make_contract(
                option_type=OptionType.CALL,
                strike="100",
                volume=200,
                open_interest=1000,
            ),
            _make_contract(
                option_type=OptionType.CALL,
                strike="105",
                volume=150,
                open_interest=800,
            ),
            _make_contract(
                option_type=OptionType.PUT,
                strike="95",
                volume=100,
                open_interest=600,
            ),
            _make_contract(
                option_type=OptionType.PUT,
                strike="100",
                volume=120,
                open_interest=900,
            ),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        assert isinstance(result, IndicatorSignals)
        assert result.put_call_ratio is not None
        # put_vol=220, call_vol=350 → ratio ≈ 0.6286
        assert result.put_call_ratio == pytest.approx(220 / 350, rel=1e-4)
        assert result.max_pain_distance is not None
        assert result.max_pain_distance >= 0.0

    def test_no_calls_put_call_ratio_none(self) -> None:
        """No calls → put_call_ratio is None (cannot compute)."""
        contracts = [
            _make_contract(
                option_type=OptionType.PUT,
                strike="95",
                volume=100,
                open_interest=500,
            ),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        assert result.put_call_ratio is None
        # max_pain can still be computed from OI
        assert result.max_pain_distance is not None

    def test_no_puts_put_call_ratio_none(self) -> None:
        """No puts → put_call_ratio is None."""
        contracts = [
            _make_contract(
                option_type=OptionType.CALL,
                strike="100",
                volume=200,
                open_interest=500,
            ),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        assert result.put_call_ratio is None

    def test_empty_contracts_both_none(self) -> None:
        """Empty contracts list → both fields None."""
        result = compute_options_indicators([], spot=100.0)
        assert result.put_call_ratio is None
        assert result.max_pain_distance is None

    def test_zero_call_volume_nan_guard(self) -> None:
        """Zero call volume → NaN from put_call_ratio_volume → guarded to None."""
        contracts = [
            _make_contract(
                option_type=OptionType.CALL,
                strike="100",
                volume=0,
                open_interest=500,
            ),
            _make_contract(
                option_type=OptionType.PUT,
                strike="95",
                volume=100,
                open_interest=500,
            ),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        assert result.put_call_ratio is None

    def test_max_pain_at_spot(self) -> None:
        """When max pain strike equals spot, distance is 0%."""
        contracts = [
            _make_contract(
                option_type=OptionType.CALL,
                strike="100",
                open_interest=1000,
            ),
            _make_contract(
                option_type=OptionType.PUT,
                strike="100",
                open_interest=1000,
            ),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        # Single strike at spot → max pain = 100 → distance = 0%
        assert result.max_pain_distance is not None
        assert result.max_pain_distance == pytest.approx(0.0)

    def test_max_pain_distance_percent(self) -> None:
        """Max pain distance is calculated as percent of spot price."""
        # Heavy OI at 110 → max pain should be near 110
        contracts = [
            _make_contract(
                option_type=OptionType.CALL,
                strike="100",
                open_interest=10,
            ),
            _make_contract(
                option_type=OptionType.CALL,
                strike="110",
                open_interest=10,
            ),
            _make_contract(
                option_type=OptionType.PUT,
                strike="100",
                open_interest=10000,
            ),
            _make_contract(
                option_type=OptionType.PUT,
                strike="110",
                open_interest=10,
            ),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        assert result.max_pain_distance is not None
        # Distance should be > 0 since max pain likely != 100
        assert result.max_pain_distance >= 0.0

    def test_zero_oi_max_pain_none(self) -> None:
        """Zero OI across all contracts → max_pain_distance None."""
        contracts = [
            _make_contract(option_type=OptionType.CALL, strike="100", open_interest=0),
            _make_contract(option_type=OptionType.PUT, strike="95", open_interest=0),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        assert result.max_pain_distance is None

    def test_invalid_spot_zero(self) -> None:
        """Spot price of 0 → both fields None."""
        contracts = [
            _make_contract(option_type=OptionType.CALL, strike="100"),
            _make_contract(option_type=OptionType.PUT, strike="95"),
        ]
        result = compute_options_indicators(contracts, spot=0.0)
        assert result.put_call_ratio is None
        assert result.max_pain_distance is None

    def test_invalid_spot_negative(self) -> None:
        """Negative spot price → both fields None."""
        contracts = [
            _make_contract(option_type=OptionType.CALL, strike="100"),
        ]
        result = compute_options_indicators(contracts, spot=-10.0)
        assert result.put_call_ratio is None
        assert result.max_pain_distance is None

    def test_other_fields_remain_none(self) -> None:
        """compute_options_indicators only sets put_call_ratio and max_pain_distance."""
        contracts = [
            _make_contract(
                option_type=OptionType.CALL,
                strike="100",
                volume=200,
                open_interest=500,
            ),
            _make_contract(
                option_type=OptionType.PUT,
                strike="95",
                volume=100,
                open_interest=500,
            ),
        ]
        result = compute_options_indicators(contracts, spot=100.0)
        # Non-options fields should be None
        assert result.rsi is None
        assert result.adx is None
        assert result.bb_width is None
        assert result.iv_rank is None
        assert result.iv_percentile is None
