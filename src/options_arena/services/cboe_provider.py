"""CBOE option chain provider via OpenBB Platform SDK.

Fetches option chains from the CBOE data source using the OpenBB derivatives
API. Maps CBOE data to typed ``OptionContract`` models with native Greeks
(when available), ``bid_iv``/``ask_iv``, and ``greeks_source=GreeksSource.MARKET``.

Uses the same guarded-import pattern as ``openbb_service.py`` — the system runs
identically without the OpenBB SDK installed (``available`` property returns
``False``). Implements the ``ChainProvider`` protocol from ``options_data.py``.

Class-based DI with ``config``, ``cache``, ``limiter`` — same pattern as all
other service classes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any  # noqa: ANN401 — required for optional untyped SDK objects

import pandas as pd

from options_arena.models.config import OpenBBConfig
from options_arena.models.enums import ExerciseStyle, GreeksSource, OptionType, PricingModel
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.services.cache import ServiceCache
from options_arena.services.helpers import safe_decimal, safe_float, safe_int
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError

logger = logging.getLogger(__name__)


def _get_obb() -> Any:  # noqa: ANN401
    """Attempt to import the OpenBB SDK. Returns ``obb`` module or ``None``."""
    try:
        from openbb import obb  # type: ignore[import-not-found]

        return obb
    except ImportError:
        logger.info("OpenBB SDK not installed — CBOE chain provider disabled")
        return None


def _validate_greeks(
    delta: float | None,
    gamma: float | None,
    theta: float | None,
    vega: float | None,
    rho: float | None,
) -> OptionGreeks | None:
    """Validate and construct ``OptionGreeks`` from raw CBOE values.

    Returns ``None`` if any required Greek is missing or fails sanity checks:
    - ``|delta| <= 1.0``
    - ``gamma >= 0``
    - ``vega >= 0``
    - ``theta`` and ``rho`` must be finite

    When all Greeks pass, ``pricing_model=PricingModel.BAW`` is used as a
    placeholder label since CBOE provides market-derived Greeks (not locally
    computed BAW/BSM values).

    Args:
        delta: Delta value from CBOE.
        gamma: Gamma value from CBOE.
        theta: Theta value from CBOE.
        vega: Vega value from CBOE.
        rho: Rho value from CBOE.

    Returns:
        Validated ``OptionGreeks`` or ``None`` if validation fails.
    """
    # All five Greeks must be present
    if any(v is None for v in (delta, gamma, theta, vega, rho)):
        return None

    # At this point we know none are None — assert for type checker
    assert delta is not None  # noqa: S101
    assert gamma is not None  # noqa: S101
    assert theta is not None  # noqa: S101
    assert vega is not None  # noqa: S101
    assert rho is not None  # noqa: S101

    # Sanity checks matching OptionGreeks validators
    if not math.isfinite(delta) or not -1.0 <= delta <= 1.0:
        logger.debug("CBOE delta failed sanity: %s", delta)
        return None
    if not math.isfinite(gamma) or gamma < 0.0:
        logger.debug("CBOE gamma failed sanity: %s", gamma)
        return None
    if not math.isfinite(vega) or vega < 0.0:
        logger.debug("CBOE vega failed sanity: %s", vega)
        return None
    if not math.isfinite(theta):
        logger.debug("CBOE theta failed sanity: %s", theta)
        return None
    if not math.isfinite(rho):
        logger.debug("CBOE rho failed sanity: %s", rho)
        return None

    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        pricing_model=PricingModel.BAW,
    )


def _cboe_row_to_contract(
    row: pd.Series[float],
    ticker: str,
    expiration: date,
) -> OptionContract | None:
    """Convert a single CBOE chain DataFrame row to an ``OptionContract``.

    Uses defensive field mapping — checks if columns exist before accessing.
    Returns ``None`` if the row lacks required fields (strike, option_type).

    Args:
        row: A single row from the CBOE chain DataFrame.
        ticker: The underlying ticker symbol.
        expiration: The expiration date for this chain.

    Returns:
        A fully constructed ``OptionContract`` or ``None`` if required data is missing.
    """
    # --- Required fields ---
    strike = safe_decimal(row.get("strike"))
    if strike is None or strike <= Decimal("0"):
        logger.debug("Skipping CBOE row with invalid strike: %r", row.get("strike"))
        return None

    # option_type: "call" or "put" from CBOE
    raw_type = row.get("option_type")
    if raw_type is None:
        logger.debug("Skipping CBOE row with missing option_type")
        return None

    type_str = str(raw_type).strip().lower()
    if type_str == "call":
        option_type = OptionType.CALL
    elif type_str == "put":
        option_type = OptionType.PUT
    else:
        logger.debug("Skipping CBOE row with unknown option_type: %r", raw_type)
        return None

    # --- Price fields (safe defaults) ---
    bid = safe_decimal(row.get("bid")) or Decimal("0")
    ask = safe_decimal(row.get("ask")) or Decimal("0")
    last = (
        safe_decimal(row.get("last_price")) or safe_decimal(row.get("lastPrice")) or Decimal("0")
    )
    volume = safe_int(row.get("volume")) or 0
    open_interest = safe_int(row.get("open_interest")) or safe_int(row.get("openInterest")) or 0

    # --- IV fields (defensive — may or may not be present) ---
    bid_iv: float | None = None
    ask_iv: float | None = None
    market_iv: float = 0.0

    # Check for separate bid/ask IV columns
    if "bid_iv" in row.index:
        bid_iv = safe_float(row.get("bid_iv"))
    if "ask_iv" in row.index:
        ask_iv = safe_float(row.get("ask_iv"))

    # Compute market_iv: prefer implied_volatility column, fall back to mid of bid/ask IV
    raw_iv = safe_float(row.get("implied_volatility"))
    if raw_iv is not None and raw_iv >= 0.0:
        market_iv = raw_iv
    elif raw_iv is None:
        # Try impliedVolatility (alternate column name)
        raw_iv_alt = safe_float(row.get("impliedVolatility"))
        if raw_iv_alt is not None and raw_iv_alt >= 0.0:
            market_iv = raw_iv_alt
        elif bid_iv is not None and ask_iv is not None:
            market_iv = (bid_iv + ask_iv) / 2.0

    # --- Greeks (defensive — may or may not be present) ---
    delta = safe_float(row.get("delta")) if "delta" in row.index else None
    gamma = safe_float(row.get("gamma")) if "gamma" in row.index else None
    theta = safe_float(row.get("theta")) if "theta" in row.index else None
    vega = safe_float(row.get("vega")) if "vega" in row.index else None
    rho = safe_float(row.get("rho")) if "rho" in row.index else None

    greeks = _validate_greeks(delta, gamma, theta, vega, rho)
    greeks_source = GreeksSource.MARKET if greeks is not None else None

    return OptionContract(
        ticker=ticker,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        bid=bid,
        ask=ask,
        last=last,
        volume=volume,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=market_iv,
        greeks=greeks,
        bid_iv=bid_iv,
        ask_iv=ask_iv,
        greeks_source=greeks_source,
    )


def _contracts_to_cache_bytes(contracts: list[OptionContract]) -> bytes:
    """Serialize a list of contracts to JSON bytes for caching."""
    return json.dumps([c.model_dump(mode="json") for c in contracts]).encode("utf-8")


def _cache_bytes_to_contracts(data: bytes) -> list[OptionContract]:
    """Deserialize cached JSON bytes back to a list of contracts."""
    raw: list[dict[str, object]] = json.loads(data.decode("utf-8"))
    return [OptionContract.model_validate(item) for item in raw]


class CBOEChainProvider:
    """CBOE option chain provider using OpenBB Platform SDK.

    Implements the ``ChainProvider`` protocol from ``options_data.py``. Falls
    back gracefully when the OpenBB SDK is not installed (``available`` returns
    ``False``). Never raises from ``__init__``.

    Args:
        config: OpenBB configuration (timeouts, TTLs, feature toggles).
        cache: Two-tier service cache for chain data.
        limiter: Rate limiter for controlling request frequency.
    """

    def __init__(
        self,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        self._config = config
        self._cache = cache
        self._limiter = limiter
        self._obb = _get_obb()

    @property
    def available(self) -> bool:
        """Whether the OpenBB SDK is importable and CBOE chains are enabled."""
        return self._obb is not None and self._config.cboe_chains_enabled

    async def _obb_call(
        self,
        fn: Any,  # noqa: ANN401
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Wrap sync OpenBB call: ``to_thread`` + ``wait_for`` with timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=self._config.request_timeout,
            )
        except TimeoutError as e:
            raise DataSourceUnavailableError(
                f"CBOE via OpenBB: timeout after {self._config.request_timeout}s"
            ) from e
        except DataSourceUnavailableError:
            raise
        except Exception as e:
            raise DataSourceUnavailableError(f"CBOE via OpenBB: {e}") from e

    async def fetch_expirations(self, ticker: str) -> list[date]:
        """Fetch available expiration dates from CBOE via OpenBB.

        Calls the OpenBB derivatives chains endpoint and extracts unique
        expiration dates. Results are cached with the ``chains_cache_ttl``
        from ``OpenBBConfig``.

        Args:
            ticker: The underlying ticker symbol.

        Returns:
            Sorted list of expiration dates.

        Raises:
            DataSourceUnavailableError: When OpenBB SDK is not available,
                CBOE chains are disabled, or any SDK error occurs.
        """
        if self._obb is None:
            raise DataSourceUnavailableError("CBOE: OpenBB SDK not installed")
        if not self._config.cboe_chains_enabled:
            raise DataSourceUnavailableError("CBOE: chains not enabled in config")

        cache_key = f"cboe:expirations:{ticker}"

        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached is not None:
            raw_dates: list[str] = json.loads(cached.decode("utf-8"))
            return [datetime.strptime(d, "%Y-%m-%d").date() for d in raw_dates]

        # Fetch full chain from CBOE and extract unique expirations
        async with self._limiter:
            result = await self._obb_call(
                self._obb.derivatives.options.chains,
                ticker,
                provider="cboe",
            )

        if result is None or not hasattr(result, "to_df"):
            raise DataSourceUnavailableError(f"CBOE: no chain data returned for {ticker}")

        df: pd.DataFrame = result.to_df()
        if df.empty or "expiration" not in df.columns:
            logger.warning("CBOE chain for %s returned empty or missing expiration column", ticker)
            return []

        # Extract unique expirations
        raw_expirations = df["expiration"].dropna().unique()
        expirations: list[date] = []
        for exp_val in raw_expirations:
            if isinstance(exp_val, date) and not isinstance(exp_val, datetime):
                expirations.append(exp_val)
            elif isinstance(exp_val, datetime):
                expirations.append(exp_val.date())
            elif isinstance(exp_val, str):
                try:
                    expirations.append(datetime.strptime(exp_val, "%Y-%m-%d").date())
                except ValueError:
                    logger.debug("Skipping unparseable expiration: %r", exp_val)
            else:
                # Try pd.Timestamp conversion
                try:
                    expirations.append(pd.Timestamp(exp_val).date())
                except (ValueError, TypeError):
                    logger.debug("Skipping unparseable expiration: %r", exp_val)

        expirations = sorted(set(expirations))

        # Cache the result
        cache_bytes = json.dumps([d.isoformat() for d in expirations]).encode("utf-8")
        await self._cache.set(cache_key, cache_bytes, ttl=self._config.chains_cache_ttl)

        logger.debug("Fetched %d expirations for %s from CBOE", len(expirations), ticker)
        return expirations

    async def fetch_chain(
        self,
        ticker: str,
        expiration: date,
    ) -> list[OptionContract]:
        """Fetch option chain from CBOE for a specific expiration date.

        Maps CBOE DataFrame columns to ``OptionContract`` models with native
        Greeks (when available). Uses defensive field mapping — checks columns
        exist before accessing. All contracts are ``ExerciseStyle.AMERICAN``.

        Args:
            ticker: The underlying ticker symbol.
            expiration: The target expiration date.

        Returns:
            List of ``OptionContract`` models from CBOE data.

        Raises:
            DataSourceUnavailableError: When OpenBB SDK is not available,
                CBOE chains are disabled, or any SDK error occurs.
        """
        if self._obb is None:
            raise DataSourceUnavailableError("CBOE: OpenBB SDK not installed")
        if not self._config.cboe_chains_enabled:
            raise DataSourceUnavailableError("CBOE: chains not enabled in config")

        cache_key = f"cboe:chain:{ticker}:{expiration.isoformat()}"

        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return _cache_bytes_to_contracts(cached)

        # Fetch the full chain from CBOE
        async with self._limiter:
            result = await self._obb_call(
                self._obb.derivatives.options.chains,
                ticker,
                provider="cboe",
            )

        if result is None or not hasattr(result, "to_df"):
            raise DataSourceUnavailableError(f"CBOE: no chain data returned for {ticker}")

        df: pd.DataFrame = result.to_df()
        if df.empty:
            logger.debug("CBOE chain for %s is empty", ticker)
            await self._cache.set(
                cache_key, _contracts_to_cache_bytes([]), ttl=self._config.chains_cache_ttl
            )
            return []

        # Filter to the requested expiration
        if "expiration" in df.columns:
            # Normalize expiration column for comparison
            df_exp = pd.to_datetime(df["expiration"]).dt.date
            df = df[df_exp == expiration]

        if df.empty:
            logger.debug("No CBOE contracts for %s exp %s", ticker, expiration.isoformat())
            await self._cache.set(
                cache_key, _contracts_to_cache_bytes([]), ttl=self._config.chains_cache_ttl
            )
            return []

        # Map each row to an OptionContract
        contracts: list[OptionContract] = []
        for _, row in df.iterrows():
            contract = _cboe_row_to_contract(row, ticker, expiration)
            if contract is not None:
                contracts.append(contract)

        # Cache the result
        await self._cache.set(
            cache_key, _contracts_to_cache_bytes(contracts), ttl=self._config.chains_cache_ttl
        )

        logger.debug(
            "Fetched CBOE chain for %s exp %s: %d contracts",
            ticker,
            expiration.isoformat(),
            len(contracts),
        )
        return contracts

    async def close(self) -> None:
        """Clean up resources. No-op for CBOE provider (no persistent connections)."""
