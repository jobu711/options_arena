"""Tests for services.helpers — retry logic and safe type converters."""

import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from options_arena.services.helpers import (
    fetch_with_retry,
    safe_decimal,
    safe_float,
    safe_int,
)
from options_arena.utils.exceptions import (
    DataSourceUnavailableError,
    TickerNotFoundError,
)

# ---------------------------------------------------------------------------
# fetch_with_retry
# ---------------------------------------------------------------------------


class TestFetchWithRetry:
    """Tests for the exponential-backoff retry wrapper."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        factory = AsyncMock(return_value=42)
        result = await fetch_with_retry(factory, max_retries=3)
        assert result == 42
        factory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_on_second_attempt_after_retryable_error(self) -> None:
        factory = AsyncMock(side_effect=[DataSourceUnavailableError("yfinance: timeout"), 99])
        result = await fetch_with_retry(factory, max_retries=3, base_delay=0.01)
        assert result == 99
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_exhaustion_raises_last_exception(self) -> None:
        exc = DataSourceUnavailableError("yfinance: gone")
        factory = AsyncMock(side_effect=exc)
        with pytest.raises(DataSourceUnavailableError, match="gone"):
            await fetch_with_retry(factory, max_retries=3, base_delay=0.01)
        assert factory.await_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self) -> None:
        factory = AsyncMock(side_effect=TickerNotFoundError("BAD"))
        with pytest.raises(TickerNotFoundError, match="BAD"):
            await fetch_with_retry(factory, max_retries=5, base_delay=0.01)
        factory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_backoff_timing_approximate(self) -> None:
        """Verify exponential backoff delays approximately double each time."""
        factory = AsyncMock(
            side_effect=[
                DataSourceUnavailableError("s: e1"),
                DataSourceUnavailableError("s: e2"),
                DataSourceUnavailableError("s: e3"),
            ]
        )
        loop = asyncio.get_event_loop()
        start = loop.time()
        with pytest.raises(DataSourceUnavailableError):
            await fetch_with_retry(factory, max_retries=3, base_delay=0.05, max_delay=1.0)
        elapsed = loop.time() - start
        # Expected delays: 0.05 (attempt 0→1) + 0.10 (attempt 1→2) = 0.15s
        assert elapsed >= 0.10  # at least most of the expected delay
        assert elapsed < 1.0  # upper sanity bound

    @pytest.mark.asyncio
    async def test_logs_warning_on_each_retry(self, caplog: pytest.LogCaptureFixture) -> None:
        factory = AsyncMock(
            side_effect=[
                DataSourceUnavailableError("src: err"),
                DataSourceUnavailableError("src: err"),
                42,
            ]
        )
        with caplog.at_level(logging.WARNING, logger="options_arena.services.helpers"):
            result = await fetch_with_retry(factory, max_retries=3, base_delay=0.01)
        assert result == 42
        retry_messages = [r for r in caplog.records if "Retry" in r.message]
        assert len(retry_messages) == 2


# ---------------------------------------------------------------------------
# safe_decimal
# ---------------------------------------------------------------------------


class TestSafeDecimal:
    """Tests for safe_decimal converter."""

    def test_valid_string(self) -> None:
        assert safe_decimal("1.05") == Decimal("1.05")

    def test_valid_int(self) -> None:
        assert safe_decimal(5) == Decimal(5)

    def test_valid_float(self) -> None:
        result = safe_decimal(1.5)
        assert result is not None
        assert result == Decimal("1.5")

    def test_invalid_string_returns_none(self) -> None:
        assert safe_decimal("abc") is None

    def test_none_returns_none(self) -> None:
        assert safe_decimal(None) is None

    def test_nan_float_returns_none(self) -> None:
        assert safe_decimal(float("nan")) is None

    def test_inf_float_returns_none(self) -> None:
        assert safe_decimal(float("inf")) is None


# ---------------------------------------------------------------------------
# safe_int
# ---------------------------------------------------------------------------


class TestSafeInt:
    """Tests for safe_int converter."""

    def test_valid_float(self) -> None:
        assert safe_int(5.7) == 5

    def test_valid_string(self) -> None:
        assert safe_int("10") == 10

    def test_invalid_string_returns_none(self) -> None:
        assert safe_int("abc") is None

    def test_nan_returns_none(self) -> None:
        assert safe_int(float("nan")) is None

    def test_none_returns_none(self) -> None:
        assert safe_int(None) is None

    def test_inf_returns_none(self) -> None:
        assert safe_int(float("inf")) is None


# ---------------------------------------------------------------------------
# safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:
    """Tests for safe_float converter."""

    def test_valid_value(self) -> None:
        assert safe_float(1.5) == pytest.approx(1.5)

    def test_nan_returns_none(self) -> None:
        assert safe_float(float("nan")) is None

    def test_inf_returns_none(self) -> None:
        assert safe_float(float("inf")) is None

    def test_neg_inf_returns_none(self) -> None:
        assert safe_float(float("-inf")) is None

    def test_invalid_string_returns_none(self) -> None:
        assert safe_float("abc") is None

    def test_valid_string(self) -> None:
        assert safe_float("3.14") == pytest.approx(3.14)

    def test_none_returns_none(self) -> None:
        assert safe_float(None) is None


# ---------------------------------------------------------------------------
# fetch_with_retry jitter
# ---------------------------------------------------------------------------


class TestFetchWithRetryJitter:
    """Tests for jitter on the exponential backoff delay."""

    @pytest.mark.asyncio
    async def test_jitter_within_bounds(self) -> None:
        """Verify delay is between 50% and 100% of base delay."""
        recorded_delays: list[float] = []
        original_sleep = asyncio.sleep

        async def capture_sleep(delay: float) -> None:
            recorded_delays.append(delay)
            await original_sleep(0)  # don't actually wait

        factory = AsyncMock(
            side_effect=[
                DataSourceUnavailableError("src: e1"),
                DataSourceUnavailableError("src: e2"),
                DataSourceUnavailableError("src: e3"),
            ]
        )
        with (
            patch("asyncio.sleep", side_effect=capture_sleep),
            pytest.raises(DataSourceUnavailableError),
        ):
            await fetch_with_retry(factory, max_retries=3, base_delay=1.0, max_delay=16.0)

        # Two retries expected (attempt 0->1 and 1->2)
        assert len(recorded_delays) == 2
        # Attempt 0: base_delay=1.0 * 2^0 = 1.0, jitter range [0.5, 1.0]
        assert 0.5 <= recorded_delays[0] <= 1.0
        # Attempt 1: base_delay=1.0 * 2^1 = 2.0, jitter range [1.0, 2.0]
        assert 1.0 <= recorded_delays[1] <= 2.0

    @pytest.mark.asyncio
    async def test_jitter_randomness(self) -> None:
        """Verify multiple calls produce different delays (mock random)."""
        recorded_delays_run1: list[float] = []
        recorded_delays_run2: list[float] = []
        original_sleep = asyncio.sleep

        async def capture_sleep_1(delay: float) -> None:
            recorded_delays_run1.append(delay)
            await original_sleep(0)

        async def capture_sleep_2(delay: float) -> None:
            recorded_delays_run2.append(delay)
            await original_sleep(0)

        # Run 1: random.random() returns 0.0 -> jitter = 0.5
        factory1 = AsyncMock(
            side_effect=[
                DataSourceUnavailableError("src: e1"),
                DataSourceUnavailableError("src: e2"),
            ]
        )
        with (
            patch("options_arena.services.helpers.random.random", return_value=0.0),
            patch("asyncio.sleep", side_effect=capture_sleep_1),
            pytest.raises(DataSourceUnavailableError),
        ):
            await fetch_with_retry(factory1, max_retries=2, base_delay=4.0, max_delay=16.0)

        # Run 2: random.random() returns 1.0 -> jitter = 1.0
        factory2 = AsyncMock(
            side_effect=[
                DataSourceUnavailableError("src: e1"),
                DataSourceUnavailableError("src: e2"),
            ]
        )
        with (
            patch("options_arena.services.helpers.random.random", return_value=1.0),
            patch("asyncio.sleep", side_effect=capture_sleep_2),
            pytest.raises(DataSourceUnavailableError),
        ):
            await fetch_with_retry(factory2, max_retries=2, base_delay=4.0, max_delay=16.0)

        # Run 1: delay = 4.0 * 0.5 = 2.0
        assert recorded_delays_run1[0] == pytest.approx(2.0)
        # Run 2: delay = 4.0 * 1.0 = 4.0
        assert recorded_delays_run2[0] == pytest.approx(4.0)
        # They must differ
        assert recorded_delays_run1[0] != pytest.approx(recorded_delays_run2[0])
