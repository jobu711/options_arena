"""Tests for FredService — FRED API risk-free rate fetching.

Covers: successful fetch, cache hit/miss, fallback on missing API key,
network errors, timeouts, malformed responses, missing-data markers,
percentage-to-decimal conversion, and rate staleness tracking.
"""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from options_arena.models.config import PricingConfig, ServiceConfig
from options_arena.services.cache import TTL_REFERENCE, ServiceCache
from options_arena.services.fred import (
    _CACHE_KEY,
    _FRED_API_URL,
    CachedRate,
    FredService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fred_response(value: str, status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with a FRED-shaped JSON body."""
    import json

    body = json.dumps(
        {
            "observations": [
                {
                    "realtime_start": "2026-02-23",
                    "realtime_end": "2026-02-23",
                    "date": "2026-02-21",
                    "value": value,
                }
            ]
        }
    )
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", _FRED_API_URL),
        content=body.encode(),
        headers={"content-type": "application/json"},
    )


def _make_empty_observations_response() -> httpx.Response:
    """Build a FRED response with no observations."""
    import json

    body = json.dumps({"observations": []})
    return httpx.Response(
        status_code=200,
        request=httpx.Request("GET", _FRED_API_URL),
        content=body.encode(),
        headers={"content-type": "application/json"},
    )


def _make_malformed_response() -> httpx.Response:
    """Build a response missing the 'observations' key entirely."""
    import json

    body = json.dumps({"seriess": [], "count": 0})
    return httpx.Response(
        status_code=200,
        request=httpx.Request("GET", _FRED_API_URL),
        content=body.encode(),
        headers={"content-type": "application/json"},
    )


@pytest.fixture
def service_config_with_key() -> ServiceConfig:
    """ServiceConfig with a FRED API key configured."""
    return ServiceConfig(fred_api_key="test-api-key-123")


@pytest.fixture
def service_config_no_key() -> ServiceConfig:
    """ServiceConfig with no FRED API key (default None)."""
    return ServiceConfig()


@pytest.fixture
def pricing_config() -> PricingConfig:
    """PricingConfig with default risk_free_rate_fallback (0.05)."""
    return PricingConfig()


@pytest.fixture
def cache(service_config_with_key: ServiceConfig) -> ServiceCache:
    """In-memory-only ServiceCache (no SQLite)."""
    return ServiceCache(config=service_config_with_key, db_path=None)


@pytest.fixture
def fred_service(
    service_config_with_key: ServiceConfig,
    pricing_config: PricingConfig,
    cache: ServiceCache,
) -> FredService:
    """FredService with API key configured."""
    return FredService(
        config=service_config_with_key,
        pricing_config=pricing_config,
        cache=cache,
    )


@pytest.fixture
def fred_service_no_key(
    service_config_no_key: ServiceConfig,
    pricing_config: PricingConfig,
    cache: ServiceCache,
) -> FredService:
    """FredService with no API key configured."""
    return FredService(
        config=service_config_no_key,
        pricing_config=pricing_config,
        cache=cache,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFredServiceSuccessfulFetch:
    """Tests for successful FRED API fetches."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_successful_fetch_converts_percentage_to_decimal(
        self, fred_service: FredService
    ) -> None:
        """FRED returns '4.5' -> service returns 0.045."""
        mock_response = _make_fred_response("4.5")
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.045, rel=1e-6)

    @pytest.mark.asyncio
    async def test_zero_rate_converts_correctly(self, fred_service: FredService) -> None:
        """FRED returns '0.0' -> 0.0 (valid, not treated as missing)."""
        mock_response = _make_fred_response("0.0")
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.0, abs=1e-9)

    @pytest.mark.asyncio
    async def test_high_rate_converts_correctly(self, fred_service: FredService) -> None:
        """FRED returns '10.0' -> 0.10."""
        mock_response = _make_fred_response("10.0")
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.10, rel=1e-6)

    @pytest.mark.asyncio
    async def test_fractional_rate_converts_correctly(self, fred_service: FredService) -> None:
        """FRED returns '3.87' -> 0.0387."""
        mock_response = _make_fred_response("3.87")
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.0387, rel=1e-6)


class TestFredServiceFallback:
    """Tests for fallback behavior on various error conditions."""

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_fallback(
        self, fred_service_no_key: FredService
    ) -> None:
        """When fred_api_key is None, return fallback without making HTTP call."""
        # Patch the client to verify no HTTP call is made
        with patch.object(fred_service_no_key._client, "get", new_callable=AsyncMock) as mock_get:
            rate = await fred_service_no_key.fetch_risk_free_rate()

        assert rate == pytest.approx(0.05, rel=1e-6)
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_network_error_returns_fallback(self, fred_service: FredService) -> None:
        """Network error -> fallback, never raises."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.05, rel=1e-6)

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback(self, fred_service: FredService) -> None:
        """Timeout -> fallback, never raises."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ReadTimeout("Read timed out"),
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.05, rel=1e-6)

    @pytest.mark.asyncio
    async def test_malformed_response_returns_fallback(self, fred_service: FredService) -> None:
        """Response missing 'observations' key -> fallback."""
        mock_response = _make_malformed_response()
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.05, rel=1e-6)

    @pytest.mark.asyncio
    async def test_empty_observations_returns_fallback(self, fred_service: FredService) -> None:
        """Empty observations list -> fallback."""
        mock_response = _make_empty_observations_response()
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.05, rel=1e-6)

    @pytest.mark.asyncio
    async def test_missing_data_marker_returns_fallback(self, fred_service: FredService) -> None:
        """FRED returns '.' (missing data marker) -> fallback."""
        mock_response = _make_fred_response(".")
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.05, rel=1e-6)

    @pytest.mark.asyncio
    async def test_http_500_returns_fallback(self, fred_service: FredService) -> None:
        """HTTP 500 server error -> fallback."""
        error_response = httpx.Response(
            status_code=500,
            request=httpx.Request("GET", _FRED_API_URL),
            content=b"Internal Server Error",
        )
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=error_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.05, rel=1e-6)


class TestFredServiceCaching:
    """Tests for cache integration."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value_no_http(
        self,
        fred_service: FredService,
        cache: ServiceCache,
    ) -> None:
        """When cache has a value, return it without making an HTTP call."""
        # Pre-populate cache
        await cache.set(_CACHE_KEY, b"0.042", ttl=TTL_REFERENCE)

        with patch.object(fred_service._client, "get", new_callable=AsyncMock) as mock_get:
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.042, rel=1e-6)
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_stores_fetched_value(
        self,
        fred_service: FredService,
        cache: ServiceCache,
    ) -> None:
        """After a successful fetch, the value is stored in cache."""
        # Verify cache is empty
        assert await cache.get(_CACHE_KEY) is None

        mock_response = _make_fred_response("4.25")
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.0425, rel=1e-6)

        # Verify value was cached (stored as JSON blob with rate + fetched_at)
        cached = await cache.get(_CACHE_KEY)
        assert cached is not None
        import json

        blob = json.loads(cached.decode())
        assert float(blob["rate"]) == pytest.approx(0.0425, rel=1e-6)
        assert "fetched_at" in blob


class TestFredServiceClose:
    """Tests for resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, fred_service: FredService) -> None:
        """close() delegates to httpx client.aclose()."""
        with patch.object(fred_service._client, "aclose", new_callable=AsyncMock) as mock_aclose:
            await fred_service.close()

        mock_aclose.assert_called_once()


class TestFredServiceStaleness:
    """Tests for FRED rate staleness tracking (AUDIT-018)."""

    @pytest.mark.asyncio
    async def test_stale_rate_triggers_refresh(
        self,
        fred_service: FredService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A cached rate older than 48 hours emits warning and attempts refresh."""
        stale_time = datetime.now(UTC) - timedelta(hours=72)
        fred_service._cached_rate = CachedRate(rate=0.042, fetched_at=stale_time)

        # Mock FRED to return a fresh rate
        mock_response = _make_fred_response("4.0")
        with (
            caplog.at_level(logging.WARNING, logger="options_arena.services.fred"),
            patch.object(
                fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
            ),
        ):
            rate = await fred_service.fetch_risk_free_rate()

        # Staleness warning should have been logged
        assert any(
            "FRED risk-free rate is" in record.message and "hours old" in record.message
            for record in caplog.records
        )
        # Fresh rate from FRED (not stale cached value)
        assert rate == pytest.approx(0.04, rel=1e-6)

    @pytest.mark.asyncio
    async def test_fresh_rate_no_warning(
        self,
        fred_service: FredService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A cached rate younger than 48 hours does NOT emit a staleness warning."""
        recent_time = datetime.now(UTC) - timedelta(hours=12)
        fred_service._cached_rate = CachedRate(rate=0.042, fetched_at=recent_time)

        with caplog.at_level(logging.WARNING, logger="options_arena.services.fred"):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.042, rel=1e-6)
        staleness_warnings = [
            r for r in caplog.records if "hours old" in r.message and r.levelno == logging.WARNING
        ]
        assert len(staleness_warnings) == 0

    @pytest.mark.asyncio
    async def test_fresh_fetch_resets_timestamp(
        self,
        fred_service: FredService,
    ) -> None:
        """After a successful FRED fetch, fetched_at is recent (within last 5 seconds)."""
        mock_response = _make_fred_response("4.0")
        with patch.object(
            fred_service._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.04, rel=1e-6)
        assert fred_service._cached_rate is not None
        age = datetime.now(UTC) - fred_service._cached_rate.fetched_at
        assert age < timedelta(seconds=5)

    @pytest.mark.asyncio
    async def test_rate_under_48h_no_warning(
        self,
        fred_service: FredService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A rate under 48 hours old is returned without staleness warning."""
        # Use 47h to avoid timing flakiness at exact boundary
        boundary_time = datetime.now(UTC) - timedelta(hours=47)
        fred_service._cached_rate = CachedRate(rate=0.042, fetched_at=boundary_time)

        with caplog.at_level(logging.WARNING, logger="options_arena.services.fred"):
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.042, rel=1e-6)
        staleness_warnings = [
            r for r in caplog.records if "hours old" in r.message and r.levelno == logging.WARNING
        ]
        assert len(staleness_warnings) == 0

    @pytest.mark.asyncio
    async def test_two_tier_cache_hit_populates_cached_rate(
        self,
        fred_service: FredService,
        cache: ServiceCache,
    ) -> None:
        """A two-tier cache hit creates a CachedRate with a recent timestamp."""
        assert fred_service._cached_rate is None
        await cache.set(_CACHE_KEY, b"0.038", ttl=TTL_REFERENCE)

        with patch.object(fred_service._client, "get", new_callable=AsyncMock) as mock_get:
            rate = await fred_service.fetch_risk_free_rate()

        assert rate == pytest.approx(0.038, rel=1e-6)
        mock_get.assert_not_called()
        assert fred_service._cached_rate is not None
        assert fred_service._cached_rate.rate == pytest.approx(0.038, rel=1e-6)
        age = datetime.now(UTC) - fred_service._cached_rate.fetched_at
        assert age < timedelta(seconds=5)
