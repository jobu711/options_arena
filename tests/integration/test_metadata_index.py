"""Integration tests for the metadata index end-to-end flow.

Verifies the full lifecycle:
  - Bulk index via batch upsert → Phase 1 loads metadata → sector_map enrichment
  - Phase 3 write-back via map_yfinance_to_metadata → persists → Phase 1 reads next scan
  - S&P 500 CSV priority over conflicting metadata
  - Fail-open behavior for uncached tickers in sector filters
  - Coverage accuracy, stale refresh, batch upsert atomicity
  - Concurrent Phase 3 writes (asyncio.gather)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

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
from options_arena.models.enums import DividendSource
from options_arena.models.market_data import TickerInfo
from options_arena.services.universe import map_yfinance_to_metadata

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(
    ticker: str = "AAPL",
    *,
    sector: GICSSector | None = GICSSector.INFORMATION_TECHNOLOGY,
    industry_group: GICSIndustryGroup | None = GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    market_cap_tier: MarketCapTier | None = MarketCapTier.MEGA,
    company_name: str | None = "Apple Inc.",
    raw_sector: str = "Technology",
    raw_industry: str = "Consumer Electronics",
    last_updated: datetime | None = None,
) -> TickerMetadata:
    """Factory for TickerMetadata with sensible defaults."""
    return TickerMetadata(
        ticker=ticker,
        sector=sector,
        industry_group=industry_group,
        market_cap_tier=market_cap_tier,
        company_name=company_name,
        raw_sector=raw_sector,
        raw_industry=raw_industry,
        last_updated=last_updated or datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
    )


def _make_ticker_info(
    ticker: str = "AAPL",
    *,
    sector: str = "Technology",
    industry: str = "Consumer Electronics",
    company_name: str = "Apple Inc.",
    market_cap: int | None = 3_000_000_000_000,
    current_price: str = "185.00",
) -> TickerInfo:
    """Factory for TickerInfo with sensible defaults."""
    price = Decimal(current_price)
    return TickerInfo(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        industry=industry,
        market_cap=market_cap,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=price,
        fifty_two_week_high=price * Decimal("1.3"),
        fifty_two_week_low=price * Decimal("0.7"),
    )


# ---------------------------------------------------------------------------
# TestMetadataIndexIntegration
# ---------------------------------------------------------------------------


class TestMetadataIndexIntegration:
    """End-to-end integration tests for the metadata index flow."""

    @pytest.mark.asyncio
    async def test_bulk_index_to_phase1_flow(self, repo: Repository) -> None:
        """Verify bulk-indexed metadata loads in Phase 1 and extends sector_map.

        Simulates:
        1. Batch upsert metadata for several tickers (including non-S&P 500)
        2. Call get_all_ticker_metadata() (Phase 1 step)
        3. Build sector_map from metadata, just like pipeline._phase_universe does
        4. Assert non-S&P 500 tickers have sectors in the map
        """
        # Insert metadata for tickers — some S&P 500 (AAPL, MSFT) and some not (PLTR, RKLB)
        batch_items = [
            _make_metadata("AAPL", sector=GICSSector.INFORMATION_TECHNOLOGY),
            _make_metadata(
                "MSFT",
                sector=GICSSector.INFORMATION_TECHNOLOGY,
                company_name="Microsoft Corporation",
            ),
            _make_metadata(
                "PLTR",
                sector=GICSSector.INFORMATION_TECHNOLOGY,
                company_name="Palantir Technologies Inc.",
                industry_group=GICSIndustryGroup.SOFTWARE_SERVICES,
            ),
            _make_metadata(
                "RKLB",
                sector=GICSSector.INDUSTRIALS,
                company_name="Rocket Lab USA Inc.",
                industry_group=GICSIndustryGroup.CAPITAL_GOODS,
            ),
        ]
        await repo.upsert_ticker_metadata_batch(batch_items)

        # Phase 1 metadata enrichment: load all metadata
        all_metadata = await repo.get_all_ticker_metadata()
        assert len(all_metadata) == 4

        # Simulate Phase 1 merge logic: start with S&P 500 CSV data (only AAPL, MSFT)
        sector_map: dict[str, GICSSector] = {
            "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
            "MSFT": GICSSector.INFORMATION_TECHNOLOGY,
        }
        industry_group_map: dict[str, GICSIndustryGroup] = {}

        # Apply metadata enrichment (exactly as pipeline.py does)
        for meta in all_metadata:
            if meta.ticker not in sector_map and meta.sector is not None:
                sector_map[meta.ticker] = meta.sector
            if meta.ticker not in industry_group_map and meta.industry_group is not None:
                industry_group_map[meta.ticker] = meta.industry_group

        # Non-S&P 500 tickers should now have sectors from metadata
        assert "PLTR" in sector_map
        assert sector_map["PLTR"] == GICSSector.INFORMATION_TECHNOLOGY
        assert "RKLB" in sector_map
        assert sector_map["RKLB"] == GICSSector.INDUSTRIALS

        # Industry groups should be populated
        assert "PLTR" in industry_group_map
        assert industry_group_map["PLTR"] == GICSIndustryGroup.SOFTWARE_SERVICES
        assert "RKLB" in industry_group_map
        assert industry_group_map["RKLB"] == GICSIndustryGroup.CAPITAL_GOODS

    @pytest.mark.asyncio
    async def test_phase3_writeback_to_phase1_flow(self, repo: Repository) -> None:
        """Verify Phase 3 write-back persists and Phase 1 reads it on next scan.

        Simulates:
        1. Phase 3: fetch_ticker_info returns TickerInfo
        2. map_yfinance_to_metadata() converts to TickerMetadata
        3. upsert to DB
        4. Phase 1 (next scan): get_all_ticker_metadata returns the persisted data
        5. Metadata has correct resolved GICS enums
        """
        # Phase 3: simulate fetching ticker info and mapping to metadata
        ticker_info = _make_ticker_info(
            "NVDA",
            sector="Technology",
            industry="Semiconductors",
            company_name="NVIDIA Corporation",
            market_cap=3_500_000_000_000,
        )

        metadata = map_yfinance_to_metadata(ticker_info)

        # Verify the mapping produced correct results
        assert metadata.ticker == "NVDA"
        assert metadata.sector == GICSSector.INFORMATION_TECHNOLOGY
        assert metadata.company_name == "NVIDIA Corporation"
        assert metadata.market_cap_tier == MarketCapTier.MEGA
        assert metadata.raw_sector == "Technology"
        assert metadata.raw_industry == "Semiconductors"

        # Phase 3: persist metadata
        await repo.upsert_ticker_metadata(metadata)

        # Phase 1 (next scan): read it back
        all_metadata = await repo.get_all_ticker_metadata()
        assert len(all_metadata) == 1

        result = all_metadata[0]
        assert result.ticker == "NVDA"
        assert result.sector == GICSSector.INFORMATION_TECHNOLOGY
        assert result.company_name == "NVIDIA Corporation"
        assert result.market_cap_tier == MarketCapTier.MEGA
        assert result.raw_sector == "Technology"

    @pytest.mark.asyncio
    async def test_sp500_priority_over_metadata(self, repo: Repository) -> None:
        """Verify S&P 500 CSV sector is preserved when metadata conflicts.

        The pipeline's Phase 1 merge logic only adds metadata for tickers NOT already
        in sector_map. So if AAPL is in the CSV as Technology, and metadata has it as
        Energy (wrong), the CSV value wins.
        """
        # Insert metadata with wrong sector for AAPL
        await repo.upsert_ticker_metadata(
            _make_metadata("AAPL", sector=GICSSector.ENERGY, raw_sector="Energy")
        )

        # S&P 500 CSV provides the correct sector
        sector_map: dict[str, GICSSector] = {
            "AAPL": GICSSector.INFORMATION_TECHNOLOGY,
        }

        # Apply metadata enrichment (same as pipeline)
        all_metadata = await repo.get_all_ticker_metadata()
        for meta in all_metadata:
            if meta.ticker not in sector_map and meta.sector is not None:
                sector_map[meta.ticker] = meta.sector

        # AAPL should still be Information Technology (from CSV), not Energy (from metadata)
        assert sector_map["AAPL"] == GICSSector.INFORMATION_TECHNOLOGY

    @pytest.mark.asyncio
    async def test_fail_open_uncached_tickers(self, repo: Repository) -> None:
        """Verify uncached tickers pass through sector filters.

        When a ticker has no metadata in the index, it should NOT be excluded by
        sector filters. The fail-open design ensures uncached tickers are included
        unless they fail other criteria.
        """
        # Insert metadata for only AAPL and MSFT with Technology sector
        await repo.upsert_ticker_metadata_batch(
            [
                _make_metadata("AAPL", sector=GICSSector.INFORMATION_TECHNOLOGY),
                _make_metadata("MSFT", sector=GICSSector.INFORMATION_TECHNOLOGY),
            ]
        )

        # All tickers in the universe (includes some without metadata)
        all_tickers = ["AAPL", "MSFT", "UNKNOWN_TICKER_1", "UNKNOWN_TICKER_2"]

        # Build sector_map from metadata
        sector_map: dict[str, GICSSector] = {}
        all_metadata = await repo.get_all_ticker_metadata()
        for meta in all_metadata:
            if meta.sector is not None:
                sector_map[meta.ticker] = meta.sector

        # Simulate sector filter: "only Technology" filter
        target_sector = GICSSector.INFORMATION_TECHNOLOGY
        filtered_tickers = [
            t for t in all_tickers if t not in sector_map or sector_map[t] == target_sector
        ]

        # Cached tickers matching filter: AAPL, MSFT
        # Uncached tickers pass through (fail-open): UNKNOWN_TICKER_1, UNKNOWN_TICKER_2
        assert "AAPL" in filtered_tickers
        assert "MSFT" in filtered_tickers
        assert "UNKNOWN_TICKER_1" in filtered_tickers
        assert "UNKNOWN_TICKER_2" in filtered_tickers

    @pytest.mark.asyncio
    async def test_metadata_coverage_accuracy(self, repo: Repository) -> None:
        """Verify get_metadata_coverage returns accurate stats.

        Insert a known mix of metadata: some with sector, some without,
        some with industry_group, some without. Assert exact counts.
        """
        items = [
            # Full metadata
            _make_metadata(
                "AAPL",
                sector=GICSSector.INFORMATION_TECHNOLOGY,
                industry_group=GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
            ),
            # Sector only, no industry group
            _make_metadata(
                "XOM",
                sector=GICSSector.ENERGY,
                industry_group=None,
                company_name="Exxon Mobil Corporation",
                raw_sector="Energy",
                raw_industry="Oil & Gas Integrated",
            ),
            # No sector, no industry group
            _make_metadata(
                "MYSTERY",
                sector=None,
                industry_group=None,
                company_name="Mystery Corp",
                raw_sector="Unknown",
                raw_industry="Unknown",
            ),
            # Industry group but no sector (unlikely but valid)
            _make_metadata(
                "WEIRD",
                sector=None,
                industry_group=GICSIndustryGroup.BANKS,
                company_name="Weird Bank Inc.",
                raw_sector="Unknown",
                raw_industry="Banks",
            ),
        ]
        await repo.upsert_ticker_metadata_batch(items)

        cov = await repo.get_metadata_coverage()
        assert isinstance(cov, MetadataCoverage)
        assert cov.total == 4
        assert cov.with_sector == 2  # AAPL, XOM
        assert cov.with_industry_group == 2  # AAPL, WEIRD
        assert cov.coverage == pytest.approx(2.0 / 4.0)  # 50% sector coverage

    @pytest.mark.asyncio
    async def test_stale_refresh_re_indexes(self, repo: Repository) -> None:
        """Verify max_age=0 causes all tickers to be returned as stale.

        This simulates the "force re-index" flow: set max_age_days=0 so that
        any ticker with a last_updated timestamp is considered stale (since
        last_updated < now - 0 days = now, which is true for all past timestamps).
        """
        # Insert metadata with current-ish timestamps
        now = datetime.now(UTC)
        items = [
            _make_metadata("AAPL", last_updated=now),
            _make_metadata("MSFT", last_updated=now, company_name="Microsoft"),
            _make_metadata("GOOG", last_updated=now, company_name="Alphabet"),
        ]
        await repo.upsert_ticker_metadata_batch(items)

        # max_age_days=0: cutoff = now - 0 days = now
        # All tickers have last_updated <= now, so all are stale
        stale = await repo.get_stale_tickers(max_age_days=0)
        assert len(stale) == 3
        assert set(stale) == {"AAPL", "GOOG", "MSFT"}

    @pytest.mark.asyncio
    async def test_batch_upsert_atomic(self, repo: Repository) -> None:
        """Verify batch upsert stores all items and they are all retrievable."""
        tickers = [f"TICK{i}" for i in range(20)]
        items = [
            _make_metadata(
                t,
                sector=GICSSector.INFORMATION_TECHNOLOGY,
                company_name=f"Company {t}",
            )
            for t in tickers
        ]

        await repo.upsert_ticker_metadata_batch(items)

        # Verify all items stored
        all_meta = await repo.get_all_ticker_metadata()
        assert len(all_meta) == 20
        stored_tickers = {m.ticker for m in all_meta}
        assert stored_tickers == set(tickers)

        # Verify coverage
        cov = await repo.get_metadata_coverage()
        assert cov.total == 20
        assert cov.with_sector == 20
        assert cov.coverage == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_concurrent_phase3_writes(self, repo: Repository) -> None:
        """Verify multiple concurrent upserts do not conflict.

        Simulates Phase 3 processing multiple tickers concurrently via
        asyncio.gather, each writing metadata independently.
        """
        tickers_info = [
            _make_ticker_info(
                "AAPL",
                sector="Technology",
                industry="Consumer Electronics",
                company_name="Apple Inc.",
                market_cap=3_000_000_000_000,
            ),
            _make_ticker_info(
                "MSFT",
                sector="Technology",
                industry="Software—Infrastructure",
                company_name="Microsoft Corporation",
                market_cap=2_800_000_000_000,
            ),
            _make_ticker_info(
                "XOM",
                sector="Energy",
                industry="Oil & Gas Integrated",
                company_name="Exxon Mobil Corporation",
                market_cap=450_000_000_000,
            ),
            _make_ticker_info(
                "JPM",
                sector="Financial Services",
                industry="Banks—Diversified",
                company_name="JPMorgan Chase & Co.",
                market_cap=600_000_000_000,
            ),
            _make_ticker_info(
                "JNJ",
                sector="Healthcare",
                industry="Drug Manufacturers—General",
                company_name="Johnson & Johnson",
                market_cap=380_000_000_000,
            ),
        ]

        async def _write_metadata(ti: TickerInfo) -> None:
            metadata = map_yfinance_to_metadata(ti)
            await repo.upsert_ticker_metadata(metadata)

        # Run all writes concurrently
        await asyncio.gather(*[_write_metadata(ti) for ti in tickers_info])

        # Verify all stored correctly
        all_meta = await repo.get_all_ticker_metadata()
        assert len(all_meta) == 5
        stored_tickers = {m.ticker for m in all_meta}
        assert stored_tickers == {"AAPL", "MSFT", "XOM", "JPM", "JNJ"}

        # Verify sector resolution happened correctly
        meta_map = {m.ticker: m for m in all_meta}
        assert meta_map["AAPL"].sector == GICSSector.INFORMATION_TECHNOLOGY
        assert meta_map["XOM"].sector == GICSSector.ENERGY
        assert meta_map["JNJ"].sector == GICSSector.HEALTH_CARE

        # Verify all have mega market cap tier
        for m in all_meta:
            assert m.market_cap_tier == MarketCapTier.MEGA
