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
        ollama_timeout=5.0,
        ollama_host="http://localhost:11434",
        ollama_model="llama3.1:8b",
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
        mock_ticker.fast_info = property(
            lambda self: (_ for _ in ()).throw(ConnectionError("network down"))
        )
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
# check_ollama
# ---------------------------------------------------------------------------


class TestCheckOllama:
    """Tests for Ollama health check."""

    @pytest.mark.asyncio
    async def test_success_with_model_present(self, service: HealthService) -> None:
        """Ollama reachable with configured model returns available=True."""
        mock_response = httpx.Response(
            status_code=200,
            json={"models": [{"name": "llama3.1:8b"}, {"name": "codellama:7b"}]},
            request=httpx.Request("GET", "test"),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_ollama()

        assert result.service_name == "ollama"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_model_missing(self, service: HealthService) -> None:
        """Ollama reachable but configured model not found returns available=False."""
        mock_response = httpx.Response(
            status_code=200,
            json={"models": [{"name": "codellama:7b"}, {"name": "mistral:latest"}]},
            request=httpx.Request("GET", "test"),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_ollama()

        assert result.service_name == "ollama"
        assert result.available is False
        assert result.error is not None
        assert "llama3.1:8b" in result.error
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_connection_failure(self, service: HealthService) -> None:
        """Ollama connection error returns available=False."""
        service._client.get = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        result = await service.check_ollama()

        assert result.service_name == "ollama"
        assert result.available is False
        assert result.error is not None
        assert result.latency_ms is not None
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_server_error_500(self, service: HealthService) -> None:
        """Ollama returning HTTP 500 marks service as unavailable."""
        mock_response = httpx.Response(
            status_code=500,
            request=httpx.Request("GET", "test"),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service.check_ollama()

        assert result.service_name == "ollama"
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
        """All checks succeed: 4 HealthStatus objects, all available."""
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
        ollama_status = HealthStatus(
            service_name="ollama",
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

        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(return_value=fred_status)  # type: ignore[method-assign]
        service.check_ollama = AsyncMock(return_value=ollama_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=cboe_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 4
        assert all(isinstance(r, HealthStatus) for r in results)
        assert all(r.available for r in results)

    @pytest.mark.asyncio
    async def test_partial_failure(self, service: HealthService) -> None:
        """Two succeed, two fail: all 4 HealthStatus objects returned with correct flags."""
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
        ollama_status = HealthStatus(
            service_name="ollama",
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

        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(return_value=fred_status)  # type: ignore[method-assign]
        service.check_ollama = AsyncMock(return_value=ollama_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=cboe_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 4
        names_available = {r.service_name: r.available for r in results}
        assert names_available["yfinance"] is True
        assert names_available["fred"] is False
        assert names_available["ollama"] is True
        assert names_available["cboe"] is False

    @pytest.mark.asyncio
    async def test_unhandled_exception_becomes_health_status(self, service: HealthService) -> None:
        """If a check raises an unhandled exception in gather, it becomes HealthStatus(False)."""
        yf_status = HealthStatus(
            service_name="yfinance",
            available=True,
            latency_ms=50.0,
            checked_at=_utc_now(),
        )
        # Simulate an unhandled exception escaping from check_fred
        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        service.check_ollama = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 4
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
