"""Universe service — CBOE optionable tickers and S&P 500 constituents.

Fetches the optionable ticker universe from CBOE, classifies tickers by
S&P 500 membership and GICS sector (via Wikipedia), and provides
``MarketCapTier`` classification. Two external data sources:
CBOE CSV (optionable universe) and Wikipedia table (S&P 500 constituents).
"""

import asyncio
import io
import json
import logging
import re

import httpx
import pandas as pd
from pydantic import BaseModel

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import MarketCapTier
from options_arena.services.cache import TTL_REFERENCE, ServiceCache
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError, InsufficientDataError

logger = logging.getLogger(__name__)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_REQUIRED_COLUMNS: frozenset[str] = frozenset({"Symbol", "GICS Sector"})

CBOE_URL = (
    "https://www.cboe.com/markets/us/options/symbol-directory/equity-index-options?download=csv"
)

# Characters that indicate an index symbol (not an equity)
INDEX_SYMBOL_CHARS: frozenset[str] = frozenset({"^", "$", "/"})

# Valid ticker: 1-5 uppercase letters, optionally followed by a dot and 1 letter (BRK.B)
_TICKER_RE: re.Pattern[str] = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

# Cache keys
_CACHE_KEY_CBOE = "cboe:reference:universe:optionable"
_CACHE_KEY_SP500 = "wiki:reference:sp500:constituents"

# Market cap tier boundaries in dollars
_MEGA_CAP_THRESHOLD: int = 200_000_000_000
_LARGE_CAP_THRESHOLD: int = 10_000_000_000
_MID_CAP_THRESHOLD: int = 2_000_000_000
_SMALL_CAP_THRESHOLD: int = 300_000_000


class SP500Constituent(BaseModel):
    """A single S&P 500 constituent with its GICS sector classification.

    Typed replacement for ``dict[str, str]`` (ticker -> sector mapping).
    """

    ticker: str
    sector: str


class UniverseService:
    """Fetches optionable ticker universe and S&P 500 classification data.

    Uses CBOE for the list of optionable tickers and Wikipedia for
    S&P 500 constituency and GICS sector mapping.

    Args:
        config: Service configuration with timeouts and rate limits.
        cache: Two-tier cache for storing fetched data.
        limiter: Rate limiter for external API calls.
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
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "OptionsArena/1.0 "
                    "(https://github.com/jobu711/options_arena; "
                    "options analysis tool) "
                    "python-httpx"
                ),
                "Accept": "text/html",
            },
        )

    async def fetch_optionable_tickers(self) -> list[str]:
        """Fetch CBOE optionable universe as a deduplicated list of ticker symbols.

        Downloads the CBOE directory CSV, extracts ticker symbols, filters out
        index symbols (containing ``^``, ``$``, or ``/``), strips whitespace,
        and deduplicates. Results are cached for 24 hours.

        Returns:
            Sorted, deduplicated list of optionable ticker symbols.

        Raises:
            DataSourceUnavailableError: If CBOE is unreachable or returns an error.
            InsufficientDataError: If no valid tickers are found in the CSV.
        """
        # Check cache first
        cached = await self._cache.get(_CACHE_KEY_CBOE)
        if cached is not None:
            tickers: list[str] = json.loads(cached.decode())
            logger.debug("CBOE universe cache hit: %d tickers", len(tickers))
            return tickers

        # Fetch from CBOE
        async with self._limiter:
            try:
                response = await asyncio.wait_for(
                    self._client.get(CBOE_URL),
                    timeout=self._config.cboe_timeout,
                )
                response.raise_for_status()
            except TimeoutError as exc:
                raise DataSourceUnavailableError(
                    f"CBOE: timeout after {self._config.cboe_timeout}s"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise DataSourceUnavailableError(f"CBOE: HTTP {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                raise DataSourceUnavailableError(f"CBOE: {exc}") from exc

        # Parse CSV content
        tickers = self._parse_cboe_csv(response.text)

        if not tickers:
            raise InsufficientDataError("No valid tickers found in CBOE CSV")

        logger.info("CBOE universe fetched: %d optionable tickers", len(tickers))

        # Cache for 24 hours
        await self._cache.set(
            _CACHE_KEY_CBOE,
            json.dumps(tickers).encode(),
            ttl=TTL_REFERENCE,
        )

        return tickers

    async def fetch_sp500_constituents(self) -> list[SP500Constituent]:
        """Fetch S&P 500 constituents with GICS sector classification from Wikipedia.

        Uses ``pd.read_html`` with ``attrs={"id": "constituents"}`` for stable
        table targeting. Translates tickers from Wikipedia format (``.`` separator)
        to yfinance format (``-`` separator). Results are cached for 24 hours.

        Returns:
            List of ``SP500Constituent`` models (ticker + sector).

        Raises:
            InsufficientDataError: If the Wikipedia table schema has drifted
                (missing required columns) or no data is returned.
            DataSourceUnavailableError: If Wikipedia is unreachable.
        """
        # Check cache first
        cached = await self._cache.get(_CACHE_KEY_SP500)
        if cached is not None:
            raw: list[dict[str, str]] = json.loads(cached.decode())
            constituents = [SP500Constituent.model_validate(item) for item in raw]
            logger.debug("S&P 500 cache hit: %d constituents", len(constituents))
            return constituents

        # Fetch HTML with httpx (proper User-Agent), then parse with pd.read_html
        async with self._limiter:
            try:
                response = await asyncio.wait_for(
                    self._client.get(SP500_URL),
                    timeout=self._config.yfinance_timeout,
                )
                response.raise_for_status()
                tables: list[pd.DataFrame] = await asyncio.wait_for(
                    asyncio.to_thread(
                        pd.read_html,
                        io.StringIO(response.text),
                        attrs={"id": "constituents"},
                    ),
                    timeout=self._config.yfinance_timeout,
                )
            except TimeoutError as exc:
                raise DataSourceUnavailableError(
                    f"Wikipedia: timeout after {self._config.yfinance_timeout}s"
                ) from exc
            except Exception as exc:
                raise DataSourceUnavailableError(f"Wikipedia: {exc}") from exc

        if not tables:
            raise InsufficientDataError("No tables found at Wikipedia S&P 500 page")

        df = tables[0]

        # Validate required columns exist
        actual_columns = set(df.columns)
        if not actual_columns >= SP500_REQUIRED_COLUMNS:
            missing = SP500_REQUIRED_COLUMNS - actual_columns
            raise InsufficientDataError(
                f"Wikipedia S&P 500 table missing columns: {missing}. Found: {actual_columns}"
            )

        if df.empty:
            raise InsufficientDataError("Wikipedia S&P 500 table is empty")

        # Translate tickers: '.' → '-' for yfinance compatibility (BRK.B → BRK-B)
        df["Symbol"] = df["Symbol"].str.strip().str.replace(".", "-", regex=False)

        constituents = [
            SP500Constituent(ticker=row["Symbol"], sector=row["GICS Sector"])
            for _, row in df.iterrows()
        ]

        logger.info("S&P 500 constituents fetched: %d tickers", len(constituents))

        # Cache for 24 hours
        await self._cache.set(
            _CACHE_KEY_SP500,
            json.dumps([c.model_dump() for c in constituents]).encode(),
            ttl=TTL_REFERENCE,
        )

        return constituents

    def classify_market_cap(self, market_cap: int | None) -> MarketCapTier | None:
        """Classify a market capitalisation value into a tier.

        Args:
            market_cap: Market capitalisation in dollars, or ``None`` if unknown.

        Returns:
            The corresponding ``MarketCapTier``, or ``None`` if input is ``None``.
        """
        if market_cap is None:
            return None

        if market_cap >= _MEGA_CAP_THRESHOLD:
            return MarketCapTier.MEGA
        if market_cap >= _LARGE_CAP_THRESHOLD:
            return MarketCapTier.LARGE
        if market_cap >= _MID_CAP_THRESHOLD:
            return MarketCapTier.MID
        if market_cap >= _SMALL_CAP_THRESHOLD:
            return MarketCapTier.SMALL
        return MarketCapTier.MICRO

    async def close(self) -> None:
        """Close the shared httpx client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_cboe_csv(content: str) -> list[str]:
        """Parse CBOE CSV content and extract valid ticker symbols.

        Filters out index symbols (containing ``^``, ``$``, ``/``),
        strips whitespace, and deduplicates. Returns a sorted list.
        """
        try:
            df = pd.read_csv(io.StringIO(content), skipinitialspace=True)
        except Exception:
            logger.warning("Failed to parse CBOE CSV with pandas, trying line-based parsing")
            return UniverseService._parse_cboe_lines(content)

        # Look for a column that contains ticker symbols
        # CBOE CSV may have varying column names
        ticker_column: str | None = None
        for col_name in df.columns:
            col_lower = str(col_name).strip().lower()
            if col_lower in ("symbol", "ticker", "stock symbol"):
                ticker_column = str(col_name)
                break

        # If no obvious column found, use the first column
        if ticker_column is None and len(df.columns) > 0:
            ticker_column = str(df.columns[0])

        if ticker_column is None:
            logger.warning("No columns found in CBOE CSV")
            return []

        raw_symbols: list[str] = df[ticker_column].dropna().astype(str).tolist()
        return UniverseService._filter_symbols(raw_symbols)

    @staticmethod
    def _parse_cboe_lines(content: str) -> list[str]:
        """Fallback line-based parser for CBOE CSV content.

        Handles the two-column format: ``"TICKER","Company Name"``
        and filters out header/schedule rows via the ticker regex in
        ``_filter_symbols``.
        """
        raw_symbols: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Extract first comma-delimited field, stripping quotes
            token = stripped.split(",")[0].strip().strip('"')
            if token:
                raw_symbols.append(token)
        return UniverseService._filter_symbols(raw_symbols)

    @staticmethod
    def _filter_symbols(raw_symbols: list[str]) -> list[str]:
        """Filter, deduplicate, and sort ticker symbols.

        Removes index symbols (containing ``^``, ``$``, ``/``), rejects
        non-ticker strings (HTML fragments, CSS, etc.), strips whitespace,
        deduplicates, and returns sorted.
        """
        seen: set[str] = set()
        result: list[str] = []

        for symbol in raw_symbols:
            cleaned = symbol.strip().strip('"')
            if not cleaned:
                continue

            # Filter out index symbols
            if any(char in cleaned for char in INDEX_SYMBOL_CHARS):
                continue

            upper = cleaned.upper()

            # Validate against ticker pattern (rejects HTML/CSS junk)
            if not _TICKER_RE.match(upper):
                continue

            if upper not in seen:
                seen.add(upper)
                result.append(upper)

        result.sort()
        return result
