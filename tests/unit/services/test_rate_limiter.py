"""Tests for services.rate_limiter — token bucket + semaphore dual-layer."""

import asyncio
import time

import pytest

from options_arena.services.rate_limiter import RateLimiter


class TestTokenBucket:
    """Tests for the token-bucket throughput limiter."""

    @pytest.mark.asyncio
    async def test_tokens_deplete_after_burst(self) -> None:
        """Initial burst capacity should be consumed, then block."""
        limiter = RateLimiter(rate=2.0, max_concurrent=10)
        # Consume all 2 initial tokens rapidly
        start = time.monotonic()
        async with limiter:
            pass
        async with limiter:
            pass
        # Third acquire should block (no tokens left)
        async with limiter:
            pass
        elapsed = time.monotonic() - start
        # Expect ~0.5s wait for third token at rate=2/s
        assert elapsed >= 0.3  # some tolerance for scheduling jitter

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self) -> None:
        """After depletion, tokens should refill at the configured rate."""
        limiter = RateLimiter(rate=10.0, max_concurrent=20)
        # Drain all tokens
        for _ in range(10):
            await limiter.acquire()
            limiter.release()
        # Wait for refill
        await asyncio.sleep(0.2)
        # Should be able to acquire at least 1 token without blocking
        start = time.monotonic()
        await limiter.acquire()
        limiter.release()
        elapsed = time.monotonic() - start
        assert elapsed < 0.15  # should be nearly instant after refill

    @pytest.mark.asyncio
    async def test_single_token_available_immediately(self) -> None:
        """First acquire on a fresh limiter should be near-instant."""
        limiter = RateLimiter(rate=1.0, max_concurrent=5)
        start = time.monotonic()
        async with limiter:
            pass
        elapsed = time.monotonic() - start
        assert elapsed < 0.1


class TestSemaphore:
    """Tests for the concurrent-request semaphore."""

    @pytest.mark.asyncio
    async def test_max_concurrent_limits_parallel_access(self) -> None:
        """Only max_concurrent tasks should run simultaneously."""
        limiter = RateLimiter(rate=100.0, max_concurrent=2)
        active = 0
        max_active = 0

        async def task() -> None:
            nonlocal active, max_active
            async with limiter:
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1

        await asyncio.gather(*(task() for _ in range(6)))
        assert max_active <= 2

    @pytest.mark.asyncio
    async def test_semaphore_release_after_exception(self) -> None:
        """Semaphore should be released even when the body raises."""
        limiter = RateLimiter(rate=100.0, max_concurrent=1)
        with pytest.raises(ValueError, match="boom"):
            async with limiter:
                raise ValueError("boom")
        # Should be able to acquire again (slot was released)
        start = time.monotonic()
        async with limiter:
            pass
        elapsed = time.monotonic() - start
        assert elapsed < 0.1


class TestContextManager:
    """Tests for the async context manager protocol."""

    @pytest.mark.asyncio
    async def test_async_with_works_correctly(self) -> None:
        limiter = RateLimiter(rate=5.0, max_concurrent=3)
        async with limiter as acquired:
            assert acquired is limiter

    @pytest.mark.asyncio
    async def test_release_is_not_coroutine(self) -> None:
        """release() must be synchronous (Semaphore.release is sync)."""
        limiter = RateLimiter(rate=5.0, max_concurrent=3)
        assert not asyncio.iscoroutinefunction(limiter.release)


class TestConcurrency:
    """Tests for concurrent task behavior under rate limiting."""

    @pytest.mark.asyncio
    async def test_multiple_tasks_properly_rate_limited(self) -> None:
        """Multiple tasks should be paced by the token bucket."""
        limiter = RateLimiter(rate=10.0, max_concurrent=10)
        completed: list[float] = []

        async def task() -> None:
            async with limiter:
                completed.append(time.monotonic())

        start = time.monotonic()
        # Launch 15 tasks; bucket starts with 10 tokens, rate=10/s
        await asyncio.gather(*(task() for _ in range(15)))
        elapsed = time.monotonic() - start

        assert len(completed) == 15
        # With 10 initial tokens and rate=10/s, 5 extra tokens need ~0.5s
        # Allow generous tolerance for CI/scheduling jitter
        assert elapsed >= 0.3
        assert elapsed < 3.0  # sanity upper bound

    @pytest.mark.asyncio
    async def test_acquire_release_manual(self) -> None:
        """Manual acquire/release (without context manager) works correctly."""
        limiter = RateLimiter(rate=5.0, max_concurrent=2)
        await limiter.acquire()
        limiter.release()
        # Should not deadlock; acquire again
        await limiter.acquire()
        limiter.release()
