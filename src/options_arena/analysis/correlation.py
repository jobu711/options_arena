"""Portfolio correlation matrix computation using log daily returns.

Computes pairwise Pearson correlation coefficients between tickers using
log daily returns. Based on Markowitz (1952) portfolio theory.

Architecture rules:
- Pure computation -- no I/O, no API calls, no database access.
- Imports only from ``models/`` and stdlib/numpy/pandas.
- Input: dict of ticker -> pd.DataFrame with a "Close" column.
- Output: typed ``CorrelationMatrix`` model.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from options_arena.models.correlation import CorrelationMatrix, PairwiseCorrelation

logger = logging.getLogger(__name__)

# Minimum overlapping trading days required for a valid correlation
MIN_OVERLAP_DEFAULT = 30


def compute_correlation_matrix(
    price_data: dict[str, pd.DataFrame],
    min_overlap: int = MIN_OVERLAP_DEFAULT,
) -> CorrelationMatrix:
    """Compute pairwise Pearson correlation matrix from OHLCV DataFrames.

    Parameters
    ----------
    price_data
        Dict mapping ticker symbol to a DataFrame with at least a ``"Close"``
        column and a date-like index. Each DataFrame represents one ticker's
        daily price history.
    min_overlap
        Minimum number of overlapping non-NaN trading days required for a
        valid correlation. Pairs below this threshold are excluded.

    Returns
    -------
    CorrelationMatrix
        Frozen model with all valid pairs, sorted tickers, and UTC timestamp.

    Algorithm
    ---------
    1. Extract "Close" column from each DataFrame.
    2. Build a combined DataFrame (inner join on date index).
    3. Compute log daily returns: ``ln(P_t / P_{t-1})``.
    4. For each unique pair ``(i, j)`` where ``i < j``:
       - Count overlapping non-NaN return days.
       - If >= min_overlap: compute Pearson correlation.
       - If < min_overlap: skip pair.
    5. Return ``CorrelationMatrix`` with all valid pairs.
    """
    # Deduplicate tickers while preserving order
    tickers = list(dict.fromkeys(price_data.keys()))

    if len(tickers) < 2:  # noqa: PLR2004
        return CorrelationMatrix(
            tickers=tickers,
            pairs=[],
            computed_at=datetime.now(UTC),
        )

    # Extract close prices into a combined DataFrame
    close_series: dict[str, pd.Series[float]] = {}
    for ticker in tickers:
        df = price_data[ticker]
        if df.empty:
            logger.debug("Empty DataFrame for %s, skipping", ticker)
            continue
        if "Close" not in df.columns:
            logger.debug("No 'Close' column for %s, skipping", ticker)
            continue
        series = df["Close"].dropna()
        if series.empty:
            logger.debug("Empty Close series for %s after dropna, skipping", ticker)
            continue
        close_series[ticker] = series

    # Update tickers to only those with valid close data
    valid_tickers = [t for t in tickers if t in close_series]

    if len(valid_tickers) < 2:  # noqa: PLR2004
        return CorrelationMatrix(
            tickers=valid_tickers,
            pairs=[],
            computed_at=datetime.now(UTC),
        )

    # Combine into a single DataFrame (inner join on dates)
    combined = pd.DataFrame(close_series)

    # Compute log returns: ln(P_t / P_{t-1})
    # Use DataFrame.apply to keep the result as a DataFrame (np.log returns ndarray)
    ratio = combined / combined.shift(1)
    log_returns: pd.DataFrame = ratio.apply(np.log)
    log_returns = log_returns.iloc[1:]  # Drop first row (NaN from shift)

    # Compute pairwise correlations
    pairs: list[PairwiseCorrelation] = []
    sorted_tickers = sorted(valid_tickers)

    for i in range(len(sorted_tickers)):
        for j in range(i + 1, len(sorted_tickers)):
            ticker_a = sorted_tickers[i]
            ticker_b = sorted_tickers[j]

            if ticker_a not in log_returns.columns or ticker_b not in log_returns.columns:
                continue

            # Get pairwise non-NaN returns
            pair_returns = log_returns[[ticker_a, ticker_b]].dropna()
            overlapping = len(pair_returns)

            if overlapping < min_overlap:
                logger.debug(
                    "Pair %s/%s has %d overlapping days (< %d), skipping",
                    ticker_a,
                    ticker_b,
                    overlapping,
                    min_overlap,
                )
                continue

            # Check for zero-variance series (constant returns)
            std_a = float(pair_returns[ticker_a].std())
            std_b = float(pair_returns[ticker_b].std())

            if not math.isfinite(std_a) or std_a == 0.0:
                logger.debug(
                    "Zero variance for %s, skipping pair %s/%s",
                    ticker_a,
                    ticker_a,
                    ticker_b,
                )
                continue
            if not math.isfinite(std_b) or std_b == 0.0:
                logger.debug(
                    "Zero variance for %s, skipping pair %s/%s",
                    ticker_b,
                    ticker_a,
                    ticker_b,
                )
                continue

            # Compute Pearson correlation
            corr = float(pair_returns[ticker_a].corr(pair_returns[ticker_b]))

            if not math.isfinite(corr):
                logger.debug(
                    "Non-finite correlation for %s/%s, skipping",
                    ticker_a,
                    ticker_b,
                )
                continue

            # Clamp to [-1.0, 1.0] for numerical safety
            corr = max(-1.0, min(1.0, corr))

            pairs.append(
                PairwiseCorrelation(
                    ticker_a=ticker_a,
                    ticker_b=ticker_b,
                    correlation=corr,
                    overlapping_days=overlapping,
                )
            )

    return CorrelationMatrix(
        tickers=sorted_tickers,
        pairs=pairs,
        computed_at=datetime.now(UTC),
    )
