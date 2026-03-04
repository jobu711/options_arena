"""Tests for theme persistence (migration 017 + repository methods)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import ThemeSnapshot

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


def _make_theme(**overrides: object) -> ThemeSnapshot:
    """Build a ThemeSnapshot with sensible defaults."""
    defaults: dict[str, object] = {
        "name": "AI & Machine Learning",
        "description": "Companies focused on artificial intelligence and machine learning",
        "source_etfs": ["ARKK", "BOTZ", "ROBO", "AIQ"],
        "tickers": ["NVDA", "MSFT", "GOOGL", "AMZN", "META"],
        "ticker_count": 5,
        "updated_at": datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return ThemeSnapshot(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Theme persistence
# ---------------------------------------------------------------------------


class TestThemePersistence:
    """Tests for save_themes() and get_themes() repository methods."""

    @pytest.mark.asyncio
    async def test_save_and_get_themes(self, repo: Repository) -> None:
        """Verify themes roundtrip through SQLite."""
        theme = _make_theme()
        await repo.save_themes([theme])
        result = await repo.get_themes()

        assert len(result) == 1
        assert result[0].name == "AI & Machine Learning"
        assert result[0].description == (
            "Companies focused on artificial intelligence and machine learning"
        )
        assert result[0].source_etfs == ["ARKK", "BOTZ", "ROBO", "AIQ"]
        assert result[0].tickers == ["NVDA", "MSFT", "GOOGL", "AMZN", "META"]
        assert result[0].ticker_count == 5
        assert result[0].updated_at == datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_upsert_theme_updates_existing(self, repo: Repository) -> None:
        """Verify save_themes overwrites existing theme on same name (PK)."""
        theme_v1 = _make_theme(
            tickers=["NVDA", "MSFT"],
            ticker_count=2,
            updated_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        )
        await repo.save_themes([theme_v1])

        # Upsert with updated data
        theme_v2 = _make_theme(
            tickers=["NVDA", "MSFT", "GOOGL", "AMZN"],
            ticker_count=4,
            updated_at=datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC),
        )
        await repo.save_themes([theme_v2])

        result = await repo.get_themes()
        assert len(result) == 1
        assert result[0].tickers == ["NVDA", "MSFT", "GOOGL", "AMZN"]
        assert result[0].ticker_count == 4
        assert result[0].updated_at == datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_get_themes_empty_db(self, repo: Repository) -> None:
        """Verify empty list returned from fresh DB with no themes."""
        result = await repo.get_themes()
        assert result == []

    @pytest.mark.asyncio
    async def test_theme_tickers_json_roundtrip(self, repo: Repository) -> None:
        """Verify ticker list survives JSON serialization."""
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
        theme = _make_theme(tickers=tickers, ticker_count=len(tickers))
        await repo.save_themes([theme])

        result = await repo.get_themes()
        assert result[0].tickers == tickers

    @pytest.mark.asyncio
    async def test_theme_empty_tickers_list(self, repo: Repository) -> None:
        """Verify empty tickers list persists as [] and roundtrips correctly."""
        theme = _make_theme(
            name="Popular Options",
            tickers=[],
            ticker_count=0,
            source_etfs=[],
        )
        await repo.save_themes([theme])

        result = await repo.get_themes()
        assert len(result) == 1
        assert result[0].tickers == []
        assert result[0].source_etfs == []
        assert result[0].ticker_count == 0

    @pytest.mark.asyncio
    async def test_multiple_themes_ordered_by_name(self, repo: Repository) -> None:
        """Verify multiple themes returned ordered by name."""
        themes = [
            _make_theme(name="Cybersecurity", tickers=["CRWD", "PANW"], ticker_count=2),
            _make_theme(name="AI & Machine Learning"),
            _make_theme(name="Electric Vehicles", tickers=["TSLA", "RIVN"], ticker_count=2),
        ]
        await repo.save_themes(themes)

        result = await repo.get_themes()
        assert len(result) == 3
        assert result[0].name == "AI & Machine Learning"
        assert result[1].name == "Cybersecurity"
        assert result[2].name == "Electric Vehicles"

    @pytest.mark.asyncio
    async def test_migration_017_creates_table(self, db: Database) -> None:
        """Verify themes table exists after migrations."""
        conn = db.conn
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='themes'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "themes"

    @pytest.mark.asyncio
    async def test_save_themes_empty_list_no_op(self, repo: Repository) -> None:
        """Verify save_themes with empty list does not crash or error."""
        await repo.save_themes([])
        result = await repo.get_themes()
        assert result == []

    @pytest.mark.asyncio
    async def test_theme_unicode_name(self, repo: Repository) -> None:
        """Verify Unicode in theme names stored correctly."""
        theme = _make_theme(name="Energ\u00eda Limpia")
        await repo.save_themes([theme])

        result = await repo.get_themes()
        assert len(result) == 1
        assert result[0].name == "Energ\u00eda Limpia"

    @pytest.mark.asyncio
    async def test_large_tickers_list(self, repo: Repository) -> None:
        """Verify a large ticker list (500+) survives JSON roundtrip."""
        large_tickers = [f"T{i:04d}" for i in range(600)]
        theme = _make_theme(tickers=large_tickers, ticker_count=600)
        await repo.save_themes([theme])

        result = await repo.get_themes()
        assert len(result) == 1
        assert result[0].tickers == large_tickers
        assert result[0].ticker_count == 600
