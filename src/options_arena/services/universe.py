"""Universe service — CBOE optionable tickers and S&P 500 constituents.

Fetches the optionable ticker universe from CBOE, classifies tickers by
S&P 500 membership and GICS sector (via GitHub CSV), and provides
``MarketCapTier`` classification. Includes ETF detection and sector
filtering helpers. Two external data sources:
CBOE CSV (optionable universe) and GitHub CSV (S&P 500 constituents).
"""

import asyncio
import io
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd
import yfinance as yf
from pydantic import BaseModel

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import (
    INDUSTRY_GROUP_ALIASES,
    SECTOR_ALIASES,
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
)
from options_arena.models.market_data import TickerInfo
from options_arena.models.metadata import TickerMetadata
from options_arena.services.base import ServiceBase
from options_arena.services.cache import TTL_REFERENCE, ServiceCache
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError, InsufficientDataError

logger = logging.getLogger(__name__)

SP500_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)
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
_CACHE_KEY_SP500 = "github:reference:sp500:constituents"
_CACHE_KEY_ETFS = "yf:reference:universe:etfs"
_CACHE_KEY_NASDAQ100 = "github:reference:nasdaq100:constituents"
_CACHE_KEY_RUSSELL2000 = "meta:reference:russell2000:tickers"
_CACHE_KEY_MOST_ACTIVE = "curated:reference:most_active:tickers"

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

NASDAQ100_URL = (
    "https://raw.githubusercontent.com/Gary-Strauss/"
    "NASDAQ100_Constituents/master/data/nasdaq100_constituents.csv"
)

# Curated NASDAQ-100 fallback — well-known constituents used when GitHub CSV
# is unavailable.  Cross-referenced against the CBOE optionable list.
_NASDAQ100_FALLBACK: frozenset[str] = frozenset(
    {
        "AAPL",
        "ABNB",
        "ADBE",
        "ADI",
        "ADP",
        "ADSK",
        "AEP",
        "AMAT",
        "AMD",
        "AMGN",
        "AMZN",
        "ANSS",
        "ARM",
        "ASML",
        "AVGO",
        "AZN",
        "BIIB",
        "BKNG",
        "BKR",
        "CCEP",
        "CDNS",
        "CDW",
        "CEG",
        "CHTR",
        "CMCSA",
        "COIN",
        "COST",
        "CPRT",
        "CRWD",
        "CSCO",
        "CSGP",
        "CTAS",
        "CTSH",
        "DASH",
        "DDOG",
        "DLTR",
        "DXCM",
        "EA",
        "EXC",
        "FANG",
        "FAST",
        "FTNT",
        "GEHC",
        "GFS",
        "GILD",
        "GOOG",
        "GOOGL",
        "HON",
        "IDXX",
        "ILMN",
        "INTC",
        "INTU",
        "ISRG",
        "KDP",
        "KHC",
        "KLAC",
        "LIN",
        "LRCX",
        "LULU",
        "MAR",
        "MCHP",
        "MDB",
        "MDLZ",
        "MELI",
        "META",
        "MNST",
        "MRNA",
        "MRVL",
        "MSFT",
        "MU",
        "NFLX",
        "NVDA",
        "NXPI",
        "ODFL",
        "ON",
        "ORLY",
        "PANW",
        "PAYX",
        "PCAR",
        "PDD",
        "PEP",
        "PYPL",
        "QCOM",
        "REGN",
        "ROP",
        "ROST",
        "SBUX",
        "SMCI",
        "SNPS",
        "TEAM",
        "TMUS",
        "TSLA",
        "TTD",
        "TTWO",
        "TXN",
        "VRSK",
        "VRTX",
        "WBD",
        "WDAY",
        "XEL",
        "ZS",
    }
)

# Curated most-active options seed list — high-volume names that are reliably
# available on CBOE.  Cross-referenced against the CBOE optionable list.
_MOST_ACTIVE_SEED: frozenset[str] = frozenset(
    {
        # Mega-cap tech
        "AAPL",
        "MSFT",
        "AMZN",
        "GOOGL",
        "GOOG",
        "META",
        "NVDA",
        "TSLA",
        # Broad-market ETFs
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "VOO",
        "VTI",
        # Semiconductor
        "AMD",
        "INTC",
        "MU",
        "AVGO",
        "MRVL",
        "QCOM",
        "TXN",
        "AMAT",
        "LRCX",
        "KLAC",
        "ON",
        "NXPI",
        "SMCI",
        "ARM",
        # Software / cloud
        "CRM",
        "ORCL",
        "ADBE",
        "NOW",
        "SNOW",
        "PLTR",
        "NET",
        "DDOG",
        "CRWD",
        "ZS",
        "PANW",
        "TEAM",
        "WDAY",
        "MDB",
        "SHOP",
        # Consumer internet
        "NFLX",
        "DIS",
        "ROKU",
        "SNAP",
        "PINS",
        "SPOT",
        "UBER",
        "LYFT",
        "ABNB",
        "DASH",
        "COIN",
        "SQ",
        "PYPL",
        "HOOD",
        # Financials
        "JPM",
        "BAC",
        "C",
        "GS",
        "MS",
        "WFC",
        "SCHW",
        "BLK",
        "AXP",
        "V",
        "MA",
        # Industrials
        "BA",
        "CAT",
        "DE",
        "GE",
        "LMT",
        "RTX",
        "HON",
        "UPS",
        "FDX",
        # Energy
        "XOM",
        "CVX",
        "OXY",
        "COP",
        "SLB",
        "HAL",
        "DVN",
        "MPC",
        "PSX",
        "VLO",
        # Pharma / biotech
        "JNJ",
        "PFE",
        "MRK",
        "ABBV",
        "LLY",
        "BMY",
        "AMGN",
        "GILD",
        "MRNA",
        "BIIB",
        "REGN",
        # Healthcare
        "UNH",
        "CI",
        "HUM",
        "CVS",
        "ELV",
        "ISRG",
        # Retail / consumer
        "WMT",
        "TGT",
        "COST",
        "HD",
        "LOW",
        "NKE",
        "SBUX",
        "MCD",
        "LULU",
        # Telecom / media
        "T",
        "VZ",
        "TMUS",
        "CMCSA",
        "CHTR",
        # Real estate / REITs
        "O",
        "AMT",
        "PLD",
        "SPG",
        "WELL",
        # EV / Auto
        "RIVN",
        "LCID",
        "F",
        "GM",
        "NIO",
        # Sector ETFs
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
        # Thematic ETFs
        "SMH",
        "XBI",
        "XOP",
        "KRE",
        "XHB",
        "XRT",
        "ARKK",
        # Fixed income / commodity ETFs
        "TLT",
        "HYG",
        "GLD",
        "SLV",
        "USO",
        "GDX",
        # Volatility
        "VXX",
        "UVXY",
        "SVXY",
        # Leveraged
        "TQQQ",
        "SQQQ",
        "SOXL",
        "SOXS",
        # Chinese ADRs
        "BABA",
        "JD",
        "PDD",
        "BIDU",
        "LI",
        "XPEV",
        # Misc high-volume
        "SOFI",
        "MARA",
        "RIOT",
        "RBLX",
        "U",
        "TTWO",
        "EA",
        "ENPH",
        "SEDG",
        "FSLR",
        "RUN",
        "AAL",
        "DAL",
        "UAL",
        "CCL",
        "RCL",
        "NCLH",
        "WBA",
        "KO",
        "PEP",
        "PM",
        "MO",
        "GME",
        "AMC",
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
    sub_industry: str | None = None


class UniverseService(ServiceBase[ServiceConfig]):
    """Fetches optionable ticker universe and S&P 500 classification data.

    Uses CBOE for the list of optionable tickers and a GitHub-hosted CSV for
    S&P 500 constituency and GICS sector mapping. Inherits cache, config, and
    rate-limiter management from :class:`ServiceBase`.

    Args:
        config: Service configuration with timeouts and rate limits.
        cache: Two-tier cache for storing fetched data.
        limiter: Rate limiter for external API calls.
    """

    _limiter: RateLimiter  # Override: always non-None (required by constructor)

    def __init__(
        self,
        config: ServiceConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        super().__init__(config, cache, limiter)
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
                "Accept": "text/html, text/plain, text/csv",
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
            self._log.debug("CBOE universe cache hit: %d tickers", len(tickers))
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

        self._log.info("CBOE universe fetched: %d optionable tickers", len(tickers))

        # Cache for 24 hours
        await self._cache.set(
            _CACHE_KEY_CBOE,
            json.dumps(tickers).encode(),
            ttl=TTL_REFERENCE,
        )

        return tickers

    async def fetch_sp500_constituents(self) -> list[SP500Constituent]:
        """Fetch S&P 500 constituents with GICS sector classification from GitHub CSV.

        Downloads a CSV from the ``datasets/s-and-p-500-companies`` repository and
        parses it with ``pd.read_csv``. Translates tickers from dot format (``.``)
        to yfinance dash format (``-``). Results are cached for 24 hours.

        Returns:
            List of ``SP500Constituent`` models (ticker + sector).

        Raises:
            InsufficientDataError: If the CSV schema has drifted (missing required
                columns) or no data is returned.
            DataSourceUnavailableError: If GitHub is unreachable.
        """
        # Check cache first
        cached = await self._cache.get(_CACHE_KEY_SP500)
        if cached is not None:
            raw: list[dict[str, str]] = json.loads(cached.decode())
            constituents = [SP500Constituent.model_validate(item) for item in raw]
            self._log.debug("S&P 500 cache hit: %d constituents", len(constituents))
            return constituents

        # Fetch CSV from GitHub, parse with pd.read_csv
        async with self._limiter:
            try:
                response = await asyncio.wait_for(
                    self._client.get(SP500_URL),
                    timeout=self._config.yfinance_timeout,
                )
                response.raise_for_status()
                df: pd.DataFrame = await asyncio.wait_for(
                    asyncio.to_thread(pd.read_csv, io.StringIO(response.text)),
                    timeout=self._config.yfinance_timeout,
                )
            except TimeoutError as exc:
                raise DataSourceUnavailableError(
                    f"GitHub: timeout after {self._config.yfinance_timeout}s"
                ) from exc
            except Exception as exc:
                raise DataSourceUnavailableError(f"GitHub: {exc}") from exc

        # Validate required columns exist
        actual_columns = set(df.columns)
        if not actual_columns >= SP500_REQUIRED_COLUMNS:
            missing = SP500_REQUIRED_COLUMNS - actual_columns
            raise InsufficientDataError(
                f"S&P 500 CSV missing columns: {missing}. Found: {actual_columns}"
            )

        if df.empty:
            raise InsufficientDataError("S&P 500 CSV is empty")

        # Translate tickers: '.' → '-' for yfinance compatibility (BRK.B → BRK-B)
        df["Symbol"] = df["Symbol"].str.strip().str.replace(".", "-", regex=False)

        has_sub_industry = "GICS Sub-Industry" in df.columns
        constituents = [
            SP500Constituent(
                ticker=row["Symbol"],
                sector=row["GICS Sector"],
                sub_industry=(
                    v.strip() or None
                    if has_sub_industry
                    and isinstance(v := row.get("GICS Sub-Industry"), str)
                    and v.strip()
                    else None
                ),
            )
            for _, row in df.iterrows()
        ]

        self._log.info("S&P 500 constituents fetched: %d tickers", len(constituents))

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
            self._log.debug("ETF universe cache hit: %d tickers", len(etf_tickers))
            return etf_tickers

        # Fetch CBOE optionable list (uses its own cache)
        optionable = await self.fetch_optionable_tickers()
        optionable_set = frozenset(optionable)

        # Cross-reference seed list with CBOE — only check tickers that are optionable
        candidates = sorted(_ETF_SEED_LIST & optionable_set)

        if not candidates:
            self._log.warning("No ETF seed tickers found in CBOE optionable list")
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
                self._log.debug("ETF check failed for %s: %s", ticker, result)
                # Include seed tickers even on yfinance failure — seed list
                # is curated and reliable
                confirmed_etfs.append(ticker)
            elif result:
                confirmed_etfs.append(ticker)

        confirmed_etfs.sort()

        self._log.info("ETF universe detected: %d tickers", len(confirmed_etfs))

        # Cache for 24 hours
        await self._cache.set(
            _CACHE_KEY_ETFS,
            json.dumps(confirmed_etfs).encode(),
            ttl=TTL_REFERENCE,
        )

        return confirmed_etfs

    async def fetch_nasdaq100_constituents(self) -> list[str]:
        """Fetch NASDAQ-100 constituents from GitHub CSV with CBOE cross-ref.

        Downloads a CSV from the ``datasets/nasdaq-100`` repository and
        extracts ticker symbols. Cross-references against the CBOE optionable
        universe and falls back to a curated list (~100 tickers) on any
        failure. Results are cached for 24 hours.

        Never raises — returns empty list on total failure.

        Returns:
            Sorted, deduplicated list of NASDAQ-100 ticker symbols that are
            optionable on CBOE.
        """
        # Check cache first
        try:
            cached = await self._cache.get(_CACHE_KEY_NASDAQ100)
            if cached is not None:
                tickers: list[str] = json.loads(cached.decode())
                self._log.debug("NASDAQ-100 cache hit: %d tickers", len(tickers))
                return tickers
        except Exception:
            self._log.warning("NASDAQ-100 cache read failed, fetching fresh", exc_info=True)

        raw_tickers: list[str] = []
        try:
            async with self._limiter:
                response = await asyncio.wait_for(
                    self._client.get(NASDAQ100_URL),
                    timeout=self._config.yfinance_timeout,
                )
                response.raise_for_status()
                df: pd.DataFrame = await asyncio.wait_for(
                    asyncio.to_thread(pd.read_csv, io.StringIO(response.text)),
                    timeout=self._config.yfinance_timeout,
                )

            # Look for a ticker/symbol column
            ticker_col: str | None = None
            for col_name in df.columns:
                col_lower = str(col_name).strip().lower()
                if col_lower in ("symbol", "ticker", "stock symbol"):
                    ticker_col = str(col_name)
                    break
            if ticker_col is None and len(df.columns) > 0:
                ticker_col = str(df.columns[0])

            if ticker_col is not None:
                raw_symbols = df[ticker_col].dropna().astype(str).str.strip().str.upper().tolist()
                raw_tickers = UniverseService._filter_symbols(raw_symbols)
                self._log.info("NASDAQ-100 CSV fetched: %d raw tickers", len(raw_tickers))
        except Exception:
            self._log.warning("NASDAQ-100 CSV fetch failed, using curated fallback", exc_info=True)

        # Fallback to curated list if CSV failed or was empty
        if not raw_tickers:
            raw_tickers = sorted(_NASDAQ100_FALLBACK)
            self._log.info("NASDAQ-100 using curated fallback: %d tickers", len(raw_tickers))

        # CBOE cross-reference
        try:
            optionable = await self.fetch_optionable_tickers()
            optionable_set = frozenset(optionable)
            tickers = sorted(t for t in raw_tickers if t in optionable_set)
        except Exception:
            self._log.warning("CBOE cross-ref failed for NASDAQ-100, returning raw list")
            tickers = sorted(set(raw_tickers))

        self._log.info("NASDAQ-100 universe: %d optionable tickers", len(tickers))

        # Cache for 24 hours
        try:
            await self._cache.set(
                _CACHE_KEY_NASDAQ100,
                json.dumps(tickers).encode(),
                ttl=TTL_REFERENCE,
            )
        except Exception:
            self._log.warning("NASDAQ-100 cache write failed", exc_info=True)

        return tickers

    async def fetch_russell2000_tickers(
        self,
        repo: object | None = None,
    ) -> list[str]:
        """Fetch Russell 2000-like small/micro-cap tickers from the metadata index.

        Queries ``Repository.get_all_ticker_metadata()`` and filters for
        ``market_cap_tier`` in ``{SMALL, MICRO}``. Cross-references against
        the CBOE optionable universe. Results are cached for 24 hours.

        Never raises — returns empty list on failure or missing repo.

        Args:
            repo: An optional ``Repository`` instance. If ``None``, returns
                an empty list immediately.

        Returns:
            Sorted, deduplicated list of small/micro-cap optionable tickers.
        """
        # Check cache first
        try:
            cached = await self._cache.get(_CACHE_KEY_RUSSELL2000)
            if cached is not None:
                tickers: list[str] = json.loads(cached.decode())
                self._log.debug("Russell 2000 cache hit: %d tickers", len(tickers))
                return tickers
        except Exception:
            self._log.warning("Russell 2000 cache read failed, fetching fresh", exc_info=True)

        if repo is None:
            self._log.warning("Russell 2000 fetch skipped: no Repository provided")
            return []

        try:
            # Duck-type check: repo must have get_all_ticker_metadata()
            if not hasattr(repo, "get_all_ticker_metadata"):
                self._log.warning("Russell 2000 fetch skipped: repo lacks get_all_ticker_metadata")
                return []

            # hasattr guard above ensures get_all_ticker_metadata exists;
            # cast to Any so mypy allows attribute access on duck-typed repo.
            repo_any: Any = repo
            all_metadata: list[TickerMetadata] = await repo_any.get_all_ticker_metadata()
            small_micro_tickers = sorted(
                m.ticker
                for m in all_metadata
                if m.market_cap_tier in {MarketCapTier.SMALL, MarketCapTier.MICRO}
            )

            if not small_micro_tickers:
                self._log.info("Russell 2000: no small/micro-cap tickers in metadata index")
                try:
                    await self._cache.set(
                        _CACHE_KEY_RUSSELL2000,
                        json.dumps([]).encode(),
                        ttl=TTL_REFERENCE,
                    )
                except Exception:
                    self._log.warning("Russell 2000 cache write failed", exc_info=True)
                return []

            # CBOE cross-reference
            try:
                optionable = await self.fetch_optionable_tickers()
                optionable_set = frozenset(optionable)
                tickers = sorted(t for t in small_micro_tickers if t in optionable_set)
            except Exception:
                self._log.warning("CBOE cross-ref failed for Russell 2000, returning raw list")
                tickers = small_micro_tickers

            self._log.info("Russell 2000 universe: %d optionable tickers", len(tickers))

            # Cache for 24 hours
            try:
                await self._cache.set(
                    _CACHE_KEY_RUSSELL2000,
                    json.dumps(tickers).encode(),
                    ttl=TTL_REFERENCE,
                )
            except Exception:
                self._log.warning("Russell 2000 cache write failed", exc_info=True)

            return tickers

        except Exception:
            self._log.warning("Russell 2000 fetch failed", exc_info=True)
            return []

    async def fetch_most_active(self) -> list[str]:
        """Fetch most actively traded options tickers with CBOE cross-ref.

        Uses a curated seed list of ~250 high-volume names cross-referenced
        against the CBOE optionable universe. Results are cached for 24 hours.

        Never raises — returns empty list on failure.

        Returns:
            Sorted, deduplicated list of most-active optionable tickers.
        """
        # Check cache first
        try:
            cached = await self._cache.get(_CACHE_KEY_MOST_ACTIVE)
            if cached is not None:
                tickers: list[str] = json.loads(cached.decode())
                self._log.debug("Most Active cache hit: %d tickers", len(tickers))
                return tickers
        except Exception:
            self._log.warning("Most Active cache read failed, fetching fresh", exc_info=True)

        try:
            # CBOE cross-reference
            optionable = await self.fetch_optionable_tickers()
            optionable_set = frozenset(optionable)
            tickers = sorted(t for t in _MOST_ACTIVE_SEED if t in optionable_set)
        except Exception:
            self._log.warning("CBOE cross-ref failed for Most Active, returning seed list")
            tickers = sorted(_MOST_ACTIVE_SEED)

        self._log.info("Most Active universe: %d tickers", len(tickers))

        # Cache for 24 hours
        try:
            await self._cache.set(
                _CACHE_KEY_MOST_ACTIVE,
                json.dumps(tickers).encode(),
                ttl=TTL_REFERENCE,
            )
        except Exception:
            self._log.warning("Most Active cache write failed", exc_info=True)

        return tickers

    async def close(self) -> None:
        """Close the shared httpx client and release base resources."""
        await self._client.aclose()
        await super().close()

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
            self._log.debug("ETF check timeout for %s", ticker)
            raise
        except Exception as exc:
            self._log.debug("ETF check error for %s: %s", ticker, exc)
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


def classify_market_cap(market_cap: int | None) -> MarketCapTier | None:
    """Classify a market capitalisation value into a ``MarketCapTier``.

    Standalone version of ``UniverseService.classify_market_cap`` — usable
    without a service instance.

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


def map_yfinance_to_metadata(ticker_info: TickerInfo) -> TickerMetadata:
    """Map yfinance ``TickerInfo`` to typed ``TickerMetadata`` using GICS alias dicts.

    Resolves ``sector`` and ``industry`` strings from yfinance to typed GICS enums
    via ``SECTOR_ALIASES`` and ``INDUSTRY_GROUP_ALIASES``. Classifies market cap
    into a ``MarketCapTier``. Preserves original raw strings for audit.

    Unmapped sector/industry strings are logged at WARNING level. The sentinel
    value ``"Unknown"`` (the default from yfinance) is treated as absent and
    does **not** trigger a warning.

    Args:
        ticker_info: A ``TickerInfo`` model from the market data service.

    Returns:
        A frozen ``TickerMetadata`` snapshot with resolved GICS enums.
    """
    # 1. Resolve sector via _resolve_sector (canonical enum + SECTOR_ALIASES fallback)
    raw_sector = ticker_info.sector
    sector: GICSSector | None = None
    if raw_sector and raw_sector != "Unknown":
        sector = _resolve_sector(raw_sector)
        if sector is None:
            logger.warning("Unmapped yfinance sector for %s: %s", ticker_info.ticker, raw_sector)

    # 2. Resolve industry via INDUSTRY_GROUP_ALIASES
    raw_industry = ticker_info.industry
    industry_group: GICSIndustryGroup | None = None
    if raw_industry and raw_industry != "Unknown":
        industry_group = INDUSTRY_GROUP_ALIASES.get(raw_industry.strip().lower())
        if industry_group is None:
            logger.warning(
                "Unmapped yfinance industry for %s: %s", ticker_info.ticker, raw_industry
            )

    # 3. Classify market cap
    market_cap_tier: MarketCapTier | None = None
    if ticker_info.market_cap is not None:
        market_cap_tier = classify_market_cap(ticker_info.market_cap)

    # 4. Build TickerMetadata
    return TickerMetadata(
        ticker=ticker_info.ticker.upper(),
        sector=sector,
        industry_group=industry_group,
        market_cap_tier=market_cap_tier,
        company_name=ticker_info.company_name,
        raw_sector=raw_sector,
        raw_industry=raw_industry,
        last_updated=datetime.now(UTC),
    )
