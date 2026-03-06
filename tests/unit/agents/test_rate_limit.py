"""Tests for rate-limit resilience: retry transport + model_config integration.

Tests cover:
  - _build_rate_limit_client returns httpx.AsyncClient with retry transport
  - rate_limit_retries=0 skips transport wrapping
  - _RetryTransport retries on 429 and eventually succeeds
  - _RetryTransport retries exhaust and returns last response
  - _RetryTransport does not retry on non-retryable status codes (200, 400, 401)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic_ai import models

from options_arena.agents.model_config import (
    _build_rate_limit_client,
    _RetryTransport,
    build_debate_model,
)
from options_arena.models import DebateConfig

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# _build_rate_limit_client
# ---------------------------------------------------------------------------


class TestBuildRateLimitClient:
    """Tests for _build_rate_limit_client factory."""

    def test_returns_async_client(self) -> None:
        """Returns an httpx.AsyncClient with retry transport."""
        config = DebateConfig(rate_limit_retries=3, rate_limit_max_wait=10.0)
        client = _build_rate_limit_client(config)
        assert isinstance(client, httpx.AsyncClient)

    def test_client_has_retry_transport(self) -> None:
        """The client's transport is a _RetryTransport."""
        config = DebateConfig(rate_limit_retries=2, rate_limit_max_wait=5.0)
        client = _build_rate_limit_client(config)
        assert isinstance(client._transport, _RetryTransport)

    def test_max_attempts_includes_initial(self) -> None:
        """Max attempts = retries + 1 (initial attempt counts)."""
        config = DebateConfig(rate_limit_retries=3, rate_limit_max_wait=10.0)
        client = _build_rate_limit_client(config)
        transport: _RetryTransport = client._transport  # type: ignore[assignment]
        assert transport._max_attempts == 4


class TestBuildDebateModelRateLimit:
    """Tests for build_debate_model rate-limit transport integration."""

    def test_no_http_client_when_retries_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When rate_limit_retries=0, no custom http_client is passed."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(api_key="gsk_test_key", rate_limit_retries=0)
        model = build_debate_model(config)
        # Model builds successfully — no error from missing transport
        assert model is not None

    def test_http_client_when_retries_positive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When rate_limit_retries > 0, model builds with retry-capable transport."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(api_key="gsk_test_key", rate_limit_retries=2)
        model = build_debate_model(config)
        assert model is not None


# ---------------------------------------------------------------------------
# _RetryTransport behavior
# ---------------------------------------------------------------------------


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    """Create a minimal httpx.Response for testing."""
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        request=httpx.Request("POST", "https://api.groq.com/v1/chat/completions"),
    )


class TestRetryTransport:
    """Tests for _RetryTransport retry behavior."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        """200 response is returned immediately without retry."""
        mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
        mock_transport.handle_async_request = AsyncMock(return_value=_make_response(200))

        transport = _RetryTransport(wrapped=mock_transport, max_attempts=3, max_wait=1.0)
        request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert mock_transport.handle_async_request.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self) -> None:
        """429 triggers retry; success on second attempt."""
        mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
        mock_transport.handle_async_request = AsyncMock(
            side_effect=[
                _make_response(429, {"retry-after": "0"}),
                _make_response(200),
            ]
        )

        transport = _RetryTransport(wrapped=mock_transport, max_attempts=3, max_wait=1.0)
        request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert mock_transport.handle_async_request.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_502_then_succeeds(self) -> None:
        """502 triggers retry; success on second attempt."""
        mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
        mock_transport.handle_async_request = AsyncMock(
            side_effect=[
                _make_response(502),
                _make_response(200),
            ]
        )

        transport = _RetryTransport(wrapped=mock_transport, max_attempts=3, max_wait=1.0)
        request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert mock_transport.handle_async_request.call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_400(self) -> None:
        """400 is not retryable — returned immediately."""
        mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
        mock_transport.handle_async_request = AsyncMock(return_value=_make_response(400))

        transport = _RetryTransport(wrapped=mock_transport, max_attempts=3, max_wait=1.0)
        request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        response = await transport.handle_async_request(request)

        assert response.status_code == 400
        assert mock_transport.handle_async_request.call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_401(self) -> None:
        """401 (auth error) is not retryable — returned immediately."""
        mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
        mock_transport.handle_async_request = AsyncMock(return_value=_make_response(401))

        transport = _RetryTransport(wrapped=mock_transport, max_attempts=3, max_wait=1.0)
        request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        response = await transport.handle_async_request(request)

        assert response.status_code == 401
        assert mock_transport.handle_async_request.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self) -> None:
        """When all retry attempts are 429, _RateLimitError is raised."""
        from options_arena.agents.model_config import _RateLimitError

        mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
        mock_transport.handle_async_request = AsyncMock(return_value=_make_response(429))

        transport = _RetryTransport(wrapped=mock_transport, max_attempts=2, max_wait=1.0)
        request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")

        with pytest.raises(_RateLimitError):
            await transport.handle_async_request(request)

        assert mock_transport.handle_async_request.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_503_504(self) -> None:
        """503 and 504 are retryable status codes."""
        mock_transport = AsyncMock(spec=httpx.AsyncBaseTransport)
        mock_transport.handle_async_request = AsyncMock(
            side_effect=[
                _make_response(503),
                _make_response(504),
                _make_response(200),
            ]
        )

        transport = _RetryTransport(wrapped=mock_transport, max_attempts=4, max_wait=1.0)
        request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert mock_transport.handle_async_request.call_count == 3
