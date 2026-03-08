"""Tests for services.helpers — retry logic and safe type converters."""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import options_arena.services.helpers as helpers_module
from options_arena.services.helpers import (
    clear_stale_yf_cookies,
    fetch_with_limiter_retry,
    fetch_with_retry,
    safe_decimal,
    safe_float,
    safe_int,
)
from options_arena.services.rate_limiter import RateLimiter
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
        with (
            pytest.raises(DataSourceUnavailableError),
            patch("options_arena.services.helpers.random.random", return_value=1.0),
        ):
            await fetch_with_retry(factory, max_retries=3, base_delay=0.05, max_delay=1.0)
        elapsed = loop.time() - start
        # With jitter=1.0: delays are 0.05 (attempt 0→1) + 0.10 (attempt 1→2) = 0.15s
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
# fetch_with_limiter_retry
# ---------------------------------------------------------------------------


class TestFetchWithLimiterRetry:
    """Tests for the rate-limiter-aware retry wrapper."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        limiter = RateLimiter(rate=100.0, max_concurrent=10)
        fn = AsyncMock(return_value=42)
        result = await fetch_with_limiter_retry(fn, limiter=limiter, max_attempts=3)
        assert result == 42
        fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retryable_error_retried(self) -> None:
        limiter = RateLimiter(rate=100.0, max_concurrent=10)
        fn = AsyncMock(side_effect=[DataSourceUnavailableError("timeout"), 99])
        result = await fetch_with_limiter_retry(
            fn, limiter=limiter, max_attempts=3, base_delay=0.01
        )
        assert result == 99
        assert fn.await_count == 2

    @pytest.mark.asyncio
    async def test_permanent_error_not_retried(self) -> None:
        """Non-retryable errors (e.g. TickerNotFoundError) propagate immediately."""
        limiter = RateLimiter(rate=100.0, max_concurrent=10)
        fn = AsyncMock(side_effect=TickerNotFoundError("INVALID"))
        with pytest.raises(TickerNotFoundError, match="INVALID"):
            await fetch_with_limiter_retry(fn, limiter=limiter, max_attempts=3, base_delay=0.01)
        fn.assert_awaited_once()  # No retries

    @pytest.mark.asyncio
    async def test_exhaustion_raises_last_exception(self) -> None:
        limiter = RateLimiter(rate=100.0, max_concurrent=10)
        fn = AsyncMock(side_effect=DataSourceUnavailableError("gone"))
        with pytest.raises(DataSourceUnavailableError, match="gone"):
            await fetch_with_limiter_retry(fn, limiter=limiter, max_attempts=3, base_delay=0.01)
        assert fn.await_count == 3

    @pytest.mark.asyncio
    async def test_custom_retryable_types(self) -> None:
        """Custom retryable tuple only retries specified types."""
        limiter = RateLimiter(rate=100.0, max_concurrent=10)
        fn = AsyncMock(side_effect=[ValueError("bad"), 42])
        result = await fetch_with_limiter_retry(
            fn,
            limiter=limiter,
            max_attempts=3,
            base_delay=0.01,
            retryable=(ValueError,),
        )
        assert result == 42
        assert fn.await_count == 2


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


# ---------------------------------------------------------------------------
# clear_stale_yf_cookies
# ---------------------------------------------------------------------------


def _create_cookie_db(db_path: Path) -> None:
    """Create a minimal yfinance-compatible cookie DB at *db_path*."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE _cookieschema ("
        "  id INTEGER PRIMARY KEY,"
        "  fetch_date DATETIME,"
        "  cookie_bytes BLOB"
        ")"
    )
    conn.commit()
    conn.close()


def _insert_cookie(db_path: Path, fetch_date: datetime) -> None:
    """Insert a cookie row with the given fetch_date."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO _cookieschema (fetch_date, cookie_bytes) VALUES (?, ?)",
        (fetch_date, b"dummy-cookie"),
    )
    conn.commit()
    conn.close()


def _count_cookies(db_path: Path) -> int:
    """Return the number of rows in the cookie table."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT COUNT(*) FROM _cookieschema")
    count: int = cursor.fetchone()[0]
    conn.close()
    return count


class TestClearStaleYfCookies:
    """Tests for proactive yfinance cookie cleanup."""

    @pytest.fixture(autouse=True)
    def _reset_guard(self) -> None:
        """Reset the module-level once-per-process guard before each test."""
        helpers_module._yf_cookies_checked = False

    def test_deletes_stale_cookies(self, tmp_path: Path) -> None:
        """Cookies older than max_age_hours are deleted."""
        db_path = tmp_path / "py-yfinance" / "cookies.db"
        _create_cookie_db(db_path)
        _insert_cookie(db_path, datetime.now() - timedelta(hours=24))

        with patch("platformdirs.user_cache_dir", return_value=str(tmp_path)):
            deleted = clear_stale_yf_cookies(max_age_hours=4.0)

        assert deleted == 1
        assert _count_cookies(db_path) == 0

    def test_preserves_fresh_cookies(self, tmp_path: Path) -> None:
        """Cookies newer than max_age_hours survive cleanup."""
        db_path = tmp_path / "py-yfinance" / "cookies.db"
        _create_cookie_db(db_path)
        _insert_cookie(db_path, datetime.now() - timedelta(hours=1))

        with patch("platformdirs.user_cache_dir", return_value=str(tmp_path)):
            deleted = clear_stale_yf_cookies(max_age_hours=4.0)

        assert deleted == 0
        assert _count_cookies(db_path) == 1

    def test_missing_db_returns_zero(self, tmp_path: Path) -> None:
        """No-op when the cookie DB doesn't exist."""
        with patch("platformdirs.user_cache_dir", return_value=str(tmp_path)):
            assert clear_stale_yf_cookies() == 0

    def test_guard_prevents_second_run(self, tmp_path: Path) -> None:
        """The module-level guard makes the second call a no-op."""
        db_path = tmp_path / "py-yfinance" / "cookies.db"
        _create_cookie_db(db_path)
        _insert_cookie(db_path, datetime.now() - timedelta(hours=24))

        with patch("platformdirs.user_cache_dir", return_value=str(tmp_path)):
            first = clear_stale_yf_cookies(max_age_hours=4.0)
            # Insert another stale cookie
            _insert_cookie(db_path, datetime.now() - timedelta(hours=24))
            second = clear_stale_yf_cookies(max_age_hours=4.0)

        assert first == 1
        assert second == 0  # guard prevented second run
        assert _count_cookies(db_path) == 1  # second cookie still there

    def test_locked_db_returns_zero(self, tmp_path: Path) -> None:
        """Graceful failure when the DB is locked by another connection."""
        db_path = tmp_path / "py-yfinance" / "cookies.db"
        _create_cookie_db(db_path)
        _insert_cookie(db_path, datetime.now() - timedelta(hours=24))

        # Hold an exclusive lock on the DB
        blocker = sqlite3.connect(str(db_path))
        blocker.execute("BEGIN EXCLUSIVE")

        try:
            with patch("platformdirs.user_cache_dir", return_value=str(tmp_path)):
                result = clear_stale_yf_cookies(max_age_hours=4.0)
            assert result == 0
        finally:
            blocker.rollback()
            blocker.close()
