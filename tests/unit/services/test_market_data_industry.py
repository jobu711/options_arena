"""Unit tests for industry extraction in MarketDataService.fetch_ticker_info.

Tests cover:
- Industry field populated from yfinance info dict
- Industry defaults to 'Unknown' when yfinance info lacks the key
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.market_data import TickerInfo
from options_arena.services.cache import ServiceCache
from options_arena.services.market_data import MarketDataService
from options_arena.services.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_market_data.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> ServiceConfig:
    """Default ServiceConfig for tests."""
    return ServiceConfig()


@pytest.fixture
def cache(config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache for fast unit tests."""
    return ServiceCache(config, db_path=None, max_size=100)


@pytest.fixture
def limiter() -> RateLimiter:
    """Rate limiter with high throughput for tests."""
    return RateLimiter(rate=1000.0, max_concurrent=100)


@pytest.fixture
def service(config: ServiceConfig, cache: ServiceCache, limiter: RateLimiter) -> MarketDataService:
    """MarketDataService wired with test dependencies."""
    return MarketDataService(config=config, cache=cache, limiter=limiter)


def _make_info_dict(**overrides: float | int | str | None) -> dict[str, Any]:
    """Build a yfinance-style info dict with sensible defaults."""
    base: dict[str, Any] = {
        "shortName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "marketCap": 3_000_000_000_000,
        "currentPrice": 185.50,
        "fiftyTwoWeekHigh": 200.0,
        "fiftyTwoWeekLow": 140.0,
        "dividendYield": 0.005,
        "trailingAnnualDividendYield": 0.0048,
        "dividendRate": 0.96,
        "trailingAnnualDividendRate": 0.92,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestFetchTickerInfoIndustry
# ---------------------------------------------------------------------------


class TestFetchTickerInfoIndustry:
    """Tests for industry extraction in fetch_ticker_info."""

    async def test_extracts_industry_from_yfinance(self, service: MarketDataService) -> None:
        """Verify fetch_ticker_info populates industry from yfinance info dict."""
        info = _make_info_dict(industry="Consumer Electronics")
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series(dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ticker_info("AAPL")

        assert isinstance(result, TickerInfo)
        assert result.industry == "Consumer Electronics"

    async def test_industry_defaults_when_missing(self, service: MarketDataService) -> None:
        """Verify industry='Unknown' when yfinance info lacks 'industry' key."""
        info = _make_info_dict()
        # Remove the industry key to simulate missing data
        info.pop("industry", None)
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series(dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ticker_info("AAPL")

        assert isinstance(result, TickerInfo)
        assert result.industry == "Unknown"
