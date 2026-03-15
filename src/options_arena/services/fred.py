"""FRED service for fetching the risk-free rate and macro-economic context.

Fetches the 10-year Treasury yield (DGS10) from the FRED API as a proxy for
the risk-free rate. Converts the percentage value to a decimal fraction
(4.5 -> 0.045). Gracefully falls back to ``PricingConfig.risk_free_rate_fallback``
on ANY error -- this service never raises.

Also provides ``fetch_macro_context()`` which batch-fetches 8 FRED series
(DGS10, DGS2, T10Y2Y, FEDFUNDS, VIXCLS, CPIAUCSL, INDPRO, UNRATE) with
per-series TTL caching and returns a ``MacroContext`` model. Follows the
same never-raises pattern.
"""

import asyncio
import json as _json
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import httpx

from options_arena.models.config import PricingConfig, ServiceConfig
from options_arena.models.enums import FredTransform
from options_arena.models.macro import FredSeriesConfig, MacroContext
from options_arena.services.base import ServiceBase
from options_arena.services.cache import TTL_REFERENCE, ServiceCache

# FRED API constants
_FRED_API_URL: str = "https://api.stlouisfed.org/fred/series/observations"
_FRED_SERIES_ID: str = "DGS10"
_FRED_MISSING_VALUE: str = "."
_CACHE_KEY: str = "fred:rate:DGS10"
_PERCENTAGE_DIVISOR: float = 100.0
_STALENESS_THRESHOLD: timedelta = timedelta(hours=48)

# ---------------------------------------------------------------------------
# Macro series registry — 8 FRED series for MacroContext
# ---------------------------------------------------------------------------
# Daily series: 24h TTL (released every trading day)
# Monthly series: 168h (7 day) TTL (released monthly)
_MACRO_SERIES: list[FredSeriesConfig] = [
    FredSeriesConfig(
        series_id="DGS10",
        display_name="10-Year Treasury",
        ttl_hours=24,
        transform=FredTransform.PCT_TO_DECIMAL,
    ),
    FredSeriesConfig(
        series_id="DGS2",
        display_name="2-Year Treasury",
        ttl_hours=24,
        transform=FredTransform.PCT_TO_DECIMAL,
    ),
    FredSeriesConfig(
        series_id="T10Y2Y",
        display_name="10Y-2Y Yield Spread",
        ttl_hours=24,
        transform=FredTransform.PCT_TO_DECIMAL,
    ),
    FredSeriesConfig(
        series_id="FEDFUNDS",
        display_name="Fed Funds Rate",
        ttl_hours=24,
        transform=FredTransform.PCT_TO_DECIMAL,
    ),
    FredSeriesConfig(
        series_id="VIXCLS",
        display_name="VIX",
        ttl_hours=24,
        transform=FredTransform.PASSTHROUGH,
    ),
    FredSeriesConfig(
        series_id="CPIAUCSL",
        display_name="CPI YoY",
        ttl_hours=168,
        transform=FredTransform.YOY_PCT_CHANGE,
    ),
    FredSeriesConfig(
        series_id="INDPRO",
        display_name="Industrial Production YoY",
        ttl_hours=168,
        transform=FredTransform.YOY_PCT_CHANGE,
    ),
    FredSeriesConfig(
        series_id="UNRATE",
        display_name="Unemployment Rate",
        ttl_hours=168,
        transform=FredTransform.PCT_TO_DECIMAL,
    ),
]

# Map FRED series_id -> MacroContext field name
_SERIES_TO_FIELD: dict[str, str] = {
    "DGS10": "treasury_10y",
    "DGS2": "treasury_2y",
    "T10Y2Y": "yield_spread_10y2y",
    "FEDFUNDS": "fed_funds_rate",
    "VIXCLS": "vix",
    "CPIAUCSL": "cpi_yoy",
    "INDPRO": "industrial_production_yoy",
    "UNRATE": "unemployment_rate",
}


class CachedRate(NamedTuple):
    """A cached risk-free rate with its fetch timestamp."""

    rate: float
    fetched_at: datetime


class FredService(ServiceBase[ServiceConfig]):
    """Fetches the 10-year Treasury yield from FRED as a risk-free rate proxy.

    Never raises. Falls back to ``PricingConfig.risk_free_rate_fallback`` on
    any error condition (missing API key, network failure, malformed response,
    FRED missing-data marker, etc.).

    Also provides ``fetch_macro_context()`` for batch macro data. See
    ``_MACRO_SERIES`` for the full list of series and their TTLs.

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
            self._log.warning(
                "Unexpected error in fetch_risk_free_rate, returning fallback %.4f",
                fallback,
            )
            return fallback

    async def fetch_macro_context(self) -> MacroContext:
        """Batch-fetch 8 FRED series and return a ``MacroContext`` snapshot.

        NEVER raises. Returns a partial ``MacroContext`` on partial failures,
        or ``MacroContext.fallback()`` (all-None) on total failure. Each series
        is fetched concurrently with per-series TTL caching.

        Returns:
            MacroContext with populated fields for successfully fetched series.
        """
        try:
            return await self._fetch_macro_context_inner()
        except Exception:
            self._log.warning(
                "Unexpected error in fetch_macro_context, returning all-None fallback"
            )
            return MacroContext.fallback()

    async def close(self) -> None:
        """Close the httpx client."""
        await self._client.aclose()
        await super().close()

    # ------------------------------------------------------------------
    # Private helpers — risk-free rate
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
                self._log.warning(
                    "FRED risk-free rate is %.0f hours old; attempting refresh",
                    age.total_seconds() / 3600,
                )
                # Fall through to attempt refresh from two-tier cache / FRED API
            else:
                self._log.debug("FRED rate in-memory cache hit: %.4f", self._cached_rate.rate)
                return self._cached_rate.rate

        # --- Two-tier cache check ---
        try:
            cached = await self._cache.get(_CACHE_KEY)
            if cached is not None:
                decoded = cached.decode()
                # Support both JSON (with timestamp) and plain float (legacy)
                if decoded.startswith("{"):
                    blob = _json.loads(decoded)
                    rate = float(blob["rate"])
                    fetched_at = datetime.fromisoformat(blob["fetched_at"])
                else:
                    rate = float(decoded)
                    fetched_at = datetime.now(UTC)  # legacy: no timestamp available
                self._cached_rate = CachedRate(rate=rate, fetched_at=fetched_at)
                self._log.debug("FRED rate cache hit: %.4f", rate)
                return rate
        except Exception:
            self._log.warning("Error reading FRED rate from cache, proceeding to fetch")

        # --- API key check ---
        if self._config.fred_api_key is None:
            self._log.warning(
                "FRED API key not configured, returning fallback rate %.4f",
                fallback,
            )
            return fallback

        api_key = self._config.fred_api_key.get_secret_value()

        # --- Fetch from FRED ---
        try:
            fetched_rate = await self._fetch_series_value(api_key, _FRED_SERIES_ID)
        except Exception as exc:
            # Log class name only — str(exc) can include the full request URL
            # with the FRED API key as a query parameter.
            safe_err = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else type(exc).__name__
            )
            self._log.warning(
                "FRED fetch failed (%s), returning fallback rate %.4f",
                safe_err,
                fallback,
            )
            return fallback

        if fetched_rate is None:
            self._log.warning(
                "FRED returned no usable data, returning fallback rate %.4f",
                fallback,
            )
            return fallback

        # Convert percentage to decimal fraction for risk-free rate
        rate = fetched_rate / _PERCENTAGE_DIVISOR

        # --- Cache successful result ---
        now = datetime.now(UTC)
        self._cached_rate = CachedRate(rate=rate, fetched_at=now)
        try:
            cache_blob = _json.dumps({"rate": rate, "fetched_at": now.isoformat()})
            await self._cache.set(
                _CACHE_KEY,
                cache_blob.encode(),
                ttl=TTL_REFERENCE,
            )
            self._log.debug("Cached FRED rate %.4f with TTL %ds", rate, TTL_REFERENCE)
        except Exception:
            self._log.warning("Failed to cache FRED rate, continuing with fetched value")

        return rate

    # ------------------------------------------------------------------
    # Private helpers — generalized FRED fetching
    # ------------------------------------------------------------------

    async def _fetch_series_value(
        self,
        api_key: str,
        series_id: str,
        *,
        units: str | None = None,
    ) -> float | None:
        """Make the actual FRED API request for a single series and parse the response.

        Args:
            api_key: FRED API key for authentication.
            series_id: FRED series identifier (e.g. ``"DGS10"``).
            units: Optional FRED ``units`` parameter for server-side transformation
                (e.g. ``"pc1"`` for percent change from year ago).

        Returns:
            Numeric value from FRED (after any server-side transform), or ``None``
            if data is unavailable/unparseable.

        Raises:
            httpx.HTTPError: On network/timeout errors (caught by caller).
        """
        params: dict[str, str] = {
            "series_id": series_id,
            "sort_order": "desc",
            "limit": "1",
            "file_type": "json",
            "api_key": api_key,
        }
        if units is not None:
            params["units"] = units

        response = await self._client.get(_FRED_API_URL, params=params)
        response.raise_for_status()

        data = response.json()
        observations: list[dict[str, str]] = data.get("observations", [])

        if not observations:
            self._log.warning("FRED response contained no observations for %s", series_id)
            return None

        value_str: str = observations[0].get("value", _FRED_MISSING_VALUE)

        # FRED uses "." as a missing-data marker
        if value_str == _FRED_MISSING_VALUE:
            self._log.warning("FRED returned missing-data marker '.' for %s", series_id)
            return None

        raw_value = float(value_str)

        self._log.info("Fetched FRED %s: %s", series_id, value_str)
        return raw_value

    def _apply_transform(self, raw_value: float, transform: FredTransform) -> float:
        """Apply the configured transform to a raw FRED value.

        Args:
            raw_value: Raw numeric value from FRED API.
            transform: ``FredTransform`` enum member specifying the transformation.

        Returns:
            Transformed value suitable for ``MacroContext``.
        """
        match transform:
            case FredTransform.PCT_TO_DECIMAL:
                return raw_value / _PERCENTAGE_DIVISOR
            case FredTransform.YOY_PCT_CHANGE | FredTransform.PASSTHROUGH:
                # YOY_PCT_CHANGE: FRED already computed the YoY % via units=pc1
                # PASSTHROUGH: raw value used as-is
                return raw_value

    # ------------------------------------------------------------------
    # Private helpers — macro context
    # ------------------------------------------------------------------

    async def _fetch_macro_context_inner(self) -> MacroContext:
        """Internal implementation of ``fetch_macro_context()``.

        Fetches all 8 series concurrently with per-series caching. Returns a
        partial ``MacroContext`` — any series that fails gets ``None``.
        """
        if self._config.fred_api_key is None:
            self._log.warning("FRED API key not configured, returning all-None MacroContext")
            return MacroContext.fallback()

        api_key = self._config.fred_api_key.get_secret_value()

        # Create per-series fetch tasks
        tasks = [self._fetch_macro_series(api_key, series_cfg) for series_cfg in _MACRO_SERIES]

        # Batch fetch with error isolation
        results: list[tuple[str, float | None] | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        # Build MacroContext kwargs from results
        kwargs: dict[str, float | None] = {}
        for series_cfg, result in zip(_MACRO_SERIES, results, strict=True):
            field_name = _SERIES_TO_FIELD[series_cfg.series_id]
            if isinstance(result, BaseException):
                self._log.warning(
                    "FRED macro series %s failed: %s",
                    series_cfg.series_id,
                    type(result).__name__,
                )
                kwargs[field_name] = None
            else:
                _series_id, value = result
                kwargs[field_name] = value

        macro_ctx = MacroContext(**kwargs)
        ratio = macro_ctx.completeness_ratio()
        self._log.info(
            "MacroContext populated: %.0f%% complete (%d/8 series)",
            ratio * 100,
            int(ratio * 8),
        )
        return macro_ctx

    async def _fetch_macro_series(
        self,
        api_key: str,
        series_cfg: FredSeriesConfig,
    ) -> tuple[str, float | None]:
        """Fetch a single macro series with per-series caching.

        Returns:
            Tuple of (series_id, transformed_value_or_None).
        """
        cache_key = f"fred:macro:{series_cfg.series_id}"
        ttl_seconds = series_cfg.ttl_hours * 3600

        # --- Cache check ---
        try:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                blob = _json.loads(cached.decode())
                value: float | None = blob.get("value")
                self._log.debug("FRED macro cache hit: %s = %s", series_cfg.series_id, value)
                return (series_cfg.series_id, value)
        except Exception:
            self._log.warning(
                "Error reading FRED macro cache for %s, proceeding to fetch",
                series_cfg.series_id,
            )

        # --- Fetch ---
        # For YoY series (CPI, Industrial Production), FRED computes the
        # percent change from year ago server-side via units=pc1.  Without
        # this, FRED returns raw index levels (~317 for CPI, ~103 for INDPRO).
        fred_units: str | None = None
        if series_cfg.transform == FredTransform.YOY_PCT_CHANGE:
            fred_units = "pc1"

        try:
            raw_value = await self._fetch_series_value(
                api_key, series_cfg.series_id, units=fred_units
            )
        except Exception as exc:
            safe_err = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else type(exc).__name__
            )
            self._log.warning(
                "FRED macro fetch failed for %s (%s)",
                series_cfg.series_id,
                safe_err,
            )
            return (series_cfg.series_id, None)

        if raw_value is None:
            return (series_cfg.series_id, None)

        # Apply transform
        transformed = self._apply_transform(raw_value, series_cfg.transform)

        # --- Cache result ---
        try:
            cache_blob = _json.dumps({"value": transformed})
            await self._cache.set(cache_key, cache_blob.encode(), ttl=ttl_seconds)
            self._log.debug(
                "Cached FRED macro %s = %.4f with TTL %dh",
                series_cfg.series_id,
                transformed,
                series_cfg.ttl_hours,
            )
        except Exception:
            self._log.warning(
                "Failed to cache FRED macro %s, continuing with fetched value",
                series_cfg.series_id,
            )

        return (series_cfg.series_id, transformed)
