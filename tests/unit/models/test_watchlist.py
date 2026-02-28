"""Tests for Watchlist Pydantic models."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models.watchlist import (
    Watchlist,
    WatchlistDetail,
    WatchlistTicker,
    WatchlistTickerDetail,
)

# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------


class TestWatchlist:
    """Tests for the Watchlist model."""

    def test_construction_valid(self) -> None:
        """Watchlist constructs with valid data."""
        wl = Watchlist(id=1, name="My Picks", created_at=datetime(2026, 2, 27, tzinfo=UTC))
        assert wl.id == 1
        assert wl.name == "My Picks"
        assert wl.created_at.tzinfo is not None

    def test_frozen(self) -> None:
        """Watchlist is frozen (immutable)."""
        wl = Watchlist(id=1, name="Test", created_at=datetime(2026, 2, 27, tzinfo=UTC))
        with pytest.raises(ValidationError):
            wl.name = "Changed"  # type: ignore[misc]

    def test_utc_validator_rejects_naive(self) -> None:
        """Watchlist rejects naive datetime (no tzinfo)."""
        with pytest.raises(ValidationError, match="UTC"):
            Watchlist(id=1, name="Bad", created_at=datetime(2026, 2, 27))

    def test_utc_validator_rejects_non_utc(self) -> None:
        """Watchlist rejects non-UTC timezone."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            Watchlist(id=1, name="Bad", created_at=datetime(2026, 2, 27, tzinfo=est))

    def test_json_roundtrip(self) -> None:
        """Watchlist survives JSON serialization roundtrip."""
        wl = Watchlist(id=1, name="RT", created_at=datetime(2026, 2, 27, 10, 30, tzinfo=UTC))
        loaded = Watchlist.model_validate_json(wl.model_dump_json())
        assert loaded == wl


# ---------------------------------------------------------------------------
# WatchlistTicker
# ---------------------------------------------------------------------------


class TestWatchlistTicker:
    """Tests for the WatchlistTicker model."""

    def test_construction_valid(self) -> None:
        """WatchlistTicker constructs with valid data."""
        wt = WatchlistTicker(
            id=1,
            watchlist_id=1,
            ticker="AAPL",
            added_at=datetime(2026, 2, 27, tzinfo=UTC),
        )
        assert wt.ticker == "AAPL"
        assert wt.watchlist_id == 1

    def test_frozen(self) -> None:
        """WatchlistTicker is frozen."""
        wt = WatchlistTicker(
            id=1, watchlist_id=1, ticker="AAPL", added_at=datetime(2026, 2, 27, tzinfo=UTC)
        )
        with pytest.raises(ValidationError):
            wt.ticker = "MSFT"  # type: ignore[misc]

    def test_utc_validator_rejects_naive(self) -> None:
        """WatchlistTicker rejects naive datetime."""
        with pytest.raises(ValidationError, match="UTC"):
            WatchlistTicker(id=1, watchlist_id=1, ticker="AAPL", added_at=datetime(2026, 2, 27))

    def test_json_roundtrip(self) -> None:
        """WatchlistTicker survives JSON roundtrip."""
        wt = WatchlistTicker(
            id=1, watchlist_id=1, ticker="AAPL", added_at=datetime(2026, 2, 27, tzinfo=UTC)
        )
        loaded = WatchlistTicker.model_validate_json(wt.model_dump_json())
        assert loaded == wt


# ---------------------------------------------------------------------------
# WatchlistTickerDetail
# ---------------------------------------------------------------------------


class TestWatchlistTickerDetail:
    """Tests for the WatchlistTickerDetail model."""

    def test_construction_minimal(self) -> None:
        """WatchlistTickerDetail constructs with only required fields."""
        wtd = WatchlistTickerDetail(ticker="AAPL", added_at=datetime(2026, 2, 27, tzinfo=UTC))
        assert wtd.ticker == "AAPL"
        assert wtd.composite_score is None
        assert wtd.direction is None
        assert wtd.last_debate_at is None

    def test_construction_full(self) -> None:
        """WatchlistTickerDetail constructs with all fields populated."""
        ts = datetime(2026, 2, 27, tzinfo=UTC)
        wtd = WatchlistTickerDetail(
            ticker="MSFT",
            added_at=ts,
            composite_score=85.3,
            direction="bullish",
            last_debate_at=ts,
        )
        assert wtd.composite_score == pytest.approx(85.3)
        assert wtd.direction == "bullish"
        assert wtd.last_debate_at == ts

    def test_utc_validator_on_added_at(self) -> None:
        """WatchlistTickerDetail rejects naive added_at."""
        with pytest.raises(ValidationError, match="UTC"):
            WatchlistTickerDetail(ticker="X", added_at=datetime(2026, 2, 27))

    def test_utc_validator_on_last_debate_at(self) -> None:
        """WatchlistTickerDetail rejects naive last_debate_at."""
        with pytest.raises(ValidationError, match="UTC"):
            WatchlistTickerDetail(
                ticker="X",
                added_at=datetime(2026, 2, 27, tzinfo=UTC),
                last_debate_at=datetime(2026, 2, 27),
            )


# ---------------------------------------------------------------------------
# WatchlistDetail
# ---------------------------------------------------------------------------


class TestWatchlistDetail:
    """Tests for the WatchlistDetail model."""

    def test_construction_valid(self) -> None:
        """WatchlistDetail constructs with valid data."""
        ts = datetime(2026, 2, 27, tzinfo=UTC)
        detail = WatchlistDetail(
            id=1,
            name="Tech",
            created_at=ts,
            tickers=[
                WatchlistTickerDetail(ticker="AAPL", added_at=ts, composite_score=80.0),
                WatchlistTickerDetail(ticker="MSFT", added_at=ts),
            ],
        )
        assert detail.id == 1
        assert len(detail.tickers) == 2

    def test_frozen(self) -> None:
        """WatchlistDetail is frozen."""
        ts = datetime(2026, 2, 27, tzinfo=UTC)
        detail = WatchlistDetail(id=1, name="Test", created_at=ts, tickers=[])
        with pytest.raises(ValidationError):
            detail.name = "Changed"  # type: ignore[misc]

    def test_utc_validator(self) -> None:
        """WatchlistDetail rejects naive created_at."""
        with pytest.raises(ValidationError, match="UTC"):
            WatchlistDetail(id=1, name="Bad", created_at=datetime(2026, 2, 27), tickers=[])

    def test_empty_tickers(self) -> None:
        """WatchlistDetail with empty tickers list is valid."""
        ts = datetime(2026, 2, 27, tzinfo=UTC)
        detail = WatchlistDetail(id=1, name="Empty", created_at=ts, tickers=[])
        assert detail.tickers == []

    def test_json_roundtrip(self) -> None:
        """WatchlistDetail survives JSON roundtrip."""
        ts = datetime(2026, 2, 27, tzinfo=UTC)
        detail = WatchlistDetail(
            id=1,
            name="RT",
            created_at=ts,
            tickers=[
                WatchlistTickerDetail(ticker="AAPL", added_at=ts, composite_score=75.0),
            ],
        )
        loaded = WatchlistDetail.model_validate_json(detail.model_dump_json())
        assert loaded == detail
