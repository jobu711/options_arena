"""Unit tests for the HealthStatus model.

Tests cover:
- Happy path construction with all fields
- Frozen enforcement (attribute reassignment raises ValidationError)
- Optional fields default to None
- JSON serialization roundtrip
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from options_arena.models import HealthStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_health_available() -> HealthStatus:
    """Create a valid HealthStatus for an available service."""
    return HealthStatus(
        service_name="ollama",
        available=True,
        latency_ms=42.5,
        checked_at=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_health_unavailable() -> HealthStatus:
    """Create a valid HealthStatus for an unavailable service."""
    return HealthStatus(
        service_name="ollama",
        available=False,
        error="Connection refused",
        checked_at=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# HealthStatus Tests
# ---------------------------------------------------------------------------


class TestHealthStatus:
    """Tests for the HealthStatus model."""

    def test_happy_path_construction(self, sample_health_available: HealthStatus) -> None:
        """HealthStatus constructs with all fields correctly assigned."""
        assert sample_health_available.service_name == "ollama"
        assert sample_health_available.available is True
        assert sample_health_available.latency_ms == pytest.approx(42.5)
        assert sample_health_available.error is None
        assert sample_health_available.checked_at == datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)

    def test_frozen_enforcement(self, sample_health_available: HealthStatus) -> None:
        """HealthStatus is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_health_available.available = False  # type: ignore[misc]

    def test_latency_ms_defaults_to_none(self) -> None:
        """HealthStatus latency_ms defaults to None when not provided."""
        status = HealthStatus(
            service_name="fred",
            available=True,
            checked_at=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
        )
        assert status.latency_ms is None

    def test_error_defaults_to_none(self) -> None:
        """HealthStatus error defaults to None when not provided."""
        status = HealthStatus(
            service_name="yfinance",
            available=True,
            checked_at=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
        )
        assert status.error is None

    def test_naive_checked_at_raises(self) -> None:
        """HealthStatus rejects naive datetime for checked_at."""
        with pytest.raises(ValidationError, match="timezone-aware"):
            HealthStatus(
                service_name="ollama",
                available=True,
                checked_at=datetime(2025, 6, 15, 14, 30, 0),  # naive
            )

    def test_json_roundtrip_available(self, sample_health_available: HealthStatus) -> None:
        """HealthStatus (available) survives JSON roundtrip."""
        json_str = sample_health_available.model_dump_json()
        restored = HealthStatus.model_validate_json(json_str)
        assert restored == sample_health_available

    def test_json_roundtrip_unavailable(self, sample_health_unavailable: HealthStatus) -> None:
        """HealthStatus (unavailable with error) survives JSON roundtrip."""
        json_str = sample_health_unavailable.model_dump_json()
        restored = HealthStatus.model_validate_json(json_str)
        assert restored == sample_health_unavailable
