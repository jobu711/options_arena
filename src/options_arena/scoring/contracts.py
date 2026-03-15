"""Contract filtering, Greeks dispatch, and delta-targeted selection.

Receives pre-fetched option contracts and selects the best candidate for a
directional signal. Greeks are computed exclusively via ``pricing/dispatch.py``
(BAW for American, BSM for European) — no local computation.

Functions:
    filter_contracts     -- Liquidity, spread, and direction filtering.
    select_expiration    -- DTE-range selection closest to midpoint.
    compute_greeks       -- Batch Greeks computation via pricing dispatch.
    select_by_delta      -- Delta-targeted contract selection with fallback.
    recommend_contracts  -- Full pipeline: filter -> expiration -> greeks -> delta.
"""

import logging
import math
from datetime import date
from decimal import Decimal

from options_arena.models.enums import GreeksSource, OptionType, SignalDirection
from options_arena.models.filters import OptionsFilters
from options_arena.models.options import OptionContract
from options_arena.pricing import smooth_iv_parity
from options_arena.pricing.dispatch import option_greeks, option_iv, option_second_order_greeks

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_DAYS_PER_YEAR = 365.0
_DEFAULT_DELTA_TARGET: float = 0.35

# Liquidity multiplier calibration — internal constants, NOT config.
_SPREAD_WEIGHT: float = 0.7
_OI_WEIGHT: float = 0.3


def _default_filters(filters: OptionsFilters | None) -> OptionsFilters:
    """Return *filters* if provided, otherwise a fresh ``OptionsFilters`` with defaults."""
    return filters if filters is not None else OptionsFilters()


def filter_contracts(
    contracts: list[OptionContract],
    direction: SignalDirection,
    filters: OptionsFilters | None = None,
) -> list[OptionContract]:
    """Filter contracts by liquidity, spread width, and directional type.

    Args:
        contracts: Raw list of option contracts to filter.
        direction: BULLISH selects calls, BEARISH selects puts,
            NEUTRAL keeps both types.
        filters: Options filter configuration. Uses ``OptionsFilters()`` defaults if None.

    Returns:
        Filtered contracts sorted by ``open_interest`` descending.
    """
    cfg = _default_filters(filters)

    if direction == SignalDirection.BULLISH:
        desired_types = {OptionType.CALL}
    elif direction == SignalDirection.BEARISH:
        desired_types = {OptionType.PUT}
    else:
        # NEUTRAL keeps both calls and puts
        desired_types = {OptionType.CALL, OptionType.PUT}

    filtered: list[OptionContract] = []
    for contract in contracts:
        if contract.option_type not in desired_types:
            continue
        if contract.open_interest < cfg.min_oi:
            continue
        if contract.volume < cfg.min_volume:
            continue

        # Zero-bid handling: contracts with bid=0 but ask>0 are potentially
        # tradeable via limit orders (yfinance often returns bid=0 for mid-cap
        # and ETF options). Skip spread check for these since spread/mid is
        # meaningless. Contracts with both bid=0 AND ask=0 are truly dead.
        if contract.bid == _ZERO:
            if contract.ask == _ZERO:
                continue  # Truly dead contract
            # bid=0 but ask>0: pass through without spread check
        elif contract.mid == _ZERO:
            # Defensive: unreachable when bid>0 (prices are non-negative),
            # but guards against unexpected Decimal edge cases.
            continue
        else:
            spread_pct = float(contract.spread / contract.mid)
            if spread_pct < 0.0 or spread_pct > cfg.max_spread_pct:
                continue

        filtered.append(contract)

    filtered.sort(key=lambda c: c.open_interest, reverse=True)

    logger.debug(
        "filter_contracts: %d -> %d contracts (direction=%s)",
        len(contracts),
        len(filtered),
        direction.value,
    )
    return filtered


def select_expiration(
    contracts: list[OptionContract],
    filters: OptionsFilters | None = None,
) -> date | None:
    """Select the expiration closest to the midpoint of the DTE range.

    Args:
        contracts: Pre-filtered contracts with various expirations.
        filters: Options filter configuration. Uses ``OptionsFilters()`` defaults if None.

    Returns:
        Best expiration ``date``, or ``None`` if no contracts fall within the DTE range.
    """
    if not contracts:
        return None

    cfg = _default_filters(filters)
    target_dte = (cfg.min_dte + cfg.max_dte) / 2.0

    # Collect unique expirations with their DTE values
    expiration_dte: dict[date, int] = {}
    for contract in contracts:
        if contract.expiration not in expiration_dte:
            expiration_dte[contract.expiration] = contract.dte

    # Filter to valid DTE range
    valid: list[tuple[date, int]] = [
        (exp_date, dte)
        for exp_date, dte in expiration_dte.items()
        if cfg.min_dte <= dte <= cfg.max_dte
    ]

    if not valid:
        logger.debug(
            "select_expiration: no expirations in [%d, %d] DTE range",
            cfg.min_dte,
            cfg.max_dte,
        )
        return None

    best_date, best_dte = min(valid, key=lambda pair: abs(pair[1] - target_dte))

    logger.debug(
        "select_expiration: picked %s (DTE=%d, target=%.1f), from %d valid expirations",
        best_date.isoformat(),
        best_dte,
        target_dte,
        len(valid),
    )
    return best_date


def compute_greeks(
    contracts: list[OptionContract],
    spot: float,
    risk_free_rate: float,
    dividend_yield: float,
    *,
    use_parity_smoothing: bool = True,
) -> list[OptionContract]:
    """Compute or preserve Greeks for each contract using three-tier resolution.

    **Tier 1** — Contract already has ``greeks`` (e.g. from CBOE native data):
    preserve existing Greeks as-is, set ``greeks_source=GreeksSource.MARKET``
    if the source is not already set, skip ``pricing/dispatch.py`` entirely.

    **Tier 2** — Contract has no ``greeks``: compute via ``pricing/dispatch.py``
    (existing behavior), set ``greeks_source=GreeksSource.COMPUTED``.
    When ``use_parity_smoothing`` is True and both call and put exist at the
    same (strike, expiration), the smoothed IV from ``smooth_iv_parity()``
    replaces the raw ``market_iv`` as sigma, and
    ``greeks_source=GreeksSource.SMOOTHED``.

    **Tier 3** — Local computation fails: contract excluded (logged at warning).

    Since ``OptionContract`` is frozen, returns new instances with greeks
    populated. Contracts where computation fails are silently skipped
    (logged at warning level).

    Args:
        contracts: Contracts to compute Greeks for.
        spot: Current underlying price.
        risk_free_rate: Annualized risk-free rate (decimal).
        dividend_yield: Continuous dividend yield (decimal).
        use_parity_smoothing: When True, group contracts by (strike, expiration)
            and apply IV smoothing via put-call parity spread weighting when
            both call and put exist at the same strike/expiration.

    Returns:
        List of new ``OptionContract`` instances with ``greeks`` populated.
        May be shorter than the input if some contracts fail.
    """
    result: list[OptionContract] = []

    # Build call/put pair lookup for IV smoothing
    pairs: dict[tuple[Decimal, date], dict[str, OptionContract]] = {}
    if use_parity_smoothing:
        for c in contracts:
            key = (c.strike, c.expiration)
            pairs.setdefault(key, {})[c.option_type.value] = c

    for contract in contracts:
        # ------------------------------------------------------------------
        # Tier 1: Contract already has Greeks (e.g. CBOE native)
        # ------------------------------------------------------------------
        if contract.greeks is not None:
            update: dict[str, object] = {}
            if contract.greeks_source is None:
                update["greeks_source"] = GreeksSource.MARKET
            new_contract = contract.model_copy(update=update) if update else contract
            result.append(new_contract)
            logger.debug(
                "Tier 1 (market): %s strike %s — preserving existing Greeks",
                contract.ticker,
                contract.strike,
            )
            continue

        # ------------------------------------------------------------------
        # Tier 2: No Greeks — compute via pricing/dispatch.py
        # ------------------------------------------------------------------
        try:
            time_to_expiry = contract.dte / _DAYS_PER_YEAR
            if time_to_expiry <= 0.0:
                logger.warning(
                    "Skipping %s strike %s: DTE=%d (expired or same-day)",
                    contract.ticker,
                    contract.strike,
                    contract.dte,
                )
                continue

            strike_f = float(contract.strike)
            sigma = contract.market_iv

            # Attempt IV smoothing via put-call parity when a paired contract exists
            smoothed_iv_value: float | None = None
            if use_parity_smoothing:
                key = (contract.strike, contract.expiration)
                pair = pairs.get(key, {})
                other_type = "put" if contract.option_type == OptionType.CALL else "call"
                other = pair.get(other_type)
                if (
                    other is not None
                    and math.isfinite(other.market_iv)
                    and other.market_iv > 0
                    and math.isfinite(sigma)
                    and sigma > 0
                ):
                    smoothed_iv_value = smooth_iv_parity(
                        call_iv=(
                            sigma if contract.option_type == OptionType.CALL else other.market_iv
                        ),
                        put_iv=(
                            other.market_iv if contract.option_type == OptionType.CALL else sigma
                        ),
                        call_bid=float(
                            contract.bid if contract.option_type == OptionType.CALL else other.bid
                        ),
                        call_ask=float(
                            contract.ask if contract.option_type == OptionType.CALL else other.ask
                        ),
                        put_bid=float(
                            other.bid if contract.option_type == OptionType.CALL else contract.bid
                        ),
                        put_ask=float(
                            other.ask if contract.option_type == OptionType.CALL else contract.ask
                        ),
                    )
                    if math.isfinite(smoothed_iv_value) and smoothed_iv_value > 0:
                        sigma = smoothed_iv_value
                    else:
                        smoothed_iv_value = None

            # If market_iv is suspect, attempt IV solve using mid price
            if not math.isfinite(sigma) or sigma <= 0.0 or sigma > 5.0:
                mid_price = float(contract.mid)
                if not math.isfinite(mid_price) or mid_price <= 0.0:
                    logger.warning(
                        "Skipping %s strike %s: invalid market_iv=%.4f and mid=%.4f",
                        contract.ticker,
                        contract.strike,
                        sigma,
                        mid_price,
                    )
                    continue
                try:
                    original_iv = sigma
                    sigma = option_iv(
                        contract.exercise_style,
                        mid_price,
                        spot,
                        strike_f,
                        time_to_expiry,
                        risk_free_rate,
                        dividend_yield,
                        contract.option_type,
                    )
                    smoothed_iv_value = None  # solver overrode smoothed IV
                    logger.debug(
                        "IV re-solved for %s strike %s: %.4f -> %.4f",
                        contract.ticker,
                        contract.strike,
                        original_iv,
                        sigma,
                    )
                except (ValueError, OverflowError, ZeroDivisionError):
                    logger.warning(
                        "IV solve failed for %s strike %s: market_iv=%.4f, mid=%.4f",
                        contract.ticker,
                        contract.strike,
                        contract.market_iv,
                        mid_price,
                    )
                    continue

            greeks = option_greeks(
                contract.exercise_style,
                spot,
                strike_f,
                time_to_expiry,
                risk_free_rate,
                dividend_yield,
                sigma,
                contract.option_type,
            )

            # Attempt second-order Greeks — failure is non-fatal (keep first-order)
            try:
                second = option_second_order_greeks(
                    contract.exercise_style,
                    spot,
                    strike_f,
                    time_to_expiry,
                    risk_free_rate,
                    dividend_yield,
                    sigma,
                    contract.option_type,
                )
                greeks = greeks.model_copy(
                    update={
                        "vanna": second.vanna,
                        "charm": second.charm,
                        "vomma": second.vomma,
                    },
                )
            except (ValueError, OverflowError, ZeroDivisionError):
                logger.debug(
                    "Second-order Greeks failed for %s strike %s; keeping first-order only",
                    contract.ticker,
                    contract.strike,
                )

            # OptionContract is frozen — model_copy skips validators on ALL
            # fields (including updated ones). Safe here because greeks was
            # constructed via OptionGreeks(...) and sigma passed isfinite above.
            greeks_source = (
                GreeksSource.SMOOTHED if smoothed_iv_value is not None else GreeksSource.COMPUTED
            )
            new_contract = contract.model_copy(
                update={
                    "greeks": greeks,
                    "market_iv": sigma,
                    "smoothed_iv": smoothed_iv_value,
                    "greeks_source": greeks_source,
                },
            )
            result.append(new_contract)

        except (ValueError, OverflowError, ZeroDivisionError):
            # Tier 3: Computation failed — contract excluded
            logger.warning(
                "Greeks computation failed for %s strike %s: IV=%.4f, DTE=%d",
                contract.ticker,
                contract.strike,
                contract.market_iv,
                contract.dte,
                exc_info=True,
            )

    logger.debug(
        "compute_greeks: %d -> %d contracts with greeks (spot=%.2f)",
        len(contracts),
        len(result),
        spot,
    )
    return result


def _compute_liquidity_score(
    contract: OptionContract,
    max_spread_pct: float,
) -> float:
    """Compute 0-1 liquidity score for a contract. Higher = more liquid.

    Blends bid-ask tightness (70%) with open interest depth (30%).
    Floor of 0.01 prevents division-by-zero in effective distance.
    """
    mid = float(contract.mid)
    if not math.isfinite(max_spread_pct) or max_spread_pct <= 0.0:
        spread_component = 0.0
    elif mid > 0:
        spread_pct = float(contract.spread) / mid
        # Stale quote (bid > ask) → penalize; normal → linear decay
        spread_component = 0.0 if spread_pct < 0.0 else max(1.0 - spread_pct / max_spread_pct, 0.0)
    else:
        spread_component = 0.0

    oi_component = min(math.log10(contract.open_interest + 1) / 4.0, 1.0)
    score = spread_component * _SPREAD_WEIGHT + oi_component * _OI_WEIGHT

    return score if math.isfinite(score) else 0.0


def select_by_delta(
    contracts: list[OptionContract],
    filters: OptionsFilters | None = None,
    delta_target: float = _DEFAULT_DELTA_TARGET,
    *,
    direction: SignalDirection | None = None,
    surface_residuals: dict[tuple[OptionType, Decimal, date], float] | None = None,
) -> OptionContract | None:
    """Select the contract with delta closest to the target.

    Uses ``abs(delta)`` for comparison so that puts (negative delta) and
    calls (positive delta) are treated symmetrically.

    When ``direction`` and ``surface_residuals`` are provided, a secondary
    tiebreaker favours contracts with direction-favorable vol mispricing:
    BULLISH prefers underpriced (lower residual = cheaper vol), BEARISH
    prefers overpriced (higher residual = richer vol to sell).

    Args:
        contracts: Contracts with greeks already computed.
        filters: Options filter configuration. Uses ``OptionsFilters()`` defaults if None.
        delta_target: Target delta value (from ``PricingConfig``).
        direction: Signal direction for vol-mispricing tiebreaker.
        surface_residuals: Map of ``(option_type, strike, expiration)`` to IV
            surface residual z-score. Positive = IV above fitted surface (overpriced).

    Returns:
        Best contract by delta proximity, or ``None`` if no contract has
        delta within primary or fallback range.
    """
    if not contracts:
        return None

    cfg = _default_filters(filters)

    # Partition into primary and fallback candidate lists
    primary: list[tuple[OptionContract, float]] = []  # (contract, distance)
    fallback: list[tuple[OptionContract, float]] = []

    for contract in contracts:
        if contract.greeks is None:
            continue

        abs_delta = abs(contract.greeks.delta)
        if not math.isfinite(abs_delta):
            continue
        distance = abs(abs_delta - delta_target)

        if cfg.delta_primary_min <= abs_delta <= cfg.delta_primary_max:
            primary.append((contract, distance))
        elif cfg.delta_fallback_min <= abs_delta <= cfg.delta_fallback_max:
            fallback.append((contract, distance))

    def _vol_tiebreaker(c: OptionContract) -> float:
        """Compute vol-mispricing tiebreaker for sort key.

        Returns a float where lower = better for the given direction.
        """
        if not surface_residuals or not direction:
            return 0.0
        key = (c.option_type, c.strike, c.expiration)
        residual = surface_residuals.get(key)
        if residual is None or not math.isfinite(residual):
            return 0.0
        if direction == SignalDirection.BULLISH:
            # Lower residual = underpriced vol = better for buying
            return residual
        if direction == SignalDirection.BEARISH:
            # Higher residual = overpriced vol = better for selling (negate)
            return -residual
        # NEUTRAL — no tiebreaker
        return 0.0

    if primary:
        # Sort by effective distance (delta_distance / liquidity),
        # then vol tiebreaker, then strike
        def _sort_key(
            pair: tuple[OptionContract, float],
        ) -> tuple[float, float, Decimal]:
            c, delta_dist = pair
            liq = _compute_liquidity_score(c, cfg.max_spread_pct)
            effective = delta_dist / max(liq, 0.01)
            tb = _vol_tiebreaker(c)
            return (effective, tb, c.strike)

        primary.sort(key=_sort_key)
        best, best_distance = primary[0]
        logger.debug(
            "select_by_delta: primary — strike=%s, |delta|=%.4f (distance=%.4f)",
            best.strike,
            abs(best.greeks.delta) if best.greeks else 0.0,
            best_distance,
        )
        return best

    if fallback:

        def _sort_key_fb(
            pair: tuple[OptionContract, float],
        ) -> tuple[float, float, Decimal]:
            c, delta_dist = pair
            liq = _compute_liquidity_score(c, cfg.max_spread_pct)
            effective = delta_dist / max(liq, 0.01)
            tb = _vol_tiebreaker(c)
            return (effective, tb, c.strike)

        fallback.sort(key=_sort_key_fb)
        best_fb, best_fb_distance = fallback[0]
        logger.info(
            "select_by_delta: fallback — strike=%s, distance=%.4f",
            best_fb.strike,
            best_fb_distance,
        )
        return best_fb

    logger.debug("select_by_delta: no contracts with delta in any acceptable range")
    return None


def recommend_contracts(
    contracts: list[OptionContract],
    direction: SignalDirection,
    spot: float,
    risk_free_rate: float,
    dividend_yield: float,
    filters: OptionsFilters | None = None,
    delta_target: float = _DEFAULT_DELTA_TARGET,
    *,
    surface_residuals: dict[tuple[OptionType, Decimal, date], float] | None = None,
) -> list[OptionContract]:
    """Run the full recommendation pipeline: filter -> expiration -> greeks -> delta.

    Args:
        contracts: All available option contracts for a ticker.
        direction: Directional signal driving type selection.
        spot: Current underlying price.
        risk_free_rate: Annualized risk-free rate (decimal).
        dividend_yield: Continuous dividend yield (decimal).
        filters: Options filter configuration. Uses ``OptionsFilters()`` defaults if None.
        delta_target: Target delta value (from ``PricingConfig``).
        surface_residuals: Map of ``(option_type, strike, expiration)`` to IV
            surface residual z-score for vol-mispricing tiebreaker.

    Returns:
        List of 0 or 1 recommended contracts.
    """
    cfg = _default_filters(filters)

    # Step 1: Filter by direction, liquidity, spread
    filtered = filter_contracts(contracts, direction, cfg)
    if not filtered:
        logger.info("recommend_contracts: no contracts passed filtering")
        return []

    # Step 2: Select best expiration
    best_expiration = select_expiration(filtered, cfg)
    if best_expiration is None:
        logger.info("recommend_contracts: no contracts in DTE range")
        return []

    # Step 3: Narrow to that expiration
    at_expiration = [c for c in filtered if c.expiration == best_expiration]

    # Step 4: Compute Greeks
    with_greeks = compute_greeks(at_expiration, spot, risk_free_rate, dividend_yield)
    if not with_greeks:
        logger.info("recommend_contracts: Greeks computation failed for all contracts")
        return []

    # Step 5: Select by delta (with optional vol-mispricing tiebreaker)
    best = select_by_delta(
        with_greeks,
        cfg,
        delta_target,
        direction=direction,
        surface_residuals=surface_residuals,
    )
    if best is None:
        logger.info("recommend_contracts: no contracts matched delta target")
        return []

    return [best]
