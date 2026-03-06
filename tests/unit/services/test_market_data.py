"""Tests for MarketDataService — OHLCV, quotes, ticker info, dividend waterfall."""

import logging
from datetime import UTC, date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import DividendSource, MarketCapTier
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.services.cache import ServiceCache
from options_arena.services.market_data import (
    MarketDataService,
    _classify_market_cap,
    _extract_dividend_yield,
)
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import (
    DataSourceUnavailableError,
    InsufficientDataError,
    TickerNotFoundError,
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
    return ServiceCache(config, db_path=None, max_size=100)


@pytest.fixture
def limiter() -> RateLimiter:
    """Rate limiter with high throughput for tests."""
    return RateLimiter(rate=1000.0, max_concurrent=100)


@pytest.fixture
def service(config: ServiceConfig, cache: ServiceCache, limiter: RateLimiter) -> MarketDataService:
    """MarketDataService wired with test dependencies."""
    return MarketDataService(config=config, cache=cache, limiter=limiter)


def _make_ohlcv_df(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    """Build a yfinance-style OHLCV DataFrame with DatetimeIndex."""
    df = pd.DataFrame(rows)
    df.index = pd.DatetimeIndex(df.pop("Date"))
    return df


def _make_info_dict(**overrides: float | int | str | None) -> dict[str, Any]:
    """Build a yfinance-style info dict with sensible defaults."""
    base: dict[str, Any] = {
        "shortName": "Apple Inc.",
        "sector": "Technology",
        "marketCap": 3_000_000_000_000,
        "currentPrice": 185.50,
        "fiftyTwoWeekHigh": 200.0,
        "fiftyTwoWeekLow": 140.0,
        "dividendYield": 0.005,
        "trailingAnnualDividendYield": 0.0048,
        "dividendRate": 0.96,
        "trailingAnnualDividendRate": 0.92,
        "bid": 185.40,
        "ask": 185.60,
        "volume": 50_000_000,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestFetchOHLCV
# ---------------------------------------------------------------------------


class TestFetchOHLCV:
    """Tests for MarketDataService.fetch_ohlcv."""

    async def test_happy_path(self, service: MarketDataService) -> None:
        """Successful fetch returns sorted list[OHLCV] with correct Decimal values."""
        df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-02",
                    "Open": 150.0,
                    "High": 155.0,
                    "Low": 149.0,
                    "Close": 154.0,
                    "Volume": 1000000,
                },
                {
                    "Date": "2025-01-03",
                    "Open": 154.0,
                    "High": 158.0,
                    "Low": 153.0,
                    "Close": 157.0,
                    "Volume": 1200000,
                },
            ]
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ohlcv("AAPL", period="1y")

        assert len(result) == 2
        assert all(isinstance(r, OHLCV) for r in result)
        assert result[0].ticker == "AAPL"
        assert result[0].open == Decimal("150.0")
        assert result[0].close == Decimal("154.0")
        assert result[0].volume == 1000000
        # Sorted ascending by date
        assert result[0].date < result[1].date

    async def test_empty_dataframe_raises_insufficient_data(
        self, service: MarketDataService
    ) -> None:
        """Empty DataFrame from yfinance raises InsufficientDataError."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(InsufficientDataError, match="no OHLCV data"):
                await service.fetch_ohlcv("BADTICKER")

    async def test_sorted_by_date_ascending(self, service: MarketDataService) -> None:
        """OHLCV records are sorted by date ascending regardless of input order."""
        df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-05",
                    "Open": 160.0,
                    "High": 165.0,
                    "Low": 159.0,
                    "Close": 164.0,
                    "Volume": 800000,
                },
                {
                    "Date": "2025-01-02",
                    "Open": 150.0,
                    "High": 155.0,
                    "Low": 149.0,
                    "Close": 154.0,
                    "Volume": 1000000,
                },
            ]
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ohlcv("AAPL")

        assert result[0].date == date(2025, 1, 2)
        assert result[1].date == date(2025, 1, 5)

    async def test_decimal_precision_preserved(self, service: MarketDataService) -> None:
        """Prices are converted to Decimal via string, not float."""
        df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-02",
                    "Open": 1.05,
                    "High": 1.10,
                    "Low": 1.00,
                    "Close": 1.05,
                    "Volume": 500,
                },
            ]
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ohlcv("CHEAP")

        assert isinstance(result[0].open, Decimal)
        # Verify it did not go through float imprecision
        assert result[0].open == Decimal("1.05")

    async def test_invalid_candle_skipped_gracefully(self, service: MarketDataService) -> None:
        """Bad candle (open > high) is skipped, valid candles retained."""
        df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-02",
                    "Open": 150.0,
                    "High": 155.0,
                    "Low": 149.0,
                    "Close": 154.0,
                    "Volume": 1000000,
                },
                {
                    "Date": "2025-01-03",
                    "Open": 999.0,  # open > high — invalid candle
                    "High": 158.0,
                    "Low": 153.0,
                    "Close": 157.0,
                    "Volume": 1200000,
                },
            ]
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ohlcv("BADCANDLE", period="1y")

        # Only the valid candle should be retained
        assert len(result) == 1
        assert result[0].open == Decimal("150.0")

    async def test_all_candles_invalid_raises(self, service: MarketDataService) -> None:
        """When all candles fail validation, raises InsufficientDataError."""
        df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-02",
                    "Open": 999.0,  # open > high
                    "High": 155.0,
                    "Low": 149.0,
                    "Close": 154.0,
                    "Volume": 1000000,
                },
            ]
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(InsufficientDataError, match="invalid prices"):
                await service.fetch_ohlcv("ALLINVALID")

    async def test_cache_hit_skips_yfinance_call(self, service: MarketDataService) -> None:
        """Second call returns from cache without calling yfinance again."""
        df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-02",
                    "Open": 150.0,
                    "High": 155.0,
                    "Low": 149.0,
                    "Close": 154.0,
                    "Volume": 1000000,
                },
            ]
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker

            # First call — fetches from yfinance
            first = await service.fetch_ohlcv("AAPL")
            assert mock_yf.Ticker.call_count == 1
            assert len(first) == 1

            # Second call — should come from cache
            second = await service.fetch_ohlcv("AAPL")
            # Ticker should NOT be called again
            assert mock_yf.Ticker.call_count == 1

        assert len(second) == 1
        assert second[0].close == Decimal("154.0")


# ---------------------------------------------------------------------------
# TestFetchQuote
# ---------------------------------------------------------------------------


class TestFetchQuote:
    """Tests for MarketDataService.fetch_quote."""

    async def test_happy_path(self, service: MarketDataService) -> None:
        """Successful fetch returns a Quote with correct fields."""
        info = _make_info_dict()
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_quote("AAPL")

        assert isinstance(result, Quote)
        assert result.ticker == "AAPL"
        assert result.price == Decimal("185.5")
        assert result.bid == Decimal("185.4")
        assert result.ask == Decimal("185.6")
        assert result.volume == 50_000_000

    async def test_utc_timestamp(self, service: MarketDataService) -> None:
        """Quote timestamp is UTC-aware."""
        info = _make_info_dict()
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_quote("AAPL")

        assert result.timestamp.tzinfo is not None
        assert result.timestamp.tzinfo == UTC

    async def test_no_price_raises_ticker_not_found(self, service: MarketDataService) -> None:
        """When no price data exists, raises TickerNotFoundError."""
        info: dict[str, Any] = {"shortName": "Unknown"}
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(TickerNotFoundError, match="invalid price data"):
                await service.fetch_quote("INVALID")

    async def test_fetch_quote_rejects_none_price(self, service: MarketDataService) -> None:
        """When yfinance returns None for currentPrice, raises TickerNotFoundError."""
        info = _make_info_dict(currentPrice=None, regularMarketPrice=None)
        # Remove keys that fall back to None via `or` chain
        info.pop("currentPrice", None)
        info.pop("regularMarketPrice", None)
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(TickerNotFoundError, match="invalid price data"):
                await service.fetch_quote("NONEPRICE")

    async def test_fetch_quote_rejects_zero_price(self, service: MarketDataService) -> None:
        """When yfinance returns 0.0 for price, raises TickerNotFoundError.

        Note: ``currentPrice=0.0`` is falsy so the ``or`` falls through to
        ``regularMarketPrice``. Setting both to ``0.0`` ensures the zero
        reaches ``safe_decimal`` and the ``<= Decimal("0")`` guard fires.
        """
        info = _make_info_dict(currentPrice=0.0, regularMarketPrice=0.0)
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(TickerNotFoundError, match="invalid price data"):
                await service.fetch_quote("ZEROPRICE")

    async def test_fetch_quote_rejects_negative_price(self, service: MarketDataService) -> None:
        """When yfinance returns a negative price, raises TickerNotFoundError."""
        info = _make_info_dict(currentPrice=-5.0)
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(TickerNotFoundError, match="invalid price data"):
                await service.fetch_quote("NEGPRICE")

    async def test_fetch_quote_allows_zero_bid_ask(self, service: MarketDataService) -> None:
        """Zero bid/ask is legitimate for illiquid contracts — should NOT raise."""
        info = _make_info_dict(bid=0.0, ask=0.0)
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_quote("ILLIQUID")

        assert result.bid == Decimal("0")
        assert result.ask == Decimal("0")
        assert result.price == Decimal("185.5")

    async def test_fetch_quote_valid_price_succeeds(self, service: MarketDataService) -> None:
        """Positive price produces a valid Quote with correct fields."""
        info = _make_info_dict(currentPrice=42.50, bid=42.40, ask=42.60, volume=100_000)
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_quote("GOOD")

        assert isinstance(result, Quote)
        assert result.price == Decimal("42.5")
        assert result.bid == Decimal("42.4")
        assert result.ask == Decimal("42.6")
        assert result.volume == 100_000


# ---------------------------------------------------------------------------
# TestFetchTickerInfo
# ---------------------------------------------------------------------------


class TestFetchTickerInfo:
    """Tests for MarketDataService.fetch_ticker_info."""

    async def test_happy_path(self, service: MarketDataService) -> None:
        """Full ticker info with dividend data and market cap tier."""
        info = _make_info_dict()
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series([0.24, 0.24, 0.24, 0.24], dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ticker_info("AAPL")

        assert isinstance(result, TickerInfo)
        assert result.ticker == "AAPL"
        assert result.company_name == "Apple Inc."
        assert result.sector == "Technology"
        assert result.market_cap == 3_000_000_000_000
        assert result.market_cap_tier == MarketCapTier.MEGA
        assert result.dividend_yield == pytest.approx(0.005)
        assert result.dividend_source == DividendSource.FORWARD
        assert result.dividend_rate == pytest.approx(0.96)
        assert result.trailing_dividend_rate == pytest.approx(0.92)
        assert result.current_price == Decimal("185.5")

    async def test_fetch_ticker_info_rejects_none_price(self, service: MarketDataService) -> None:
        """When yfinance returns None for currentPrice and previousClose, raises."""
        info: dict[str, Any] = {
            "shortName": "Ghost Corp",
            "sector": "Unknown",
            "marketCap": 1_000_000,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series(dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(TickerNotFoundError, match="invalid current price"):
                await service.fetch_ticker_info("GHOST")

    async def test_fetch_ticker_info_rejects_negative_price(
        self, service: MarketDataService
    ) -> None:
        """When yfinance returns a negative price, raises TickerNotFoundError."""
        info = _make_info_dict(currentPrice=-10.0)
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series(dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(TickerNotFoundError, match="invalid current price"):
                await service.fetch_ticker_info("NEGPRICE")

    async def test_fetch_ticker_info_rejects_zero_price(self, service: MarketDataService) -> None:
        """When yfinance returns 0.0 for currentPrice, raises TickerNotFoundError.

        ``fetch_ticker_info`` uses ``currentPrice or previousClose``. Setting both
        to ``0.0`` ensures the zero reaches ``safe_decimal`` and the guard fires.
        """
        info = _make_info_dict(currentPrice=0.0, previousClose=0.0)
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series(dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(TickerNotFoundError, match="invalid current price"):
                await service.fetch_ticker_info("ZEROTICKER")


# ---------------------------------------------------------------------------
# TestShortInterestExtraction
# ---------------------------------------------------------------------------


class TestShortInterestExtraction:
    """Tests for short interest field extraction in fetch_ticker_info (#319)."""

    async def test_short_ratio_extracted(self, service: MarketDataService) -> None:
        """Short interest fields are extracted from yfinance info dict."""
        info = _make_info_dict(shortRatio=3.5, shortPercentOfFloat=0.12)
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series([0.24, 0.24], dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ticker_info("GME")

        assert result.short_ratio == pytest.approx(3.5)
        assert result.short_pct_of_float == pytest.approx(0.12)

    async def test_missing_short_ratio_returns_none(self, service: MarketDataService) -> None:
        """When yfinance info has no shortRatio/shortPercentOfFloat, fields are None."""
        info = _make_info_dict()
        # Ensure the keys are absent (not just None)
        info.pop("shortRatio", None)
        info.pop("shortPercentOfFloat", None)
        mock_ticker = MagicMock()
        mock_ticker.info = info
        mock_ticker.get_dividends.return_value = pd.Series([0.24, 0.24], dtype=float)

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_ticker_info("AAPL")

        assert result.short_ratio is None
        assert result.short_pct_of_float is None


# ---------------------------------------------------------------------------
# TestDividendWaterfall
# ---------------------------------------------------------------------------


class TestDividendWaterfall:
    """Tests for the 3-tier dividend yield extraction waterfall."""

    def test_tier1_forward_yield(self) -> None:
        """Tier 1: dividendYield present -> FORWARD source."""
        info = {"dividendYield": 0.005, "dividendRate": 0.96}
        result = _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("185.50"))
        yield_val, source, _rate, _trailing_rate = result

        assert yield_val == pytest.approx(0.005)
        assert source == DividendSource.FORWARD

    def test_tier2_trailing_yield(self) -> None:
        """Tier 2: dividendYield None, trailingAnnualDividendYield present -> TRAILING."""
        info = {
            "dividendYield": None,
            "trailingAnnualDividendYield": 0.0048,
            "trailingAnnualDividendRate": 0.89,
        }
        result = _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("185.50"))
        yield_val, source, _, _trailing_rate = result

        assert yield_val == pytest.approx(0.0048)
        assert source == DividendSource.TRAILING

    def test_tier3_computed_from_dividends(self) -> None:
        """Tier 3: both yields None, dividends_series has payments -> COMPUTED."""
        info: dict[str, Any] = {"dividendYield": None, "trailingAnnualDividendYield": None}
        dividends = pd.Series([0.50, 0.50, 0.50, 0.50], dtype=float)
        result = _extract_dividend_yield(info, dividends, Decimal("100.00"))
        yield_val, source, _, _ = result

        assert yield_val == pytest.approx(2.0 / 100.0)  # 0.02
        assert source == DividendSource.COMPUTED

    def test_tier4_no_data(self) -> None:
        """Tier 4: all None/empty -> (0.0, NONE)."""
        info: dict[str, Any] = {"dividendYield": None, "trailingAnnualDividendYield": None}
        result = _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("185.50"))
        yield_val, source, _, _ = result

        assert yield_val == 0.0
        assert source == DividendSource.NONE

    def test_zero_is_valid_does_not_fall_through(self) -> None:
        """CRITICAL: 0.0 is valid data (growth stocks), does NOT fall through to tier 2."""
        info: dict[str, Any] = {
            "dividendYield": 0.0,
            "trailingAnnualDividendYield": 0.005,
        }
        result = _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("100.00"))
        yield_val, source, _, _ = result

        assert yield_val == 0.0
        assert source == DividendSource.FORWARD  # NOT TRAILING

    def test_audit_fields_populated(self) -> None:
        """Audit fields dividend_rate and trailing_dividend_rate are extracted."""
        info: dict[str, Any] = {
            "dividendYield": 0.005,
            "dividendRate": 0.96,
            "trailingAnnualDividendRate": 0.89,
        }
        result = _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("185.50"))
        _, _, rate, trailing_rate = result

        assert rate == pytest.approx(0.96)
        assert trailing_rate == pytest.approx(0.89)

    def test_missing_keys_return_none_audit_fields(self) -> None:
        """When audit keys are missing, audit fields are None."""
        info: dict[str, Any] = {"dividendYield": 0.005}
        result = _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("185.50"))
        _, _, rate, trailing_rate = result

        assert rate is None
        assert trailing_rate is None


# ---------------------------------------------------------------------------
# TestCrossValidation
# ---------------------------------------------------------------------------


class TestCrossValidation:
    """Tests for dividend cross-validation warning logic."""

    def test_divergence_over_20pct_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """When yield and dollar-rate diverge by >20%, a WARNING is logged."""
        # dividendYield = 0.005, dividendRate = 3.0
        # implied_yield = 3.0 / 185.50 = ~0.01617 (huge divergence from 0.005)
        info: dict[str, Any] = {
            "dividendYield": 0.005,
            "dividendRate": 3.0,
        }
        with caplog.at_level(logging.WARNING, logger="options_arena.services.market_data"):
            _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("185.50"))

        warning_messages = [r for r in caplog.records if "Dividend divergence" in r.message]
        assert len(warning_messages) == 1

    def test_no_divergence_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """When yield and dollar-rate are consistent, no WARNING is logged."""
        # dividendYield = 0.005, dividendRate = 0.9275 (implied = 0.9275/185.5 = 0.005)
        info: dict[str, Any] = {
            "dividendYield": 0.005,
            "dividendRate": 0.9275,
        }
        with caplog.at_level(logging.WARNING, logger="options_arena.services.market_data"):
            _extract_dividend_yield(info, pd.Series(dtype=float), Decimal("185.50"))

        warning_messages = [r for r in caplog.records if "Dividend divergence" in r.message]
        assert len(warning_messages) == 0


# ---------------------------------------------------------------------------
# TestMarketCapTier
# ---------------------------------------------------------------------------


class TestMarketCapTier:
    """Tests for _classify_market_cap."""

    def test_none_returns_none(self) -> None:
        assert _classify_market_cap(None) is None

    def test_mega_at_boundary(self) -> None:
        assert _classify_market_cap(200_000_000_000) == MarketCapTier.MEGA

    def test_mega_above_boundary(self) -> None:
        assert _classify_market_cap(3_000_000_000_000) == MarketCapTier.MEGA

    def test_large_at_boundary(self) -> None:
        assert _classify_market_cap(10_000_000_000) == MarketCapTier.LARGE

    def test_large_below_mega(self) -> None:
        assert _classify_market_cap(199_999_999_999) == MarketCapTier.LARGE

    def test_mid_at_boundary(self) -> None:
        assert _classify_market_cap(2_000_000_000) == MarketCapTier.MID

    def test_small_at_boundary(self) -> None:
        assert _classify_market_cap(300_000_000) == MarketCapTier.SMALL

    def test_micro_below_small(self) -> None:
        assert _classify_market_cap(299_999_999) == MarketCapTier.MICRO

    def test_micro_zero(self) -> None:
        assert _classify_market_cap(0) == MarketCapTier.MICRO


# ---------------------------------------------------------------------------
# TestBatchOHLCV
# ---------------------------------------------------------------------------


class TestBatchOHLCV:
    """Tests for MarketDataService.fetch_batch_ohlcv."""

    async def test_mixed_success_and_failure(self, service: MarketDataService) -> None:
        """3 tickers: 2 succeed, 1 fails -> BatchOHLCVResult with 2 ok + 1 error."""
        good_df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-02",
                    "Open": 150.0,
                    "High": 155.0,
                    "Low": 149.0,
                    "Close": 154.0,
                    "Volume": 1000000,
                },
            ]
        )

        def make_mock_ticker(symbol: str) -> MagicMock:
            mock = MagicMock()
            if symbol == "BAD":
                mock.history.side_effect = Exception("Network error")
            else:
                mock.history.return_value = good_df.copy()
            return mock

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.side_effect = lambda s: make_mock_ticker(s)
            result = await service.fetch_batch_ohlcv(["AAPL", "BAD", "MSFT"])

        assert len(result.succeeded()) == 2
        assert len(result.failed()) == 1

        aapl = result.get("AAPL")
        assert aapl is not None and aapl.ok
        assert aapl.data is not None and len(aapl.data) == 1

        msft = result.get("MSFT")
        assert msft is not None and msft.ok
        assert msft.data is not None and len(msft.data) == 1

        bad = result.get("BAD")
        assert bad is not None and not bad.ok
        assert bad.error is not None

    async def test_all_succeed(self, service: MarketDataService) -> None:
        """When all tickers succeed, all results are ok."""
        df = _make_ohlcv_df(
            [
                {
                    "Date": "2025-01-02",
                    "Open": 100.0,
                    "High": 105.0,
                    "Low": 99.0,
                    "Close": 104.0,
                    "Volume": 500000,
                },
            ]
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            result = await service.fetch_batch_ohlcv(["SPY", "QQQ"])

        assert all(r.ok for r in result.results)
        assert len(result.results) == 2


# ---------------------------------------------------------------------------
# TestTimeout
# ---------------------------------------------------------------------------


class TestTimeout:
    """Tests for yfinance timeout handling."""

    async def test_timeout_raises_data_source_unavailable(
        self,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When yfinance hangs beyond timeout, DataSourceUnavailableError is raised."""
        # Use a very short timeout
        config = ServiceConfig(yfinance_timeout=0.01)
        svc = MarketDataService(config=config, cache=cache, limiter=limiter)

        def slow_history(**_kwargs: object) -> pd.DataFrame:
            import time

            time.sleep(5.0)
            return pd.DataFrame()

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = slow_history

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(DataSourceUnavailableError, match="timeout"):
                await svc.fetch_ohlcv("SLOW")

    async def test_generic_exception_raises_data_source_unavailable(
        self, service: MarketDataService
    ) -> None:
        """Non-timeout exceptions from yfinance are wrapped as DataSourceUnavailableError."""
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = RuntimeError("connection reset")

        with patch("options_arena.services.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            with pytest.raises(DataSourceUnavailableError, match="connection reset"):
                await service.fetch_ohlcv("ERR")
