"""Tests for FredService.fetch_macro_context() — batch macro data fetching.

Covers: full success, partial failure, all-fail, caching, no API key,
per-series TTL, transform application, and never-raises contract.
"""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from options_arena.models.config import PricingConfig, ServiceConfig
from options_arena.models.macro import MacroContext
from options_arena.services.cache import ServiceCache
from options_arena.services.fred import (
    _FRED_API_URL,
    _MACRO_SERIES,
    _SERIES_TO_FIELD,
    FredService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fred_response(value: str, status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with a FRED-shaped JSON body."""
    body = json.dumps(
        {
            "observations": [
                {
                    "realtime_start": "2026-03-15",
                    "realtime_end": "2026-03-15",
                    "date": "2026-03-14",
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


def _make_missing_data_response() -> httpx.Response:
    """Build a FRED response with missing-data marker."""
    body = json.dumps(
        {
            "observations": [
                {
                    "realtime_start": "2026-03-15",
                    "realtime_end": "2026-03-15",
                    "date": "2026-03-14",
                    "value": ".",
                }
            ]
        }
    )
    return httpx.Response(
        status_code=200,
        request=httpx.Request("GET", _FRED_API_URL),
        content=body.encode(),
        headers={"content-type": "application/json"},
    )


# Series-specific raw values for a "successful" fetch scenario.
# Map: series_id -> (raw FRED value string, expected transformed value)
_SERIES_VALUES: dict[str, tuple[str, float]] = {
    "DGS10": ("4.50", 0.045),  # pct_to_decimal: 4.50 / 100
    "DGS2": ("4.20", 0.042),  # pct_to_decimal: 4.20 / 100
    "T10Y2Y": ("0.30", 0.003),  # pct_to_decimal: 0.30 / 100
    "FEDFUNDS": ("5.25", 0.0525),  # pct_to_decimal: 5.25 / 100
    "VIXCLS": ("18.50", 18.50),  # passthrough
    "CPIAUCSL": ("3.20", 3.20),  # yoy_pct_change (passthrough)
    "INDPRO": ("1.50", 1.50),  # yoy_pct_change (passthrough)
    "UNRATE": ("3.50", 0.035),  # pct_to_decimal: 3.50 / 100
}


def _mock_get_all_success(url: str, **kwargs: object) -> httpx.Response:
    """Mock httpx client.get() that returns success for all series."""
    params = kwargs.get("params", {})
    series_id = params.get("series_id", "") if isinstance(params, dict) else ""
    if series_id in _SERIES_VALUES:
        raw_str, _ = _SERIES_VALUES[series_id]
        return _make_fred_response(raw_str)
    return _make_fred_response("0.0")


def _mock_get_partial_success(url: str, **kwargs: object) -> httpx.Response:
    """Mock httpx client.get() that succeeds for some series and fails for others."""
    params = kwargs.get("params", {})
    series_id = params.get("series_id", "") if isinstance(params, dict) else ""
    # Succeed for daily series, fail for monthly
    if series_id in ("DGS10", "DGS2", "T10Y2Y", "FEDFUNDS", "VIXCLS"):
        raw_str = _SERIES_VALUES[series_id][0]
        return _make_fred_response(raw_str)
    # Return missing-data marker for monthly series
    return _make_missing_data_response()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service_config_with_key() -> ServiceConfig:
    """ServiceConfig with a FRED API key configured."""
    return ServiceConfig(fred_api_key="test-api-key-123")


@pytest.fixture
def service_config_no_key() -> ServiceConfig:
    """ServiceConfig with no FRED API key."""
    return ServiceConfig()


@pytest.fixture
def pricing_config() -> PricingConfig:
    """PricingConfig with default risk_free_rate_fallback."""
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
    """FredService with no API key."""
    return FredService(
        config=service_config_no_key,
        pricing_config=pricing_config,
        cache=cache,
    )


# ---------------------------------------------------------------------------
# Tests — fetch_macro_context full success
# ---------------------------------------------------------------------------


class TestFetchMacroContextFullSuccess:
    """Tests for fetch_macro_context() when all series succeed."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_all_series_populated(self, fred_service: FredService) -> None:
        """All 8 MacroContext fields are populated on full success."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=_mock_get_all_success,
        ):
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        assert ctx.completeness_ratio() == pytest.approx(1.0, abs=1e-9)

        # Verify each field's transformed value
        assert ctx.treasury_10y == pytest.approx(0.045, rel=1e-6)
        assert ctx.treasury_2y == pytest.approx(0.042, rel=1e-6)
        assert ctx.yield_spread_10y2y == pytest.approx(0.003, rel=1e-6)
        assert ctx.fed_funds_rate == pytest.approx(0.0525, rel=1e-6)
        assert ctx.vix == pytest.approx(18.50, rel=1e-6)
        assert ctx.cpi_yoy == pytest.approx(3.20, rel=1e-6)
        assert ctx.industrial_production_yoy == pytest.approx(1.50, rel=1e-6)
        assert ctx.unemployment_rate == pytest.approx(0.035, rel=1e-6)

    @pytest.mark.asyncio
    async def test_returns_frozen_model(self, fred_service: FredService) -> None:
        """The returned MacroContext is frozen (immutable)."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=_mock_get_all_success,
        ):
            ctx = await fred_service.fetch_macro_context()

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ctx.treasury_10y = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests — partial failure
# ---------------------------------------------------------------------------


class TestFetchMacroContextPartialFailure:
    """Tests for fetch_macro_context() when some series fail."""

    @pytest.mark.asyncio
    async def test_partial_data_returns_partial_context(self, fred_service: FredService) -> None:
        """When some series fail, the successful ones are still populated."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=_mock_get_partial_success,
        ):
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        # Daily series should be populated
        assert ctx.treasury_10y is not None
        assert ctx.treasury_2y is not None
        assert ctx.vix is not None
        # Monthly series should be None (missing-data marker)
        assert ctx.cpi_yoy is None
        assert ctx.industrial_production_yoy is None
        assert ctx.unemployment_rate is None

    @pytest.mark.asyncio
    async def test_partial_completeness_ratio(self, fred_service: FredService) -> None:
        """Completeness ratio reflects partial population."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=_mock_get_partial_success,
        ):
            ctx = await fred_service.fetch_macro_context()

        # 5 daily series should succeed, 3 monthly should fail
        assert ctx.completeness_ratio() == pytest.approx(5 / 8, abs=1e-6)

    @pytest.mark.asyncio
    async def test_network_error_on_some_series(self, fred_service: FredService) -> None:
        """A network error on individual series does not crash the batch."""
        call_count = 0

        async def _mock_get_with_errors(url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            series_id = params.get("series_id", "") if isinstance(params, dict) else ""
            if series_id in ("CPIAUCSL", "INDPRO"):
                raise httpx.ConnectError("Connection refused")
            if series_id in _SERIES_VALUES:
                raw_str = _SERIES_VALUES[series_id][0]
                return _make_fred_response(raw_str)
            return _make_fred_response("0.0")

        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=_mock_get_with_errors,
        ):
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        # Series that had network errors should be None
        assert ctx.cpi_yoy is None
        assert ctx.industrial_production_yoy is None
        # Others should be populated
        assert ctx.treasury_10y is not None
        assert ctx.vix is not None


# ---------------------------------------------------------------------------
# Tests — total failure
# ---------------------------------------------------------------------------


class TestFetchMacroContextTotalFailure:
    """Tests for fetch_macro_context() when all series fail."""

    @pytest.mark.asyncio
    async def test_all_fail_returns_fallback(self, fred_service: FredService) -> None:
        """When all series fail, returns all-None MacroContext."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        assert ctx.completeness_ratio() == pytest.approx(0.0, abs=1e-9)
        assert ctx.treasury_10y is None
        assert ctx.vix is None

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_fallback(self, fred_service: FredService) -> None:
        """Even an unexpected exception returns fallback, never raises."""
        with patch.object(
            fred_service,
            "_fetch_macro_context_inner",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected"),
        ):
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        assert ctx.completeness_ratio() == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Tests — no API key
# ---------------------------------------------------------------------------


class TestFetchMacroContextNoApiKey:
    """Tests for fetch_macro_context() when FRED API key is not configured."""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_fallback(self, fred_service_no_key: FredService) -> None:
        """When FRED API key is None, returns all-None MacroContext."""
        with patch.object(fred_service_no_key._client, "get", new_callable=AsyncMock) as mock_get:
            ctx = await fred_service_no_key.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        assert ctx.completeness_ratio() == pytest.approx(0.0, abs=1e-9)
        # Should NOT have made any HTTP calls
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — caching
# ---------------------------------------------------------------------------


class TestFetchMacroContextCaching:
    """Tests for per-series caching in fetch_macro_context()."""

    @pytest.mark.asyncio
    async def test_cache_stores_fetched_values(
        self,
        fred_service: FredService,
        cache: ServiceCache,
    ) -> None:
        """After a successful fetch, values are cached per-series."""
        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=_mock_get_all_success,
        ):
            await fred_service.fetch_macro_context()

        # Check that DGS10 was cached
        cached = await cache.get("fred:macro:DGS10")
        assert cached is not None
        blob = json.loads(cached.decode())
        assert blob["value"] == pytest.approx(0.045, rel=1e-6)

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(
        self,
        fred_service: FredService,
        cache: ServiceCache,
    ) -> None:
        """When all series are cached, no HTTP calls are made."""
        # Pre-populate cache for all series
        for series_cfg in _MACRO_SERIES:
            _, expected_value = _SERIES_VALUES[series_cfg.series_id]
            cache_key = f"fred:macro:{series_cfg.series_id}"
            blob = json.dumps({"value": expected_value})
            ttl = series_cfg.ttl_hours * 3600
            await cache.set(cache_key, blob.encode(), ttl=ttl)

        with patch.object(fred_service._client, "get", new_callable=AsyncMock) as mock_get:
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        assert ctx.completeness_ratio() == pytest.approx(1.0, abs=1e-9)
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_cache_fetches_remaining(
        self,
        fred_service: FredService,
        cache: ServiceCache,
    ) -> None:
        """When some series are cached, only uncached series are fetched."""
        # Cache only DGS10 and VIX
        for sid in ("DGS10", "VIXCLS"):
            _, expected_value = _SERIES_VALUES[sid]
            cache_key = f"fred:macro:{sid}"
            blob = json.dumps({"value": expected_value})
            await cache.set(cache_key, blob.encode(), ttl=86400)

        call_series: list[str] = []

        async def _mock_get_tracking(url: str, **kwargs: object) -> httpx.Response:
            params = kwargs.get("params", {})
            series_id = params.get("series_id", "") if isinstance(params, dict) else ""
            call_series.append(series_id)
            if series_id in _SERIES_VALUES:
                raw_str = _SERIES_VALUES[series_id][0]
                return _make_fred_response(raw_str)
            return _make_fred_response("0.0")

        with patch.object(
            fred_service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=_mock_get_tracking,
        ):
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)
        assert ctx.completeness_ratio() == pytest.approx(1.0, abs=1e-9)
        # DGS10 and VIXCLS should NOT have been fetched (they were cached)
        assert "DGS10" not in call_series
        assert "VIXCLS" not in call_series
        # Other series should have been fetched
        assert "DGS2" in call_series
        assert "UNRATE" in call_series


# ---------------------------------------------------------------------------
# Tests — per-series TTL
# ---------------------------------------------------------------------------


class TestMacroSeriesTTL:
    """Tests for per-series TTL configuration."""

    def test_daily_series_have_24h_ttl(self) -> None:
        """Daily series (DGS10, DGS2, T10Y2Y, FEDFUNDS, VIXCLS) have 24h TTL."""
        daily_ids = {"DGS10", "DGS2", "T10Y2Y", "FEDFUNDS", "VIXCLS"}
        for cfg in _MACRO_SERIES:
            if cfg.series_id in daily_ids:
                assert cfg.ttl_hours == 24, f"{cfg.series_id} should have 24h TTL"

    def test_monthly_series_have_168h_ttl(self) -> None:
        """Monthly series (CPIAUCSL, INDPRO, UNRATE) have 168h (7-day) TTL."""
        monthly_ids = {"CPIAUCSL", "INDPRO", "UNRATE"}
        for cfg in _MACRO_SERIES:
            if cfg.series_id in monthly_ids:
                assert cfg.ttl_hours == 168, f"{cfg.series_id} should have 168h TTL"

    def test_all_series_in_registry(self) -> None:
        """All 8 expected series are in _MACRO_SERIES."""
        expected_ids = {
            "DGS10",
            "DGS2",
            "T10Y2Y",
            "FEDFUNDS",
            "VIXCLS",
            "CPIAUCSL",
            "INDPRO",
            "UNRATE",
        }
        actual_ids = {cfg.series_id for cfg in _MACRO_SERIES}
        assert actual_ids == expected_ids

    def test_series_to_field_mapping_complete(self) -> None:
        """Every series in registry has a mapping to a MacroContext field."""
        for cfg in _MACRO_SERIES:
            assert cfg.series_id in _SERIES_TO_FIELD, (
                f"{cfg.series_id} missing from _SERIES_TO_FIELD"
            )


# ---------------------------------------------------------------------------
# Tests — transform application
# ---------------------------------------------------------------------------


class TestTransformApplication:
    """Tests for FRED value transforms using FredTransform enum."""

    @pytest.mark.asyncio
    async def test_pct_to_decimal_transform(self, fred_service: FredService) -> None:
        """PCT_TO_DECIMAL divides by 100 (4.50 -> 0.045)."""
        from options_arena.models.enums import FredTransform

        result = fred_service._apply_transform(4.50, FredTransform.PCT_TO_DECIMAL)
        assert result == pytest.approx(0.045, rel=1e-6)

    @pytest.mark.asyncio
    async def test_passthrough_transform(self, fred_service: FredService) -> None:
        """PASSTHROUGH returns the value as-is (18.50 -> 18.50)."""
        from options_arena.models.enums import FredTransform

        result = fred_service._apply_transform(18.50, FredTransform.PASSTHROUGH)
        assert result == pytest.approx(18.50, rel=1e-6)

    @pytest.mark.asyncio
    async def test_yoy_pct_change_transform(self, fred_service: FredService) -> None:
        """YOY_PCT_CHANGE returns the value as-is (3.20 -> 3.20)."""
        from options_arena.models.enums import FredTransform

        result = fred_service._apply_transform(3.20, FredTransform.YOY_PCT_CHANGE)
        assert result == pytest.approx(3.20, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests — never-raises contract
# ---------------------------------------------------------------------------


class TestNeverRaisesContract:
    """Verify fetch_macro_context() never raises, regardless of failure mode."""

    @pytest.mark.asyncio
    async def test_type_error_does_not_propagate(self, fred_service: FredService) -> None:
        """TypeError in inner method does not propagate."""
        with patch.object(
            fred_service,
            "_fetch_macro_context_inner",
            new_callable=AsyncMock,
            side_effect=TypeError("bad type"),
        ):
            ctx = await fred_service.fetch_macro_context()

        assert isinstance(ctx, MacroContext)

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_propagates(self, fred_service: FredService) -> None:
        """KeyboardInterrupt is NOT caught (Python standard — let it propagate)."""
        with (
            patch.object(
                fred_service,
                "_fetch_macro_context_inner",
                new_callable=AsyncMock,
                side_effect=KeyboardInterrupt(),
            ),
            pytest.raises(KeyboardInterrupt),
        ):
            await fred_service.fetch_macro_context()
