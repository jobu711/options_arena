"""Health check model for Options Arena.

Single model for service health status:
  HealthStatus -- frozen snapshot of a service's availability.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
