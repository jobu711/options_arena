"""Unit tests for OpenBB integration models.

Tests cover:
- SentimentLabel enum members and serialization
- FundamentalSnapshot: construction, frozen, validators, JSON roundtrip
- UnusualFlowSnapshot: construction, frozen, validators, JSON roundtrip
- NewsHeadline: construction, sentiment bounds, UTC validation
- NewsSentimentSnapshot: construction, aggregate bounds, empty headlines
- OpenBBHealthStatus: construction, all-false, UTC validation
- OpenBBConfig: defaults, env overrides, nesting in AppSettings
"""

from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AppSettings,
    OpenBBConfig,
    SentimentLabel,
)
from options_arena.models.openbb import (
    FundamentalSnapshot,
    NewsHeadline,
    NewsSentimentSnapshot,
    OpenBBHealthStatus,
    UnusualFlowSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# List of all ARENA_OPENBB_* env vars to clean
# ---------------------------------------------------------------------------

_ARENA_OPENBB_VARS = [
    "ARENA_OPENBB__ENABLED",
    "ARENA_OPENBB__FUNDAMENTALS_ENABLED",
    "ARENA_OPENBB__UNUSUAL_FLOW_ENABLED",
    "ARENA_OPENBB__NEWS_SENTIMENT_ENABLED",
    "ARENA_OPENBB__FUNDAMENTALS_CACHE_TTL",
    "ARENA_OPENBB__FLOW_CACHE_TTL",
    "ARENA_OPENBB__NEWS_CACHE_TTL",
    "ARENA_OPENBB__REQUEST_TIMEOUT",
    "ARENA_OPENBB__MAX_RETRIES",
]


@pytest.fixture(autouse=True)
def _clean_arena_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all ARENA_OPENBB_* env vars before each test."""
    for var in _ARENA_OPENBB_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fundamental_snapshot() -> FundamentalSnapshot:
    """Create a valid FundamentalSnapshot with all fields populated."""
    return FundamentalSnapshot(
        ticker="AAPL",
        pe_ratio=28.5,
        forward_pe=24.2,
        peg_ratio=1.8,
        price_to_book=45.3,
        debt_to_equity=1.87,
        revenue_growth=0.128,
        profit_margin=0.265,
        market_cap=2_800_000_000_000,
        fetched_at=NOW_UTC,
    )


@pytest.fixture
def unusual_flow_snapshot() -> UnusualFlowSnapshot:
    """Create a valid UnusualFlowSnapshot."""
    return UnusualFlowSnapshot(
        ticker="AAPL",
        net_call_premium=4_200_000.0,
        net_put_premium=-1_500_000.0,
        call_volume=150_000,
        put_volume=80_000,
        put_call_ratio=0.53,
        fetched_at=NOW_UTC,
    )


@pytest.fixture
def news_headline() -> NewsHeadline:
    """Create a valid NewsHeadline."""
    return NewsHeadline(
        title="Apple Reports Record Q4 Earnings",
        published_at=NOW_UTC,
        sentiment_score=0.72,
        source="Reuters",
    )


@pytest.fixture
def news_sentiment_snapshot(news_headline: NewsHeadline) -> NewsSentimentSnapshot:
    """Create a valid NewsSentimentSnapshot."""
    return NewsSentimentSnapshot(
        ticker="AAPL",
        headlines=[news_headline],
        aggregate_sentiment=0.42,
        sentiment_label=SentimentLabel.BULLISH,
        article_count=1,
        fetched_at=NOW_UTC,
    )


# ===========================================================================
# SentimentLabel
# ===========================================================================


class TestSentimentLabel:
    """Tests for the SentimentLabel StrEnum."""

    def test_has_exactly_three_members(self) -> None:
        """SentimentLabel has exactly 3 members."""
        assert len(SentimentLabel) == 3

    def test_values_are_lowercase(self) -> None:
        """All SentimentLabel values are lowercase strings."""
        for member in SentimentLabel:
            assert member.value == member.value.lower()

    def test_is_str_enum(self) -> None:
        """SentimentLabel is a StrEnum subclass."""
        assert issubclass(SentimentLabel, StrEnum)

    def test_members(self) -> None:
        """SentimentLabel has BULLISH, BEARISH, NEUTRAL members."""
        assert SentimentLabel.BULLISH == "bullish"
        assert SentimentLabel.BEARISH == "bearish"
        assert SentimentLabel.NEUTRAL == "neutral"

    def test_roundtrip_serialization(self) -> None:
        """SentimentLabel survives str → enum roundtrip."""
        for member in SentimentLabel:
            restored = SentimentLabel(member.value)
            assert restored is member


# ===========================================================================
# FundamentalSnapshot
# ===========================================================================


class TestFundamentalSnapshot:
    """Tests for the FundamentalSnapshot model."""

    def test_valid_construction(self, fundamental_snapshot: FundamentalSnapshot) -> None:
        """FundamentalSnapshot constructs with all fields correctly assigned."""
        assert fundamental_snapshot.ticker == "AAPL"
        assert fundamental_snapshot.pe_ratio == pytest.approx(28.5)
        assert fundamental_snapshot.forward_pe == pytest.approx(24.2)
        assert fundamental_snapshot.peg_ratio == pytest.approx(1.8)
        assert fundamental_snapshot.price_to_book == pytest.approx(45.3)
        assert fundamental_snapshot.debt_to_equity == pytest.approx(1.87)
        assert fundamental_snapshot.revenue_growth == pytest.approx(0.128)
        assert fundamental_snapshot.profit_margin == pytest.approx(0.265)
        assert fundamental_snapshot.market_cap == 2_800_000_000_000
        assert fundamental_snapshot.fetched_at == NOW_UTC

    def test_frozen(self, fundamental_snapshot: FundamentalSnapshot) -> None:
        """FundamentalSnapshot is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            fundamental_snapshot.pe_ratio = 30.0  # type: ignore[misc]

    def test_json_roundtrip(self, fundamental_snapshot: FundamentalSnapshot) -> None:
        """FundamentalSnapshot survives JSON roundtrip."""
        json_str = fundamental_snapshot.model_dump_json()
        restored = FundamentalSnapshot.model_validate_json(json_str)
        assert restored == fundamental_snapshot

    def test_all_none_optional_fields(self) -> None:
        """FundamentalSnapshot constructs with all optional fields as None."""
        snapshot = FundamentalSnapshot(ticker="MSFT", fetched_at=NOW_UTC)
        assert snapshot.pe_ratio is None
        assert snapshot.forward_pe is None
        assert snapshot.peg_ratio is None
        assert snapshot.price_to_book is None
        assert snapshot.debt_to_equity is None
        assert snapshot.revenue_growth is None
        assert snapshot.profit_margin is None
        assert snapshot.market_cap is None

    def test_rejects_nan_pe_ratio(self) -> None:
        """FundamentalSnapshot rejects NaN pe_ratio."""
        with pytest.raises(ValidationError, match="finite"):
            FundamentalSnapshot(
                ticker="AAPL",
                pe_ratio=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_inf_debt_to_equity(self) -> None:
        """FundamentalSnapshot rejects Inf debt_to_equity."""
        with pytest.raises(ValidationError, match="finite"):
            FundamentalSnapshot(
                ticker="AAPL",
                debt_to_equity=float("inf"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_neg_inf_revenue_growth(self) -> None:
        """FundamentalSnapshot rejects -Inf revenue_growth."""
        with pytest.raises(ValidationError, match="finite"):
            FundamentalSnapshot(
                ticker="AAPL",
                revenue_growth=float("-inf"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_nan_forward_pe(self) -> None:
        """FundamentalSnapshot rejects NaN forward_pe."""
        with pytest.raises(ValidationError, match="finite"):
            FundamentalSnapshot(
                ticker="AAPL",
                forward_pe=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_nan_peg_ratio(self) -> None:
        """FundamentalSnapshot rejects NaN peg_ratio."""
        with pytest.raises(ValidationError, match="finite"):
            FundamentalSnapshot(
                ticker="AAPL",
                peg_ratio=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_nan_price_to_book(self) -> None:
        """FundamentalSnapshot rejects NaN price_to_book."""
        with pytest.raises(ValidationError, match="finite"):
            FundamentalSnapshot(
                ticker="AAPL",
                price_to_book=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_nan_profit_margin(self) -> None:
        """FundamentalSnapshot rejects NaN profit_margin."""
        with pytest.raises(ValidationError, match="finite"):
            FundamentalSnapshot(
                ticker="AAPL",
                profit_margin=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_naive_datetime(self) -> None:
        """FundamentalSnapshot rejects naive datetime for fetched_at."""
        with pytest.raises(ValidationError, match="UTC"):
            FundamentalSnapshot(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 1, 12, 0, 0),
            )

    def test_rejects_non_utc_datetime(self) -> None:
        """FundamentalSnapshot rejects non-UTC timezone for fetched_at."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            FundamentalSnapshot(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=est),
            )

    def test_negative_pe_ratio_allowed(self) -> None:
        """Negative P/E ratio is valid (company with losses)."""
        snapshot = FundamentalSnapshot(ticker="RIVN", pe_ratio=-42.0, fetched_at=NOW_UTC)
        assert snapshot.pe_ratio == pytest.approx(-42.0)

    def test_negative_revenue_growth_allowed(self) -> None:
        """Negative revenue growth is valid (declining revenue)."""
        snapshot = FundamentalSnapshot(ticker="META", revenue_growth=-0.05, fetched_at=NOW_UTC)
        assert snapshot.revenue_growth == pytest.approx(-0.05)


# ===========================================================================
# UnusualFlowSnapshot
# ===========================================================================


class TestUnusualFlowSnapshot:
    """Tests for the UnusualFlowSnapshot model."""

    def test_valid_construction(self, unusual_flow_snapshot: UnusualFlowSnapshot) -> None:
        """UnusualFlowSnapshot constructs with all fields correctly assigned."""
        assert unusual_flow_snapshot.ticker == "AAPL"
        assert unusual_flow_snapshot.net_call_premium == pytest.approx(4_200_000.0)
        assert unusual_flow_snapshot.net_put_premium == pytest.approx(-1_500_000.0)
        assert unusual_flow_snapshot.call_volume == 150_000
        assert unusual_flow_snapshot.put_volume == 80_000
        assert unusual_flow_snapshot.put_call_ratio == pytest.approx(0.53)

    def test_frozen(self, unusual_flow_snapshot: UnusualFlowSnapshot) -> None:
        """UnusualFlowSnapshot is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            unusual_flow_snapshot.ticker = "MSFT"  # type: ignore[misc]

    def test_json_roundtrip(self, unusual_flow_snapshot: UnusualFlowSnapshot) -> None:
        """UnusualFlowSnapshot survives JSON roundtrip."""
        json_str = unusual_flow_snapshot.model_dump_json()
        restored = UnusualFlowSnapshot.model_validate_json(json_str)
        assert restored == unusual_flow_snapshot

    def test_rejects_nan_put_call_ratio(self) -> None:
        """UnusualFlowSnapshot rejects NaN put_call_ratio."""
        with pytest.raises(ValidationError, match="finite"):
            UnusualFlowSnapshot(
                ticker="AAPL",
                put_call_ratio=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_inf_net_call_premium(self) -> None:
        """UnusualFlowSnapshot rejects Inf net_call_premium."""
        with pytest.raises(ValidationError, match="finite"):
            UnusualFlowSnapshot(
                ticker="AAPL",
                net_call_premium=float("inf"),
                fetched_at=NOW_UTC,
            )

    def test_rejects_nan_net_put_premium(self) -> None:
        """UnusualFlowSnapshot rejects NaN net_put_premium."""
        with pytest.raises(ValidationError, match="finite"):
            UnusualFlowSnapshot(
                ticker="AAPL",
                net_put_premium=float("nan"),
                fetched_at=NOW_UTC,
            )

    def test_all_none_optional_fields(self) -> None:
        """UnusualFlowSnapshot constructs with all optional fields as None."""
        snapshot = UnusualFlowSnapshot(ticker="TSLA", fetched_at=NOW_UTC)
        assert snapshot.net_call_premium is None
        assert snapshot.net_put_premium is None
        assert snapshot.call_volume is None
        assert snapshot.put_volume is None
        assert snapshot.put_call_ratio is None

    def test_rejects_naive_datetime(self) -> None:
        """UnusualFlowSnapshot rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            UnusualFlowSnapshot(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 1, 12, 0, 0),
            )

    def test_rejects_non_utc_datetime(self) -> None:
        """UnusualFlowSnapshot rejects non-UTC timezone."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            UnusualFlowSnapshot(
                ticker="AAPL",
                fetched_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=est),
            )


# ===========================================================================
# NewsHeadline
# ===========================================================================


class TestNewsHeadline:
    """Tests for the NewsHeadline model."""

    def test_valid_construction(self, news_headline: NewsHeadline) -> None:
        """NewsHeadline constructs with all fields correctly assigned."""
        assert news_headline.title == "Apple Reports Record Q4 Earnings"
        assert news_headline.published_at == NOW_UTC
        assert news_headline.sentiment_score == pytest.approx(0.72)
        assert news_headline.source == "Reuters"

    def test_frozen(self, news_headline: NewsHeadline) -> None:
        """NewsHeadline is frozen."""
        with pytest.raises(ValidationError):
            news_headline.title = "Changed"  # type: ignore[misc]

    def test_json_roundtrip(self, news_headline: NewsHeadline) -> None:
        """NewsHeadline survives JSON roundtrip."""
        json_str = news_headline.model_dump_json()
        restored = NewsHeadline.model_validate_json(json_str)
        assert restored == news_headline

    def test_sentiment_at_lower_bound(self) -> None:
        """Sentiment score of exactly -1.0 is valid."""
        headline = NewsHeadline(title="Bad news", sentiment_score=-1.0)
        assert headline.sentiment_score == pytest.approx(-1.0)

    def test_sentiment_at_upper_bound(self) -> None:
        """Sentiment score of exactly 1.0 is valid."""
        headline = NewsHeadline(title="Great news", sentiment_score=1.0)
        assert headline.sentiment_score == pytest.approx(1.0)

    def test_rejects_sentiment_below_neg1(self) -> None:
        """NewsHeadline rejects sentiment_score below -1.0."""
        with pytest.raises(ValidationError, match=r"\[-1\.0, 1\.0\]"):
            NewsHeadline(title="X", sentiment_score=-1.01)

    def test_rejects_sentiment_above_pos1(self) -> None:
        """NewsHeadline rejects sentiment_score above 1.0."""
        with pytest.raises(ValidationError, match=r"\[-1\.0, 1\.0\]"):
            NewsHeadline(title="X", sentiment_score=1.01)

    def test_rejects_nan_sentiment(self) -> None:
        """NewsHeadline rejects NaN sentiment_score."""
        with pytest.raises(ValidationError, match="finite"):
            NewsHeadline(title="X", sentiment_score=float("nan"))

    def test_rejects_inf_sentiment(self) -> None:
        """NewsHeadline rejects Inf sentiment_score."""
        with pytest.raises(ValidationError, match="finite"):
            NewsHeadline(title="X", sentiment_score=float("inf"))

    def test_optional_fields_default_none(self) -> None:
        """NewsHeadline optional fields default to None."""
        headline = NewsHeadline(title="Test", sentiment_score=0.0)
        assert headline.published_at is None
        assert headline.source is None

    def test_rejects_naive_published_at(self) -> None:
        """NewsHeadline rejects naive datetime for published_at."""
        with pytest.raises(ValidationError, match="UTC"):
            NewsHeadline(
                title="X",
                sentiment_score=0.5,
                published_at=datetime(2026, 3, 1, 12, 0, 0),
            )

    def test_rejects_non_utc_published_at(self) -> None:
        """NewsHeadline rejects non-UTC timezone for published_at."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            NewsHeadline(
                title="X",
                sentiment_score=0.5,
                published_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=est),
            )


# ===========================================================================
# NewsSentimentSnapshot
# ===========================================================================


class TestNewsSentimentSnapshot:
    """Tests for the NewsSentimentSnapshot model."""

    def test_valid_construction(self, news_sentiment_snapshot: NewsSentimentSnapshot) -> None:
        """NewsSentimentSnapshot constructs with all fields correctly assigned."""
        assert news_sentiment_snapshot.ticker == "AAPL"
        assert len(news_sentiment_snapshot.headlines) == 1
        assert news_sentiment_snapshot.aggregate_sentiment == pytest.approx(0.42)
        assert news_sentiment_snapshot.sentiment_label == SentimentLabel.BULLISH
        assert news_sentiment_snapshot.article_count == 1

    def test_frozen(self, news_sentiment_snapshot: NewsSentimentSnapshot) -> None:
        """NewsSentimentSnapshot is frozen."""
        with pytest.raises(ValidationError):
            news_sentiment_snapshot.ticker = "MSFT"  # type: ignore[misc]

    def test_json_roundtrip(self, news_sentiment_snapshot: NewsSentimentSnapshot) -> None:
        """NewsSentimentSnapshot survives JSON roundtrip."""
        json_str = news_sentiment_snapshot.model_dump_json()
        restored = NewsSentimentSnapshot.model_validate_json(json_str)
        assert restored == news_sentiment_snapshot

    def test_aggregate_at_lower_bound(self) -> None:
        """Aggregate sentiment of exactly -1.0 is valid."""
        snapshot = NewsSentimentSnapshot(
            ticker="X",
            headlines=[],
            aggregate_sentiment=-1.0,
            sentiment_label=SentimentLabel.BEARISH,
            article_count=0,
            fetched_at=NOW_UTC,
        )
        assert snapshot.aggregate_sentiment == pytest.approx(-1.0)

    def test_aggregate_at_upper_bound(self) -> None:
        """Aggregate sentiment of exactly 1.0 is valid."""
        snapshot = NewsSentimentSnapshot(
            ticker="X",
            headlines=[],
            aggregate_sentiment=1.0,
            sentiment_label=SentimentLabel.BULLISH,
            article_count=0,
            fetched_at=NOW_UTC,
        )
        assert snapshot.aggregate_sentiment == pytest.approx(1.0)

    def test_rejects_nan_aggregate(self) -> None:
        """NewsSentimentSnapshot rejects NaN aggregate_sentiment."""
        with pytest.raises(ValidationError, match="finite"):
            NewsSentimentSnapshot(
                ticker="X",
                headlines=[],
                aggregate_sentiment=float("nan"),
                sentiment_label=SentimentLabel.NEUTRAL,
                article_count=0,
                fetched_at=NOW_UTC,
            )

    def test_rejects_aggregate_above_1(self) -> None:
        """NewsSentimentSnapshot rejects aggregate_sentiment > 1.0."""
        with pytest.raises(ValidationError, match=r"\[-1\.0, 1\.0\]"):
            NewsSentimentSnapshot(
                ticker="X",
                headlines=[],
                aggregate_sentiment=1.5,
                sentiment_label=SentimentLabel.BULLISH,
                article_count=0,
                fetched_at=NOW_UTC,
            )

    def test_rejects_aggregate_below_neg1(self) -> None:
        """NewsSentimentSnapshot rejects aggregate_sentiment < -1.0."""
        with pytest.raises(ValidationError, match=r"\[-1\.0, 1\.0\]"):
            NewsSentimentSnapshot(
                ticker="X",
                headlines=[],
                aggregate_sentiment=-1.5,
                sentiment_label=SentimentLabel.BEARISH,
                article_count=0,
                fetched_at=NOW_UTC,
            )

    def test_empty_headlines_list(self) -> None:
        """NewsSentimentSnapshot with empty headlines list is valid."""
        snapshot = NewsSentimentSnapshot(
            ticker="MSFT",
            headlines=[],
            aggregate_sentiment=0.0,
            sentiment_label=SentimentLabel.NEUTRAL,
            article_count=0,
            fetched_at=NOW_UTC,
        )
        assert snapshot.headlines == []
        assert snapshot.article_count == 0

    def test_rejects_negative_article_count(self) -> None:
        """NewsSentimentSnapshot rejects negative article_count."""
        with pytest.raises(ValidationError, match=">= 0"):
            NewsSentimentSnapshot(
                ticker="X",
                headlines=[],
                aggregate_sentiment=0.0,
                sentiment_label=SentimentLabel.NEUTRAL,
                article_count=-1,
                fetched_at=NOW_UTC,
            )

    def test_rejects_naive_datetime(self) -> None:
        """NewsSentimentSnapshot rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            NewsSentimentSnapshot(
                ticker="X",
                headlines=[],
                aggregate_sentiment=0.0,
                sentiment_label=SentimentLabel.NEUTRAL,
                article_count=0,
                fetched_at=datetime(2026, 3, 1, 12, 0, 0),
            )


# ===========================================================================
# OpenBBHealthStatus
# ===========================================================================


class TestOpenBBHealthStatus:
    """Tests for the OpenBBHealthStatus model."""

    def test_valid_construction(self) -> None:
        """OpenBBHealthStatus constructs with all fields."""
        status = OpenBBHealthStatus(
            openbb_available=True,
            yahoo_fundamentals=True,
            stockgrid_flow=True,
            last_checked=NOW_UTC,
        )
        assert status.openbb_available is True
        assert status.yahoo_fundamentals is True
        assert status.stockgrid_flow is True

    def test_all_false(self) -> None:
        """OpenBBHealthStatus with all providers unavailable."""
        status = OpenBBHealthStatus(
            openbb_available=False,
            yahoo_fundamentals=False,
            stockgrid_flow=False,
            last_checked=NOW_UTC,
        )
        assert status.openbb_available is False
        assert status.yahoo_fundamentals is False
        assert status.stockgrid_flow is False

    def test_frozen(self) -> None:
        """OpenBBHealthStatus is frozen."""
        status = OpenBBHealthStatus(
            openbb_available=True,
            yahoo_fundamentals=True,
            stockgrid_flow=True,
            last_checked=NOW_UTC,
        )
        with pytest.raises(ValidationError):
            status.openbb_available = False  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        """OpenBBHealthStatus survives JSON roundtrip."""
        status = OpenBBHealthStatus(
            openbb_available=True,
            yahoo_fundamentals=True,
            stockgrid_flow=False,
            last_checked=NOW_UTC,
        )
        json_str = status.model_dump_json()
        restored = OpenBBHealthStatus.model_validate_json(json_str)
        assert restored == status

    def test_rejects_naive_datetime(self) -> None:
        """OpenBBHealthStatus rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            OpenBBHealthStatus(
                openbb_available=True,
                yahoo_fundamentals=True,
                stockgrid_flow=True,
                last_checked=datetime(2026, 3, 1, 12, 0, 0),
            )

    def test_rejects_non_utc_datetime(self) -> None:
        """OpenBBHealthStatus rejects non-UTC timezone."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            OpenBBHealthStatus(
                openbb_available=True,
                yahoo_fundamentals=True,
                stockgrid_flow=True,
                last_checked=datetime(2026, 3, 1, 12, 0, 0, tzinfo=est),
            )


# ===========================================================================
# OpenBBConfig
# ===========================================================================


class TestOpenBBConfig:
    """Tests for the OpenBBConfig model."""

    def test_default_values(self) -> None:
        """OpenBBConfig defaults are correct."""
        config = OpenBBConfig()
        assert config.enabled is True
        assert config.fundamentals_enabled is True
        assert config.unusual_flow_enabled is True
        assert config.news_sentiment_enabled is True
        assert config.fundamentals_cache_ttl == 3600
        assert config.flow_cache_ttl == 300
        assert config.news_cache_ttl == 900
        assert config.request_timeout == 15
        assert config.max_retries == 2

    def test_disabled_master_switch(self) -> None:
        """OpenBBConfig enabled=False disables everything at config level."""
        config = OpenBBConfig(enabled=False)
        assert config.enabled is False
        # Individual toggles still respect their defaults
        assert config.fundamentals_enabled is True

    def test_custom_ttls(self) -> None:
        """OpenBBConfig accepts custom TTL values."""
        config = OpenBBConfig(
            fundamentals_cache_ttl=7200,
            flow_cache_ttl=600,
            news_cache_ttl=1800,
        )
        assert config.fundamentals_cache_ttl == 7200
        assert config.flow_cache_ttl == 600
        assert config.news_cache_ttl == 1800

    def test_nested_in_app_settings(self) -> None:
        """OpenBBConfig is nested in AppSettings with defaults."""
        settings = AppSettings()
        assert isinstance(settings.openbb, OpenBBConfig)
        assert settings.openbb.enabled is True

    def test_env_override_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_OPENBB__ENABLED=false disables OpenBB via env var."""
        monkeypatch.setenv("ARENA_OPENBB__ENABLED", "false")
        settings = AppSettings()
        assert settings.openbb.enabled is False

    def test_env_override_cache_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_OPENBB__FUNDAMENTALS_CACHE_TTL=7200 overrides default."""
        monkeypatch.setenv("ARENA_OPENBB__FUNDAMENTALS_CACHE_TTL", "7200")
        settings = AppSettings()
        assert settings.openbb.fundamentals_cache_ttl == 7200

    def test_env_override_request_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_OPENBB__REQUEST_TIMEOUT=30 overrides default."""
        monkeypatch.setenv("ARENA_OPENBB__REQUEST_TIMEOUT", "30")
        settings = AppSettings()
        assert settings.openbb.request_timeout == 30
