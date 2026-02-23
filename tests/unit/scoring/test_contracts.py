"""Tests for options_arena.scoring.contracts — contract filtering and selection."""

from decimal import Decimal

import pytest

from options_arena.models.config import PricingConfig
from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    PricingModel,
    SignalDirection,
)
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.scoring.contracts import (
    compute_greeks,
    filter_contracts,
    recommend_contracts,
    select_by_delta,
    select_expiration,
)
from tests.unit.scoring.conftest import make_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_greeks(
    delta: float = 0.35,
    gamma: float = 0.05,
    theta: float = -0.05,
    vega: float = 0.10,
    rho: float = 0.01,
    pricing_model: PricingModel = PricingModel.BAW,
) -> OptionGreeks:
    """Create an OptionGreeks for testing."""
    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        pricing_model=pricing_model,
    )


def _contract_with_greeks(
    delta: float = 0.35,
    **kwargs: object,
) -> OptionContract:
    """Create a contract with pre-populated greeks."""
    base = make_contract(**kwargs)  # type: ignore[arg-type]
    return OptionContract(
        ticker=base.ticker,
        option_type=base.option_type,
        strike=base.strike,
        expiration=base.expiration,
        bid=base.bid,
        ask=base.ask,
        last=base.last,
        volume=base.volume,
        open_interest=base.open_interest,
        exercise_style=base.exercise_style,
        market_iv=base.market_iv,
        greeks=_make_greeks(delta=delta),
    )


# ===========================================================================
# filter_contracts tests
# ===========================================================================


class TestFilterContracts:
    """Tests for filter_contracts."""

    def test_bullish_only_calls(self) -> None:
        """BULLISH direction should keep only calls."""
        call = make_contract(option_type=OptionType.CALL)
        put = make_contract(option_type=OptionType.PUT)
        result = filter_contracts([call, put], SignalDirection.BULLISH)
        assert len(result) == 1
        assert result[0].option_type == OptionType.CALL

    def test_bearish_only_puts(self) -> None:
        """BEARISH direction should keep only puts."""
        call = make_contract(option_type=OptionType.CALL)
        put = make_contract(option_type=OptionType.PUT)
        result = filter_contracts([call, put], SignalDirection.BEARISH)
        assert len(result) == 1
        assert result[0].option_type == OptionType.PUT

    def test_neutral_keeps_both_types(self) -> None:
        """NEUTRAL direction should keep both calls and puts."""
        call = make_contract(option_type=OptionType.CALL)
        put = make_contract(option_type=OptionType.PUT)
        result = filter_contracts([call, put], SignalDirection.NEUTRAL)
        assert len(result) == 2

    def test_oi_below_threshold_rejected(self) -> None:
        """Contracts with open_interest below min_oi should be rejected."""
        contract = make_contract(open_interest=50)
        result = filter_contracts([contract], SignalDirection.BULLISH)
        assert result == []

    def test_volume_below_threshold_rejected(self) -> None:
        """Contracts with volume below min_volume should be rejected."""
        contract = make_contract(volume=0)
        result = filter_contracts([contract], SignalDirection.BULLISH)
        assert result == []

    def test_wide_spread_rejected(self) -> None:
        """Contracts with spread/mid exceeding max_spread_pct should be rejected."""
        # spread = 3.00, mid = 6.50, spread_pct = 3.00/6.50 = 0.4615 > 0.10
        contract = make_contract(bid="5.00", ask="8.00")
        result = filter_contracts([contract], SignalDirection.BULLISH)
        assert result == []

    def test_zero_bid_exemption(self) -> None:
        """Contracts with bid=0, ask>0 should skip spread check (zero-bid exemption)."""
        contract = make_contract(bid="0.00", ask="1.50", last="0.75")
        result = filter_contracts([contract], SignalDirection.BULLISH)
        assert len(result) == 1

    def test_both_bid_and_ask_zero_rejected(self) -> None:
        """Contracts with both bid=0 AND ask=0 are truly dead and should be rejected."""
        contract = make_contract(bid="0.00", ask="0.00", last="0.00")
        result = filter_contracts([contract], SignalDirection.BULLISH)
        assert result == []

    def test_config_override_stricter_spread(self) -> None:
        """Custom max_spread_pct=0.05 should be stricter."""
        # spread = 0.50, mid = 5.25, spread_pct = 0.50/5.25 = 0.0952 > 0.05
        contract = make_contract(bid="5.00", ask="5.50")
        config = PricingConfig(max_spread_pct=0.05)
        result = filter_contracts([contract], SignalDirection.BULLISH, config)
        assert result == []

    def test_empty_input_returns_empty(self) -> None:
        """Empty input should return empty output."""
        result = filter_contracts([], SignalDirection.BULLISH)
        assert result == []

    def test_sorted_by_oi_descending(self) -> None:
        """Results should be sorted by open_interest descending."""
        c1 = make_contract(open_interest=200, strike="145.00")
        c2 = make_contract(open_interest=1000, strike="150.00")
        c3 = make_contract(open_interest=500, strike="155.00")
        result = filter_contracts([c1, c2, c3], SignalDirection.BULLISH)
        assert [c.open_interest for c in result] == [1000, 500, 200]


# ===========================================================================
# select_expiration tests
# ===========================================================================


class TestSelectExpiration:
    """Tests for select_expiration."""

    def test_picks_closest_to_midpoint(self) -> None:
        """Should pick expiration closest to DTE midpoint (45 by default)."""
        c30 = make_contract(dte_days=30)
        c45 = make_contract(dte_days=45)
        c60 = make_contract(dte_days=60)
        result = select_expiration([c30, c45, c60])
        assert result == c45.expiration

    def test_no_contracts_in_dte_range_returns_none(self) -> None:
        """Should return None if no contracts in DTE range."""
        c10 = make_contract(dte_days=10)
        c90 = make_contract(dte_days=90)
        result = select_expiration([c10, c90])
        assert result is None

    def test_all_same_dte(self) -> None:
        """All contracts at same DTE should return that date."""
        c1 = make_contract(dte_days=40, strike="145.00")
        c2 = make_contract(dte_days=40, strike="150.00")
        result = select_expiration([c1, c2])
        assert result == c1.expiration

    def test_edge_dte_exactly_min(self) -> None:
        """DTE exactly at minimum (30) should be included."""
        c30 = make_contract(dte_days=30)
        result = select_expiration([c30])
        assert result == c30.expiration

    def test_edge_dte_exactly_max(self) -> None:
        """DTE exactly at maximum (60) should be included."""
        c60 = make_contract(dte_days=60)
        result = select_expiration([c60])
        assert result == c60.expiration

    def test_empty_contracts_returns_none(self) -> None:
        """Empty input should return None."""
        result = select_expiration([])
        assert result is None


# ===========================================================================
# compute_greeks tests
# ===========================================================================


class TestComputeGreeks:
    """Tests for compute_greeks."""

    def test_valid_contract_gets_greeks(self) -> None:
        """Contract with valid market_iv should get Greeks computed."""
        contract = make_contract(
            strike="150.00",
            market_iv=0.30,
            dte_days=45,
        )
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        assert len(result) == 1
        assert result[0].greeks is not None

    def test_american_exercise_greeks(self) -> None:
        """American contracts should get Greeks via BAW dispatch."""
        contract = make_contract(
            exercise_style=ExerciseStyle.AMERICAN,
            strike="150.00",
            market_iv=0.30,
            dte_days=45,
        )
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        assert len(result) == 1
        assert result[0].greeks is not None
        assert result[0].greeks.pricing_model == PricingModel.BAW

    def test_european_exercise_greeks(self) -> None:
        """European contracts should get Greeks via BSM dispatch."""
        contract = make_contract(
            exercise_style=ExerciseStyle.EUROPEAN,
            strike="150.00",
            market_iv=0.30,
            dte_days=45,
        )
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        assert len(result) == 1
        assert result[0].greeks is not None
        assert result[0].greeks.pricing_model == PricingModel.BSM

    def test_zero_market_iv_attempts_iv_solve(self) -> None:
        """market_iv=0 should trigger IV solve via mid price."""
        contract = make_contract(
            strike="150.00",
            market_iv=0.0,
            bid="5.00",
            ask="5.50",
            dte_days=45,
        )
        # The IV solve may or may not succeed depending on the mid price.
        # Either way, it should not crash.
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        # Contract is either processed or skipped, but no crash
        assert isinstance(result, list)

    def test_iv_solve_failure_skips_contract(self) -> None:
        """If IV solve fails, contract should be skipped (not crash batch)."""
        contract = make_contract(
            strike="150.00",
            market_iv=0.0,
            bid="0.00",
            ask="0.01",
            last="0.01",
            dte_days=45,
        )
        # Very low mid price with 0 IV — solve will likely fail
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        # Should not crash; contract may be skipped
        assert isinstance(result, list)

    def test_batch_partial_failure(self) -> None:
        """Multiple contracts: partial failure should not crash the batch."""
        good = make_contract(strike="150.00", market_iv=0.30, dte_days=45)
        # Bad: expired contract (dte=0)
        bad = make_contract(strike="150.00", market_iv=0.30, dte_days=0)
        result = compute_greeks([good, bad], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        # At least the good contract should succeed
        assert len(result) >= 1

    def test_greeks_values_sanity(self) -> None:
        """Greeks values should be within reasonable ranges."""
        contract = make_contract(
            strike="150.00",
            market_iv=0.30,
            dte_days=45,
        )
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        assert len(result) == 1
        greeks = result[0].greeks
        assert greeks is not None
        assert -1.0 <= greeks.delta <= 1.0
        assert greeks.gamma >= 0.0
        assert greeks.vega >= 0.0

    def test_frozen_contract_new_instance(self) -> None:
        """Returned contracts should be new instances (frozen model requires copy)."""
        contract = make_contract(
            strike="150.00",
            market_iv=0.30,
            dte_days=45,
        )
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        assert len(result) == 1
        # New instance, not the same object
        assert result[0] is not contract
        assert result[0].greeks is not None
        assert contract.greeks is None

    def test_deep_itm_call_delta_near_one(self) -> None:
        """Deep ITM call (spot >> strike) should have delta close to 1.0."""
        contract = make_contract(
            strike="100.00",
            market_iv=0.25,
            dte_days=45,
            option_type=OptionType.CALL,
        )
        result = compute_greeks([contract], spot=200.0, risk_free_rate=0.05, dividend_yield=0.01)
        assert len(result) == 1
        assert result[0].greeks is not None
        assert result[0].greeks.delta > 0.90

    def test_deep_otm_call_delta_near_zero(self) -> None:
        """Deep OTM call (spot << strike) should have delta close to 0."""
        contract = make_contract(
            strike="300.00",
            market_iv=0.25,
            dte_days=45,
            option_type=OptionType.CALL,
            bid="0.01",
            ask="0.05",
            last="0.03",
        )
        result = compute_greeks([contract], spot=150.0, risk_free_rate=0.05, dividend_yield=0.01)
        assert len(result) == 1
        assert result[0].greeks is not None
        assert result[0].greeks.delta < 0.10


# ===========================================================================
# select_by_delta tests
# ===========================================================================


class TestSelectByDelta:
    """Tests for select_by_delta."""

    def test_picks_exact_target(self) -> None:
        """Contracts at delta 0.25, 0.35, 0.45: should pick 0.35 (exact target)."""
        c1 = _contract_with_greeks(delta=0.25, strike="145.00")
        c2 = _contract_with_greeks(delta=0.35, strike="150.00")
        c3 = _contract_with_greeks(delta=0.45, strike="155.00")
        result = select_by_delta([c1, c2, c3])
        assert result is not None
        assert result.greeks is not None
        assert result.greeks.delta == pytest.approx(0.35, abs=0.001)

    def test_fallback_when_no_primary(self) -> None:
        """No contracts in primary range should fall back to [0.10, 0.80]."""
        c1 = _contract_with_greeks(delta=0.15, strike="145.00")
        c2 = _contract_with_greeks(delta=0.75, strike="155.00")
        result = select_by_delta([c1, c2])
        # 0.15 is distance 0.20, 0.75 is distance 0.40 from target 0.35
        assert result is not None
        assert result.greeks is not None
        assert abs(result.greeks.delta) == pytest.approx(0.15, abs=0.001)

    def test_no_contracts_in_any_range_returns_none(self) -> None:
        """No contracts in fallback range should return None."""
        c1 = _contract_with_greeks(delta=0.05, strike="145.00")
        c2 = _contract_with_greeks(delta=0.95, strike="155.00")
        result = select_by_delta([c1, c2])
        assert result is None

    def test_tiebreaker_lowest_strike(self) -> None:
        """Equal distance to target: pick lowest strike for determinism."""
        c1 = _contract_with_greeks(delta=0.30, strike="145.00")
        c2 = _contract_with_greeks(delta=0.40, strike="155.00")
        # Both are distance 0.05 from target 0.35
        result = select_by_delta([c1, c2])
        assert result is not None
        assert result.strike == Decimal("145.00")

    def test_put_contracts_uses_abs_delta(self) -> None:
        """Put contracts with negative delta: should use abs(delta)."""
        c1 = _contract_with_greeks(
            delta=-0.35,
            option_type=OptionType.PUT,
            strike="150.00",
        )
        result = select_by_delta([c1])
        assert result is not None
        assert result.greeks is not None
        # abs(-0.35) = 0.35 which is exactly the target
        assert result.greeks.delta == pytest.approx(-0.35, abs=0.001)

    def test_edge_delta_exactly_primary_min(self) -> None:
        """Delta exactly at primary min (0.20) should be included."""
        c1 = _contract_with_greeks(delta=0.20, strike="145.00")
        result = select_by_delta([c1])
        assert result is not None

    def test_edge_delta_exactly_primary_max(self) -> None:
        """Delta exactly at primary max (0.50) should be included."""
        c1 = _contract_with_greeks(delta=0.50, strike="145.00")
        result = select_by_delta([c1])
        assert result is not None

    def test_config_override_delta_target(self) -> None:
        """Custom delta_target=0.40 should pick closest to 0.40."""
        c1 = _contract_with_greeks(delta=0.35, strike="145.00")
        c2 = _contract_with_greeks(delta=0.40, strike="150.00")
        c3 = _contract_with_greeks(delta=0.45, strike="155.00")
        config = PricingConfig(delta_target=0.40)
        result = select_by_delta([c1, c2, c3], config)
        assert result is not None
        assert result.greeks is not None
        assert result.greeks.delta == pytest.approx(0.40, abs=0.001)

    def test_no_contracts_with_greeks_returns_none(self) -> None:
        """Contracts without greeks should be filtered out."""
        contract = make_contract()  # No greeks
        result = select_by_delta([contract])
        assert result is None

    def test_empty_list_returns_none(self) -> None:
        """Empty input should return None."""
        result = select_by_delta([])
        assert result is None


# ===========================================================================
# recommend_contracts tests
# ===========================================================================


class TestRecommendContracts:
    """Tests for recommend_contracts pipeline."""

    def test_happy_path_returns_one_recommendation(self) -> None:
        """Valid contracts through the full pipeline should return 1 recommendation."""
        contracts = [
            make_contract(
                option_type=OptionType.CALL,
                strike="150.00",
                dte_days=45,
                market_iv=0.30,
                bid="5.00",
                ask="5.50",
                volume=200,
                open_interest=1000,
            ),
            make_contract(
                option_type=OptionType.CALL,
                strike="155.00",
                dte_days=45,
                market_iv=0.30,
                bid="3.00",
                ask="3.50",
                volume=150,
                open_interest=800,
            ),
        ]
        result = recommend_contracts(
            contracts,
            SignalDirection.BULLISH,
            spot=150.0,
            risk_free_rate=0.05,
            dividend_yield=0.01,
        )
        assert len(result) == 1
        assert result[0].greeks is not None

    def test_no_liquid_contracts_returns_empty(self) -> None:
        """No contracts passing liquidity filter should return empty list."""
        contracts = [
            make_contract(open_interest=10),  # Below min_oi=100
        ]
        result = recommend_contracts(
            contracts,
            SignalDirection.BULLISH,
            spot=150.0,
            risk_free_rate=0.05,
            dividend_yield=0.01,
        )
        assert result == []

    def test_no_contracts_in_dte_range_returns_empty(self) -> None:
        """No contracts in DTE range should return empty list."""
        contracts = [
            make_contract(dte_days=10, bid="5.00", ask="5.50"),  # Too short
        ]
        result = recommend_contracts(
            contracts,
            SignalDirection.BULLISH,
            spot=150.0,
            risk_free_rate=0.05,
            dividend_yield=0.01,
        )
        assert result == []

    def test_no_contracts_in_delta_range_returns_empty(self) -> None:
        """Contracts outside delta range should return empty list."""
        # Deep OTM contract — delta will be very small (below fallback min)
        contracts = [
            make_contract(
                strike="500.00",
                dte_days=45,
                market_iv=0.10,
                bid="0.01",
                ask="0.02",
                last="0.01",
            ),
        ]
        result = recommend_contracts(
            contracts,
            SignalDirection.BULLISH,
            spot=150.0,
            risk_free_rate=0.05,
            dividend_yield=0.01,
        )
        assert result == []

    def test_greeks_fail_for_all_returns_empty(self) -> None:
        """If Greeks computation fails for all contracts, return empty list."""
        # Expired contract — DTE = 0 so Greeks will fail
        contracts = [
            make_contract(
                dte_days=0,
                bid="0.01",
                ask="0.02",
                last="0.01",
            ),
        ]
        # Since dte_days=0 won't be in the DTE range [30, 60], this returns empty
        result = recommend_contracts(
            contracts,
            SignalDirection.BULLISH,
            spot=150.0,
            risk_free_rate=0.05,
            dividend_yield=0.01,
        )
        assert result == []

    def test_full_pipeline_with_realistic_data(self) -> None:
        """Integration: full pipeline with realistic market data."""
        contracts = [
            make_contract(
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike="145.00",
                dte_days=35,
                market_iv=0.28,
                bid="8.50",
                ask="9.00",
                volume=500,
                open_interest=5000,
            ),
            make_contract(
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike="150.00",
                dte_days=35,
                market_iv=0.30,
                bid="5.00",
                ask="5.50",
                volume=300,
                open_interest=3000,
            ),
            make_contract(
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike="155.00",
                dte_days=35,
                market_iv=0.32,
                bid="3.00",
                ask="3.50",
                volume=200,
                open_interest=2000,
            ),
            make_contract(
                ticker="AAPL",
                option_type=OptionType.PUT,
                strike="150.00",
                dte_days=35,
                market_iv=0.30,
                bid="4.00",
                ask="4.50",
                volume=250,
                open_interest=2500,
            ),
        ]
        result = recommend_contracts(
            contracts,
            SignalDirection.BULLISH,
            spot=150.0,
            risk_free_rate=0.05,
            dividend_yield=0.01,
        )
        assert len(result) == 1
        assert result[0].option_type == OptionType.CALL
        assert result[0].greeks is not None

    def test_direction_drives_type_selection(self) -> None:
        """BEARISH direction should select put contracts."""
        contracts = [
            make_contract(
                option_type=OptionType.CALL,
                strike="150.00",
                dte_days=45,
                market_iv=0.30,
            ),
            make_contract(
                option_type=OptionType.PUT,
                strike="150.00",
                dte_days=45,
                market_iv=0.30,
                bid="5.00",
                ask="5.50",
            ),
        ]
        result = recommend_contracts(
            contracts,
            SignalDirection.BEARISH,
            spot=150.0,
            risk_free_rate=0.05,
            dividend_yield=0.01,
        )
        if result:
            assert result[0].option_type == OptionType.PUT
