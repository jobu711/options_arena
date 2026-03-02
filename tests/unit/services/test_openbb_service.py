"""Unit tests for OpenBBService.

Tests cover:
- Construction with and without OpenBB SDK
- fetch_fundamentals: happy path, cache hit/miss, SDK unavailable, errors, config toggle
- fetch_unusual_flow: happy path, cache hit, errors, config toggle
- fetch_news_sentiment: happy path, VADER scoring, aggregate sentiment, labels, empty results
- _obb_call: async wrapping, timeout handling
- Never-raises contract: every public method catches all exceptions
- Guarded import: SDK absent returns None gracefully
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from options_arena.models.config import OpenBBConfig
from options_arena.models.enums import SentimentLabel
from options_arena.models.openbb import (
    FundamentalSnapshot,
    NewsSentimentSnapshot,
    UnusualFlowSnapshot,
)
from options_arena.services.openbb_service import (
    OpenBBService,
    _classify_sentiment,
    _safe_float,
    _safe_int,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create a mock ServiceCache."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_limiter() -> MagicMock:
    """Create a mock RateLimiter that acts as async context manager."""
    limiter = MagicMock()
    limiter.__aenter__ = AsyncMock(return_value=limiter)
    limiter.__aexit__ = AsyncMock(return_value=None)
    return limiter


@pytest.fixture
def config() -> OpenBBConfig:
    """Default OpenBBConfig for tests."""
    return OpenBBConfig()


@pytest.fixture
def disabled_config() -> OpenBBConfig:
    """OpenBBConfig with everything disabled."""
    return OpenBBConfig(enabled=False)


@pytest.fixture
def fundamentals_disabled_config() -> OpenBBConfig:
    """OpenBBConfig with fundamentals disabled."""
    return OpenBBConfig(fundamentals_enabled=False)


@pytest.fixture
def flow_disabled_config() -> OpenBBConfig:
    """OpenBBConfig with flow disabled."""
    return OpenBBConfig(unusual_flow_enabled=False)


@pytest.fixture
def news_disabled_config() -> OpenBBConfig:
    """OpenBBConfig with news disabled."""
    return OpenBBConfig(news_sentiment_enabled=False)


_SENTINEL = object()


def _make_service(
    config: OpenBBConfig,
    cache: MagicMock,
    limiter: MagicMock,
    *,
    obb: object = _SENTINEL,
    vader: object = _SENTINEL,
) -> OpenBBService:
    """Create OpenBBService with injected obb and vader mocks.

    Pass ``obb=None`` to simulate SDK not installed.
    Pass ``vader=None`` to simulate VADER not installed.
    """
    service = OpenBBService(config=config, cache=cache, limiter=limiter)
    service._obb = MagicMock() if obb is _SENTINEL else obb
    service._vader = MagicMock() if vader is _SENTINEL else vader
    return service


def _make_fundamental_result() -> SimpleNamespace:
    """Mock OpenBB fundamental overview result."""
    data = SimpleNamespace(
        pe_ratio=28.5,
        forward_pe=24.2,
        peg_ratio=1.8,
        price_to_book=45.3,
        debt_to_equity=1.87,
        revenue_growth=0.128,
        profit_margin=0.265,
        market_cap=2_800_000_000_000,
    )
    return SimpleNamespace(results=[data])


def _make_flow_result() -> SimpleNamespace:
    """Mock OpenBB short volume result."""
    data = SimpleNamespace(
        short_volume=10_000,
        total_volume=50_000,
        short_volume_percent=0.20,
    )
    return SimpleNamespace(results=[data])


def _make_news_result(count: int = 3) -> SimpleNamespace:
    """Mock OpenBB news result."""
    articles = [
        SimpleNamespace(
            title=f"News headline {i}",
            date=datetime(2026, 3, 1, 10, i, 0, tzinfo=UTC),
            source="Reuters",
        )
        for i in range(count)
    ]
    return SimpleNamespace(results=articles)


# ===========================================================================
# OpenBBService Init
# ===========================================================================


class TestOpenBBServiceInit:
    """Tests for OpenBBService construction."""

    def test_construction_with_config(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """OpenBBService constructs and stores config."""
        service = _make_service(config, mock_cache, mock_limiter)
        assert service._config is config

    def test_sdk_available_when_obb_present(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """sdk_available returns True when obb is present."""
        service = _make_service(config, mock_cache, mock_limiter, obb=MagicMock())
        assert service.sdk_available is True

    def test_sdk_unavailable_when_obb_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """sdk_available returns False when obb is None."""
        service = _make_service(config, mock_cache, mock_limiter, obb=None)
        assert service.sdk_available is False


# ===========================================================================
# fetch_fundamentals
# ===========================================================================


class TestFetchFundamentals:
    """Tests for fetch_fundamentals method."""

    async def test_happy_path_returns_snapshot(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Successful fetch returns FundamentalSnapshot with correct fields."""
        obb = MagicMock()
        obb.equity.fundamental.metrics = MagicMock(return_value=_make_fundamental_result())
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_fundamentals("AAPL")

        assert result is not None
        assert isinstance(result, FundamentalSnapshot)
        assert result.ticker == "AAPL"
        assert result.pe_ratio == pytest.approx(28.5)
        assert result.forward_pe == pytest.approx(24.2)
        assert result.market_cap == 2_800_000_000_000

    async def test_cache_hit_skips_fetch(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Cache hit returns cached data without calling SDK."""
        cached_snapshot = FundamentalSnapshot(
            ticker="AAPL",
            pe_ratio=30.0,
            fetched_at=NOW_UTC,
        )
        mock_cache.get = AsyncMock(return_value=cached_snapshot.model_dump_json().encode())

        obb = MagicMock()
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_fundamentals("AAPL")

        assert result is not None
        assert result.pe_ratio == pytest.approx(30.0)
        # SDK should NOT have been called
        obb.equity.fundamental.metrics.assert_not_called()

    async def test_cache_miss_fetches_and_stores(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Cache miss triggers SDK fetch and stores result in cache."""
        obb = MagicMock()
        obb.equity.fundamental.metrics = MagicMock(return_value=_make_fundamental_result())
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_fundamentals("AAPL")

        assert result is not None
        mock_cache.set.assert_awaited_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][0] == "openbb:fundamentals:AAPL"
        assert call_args[1]["ttl"] == config.fundamentals_cache_ttl

    async def test_sdk_unavailable_returns_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """SDK not installed returns None."""
        service = _make_service(config, mock_cache, mock_limiter, obb=None)
        result = await service.fetch_fundamentals("AAPL")
        assert result is None

    async def test_sdk_raises_returns_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """SDK exception is caught, returns None."""
        obb = MagicMock()
        obb.equity.fundamental.metrics = MagicMock(side_effect=RuntimeError("SDK error"))
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_fundamentals("AAPL")

        assert result is None

    async def test_timeout_returns_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Timeout during fetch returns None."""
        obb = MagicMock()
        obb.equity.fundamental.metrics = MagicMock(side_effect=TimeoutError("timeout"))
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_fundamentals("AAPL")

        assert result is None

    async def test_disabled_via_config_returns_none(
        self,
        disabled_config: OpenBBConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Config enabled=False returns None without SDK call."""
        service = _make_service(disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_fundamentals("AAPL")
        assert result is None

    async def test_fundamentals_disabled_returns_none(
        self,
        fundamentals_disabled_config: OpenBBConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """fundamentals_enabled=False returns None."""
        service = _make_service(fundamentals_disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_fundamentals("AAPL")
        assert result is None

    async def test_empty_results_returns_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Empty results list from SDK returns None."""
        obb = MagicMock()
        obb.equity.fundamental.metrics = MagicMock(
            return_value=SimpleNamespace(results=[])
        )
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_fundamentals("AAPL")

        assert result is None


# ===========================================================================
# fetch_unusual_flow
# ===========================================================================


class TestFetchUnusualFlow:
    """Tests for fetch_unusual_flow method."""

    async def test_happy_path_returns_snapshot(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Successful fetch returns UnusualFlowSnapshot."""
        obb = MagicMock()
        obb.equity.shorts.short_volume = MagicMock(return_value=_make_flow_result())
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_unusual_flow("AAPL")

        assert result is not None
        assert isinstance(result, UnusualFlowSnapshot)
        assert result.ticker == "AAPL"
        assert result.put_volume == 10_000
        assert result.call_volume == 40_000

    async def test_cache_hit(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Cache hit returns cached flow data."""
        cached = UnusualFlowSnapshot(
            ticker="AAPL",
            put_call_ratio=0.5,
            fetched_at=NOW_UTC,
        )
        mock_cache.get = AsyncMock(return_value=cached.model_dump_json().encode())
        obb = MagicMock()
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_unusual_flow("AAPL")

        assert result is not None
        assert result.put_call_ratio == pytest.approx(0.5)
        obb.equity.shorts.short_volume.assert_not_called()

    async def test_sdk_raises_returns_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """SDK exception returns None."""
        obb = MagicMock()
        obb.equity.shorts.short_volume = MagicMock(side_effect=RuntimeError("fail"))
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_unusual_flow("AAPL")

        assert result is None

    async def test_disabled_via_config_returns_none(
        self,
        flow_disabled_config: OpenBBConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """unusual_flow_enabled=False returns None."""
        service = _make_service(flow_disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_unusual_flow("AAPL")
        assert result is None

    async def test_sdk_unavailable_returns_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """SDK not installed returns None."""
        service = _make_service(config, mock_cache, mock_limiter, obb=None)
        result = await service.fetch_unusual_flow("AAPL")
        assert result is None


# ===========================================================================
# fetch_news_sentiment
# ===========================================================================


class TestFetchNewsSentiment:
    """Tests for fetch_news_sentiment method."""

    async def test_happy_path_returns_snapshot(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Successful fetch returns NewsSentimentSnapshot."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=_make_news_result(3))
        vader = MagicMock()
        vader.polarity_scores = MagicMock(return_value={"compound": 0.5})
        service = _make_service(config, mock_cache, mock_limiter, obb=obb, vader=vader)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert isinstance(result, NewsSentimentSnapshot)
        assert result.ticker == "AAPL"
        assert result.article_count == 3
        assert len(result.headlines) == 3

    async def test_vader_scores_headlines(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Each headline gets a VADER compound score."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=_make_news_result(2))
        vader = MagicMock()
        vader.polarity_scores = MagicMock(
            side_effect=[{"compound": 0.8}, {"compound": -0.3}]
        )
        service = _make_service(config, mock_cache, mock_limiter, obb=obb, vader=vader)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert result.headlines[0].sentiment_score == pytest.approx(0.8)
        assert result.headlines[1].sentiment_score == pytest.approx(-0.3)

    async def test_aggregate_sentiment_computed(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Aggregate sentiment is the mean of headline scores."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=_make_news_result(2))
        vader = MagicMock()
        vader.polarity_scores = MagicMock(
            side_effect=[{"compound": 0.6}, {"compound": 0.4}]
        )
        service = _make_service(config, mock_cache, mock_limiter, obb=obb, vader=vader)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert result.aggregate_sentiment == pytest.approx(0.5)

    async def test_sentiment_label_bullish(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Positive aggregate gets BULLISH label."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=_make_news_result(1))
        vader = MagicMock()
        vader.polarity_scores = MagicMock(return_value={"compound": 0.5})
        service = _make_service(config, mock_cache, mock_limiter, obb=obb, vader=vader)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert result.sentiment_label == SentimentLabel.BULLISH

    async def test_sentiment_label_bearish(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Negative aggregate gets BEARISH label."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=_make_news_result(1))
        vader = MagicMock()
        vader.polarity_scores = MagicMock(return_value={"compound": -0.5})
        service = _make_service(config, mock_cache, mock_limiter, obb=obb, vader=vader)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert result.sentiment_label == SentimentLabel.BEARISH

    async def test_sentiment_label_neutral(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Near-zero aggregate gets NEUTRAL label."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=_make_news_result(1))
        vader = MagicMock()
        vader.polarity_scores = MagicMock(return_value={"compound": 0.03})
        service = _make_service(config, mock_cache, mock_limiter, obb=obb, vader=vader)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert result.sentiment_label == SentimentLabel.NEUTRAL

    async def test_no_headlines_returns_neutral(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Empty news results return neutral sentiment."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=SimpleNamespace(results=[]))
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert result.article_count == 0
        assert result.aggregate_sentiment == pytest.approx(0.0)
        assert result.sentiment_label == SentimentLabel.NEUTRAL

    async def test_vader_unavailable_returns_zero_scores(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """VADER not installed returns zero scores."""
        obb = MagicMock()
        obb.news.company = MagicMock(return_value=_make_news_result(2))
        service = _make_service(config, mock_cache, mock_limiter, obb=obb, vader=None)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        for headline in result.headlines:
            assert headline.sentiment_score == pytest.approx(0.0)

    async def test_cache_hit(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Cache hit returns cached sentiment data."""
        cached = NewsSentimentSnapshot(
            ticker="AAPL",
            headlines=[],
            aggregate_sentiment=0.42,
            sentiment_label=SentimentLabel.BULLISH,
            article_count=0,
            fetched_at=NOW_UTC,
        )
        mock_cache.get = AsyncMock(return_value=cached.model_dump_json().encode())
        obb = MagicMock()
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is not None
        assert result.aggregate_sentiment == pytest.approx(0.42)

    async def test_sdk_raises_returns_none(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """SDK exception returns None."""
        obb = MagicMock()
        obb.news.company = MagicMock(side_effect=RuntimeError("fail"))
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is None

    async def test_disabled_via_config_returns_none(
        self,
        news_disabled_config: OpenBBConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """news_sentiment_enabled=False returns None."""
        service = _make_service(news_disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_news_sentiment("AAPL")
        assert result is None


# ===========================================================================
# _obb_call
# ===========================================================================


class TestObbCall:
    """Tests for the _obb_call async wrapper."""

    async def test_wraps_sync_call_in_thread(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """_obb_call wraps a sync function via to_thread."""
        service = _make_service(config, mock_cache, mock_limiter)

        def sync_fn(x: int) -> int:
            return x * 2

        result = await service._obb_call(sync_fn, 21)
        assert result == 42

    async def test_timeout_raises(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """_obb_call raises TimeoutError when function exceeds timeout."""
        short_timeout_config = OpenBBConfig(request_timeout=1)
        service = _make_service(short_timeout_config, mock_cache, mock_limiter)

        def slow_fn() -> None:
            import time

            time.sleep(5)

        with pytest.raises(TimeoutError):
            await service._obb_call(slow_fn)


# ===========================================================================
# Never-Raises Contract
# ===========================================================================


class TestNeverRaises:
    """Verify that public methods never propagate exceptions."""

    async def test_fundamentals_never_raises(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """fetch_fundamentals catches all exceptions."""
        obb = MagicMock()
        obb.equity.fundamental.metrics = MagicMock(
            side_effect=Exception("catastrophic failure")
        )
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_fundamentals("AAPL")

        assert result is None

    async def test_flow_never_raises(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """fetch_unusual_flow catches all exceptions."""
        obb = MagicMock()
        obb.equity.shorts.short_volume = MagicMock(
            side_effect=Exception("catastrophic failure")
        )
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_unusual_flow("AAPL")

        assert result is None

    async def test_sentiment_never_raises(
        self, config: OpenBBConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """fetch_news_sentiment catches all exceptions."""
        obb = MagicMock()
        obb.news.company = MagicMock(side_effect=Exception("catastrophic failure"))
        service = _make_service(config, mock_cache, mock_limiter, obb=obb)

        result = await service.fetch_news_sentiment("AAPL")

        assert result is None


# ===========================================================================
# Helper functions
# ===========================================================================


class TestClassifySentiment:
    """Tests for the _classify_sentiment helper."""

    def test_bullish(self) -> None:
        assert _classify_sentiment(0.5) == SentimentLabel.BULLISH

    def test_bearish(self) -> None:
        assert _classify_sentiment(-0.5) == SentimentLabel.BEARISH

    def test_neutral_positive(self) -> None:
        assert _classify_sentiment(0.03) == SentimentLabel.NEUTRAL

    def test_neutral_negative(self) -> None:
        assert _classify_sentiment(-0.03) == SentimentLabel.NEUTRAL

    def test_neutral_zero(self) -> None:
        assert _classify_sentiment(0.0) == SentimentLabel.NEUTRAL

    def test_threshold_boundary_bullish(self) -> None:
        assert _classify_sentiment(0.06) == SentimentLabel.BULLISH

    def test_threshold_boundary_bearish(self) -> None:
        assert _classify_sentiment(-0.06) == SentimentLabel.BEARISH


class TestSafeFloat:
    """Tests for _safe_float helper."""

    def test_valid_float(self) -> None:
        assert _safe_float(42.5) == pytest.approx(42.5)

    def test_none(self) -> None:
        assert _safe_float(None) is None

    def test_nan(self) -> None:
        assert _safe_float(float("nan")) is None

    def test_inf(self) -> None:
        assert _safe_float(float("inf")) is None

    def test_neg_inf(self) -> None:
        assert _safe_float(float("-inf")) is None

    def test_string_number(self) -> None:
        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_invalid_string(self) -> None:
        assert _safe_float("not_a_number") is None


class TestSafeInt:
    """Tests for _safe_int helper."""

    def test_valid_int(self) -> None:
        assert _safe_int(42) == 42

    def test_none(self) -> None:
        assert _safe_int(None) is None

    def test_float_to_int(self) -> None:
        assert _safe_int(42.9) == 42

    def test_invalid_string(self) -> None:
        assert _safe_int("not_a_number") is None
