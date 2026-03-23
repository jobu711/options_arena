"""Tests for ML-based regime classification (GBM inference).

Covers:
- TestClassifyRegimeMl: returns RegimeClassification with mocked model, returns None
  on missing model / sklearn / incomplete signals, confidence = max prob, probabilities
  sum to ~1.0, predicted_regime is max prob class
- TestModelCaching: model loaded once on repeated calls, cache cleared on different path
- TestFeatureExtraction: 9 features from signals, returns None on missing RSI
- TestConfigFlag: enable_ml_regime defaults to False
- TestIndicatorSignalsField: ml_regime_confidence defaults to None, accepts valid float
- TestMarketContextFields: ml_regime and ml_regime_confidence exist on MarketContext
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from options_arena.indicators.regime_ml import (
    RegimeClassification,
    _extract_ml_features,
    _load_model,
    classify_regime_ml,
)
from options_arena.models.config import MLConfig
from options_arena.models.scan import IndicatorSignals

# ---------------------------------------------------------------------------
# Helpers: mock classifier
# ---------------------------------------------------------------------------


def _make_mock_classifier(
    classes: list[str] | None = None,
    proba: list[float] | None = None,
) -> MagicMock:
    """Create a mock sklearn classifier with predict_proba() and classes_."""
    if classes is None:
        classes = [
            "trending_up",
            "trending_down",
            "mean_reverting",
            "high_volatility",
            "low_volatility",
        ]
    if proba is None:
        proba = [0.50, 0.20, 0.15, 0.10, 0.05]

    mock = MagicMock()
    mock.classes_ = np.array(classes)
    mock.predict_proba.return_value = np.array([proba])
    return mock


def _make_complete_signals() -> IndicatorSignals:
    """Create IndicatorSignals with all 9 ML feature fields populated."""
    return IndicatorSignals(
        rsi=55.0,
        adx=30.0,
        atr_pct=12.5,
        relative_volume=60.0,
        iv_rank=45.0,
        bb_width=20.0,
        put_call_ratio=0.8,
        roc=3.5,
        sma_alignment=70.0,
    )


# ===========================================================================
# TestClassifyRegimeMl
# ===========================================================================


class TestClassifyRegimeMl:
    """Tests for classify_regime_ml()."""

    def test_returns_classification_with_valid_model(self) -> None:
        """Verify RegimeClassification returned with mocked trained model."""
        signals = _make_complete_signals()
        mock_clf = _make_mock_classifier()

        with patch(
            "options_arena.indicators.regime_ml._load_model",
            return_value=mock_clf,
        ):
            result = classify_regime_ml(signals)

        assert result is not None
        assert isinstance(result, RegimeClassification)
        assert result.predicted_regime == "trending_up"

    def test_returns_none_when_model_not_found(self, tmp_path: Path) -> None:
        """Verify None when model_path points to nonexistent file."""
        import options_arena.indicators.regime_ml as mod

        # Reset cache
        mod._cached_model = None
        mod._cached_model_path = None

        signals = _make_complete_signals()
        result = classify_regime_ml(signals, model_path=tmp_path / "nonexistent.pkl")
        assert result is None

    def test_returns_none_when_sklearn_not_installed(self) -> None:
        """Verify None when joblib import fails."""
        import options_arena.indicators.regime_ml as mod

        # Reset cache
        mod._cached_model = None
        mod._cached_model_path = None

        signals = _make_complete_signals()
        with patch(
            "options_arena.indicators.regime_ml._get_joblib",
            return_value=None,
        ):
            result = classify_regime_ml(signals)
        assert result is None

    def test_returns_none_when_signals_incomplete(self) -> None:
        """Verify None when required IndicatorSignals fields are None."""
        signals = IndicatorSignals()  # all None
        mock_clf = _make_mock_classifier()

        with patch(
            "options_arena.indicators.regime_ml._load_model",
            return_value=mock_clf,
        ):
            result = classify_regime_ml(signals)

        assert result is None

    def test_confidence_equals_max_probability(self) -> None:
        """Verify confidence is max(probabilities.values())."""
        signals = _make_complete_signals()
        proba = [0.10, 0.60, 0.15, 0.10, 0.05]
        mock_clf = _make_mock_classifier(proba=proba)

        with patch(
            "options_arena.indicators.regime_ml._load_model",
            return_value=mock_clf,
        ):
            result = classify_regime_ml(signals)

        assert result is not None
        assert result.confidence == pytest.approx(0.60, abs=1e-6)
        assert result.confidence == pytest.approx(max(result.probabilities.values()), abs=1e-6)

    def test_probabilities_sum_to_one(self) -> None:
        """Verify class probabilities sum to ~1.0."""
        signals = _make_complete_signals()
        mock_clf = _make_mock_classifier()

        with patch(
            "options_arena.indicators.regime_ml._load_model",
            return_value=mock_clf,
        ):
            result = classify_regime_ml(signals)

        assert result is not None
        assert sum(result.probabilities.values()) == pytest.approx(1.0, abs=1e-6)

    def test_predicted_regime_is_max_prob_class(self) -> None:
        """Verify predicted_regime matches the highest-probability class."""
        signals = _make_complete_signals()
        # Make "mean_reverting" the highest probability
        proba = [0.05, 0.10, 0.60, 0.15, 0.10]
        classes = [
            "trending_up",
            "trending_down",
            "mean_reverting",
            "high_volatility",
            "low_volatility",
        ]
        mock_clf = _make_mock_classifier(classes=classes, proba=proba)

        with patch(
            "options_arena.indicators.regime_ml._load_model",
            return_value=mock_clf,
        ):
            result = classify_regime_ml(signals)

        assert result is not None
        assert result.predicted_regime == "mean_reverting"


# ===========================================================================
# TestModelCaching
# ===========================================================================


class TestModelCaching:
    """Tests for _load_model caching behavior."""

    def test_model_loaded_once_on_repeated_calls(self, tmp_path: Path) -> None:
        """Verify _load_model caches and doesn't reload."""
        import options_arena.indicators.regime_ml as mod

        # Reset cache
        mod._cached_model = None
        mod._cached_model_path = None

        model_path = tmp_path / "model.pkl"
        model_path.touch()

        fake_model = MagicMock()
        mock_joblib = MagicMock()
        mock_joblib.load.return_value = fake_model

        with (
            patch(
                "options_arena.indicators.regime_ml._get_joblib",
                return_value=mock_joblib,
            ),
            patch("pathlib.PurePath.is_relative_to", return_value=True),
        ):
            result1 = _load_model(model_path)
            result2 = _load_model(model_path)

        assert result1 is fake_model
        assert result2 is fake_model
        # joblib.load called only once (second call uses cache)
        assert mock_joblib.load.call_count == 1

    def test_cache_cleared_on_different_path(self, tmp_path: Path) -> None:
        """Verify different model_path triggers reload."""
        import options_arena.indicators.regime_ml as mod

        # Reset cache
        mod._cached_model = None
        mod._cached_model_path = None

        path_a = tmp_path / "model_a.pkl"
        path_b = tmp_path / "model_b.pkl"
        path_a.touch()
        path_b.touch()

        model_a = MagicMock(name="model_a")
        model_b = MagicMock(name="model_b")
        mock_joblib = MagicMock()
        mock_joblib.load.side_effect = [model_a, model_b]

        with (
            patch(
                "options_arena.indicators.regime_ml._get_joblib",
                return_value=mock_joblib,
            ),
            patch("pathlib.PurePath.is_relative_to", return_value=True),
        ):
            result1 = _load_model(path_a)
            result2 = _load_model(path_b)

        assert result1 is model_a
        assert result2 is model_b
        assert mock_joblib.load.call_count == 2


# ===========================================================================
# TestFeatureExtraction
# ===========================================================================


class TestFeatureExtraction:
    """Tests for _extract_ml_features()."""

    def test_extract_9_features_from_signals(self) -> None:
        """Verify 9-element feature vector from complete IndicatorSignals."""
        signals = _make_complete_signals()
        features = _extract_ml_features(signals)

        assert features is not None
        assert features.shape == (9,)
        assert features[0] == pytest.approx(55.0)  # rsi
        assert features[1] == pytest.approx(30.0)  # adx
        assert features[2] == pytest.approx(12.5)  # atr_pct
        assert features[3] == pytest.approx(60.0)  # relative_volume
        assert features[4] == pytest.approx(45.0)  # iv_rank
        assert features[5] == pytest.approx(20.0)  # bb_width
        assert features[6] == pytest.approx(0.8)  # put_call_ratio
        assert features[7] == pytest.approx(3.5)  # roc
        assert features[8] == pytest.approx(70.0)  # sma_alignment

    def test_returns_none_on_missing_rsi(self) -> None:
        """Verify None when RSI is None."""
        signals = _make_complete_signals()
        signals.rsi = None
        features = _extract_ml_features(signals)
        assert features is None

    def test_returns_none_on_nan_feature(self) -> None:
        """Verify None when a feature is NaN (non-finite guard)."""
        signals = IndicatorSignals(
            rsi=55.0,
            adx=float("nan"),  # will be normalized to None by model_validator
            atr_pct=12.5,
            relative_volume=60.0,
            iv_rank=45.0,
            bb_width=20.0,
            put_call_ratio=0.8,
            roc=3.5,
            sma_alignment=70.0,
        )
        # IndicatorSignals normalizes NaN to None, so this becomes a missing field case
        features = _extract_ml_features(signals)
        assert features is None


# ===========================================================================
# TestConfigFlag
# ===========================================================================


class TestConfigFlag:
    """Tests for MLConfig.enable_ml_regime flag."""

    def test_ml_regime_default_false(self) -> None:
        """Verify MLConfig.enable_ml_regime defaults to False."""
        config = MLConfig()
        assert config.enable_ml_regime is False


# ===========================================================================
# TestIndicatorSignalsField
# ===========================================================================


class TestIndicatorSignalsField:
    """Tests for ml_regime_confidence field on IndicatorSignals."""

    def test_ml_regime_confidence_defaults_none(self) -> None:
        """Verify new field defaults to None."""
        signals = IndicatorSignals()
        assert signals.ml_regime_confidence is None

    def test_ml_regime_confidence_accepts_valid_float(self) -> None:
        """Verify field accepts float in [0, 1]."""
        signals = IndicatorSignals(ml_regime_confidence=0.85)
        assert signals.ml_regime_confidence == pytest.approx(0.85)


# ===========================================================================
# TestMarketContextFields
# ===========================================================================


class TestMarketContextFields:
    """Tests for ml_regime_confidence field on IndicatorSignals (MarketContext fields removed)."""

    def test_ml_regime_confidence_on_indicator_signals(self) -> None:
        """Verify ml_regime_confidence field exists on IndicatorSignals (not MarketContext)."""
        signals = IndicatorSignals(ml_regime_confidence=0.85)
        assert signals.ml_regime_confidence == pytest.approx(0.85)
