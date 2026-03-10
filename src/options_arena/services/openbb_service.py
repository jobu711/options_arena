"""OpenBB Platform SDK service for enrichment data.

Wraps the OpenBB SDK to fetch fundamentals, unusual flow, and news sentiment.
All methods follow the never-raises contract — errors are logged and ``None``
is returned. Uses guarded imports so the system runs identically without the
OpenBB SDK installed.

Class-based DI with ``config``, ``cache``, ``limiter`` — same pattern as
``MarketDataService``, ``FredService``, etc.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime
from typing import Any  # noqa: ANN401 — required for optional untyped SDK objects

from options_arena.models.config import OpenBBConfig
from options_arena.models.enums import SentimentLabel
from options_arena.models.openbb import (
    FundamentalSnapshot,
    NewsHeadline,
    NewsSentimentSnapshot,
    UnusualFlowSnapshot,
)
from options_arena.services.base import ServiceBase
from options_arena.services.cache import ServiceCache
from options_arena.services.helpers import safe_float as _safe_float
from options_arena.services.helpers import safe_int as _safe_int
from options_arena.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _get_obb() -> Any:  # noqa: ANN401
    """Attempt to import the OpenBB SDK. Returns ``obb`` module or ``None``."""
    try:
        from openbb import obb

        return obb
    except ImportError:
        logger.info("OpenBB SDK not installed — OpenBB features disabled")
        return None


def _get_vader() -> Any:  # noqa: ANN401
    """Attempt to import VADER sentiment analyzer. Returns analyzer or ``None``."""
    try:
        from vaderSentiment.vaderSentiment import (
            SentimentIntensityAnalyzer,
        )

        return SentimentIntensityAnalyzer()
    except ImportError:
        logger.info("vaderSentiment not installed — sentiment scoring disabled")
        return None


class OpenBBService(ServiceBase[OpenBBConfig]):
    """Enrichment service wrapping the OpenBB Platform SDK.

    All public methods follow the never-raises contract: exceptions are
    caught, logged at WARNING, and ``None`` is returned.

    Args:
        config: OpenBB configuration (timeouts, TTLs, feature toggles).
        cache: Two-tier service cache for caching responses.
        limiter: Rate limiter for controlling request frequency.
    """

    def __init__(
        self,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        super().__init__(config, cache, limiter)
        self._obb = _get_obb()
        self._vader = _get_vader()

    @property
    def sdk_available(self) -> bool:
        """Whether the OpenBB SDK is importable."""
        return self._obb is not None

    async def fetch_fundamentals(self, ticker: str) -> FundamentalSnapshot | None:
        """Fetch fundamental metrics for a ticker.

        Returns ``None`` if the SDK is unavailable, the feature is disabled,
        or any error occurs during the fetch.
        """
        if not self._config.enabled or not self._config.fundamentals_enabled:
            return None
        if self._obb is None:
            return None

        try:
            return await self._cached_fetch(
                key=f"openbb:fundamentals:{ticker}",
                model_type=FundamentalSnapshot,
                factory=lambda: self._fetch_fundamentals_from_sdk(ticker),
                ttl=self._config.fundamentals_cache_ttl,
            )
        except Exception:
            logger.warning("OpenBB fundamentals fetch failed for %s", ticker, exc_info=True)
            return None

    async def _fetch_fundamentals_from_sdk(self, ticker: str) -> FundamentalSnapshot:
        """Fetch fundamentals from OpenBB SDK (cache-miss path).

        Raises:
            ValueError: If the SDK returns no usable data.
        """
        async with self._limiter:  # type: ignore[union-attr]
            result = await self._obb_call(
                self._obb.equity.fundamental.metrics,
                ticker,
                provider="yfinance",
            )

        if result is None or not hasattr(result, "results"):
            raise ValueError(f"OpenBB fundamentals returned no data for {ticker}")

        # Map SDK output to typed model
        data = result.results
        if isinstance(data, list):
            data = data[0] if data else None
        if data is None:
            raise ValueError(f"OpenBB fundamentals results empty for {ticker}")

        # Extract sector/industry strings (never-raises — None on error)
        raw_sector = getattr(data, "sector", None)
        raw_industry = getattr(data, "industry", None)
        sector_str: str | None = str(raw_sector) if raw_sector is not None else None
        industry_str: str | None = str(raw_industry) if raw_industry is not None else None

        snapshot = FundamentalSnapshot(
            ticker=ticker,
            pe_ratio=_safe_float(getattr(data, "pe_ratio", None)),
            forward_pe=_safe_float(getattr(data, "forward_pe", None)),
            peg_ratio=_safe_float(getattr(data, "peg_ratio", None)),
            price_to_book=_safe_float(getattr(data, "price_to_book", None)),
            debt_to_equity=_safe_float(getattr(data, "debt_to_equity", None)),
            revenue_growth=_safe_float(getattr(data, "revenue_growth", None)),
            profit_margin=_safe_float(getattr(data, "profit_margin", None)),
            market_cap=_safe_int(getattr(data, "market_cap", None)),
            sector=sector_str,
            industry=industry_str,
            fetched_at=datetime.now(UTC),
        )
        logger.debug("Fetched OpenBB fundamentals for %s", ticker)
        return snapshot

    async def fetch_unusual_flow(self, ticker: str) -> UnusualFlowSnapshot | None:
        """Fetch unusual options/dark-pool flow data for a ticker.

        Returns ``None`` if the SDK is unavailable, the feature is disabled,
        or any error occurs during the fetch.
        """
        if not self._config.enabled or not self._config.unusual_flow_enabled:
            return None
        if self._obb is None:
            return None

        # Guard against missing shorts router — the openbb-stockgrid extension
        # may not be loaded even when the package is installed.
        if not hasattr(self._obb.equity, "shorts"):
            logger.warning(
                "OpenBB equity.shorts router not available — stockgrid extension may not be loaded"
            )
            return None

        try:
            return await self._cached_fetch(
                key=f"openbb:flow:{ticker}",
                model_type=UnusualFlowSnapshot,
                factory=lambda: self._fetch_flow_from_sdk(ticker),
                ttl=self._config.flow_cache_ttl,
            )
        except Exception:
            logger.warning("OpenBB flow fetch failed for %s", ticker, exc_info=True)
            return None

    async def _fetch_flow_from_sdk(self, ticker: str) -> UnusualFlowSnapshot:
        """Fetch unusual flow from OpenBB SDK (cache-miss path).

        Raises:
            ValueError: If the SDK returns no usable data.
        """
        async with self._limiter:  # type: ignore[union-attr]
            result = await self._obb_call(
                self._obb.equity.shorts.short_volume,
                ticker,
                provider="stockgrid",
            )

        if result is None or not hasattr(result, "results"):
            raise ValueError(f"OpenBB flow returned no data for {ticker}")

        data_list = result.results
        if not data_list:
            raise ValueError(f"OpenBB flow results empty for {ticker}")

        # Aggregate recent data into a flow snapshot.
        # NOTE: short_volume is used as a proxy for put-side sentiment.
        # Stockgrid short-selling data != true options put volume.
        latest = data_list[0] if isinstance(data_list, list) else data_list
        short_vol = _safe_int(getattr(latest, "short_volume", None))
        total_vol = _safe_int(getattr(latest, "total_volume", None))
        short_pct = _safe_float(getattr(latest, "short_volume_percent", None))

        snapshot = UnusualFlowSnapshot(
            ticker=ticker,
            net_call_premium=None,
            net_put_premium=None,
            call_volume=((total_vol - short_vol) if total_vol and short_vol else None),
            put_volume=short_vol,
            put_call_ratio=(
                short_pct / (1.0 - short_pct)
                if short_pct is not None and short_pct < 1.0
                else None
            ),
            fetched_at=datetime.now(UTC),
        )
        logger.debug("Fetched OpenBB flow for %s", ticker)
        return snapshot

    async def fetch_news_sentiment(
        self, ticker: str, limit: int = 10
    ) -> NewsSentimentSnapshot | None:
        """Fetch recent news and compute VADER sentiment for a ticker.

        Returns ``None`` if the SDK is unavailable, the feature is disabled,
        or any error occurs during the fetch.
        """
        if not self._config.enabled or not self._config.news_sentiment_enabled:
            return None
        if self._obb is None:
            return None

        try:
            return await self._cached_fetch(
                key=f"openbb:news:{ticker}",
                model_type=NewsSentimentSnapshot,
                factory=lambda: self._fetch_news_from_sdk(ticker, limit),
                ttl=self._config.news_cache_ttl,
            )
        except Exception:
            logger.warning("OpenBB news sentiment fetch failed for %s", ticker, exc_info=True)
            return None

    async def _fetch_news_from_sdk(self, ticker: str, limit: int) -> NewsSentimentSnapshot:
        """Fetch news sentiment from OpenBB SDK (cache-miss path).

        Raises:
            ValueError: If the SDK returns no result object.
        """
        async with self._limiter:  # type: ignore[union-attr]
            result = await self._obb_call(
                self._obb.news.company,
                ticker,
                limit=limit,
                provider="yfinance",
            )

        if result is None or not hasattr(result, "results"):
            raise ValueError(f"OpenBB news returned no data for {ticker}")

        articles = result.results
        if not articles:
            # No news — return neutral sentiment
            return NewsSentimentSnapshot(
                ticker=ticker,
                headlines=[],
                aggregate_sentiment=0.0,
                sentiment_label=SentimentLabel.NEUTRAL,
                article_count=0,
                fetched_at=datetime.now(UTC),
            )

        # Score each headline with VADER
        headlines: list[NewsHeadline] = []
        for article in articles:
            title = getattr(article, "title", None) or ""
            if not title:
                continue
            score = self._score_sentiment(title)
            pub_date = getattr(article, "date", None)
            if pub_date is not None:
                # Ensure datetime is UTC-aware
                if hasattr(pub_date, "tzinfo") and pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=UTC)
                elif not hasattr(pub_date, "tzinfo"):
                    pub_date = None  # Not a datetime
            source = getattr(article, "source", None)
            headlines.append(
                NewsHeadline(
                    title=title,
                    published_at=pub_date,
                    sentiment_score=max(-1.0, min(1.0, score)),
                    source=source,
                )
            )

        # Compute aggregate
        if headlines:
            raw_agg = sum(h.sentiment_score for h in headlines) / len(headlines)
            aggregate = max(-1.0, min(1.0, raw_agg))
        else:
            aggregate = 0.0

        label = _classify_sentiment(aggregate)

        snapshot = NewsSentimentSnapshot(
            ticker=ticker,
            headlines=headlines,
            aggregate_sentiment=aggregate,
            sentiment_label=label,
            article_count=len(headlines),
            fetched_at=datetime.now(UTC),
        )
        logger.debug("Fetched OpenBB news sentiment for %s", ticker)
        return snapshot

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _obb_call(
        self,
        fn: Any,  # noqa: ANN401
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Wrap sync OpenBB call: ``to_thread`` + ``wait_for``."""
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=self._config.request_timeout,
        )

    def _score_sentiment(self, text: str) -> float:
        """Score headline text using VADER. Returns compound score -1.0 to 1.0."""
        if self._vader is None:
            return 0.0
        scores: dict[str, float] = self._vader.polarity_scores(text)
        compound = scores.get("compound", 0.0)
        if not math.isfinite(compound):
            return 0.0
        return compound


def _classify_sentiment(score: float) -> SentimentLabel:
    """Classify aggregate sentiment score into a label."""
    if score > 0.05:
        return SentimentLabel.BULLISH
    if score < -0.05:
        return SentimentLabel.BEARISH
    return SentimentLabel.NEUTRAL
