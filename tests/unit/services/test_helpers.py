"""Tests for services.helpers — retry logic and safe type converters."""

import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock

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
