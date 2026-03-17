"""Tests for services.helpers — retry logic and safe type converters."""

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
