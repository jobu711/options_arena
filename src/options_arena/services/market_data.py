"""Market data service — OHLCV, quotes, and ticker info from yfinance.

Fetches and normalizes yfinance market data into typed Pydantic models.
Includes the 3-tier dividend yield waterfall (FR-M7.1), MarketCapTier
classification, and cross-validation logic. All yfinance calls are
wrapped with ``asyncio.to_thread`` + ``asyncio.wait_for`` for async safety.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import DividendSource, MarketCapTier
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.services.cache import TTL_FUNDAMENTALS, TTL_OHLCV, ServiceCache
from options_arena.services.helpers import fetch_with_retry, safe_decimal, safe_float, safe_int
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import (
    DataFetchError,
    DataSourceUnavailableError,
    InsufficientDataError,
    TickerNotFoundError,
)

logger = logging.getLogger(__name__)


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
                "yfinance", f"timeout after {self._config.yfinance_timeout}s"
            ) from exc
        except DataFetchError:
            raise
        except Exception as exc:
            raise DataSourceUnavailableError("yfinance", str(exc)) from exc

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
            raise InsufficientDataError(ticker, "no OHLCV data returned by yfinance")

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
            raise InsufficientDataError(ticker, "all OHLCV rows had invalid prices")

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
            info: dict[str, Any] = await fetch_with_retry(
                lambda: self._yf_call(lambda: ticker_obj.info)
            )

        price_raw = info.get("currentPrice") or info.get("regularMarketPrice")
        price = safe_decimal(price_raw)
        if price is None or price <= Decimal("0"):
            raise TickerNotFoundError(ticker, f"invalid price data: {price_raw!r}")
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
            info: dict[str, Any] = await fetch_with_retry(
                lambda: self._yf_call(lambda: ticker_obj.info)
            )

        # Fetch dividends for tier 3 of the waterfall
        async with self._limiter:
            dividends_series: pd.Series[float] = await fetch_with_retry(
                lambda: self._yf_call(ticker_obj.get_dividends, period="1y")
            )

        # Extract current price — prefer currentPrice, fall back to previousClose
        current_price_raw = info.get("currentPrice") or info.get("previousClose")
        current_price = safe_decimal(current_price_raw)
        if current_price is None or current_price <= Decimal("0"):
            raise TickerNotFoundError(ticker, f"invalid current price: {current_price_raw!r}")

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
            sector=str(info.get("sector", "Unknown")),
            market_cap=market_cap_raw,
            market_cap_tier=market_cap_tier,
            dividend_yield=dividend_yield,
            dividend_source=dividend_source,
            dividend_rate=dividend_rate,
            trailing_dividend_rate=trailing_dividend_rate,
            current_price=current_price,
            fifty_two_week_high=fifty_two_week_high,
            fifty_two_week_low=fifty_two_week_low,
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
