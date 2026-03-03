"""Tests for OpenBB health check in HealthService.

Tests cover:
  - check_openbb() returns available=False when SDK not installed
  - check_openbb() returns available=True when SDK importable
  - check_openbb() handles unexpected errors gracefully
  - check_openbb() measures latency
  - check_openbb() never raises
  - check_all() includes openbb status
  - check_all() returns 7 statuses (includes intelligence)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from options_arena.models.config import ServiceConfig
from options_arena.services.health import HealthService


@pytest.fixture()
def health_service() -> HealthService:
    """HealthService with default config."""
    return HealthService(config=ServiceConfig())


class TestCheckOpenBB:
    """Tests for check_openbb() method."""

    @pytest.mark.asyncio
    async def test_sdk_not_installed_returns_unavailable(
        self, health_service: HealthService
    ) -> None:
        """ImportError → available=False, error='OpenBB SDK not installed'."""
        import sys

        # Force ImportError deterministically — None in sys.modules blocks import
        with patch.dict(sys.modules, {"openbb": None}):
            result = await health_service.check_openbb()
        assert result.service_name == "openbb"
        assert result.available is False
        assert result.error == "OpenBB SDK not installed"

    @pytest.mark.asyncio
    async def test_sdk_available_returns_available(self, health_service: HealthService) -> None:
        """Mocked successful import → available=True."""
        import sys
        from unittest.mock import MagicMock

        fake_obb = MagicMock()
        fake_openbb = MagicMock()
        fake_openbb.obb = fake_obb

        with patch.dict(sys.modules, {"openbb": fake_openbb}):
            result = await health_service.check_openbb()

        assert result.service_name == "openbb"
        assert result.available is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_unavailable(
        self, health_service: HealthService
    ) -> None:
        """Generic exception → available=False with error message."""
        # Make the import raise a non-ImportError
        import builtins

        original_import = builtins.__import__

        def failing_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "openbb":
                raise RuntimeError("SDK crash")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=failing_import):
            result = await health_service.check_openbb()

        assert result.service_name == "openbb"
        assert result.available is False
        assert "SDK crash" in (result.error or "")

    @pytest.mark.asyncio
    async def test_latency_measured(self, health_service: HealthService) -> None:
        """latency_ms >= 0 regardless of success/failure."""
        result = await health_service.check_openbb()
        assert result.latency_ms is not None
        assert result.latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_never_raises(self, health_service: HealthService) -> None:
        """No exception propagates — always returns HealthStatus."""
        # This should work even without OpenBB installed
        result = await health_service.check_openbb()
        assert result.service_name == "openbb"
        # Result is a HealthStatus regardless of SDK state
        assert result.checked_at is not None


class TestCheckAllIncludesOpenBB:
    """Tests for check_all() including OpenBB."""

    @pytest.mark.asyncio
    async def test_check_all_returns_openbb_status(self, health_service: HealthService) -> None:
        """check_all() result includes 'openbb' service entry."""
        # Mock all external checks to avoid network calls
        health_service.check_yfinance = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("yfinance")
        )
        health_service.check_fred = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("fred")
        )
        health_service.check_groq = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("groq")
        )
        health_service.check_cboe = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("cboe")
        )
        health_service.check_intelligence = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("intelligence")
        )
        # check_openbb will run naturally (no SDK installed → unavailable)

        results = await health_service.check_all()
        service_names = [r.service_name for r in results]
        assert "openbb" in service_names

    @pytest.mark.asyncio
    async def test_check_all_count_is_seven(self, health_service: HealthService) -> None:
        """check_all() returns 7 statuses including intelligence."""
        health_service.check_yfinance = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("yfinance")
        )
        health_service.check_fred = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("fred")
        )
        health_service.check_groq = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("groq")
        )
        health_service.check_cboe = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("cboe")
        )

        results = await health_service.check_all()
        assert len(results) == 7


def _make_status(name: str, available: bool = True) -> object:
    """Build a mock HealthStatus for testing."""
    from datetime import UTC, datetime

    from options_arena.models.health import HealthStatus

    return HealthStatus(
        service_name=name,
        available=available,
        latency_ms=10.0,
        checked_at=datetime.now(UTC),
    )
