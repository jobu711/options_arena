"""Token-bucket + semaphore dual-layer rate limiter.

Limits both request *rate* (tokens per second) and *concurrency*
(max simultaneous in-flight requests). Designed for wrapping
external API calls in the services layer.
"""

import asyncio
import time
from typing import Self


class RateLimiter:
    """Dual-layer rate limiter: token bucket for throughput, semaphore for concurrency.

    Usage::

        limiter = RateLimiter(rate=2.0, max_concurrent=5)

        async with limiter:
            await do_external_call()

    Args:
        rate: Maximum sustained requests per second (token refill rate).
        max_concurrent: Maximum number of concurrent in-flight requests.
    """

    def __init__(self, rate: float = 2.0, max_concurrent: int = 5) -> None:
        self._rate = rate
        self._max_tokens = rate  # burst capacity equals rate (1 second burst)
        self._tokens = rate  # start full
        self._last_refill = time.monotonic()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def acquire(self) -> None:
        """Acquire a rate-limit slot: wait for both a token and a semaphore permit."""
        await self._semaphore.acquire()
        await self._wait_for_token()

    def release(self) -> None:
        """Release the semaphore permit. Synchronous — do NOT await."""
        self._semaphore.release()

    async def __aenter__(self) -> Self:
        """Enter the async context manager (acquires rate-limit slot)."""
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Exit the async context manager (releases semaphore)."""
        self.release()

    async def _wait_for_token(self) -> None:
        """Block until a token is available in the bucket."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._max_tokens,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Sleep until the next token is expected to be available
            wait_time = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait_time)
