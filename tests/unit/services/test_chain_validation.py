"""Tests for chain validation mode in OptionsDataService.

Tests cover:
  - Validation mode fires background yfinance comparison
  - Validation mode logs comparison metrics
  - Validation mode returns primary result unchanged
  - yfinance failure in validation is non-blocking
  - Validation disabled follows normal flow
  - DI wiring passes openbb_config from CLI and API
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from options_arena.models.config import OpenBBConfig, PricingConfig, ServiceConfig
from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from options_arena.services.cache import ServiceCache
from options_arena.services.options_data import (
    OptionsDataService,
    YFinanceChainProvider,
)
from options_arena.services.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig."""
    return ServiceConfig()


@pytest.fixture
def pricing_config() -> PricingConfig:
    """Default PricingConfig."""
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
    market_iv: float = 0.32,
) -> OptionContract:
    """Create a minimal OptionContract for testing."""
    return OptionContract(
        ticker=ticker,
        option_type=option_type,
        strike=Decimal(strike),
        expiration=date(2099, 4, 18),
        bid=Decimal("5.30"),
        ask=Decimal("5.70"),
        last=Decimal("5.50"),
        volume=500,
        open_interest=2000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=market_iv,
        greeks=None,
    )


class _MockProvider:
    """Mock ChainProvider that satisfies the ChainProvider protocol."""

    def __init__(
        self,
        *,
        contracts: list[OptionContract] | None = None,
        expirations: list[date] | None = None,
    ) -> None:
        self._contracts = contracts or []
        self._expirations = expirations or []

    async def fetch_expirations(self, ticker: str) -> list[date]:
        return self._expirations

    async def fetch_chain(self, ticker: str, expiration: date) -> list[OptionContract]:
        return self._contracts


# ---------------------------------------------------------------------------
# TestChainValidationMode
# ---------------------------------------------------------------------------


class TestChainValidationMode:
    """Tests for parallel validation mode in OptionsDataService."""

    @pytest.mark.asyncio
    async def test_validation_mode_fetches_both(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When validation_mode=True and primary is CBOE, yfinance is also called."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True, chain_validation_mode=True)

        primary_contracts = [_make_contract(strike="185.00")]

        # Create the service with an injected non-yfinance provider
        cboe_mock = _MockProvider(contracts=primary_contracts)
        service = OptionsDataService(
            config,
            pricing_config,
            cache,
            limiter,
            provider=cboe_mock,
            openbb_config=openbb_config,
        )
        # Inject a mock yfinance provider
        yf_mock = MagicMock(spec=YFinanceChainProvider)
        yf_mock.fetch_chain = AsyncMock(return_value=[_make_contract(strike="190.00")])
        service._yfinance_provider = yf_mock

        result = await service.fetch_chain("AAPL", date(2099, 4, 18))

        # Primary result returned
        assert len(result) == 1
        assert result[0].strike == Decimal("185.00")

        # Give the background task time to complete
        await asyncio.sleep(0.1)

        # yfinance should have been called in the background
        yf_mock.fetch_chain.assert_awaited_once_with("AAPL", date(2099, 4, 18))

    @pytest.mark.asyncio
    async def test_validation_mode_logs_comparison(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Validation mode logs strike overlap and IV diff at INFO level."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True, chain_validation_mode=True)

        primary_contracts = [
            _make_contract(strike="185.00", market_iv=0.30),
            _make_contract(strike="190.00", market_iv=0.35),
        ]

        cboe_mock = _MockProvider(contracts=primary_contracts)
        service = OptionsDataService(
            config,
            pricing_config,
            cache,
            limiter,
            provider=cboe_mock,
            openbb_config=openbb_config,
        )

        yf_contracts = [
            _make_contract(strike="185.00", market_iv=0.32),
            _make_contract(strike="195.00", market_iv=0.40),
        ]
        yf_mock = MagicMock(spec=YFinanceChainProvider)
        yf_mock.fetch_chain = AsyncMock(return_value=yf_contracts)
        service._yfinance_provider = yf_mock

        with caplog.at_level(logging.INFO, logger="options_arena.services.options_data"):
            await service.fetch_chain("AAPL", date(2099, 4, 18))
            await asyncio.sleep(0.1)

        # Check for validation log message
        validation_logs = [r.message for r in caplog.records if "Chain validation" in r.message]
        assert len(validation_logs) == 1
        assert "overlap=1" in validation_logs[0]
        assert "primary_only=1" in validation_logs[0]
        assert "yf_only=1" in validation_logs[0]

    @pytest.mark.asyncio
    async def test_validation_mode_returns_primary(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Validation mode returns the primary provider's result, not yfinance's."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True, chain_validation_mode=True)

        primary_contracts = [_make_contract(strike="185.00")]
        yf_contracts = [
            _make_contract(strike="190.00"),
            _make_contract(strike="195.00"),
        ]

        cboe_mock = _MockProvider(contracts=primary_contracts)
        service = OptionsDataService(
            config,
            pricing_config,
            cache,
            limiter,
            provider=cboe_mock,
            openbb_config=openbb_config,
        )
        yf_mock = MagicMock(spec=YFinanceChainProvider)
        yf_mock.fetch_chain = AsyncMock(return_value=yf_contracts)
        service._yfinance_provider = yf_mock

        result = await service.fetch_chain("AAPL", date(2099, 4, 18))

        # Must return CBOE result, not yfinance
        assert len(result) == 1
        assert result[0].strike == Decimal("185.00")
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_validation_mode_yfinance_failure_non_blocking(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """yfinance failure in validation is non-blocking; primary result still returned."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True, chain_validation_mode=True)

        primary_contracts = [_make_contract(strike="185.00")]

        cboe_mock = _MockProvider(contracts=primary_contracts)
        service = OptionsDataService(
            config,
            pricing_config,
            cache,
            limiter,
            provider=cboe_mock,
            openbb_config=openbb_config,
        )
        yf_mock = MagicMock(spec=YFinanceChainProvider)
        yf_mock.fetch_chain = AsyncMock(side_effect=RuntimeError("yfinance network error"))
        service._yfinance_provider = yf_mock

        with caplog.at_level(logging.WARNING, logger="options_arena.services.options_data"):
            result = await service.fetch_chain("AAPL", date(2099, 4, 18))
            await asyncio.sleep(0.1)

        # Primary result returned despite yfinance failure
        assert len(result) == 1
        assert result[0].strike == Decimal("185.00")

        # Warning logged about validation failure
        warning_logs = [
            r.message for r in caplog.records if "Chain validation failed" in r.message
        ]
        assert len(warning_logs) == 1
        assert "yfinance network error" in warning_logs[0]

    @pytest.mark.asyncio
    async def test_validation_disabled_normal_flow(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When validation mode is disabled, no background task is created."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=False, chain_validation_mode=False)

        expected = [_make_contract()]
        mock_provider = _MockProvider(contracts=expected)

        service = OptionsDataService(
            config,
            pricing_config,
            cache,
            limiter,
            provider=mock_provider,
            openbb_config=openbb_config,
        )

        # Validation mode should be off
        assert service._validation_mode is False
        assert service._yfinance_provider is None

        result = await service.fetch_chain("AAPL", date(2099, 4, 18))
        assert result == expected


# ---------------------------------------------------------------------------
# TestDIWiring
# ---------------------------------------------------------------------------


class TestDIWiring:
    """Tests verifying DI wiring passes openbb_config to OptionsDataService."""

    def test_cli_scan_passes_openbb_config(self) -> None:
        """Verify _scan_async constructs OptionsDataService with openbb_config.

        Uses source inspection to confirm the keyword argument is present in
        the service construction call site.
        """
        import inspect

        from options_arena.cli.commands import _scan_async

        source = inspect.getsource(_scan_async)
        assert "openbb_config=settings.openbb" in source

    def test_cli_batch_passes_openbb_config(self) -> None:
        """Verify _batch_async constructs OptionsDataService with openbb_config."""
        import inspect

        from options_arena.cli.commands import _batch_async

        source = inspect.getsource(_batch_async)
        assert "openbb_config=settings.openbb" in source

    def test_cli_debate_passes_openbb_config(self) -> None:
        """Verify _debate_async constructs OptionsDataService with openbb_config."""
        import inspect

        from options_arena.cli.commands import _debate_async

        source = inspect.getsource(_debate_async)
        assert "openbb_config=settings.openbb" in source

    def test_api_lifespan_passes_openbb_config(self) -> None:
        """Verify API lifespan constructs OptionsDataService with openbb_config."""
        import inspect

        from options_arena.api.app import lifespan

        source = inspect.getsource(lifespan)
        assert "openbb_config=settings.openbb" in source
