"""Tests for filter_spec_json persistence on ScanRun and Repository."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    ScanSource,
    SignalDirection,
    TickerScore,
)
from options_arena.models.enums import GICSSector, MarketCapTier
from options_arena.models.filters import (
    OptionsFilters,
    ScanFilterSpec,
    ScoringFilters,
    UniverseFilters,
)
from options_arena.scan.models import OptionsResult, ScoringResult, UniverseResult
from options_arena.scan.phase_persist import run_persist_phase

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_scan_run(**overrides: object) -> ScanRun:
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


def make_ticker_score(**overrides: object) -> TickerScore:
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
# Model tests
# ---------------------------------------------------------------------------


class TestScanRunFilterSpecField:
    """ScanRun model has filter_spec_json field."""

    def test_scan_run_filter_spec_json_defaults_to_none(self) -> None:
        """filter_spec_json defaults to None when not provided."""
        scan_run = make_scan_run()
        assert scan_run.filter_spec_json is None

    def test_scan_run_filter_spec_json_accepts_string(self) -> None:
        """filter_spec_json accepts a JSON string value."""
        spec = ScanFilterSpec()
        json_str = spec.model_dump_json()
        scan_run = make_scan_run(filter_spec_json=json_str)
        assert scan_run.filter_spec_json == json_str

    def test_scan_filter_spec_roundtrip(self) -> None:
        """ScanFilterSpec JSON roundtrip works — serialize then deserialize."""
        spec = ScanFilterSpec(
            universe=UniverseFilters(
                preset=ScanPreset.FULL,
                sectors=[GICSSector.INFORMATION_TECHNOLOGY],
                min_price=25.0,
            ),
            scoring=ScoringFilters(
                direction_filter=SignalDirection.BULLISH,
                min_score=30.0,
            ),
            options=OptionsFilters(
                top_n=20,
                min_dollar_volume=5_000_000.0,
                min_dte=14,
                max_dte=90,
            ),
        )
        json_str = spec.model_dump_json()
        restored = ScanFilterSpec.model_validate_json(json_str)
        assert restored == spec
        assert restored.universe.preset == ScanPreset.FULL
        assert restored.universe.sectors == [GICSSector.INFORMATION_TECHNOLOGY]
        assert restored.scoring.direction_filter == SignalDirection.BULLISH
        assert restored.options.top_n == 20


# ---------------------------------------------------------------------------
# Repository persistence tests
# ---------------------------------------------------------------------------


class TestFilterSpecPersistence:
    """Repository correctly saves and reads filter_spec_json."""

    @pytest.mark.asyncio
    async def test_save_and_read_with_filter_spec_json(self, repo: Repository) -> None:
        """filter_spec_json survives save -> get_scan_by_id round-trip."""
        spec = ScanFilterSpec()
        json_str = spec.model_dump_json()
        scan_run = make_scan_run(filter_spec_json=json_str)

        scan_id = await repo.save_scan_run(scan_run)
        retrieved = await repo.get_scan_by_id(scan_id)

        assert retrieved is not None
        assert retrieved.filter_spec_json == json_str
        restored = ScanFilterSpec.model_validate_json(retrieved.filter_spec_json)
        assert restored == spec

    @pytest.mark.asyncio
    async def test_save_and_read_without_filter_spec_json(self, repo: Repository) -> None:
        """filter_spec_json is None when not provided."""
        scan_run = make_scan_run()
        scan_id = await repo.save_scan_run(scan_run)
        retrieved = await repo.get_scan_by_id(scan_id)

        assert retrieved is not None
        assert retrieved.filter_spec_json is None

    @pytest.mark.asyncio
    async def test_custom_filter_spec_persisted_accurately(self, repo: Repository) -> None:
        """Non-default filter spec values are persisted accurately."""
        spec = ScanFilterSpec(
            universe=UniverseFilters(
                preset=ScanPreset.FULL,
                sectors=[GICSSector.HEALTH_CARE, GICSSector.INFORMATION_TECHNOLOGY],
                market_cap_tiers=[MarketCapTier.LARGE, MarketCapTier.MEGA],
                min_price=50.0,
                max_price=500.0,
                ohlcv_min_bars=100,
            ),
            scoring=ScoringFilters(
                direction_filter=SignalDirection.BEARISH,
                min_score=25.0,
                min_direction_confidence=0.6,
            ),
            options=OptionsFilters(
                top_n=10,
                min_dollar_volume=20_000_000.0,
                min_dte=7,
                max_dte=45,
                min_oi=500,
                max_spread_pct=0.15,
            ),
        )
        json_str = spec.model_dump_json()
        scan_run = make_scan_run(filter_spec_json=json_str)

        scan_id = await repo.save_scan_run(scan_run)
        retrieved = await repo.get_scan_by_id(scan_id)

        assert retrieved is not None
        assert retrieved.filter_spec_json is not None
        restored = ScanFilterSpec.model_validate_json(retrieved.filter_spec_json)
        assert restored.universe.preset == ScanPreset.FULL
        assert restored.universe.sectors == [
            GICSSector.HEALTH_CARE,
            GICSSector.INFORMATION_TECHNOLOGY,
        ]
        assert restored.universe.market_cap_tiers == [MarketCapTier.LARGE, MarketCapTier.MEGA]
        assert restored.universe.min_price == pytest.approx(50.0)
        assert restored.universe.max_price == pytest.approx(500.0)
        assert restored.scoring.direction_filter == SignalDirection.BEARISH
        assert restored.scoring.min_score == pytest.approx(25.0)
        assert restored.options.top_n == 10
        assert restored.options.min_dte == 7

    @pytest.mark.asyncio
    async def test_filter_spec_in_recent_scans(self, repo: Repository) -> None:
        """filter_spec_json appears in get_recent_scans results."""
        spec = ScanFilterSpec()
        json_str = spec.model_dump_json()
        scan_run = make_scan_run(filter_spec_json=json_str)

        await repo.save_scan_run(scan_run)
        scans = await repo.get_recent_scans(limit=5)

        assert len(scans) == 1
        assert scans[0].filter_spec_json == json_str


# ---------------------------------------------------------------------------
# Phase persist integration test
# ---------------------------------------------------------------------------


class TestPhasePersistFilterSpec:
    """run_persist_phase stores filter_spec_json when provided."""

    @pytest.mark.asyncio
    async def test_phase_persist_stores_filter_spec(self, repo: Repository) -> None:
        """run_persist_phase persists filter_spec.model_dump_json() into ScanRun."""
        filter_spec = ScanFilterSpec(
            universe=UniverseFilters(preset=ScanPreset.FULL, min_price=20.0),
        )
        universe_result = UniverseResult(
            tickers=["AAPL", "MSFT"],
            ohlcv_map={},
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        scoring_result = ScoringResult(
            scores=[],
            raw_signals={},
            normalization_stats=[],
        )
        options_result = OptionsResult(
            recommendations={},
            risk_free_rate=0.045,
            earnings_dates={},
            entry_prices={},
        )
        progress = MagicMock()

        result = await run_persist_phase(
            started_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
            preset=ScanPreset.FULL,
            source=ScanSource.MANUAL,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=progress,
            repository=repo,
            filter_spec=filter_spec,
        )

        assert result.scan_run.filter_spec_json is not None
        restored = ScanFilterSpec.model_validate_json(result.scan_run.filter_spec_json)
        assert restored == filter_spec
        assert restored.universe.preset == ScanPreset.FULL
        assert restored.universe.min_price == pytest.approx(20.0)

        # Verify it's actually in the database
        db_run = await repo.get_scan_by_id(result.scan_run.id)
        assert db_run is not None
        assert db_run.filter_spec_json == result.scan_run.filter_spec_json


# ---------------------------------------------------------------------------
# Migration file existence test
# ---------------------------------------------------------------------------


class TestMigrationFile:
    """Migration 031 exists and contains the expected SQL."""

    def test_migration_031_exists(self) -> None:
        """Migration 031_add_filter_spec_json.sql exists in data/migrations/."""
        # Navigate from test file to project root
        project_root = Path(__file__).resolve().parents[3]
        migration_path = project_root / "data" / "migrations" / "031_add_filter_spec_json.sql"
        assert migration_path.exists(), f"Migration file not found: {migration_path}"

    def test_migration_031_contains_alter_table(self) -> None:
        """Migration 031 contains ALTER TABLE statement for filter_spec_json."""
        project_root = Path(__file__).resolve().parents[3]
        migration_path = project_root / "data" / "migrations" / "031_add_filter_spec_json.sql"
        content = migration_path.read_text(encoding="utf-8")
        assert "ALTER TABLE scan_runs" in content
        assert "filter_spec_json" in content
        assert "TEXT" in content
