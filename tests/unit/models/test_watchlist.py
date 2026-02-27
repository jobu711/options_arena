"""Unit tests for watchlist models: Watchlist, WatchlistTicker, WatchlistDetail.

Tests cover:
- Happy path construction with all fields
- Frozen enforcement (attribute reassignment raises ValidationError)
- UTC validator rejects naive and non-UTC timestamps
- Default values (id=None, description=None)
- JSON serialization roundtrip
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import Watchlist, WatchlistDetail, WatchlistTicker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_watchlist() -> Watchlist:
    """Create a valid Watchlist instance for reuse."""
    return Watchlist(
        id=1,
        name="Tech Stocks",
        description="Top technology stocks",
        created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_watchlist_ticker() -> WatchlistTicker:
    """Create a valid WatchlistTicker instance for reuse."""
    return WatchlistTicker(
        id=10,
        watchlist_id=1,
        ticker="AAPL",
        added_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_watchlist_detail(sample_watchlist_ticker: WatchlistTicker) -> WatchlistDetail:
    """Create a valid WatchlistDetail instance for reuse."""
    return WatchlistDetail(
        id=1,
        name="Tech Stocks",
        description="Top technology stocks",
        created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        tickers=[sample_watchlist_ticker],
    )


# ---------------------------------------------------------------------------
# Watchlist Tests
# ---------------------------------------------------------------------------


class TestWatchlist:
    """Tests for the Watchlist model."""

    def test_happy_path_construction(self, sample_watchlist: Watchlist) -> None:
        """Watchlist constructs with all fields correctly assigned."""
        assert sample_watchlist.id == 1
        assert sample_watchlist.name == "Tech Stocks"
        assert sample_watchlist.description == "Top technology stocks"
        assert sample_watchlist.created_at == datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert sample_watchlist.updated_at == datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_frozen_enforcement(self, sample_watchlist: Watchlist) -> None:
        """Watchlist is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_watchlist.name = "New Name"  # type: ignore[misc]

    def test_id_defaults_to_none(self) -> None:
        """Watchlist id defaults to None when not provided."""
        wl = Watchlist(
            name="My List",
            created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        )
        assert wl.id is None

    def test_description_defaults_to_none(self) -> None:
        """Watchlist description defaults to None when not provided."""
        wl = Watchlist(
            name="My List",
            created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        )
        assert wl.description is None

    def test_naive_created_at_raises(self) -> None:
        """Watchlist rejects naive datetime for created_at."""
        with pytest.raises(ValidationError, match="UTC"):
            Watchlist(
                name="My List",
                created_at=datetime(2026, 1, 15, 10, 0, 0),  # naive
                updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            )

    def test_non_utc_created_at_raises(self) -> None:
        """Watchlist rejects non-UTC timezone for created_at."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            Watchlist(
                name="My List",
                created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=est),
                updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            )

    def test_naive_updated_at_raises(self) -> None:
        """Watchlist rejects naive datetime for updated_at."""
        with pytest.raises(ValidationError, match="UTC"):
            Watchlist(
                name="My List",
                created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
                updated_at=datetime(2026, 1, 15, 10, 0, 0),  # naive
            )

    def test_json_roundtrip(self, sample_watchlist: Watchlist) -> None:
        """Watchlist survives JSON roundtrip."""
        json_str = sample_watchlist.model_dump_json()
        restored = Watchlist.model_validate_json(json_str)
        assert restored == sample_watchlist


# ---------------------------------------------------------------------------
# WatchlistTicker Tests
# ---------------------------------------------------------------------------


class TestWatchlistTicker:
    """Tests for the WatchlistTicker model."""

    def test_happy_path_construction(self, sample_watchlist_ticker: WatchlistTicker) -> None:
        """WatchlistTicker constructs with all fields correctly assigned."""
        assert sample_watchlist_ticker.id == 10
        assert sample_watchlist_ticker.watchlist_id == 1
        assert sample_watchlist_ticker.ticker == "AAPL"
        assert sample_watchlist_ticker.added_at == datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

    def test_frozen_enforcement(self, sample_watchlist_ticker: WatchlistTicker) -> None:
        """WatchlistTicker is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_watchlist_ticker.ticker = "MSFT"  # type: ignore[misc]

    def test_id_defaults_to_none(self) -> None:
        """WatchlistTicker id defaults to None when not provided."""
        wt = WatchlistTicker(
            watchlist_id=1,
            ticker="MSFT",
            added_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        assert wt.id is None

    def test_naive_added_at_raises(self) -> None:
        """WatchlistTicker rejects naive datetime for added_at."""
        with pytest.raises(ValidationError, match="UTC"):
            WatchlistTicker(
                watchlist_id=1,
                ticker="AAPL",
                added_at=datetime(2026, 1, 15, 12, 0, 0),  # naive
            )

    def test_json_roundtrip(self, sample_watchlist_ticker: WatchlistTicker) -> None:
        """WatchlistTicker survives JSON roundtrip."""
        json_str = sample_watchlist_ticker.model_dump_json()
        restored = WatchlistTicker.model_validate_json(json_str)
        assert restored == sample_watchlist_ticker


# ---------------------------------------------------------------------------
# WatchlistDetail Tests
# ---------------------------------------------------------------------------


class TestWatchlistDetail:
    """Tests for the WatchlistDetail model."""

    def test_happy_path_construction(self, sample_watchlist_detail: WatchlistDetail) -> None:
        """WatchlistDetail constructs with all fields including tickers list."""
        assert sample_watchlist_detail.id == 1
        assert sample_watchlist_detail.name == "Tech Stocks"
        assert sample_watchlist_detail.description == "Top technology stocks"
        assert len(sample_watchlist_detail.tickers) == 1
        assert sample_watchlist_detail.tickers[0].ticker == "AAPL"

    def test_frozen_enforcement(self, sample_watchlist_detail: WatchlistDetail) -> None:
        """WatchlistDetail is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_watchlist_detail.name = "New Name"  # type: ignore[misc]

    def test_empty_tickers_list(self) -> None:
        """WatchlistDetail accepts an empty tickers list."""
        wd = WatchlistDetail(
            id=2,
            name="Empty List",
            created_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            tickers=[],
        )
        assert wd.tickers == []

    def test_naive_created_at_raises(self) -> None:
        """WatchlistDetail rejects naive datetime for created_at."""
        with pytest.raises(ValidationError, match="UTC"):
            WatchlistDetail(
                name="Bad List",
                created_at=datetime(2026, 1, 15, 10, 0, 0),  # naive
                updated_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
                tickers=[],
            )

    def test_json_roundtrip(self, sample_watchlist_detail: WatchlistDetail) -> None:
        """WatchlistDetail survives JSON roundtrip."""
        json_str = sample_watchlist_detail.model_dump_json()
        restored = WatchlistDetail.model_validate_json(json_str)
        assert restored == sample_watchlist_detail
