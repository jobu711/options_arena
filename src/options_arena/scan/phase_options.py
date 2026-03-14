"""Phase 3: Options — fetch chains, compute Greeks, recommend contracts.

Extracted from ``ScanPipeline._phase_options()`` and
``ScanPipeline._process_ticker_options()`` as standalone async functions.
All service and config dependencies are passed as explicit parameters.

Module-level helper functions (``_extract_mp_strike``, ``_merge_signals``,
``_normalize_phase3_signals``, ``_recompute_composite_scores``,
``_recompute_dimensional_scores``) are pure code relocations with no parameter
or logic changes.

``run_options_phase()`` mutates ``ScoringResult.scores`` in-place — it merges
Phase 3 fields into each ``TickerScore.signals``, re-normalizes Phase 3 fields
to 0--100 percentile ranks, and recomputes composite + dimensional scores.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from options_arena.data import Repository
from options_arena.indicators.options_specific import max_pain
from options_arena.indicators.vol_surface import (
    VolSurfaceResult,
    compute_surface_indicators,
    compute_vol_surface,
)
from options_arena.models import (
    IndicatorSignals,
    MarketRegime,
    OptionContract,
    OptionType,
    PricingConfig,
    ScanConfig,
    TickerScore,
)
from options_arena.models.filters import OptionsFilters, UniverseFilters
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.models.metadata import TickerMetadata
from options_arena.scan.indicators import (
    compute_options_indicators,
    compute_phase3_indicators,
    ohlcv_to_dataframe,
)
from options_arena.scan.models import OptionsResult, ScoringResult, UniverseResult
from options_arena.scan.progress import ProgressCallback, ScanPhase
from options_arena.scoring import (
    composite_score,
    compute_dimensional_scores,
    compute_direction_signal,
    percentile_rank_normalize,
    recommend_contracts,
)
from options_arena.scoring.contracts import SurfaceResiduals
from options_arena.services import FredService, MarketDataService, OptionsDataService
from options_arena.services.universe import map_yfinance_to_metadata

# Use pipeline logger name so that tests filtering on "options_arena.scan.pipeline"
# continue to capture phase log messages after extraction.
logger = logging.getLogger("options_arena.scan.pipeline")


# ---------------------------------------------------------------------------
# Callable type aliases — used by ScanPipeline wrappers for test-patching
# ---------------------------------------------------------------------------

# (TickerInfo) -> TickerMetadata
type MapYfinanceFn = Callable[[TickerInfo], TickerMetadata]

# recommend_contracts signature
type RecommendContractsFn = Callable[
    ...,
    list[OptionContract],
]

# process_ticker_options async callable (return type only; args via ...)
type ProcessTickerFn = Callable[
    ...,
    Awaitable[tuple[str, list[OptionContract], date | None, Decimal | None]],
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# DSE field names computed in Phase 3 and merged into TickerScore.signals.
# Also includes put_call_ratio and max_pain_distance (computed per-ticker in
# Phase 3 via compute_options_indicators, not Phase 2).
_PHASE3_FIELDS: tuple[str, ...] = (
    # Options-specific (per-ticker Phase 3)
    "put_call_ratio",
    "max_pain_distance",
    # IV Analytics
    "iv_hv_spread",
    "hv_20d",
    "iv_term_slope",
    "iv_term_shape",
    "put_skew_index",
    "call_skew_index",
    "skew_ratio",
    "vol_regime",
    "ewma_vol_forecast",
    "vol_cone_percentile",
    "vix_correlation",
    "expected_move",
    "expected_move_ratio",
    # Flow Analytics
    "gex",
    "oi_concentration",
    "unusual_activity_score",
    "max_pain_magnet",
    # Second-Order Greeks
    "vanna",
    "charm",
    "vomma",
    # Risk
    "pop",
    "optimal_dte_score",
    "spread_quality",
    "max_loss_ratio",
    # Fundamental
    "earnings_em_ratio",
    "days_to_earnings_impact",
    "short_interest_ratio",
    "div_ex_date_impact",
    "iv_crush_history",
    # Relative Strength & Regime
    "rs_vs_spx",
    "correlation_regime_shift",
    "market_regime",
    "vix_term_structure",
    "risk_on_off_score",
    "sector_relative_momentum",
    # Liquidity
    "chain_spread_pct",
    "chain_oi_depth",
    # Native Quant: HV & Vol Surface
    "hv_yang_zhang",
    "skew_25d",
    "smile_curvature",
    "prob_above_current",
    # Volatility Intelligence: Surface Mispricing
    "iv_surface_residual",
    "surface_fit_r2",
    "surface_is_1d",
)


# Regime classification thresholds (applied to raw market_regime signal, 0-100 scale).
# Not configurable — empirical thresholds for vol-cone-based regime detection.
_REGIME_CRISIS_THRESHOLD: float = 80.0
_REGIME_VOLATILE_THRESHOLD: float = 60.0
_REGIME_MEAN_REVERTING_THRESHOLD: float = 40.0


# ---------------------------------------------------------------------------
# Main Phase 3 entry point
# ---------------------------------------------------------------------------


async def run_options_phase(
    scoring_result: ScoringResult,
    universe_result: UniverseResult,
    progress: ProgressCallback,
    *,
    fred: FredService,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    repository: Repository,
    scan_config: ScanConfig,
    options_filters: OptionsFilters,
    universe_filters: UniverseFilters,
    pricing_config: PricingConfig,
    process_ticker_fn: ProcessTickerFn | None = None,
) -> OptionsResult:
    """Phase 3: Fetch options chains, compute Greeks, recommend contracts.

    Steps:
        1. Apply liquidity pre-filter using OHLCV data from Phase 1.
        2. Take top-N tickers by composite_score.
        3. Fetch risk-free rate from FRED (once for entire scan).
        4. For each top-N ticker, concurrently fetch chains + ticker info,
           then call ``recommend_contracts()`` for 0 or 1 recommendations.
        5. Report progress.

    Per-ticker errors are isolated -- one failed ticker never crashes the scan.

    Mutates ``scoring_result.scores`` in-place: merges Phase 3 fields into
    each ``TickerScore.signals``, re-normalizes Phase 3 fields to 0--100
    percentile ranks, and recomputes composite + dimensional scores.

    Args:
        scoring_result: Phase 2 output with scored tickers and raw signals.
        universe_result: Phase 1 output with OHLCV data.
        progress: Callback for reporting per-phase progress.
        fred: FRED service for risk-free rate.
        market_data: Market data service for OHLCV and ticker info.
        options_data: Options data service for chain fetching.
        repository: Data layer for metadata upserts.
        scan_config: Scan pipeline configuration slice (options_per_ticker_timeout,
            options_concurrency).
        options_filters: Phase 3 option chain filters (top_n, min_dollar_volume,
            exclude_near_earnings_days, min_iv_rank).
        universe_filters: Phase 1 universe filters (min_price, max_price,
            market_cap_tiers).
        pricing_config: Pricing configuration for Greeks computation (delta_target).
        process_ticker_fn: Optional override for per-ticker processing (used by
            ``ScanPipeline`` to route through ``self._process_ticker_options``
            for test-patching compatibility).

    Returns:
        ``OptionsResult`` with recommendations and risk-free rate.
    """
    ohlcv_map = universe_result.ohlcv_map

    # Step 1: Liquidity pre-filter
    min_dollar_volume = options_filters.min_dollar_volume
    min_price = universe_filters.min_price
    max_price = universe_filters.max_price

    liquid_scores: list[TickerScore] = []
    for ts in scoring_result.scores:
        ohlcv_list = ohlcv_map.get(ts.ticker)
        if ohlcv_list is None or len(ohlcv_list) == 0:
            continue

        avg_dollar_volume = sum(float(o.close) * o.volume for o in ohlcv_list) / len(ohlcv_list)
        latest_close = float(ohlcv_list[-1].close)

        if avg_dollar_volume < min_dollar_volume:
            continue
        if latest_close < min_price:
            continue
        if max_price is not None and latest_close > max_price:
            continue

        liquid_scores.append(ts)

    logger.info(
        "Liquidity pre-filter: %d -> %d tickers (min_dv=$%.0f, min_price=$%.0f%s)",
        len(scoring_result.scores),
        len(liquid_scores),
        min_dollar_volume,
        min_price,
        f", max_price=${max_price:.0f}" if max_price is not None else "",
    )

    # Step 2: Top-N selection (scores already sorted descending)
    top_n = options_filters.top_n
    top_scores = liquid_scores[:top_n]

    logger.info("Top-N selection: %d tickers (top_n=%d)", len(top_scores), top_n)

    # Step 3: Fetch risk-free rate (once for entire scan, never raises)
    risk_free_rate: float = await fred.fetch_risk_free_rate()
    logger.info("Risk-free rate: %.4f", risk_free_rate)

    # Step 3b: Extract SPX close series for relative-strength indicators
    # SPX data may be available from Phase 1 OHLCV if "^GSPC" was in the universe,
    # otherwise we attempt a lightweight fetch. Failure is non-fatal.
    spx_close: pd.Series | None = None
    try:
        spx_ohlcv = ohlcv_map.get("^GSPC")
        if spx_ohlcv is not None and len(spx_ohlcv) >= 60:
            spx_df = ohlcv_to_dataframe(spx_ohlcv)
            spx_close = spx_df["close"]
            logger.info("SPX close series available from universe (%d bars)", len(spx_close))
        else:
            # Attempt lightweight fetch for SPX data
            try:
                spx_batch = await market_data.fetch_batch_ohlcv(["^GSPC"], period="1y")
                if (
                    spx_batch.results
                    and spx_batch.results[0].ok
                    and spx_batch.results[0].data is not None
                    and len(spx_batch.results[0].data) >= 60
                ):
                    spx_df = ohlcv_to_dataframe(spx_batch.results[0].data)
                    spx_close = spx_df["close"]
                    logger.info("SPX close series fetched on-demand (%d bars)", len(spx_close))
                else:
                    logger.debug(
                        "SPX fetch unavailable; relative strength indicators will be None"
                    )
            except Exception:
                logger.warning("Failed to fetch SPX data; rs_vs_spx will be None", exc_info=True)
    except Exception:
        logger.warning("Failed to extract SPX close series; rs_vs_spx will be None")

    # Step 4: Per-ticker options processing with semaphore-bounded concurrency
    # A semaphore limits concurrent chains-in-flight, allowing all tickers to
    # start immediately while preventing rate-limiter overload.
    progress(ScanPhase.OPTIONS, 0, len(top_scores))

    per_ticker_timeout = scan_config.options_per_ticker_timeout
    concurrency = scan_config.options_concurrency
    sem = asyncio.Semaphore(concurrency)
    recommendations: dict[str, list[OptionContract]] = {}
    earnings_dates: dict[str, date] = {}
    entry_prices: dict[str, Decimal] = {}
    completed = 0

    # Use override if provided (ScanPipeline routes through self._process_ticker_options)
    _process_fn = process_ticker_fn

    async def _fetch_with_sem(
        ts: TickerScore,
    ) -> tuple[str, list[OptionContract], date | None, Decimal | None]:
        nonlocal completed
        async with sem:
            try:
                if _process_fn is not None:
                    result = await asyncio.wait_for(
                        _process_fn(ts, risk_free_rate, ohlcv_map, spx_close),
                        timeout=per_ticker_timeout,
                    )
                else:
                    result = await asyncio.wait_for(
                        process_ticker_options(
                            ticker_score=ts,
                            risk_free_rate=risk_free_rate,
                            ohlcv_map=ohlcv_map,
                            spx_close=spx_close,
                            market_data=market_data,
                            options_data=options_data,
                            repository=repository,
                            options_filters=options_filters,
                            universe_filters=universe_filters,
                            pricing_config=pricing_config,
                        ),
                        timeout=per_ticker_timeout,
                    )
                return result
            finally:
                completed += 1
                progress(ScanPhase.OPTIONS, completed, len(top_scores))

    all_results: list[
        tuple[str, list[OptionContract], date | None, Decimal | None] | BaseException
    ] = await asyncio.gather(
        *[_fetch_with_sem(ts) for ts in top_scores],
        return_exceptions=True,
    )

    for ts, result in zip(top_scores, all_results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "Options processing failed for %s: %s: %s",
                ts.ticker,
                type(result).__name__,
                result,
            )
        else:
            ticker, contracts, next_earnings, entry_price = result
            if contracts:
                recommendations[ticker] = contracts
            if next_earnings is not None:
                earnings_dates[ticker] = next_earnings
            if entry_price is not None:
                entry_prices[ticker] = entry_price

    logger.info(
        "Options phase complete: %d recommendations from %d tickers",
        len(recommendations),
        len(top_scores),
    )

    # Normalize Phase 3 fields (raw domain values -> 0-100 percentile ranks)
    # so they are on the same scale as Phase 2 normalized fields.
    if len(top_scores) >= 2:
        _normalize_phase3_signals(top_scores)
        _recompute_composite_scores(top_scores)
        _recompute_dimensional_scores(top_scores)
    else:
        logger.info("Skipping Phase 3 re-score: need >=2 tickers for percentile normalization")

    progress(ScanPhase.OPTIONS, len(top_scores), len(top_scores))

    return OptionsResult(
        recommendations=recommendations,
        risk_free_rate=risk_free_rate,
        earnings_dates=earnings_dates,
        entry_prices=entry_prices,
    )


# ---------------------------------------------------------------------------
# Per-ticker helper
# ---------------------------------------------------------------------------


async def process_ticker_options(
    ticker_score: TickerScore,
    risk_free_rate: float,
    ohlcv_map: dict[str, list[OHLCV]],
    spx_close: pd.Series | None,
    *,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    repository: Repository,
    options_filters: OptionsFilters,
    universe_filters: UniverseFilters,
    pricing_config: PricingConfig,
    recommend_contracts_fn: RecommendContractsFn | None = None,
    map_yfinance_fn: MapYfinanceFn | None = None,
) -> tuple[str, list[OptionContract], date | None, Decimal | None]:
    """Fetch chains + ticker info + earnings date for a single ticker.

    Also computes Phase 3 DSE indicators (IV analytics, flow, fundamental,
    relative strength) from chain + ticker data and merges them into the
    ticker's ``IndicatorSignals``.

    Isolated per-ticker: exceptions propagate up to ``asyncio.gather``
    with ``return_exceptions=True``.

    Args:
        ticker_score: Scored ticker with direction set.
        risk_free_rate: Shared risk-free rate for this scan.
        ohlcv_map: Ticker to OHLCV bars from Phase 1 (for close/volume series).
        spx_close: SPX daily close prices for relative strength (None if unavailable).
        market_data: Market data service for ticker info and earnings.
        options_data: Options data service for chain fetching.
        repository: Data layer for metadata upserts.
        options_filters: Phase 3 option chain filters (exclude_near_earnings_days,
            min_iv_rank).
        universe_filters: Phase 1 universe filters (market_cap_tiers).
        pricing_config: Pricing configuration for Greeks computation (delta_target).
        recommend_contracts_fn: Optional override for ``recommend_contracts`` (used
            by ``ScanPipeline`` wrappers for test-patching compatibility).
        map_yfinance_fn: Optional override for ``map_yfinance_to_metadata`` (used
            by ``ScanPipeline`` wrappers for test-patching compatibility).

    Returns:
        Tuple of (ticker, recommended contracts, next_earnings_date | None,
        entry_stock_price | None).
    """
    _recommend = recommend_contracts_fn or recommend_contracts
    _map_yfinance = map_yfinance_fn or map_yfinance_to_metadata
    ticker = ticker_score.ticker

    # Early earnings check — before expensive chain fetch (saves API calls)
    earnings_date: date | None = None
    if options_filters.exclude_near_earnings_days is not None:
        try:
            earnings_date = await market_data.fetch_earnings_date(ticker)
        except Exception:
            logger.warning("Earnings fetch failed for %s", ticker, exc_info=True)

        if earnings_date is not None:
            market_today = datetime.now(ZoneInfo("America/New_York")).date()
            days_to_earnings = (earnings_date - market_today).days
            if 0 <= days_to_earnings <= options_filters.exclude_near_earnings_days:
                logger.info(
                    "Filtered %s: earnings in %d days (<= %d)",
                    ticker,
                    days_to_earnings,
                    options_filters.exclude_near_earnings_days,
                )
                return (ticker, [], earnings_date, None)

    # Fetch chains, ticker info (and earnings if not already fetched) concurrently
    chain_task = options_data.fetch_chain_all_expirations(ticker)
    info_task = market_data.fetch_ticker_info(ticker)

    if earnings_date is None and options_filters.exclude_near_earnings_days is None:
        # Earnings not fetched yet — fetch concurrently with chains
        earnings_task = market_data.fetch_earnings_date(ticker)
        chain_results, ticker_info, earnings_result = await asyncio.gather(
            chain_task, info_task, earnings_task, return_exceptions=True
        )
        if isinstance(earnings_result, BaseException):
            logger.warning("Earnings fetch failed for %s: %s", ticker, earnings_result)
        else:
            earnings_date = earnings_result
    else:
        chain_results, ticker_info = await asyncio.gather(
            chain_task, info_task, return_exceptions=True
        )

    # Re-raise required data failures
    if isinstance(chain_results, BaseException):
        raise chain_results
    if isinstance(ticker_info, BaseException):
        raise ticker_info

    # Pre-scan narrowing: check market cap tier
    if (
        universe_filters.market_cap_tiers
        and ticker_info.market_cap_tier is not None
        and ticker_info.market_cap_tier not in universe_filters.market_cap_tiers
    ):
        logger.info(
            "Filtered %s: market_cap_tier %s not in %s",
            ticker,
            ticker_info.market_cap_tier.value,
            [t.value for t in universe_filters.market_cap_tiers],
        )
        return (ticker, [], earnings_date, ticker_info.current_price)

    # Enrich ticker_score with company_name from ticker info
    ticker_score.company_name = ticker_info.company_name

    # Write back metadata for this ticker
    try:
        metadata = _map_yfinance(ticker_info)
        if ticker_score.sector is None and metadata.sector is not None:
            ticker_score.sector = metadata.sector
        if ticker_score.industry_group is None and metadata.industry_group is not None:
            ticker_score.industry_group = metadata.industry_group
        await repository.upsert_ticker_metadata(metadata)
    except Exception:
        logger.warning("Failed to upsert metadata for %s", ticker_info.ticker, exc_info=True)

    # Flatten all contracts across expirations
    all_contracts: list[OptionContract] = []
    for chain in chain_results:
        all_contracts.extend(chain.contracts)

    entry_stock_price = ticker_info.current_price

    if not all_contracts:
        logger.info("No contracts found for %s", ticker)
        return (ticker, [], earnings_date, entry_stock_price)

    spot = float(ticker_info.current_price)

    # Compute options-specific indicators from full chain before filtering
    options_signals = compute_options_indicators(all_contracts, spot)
    if options_signals.put_call_ratio is not None:
        ticker_score.signals.put_call_ratio = options_signals.put_call_ratio
    if options_signals.max_pain_distance is not None:
        ticker_score.signals.max_pain_distance = options_signals.max_pain_distance

    # Compute max_pain strike directly from chain for Phase 3 indicators
    mp_strike = _extract_mp_strike(all_contracts)

    # Compute Phase 3 DSE indicators (IV analytics, flow, fundamental, RS)
    ohlcv_list = ohlcv_map.get(ticker)
    vol_result: VolSurfaceResult | None = None
    vs_strikes: np.ndarray | None = None
    vs_ivs: np.ndarray | None = None
    vs_dtes: np.ndarray | None = None
    if ohlcv_list is not None and len(ohlcv_list) > 0:
        try:
            ticker_df = ohlcv_to_dataframe(ohlcv_list)
            close_series: pd.Series = ticker_df["close"]

            # Compute vol surface from option chain (graceful degradation on failure)
            try:
                if len(all_contracts) >= 3:
                    vs_strikes = np.array([float(c.strike) for c in all_contracts], dtype=float)
                    vs_ivs = np.array([c.market_iv for c in all_contracts], dtype=float)
                    vs_dtes = np.array([float(c.dte) for c in all_contracts], dtype=float)
                    vs_types = np.array(
                        [1.0 if c.option_type == OptionType.CALL else -1.0 for c in all_contracts],
                        dtype=float,
                    )
                    vol_result = compute_vol_surface(
                        vs_strikes, vs_ivs, vs_dtes, vs_types, spot, risk_free_rate,
                        dividend_yield=ticker_info.dividend_yield,
                    )
            except Exception:
                logger.warning(
                    "Vol surface computation failed for %s; continuing without",
                    ticker,
                    exc_info=True,
                )

            dse_signals = compute_phase3_indicators(
                contracts=all_contracts,
                spot=spot,
                close_series=close_series,
                dividend_yield=ticker_info.dividend_yield,
                next_earnings=earnings_date,
                mp_strike=mp_strike,
                spx_close=spx_close,
                ohlcv_df=ticker_df,
                vol_result=vol_result,
            )

            # Merge DSE signals into the ticker's existing signals
            _merge_signals(ticker_score.signals, dse_signals)

            logger.debug(
                "Phase 3 DSE indicators computed for %s",
                ticker,
            )
        except Exception:
            logger.warning(
                "Phase 3 DSE indicators failed for %s; continuing with partial signals",
                ticker,
                exc_info=True,
            )

    # Pre-scan narrowing: IV rank filter (applied after Phase 3 DSE populates iv_rank)
    if options_filters.min_iv_rank is not None:
        iv_rank = ticker_score.signals.iv_rank
        if iv_rank is None or iv_rank < options_filters.min_iv_rank:
            logger.info(
                "Filtered %s: iv_rank %s < min_iv_rank %.1f",
                ticker,
                iv_rank,
                options_filters.min_iv_rank,
            )
            return (ticker, [], earnings_date, entry_stock_price)

    # Build surface residuals mapping for direction-aware delta tiebreaker.
    # z_scores align with *filtered* contracts (valid_mask), not all_contracts.
    # Reconstruct the same valid_mask used inside compute_vol_surface() to map
    # z_scores[j] back to the correct all_contracts[i].
    _surface_residuals: SurfaceResiduals | None = None
    if (
        vol_result is not None
        and vol_result.z_scores is not None
        and vs_ivs is not None
        and vs_strikes is not None
        and vs_dtes is not None
    ):
        valid_mask = (
            np.isfinite(vs_ivs) & (vs_ivs > 0.0) & np.isfinite(vs_strikes) & np.isfinite(vs_dtes)
        )
        valid_indices = np.where(valid_mask)[0]
        _surface_residuals = {}
        for j, orig_idx in enumerate(valid_indices):
            if j < len(vol_result.z_scores) and math.isfinite(vol_result.z_scores[j]):
                c = all_contracts[int(orig_idx)]
                _surface_residuals[(c.strike, c.expiration)] = float(vol_result.z_scores[j])

    recommended = _recommend(
        contracts=all_contracts,
        direction=ticker_score.direction,
        spot=spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=ticker_info.dividend_yield,
        filters=options_filters,
        delta_target=pricing_config.delta_target,
        surface_residuals=_surface_residuals,
    )

    # Compute surface indicators for the recommended contract
    if recommended and vol_result is not None and vs_strikes is not None and vs_dtes is not None:
        try:
            first_rec = recommended[0]
            surf_ind = compute_surface_indicators(
                result=vol_result,
                contract_strike=float(first_rec.strike),
                contract_dte=float(first_rec.dte),
                strikes=vs_strikes,
                dtes=vs_dtes,
            )
            if surf_ind.iv_surface_residual is not None:
                ticker_score.signals.iv_surface_residual = surf_ind.iv_surface_residual
            if surf_ind.surface_fit_r2 is not None:
                ticker_score.signals.surface_fit_r2 = surf_ind.surface_fit_r2
            if surf_ind.surface_is_1d is not None:
                ticker_score.signals.surface_is_1d = 1.0 if surf_ind.surface_is_1d else 0.0
        except Exception:
            logger.warning(
                "Surface indicators failed for %s; continuing without",
                ticker,
                exc_info=True,
            )

    return (ticker, recommended, earnings_date, entry_stock_price)


# ---------------------------------------------------------------------------
# Module-level helper functions (pure relocations — no parameter changes)
# ---------------------------------------------------------------------------


def _extract_mp_strike(contracts: list[OptionContract]) -> float | None:
    """Extract the max-pain strike from an option chain.

    Reuses the max_pain indicator function from ``indicators.options_specific``
    to find the strike where total option holder pain is maximized (minimum
    payout to option holders).

    Returns ``None`` if the chain has no OI data or computation fails.
    """
    strike_oi: dict[float, tuple[int, int]] = {}
    for c in contracts:
        s = float(c.strike)
        call_oi, put_oi = strike_oi.get(s, (0, 0))
        if c.option_type == OptionType.CALL:
            call_oi += c.open_interest
        else:
            put_oi += c.open_interest
        strike_oi[s] = (call_oi, put_oi)

    if not strike_oi:
        return None

    total_oi = sum(co + po for co, po in strike_oi.values())
    if total_oi <= 0:
        return None

    try:
        sorted_strikes = sorted(strike_oi.keys())
        strikes_series = pd.Series(sorted_strikes, dtype=float)
        call_oi_series = pd.Series([strike_oi[s][0] for s in sorted_strikes], dtype=float)
        put_oi_series = pd.Series([strike_oi[s][1] for s in sorted_strikes], dtype=float)
        mp = max_pain(strikes_series, call_oi_series, put_oi_series)
        if math.isfinite(mp) and not np.isnan(mp):
            return float(mp)
    except Exception:
        logger.warning("max_pain strike extraction failed", exc_info=True)

    return None


def _merge_signals(
    target: IndicatorSignals,
    source: IndicatorSignals,
) -> None:
    """Merge non-None fields from *source* into *target*.

    Only DSE fields (Phase 3 indicators) are merged.  Original Phase 2 fields
    on *target* are never overwritten.  Mutates *target* in place.
    """
    for field_name in _PHASE3_FIELDS:
        value = getattr(source, field_name, None)
        if value is not None:
            setattr(target, field_name, value)


def _normalize_phase3_signals(
    top_scores: list[TickerScore],
) -> None:
    """Percentile-rank normalize Phase 3 fields across the top-N universe.

    Phase 3 indicators are computed per-ticker and produce RAW domain values
    (e.g., ``iv_hv_spread=0.15``, ``gex=50000``).  Phase 2 indicators on
    ``TickerScore.signals`` are already percentile-ranked 0--100.  Mixing
    scales breaks dimensional scoring.

    This function:
    1. Extracts Phase 3 fields into a sub-universe of ``IndicatorSignals``.
    2. Runs ``percentile_rank_normalize()`` on those fields only.
    3. Writes the normalized values back, overwriting raw Phase 3 values.

    Phase 2 fields are untouched because only Phase 3 fields are populated
    in the sub-universe (all others are ``None`` and excluded from ranking).

    Mutates ``top_scores`` in place.
    """
    if len(top_scores) < 2:
        return  # normalization needs >= 2 tickers to rank

    phase3_field_set = frozenset(_PHASE3_FIELDS)

    # Step 1: Extract Phase 3 fields into a sub-universe
    sub_universe: dict[str, IndicatorSignals] = {}
    for ts in top_scores:
        kwargs: dict[str, float | None] = {}
        for field_name in IndicatorSignals.model_fields:
            if field_name in phase3_field_set:
                kwargs[field_name] = getattr(ts.signals, field_name)
            else:
                kwargs[field_name] = None
        sub_universe[ts.ticker] = IndicatorSignals(**kwargs)

    # Step 2: Percentile-rank normalize across the top-N universe
    normalized = percentile_rank_normalize(sub_universe)

    # Step 3: Write normalized values back into each ticker's signals
    for ts in top_scores:
        norm_signals = normalized.get(ts.ticker)
        if norm_signals is None:
            continue
        for field_name in _PHASE3_FIELDS:
            norm_value: float | None = getattr(norm_signals, field_name)
            if norm_value is not None:
                setattr(ts.signals, field_name, norm_value)

    logger.info(
        "Phase 3 normalization complete: %d fields across %d tickers",
        len(_PHASE3_FIELDS),
        len(top_scores),
    )


def _recompute_composite_scores(
    top_scores: list[TickerScore],
) -> None:
    """Recompute composite scores after Phase 3 normalization.

    Phase 2 composite scores are computed with only 14 of 18 indicators
    (options-specific fields are ``None``).  After Phase 3 populates and
    normalizes ``put_call_ratio``, ``max_pain_distance``, ``iv_rank``, and
    ``iv_percentile``, the composite score should be recomputed so it
    reflects all 18 weighted indicators.

    Mutates ``top_scores`` in place.

    Note: Phase 3 fields are percentile-ranked but NOT inverted because none of
    them appear in ``INVERTED_INDICATORS`` (which only contains volatility-width
    Phase 2 fields).  The already-inverted Phase 2 fields on ``ts.signals`` are
    preserved as-is, so ``composite_score()`` receives correct values for all 18.
    """
    for ts in top_scores:
        try:
            ts.composite_score = composite_score(ts.signals)
        except Exception:
            logger.warning(
                "Composite recompute failed for %s; keeping Phase 2 score",
                ts.ticker,
                exc_info=True,
            )

    # Re-sort by updated composite score (descending)
    top_scores.sort(key=lambda ts: ts.composite_score, reverse=True)
    logger.info("Phase 3 composite recompute complete for %d tickers", len(top_scores))


def _recompute_dimensional_scores(
    top_scores: list[TickerScore],
) -> None:
    """Refresh dimensional scores, direction confidence, and market regime after Phase 3.

    The Phase 2 computation only saw Phase 2 fields.  Now that Phase 3 fields
    (including ``market_regime`` from vol cone data) are also normalized 0--100,
    recomputing gives dimensional scoring the full picture.

    Mutates ``top_scores`` in place.
    """
    for ts in top_scores:
        try:
            dim_scores = compute_dimensional_scores(ts.signals)
            ts.dimensional_scores = dim_scores

            direction_signal = compute_direction_signal(
                ts.signals,
                ts.direction,
            )
            ts.direction_confidence = direction_signal.confidence

            # Derive market regime from signals.market_regime (computed in Phase 3)
            regime_val = ts.signals.market_regime
            if regime_val is not None and math.isfinite(regime_val):
                if regime_val >= _REGIME_CRISIS_THRESHOLD:
                    ts.market_regime = MarketRegime.CRISIS
                elif regime_val >= _REGIME_VOLATILE_THRESHOLD:
                    ts.market_regime = MarketRegime.VOLATILE
                elif regime_val >= _REGIME_MEAN_REVERTING_THRESHOLD:
                    ts.market_regime = MarketRegime.MEAN_REVERTING
                else:
                    ts.market_regime = MarketRegime.TRENDING
        except Exception:
            logger.warning(
                "Dimensional re-scoring failed for %s; keeping Phase 2 values",
                ts.ticker,
                exc_info=True,
            )
