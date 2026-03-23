"""Options Arena — Evaluation models for agent quality measurement.

EvalDefinition describes what to test. EvalRun records a single execution.
EvalReport aggregates runs into pass@k metrics with baseline comparison.
All models are frozen snapshots.
"""

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

from options_arena.models._validators import validate_unit_interval
from options_arena.models.enums import (
    DeskType,
    EvalType,
    EvalVerdict,
    GraderType,
    SignalDirection,
)


class EvalDefinition(BaseModel):
    """Specification for a single evaluation case.

    Stored as git-tracked JSON in ``.claude/evals/`` for reproducibility.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    eval_type: EvalType
    target_desk: DeskType | None = None  # None = synthesis agent
    description: str
    grader_type: GraderType
    market_context_fixture: str  # relative path to JSON fixture
    expected_direction: SignalDirection | None = None
    expected_confidence_min: float | None = None
    expected_confidence_max: float | None = None
    custom_assertions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v

    @field_validator("market_context_fixture")
    @classmethod
    def _validate_fixture_path(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("market_context_fixture must not be empty")
        if "\x00" in v:
            raise ValueError("market_context_fixture must not contain null bytes")
        from pathlib import PurePosixPath  # noqa: PLC0415

        parts = PurePosixPath(v).parts
        if ".." in parts:
            raise ValueError("market_context_fixture must not contain '..'")
        if PurePosixPath(v).is_absolute():
            raise ValueError("market_context_fixture must be a relative path")
        return v

    @field_validator("expected_confidence_min", "expected_confidence_max")
    @classmethod
    def _validate_confidence_bounds(cls, v: float | None) -> float | None:
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"confidence bound must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"confidence bound must be in [0, 1], got {v}")
        return v


class EvalRun(BaseModel):
    """Record of a single eval execution."""

    model_config = ConfigDict(frozen=True)

    id: int | None = None  # DB-assigned
    eval_name: str
    timestamp: datetime
    passed: bool
    attempts: int  # for pass@k
    successes: int
    model_used: str
    duration_ms: int
    details: str  # JSON grader output

    @field_validator("timestamp")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return v

    @field_validator("attempts", "successes")
    @classmethod
    def _validate_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_validator("duration_ms")
    @classmethod
    def _validate_duration(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"duration_ms must be >= 0, got {v}")
        return v


class EvalReport(BaseModel):
    """Aggregated eval results with pass@k metrics and baseline comparison."""

    model_config = ConfigDict(frozen=True)

    runs: list[EvalRun]
    pass_at_1: float
    pass_at_3: float
    regressions: list[str]  # eval names that regressed vs baseline
    verdict: EvalVerdict

    @field_validator("pass_at_1", "pass_at_3")
    @classmethod
    def _validate_pass_rate(cls, v: float) -> float:
        return validate_unit_interval(v, "pass_rate")


class EvalOutcome(BaseModel):
    """Single eval outcome for baseline comparison."""

    model_config = ConfigDict(frozen=True)

    eval_name: str
    passed: bool


class EvalBaseline(BaseModel):
    """Stored baseline for comparison — pass rates per eval name."""

    model_config = ConfigDict(frozen=True)

    eval_results: list[EvalOutcome]
    pass_at_1: float
    pass_at_3: float
    timestamp: datetime

    @field_validator("pass_at_1", "pass_at_3")
    @classmethod
    def _validate_pass_rate(cls, v: float) -> float:
        return validate_unit_interval(v, "pass_rate")

    @field_validator("timestamp")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return v
