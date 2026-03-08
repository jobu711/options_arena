"""LLM model configuration for PydanticAI debate agents.

Multi-provider dispatcher: Groq (default) and Anthropic (Claude). Provider
selection via ``DebateConfig.provider`` (``LLMProvider`` enum).

API key resolution per provider:
  - Groq: ``config.api_key`` > ``GROQ_API_KEY`` env var
  - Anthropic: ``config.anthropic_api_key`` > ``ANTHROPIC_API_KEY`` env var

Rate-limit resilience: when ``config.rate_limit_retries > 0``, builds an
httpx ``AsyncClient`` with a retry transport that handles 429/502/503/504
responses using exponential backoff + Retry-After header respect.
"""

import logging
import os

import httpx
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.groq import GroqProvider
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from options_arena.models import DebateConfig, LLMProvider

logger = logging.getLogger(__name__)

# HTTP status codes that should trigger a retry
_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


class _RateLimitError(Exception):
    """Raised by the retry transport when a retryable HTTP status is received."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"HTTP {response.status_code}")


class _RetryTransport(httpx.AsyncBaseTransport):
    """Async httpx transport that retries on 429/5xx with exponential backoff.

    Respects the ``Retry-After`` header when present, falling back to
    exponential backoff (1s → 2s → 4s → ...) capped at ``max_wait``.
    """

    def __init__(
        self,
        *,
        wrapped: httpx.AsyncBaseTransport,
        max_attempts: int,
        max_wait: float,
    ) -> None:
        self._wrapped = wrapped
        self._max_attempts = max_attempts
        self._max_wait = max_wait

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Send request with retry logic for rate-limit responses."""
        last_response: httpx.Response | None = None

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=self._max_wait),
            retry=retry_if_exception_type(_RateLimitError),
            reraise=True,
        ):
            with attempt:
                response = await self._wrapped.handle_async_request(request)
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    last_response = response
                    retry_after = response.headers.get("retry-after")
                    if retry_after is not None:
                        logger.warning(
                            "Rate limited (HTTP %d), Retry-After: %ss",
                            response.status_code,
                            retry_after,
                        )
                    else:
                        logger.warning("Retryable HTTP %d, backing off", response.status_code)
                    raise _RateLimitError(response)
                return response

        # Should not reach here, but satisfy type checker
        assert last_response is not None  # noqa: S101
        return last_response


def _build_rate_limit_client(config: DebateConfig) -> httpx.AsyncClient:
    """Build an httpx AsyncClient with retry transport for rate-limit resilience.

    Parameters
    ----------
    config
        Debate configuration with ``rate_limit_retries`` and ``rate_limit_max_wait``.

    Returns
    -------
    httpx.AsyncClient
        Client with retry-capable transport wrapping the default httpx transport.
    """
    base_transport = httpx.AsyncHTTPTransport()
    retry_transport = _RetryTransport(
        wrapped=base_transport,
        max_attempts=config.rate_limit_retries + 1,  # +1 because first attempt counts
        max_wait=config.rate_limit_max_wait,
    )
    return httpx.AsyncClient(transport=retry_transport)


def build_debate_model(config: DebateConfig) -> Model:
    """Build a PydanticAI model for the configured LLM provider.

    Dispatches to the appropriate provider builder based on
    ``config.provider`` (``LLMProvider`` enum). Supported providers:

    - **GROQ** (default): Groq cloud API with optional rate-limit retry transport.
    - **ANTHROPIC**: Anthropic API (Claude models).

    Parameters
    ----------
    config
        Debate configuration with provider selection, model names, and API keys.

    Returns
    -------
    Model
        Configured PydanticAI model (``GroqModel`` or ``AnthropicModel``).

    Raises
    ------
    ValueError
        If no API key is found in config or environment for the selected provider.
    """
    match config.provider:
        case LLMProvider.GROQ:
            return _build_groq_model(config)
        case LLMProvider.ANTHROPIC:
            return _build_anthropic_model(config)


def _build_groq_model(config: DebateConfig) -> GroqModel:
    """Build a PydanticAI GroqModel backed by Groq cloud API.

    API key resolution: ``config.api_key`` > ``GROQ_API_KEY`` env var.
    When ``config.rate_limit_retries > 0``, wraps the HTTP transport with
    automatic 429/5xx retry logic.

    Parameters
    ----------
    config
        Debate configuration with ``model`` and optional ``api_key``.

    Returns
    -------
    GroqModel
        Configured PydanticAI GroqModel.

    Raises
    ------
    ValueError
        If no Groq API key is found in config or environment.
    """
    api_key = _resolve_groq_api_key(config)
    logger.debug("Building GroqModel: model=%s", config.model)

    http_client: httpx.AsyncClient | None = None
    if config.rate_limit_retries > 0:
        http_client = _build_rate_limit_client(config)
        logger.debug(
            "Rate-limit transport: retries=%d, max_wait=%.1fs",
            config.rate_limit_retries,
            config.rate_limit_max_wait,
        )

    provider = GroqProvider(api_key=api_key, http_client=http_client)
    return GroqModel(config.model, provider=provider)


def _build_anthropic_model(config: DebateConfig) -> AnthropicModel:
    """Build a PydanticAI AnthropicModel backed by Anthropic API.

    API key resolution: ``config.anthropic_api_key`` > ``ANTHROPIC_API_KEY``
    env var.

    Parameters
    ----------
    config
        Debate configuration with ``anthropic_model`` and optional
        ``anthropic_api_key``.

    Returns
    -------
    AnthropicModel
        Configured PydanticAI AnthropicModel.

    Raises
    ------
    ValueError
        If no Anthropic API key is found in config or environment.
    """
    api_key = _resolve_anthropic_api_key(config)
    logger.debug("Building AnthropicModel: model=%s", config.anthropic_model)
    provider = AnthropicProvider(api_key=api_key)
    return AnthropicModel(config.anthropic_model, provider=provider)


def _resolve_groq_api_key(config: DebateConfig) -> str:
    """Resolve Groq API key with priority: config > env > ValueError.

    Parameters
    ----------
    config
        Debate configuration with optional ``api_key``.

    Returns
    -------
    str
        Resolved Groq API key.

    Raises
    ------
    ValueError
        If no Groq API key is found.
    """
    if config.api_key is not None:
        return config.api_key.get_secret_value()
    env_key = os.environ.get("GROQ_API_KEY")
    if env_key is not None:
        return env_key
    raise ValueError(
        "Groq API key required. Set ARENA_DEBATE__API_KEY or GROQ_API_KEY env var, "
        "or pass api_key in DebateConfig."
    )


def _resolve_anthropic_api_key(config: DebateConfig) -> str:
    """Resolve Anthropic API key with priority: config > env > ValueError.

    Parameters
    ----------
    config
        Debate configuration with optional ``anthropic_api_key``.

    Returns
    -------
    str
        Resolved Anthropic API key.

    Raises
    ------
    ValueError
        If no Anthropic API key is found.
    """
    if config.anthropic_api_key is not None:
        return config.anthropic_api_key.get_secret_value()
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key is not None:
        return env_key
    raise ValueError(
        "Anthropic API key required. Set ARENA_DEBATE__ANTHROPIC_API_KEY or "
        "ANTHROPIC_API_KEY env var, or pass anthropic_api_key in DebateConfig."
    )


def _resolve_api_key(config: DebateConfig) -> str | None:
    """Resolve Groq API key with priority: config > env > None.

    .. deprecated::
        Use ``_resolve_groq_api_key()`` instead. Kept for backward compatibility.
    """
    if config.api_key is not None:
        return config.api_key.get_secret_value()
    return os.environ.get("GROQ_API_KEY")
