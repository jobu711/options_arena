"""Percentile-rank normalization across a scanned universe of tickers.

Transforms raw indicator values into percentile ranks (0--100) so that
indicators with different scales become comparable.  Inverted indicators
(where higher raw value = worse signal) are flipped after normalization.

All inputs and outputs use :class:`~options_arena.models.scan.IndicatorSignals`
typed model -- never ``dict[str, float]``.
"""

import logging
import math

from options_arena.models.scan import IndicatorSignals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Indicators where higher raw value indicates a worse (less favorable) signal.
# After percentile normalization, these are inverted: value = 100 - value.
INVERTED_INDICATORS: frozenset[str] = frozenset(
    {"bb_width", "atr_pct", "relative_volume", "keltner_width"}
)

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
        kwargs: dict[str, float | None] = {}
        for field in _ALL_FIELDS:
            value: float | None = getattr(signals, field)
            if value is not None and field in INVERTED_INDICATORS:
                kwargs[field] = 100.0 - value
            else:
                kwargs[field] = value
        result[ticker] = IndicatorSignals(**kwargs)
    return result
