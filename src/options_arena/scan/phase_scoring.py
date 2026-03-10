"""Phase 2: Scoring — compute indicators, score universe, classify direction.

Extracted from ``ScanPipeline._phase_scoring()`` as a standalone async function.
All config dependencies are passed as explicit parameters.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import pandas as pd

from options_arena.models import (
    IndicatorSignals,
    NormalizationStats,
    ScanConfig,
    TickerScore,
)
from options_arena.scan.indicators import (
    INDICATOR_REGISTRY,
    IndicatorSpec,
    compute_indicators,
    ohlcv_to_dataframe,
)
from options_arena.scan.models import ScoringResult, UniverseResult
from options_arena.scan.progress import ProgressCallback, ScanPhase
from options_arena.scoring import (
    compute_dimensional_scores,
    compute_direction_signal,
    compute_normalization_stats,
    determine_direction,
    score_universe,
)

# Use pipeline logger name so that tests filtering on "options_arena.scan.pipeline"
# continue to capture phase log messages after extraction.
logger = logging.getLogger("options_arena.scan.pipeline")


async def run_scoring_phase(
    universe_result: UniverseResult,
    progress: ProgressCallback,
    *,
    scan_config: ScanConfig,
    compute_indicators_fn: Callable[[pd.DataFrame, list[IndicatorSpec]], IndicatorSignals]
    | None = None,
) -> ScoringResult:
    """Phase 2: Compute indicators, score universe, determine direction.

    Steps:
        1. For each ticker, convert OHLCV to DataFrame and compute indicators.
        2. Score universe (percentile-rank normalize, composite score).
        3. Classify direction using RAW indicator values (not normalized).
        4. Report progress.

    CRITICAL: ``determine_direction()`` uses **raw** ADX/RSI/SMA values.
    Passing normalized (0--100 percentile) values to absolute thresholds
    (ADX < 15.0) produces meaningless results.

    Args:
        universe_result: Phase 1 output with tickers, OHLCV map, and sector data.
        progress: Callback for reporting per-phase progress.
        scan_config: Scan pipeline configuration slice.
        compute_indicators_fn: Optional override for ``compute_indicators`` (used by
            ``ScanPipeline`` wrappers to preserve test-patching at the pipeline module
            level).

    Returns:
        ``ScoringResult`` with scored tickers and raw signals retained.
    """
    _compute = compute_indicators_fn or compute_indicators
    progress(ScanPhase.SCORING, 0, len(universe_result.ohlcv_map))

    # Step 1: Compute indicators for each ticker
    raw_signals: dict[str, IndicatorSignals] = {}
    for i, (ticker, ohlcv_list) in enumerate(universe_result.ohlcv_map.items()):
        df = ohlcv_to_dataframe(ohlcv_list)
        raw_signals[ticker] = _compute(df, INDICATOR_REGISTRY)
        # Yield to event loop periodically to avoid blocking on large universes
        if i % 100 == 99:
            await asyncio.sleep(0)

    logger.info("Computed indicators for %d tickers", len(raw_signals))

    # Log per-indicator success rates for diagnostics
    if raw_signals:
        indicator_fields = [spec.field_name for spec in INDICATOR_REGISTRY]
        total = len(raw_signals)
        for field_name in indicator_fields:
            populated = sum(1 for s in raw_signals.values() if getattr(s, field_name) is not None)
            rate = populated / total * 100.0
            if rate < 80.0:
                logger.warning(
                    "Indicator %s success rate: %.0f%% (%d/%d)",
                    field_name,
                    rate,
                    populated,
                    total,
                )

    # Step 2: Score universe (returns normalized signals on TickerScore)
    scored: list[TickerScore] = score_universe(raw_signals)

    # Step 3: Classify direction using RAW values (not normalized)
    # and enrich with sector from Phase 1 sector_map
    for ts in scored:
        raw = raw_signals[ts.ticker]
        ts.direction = determine_direction(
            adx=raw.adx or 0.0,
            rsi=raw.rsi or 50.0,
            sma_alignment=raw.sma_alignment or 0.0,
            config=scan_config,
            supertrend=raw.supertrend,
            roc=raw.roc,
        )
        sector = universe_result.sector_map.get(ts.ticker)
        if sector is not None:
            ts.sector = sector
        ig = universe_result.industry_group_map.get(ts.ticker)
        if ig is not None:
            ts.industry_group = ig

    # Step 3b: Compute dimensional scores, direction confidence, and market regime
    for ts in scored:
        try:
            dim_scores = compute_dimensional_scores(ts.signals)
            ts.dimensional_scores = dim_scores

            direction_signal = compute_direction_signal(
                ts.signals,
                ts.direction,
            )
            ts.direction_confidence = direction_signal.confidence
        except Exception:
            logger.warning(
                "Dimensional scoring failed for %s; skipping",
                ts.ticker,
                exc_info=True,
            )

    logger.info(
        "Scoring phase complete: %d tickers scored, classified, and dimensionally scored",
        len(scored),
    )

    # Step 3c: Compute normalization distribution metadata from raw signals
    norm_stats: list[NormalizationStats] = compute_normalization_stats(raw_signals)
    logger.info("Computed normalization stats for %d indicators", len(norm_stats))

    # Step 4: Report progress
    progress(ScanPhase.SCORING, len(universe_result.ohlcv_map), len(universe_result.ohlcv_map))

    return ScoringResult(
        scores=scored,
        raw_signals=raw_signals,
        normalization_stats=norm_stats,
    )
