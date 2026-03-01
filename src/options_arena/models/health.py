"""Health check model for Options Arena.

Single model for service health status:
  HealthStatus -- frozen snapshot of a service's availability.
"""

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator


class HealthStatus(BaseModel):
    """Health check result for an external service.

    Frozen (immutable after construction) -- represents a point-in-time health check.
    ``latency_ms`` and ``error`` are ``None`` when not applicable.
    ``checked_at`` must be a UTC-aware ``datetime``.
    """

    model_config = ConfigDict(frozen=True)

    service_name: str
    available: bool
    latency_ms: float | None = None
    error: str | None = None
    checked_at: datetime

    @field_validator("latency_ms")
    @classmethod
    def validate_latency_finite(cls, v: float | None) -> float | None:
        """Ensure latency_ms is finite when provided."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"latency_ms must be finite, got {v}")
        return v

    @field_validator("checked_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure checked_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("checked_at must be UTC")
        return v
