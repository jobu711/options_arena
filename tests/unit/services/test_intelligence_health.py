"""Tests for intelligence health check in HealthService.

Verifies that ``check_intelligence()`` probes yfinance analyst price targets
and that ``check_all()`` includes the intelligence check alongside all others.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.health import HealthStatus
from options_arena.services.health import HealthService


@pytest.fixture
def health_service() -> HealthService:
    """HealthService with default config for intelligence tests."""
    config = ServiceConfig()
    return HealthService(config)


# ---------------------------------------------------------------------------
# check_intelligence
# ---------------------------------------------------------------------------


class TestCheckIntelligence:
    """Tests for the intelligence health check method."""

    @pytest.mark.asyncio
    async def test_healthy_returns_available(self, health_service: HealthService) -> None:
        """Successful yfinance analyst call returns available=True."""
        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=MagicMock())

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await health_service.check_intelligence()

        assert isinstance(result, HealthStatus)
        assert result.available is True
        assert result.service_name == "intelligence"
        assert result.error is None
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_timeout_returns_unavailable(self, health_service: HealthService) -> None:
        """Timeout during yfinance call returns available=False."""
        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(side_effect=TimeoutError("timeout"))

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await health_service.check_intelligence()

        assert result.available is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_exception_returns_unavailable(self, health_service: HealthService) -> None:
        """Generic exception returns available=False with error message."""
        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(
            side_effect=RuntimeError("network failure")
        )

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await health_service.check_intelligence()

        assert result.available is False
        assert result.error is not None
        assert "network failure" in result.error

    @pytest.mark.asyncio
    async def test_latency_measured_on_success(self, health_service: HealthService) -> None:
        """Latency is measured on successful check."""
        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=MagicMock())

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await health_service.check_intelligence()

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_latency_measured_on_failure(self, health_service: HealthService) -> None:
        """Latency is always measured, even on failure."""
        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(side_effect=RuntimeError("fail"))

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await health_service.check_intelligence()

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_service_name_is_intelligence(self, health_service: HealthService) -> None:
        """Service name is always 'intelligence'."""
        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=MagicMock())

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await health_service.check_intelligence()

        assert result.service_name == "intelligence"

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self, health_service: HealthService) -> None:
        """checked_at timestamp is UTC-aware."""
        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=MagicMock())

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await health_service.check_intelligence()

        assert result.checked_at.tzinfo is not None
        assert result.checked_at.utcoffset() == UTC.utcoffset(None)


# ---------------------------------------------------------------------------
# check_all includes intelligence
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return current UTC datetime for test fixture construction."""
    return datetime.now(UTC)


class TestCheckAllIncludesIntelligence:
    """Tests that check_all() includes the intelligence health check."""

    @pytest.mark.asyncio
    async def test_check_all_includes_intelligence(self, health_service: HealthService) -> None:
        """check_all() results include an intelligence check (7 total)."""
        ok_status = HealthStatus(
            service_name="mock", available=True, latency_ms=10.0, checked_at=_utc_now()
        )

        health_service.check_yfinance = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_fred = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_groq = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_cboe = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_openbb = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_cboe_chains = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_intelligence = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]

        results = await health_service.check_all()

        assert len(results) == 7
        health_service.check_intelligence.assert_awaited_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_intelligence_failure_doesnt_crash_check_all(
        self, health_service: HealthService
    ) -> None:
        """If intelligence check raises, check_all still completes with 7 results."""
        ok_status = HealthStatus(
            service_name="mock", available=True, latency_ms=10.0, checked_at=_utc_now()
        )

        health_service.check_yfinance = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_fred = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_groq = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_cboe = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_openbb = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_cboe_chains = AsyncMock(return_value=ok_status)  # type: ignore[method-assign]
        health_service.check_intelligence = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

        results = await health_service.check_all()

        assert len(results) == 7
        # The intelligence check exception should be converted to HealthStatus(available=False)
        intel_result = [r for r in results if r.service_name == "intelligence"]
        assert len(intel_result) == 1
        assert intel_result[0].available is False
        assert "boom" in (intel_result[0].error or "")
