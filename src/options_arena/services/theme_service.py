"""Theme service for ETF-based thematic tag management.

Fetches ETF holdings via yfinance ``Ticker.funds_data.top_holdings``, builds
theme-to-ticker mappings, caches them in SQLite, and computes the "Popular
Options" theme from historical scan data. All ETF fetch errors are logged at
WARNING and return empty lists (never-raises contract).

Class-based DI with ``config`` and ``repository`` — same pattern as
``MarketDataService``, ``OpenBBService``, etc.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

from options_arena.data.repository import Repository
from options_arena.models.config import ThemeConfig
from options_arena.models.themes import THEME_ETF_MAPPING, ThemeSnapshot

logger = logging.getLogger(__name__)


class ThemeService:
    """Fetches ETF holdings, builds theme-to-ticker mappings, caches in SQLite.

    All public methods follow the never-raises contract for ETF fetch operations:
    exceptions are caught, logged at WARNING, and empty results are returned.

    Args:
        config: Theme configuration (cache TTL, feature toggle).
        repository: Typed CRUD repository for theme persistence.
    """

    def __init__(self, config: ThemeConfig, repository: Repository) -> None:
        self._config = config
        self._repo = repository
        self._last_refresh: float = 0.0  # monotonic timestamp

    async def refresh_themes(self) -> list[ThemeSnapshot]:
        """Fetch ETF holdings for all themes, build snapshots, persist to DB.

        Iterates ``THEME_ETF_MAPPING``, fetches holdings for each source ETF,
        deduplicates tickers, and creates ``ThemeSnapshot`` models. Results are
        persisted to SQLite via the repository.

        Returns:
            List of ``ThemeSnapshot`` models for all configured themes.
        """
        snapshots: list[ThemeSnapshot] = []
        now = datetime.now(UTC)

        for theme_name, etf_tickers in THEME_ETF_MAPPING.items():
            if theme_name == "Popular Options":
                # Computed from scan data, not ETF holdings
                tickers = await self._compute_popular_options()
            else:
                tickers = await self._fetch_theme_tickers(etf_tickers)

            unique_tickers = sorted(set(tickers))
            description = (
                f"Tickers from {', '.join(etf_tickers)}"
                if etf_tickers
                else "Top options by volume"
            )

            snapshot = ThemeSnapshot(
                name=theme_name,
                description=description,
                source_etfs=etf_tickers,
                tickers=unique_tickers,
                ticker_count=len(unique_tickers),
                updated_at=now,
            )
            snapshots.append(snapshot)

        await self._repo.save_themes(snapshots)
        self._last_refresh = time.monotonic()
        logger.info(
            "Refreshed %d themes with %d total tickers",
            len(snapshots),
            sum(s.ticker_count for s in snapshots),
        )
        return snapshots

    async def get_themes(self) -> list[ThemeSnapshot]:
        """Return cached themes from DB. Refresh if stale.

        If the cache TTL has expired, attempts a refresh. On refresh failure,
        falls back to existing cached data from the repository.

        Returns:
            List of ``ThemeSnapshot`` models from DB (may be empty).
        """
        if self._should_refresh():
            try:
                return await self.refresh_themes()
            except Exception:
                self._last_refresh = time.monotonic()
                logger.warning("Theme refresh failed, using cached data", exc_info=True)
        return await self._repo.get_themes()

    async def get_theme_ticker_set(self, theme_name: str) -> frozenset[str]:
        """Fast lookup: get ticker set for a specific theme.

        Args:
            theme_name: The name of the theme to look up.

        Returns:
            Frozenset of tickers for the theme, or empty frozenset if not found.
        """
        themes = await self.get_themes()
        for theme in themes:
            if theme.name == theme_name:
                return frozenset(theme.tickers)
        return frozenset()

    async def get_all_theme_sets(self) -> dict[str, frozenset[str]]:
        """Get all theme-to-ticker frozenset mappings.

        Returns:
            Dict mapping theme names to frozensets of ticker symbols.
        """
        themes = await self.get_themes()
        return {t.name: frozenset(t.tickers) for t in themes}

    def _should_refresh(self) -> bool:
        """Check if cache TTL has expired."""
        if self._last_refresh == 0.0:
            return True
        elapsed = time.monotonic() - self._last_refresh
        return elapsed > self._config.cache_ttl

    async def _fetch_theme_tickers(self, etf_tickers: list[str]) -> list[str]:
        """Fetch holdings from multiple ETFs, union all tickers. Never raises."""
        all_tickers: list[str] = []
        for etf in etf_tickers:
            holdings = await self._fetch_etf_holdings(etf)
            all_tickers.extend(holdings)
        return all_tickers

    async def _fetch_etf_holdings(self, etf_ticker: str) -> list[str]:
        """Fetch top holdings from a single ETF via yfinance. Never raises.

        Uses ``yf.Ticker(etf).funds_data.top_holdings`` which returns a pandas
        DataFrame with ticker symbols as the index (Context7-verified).

        Args:
            etf_ticker: ETF ticker symbol (e.g. ``"ARKK"``).

        Returns:
            List of ticker symbols from the ETF's top holdings.
            Empty list on any error.
        """
        try:
            ticker_obj = yf.Ticker(etf_ticker)
            # Context7-verified: funds_data.top_holdings returns a DataFrame
            # with ticker symbols as index. Access is a property chain, so we
            # wrap the entire access in to_thread to avoid blocking the event loop.
            holdings_df = await asyncio.wait_for(
                asyncio.to_thread(self._get_top_holdings, ticker_obj),
                timeout=30.0,
            )

            if holdings_df is None:
                logger.debug("No holdings data for ETF %s", etf_ticker)
                return []

            if not isinstance(holdings_df, pd.DataFrame) or holdings_df.empty:
                logger.debug("Empty holdings DataFrame for ETF %s", etf_ticker)
                return []

            # Extract ticker symbols from the index
            tickers: list[str] = [
                str(idx) for idx in holdings_df.index if isinstance(idx, str) and idx.strip()
            ]
            logger.debug("Fetched %d holdings for ETF %s", len(tickers), etf_ticker)
            return tickers

        except Exception:
            logger.warning("Failed to fetch holdings for ETF %s", etf_ticker, exc_info=True)
            return []

    @staticmethod
    def _get_top_holdings(ticker_obj: yf.Ticker) -> pd.DataFrame | None:
        """Synchronous helper to access ``ticker.funds_data.top_holdings``.

        Separated into a static method so ``asyncio.to_thread`` receives a
        callable + args, not a pre-evaluated property access.

        Args:
            ticker_obj: A yfinance Ticker instance.

        Returns:
            A pandas DataFrame of top holdings, or ``None`` if unavailable.
        """
        try:
            funds = ticker_obj.funds_data
            if funds is None:
                return None
            return funds.top_holdings  # type: ignore[no-any-return]
        except Exception:
            return None

    async def _compute_popular_options(self) -> list[str]:
        """Top 50 tickers by average options volume from recent scans. Never raises.

        Queries the repository for recent scan scores and extracts tickers
        that appear most frequently in top-scored positions.

        Returns:
            List of ticker symbols, or empty list if no scan data exists.
        """
        try:
            # Query recent scans for tickers with highest composite scores
            recent_scans = await self._repo.get_recent_scans(limit=5)
            if not recent_scans:
                return []

            # Aggregate tickers across recent scans, counting frequency
            ticker_frequency: dict[str, int] = {}
            for scan in recent_scans:
                if scan.id is None:
                    continue
                scores = await self._repo.get_scores_for_scan(scan.id)
                for score in scores:
                    ticker_frequency[score.ticker] = ticker_frequency.get(score.ticker, 0) + 1

            # Sort by frequency descending, take top 50
            sorted_tickers = sorted(
                ticker_frequency.keys(),
                key=lambda t: ticker_frequency[t],
                reverse=True,
            )
            return sorted_tickers[:50]

        except Exception:
            logger.warning("Failed to compute popular options", exc_info=True)
            return []
