"""ServiceBase mixin — shared infrastructure for all service classes.

Provides cache-first fetching, retried fetching with rate limiting, and async
yfinance wrapping. Services opt into the helpers they need by calling the
protected methods. No abstract methods — this is a mixin, not an interface.

Generic on ``ConfigT`` so each service can declare its own config type
(``ServiceConfig``, ``OpenBBConfig``, ``IntelligenceConfig``, etc.).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from options_arena.services.cache import ServiceCache
from options_arena.services.helpers import fetch_with_limiter_retry
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataFetchError, DataSourceUnavailableError


class ServiceBase[ConfigT]:
    """Mixin providing shared service infrastructure.

    Stores ``config``, ``cache``, ``limiter``, and ``log`` on construction.
    Subclasses call the protected ``_cached_fetch``, ``_retried_fetch``, and
    ``_yf_call`` helpers as needed — none are abstract or required.

    Type Parameters:
        ConfigT: The configuration model type (e.g., ``ServiceConfig``).

    Args:
        config: Service configuration instance.
        cache: Two-tier service cache for de-duplication.
        limiter: Optional rate limiter. ``None`` disables rate-limited retries.
    """

    def __init__(
        self,
        config: ConfigT,
        cache: ServiceCache,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._config = config
        self._cache = cache
        self._limiter = limiter
        self._log = logging.getLogger(type(self).__module__)

    async def close(self) -> None:
        """Release resources. Default is a no-op; override in subclasses."""

    # ------------------------------------------------------------------
    # Cache-first fetch
    # ------------------------------------------------------------------

    async def _cached_fetch[T: BaseModel](
        self,
        key: str,
        model_type: type[T],
        factory: Callable[[], Awaitable[T]],
        ttl: int,
        *,
        deserializer: Callable[[bytes], T] | None = None,
    ) -> T:
        """Fetch with cache-first strategy.

        On cache hit, deserializes bytes back into ``model_type``. On miss,
        invokes *factory*, serializes the result via ``model_dump_json()``, and
        stores it in the cache with the given *ttl*.

        Args:
            key: Cache key (format ``{source}:{type}:{ticker}:{params}``).
            model_type: Pydantic model class for deserialization.
            factory: Zero-arg async callable that produces the model on cache miss.
            ttl: Time-to-live in seconds for the cached entry.
            deserializer: Optional custom ``bytes -> T`` callable. When ``None``,
                the default ``model_type.model_validate_json(cached)`` is used.

        Returns:
            The model instance, either from cache or freshly fetched.
        """
        cached = await self._cache.get(key)
        if cached is not None:
            self._log.debug("Cache hit: %s", key)
            if deserializer is not None:
                return deserializer(cached)
            return model_type.model_validate_json(cached)

        result = await factory()

        serialized = result.model_dump_json().encode("utf-8")
        await self._cache.set(key, serialized, ttl=ttl)

        return result

    # ------------------------------------------------------------------
    # Retried fetch with rate limiting
    # ------------------------------------------------------------------

    async def _retried_fetch[T](
        self,
        fn: Callable[..., Awaitable[T]],
        *args: object,
        max_attempts: int = 3,
    ) -> T:
        """Retry *fn* with rate limiting via :func:`fetch_with_limiter_retry`.

        Automatically passes ``self._limiter``. Raises ``RuntimeError`` if no
        limiter was provided at construction time.

        For functions that require keyword arguments, use a lambda or
        ``functools.partial`` to bind them before passing to this method::

            await self._retried_fetch(
                lambda: self._yf_call(ticker_obj.history, period="1y", timeout=15.0),
                max_attempts=3,
            )

        Args:
            fn: Async callable to invoke on each attempt.
            *args: Positional arguments forwarded to *fn*.
            max_attempts: Maximum number of attempts before raising.

        Returns:
            The result of ``fn(*args)``.

        Raises:
            RuntimeError: If ``self._limiter`` is ``None``.
        """
        if self._limiter is None:
            raise RuntimeError(f"{type(self).__name__}._retried_fetch requires a RateLimiter")
        return await fetch_with_limiter_retry(
            fn,
            *args,
            limiter=self._limiter,
            max_attempts=max_attempts,
        )

    # ------------------------------------------------------------------
    # yfinance async wrapper
    # ------------------------------------------------------------------

    async def _yf_call[T](
        self,
        fn: Callable[..., T],
        *args: object,
        timeout: float,
        **kwargs: object,
    ) -> T:
        """Wrap a synchronous yfinance call with ``to_thread`` + ``wait_for``.

        Maps all exceptions to :class:`DataSourceUnavailableError` **except**
        :class:`DataFetchError` subclasses which are re-raised as-is to avoid
        double-wrapping domain exceptions.

        Args:
            fn: Synchronous callable (yfinance method).
            *args: Positional arguments forwarded to *fn*.
            timeout: Timeout in seconds (must be explicit — no default).
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            The result of ``fn(*args, **kwargs)`` executed in a thread.

        Raises:
            DataSourceUnavailableError: On timeout or non-domain exceptions.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise DataSourceUnavailableError(f"yfinance: timeout after {timeout}s") from exc
        except DataFetchError:
            # Re-raise domain exceptions (TickerNotFoundError, etc.) as-is
            raise
        except Exception as exc:
            raise DataSourceUnavailableError(f"yfinance: {exc}") from exc
