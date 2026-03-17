"""Tests for flow anomaly detection via Isolation Forest.

Tests cover:
1. Anomaly detection on synthetic chain with injected outlier
2. Returns None with <20 rows
3. Returns None when sklearn not installed
4. Returns None on empty DataFrame
5. anomaly_score is finite float
6. is_anomalous flag matches score sign
7. feature_contributions has 4 keys
8. Normal chain not flagged as anomalous
9. NamedTuple fields verified
10. Config flag default
11. IndicatorSignals field defaults to None
12. Non-finite normalized to None via model validator
"""

from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.flow_analytics import (
    FlowAnomalyResult,
    _get_isolation_forest,
    detect_flow_anomalies,
)
from options_arena.models.config import MLConfig
from options_arena.models.scan import IndicatorSignals


def _make_normal_chain(n: int = 30) -> pd.DataFrame:
    """Create a synthetic options chain with normal (non-anomalous) flow patterns.

    Uniform volume/OI across strikes — no outlier should be detected.
    """
    rng = np.random.default_rng(42)
    strikes = np.linspace(90.0, 110.0, n)
    volume = rng.integers(100, 500, size=n).astype(float)
    oi = rng.integers(500, 2000, size=n).astype(float)
    return pd.DataFrame(
        {
            "strike": strikes,
            "volume": volume,
            "openInterest": oi,
            "optionType": ["call"] * (n // 2) + ["put"] * (n - n // 2),
            "bid": rng.uniform(1.0, 5.0, size=n),
            "ask": rng.uniform(5.0, 10.0, size=n),
        }
    )


def _make_anomalous_chain(n: int = 30) -> pd.DataFrame:
    """Create a synthetic chain with an injected outlier row.

    One row has extremely high volume relative to OI — a clear anomaly signal.
    """
    chain = _make_normal_chain(n)
    # Inject extreme outlier at row 0: volume 100x normal, OI near zero
    chain.loc[0, "volume"] = 50000.0
    chain.loc[0, "openInterest"] = 1.0
    return chain


# ---------------------------------------------------------------------------
# TestDetectFlowAnomalies
# ---------------------------------------------------------------------------


class TestDetectFlowAnomalies:
    """Tests for detect_flow_anomalies() function."""

    @pytest.mark.critical
    def test_detects_anomaly_in_synthetic_chain(self) -> None:
        """Verify anomaly detection on chain with injected outlier row.

        The injected outlier should pull the chain-level score lower than a
        normal chain's score, proving the detector senses the anomaly.
        """
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        anomalous_chain = _make_anomalous_chain(40)
        normal_chain = _make_normal_chain(40)
        result = detect_flow_anomalies(anomalous_chain, avg_volume_20d=300.0)
        baseline = detect_flow_anomalies(normal_chain, avg_volume_20d=300.0)
        assert result is not None
        assert baseline is not None
        assert isinstance(result, FlowAnomalyResult)
        assert math.isfinite(result.anomaly_score)
        # Outlier should produce a lower (more anomalous) score than baseline
        assert result.anomaly_score < baseline.anomaly_score

    def test_returns_none_with_fewer_than_20_rows(self) -> None:
        """Verify None when chain has <20 rows."""
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = _make_normal_chain(15)
        result = detect_flow_anomalies(chain)
        assert result is None

    def test_returns_none_when_sklearn_not_installed(self) -> None:
        """Verify graceful degradation without sklearn."""
        with patch(
            "options_arena.indicators.flow_analytics._get_isolation_forest",
            return_value=None,
        ):
            chain = _make_normal_chain(30)
            result = detect_flow_anomalies(chain)
            assert result is None

    def test_returns_none_on_empty_chain(self) -> None:
        """Verify None on empty DataFrame."""
        chain = pd.DataFrame(columns=["volume", "openInterest"])
        result = detect_flow_anomalies(chain)
        assert result is None

    def test_anomaly_score_is_float(self) -> None:
        """Verify anomaly_score is a finite float."""
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = _make_normal_chain(30)
        result = detect_flow_anomalies(chain, avg_volume_20d=300.0)
        assert result is not None
        assert isinstance(result.anomaly_score, float)
        assert math.isfinite(result.anomaly_score)

    def test_is_anomalous_flag_matches_score(self) -> None:
        """Verify is_anomalous=True when score < 0."""
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = _make_normal_chain(30)
        result = detect_flow_anomalies(chain, avg_volume_20d=300.0)
        assert result is not None
        if result.anomaly_score < 0.0:
            assert result.is_anomalous is True
        else:
            assert result.is_anomalous is False

    def test_feature_contributions_has_4_keys(self) -> None:
        """Verify 4 feature contribution z-scores returned."""
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = _make_normal_chain(30)
        result = detect_flow_anomalies(chain, avg_volume_20d=300.0)
        assert result is not None
        assert len(result.feature_contributions) == 4
        expected_keys = {
            "vol_oi_ratio",
            "log_call_put_vol_ratio",
            "vol_avg_ratio",
            "large_trade_concentration",
        }
        assert set(result.feature_contributions.keys()) == expected_keys
        # All z-scores should be finite
        for val in result.feature_contributions.values():
            assert math.isfinite(val)

    def test_normal_chain_not_flagged(self) -> None:
        """Verify synthetic normal chain has is_anomalous=False for the aggregate.

        With contamination=0.1 and uniform flow, the mean decision function
        should be non-negative (i.e., aggregate is not flagged).
        """
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = _make_normal_chain(50)
        result = detect_flow_anomalies(chain, avg_volume_20d=300.0)
        assert result is not None
        # With uniform/normal data and contamination=0.1, aggregate mean score
        # should be positive (not anomalous)
        assert result.is_anomalous is False

    def test_missing_columns_returns_none(self) -> None:
        """Verify None when required columns are missing."""
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = pd.DataFrame({"strike": np.linspace(90, 110, 25), "bid": np.ones(25)})
        result = detect_flow_anomalies(chain)
        assert result is None

    def test_no_avg_volume_fallback(self) -> None:
        """Verify function works without avg_volume_20d (fallback to median)."""
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = _make_normal_chain(30)
        result = detect_flow_anomalies(chain, avg_volume_20d=None)
        assert result is not None
        assert math.isfinite(result.anomaly_score)

    def test_nan_avg_volume_fallback(self) -> None:
        """Verify function handles NaN avg_volume_20d gracefully."""
        if _get_isolation_forest() is None:
            pytest.skip("scikit-learn not installed")

        chain = _make_normal_chain(30)
        result = detect_flow_anomalies(chain, avg_volume_20d=float("nan"))
        assert result is not None
        assert math.isfinite(result.anomaly_score)


# ---------------------------------------------------------------------------
# TestFlowAnomalyResult
# ---------------------------------------------------------------------------


class TestFlowAnomalyResult:
    """Tests for FlowAnomalyResult NamedTuple."""

    def test_namedtuple_fields(self) -> None:
        """Verify NamedTuple has expected fields."""
        result = FlowAnomalyResult(
            anomaly_score=-0.5,
            is_anomalous=True,
            feature_contributions={"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0},
        )
        assert result.anomaly_score == pytest.approx(-0.5, rel=1e-6)
        assert result.is_anomalous is True
        assert len(result.feature_contributions) == 4
        # Verify it's a tuple subclass (NamedTuple)
        assert isinstance(result, tuple)
        # Verify field names
        assert FlowAnomalyResult._fields == (
            "anomaly_score",
            "is_anomalous",
            "feature_contributions",
        )


# ---------------------------------------------------------------------------
# TestConfigFlag
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestIndicatorSignalsField
# ---------------------------------------------------------------------------


class TestIndicatorSignalsField:
    """Tests for IndicatorSignals.flow_anomaly_score field."""

    def test_flow_anomaly_score_defaults_none(self) -> None:
        """Verify new field defaults to None."""
        signals = IndicatorSignals()
        assert signals.flow_anomaly_score is None

    def test_flow_anomaly_score_accepts_value(self) -> None:
        """Verify field accepts a valid float value."""
        signals = IndicatorSignals(flow_anomaly_score=-0.25)
        assert signals.flow_anomaly_score == pytest.approx(-0.25, rel=1e-6)

    def test_non_finite_normalized_to_none(self) -> None:
        """Verify NaN/Inf are normalized to None via _normalize_non_finite validator."""
        signals_nan = IndicatorSignals(flow_anomaly_score=float("nan"))
        assert signals_nan.flow_anomaly_score is None

        signals_inf = IndicatorSignals(flow_anomaly_score=float("inf"))
        assert signals_inf.flow_anomaly_score is None

        signals_ninf = IndicatorSignals(flow_anomaly_score=float("-inf"))
        assert signals_ninf.flow_anomaly_score is None
