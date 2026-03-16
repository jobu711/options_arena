"""Markov-switching regime detection via Hamilton (1989) regime-switching model.

Uses ``statsmodels.tsa.regime_switching.markov_regression.MarkovRegression`` to
identify latent volatility regimes in return series. Complements the rule-based
``classify_market_regime()`` in ``regime.py`` with a statistical approach.

Rules:
- Takes pandas Series input, returns NamedTuple | None.
- NO Pydantic models, NO API calls -- pure math on pre-fetched data.
- Guarded import: returns None when ``statsmodels`` not installed.
- Returns None on insufficient data (<252 obs) or convergence failure.

Reference: Hamilton, J.D. (1989) "A New Approach to the Economic Analysis of
Nonstationary Time Series and the Business Cycle", Econometrica, 57(2), 357-384.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

from options_arena.models.enums import MarketRegime

logger = logging.getLogger(__name__)

# Minimum observations required for regime estimation (1 year of trading days)
_MIN_OBSERVATIONS: int = 252

# Default number of regimes (low_vol, normal, high_vol)
_DEFAULT_K_REGIMES: int = 3

# Number of random search repetitions for robust convergence
_SEARCH_REPS: int = 20

# Regime label mapping by variance rank (ascending)
_REGIME_LABELS: list[str] = ["low_vol", "normal", "high_vol"]

# Map regime labels to MarketRegime enum values
_REGIME_TO_MARKET_REGIME: dict[str, MarketRegime] = {
    "low_vol": MarketRegime.MEAN_REVERTING,
    "normal": MarketRegime.TRENDING,
    "high_vol": MarketRegime.VOLATILE,
}


class MarkovRegimeOutput(NamedTuple):
    """Output of Markov-switching regime detection.

    Attributes:
        current_regime: Index of the most probable current regime (0-indexed).
        regime_probabilities: Smoothed probabilities for each regime at the last observation.
        transition_matrix: k x k regime transition probability matrix (row-stochastic).
        regime_label: Human-readable label for the current regime
            (``"low_vol"``, ``"normal"``, ``"high_vol"``).
    """

    current_regime: int
    regime_probabilities: list[float]
    transition_matrix: list[list[float]]
    regime_label: str


def _get_markov_regression() -> Any:  # noqa: ANN401
    """Attempt to import ``MarkovRegression`` from statsmodels. Returns class or ``None``."""
    try:
        from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

        return MarkovRegression
    except ImportError:
        logger.info("statsmodels not installed -- Markov regime detection disabled")
        return None


def compute_markov_regime(
    returns: pd.Series,
    k_regimes: int = _DEFAULT_K_REGIMES,
) -> MarkovRegimeOutput | None:
    """Fit a Markov-switching regression model and classify the current regime.

    Fits ``MarkovRegression(returns, k_regimes=k_regimes, switching_variance=True)``
    with ``search_reps=20`` for robust convergence. Regimes are sorted by estimated
    variance: lowest variance -> ``"low_vol"``, middle -> ``"normal"``, highest ->
    ``"high_vol"``.

    Args:
        returns: Daily log returns series. Requires at least 252 observations
            after dropping NaN values.
        k_regimes: Number of latent regimes to estimate (2 or 3).

    Returns:
        ``MarkovRegimeOutput`` with current regime, smoothed probabilities,
        transition matrix, and regime label, or ``None`` if insufficient data,
        missing statsmodels, or convergence failure.

    Raises:
        ValueError: If ``k_regimes`` is not 2 or 3.
    """
    if k_regimes not in {2, 3}:
        raise ValueError("k_regimes must be 2 or 3")

    markov_cls = _get_markov_regression()
    if markov_cls is None:
        return None

    clean = returns.dropna()
    if len(clean) < _MIN_OBSERVATIONS:
        logger.debug(
            "Markov regime skipped: insufficient data (%d < %d)",
            len(clean),
            _MIN_OBSERVATIONS,
        )
        return None

    try:
        model = markov_cls(clean.to_numpy(), k_regimes=k_regimes, switching_variance=True)
        results = model.fit(search_reps=_SEARCH_REPS, disp=False)

        # Smoothed marginal probabilities: (T, k_regimes) array
        # Each row is one time step; each column is a regime.
        smoothed_probs: Any = results.smoothed_marginal_probabilities

        # Transition matrix: squeeze from (k, k, 1) to (k, k)
        # statsmodels convention: column-stochastic, tm[to, from]
        # Transpose to get row-stochastic: tm[from, to]
        raw_tm: np.ndarray[Any, np.dtype[np.floating[Any]]] = model.regime_transition_matrix(
            results.params
        )[:, :, 0].T

        # Sort regimes by estimated variance (ascending: low_vol -> normal -> high_vol)
        # Compute empirical variance per regime by weighting observations
        # with smoothed probabilities.
        regime_variances = np.zeros(k_regimes)
        returns_arr = clean.to_numpy()
        for regime_idx in range(k_regimes):
            # smoothed_probs[:, regime_idx] = prob of being in regime_idx at each time
            weights = smoothed_probs[:, regime_idx]
            weight_sum = float(np.sum(weights))
            if weight_sum > 0:
                weighted_mean = float(np.average(returns_arr, weights=weights))
                regime_variances[regime_idx] = float(
                    np.average(
                        (returns_arr - weighted_mean) ** 2,
                        weights=weights,
                    )
                )

        # Sort indices by variance (ascending)
        variance_order = np.argsort(regime_variances)

        # Build mapping from original regime index to sorted label
        sorted_label_map: dict[int, str] = {}
        for rank, orig_idx in enumerate(variance_order):
            if rank < len(_REGIME_LABELS):
                sorted_label_map[int(orig_idx)] = _REGIME_LABELS[rank]
            else:
                sorted_label_map[int(orig_idx)] = f"regime_{rank}"

        # Current regime: most probable at the last observation
        # smoothed_probs[-1, :] gives probabilities for each regime at time T
        last_probs = smoothed_probs[-1, :]
        current_regime_orig = int(np.argmax(last_probs))
        current_label = sorted_label_map[current_regime_orig]

        # Reorder probabilities and transition matrix to variance-sorted order
        sorted_probs = [float(last_probs[int(variance_order[r])]) for r in range(k_regimes)]
        sorted_transition: list[list[float]] = []
        for r_from in range(k_regimes):
            row: list[float] = []
            for r_to in range(k_regimes):
                from_idx = int(variance_order[r_from])
                to_idx = int(variance_order[r_to])
                row.append(float(raw_tm[from_idx, to_idx]))
            sorted_transition.append(row)

        # Current regime index in sorted order
        current_regime_sorted = int(np.where(variance_order == current_regime_orig)[0][0])

        return MarkovRegimeOutput(
            current_regime=current_regime_sorted,
            regime_probabilities=sorted_probs,
            transition_matrix=sorted_transition,
            regime_label=current_label,
        )

    except Exception:
        logger.warning("Markov regime detection failed", exc_info=True)
        return None


def map_regime_label_to_market_regime(label: str) -> MarketRegime:
    """Map a Markov regime label to the ``MarketRegime`` enum.

    Mapping:
        ``"low_vol"``  -> ``MarketRegime.MEAN_REVERTING``
        ``"normal"``   -> ``MarketRegime.TRENDING``
        ``"high_vol"`` -> ``MarketRegime.VOLATILE``

    Args:
        label: Regime label from ``MarkovRegimeOutput.regime_label``.

    Returns:
        Corresponding ``MarketRegime`` enum value, defaults to
        ``MarketRegime.MEAN_REVERTING`` for unknown labels.
    """
    return _REGIME_TO_MARKET_REGIME.get(label, MarketRegime.MEAN_REVERTING)
