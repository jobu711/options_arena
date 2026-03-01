"""Tests for UniverseService ETF detection and sector filtering helpers.

Covers:
- ETF detection with mocked yfinance (happy path, partial failure, all fail)
- ETF cache hit / miss
- Sector filtering with various combinations
- Empty sectors passthrough
- build_sector_map with matching and non-matching sector strings
- _resolve_sector edge cases
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import GICSSector
from options_arena.services.cache import TTL_REFERENCE, ServiceCache
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import (
    _CACHE_KEY_ETFS,
    _ETF_SEED_LIST,
    SP500Constituent,
    UniverseService,
    _resolve_sector,
    build_sector_map,
    filter_by_sectors,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig for tests."""
    return ServiceConfig()


@pytest.fixture
def cache(config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache for fast unit tests."""
    return ServiceCache(config, db_path=None)


@pytest.fixture
def limiter() -> RateLimiter:
    """Rate limiter for tests."""
    return RateLimiter(rate=100.0, max_concurrent=10)


@pytest.fixture
def service(config: ServiceConfig, cache: ServiceCache, limiter: RateLimiter) -> UniverseService:
    """UniverseService instance with mocked dependencies."""
    return UniverseService(config=config, cache=cache, limiter=limiter)


# ---------------------------------------------------------------------------
# build_sector_map — canonical sectors
# ---------------------------------------------------------------------------


def test_build_sector_map_canonical_sectors() -> None:
    """build_sector_map resolves canonical GICS sector names correctly."""
    constituents = [
        SP500Constituent(ticker="AAPL", sector="Information Technology"),
        SP500Constituent(ticker="JPM", sector="Financials"),
        SP500Constituent(ticker="XOM", sector="Energy"),
    ]
    result = build_sector_map(constituents)
    assert result == {
        "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
        "JPM": GICSSector.FINANCIALS,
        "XOM": GICSSector.ENERGY,
    }


def test_build_sector_map_all_eleven_sectors() -> None:
    """build_sector_map handles all 11 canonical GICS sectors."""
    sectors = [
        ("A", "Communication Services"),
        ("B", "Consumer Discretionary"),
        ("C", "Consumer Staples"),
        ("D", "Energy"),
        ("E", "Financials"),
        ("F", "Health Care"),
        ("G", "Industrials"),
        ("H", "Information Technology"),
        ("I", "Materials"),
        ("J", "Real Estate"),
        ("K", "Utilities"),
    ]
    constituents = [SP500Constituent(ticker=t, sector=s) for t, s in sectors]
    result = build_sector_map(constituents)
    assert len(result) == 11
    assert result["A"] == GICSSector.COMMUNICATION_SERVICES
    assert result["K"] == GICSSector.UTILITIES


def test_build_sector_map_alias_fallback() -> None:
    """build_sector_map uses SECTOR_ALIASES for non-canonical sector strings."""
    constituents = [
        SP500Constituent(ticker="AAPL", sector="tech"),
        SP500Constituent(ticker="UNH", sector="healthcare"),
    ]
    result = build_sector_map(constituents)
    assert result["AAPL"] == GICSSector.INFORMATION_TECHNOLOGY
    assert result["UNH"] == GICSSector.HEALTH_CARE


def test_build_sector_map_unrecognized_sector_skipped() -> None:
    """build_sector_map skips tickers with unrecognised sector strings."""
    constituents = [
        SP500Constituent(ticker="AAPL", sector="Information Technology"),
        SP500Constituent(ticker="FAKE", sector="Underwater Basket Weaving"),
    ]
    result = build_sector_map(constituents)
    assert "AAPL" in result
    assert "FAKE" not in result
    assert len(result) == 1


def test_build_sector_map_empty_input() -> None:
    """build_sector_map returns empty dict for empty input."""
    result = build_sector_map([])
    assert result == {}


def test_build_sector_map_whitespace_handling() -> None:
    """build_sector_map handles sector strings with leading/trailing whitespace."""
    constituents = [
        SP500Constituent(ticker="AAPL", sector="  Information Technology  "),
        SP500Constituent(ticker="JPM", sector="  Financials  "),
    ]
    result = build_sector_map(constituents)
    assert result["AAPL"] == GICSSector.INFORMATION_TECHNOLOGY
    assert result["JPM"] == GICSSector.FINANCIALS


# ---------------------------------------------------------------------------
# _resolve_sector — direct tests
# ---------------------------------------------------------------------------


def test_resolve_sector_canonical() -> None:
    """_resolve_sector resolves canonical GICS sector names."""
    assert _resolve_sector("Energy") == GICSSector.ENERGY
    assert _resolve_sector("Health Care") == GICSSector.HEALTH_CARE


def test_resolve_sector_alias() -> None:
    """_resolve_sector falls back to SECTOR_ALIASES for short names."""
    assert _resolve_sector("tech") == GICSSector.INFORMATION_TECHNOLOGY
    assert _resolve_sector("telecom") == GICSSector.COMMUNICATION_SERVICES


def test_resolve_sector_unknown() -> None:
    """_resolve_sector returns None for unknown sector strings."""
    assert _resolve_sector("Unknown Sector") is None
    assert _resolve_sector("") is None


# ---------------------------------------------------------------------------
# filter_by_sectors — basic filtering
# ---------------------------------------------------------------------------


def test_filter_by_sectors_single_sector() -> None:
    """filter_by_sectors filters to a single sector."""
    sp500_map = {
        "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
        "MSFT": GICSSector.INFORMATION_TECHNOLOGY,
        "JPM": GICSSector.FINANCIALS,
        "XOM": GICSSector.ENERGY,
    }
    result = filter_by_sectors(
        tickers=["AAPL", "MSFT", "JPM", "XOM"],
        sectors=[GICSSector.INFORMATION_TECHNOLOGY],
        sp500_map=sp500_map,
    )
    assert result == ["AAPL", "MSFT"]


def test_filter_by_sectors_multiple_sectors_or_logic() -> None:
    """filter_by_sectors with multiple sectors uses OR logic."""
    sp500_map = {
        "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
        "JPM": GICSSector.FINANCIALS,
        "XOM": GICSSector.ENERGY,
        "NEE": GICSSector.UTILITIES,
    }
    result = filter_by_sectors(
        tickers=["AAPL", "JPM", "XOM", "NEE"],
        sectors=[GICSSector.FINANCIALS, GICSSector.ENERGY],
        sp500_map=sp500_map,
    )
    assert result == ["JPM", "XOM"]


def test_filter_by_sectors_empty_sectors_passthrough() -> None:
    """filter_by_sectors with empty sectors list returns all tickers unchanged."""
    sp500_map = {
        "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
        "JPM": GICSSector.FINANCIALS,
    }
    tickers = ["AAPL", "JPM", "SPY"]
    result = filter_by_sectors(tickers=tickers, sectors=[], sp500_map=sp500_map)
    assert result == tickers


def test_filter_by_sectors_preserves_order() -> None:
    """filter_by_sectors preserves input order of tickers."""
    sp500_map = {
        "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
        "MSFT": GICSSector.INFORMATION_TECHNOLOGY,
        "GOOG": GICSSector.COMMUNICATION_SERVICES,
    }
    result = filter_by_sectors(
        tickers=["GOOG", "AAPL", "MSFT"],
        sectors=[GICSSector.INFORMATION_TECHNOLOGY],
        sp500_map=sp500_map,
    )
    assert result == ["AAPL", "MSFT"]


def test_filter_by_sectors_ticker_not_in_map_excluded() -> None:
    """filter_by_sectors excludes tickers not present in sp500_map when filtering."""
    sp500_map = {
        "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
    }
    result = filter_by_sectors(
        tickers=["AAPL", "SPY", "UNKNOWN"],
        sectors=[GICSSector.INFORMATION_TECHNOLOGY],
        sp500_map=sp500_map,
    )
    assert result == ["AAPL"]


def test_filter_by_sectors_no_matches() -> None:
    """filter_by_sectors returns empty list when no tickers match."""
    sp500_map = {
        "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
        "MSFT": GICSSector.INFORMATION_TECHNOLOGY,
    }
    result = filter_by_sectors(
        tickers=["AAPL", "MSFT"],
        sectors=[GICSSector.ENERGY],
        sp500_map=sp500_map,
    )
    assert result == []


def test_filter_by_sectors_empty_tickers() -> None:
    """filter_by_sectors with empty ticker list returns empty list."""
    sp500_map = {"AAPL": GICSSector.INFORMATION_TECHNOLOGY}
    result = filter_by_sectors(
        tickers=[],
        sectors=[GICSSector.INFORMATION_TECHNOLOGY],
        sp500_map=sp500_map,
    )
    assert result == []


# ---------------------------------------------------------------------------
# fetch_etf_tickers — cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_etf_tickers_cache_hit(service: UniverseService, cache: ServiceCache) -> None:
    """Pre-populated ETF cache returns data without yfinance calls."""
    cached_etfs = ["GLD", "QQQ", "SPY"]
    await cache.set(
        _CACHE_KEY_ETFS,
        json.dumps(cached_etfs).encode(),
        ttl=TTL_REFERENCE,
    )

    with patch.object(service, "fetch_optionable_tickers", new_callable=AsyncMock) as mock_fetch:
        result = await service.fetch_etf_tickers()

    mock_fetch.assert_not_called()
    assert result == cached_etfs


# ---------------------------------------------------------------------------
# fetch_etf_tickers — happy path (cache miss)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_etf_tickers_happy_path(service: UniverseService) -> None:
    """ETF detection cross-references seed list with CBOE and confirms via yfinance."""
    # Only include a few seed tickers in the CBOE list to keep test fast
    cboe_tickers = ["AAPL", "MSFT", "SPY", "QQQ", "IWM", "GOOG"]

    with (
        patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=cboe_tickers,
        ),
        patch.object(service, "_check_etf", new_callable=AsyncMock) as mock_check,
    ):
        # SPY, QQQ, IWM are seed tickers in CBOE → check them
        # _check_etf returns True for all
        mock_check.return_value = True
        result = await service.fetch_etf_tickers()

    # Should contain the seed tickers that are also in CBOE
    assert "SPY" in result
    assert "QQQ" in result
    assert "IWM" in result
    # Non-ETF equities should not be present (not in seed list)
    assert "AAPL" not in result
    assert "MSFT" not in result
    assert sorted(result) == result  # sorted


@pytest.mark.asyncio
async def test_fetch_etf_tickers_partial_failure(service: UniverseService) -> None:
    """ETF detection includes seed tickers even when yfinance check fails."""
    cboe_tickers = ["SPY", "QQQ", "IWM"]

    async def mock_check_etf(ticker: str) -> bool:
        if ticker == "QQQ":
            raise TimeoutError("yfinance timeout")
        return True

    with (
        patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=cboe_tickers,
        ),
        patch.object(service, "_check_etf", side_effect=mock_check_etf),
    ):
        result = await service.fetch_etf_tickers()

    # QQQ should still be included despite failure (seed list is curated)
    assert "SPY" in result
    assert "QQQ" in result
    assert "IWM" in result


@pytest.mark.asyncio
async def test_fetch_etf_tickers_all_checks_fail(service: UniverseService) -> None:
    """ETF detection includes all seed tickers when all yfinance checks fail."""
    cboe_tickers = ["SPY", "QQQ"]

    with (
        patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=cboe_tickers,
        ),
        patch.object(
            service,
            "_check_etf",
            new_callable=AsyncMock,
            side_effect=Exception("yfinance down"),
        ),
    ):
        result = await service.fetch_etf_tickers()

    assert "SPY" in result
    assert "QQQ" in result


@pytest.mark.asyncio
async def test_fetch_etf_tickers_non_etf_excluded(service: UniverseService) -> None:
    """Seed tickers that yfinance confirms are NOT ETFs are excluded."""
    cboe_tickers = ["SPY", "QQQ"]

    async def mock_check_etf(ticker: str) -> bool:
        # SPY is ETF, QQQ is not (hypothetical)
        return ticker == "SPY"

    with (
        patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=cboe_tickers,
        ),
        patch.object(service, "_check_etf", side_effect=mock_check_etf),
    ):
        result = await service.fetch_etf_tickers()

    assert "SPY" in result
    assert "QQQ" not in result


@pytest.mark.asyncio
async def test_fetch_etf_tickers_no_overlap_with_cboe(service: UniverseService) -> None:
    """When no seed tickers are in CBOE list, returns empty and caches."""
    cboe_tickers = ["AAPL", "MSFT", "GOOG"]  # No ETFs in seed list

    with patch.object(
        service,
        "fetch_optionable_tickers",
        new_callable=AsyncMock,
        return_value=cboe_tickers,
    ):
        result = await service.fetch_etf_tickers()

    assert result == []


@pytest.mark.asyncio
async def test_fetch_etf_tickers_caches_result(
    service: UniverseService, cache: ServiceCache
) -> None:
    """After a cache miss, ETF tickers are stored in the cache."""
    cboe_tickers = ["SPY", "QQQ"]

    with (
        patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=cboe_tickers,
        ),
        patch.object(service, "_check_etf", new_callable=AsyncMock, return_value=True),
    ):
        await service.fetch_etf_tickers()

    cached = await cache.get(_CACHE_KEY_ETFS)
    assert cached is not None
    cached_tickers = json.loads(cached.decode())
    assert "SPY" in cached_tickers
    assert "QQQ" in cached_tickers


# ---------------------------------------------------------------------------
# _check_etf — private helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_etf_returns_true_for_etf(service: UniverseService) -> None:
    """_check_etf returns True when quoteType is ETF."""
    mock_ticker = MagicMock()
    mock_ticker.info = {"quoteType": "ETF", "shortName": "SPDR S&P 500"}

    with patch("options_arena.services.universe.yf.Ticker", return_value=mock_ticker):
        result = await service._check_etf("SPY")

    assert result is True


@pytest.mark.asyncio
async def test_check_etf_returns_false_for_equity(service: UniverseService) -> None:
    """_check_etf returns False when quoteType is EQUITY."""
    mock_ticker = MagicMock()
    mock_ticker.info = {"quoteType": "EQUITY", "shortName": "Apple Inc."}

    with patch("options_arena.services.universe.yf.Ticker", return_value=mock_ticker):
        result = await service._check_etf("AAPL")

    assert result is False


@pytest.mark.asyncio
async def test_check_etf_returns_false_for_missing_quote_type(
    service: UniverseService,
) -> None:
    """_check_etf returns False when quoteType is missing from info."""
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "Unknown"}

    with patch("options_arena.services.universe.yf.Ticker", return_value=mock_ticker):
        result = await service._check_etf("UNKNOWN")

    assert result is False


# ---------------------------------------------------------------------------
# ETF seed list sanity checks
# ---------------------------------------------------------------------------


def test_etf_seed_list_contains_major_etfs() -> None:
    """ETF seed list contains the most widely-traded ETFs."""
    major_etfs = {"SPY", "QQQ", "IWM", "DIA", "GLD", "TLT", "EEM", "XLF"}
    assert major_etfs <= _ETF_SEED_LIST


def test_etf_seed_list_is_frozenset() -> None:
    """ETF seed list is immutable."""
    assert isinstance(_ETF_SEED_LIST, frozenset)


def test_etf_seed_list_all_uppercase() -> None:
    """All ETF seed tickers are uppercase."""
    for ticker in _ETF_SEED_LIST:
        assert ticker == ticker.upper(), f"Seed ticker {ticker!r} is not uppercase"
