"""Tests for OptionsDataService — option chain fetching and liquidity filtering."""

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
    OptionsDataService,
    _passes_liquidity_filter,
)
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig for options data tests."""
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
def service(
    config: ServiceConfig,
    pricing_config: PricingConfig,
    cache: ServiceCache,
    limiter: RateLimiter,
) -> OptionsDataService:
    """Fully constructed OptionsDataService for testing."""
    return OptionsDataService(config, pricing_config, cache, limiter)


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
    # Fill missing columns with defaults
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
# fetch_expirations
# ---------------------------------------------------------------------------


async def test_fetch_expirations_happy_path(service: OptionsDataService) -> None:
    """fetch_expirations returns sorted list[date] from yfinance .options."""
    mock_ticker = MagicMock()
    mock_ticker.options = ("2026-04-18", "2026-03-21", "2026-05-16")

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        result = await service.fetch_expirations("AAPL")

    assert result == [
        date(2026, 3, 21),
        date(2026, 4, 18),
        date(2026, 5, 16),
    ]
    # All dates are date objects
    for d in result:
        assert isinstance(d, date)


# ---------------------------------------------------------------------------
# fetch_chain — happy path
# ---------------------------------------------------------------------------


async def test_fetch_chain_happy_path(service: OptionsDataService) -> None:
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
        contracts = await service.fetch_chain("AAPL", date(2026, 4, 18))

    assert len(contracts) == 2

    call = contracts[0]
    assert call.option_type == OptionType.CALL
    assert call.ticker == "AAPL"
    assert call.expiration == date(2026, 4, 18)

    put = contracts[1]
    assert put.option_type == OptionType.PUT


# ---------------------------------------------------------------------------
# Column mapping correctness
# ---------------------------------------------------------------------------


async def test_column_mapping_correctness(service: OptionsDataService) -> None:
    """Verify each yfinance column maps to the correct OptionContract field."""
    row = {
        "contractSymbol": "SPY260320C00500000",
        "strike": 500.0,
        "lastPrice": 12.75,
        "bid": 12.50,
        "ask": 13.00,
        "volume": 1200,
        "openInterest": 5000,
        "impliedVolatility": 0.1856,
        "inTheMoney": True,
    }
    chain_result = _make_option_chain_result([row], [])

    mock_ticker = MagicMock()
    mock_ticker.option_chain.return_value = chain_result

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        contracts = await service.fetch_chain("SPY", date(2026, 3, 20))

    assert len(contracts) == 1
    c = contracts[0]

    assert c.strike == Decimal("500.0")
    assert c.last == Decimal("12.75")
    assert c.bid == Decimal("12.5")
    assert c.ask == Decimal("13.0")
    assert c.volume == 1200
    assert c.open_interest == 5000
    assert c.market_iv == pytest.approx(0.1856, rel=1e-4)


# ---------------------------------------------------------------------------
# market_iv passthrough (no re-annualization)
# ---------------------------------------------------------------------------


async def test_market_iv_passthrough(service: OptionsDataService) -> None:
    """impliedVolatility passes through as market_iv without modification."""
    row = {
        "strike": 150.0,
        "lastPrice": 2.0,
        "bid": 1.0,
        "ask": 3.0,
        "volume": 10,
        "openInterest": 200,
        "impliedVolatility": 0.4567,
    }
    chain_result = _make_option_chain_result([row], [])

    mock_ticker = MagicMock()
    mock_ticker.option_chain.return_value = chain_result

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        contracts = await service.fetch_chain("TEST", date(2026, 6, 19))

    assert len(contracts) == 1
    # Exact passthrough — not multiplied by sqrt(252) or any other factor
    assert contracts[0].market_iv == pytest.approx(0.4567, rel=1e-6)


# ---------------------------------------------------------------------------
# exercise_style always AMERICAN
# ---------------------------------------------------------------------------


async def test_exercise_style_always_american(service: OptionsDataService) -> None:
    """All contracts from US equity options have ExerciseStyle.AMERICAN."""
    rows = [
        {
            "strike": 100.0 + i * 5,
            "lastPrice": 2.0,
            "bid": 1.5,
            "ask": 2.5,
            "volume": 50,
            "openInterest": 500,
            "impliedVolatility": 0.30,
        }
        for i in range(3)
    ]
    chain_result = _make_option_chain_result(rows, rows)

    mock_ticker = MagicMock()
    mock_ticker.option_chain.return_value = chain_result

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        contracts = await service.fetch_chain("XYZ", date(2026, 5, 15))

    assert len(contracts) == 6  # 3 calls + 3 puts
    for c in contracts:
        assert c.exercise_style == ExerciseStyle.AMERICAN


# ---------------------------------------------------------------------------
# greeks always None
# ---------------------------------------------------------------------------


async def test_greeks_always_none(service: OptionsDataService) -> None:
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
        contracts = await service.fetch_chain("QQQ", date(2026, 4, 17))

    for c in contracts:
        assert c.greeks is None


# ---------------------------------------------------------------------------
# Decimal precision
# ---------------------------------------------------------------------------


async def test_decimal_precision(service: OptionsDataService) -> None:
    """Strike/bid/ask/last are Decimal, not float — precision preserved."""
    row = {
        "strike": 185.50,
        "lastPrice": 1.05,
        "bid": 1.00,
        "ask": 1.10,
        "volume": 10,
        "openInterest": 200,
        "impliedVolatility": 0.30,
    }
    chain_result = _make_option_chain_result([row], [])

    mock_ticker = MagicMock()
    mock_ticker.option_chain.return_value = chain_result

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        contracts = await service.fetch_chain("PREC", date(2026, 7, 17))

    c = contracts[0]
    assert isinstance(c.strike, Decimal)
    assert isinstance(c.bid, Decimal)
    assert isinstance(c.ask, Decimal)
    assert isinstance(c.last, Decimal)
    # Verify string representation — Decimal("185.5") not float(185.5)
    assert c.strike == Decimal("185.5")
    assert c.last == Decimal("1.05")


# ---------------------------------------------------------------------------
# Liquidity filter — low OI rejection
# ---------------------------------------------------------------------------


def test_liquidity_filter_rejects_low_oi() -> None:
    """Contracts with OI below min_oi are rejected."""
    config = PricingConfig(min_oi=100, min_volume=1)
    row = pd.Series(
        {
            "openInterest": 50,  # below 100
            "volume": 10,
            "bid": 1.0,
            "ask": 2.0,
        }
    )
    assert _passes_liquidity_filter(row, config) is False


# ---------------------------------------------------------------------------
# Liquidity filter — low volume rejection
# ---------------------------------------------------------------------------


def test_liquidity_filter_rejects_low_volume() -> None:
    """Contracts with volume below min_volume are rejected."""
    config = PricingConfig(min_oi=100, min_volume=5)
    row = pd.Series(
        {
            "openInterest": 200,
            "volume": 2,  # below 5
            "bid": 1.0,
            "ask": 2.0,
        }
    )
    assert _passes_liquidity_filter(row, config) is False


# ---------------------------------------------------------------------------
# Liquidity filter — both-zero bid/ask rejection
# ---------------------------------------------------------------------------


def test_liquidity_filter_rejects_both_zero_bid_ask() -> None:
    """Truly dead contracts (bid=0, ask=0) are rejected regardless of OI/volume."""
    config = PricingConfig(min_oi=1, min_volume=1)
    row = pd.Series(
        {
            "openInterest": 5000,
            "volume": 1000,
            "bid": 0.0,
            "ask": 0.0,
        }
    )
    assert _passes_liquidity_filter(row, config) is False


# ---------------------------------------------------------------------------
# Liquidity filter — zero-bid exemption
# ---------------------------------------------------------------------------


def test_liquidity_filter_zero_bid_exemption() -> None:
    """Contracts with bid=0 but ask>0 pass through (zero-bid exemption)."""
    config = PricingConfig(min_oi=100, min_volume=1)
    row = pd.Series(
        {
            "openInterest": 500,
            "volume": 10,
            "bid": 0.0,
            "ask": 5.0,
        }
    )
    assert _passes_liquidity_filter(row, config) is True


# ---------------------------------------------------------------------------
# Empty chain
# ---------------------------------------------------------------------------


async def test_empty_chain_returns_empty_list(service: OptionsDataService) -> None:
    """When yfinance returns empty DataFrames, result is an empty list."""
    chain_result = _make_option_chain_result([], [])

    mock_ticker = MagicMock()
    mock_ticker.option_chain.return_value = chain_result

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        contracts = await service.fetch_chain("EMPTY", date(2026, 4, 18))

    assert contracts == []


# ---------------------------------------------------------------------------
# Timeout raises DataSourceUnavailableError
# ---------------------------------------------------------------------------


async def test_timeout_raises_data_source_unavailable(
    pricing_config: PricingConfig,
    cache: ServiceCache,
    limiter: RateLimiter,
) -> None:
    """yfinance hang triggers DataSourceUnavailableError via timeout."""
    fast_config = ServiceConfig(yfinance_timeout=0.1)
    svc = OptionsDataService(fast_config, pricing_config, cache, limiter)

    mock_ticker = MagicMock()

    def slow_option_chain(*_args: object, **_kwargs: object) -> None:
        import time

        time.sleep(5.0)  # longer than timeout

    mock_ticker.option_chain = slow_option_chain

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        with pytest.raises(DataSourceUnavailableError, match="timeout"):
            await svc.fetch_chain("SLOW", date(2026, 4, 18))


# ---------------------------------------------------------------------------
# fetch_chain_all_expirations
# ---------------------------------------------------------------------------


async def test_fetch_chain_all_expirations(service: OptionsDataService) -> None:
    """fetch_chain_all_expirations fetches all expirations concurrently."""
    expirations = ("2026-03-21", "2026-04-18", "2026-05-16")

    call_row = {
        "strike": 150.0,
        "lastPrice": 3.0,
        "bid": 2.5,
        "ask": 3.5,
        "volume": 100,
        "openInterest": 500,
        "impliedVolatility": 0.30,
    }
    chain_result = _make_option_chain_result([call_row], [])

    mock_ticker = MagicMock()
    mock_ticker.options = expirations
    mock_ticker.option_chain.return_value = chain_result

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        chains = await service.fetch_chain_all_expirations("AAPL")

    assert len(chains) == 3
    exp_dates = {c.expiration for c in chains}
    assert date(2026, 3, 21) in exp_dates
    assert date(2026, 4, 18) in exp_dates
    assert date(2026, 5, 16) in exp_dates
    # Each expiration has 1 call contract
    for chain in chains:
        assert len(chain.contracts) == 1
        assert chain.contracts[0].option_type == OptionType.CALL


# ---------------------------------------------------------------------------
# option_type assignment
# ---------------------------------------------------------------------------


async def test_option_type_call_vs_put(service: OptionsDataService) -> None:
    """Calls DataFrame produces CALL contracts, puts DataFrame produces PUT."""
    call_row = {
        "strike": 200.0,
        "lastPrice": 5.0,
        "bid": 4.5,
        "ask": 5.5,
        "volume": 200,
        "openInterest": 1000,
        "impliedVolatility": 0.25,
    }
    put_row = {
        "strike": 200.0,
        "lastPrice": 4.0,
        "bid": 3.5,
        "ask": 4.5,
        "volume": 150,
        "openInterest": 800,
        "impliedVolatility": 0.27,
    }
    chain_result = _make_option_chain_result([call_row], [put_row])

    mock_ticker = MagicMock()
    mock_ticker.option_chain.return_value = chain_result

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        contracts = await service.fetch_chain("MSFT", date(2026, 6, 19))

    calls = [c for c in contracts if c.option_type == OptionType.CALL]
    puts = [c for c in contracts if c.option_type == OptionType.PUT]
    assert len(calls) == 1
    assert len(puts) == 1


# ---------------------------------------------------------------------------
# Caching — second call uses cache
# ---------------------------------------------------------------------------


async def test_fetch_chain_caches_result(service: OptionsDataService) -> None:
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

    mock_ticker = MagicMock()
    mock_ticker.option_chain.return_value = chain_result
    call_count = 0

    def counting_option_chain(*_args: object, **_kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return chain_result

    mock_ticker.option_chain = counting_option_chain

    with patch("options_arena.services.options_data.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker

        # First call — hits yfinance
        result1 = await service.fetch_chain("CACHE", date(2026, 4, 18))
        # Second call — should use cache
        result2 = await service.fetch_chain("CACHE", date(2026, 4, 18))

    assert call_count == 1  # yfinance called only once
    assert len(result1) == len(result2)
    assert result1[0].strike == result2[0].strike
