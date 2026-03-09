"""Tests for agent calibration models.

Covers AgentAccuracyReport, CalibrationBucket, AgentCalibrationData,
and AgentWeightsComparison — validation, frozen behavior, and JSON roundtrip.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.models.analytics import (
    AgentAccuracyReport,
    AgentCalibrationData,
    AgentWeightsComparison,
    CalibrationBucket,
)

# ---------------------------------------------------------------------------
# AgentAccuracyReport
# ---------------------------------------------------------------------------


class TestAgentAccuracyReport:
    """Tests for AgentAccuracyReport model."""

    def test_valid_report(self) -> None:
        """Verify construction with valid data."""
        report = AgentAccuracyReport(
            agent_name="trend",
            direction_hit_rate=0.65,
            mean_confidence=0.72,
            brier_score=0.18,
            sample_size=50,
        )
        assert report.agent_name == "trend"
        assert report.direction_hit_rate == 0.65
        assert report.mean_confidence == 0.72
        assert report.brier_score == 0.18
        assert report.sample_size == 50

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True prevents field assignment."""
        report = AgentAccuracyReport(
            agent_name="trend",
            direction_hit_rate=0.65,
            mean_confidence=0.72,
            brier_score=0.18,
            sample_size=50,
        )
        with pytest.raises(ValidationError):
            report.direction_hit_rate = 0.5  # type: ignore[misc]

    def test_nan_rejected_direction_hit_rate(self) -> None:
        """Verify math.isfinite() rejects NaN on direction_hit_rate."""
        with pytest.raises(ValidationError, match="finite"):
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=float("nan"),
                mean_confidence=0.72,
                brier_score=0.18,
                sample_size=50,
            )

    def test_inf_rejected_mean_confidence(self) -> None:
        """Verify math.isfinite() rejects Inf on mean_confidence."""
        with pytest.raises(ValidationError, match="finite"):
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=0.65,
                mean_confidence=float("inf"),
                brier_score=0.18,
                sample_size=50,
            )

    def test_nan_rejected_brier_score(self) -> None:
        """Verify math.isfinite() rejects NaN on brier_score."""
        with pytest.raises(ValidationError, match="finite"):
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=0.65,
                mean_confidence=0.72,
                brier_score=float("nan"),
                sample_size=50,
            )

    def test_brier_score_range_above(self) -> None:
        """Verify brier_score rejects > 1.0."""
        with pytest.raises(ValidationError, match="0.0, 1.0"):
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=0.65,
                mean_confidence=0.72,
                brier_score=1.5,
                sample_size=50,
            )

    def test_brier_score_range_below(self) -> None:
        """Verify brier_score rejects < 0.0."""
        with pytest.raises(ValidationError, match="0.0, 1.0"):
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=0.65,
                mean_confidence=0.72,
                brier_score=-0.1,
                sample_size=50,
            )

    def test_direction_hit_rate_range(self) -> None:
        """Verify direction_hit_rate constrained to [0.0, 1.0]."""
        with pytest.raises(ValidationError, match="0.0, 1.0"):
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=1.5,
                mean_confidence=0.72,
                brier_score=0.18,
                sample_size=50,
            )

    def test_negative_sample_size_rejected(self) -> None:
        """Verify negative sample_size is rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            AgentAccuracyReport(
                agent_name="trend",
                direction_hit_rate=0.65,
                mean_confidence=0.72,
                brier_score=0.18,
                sample_size=-1,
            )

    def test_json_roundtrip(self) -> None:
        """Verify JSON serialization/deserialization preserves all fields."""
        report = AgentAccuracyReport(
            agent_name="volatility",
            direction_hit_rate=0.55,
            mean_confidence=0.68,
            brier_score=0.25,
            sample_size=30,
        )
        roundtripped = AgentAccuracyReport.model_validate_json(report.model_dump_json())
        assert roundtripped == report

    def test_boundary_values(self) -> None:
        """Verify edge values 0.0 and 1.0 are accepted."""
        report = AgentAccuracyReport(
            agent_name="flow",
            direction_hit_rate=0.0,
            mean_confidence=1.0,
            brier_score=0.0,
            sample_size=0,
        )
        assert report.direction_hit_rate == 0.0
        assert report.mean_confidence == 1.0
        assert report.brier_score == 0.0
        assert report.sample_size == 0


# ---------------------------------------------------------------------------
# CalibrationBucket
# ---------------------------------------------------------------------------


class TestCalibrationBucket:
    """Tests for CalibrationBucket model."""

    def test_valid_bucket(self) -> None:
        """Verify construction with valid bucket data."""
        bucket = CalibrationBucket(
            bucket_label="0.6-0.8",
            bucket_low=0.6,
            bucket_high=0.8,
            mean_confidence=0.72,
            actual_hit_rate=0.65,
            count=15,
        )
        assert bucket.bucket_label == "0.6-0.8"
        assert bucket.bucket_low == 0.6
        assert bucket.bucket_high == 0.8
        assert bucket.mean_confidence == 0.72
        assert bucket.actual_hit_rate == 0.65
        assert bucket.count == 15

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True."""
        bucket = CalibrationBucket(
            bucket_label="0.0-0.2",
            bucket_low=0.0,
            bucket_high=0.2,
            mean_confidence=0.1,
            actual_hit_rate=0.3,
            count=5,
        )
        with pytest.raises(ValidationError):
            bucket.count = 10  # type: ignore[misc]

    def test_nan_rejected_bucket_bounds(self) -> None:
        """Verify NaN rejected on bucket bounds."""
        with pytest.raises(ValidationError, match="finite"):
            CalibrationBucket(
                bucket_label="bad",
                bucket_low=float("nan"),
                bucket_high=0.2,
                mean_confidence=0.1,
                actual_hit_rate=0.3,
                count=5,
            )

    def test_negative_count_rejected(self) -> None:
        """Verify negative count is rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            CalibrationBucket(
                bucket_label="0.0-0.2",
                bucket_low=0.0,
                bucket_high=0.2,
                mean_confidence=0.1,
                actual_hit_rate=0.3,
                count=-1,
            )

    def test_hit_rate_out_of_range(self) -> None:
        """Verify actual_hit_rate rejects > 1.0."""
        with pytest.raises(ValidationError, match="0.0, 1.0"):
            CalibrationBucket(
                bucket_label="0.0-0.2",
                bucket_low=0.0,
                bucket_high=0.2,
                mean_confidence=0.1,
                actual_hit_rate=1.5,
                count=5,
            )

    def test_json_roundtrip(self) -> None:
        """Verify JSON roundtrip."""
        bucket = CalibrationBucket(
            bucket_label="0.4-0.6",
            bucket_low=0.4,
            bucket_high=0.6,
            mean_confidence=0.52,
            actual_hit_rate=0.48,
            count=20,
        )
        roundtripped = CalibrationBucket.model_validate_json(bucket.model_dump_json())
        assert roundtripped == bucket


# ---------------------------------------------------------------------------
# AgentCalibrationData
# ---------------------------------------------------------------------------


class TestAgentCalibrationData:
    """Tests for AgentCalibrationData model."""

    def _make_buckets(self) -> list[CalibrationBucket]:
        """Create a standard 5-bucket set."""
        labels = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
        bounds = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
        return [
            CalibrationBucket(
                bucket_label=label,
                bucket_low=low,
                bucket_high=high,
                mean_confidence=(low + high) / 2,
                actual_hit_rate=0.5,
                count=10,
            )
            for label, (low, high) in zip(labels, bounds, strict=True)
        ]

    def test_aggregate_view(self) -> None:
        """Verify agent_name=None for aggregate calibration."""
        data = AgentCalibrationData(
            agent_name=None,
            buckets=self._make_buckets(),
            sample_size=50,
        )
        assert data.agent_name is None
        assert len(data.buckets) == 5
        assert data.sample_size == 50

    def test_per_agent_view(self) -> None:
        """Verify agent_name set for per-agent calibration."""
        data = AgentCalibrationData(
            agent_name="trend",
            buckets=self._make_buckets(),
            sample_size=50,
        )
        assert data.agent_name == "trend"

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True."""
        data = AgentCalibrationData(
            agent_name="trend",
            buckets=[],
            sample_size=0,
        )
        with pytest.raises(ValidationError):
            data.sample_size = 10  # type: ignore[misc]

    def test_negative_sample_size_rejected(self) -> None:
        """Verify negative sample_size is rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            AgentCalibrationData(
                agent_name="trend",
                buckets=[],
                sample_size=-1,
            )

    def test_json_roundtrip(self) -> None:
        """Verify JSON roundtrip with nested buckets."""
        data = AgentCalibrationData(
            agent_name="volatility",
            buckets=self._make_buckets(),
            sample_size=50,
        )
        roundtripped = AgentCalibrationData.model_validate_json(data.model_dump_json())
        assert roundtripped == data


# ---------------------------------------------------------------------------
# AgentWeightsComparison
# ---------------------------------------------------------------------------


class TestAgentWeightsComparison:
    """Tests for AgentWeightsComparison model."""

    def test_valid_comparison(self) -> None:
        """Verify construction with Brier score."""
        cmp = AgentWeightsComparison(
            agent_name="trend",
            manual_weight=0.17,
            auto_weight=0.22,
            brier_score=0.18,
            sample_size=50,
        )
        assert cmp.agent_name == "trend"
        assert cmp.manual_weight == 0.17
        assert cmp.auto_weight == 0.22
        assert cmp.brier_score == 0.18
        assert cmp.sample_size == 50

    def test_no_brier_score(self) -> None:
        """Verify brier_score=None for insufficient samples."""
        cmp = AgentWeightsComparison(
            agent_name="contrarian",
            manual_weight=0.17,
            auto_weight=0.17,
            brier_score=None,
            sample_size=5,
        )
        assert cmp.brier_score is None

    def test_frozen_rejects_mutation(self) -> None:
        """Verify frozen=True."""
        cmp = AgentWeightsComparison(
            agent_name="trend",
            manual_weight=0.17,
            auto_weight=0.22,
            brier_score=0.18,
            sample_size=50,
        )
        with pytest.raises(ValidationError):
            cmp.auto_weight = 0.3  # type: ignore[misc]

    def test_nan_rejected_weight(self) -> None:
        """Verify NaN rejected on weight fields."""
        with pytest.raises(ValidationError, match="finite"):
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=float("nan"),
                auto_weight=0.22,
                brier_score=0.18,
                sample_size=50,
            )

    def test_negative_weight_rejected(self) -> None:
        """Verify negative weight is rejected."""
        with pytest.raises(ValidationError, match=">= 0.0"):
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=-0.1,
                auto_weight=0.22,
                brier_score=0.18,
                sample_size=50,
            )

    def test_inf_rejected_brier_score(self) -> None:
        """Verify Inf rejected on brier_score."""
        with pytest.raises(ValidationError, match="finite"):
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.17,
                auto_weight=0.22,
                brier_score=float("inf"),
                sample_size=50,
            )

    def test_brier_score_out_of_range(self) -> None:
        """Verify brier_score rejects > 1.0."""
        with pytest.raises(ValidationError, match="0.0, 1.0"):
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.17,
                auto_weight=0.22,
                brier_score=1.5,
                sample_size=50,
            )

    def test_negative_sample_size_rejected(self) -> None:
        """Verify negative sample_size is rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.17,
                auto_weight=0.22,
                brier_score=0.18,
                sample_size=-1,
            )

    def test_json_roundtrip(self) -> None:
        """Verify JSON serialization/deserialization."""
        cmp = AgentWeightsComparison(
            agent_name="flow",
            manual_weight=0.17,
            auto_weight=0.20,
            brier_score=0.22,
            sample_size=35,
        )
        roundtripped = AgentWeightsComparison.model_validate_json(cmp.model_dump_json())
        assert roundtripped == cmp

    def test_zero_weight_allowed(self) -> None:
        """Verify zero weight is valid (risk agent case)."""
        cmp = AgentWeightsComparison(
            agent_name="risk",
            manual_weight=0.0,
            auto_weight=0.0,
            brier_score=None,
            sample_size=0,
        )
        assert cmp.manual_weight == 0.0
        assert cmp.auto_weight == 0.0


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


class TestModelExports:
    """Verify models are exported from the models package."""

    def test_models_importable_from_package(self) -> None:
        """Verify all 4 new models are importable from options_arena.models."""
        from options_arena.models import (
            AgentAccuracyReport,
            AgentCalibrationData,
            AgentWeightsComparison,
            CalibrationBucket,
        )

        assert AgentAccuracyReport is not None
        assert CalibrationBucket is not None
        assert AgentCalibrationData is not None
        assert AgentWeightsComparison is not None
