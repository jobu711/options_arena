"""Frozen Pydantic models for the mathematical computation audit framework.

Defines typed models for audit findings, layer summaries, and reports.
All models are frozen (immutable) snapshots. No business logic, no I/O.
"""

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import AuditLayer, AuditSeverity

# Number of mathematical functions tracked by the audit framework.
# Update when adding/removing auditable functions in pricing/, indicators/, scoring/.
MATH_FUNCTION_COUNT: int = 92


class AuditFinding(BaseModel):
    """A single finding from a mathematical computation audit.

    Represents a specific issue (or passing result) discovered during audit
    testing of a mathematical function.
    """

    model_config = ConfigDict(frozen=True)

    function_name: str
    layer: AuditLayer
    severity: AuditSeverity
    description: str
    expected_value: float | None = None
    actual_value: float | None = None
    tolerance: float | None = None
    source: str | None = None
    proposed_test: str | None = None

    @field_validator("expected_value", "actual_value", "tolerance")
    @classmethod
    def _validate_finite_or_none(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on numeric fields (None is allowed)."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite or None, got {v}")
        return v


class AuditLayerSummary(BaseModel):
    """Summary of audit results for a single audit layer.

    Aggregates counts of tested/passed/failed functions and all findings
    for one audit layer (correctness, stability, performance, discovery).
    """

    model_config = ConfigDict(frozen=True)

    layer: AuditLayer
    total_functions: int
    tested_functions: int
    passed: int
    failed: int
    coverage_pct: float
    findings: list[AuditFinding]

    @field_validator("coverage_pct")
    @classmethod
    def _validate_coverage_pct(cls, v: float) -> float:
        """Ensure coverage_pct is finite and within [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"coverage_pct must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"coverage_pct must be in [0.0, 1.0], got {v}")
        return v


class AuditReport(BaseModel):
    """Complete audit report aggregating all layer summaries.

    Top-level model for the mathematical computation audit. Contains
    a UTC-validated timestamp, per-layer summaries, and aggregate counts.
    """

    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    layers: list[AuditLayerSummary]
    total_findings: int
    critical_count: int
    warning_count: int
    info_count: int

    @field_validator("generated_at")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        """Enforce UTC timezone on generated_at."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("generated_at must be UTC")
        return v
