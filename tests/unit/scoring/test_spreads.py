"""Tests for scoring/spreads.py — strategy construction and selection engine.

Covers all four builders (vertical, iron condor, straddle, strangle), the
``select_strategy()`` decision tree, and the ``_compute_pop`` helper.
Uses ``make_option_contract()`` from the test factory for contract creation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from options_arena.models.config import SpreadConfig
from options_arena.models.enums import (
    OptionType,
    PositionSide,
    SignalDirection,
    SpreadType,
    VolRegime,
)
from options_arena.models.options import SpreadAnalysis
from options_arena.scoring.spreads import (
    _compute_pop,
    _compute_pop_between,
    _compute_pop_outside,
    build_iron_condor,
    build_straddle,
    build_strangle,
    build_vertical_spread,
    select_strategy,
)
from tests.factories import make_option_contract

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_DEFAULT_SPOT = 150.0
_DEFAULT_RATE = 0.05
_DEFAULT_TTE = 45.0 / 365.0  # 45 days
_DEFAULT_CONFIG = SpreadConfig(vertical_width=5, iron_condor_wing_width=5)


def _make_call_chain(
    strikes: list[str],
    bids: list[str],
    asks: list[str],
) -> list[object]:
    """Build a list of call OptionContracts from strike/bid/ask string triples."""
    return [
        make_option_contract(
            strike=Decimal(s),
            option_type=OptionType.CALL,
            bid=Decimal(b),
            ask=Decimal(a),
        )
        for s, b, a in zip(strikes, bids, asks, strict=True)
    ]


def _make_put_chain(
    strikes: list[str],
    bids: list[str],
    asks: list[str],
) -> list[object]:
    """Build a list of put OptionContracts from strike/bid/ask string triples."""
    return [
        make_option_contract(
            strike=Decimal(s),
            option_type=OptionType.PUT,
            bid=Decimal(b),
            ask=Decimal(a),
        )
        for s, b, a in zip(strikes, bids, asks, strict=True)
    ]


def _make_full_chain() -> list[object]:
    """Build a realistic chain with calls and puts at multiple strikes."""
    calls = _make_call_chain(
        strikes=["140", "145", "150", "155", "160"],
        bids=["12.00", "8.00", "5.00", "3.00", "1.50"],
        asks=["12.50", "8.50", "5.50", "3.50", "2.00"],
    )
    puts = _make_put_chain(
        strikes=["140", "145", "150", "155", "160"],
        bids=["1.50", "3.00", "5.00", "8.00", "12.00"],
        asks=["2.00", "3.50", "5.50", "8.50", "12.50"],
    )
    return calls + puts  # type: ignore[return-value]


# ===========================================================================
# TestBuildVerticalSpread
# ===========================================================================


class TestBuildVerticalSpread:
    """Tests for ``build_vertical_spread()``."""

    def test_bull_call_debit_spread(self) -> None:
        """Verify bull call spread P&L: max_profit = width - debit, max_loss = debit."""
        contracts = _make_call_chain(
            strikes=["145", "150", "155"],
            bids=["7.00", "4.50", "2.50"],
            asks=["7.50", "5.00", "3.00"],
        )
        # Low IV to trigger debit spread
        for c in contracts:
            object.__setattr__(c, "market_iv", 0.15)

        result = build_vertical_spread(
            contracts,
            SignalDirection.BULLISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.VERTICAL

        # Bull call debit: buy 145 call (mid=7.25), sell 150 call (mid=4.75)
        # net_debit = 7.25 - 4.75 = 2.50, max_profit = 5 - 2.50 = 2.50
        assert result.net_premium == Decimal("2.50")
        assert result.max_profit == Decimal("2.50")
        assert result.max_loss == Decimal("2.50")

    def test_bear_put_debit_spread(self) -> None:
        """Verify bear put spread P&L formulas."""
        contracts = _make_put_chain(
            strikes=["145", "150", "155"],
            bids=["2.50", "5.00", "8.00"],
            asks=["3.00", "5.50", "8.50"],
        )
        for c in contracts:
            object.__setattr__(c, "market_iv", 0.15)

        result = build_vertical_spread(
            contracts,
            SignalDirection.BEARISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.VERTICAL

        # Builder picks pair nearest to spot=150. Two pairs: (145,150) mid=147.5
        # and (150,155) mid=152.5. Both are 2.5 from spot, first found wins.
        # Bear put debit: buy 150 put (mid=5.25), sell 145 put (mid=2.75)
        # net_debit = 5.25 - 2.75 = 2.50, max_profit = 5 - 2.50 = 2.50
        assert result.net_premium == Decimal("2.50")
        assert result.max_profit == Decimal("2.50")
        assert result.max_loss == Decimal("2.50")

    def test_bull_put_credit_spread(self) -> None:
        """Verify bull put credit spread: max_profit = credit, max_loss = width - credit."""
        contracts = _make_put_chain(
            strikes=["145", "150", "155"],
            bids=["2.50", "5.00", "8.00"],
            asks=["3.00", "5.50", "8.50"],
        )
        # High IV to trigger credit spread
        for c in contracts:
            object.__setattr__(c, "market_iv", 0.60)

        result = build_vertical_spread(
            contracts,
            SignalDirection.BULLISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
            vol_regime=VolRegime.ELEVATED,
        )

        assert result is not None
        # Bull put credit: sell 150 put (mid=5.25), buy 145 put (mid=2.75)
        # net_credit = 5.25 - 2.75 = 2.50
        assert result.net_premium == Decimal("2.50")
        assert result.max_profit == Decimal("2.50")
        assert result.max_loss == Decimal("2.50")

    def test_bear_call_credit_spread(self) -> None:
        """Verify bear call credit spread."""
        contracts = _make_call_chain(
            strikes=["145", "150", "155"],
            bids=["7.00", "4.50", "2.50"],
            asks=["7.50", "5.00", "3.00"],
        )
        for c in contracts:
            object.__setattr__(c, "market_iv", 0.60)

        result = build_vertical_spread(
            contracts,
            SignalDirection.BEARISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
            vol_regime=VolRegime.ELEVATED,
        )

        assert result is not None
        # Bear call credit: sell 145 call (mid=7.25), buy 150 call (mid=4.75)
        # net_credit = 7.25 - 4.75 = 2.50
        assert result.net_premium == Decimal("2.50")
        assert result.max_profit == Decimal("2.50")
        assert result.max_loss == Decimal("2.50")

    def test_breakeven_debit_call(self) -> None:
        """Verify breakeven for bull call debit = long_strike + net_debit."""
        contracts = _make_call_chain(
            strikes=["145", "150", "155"],
            bids=["7.00", "4.50", "2.50"],
            asks=["7.50", "5.00", "3.00"],
        )
        for c in contracts:
            object.__setattr__(c, "market_iv", 0.15)

        result = build_vertical_spread(
            contracts,
            SignalDirection.BULLISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert len(result.breakevens) == 1
        # Bull call debit: breakeven = long_strike (145) + net_debit (2.50) = 147.50
        assert result.breakevens[0] == Decimal("147.50")

    def test_returns_none_insufficient_contracts(self) -> None:
        """Verify returns None when < 2 contracts available."""
        contracts = [
            make_option_contract(
                strike=Decimal("150"),
                option_type=OptionType.CALL,
            ),
        ]
        result = build_vertical_spread(
            contracts,
            SignalDirection.BULLISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert result is None

    def test_returns_none_no_matching_width(self) -> None:
        """Verify returns None when no strike pair matches configured width."""
        # Width=5, but strikes are 3 apart
        contracts = _make_call_chain(
            strikes=["147", "150", "153"],
            bids=["5.00", "3.50", "2.00"],
            asks=["5.50", "4.00", "2.50"],
        )
        result = build_vertical_spread(
            contracts,
            SignalDirection.BULLISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert result is None

    def test_decimal_precision_survives(self) -> None:
        """Verify all monetary values maintain Decimal precision."""
        contracts = _make_call_chain(
            strikes=["145.00", "150.00", "155.00"],
            bids=["7.05", "4.55", "2.55"],
            asks=["7.55", "5.05", "3.05"],
        )
        for c in contracts:
            object.__setattr__(c, "market_iv", 0.15)

        result = build_vertical_spread(
            contracts,
            SignalDirection.BULLISH,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert isinstance(result.net_premium, Decimal)
        assert isinstance(result.max_profit, Decimal)
        assert isinstance(result.max_loss, Decimal)
        for be in result.breakevens:
            assert isinstance(be, Decimal)

    def test_neutral_direction_returns_none(self) -> None:
        """Verify NEUTRAL direction returns None for vertical spread."""
        contracts = _make_call_chain(
            strikes=["145", "150", "155"],
            bids=["7.00", "4.50", "2.50"],
            asks=["7.50", "5.00", "3.00"],
        )
        result = build_vertical_spread(
            contracts,
            SignalDirection.NEUTRAL,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert result is None


# ===========================================================================
# TestBuildIronCondor
# ===========================================================================


class TestBuildIronCondor:
    """Tests for ``build_iron_condor()``."""

    def test_four_leg_construction(self) -> None:
        """Verify iron condor has exactly 4 legs with correct sides."""
        contracts = _make_full_chain()
        result = build_iron_condor(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert len(result.spread.legs) == 4
        assert result.spread.spread_type == SpreadType.IRON_CONDOR

        # Check sides: should have 2 long, 2 short
        sides = [leg.side for leg in result.spread.legs]
        assert sides.count(PositionSide.LONG) == 2
        assert sides.count(PositionSide.SHORT) == 2

        # Check types: should have 2 puts, 2 calls
        types = [leg.contract.option_type for leg in result.spread.legs]
        assert types.count(OptionType.PUT) == 2
        assert types.count(OptionType.CALL) == 2

    def test_pnl_formulas(self) -> None:
        """Verify max_profit = net_credit, max_loss = wing_width - net_credit."""
        contracts = _make_full_chain()
        result = build_iron_condor(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        # max_profit = net_premium (credit received)
        assert result.max_profit == result.net_premium
        # max_loss = wing_width - net_premium
        wing_width = Decimal("5")
        assert result.max_loss == wing_width - result.net_premium

    def test_two_breakevens(self) -> None:
        """Verify iron condor has exactly 2 breakeven prices."""
        contracts = _make_full_chain()
        result = build_iron_condor(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert len(result.breakevens) == 2
        # Lower breakeven < upper breakeven
        assert result.breakevens[0] < result.breakevens[1]

    def test_returns_none_insufficient_strikes(self) -> None:
        """Verify returns None when insufficient OTM strikes available."""
        # Only one strike on each side — can't build wing width
        contracts = [
            make_option_contract(
                strike=Decimal("145"),
                option_type=OptionType.PUT,
                bid=Decimal("3.00"),
                ask=Decimal("3.50"),
            ),
            make_option_contract(
                strike=Decimal("155"),
                option_type=OptionType.CALL,
                bid=Decimal("3.00"),
                ask=Decimal("3.50"),
            ),
        ]
        result = build_iron_condor(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert result is None

    def test_returns_none_all_same_type(self) -> None:
        """Verify returns None when only calls (no puts) available."""
        contracts = _make_call_chain(
            strikes=["140", "145", "150", "155", "160"],
            bids=["12.00", "8.00", "5.00", "3.00", "1.50"],
            asks=["12.50", "8.50", "5.50", "3.50", "2.00"],
        )
        result = build_iron_condor(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert result is None


# ===========================================================================
# TestBuildStraddle
# ===========================================================================


class TestBuildStraddle:
    """Tests for ``build_straddle()``."""

    def test_atm_construction(self) -> None:
        """Verify straddle uses ATM call + ATM put at same strike."""
        contracts = _make_full_chain()
        result = build_straddle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)

        assert result is not None
        assert result.spread.spread_type == SpreadType.STRADDLE
        assert len(result.spread.legs) == 2

        # Both legs should be at the ATM strike (150, closest to spot=150)
        strikes = {leg.contract.strike for leg in result.spread.legs}
        assert len(strikes) == 1
        assert Decimal("150") in strikes

        # Both legs should be LONG
        for leg in result.spread.legs:
            assert leg.side == PositionSide.LONG

    def test_max_loss_equals_premium(self) -> None:
        """Verify max_loss = call.mid + put.mid."""
        contracts = _make_full_chain()
        result = build_straddle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)

        assert result is not None
        # ATM at 150: call mid = (5.00+5.50)/2 = 5.25, put mid = (5.00+5.50)/2 = 5.25
        assert result.max_loss == Decimal("10.50")
        assert result.net_premium == Decimal("10.50")

    def test_max_profit_unlimited(self) -> None:
        """Verify max_profit is the unlimited sentinel."""
        contracts = _make_full_chain()
        result = build_straddle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)

        assert result is not None
        assert result.max_profit == Decimal("999999.99")

    def test_two_breakevens(self) -> None:
        """Verify breakevens at strike +/- total_premium."""
        contracts = _make_full_chain()
        result = build_straddle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)

        assert result is not None
        assert len(result.breakevens) == 2
        # strike=150, premium=10.50 → breakevens at 139.50 and 160.50
        assert result.breakevens[0] == Decimal("139.50")
        assert result.breakevens[1] == Decimal("160.50")

    def test_returns_none_no_atm(self) -> None:
        """Verify returns None when no common call/put strikes."""
        # Only calls, no puts
        contracts = _make_call_chain(
            strikes=["145", "150", "155"],
            bids=["7.00", "4.50", "2.50"],
            asks=["7.50", "5.00", "3.00"],
        )
        result = build_straddle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)
        assert result is None

    def test_returns_none_empty_contracts(self) -> None:
        """Verify returns None for empty contract list."""
        result = build_straddle([], _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)
        assert result is None


# ===========================================================================
# TestBuildStrangle
# ===========================================================================


class TestBuildStrangle:
    """Tests for ``build_strangle()``."""

    def test_otm_construction(self) -> None:
        """Verify strangle uses OTM call + OTM put at different strikes."""
        contracts = _make_full_chain()
        result = build_strangle(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.STRANGLE
        assert len(result.spread.legs) == 2

        # One put (strike < spot), one call (strike > spot)
        put_legs = [
            leg for leg in result.spread.legs if leg.contract.option_type == OptionType.PUT
        ]
        call_legs = [
            leg for leg in result.spread.legs if leg.contract.option_type == OptionType.CALL
        ]
        assert len(put_legs) == 1
        assert len(call_legs) == 1
        assert put_legs[0].contract.strike < Decimal(str(_DEFAULT_SPOT))
        assert call_legs[0].contract.strike > Decimal(str(_DEFAULT_SPOT))

        # Both legs should be LONG
        for leg in result.spread.legs:
            assert leg.side == PositionSide.LONG

    def test_max_loss_equals_premium(self) -> None:
        """Verify max_loss = call.mid + put.mid."""
        contracts = _make_full_chain()
        result = build_strangle(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        # OTM put at 145 (mid=3.25), OTM call at 155 (mid=3.25)
        assert result.max_loss == Decimal("6.50")
        assert result.net_premium == Decimal("6.50")

    def test_max_profit_unlimited(self) -> None:
        """Verify max_profit is the unlimited sentinel."""
        contracts = _make_full_chain()
        result = build_strangle(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.max_profit == Decimal("999999.99")

    def test_breakevens(self) -> None:
        """Verify breakevens at put_strike - premium and call_strike + premium."""
        contracts = _make_full_chain()
        result = build_strangle(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        assert len(result.breakevens) == 2
        # Put at 145, call at 155, premium=6.50
        # lower = 145 - 6.50 = 138.50, upper = 155 + 6.50 = 161.50
        assert result.breakevens[0] == Decimal("138.50")
        assert result.breakevens[1] == Decimal("161.50")

    def test_returns_none_insufficient_otm(self) -> None:
        """Verify returns None when insufficient OTM contracts."""
        # All strikes at or above spot — no OTM puts
        contracts = _make_call_chain(
            strikes=["150", "155", "160"],
            bids=["5.00", "3.00", "1.50"],
            asks=["5.50", "3.50", "2.00"],
        )
        result = build_strangle(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert result is None

    def test_returns_none_empty_contracts(self) -> None:
        """Verify returns None for empty contract list."""
        result = build_strangle(
            [],
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert result is None


# ===========================================================================
# TestSelectStrategy
# ===========================================================================


class TestSelectStrategy:
    """Tests for ``select_strategy()`` decision tree."""

    def test_high_iv_neutral_selects_iron_condor(self) -> None:
        """Verify IV>50 + NEUTRAL -> iron condor."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.NEUTRAL,
            confidence=0.6,
            iv_rank=65.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.IRON_CONDOR

    def test_high_iv_directional_selects_credit_vertical(self) -> None:
        """Verify IV>50 + BULLISH + confidence>=0.4 -> vertical credit spread."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BULLISH,
            confidence=0.6,
            iv_rank=65.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.VERTICAL

    def test_low_iv_directional_selects_debit_vertical(self) -> None:
        """Verify IV<25 + BULLISH -> vertical debit spread."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BULLISH,
            confidence=0.6,
            iv_rank=15.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.VERTICAL

    def test_high_iv_low_confidence_selects_strangle(self) -> None:
        """Verify IV>50 + confidence<0.4 -> strangle."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BULLISH,
            confidence=0.3,
            iv_rank=65.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.STRANGLE

    def test_mid_iv_returns_none(self) -> None:
        """Verify IV 25-50 -> None (single contract fallback)."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BULLISH,
            confidence=0.6,
            iv_rank=35.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is None

    def test_none_iv_rank_returns_none(self) -> None:
        """Verify iv_rank=None -> None."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BULLISH,
            confidence=0.6,
            iv_rank=None,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is None

    def test_fallback_cascade(self) -> None:
        """Verify if primary strategy can't be built, tries next in cascade."""
        # Only calls with no matching wing width for iron condor,
        # but strangle should work as fallback
        contracts = _make_full_chain()

        # Use a config with impossible iron condor width but valid strangle
        config = SpreadConfig(
            vertical_width=5,
            iron_condor_wing_width=50,  # no pair will match
        )

        result = select_strategy(
            contracts,
            SignalDirection.NEUTRAL,
            confidence=0.6,
            iv_rank=65.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=config,
        )

        # Iron condor fails, should fall back to strangle
        assert result is not None
        assert result.spread.spread_type == SpreadType.STRANGLE

    def test_extreme_iv_neutral_selects_iron_condor(self) -> None:
        """Verify EXTREME IV (>=75) + NEUTRAL -> iron condor."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.NEUTRAL,
            confidence=0.6,
            iv_rank=85.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.IRON_CONDOR

    def test_low_iv_neutral_returns_none(self) -> None:
        """Verify LOW IV + NEUTRAL -> None (no spread for non-directional low IV)."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.NEUTRAL,
            confidence=0.6,
            iv_rank=10.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is None

    def test_disabled_config_returns_none(self) -> None:
        """Verify disabled spread config returns None."""
        config = SpreadConfig(enabled=False)
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BULLISH,
            confidence=0.6,
            iv_rank=65.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=config,
        )
        assert result is None

    def test_bearish_high_iv_selects_vertical(self) -> None:
        """Verify IV>50 + BEARISH + confidence>=0.4 -> vertical."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BEARISH,
            confidence=0.6,
            iv_rank=65.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.VERTICAL

    def test_bearish_low_iv_selects_debit_vertical(self) -> None:
        """Verify IV<25 + BEARISH -> vertical debit spread."""
        contracts = _make_full_chain()
        result = select_strategy(
            contracts,
            SignalDirection.BEARISH,
            confidence=0.6,
            iv_rank=15.0,
            spot_price=_DEFAULT_SPOT,
            risk_free_rate=_DEFAULT_RATE,
            time_to_expiry=_DEFAULT_TTE,
            config=_DEFAULT_CONFIG,
        )

        assert result is not None
        assert result.spread.spread_type == SpreadType.VERTICAL


# ===========================================================================
# TestComputePoP
# ===========================================================================


class TestComputePoP:
    """Tests for ``_compute_pop()`` and related helpers."""

    def test_pop_in_bounds(self) -> None:
        """Verify PoP always in [0.0, 1.0]."""
        pop = _compute_pop(
            spot_price=150.0,
            breakeven=Decimal("155"),
            risk_free_rate=0.05,
            time_to_expiry=0.12,
            sigma=0.30,
            profit_above=True,
        )
        assert 0.0 <= pop <= 1.0

    def test_deep_itm_bullish_spread_high_pop(self) -> None:
        """Verify bullish spread with breakeven far below spot has high PoP."""
        # Breakeven far below spot — profit_above=True, price likely stays above
        pop = _compute_pop(
            spot_price=150.0,
            breakeven=Decimal("100"),
            risk_free_rate=0.05,
            time_to_expiry=0.12,
            sigma=0.30,
            profit_above=True,
        )
        assert pop > 0.8

    def test_deep_otm_bullish_spread_low_pop(self) -> None:
        """Verify bullish spread with breakeven far above spot has low PoP."""
        # Breakeven far above spot — profit_above=True, unlikely to reach it
        pop = _compute_pop(
            spot_price=150.0,
            breakeven=Decimal("200"),
            risk_free_rate=0.05,
            time_to_expiry=0.12,
            sigma=0.30,
            profit_above=True,
        )
        assert pop < 0.2

    def test_pop_fallback_on_zero_time(self) -> None:
        """Verify PoP returns 0.5 when time_to_expiry is 0."""
        pop = _compute_pop(
            spot_price=150.0,
            breakeven=Decimal("155"),
            risk_free_rate=0.05,
            time_to_expiry=0.0,
            sigma=0.30,
            profit_above=True,
        )
        assert pop == 0.5

    def test_pop_fallback_on_zero_sigma(self) -> None:
        """Verify PoP returns 0.5 when sigma is 0."""
        pop = _compute_pop(
            spot_price=150.0,
            breakeven=Decimal("155"),
            risk_free_rate=0.05,
            time_to_expiry=0.12,
            sigma=0.0,
            profit_above=True,
        )
        assert pop == 0.5

    def test_pop_between_in_bounds(self) -> None:
        """Verify pop_between always in [0.0, 1.0]."""
        pop = _compute_pop_between(
            spot_price=150.0,
            lower_breakeven=Decimal("140"),
            upper_breakeven=Decimal("160"),
            risk_free_rate=0.05,
            time_to_expiry=0.12,
            sigma=0.30,
        )
        assert 0.0 <= pop <= 1.0

    def test_pop_outside_complement(self) -> None:
        """Verify pop_outside = 1 - pop_between."""
        inside = _compute_pop_between(
            spot_price=150.0,
            lower_breakeven=Decimal("140"),
            upper_breakeven=Decimal("160"),
            risk_free_rate=0.05,
            time_to_expiry=0.12,
            sigma=0.30,
        )
        outside = _compute_pop_outside(
            spot_price=150.0,
            lower_breakeven=Decimal("140"),
            upper_breakeven=Decimal("160"),
            risk_free_rate=0.05,
            time_to_expiry=0.12,
            sigma=0.30,
        )
        assert inside + outside == pytest.approx(1.0, abs=1e-10)


# ===========================================================================
# TestAnalysisModel
# ===========================================================================


class TestAnalysisModel:
    """Verify SpreadAnalysis model integration with builder output."""

    def test_spread_analysis_serialization(self) -> None:
        """Verify SpreadAnalysis from builder survives JSON round-trip."""
        contracts = _make_full_chain()
        result = build_straddle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)

        assert result is not None
        json_str = result.model_dump_json()
        restored = SpreadAnalysis.model_validate_json(json_str)
        assert restored.net_premium == result.net_premium
        assert restored.max_profit == result.max_profit
        assert restored.pop_estimate == pytest.approx(result.pop_estimate, abs=1e-10)

    def test_risk_reward_ratio_correct(self) -> None:
        """Verify risk_reward_ratio = max_profit / max_loss."""
        contracts = _make_full_chain()
        result = build_iron_condor(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )

        assert result is not None
        expected = float(result.max_profit / result.max_loss)
        assert result.risk_reward_ratio == pytest.approx(expected, rel=1e-6)

    def test_pop_estimate_valid_range(self) -> None:
        """Verify all builders produce pop_estimate in [0, 1]."""
        contracts = _make_full_chain()

        # Straddle
        r1 = build_straddle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE)
        assert r1 is not None
        assert 0.0 <= r1.pop_estimate <= 1.0

        # Strangle
        r2 = build_strangle(contracts, _DEFAULT_SPOT, _DEFAULT_RATE, _DEFAULT_TTE, _DEFAULT_CONFIG)
        assert r2 is not None
        assert 0.0 <= r2.pop_estimate <= 1.0

        # Iron condor
        r3 = build_iron_condor(
            contracts,
            _DEFAULT_SPOT,
            _DEFAULT_RATE,
            _DEFAULT_TTE,
            _DEFAULT_CONFIG,
        )
        assert r3 is not None
        assert 0.0 <= r3.pop_estimate <= 1.0
