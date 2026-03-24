"""Prediction attribution models for Options Arena.

Six frozen Pydantic v2 models for the prediction ledger:
  PredictionSource     — StrEnum of decision points that produce predictions.
  Prediction           — immutable snapshot of an intermediate directional decision.
  PredictionAccuracy   — per-source accuracy statistics.
  ConditionBucketAccuracy — accuracy within a condition bucket (e.g. ADX regime).
  ContractGuidance     — learned optimal contract parameters.
  AttributionReport    — top-level report aggregating all attribution data.

All snapshot models use ``frozen=True``. All float validators check ``math.isfinite()``.
All datetime fields enforce UTC.
"""

import math
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from options_arena.models.enums import SignalDirection


class PredictionSource(StrEnum):
    """Decision point that produced a prediction.

    Maps to the scan pipeline direction phase, the 6 recommendation desk agents,
    and the synthesis agent. Research desk is excluded because it is interactive
    and does not produce a ``DomainAssessment``.
    """

    SCAN_DIRECTION = "scan_direction"
    DESK_TREND = "desk_trend"
    DESK_VOLATILITY = "desk_volatility"
    DESK_FLOW = "desk_flow"
    DESK_FUNDAMENTAL = "desk_fundamental"
    DESK_RISK = "desk_risk"
    DESK_CONTRARIAN = "desk_contrarian"
    SYNTHESIS = "synthesis"


class Prediction(BaseModel):
    """An intermediate directional decision that can be scored against reality.

    Frozen snapshot — all fields immutable after construction. At least one of
    ``recommendation_id`` or ``scan_run_id`` must be set (enforced by model
    validator). Context snapshot fields (``adx``, ``iv_rank``, ``atr_pct``,
    ``rsi``) capture indicator values at decision time for dimensional slicing.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    recommendation_id: int | None = None
    scan_run_id: int | None = None
    ticker: str
    source: PredictionSource
    predicted_direction: SignalDirection
    confidence: float
    adx: float | None = None
    iv_rank: float | None = None
    atr_pct: float | None = None
    rsi: float | None = None
    was_correct: bool | None = None
    created_at: datetime

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("adx", "iv_rank", "atr_pct", "rsi")
    @classmethod
    def _validate_context_float(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError(f"context field must be finite, got {v}")
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v

    @model_validator(mode="after")
    def _validate_fk(self) -> "Prediction":
        if self.recommendation_id is None and self.scan_run_id is None:
            raise ValueError("at least one of recommendation_id or scan_run_id must be set")
        return self


class PredictionAccuracy(BaseModel):
    """Accuracy statistics for a single prediction source.

    ``sample_sufficient`` indicates whether ``total`` meets the minimum
    threshold for statistical reliability.
    """

    model_config = ConfigDict(frozen=True)

    source: PredictionSource
    total: int
    correct: int
    accuracy: float
    sample_sufficient: bool

    @field_validator("accuracy")
    @classmethod
    def _validate_accuracy(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"accuracy must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"accuracy must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("total")
    @classmethod
    def _validate_total(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"total must be >= 0, got {v}")
        return v

    @field_validator("correct")
    @classmethod
    def _validate_correct(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"correct must be >= 0, got {v}")
        return v

    @model_validator(mode="after")
    def _validate_correct_le_total(self) -> "PredictionAccuracy":
        if self.correct > self.total:
            raise ValueError(f"correct ({self.correct}) must be <= total ({self.total})")
        return self


class ConditionBucketAccuracy(BaseModel):
    """Accuracy for a prediction source within a condition bucket.

    ``condition`` describes the bucket (e.g. ``"adx_strong"``, ``"iv_rank_low"``).
    """

    model_config = ConfigDict(frozen=True)

    source: PredictionSource
    condition: str
    total: int
    correct: int
    accuracy: float

    @field_validator("accuracy")
    @classmethod
    def _validate_accuracy(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"accuracy must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"accuracy must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("total")
    @classmethod
    def _validate_total(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"total must be >= 0, got {v}")
        return v

    @field_validator("correct")
    @classmethod
    def _validate_correct(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"correct must be >= 0, got {v}")
        return v

    @model_validator(mode="after")
    def _validate_correct_le_total(self) -> "ConditionBucketAccuracy":
        if self.correct > self.total:
            raise ValueError(f"correct ({self.correct}) must be <= total ({self.total})")
        return self


class ContractGuidance(BaseModel):
    """Learned optimal contract parameters from historical outcome analysis.

    Delta and DTE ranges that historically produced the best win rates,
    intended for injection into the synthesis agent prompt.
    """

    model_config = ConfigDict(frozen=True)

    optimal_delta_low: float
    optimal_delta_high: float
    optimal_dte_low: int
    optimal_dte_high: int
    delta_win_rate: float
    dte_win_rate: float
    sample_count: int

    @field_validator("optimal_delta_low", "optimal_delta_high")
    @classmethod
    def _validate_delta(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"delta field must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"delta must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("optimal_dte_low", "optimal_dte_high")
    @classmethod
    def _validate_dte(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"DTE must be >= 0, got {v}")
        return v

    @field_validator("delta_win_rate", "dte_win_rate")
    @classmethod
    def _validate_win_rate(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"win rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"win rate must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("sample_count")
    @classmethod
    def _validate_sample_count(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"sample_count must be >= 0, got {v}")
        return v

    @model_validator(mode="after")
    def _validate_ranges(self) -> "ContractGuidance":
        if self.optimal_delta_low > self.optimal_delta_high:
            raise ValueError(
                f"optimal_delta_low ({self.optimal_delta_low}) must be "
                f"<= optimal_delta_high ({self.optimal_delta_high})"
            )
        if self.optimal_dte_low > self.optimal_dte_high:
            raise ValueError(
                f"optimal_dte_low ({self.optimal_dte_low}) must be "
                f"<= optimal_dte_high ({self.optimal_dte_high})"
            )
        return self


class AttributionReport(BaseModel):
    """Full attribution output aggregating source accuracy, condition accuracy,
    and learned contract guidance over a time window.
    """

    model_config = ConfigDict(frozen=True)

    window_days: int
    total_recommendations: int
    total_outcomes: int
    source_accuracy: list[PredictionAccuracy]
    condition_accuracy: list[ConditionBucketAccuracy]
    contract_guidance: ContractGuidance | None

    @field_validator("window_days")
    @classmethod
    def _validate_window_days(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"window_days must be >= 0, got {v}")
        return v

    @field_validator("total_recommendations")
    @classmethod
    def _validate_total_recommendations(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"total_recommendations must be >= 0, got {v}")
        return v

    @field_validator("total_outcomes")
    @classmethod
    def _validate_total_outcomes(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"total_outcomes must be >= 0, got {v}")
        return v
