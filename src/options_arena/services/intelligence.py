"""Intelligence data service for Options Arena.

Fetches analyst targets, recommendations, upgrades/downgrades, insider transactions,
institutional holders, and news headlines from yfinance. Mirrors the OpenBB service
pattern: class-based DI, never-raises contract, cache-first, rate-limited.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, date, datetime, timedelta

import yfinance as yf  # type: ignore[import-untyped]

from options_arena.models.config import IntelligenceConfig
from options_arena.models.intelligence import (
    AnalystActivitySnapshot,
    AnalystSnapshot,
    InsiderSnapshot,
    InsiderTransaction,
    InstitutionalSnapshot,
    IntelligencePackage,
    UpgradeDowngrade,
    _parse_transaction_type,
)
from options_arena.services.cache import ServiceCache
from options_arena.services.helpers import safe_float, safe_int
from options_arena.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class IntelligenceService:
    """Fetches intelligence data from yfinance with caching and rate limiting.

    Never raises -- every method returns typed data or ``None`` on any error.
    Follows the same DI pattern as ``OpenBBService`` and ``MarketDataService``.

    Args:
        config: Intelligence configuration (timeouts, TTLs, feature toggles).
        cache: Two-tier service cache for caching responses.
        limiter: Rate limiter for controlling request frequency.
    """

    def __init__(
        self,
        config: IntelligenceConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        self._config = config
        self._cache = cache
        self._limiter = limiter

    async def close(self) -> None:
        """Explicit cleanup -- no resources to release currently."""

    # ------------------------------------------------------------------
    # 1. Analyst Targets
    # ------------------------------------------------------------------

    async def fetch_analyst_targets(
        self,
        ticker: str,
        current_price: float,
    ) -> AnalystSnapshot | None:
        """Fetch analyst price targets and recommendation counts.

        Returns ``None`` if the feature is disabled, data is unavailable,
        or any error occurs.
        """
        if not self._config.analyst_enabled:
            return None

        try:
            # Cache check
            cache_key = f"intel:analyst:{ticker}"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Intel analyst cache hit for %s", ticker)
                return AnalystSnapshot.model_validate_json(cached)

            # Rate-limited yfinance calls
            async with self._limiter:
                ticker_obj = yf.Ticker(ticker)
                targets_df = await asyncio.wait_for(
                    asyncio.to_thread(ticker_obj.get_analyst_price_targets),
                    timeout=self._config.request_timeout,
                )
                recs_df = await asyncio.wait_for(
                    asyncio.to_thread(ticker_obj.get_recommendations),
                    timeout=self._config.request_timeout,
                )

            # Both empty → nothing to report
            targets_empty = targets_df is None or (
                hasattr(targets_df, "empty") and targets_df.empty
            )
            recs_empty = recs_df is None or (hasattr(recs_df, "empty") and recs_df.empty)
            if targets_empty and recs_empty:
                return None

            # Parse targets
            target_low: float | None = None
            target_high: float | None = None
            target_mean: float | None = None
            target_median: float | None = None
            target_current: float | None = None

            if not targets_empty:
                row = targets_df.iloc[0] if len(targets_df) > 0 else None
                if row is not None:
                    target_low = safe_float(row.get("low"))
                    target_high = safe_float(row.get("high"))
                    target_mean = safe_float(row.get("mean"))
                    target_median = safe_float(row.get("median"))
                    target_current = safe_float(row.get("current"))

            # Parse recommendations — filter to period == "0m"
            strong_buy = 0
            buy = 0
            hold = 0
            sell = 0
            strong_sell = 0

            if not recs_empty:
                current_period = recs_df[recs_df["period"] == "0m"]
                if not current_period.empty:
                    rec_row = current_period.iloc[0]
                    strong_buy = safe_int(rec_row.get("strongBuy")) or 0
                    buy = safe_int(rec_row.get("buy")) or 0
                    hold = safe_int(rec_row.get("hold")) or 0
                    sell = safe_int(rec_row.get("sell")) or 0
                    strong_sell = safe_int(rec_row.get("strongSell")) or 0

            snapshot = AnalystSnapshot(
                ticker=ticker,
                target_low=target_low,
                target_high=target_high,
                target_mean=target_mean,
                target_median=target_median,
                current_price=target_current if target_current is not None else current_price,
                strong_buy=strong_buy,
                buy=buy,
                hold=hold,
                sell=sell,
                strong_sell=strong_sell,
                fetched_at=datetime.now(UTC),
            )

            # Cache result
            await self._cache.set(
                cache_key,
                snapshot.model_dump_json().encode(),
                ttl=self._config.analyst_cache_ttl,
            )
            logger.debug("Fetched and cached intel analyst for %s", ticker)
            return snapshot

        except Exception:
            logger.warning("Intel analyst fetch failed for %s", ticker, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 2. Analyst Activity (Upgrades / Downgrades)
    # ------------------------------------------------------------------

    async def fetch_analyst_activity(
        self,
        ticker: str,
    ) -> AnalystActivitySnapshot | None:
        """Fetch recent analyst upgrades/downgrades.

        Returns ``None`` if the feature is disabled, data is unavailable,
        or any error occurs.
        """
        if not self._config.analyst_enabled:
            return None

        try:
            # Cache check
            cache_key = f"intel:activity:{ticker}"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Intel activity cache hit for %s", ticker)
                return AnalystActivitySnapshot.model_validate_json(cached)

            # Rate-limited yfinance call
            async with self._limiter:
                ticker_obj = yf.Ticker(ticker)
                df = await asyncio.wait_for(
                    asyncio.to_thread(ticker_obj.get_upgrades_downgrades),
                    timeout=self._config.request_timeout,
                )

            if df is None or (hasattr(df, "empty") and df.empty):
                return None

            # Parse — date is in INDEX (GradeDate), not a column
            recent_changes: list[UpgradeDowngrade] = []
            for i in range(min(len(df), 10)):
                row = df.iloc[i]
                # Date from index
                grade_date_raw = df.index[i]
                if hasattr(grade_date_raw, "date"):
                    grade_date = grade_date_raw.date()
                elif isinstance(grade_date_raw, date):
                    grade_date = grade_date_raw
                else:
                    grade_date = date.fromisoformat(str(grade_date_raw)[:10])

                firm = str(row.get("Firm", ""))
                to_grade = str(row.get("ToGrade", ""))
                from_grade = str(row.get("FromGrade", ""))
                action = str(row.get("Action", ""))

                recent_changes.append(
                    UpgradeDowngrade(
                        firm=firm,
                        action=action,
                        to_grade=to_grade,
                        from_grade=from_grade,
                        date=grade_date,
                    )
                )

            # Count upgrades/downgrades in last 30 days
            cutoff = date.today() - timedelta(days=30)
            upgrades_30d = sum(
                1 for ud in recent_changes if ud.action == "Upgrade" and ud.date >= cutoff
            )
            downgrades_30d = sum(
                1 for ud in recent_changes if ud.action == "Downgrade" and ud.date >= cutoff
            )
            net_sentiment_30d = upgrades_30d - downgrades_30d

            snapshot = AnalystActivitySnapshot(
                ticker=ticker,
                recent_changes=recent_changes,
                upgrades_30d=upgrades_30d,
                downgrades_30d=downgrades_30d,
                net_sentiment_30d=net_sentiment_30d,
                fetched_at=datetime.now(UTC),
            )

            # Cache result
            await self._cache.set(
                cache_key,
                snapshot.model_dump_json().encode(),
                ttl=self._config.analyst_cache_ttl,
            )
            logger.debug("Fetched and cached intel activity for %s", ticker)
            return snapshot

        except Exception:
            logger.warning("Intel activity fetch failed for %s", ticker, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 3. Insider Activity
    # ------------------------------------------------------------------

    async def fetch_insider_activity(
        self,
        ticker: str,
    ) -> InsiderSnapshot | None:
        """Fetch insider transactions.

        Returns ``None`` if the feature is disabled, data is unavailable,
        or any error occurs.
        """
        if not self._config.insider_enabled:
            return None

        try:
            # Cache check
            cache_key = f"intel:insider:{ticker}"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Intel insider cache hit for %s", ticker)
                return InsiderSnapshot.model_validate_json(cached)

            # Rate-limited yfinance call
            async with self._limiter:
                ticker_obj = yf.Ticker(ticker)
                df = await asyncio.wait_for(
                    asyncio.to_thread(ticker_obj.get_insider_transactions),
                    timeout=self._config.request_timeout,
                )

            if df is None or (hasattr(df, "empty") and df.empty):
                return None

            # Parse — Transaction column is ALWAYS empty, parse from Text
            transactions: list[InsiderTransaction] = []
            for i in range(min(len(df), 20)):
                row = df.iloc[i]
                insider_name = str(row.get("Insider", "Unknown"))
                position = str(row.get("Position", "Unknown"))
                shares_raw = safe_int(row.get("Shares"))
                shares = shares_raw if shares_raw is not None else 0
                value = safe_float(row.get("Value"))
                text = str(row.get("Text", ""))
                transaction_type = _parse_transaction_type(text)

                # Parse date — Start Date may be Timestamp
                start_date_raw = row.get("Start Date")
                transaction_date: date | None = None
                if start_date_raw is not None:
                    if hasattr(start_date_raw, "date"):
                        transaction_date = start_date_raw.date()
                    elif isinstance(start_date_raw, date):
                        transaction_date = start_date_raw
                    else:
                        try:
                            transaction_date = date.fromisoformat(str(start_date_raw)[:10])
                        except (ValueError, TypeError):
                            transaction_date = None

                transactions.append(
                    InsiderTransaction(
                        insider_name=insider_name,
                        position=position,
                        transaction_type=transaction_type,
                        shares=shares,
                        value=value,
                        transaction_date=transaction_date,
                    )
                )

            # Compute 90-day metrics
            cutoff_90d = date.today() - timedelta(days=90)
            recent_txns = [
                t
                for t in transactions
                if t.transaction_date is not None and t.transaction_date >= cutoff_90d
            ]
            purchases = [t for t in recent_txns if t.transaction_type == "Purchase"]
            sales = [t for t in recent_txns if t.transaction_type == "Sale"]
            net_insider_buys_90d = len(purchases) - len(sales)
            total = len(purchases) + len(sales)
            insider_buy_ratio: float | None = len(purchases) / total if total > 0 else None
            net_insider_value_90d = sum(t.value for t in purchases if t.value is not None) - sum(
                t.value for t in sales if t.value is not None
            )

            snapshot = InsiderSnapshot(
                ticker=ticker,
                transactions=transactions,
                net_insider_buys_90d=net_insider_buys_90d,
                net_insider_value_90d=net_insider_value_90d,
                insider_buy_ratio=insider_buy_ratio,
                fetched_at=datetime.now(UTC),
            )

            # Cache result
            await self._cache.set(
                cache_key,
                snapshot.model_dump_json().encode(),
                ttl=self._config.insider_cache_ttl,
            )
            logger.debug("Fetched and cached intel insider for %s", ticker)
            return snapshot

        except Exception:
            logger.warning("Intel insider fetch failed for %s", ticker, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 4. Institutional Ownership
    # ------------------------------------------------------------------

    async def fetch_institutional(
        self,
        ticker: str,
    ) -> InstitutionalSnapshot | None:
        """Fetch institutional ownership data.

        Returns ``None`` if the feature is disabled, data is unavailable,
        or any error occurs.
        """
        if not self._config.institutional_enabled:
            return None

        try:
            # Cache check
            cache_key = f"intel:institutional:{ticker}"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Intel institutional cache hit for %s", ticker)
                return InstitutionalSnapshot.model_validate_json(cached)

            # Rate-limited yfinance calls
            async with self._limiter:
                ticker_obj = yf.Ticker(ticker)
                major_df = await asyncio.wait_for(
                    asyncio.to_thread(ticker_obj.get_major_holders),
                    timeout=self._config.request_timeout,
                )
                inst_df = await asyncio.wait_for(
                    asyncio.to_thread(ticker_obj.get_institutional_holders),
                    timeout=self._config.request_timeout,
                )

            major_empty = major_df is None or (hasattr(major_df, "empty") and major_df.empty)
            inst_empty = inst_df is None or (hasattr(inst_df, "empty") and inst_df.empty)
            if major_empty and inst_empty:
                return None

            # Parse major holders — indexed by string keys, single Value column
            insider_pct: float | None = None
            institutional_pct: float | None = None
            institutional_float_pct: float | None = None
            institutions_count: int | None = None

            if not major_empty:
                with contextlib.suppress(KeyError, TypeError):
                    insider_pct = safe_float(major_df.loc["insidersPercentHeld", "Value"])
                with contextlib.suppress(KeyError, TypeError):
                    institutional_pct = safe_float(
                        major_df.loc["institutionsPercentHeld", "Value"]
                    )
                with contextlib.suppress(KeyError, TypeError):
                    institutional_float_pct = safe_float(
                        major_df.loc["institutionsFloatPercentHeld", "Value"]
                    )
                with contextlib.suppress(KeyError, TypeError):
                    institutions_count = safe_int(major_df.loc["institutionsCount", "Value"])

            # Parse institutional holders — top 5
            top_holders: list[str] = []
            top_holder_pcts: list[float] = []

            if not inst_empty:
                for i in range(min(len(inst_df), 5)):
                    row = inst_df.iloc[i]
                    holder = str(row.get("Holder", "Unknown"))
                    pct = safe_float(row.get("pctHeld")) or safe_float(row.get("% Out"))
                    top_holders.append(holder)
                    if pct is not None:
                        top_holder_pcts.append(pct)

            snapshot = InstitutionalSnapshot(
                ticker=ticker,
                institutional_pct=institutional_pct,
                institutional_float_pct=institutional_float_pct,
                insider_pct=insider_pct,
                institutions_count=institutions_count,
                top_holders=top_holders,
                top_holder_pcts=top_holder_pcts,
                fetched_at=datetime.now(UTC),
            )

            # Cache result
            await self._cache.set(
                cache_key,
                snapshot.model_dump_json().encode(),
                ttl=self._config.institutional_cache_ttl,
            )
            logger.debug("Fetched and cached intel institutional for %s", ticker)
            return snapshot

        except Exception:
            logger.warning("Intel institutional fetch failed for %s", ticker, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 5. News Headlines
    # ------------------------------------------------------------------

    async def fetch_news_headlines(
        self,
        ticker: str,
    ) -> list[str] | None:
        """Fetch recent news headlines.

        Returns ``None`` if the feature is disabled, no news is available,
        or any error occurs.
        """
        if not self._config.news_fallback_enabled:
            return None

        try:
            # Cache check
            cache_key = f"intel:news:{ticker}"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Intel news cache hit for %s", ticker)
                data = json.loads(cached.decode())
                return data if isinstance(data, list) else None

            # Rate-limited yfinance call
            async with self._limiter:
                ticker_obj = yf.Ticker(ticker)
                news_items = await asyncio.wait_for(
                    asyncio.to_thread(ticker_obj.get_news, _count=10),
                    timeout=self._config.request_timeout,
                )

            if not news_items:
                return None

            # Extract titles from nested structure
            headlines: list[str] = []
            for item in news_items:
                try:
                    content = item.get("content", {}) if isinstance(item, dict) else {}
                    title = content.get("title") if isinstance(content, dict) else None
                    if title and isinstance(title, str):
                        headlines.append(title)
                except (AttributeError, TypeError):
                    continue

            if not headlines:
                return None

            # Cap at 5
            headlines = headlines[:5]

            # Cache result
            await self._cache.set(
                cache_key,
                json.dumps(headlines).encode(),
                ttl=self._config.news_cache_ttl,
            )
            logger.debug("Fetched and cached intel news for %s", ticker)
            return headlines

        except Exception:
            logger.warning("Intel news fetch failed for %s", ticker, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # 6. Aggregator
    # ------------------------------------------------------------------

    async def fetch_intelligence(
        self,
        ticker: str,
        current_price: float,
    ) -> IntelligencePackage | None:
        """Aggregate all intelligence categories for a ticker.

        Calls all 5 fetch methods in parallel via ``asyncio.gather``.
        Converts exceptions to ``None``. Returns ``None`` if all categories
        fail or the master toggle is disabled.
        """
        if not self._config.enabled:
            return None

        try:
            results = await asyncio.gather(
                self.fetch_analyst_targets(ticker, current_price),
                self.fetch_analyst_activity(ticker),
                self.fetch_insider_activity(ticker),
                self.fetch_institutional(ticker),
                self.fetch_news_headlines(ticker),
                return_exceptions=True,
            )

            # Convert exceptions to None
            analyst = results[0] if not isinstance(results[0], BaseException) else None
            activity = results[1] if not isinstance(results[1], BaseException) else None
            insider = results[2] if not isinstance(results[2], BaseException) else None
            institutional = results[3] if not isinstance(results[3], BaseException) else None
            news = results[4] if not isinstance(results[4], BaseException) else None

            # If ALL are None, return None
            if all(x is None for x in [analyst, activity, insider, institutional, news]):
                return None

            return IntelligencePackage(
                ticker=ticker,
                analyst=analyst,
                analyst_activity=activity,
                insider=insider,
                institutional=institutional,
                news_headlines=news,
                fetched_at=datetime.now(UTC),
            )

        except Exception:
            logger.exception("fetch_intelligence failed for %s", ticker)
            return None
