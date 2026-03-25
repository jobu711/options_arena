"""Offline training script for Gradient Boosting regime classifier.

Trains a ``GradientBoostingClassifier`` on historical scan data to classify
market regimes into 5 classes: ``trending_up``, ``trending_down``,
``mean_reverting``, ``high_volatility``, ``low_volatility``.

The feature vector is built from 9 Phase 2 indicators stored in
``IndicatorSignals``:
  rsi, adx, atr_pct, relative_volume, iv_rank, bb_width,
  put_call_ratio, roc, sma_alignment.

Labels are derived from heuristic rules on indicator thresholds (see
``label_regime()``).  Trained model is saved to ``data/model_cache/`` via
``joblib``.

Usage:
    python tools/train_regime_classifier.py --help
    python tools/train_regime_classifier.py --n-estimators 200 --max-depth 4
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Project root detection (tools/ is one level below project root)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"

# Add src/ to sys.path so we can import options_arena models
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from options_arena.models.scan import IndicatorSignals  # type: ignore[import-untyped]  # noqa: E402, I001

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
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
"""Ordered list of 9 indicator field names extracted from ``IndicatorSignals``."""

REGIME_LABELS: list[str] = [
    "trending_up",
    "trending_down",
    "mean_reverting",
    "high_volatility",
    "low_volatility",
]
"""5-class regime labels used as classification targets."""

_DEFAULT_OUTPUT = _PROJECT_ROOT / "data" / "model_cache" / "regime_classifier.pkl"
_DEFAULT_N_ESTIMATORS = 100
_DEFAULT_MAX_DEPTH = 3
_DEFAULT_LEARNING_RATE = 0.1
_DEFAULT_CV_FOLDS = 5

# ---------------------------------------------------------------------------
# Heuristic labeling thresholds
# ---------------------------------------------------------------------------

# ADX threshold for trending vs non-trending
_ADX_TRENDING_THRESHOLD = 25.0
# ADX threshold for mean-reverting (low directional strength)
_ADX_MEAN_REVERTING_THRESHOLD = 15.0
# ROC thresholds for directional classification
_ROC_UP_THRESHOLD = 5.0
_ROC_DOWN_THRESHOLD = -5.0
# ATR% thresholds for volatility regimes (normalized 0-100 percentile)
_ATR_HIGH_VOL_THRESHOLD = 95.0
_ATR_LOW_VOL_THRESHOLD = 5.0


# ---------------------------------------------------------------------------
# Guarded sklearn import
# ---------------------------------------------------------------------------


def _get_sklearn() -> Any:  # noqa: ANN401
    """Attempt to import scikit-learn. Returns the ``sklearn`` module or ``None``.

    Prints a clear error message to stderr when sklearn is not installed,
    guiding the user to install the ``[ml]`` optional extra.
    """
    try:
        import sklearn

        return sklearn
    except ImportError:
        logger.error(
            "scikit-learn is not installed. "
            "Install it with: uv pip install 'options-arena[ml]' "
            "or: uv add --optional ml scikit-learn"
        )
        return None


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def extract_features(
    signals: IndicatorSignals,
) -> np.ndarray[Any, np.dtype[np.floating[Any]]] | None:
    """Extract a 9-element feature vector from ``IndicatorSignals``.

    Returns a 1-D numpy array of shape ``(9,)`` with values in the same order
    as ``FEATURE_NAMES``, or ``None`` if any required field is ``None``.

    Args:
        signals: Typed indicator signals from the scan pipeline.

    Returns:
        Feature vector as ``np.ndarray`` (float64) or ``None``.
    """
    values: list[float] = []
    for name in FEATURE_NAMES:
        val = getattr(signals, name, None)
        if val is None:
            return None
        values.append(float(val))
    return np.array(values, dtype=np.float64)


# ---------------------------------------------------------------------------
# Heuristic labeling
# ---------------------------------------------------------------------------


def label_regime(signals: IndicatorSignals) -> str | None:
    """Assign a regime label based on heuristic indicator thresholds.

    Rules (evaluated in priority order):
      1. ``atr_pct >= 95``  -> ``high_volatility``
      2. ``atr_pct <= 5``   -> ``low_volatility``
      3. ``adx > 25`` and ``roc > 5``  -> ``trending_up``
      4. ``adx > 25`` and ``roc < -5`` -> ``trending_down``
      5. ``adx < 15``       -> ``mean_reverting``
      6. Otherwise           -> ``None`` (ambiguous, skip sample)

    Args:
        signals: Typed indicator signals from the scan pipeline.

    Returns:
        One of the 5 ``REGIME_LABELS`` strings, or ``None`` if required
        fields are missing or the regime is ambiguous.
    """
    adx = signals.adx
    roc = signals.roc
    atr_pct = signals.atr_pct

    # Require all three core fields for labeling
    if adx is None or roc is None or atr_pct is None:
        return None

    # Volatility regimes take priority (extreme ATR percentiles)
    if atr_pct >= _ATR_HIGH_VOL_THRESHOLD:
        return "high_volatility"
    if atr_pct <= _ATR_LOW_VOL_THRESHOLD:
        return "low_volatility"

    # Trending regimes (strong directional movement)
    if adx > _ADX_TRENDING_THRESHOLD and roc > _ROC_UP_THRESHOLD:
        return "trending_up"
    if adx > _ADX_TRENDING_THRESHOLD and roc < _ROC_DOWN_THRESHOLD:
        return "trending_down"

    # Mean-reverting (weak directional strength)
    if adx < _ADX_MEAN_REVERTING_THRESHOLD:
        return "mean_reverting"

    # Ambiguous — ADX between 15-25, or ROC between -5 and +5 with strong ADX
    return None


# ---------------------------------------------------------------------------
# Classifier training
# ---------------------------------------------------------------------------


def train_classifier(
    features: np.ndarray[Any, np.dtype[np.floating[Any]]],
    labels: np.ndarray[Any, np.dtype[Any]],
    *,
    n_estimators: int = _DEFAULT_N_ESTIMATORS,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    learning_rate: float = _DEFAULT_LEARNING_RATE,
) -> Any:  # noqa: ANN401
    """Train a Gradient Boosting classifier on the provided features and labels.

    Args:
        features: 2-D array of shape ``(n_samples, 9)`` with indicator values.
        labels: 1-D array of shape ``(n_samples,)`` with regime label strings.
        n_estimators: Number of boosting stages.
        max_depth: Maximum depth of individual trees.
        learning_rate: Shrinkage applied to each tree.

    Returns:
        Fitted ``GradientBoostingClassifier`` instance.

    Raises:
        RuntimeError: If scikit-learn is not installed.
        ValueError: If ``features`` and ``labels`` have mismatched lengths or
            ``features`` is empty.
    """
    sklearn = _get_sklearn()
    if sklearn is None:
        raise RuntimeError(
            "scikit-learn is required for training. "
            "Install with: uv pip install 'options-arena[ml]'"
        )

    if features.ndim != 2 or features.shape[0] == 0:
        raise ValueError(f"features must be a non-empty 2-D array, got shape {features.shape}")
    if features.shape[0] != labels.shape[0]:
        raise ValueError(
            f"features ({features.shape[0]}) and labels ({labels.shape[0]}) "
            "must have the same number of samples"
        )

    from sklearn.ensemble import GradientBoostingClassifier

    clf = GradientBoostingClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        random_state=42,
    )
    clf.fit(features, labels)
    return clf


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------


def run_cross_validation(
    features: np.ndarray[Any, np.dtype[np.floating[Any]]],
    labels: np.ndarray[Any, np.dtype[Any]],
    *,
    n_estimators: int = _DEFAULT_N_ESTIMATORS,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    learning_rate: float = _DEFAULT_LEARNING_RATE,
    cv_folds: int = _DEFAULT_CV_FOLDS,
) -> np.ndarray[Any, np.dtype[np.floating[Any]]]:
    """Run stratified cross-validation and return per-fold accuracy scores.

    Args:
        features: 2-D feature array.
        labels: 1-D label array.
        n_estimators: Number of boosting stages.
        max_depth: Maximum depth of individual trees.
        learning_rate: Shrinkage applied to each tree.
        cv_folds: Number of cross-validation folds.

    Returns:
        Array of accuracy scores, one per fold.

    Raises:
        RuntimeError: If scikit-learn is not installed.
    """
    sklearn = _get_sklearn()
    if sklearn is None:
        raise RuntimeError("scikit-learn is required for cross-validation.")

    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score

    clf = GradientBoostingClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        random_state=42,
    )
    scores: np.ndarray[Any, np.dtype[np.floating[Any]]] = cross_val_score(
        clf, features, labels, cv=cv_folds, scoring="accuracy"
    )
    return scores


# ---------------------------------------------------------------------------
# Model serialization
# ---------------------------------------------------------------------------


def save_model(model: Any, path: Path) -> None:  # noqa: ANN401
    """Save a trained model to disk via joblib.

    Creates parent directories if they do not exist.

    Args:
        model: Fitted classifier instance.
        path: Destination file path (typically ``.pkl``).
    """
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    logger.info("Model saved to %s", path)


def load_model(path: Path) -> Any:  # noqa: ANN401
    """Load a trained model from disk via joblib.

    Args:
        path: Path to the serialized model file.

    Returns:
        Deserialized model instance.

    Raises:
        FileNotFoundError: If the path does not exist.
    """
    import joblib

    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")
    model: object = joblib.load(path)
    return model


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse CLI parser."""
    parser = argparse.ArgumentParser(
        description="Train a Gradient Boosting regime classifier on historical scan data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=_DEFAULT_N_ESTIMATORS,
        help="Number of boosting stages.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=_DEFAULT_MAX_DEPTH,
        help="Maximum depth of individual trees.",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=_DEFAULT_LEARNING_RATE,
        help="Learning rate (shrinkage).",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Path to save the trained model.",
    )
    parser.add_argument(
        "--cv-folds",
        type=int,
        default=_DEFAULT_CV_FOLDS,
        help="Number of cross-validation folds.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=_PROJECT_ROOT / "data" / "options_arena.db",
        help="Path to the SQLite database for real training data.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output.",
    )
    return parser


_MIN_REAL_SAMPLES = 200
"""Minimum labeled samples required from real data before falling back to synthetic."""


def _load_real_data(
    db_path: Path,
) -> tuple[np.ndarray[Any, np.dtype[np.floating[Any]]], np.ndarray[Any, np.dtype[Any]]]:
    """Load training data from the SQLite database.

    Opens the database directly via ``sqlite3`` (tool script, not library code),
    queries ``ticker_scores`` for stored indicator JSON, and labels each row
    using the heuristic ``label_regime()`` function.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Tuple of ``(features, labels)`` numpy arrays. May be empty if no rows qualify.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    features_list: list[np.ndarray[Any, np.dtype[np.floating[Any]]]] = []
    labels_list: list[str] = []

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT signals_json FROM ticker_scores WHERE signals_json IS NOT NULL"
        )
        for (signals_json,) in cursor:
            try:
                data: dict[str, Any] = json.loads(signals_json)
            except (json.JSONDecodeError, TypeError):
                continue

            signals = IndicatorSignals(**data)
            label = label_regime(signals)
            if label is None:
                continue

            feat = extract_features(signals)
            if feat is not None:
                features_list.append(feat)
                labels_list.append(label)
    finally:
        conn.close()

    if not features_list:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float64), np.empty(0, dtype=object)

    return np.array(features_list), np.array(labels_list)


def _generate_synthetic_data(
    n_samples: int = 1000,
) -> tuple[np.ndarray[Any, np.dtype[np.floating[Any]]], np.ndarray[Any, np.dtype[Any]]]:
    """Generate synthetic training data for demonstration purposes.

    Creates random indicator values and labels them using the heuristic rules.
    Samples that receive ``None`` labels (ambiguous) are discarded.

    Args:
        n_samples: Number of candidate samples to generate.

    Returns:
        Tuple of ``(features, labels)`` numpy arrays.
    """
    rng = np.random.default_rng(42)

    features_list: list[np.ndarray[Any, np.dtype[np.floating[Any]]]] = []
    labels_list: list[str] = []

    for _ in range(n_samples):
        signals = IndicatorSignals(
            rsi=float(rng.uniform(10.0, 90.0)),
            adx=float(rng.uniform(5.0, 60.0)),
            atr_pct=float(rng.uniform(0.0, 100.0)),
            relative_volume=float(rng.uniform(0.0, 100.0)),
            iv_rank=float(rng.uniform(0.0, 100.0)),
            bb_width=float(rng.uniform(0.0, 100.0)),
            put_call_ratio=float(rng.uniform(0.0, 100.0)),
            roc=float(rng.uniform(-20.0, 20.0)),
            sma_alignment=float(rng.uniform(0.0, 100.0)),
        )

        label = label_regime(signals)
        if label is None:
            continue

        feat = extract_features(signals)
        if feat is not None:
            features_list.append(feat)
            labels_list.append(label)

    return np.array(features_list), np.array(labels_list)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the regime classifier training script.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    sklearn = _get_sklearn()
    if sklearn is None:
        sys.exit(1)

    # Try real data first, fall back to synthetic if insufficient
    db_path: Path = args.db_path
    features: np.ndarray[Any, np.dtype[np.floating[Any]]] | None = None
    labels: np.ndarray[Any, np.dtype[Any]] | None = None

    try:
        logger.info("Loading real training data from %s...", db_path)
        features, labels = _load_real_data(db_path)
        logger.info("Loaded %d labeled samples from database", features.shape[0])
    except FileNotFoundError:
        logger.warning("Database not found at %s", db_path)
    except Exception:
        logger.warning("Failed to load real data", exc_info=True)

    if features is None or features.shape[0] < _MIN_REAL_SAMPLES:
        count = 0 if features is None else features.shape[0]
        logger.warning(
            "Only %d real labeled samples (need >= %d). Falling back to synthetic data.",
            count,
            _MIN_REAL_SAMPLES,
        )
        features, labels = _generate_synthetic_data()

    logger.info(
        "%d labeled samples (%d features each)",
        features.shape[0],
        features.shape[1],
    )

    # Print class distribution
    unique_labels, counts = np.unique(labels, return_counts=True)
    for lbl, cnt in zip(unique_labels, counts, strict=True):
        logger.info("  %s: %d samples", lbl, cnt)

    # Cross-validation
    logger.info("Running %d-fold cross-validation...", args.cv_folds)
    cv_scores = run_cross_validation(
        features,
        labels,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        cv_folds=args.cv_folds,
    )
    logger.info(
        "CV accuracy: %.3f (+/- %.3f)",
        float(np.mean(cv_scores)),
        float(np.std(cv_scores) * 2),
    )

    # Train final model on all data
    logger.info("Training final model on all data...")
    clf = train_classifier(
        features,
        labels,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
    )

    # Classification report
    from sklearn.metrics import classification_report

    predictions = clf.predict(features)
    report: str = classification_report(labels, predictions, labels=REGIME_LABELS)
    logger.info("Classification report (training set):\n%s", report)

    # Save model
    output_path = Path(args.output_path)
    save_model(clf, output_path)
    logger.info("Done. Model saved to %s", output_path)


if __name__ == "__main__":
    main()
