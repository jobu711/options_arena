"""Tests for prediction attribution models.

Covers PredictionSource, Prediction, PredictionAccuracy,
ConditionBucketAccuracy, ContractGuidance, and AttributionReport.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models.attribution import (
    AttributionReport,
    ConditionBucketAccuracy,
    ContractGuidance,
    Prediction,
    PredictionAccuracy,
    PredictionSource,
)
from options_arena.models.enums import SignalDirection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


def _make_prediction(**overrides: object) -> Prediction:
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "source": PredictionSource.DESK_TREND,
        "predicted_direction": SignalDirection.BULLISH,
        "confidence": 0.75,
        "recommendation_id": 1,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return Prediction(**defaults)


def _make_accuracy(**overrides: object) -> PredictionAccuracy:
    defaults: dict[str, object] = {
        "source": PredictionSource.DESK_TREND,
        "total": 20,
        "correct": 14,
        "accuracy": 0.70,
        "sample_sufficient": True,
    }
    defaults.update(overrides)
    return PredictionAccuracy(**defaults)


def _make_condition_bucket_accuracy(**overrides: object) -> ConditionBucketAccuracy:
    defaults: dict[str, object] = {
        "source": PredictionSource.DESK_VOLATILITY,
        "condition": "adx_strong",
        "total": 15,
        "correct": 10,
        "accuracy": 0.667,
    }
    defaults.update(overrides)
    return ConditionBucketAccuracy(**defaults)


def _make_contract_guidance(**overrides: object) -> ContractGuidance:
    defaults: dict[str, object] = {
        "optimal_delta_low": 0.25,
        "optimal_delta_high": 0.45,
        "optimal_dte_low": 30,
        "optimal_dte_high": 60,
        "delta_win_rate": 0.62,
        "dte_win_rate": 0.58,
        "sample_count": 100,
    }
    defaults.update(overrides)
    return ContractGuidance(**defaults)


def _make_attribution_report(**overrides: object) -> AttributionReport:
    defaults: dict[str, object] = {
        "window_days": 30,
        "total_recommendations": 50,
        "total_outcomes": 40,
        "source_accuracy": [_make_accuracy()],
        "condition_accuracy": [_make_condition_bucket_accuracy()],
        "contract_guidance": _make_contract_guidance(),
    }
    defaults.update(overrides)
    return AttributionReport(**defaults)


# ---------------------------------------------------------------------------
# PredictionSource enum
# ---------------------------------------------------------------------------


class TestPredictionSource:
    def test_member_count(self) -> None:
        assert len(PredictionSource) == 8

    def test_values_are_lowercase_strings(self) -> None:
        expected = {
            "scan_direction",
            "desk_trend",
            "desk_volatility",
            "desk_flow",
            "desk_fundamental",
            "desk_risk",
            "desk_contrarian",
            "synthesis",
        }
        assert {m.value for m in PredictionSource} == expected

    def test_is_strenum(self) -> None:
        assert isinstance(PredictionSource.DESK_TREND, str)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


class TestPrediction:
    def test_valid_with_recommendation_id(self) -> None:
        p = _make_prediction(recommendation_id=42, scan_run_id=None)
        assert p.recommendation_id == 42
        assert p.scan_run_id is None

    def test_valid_with_scan_run_id(self) -> None:
        p = _make_prediction(recommendation_id=None, scan_run_id=7)
        assert p.scan_run_id == 7
        assert p.recommendation_id is None

    def test_valid_with_both_fks(self) -> None:
        p = _make_prediction(recommendation_id=1, scan_run_id=2)
        assert p.recommendation_id == 1
        assert p.scan_run_id == 2

    def test_rejects_both_fks_none(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            _make_prediction(recommendation_id=None, scan_run_id=None)

    def test_confidence_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_prediction(confidence=float("nan"))

    def test_confidence_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_prediction(confidence=float("inf"))

    def test_confidence_out_of_range_high(self) -> None:
        with pytest.raises(ValidationError, match="confidence"):
            _make_prediction(confidence=1.5)

    def test_confidence_out_of_range_low(self) -> None:
        with pytest.raises(ValidationError, match="confidence"):
            _make_prediction(confidence=-0.1)

    def test_context_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_prediction(adx=float("nan"))

    def test_frozen_mutation_rejected(self) -> None:
        p = _make_prediction()
        with pytest.raises(ValidationError):
            p.ticker = "MSFT"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        p = _make_prediction(
            adx=25.0,
            iv_rank=40.0,
            atr_pct=3.5,
            rsi=55.0,
            was_correct=True,
        )
        restored = Prediction.model_validate_json(p.model_dump_json())
        assert restored == p

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            _make_prediction(created_at=datetime(2026, 1, 1))

    def test_non_utc_datetime_rejected(self) -> None:
        non_utc = datetime(2026, 1, 1, tzinfo=timezone(offset=timedelta(hours=5)))
        with pytest.raises(ValidationError, match="UTC"):
            _make_prediction(created_at=non_utc)

    def test_default_id_is_none(self) -> None:
        p = _make_prediction()
        assert p.id is None

    def test_was_correct_none_default(self) -> None:
        p = _make_prediction()
        assert p.was_correct is None

    def test_context_fields_none_default(self) -> None:
        p = _make_prediction()
        assert p.adx is None
        assert p.iv_rank is None
        assert p.atr_pct is None
        assert p.rsi is None


# ---------------------------------------------------------------------------
# PredictionAccuracy
# ---------------------------------------------------------------------------


class TestPredictionAccuracy:
    def test_valid_construction(self) -> None:
        a = _make_accuracy()
        assert a.source == PredictionSource.DESK_TREND
        assert a.total == 20
        assert a.correct == 14
        assert a.accuracy == pytest.approx(0.70, abs=0.01)
        assert a.sample_sufficient is True

    def test_accuracy_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_accuracy(accuracy=float("nan"))

    def test_accuracy_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="accuracy"):
            _make_accuracy(accuracy=1.5)

    def test_frozen(self) -> None:
        a = _make_accuracy()
        with pytest.raises(ValidationError):
            a.total = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ConditionBucketAccuracy
# ---------------------------------------------------------------------------


class TestConditionBucketAccuracy:
    def test_valid_construction(self) -> None:
        cb = _make_condition_bucket_accuracy()
        assert cb.source == PredictionSource.DESK_VOLATILITY
        assert cb.condition == "adx_strong"
        assert cb.total == 15
        assert cb.correct == 10

    def test_accuracy_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_condition_bucket_accuracy(accuracy=float("nan"))

    def test_accuracy_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_condition_bucket_accuracy(accuracy=float("inf"))


# ---------------------------------------------------------------------------
# ContractGuidance
# ---------------------------------------------------------------------------


class TestContractGuidance:
    def test_valid_construction(self) -> None:
        g = _make_contract_guidance()
        assert g.optimal_delta_low == pytest.approx(0.25, abs=0.01)
        assert g.optimal_dte_low == 30
        assert g.sample_count == 100

    def test_win_rate_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="win rate"):
            _make_contract_guidance(delta_win_rate=1.5)

    def test_delta_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_contract_guidance(optimal_delta_low=float("nan"))

    def test_win_rate_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_contract_guidance(delta_win_rate=float("nan"))

    def test_frozen(self) -> None:
        g = _make_contract_guidance()
        with pytest.raises(ValidationError):
            g.sample_count = 200  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AttributionReport
# ---------------------------------------------------------------------------


class TestAttributionReport:
    def test_valid_with_guidance(self) -> None:
        r = _make_attribution_report()
        assert r.window_days == 30
        assert r.total_recommendations == 50
        assert r.contract_guidance is not None

    def test_valid_without_guidance(self) -> None:
        r = _make_attribution_report(contract_guidance=None)
        assert r.contract_guidance is None

    def test_frozen(self) -> None:
        r = _make_attribution_report()
        with pytest.raises(ValidationError):
            r.window_days = 60  # type: ignore[misc]

    def test_negative_window_days_rejected(self) -> None:
        with pytest.raises(ValidationError, match="window_days"):
            _make_attribution_report(window_days=-1)


# ---------------------------------------------------------------------------
# NaN/Inf defense — parametrized
# ---------------------------------------------------------------------------


class TestPredictionNaNDefense:
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_confidence_non_finite(self, value: float) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_prediction(confidence=value)

    @pytest.mark.parametrize("field", ["adx", "iv_rank", "atr_pct", "rsi"])
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_context_fields_non_finite(self, field: str, value: float) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_prediction(**{field: value})


# ---------------------------------------------------------------------------
# JSON roundtrip — all 5 models
# ---------------------------------------------------------------------------


class TestJsonRoundtrip:
    @pytest.mark.critical
    def test_prediction_roundtrip(self) -> None:
        p = _make_prediction(adx=25.0, rsi=55.0, was_correct=True)
        restored = Prediction.model_validate_json(p.model_dump_json())
        assert restored == p

    def test_prediction_accuracy_roundtrip(self) -> None:
        a = _make_accuracy()
        restored = PredictionAccuracy.model_validate_json(a.model_dump_json())
        assert restored == a

    def test_condition_bucket_accuracy_roundtrip(self) -> None:
        cb = _make_condition_bucket_accuracy()
        restored = ConditionBucketAccuracy.model_validate_json(cb.model_dump_json())
        assert restored == cb

    def test_contract_guidance_roundtrip(self) -> None:
        g = _make_contract_guidance()
        restored = ContractGuidance.model_validate_json(g.model_dump_json())
        assert restored == g

    def test_attribution_report_roundtrip(self) -> None:
        r = _make_attribution_report()
        restored = AttributionReport.model_validate_json(r.model_dump_json())
        assert restored == r


# ---------------------------------------------------------------------------
# PredictionSource enum roundtrip
# ---------------------------------------------------------------------------


class TestPredictionSourceRoundtrip:
    @pytest.mark.parametrize("source", list(PredictionSource))
    def test_roundtrip_via_value(self, source: PredictionSource) -> None:
        restored = PredictionSource(source.value)
        assert restored is source

    @pytest.mark.parametrize("source", list(PredictionSource))
    def test_prediction_with_each_source(self, source: PredictionSource) -> None:
        p = _make_prediction(source=source)
        assert p.source is source
        # JSON roundtrip preserves source identity
        restored = Prediction.model_validate_json(p.model_dump_json())
        assert restored.source is source
