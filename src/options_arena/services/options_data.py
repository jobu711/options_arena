"""Options data service — fetches option chains from yfinance.

Applies basic liquidity filters (OI, volume, both-zero rejection) and converts
yfinance camelCase DataFrame rows to typed ``OptionContract`` models.

Does NOT compute Greeks — that is ``pricing/dispatch.py``'s job. The yfinance
``impliedVolatility`` column is passed through as ``market_iv`` without
re-annualization (it is already annualized).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]
from pydantic import BaseModel

from options_arena.models.config import PricingConfig, ServiceConfig
from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from options_arena.services.cache import ServiceCache
from options_arena.services.helpers import fetch_with_retry, safe_decimal, safe_float, safe_int
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataFetchError, DataSourceUnavailableError

logger = logging.getLogger(__name__)


def _passes_liquidity_filter(row: pd.Series[float], config: PricingConfig) -> bool:
    """Check if an option contract row passes basic liquidity requirements.

    Filters applied:
    - Reject truly dead contracts where both bid AND ask are zero.
    - Zero-bid exemption: bid=0/ask>0 passes through (allows the analysis
      layer to price these contracts via ``pricing/dispatch.py``).
    - Open interest must meet ``config.min_oi``.
    - Volume must meet ``config.min_volume``.

    Args:
        row: A single row from a yfinance option chain DataFrame.
        config: Pricing configuration with ``min_oi`` and ``min_volume`` thresholds.

    Returns:
        ``True`` if the contract passes all liquidity checks.
    """
    oi = safe_int(row.get("openInterest")) or 0
    vol = safe_int(row.get("volume")) or 0
    bid = safe_float(row.get("bid")) or 0.0
    ask = safe_float(row.get("ask")) or 0.0

    # Truly dead — both zero -> reject
    if bid == 0.0 and ask == 0.0:
        return False

    # bid=0/ask>0 passes (zero-bid exemption)
    return oi >= config.min_oi and vol >= config.min_volume


def _row_to_contract(
    row: pd.Series[float],
    ticker: str,
    option_type: OptionType,
    expiration: date,
) -> OptionContract:
    """Convert a single yfinance chain row to an ``OptionContract``.

    All price fields are converted to ``Decimal`` via ``safe_decimal`` with
    ``Decimal("0")`` fallback. Volume and open interest use ``safe_int`` with
    ``0`` fallback. ``market_iv`` uses ``safe_float`` with ``0.0`` fallback.

    Args:
        row: A single row from a yfinance option chain DataFrame.
        ticker: The underlying ticker symbol.
        option_type: ``OptionType.CALL`` or ``OptionType.PUT``.
        expiration: The expiration date for this chain.

    Returns:
        A fully constructed ``OptionContract`` with ``greeks=None`` and
        ``exercise_style=ExerciseStyle.AMERICAN``.
    """
    strike = safe_decimal(row.get("strike"))
    if strike is None or strike <= Decimal("0"):
        raise ValueError(f"invalid strike price: {row.get('strike')!r}")

    return OptionContract(
        ticker=ticker,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        bid=safe_decimal(row.get("bid")) or Decimal("0"),
        ask=safe_decimal(row.get("ask")) or Decimal("0"),
        last=safe_decimal(row.get("lastPrice")) or Decimal("0"),
        volume=safe_int(row.get("volume")) or 0,
        open_interest=safe_int(row.get("openInterest")) or 0,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=safe_float(row.get("impliedVolatility")) or 0.0,
        greeks=None,
    )


def _contracts_to_cache_bytes(contracts: list[OptionContract]) -> bytes:
    """Serialize a list of contracts to JSON bytes for caching."""
    return json.dumps([c.model_dump(mode="json") for c in contracts]).encode("utf-8")


def _cache_bytes_to_contracts(data: bytes) -> list[OptionContract]:
    """Deserialize cached JSON bytes back to a list of contracts."""
    raw: list[dict[str, object]] = json.loads(data.decode("utf-8"))
    return [OptionContract.model_validate(item) for item in raw]


class ExpirationChain(BaseModel):
    """Option contracts for a single expiration date."""

    expiration: date
    contracts: list[OptionContract]


class OptionsDataService:
    """Fetches option chains from yfinance with caching and rate limiting.

    Applies basic liquidity filters and converts yfinance data to typed
    ``OptionContract`` models. Does NOT compute Greeks — all contracts
    have ``greeks=None``.

    Args:
        config: Service configuration with timeout settings.
        pricing_config: Pricing configuration with OI/volume filter thresholds.
        cache: Two-tier service cache for chain data.
        limiter: Rate limiter for yfinance API calls.
    """

    def __init__(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        self._config = config
        self._pricing_config = pricing_config
        self._cache = cache
        self._limiter = limiter

    async def _yf_call[T](
        self,
        fn: Callable[..., T],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Wrap a sync yfinance call: ``asyncio.to_thread`` + ``asyncio.wait_for``.

        Offloads the synchronous yfinance function to a thread and enforces a
        timeout from ``ServiceConfig.yfinance_timeout``. Maps all errors to
        ``DataSourceUnavailableError``.

        Args:
            fn: The synchronous callable (e.g., ``ticker_obj.option_chain``).
            *args: Positional arguments forwarded to ``fn``.
            **kwargs: Keyword arguments forwarded to ``fn``.

        Returns:
            The return value of ``fn(*args, **kwargs)``.

        Raises:
            DataSourceUnavailableError: On timeout or any yfinance error.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=self._config.yfinance_timeout,
            )
        except TimeoutError as e:
            raise DataSourceUnavailableError(
                "yfinance", f"timeout after {self._config.yfinance_timeout}s"
            ) from e
        except DataFetchError:
            raise
        except Exception as e:
            raise DataSourceUnavailableError("yfinance", str(e)) from e

    async def fetch_expirations(self, ticker: str) -> list[date]:
        """Fetch available option expiration dates for a ticker.

        Returns dates sorted ascending. Uses the cache with ``chain`` TTL.

        Args:
            ticker: The underlying ticker symbol (e.g., ``"AAPL"``).

        Returns:
            Sorted list of expiration dates.

        Raises:
            DataSourceUnavailableError: On yfinance timeout or error.
        """
        cache_key = f"yf:expirations:{ticker}"

        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached is not None:
            raw_dates: list[str] = json.loads(cached.decode("utf-8"))
            return [datetime.strptime(d, "%Y-%m-%d").date() for d in raw_dates]

        async with self._limiter:
            ticker_obj = yf.Ticker(ticker)
            raw_expirations: tuple[str, ...] = await fetch_with_retry(
                lambda: self._yf_call(getattr, ticker_obj, "options")
            )

        expirations = sorted(datetime.strptime(s, "%Y-%m-%d").date() for s in raw_expirations)

        # Cache the result
        cache_bytes = json.dumps([d.isoformat() for d in expirations]).encode("utf-8")
        ttl = self._cache.ttl_for("reference")
        await self._cache.set(cache_key, cache_bytes, ttl=ttl)

        logger.debug("Fetched %d expirations for %s", len(expirations), ticker)
        return expirations

    async def fetch_chain(
        self,
        ticker: str,
        expiration: date,
    ) -> list[OptionContract]:
        """Fetch the option chain for a specific expiration date.

        Applies liquidity filtering and converts yfinance data to typed
        ``OptionContract`` models with ``greeks=None`` and
        ``exercise_style=ExerciseStyle.AMERICAN``.

        Args:
            ticker: The underlying ticker symbol.
            expiration: The target expiration date.

        Returns:
            List of ``OptionContract`` models that pass liquidity filters.

        Raises:
            DataSourceUnavailableError: On yfinance timeout or error.
        """
        cache_key = f"yf:chain:{ticker}:{expiration.isoformat()}"

        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return _cache_bytes_to_contracts(cached)

        async with self._limiter:
            ticker_obj = yf.Ticker(ticker)
            chain_data = await fetch_with_retry(
                lambda: self._yf_call(ticker_obj.option_chain, expiration.isoformat())
            )

        contracts: list[OptionContract] = []

        # Process calls DataFrame
        calls_df: pd.DataFrame = chain_data.calls
        for _, row in calls_df.iterrows():
            if _passes_liquidity_filter(row, self._pricing_config):
                try:
                    contracts.append(_row_to_contract(row, ticker, OptionType.CALL, expiration))
                except ValueError:
                    logger.debug("Skipping call with invalid strike for %s", ticker)

        # Process puts DataFrame
        puts_df: pd.DataFrame = chain_data.puts
        for _, row in puts_df.iterrows():
            if _passes_liquidity_filter(row, self._pricing_config):
                try:
                    contracts.append(_row_to_contract(row, ticker, OptionType.PUT, expiration))
                except ValueError:
                    logger.debug("Skipping put with invalid strike for %s", ticker)

        # Cache the result
        ttl = self._cache.ttl_for("chain")
        await self._cache.set(cache_key, _contracts_to_cache_bytes(contracts), ttl=ttl)

        logger.debug(
            "Fetched chain for %s exp %s: %d contracts (after liquidity filter)",
            ticker,
            expiration.isoformat(),
            len(contracts),
        )
        return contracts

    async def fetch_chain_all_expirations(
        self,
        ticker: str,
    ) -> list[ExpirationChain]:
        """Fetch option chains for all available expirations concurrently.

        Uses ``asyncio.gather(return_exceptions=True)`` so one failed expiration
        does not cancel the rest. Failed expirations are logged and excluded
        from the result.

        Args:
            ticker: The underlying ticker symbol.

        Returns:
            List of ``ExpirationChain`` models (one per successful expiration).
        """
        expirations = await self.fetch_expirations(ticker)

        tasks = [self.fetch_chain(ticker, exp) for exp in expirations]
        results: list[list[OptionContract] | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        chains: list[ExpirationChain] = []
        succeeded = 0
        for exp, result in zip(expirations, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to fetch chain for %s exp %s: %s",
                    ticker,
                    exp.isoformat(),
                    result,
                )
            else:
                chains.append(ExpirationChain(expiration=exp, contracts=result))
                succeeded += 1

        logger.debug(
            "Fetched all chains for %s: %d/%d expirations succeeded",
            ticker,
            succeeded,
            len(expirations),
        )
        return chains

    async def close(self) -> None:
        """Clean up resources. No-op for this service (no owned connections)."""
