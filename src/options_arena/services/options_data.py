"""Options data service — fetches option chains with provider orchestration.

Applies basic liquidity filters (OI, volume, both-zero rejection) and converts
yfinance camelCase DataFrame rows to typed ``OptionContract`` models.

Does NOT compute Greeks — that is ``pricing/dispatch.py``'s job. The yfinance
``impliedVolatility`` column is passed through as ``market_iv`` without
re-annualization (it is already annualized).

Architecture:
    ``ChainProvider`` is a ``Protocol`` defining the chain-fetching contract.
    ``YFinanceChainProvider`` implements it using yfinance.
    ``CBOEChainProvider`` implements it using OpenBB (optional).
    ``OptionsDataService`` builds a prioritized provider list and iterates
    with fallback on ``DataSourceUnavailableError``. CBOE is tried first
    (when enabled and available), yfinance as fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]
from pydantic import BaseModel

from options_arena.models.config import OpenBBConfig, PricingConfig, ServiceConfig
from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from options_arena.services.cache import ServiceCache
from options_arena.services.cboe_provider import CBOEChainProvider
from options_arena.services.helpers import (
    fetch_with_limiter_retry,
    safe_decimal,
    safe_float,
    safe_int,
)
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataFetchError, DataSourceUnavailableError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions, no state)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ChainProvider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ChainProvider(Protocol):
    """Protocol defining the contract for option chain data providers.

    Any class implementing ``fetch_expirations`` and ``fetch_chain`` with
    the correct signatures satisfies this protocol. Use
    ``isinstance(obj, ChainProvider)`` at runtime to verify.
    """

    async def fetch_expirations(self, ticker: str) -> list[date]:
        """Fetch available option expiration dates for a ticker.

        Args:
            ticker: The underlying ticker symbol.

        Returns:
            Sorted list of expiration dates.
        """
        ...

    async def fetch_chain(self, ticker: str, expiration: date) -> list[OptionContract]:
        """Fetch the option chain for a specific expiration date.

        Args:
            ticker: The underlying ticker symbol.
            expiration: The target expiration date.

        Returns:
            List of ``OptionContract`` models that pass liquidity filters.
        """
        ...


# ---------------------------------------------------------------------------
# YFinanceChainProvider — yfinance implementation of ChainProvider
# ---------------------------------------------------------------------------


class YFinanceChainProvider:
    """Fetches option chains from yfinance with caching and rate limiting.

    Applies basic liquidity filters (via module-level ``_passes_liquidity_filter``)
    and converts yfinance data to typed ``OptionContract`` models. Does NOT
    compute Greeks — all contracts have ``greeks=None``.

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
                f"yfinance: timeout after {self._config.yfinance_timeout}s"
            ) from e
        except DataFetchError:
            raise
        except Exception as e:
            raise DataSourceUnavailableError(f"yfinance: {e}") from e

    async def fetch_expirations(self, ticker: str) -> list[date]:
        """Fetch available option expiration dates for a ticker.

        Returns dates sorted ascending. Uses the cache with ``reference`` TTL.

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

        ticker_obj = yf.Ticker(ticker)
        raw_expirations: tuple[str, ...] = await fetch_with_limiter_retry(
            self._yf_call, getattr, ticker_obj, "options", limiter=self._limiter
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

        ticker_obj = yf.Ticker(ticker)
        chain_data = await fetch_with_limiter_retry(
            self._yf_call,
            ticker_obj.option_chain,
            expiration.isoformat(),
            limiter=self._limiter,
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


# ---------------------------------------------------------------------------
# Pydantic model for grouped chain results
# ---------------------------------------------------------------------------


class ExpirationChain(BaseModel):
    """Option contracts for a single expiration date."""

    expiration: date
    contracts: list[OptionContract]


# ---------------------------------------------------------------------------
# OptionsDataService — public facade delegating to a ChainProvider
# ---------------------------------------------------------------------------


class OptionsDataService:
    """Fetches option chains with provider orchestration and fallback.

    Builds a prioritized list of ``ChainProvider`` instances and iterates
    them with fallback on ``DataSourceUnavailableError``. When CBOE chains
    are enabled (via ``OpenBBConfig``), CBOE is tried first; yfinance is
    always the last-resort fallback.

    Backward compatible: existing code that passes ``provider=`` or omits
    ``openbb_config`` works exactly as before.

    Args:
        config: Service configuration with timeout settings.
        pricing_config: Pricing configuration with OI/volume filter thresholds.
        cache: Two-tier service cache for chain data.
        limiter: Rate limiter for API calls.
        provider: Optional chain provider override — when given, used as the
            sole provider (ignores ``openbb_config``). Useful for tests.
        openbb_config: Optional OpenBB configuration. When provided with
            ``cboe_chains_enabled=True`` and the SDK is available, CBOE is
            registered as the primary provider ahead of yfinance.
    """

    def __init__(
        self,
        config: ServiceConfig,
        pricing_config: PricingConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
        *,
        provider: ChainProvider | None = None,
        openbb_config: OpenBBConfig | None = None,
    ) -> None:
        self._config = config
        self._pricing_config = pricing_config
        self._cache = cache
        self._limiter = limiter
        self._openbb_config = openbb_config
        self._validation_mode = openbb_config is not None and openbb_config.chain_validation_mode

        # When a custom provider is injected (tests), use it as the sole provider
        if provider is not None:
            self._providers: list[ChainProvider] = [provider]
            logger.info("Using injected chain provider: %s", type(provider).__name__)
        else:
            self._providers = self._build_provider_list(openbb_config, cache, limiter)

        # Keep a reference to the yfinance provider for validation mode
        self._yfinance_provider: YFinanceChainProvider | None = None
        if self._validation_mode:
            # Find the yfinance provider in the list
            for p in self._providers:
                if isinstance(p, YFinanceChainProvider):
                    self._yfinance_provider = p
                    break
            if self._yfinance_provider is None:
                # Build one if needed (e.g., when CBOE is primary and yfinance is fallback)
                self._yfinance_provider = YFinanceChainProvider(
                    config=config,
                    pricing_config=pricing_config,
                    cache=cache,
                    limiter=limiter,
                )

    def _build_provider_list(
        self,
        openbb_config: OpenBBConfig | None,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> list[ChainProvider]:
        """Build the prioritized provider list from configuration.

        CBOE (via OpenBB) is registered first when enabled and available.
        ``YFinanceChainProvider`` is always appended as the last-resort fallback.

        Args:
            openbb_config: Optional OpenBB configuration with CBOE toggle.
            cache: Two-tier service cache for chain data.
            limiter: Rate limiter for API calls.

        Returns:
            Ordered list of ``ChainProvider`` instances.
        """
        providers: list[ChainProvider] = []

        if openbb_config is not None and openbb_config.cboe_chains_enabled:
            cboe = CBOEChainProvider(config=openbb_config, cache=cache, limiter=limiter)
            if cboe.available:
                providers.append(cboe)
                logger.info("Registered CBOE chain provider (primary)")
            else:
                logger.debug(
                    "CBOE chains enabled in config but OpenBB SDK not available — skipping"
                )

        yfinance_provider = YFinanceChainProvider(
            config=self._config,
            pricing_config=self._pricing_config,
            cache=cache,
            limiter=limiter,
        )
        providers.append(yfinance_provider)
        logger.info("Registered YFinance chain provider (fallback)")

        return providers

    async def fetch_expirations(self, ticker: str) -> list[date]:
        """Fetch available option expiration dates for a ticker.

        Iterates providers in priority order with fallback on
        ``DataSourceUnavailableError``.

        Args:
            ticker: The underlying ticker symbol (e.g., ``"AAPL"``).

        Returns:
            Sorted list of expiration dates.

        Raises:
            DataSourceUnavailableError: When all providers fail.
        """
        last_error: DataSourceUnavailableError | None = None
        for provider in self._providers:
            try:
                return await asyncio.wait_for(
                    provider.fetch_expirations(ticker),
                    timeout=self._config.yfinance_timeout,
                )
            except TimeoutError:
                logger.warning(
                    "Provider %s timed out in fetch_expirations for %s",
                    type(provider).__name__,
                    ticker,
                )
                last_error = DataSourceUnavailableError(
                    type(provider).__name__,
                    f"timeout after {self._config.yfinance_timeout}s",
                )
            except DataSourceUnavailableError as e:
                logger.warning(
                    "Provider %s failed fetch_expirations for %s: %s",
                    type(provider).__name__,
                    ticker,
                    e,
                )
                last_error = e
            except Exception as e:
                logger.warning(
                    "Provider %s unexpected error in fetch_expirations for %s: %s",
                    type(provider).__name__,
                    ticker,
                    e,
                )
                last_error = DataSourceUnavailableError(type(provider).__name__, str(e))
        raise last_error or DataSourceUnavailableError("options", "No chain providers available")

    async def fetch_chain(
        self,
        ticker: str,
        expiration: date,
    ) -> list[OptionContract]:
        """Fetch the option chain for a specific expiration date.

        Iterates providers in priority order with fallback on
        ``DataSourceUnavailableError``. The first provider to succeed
        returns the result; subsequent providers are not tried.

        When ``chain_validation_mode`` is enabled, the primary result is
        compared against a background yfinance fetch. The comparison is
        logged at INFO level. Validation is observational only — it never
        affects the return value.

        Args:
            ticker: The underlying ticker symbol.
            expiration: The target expiration date.

        Returns:
            List of ``OptionContract`` models that pass liquidity filters.

        Raises:
            DataSourceUnavailableError: When all providers fail.
        """
        last_error: DataSourceUnavailableError | None = None
        for provider in self._providers:
            try:
                primary_result = await asyncio.wait_for(
                    provider.fetch_chain(ticker, expiration),
                    timeout=self._config.yfinance_timeout,
                )
                # Kick off validation if enabled and the primary provider isn't yfinance
                if (
                    self._validation_mode
                    and self._yfinance_provider is not None
                    and not isinstance(provider, YFinanceChainProvider)
                ):
                    asyncio.create_task(
                        self._validate_chain(
                            ticker, expiration, primary_result, self._yfinance_provider
                        )
                    )
                return primary_result
            except TimeoutError:
                logger.warning(
                    "Provider %s timed out in fetch_chain for %s",
                    type(provider).__name__,
                    ticker,
                )
                last_error = DataSourceUnavailableError(
                    type(provider).__name__,
                    f"timeout after {self._config.yfinance_timeout}s",
                )
            except DataSourceUnavailableError as e:
                logger.warning(
                    "Provider %s failed fetch_chain for %s: %s",
                    type(provider).__name__,
                    ticker,
                    e,
                )
                last_error = e
            except Exception as e:
                logger.warning(
                    "Provider %s unexpected error in fetch_chain for %s: %s",
                    type(provider).__name__,
                    ticker,
                    e,
                )
                last_error = DataSourceUnavailableError(type(provider).__name__, str(e))
        raise last_error or DataSourceUnavailableError("options", "No chain providers available")

    async def _validate_chain(
        self,
        ticker: str,
        expiration: date,
        primary: list[OptionContract],
        yfinance_provider: YFinanceChainProvider,
    ) -> None:
        """Compare primary provider chain against yfinance (observational only).

        Runs in the background via ``asyncio.create_task``. Logs comparison
        metrics at INFO level. Never raises — all errors are caught and logged.

        Args:
            ticker: The underlying ticker symbol.
            expiration: The target expiration date.
            primary: Contracts from the primary provider (e.g., CBOE).
            yfinance_provider: The yfinance provider to fetch comparison data.
        """
        try:
            yf_contracts = await yfinance_provider.fetch_chain(ticker, expiration)

            # Strike coverage comparison
            primary_strikes = {c.strike for c in primary}
            yf_strikes = {c.strike for c in yf_contracts}
            overlap = primary_strikes & yf_strikes
            primary_only = primary_strikes - yf_strikes
            yf_only = yf_strikes - primary_strikes

            # IV comparison for overlapping strikes
            iv_diffs: list[float] = []
            primary_iv_map = {(c.strike, c.option_type): c.market_iv for c in primary}
            yf_iv_map = {(c.strike, c.option_type): c.market_iv for c in yf_contracts}
            for key in set(primary_iv_map) & set(yf_iv_map):
                p_iv = primary_iv_map[key]
                y_iv = yf_iv_map[key]
                if p_iv > 0.0 and y_iv > 0.0:
                    iv_diffs.append(abs(p_iv - y_iv))

            avg_iv_diff = sum(iv_diffs) / len(iv_diffs) if iv_diffs else 0.0

            logger.info(
                "Chain validation %s exp %s: "
                "strikes overlap=%d, primary_only=%d, yf_only=%d, "
                "avg IV diff=%.4f (%d comparisons)",
                ticker,
                expiration.isoformat(),
                len(overlap),
                len(primary_only),
                len(yf_only),
                avg_iv_diff,
                len(iv_diffs),
            )
        except Exception as exc:
            logger.warning(
                "Chain validation failed for %s exp %s: %s",
                ticker,
                expiration.isoformat(),
                exc,
            )

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
        """Clean up resources. Closes all providers that have a ``close`` method."""
        for provider in self._providers:
            close_fn = getattr(provider, "close", None)
            if close_fn is not None and callable(close_fn):
                await close_fn()
