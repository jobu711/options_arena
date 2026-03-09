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

from options_arena.models.config import PricingConfig
from options_arena.models.enums import GreeksSource, OptionType, SignalDirection
from options_arena.models.options import OptionContract
from options_arena.pricing.dispatch import option_greeks, option_iv

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_DAYS_PER_YEAR = 365.0

# Liquidity multiplier calibration — internal constants, NOT config.
_SPREAD_WEIGHT: float = 0.7
_OI_WEIGHT: float = 0.3


def _default_config(config: PricingConfig | None) -> PricingConfig:
    """Return *config* if provided, otherwise a fresh ``PricingConfig`` with defaults."""
    return config if config is not None else PricingConfig()


def filter_contracts(
    contracts: list[OptionContract],
    direction: SignalDirection,
    config: PricingConfig | None = None,
) -> list[OptionContract]:
    """Filter contracts by liquidity, spread width, and directional type.

    Args:
        contracts: Raw list of option contracts to filter.
        direction: BULLISH selects calls, BEARISH selects puts,
            NEUTRAL keeps both types.
        config: Pricing configuration. Uses ``PricingConfig()`` defaults if None.

    Returns:
        Filtered contracts sorted by ``open_interest`` descending.
    """
    cfg = _default_config(config)

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
            if spread_pct > cfg.max_spread_pct:
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
    config: PricingConfig | None = None,
) -> date | None:
    """Select the expiration closest to the midpoint of the DTE range.

    Args:
        contracts: Pre-filtered contracts with various expirations.
        config: Pricing configuration. Uses ``PricingConfig()`` defaults if None.

    Returns:
        Best expiration ``date``, or ``None`` if no contracts fall within the DTE range.
    """
    if not contracts:
        return None

    cfg = _default_config(config)
    target_dte = (cfg.dte_min + cfg.dte_max) / 2.0

    # Collect unique expirations with their DTE values
    expiration_dte: dict[date, int] = {}
    for contract in contracts:
        if contract.expiration not in expiration_dte:
            expiration_dte[contract.expiration] = contract.dte

    # Filter to valid DTE range
    valid: list[tuple[date, int]] = [
        (exp_date, dte)
        for exp_date, dte in expiration_dte.items()
        if cfg.dte_min <= dte <= cfg.dte_max
    ]

    if not valid:
        logger.debug(
            "select_expiration: no expirations in [%d, %d] DTE range",
            cfg.dte_min,
            cfg.dte_max,
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
) -> list[OptionContract]:
    """Compute or preserve Greeks for each contract using three-tier resolution.

    **Tier 1** — Contract already has ``greeks`` (e.g. from CBOE native data):
    preserve existing Greeks as-is, set ``greeks_source=GreeksSource.MARKET``
    if the source is not already set, skip ``pricing/dispatch.py`` entirely.

    **Tier 2** — Contract has no ``greeks``: compute via ``pricing/dispatch.py``
    (existing behavior), set ``greeks_source=GreeksSource.COMPUTED``.

    **Tier 3** — Local computation fails: contract excluded (logged at warning).

    Since ``OptionContract`` is frozen, returns new instances with greeks
    populated. Contracts where computation fails are silently skipped
    (logged at warning level).

    Args:
        contracts: Contracts to compute Greeks for.
        spot: Current underlying price.
        risk_free_rate: Annualized risk-free rate (decimal).
        dividend_yield: Continuous dividend yield (decimal).

    Returns:
        List of new ``OptionContract`` instances with ``greeks`` populated.
        May be shorter than the input if some contracts fail.
    """
    result: list[OptionContract] = []

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

            # OptionContract is frozen — model_copy skips validators on ALL
            # fields (including updated ones). Safe here because greeks was
            # constructed via OptionGreeks(...) and sigma passed isfinite above.
            new_contract = contract.model_copy(
                update={
                    "greeks": greeks,
                    "market_iv": sigma,
                    "greeks_source": GreeksSource.COMPUTED,
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
    config: PricingConfig | None = None,
) -> OptionContract | None:
    """Select the contract with delta closest to the target.

    Uses ``abs(delta)`` for comparison so that puts (negative delta) and
    calls (positive delta) are treated symmetrically.

    Args:
        contracts: Contracts with greeks already computed.
        config: Pricing configuration. Uses ``PricingConfig()`` defaults if None.

    Returns:
        Best contract by delta proximity, or ``None`` if no contract has
        delta within primary or fallback range.
    """
    if not contracts:
        return None

    cfg = _default_config(config)

    # Partition into primary and fallback candidate lists
    primary: list[tuple[OptionContract, float]] = []  # (contract, distance)
    fallback: list[tuple[OptionContract, float]] = []

    for contract in contracts:
        if contract.greeks is None:
            continue

        abs_delta = abs(contract.greeks.delta)
        if not math.isfinite(abs_delta):
            continue
        distance = abs(abs_delta - cfg.delta_target)

        if cfg.delta_primary_min <= abs_delta <= cfg.delta_primary_max:
            primary.append((contract, distance))
        elif cfg.delta_fallback_min <= abs_delta <= cfg.delta_fallback_max:
            fallback.append((contract, distance))

    if primary:
        # Sort by effective distance (delta_distance / liquidity), then by strike
        def _sort_key(pair: tuple[OptionContract, float]) -> tuple[float, Decimal]:
            c, delta_dist = pair
            liq = _compute_liquidity_score(c, cfg.max_spread_pct)
            effective = delta_dist / max(liq, 0.01)
            return (effective, c.strike)

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

        def _sort_key_fb(pair: tuple[OptionContract, float]) -> tuple[float, Decimal]:
            c, delta_dist = pair
            liq = _compute_liquidity_score(c, cfg.max_spread_pct)
            effective = delta_dist / max(liq, 0.01)
            return (effective, c.strike)

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
    config: PricingConfig | None = None,
) -> list[OptionContract]:
    """Run the full recommendation pipeline: filter -> expiration -> greeks -> delta.

    Args:
        contracts: All available option contracts for a ticker.
        direction: Directional signal driving type selection.
        spot: Current underlying price.
        risk_free_rate: Annualized risk-free rate (decimal).
        dividend_yield: Continuous dividend yield (decimal).
        config: Pricing configuration. Uses ``PricingConfig()`` defaults if None.

    Returns:
        List of 0 or 1 recommended contracts.
    """
    cfg = _default_config(config)

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

    # Step 5: Select by delta
    best = select_by_delta(with_greeks, cfg)
    if best is None:
        logger.info("recommend_contracts: no contracts matched delta target")
        return []

    return [best]
