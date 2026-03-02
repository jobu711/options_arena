"""Tests for provider orchestration — CBOE-to-yfinance fallback in OptionsDataService."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.models.config import OpenBBConfig, PricingConfig, ServiceConfig
from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from options_arena.services.cache import ServiceCache
from options_arena.services.cboe_provider import CBOEChainProvider
from options_arena.services.options_data import (
    OptionsDataService,
    YFinanceChainProvider,
)
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig for orchestration tests."""
    return ServiceConfig()


@pytest.fixture
def pricing_config() -> PricingConfig:
    """Default PricingConfig with min_oi=100, min_volume=1."""
    return PricingConfig()


@pytest.fixture
def cache(config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache (no SQLite)."""
    return ServiceCache(config, db_path=None)


@pytest.fixture
def limiter() -> RateLimiter:
    """Fast rate limiter for tests."""
    return RateLimiter(rate=100.0, max_concurrent=10)


def _make_contract(
    ticker: str = "AAPL",
    strike: str = "185.00",
    option_type: OptionType = OptionType.CALL,
) -> OptionContract:
    """Create a minimal OptionContract for testing."""
    return OptionContract(
        ticker=ticker,
        option_type=option_type,
        strike=Decimal(strike),
        expiration=date(2026, 4, 18),
        bid=Decimal("5.30"),
        ask=Decimal("5.70"),
        last=Decimal("5.50"),
        volume=500,
        open_interest=2000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.32,
        greeks=None,
    )


class _MockProvider:
    """Mock ChainProvider for testing — satisfies the ChainProvider protocol."""

    def __init__(
        self,
        *,
        expirations: list[date] | None = None,
        contracts: list[OptionContract] | None = None,
        error: DataSourceUnavailableError | None = None,
    ) -> None:
        self._expirations = expirations or []
        self._contracts = contracts or []
        self._error = error

    async def fetch_expirations(self, ticker: str) -> list[date]:
        if self._error is not None:
            raise self._error
        return self._expirations

    async def fetch_chain(self, ticker: str, expiration: date) -> list[OptionContract]:
        if self._error is not None:
            raise self._error
        return self._contracts


# ---------------------------------------------------------------------------
# TestProviderOrchestration
# ---------------------------------------------------------------------------


class TestProviderOrchestration:
    """Tests for OptionsDataService provider orchestration with fallback."""

    async def test_cboe_first_when_enabled(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify CBOE provider is tried first when enabled and SDK available."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        with patch("options_arena.services.options_data.CBOEChainProvider") as mock_cboe_cls:
            mock_cboe = MagicMock(spec=CBOEChainProvider)
            mock_cboe.available = True
            mock_cboe_cls.return_value = mock_cboe

            service = OptionsDataService(
                config,
                pricing_config,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

        # Should have 2 providers: CBOE first, then yfinance
        assert len(service._providers) == 2
        assert service._providers[0] is mock_cboe
        assert isinstance(service._providers[1], YFinanceChainProvider)

    async def test_yfinance_only_when_cboe_disabled(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify only yfinance provider when cboe_chains_enabled=False."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=False)

        service = OptionsDataService(
            config,
            pricing_config,
            cache,
            limiter,
            openbb_config=openbb_config,
        )

        assert len(service._providers) == 1
        assert isinstance(service._providers[0], YFinanceChainProvider)

    async def test_yfinance_only_when_no_config(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify only yfinance when openbb_config is None."""
        service = OptionsDataService(config, pricing_config, cache, limiter)

        assert len(service._providers) == 1
        assert isinstance(service._providers[0], YFinanceChainProvider)

    async def test_yfinance_only_when_sdk_missing(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify fallback to yfinance when OpenBB SDK not installed."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        with patch("options_arena.services.options_data.CBOEChainProvider") as mock_cboe_cls:
            mock_cboe = MagicMock(spec=CBOEChainProvider)
            mock_cboe.available = False  # SDK not installed
            mock_cboe_cls.return_value = mock_cboe

            service = OptionsDataService(
                config,
                pricing_config,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

        # CBOE not available, so only yfinance
        assert len(service._providers) == 1
        assert isinstance(service._providers[0], YFinanceChainProvider)

    async def test_fallback_cboe_to_yfinance(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify CBOE failure falls back to yfinance."""
        expected_contracts = [_make_contract()]

        cboe_provider = _MockProvider(
            error=DataSourceUnavailableError("CBOE: test error"),
        )
        yfinance_provider = _MockProvider(contracts=expected_contracts)

        service = OptionsDataService(
            config, pricing_config, cache, limiter, provider=cboe_provider
        )
        # Override providers list to simulate CBOE + yfinance
        service._providers = [cboe_provider, yfinance_provider]

        result = await service.fetch_chain("AAPL", date(2026, 4, 18))
        assert result == expected_contracts

    async def test_fallback_logs_warning(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify fallback event is logged at WARNING."""
        cboe_provider = _MockProvider(
            error=DataSourceUnavailableError("CBOE: test failure"),
        )
        yfinance_provider = _MockProvider(contracts=[_make_contract()])

        service = OptionsDataService(
            config, pricing_config, cache, limiter, provider=cboe_provider
        )
        service._providers = [cboe_provider, yfinance_provider]

        with caplog.at_level(logging.WARNING, logger="options_arena.services.options_data"):
            await service.fetch_chain("AAPL", date(2026, 4, 18))

        # Should have a warning about the failed provider
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("_MockProvider" in msg and "AAPL" in msg for msg in warning_messages)

    async def test_all_providers_fail_raises(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify DataSourceUnavailableError when all providers fail."""
        provider1 = _MockProvider(
            error=DataSourceUnavailableError("CBOE: down"),
        )
        provider2 = _MockProvider(
            error=DataSourceUnavailableError("yfinance: also down"),
        )

        service = OptionsDataService(config, pricing_config, cache, limiter, provider=provider1)
        service._providers = [provider1, provider2]

        with pytest.raises(DataSourceUnavailableError, match="yfinance: also down"):
            await service.fetch_chain("FAIL", date(2026, 4, 18))

    async def test_fetch_expirations_fallback(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify expiration fetch also uses provider fallback."""
        expected_expirations = [date(2026, 3, 21), date(2026, 4, 18)]

        cboe_provider = _MockProvider(
            error=DataSourceUnavailableError("CBOE: timeout"),
        )
        yfinance_provider = _MockProvider(expirations=expected_expirations)

        service = OptionsDataService(
            config, pricing_config, cache, limiter, provider=cboe_provider
        )
        service._providers = [cboe_provider, yfinance_provider]

        result = await service.fetch_expirations("AAPL")
        assert result == expected_expirations

    async def test_backward_compat_no_openbb_config(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify existing constructor (without openbb_config) still works."""
        # This is the original constructor signature — must not raise
        service = OptionsDataService(config, pricing_config, cache, limiter)
        assert len(service._providers) == 1
        assert isinstance(service._providers[0], YFinanceChainProvider)

    async def test_custom_provider_injection(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify provider= param still works (for tests)."""
        expected_contracts = [_make_contract()]
        mock_provider = _MockProvider(contracts=expected_contracts)

        service = OptionsDataService(
            config, pricing_config, cache, limiter, provider=mock_provider
        )

        # Custom provider is the sole provider
        assert len(service._providers) == 1
        assert service._providers[0] is mock_provider

        # And it works correctly
        result = await service.fetch_chain("AAPL", date(2026, 4, 18))
        assert result == expected_contracts

    async def test_close_closes_all_providers(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify close() calls close on all providers that have a close method."""
        provider1 = _MockProvider(contracts=[])
        provider1.close = AsyncMock()  # type: ignore[attr-defined]
        provider2 = _MockProvider(contracts=[])
        provider2.close = AsyncMock()  # type: ignore[attr-defined]

        service = OptionsDataService(config, pricing_config, cache, limiter, provider=provider1)
        service._providers = [provider1, provider2]

        await service.close()

        provider1.close.assert_awaited_once()  # type: ignore[attr-defined]
        provider2.close.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_fetch_expirations_all_fail_raises(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify DataSourceUnavailableError on fetch_expirations when all providers fail."""
        provider1 = _MockProvider(
            error=DataSourceUnavailableError("CBOE: down"),
        )
        provider2 = _MockProvider(
            error=DataSourceUnavailableError("yfinance: timeout"),
        )

        service = OptionsDataService(config, pricing_config, cache, limiter, provider=provider1)
        service._providers = [provider1, provider2]

        with pytest.raises(DataSourceUnavailableError, match="yfinance: timeout"):
            await service.fetch_expirations("FAIL")

    async def test_first_provider_succeeds_no_fallback(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When the first provider succeeds, the second is never called."""
        cboe_contracts = [_make_contract(strike="180.00")]

        cboe_provider = _MockProvider(contracts=cboe_contracts)
        yfinance_provider = _MockProvider(
            error=DataSourceUnavailableError("should not be called"),
        )

        service = OptionsDataService(
            config, pricing_config, cache, limiter, provider=cboe_provider
        )
        service._providers = [cboe_provider, yfinance_provider]

        result = await service.fetch_chain("AAPL", date(2026, 4, 18))
        assert len(result) == 1
        assert result[0].strike == Decimal("180.00")
