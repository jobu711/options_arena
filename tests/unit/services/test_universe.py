"""Tests for UniverseService — CBOE optionable tickers and S&P 500 constituents."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import MarketCapTier
from options_arena.services.cache import TTL_REFERENCE, ServiceCache
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import (
    _CACHE_KEY_CBOE,
    _CACHE_KEY_SP500,
    SP500_REQUIRED_COLUMNS,
    SP500Constituent,
    UniverseService,
)
from options_arena.utils.exceptions import DataSourceUnavailableError, InsufficientDataError


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig for universe tests."""
    return ServiceConfig()


@pytest.fixture
def cache(config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache for fast unit tests."""
    return ServiceCache(config, db_path=None)


@pytest.fixture
def limiter() -> RateLimiter:
    """Rate limiter for universe tests."""
    return RateLimiter(rate=100.0, max_concurrent=10)


@pytest.fixture
def service(config: ServiceConfig, cache: ServiceCache, limiter: RateLimiter) -> UniverseService:
    """UniverseService instance with mocked dependencies."""
    return UniverseService(config=config, cache=cache, limiter=limiter)


# ---------------------------------------------------------------------------
# S&P 500 — happy path
# ---------------------------------------------------------------------------


def _mock_httpx_response(html: str = "<html></html>") -> MagicMock:
    """Create a mock httpx.Response with the given HTML body."""
    resp = MagicMock()
    resp.text = html
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_sp500_happy_path(service: UniverseService) -> None:
    """Fetch S&P 500 constituents returns list of SP500Constituent models."""
    sectors = [
        "Information Technology",
        "Information Technology",
        "Communication Services",
    ]
    mock_df = pd.DataFrame(
        {
            "Symbol": ["AAPL", "MSFT", "GOOG"],
            "GICS Sector": sectors,
            "Security": ["Apple Inc.", "Microsoft Corp.", "Alphabet Inc."],
        }
    )

    with (
        patch.object(
            service._client,
            "get",
            new_callable=AsyncMock,
            return_value=_mock_httpx_response(),
        ),
        patch(
            "options_arena.services.universe.pd.read_html",
            return_value=[mock_df],
        ),
    ):
        result = await service.fetch_sp500_constituents()

    assert len(result) == 3
    assert all(isinstance(c, SP500Constituent) for c in result)
    by_ticker = {c.ticker: c.sector for c in result}
    assert by_ticker == {
        "AAPL": "Information Technology",
        "MSFT": "Information Technology",
        "GOOG": "Communication Services",
    }


# ---------------------------------------------------------------------------
# S&P 500 — ticker translation (. → -)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sp500_ticker_translation(service: UniverseService) -> None:
    """Wikipedia dot-separated tickers are translated to yfinance dash format."""
    mock_df = pd.DataFrame(
        {
            "Symbol": ["BRK.B", "BF.B", "AAPL"],
            "GICS Sector": ["Financials", "Consumer Staples", "Information Technology"],
        }
    )

    with (
        patch.object(
            service._client,
            "get",
            new_callable=AsyncMock,
            return_value=_mock_httpx_response(),
        ),
        patch(
            "options_arena.services.universe.pd.read_html",
            return_value=[mock_df],
        ),
    ):
        result = await service.fetch_sp500_constituents()

    tickers = {c.ticker for c in result}
    assert "BRK-B" in tickers
    assert "BF-B" in tickers
    assert "AAPL" in tickers
    # Original dot format should NOT be present
    assert "BRK.B" not in tickers
    assert "BF.B" not in tickers


# ---------------------------------------------------------------------------
# S&P 500 — column validation failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sp500_missing_required_column(service: UniverseService) -> None:
    """Missing required columns raise InsufficientDataError."""
    mock_df = pd.DataFrame(
        {
            "Symbol": ["AAPL", "MSFT"],
            "Wrong Column": ["foo", "bar"],
        }
    )

    with (
        patch.object(
            service._client,
            "get",
            new_callable=AsyncMock,
            return_value=_mock_httpx_response(),
        ),
        patch(
            "options_arena.services.universe.pd.read_html",
            return_value=[mock_df],
        ),
        pytest.raises(InsufficientDataError, match="missing columns"),
    ):
        await service.fetch_sp500_constituents()


# ---------------------------------------------------------------------------
# S&P 500 — empty DataFrame
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sp500_empty_dataframe(service: UniverseService) -> None:
    """Empty S&P 500 table raises InsufficientDataError."""
    mock_df = pd.DataFrame(columns=["Symbol", "GICS Sector"])

    with (
        patch.object(
            service._client,
            "get",
            new_callable=AsyncMock,
            return_value=_mock_httpx_response(),
        ),
        patch(
            "options_arena.services.universe.pd.read_html",
            return_value=[mock_df],
        ),
        pytest.raises(InsufficientDataError, match="empty"),
    ):
        await service.fetch_sp500_constituents()


# ---------------------------------------------------------------------------
# S&P 500 — no tables returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sp500_no_tables(service: UniverseService) -> None:
    """No tables found at Wikipedia raises InsufficientDataError."""
    with (
        patch.object(
            service._client,
            "get",
            new_callable=AsyncMock,
            return_value=_mock_httpx_response(),
        ),
        patch(
            "options_arena.services.universe.pd.read_html",
            return_value=[],
        ),
        pytest.raises(InsufficientDataError, match="No tables"),
    ):
        await service.fetch_sp500_constituents()


# ---------------------------------------------------------------------------
# CBOE CSV — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_happy_path(service: UniverseService) -> None:
    """CBOE CSV parsing returns filtered, sorted ticker list."""
    csv_content = "Symbol\nAAPL\nMSFT\nGOOG\nAMZN\n"
    mock_response = MagicMock()
    mock_response.text = csv_content
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(service._client, "get", new_callable=AsyncMock, return_value=mock_response):
        result = await service.fetch_optionable_tickers()

    assert result == ["AAPL", "AMZN", "GOOG", "MSFT"]


# ---------------------------------------------------------------------------
# CBOE — index symbol filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_filters_index_symbols(service: UniverseService) -> None:
    """Index symbols containing ^, $, / are filtered out."""
    csv_content = "Symbol\nAAPL\n^SPX\n$VIX\nSPX/W\nMSFT\n"
    mock_response = MagicMock()
    mock_response.text = csv_content
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(service._client, "get", new_callable=AsyncMock, return_value=mock_response):
        result = await service.fetch_optionable_tickers()

    assert "^SPX" not in result
    assert "$VIX" not in result
    assert "SPX/W" not in result
    assert "AAPL" in result
    assert "MSFT" in result


# ---------------------------------------------------------------------------
# CBOE — whitespace stripping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_strips_whitespace(service: UniverseService) -> None:
    """Tickers with leading/trailing whitespace are properly cleaned."""
    csv_content = "Symbol\n  AAPL  \n  MSFT\nGOOG  \n"
    mock_response = MagicMock()
    mock_response.text = csv_content
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(service._client, "get", new_callable=AsyncMock, return_value=mock_response):
        result = await service.fetch_optionable_tickers()

    assert "AAPL" in result
    assert "MSFT" in result
    assert "GOOG" in result


# ---------------------------------------------------------------------------
# CBOE — deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_deduplication(service: UniverseService) -> None:
    """Duplicate tickers in CBOE CSV are deduplicated."""
    csv_content = "Symbol\nAAPL\nMSFT\nAAPL\nGOOG\nMSFT\n"
    mock_response = MagicMock()
    mock_response.text = csv_content
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(service._client, "get", new_callable=AsyncMock, return_value=mock_response):
        result = await service.fetch_optionable_tickers()

    assert result == ["AAPL", "GOOG", "MSFT"]
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Market cap classification — all tier boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("market_cap", "expected_tier"),
    [
        (200_000_000_000, MarketCapTier.MEGA),  # Exactly 200B
        (300_000_000_000, MarketCapTier.MEGA),  # Above 200B
        (199_999_999_999, MarketCapTier.LARGE),  # Just below 200B
        (10_000_000_000, MarketCapTier.LARGE),  # Exactly 10B
        (9_999_999_999, MarketCapTier.MID),  # Just below 10B
        (2_000_000_000, MarketCapTier.MID),  # Exactly 2B
        (1_999_999_999, MarketCapTier.SMALL),  # Just below 2B
        (300_000_000, MarketCapTier.SMALL),  # Exactly 300M
        (299_999_999, MarketCapTier.MICRO),  # Just below 300M
        (1, MarketCapTier.MICRO),  # Very small
        (0, MarketCapTier.MICRO),  # Zero market cap
    ],
    ids=[
        "200B_mega",
        "300B_mega",
        "below_200B_large",
        "10B_large",
        "below_10B_mid",
        "2B_mid",
        "below_2B_small",
        "300M_small",
        "below_300M_micro",
        "1_dollar_micro",
        "zero_micro",
    ],
)
def test_classify_market_cap_boundaries(
    service: UniverseService,
    market_cap: int,
    expected_tier: MarketCapTier,
) -> None:
    """Market cap classification places values at correct tier boundaries."""
    assert service.classify_market_cap(market_cap) == expected_tier


def test_classify_market_cap_none(service: UniverseService) -> None:
    """None market cap returns None."""
    assert service.classify_market_cap(None) is None


# ---------------------------------------------------------------------------
# Cache hit — CBOE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_cache_hit(service: UniverseService, cache: ServiceCache) -> None:
    """Pre-populated cache returns data without making HTTP call."""
    cached_tickers = ["AAPL", "GOOG", "MSFT"]
    await cache.set(
        _CACHE_KEY_CBOE,
        json.dumps(cached_tickers).encode(),
        ttl=TTL_REFERENCE,
    )

    # Patch the client to ensure it is NOT called
    with patch.object(service._client, "get", new_callable=AsyncMock) as mock_get:
        result = await service.fetch_optionable_tickers()

    mock_get.assert_not_called()
    assert result == cached_tickers


# ---------------------------------------------------------------------------
# Cache hit — S&P 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sp500_cache_hit(service: UniverseService, cache: ServiceCache) -> None:
    """Pre-populated cache returns S&P 500 data without fetching from Wikipedia."""
    cached_constituents = [
        {"ticker": "AAPL", "sector": "Information Technology"},
        {"ticker": "MSFT", "sector": "Information Technology"},
    ]
    await cache.set(
        _CACHE_KEY_SP500,
        json.dumps(cached_constituents).encode(),
        ttl=TTL_REFERENCE,
    )

    with patch("options_arena.services.universe.pd.read_html") as mock_read_html:
        result = await service.fetch_sp500_constituents()

    mock_read_html.assert_not_called()
    assert len(result) == 2
    assert all(isinstance(c, SP500Constituent) for c in result)
    assert result[0].ticker == "AAPL"
    assert result[1].ticker == "MSFT"


# ---------------------------------------------------------------------------
# Cache miss stores result — CBOE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_cache_miss_stores_result(
    service: UniverseService, cache: ServiceCache
) -> None:
    """After a cache miss, fetched CBOE data is stored in the cache."""
    csv_content = "Symbol\nAAPL\nMSFT\n"
    mock_response = MagicMock()
    mock_response.text = csv_content
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(service._client, "get", new_callable=AsyncMock, return_value=mock_response):
        await service.fetch_optionable_tickers()

    # Verify cache was populated
    cached = await cache.get(_CACHE_KEY_CBOE)
    assert cached is not None
    assert json.loads(cached.decode()) == ["AAPL", "MSFT"]


# ---------------------------------------------------------------------------
# CBOE — network failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_network_failure(service: UniverseService) -> None:
    """CBOE network failure raises DataSourceUnavailableError."""
    with (
        patch.object(
            service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ),
        pytest.raises(DataSourceUnavailableError, match="CBOE"),
    ):
        await service.fetch_optionable_tickers()


# ---------------------------------------------------------------------------
# S&P 500 — Wikipedia unreachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sp500_wikipedia_unreachable(service: UniverseService) -> None:
    """Wikipedia network failure raises DataSourceUnavailableError."""
    with (
        patch.object(
            service._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ),
        pytest.raises(DataSourceUnavailableError, match="Wikipedia"),
    ):
        await service.fetch_sp500_constituents()


# ---------------------------------------------------------------------------
# CBOE — case normalization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cboe_case_normalization(service: UniverseService) -> None:
    """Tickers are uppercased regardless of input case."""
    csv_content = "Symbol\naapl\nMsft\ngOOG\n"
    mock_response = MagicMock()
    mock_response.text = csv_content
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(service._client, "get", new_callable=AsyncMock, return_value=mock_response):
        result = await service.fetch_optionable_tickers()

    assert result == ["AAPL", "GOOG", "MSFT"]


# ---------------------------------------------------------------------------
# Required columns constant verification
# ---------------------------------------------------------------------------


def test_sp500_required_columns_constant() -> None:
    """SP500_REQUIRED_COLUMNS contains the expected column names."""
    assert {"Symbol", "GICS Sector"} == SP500_REQUIRED_COLUMNS
