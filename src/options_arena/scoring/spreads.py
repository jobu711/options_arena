"""Strategy construction and selection engine for multi-leg option spreads.

Four strategy builders (vertical, iron condor, straddle, strangle) plus a
``select_strategy()`` entry point that maps IV regime, direction, and confidence
to the optimal multi-leg strategy. Each builder computes P&L mechanics,
breakevens, and probability of profit (PoP) via BSM N(d2).

Returns ``SpreadAnalysis | None`` — graceful fallback to single-contract when
a spread cannot be built from the available contracts.

Module boundary:
    - Imports: ``models/``, ``pricing/dispatch`` (via ``pricing/spreads``),
      ``indicators/iv_analytics``, ``scipy.stats.norm``
    - Cannot import: ``services/``, ``pricing/bsm``, ``pricing/american`` directly
"""

import logging
import math
from decimal import Decimal

from scipy.stats import norm

from options_arena.indicators.iv_analytics import classify_vol_regime
from options_arena.models.config import SpreadConfig
from options_arena.models.enums import (
    OptionType,
    PositionSide,
    SignalDirection,
    SpreadType,
    VolRegime,
)
from options_arena.models.options import (
    OptionContract,
    OptionGreeks,
    OptionSpread,
    SpreadAnalysis,
    SpreadLeg,
)
from options_arena.pricing.spreads import aggregate_spread_greeks

logger = logging.getLogger(__name__)

_TWO = Decimal("2")
_UNLIMITED_PROFIT = Decimal("999999.99")


# ---------------------------------------------------------------------------
# Internal helper: Probability of Profit via BSM N(d2)
# ---------------------------------------------------------------------------


def _compute_pop(
    spot_price: float,
    breakeven: Decimal,
    risk_free_rate: float,
    time_to_expiry: float,
    sigma: float,
    *,
    profit_above: bool,
    dividend_yield: float = 0.0,
) -> float:
    """Probability of profit via BSM N(d2) (Merton 1973 with dividends).

    Computes the risk-neutral probability that ``S_T`` finishes on the
    profitable side of the breakeven.

    - ``profit_above=True``: profit when ``S_T > breakeven`` (bullish).
      PoP = N(d2) where d2 is computed with breakeven as the strike.
    - ``profit_above=False``: profit when ``S_T < breakeven`` (bearish).
      PoP = N(-d2) = 1 - N(d2).

    Args:
        spot_price: Current underlying price.
        breakeven: Breakeven price for the spread.
        risk_free_rate: Annualized risk-free rate (decimal).
        time_to_expiry: Time to expiry in years.
        sigma: Implied volatility (annualized, decimal).
        profit_above: True if the strategy profits when the price
            finishes above the breakeven (bullish bias).
        dividend_yield: Continuous dividend yield (decimal).

    Returns:
        Probability of profit in ``[0.0, 1.0]``. Falls back to ``0.5``
        when inputs are degenerate (expired or zero vol).
    """
    if time_to_expiry <= 0 or sigma <= 0:
        return 0.5
    be = float(breakeven)
    if be <= 0 or not math.isfinite(be):
        return 0.5
    if not math.isfinite(spot_price) or spot_price <= 0:
        return 0.5

    d2 = (
        math.log(spot_price / be)
        + (risk_free_rate - dividend_yield - 0.5 * sigma**2) * time_to_expiry
    ) / (sigma * math.sqrt(time_to_expiry))

    prob = float(norm.cdf(d2))
    # N(d2) = P(S_T > breakeven) in risk-neutral measure
    result = prob if profit_above else (1.0 - prob)
    # Clamp to [0, 1] for safety
    return max(0.0, min(1.0, result))


def _compute_pop_between(
    spot_price: float,
    lower_breakeven: Decimal,
    upper_breakeven: Decimal,
    risk_free_rate: float,
    time_to_expiry: float,
    sigma: float,
    *,
    dividend_yield: float = 0.0,
) -> float:
    """Probability price stays between two breakevens (iron condor, short straddle).

    Uses BSM (Merton 1973): P(lower < S_T < upper) = N(d2_upper) - N(d2_lower).

    Args:
        spot_price: Current underlying price.
        lower_breakeven: Lower breakeven price.
        upper_breakeven: Upper breakeven price.
        risk_free_rate: Annualized risk-free rate (decimal).
        time_to_expiry: Time to expiry in years.
        sigma: Implied volatility (annualized, decimal).
        dividend_yield: Continuous dividend yield (decimal).

    Returns:
        Probability in ``[0.0, 1.0]``. Falls back to ``0.5`` on degenerate inputs.
    """
    if time_to_expiry <= 0 or sigma <= 0:
        return 0.5
    if not math.isfinite(spot_price) or spot_price <= 0:
        return 0.5
    lo = float(lower_breakeven)
    hi = float(upper_breakeven)
    if lo <= 0 or hi <= 0 or not math.isfinite(lo) or not math.isfinite(hi):
        return 0.5

    sqrt_t = sigma * math.sqrt(time_to_expiry)
    drift = (risk_free_rate - dividend_yield - 0.5 * sigma**2) * time_to_expiry

    d2_upper = (math.log(spot_price / hi) + drift) / sqrt_t
    d2_lower = (math.log(spot_price / lo) + drift) / sqrt_t

    # P(lo < S_T < hi) = P(S_T > lo) - P(S_T > hi) = N(d2_lower) - N(d2_upper)
    prob = float(norm.cdf(d2_lower)) - float(norm.cdf(d2_upper))
    return max(0.0, min(1.0, prob))


def _compute_pop_outside(
    spot_price: float,
    lower_breakeven: Decimal,
    upper_breakeven: Decimal,
    risk_free_rate: float,
    time_to_expiry: float,
    sigma: float,
    *,
    dividend_yield: float = 0.0,
) -> float:
    """Probability price moves outside two breakevens (long straddle/strangle).

    P(S_T < lower OR S_T > upper) = 1 - P(lower < S_T < upper).

    Args:
        spot_price: Current underlying price.
        lower_breakeven: Lower breakeven price.
        upper_breakeven: Upper breakeven price.
        risk_free_rate: Annualized risk-free rate (decimal).
        time_to_expiry: Time to expiry in years.
        sigma: Implied volatility (annualized, decimal).
        dividend_yield: Continuous dividend yield (decimal).

    Returns:
        Probability in ``[0.0, 1.0]``.
    """
    inside = _compute_pop_between(
        spot_price,
        lower_breakeven,
        upper_breakeven,
        risk_free_rate,
        time_to_expiry,
        sigma,
        dividend_yield=dividend_yield,
    )
    return max(0.0, min(1.0, 1.0 - inside))


# ---------------------------------------------------------------------------
# Helper: Average market IV from contracts
# ---------------------------------------------------------------------------


def _avg_iv(contracts: list[OptionContract]) -> float:
    """Compute average market IV from a list of contracts.

    Skips contracts with zero or non-finite IV. Returns 0.3 as fallback.
    """
    ivs = [c.market_iv for c in contracts if math.isfinite(c.market_iv) and c.market_iv > 0]
    if not ivs:
        return 0.3
    return sum(ivs) / len(ivs)


# ---------------------------------------------------------------------------
# Helper: Safe risk-reward ratio
# ---------------------------------------------------------------------------


def _risk_reward(max_profit: Decimal, max_loss: Decimal) -> float:
    """Compute risk-reward ratio. Returns NaN when max_loss is zero."""
    if max_loss == Decimal("0"):
        return float("nan")
    ratio = float(max_profit / max_loss)
    return ratio if math.isfinite(ratio) else float("nan")


# ---------------------------------------------------------------------------
# Helper: Build net Greeks from legs
# ---------------------------------------------------------------------------


def _net_greeks(legs: list[SpreadLeg]) -> OptionGreeks | None:
    """Aggregate spread Greeks. Returns None if any leg lacks Greeks."""
    return aggregate_spread_greeks(legs)


# ---------------------------------------------------------------------------
# Builder 1: Vertical Spread
# ---------------------------------------------------------------------------


def build_vertical_spread(
    contracts: list[OptionContract],
    direction: SignalDirection,
    spot_price: float,
    risk_free_rate: float,
    time_to_expiry: float,
    config: SpreadConfig,
    *,
    dividend_yield: float = 0.0,
    vol_regime: VolRegime | None = None,
) -> SpreadAnalysis | None:
    """Build a vertical spread (bull/bear, credit/debit).

    For BULLISH direction:
      - High IV → bull put credit spread (sell higher-strike put, buy lower-strike put)
      - Low IV  → bull call debit spread (buy lower-strike call, sell higher-strike call)

    For BEARISH direction:
      - High IV → bear call credit spread (sell lower-strike call, buy higher-strike call)
      - Low IV  → bear put debit spread (buy higher-strike put, sell lower-strike put)

    Args:
        contracts: Available option contracts (pre-filtered for expiration).
        direction: BULLISH or BEARISH signal.
        spot_price: Current underlying price.
        risk_free_rate: Annualized risk-free rate.
        time_to_expiry: Time to expiry in years.
        config: Spread configuration (vertical_width, min_pop).

    Returns:
        ``SpreadAnalysis`` or ``None`` if insufficient contracts.
    """
    if direction == SignalDirection.NEUTRAL:
        logger.debug("build_vertical_spread: NEUTRAL direction, skipping")
        return None

    width = Decimal(str(config.vertical_width))

    # Use vol_regime passed from select_strategy (avoids IV-to-rank conflation)
    if vol_regime is None:
        vol_regime = classify_vol_regime(None)
    is_credit = vol_regime in (VolRegime.ELEVATED, VolRegime.EXTREME)

    # Determine option type based on direction + credit/debit
    # BULLISH credit → put spread, BULLISH debit → call spread
    # BEARISH credit → call spread, BEARISH debit → put spread
    if direction == SignalDirection.BULLISH:
        opt_type = OptionType.PUT if is_credit else OptionType.CALL
    else:  # BEARISH
        opt_type = OptionType.CALL if is_credit else OptionType.PUT

    # Filter contracts by type
    typed_contracts = [c for c in contracts if c.option_type == opt_type]
    if len(typed_contracts) < 2:
        logger.debug(
            "build_vertical_spread: insufficient %s contracts (%d)",
            opt_type.value,
            len(typed_contracts),
        )
        return None

    # Sort by strike for pair searching
    typed_contracts.sort(key=lambda c: c.strike)

    # Find a pair matching the configured width
    best_pair: tuple[OptionContract, OptionContract] | None = None
    spot_dec = Decimal(str(spot_price))

    for i, lower in enumerate(typed_contracts):
        for upper in typed_contracts[i + 1 :]:
            if upper.strike - lower.strike == width:
                # Prefer pairs nearest to spot
                if best_pair is None:
                    best_pair = (lower, upper)
                else:
                    current_mid = (lower.strike + upper.strike) / _TWO
                    best_mid = (best_pair[0].strike + best_pair[1].strike) / _TWO
                    if abs(current_mid - spot_dec) < abs(best_mid - spot_dec):
                        best_pair = (lower, upper)

    if best_pair is None:
        logger.debug(
            "build_vertical_spread: no strike pair with width=%s found",
            width,
        )
        return None

    lower_contract, upper_contract = best_pair

    # Construct legs based on strategy
    if direction == SignalDirection.BULLISH:
        if is_credit:
            # Bull put credit: sell upper put (higher premium), buy lower put
            short_leg = SpreadLeg(
                contract=upper_contract,
                side=PositionSide.SHORT,
                quantity=1,
            )
            long_leg = SpreadLeg(
                contract=lower_contract,
                side=PositionSide.LONG,
                quantity=1,
            )
        else:
            # Bull call debit: buy lower call, sell upper call
            long_leg = SpreadLeg(
                contract=lower_contract,
                side=PositionSide.LONG,
                quantity=1,
            )
            short_leg = SpreadLeg(
                contract=upper_contract,
                side=PositionSide.SHORT,
                quantity=1,
            )
    else:  # BEARISH
        if is_credit:
            # Bear call credit: sell lower call (higher premium), buy upper call
            short_leg = SpreadLeg(
                contract=lower_contract,
                side=PositionSide.SHORT,
                quantity=1,
            )
            long_leg = SpreadLeg(
                contract=upper_contract,
                side=PositionSide.LONG,
                quantity=1,
            )
        else:
            # Bear put debit: buy upper put (higher premium), sell lower put
            long_leg = SpreadLeg(
                contract=upper_contract,
                side=PositionSide.LONG,
                quantity=1,
            )
            short_leg = SpreadLeg(
                contract=lower_contract,
                side=PositionSide.SHORT,
                quantity=1,
            )

    legs = [long_leg, short_leg]

    # Compute P&L
    if is_credit:
        # Credit spread: premium received = short_mid - long_mid
        net_premium = short_leg.contract.mid - long_leg.contract.mid
        max_profit = net_premium
        max_loss = width - net_premium
    else:
        # Debit spread: premium paid = long_mid - short_mid
        net_premium = long_leg.contract.mid - short_leg.contract.mid
        max_profit = width - net_premium
        max_loss = net_premium

    # Guard against negative P&L (degenerate pricing)
    if max_profit <= Decimal("0") or max_loss <= Decimal("0"):
        logger.debug("build_vertical_spread: degenerate P&L, skipping")
        return None

    # Compute breakeven
    if is_credit:
        if opt_type == OptionType.PUT:
            # Bull put credit: breakeven = short_strike - net_credit
            breakeven = short_leg.contract.strike - net_premium
        else:
            # Bear call credit: breakeven = short_strike + net_credit
            breakeven = short_leg.contract.strike + net_premium
    else:
        if opt_type == OptionType.CALL:
            # Bull call debit: breakeven = long_strike + net_debit
            breakeven = long_leg.contract.strike + net_premium
        else:
            # Bear put debit: breakeven = long_strike - net_debit
            breakeven = long_leg.contract.strike - net_premium

    # Compute PoP
    # Bullish spreads profit above breakeven, bearish below
    profit_above = direction == SignalDirection.BULLISH
    sigma = _avg_iv([long_leg.contract, short_leg.contract])
    pop = _compute_pop(
        spot_price,
        breakeven,
        risk_free_rate,
        time_to_expiry,
        sigma,
        profit_above=profit_above,
        dividend_yield=dividend_yield,
    )

    # Build rationale
    if is_credit:
        style = "credit"
        direction_label = "bull" if direction == SignalDirection.BULLISH else "bear"
    else:
        style = "debit"
        direction_label = "bull" if direction == SignalDirection.BULLISH else "bear"
    rationale = (
        f"{direction_label.title()} {opt_type.value} {style} spread: "
        f"{lower_contract.strike}/{upper_contract.strike} "
        f"({direction.value} bias, {'high' if is_credit else 'low'} IV regime)"
    )

    spread = OptionSpread(
        spread_type=SpreadType.VERTICAL,
        legs=legs,
        ticker=lower_contract.ticker,
    )

    net_greeks = _net_greeks(legs)

    return SpreadAnalysis(
        spread=spread,
        net_premium=net_premium,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=[breakeven],
        risk_reward_ratio=_risk_reward(max_profit, max_loss),
        pop_estimate=pop,
        net_greeks=net_greeks,
        strategy_rationale=rationale,
        iv_regime=vol_regime,
    )


# ---------------------------------------------------------------------------
# Builder 2: Iron Condor
# ---------------------------------------------------------------------------


def build_iron_condor(
    contracts: list[OptionContract],
    spot_price: float,
    risk_free_rate: float,
    time_to_expiry: float,
    config: SpreadConfig,
    *,
    dividend_yield: float = 0.0,
    vol_regime: VolRegime | None = None,
) -> SpreadAnalysis | None:
    """Build an iron condor (sell OTM put + call, buy further OTM put + call).

    Structure:
      1. Buy OTM put (lowest strike — long put wing)
      2. Sell OTM put (higher strike — short put)
      3. Sell OTM call (lower strike — short call)
      4. Buy OTM call (highest strike — long call wing)

    Args:
        contracts: Available option contracts.
        spot_price: Current underlying price.
        risk_free_rate: Annualized risk-free rate.
        time_to_expiry: Time to expiry in years.
        config: Spread configuration (iron_condor_wing_width, min_pop).

    Returns:
        ``SpreadAnalysis`` or ``None`` if insufficient contracts.
    """
    wing_width = Decimal(str(config.iron_condor_wing_width))
    spot_dec = Decimal(str(spot_price))

    puts = sorted(
        [c for c in contracts if c.option_type == OptionType.PUT],
        key=lambda c: c.strike,
    )
    calls = sorted(
        [c for c in contracts if c.option_type == OptionType.CALL],
        key=lambda c: c.strike,
    )

    if len(puts) < 2 or len(calls) < 2:
        logger.debug(
            "build_iron_condor: insufficient contracts (puts=%d, calls=%d)",
            len(puts),
            len(calls),
        )
        return None

    # Find OTM put pair: sell a put below spot, buy a put further below
    # OTM puts have strike < spot
    otm_puts = [p for p in puts if p.strike < spot_dec]
    # Find OTM call pair: sell a call above spot, buy a call further above
    # OTM calls have strike > spot
    otm_calls = [c for c in calls if c.strike > spot_dec]

    # Find put pair with matching wing width
    put_pair: tuple[OptionContract, OptionContract] | None = None
    for i in range(len(otm_puts) - 1, 0, -1):
        short_put = otm_puts[i]  # higher strike (closer to ATM)
        for j in range(i - 1, -1, -1):
            long_put = otm_puts[j]  # lower strike (further OTM)
            if short_put.strike - long_put.strike == wing_width:
                put_pair = (long_put, short_put)
                break
        if put_pair is not None:
            break

    # Find call pair with matching wing width
    call_pair: tuple[OptionContract, OptionContract] | None = None
    for i, short_call in enumerate(otm_calls):
        for upper_call in otm_calls[i + 1 :]:
            if upper_call.strike - short_call.strike == wing_width:
                call_pair = (short_call, upper_call)
                break
        if call_pair is not None:
            break

    if put_pair is None or call_pair is None:
        logger.debug(
            "build_iron_condor: no matching wing width=%s (put_pair=%s, call_pair=%s)",
            wing_width,
            put_pair is not None,
            call_pair is not None,
        )
        return None

    long_put, short_put = put_pair
    short_call, long_call = call_pair

    # Construct legs
    leg_long_put = SpreadLeg(contract=long_put, side=PositionSide.LONG, quantity=1)
    leg_short_put = SpreadLeg(contract=short_put, side=PositionSide.SHORT, quantity=1)
    leg_short_call = SpreadLeg(contract=short_call, side=PositionSide.SHORT, quantity=1)
    leg_long_call = SpreadLeg(contract=long_call, side=PositionSide.LONG, quantity=1)
    legs = [leg_long_put, leg_short_put, leg_short_call, leg_long_call]

    # P&L: Iron condor is a credit strategy
    # Credit from put side = short_put.mid - long_put.mid
    put_credit = short_put.mid - long_put.mid
    # Credit from call side = short_call.mid - long_call.mid
    call_credit = short_call.mid - long_call.mid
    net_premium = put_credit + call_credit
    max_profit = net_premium
    max_loss = wing_width - net_premium

    if max_profit <= Decimal("0") or max_loss <= Decimal("0"):
        logger.debug("build_iron_condor: degenerate P&L, skipping")
        return None

    # Breakevens — use total net premium (not per-side credits)
    # At the lower breakeven, the call side expires worthless and its credit offsets put losses
    lower_breakeven = short_put.strike - net_premium
    upper_breakeven = short_call.strike + net_premium

    # PoP: probability price stays between breakevens
    sigma = _avg_iv([long_put, short_put, short_call, long_call])
    pop = _compute_pop_between(
        spot_price,
        lower_breakeven,
        upper_breakeven,
        risk_free_rate,
        time_to_expiry,
        sigma,
        dividend_yield=dividend_yield,
    )

    if vol_regime is None:
        vol_regime = classify_vol_regime(_avg_iv(contracts) * 100)
    rationale = (
        f"Iron condor: {long_put.strike}/{short_put.strike} puts, "
        f"{short_call.strike}/{long_call.strike} calls "
        f"(neutral bias, {vol_regime.value if vol_regime else 'unknown'} IV regime)"
    )

    spread = OptionSpread(
        spread_type=SpreadType.IRON_CONDOR,
        legs=legs,
        ticker=long_put.ticker,
    )

    net_greeks = _net_greeks(legs)

    return SpreadAnalysis(
        spread=spread,
        net_premium=net_premium,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=[lower_breakeven, upper_breakeven],
        risk_reward_ratio=_risk_reward(max_profit, max_loss),
        pop_estimate=pop,
        net_greeks=net_greeks,
        strategy_rationale=rationale,
        iv_regime=vol_regime,
    )


# ---------------------------------------------------------------------------
# Builder 3: Straddle
# ---------------------------------------------------------------------------


def build_straddle(
    contracts: list[OptionContract],
    spot_price: float,
    risk_free_rate: float,
    time_to_expiry: float,
    *,
    dividend_yield: float = 0.0,
    vol_regime: VolRegime | None = None,
) -> SpreadAnalysis | None:
    """Build a long straddle (ATM call + ATM put at same strike).

    Profits when the underlying makes a large move in either direction.
    Max loss is limited to the total premium paid.

    Args:
        contracts: Available option contracts.
        spot_price: Current underlying price.
        risk_free_rate: Annualized risk-free rate.
        time_to_expiry: Time to expiry in years.

    Returns:
        ``SpreadAnalysis`` or ``None`` if no ATM pair found.
    """
    spot_dec = Decimal(str(spot_price))

    calls = [c for c in contracts if c.option_type == OptionType.CALL]
    puts = [c for c in contracts if c.option_type == OptionType.PUT]

    if not calls or not puts:
        logger.debug(
            "build_straddle: insufficient contracts (calls=%d, puts=%d)",
            len(calls),
            len(puts),
        )
        return None

    # Find ATM: strike closest to spot
    # Build strike -> (call, put) pairs
    call_by_strike: dict[Decimal, OptionContract] = {}
    for c in calls:
        if c.strike not in call_by_strike or abs(c.strike - spot_dec) < abs(
            call_by_strike[c.strike].strike - spot_dec
        ):
            call_by_strike[c.strike] = c

    put_by_strike: dict[Decimal, OptionContract] = {}
    for p in puts:
        if p.strike not in put_by_strike or abs(p.strike - spot_dec) < abs(
            put_by_strike[p.strike].strike - spot_dec
        ):
            put_by_strike[p.strike] = p

    # Find common strikes
    common_strikes = set(call_by_strike.keys()) & set(put_by_strike.keys())
    if not common_strikes:
        logger.debug("build_straddle: no common call/put strikes found")
        return None

    # Pick strike closest to spot
    atm_strike = min(common_strikes, key=lambda s: abs(s - spot_dec))
    atm_call = call_by_strike[atm_strike]
    atm_put = put_by_strike[atm_strike]

    # Construct legs (long straddle)
    leg_call = SpreadLeg(contract=atm_call, side=PositionSide.LONG, quantity=1)
    leg_put = SpreadLeg(contract=atm_put, side=PositionSide.LONG, quantity=1)
    legs = [leg_call, leg_put]

    # P&L
    net_premium = atm_call.mid + atm_put.mid  # debit paid
    max_profit = _UNLIMITED_PROFIT
    max_loss = net_premium

    if max_loss <= Decimal("0"):
        logger.debug("build_straddle: zero or negative premium, skipping")
        return None

    # Breakevens: strike +/- total premium
    lower_breakeven = atm_strike - net_premium
    upper_breakeven = atm_strike + net_premium

    # PoP: probability price moves outside breakevens
    sigma = _avg_iv([atm_call, atm_put])
    pop = _compute_pop_outside(
        spot_price,
        lower_breakeven,
        upper_breakeven,
        risk_free_rate,
        time_to_expiry,
        sigma,
        dividend_yield=dividend_yield,
    )

    rationale = (
        f"Long straddle at {atm_strike} strike: "
        f"ATM call + ATM put (expecting large move, direction uncertain)"
    )

    spread = OptionSpread(
        spread_type=SpreadType.STRADDLE,
        legs=legs,
        ticker=atm_call.ticker,
    )

    net_greeks = _net_greeks(legs)

    return SpreadAnalysis(
        spread=spread,
        net_premium=net_premium,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=[lower_breakeven, upper_breakeven],
        risk_reward_ratio=_risk_reward(max_profit, max_loss),
        pop_estimate=pop,
        net_greeks=net_greeks,
        strategy_rationale=rationale,
        iv_regime=vol_regime,
    )


# ---------------------------------------------------------------------------
# Builder 4: Strangle
# ---------------------------------------------------------------------------


def build_strangle(
    contracts: list[OptionContract],
    spot_price: float,
    risk_free_rate: float,
    time_to_expiry: float,
    config: SpreadConfig,
    *,
    dividend_yield: float = 0.0,
    vol_regime: VolRegime | None = None,
) -> SpreadAnalysis | None:
    """Build a long strangle (OTM call + OTM put at different strikes).

    Cheaper than a straddle but with wider breakevens.

    Args:
        contracts: Available option contracts.
        spot_price: Current underlying price.
        risk_free_rate: Annualized risk-free rate.
        time_to_expiry: Time to expiry in years.
        config: Spread configuration.

    Returns:
        ``SpreadAnalysis`` or ``None`` if insufficient OTM contracts.
    """
    spot_dec = Decimal(str(spot_price))

    # OTM puts: strike < spot
    otm_puts = sorted(
        [c for c in contracts if c.option_type == OptionType.PUT and c.strike < spot_dec],
        key=lambda c: c.strike,
        reverse=True,  # highest strike first (closest to ATM)
    )
    # OTM calls: strike > spot
    otm_calls = sorted(
        [c for c in contracts if c.option_type == OptionType.CALL and c.strike > spot_dec],
        key=lambda c: c.strike,
    )

    if not otm_puts or not otm_calls:
        logger.debug(
            "build_strangle: insufficient OTM contracts (puts=%d, calls=%d)",
            len(otm_puts),
            len(otm_calls),
        )
        return None

    # Pick the closest OTM put and call to spot (most liquid, tightest spreads)
    chosen_put = otm_puts[0]  # highest OTM put strike
    chosen_call = otm_calls[0]  # lowest OTM call strike

    # Construct legs (long strangle)
    leg_put = SpreadLeg(contract=chosen_put, side=PositionSide.LONG, quantity=1)
    leg_call = SpreadLeg(contract=chosen_call, side=PositionSide.LONG, quantity=1)
    legs = [leg_put, leg_call]

    # P&L
    net_premium = chosen_put.mid + chosen_call.mid  # debit paid
    max_profit = _UNLIMITED_PROFIT
    max_loss = net_premium

    if max_loss <= Decimal("0"):
        logger.debug("build_strangle: zero or negative premium, skipping")
        return None

    # Breakevens: put_strike - premium, call_strike + premium
    lower_breakeven = chosen_put.strike - net_premium
    upper_breakeven = chosen_call.strike + net_premium

    # PoP: probability price moves outside breakevens
    sigma = _avg_iv([chosen_put, chosen_call])
    pop = _compute_pop_outside(
        spot_price,
        lower_breakeven,
        upper_breakeven,
        risk_free_rate,
        time_to_expiry,
        sigma,
        dividend_yield=dividend_yield,
    )

    rationale = (
        f"Long strangle: {chosen_put.strike} put / {chosen_call.strike} call "
        f"(expecting large move, lower cost than straddle)"
    )

    spread = OptionSpread(
        spread_type=SpreadType.STRANGLE,
        legs=legs,
        ticker=chosen_put.ticker,
    )

    net_greeks = _net_greeks(legs)

    return SpreadAnalysis(
        spread=spread,
        net_premium=net_premium,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=[lower_breakeven, upper_breakeven],
        risk_reward_ratio=_risk_reward(max_profit, max_loss),
        pop_estimate=pop,
        net_greeks=net_greeks,
        strategy_rationale=rationale,
        iv_regime=vol_regime,
    )


# ---------------------------------------------------------------------------
# Selection Engine
# ---------------------------------------------------------------------------


def select_strategy(
    contracts: list[OptionContract],
    direction: SignalDirection,
    confidence: float,
    iv_rank: float | None,
    spot_price: float,
    risk_free_rate: float,
    time_to_expiry: float,
    config: SpreadConfig,
    *,
    dividend_yield: float = 0.0,
) -> SpreadAnalysis | None:
    """Select the optimal multi-leg strategy based on IV regime, direction, and confidence.

    Decision tree:
      1. ELEVATED/EXTREME IV + NEUTRAL → iron condor
      2. ELEVATED/EXTREME IV + low confidence (<0.4) → strangle
      3. ELEVATED/EXTREME IV + directional → vertical credit spread
      4. LOW IV + directional → vertical debit spread
      5. NORMAL IV or no IV data → None (single-contract fallback)

    Falls through in priority: if the primary strategy cannot be built from
    available contracts, tries the next in the cascade.

    Args:
        contracts: Available option contracts (pre-filtered for expiration).
        direction: BULLISH, BEARISH, or NEUTRAL signal.
        confidence: Confidence level in ``[0.0, 1.0]``.
        iv_rank: IV rank as percentage (0-100), or ``None`` if unavailable.
        spot_price: Current underlying price.
        risk_free_rate: Annualized risk-free rate.
        time_to_expiry: Time to expiry in years.
        config: Spread configuration.

    Returns:
        ``SpreadAnalysis`` for the selected strategy, or ``None`` when no
        multi-leg strategy is appropriate (falls back to single contract).
    """
    if not config.enabled:
        logger.debug("select_strategy: spread analysis disabled")
        return None

    vol_regime = classify_vol_regime(iv_rank)
    if vol_regime is None:
        logger.debug("select_strategy: iv_rank=%s -> no vol regime, returning None", iv_rank)
        return None

    logger.debug(
        "select_strategy: vol_regime=%s, direction=%s, confidence=%.2f",
        vol_regime.value,
        direction.value,
        confidence,
    )

    def _check_pop(result: SpreadAnalysis | None) -> SpreadAnalysis | None:
        """Return *result* only if it meets the configured min PoP threshold."""
        if result is None:
            return None
        if result.pop_estimate < config.min_pop:
            logger.debug(
                "select_strategy: rejecting %s (PoP %.2f < min_pop %.2f)",
                result.spread.spread_type.value,
                result.pop_estimate,
                config.min_pop,
            )
            return None
        return result

    match (vol_regime, direction):
        case (VolRegime.ELEVATED | VolRegime.EXTREME, SignalDirection.NEUTRAL):
            # High IV + neutral → iron condor
            result = _check_pop(
                build_iron_condor(
                    contracts,
                    spot_price,
                    risk_free_rate,
                    time_to_expiry,
                    config,
                    dividend_yield=dividend_yield,
                    vol_regime=vol_regime,
                )
            )
            if result is not None:
                return result
            # Fallback: try strangle if iron condor can't be built
            logger.debug("select_strategy: iron condor failed, trying strangle fallback")
            return _check_pop(
                build_strangle(
                    contracts,
                    spot_price,
                    risk_free_rate,
                    time_to_expiry,
                    config,
                    dividend_yield=dividend_yield,
                    vol_regime=vol_regime,
                )
            )

        case (VolRegime.ELEVATED | VolRegime.EXTREME, _) if confidence < 0.4:
            # High IV + low confidence → strangle
            result = _check_pop(
                build_strangle(
                    contracts,
                    spot_price,
                    risk_free_rate,
                    time_to_expiry,
                    config,
                    dividend_yield=dividend_yield,
                    vol_regime=vol_regime,
                )
            )
            if result is not None:
                return result
            # Fallback: try straddle
            logger.debug("select_strategy: strangle failed, trying straddle fallback")
            return _check_pop(
                build_straddle(
                    contracts,
                    spot_price,
                    risk_free_rate,
                    time_to_expiry,
                    dividend_yield=dividend_yield,
                    vol_regime=vol_regime,
                )
            )

        case (VolRegime.ELEVATED | VolRegime.EXTREME, _):
            # High IV + directional + decent confidence → vertical credit spread
            result = _check_pop(
                build_vertical_spread(
                    contracts,
                    direction,
                    spot_price,
                    risk_free_rate,
                    time_to_expiry,
                    config,
                    dividend_yield=dividend_yield,
                    vol_regime=vol_regime,
                )
            )
            if result is not None:
                return result
            # Fallback: try strangle
            logger.debug("select_strategy: vertical credit failed, trying strangle fallback")
            return _check_pop(
                build_strangle(
                    contracts,
                    spot_price,
                    risk_free_rate,
                    time_to_expiry,
                    config,
                    dividend_yield=dividend_yield,
                    vol_regime=vol_regime,
                )
            )

        case (VolRegime.LOW, SignalDirection.BULLISH | SignalDirection.BEARISH):
            # Low IV + directional → vertical debit spread
            result = _check_pop(
                build_vertical_spread(
                    contracts,
                    direction,
                    spot_price,
                    risk_free_rate,
                    time_to_expiry,
                    config,
                    dividend_yield=dividend_yield,
                    vol_regime=vol_regime,
                )
            )
            if result is not None:
                return result
            logger.debug("select_strategy: vertical debit failed, no fallback for low IV")
            return None

        case _:
            # NORMAL IV, LOW+NEUTRAL, or anything else → single contract
            logger.debug(
                "select_strategy: no spread for vol_regime=%s, direction=%s",
                vol_regime.value,
                direction.value,
            )
            return None
