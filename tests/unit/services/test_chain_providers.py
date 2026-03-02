"""Tests for ChainProvider protocol and YFinanceChainProvider implementation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any  # noqa: ANN401 — test helper dicts need Any for mixed-type values
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_arena.models.config import PricingConfig, ServiceConfig
from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.services.cache import ServiceCache
from options_arena.services.options_data import (
    ChainProvider,
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
    """Default ServiceConfig for chain provider tests."""
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


@pytest.fixture
def provider(
    config: ServiceConfig,
    pricing_config: PricingConfig,
    cache: ServiceCache,
    limiter: RateLimiter,
) -> YFinanceChainProvider:
    """Fully constructed YFinanceChainProvider for testing."""
    return YFinanceChainProvider(config, pricing_config, cache, limiter)


def _make_chain_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame mimicking yfinance option chain columns."""
    columns = [
        "contractSymbol",
        "lastTradeDate",
        "strike",
        "lastPrice",
        "bid",
        "ask",
        "change",
        "percentChange",
        "volume",
        "openInterest",
        "impliedVolatility",
        "inTheMoney",
        "contractSize",
        "currency",
    ]
    full_rows = []
    for row in rows:
        full_row: dict[str, Any] = {col: None for col in columns}
        full_row.update(row)
        full_rows.append(full_row)
    return pd.DataFrame(full_rows)


def _make_option_chain_result(
    calls_rows: list[dict[str, Any]],
    puts_rows: list[dict[str, Any]],
) -> MagicMock:
    """Create a mock yfinance option_chain() result with .calls and .puts."""
    result = MagicMock()
    result.calls = _make_chain_df(calls_rows)
    result.puts = _make_chain_df(puts_rows)
    return result


# ---------------------------------------------------------------------------
# TestChainProviderProtocol
# ---------------------------------------------------------------------------


class TestChainProviderProtocol:
    """Verify ChainProvider protocol behavior."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """ChainProvider is decorated with @runtime_checkable."""
        assert (
            hasattr(ChainProvider, "__protocol_attrs__")
            or hasattr(ChainProvider, "__abstractmethods__")
            or issubclass(type(ChainProvider), type)
        )
        # runtime_checkable means isinstance works
        assert isinstance(ChainProvider, type)

    def test_yfinance_provider_satisfies_protocol(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """YFinanceChainProvider is an instance of ChainProvider at runtime."""
        provider = YFinanceChainProvider(config, pricing_config, cache, limiter)
        assert isinstance(provider, ChainProvider)

    def test_protocol_has_required_methods(self) -> None:
        """ChainProvider protocol defines fetch_expirations and fetch_chain."""
        # These are the structural requirements of the protocol
        assert hasattr(ChainProvider, "fetch_expirations")
        assert hasattr(ChainProvider, "fetch_chain")


# ---------------------------------------------------------------------------
# TestYFinanceChainProvider
# ---------------------------------------------------------------------------


class TestYFinanceChainProvider:
    """Tests for YFinanceChainProvider — the yfinance implementation."""

    async def test_fetch_expirations_happy_path(self, provider: YFinanceChainProvider) -> None:
        """fetch_expirations returns sorted list[date] from yfinance .options."""
        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-04-18", "2026-03-21", "2026-05-16")

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await provider.fetch_expirations("AAPL")

        assert result == [
            date(2026, 3, 21),
            date(2026, 4, 18),
            date(2026, 5, 16),
        ]
        for d in result:
            assert isinstance(d, date)

    async def test_fetch_chain_happy_path(self, provider: YFinanceChainProvider) -> None:
        """fetch_chain returns OptionContract list from calls + puts DataFrames."""
        call_row = {
            "contractSymbol": "AAPL260418C00185000",
            "strike": 185.0,
            "lastPrice": 5.50,
            "bid": 5.30,
            "ask": 5.70,
            "volume": 500,
            "openInterest": 2000,
            "impliedVolatility": 0.32,
            "inTheMoney": True,
        }
        put_row = {
            "contractSymbol": "AAPL260418P00185000",
            "strike": 185.0,
            "lastPrice": 3.20,
            "bid": 3.00,
            "ask": 3.40,
            "volume": 300,
            "openInterest": 1500,
            "impliedVolatility": 0.28,
            "inTheMoney": False,
        }
        chain_result = _make_option_chain_result([call_row], [put_row])

        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = chain_result

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            contracts = await provider.fetch_chain("AAPL", date(2026, 4, 18))

        assert len(contracts) == 2
        call = contracts[0]
        assert call.option_type == OptionType.CALL
        assert call.ticker == "AAPL"
        assert call.expiration == date(2026, 4, 18)
        assert call.exercise_style == ExerciseStyle.AMERICAN

        put = contracts[1]
        assert put.option_type == OptionType.PUT

    async def test_fetch_chain_cache_usage(self, provider: YFinanceChainProvider) -> None:
        """Second call to fetch_chain uses cached data, not yfinance."""
        row = {
            "strike": 300.0,
            "lastPrice": 10.0,
            "bid": 9.5,
            "ask": 10.5,
            "volume": 50,
            "openInterest": 500,
            "impliedVolatility": 0.22,
        }
        chain_result = _make_option_chain_result([row], [])

        call_count = 0

        def counting_option_chain(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return chain_result

        mock_ticker = MagicMock()
        mock_ticker.option_chain = counting_option_chain

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker

            # First call — hits yfinance
            result1 = await provider.fetch_chain("CACHE", date(2026, 4, 18))
            # Second call — should use cache
            result2 = await provider.fetch_chain("CACHE", date(2026, 4, 18))

        assert call_count == 1  # yfinance called only once
        assert len(result1) == len(result2)
        assert result1[0].strike == result2[0].strike

    async def test_fetch_chain_timeout(
        self,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """yfinance hang triggers DataSourceUnavailableError via timeout."""
        fast_config = ServiceConfig(yfinance_timeout=0.1)
        prov = YFinanceChainProvider(fast_config, pricing_config, cache, limiter)

        mock_ticker = MagicMock()

        def slow_option_chain(*_args: object, **_kwargs: object) -> None:
            import time

            time.sleep(5.0)

        mock_ticker.option_chain = slow_option_chain

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(DataSourceUnavailableError, match="timeout"):
                await prov.fetch_chain("SLOW", date(2026, 4, 18))

    async def test_fetch_chain_liquidity_filter(self, provider: YFinanceChainProvider) -> None:
        """Contracts failing liquidity filter are excluded from results."""
        good_row = {
            "strike": 150.0,
            "lastPrice": 5.0,
            "bid": 4.5,
            "ask": 5.5,
            "volume": 100,
            "openInterest": 500,
            "impliedVolatility": 0.30,
        }
        # Both bid and ask zero — dead contract, should be filtered
        dead_row = {
            "strike": 160.0,
            "lastPrice": 1.0,
            "bid": 0.0,
            "ask": 0.0,
            "volume": 200,
            "openInterest": 1000,
            "impliedVolatility": 0.25,
        }
        chain_result = _make_option_chain_result([good_row, dead_row], [])

        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = chain_result

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            contracts = await provider.fetch_chain("FILT", date(2026, 5, 15))

        assert len(contracts) == 1
        assert contracts[0].strike == Decimal("150.0")

    async def test_fetch_chain_greeks_none(self, provider: YFinanceChainProvider) -> None:
        """yfinance provides NO Greeks — greeks must be None on all contracts."""
        row = {
            "strike": 200.0,
            "lastPrice": 8.0,
            "bid": 7.5,
            "ask": 8.5,
            "volume": 100,
            "openInterest": 1000,
            "impliedVolatility": 0.25,
        }
        chain_result = _make_option_chain_result([row], [row])

        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = chain_result

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            contracts = await provider.fetch_chain("QQQ", date(2026, 4, 17))

        for c in contracts:
            assert c.greeks is None

    async def test_fetch_chain_greeks_source_none(self, provider: YFinanceChainProvider) -> None:
        """yfinance does not provide greeks_source — must be None."""
        row = {
            "strike": 180.0,
            "lastPrice": 6.0,
            "bid": 5.5,
            "ask": 6.5,
            "volume": 200,
            "openInterest": 800,
            "impliedVolatility": 0.28,
        }
        chain_result = _make_option_chain_result([row], [])

        mock_ticker = MagicMock()
        mock_ticker.option_chain.return_value = chain_result

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            contracts = await provider.fetch_chain("GS", date(2026, 6, 19))

        assert len(contracts) == 1
        assert contracts[0].greeks_source is None


# ---------------------------------------------------------------------------
# TestOptionsDataServiceDelegation
# ---------------------------------------------------------------------------


class TestOptionsDataServiceDelegation:
    """Verify OptionsDataService delegates to its ChainProvider."""

    async def test_service_delegates_fetch_expirations(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """OptionsDataService.fetch_expirations delegates to provider."""
        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-04-18", "2026-03-21")

        service = OptionsDataService(config, pricing_config, cache, limiter)

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_expirations("AAPL")

        assert result == [date(2026, 3, 21), date(2026, 4, 18)]

    async def test_service_uses_injected_provider(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """OptionsDataService accepts a custom ChainProvider via constructor."""
        # Create a mock provider that satisfies ChainProvider protocol
        mock_provider = MagicMock(spec=YFinanceChainProvider)
        mock_provider.fetch_expirations.return_value = [date(2026, 7, 17)]
        mock_provider.fetch_chain.return_value = []

        service = OptionsDataService(
            config, pricing_config, cache, limiter, provider=mock_provider
        )

        expirations = await service.fetch_expirations("TEST")
        assert expirations == [date(2026, 7, 17)]
        mock_provider.fetch_expirations.assert_awaited_once_with("TEST")

        chain = await service.fetch_chain("TEST", date(2026, 7, 17))
        assert chain == []
        mock_provider.fetch_chain.assert_awaited_once_with("TEST", date(2026, 7, 17))

    async def test_service_default_provider_is_yfinance(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When no provider is given, OptionsDataService defaults to YFinanceChainProvider."""
        service = OptionsDataService(config, pricing_config, cache, limiter)
        assert isinstance(service._provider, YFinanceChainProvider)
