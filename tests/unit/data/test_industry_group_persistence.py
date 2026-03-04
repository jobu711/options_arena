"""Tests for industry_group and thematic_tags persistence (migration 016)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    GICSIndustryGroup,
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scan_run(**overrides: object) -> ScanRun:
    """Build a ScanRun with sensible defaults."""
    defaults: dict[str, object] = {
        "started_at": datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 15, 10, 35, 0, tzinfo=UTC),
        "preset": ScanPreset.SP500,
        "tickers_scanned": 500,
        "tickers_scored": 450,
        "recommendations": 8,
    }
    defaults.update(overrides)
    return ScanRun(**defaults)  # type: ignore[arg-type]


def _make_ticker_score(**overrides: object) -> TickerScore:
    """Build a TickerScore with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "composite_score": 78.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1),
    }
    defaults.update(overrides)
    return TickerScore(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# industry_group persistence
# ---------------------------------------------------------------------------


class TestIndustryGroupPersistence:
    """Tests for industry_group column on ticker_scores."""

    @pytest.mark.asyncio
    async def test_save_score_with_industry_group(self, repo: Repository) -> None:
        """Verify industry_group persisted and retrieved."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score(industry_group=GICSIndustryGroup.SOFTWARE_SERVICES)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].industry_group == GICSIndustryGroup.SOFTWARE_SERVICES

    @pytest.mark.asyncio
    async def test_save_score_without_industry_group(self, repo: Repository) -> None:
        """Verify None industry_group stored as NULL and retrieved as None."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score()  # no industry_group set
        assert score.industry_group is None

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].industry_group is None

    @pytest.mark.asyncio
    async def test_industry_group_roundtrip_special_characters(self, repo: Repository) -> None:
        """Verify industry_group with ampersand and spaces roundtrips correctly."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        ig = GICSIndustryGroup.PHARMA_BIOTECH
        score = _make_ticker_score(industry_group=ig)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert result[0].industry_group == ig

    @pytest.mark.asyncio
    async def test_mixed_industry_group_in_batch(self, repo: Repository) -> None:
        """Verify batch with mixed None and populated industry_group values."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        scores = [
            _make_ticker_score(
                ticker="AAPL",
                industry_group=GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
            ),
            _make_ticker_score(ticker="MSFT"),  # None
            _make_ticker_score(ticker="JPM", industry_group=GICSIndustryGroup.BANKS),
        ]
        await repo.save_ticker_scores(scan_id, scores)
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 3
        by_ticker = {r.ticker: r for r in result}
        assert by_ticker["AAPL"].industry_group == GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT
        assert by_ticker["MSFT"].industry_group is None
        assert by_ticker["JPM"].industry_group == GICSIndustryGroup.BANKS


# ---------------------------------------------------------------------------
# thematic_tags persistence
# ---------------------------------------------------------------------------


class TestThematicTagsPersistence:
    """Tests for thematic_tags_json column on ticker_scores."""

    @pytest.mark.asyncio
    async def test_save_score_with_thematic_tags(self, repo: Repository) -> None:
        """Verify thematic_tags list persisted and retrieved as list[str]."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score(thematic_tags=["AI & Machine Learning", "Cybersecurity"])

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].thematic_tags == ["AI & Machine Learning", "Cybersecurity"]

    @pytest.mark.asyncio
    async def test_save_score_with_empty_thematic_tags(self, repo: Repository) -> None:
        """Verify empty thematic_tags list stored as NULL and retrieved as empty list."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score()  # default empty list
        assert score.thematic_tags == []

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].thematic_tags == []

    @pytest.mark.asyncio
    async def test_thematic_tags_json_roundtrip(self, repo: Repository) -> None:
        """Verify ticker list survives JSON serialization with special characters."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        tags = ["AI & Machine Learning", "Electric Vehicles", "Clean Energy"]
        score = _make_ticker_score(thematic_tags=tags)

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert result[0].thematic_tags == tags

    @pytest.mark.asyncio
    async def test_both_industry_group_and_thematic_tags(self, repo: Repository) -> None:
        """Verify both new fields persist and roundtrip together."""
        scan_id = await repo.save_scan_run(_make_scan_run())
        score = _make_ticker_score(
            industry_group=GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            thematic_tags=["AI & Machine Learning"],
        )

        await repo.save_ticker_scores(scan_id, [score])
        result = await repo.get_scores_for_scan(scan_id)

        assert len(result) == 1
        assert result[0].industry_group == GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        assert result[0].thematic_tags == ["AI & Machine Learning"]
