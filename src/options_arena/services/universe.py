"""Universe service — CBOE optionable tickers and S&P 500 constituents.

Fetches the optionable ticker universe from CBOE, classifies tickers by
S&P 500 membership and GICS sector (via Wikipedia), and provides
``MarketCapTier`` classification. Includes ETF detection and sector
filtering helpers. Two external data sources:
CBOE CSV (optionable universe) and Wikipedia table (S&P 500 constituents).
"""

import asyncio
import io
import json
import logging
import re
from typing import Any

import httpx
import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]
from pydantic import BaseModel

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import (
    INDUSTRY_GROUP_ALIASES,
    SECTOR_ALIASES,
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
)
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
_CACHE_KEY_ETFS = "yf:reference:universe:etfs"

# Curated ETF seed list — well-known optionable ETFs that are reliably available
# on CBOE. Cross-referenced against the CBOE optionable list.
_ETF_SEED_LIST: frozenset[str] = frozenset(
    {
        # Broad market
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "VOO",
        "VTI",
        "IVV",
        "RSP",
        # Sector SPDR
        "XLF",
        "XLE",
        "XLK",
        "XLV",
        "XLI",
        "XLP",
        "XLU",
        "XLY",
        "XLB",
        "XLRE",
        "XLC",
        # Other sector / thematic
        "SMH",
        "XBI",
        "XOP",
        "KRE",
        "XHB",
        "XRT",
        "ARKK",
        "ARKG",
        # Fixed income
        "TLT",
        "HYG",
        "LQD",
        "TIP",
        "BND",
        "AGG",
        "SHY",
        "IEF",
        # International
        "EEM",
        "EFA",
        "FXI",
        "INDA",
        "EWZ",
        "EWJ",
        "VWO",
        "IEMG",
        # Commodity
        "GLD",
        "SLV",
        "USO",
        "GDX",
        "GDXJ",
        "UNG",
        # Volatility
        "VXX",
        "UVXY",
        "SVXY",
        # Leveraged
        "TQQQ",
        "SQQQ",
        "SPXL",
        "SPXS",
        "SOXL",
        "SOXS",
        # Real estate
        "VNQ",
        "IYR",
    }
)

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

    async def fetch_etf_tickers(self) -> list[str]:
        """Fetch ETF tickers from the CBOE optionable list with 24h cache.

        Uses a curated seed list of well-known ETFs cross-referenced against
        the CBOE optionable universe. For any seed ticker present in the CBOE
        list, verifies ETF status via yfinance ``Ticker.info["quoteType"]``.
        Uses ``asyncio.gather(return_exceptions=True)`` for batch fault
        isolation so one failed lookup never crashes the entire detection.

        Returns:
            Sorted, deduplicated list of ETF ticker symbols.

        Raises:
            DataSourceUnavailableError: If CBOE is unreachable (propagated
                from ``fetch_optionable_tickers``).
        """
        # Check cache first
        cached = await self._cache.get(_CACHE_KEY_ETFS)
        if cached is not None:
            etf_tickers: list[str] = json.loads(cached.decode())
            logger.debug("ETF universe cache hit: %d tickers", len(etf_tickers))
            return etf_tickers

        # Fetch CBOE optionable list (uses its own cache)
        optionable = await self.fetch_optionable_tickers()
        optionable_set = frozenset(optionable)

        # Cross-reference seed list with CBOE — only check tickers that are optionable
        candidates = sorted(_ETF_SEED_LIST & optionable_set)

        if not candidates:
            logger.warning("No ETF seed tickers found in CBOE optionable list")
            await self._cache.set(
                _CACHE_KEY_ETFS,
                json.dumps([]).encode(),
                ttl=TTL_REFERENCE,
            )
            return []

        # Batch-check via yfinance with fault isolation
        tasks = [self._check_etf(ticker) for ticker in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        confirmed_etfs: list[str] = []
        for ticker, result in zip(candidates, results, strict=True):
            if isinstance(result, Exception):
                logger.debug("ETF check failed for %s: %s", ticker, result)
                # Include seed tickers even on yfinance failure — seed list
                # is curated and reliable
                confirmed_etfs.append(ticker)
            elif result:
                confirmed_etfs.append(ticker)

        confirmed_etfs.sort()

        logger.info("ETF universe detected: %d tickers", len(confirmed_etfs))

        # Cache for 24 hours
        await self._cache.set(
            _CACHE_KEY_ETFS,
            json.dumps(confirmed_etfs).encode(),
            ttl=TTL_REFERENCE,
        )

        return confirmed_etfs

    async def close(self) -> None:
        """Close the shared httpx client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_etf(self, ticker: str) -> bool:
        """Check if a ticker is an ETF via yfinance quoteType.

        Args:
            ticker: Ticker symbol to check.

        Returns:
            ``True`` if yfinance reports ``quoteType == "ETF"``, ``False`` otherwise.
        """
        try:
            info: dict[str, Any] = await asyncio.wait_for(
                asyncio.to_thread(lambda: yf.Ticker(ticker).info),
                timeout=self._config.yfinance_timeout,
            )
            quote_type = info.get("quoteType", "")
            return str(quote_type).upper() == "ETF"
        except TimeoutError:
            logger.debug("ETF check timeout for %s", ticker)
            raise
        except Exception as exc:
            logger.debug("ETF check error for %s: %s", ticker, exc)
            raise

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


# ---------------------------------------------------------------------------
# Standalone helpers — pure functions, no service instance needed
# ---------------------------------------------------------------------------


def build_sector_map(constituents: list[SP500Constituent]) -> dict[str, GICSSector]:
    """Build a ticker-to-GICS-sector mapping from S&P 500 constituents.

    Handles Wikipedia sector strings that may differ from canonical GICS names
    by trying direct ``GICSSector(sector_str)`` construction, then falling back
    to ``SECTOR_ALIASES`` for short names and variant formats.

    Args:
        constituents: List of ``SP500Constituent`` models (ticker + sector string).

    Returns:
        Mapping from ticker symbol to ``GICSSector`` enum. Tickers whose sector
        string cannot be resolved are silently skipped with a warning log.
    """
    result: dict[str, GICSSector] = {}
    for constituent in constituents:
        sector = _resolve_sector(constituent.sector)
        if sector is not None:
            result[constituent.ticker] = sector
        else:
            logger.warning(
                "Could not resolve sector %r for ticker %s",
                constituent.sector,
                constituent.ticker,
            )
    return result


def filter_by_sectors(
    tickers: list[str],
    sectors: list[GICSSector],
    sp500_map: dict[str, GICSSector],
) -> list[str]:
    """Filter tickers by GICS sector membership (OR logic).

    Pure function. If ``sectors`` is empty, returns all tickers unchanged.
    Only tickers present in ``sp500_map`` can match; tickers not in the map
    are excluded when sector filtering is active.

    Args:
        tickers: List of ticker symbols to filter.
        sectors: GICS sectors to include (OR logic — ticker matches if in any).
        sp500_map: Mapping from ticker to ``GICSSector`` (from ``build_sector_map``).

    Returns:
        Filtered list of tickers belonging to at least one of the specified sectors.
        Preserves input order. If ``sectors`` is empty, returns ``tickers`` unchanged.
    """
    if not sectors:
        return tickers

    sector_set = frozenset(sectors)
    return [t for t in tickers if sp500_map.get(t) in sector_set]


def build_industry_group_map(
    industry_data: dict[str, str],
) -> dict[str, GICSIndustryGroup]:
    """Build a ticker-to-GICS-industry-group mapping from raw industry strings.

    Maps yfinance free-text industry strings (e.g., ``"Semiconductors"``,
    ``"Software\u2014Application"``) through ``INDUSTRY_GROUP_ALIASES``.
    Unmapped industries are excluded from the result and logged at DEBUG.

    Args:
        industry_data: Mapping from ticker symbol to raw industry string
            (typically from yfinance ``Ticker.info["industry"]``).

    Returns:
        Mapping from ticker symbol to ``GICSIndustryGroup`` enum. Tickers
        whose industry string cannot be resolved are silently excluded.
    """
    result: dict[str, GICSIndustryGroup] = {}
    for ticker, raw_industry in industry_data.items():
        if not isinstance(raw_industry, str) or not raw_industry.strip():
            logger.debug("Unknown industry for %s: %r", ticker, raw_industry)
            continue
        key = raw_industry.strip().lower()
        ig = INDUSTRY_GROUP_ALIASES.get(key)
        if ig is not None:
            result[ticker] = ig
        else:
            logger.debug("Unknown industry for %s: %s", ticker, raw_industry)
    return result


def filter_by_industry_groups(
    tickers: list[str],
    industry_groups: list[GICSIndustryGroup],
    ig_map: dict[str, GICSIndustryGroup],
) -> list[str]:
    """Filter tickers by GICS industry group membership (OR logic).

    Pure function. If ``industry_groups`` is empty, returns all tickers
    unchanged. Only tickers present in ``ig_map`` can match; tickers not
    in the map are excluded when industry group filtering is active.

    Args:
        tickers: List of ticker symbols to filter.
        industry_groups: Industry groups to include (OR logic).
        ig_map: Mapping from ticker to ``GICSIndustryGroup`` (from
            ``build_industry_group_map``).

    Returns:
        Filtered list of tickers belonging to at least one of the specified
        industry groups. Preserves input order. If ``industry_groups`` is
        empty, returns ``tickers`` unchanged.
    """
    if not industry_groups:
        return tickers

    ig_set = frozenset(industry_groups)
    return [t for t in tickers if ig_map.get(t) in ig_set]


def _resolve_sector(sector_str: str) -> GICSSector | None:
    """Resolve a sector string to a GICSSector enum value.

    Tries direct enum construction first, then falls back to SECTOR_ALIASES
    with case-insensitive matching.

    Args:
        sector_str: Sector name from Wikipedia or other source.

    Returns:
        Resolved ``GICSSector`` or ``None`` if unrecognised.
    """
    # Try direct enum construction (handles canonical values like "Energy")
    try:
        return GICSSector(sector_str.strip())
    except ValueError:
        pass

    # Fall back to aliases (lowercase lookup)
    key = sector_str.strip().lower()
    return SECTOR_ALIASES.get(key)
