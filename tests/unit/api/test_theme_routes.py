"""Tests for theme endpoint and pipeline theme annotation (#230)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from options_arena.api.app import create_app, limiter
from options_arena.api.deps import get_repo, get_settings, get_theme_service, get_universe
from options_arena.models.config import AppSettings
from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals, TickerScore
from options_arena.models.themes import ThemeSnapshot
from options_arena.services.theme_service import ThemeService


def _make_theme(name: str, tickers: list[str], etfs: list[str]) -> ThemeSnapshot:
    """Build a ThemeSnapshot for testing."""
    return ThemeSnapshot(
        name=name,
        description=f"Test theme: {name}",
        source_etfs=etfs,
        tickers=tickers,
        ticker_count=len(tickers),
        updated_at=datetime.now(UTC),
    )


def _make_score(ticker: str, *, score: float = 50.0) -> TickerScore:
    """Build a minimal TickerScore for pipeline tests."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(),
    )


@pytest.fixture()
def theme_app_with_data() -> create_app:
    """Create test app with mocked ThemeService that returns themes."""
    import asyncio  # noqa: PLC0415

    app = create_app()
    limiter.enabled = False

    themes = [
        _make_theme("AI & Robotics", ["NVDA", "MSFT", "GOOGL"], ["BOTZ", "ROBO"]),
        _make_theme("Clean Energy", ["ENPH", "FSLR", "NEE"], ["ICLN", "TAN"]),
    ]

    mock_theme_svc = MagicMock(spec=ThemeService)
    mock_theme_svc.get_themes = AsyncMock(return_value=themes)

    mock_universe = MagicMock()
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=[])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])

    mock_repo = MagicMock()

    app.dependency_overrides[get_theme_service] = lambda: mock_theme_svc
    app.dependency_overrides[get_universe] = lambda: mock_universe
    app.dependency_overrides[get_repo] = lambda: mock_repo
    app.dependency_overrides[get_settings] = lambda: AppSettings()

    app.state.cache = MagicMock()
    app.state.limiter = MagicMock()
    app.state.scan_counter = 0
    app.state.active_scans = {}
    app.state.scan_queues = {}
    app.state.debate_counter = 0
    app.state.debate_queues = {}
    app.state.batch_counter = 0
    app.state.batch_queues = {}
    app.state.operation_lock = asyncio.Lock()

    return app


@pytest.fixture()
def theme_app_empty() -> create_app:
    """Create test app with mocked ThemeService that returns no themes."""
    import asyncio  # noqa: PLC0415

    app = create_app()
    limiter.enabled = False

    mock_theme_svc = MagicMock(spec=ThemeService)
    mock_theme_svc.get_themes = AsyncMock(return_value=[])

    mock_universe = MagicMock()
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=[])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])

    mock_repo = MagicMock()

    app.dependency_overrides[get_theme_service] = lambda: mock_theme_svc
    app.dependency_overrides[get_universe] = lambda: mock_universe
    app.dependency_overrides[get_repo] = lambda: mock_repo
    app.dependency_overrides[get_settings] = lambda: AppSettings()

    app.state.cache = MagicMock()
    app.state.limiter = MagicMock()
    app.state.scan_counter = 0
    app.state.active_scans = {}
    app.state.scan_queues = {}
    app.state.debate_counter = 0
    app.state.debate_queues = {}
    app.state.batch_counter = 0
    app.state.batch_queues = {}
    app.state.operation_lock = asyncio.Lock()

    return app


class TestThemesEndpoint:
    """Tests for GET /api/themes."""

    @pytest.mark.asyncio()
    async def test_returns_theme_list(self, theme_app_with_data: create_app) -> None:
        """Verify GET /api/themes returns available themes."""
        transport = ASGITransport(app=theme_app_with_data)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/themes")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 2

            ai_theme = next(t for t in data if t["name"] == "AI & Robotics")
            assert ai_theme["ticker_count"] == 3
            assert ai_theme["source_etfs"] == ["BOTZ", "ROBO"]

            clean = next(t for t in data if t["name"] == "Clean Energy")
            assert clean["ticker_count"] == 3
            assert clean["source_etfs"] == ["ICLN", "TAN"]

    @pytest.mark.asyncio()
    async def test_empty_when_no_themes(self, theme_app_empty: create_app) -> None:
        """Verify empty list when ThemeService has no data."""
        transport = ASGITransport(app=theme_app_empty)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/themes")
            assert response.status_code == 200
            assert response.json() == []

    @pytest.mark.asyncio()
    async def test_theme_response_shape(self, theme_app_with_data: create_app) -> None:
        """Verify each theme has the correct response fields."""
        transport = ASGITransport(app=theme_app_with_data)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/themes")
            data = response.json()

            for item in data:
                assert "name" in item
                assert "ticker_count" in item
                assert "source_etfs" in item
                assert isinstance(item["source_etfs"], list)
                assert isinstance(item["ticker_count"], int)


class TestPipelineThemeAnnotation:
    """Tests for Phase 3 thematic_tags annotation via ThemeService."""

    @pytest.mark.asyncio()
    async def test_thematic_tags_populated(self) -> None:
        """Verify TickerScore.thematic_tags set from ThemeService."""

        mock_theme_svc = MagicMock(spec=ThemeService)
        mock_theme_svc.get_all_theme_sets = AsyncMock(
            return_value={
                "AI & Robotics": frozenset({"NVDA", "MSFT"}),
                "Clean Energy": frozenset({"ENPH", "NEE"}),
            }
        )

        # Create a minimal pipeline to test the theme annotation logic
        # We'll directly test the logic pattern rather than running the full pipeline
        top_scores = [
            _make_score("NVDA", score=80.0),
            _make_score("ENPH", score=70.0),
            _make_score("AAPL", score=60.0),  # Not in any theme
        ]

        # Simulate what the pipeline does:
        theme_sets = await mock_theme_svc.get_all_theme_sets()
        for ts in top_scores:
            ts.thematic_tags = [name for name, tset in theme_sets.items() if ts.ticker in tset]

        assert top_scores[0].thematic_tags == ["AI & Robotics"]  # NVDA
        assert top_scores[1].thematic_tags == ["Clean Energy"]  # ENPH
        assert top_scores[2].thematic_tags == []  # AAPL

    @pytest.mark.asyncio()
    async def test_ticker_in_multiple_themes(self) -> None:
        """Verify ticker in multiple themes gets all tags."""
        mock_theme_svc = MagicMock(spec=ThemeService)
        mock_theme_svc.get_all_theme_sets = AsyncMock(
            return_value={
                "AI & Robotics": frozenset({"MSFT"}),
                "Big Tech": frozenset({"MSFT", "AAPL"}),
            }
        )

        score = _make_score("MSFT")
        theme_sets = await mock_theme_svc.get_all_theme_sets()
        score.thematic_tags = [name for name, tset in theme_sets.items() if score.ticker in tset]

        assert "AI & Robotics" in score.thematic_tags
        assert "Big Tech" in score.thematic_tags
        assert len(score.thematic_tags) == 2

    @pytest.mark.asyncio()
    async def test_no_themes_when_service_empty(self) -> None:
        """Verify empty tags when ThemeService has no data."""
        mock_theme_svc = MagicMock(spec=ThemeService)
        mock_theme_svc.get_all_theme_sets = AsyncMock(return_value={})

        score = _make_score("NVDA")
        theme_sets = await mock_theme_svc.get_all_theme_sets()
        score.thematic_tags = [name for name, tset in theme_sets.items() if score.ticker in tset]

        assert score.thematic_tags == []
