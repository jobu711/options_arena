"""Tests for Repository — ticker_metadata CRUD operations."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
    MetadataCoverage,
    TickerMetadata,
)

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(db)


def _make_metadata(**overrides: object) -> TickerMetadata:
    """Factory for TickerMetadata with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "sector": GICSSector.INFORMATION_TECHNOLOGY,
        "industry_group": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
        "market_cap_tier": MarketCapTier.MEGA,
        "company_name": "Apple Inc.",
        "raw_sector": "Technology",
        "raw_industry": "Consumer Electronics",
        "last_updated": datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return TickerMetadata(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# upsert_ticker_metadata + get_ticker_metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_and_get(repo: Repository) -> None:
    """Store and retrieve a TickerMetadata — all fields round-trip."""
    meta = _make_metadata()
    await repo.upsert_ticker_metadata(meta)

    result = await repo.get_ticker_metadata("AAPL")
    assert result is not None
    assert isinstance(result, TickerMetadata)
    assert result.ticker == "AAPL"
    assert result.sector == GICSSector.INFORMATION_TECHNOLOGY
    assert result.industry_group == GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT
    assert result.market_cap_tier == MarketCapTier.MEGA
    assert result.company_name == "Apple Inc."
    assert result.raw_sector == "Technology"
    assert result.raw_industry == "Consumer Electronics"
    assert result.last_updated == datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_upsert_overwrites_existing(repo: Repository) -> None:
    """Second upsert replaces the first row for the same ticker."""
    meta1 = _make_metadata(company_name="Apple Inc.")
    await repo.upsert_ticker_metadata(meta1)

    meta2 = _make_metadata(
        company_name="Apple Inc. (Updated)",
        sector=GICSSector.CONSUMER_DISCRETIONARY,
        last_updated=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
    )
    await repo.upsert_ticker_metadata(meta2)

    result = await repo.get_ticker_metadata("AAPL")
    assert result is not None
    assert result.company_name == "Apple Inc. (Updated)"
    assert result.sector == GICSSector.CONSUMER_DISCRETIONARY
    assert result.last_updated == datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_get_returns_none_for_missing(repo: Repository) -> None:
    """get_ticker_metadata returns None for an unknown ticker."""
    result = await repo.get_ticker_metadata("ZZZZZ")
    assert result is None


@pytest.mark.asyncio
async def test_get_normalizes_ticker_case(repo: Repository) -> None:
    """get_ticker_metadata('aapl') finds a row stored as 'AAPL'."""
    await repo.upsert_ticker_metadata(_make_metadata(ticker="AAPL"))

    result = await repo.get_ticker_metadata("aapl")
    assert result is not None
    assert result.ticker == "AAPL"


# ---------------------------------------------------------------------------
# upsert_ticker_metadata_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_upsert(repo: Repository) -> None:
    """Batch upsert persists multiple rows."""
    items = [
        _make_metadata(ticker="AAPL"),
        _make_metadata(ticker="MSFT", company_name="Microsoft Corporation"),
        _make_metadata(ticker="GOOGL", company_name="Alphabet Inc."),
    ]
    await repo.upsert_ticker_metadata_batch(items)

    all_meta = await repo.get_all_ticker_metadata()
    assert len(all_meta) == 3
    tickers = {m.ticker for m in all_meta}
    assert tickers == {"AAPL", "GOOGL", "MSFT"}


@pytest.mark.asyncio
async def test_batch_upsert_commit_false(repo: Repository) -> None:
    """commit=False defers the commit — data is only visible after explicit commit."""
    items = [_make_metadata(ticker="TSLA", company_name="Tesla Inc.")]
    await repo.upsert_ticker_metadata_batch(items, commit=False)

    # Data should still be visible within the same connection (uncommitted read)
    # but to verify commit=False works, we manually commit and confirm data persists
    conn = repo._db.conn  # noqa: SLF001
    await conn.commit()

    result = await repo.get_ticker_metadata("TSLA")
    assert result is not None
    assert result.company_name == "Tesla Inc."


# ---------------------------------------------------------------------------
# get_all_ticker_metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all(repo: Repository) -> None:
    """get_all_ticker_metadata returns all rows ordered by ticker."""
    items = [
        _make_metadata(ticker="MSFT", company_name="Microsoft"),
        _make_metadata(ticker="AAPL", company_name="Apple"),
        _make_metadata(ticker="GOOGL", company_name="Alphabet"),
    ]
    await repo.upsert_ticker_metadata_batch(items)

    results = await repo.get_all_ticker_metadata()
    assert len(results) == 3
    assert [m.ticker for m in results] == ["AAPL", "GOOGL", "MSFT"]


# ---------------------------------------------------------------------------
# get_stale_tickers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stale_tickers(repo: Repository) -> None:
    """Tickers older than max_age_days are returned as stale."""
    old_date = datetime.now(UTC) - timedelta(days=60)
    await repo.upsert_ticker_metadata(_make_metadata(ticker="OLD", last_updated=old_date))
    await repo.upsert_ticker_metadata(
        _make_metadata(ticker="FRESH", last_updated=datetime.now(UTC))
    )

    stale = await repo.get_stale_tickers(max_age_days=30)
    assert "OLD" in stale
    assert "FRESH" not in stale


@pytest.mark.asyncio
async def test_get_stale_tickers_excludes_fresh(repo: Repository) -> None:
    """Fresh tickers (within max_age_days) are not returned."""
    fresh_date = datetime.now(UTC) - timedelta(days=5)
    await repo.upsert_ticker_metadata(_make_metadata(ticker="RECENT", last_updated=fresh_date))

    stale = await repo.get_stale_tickers(max_age_days=30)
    assert stale == []


# ---------------------------------------------------------------------------
# get_metadata_coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_coverage_empty_db(repo: Repository) -> None:
    """Coverage on an empty table returns zeros."""
    cov = await repo.get_metadata_coverage()
    assert isinstance(cov, MetadataCoverage)
    assert cov.total == 0
    assert cov.with_sector == 0
    assert cov.with_industry_group == 0
    assert cov.coverage == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_metadata_coverage_with_data(repo: Repository) -> None:
    """Coverage reflects correct counts from stored data."""
    items = [
        _make_metadata(
            ticker="AAPL",
            sector=GICSSector.INFORMATION_TECHNOLOGY,
            industry_group=GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
        ),
        _make_metadata(
            ticker="MSFT",
            sector=GICSSector.INFORMATION_TECHNOLOGY,
            industry_group=None,
        ),
        _make_metadata(
            ticker="XYZ",
            sector=None,
            industry_group=None,
        ),
    ]
    await repo.upsert_ticker_metadata_batch(items)

    cov = await repo.get_metadata_coverage()
    assert cov.total == 3
    assert cov.with_sector == 2
    assert cov.with_industry_group == 1
    assert cov.coverage == pytest.approx(2.0 / 3.0)


# ---------------------------------------------------------------------------
# Enum round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enum_roundtrip(repo: Repository) -> None:
    """GICSSector and GICSIndustryGroup survive a DB round-trip as enum members."""
    meta = _make_metadata(
        sector=GICSSector.HEALTH_CARE,
        industry_group=GICSIndustryGroup.PHARMA_BIOTECH,
        market_cap_tier=MarketCapTier.LARGE,
    )
    await repo.upsert_ticker_metadata(meta)

    result = await repo.get_ticker_metadata("AAPL")
    assert result is not None
    assert isinstance(result.sector, GICSSector)
    assert result.sector is GICSSector.HEALTH_CARE
    assert isinstance(result.industry_group, GICSIndustryGroup)
    assert result.industry_group is GICSIndustryGroup.PHARMA_BIOTECH
    assert isinstance(result.market_cap_tier, MarketCapTier)
    assert result.market_cap_tier is MarketCapTier.LARGE


@pytest.mark.asyncio
async def test_none_enums_roundtrip(repo: Repository) -> None:
    """None values for optional enum fields survive a DB round-trip."""
    meta = _make_metadata(
        sector=None,
        industry_group=None,
        market_cap_tier=None,
        company_name=None,
    )
    await repo.upsert_ticker_metadata(meta)

    result = await repo.get_ticker_metadata("AAPL")
    assert result is not None
    assert result.sector is None
    assert result.industry_group is None
    assert result.market_cap_tier is None
    assert result.company_name is None
