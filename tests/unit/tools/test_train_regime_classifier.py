"""Tests for tools/train_regime_classifier.py — offline regime classifier training.

Covers:
  - Feature extraction from IndicatorSignals
  - Heuristic regime labeling
  - GradientBoostingClassifier training with synthetic data
  - Model serialization (joblib dump/load roundtrip)
  - Guarded sklearn import when sklearn is missing
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

# Add tools/ parent (project root) and src/ to sys.path so we can import the script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TOOLS_DIR = _PROJECT_ROOT / "tools"
_SRC_DIR = _PROJECT_ROOT / "src"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from train_regime_classifier import (  # noqa: E402, I001
    FEATURE_NAMES,
    REGIME_LABELS,
    extract_features,
    label_regime,
    load_model,
    run_cross_validation,
    save_model,
    train_classifier,
)

from options_arena.models.scan import IndicatorSignals  # noqa: E402

# Type alias to keep annotation lines within 99 chars
type _SyntheticData = tuple[
    np.ndarray[Any, np.dtype[np.floating[Any]]],
    np.ndarray[Any, np.dtype[Any]],
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def complete_signals() -> IndicatorSignals:
    """IndicatorSignals with all 9 required features populated."""
    return IndicatorSignals(
        rsi=55.0,
        adx=30.0,
        atr_pct=50.0,
        relative_volume=60.0,
        iv_rank=45.0,
        bb_width=40.0,
        put_call_ratio=50.0,
        roc=8.0,
        sma_alignment=65.0,
    )


@pytest.fixture()
def synthetic_data() -> _SyntheticData:
    """Synthetic training data: 200 samples x 9 features, 5 balanced classes."""
    rng = np.random.default_rng(123)
    n_per_class = 40
    features_list: list[np.ndarray[Any, np.dtype[np.floating[Any]]]] = []
    labels_list: list[str] = []

    for label in REGIME_LABELS:
        block = rng.uniform(0.0, 100.0, size=(n_per_class, len(FEATURE_NAMES)))
        features_list.append(block)
        labels_list.extend([label] * n_per_class)

    features = np.vstack(features_list)
    labels = np.array(labels_list)
    return features, labels


# ---------------------------------------------------------------------------
# TestExtractFeatures
# ---------------------------------------------------------------------------


class TestExtractFeatures:
    """Tests for extract_features()."""

    def test_extracts_9_features_from_complete_signals(
        self, complete_signals: IndicatorSignals
    ) -> None:
        """Verify 9-element vector from fully populated IndicatorSignals."""
        result = extract_features(complete_signals)
        assert result is not None
        assert result.shape == (9,)
        assert result.dtype == np.float64

    def test_returns_none_when_required_field_missing(self) -> None:
        """Verify None when RSI is None (one of the 9 required fields)."""
        signals = IndicatorSignals(
            rsi=None,  # missing
            adx=30.0,
            atr_pct=50.0,
            relative_volume=60.0,
            iv_rank=45.0,
            bb_width=40.0,
            put_call_ratio=50.0,
            roc=8.0,
            sma_alignment=65.0,
        )
        assert extract_features(signals) is None

    def test_returns_none_when_adx_missing(self) -> None:
        """Verify None when ADX is None."""
        signals = IndicatorSignals(
            rsi=55.0,
            adx=None,  # missing
            atr_pct=50.0,
            relative_volume=60.0,
            iv_rank=45.0,
            bb_width=40.0,
            put_call_ratio=50.0,
            roc=8.0,
            sma_alignment=65.0,
        )
        assert extract_features(signals) is None

    def test_feature_order_matches_feature_names(self, complete_signals: IndicatorSignals) -> None:
        """Verify feature vector order matches FEATURE_NAMES constant."""
        result = extract_features(complete_signals)
        assert result is not None

        for idx, name in enumerate(FEATURE_NAMES):
            expected = getattr(complete_signals, name)
            assert result[idx] == pytest.approx(expected, rel=1e-6)

    def test_all_none_signals_returns_none(self) -> None:
        """Verify None when all IndicatorSignals fields are None."""
        signals = IndicatorSignals()
        assert extract_features(signals) is None


# ---------------------------------------------------------------------------
# TestLabelRegime
# ---------------------------------------------------------------------------


class TestLabelRegime:
    """Tests for label_regime()."""

    def test_trending_up_label(self) -> None:
        """ADX>25, ROC>5 -> trending_up."""
        signals = IndicatorSignals(adx=30.0, roc=10.0, atr_pct=50.0)
        assert label_regime(signals) == "trending_up"

    def test_trending_down_label(self) -> None:
        """ADX>25, ROC<-5 -> trending_down."""
        signals = IndicatorSignals(adx=35.0, roc=-8.0, atr_pct=50.0)
        assert label_regime(signals) == "trending_down"

    def test_mean_reverting_label(self) -> None:
        """ADX<15 -> mean_reverting (when ATR% is in mid-range)."""
        signals = IndicatorSignals(adx=10.0, roc=2.0, atr_pct=50.0)
        assert label_regime(signals) == "mean_reverting"

    def test_high_volatility_label(self) -> None:
        """ATR%>=95 -> high_volatility (takes priority over trending)."""
        signals = IndicatorSignals(adx=30.0, roc=10.0, atr_pct=97.0)
        assert label_regime(signals) == "high_volatility"

    def test_low_volatility_label(self) -> None:
        """ATR%<=5 -> low_volatility (takes priority over trending)."""
        signals = IndicatorSignals(adx=30.0, roc=10.0, atr_pct=3.0)
        assert label_regime(signals) == "low_volatility"

    def test_returns_none_when_fields_missing(self) -> None:
        """Verify None when required indicators (ADX, ROC, ATR%) are None."""
        signals = IndicatorSignals(adx=30.0, roc=None, atr_pct=50.0)
        assert label_regime(signals) is None

    def test_returns_none_when_all_missing(self) -> None:
        """Verify None when all IndicatorSignals fields are None."""
        signals = IndicatorSignals()
        assert label_regime(signals) is None

    def test_ambiguous_returns_none(self) -> None:
        """ADX between 15-25, ROC between -5 and +5 -> None (ambiguous)."""
        signals = IndicatorSignals(adx=20.0, roc=2.0, atr_pct=50.0)
        assert label_regime(signals) is None

    def test_volatility_priority_over_trending(self) -> None:
        """High volatility label takes priority over trending conditions."""
        # This would be trending_up by ADX/ROC, but ATR% is extreme
        signals = IndicatorSignals(adx=40.0, roc=15.0, atr_pct=96.0)
        assert label_regime(signals) == "high_volatility"


# ---------------------------------------------------------------------------
# TestTrainClassifier
# ---------------------------------------------------------------------------


class TestTrainClassifier:
    """Tests for train_classifier()."""

    def test_trains_gbm_on_synthetic_data(
        self,
        synthetic_data: _SyntheticData,
    ) -> None:
        """Verify fitted GBM returns predictions on 5-class synthetic data."""
        features, labels = synthetic_data
        clf = train_classifier(features, labels)

        predictions = clf.predict(features)
        assert len(predictions) == len(labels)
        # All predictions should be valid regime labels
        for pred in predictions:
            assert pred in REGIME_LABELS

    def test_custom_hyperparameters(
        self,
        synthetic_data: _SyntheticData,
    ) -> None:
        """Verify n_estimators and max_depth are respected."""
        features, labels = synthetic_data
        clf = train_classifier(
            features,
            labels,
            n_estimators=50,
            max_depth=2,
            learning_rate=0.05,
        )

        assert clf.n_estimators == 50
        assert clf.max_depth == 2
        assert clf.learning_rate == pytest.approx(0.05, rel=1e-6)

    def test_cross_validation_runs(
        self,
        synthetic_data: _SyntheticData,
    ) -> None:
        """Verify cross_val_score completes without error."""
        features, labels = synthetic_data
        scores = run_cross_validation(features, labels, cv_folds=3)
        assert len(scores) == 3
        # Each fold should have accuracy between 0 and 1
        for score in scores:
            assert 0.0 <= score <= 1.0

    def test_empty_features_raises(self) -> None:
        """Verify ValueError on empty feature array."""
        features = np.empty((0, 9), dtype=np.float64)
        labels = np.array([], dtype=object)
        with pytest.raises(ValueError, match="non-empty"):
            train_classifier(features, labels)

    def test_mismatched_lengths_raises(self) -> None:
        """Verify ValueError when features and labels have different lengths."""
        features = np.ones((10, 9), dtype=np.float64)
        labels = np.array(["trending_up"] * 5)
        with pytest.raises(ValueError, match="same number of samples"):
            train_classifier(features, labels)


# ---------------------------------------------------------------------------
# TestModelSerialization
# ---------------------------------------------------------------------------


class TestModelSerialization:
    """Tests for save_model() and load_model()."""

    def test_save_and_load_roundtrip(
        self,
        tmp_path: Path,
        synthetic_data: _SyntheticData,
    ) -> None:
        """Verify joblib dump/load preserves model predictions."""
        features, labels = synthetic_data
        clf = train_classifier(features, labels, n_estimators=20)

        model_path = tmp_path / "test_model.pkl"
        save_model(clf, model_path)
        assert model_path.exists()

        loaded = load_model(model_path)
        original_preds = clf.predict(features)
        loaded_preds = loaded.predict(features)
        np.testing.assert_array_equal(original_preds, loaded_preds)

    def test_creates_output_directory(
        self,
        tmp_path: Path,
        synthetic_data: _SyntheticData,
    ) -> None:
        """Verify script creates parent directory if missing."""
        features, labels = synthetic_data
        clf = train_classifier(features, labels, n_estimators=10)

        nested_path = tmp_path / "nested" / "dir" / "model.pkl"
        assert not nested_path.parent.exists()

        save_model(clf, nested_path)
        assert nested_path.exists()

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        """Verify FileNotFoundError when model file does not exist."""
        missing_path = tmp_path / "nonexistent.pkl"
        with pytest.raises(FileNotFoundError, match="not found"):
            load_model(missing_path)


# ---------------------------------------------------------------------------
# TestGuardedImport
# ---------------------------------------------------------------------------


class TestGuardedImport:
    """Tests for guarded sklearn import behavior."""

    def test_sklearn_not_installed(self) -> None:
        """Verify graceful error message when sklearn missing."""
        # Patch sys.modules to simulate sklearn not being installed
        with patch.dict(sys.modules, {"sklearn": None}):
            from train_regime_classifier import _get_sklearn

            result = _get_sklearn()
            assert result is None

    def test_train_classifier_raises_when_sklearn_missing(self) -> None:
        """Verify RuntimeError when training without sklearn."""
        features = np.ones((10, 9), dtype=np.float64)
        labels = np.array(["trending_up"] * 10)

        with patch.dict(sys.modules, {"sklearn": None}):
            from train_regime_classifier import _get_sklearn

            # Verify _get_sklearn returns None
            assert _get_sklearn() is None

            # train_classifier should raise RuntimeError
            with (
                patch(
                    "train_regime_classifier._get_sklearn",
                    return_value=None,
                ),
                pytest.raises(
                    RuntimeError,
                    match="scikit-learn is required",
                ),
            ):
                train_classifier(features, labels)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_feature_names_count(self) -> None:
        """Verify exactly 9 feature names."""
        assert len(FEATURE_NAMES) == 9

    def test_regime_labels_count(self) -> None:
        """Verify exactly 5 regime labels."""
        assert len(REGIME_LABELS) == 5

    def test_feature_names_are_indicator_fields(self) -> None:
        """Verify all feature names are valid IndicatorSignals field names."""
        field_names = set(IndicatorSignals.model_fields.keys())
        for name in FEATURE_NAMES:
            assert name in field_names, f"{name} is not a valid IndicatorSignals field"

    def test_regime_labels_are_unique(self) -> None:
        """Verify regime labels are unique."""
        assert len(set(REGIME_LABELS)) == len(REGIME_LABELS)
