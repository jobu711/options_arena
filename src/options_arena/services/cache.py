"""Two-tier service cache with market-hours-aware TTL.

In-memory LRU for hot data (quotes, chains) and persistent SQLite for cold
data (OHLCV, fundamentals, failures). TTLs adjust based on whether US options
markets are currently open.

Cache key format: ``{source}:{type}:{ticker}:{params}``
Example: ``yf:ohlcv:AAPL:1y``, ``yf:chain:AAPL:2026-04-18``
"""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite

from options_arena.models.config import ServiceConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named TTL constants (seconds) — never use magic numbers
# ---------------------------------------------------------------------------

TTL_OHLCV: int = 6 * 60 * 60  # 6 hrs — daily bars refresh between scan runs
TTL_CHAIN_MARKET: int = 5 * 60  # 5 min during market hours
TTL_CHAIN_AFTER: int = 60 * 60  # 1 hr after hours
TTL_QUOTE_MARKET: int = 1 * 60  # 1 min during market hours
TTL_QUOTE_AFTER: int = 5 * 60  # 5 min after hours
TTL_FUNDAMENTALS: int = 24 * 60 * 60  # 24 hrs
TTL_REFERENCE: int = 24 * 60 * 60  # 24 hrs (FRED rate, universe)
TTL_FAILURE: int = 24 * 60 * 60  # 24 hrs (cached failures)

# Data types that stay in-memory only (short-TTL, high-churn)
_MEMORY_ONLY_TYPES: frozenset[str] = frozenset({"quote", "chain"})

# Eastern timezone for market-hours detection
_ET = ZoneInfo("America/New_York")

# Market hours boundaries (9:30 AM – 4:00 PM ET)
_MARKET_OPEN_HOUR: int = 9
_MARKET_OPEN_MINUTE: int = 30
_MARKET_CLOSE_HOUR: int = 16
_MARKET_CLOSE_MINUTE: int = 0

# Sweep interval: run expired-entry cleanup every N get() calls
_SWEEP_INTERVAL: int = 100

# Default max in-memory entries before LRU eviction
_DEFAULT_MAX_SIZE: int = 1000


def is_market_hours() -> bool:
    """Check if US options markets are currently open (9:30-16:00 ET, Mon-Fri).

    Uses ``zoneinfo.ZoneInfo("America/New_York")`` for correct DST handling.
    Returns ``False`` on weekends and outside regular trading hours.
    """
    now_et = datetime.now(UTC).astimezone(_ET)
    weekday = now_et.weekday()  # 0=Monday .. 6=Sunday
    if weekday > 4:  # Saturday or Sunday
        return False
    current_minutes = now_et.hour * 60 + now_et.minute
    open_minutes = _MARKET_OPEN_HOUR * 60 + _MARKET_OPEN_MINUTE
    close_minutes = _MARKET_CLOSE_HOUR * 60 + _MARKET_CLOSE_MINUTE
    return open_minutes <= current_minutes < close_minutes


class ServiceCache:
    """Two-tier cache: in-memory LRU + persistent SQLite.

    Construction requires a ``ServiceConfig`` instance and an optional
    ``db_path`` for SQLite persistence. Call :meth:`init_db` after
    construction to initialize the SQLite tier.

    **Dual-clock design**: The in-memory tier tracks expiry with
    ``time.monotonic()`` (immune to NTP adjustments and clock skew).
    The SQLite tier uses ``time.time()`` (wall-clock) because monotonic
    timestamps reset to zero on process restart, making them unsuitable
    for persistent storage. When promoting a SQLite entry to memory, the
    remaining wall-clock TTL is converted to a monotonic deadline via
    ``now_mono + max(db_expires_at - time.time(), 0.0)``. This is safe
    because a process restart clears all in-memory state anyway.

    Args:
        config: Service configuration with cache TTL settings.
        db_path: Path to the SQLite database file. If ``None``, SQLite
            tier is disabled (in-memory only mode, useful for tests).
        max_size: Maximum number of entries in the in-memory LRU cache.
    """

    def __init__(
        self,
        config: ServiceConfig,
        db_path: Path | None = None,
        max_size: int = _DEFAULT_MAX_SIZE,
    ) -> None:
        self._config = config
        self._db_path = db_path
        self._max_size = max_size
        self._db: aiosqlite.Connection | None = None

        # In-memory cache: key -> (value_bytes, expiry_monotonic)
        # expiry_monotonic == 0.0 means permanent (never expires)
        self._memory: dict[str, tuple[bytes, float]] = {}

        # LRU tracking: key -> last_access_monotonic
        self._access_order: dict[str, float] = {}

        # Counter for periodic sweep
        self._get_count: int = 0

    async def init_db(self) -> None:
        """Initialize SQLite with WAL mode. Must be called after construction.

        Skips initialization if no ``db_path`` was provided.
        """
        if self._db_path is None:
            return
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS service_cache "
            "(key TEXT PRIMARY KEY, value BLOB, expires_at REAL)"
        )
        await self._db.commit()
        logger.debug("ServiceCache SQLite initialized at %s", self._db_path)

    async def get(self, key: str) -> bytes | None:
        """Retrieve a cached value by key.

        Checks in-memory first, then SQLite. Returns ``None`` if the key is
        missing or expired. Expired entries are lazily deleted on access.
        Triggers a periodic sweep every :data:`_SWEEP_INTERVAL` calls.
        """
        self._get_count += 1
        if self._get_count % _SWEEP_INTERVAL == 0:
            self._sweep_memory()

        # --- In-memory tier ---
        entry = self._memory.get(key)
        if entry is not None:
            value, expires_at = entry
            if expires_at != 0.0 and expires_at < time.monotonic():
                # Expired — remove lazily
                del self._memory[key]
                self._access_order.pop(key, None)
                logger.debug("Cache miss (expired in-memory): %s", key)
            else:
                # Hit — update LRU access time
                self._access_order[key] = time.monotonic()
                return value

        # --- SQLite tier ---
        if self._db is not None:
            async with self._db.execute(
                "SELECT value, expires_at FROM service_cache WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
            if row is not None:
                value_blob: bytes = row[0]
                db_expires_at: float = row[1]
                if db_expires_at != 0.0 and db_expires_at < time.time():
                    # Expired in SQLite — clean up
                    await self._db.execute("DELETE FROM service_cache WHERE key = ?", (key,))
                    await self._db.commit()
                    logger.debug("Cache miss (expired in SQLite): %s", key)
                    return None
                # Promote to in-memory for faster subsequent access
                now_mono = time.monotonic()
                mem_expires = 0.0
                if db_expires_at != 0.0:
                    # Convert wall-clock expiry to monotonic
                    remaining = db_expires_at - time.time()
                    mem_expires = now_mono + max(remaining, 0.0)
                self._memory[key] = (value_blob, mem_expires)
                self._access_order[key] = now_mono
                self._enforce_lru()
                return value_blob

        return None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        """Store a value with an optional TTL.

        Args:
            key: Cache key (format: ``{source}:{type}:{ticker}:{params}``).
            value: Raw bytes to store.
            ttl: Time-to-live in seconds. ``0`` or ``None`` means permanent.
                Short-TTL data types (quote, chain) stay in-memory only.
        """
        now_mono = time.monotonic()

        # Compute monotonic expiry for in-memory tier (0.0 = permanent sentinel)
        mem_expires = 0.0 if ttl is None or ttl == 0 else now_mono + ttl

        # Store in-memory
        self._memory[key] = (value, mem_expires)
        self._access_order[key] = now_mono
        self._enforce_lru()

        # Store in SQLite for persistent data types (not short-TTL)
        data_type = self._extract_data_type(key)
        if self._db is not None and data_type not in _MEMORY_ONLY_TYPES:
            wall_expires = 0.0 if ttl is None or ttl == 0 else time.time() + ttl
            await self._db.execute(
                "INSERT OR REPLACE INTO service_cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, value, wall_expires),
            )
            await self._db.commit()
            logger.debug("Cache set (both tiers): %s, ttl=%s", key, ttl)
        else:
            logger.debug("Cache set (memory-only): %s, ttl=%s", key, ttl)

    async def invalidate(self, key: str) -> None:
        """Remove a key from both tiers."""
        self._memory.pop(key, None)
        self._access_order.pop(key, None)

        if self._db is not None:
            await self._db.execute("DELETE FROM service_cache WHERE key = ?", (key,))
            await self._db.commit()
        logger.debug("Cache invalidated: %s", key)

    async def clear(self) -> None:
        """Clear all cached data from both tiers."""
        self._memory.clear()
        self._access_order.clear()
        self._get_count = 0

        if self._db is not None:
            await self._db.execute("DELETE FROM service_cache")
            await self._db.commit()
        logger.debug("Cache cleared (all tiers)")

    async def close(self) -> None:
        """Close SQLite connection. Safe to call multiple times."""
        if self._db is not None:
            await self._db.close()
            self._db = None
        logger.debug("ServiceCache closed")

    def ttl_for(self, data_type: str) -> int:
        """Get the appropriate TTL for a data type based on current market hours.

        Args:
            data_type: One of ``"ohlcv"``, ``"chain"``, ``"quote"``,
                ``"fundamentals"``, ``"reference"``, ``"failure"``.

        Returns:
            TTL in seconds. ``0`` means permanent.
        """
        market_open = is_market_hours()

        match data_type:
            case "ohlcv":
                return TTL_OHLCV
            case "chain":
                return TTL_CHAIN_MARKET if market_open else TTL_CHAIN_AFTER
            case "quote":
                return TTL_QUOTE_MARKET if market_open else TTL_QUOTE_AFTER
            case "fundamentals":
                return TTL_FUNDAMENTALS
            case "reference":
                return TTL_REFERENCE
            case "failure":
                return TTL_FAILURE
            case _:
                logger.warning("Unknown data type %r, using after-hours TTL", data_type)
                return self._config.cache_ttl_after_hours

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _enforce_lru(self) -> None:
        """Evict oldest-accessed entries when memory cache exceeds max_size."""
        while len(self._memory) > self._max_size:
            # Find the key with the smallest (oldest) access time
            oldest_key = min(self._access_order, key=self._access_order.get)  # type: ignore[arg-type]
            del self._memory[oldest_key]
            del self._access_order[oldest_key]
            logger.debug("LRU eviction: %s", oldest_key)

    def _sweep_memory(self) -> None:
        """Remove all expired entries from the in-memory cache."""
        now = time.monotonic()
        expired_keys = [
            k
            for k, (_, expires_at) in self._memory.items()
            if expires_at != 0.0 and expires_at < now
        ]
        for k in expired_keys:
            del self._memory[k]
            self._access_order.pop(k, None)
        if expired_keys:
            logger.debug("Sweep removed %d expired entries", len(expired_keys))

    @staticmethod
    def _extract_data_type(key: str) -> str:
        """Extract the data type segment from a cache key.

        Key format: ``{source}:{type}:{ticker}:{params}``
        Returns the ``{type}`` segment, or the full key if format is unexpected.
        """
        parts = key.split(":")
        if len(parts) >= 2:  # noqa: PLR2004
            return parts[1]
        return key
