"""Tests for HealthService._check_api_provider — shared API provider health check logic.

Covers all status-code branches, timeout/exception handling, and latency recording
for the extracted helper that backs both check_groq() and check_anthropic().
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.health import HealthStatus
from options_arena.services.health import HealthService

_PROVIDER_NAME = "test_provider"
_PROVIDER_URL = "https://api.example.com/v1/models"
_PROVIDER_HEADERS = {"Authorization": "Bearer test-key-123"}
_PROVIDER_TIMEOUT = 10.0


@pytest.fixture
def service() -> HealthService:
    """HealthService with minimal config for helper tests."""
    config = ServiceConfig(yfinance_timeout=5.0, fred_timeout=5.0)
    return HealthService(config)


class TestCheckApiProvider200:
    """HTTP 200 returns available=True with no error."""

    @pytest.mark.asyncio
    async def test_success_available(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=200,
            json={"data": []},
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert isinstance(result, HealthStatus)
        assert result.service_name == _PROVIDER_NAME
        assert result.available is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_success_passes_headers(self, service: HealthService) -> None:
        """Verify the helper forwards the exact headers to the HTTP client."""
        mock_response = httpx.Response(
            status_code=200,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        service._client.get.assert_awaited_once()
        call_args = service._client.get.call_args
        assert call_args.kwargs.get("headers") == _PROVIDER_HEADERS
        assert call_args.args[0] == _PROVIDER_URL


class TestCheckApiProvider401:
    """HTTP 401 returns available=False with 'invalid API key' error."""

    @pytest.mark.asyncio
    async def test_invalid_key(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=401,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == _PROVIDER_NAME
        assert result.available is False
        assert result.error is not None
        assert "invalid API key" in result.error
        assert "401" in result.error


class TestCheckApiProvider403:
    """HTTP 403 returns available=False with 'forbidden' error."""

    @pytest.mark.asyncio
    async def test_forbidden(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=403,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == _PROVIDER_NAME
        assert result.available is False
        assert result.error is not None
        assert "forbidden" in result.error
        assert "403" in result.error


class TestCheckApiProvider429:
    """HTTP 429 returns available=True with 'rate limited' warning."""

    @pytest.mark.asyncio
    async def test_rate_limited(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=429,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == _PROVIDER_NAME
        assert result.available is True
        assert result.error is not None
        assert "rate limited" in result.error
        assert "429" in result.error


class TestCheckApiProvider500:
    """HTTP 500+ returns available=False with 'HTTP {code}' error."""

    @pytest.mark.asyncio
    async def test_server_error_500(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=500,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == _PROVIDER_NAME
        assert result.available is False
        assert result.error == "HTTP 500"

    @pytest.mark.asyncio
    async def test_server_error_503(self, service: HealthService) -> None:
        """Other 5xx codes also return unavailable with correct error string."""
        mock_response = httpx.Response(
            status_code=503,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == _PROVIDER_NAME
        assert result.available is False
        assert result.error == "HTTP 503"


class TestCheckApiProviderTimeout:
    """Timeout exception returns available=False with exception type as error."""

    @pytest.mark.asyncio
    async def test_timeout_unavailable(self, service: HealthService) -> None:
        service._client.get = AsyncMock(  # type: ignore[method-assign]
            side_effect=TimeoutError("timed out"),
        )

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == _PROVIDER_NAME
        assert result.available is False
        assert result.error is not None
        assert result.error == "TimeoutError"

    @pytest.mark.asyncio
    async def test_connection_error_unavailable(self, service: HealthService) -> None:
        """Network-level failures also return unavailable."""
        service._client.get = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == _PROVIDER_NAME
        assert result.available is False
        assert result.error == "ConnectError"


class TestCheckApiProviderLatency:
    """Latency is always recorded as a positive value on both success and failure."""

    @pytest.mark.asyncio
    async def test_latency_on_success(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=200,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_latency_on_error_status(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=401,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_latency_on_exception(self, service: HealthService) -> None:
        service._client.get = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("refused"),
        )

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self, service: HealthService) -> None:
        """All returned HealthStatus objects have UTC-aware checked_at."""
        mock_response = httpx.Response(
            status_code=200,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name=_PROVIDER_NAME,
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.checked_at.tzinfo is not None


class TestCheckApiProviderServiceName:
    """The provider name is correctly propagated to HealthStatus.service_name."""

    @pytest.mark.asyncio
    async def test_custom_name(self, service: HealthService) -> None:
        mock_response = httpx.Response(
            status_code=200,
            request=httpx.Request("GET", _PROVIDER_URL),
        )
        service._client.get = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await service._check_api_provider(
            name="custom_llm_provider",
            url=_PROVIDER_URL,
            headers=_PROVIDER_HEADERS,
            timeout=_PROVIDER_TIMEOUT,
        )

        assert result.service_name == "custom_llm_provider"
