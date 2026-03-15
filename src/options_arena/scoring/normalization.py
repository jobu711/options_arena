"""Percentile-rank normalization across a scanned universe of tickers.

Transforms raw indicator values into percentile ranks (0--100) so that
indicators with different scales become comparable.  Inverted indicators
(where higher raw value = worse signal) are flipped after normalization.

Also provides :func:`normalize_single_ticker` for ad-hoc single-ticker
normalization via domain-bound linear scaling (used by the debate route
when no scan universe is available for percentile ranking).

All inputs and outputs use :class:`~options_arena.models.scan.IndicatorSignals`
typed model -- never ``dict[str, float]``.
"""

import logging
import math
from datetime import UTC, datetime

import numpy as np

from options_arena.models.analytics import NormalizationStats
from options_arena.models.scan import IndicatorSignals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Indicators where higher raw value indicates a worse (less favorable) signal.
# After percentile normalization, these are inverted: value = 100 - value.
#
# NOTE: ``relative_volume`` is intentionally NOT inverted.  High relative volume
# signals institutional attention and better options liquidity — desirable traits
# for an options scanner.  Volatility-width and liquidity-spread indicators are
# inverted because wider ranges/spreads are less favorable.
INVERTED_INDICATORS: frozenset[str] = frozenset(
    {
        "bb_width",
        "atr_pct",
        "keltner_width",
        "chain_spread_pct",
    }
)

# Domain bounds for single-ticker linear scaling.
# Each entry maps an ``IndicatorSignals`` field name to its
# ``(min_domain, max_domain)`` natural range.  Values outside these bounds
# are clamped to [0, 100] after scaling.
DOMAIN_BOUNDS: dict[str, tuple[float, float]] = {
    "rsi": (0.0, 100.0),
    "stochastic_rsi": (0.0, 100.0),
    "williams_r": (-100.0, 0.0),
    "adx": (0.0, 100.0),
    "roc": (-50.0, 50.0),
    "supertrend": (-1.0, 1.0),
    "macd": (-5.0, 5.0),
    "bb_width": (0.0, 0.5),
    "atr_pct": (0.0, 0.1),
    "keltner_width": (0.0, 0.5),
    "obv": (-1e7, 1e7),
    "ad": (-1e7, 1e7),
    "relative_volume": (0.0, 5.0),
    "sma_alignment": (-1.0, 1.0),
    "vwap_deviation": (-0.1, 0.1),
    "iv_rank": (0.0, 100.0),
    "iv_percentile": (0.0, 100.0),
    "put_call_ratio": (0.0, 3.0),
    "max_pain_distance": (-0.2, 0.2),
    "chain_spread_pct": (0.0, 30.0),
    "chain_oi_depth": (0.0, 6.0),
    "skew_25d": (-0.15, 0.15),
    "smile_curvature": (-10.0, 10.0),
    "hurst_exponent": (0.0, 1.0),
}

# All indicator field names from IndicatorSignals, cached once at import time.
_ALL_FIELDS: tuple[str, ...] = tuple(IndicatorSignals.model_fields.keys())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_active_indicators(universe: dict[str, IndicatorSignals]) -> set[str]:
    """Return indicator field names that have at least one non-None value.

    Scans every ticker in *universe* and collects field names where at least
    one ticker has a finite (non-NaN, non-None) value.

    Args:
        universe: Mapping of ticker symbol to ``IndicatorSignals``.

    Returns:
        Set of field names with at least one valid value across the universe.
    """
    active: set[str] = set()
    for signals in universe.values():
        for field in _ALL_FIELDS:
            if field in active:
                continue
            value: float | None = getattr(signals, field)
            if value is not None and math.isfinite(value):
                active.add(field)
    return active


def percentile_rank_normalize(
    universe: dict[str, IndicatorSignals],
) -> dict[str, IndicatorSignals]:
    """Convert raw indicator values to percentile ranks across the universe.

    For each indicator field, all tickers with a non-None finite value are
    ranked.  Ties receive the average rank of the tied positions.  The
    percentile is scaled to [0, 100]:

    * **n == 1**: the single ticker receives 50.0 (midpoint).
    * **n >= 2**: ``(rank - 1) / (n - 1) * 100``, yielding 0.0 for the
      lowest and 100.0 for the highest.

    Tickers missing an indicator (``None`` or ``NaN``) are excluded from
    that indicator's ranking and receive ``None`` in the output, so
    downstream scoring only weights indicators the ticker actually has data
    for.

    Args:
        universe: Mapping of ticker symbol to raw ``IndicatorSignals``.

    Returns:
        Mapping of ticker symbol to percentile-ranked ``IndicatorSignals``.
    """
    if not universe:
        return {}

    # Accumulate per-ticker kwargs for building output IndicatorSignals.
    result_kwargs: dict[str, dict[str, float | None]] = {ticker: {} for ticker in universe}

    for field in _ALL_FIELDS:
        # Collect (ticker, value) pairs where value is finite.
        ticker_values: list[tuple[str, float]] = []
        for ticker, signals in universe.items():
            value: float | None = getattr(signals, field)
            if value is not None and math.isfinite(value):
                ticker_values.append((ticker, value))

        count = len(ticker_values)

        if count == 0:
            # Universally missing -- leave as None for all tickers.
            logger.debug(
                "Indicator '%s' has no valid values -- excluded from normalization",
                field,
            )
            for ticker in universe:
                result_kwargs[ticker][field] = None
            continue

        # Sort ascending by value to assign ranks.
        ticker_values.sort(key=lambda tv: tv[1])

        # Assign ranks with tie handling: identical values get average rank.
        ranks: dict[str, float] = {}
        idx = 0
        while idx < count:
            run_start = idx
            while idx < count and ticker_values[idx][1] == ticker_values[run_start][1]:
                idx += 1
            # Average of 1-based positions in the run.
            avg_rank = (run_start + 1 + idx) / 2.0
            for j in range(run_start, idx):
                ranks[ticker_values[j][0]] = avg_rank

        # Convert ranks to percentiles.
        for ticker in universe:
            if ticker in ranks:
                percentile = 50.0 if count == 1 else (ranks[ticker] - 1.0) / (count - 1.0) * 100.0
                result_kwargs[ticker][field] = percentile
            else:
                result_kwargs[ticker][field] = None

    return {ticker: IndicatorSignals(**kwargs) for ticker, kwargs in result_kwargs.items()}


def invert_indicators(
    normalized: dict[str, IndicatorSignals],
) -> dict[str, IndicatorSignals]:
    """Flip inverted indicators so that higher percentile = better signal.

    For indicators in :data:`INVERTED_INDICATORS`, the percentile rank is
    replaced with ``100 - value``.  ``None`` values are preserved.

    Args:
        normalized: Percentile-ranked indicators from
            :func:`percentile_rank_normalize`.

    Returns:
        Same structure with inverted indicators flipped.
    """
    result: dict[str, IndicatorSignals] = {}
    for ticker, signals in normalized.items():
        result[ticker] = _invert_single(signals)
    return result


def _invert_single(signals: IndicatorSignals) -> IndicatorSignals:
    """Flip inverted indicators on a single ``IndicatorSignals`` instance.

    Shared by :func:`invert_indicators` (universe) and
    :func:`normalize_single_ticker` (ad-hoc single ticker).
    """
    kwargs: dict[str, float | None] = {}
    for field in _ALL_FIELDS:
        value: float | None = getattr(signals, field)
        if value is not None and field in INVERTED_INDICATORS:
            kwargs[field] = 100.0 - value
        else:
            kwargs[field] = value
    return IndicatorSignals(**kwargs)


def normalize_single_ticker(signals: IndicatorSignals) -> IndicatorSignals:
    """Normalize raw indicator signals to 0--100 via domain-bound linear scaling.

    Used for ad-hoc single-ticker debates where no universe exists for
    percentile ranking.  Each indicator with a known domain range in
    :data:`DOMAIN_BOUNDS` is linearly scaled:

    .. math::

        normalized = \\frac{value - lo}{hi - lo} \\times 100

    Values outside ``[lo, hi]`` are clamped to ``[0, 100]``.  ``None`` and
    non-finite values are passed through unchanged.  After scaling, inverted
    indicators (from :data:`INVERTED_INDICATORS`) are flipped via
    :func:`_invert_single`.

    Args:
        signals: Raw ``IndicatorSignals`` from indicator computation.

    Returns:
        New ``IndicatorSignals`` with domain-scaled values in ``[0, 100]``.
    """
    update: dict[str, float | None] = {}
    for field, (lo, hi) in DOMAIN_BOUNDS.items():
        value: float | None = getattr(signals, field, None)
        if value is not None and math.isfinite(value):
            update[field] = max(0.0, min(100.0, (value - lo) / (hi - lo) * 100.0))
        else:
            update[field] = value
    result = signals.model_copy(update=update)
    return _invert_single(result)


def compute_normalization_stats(
    raw_signals: dict[str, IndicatorSignals],
) -> list[NormalizationStats]:
    """Compute per-indicator distribution metadata from raw signals.

    For each indicator field on ``IndicatorSignals``, collects all non-None,
    finite values across all tickers and computes min, max, median, mean,
    std_dev, p25, p75.  Indicators with zero valid values are skipped.

    Returns ``NormalizationStats`` with ``scan_run_id=0`` (placeholder) and
    ``created_at=now(UTC)``.  The pipeline sets the real ``scan_run_id`` at
    persist time by reconstructing instances with the correct ID.

    Args:
        raw_signals: Mapping of ticker symbol to raw ``IndicatorSignals``.

    Returns:
        List of ``NormalizationStats``, one per active indicator.
    """
    if not raw_signals:
        return []

    active = get_active_indicators(raw_signals)
    if not active:
        return []

    now = datetime.now(UTC)
    stats_list: list[NormalizationStats] = []

    for field_name in sorted(active):
        # Collect all finite, non-None values for this indicator
        values: list[float] = []
        for signals in raw_signals.values():
            v: float | None = getattr(signals, field_name)
            if v is not None and math.isfinite(v):
                values.append(v)

        if not values:
            continue

        arr = np.array(values, dtype=np.float64)
        stats_list.append(
            NormalizationStats(
                scan_run_id=0,
                indicator_name=field_name,
                ticker_count=len(values),
                min_value=float(np.min(arr)),
                max_value=float(np.max(arr)),
                median_value=float(np.median(arr)),
                mean_value=float(np.mean(arr)),
                std_dev=float(np.std(arr, ddof=1)) if len(values) >= 2 else None,
                p25=float(np.percentile(arr, 25)),
                p75=float(np.percentile(arr, 75)),
                created_at=now,
            )
        )

    logger.info(
        "Computed normalization stats for %d active indicators across %d tickers",
        len(stats_list),
        len(raw_signals),
    )
    return stats_list
