"""Tests for ServiceCache — two-tier caching with market-hours-aware TTL."""

import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from options_arena.models.config import ServiceConfig
from options_arena.services.cache import (
    TTL_CHAIN_AFTER,
    TTL_CHAIN_MARKET,
    TTL_FAILURE,
    TTL_FUNDAMENTALS,
    TTL_OHLCV_AFTER,
    TTL_OHLCV_MARKET,
    TTL_QUOTE_AFTER,
    TTL_QUOTE_MARKET,
    TTL_REFERENCE,
    ServiceCache,
    is_market_hours,
)


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig for cache tests."""
    return ServiceConfig()


@pytest.fixture
async def memory_cache(config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache (no SQLite) for fast unit tests."""
    return ServiceCache(config, db_path=None, max_size=5)


@pytest.fixture
async def sqlite_cache(config: ServiceConfig, tmp_path: Path) -> ServiceCache:
    """Cache with SQLite persistence for persistence tests."""
    db_path = tmp_path / "test_cache.db"
    cache = ServiceCache(config, db_path=db_path, max_size=100)
    await cache.init_db()
    return cache


# ---------------------------------------------------------------------------
# set/get round-trip
# ---------------------------------------------------------------------------


async def test_set_get_roundtrip(memory_cache: ServiceCache) -> None:
    """Store bytes and retrieve the same bytes."""
    payload = b'{"ticker": "AAPL", "price": 185.50}'
    await memory_cache.set("yf:ohlcv:AAPL:1y", payload, ttl=60)

    result = await memory_cache.get("yf:ohlcv:AAPL:1y")
    assert result == payload


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


async def test_ttl_expiry_returns_none(memory_cache: ServiceCache) -> None:
    """After TTL elapses, get() returns None."""
    await memory_cache.set("yf:quote:AAPL:latest", b"old_data", ttl=10)

    # Advance monotonic clock past expiry
    base = time.monotonic()
    with patch("options_arena.services.cache.time") as mock_time:
        mock_time.monotonic.return_value = base + 11.0
        result = await memory_cache.get("yf:quote:AAPL:latest")

    assert result is None


# ---------------------------------------------------------------------------
# Permanent storage (TTL=0 or None)
# ---------------------------------------------------------------------------


async def test_permanent_storage_never_expires(memory_cache: ServiceCache) -> None:
    """TTL=0 entries never expire, even far in the future."""
    await memory_cache.set("yf:ohlcv:AAPL:1y", b"historical", ttl=0)

    # Simulate far future
    base = time.monotonic()
    with patch("options_arena.services.cache.time") as mock_time:
        mock_time.monotonic.return_value = base + 999_999.0
        result = await memory_cache.get("yf:ohlcv:AAPL:1y")

    assert result == b"historical"


async def test_none_ttl_is_permanent(memory_cache: ServiceCache) -> None:
    """TTL=None is treated as permanent (same as TTL=0)."""
    await memory_cache.set("yf:ohlcv:SPY:1y", b"permanent_data", ttl=None)

    base = time.monotonic()
    with patch("options_arena.services.cache.time") as mock_time:
        mock_time.monotonic.return_value = base + 999_999.0
        result = await memory_cache.get("yf:ohlcv:SPY:1y")

    assert result == b"permanent_data"


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


async def test_lru_evicts_oldest_entry(config: ServiceConfig) -> None:
    """When max_size is exceeded, the least-recently-accessed entry is evicted."""
    cache = ServiceCache(config, db_path=None, max_size=3)

    mono_counter = [100.0]

    def advancing_monotonic() -> float:
        mono_counter[0] += 1.0
        return mono_counter[0]

    with patch("options_arena.services.cache.time") as mock_time:
        mock_time.monotonic = advancing_monotonic
        # Fill cache to capacity
        await cache.set("key:a:X:1", b"a", ttl=60)  # oldest
        await cache.set("key:b:X:2", b"b", ttl=60)
        await cache.set("key:c:X:3", b"c", ttl=60)

        # Access 'a' to make it recent, then add a 4th entry
        await cache.get("key:a:X:1")  # refreshes 'a'
        await cache.set("key:d:X:4", b"d", ttl=60)  # triggers eviction

        # 'b' should be evicted (oldest access), 'a' should survive
        result_b = await cache.get("key:b:X:2")
        result_a = await cache.get("key:a:X:1")

    assert result_b is None
    assert result_a == b"a"


# ---------------------------------------------------------------------------
# Market hours TTL selection
# ---------------------------------------------------------------------------


async def test_ttl_for_ohlcv_market_hours(memory_cache: ServiceCache) -> None:
    """During market hours, OHLCV TTL uses the shorter 30-min value."""
    with patch("options_arena.services.cache.is_market_hours", return_value=True):
        assert memory_cache.ttl_for("ohlcv") == TTL_OHLCV_MARKET


async def test_ttl_for_ohlcv_after_hours(memory_cache: ServiceCache) -> None:
    """After hours, OHLCV TTL uses the longer 6-hour value."""
    with patch("options_arena.services.cache.is_market_hours", return_value=False):
        assert memory_cache.ttl_for("ohlcv") == TTL_OHLCV_AFTER


async def test_ttl_for_chain_market_hours(memory_cache: ServiceCache) -> None:
    """During market hours, chain TTL uses the shorter market-hours value."""
    with patch("options_arena.services.cache.is_market_hours", return_value=True):
        assert memory_cache.ttl_for("chain") == TTL_CHAIN_MARKET


async def test_ttl_for_chain_after_hours(memory_cache: ServiceCache) -> None:
    """After hours, chain TTL uses the longer after-hours value."""
    with patch("options_arena.services.cache.is_market_hours", return_value=False):
        assert memory_cache.ttl_for("chain") == TTL_CHAIN_AFTER


async def test_ttl_for_all_data_types(memory_cache: ServiceCache) -> None:
    """Verify correct TTL for each known data type during market hours."""
    with patch("options_arena.services.cache.is_market_hours", return_value=True):
        assert memory_cache.ttl_for("ohlcv") == TTL_OHLCV_MARKET
        assert memory_cache.ttl_for("chain") == TTL_CHAIN_MARKET
        assert memory_cache.ttl_for("quote") == TTL_QUOTE_MARKET
        assert memory_cache.ttl_for("fundamentals") == TTL_FUNDAMENTALS
        assert memory_cache.ttl_for("reference") == TTL_REFERENCE
        assert memory_cache.ttl_for("failure") == TTL_FAILURE


async def test_ttl_for_unknown_type_uses_after_hours(config: ServiceConfig) -> None:
    """Unknown data type falls back to config after-hours TTL."""
    cache = ServiceCache(config, db_path=None)
    assert cache.ttl_for("unknown_type") == config.cache_ttl_after_hours


# ---------------------------------------------------------------------------
# is_market_hours()
# ---------------------------------------------------------------------------


def test_is_market_hours_during_trading() -> None:
    """Wednesday at 10:30 AM ET is within market hours."""
    # 2026-02-25 is a Wednesday
    mock_dt = datetime(2026, 2, 25, 10, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    mock_utc = mock_dt.astimezone(UTC)
    with patch("options_arena.services.cache.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_utc
        assert is_market_hours() is True


def test_is_market_hours_before_open() -> None:
    """Wednesday at 8:00 AM ET is before market open."""
    mock_dt = datetime(2026, 2, 25, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    mock_utc = mock_dt.astimezone(UTC)
    with patch("options_arena.services.cache.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_utc
        assert is_market_hours() is False


def test_is_market_hours_after_close() -> None:
    """Wednesday at 4:30 PM ET is after market close."""
    mock_dt = datetime(2026, 2, 25, 16, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    mock_utc = mock_dt.astimezone(UTC)
    with patch("options_arena.services.cache.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_utc
        assert is_market_hours() is False


def test_is_market_hours_weekend() -> None:
    """Saturday is always outside market hours."""
    # 2026-02-28 is a Saturday
    mock_dt = datetime(2026, 2, 28, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    mock_utc = mock_dt.astimezone(UTC)
    with patch("options_arena.services.cache.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_utc
        assert is_market_hours() is False


def test_is_market_hours_at_exact_open() -> None:
    """At exactly 9:30 AM ET, the market is open."""
    mock_dt = datetime(2026, 2, 25, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    mock_utc = mock_dt.astimezone(UTC)
    with patch("options_arena.services.cache.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_utc
        assert is_market_hours() is True


def test_is_market_hours_at_exact_close() -> None:
    """At exactly 4:00 PM ET, the market is closed (half-open interval)."""
    mock_dt = datetime(2026, 2, 25, 16, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    mock_utc = mock_dt.astimezone(UTC)
    with patch("options_arena.services.cache.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_utc
        assert is_market_hours() is False


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


async def test_sqlite_persistence_across_close(config: ServiceConfig, tmp_path: Path) -> None:
    """Data persists in SQLite across cache close and reopen."""
    db_path = tmp_path / "persist_test.db"

    # Create cache, store data, close
    cache1 = ServiceCache(config, db_path=db_path, max_size=100)
    await cache1.init_db()
    await cache1.set("yf:fundamentals:AAPL:info", b"ticker_info_json", ttl=0)
    await cache1.close()

    # Reopen and verify
    cache2 = ServiceCache(config, db_path=db_path, max_size=100)
    await cache2.init_db()
    result = await cache2.get("yf:fundamentals:AAPL:info")
    await cache2.close()

    assert result == b"ticker_info_json"


async def test_memory_only_types_not_persisted(config: ServiceConfig, tmp_path: Path) -> None:
    """Quote and chain data types stay in-memory only, not written to SQLite."""
    db_path = tmp_path / "memonly_test.db"
    cache = ServiceCache(config, db_path=db_path, max_size=100)
    await cache.init_db()

    await cache.set("yf:quote:AAPL:latest", b"quote_data", ttl=60)
    await cache.set("yf:chain:AAPL:2026-04-18", b"chain_data", ttl=300)

    # Check SQLite directly — these should NOT be there
    assert cache._db is not None
    async with cache._db.execute("SELECT COUNT(*) FROM service_cache") as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 0

    # But they should be in memory
    assert await cache.get("yf:quote:AAPL:latest") == b"quote_data"
    assert await cache.get("yf:chain:AAPL:2026-04-18") == b"chain_data"

    await cache.close()


# ---------------------------------------------------------------------------
# Invalidate
# ---------------------------------------------------------------------------


async def test_invalidate_removes_from_both_tiers(sqlite_cache: ServiceCache) -> None:
    """Invalidate removes the key from memory and SQLite."""
    await sqlite_cache.set("yf:fundamentals:MSFT:info", b"msft_data", ttl=0)

    # Verify it exists
    assert await sqlite_cache.get("yf:fundamentals:MSFT:info") == b"msft_data"

    # Invalidate and verify gone
    await sqlite_cache.invalidate("yf:fundamentals:MSFT:info")
    assert await sqlite_cache.get("yf:fundamentals:MSFT:info") is None

    await sqlite_cache.close()


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


async def test_clear_removes_all(sqlite_cache: ServiceCache) -> None:
    """Clear empties both in-memory and SQLite tiers."""
    await sqlite_cache.set("yf:fundamentals:AAPL:info", b"a", ttl=0)
    await sqlite_cache.set("yf:fundamentals:MSFT:info", b"b", ttl=0)
    await sqlite_cache.set("yf:quote:GOOG:latest", b"c", ttl=60)

    await sqlite_cache.clear()

    assert await sqlite_cache.get("yf:fundamentals:AAPL:info") is None
    assert await sqlite_cache.get("yf:fundamentals:MSFT:info") is None
    assert await sqlite_cache.get("yf:quote:GOOG:latest") is None

    await sqlite_cache.close()


# ---------------------------------------------------------------------------
# Periodic sweep
# ---------------------------------------------------------------------------


async def test_periodic_sweep_cleans_expired(config: ServiceConfig) -> None:
    """After _SWEEP_INTERVAL get() calls, expired entries are cleaned up."""
    cache = ServiceCache(config, db_path=None, max_size=1000)

    # Insert an entry that will expire
    now = time.monotonic()
    cache._memory["yf:quote:OLD:x"] = (b"stale", now - 1.0)  # already expired
    cache._access_order["yf:quote:OLD:x"] = now - 1.0

    # Perform 100 get() calls on a non-existent key to trigger sweep
    for _ in range(100):
        await cache.get("nonexistent:key:X:Y")

    # The expired entry should have been swept
    assert "yf:quote:OLD:x" not in cache._memory


# ---------------------------------------------------------------------------
# Empty get
# ---------------------------------------------------------------------------


async def test_get_nonexistent_returns_none(memory_cache: ServiceCache) -> None:
    """Getting a key that was never set returns None."""
    assert await memory_cache.get("yf:ohlcv:DOESNOTEXIST:1y") is None


# ---------------------------------------------------------------------------
# TTL constants verification
# ---------------------------------------------------------------------------


def test_ttl_constants_values() -> None:
    """Verify named TTL constants have the expected values in seconds."""
    assert TTL_OHLCV_MARKET == 30 * 60
    assert TTL_OHLCV_AFTER == 6 * 60 * 60
    assert TTL_CHAIN_MARKET == 300
    assert TTL_CHAIN_AFTER == 3600
    assert TTL_QUOTE_MARKET == 60
    assert TTL_QUOTE_AFTER == 300
    assert TTL_FUNDAMENTALS == 86400
    assert TTL_REFERENCE == 86400
    assert TTL_FAILURE == 86400


# ---------------------------------------------------------------------------
# TTL validation
# ---------------------------------------------------------------------------


async def test_cache_set_rejects_negative_ttl(memory_cache: ServiceCache) -> None:
    """Passing ttl=-1 raises ValueError with a descriptive message."""
    with pytest.raises(ValueError, match=r"ttl must be >= 0, got -1"):
        await memory_cache.set("yf:ohlcv:AAPL:1y", b"data", ttl=-1)


async def test_cache_set_accepts_zero_ttl(memory_cache: ServiceCache) -> None:
    """ttl=0 is valid (permanent storage) and does not raise."""
    await memory_cache.set("yf:ohlcv:AAPL:1y", b"permanent", ttl=0)
    result = await memory_cache.get("yf:ohlcv:AAPL:1y")
    assert result == b"permanent"


async def test_cache_set_accepts_none_ttl(memory_cache: ServiceCache) -> None:
    """ttl=None is valid (permanent storage) and does not raise."""
    await memory_cache.set("yf:ohlcv:SPY:1y", b"also_permanent", ttl=None)
    result = await memory_cache.get("yf:ohlcv:SPY:1y")
    assert result == b"also_permanent"


async def test_cache_set_accepts_positive_ttl(memory_cache: ServiceCache) -> None:
    """ttl=300 (positive) is valid and stores the value normally."""
    await memory_cache.set("yf:reference:FRED:rate", b"rate_data", ttl=300)
    result = await memory_cache.get("yf:reference:FRED:rate")
    assert result == b"rate_data"
