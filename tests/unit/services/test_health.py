"""Tests for services.health — pre-flight health checks for external dependencies."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.health import HealthStatus
from options_arena.services.health import HealthService


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig for tests."""
    return ServiceConfig(
        yfinance_timeout=5.0,
        fred_timeout=5.0,
        groq_api_key="gsk_test_key_for_health",
    )


@pytest.fixture
def service(config: ServiceConfig) -> HealthService:
    """HealthService instance with default config."""
    return HealthService(config)


# ---------------------------------------------------------------------------
# check_yfinance
# ---------------------------------------------------------------------------


class TestCheckYfinance:
    """Tests for yfinance health check."""

    @pytest.mark.asyncio
    async def test_success(self, service: HealthService) -> None:
        """Successful yfinance check returns available=True with latency."""
        mock_fast_info = MagicMock()
        mock_fast_info.last_price = 500.0

        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_fast_info

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.check_yfinance()

        assert isinstance(result, HealthStatus)
        assert result.service_name == "yfinance"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None
        assert result.checked_at.tzinfo is not None
        assert result.checked_at.utcoffset() == UTC.utcoffset(None)

    @pytest.mark.asyncio
    async def test_failure(self, service: HealthService) -> None:
        """Failed yfinance check returns available=False with error message."""
        mock_ticker = MagicMock()
        # Simulate accessing fast_info raising an exception in the thread
        type(mock_ticker).fast_info = property(
            fget=MagicMock(side_effect=ConnectionError("network down"))
        )

        with patch("options_arena.services.health.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.check_yfinance()

        assert isinstance(result, HealthStatus)
        assert result.service_name == "yfinance"
        assert result.available is False
        assert result.error is not None
        assert "network down" in result.error
        assert result.latency_ms is not None
        assert result.latency_ms > 0


# ---------------------------------------------------------------------------
# check_fred
# ---------------------------------------------------------------------------


class TestCheckFred:
    """Tests for FRED API health check."""

    @pytest.mark.asyncio
    async def test_success(self, service: HealthService) -> None:
        """Successful FRED check returns available=True."""
        mock_response = httpx.Response(status_code=200, request=httpx.Request("HEAD", "test"))
        service._client.head = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_fred()

        assert isinstance(result, HealthStatus)
        assert result.service_name == "fred"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_server_error(self, service: HealthService) -> None:
        """FRED returning 500 marks service as unavailable."""
        mock_response = httpx.Response(status_code=500, request=httpx.Request("HEAD", "test"))
        service._client.head = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_fred()

        assert result.service_name == "fred"
        assert result.available is False
        assert result.error == "HTTP 500"

    @pytest.mark.asyncio
    async def test_connection_failure(self, service: HealthService) -> None:
        """FRED connection error returns available=False with error."""
        service._client.head = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        result = await service.check_fred()

        assert result.service_name == "fred"
        assert result.available is False
        assert result.error is not None
        assert result.latency_ms is not None
        assert result.latency_ms > 0


# ---------------------------------------------------------------------------
# check_groq
# ---------------------------------------------------------------------------


class TestCheckGroq:
    """Tests for Groq API health check."""

    @pytest.mark.asyncio
    async def test_success(self, service: HealthService) -> None:
        """Groq reachable with valid API key returns available=True."""
        mock_response = httpx.Response(
            status_code=200,
            json={"data": [{"id": "llama-3.3-70b-versatile"}]},
            request=httpx.Request("GET", "test"),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_groq()

        assert result.service_name == "groq"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_invalid_api_key_401(self, service: HealthService) -> None:
        """Groq returning 401 marks service as unavailable with clear error."""
        mock_response = httpx.Response(
            status_code=401,
            request=httpx.Request("GET", "test"),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_groq()

        assert result.service_name == "groq"
        assert result.available is False
        assert result.error is not None
        assert "invalid API key" in result.error

    @pytest.mark.asyncio
    async def test_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Groq check without API key returns available=False."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = ServiceConfig(groq_api_key=None)
        svc = HealthService(config)

        result = await svc.check_groq()

        assert result.service_name == "groq"
        assert result.available is False
        assert result.error is not None
        assert "no API key" in result.error

    @pytest.mark.asyncio
    async def test_connection_failure(self, service: HealthService) -> None:
        """Groq connection error returns available=False."""
        service._client.get = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        result = await service.check_groq()

        assert result.service_name == "groq"
        assert result.available is False
        assert result.error is not None
        assert result.latency_ms is not None
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_server_error_500(self, service: HealthService) -> None:
        """Groq returning HTTP 500 marks service as unavailable."""
        mock_response = httpx.Response(
            status_code=500,
            request=httpx.Request("GET", "test"),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_groq()

        assert result.service_name == "groq"
        assert result.available is False
        assert result.error == "HTTP 500"


# ---------------------------------------------------------------------------
# check_cboe
# ---------------------------------------------------------------------------


class TestCheckCboe:
    """Tests for CBOE health check."""

    @pytest.mark.asyncio
    async def test_success(self, service: HealthService) -> None:
        """Successful CBOE check returns available=True."""
        mock_response = httpx.Response(status_code=200, request=httpx.Request("HEAD", "test"))
        service._client.head = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_cboe()

        assert isinstance(result, HealthStatus)
        assert result.service_name == "cboe"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_connection_failure(self, service: HealthService) -> None:
        """CBOE connection error returns available=False."""
        service._client.head = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        result = await service.check_cboe()

        assert result.service_name == "cboe"
        assert result.available is False
        assert result.error is not None
        assert result.latency_ms is not None


# ---------------------------------------------------------------------------
# check_all
# ---------------------------------------------------------------------------


class TestCheckAll:
    """Tests for concurrent check_all."""

    @pytest.mark.asyncio
    async def test_all_succeed(self, service: HealthService) -> None:
        """All checks succeed: 5 HealthStatus objects, all available."""
        yf_status = HealthStatus(
            service_name="yfinance",
            available=True,
            latency_ms=50.0,
            checked_at=_utc_now(),
        )
        fred_status = HealthStatus(
            service_name="fred",
            available=True,
            latency_ms=30.0,
            checked_at=_utc_now(),
        )
        groq_status = HealthStatus(
            service_name="groq",
            available=True,
            latency_ms=20.0,
            checked_at=_utc_now(),
        )
        cboe_status = HealthStatus(
            service_name="cboe",
            available=True,
            latency_ms=40.0,
            checked_at=_utc_now(),
        )
        openbb_status = HealthStatus(
            service_name="openbb",
            available=True,
            latency_ms=10.0,
            checked_at=_utc_now(),
        )

        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(return_value=fred_status)  # type: ignore[method-assign]
        service.check_groq = AsyncMock(return_value=groq_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=cboe_status)  # type: ignore[method-assign]
        service.check_openbb = AsyncMock(return_value=openbb_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 5
        assert all(isinstance(r, HealthStatus) for r in results)
        assert all(r.available for r in results)

    @pytest.mark.asyncio
    async def test_partial_failure(self, service: HealthService) -> None:
        """Two succeed, three fail: all 5 HealthStatus objects returned with correct flags."""
        yf_status = HealthStatus(
            service_name="yfinance",
            available=True,
            latency_ms=50.0,
            checked_at=_utc_now(),
        )
        fred_status = HealthStatus(
            service_name="fred",
            available=False,
            latency_ms=100.0,
            error="connection refused",
            checked_at=_utc_now(),
        )
        groq_status = HealthStatus(
            service_name="groq",
            available=True,
            latency_ms=20.0,
            checked_at=_utc_now(),
        )
        cboe_status = HealthStatus(
            service_name="cboe",
            available=False,
            latency_ms=80.0,
            error="HTTP 503",
            checked_at=_utc_now(),
        )
        openbb_status = HealthStatus(
            service_name="openbb",
            available=False,
            latency_ms=5.0,
            error="OpenBB SDK not installed",
            checked_at=_utc_now(),
        )

        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(return_value=fred_status)  # type: ignore[method-assign]
        service.check_groq = AsyncMock(return_value=groq_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=cboe_status)  # type: ignore[method-assign]
        service.check_openbb = AsyncMock(return_value=openbb_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 5
        names_available = {r.service_name: r.available for r in results}
        assert names_available["yfinance"] is True
        assert names_available["fred"] is False
        assert names_available["groq"] is True
        assert names_available["cboe"] is False
        assert names_available["openbb"] is False

    @pytest.mark.asyncio
    async def test_unhandled_exception_becomes_health_status(self, service: HealthService) -> None:
        """If a check raises an unhandled exception in gather, it becomes HealthStatus(False)."""
        yf_status = HealthStatus(
            service_name="yfinance",
            available=True,
            latency_ms=50.0,
            checked_at=_utc_now(),
        )
        openbb_status = HealthStatus(
            service_name="openbb",
            available=False,
            latency_ms=5.0,
            error="OpenBB SDK not installed",
            checked_at=_utc_now(),
        )
        # Simulate an unhandled exception escaping from check_fred
        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        service.check_groq = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_openbb = AsyncMock(return_value=openbb_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 5
        fred_result = results[1]  # second in the list (order preserved)
        assert fred_result.service_name == "fred"
        assert fred_result.available is False
        assert fred_result.error is not None
        assert "boom" in fred_result.error


# ---------------------------------------------------------------------------
# Latency recording
# ---------------------------------------------------------------------------


class TestLatencyRecording:
    """Verify that latency_ms is always positive on both success and failure paths."""

    @pytest.mark.asyncio
    async def test_latency_recorded_on_success(self, service: HealthService) -> None:
        """Successful checks record positive latency."""
        mock_response = httpx.Response(status_code=200, request=httpx.Request("HEAD", "test"))
        service._client.head = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_fred()

        assert result.latency_ms is not None
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_latency_recorded_on_failure(self, service: HealthService) -> None:
        """Failed checks still record positive latency."""
        service._client.head = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("refused"),
        )

        result = await service.check_fred()

        assert result.latency_ms is not None
        assert result.latency_ms > 0


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    """Tests for client lifecycle."""

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, service: HealthService) -> None:
        """close() delegates to httpx client.aclose()."""
        service._client.aclose = AsyncMock()  # type: ignore[method-assign]
        await service.close()
        service._client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return current UTC datetime for test fixture construction."""
    return datetime.now(UTC)
