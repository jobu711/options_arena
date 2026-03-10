"""FRED service for fetching the risk-free rate.

Fetches the 10-year Treasury yield (DGS10) from the FRED API as a proxy for
the risk-free rate. Converts the percentage value to a decimal fraction
(4.5 -> 0.045). Gracefully falls back to ``PricingConfig.risk_free_rate_fallback``
on ANY error -- this service never raises.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import httpx

from options_arena.models.config import PricingConfig, ServiceConfig
from options_arena.services.base import ServiceBase
from options_arena.services.cache import TTL_REFERENCE, ServiceCache

logger = logging.getLogger(__name__)

# FRED API constants
_FRED_API_URL: str = "https://api.stlouisfed.org/fred/series/observations"
_FRED_SERIES_ID: str = "DGS10"
_FRED_MISSING_VALUE: str = "."
_CACHE_KEY: str = "fred:rate:DGS10"
_PERCENTAGE_DIVISOR: float = 100.0
_STALENESS_THRESHOLD: timedelta = timedelta(hours=48)


class CachedRate(NamedTuple):
    """A cached risk-free rate with its fetch timestamp."""

    rate: float
    fetched_at: datetime


class FredService(ServiceBase[ServiceConfig]):
    """Fetches the 10-year Treasury yield from FRED as a risk-free rate proxy.

    Never raises. Falls back to ``PricingConfig.risk_free_rate_fallback`` on
    any error condition (missing API key, network failure, malformed response,
    FRED missing-data marker, etc.).

    Args:
        config: Service configuration with FRED timeout and API key.
        pricing_config: Pricing configuration with ``risk_free_rate_fallback``.
        cache: Two-tier service cache for 24-hour caching of successful responses.
    """

    def __init__(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
    ) -> None:
        super().__init__(config, cache, limiter=None)
        self._pricing_config = pricing_config
        self._cached_rate: CachedRate | None = None
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                10.0,
                connect=5.0,
                read=config.fred_timeout,
            ),
            limits=httpx.Limits(
                max_connections=5,
                max_keepalive_connections=2,
            ),
        )

    async def fetch_risk_free_rate(self) -> float:
        """Fetch 10-year Treasury yield as a decimal fraction (0.045 = 4.5%).

        NEVER raises. Falls back to ``PricingConfig.risk_free_rate_fallback``
        on ANY error. Caches successful responses for 24 hours via
        ``ServiceCache``.

        Returns:
            Risk-free rate as a decimal fraction. Always returns a valid float.
        """
        fallback = self._pricing_config.risk_free_rate_fallback

        try:
            return await self._fetch_with_cache(fallback)
        except Exception:
            # Defensive outer catch -- should never reach here because
            # _fetch_with_cache already catches broadly, but belt-and-suspenders.
            logger.warning(
                "Unexpected error in fetch_risk_free_rate, returning fallback %.4f",
                fallback,
            )
            return fallback

    async def close(self) -> None:
        """Close the httpx client."""
        await self._client.aclose()
        await super().close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_with_cache(self, fallback: float) -> float:
        """Check cache, then fetch from FRED if miss.

        Returns:
            Risk-free rate as decimal fraction, or fallback on any error.
        """
        # --- In-memory staleness-aware cache check ---
        if self._cached_rate is not None:
            age = datetime.now(UTC) - self._cached_rate.fetched_at
            if age > _STALENESS_THRESHOLD:
                logger.warning(
                    "FRED risk-free rate is %.0f hours old; attempting refresh",
                    age.total_seconds() / 3600,
                )
                # Fall through to attempt refresh from two-tier cache / FRED API
            else:
                logger.debug("FRED rate in-memory cache hit: %.4f", self._cached_rate.rate)
                return self._cached_rate.rate

        # --- Two-tier cache check ---
        try:
            cached = await self._cache.get(_CACHE_KEY)
            if cached is not None:
                decoded = cached.decode()
                # Support both JSON (with timestamp) and plain float (legacy)
                if decoded.startswith("{"):
                    import json as _json

                    blob = _json.loads(decoded)
                    rate = float(blob["rate"])
                    fetched_at = datetime.fromisoformat(blob["fetched_at"])
                else:
                    rate = float(decoded)
                    fetched_at = datetime.now(UTC)  # legacy: no timestamp available
                self._cached_rate = CachedRate(rate=rate, fetched_at=fetched_at)
                logger.debug("FRED rate cache hit: %.4f", rate)
                return rate
        except Exception:
            logger.warning("Error reading FRED rate from cache, proceeding to fetch")

        # --- API key check ---
        if self._config.fred_api_key is None:
            logger.warning(
                "FRED API key not configured, returning fallback rate %.4f",
                fallback,
            )
            return fallback

        api_key = self._config.fred_api_key.get_secret_value()

        # --- Fetch from FRED ---
        try:
            fetched_rate = await self._fetch_from_fred(api_key)
        except Exception as exc:
            logger.warning(
                "FRED fetch failed (%s), returning fallback rate %.4f",
                exc,
                fallback,
            )
            return fallback

        if fetched_rate is None:
            logger.warning(
                "FRED returned no usable data, returning fallback rate %.4f",
                fallback,
            )
            return fallback

        # --- Cache successful result ---
        now = datetime.now(UTC)
        self._cached_rate = CachedRate(rate=fetched_rate, fetched_at=now)
        try:
            import json as _json

            cache_blob = _json.dumps({"rate": fetched_rate, "fetched_at": now.isoformat()})
            await self._cache.set(
                _CACHE_KEY,
                cache_blob.encode(),
                ttl=TTL_REFERENCE,
            )
            logger.debug("Cached FRED rate %.4f with TTL %ds", fetched_rate, TTL_REFERENCE)
        except Exception:
            logger.warning("Failed to cache FRED rate, continuing with fetched value")

        return fetched_rate

    async def _fetch_from_fred(self, api_key: str) -> float | None:
        """Make the actual FRED API request and parse the response.

        Args:
            api_key: FRED API key for authentication.

        Returns:
            Rate as decimal fraction, or ``None`` if data is unavailable/unparseable.

        Raises:
            httpx.HTTPError: On network/timeout errors (caught by caller).
        """
        params = {
            "series_id": _FRED_SERIES_ID,
            "sort_order": "desc",
            "limit": "1",
            "file_type": "json",
            "api_key": api_key,
        }

        response = await self._client.get(_FRED_API_URL, params=params)
        response.raise_for_status()

        data = response.json()
        observations: list[dict[str, str]] = data.get("observations", [])

        if not observations:
            logger.warning("FRED response contained no observations")
            return None

        value_str: str = observations[0].get("value", _FRED_MISSING_VALUE)

        # FRED uses "." as a missing-data marker
        if value_str == _FRED_MISSING_VALUE:
            logger.warning("FRED returned missing-data marker '.' for DGS10")
            return None

        # Parse percentage string and convert to decimal fraction
        percentage = float(value_str)
        rate = percentage / _PERCENTAGE_DIVISOR

        logger.info(
            "Fetched FRED DGS10 rate: %s%% -> %.4f decimal",
            value_str,
            rate,
        )
        return rate
