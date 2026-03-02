"""Tests for CBOE chains health check in HealthService.

Tests cover:
  - check_cboe_chains() returns unavailable when CBOE chains disabled
  - check_cboe_chains() returns unavailable when OpenBB SDK not installed
  - check_cboe_chains() returns available with latency on success
  - check_cboe_chains() returns error on probe failure
  - check_all() includes cboe_chains status
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.models.config import OpenBBConfig, ServiceConfig
from options_arena.models.health import HealthStatus
from options_arena.services.cache import ServiceCache
from options_arena.services.health import HealthService
from options_arena.services.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service_config() -> ServiceConfig:
    """Default ServiceConfig for tests."""
    return ServiceConfig()


@pytest.fixture
def openbb_config_enabled() -> OpenBBConfig:
    """OpenBB config with CBOE chains enabled."""
    return OpenBBConfig(cboe_chains_enabled=True)


@pytest.fixture
def openbb_config_disabled() -> OpenBBConfig:
    """OpenBB config with CBOE chains disabled."""
    return OpenBBConfig(cboe_chains_enabled=False)


@pytest.fixture
def cache(service_config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache (no SQLite)."""
    return ServiceCache(service_config, db_path=None)


@pytest.fixture
def limiter() -> RateLimiter:
    """Fast rate limiter for tests."""
    return RateLimiter(rate=100.0, max_concurrent=10)


# ---------------------------------------------------------------------------
# TestCBOEHealthCheck
# ---------------------------------------------------------------------------


class TestCBOEHealthCheck:
    """Tests for check_cboe_chains() method."""

    @pytest.mark.asyncio
    async def test_cboe_disabled_returns_unavailable(
        self,
        service_config: ServiceConfig,
        openbb_config_disabled: OpenBBConfig,
    ) -> None:
        """CBOE chains disabled in config returns available=False."""
        svc = HealthService(service_config, openbb_config=openbb_config_disabled)
        result = await svc.check_cboe_chains()

        assert isinstance(result, HealthStatus)
        assert result.service_name == "cboe_chains"
        assert result.available is False
        assert result.error == "CBOE chains disabled"

    @pytest.mark.asyncio
    async def test_cboe_no_config_returns_unavailable(
        self,
        service_config: ServiceConfig,
    ) -> None:
        """No openbb_config at all returns available=False."""
        svc = HealthService(service_config)
        result = await svc.check_cboe_chains()

        assert result.service_name == "cboe_chains"
        assert result.available is False
        assert result.error == "CBOE chains disabled"

    @pytest.mark.asyncio
    async def test_cboe_sdk_missing_returns_unavailable(
        self,
        service_config: ServiceConfig,
        openbb_config_enabled: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """OpenBB SDK not installed returns available=False."""
        svc = HealthService(
            service_config,
            openbb_config=openbb_config_enabled,
            cache=cache,
            limiter=limiter,
        )

        with patch("options_arena.services.cboe_provider.CBOEChainProvider") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.available = False
            mock_cls.return_value = mock_provider

            result = await svc.check_cboe_chains()

        assert result.service_name == "cboe_chains"
        assert result.available is False
        assert result.error == "OpenBB SDK not installed"

    @pytest.mark.asyncio
    async def test_cboe_available_returns_latency(
        self,
        service_config: ServiceConfig,
        openbb_config_enabled: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Successful CBOE probe returns available=True with latency."""
        svc = HealthService(
            service_config,
            openbb_config=openbb_config_enabled,
            cache=cache,
            limiter=limiter,
        )

        with patch("options_arena.services.cboe_provider.CBOEChainProvider") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.available = True
            mock_provider.fetch_expirations = AsyncMock(return_value=[])
            mock_cls.return_value = mock_provider

            result = await svc.check_cboe_chains()

        assert result.service_name == "cboe_chains"
        assert result.available is True
        assert result.latency_ms is not None
        assert result.latency_ms >= 0.0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_cboe_probe_failure_returns_error(
        self,
        service_config: ServiceConfig,
        openbb_config_enabled: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """CBOE probe failure returns available=False with error and latency."""
        svc = HealthService(
            service_config,
            openbb_config=openbb_config_enabled,
            cache=cache,
            limiter=limiter,
        )

        with patch("options_arena.services.cboe_provider.CBOEChainProvider") as mock_cls:
            mock_provider = MagicMock()
            mock_provider.available = True
            mock_provider.fetch_expirations = AsyncMock(
                side_effect=RuntimeError("CBOE endpoint down")
            )
            mock_cls.return_value = mock_provider

            result = await svc.check_cboe_chains()

        assert result.service_name == "cboe_chains"
        assert result.available is False
        assert result.latency_ms is not None
        assert result.latency_ms >= 0.0
        assert result.error is not None
        assert "CBOE endpoint down" in result.error

    @pytest.mark.asyncio
    async def test_check_all_includes_cboe_chains(
        self,
        service_config: ServiceConfig,
        openbb_config_disabled: OpenBBConfig,
    ) -> None:
        """check_all() includes cboe_chains in the result set."""
        svc = HealthService(service_config, openbb_config=openbb_config_disabled)

        # Mock all other checks to avoid network calls
        svc.check_yfinance = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("yfinance")
        )
        svc.check_fred = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("fred")
        )
        svc.check_groq = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("groq")
        )
        svc.check_cboe = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("cboe")
        )
        svc.check_openbb = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_status("openbb", available=False)
        )

        results = await svc.check_all()
        service_names = [r.service_name for r in results]
        assert "cboe_chains" in service_names
        assert len(results) == 6

        # The cboe_chains entry should show disabled
        cboe_chains_result = next(r for r in results if r.service_name == "cboe_chains")
        assert cboe_chains_result.available is False
        assert cboe_chains_result.error == "CBOE chains disabled"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_status(name: str, available: bool = True) -> HealthStatus:
    """Build a HealthStatus for testing."""
    return HealthStatus(
        service_name=name,
        available=available,
        latency_ms=10.0,
        checked_at=datetime.now(UTC),
    )
