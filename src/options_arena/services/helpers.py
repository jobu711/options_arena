"""Internal helpers for the services layer.

Retry logic with exponential backoff and safe type conversion utilities.
NOT exported in ``__init__.py`` — internal use only.
"""

import asyncio
import logging
import math
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation

from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError

logger = logging.getLogger(__name__)


async def fetch_with_retry[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    retryable: tuple[type[Exception], ...] = (DataSourceUnavailableError,),
) -> T:
    """Execute an async factory with exponential backoff on retryable errors.

    Args:
        coro_factory: Zero-arg callable that returns an awaitable. Re-invoked on
            each retry attempt (must NOT be a pre-created coroutine).
        max_retries: Maximum number of retry attempts before raising.
        base_delay: Initial delay in seconds before first retry.
        max_delay: Upper bound on delay between retries.
        retryable: Tuple of exception types that trigger a retry.

    Returns:
        The result of the awaitable produced by ``coro_factory``.

    Raises:
        The last exception encountered after all retries are exhausted,
        or immediately for non-retryable exceptions.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except tuple(retryable) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                jitter = 0.5 + random.random() * 0.5  # noqa: S311
                delay *= jitter
                logger.warning(
                    "Retry %d/%d after %s: %.1fs delay",
                    attempt + 1,
                    max_retries - 1,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
        except Exception:
            raise
    # All retries exhausted — raise the last retryable exception
    assert last_exc is not None  # noqa: S101 — guaranteed by loop logic
    raise last_exc


async def fetch_with_limiter_retry[T](
    fn: Callable[..., Awaitable[T]],
    *args: object,
    limiter: RateLimiter,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    **kwargs: object,
) -> T:
    """Retry with rate limiter — releases semaphore during backoff sleep.

    Unlike :func:`fetch_with_retry` which holds the rate-limit slot for the
    entire retry loop, this function acquires the limiter per-attempt and
    releases it before sleeping between retries. This avoids starving other
    tasks of concurrency slots during backoff waits.

    Args:
        fn: Async callable to invoke on each attempt.
        *args: Positional arguments forwarded to ``fn``.
        limiter: :class:`RateLimiter` instance — acquired per attempt.
        max_attempts: Maximum number of attempts before raising.
        base_delay: Initial delay in seconds before first retry.
        max_delay: Upper bound on delay between retries.
        **kwargs: Keyword arguments forwarded to ``fn``.

    Returns:
        The result of ``fn(*args, **kwargs)``.

    Raises:
        The last exception encountered after all attempts are exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        async with limiter:  # acquire per attempt
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_error = exc
        # Limiter released before sleeping
        if attempt < max_attempts - 1:
            delay = min(base_delay * (2**attempt), max_delay)
            jitter = 0.5 + random.random() * 0.5  # noqa: S311
            delay *= jitter
            logger.warning(
                "Limiter-retry %d/%d after %s: %.1fs delay",
                attempt + 1,
                max_attempts - 1,
                type(last_error).__name__,
                delay,
            )
            await asyncio.sleep(delay)
    assert last_error is not None  # noqa: S101 — guaranteed by loop logic
    raise last_error


def safe_decimal(value: object) -> Decimal | None:
    """Convert *value* to ``Decimal`` safely.

    Returns ``None`` on any conversion failure (including ``None`` input).
    """
    if value is None:
        return None
    try:
        if isinstance(value, float):
            if not math.isfinite(value):
                logger.debug("safe_decimal: non-finite float %r", value)
                return None
            return Decimal(str(value))
        return Decimal(value)  # type: ignore[arg-type]
    except (InvalidOperation, TypeError, ValueError, ArithmeticError) as exc:
        logger.debug("safe_decimal: failed to convert %r — %s", value, exc)
        return None


def safe_int(value: object) -> int | None:
    """Convert *value* to ``int`` safely.

    Returns ``None`` on any conversion failure (including ``None``, NaN, inf).
    """
    if value is None:
        return None
    try:
        as_float = float(value)  # type: ignore[arg-type]
        if not math.isfinite(as_float):
            logger.debug("safe_int: non-finite value %r", value)
            return None
        return int(as_float)
    except (TypeError, ValueError, OverflowError) as exc:
        logger.debug("safe_int: failed to convert %r — %s", value, exc)
        return None


def safe_float(value: object) -> float | None:
    """Convert *value* to ``float`` safely.

    Rejects ``NaN`` and ``+-inf`` via ``math.isfinite()``.
    Returns ``None`` on any conversion failure.
    """
    if value is None:
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
        if not math.isfinite(result):
            logger.debug("safe_float: non-finite result %r from %r", result, value)
            return None
        return result
    except (TypeError, ValueError, OverflowError) as exc:
        logger.debug("safe_float: failed to convert %r — %s", value, exc)
        return None
