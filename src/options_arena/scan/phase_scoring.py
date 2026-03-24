"""Phase 2: Scoring — compute indicators, score universe, classify direction.

Extracted from ``ScanPipeline._phase_scoring()`` as a standalone async function.
All config dependencies are passed as explicit parameters.

Also provides ``_compute_ml_indicators()`` which enriches ``IndicatorSignals``
with GARCH volatility forecasts and Markov-switching regime detection
when the corresponding ML feature flags are enabled on ``ScanConfig.ml``.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from options_arena.models import (
    IndicatorSignals,
    NormalizationStats,
    ScanConfig,
    TickerScore,
)
from options_arena.models.attribution import Prediction, PredictionSource
from options_arena.models.config import MLConfig
from options_arena.models.market_data import OHLCV
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

    # Step 1b: Compute ML indicators (GARCH/EGARCH, Markov regime) when enabled
    if scan_config.ml.enable_garch or scan_config.ml.enable_markov:
        await _compute_ml_indicators(
            raw_signals=raw_signals,
            ohlcv_map=universe_result.ohlcv_map,
            ml_config=scan_config.ml,
        )

    # Step 1c: ML regime classification (GBM) when enabled
    if scan_config.ml.enable_ml_regime:
        _compute_ml_regime_classifications(raw_signals)

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

    # Step 3c: Record scan direction predictions for attribution ledger
    scan_predictions: list[Prediction] = []
    for ts in scored:
        try:
            raw_ctx: IndicatorSignals | None = raw_signals.get(ts.ticker)
            scan_predictions.append(
                Prediction(
                    scan_run_id=0,  # placeholder — orchestrator sets real ID
                    ticker=ts.ticker,
                    source=PredictionSource.SCAN_DIRECTION,
                    predicted_direction=ts.direction,
                    confidence=ts.direction_confidence or 0.5,  # fallback if None
                    adx=raw_ctx.adx if raw_ctx else None,
                    iv_rank=raw_ctx.iv_rank if raw_ctx else None,  # expected None in Phase 2
                    atr_pct=raw_ctx.atr_pct if raw_ctx else None,
                    rsi=raw_ctx.rsi if raw_ctx else None,
                    created_at=datetime.now(UTC),
                )
            )
        except Exception:
            logger.warning("Failed to create scan prediction for %s", ts.ticker)

    logger.info(
        "Scoring phase complete: %d tickers scored, classified, and dimensionally scored",
        len(scored),
    )

    # Step 3d: Compute normalization distribution metadata from raw signals
    norm_stats: list[NormalizationStats] = compute_normalization_stats(raw_signals)
    logger.info("Computed normalization stats for %d indicators", len(norm_stats))

    # Step 4: Report progress
    progress(ScanPhase.SCORING, len(universe_result.ohlcv_map), len(universe_result.ohlcv_map))

    return ScoringResult(
        scores=scored,
        raw_signals=raw_signals,
        normalization_stats=norm_stats,
        scan_predictions=scan_predictions,
    )


# ---------------------------------------------------------------------------
# ML indicator computation (GARCH, Markov regime)
# ---------------------------------------------------------------------------

# Timeout for each ML computation (seconds). GARCH fitting is CPU-bound and
# can take several seconds on long return series.
_ML_COMPUTATION_TIMEOUT: float = 30.0

# Markov regime label mapping to float for IndicatorSignals storage
_MARKOV_LABEL_TO_FLOAT: dict[str, float] = {
    "low_vol": 0.0,
    "normal": 1.0,
    "high_vol": 2.0,
}


async def _compute_ml_indicators(
    *,
    raw_signals: dict[str, IndicatorSignals],
    ohlcv_map: dict[str, list[OHLCV]],
    ml_config: MLConfig,
) -> None:
    """Enrich raw indicator signals with ML-based indicators.

    Computes GARCH volatility forecasts and Markov-switching regime
    detection for each ticker when the corresponding feature flags are enabled.
    All computations run via ``asyncio.to_thread()`` with a 30-second timeout
    since ``arch`` and ``statsmodels`` are synchronous and CPU-bound.

    Mutates ``raw_signals`` in place — sets ``vol_forecast_garch``,
    ``iv_vs_forecast_spread``, ``regime_markov_label``,
    and ``regime_transition_prob`` on each ticker's ``IndicatorSignals``.

    Args:
        raw_signals: Ticker -> IndicatorSignals mapping (mutated in place).
        ohlcv_map: Ticker -> OHLCV bars from Phase 1.
        ml_config: ML feature flags and hyperparameters.
    """
    # Build per-ticker ML tasks and run them concurrently via asyncio.gather
    # to avoid O(tickers) serial wall-clock time.
    eligible: list[tuple[str, IndicatorSignals, pd.Series]] = []
    for ticker, signals in raw_signals.items():
        ohlcv_list = ohlcv_map.get(ticker)
        if ohlcv_list is None or len(ohlcv_list) < 252:
            continue

        df = ohlcv_to_dataframe(ohlcv_list)
        close_series: pd.Series = df["close"]

        # Build percentage log returns for GARCH and Markov models
        close_arr = close_series.to_numpy(dtype=float)
        log_returns = np.log(close_arr[1:] / close_arr[:-1]) * 100.0
        returns_series = pd.Series(log_returns, index=close_series.index[1:])
        eligible.append((ticker, signals, returns_series))

    if not eligible:
        logger.info("ML indicators computed for 0 tickers")
        return

    async def _process_ticker(
        signals: IndicatorSignals,
        returns_series: pd.Series,
    ) -> None:
        if ml_config.enable_garch:
            await _compute_garch_for_ticker(
                signals=signals,
                returns_series=returns_series,
                ml_config=ml_config,
            )
        if ml_config.enable_markov:
            await _compute_markov_for_ticker(
                signals=signals,
                returns_series=returns_series,
                ml_config=ml_config,
            )

    tasks = [_process_ticker(signals, returns) for _, signals, returns in eligible]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            ticker = eligible[i][0]
            logger.warning("ML indicator computation failed for %s: %s", ticker, result)

    logger.info("ML indicators computed for %d tickers", len(eligible))


async def _compute_garch_for_ticker(
    *,
    signals: IndicatorSignals,
    returns_series: pd.Series,
    ml_config: MLConfig,
) -> None:
    """Compute GARCH forecast for a single ticker.

    Uses ``asyncio.to_thread()`` + ``wait_for(timeout=30)`` since ``arch``
    model fitting is synchronous and CPU-bound. On timeout or failure, the
    fields remain ``None`` (graceful degradation).
    """
    from options_arena.indicators.vol_forecast import compute_garch_forecast

    # GARCH(p,q) forecast
    try:
        garch_vol: float | None = await asyncio.wait_for(
            asyncio.to_thread(
                compute_garch_forecast,
                returns_series,
                ml_config.garch_p,
                ml_config.garch_q,
            ),
            timeout=_ML_COMPUTATION_TIMEOUT,
        )
        if garch_vol is not None and math.isfinite(garch_vol):
            signals.vol_forecast_garch = garch_vol

            # Compute IV vs GARCH forecast spread when both are available.
            # iv_rank serves as a proxy for current market IV level (0-100 scale,
            # not directly comparable) — instead use ewma_vol_forecast or hv_20d
            # as a crude market IV proxy if atm_iv is unavailable at this phase.
            # The actual ATM IV is populated in Phase 3; for Phase 2, we use
            # ewma_vol_forecast (annualized) if available.
            ewma = signals.ewma_vol_forecast
            if ewma is not None and math.isfinite(ewma):
                spread = ewma - garch_vol
                if math.isfinite(spread):
                    signals.iv_vs_forecast_spread = spread
    except TimeoutError:
        logger.warning("GARCH forecast timed out (%.0fs)", _ML_COMPUTATION_TIMEOUT)
    except Exception:
        logger.warning("GARCH forecast failed", exc_info=True)


def _compute_ml_regime_classifications(
    raw_signals: dict[str, IndicatorSignals],
) -> None:
    """Enrich raw signals with GBM regime classification confidence.

    Calls ``classify_regime_ml()`` for each ticker and stores the confidence
    value on ``IndicatorSignals.ml_regime_confidence``. Failures are silently
    skipped (confidence remains ``None``).

    Args:
        raw_signals: Ticker -> IndicatorSignals mapping (mutated in place).
    """
    from options_arena.indicators.regime_ml import classify_regime_ml

    classified = 0
    for signals in raw_signals.values():
        result = classify_regime_ml(signals)
        if result is not None:
            signals.ml_regime_confidence = result.confidence
            classified += 1

    logger.info(
        "ML regime classification computed for %d/%d tickers",
        classified,
        len(raw_signals),
    )


async def _compute_markov_for_ticker(
    *,
    signals: IndicatorSignals,
    returns_series: pd.Series,
    ml_config: MLConfig,
) -> None:
    """Compute Markov-switching regime for a single ticker.

    Uses ``asyncio.to_thread()`` + ``wait_for(timeout=30)`` since
    ``statsmodels`` Markov regression fitting is synchronous and CPU-bound.
    On timeout or failure, the fields remain ``None``.
    """
    from options_arena.indicators.regime_ml import compute_markov_regime

    try:
        # Use decimal returns (not percentage) for Markov model
        decimal_returns = returns_series / 100.0
        result = await asyncio.wait_for(
            asyncio.to_thread(
                compute_markov_regime,
                decimal_returns,
                ml_config.markov_n_regimes,
            ),
            timeout=_ML_COMPUTATION_TIMEOUT,
        )
        if result is not None:
            label_float = _MARKOV_LABEL_TO_FLOAT.get(result.regime_label)
            if label_float is not None:
                signals.regime_markov_label = label_float

            # Transition probability: probability of staying in current regime
            current = result.current_regime
            if 0 <= current < len(result.transition_matrix):
                stay_prob = result.transition_matrix[current][current]
                if math.isfinite(stay_prob):
                    signals.regime_transition_prob = stay_prob
    except TimeoutError:
        logger.warning("Markov regime timed out (%.0fs)", _ML_COMPUTATION_TIMEOUT)
    except Exception:
        logger.warning("Markov regime detection failed", exc_info=True)
