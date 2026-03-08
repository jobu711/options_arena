"""Market data service — OHLCV, quotes, and ticker info from yfinance.

Fetches and normalizes yfinance market data into typed Pydantic models.
Includes the 3-tier dividend yield waterfall (FR-M7.1), MarketCapTier
classification, and cross-validation logic. All yfinance calls are
wrapped with ``asyncio.to_thread`` + ``asyncio.wait_for`` for async safety.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import ValidationError as PydanticValidationError

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import DividendSource, MarketCapTier
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.services.cache import (
    TTL_EARNINGS,
    TTL_FUNDAMENTALS,
    TTL_OHLCV,
    TTL_REFERENCE,
    ServiceCache,
)
from options_arena.services.helpers import fetch_with_retry, safe_decimal, safe_float, safe_int
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import (
    DataFetchError,
    DataSourceUnavailableError,
    InsufficientDataError,
    TickerNotFoundError,
)

logger = logging.getLogger(__name__)

# GICS sector → SPDR sector ETF mapping for regime/macro indicators.
SECTOR_ETF_MAP: dict[str, str] = {
    "Technology": "XLK",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
}


@dataclass
class UniverseData:
    """Reference data for regime/macro indicators.

    Fetched once per scan by ``MarketDataService.fetch_universe_data()``.
    Individual fields are passed to ``indicators/regime.py`` functions — the
    dataclass itself does NOT cross the service boundary into indicators.
    """

    spx_close: pd.Series[float] | None = None
    vix_close: float | None = None
    vix3m_close: float | None = None
    hyg_return_20d: float | None = None
    lqd_return_20d: float | None = None
    spx_return_20d: float | None = None
    sector_etf_returns: dict[str, float | None] = field(default_factory=dict)


class TickerOHLCVResult(BaseModel):
    """Result for a single ticker in a batch OHLCV fetch.

    Exactly one of ``data`` or ``error`` will be populated (never both).
    """

    ticker: str
    data: list[OHLCV] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """``True`` if the fetch succeeded."""
        return self.data is not None


class BatchOHLCVResult(BaseModel):
    """Typed result for a batch OHLCV fetch, replacing ``dict[str, list[OHLCV] | error]``."""

    results: list[TickerOHLCVResult]

    def succeeded(self) -> list[TickerOHLCVResult]:
        """Return only the results that fetched successfully."""
        return [r for r in self.results if r.ok]

    def failed(self) -> list[TickerOHLCVResult]:
        """Return only the results that failed."""
        return [r for r in self.results if not r.ok]

    def get(self, ticker: str) -> TickerOHLCVResult | None:
        """Look up a result by ticker symbol."""
        for r in self.results:
            if r.ticker == ticker:
                return r
        return None


class BatchQuote(BaseModel):
    """A single ticker's daily price snapshot for heatmap display."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    price: float
    change_pct: float | None
    volume: int

    @field_validator("price")
    @classmethod
    def _validate_price(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("price must be finite")
        if v <= 0:
            raise ValueError("price must be positive")
        return v

    @field_validator("change_pct")
    @classmethod
    def _validate_change_pct(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("change_pct must be finite")
        return v


def _extract_dividend_yield(
    info: dict[str, Any],
    dividends_series: pd.Series[float],
    current_price: Decimal,
) -> tuple[float, DividendSource, float | None, float | None]:
    """Extract dividend yield via the 3-tier waterfall (FR-M7.1).

    Returns:
        Tuple of (yield_value, source, dividend_rate, trailing_dividend_rate).

    CRITICAL: Fall-through condition is ``value is None``, NOT falsy.
    ``0.0`` is valid data for non-dividend-paying growth stocks.
    """
    dividend_rate: float | None = safe_float(info.get("dividendRate"))
    trailing_dividend_rate: float | None = safe_float(info.get("trailingAnnualDividendRate"))

    # Tier 1: Forward dividend yield
    forward_yield = info.get("dividendYield")
    if forward_yield is not None:
        yield_val = safe_float(forward_yield)
        if yield_val is not None:
            # yfinance >= 1.2.0 returns dividendYield as a percentage number
            # (e.g., 3.58 meaning 3.58%) instead of a decimal fraction (0.0358).
            # Normalize: no real stock has a >100% annual dividend yield as a
            # decimal fraction, so values > 1.0 are unambiguously percentages.
            if yield_val > 1.0:
                yield_val = yield_val / 100.0
            _cross_validate_yield(yield_val, dividend_rate, current_price, "forward")
            return (yield_val, DividendSource.FORWARD, dividend_rate, trailing_dividend_rate)

    # Tier 2: Trailing annual dividend yield
    trailing_yield = info.get("trailingAnnualDividendYield")
    if trailing_yield is not None:
        yield_val = safe_float(trailing_yield)
        if yield_val is not None:
            _cross_validate_yield(yield_val, trailing_dividend_rate, current_price, "trailing")
            return (yield_val, DividendSource.TRAILING, dividend_rate, trailing_dividend_rate)

    # Tier 3: Computed from dividend payments
    price_float = float(current_price)
    if price_float > 0 and not dividends_series.empty:
        total_dividends = float(dividends_series.sum())
        if total_dividends > 0:
            computed_yield = total_dividends / price_float
            return (
                computed_yield,
                DividendSource.COMPUTED,
                dividend_rate,
                trailing_dividend_rate,
            )

    # Tier 4: No dividend data
    return (0.0, DividendSource.NONE, dividend_rate, trailing_dividend_rate)


def _cross_validate_yield(
    yield_val: float,
    rate_val: float | None,
    current_price: Decimal,
    label: str,
) -> None:
    """Warn if dividend yield and dollar rate diverge by more than 20%.

    Args:
        yield_val: Dividend yield as a decimal fraction.
        rate_val: Dollar-denominated annual dividend rate, or None.
        current_price: Current ticker price.
        label: Human-readable label for the log message.
    """
    price_float = float(current_price)
    if rate_val is not None and price_float > 0:
        implied_yield = rate_val / price_float
        divergence = abs(yield_val - implied_yield) / max(yield_val, 1e-9)
        if divergence > 0.20:
            logger.warning(
                "Dividend divergence %.1f%% for %s yield (yield=%.6f, implied=%.6f)",
                divergence * 100,
                label,
                yield_val,
                implied_yield,
            )


def _classify_market_cap(market_cap: int | None) -> MarketCapTier | None:
    """Classify a market capitalisation value into a tier.

    Thresholds:
        mega  >= 200B
        large >= 10B
        mid   >= 2B
        small >= 300M
        micro <  300M
    """
    if market_cap is None:
        return None
    if market_cap >= 200_000_000_000:
        return MarketCapTier.MEGA
    if market_cap >= 10_000_000_000:
        return MarketCapTier.LARGE
    if market_cap >= 2_000_000_000:
        return MarketCapTier.MID
    if market_cap >= 300_000_000:
        return MarketCapTier.SMALL
    return MarketCapTier.MICRO


class MarketDataService:
    """Fetches and normalises yfinance market data into typed Pydantic models.

    All yfinance calls are wrapped via :meth:`_yf_call` which uses
    ``asyncio.to_thread`` + ``asyncio.wait_for`` for async safety and timeout.

    Args:
        config: Service configuration with timeouts and rate limits.
        cache: Two-tier cache (in-memory + SQLite) for de-duplication.
        limiter: Token-bucket + semaphore rate limiter.
    """

    def __init__(
        self,
        config: ServiceConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        self._config = config
        self._cache = cache
        self._limiter = limiter

    async def _yf_call[T](
        self,
        fn: Callable[..., T],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Wrap a sync yfinance call with to_thread + wait_for + error mapping.

        CRITICAL: Pass the callable and its args separately —
        ``to_thread(fn, *args)``, NOT ``to_thread(fn())``.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=self._config.yfinance_timeout,
            )
        except TimeoutError as exc:
            raise DataSourceUnavailableError(
                f"yfinance: timeout after {self._config.yfinance_timeout}s"
            ) from exc
        except DataFetchError:
            raise
        except Exception as exc:
            raise DataSourceUnavailableError(f"yfinance: {exc}") from exc

    @staticmethod
    def _build_info_from_fast_info(ticker_obj: yf.Ticker) -> dict[str, Any]:
        """Build an info-compatible dict from ``fast_info`` (Context7-verified).

        Used as fallback when ``Ticker.info`` fails (e.g. ETFs returning
        HTTP 404 for quoteSummary fundamentals).  ``fast_info`` uses a
        simpler Yahoo endpoint that works for all ticker types.
        """
        fi = ticker_obj.fast_info
        return {
            "currentPrice": fi["last_price"],
            "regularMarketPrice": fi["last_price"],
            "previousClose": fi["previous_close"],
            "marketCap": fi.get("market_cap"),
            "fiftyTwoWeekHigh": fi.get("year_high"),
            "fiftyTwoWeekLow": fi.get("year_low"),
            "volume": fi.get("last_volume"),
            "shortName": ticker_obj.ticker,
        }

    async def fetch_ohlcv(self, ticker: str, period: str = "1y") -> list[OHLCV]:
        """Fetch OHLCV history for *ticker* from yfinance.

        Returns a list of :class:`OHLCV` models sorted by date ascending.
        Uses cache-first strategy with permanent TTL for historical data.

        Raises:
            TickerNotFoundError: When yfinance returns no data for the ticker.
            InsufficientDataError: When yfinance returns an empty DataFrame.
            DataSourceUnavailableError: On timeout or network error.
        """
        cache_key = f"yf:ohlcv:{ticker}:{period}"

        # Cache-first
        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return _deserialize_ohlcv_list(cached, ticker)

        # Fetch from yfinance (with retry on transient failures)
        async with self._limiter:
            ticker_obj = yf.Ticker(ticker)
            df: pd.DataFrame = await fetch_with_retry(
                lambda: self._yf_call(ticker_obj.history, period=period)
            )

        if df.empty:
            raise InsufficientDataError(f"{ticker}: no OHLCV data returned by yfinance")

        # Convert DataFrame rows to OHLCV models
        records: list[OHLCV] = []
        for idx, row in df.iterrows():
            # yfinance history index is a DatetimeIndex — extract date
            row_date: date = pd.Timestamp(cast("str", idx)).date()

            open_d = safe_decimal(row.get("Open"))
            high_d = safe_decimal(row.get("High"))
            low_d = safe_decimal(row.get("Low"))
            close_d = safe_decimal(row.get("Close"))
            volume_i = safe_int(row.get("Volume")) or 0

            # Prefer "Adj Close" if available, fall back to "Close"
            adj_close_raw = row.get("Adj Close")
            adj_close_d = safe_decimal(adj_close_raw) if adj_close_raw is not None else close_d

            if open_d is None or high_d is None or low_d is None or close_d is None:
                logger.debug("Skipping row with None price for %s on %s", ticker, row_date)
                continue

            try:
                records.append(
                    OHLCV(
                        ticker=ticker,
                        date=row_date,
                        open=open_d,
                        high=high_d,
                        low=low_d,
                        close=close_d,
                        volume=volume_i,
                        adjusted_close=adj_close_d if adj_close_d is not None else close_d,
                    )
                )
            except PydanticValidationError as exc:
                logger.debug("Skipping invalid candle for %s on %s: %s", ticker, row_date, exc)
                continue

        if not records:
            raise InsufficientDataError(f"{ticker}: all OHLCV rows had invalid prices")

        # Sort by date ascending
        records.sort(key=lambda r: r.date)

        # Cache result
        serialized = _serialize_ohlcv_list(records)
        await self._cache.set(cache_key, serialized, ttl=TTL_OHLCV)

        logger.debug("Fetched %d OHLCV bars for %s (period=%s)", len(records), ticker, period)
        return records

    async def fetch_quote(self, ticker: str) -> Quote:
        """Fetch a real-time quote for *ticker* from yfinance.

        Returns a :class:`Quote` with UTC timestamp.

        Raises:
            DataSourceUnavailableError: On timeout or network error.
            TickerNotFoundError: When no price data is available.
        """
        cache_key = f"yf:quote:{ticker}"

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return _deserialize_quote(cached)

        async with self._limiter:
            ticker_obj = yf.Ticker(ticker)
            try:
                # Single attempt — ETF 404s are permanent, retrying wastes ~31s.
                info: dict[str, Any] = await self._yf_call(lambda: ticker_obj.info)
            except DataSourceUnavailableError:
                # ETFs (SPY, QQQ) lack quoteSummary fundamentals (Yahoo 404).
                # Fall back to fast_info for basic price data.
                logger.warning("%s: Ticker.info failed, using fast_info fallback", ticker)
                info = await self._yf_call(self._build_info_from_fast_info, ticker_obj)

        price_raw = info.get("currentPrice") or info.get("regularMarketPrice")
        price = safe_decimal(price_raw)
        if price is None or price <= Decimal("0"):
            raise TickerNotFoundError(f"{ticker}: invalid price data: {price_raw!r}")
        bid = safe_decimal(info.get("bid")) or Decimal("0")
        ask = safe_decimal(info.get("ask")) or Decimal("0")
        volume = safe_int(info.get("volume")) or 0

        quote = Quote(
            ticker=ticker,
            price=price,
            bid=bid,
            ask=ask,
            volume=volume,
            timestamp=datetime.now(UTC),
        )

        # Cache
        ttl = self._cache.ttl_for("quote")
        await self._cache.set(cache_key, _serialize_quote(quote), ttl=ttl)

        return quote

    async def fetch_ticker_info(self, ticker: str) -> TickerInfo:
        """Fetch fundamental data for *ticker* from yfinance.

        Implements the 3-tier dividend yield waterfall (FR-M7.1) and
        MarketCapTier classification.

        Raises:
            DataSourceUnavailableError: On timeout or network error.
            TickerNotFoundError: When no data is available.
        """
        cache_key = f"yf:fundamentals:{ticker}:info"

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return _deserialize_ticker_info(cached)

        async with self._limiter:
            ticker_obj = yf.Ticker(ticker)
            try:
                # Single attempt — ETF 404s are permanent, retrying wastes ~31s.
                info: dict[str, Any] = await self._yf_call(lambda: ticker_obj.info)
            except DataSourceUnavailableError:
                # ETFs (SPY, QQQ) lack quoteSummary fundamentals (Yahoo 404).
                # Fall back to fast_info for basic price/market-cap data.
                logger.warning("%s: Ticker.info failed, using fast_info fallback", ticker)
                info = await self._yf_call(self._build_info_from_fast_info, ticker_obj)

        # Fetch dividends for tier 3 of the waterfall
        try:
            async with self._limiter:
                dividends_series: pd.Series[float] = await fetch_with_retry(
                    lambda: self._yf_call(ticker_obj.get_dividends, period="1y")
                )
        except (DataSourceUnavailableError, DataFetchError):
            # ETFs or tickers without dividend data — fall through to tier 4 (0.0).
            logger.warning("%s: get_dividends failed, using empty series", ticker)
            dividends_series = pd.Series(dtype=float)

        # Extract current price — prefer currentPrice, fall back to previousClose
        current_price_raw = info.get("currentPrice") or info.get("previousClose")
        current_price = safe_decimal(current_price_raw)
        if current_price is None or current_price <= Decimal("0"):
            raise TickerNotFoundError(f"{ticker}: invalid current price: {current_price_raw!r}")

        # Dividend waterfall
        dividend_yield, dividend_source, dividend_rate, trailing_dividend_rate = (
            _extract_dividend_yield(info, dividends_series, current_price)
        )

        # Market cap classification
        market_cap_raw = safe_int(info.get("marketCap"))
        market_cap_tier = _classify_market_cap(market_cap_raw)

        # 52-week high/low
        fifty_two_week_high = safe_decimal(info.get("fiftyTwoWeekHigh")) or current_price
        fifty_two_week_low = safe_decimal(info.get("fiftyTwoWeekLow")) or current_price

        ticker_info = TickerInfo(
            ticker=ticker,
            company_name=str(info.get("shortName", ticker)),
            sector=str(v) if (v := info.get("sector")) not in (None, "") else "Unknown",
            industry=str(v) if (v := info.get("industry")) not in (None, "") else "Unknown",
            market_cap=market_cap_raw,
            market_cap_tier=market_cap_tier,
            dividend_yield=dividend_yield,
            dividend_source=dividend_source,
            dividend_rate=dividend_rate,
            trailing_dividend_rate=trailing_dividend_rate,
            current_price=current_price,
            fifty_two_week_high=fifty_two_week_high,
            fifty_two_week_low=fifty_two_week_low,
            short_ratio=safe_float(info.get("shortRatio")),
            short_pct_of_float=safe_float(info.get("shortPercentOfFloat")),
        )

        # Cache
        await self._cache.set(
            cache_key,
            _serialize_ticker_info(ticker_info),
            ttl=TTL_FUNDAMENTALS,
        )

        return ticker_info

    async def fetch_batch_ohlcv(
        self,
        tickers: list[str],
        period: str = "1y",
    ) -> BatchOHLCVResult:
        """Fetch OHLCV data for multiple tickers concurrently.

        Uses ``asyncio.gather(return_exceptions=True)`` for per-ticker
        error isolation. One failed ticker never crashes the batch.

        Returns:
            A ``BatchOHLCVResult`` with per-ticker success/error results.
        """
        tasks = [self.fetch_ohlcv(ticker, period) for ticker in tickers]
        results: list[list[OHLCV] | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        items: list[TickerOHLCVResult] = []
        for ticker, result in zip(tickers, results, strict=True):
            if isinstance(result, BaseException):
                items.append(TickerOHLCVResult(ticker=ticker, error=str(result)))
            else:
                items.append(TickerOHLCVResult(ticker=ticker, data=result))
        return BatchOHLCVResult(results=items)

    async def fetch_earnings_date(self, ticker: str) -> date | None:
        """Fetch the next earnings date for *ticker* from yfinance.

        Uses ``Ticker.calendar`` which returns a dict containing earnings
        event data. The dict's ``"Earnings Date"`` key holds a list of
        ``Timestamp`` objects (usually 1-2 entries for the estimated range).
        We pick the earliest future date.

        Returns ``None`` gracefully if yfinance has no earnings data — this is
        expected for ~20% of tickers (small caps, REITs, etc.).

        Cache TTL: 24 h (``TTL_EARNINGS``).
        """
        cache_key = f"yf:earnings:{ticker}"

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return _deserialize_earnings_date(cached)

        try:
            async with self._limiter:
                ticker_obj = yf.Ticker(ticker)
                calendar: dict[str, Any] = await fetch_with_retry(
                    lambda: self._yf_call(lambda: ticker_obj.calendar)
                )
        except Exception:
            logger.debug("No earnings calendar available for %s", ticker)
            # Cache the absence to avoid re-fetching on the same scan
            await self._cache.set(cache_key, b"null", ttl=TTL_EARNINGS)
            return None

        if not calendar or not isinstance(calendar, dict):
            await self._cache.set(cache_key, b"null", ttl=TTL_EARNINGS)
            return None

        # yfinance calendar dict uses "Earnings Date" key which holds a list
        # of Timestamp objects. Some versions use different key patterns.
        earnings_dates_raw = calendar.get("Earnings Date")
        if earnings_dates_raw is None:
            # Try alternative keys seen in some yfinance versions
            earnings_dates_raw = calendar.get("earningsDate")

        if not earnings_dates_raw:
            logger.debug("No earnings dates in calendar for %s", ticker)
            await self._cache.set(cache_key, b"null", ttl=TTL_EARNINGS)
            return None

        # Extract the earliest future date from the list
        today = date.today()
        earnings_date: date | None = None
        for raw_date in earnings_dates_raw:
            try:
                if hasattr(raw_date, "date"):
                    # pandas Timestamp
                    d = raw_date.date()
                elif isinstance(raw_date, str):
                    d = date.fromisoformat(raw_date[:10])
                else:
                    d = date.fromisoformat(str(raw_date)[:10])

                if d >= today and (earnings_date is None or d < earnings_date):
                    earnings_date = d
            except (ValueError, TypeError):
                logger.debug("Unparseable earnings date for %s: %r", ticker, raw_date)
                continue

        # Cache result (even None → "null")
        serialized = _serialize_earnings_date(earnings_date)
        await self._cache.set(cache_key, serialized, ttl=TTL_EARNINGS)

        if earnings_date is not None:
            logger.debug("Earnings date for %s: %s", ticker, earnings_date.isoformat())

        return earnings_date

    async def fetch_universe_data(self) -> UniverseData:
        """Fetch reference data for regime/macro indicators.

        Tickers: ^GSPC, ^VIX, ^VIX3M, HYG, LQD, plus 11 sector ETFs.
        Fetched once per scan, cached with existing 2-tier caching (24h TTL).

        VIX3M fallback: if ^VIX3M is unavailable, ``vix3m_close`` is ``None``.

        Returns:
            Typed :class:`UniverseData` dataclass with OHLCV for each reference ticker.
        """
        cache_key = "yf:universe_data:v1"

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return _deserialize_universe_data(cached)

        # Define tickers to fetch
        core_tickers = ["^GSPC", "^VIX", "^VIX3M", "HYG", "LQD"]
        sector_tickers = list(SECTOR_ETF_MAP.values())
        all_tickers = core_tickers + sector_tickers

        # Fetch all in parallel using _yf_call pattern
        async def _fetch_one(symbol: str) -> tuple[str, pd.DataFrame | None]:
            try:
                async with self._limiter:
                    ticker_obj = yf.Ticker(symbol)
                    df: pd.DataFrame = await fetch_with_retry(
                        lambda t=ticker_obj: self._yf_call(t.history, period="3mo")  # type: ignore[misc]
                    )
                if df.empty:
                    logger.debug("Empty data for universe ticker %s", symbol)
                    return (symbol, None)
                return (symbol, df)
            except Exception:
                logger.debug("Failed to fetch universe ticker %s", symbol, exc_info=True)
                return (symbol, None)

        tasks = [_fetch_one(t) for t in all_tickers]
        results: list[tuple[str, pd.DataFrame | None] | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        frames: dict[str, pd.DataFrame] = {}
        for ticker, result in zip(all_tickers, results, strict=True):
            if isinstance(result, BaseException):
                logger.debug("Universe fetch exception for %s: %s", ticker, result)
                continue
            _symbol, df = result
            if df is not None:
                frames[_symbol] = df

        # Extract latest close prices and return series
        def _latest_close(symbol: str) -> float | None:
            df = frames.get(symbol)
            if df is None or df.empty:
                return None
            close_col = df.get("Close")
            if close_col is None or close_col.empty:
                return None
            val = float(close_col.iloc[-1])
            return val if math.isfinite(val) else None

        def _close_series(symbol: str) -> pd.Series | None:
            df = frames.get(symbol)
            if df is None or df.empty:
                return None
            close_col = df.get("Close")
            if close_col is None or close_col.empty:
                return None
            return close_col

        def _return_20d(symbol: str) -> float | None:
            series = _close_series(symbol)
            if series is None or len(series) < 20:
                return None
            current = float(series.iloc[-1])
            past = float(series.iloc[-20])
            if past == 0.0 or not math.isfinite(current) or not math.isfinite(past):
                return None
            return (current - past) / past

        # Build sector ETF returns
        sector_etf_returns: dict[str, float | None] = {}
        for sector, etf in SECTOR_ETF_MAP.items():
            sector_etf_returns[sector] = _return_20d(etf)

        universe = UniverseData(
            spx_close=_close_series("^GSPC"),
            vix_close=_latest_close("^VIX"),
            vix3m_close=_latest_close("^VIX3M"),
            hyg_return_20d=_return_20d("HYG"),
            lqd_return_20d=_return_20d("LQD"),
            spx_return_20d=_return_20d("^GSPC"),
            sector_etf_returns=sector_etf_returns,
        )

        # Cache result
        serialized = _serialize_universe_data(universe)
        await self._cache.set(cache_key, serialized, ttl=TTL_REFERENCE)

        logger.debug(
            "Fetched universe data: VIX=%s, VIX3M=%s, SPX_ret=%s",
            universe.vix_close,
            universe.vix3m_close,
            universe.spx_return_20d,
        )
        return universe

    async def fetch_batch_daily_changes(
        self,
        tickers: list[str],
    ) -> list[BatchQuote]:
        """Fetch daily price changes for multiple tickers in a single batch call.

        Uses ``yf.download()`` to fetch 2 days of data for all tickers at once,
        then computes the daily percent change. Results are cached with a 5-minute
        heatmap TTL via ``cache.ttl_for("heatmap")``.
        """
        if not tickers:
            return []

        ticker_hash = hashlib.sha256(",".join(sorted(tickers)).encode()).hexdigest()[:16]
        cache_key = f"yf:heatmap:{ticker_hash}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return _deserialize_batch_quotes(cached)

        try:
            async with self._limiter:
                df: pd.DataFrame = await asyncio.wait_for(
                    asyncio.to_thread(
                        yf.download,
                        tickers=" ".join(tickers),
                        period="2d",
                        group_by="ticker",
                        progress=False,
                        threads=True,
                        timeout=self._config.yfinance_timeout,
                    ),
                    timeout=self._config.yfinance_timeout,
                )
        except Exception:
            logger.warning("yf.download batch fetch failed", exc_info=True)
            return []

        if df.empty:
            logger.warning("yf.download returned empty DataFrame for batch fetch")
            return []

        quotes: list[BatchQuote] = []
        single_ticker = len(tickers) == 1

        for ticker in tickers:
            try:
                if single_ticker:
                    close_series = df["Close"]
                    vol_series = df["Volume"]
                else:
                    close_series = df[(ticker, "Close")]
                    vol_series = df[(ticker, "Volume")]

                close_values = close_series.dropna()
                if close_values.empty:
                    continue

                latest_close = float(close_values.iloc[-1])
                if not math.isfinite(latest_close) or latest_close <= 0:
                    continue

                change_pct: float | None = None
                if len(close_values) >= 2:  # noqa: PLR2004
                    prev_close = float(close_values.iloc[-2])
                    if math.isfinite(prev_close) and prev_close > 0:
                        change_pct = (latest_close - prev_close) / prev_close * 100.0
                        if not math.isfinite(change_pct):
                            change_pct = None

                vol_values = vol_series.dropna()
                volume = int(vol_values.iloc[-1]) if not vol_values.empty else 0

                quotes.append(
                    BatchQuote(
                        ticker=ticker,
                        price=latest_close,
                        change_pct=change_pct,
                        volume=volume,
                    )
                )
            except (KeyError, IndexError, ValueError, TypeError):
                logger.debug("Skipping %s in batch daily changes", ticker)
                continue

        serialized = _serialize_batch_quotes(quotes)
        await self._cache.set(cache_key, serialized, ttl=self._cache.ttl_for("heatmap"))

        logger.debug(
            "Fetched batch daily changes: %d/%d tickers succeeded",
            len(quotes),
            len(tickers),
        )
        return quotes

    async def close(self) -> None:
        """Release resources. Safe to call multiple times."""
        logger.debug("MarketDataService closed")


# ---------------------------------------------------------------------------
# Serialization helpers (OHLCV, Quote, TickerInfo <-> bytes for cache)
# ---------------------------------------------------------------------------


def _serialize_ohlcv_list(records: list[OHLCV]) -> bytes:
    """Serialize a list of OHLCV models to bytes for cache storage."""
    return json.dumps([r.model_dump(mode="json") for r in records]).encode("utf-8")


def _deserialize_ohlcv_list(data: bytes, ticker: str) -> list[OHLCV]:
    """Deserialize bytes from cache back into a list of OHLCV models."""
    raw_list: list[dict[str, Any]] = json.loads(data.decode("utf-8"))
    return [OHLCV.model_validate(item) for item in raw_list]


def _serialize_quote(quote: Quote) -> bytes:
    """Serialize a Quote model to bytes for cache storage."""
    return quote.model_dump_json().encode("utf-8")


def _deserialize_quote(data: bytes) -> Quote:
    """Deserialize bytes from cache back into a Quote model."""
    return Quote.model_validate_json(data.decode("utf-8"))


def _serialize_ticker_info(info: TickerInfo) -> bytes:
    """Serialize a TickerInfo model to bytes for cache storage."""
    return info.model_dump_json().encode("utf-8")


def _deserialize_ticker_info(data: bytes) -> TickerInfo:
    """Deserialize bytes from cache back into a TickerInfo model."""
    return TickerInfo.model_validate_json(data.decode("utf-8"))


def _serialize_earnings_date(earnings_date: date | None) -> bytes:
    """Serialize an optional date to bytes for cache storage."""
    if earnings_date is None:
        return b"null"
    return earnings_date.isoformat().encode("utf-8")


def _deserialize_earnings_date(data: bytes) -> date | None:
    """Deserialize bytes from cache back into an optional date."""
    text = data.decode("utf-8")
    if text == "null":
        return None
    return date.fromisoformat(text)


def _serialize_universe_data(universe: UniverseData) -> bytes:
    """Serialize UniverseData to bytes for cache storage.

    SPX close series is serialized as a JSON array of [iso_date, value] pairs.
    """
    spx_list: list[list[str | float]] | None = None
    if universe.spx_close is not None and not universe.spx_close.empty:
        spx_list = [
            [str(idx), float(val)]
            for idx, val in universe.spx_close.items()
            if math.isfinite(float(val))
        ]
    payload: dict[str, Any] = {
        "spx_close": spx_list,
        "vix_close": universe.vix_close,
        "vix3m_close": universe.vix3m_close,
        "hyg_return_20d": universe.hyg_return_20d,
        "lqd_return_20d": universe.lqd_return_20d,
        "spx_return_20d": universe.spx_return_20d,
        "sector_etf_returns": universe.sector_etf_returns,
    }
    return json.dumps(payload).encode("utf-8")


def _deserialize_universe_data(data: bytes) -> UniverseData:
    """Deserialize bytes from cache back into a UniverseData dataclass."""
    raw: dict[str, Any] = json.loads(data.decode("utf-8"))
    spx_close: pd.Series[float] | None = None
    if raw.get("spx_close") is not None:
        pairs: list[list[str | float]] = raw["spx_close"]
        dates = [p[0] for p in pairs]
        values = [p[1] for p in pairs]
        spx_close = pd.Series(values, index=pd.Index(dates))
    return UniverseData(
        spx_close=spx_close,
        vix_close=raw.get("vix_close"),
        vix3m_close=raw.get("vix3m_close"),
        hyg_return_20d=raw.get("hyg_return_20d"),
        lqd_return_20d=raw.get("lqd_return_20d"),
        spx_return_20d=raw.get("spx_return_20d"),
        sector_etf_returns=raw.get("sector_etf_returns", {}),
    )


def _serialize_batch_quotes(quotes: list[BatchQuote]) -> bytes:
    """Serialize a list of BatchQuote models to bytes for cache storage."""
    return json.dumps([q.model_dump(mode="json") for q in quotes]).encode("utf-8")


def _deserialize_batch_quotes(data: bytes) -> list[BatchQuote]:
    """Deserialize bytes from cache back into a list of BatchQuote models."""
    raw_list: list[dict[str, Any]] = json.loads(data.decode("utf-8"))
    return [BatchQuote.model_validate(item) for item in raw_list]
