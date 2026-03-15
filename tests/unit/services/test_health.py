"""Tests for services.health — pre-flight health checks for external dependencies."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.health import HealthStatus
from options_arena.services.financial_datasets import FinancialDatasetsService
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

    @pytest.mark.critical
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
        assert result.error == "ConnectionError"
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
# check_anthropic
# ---------------------------------------------------------------------------


class TestCheckAnthropic:
    """Tests for Anthropic API health check."""

    @pytest.mark.asyncio
    async def test_no_api_key_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Anthropic check without API key returns available=False."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = ServiceConfig(anthropic_api_key=None, groq_api_key=None)
        svc = HealthService(config)

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is False
        assert result.error is not None
        assert "no API key" in result.error
        assert result.checked_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_success_200(self, service: HealthService) -> None:
        """Anthropic reachable with valid API key returns available=True."""
        # Set anthropic_api_key on the config
        config = ServiceConfig(
            anthropic_api_key="sk-ant-test-key",
            groq_api_key="gsk_test_key_for_health",
        )
        svc = HealthService(config)
        mock_response = httpx.Response(
            status_code=200,
            json={"data": [{"id": "claude-sonnet-4-5-20250929"}]},
            request=httpx.Request("GET", "test"),
        )
        svc._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None
        # Verify correct headers were used
        call_kwargs = svc._client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert "x-api-key" in headers
        assert headers["anthropic-version"] == "2023-06-01"

    @pytest.mark.asyncio
    async def test_invalid_key_401(self, service: HealthService) -> None:
        """Anthropic returning 401 marks service as unavailable with clear error."""
        config = ServiceConfig(
            anthropic_api_key="sk-ant-bad-key",
            groq_api_key="gsk_test_key_for_health",
        )
        svc = HealthService(config)
        mock_response = httpx.Response(
            status_code=401,
            request=httpx.Request("GET", "test"),
        )
        svc._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is False
        assert result.error is not None
        assert "invalid API key" in result.error

    @pytest.mark.asyncio
    async def test_server_error_500(self, service: HealthService) -> None:
        """Anthropic returning HTTP 500 marks service as unavailable."""
        config = ServiceConfig(
            anthropic_api_key="sk-ant-test-key",
            groq_api_key="gsk_test_key_for_health",
        )
        svc = HealthService(config)
        mock_response = httpx.Response(
            status_code=500,
            request=httpx.Request("GET", "test"),
        )
        svc._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is False
        assert result.error == "HTTP 500"

    @pytest.mark.asyncio
    async def test_forbidden_403(self, service: HealthService) -> None:
        """Anthropic returning 403 marks service as unavailable."""
        config = ServiceConfig(
            anthropic_api_key="sk-ant-test-key",
            groq_api_key="gsk_test_key_for_health",
        )
        svc = HealthService(config)
        mock_response = httpx.Response(
            status_code=403,
            request=httpx.Request("GET", "test"),
        )
        svc._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is False
        assert result.error is not None
        assert "403" in result.error

    @pytest.mark.asyncio
    async def test_rate_limited_429(self, service: HealthService) -> None:
        """Anthropic returning 429 marks service as available but rate-limited."""
        config = ServiceConfig(
            anthropic_api_key="sk-ant-test-key",
            groq_api_key="gsk_test_key_for_health",
        )
        svc = HealthService(config)
        mock_response = httpx.Response(
            status_code=429,
            request=httpx.Request("GET", "test"),
        )
        svc._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is True
        assert result.error is not None
        assert "429" in result.error

    @pytest.mark.asyncio
    async def test_network_exception(self, service: HealthService) -> None:
        """Anthropic connection error returns available=False with error."""
        config = ServiceConfig(
            anthropic_api_key="sk-ant-test-key",
            groq_api_key="gsk_test_key_for_health",
        )
        svc = HealthService(config)
        svc._client.get = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is False
        assert result.error is not None
        assert result.latency_ms is not None
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Anthropic uses ANTHROPIC_API_KEY env var when config key is None."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        config = ServiceConfig(anthropic_api_key=None, groq_api_key=None)
        svc = HealthService(config)
        mock_response = httpx.Response(
            status_code=200,
            json={"data": []},
            request=httpx.Request("GET", "test"),
        )
        svc._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await svc.check_anthropic()

        assert result.service_name == "anthropic"
        assert result.available is True

    @pytest.mark.asyncio
    async def test_check_all_includes_anthropic(self, service: HealthService) -> None:
        """check_all() includes anthropic in the results."""
        anthropic_status = HealthStatus(
            service_name="anthropic",
            available=True,
            latency_ms=25.0,
            checked_at=_utc_now(),
        )
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
            available=False,
            latency_ms=5.0,
            error="OpenBB SDK not installed",
            checked_at=_utc_now(),
        )
        cboe_chains_status = HealthStatus(
            service_name="cboe_chains",
            available=False,
            error="CBOE chains disabled",
            checked_at=_utc_now(),
        )
        intel_status = HealthStatus(
            service_name="intelligence",
            available=True,
            latency_ms=15.0,
            checked_at=_utc_now(),
        )

        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(return_value=fred_status)  # type: ignore[method-assign]
        service.check_groq = AsyncMock(return_value=groq_status)  # type: ignore[method-assign]
        service.check_anthropic = AsyncMock(return_value=anthropic_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=cboe_status)  # type: ignore[method-assign]
        service.check_openbb = AsyncMock(return_value=openbb_status)  # type: ignore[method-assign]
        service.check_cboe_chains = AsyncMock(return_value=cboe_chains_status)  # type: ignore[method-assign]
        service.check_intelligence = AsyncMock(return_value=intel_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 8
        names = {r.service_name for r in results}
        assert "anthropic" in names
        anthropic_result = next(r for r in results if r.service_name == "anthropic")
        assert anthropic_result.available is True


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
        """All checks succeed: 8 HealthStatus objects, all available."""
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
        anthropic_status = HealthStatus(
            service_name="anthropic",
            available=True,
            latency_ms=25.0,
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
        cboe_chains_status = HealthStatus(
            service_name="cboe_chains",
            available=False,
            error="CBOE chains disabled",
            checked_at=_utc_now(),
        )
        intel_status = HealthStatus(
            service_name="intelligence",
            available=True,
            latency_ms=15.0,
            checked_at=_utc_now(),
        )

        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(return_value=fred_status)  # type: ignore[method-assign]
        service.check_groq = AsyncMock(return_value=groq_status)  # type: ignore[method-assign]
        service.check_anthropic = AsyncMock(return_value=anthropic_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=cboe_status)  # type: ignore[method-assign]
        service.check_openbb = AsyncMock(return_value=openbb_status)  # type: ignore[method-assign]
        service.check_cboe_chains = AsyncMock(return_value=cboe_chains_status)  # type: ignore[method-assign]
        service.check_intelligence = AsyncMock(return_value=intel_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 8
        assert all(isinstance(r, HealthStatus) for r in results)

    @pytest.mark.asyncio
    async def test_partial_failure(self, service: HealthService) -> None:
        """Three succeed, five fail: all 8 HealthStatus objects returned with correct flags."""
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
        anthropic_status = HealthStatus(
            service_name="anthropic",
            available=True,
            latency_ms=25.0,
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
        cboe_chains_status = HealthStatus(
            service_name="cboe_chains",
            available=False,
            error="CBOE chains disabled",
            checked_at=_utc_now(),
        )
        intel_status = HealthStatus(
            service_name="intelligence",
            available=False,
            latency_ms=25.0,
            error="timeout",
            checked_at=_utc_now(),
        )

        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(return_value=fred_status)  # type: ignore[method-assign]
        service.check_groq = AsyncMock(return_value=groq_status)  # type: ignore[method-assign]
        service.check_anthropic = AsyncMock(return_value=anthropic_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=cboe_status)  # type: ignore[method-assign]
        service.check_openbb = AsyncMock(return_value=openbb_status)  # type: ignore[method-assign]
        service.check_cboe_chains = AsyncMock(return_value=cboe_chains_status)  # type: ignore[method-assign]
        service.check_intelligence = AsyncMock(return_value=intel_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 8
        names_available = {r.service_name: r.available for r in results}
        assert names_available["yfinance"] is True
        assert names_available["fred"] is False
        assert names_available["groq"] is True
        assert names_available["anthropic"] is True
        assert names_available["cboe"] is False
        assert names_available["openbb"] is False
        assert names_available["cboe_chains"] is False
        assert names_available["intelligence"] is False

    @pytest.mark.asyncio
    async def test_unhandled_exception_becomes_health_status(self, service: HealthService) -> None:
        """If a check raises an unhandled exception in gather, it becomes HealthStatus(False)."""
        yf_status = HealthStatus(
            service_name="yfinance",
            available=True,
            latency_ms=50.0,
            checked_at=_utc_now(),
        )
        anthropic_status = HealthStatus(
            service_name="anthropic",
            available=True,
            latency_ms=25.0,
            checked_at=_utc_now(),
        )
        openbb_status = HealthStatus(
            service_name="openbb",
            available=False,
            latency_ms=5.0,
            error="OpenBB SDK not installed",
            checked_at=_utc_now(),
        )
        cboe_chains_status = HealthStatus(
            service_name="cboe_chains",
            available=False,
            error="CBOE chains disabled",
            checked_at=_utc_now(),
        )
        intel_status = HealthStatus(
            service_name="intelligence",
            available=True,
            latency_ms=15.0,
            checked_at=_utc_now(),
        )
        # Simulate an unhandled exception escaping from check_fred
        service.check_yfinance = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_fred = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        service.check_groq = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_anthropic = AsyncMock(return_value=anthropic_status)  # type: ignore[method-assign]
        service.check_cboe = AsyncMock(return_value=yf_status)  # type: ignore[method-assign]
        service.check_openbb = AsyncMock(return_value=openbb_status)  # type: ignore[method-assign]
        service.check_cboe_chains = AsyncMock(return_value=cboe_chains_status)  # type: ignore[method-assign]
        service.check_intelligence = AsyncMock(return_value=intel_status)  # type: ignore[method-assign]

        results = await service.check_all()

        assert len(results) == 8
        fred_result = results[1]  # second in the list (order preserved)
        assert fred_result.service_name == "fred"
        assert fred_result.available is False
        assert fred_result.error is not None
        assert fred_result.error == "RuntimeError"


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
# check_financial_datasets
# ---------------------------------------------------------------------------


class TestCheckFinancialDatasets:
    """Tests for Financial Datasets health check."""

    @pytest.mark.asyncio
    async def test_healthy(self) -> None:
        """Successful FD check returns available=True with latency."""
        from options_arena.models.config import FinancialDatasetsConfig

        fd_config = FinancialDatasetsConfig(enabled=True, api_key="test_fd_key")
        svc_config = ServiceConfig(yfinance_timeout=5.0, fred_timeout=5.0)
        svc = HealthService(svc_config, fd_config=fd_config)

        from options_arena.models.financial_datasets import FinancialMetricsData

        mock_result = FinancialMetricsData(pe_ratio=28.5)
        with (
            patch.object(
                FinancialDatasetsService,
                "fetch_financial_metrics",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch.object(FinancialDatasetsService, "close", new_callable=AsyncMock),
        ):
            result = await svc.check_financial_datasets()

        assert isinstance(result, HealthStatus)
        assert result.service_name == "financial_datasets"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_unhealthy_no_data(self) -> None:
        """FD check returns available=False when no data returned."""
        from options_arena.models.config import FinancialDatasetsConfig

        fd_config = FinancialDatasetsConfig(enabled=True, api_key="test_fd_key")
        svc_config = ServiceConfig(yfinance_timeout=5.0, fred_timeout=5.0)
        svc = HealthService(svc_config, fd_config=fd_config)

        with (
            patch.object(
                FinancialDatasetsService,
                "fetch_financial_metrics",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(FinancialDatasetsService, "close", new_callable=AsyncMock),
        ):
            result = await svc.check_financial_datasets()

        assert result.service_name == "financial_datasets"
        assert result.available is False
        assert result.error == "No data returned"

    @pytest.mark.asyncio
    async def test_unhealthy_exception(self) -> None:
        """FD check returns available=False on API failure."""
        from options_arena.models.config import FinancialDatasetsConfig

        fd_config = FinancialDatasetsConfig(enabled=True, api_key="test_fd_key")
        svc_config = ServiceConfig(yfinance_timeout=5.0, fred_timeout=5.0)
        svc = HealthService(svc_config, fd_config=fd_config)

        with (
            patch.object(
                FinancialDatasetsService,
                "fetch_financial_metrics",
                new_callable=AsyncMock,
                side_effect=ConnectionError("API down"),
            ),
            patch.object(FinancialDatasetsService, "close", new_callable=AsyncMock),
        ):
            result = await svc.check_financial_datasets()

        assert result.service_name == "financial_datasets"
        assert result.available is False
        assert result.error == "ConnectionError"

    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        """FD check returns available=False when config disabled."""
        from options_arena.models.config import FinancialDatasetsConfig

        fd_config = FinancialDatasetsConfig(enabled=False, api_key="test_fd_key")
        svc_config = ServiceConfig(yfinance_timeout=5.0, fred_timeout=5.0)
        svc = HealthService(svc_config, fd_config=fd_config)

        result = await svc.check_financial_datasets()

        assert result.service_name == "financial_datasets"
        assert result.available is False
        assert "disabled" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_no_api_key(self) -> None:
        """FD check returns available=False when no API key."""
        from options_arena.models.config import FinancialDatasetsConfig

        fd_config = FinancialDatasetsConfig(enabled=True, api_key=None)
        svc_config = ServiceConfig(yfinance_timeout=5.0, fred_timeout=5.0)
        svc = HealthService(svc_config, fd_config=fd_config)

        result = await svc.check_financial_datasets()

        assert result.service_name == "financial_datasets"
        assert result.available is False
        assert "no api key" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_check_all_includes_fd_when_enabled(self) -> None:
        """Verify check_all includes FD check when config enabled."""
        from options_arena.models.config import FinancialDatasetsConfig

        fd_config = FinancialDatasetsConfig(enabled=True, api_key="test_fd_key")
        svc_config = ServiceConfig(
            yfinance_timeout=5.0,
            fred_timeout=5.0,
            groq_api_key="gsk_test",
        )
        svc = HealthService(svc_config, fd_config=fd_config)

        # Mock ALL check methods to avoid real API calls
        # Map method names to production service_name values
        method_service_map = {
            "check_yfinance": "yfinance",
            "check_fred": "fred",
            "check_groq": "groq",
            "check_anthropic": "anthropic",
            "check_cboe": "cboe",
            "check_openbb": "openbb",
            "check_cboe_chains": "cboe_chains",
            "check_intelligence": "intelligence",
            "check_financial_datasets": "financial_datasets",
        }
        for method_name, service_name in method_service_map.items():
            mock = AsyncMock(
                return_value=HealthStatus(
                    service_name=service_name,
                    available=True,
                    checked_at=_utc_now(),
                )
            )
            setattr(svc, method_name, mock)

        results = await svc.check_all()
        service_names = [r.service_name for r in results]
        assert "financial_datasets" in service_names

    @pytest.mark.asyncio
    async def test_check_all_omits_fd_when_no_config(self) -> None:
        """Verify check_all skips FD check when fd_config is None."""
        svc_config = ServiceConfig(
            yfinance_timeout=5.0,
            fred_timeout=5.0,
            groq_api_key="gsk_test",
        )
        # No fd_config provided -> fd check skipped
        svc = HealthService(svc_config)

        # Mock ALL base check methods to avoid real API calls
        # Map method names to production service_name values
        method_service_map = {
            "check_yfinance": "yfinance",
            "check_fred": "fred",
            "check_groq": "groq",
            "check_anthropic": "anthropic",
            "check_cboe": "cboe",
            "check_openbb": "openbb",
            "check_cboe_chains": "cboe_chains",
            "check_intelligence": "intelligence",
        }
        for method_name, service_name in method_service_map.items():
            mock = AsyncMock(
                return_value=HealthStatus(
                    service_name=service_name,
                    available=True,
                    checked_at=_utc_now(),
                )
            )
            setattr(svc, method_name, mock)

        results = await svc.check_all()
        service_names = [r.service_name for r in results]
        assert "financial_datasets" not in service_names

    @pytest.mark.asyncio
    async def test_check_all_includes_fd_when_disabled(self) -> None:
        """Verify check_all includes FD check even when disabled (returns diagnostic status)."""
        from options_arena.models.config import FinancialDatasetsConfig

        fd_config = FinancialDatasetsConfig(enabled=False, api_key="test_fd_key")
        svc_config = ServiceConfig(
            yfinance_timeout=5.0,
            fred_timeout=5.0,
            groq_api_key="gsk_test",
        )
        svc = HealthService(svc_config, fd_config=fd_config)

        # Mock ALL check methods to avoid real API calls
        method_service_map = {
            "check_yfinance": "yfinance",
            "check_fred": "fred",
            "check_groq": "groq",
            "check_anthropic": "anthropic",
            "check_cboe": "cboe",
            "check_openbb": "openbb",
            "check_cboe_chains": "cboe_chains",
            "check_intelligence": "intelligence",
            "check_financial_datasets": "financial_datasets",
        }
        for method_name, service_name in method_service_map.items():
            mock = AsyncMock(
                return_value=HealthStatus(
                    service_name=service_name,
                    available=False,
                    error="disabled" if service_name == "financial_datasets" else None,
                    checked_at=_utc_now(),
                )
            )
            setattr(svc, method_name, mock)

        results = await svc.check_all()
        service_names = [r.service_name for r in results]
        assert "financial_datasets" in service_names
        fd_result = next(r for r in results if r.service_name == "financial_datasets")
        assert fd_result.available is False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return current UTC datetime for test fixture construction."""
    return datetime.now(UTC)
