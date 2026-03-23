"""Markov-switching regime detection and ML-based regime classification.

Two complementary approaches to market regime identification:

1. **Markov-switching** (Hamilton 1989): Uses ``statsmodels`` ``MarkovRegression`` to
   identify latent volatility regimes in return series.
2. **ML classification** (GBM): Loads a pre-trained Gradient Boosting model from disk
   and classifies regimes from the Phase 2 indicator feature vector.

Rules:
- Takes pandas Series / IndicatorSignals input, returns NamedTuple | None.
- NO Pydantic models, NO API calls -- pure math on pre-fetched data.
- Guarded imports: returns None when ``statsmodels`` / ``joblib`` / ``sklearn`` not installed.
- Returns None on insufficient data, missing model, or any failure.

Reference: Hamilton, J.D. (1989) "A New Approach to the Economic Analysis of
Nonstationary Time Series and the Business Cycle", Econometrica, 57(2), 357-384.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Minimum observations required for regime estimation (1 year of trading days)
_MIN_OBSERVATIONS: int = 252

# Default number of regimes (low_vol, normal, high_vol)
_DEFAULT_K_REGIMES: int = 3

# Number of random search repetitions for robust convergence
_SEARCH_REPS: int = 20

# Regime label mapping by variance rank (ascending)
_REGIME_LABELS: list[str] = ["low_vol", "normal", "high_vol"]


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


class RegimeClassification(NamedTuple):
    """Output of ML-based regime classification.

    Attributes:
        predicted_regime: The winning class label (e.g., ``"trending_up"``).
        probabilities: Class probability for each regime label.
        confidence: Max probability across classes (the winning class probability).
    """

    predicted_regime: str
    probabilities: dict[str, float]
    confidence: float


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


# ---------------------------------------------------------------------------
# ML regime classification (GBM-based)
# ---------------------------------------------------------------------------

# 9 indicator feature names — same as tools/train_regime_classifier.py.
# Duplicated here to keep the indicator module independent of the tools/ package.
_ML_FEATURE_NAMES: list[str] = [
    "rsi",
    "adx",
    "atr_pct",
    "relative_volume",
    "iv_rank",
    "bb_width",
    "put_call_ratio",
    "roc",
    "sma_alignment",
]

# Default model path (project root / data / model_cache / regime_classifier.pkl)
_DEFAULT_MODEL_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "model_cache"
    / "regime_classifier.pkl"
)

# Module-level model cache — avoids re-loading the model on every call.
_cached_model: Any = None
_cached_model_path: Path | None = None


def _get_joblib() -> Any:  # noqa: ANN401
    """Attempt to import ``joblib``. Returns the module or ``None``."""
    try:
        import joblib

        return joblib
    except ImportError:
        logger.info("joblib not installed -- ML regime classification disabled")
        return None


def _load_model(path: Path | None) -> Any:  # noqa: ANN401
    """Load and cache a pre-trained regime classifier from disk.

    Uses module-level ``_cached_model`` / ``_cached_model_path`` to avoid
    re-loading the model on every call. Returns ``None`` on any failure
    (missing file, import error, corrupt file).

    Args:
        path: Path to the serialized model file. Defaults to
            ``data/model_cache/regime_classifier.pkl``.

    Returns:
        Loaded model instance or ``None``.
    """
    global _cached_model, _cached_model_path  # noqa: PLW0603

    resolved = path or _DEFAULT_MODEL_PATH

    # Return cached model if path matches
    if _cached_model is not None and _cached_model_path == resolved:
        return _cached_model

    joblib = _get_joblib()
    if joblib is None:
        return None

    try:
        if not resolved.exists():
            logger.debug("ML regime model not found at %s", resolved)
            return None

        # Security: validate ALL paths resolve within the project root to
        # prevent arbitrary deserialization via configurable model_cache_dir
        # or caller-provided paths (CWE-502/CWE-918).
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        if not resolved.resolve().is_relative_to(project_root):
            logger.warning(
                "ML regime model path %s is outside project root — refusing to load",
                resolved,
            )
            return None

        model: object = joblib.load(resolved)
        _cached_model = model
        _cached_model_path = resolved
        logger.info("Loaded ML regime model from %s", resolved)
        return model
    except Exception:
        logger.warning("Failed to load ML regime model from %s", resolved, exc_info=True)
        return None


def _extract_ml_features(
    signals: Any,  # noqa: ANN401  (IndicatorSignals, but we avoid circular imports)
) -> np.ndarray[Any, np.dtype[np.floating[Any]]] | None:
    """Extract a 9-element feature vector from ``IndicatorSignals``.

    Returns a 1-D numpy array of shape ``(9,)`` with values in the same order
    as ``_ML_FEATURE_NAMES``, or ``None`` if any required field is ``None`` or
    non-finite.
    """
    values: list[float] = []
    for name in _ML_FEATURE_NAMES:
        val = getattr(signals, name, None)
        if val is None:
            return None
        fval = float(val)
        if not math.isfinite(fval):
            return None
        values.append(fval)
    return np.array(values, dtype=np.float64)


def classify_regime_ml(
    signals: Any,  # noqa: ANN401  (IndicatorSignals)
    model_path: Path | None = None,
) -> RegimeClassification | None:
    """Classify the current market regime using a pre-trained GBM model.

    Extracts the same 9-feature vector used during training (RSI, ADX, ATR%,
    relative volume, IV rank, BB width, put/call ratio, ROC, SMA alignment)
    and calls ``predict_proba()`` on the loaded model.

    Returns ``None`` on **any** failure: missing model file, missing sklearn/joblib,
    incomplete signals, NaN features, or prediction error.

    Args:
        signals: Typed indicator signals from the scan pipeline.
        model_path: Optional path to the serialized model file. Defaults to
            ``data/model_cache/regime_classifier.pkl``.

    Returns:
        ``RegimeClassification`` with predicted regime, class probabilities, and
        confidence (max probability), or ``None`` on failure.
    """
    # Extract feature vector
    features = _extract_ml_features(signals)
    if features is None:
        logger.debug("ML regime classification skipped: incomplete feature vector")
        return None

    # Load model (cached)
    model = _load_model(model_path)
    if model is None:
        return None

    try:
        # predict_proba returns (n_samples, n_classes) — we have 1 sample
        proba: np.ndarray[Any, np.dtype[np.floating[Any]]] = model.predict_proba(
            features.reshape(1, -1)
        )
        classes: list[str] = list(model.classes_)

        # Build probability dict
        prob_row = proba[0]
        probabilities: dict[str, float] = {}
        for cls_label, prob in zip(classes, prob_row, strict=True):
            probabilities[str(cls_label)] = float(prob)

        # Confidence = max probability
        confidence = float(np.max(prob_row))

        # Predicted regime = class with highest probability
        predicted_idx = int(np.argmax(prob_row))
        predicted_regime = str(classes[predicted_idx])

        return RegimeClassification(
            predicted_regime=predicted_regime,
            probabilities=probabilities,
            confidence=confidence,
        )
    except Exception:
        logger.warning("ML regime classification failed", exc_info=True)
        return None
