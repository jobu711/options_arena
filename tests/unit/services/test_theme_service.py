"""Unit tests for ThemeService.

Tests cover:
- refresh_themes: builds ThemeSnapshot for each theme in THEME_ETF_MAPPING
- _fetch_etf_holdings: happy path, failure returns empty (never-raises)
- get_themes: returns from repository cache
- get_theme_ticker_set: frozenset lookup, unknown theme returns empty
- get_all_theme_sets: returns all theme mappings
- Deduplication: tickers from multiple ETFs are deduplicated
- Cache TTL: refresh not called when cache is fresh
- Popular Options: works when no scan data exists
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from options_arena.models.config import ThemeConfig
from options_arena.models.themes import THEME_ETF_MAPPING, ThemeSnapshot
from options_arena.services.theme_service import ThemeService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def config() -> ThemeConfig:
    """Default ThemeConfig for tests."""
    return ThemeConfig()


@pytest.fixture
def short_ttl_config() -> ThemeConfig:
    """ThemeConfig with very short TTL for cache testing."""
    return ThemeConfig(cache_ttl=1)  # 1 second


@pytest.fixture
def mock_repo() -> MagicMock:
    """Create a mock Repository with async methods."""
    repo = MagicMock()
    repo.save_themes = AsyncMock(return_value=None)
    repo.get_themes = AsyncMock(return_value=[])
    repo.get_recent_scans = AsyncMock(return_value=[])
    repo.get_scores_for_scan = AsyncMock(return_value=[])
    return repo


def _make_holdings_df(tickers: list[str]) -> pd.DataFrame:
    """Create a mock holdings DataFrame matching yfinance format.

    yfinance top_holdings has ticker symbols as the index and
    a 'Holding Percent' column with weight values.
    """
    return pd.DataFrame(
        {"Holding Percent": [0.05] * len(tickers)},
        index=tickers,
    )


def _make_theme_snapshot(
    name: str = "AI & Machine Learning",
    tickers: list[str] | None = None,
    source_etfs: list[str] | None = None,
) -> ThemeSnapshot:
    """Create a ThemeSnapshot for test assertions."""
    if tickers is None:
        tickers = ["AAPL", "MSFT", "GOOGL"]
    if source_etfs is None:
        source_etfs = ["ARKK", "BOTZ"]
    return ThemeSnapshot(
        name=name,
        description=f"Tickers from {', '.join(source_etfs)}",
        source_etfs=source_etfs,
        tickers=tickers,
        ticker_count=len(tickers),
        updated_at=NOW_UTC,
    )


# ---------------------------------------------------------------------------
# Tests: refresh_themes
# ---------------------------------------------------------------------------


class TestRefreshThemes:
    """Tests for ThemeService.refresh_themes()."""

    @pytest.mark.asyncio
    async def test_refresh_themes_builds_snapshots(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify refresh_themes creates ThemeSnapshot for each theme in THEME_ETF_MAPPING."""
        service = ThemeService(config, mock_repo)

        # Mock _fetch_etf_holdings to return known tickers
        with patch.object(
            service,
            "_fetch_etf_holdings",
            new_callable=AsyncMock,
            return_value=["AAPL", "MSFT"],
        ):
            snapshots = await service.refresh_themes()

        assert len(snapshots) == len(THEME_ETF_MAPPING)
        mock_repo.save_themes.assert_awaited_once()

        # Verify all theme names are present
        names = {s.name for s in snapshots}
        for theme_name in THEME_ETF_MAPPING:
            assert theme_name in names

    @pytest.mark.asyncio
    async def test_refresh_themes_updates_last_refresh(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify refresh_themes updates the _last_refresh timestamp."""
        service = ThemeService(config, mock_repo)
        assert service._last_refresh == 0.0

        with patch.object(
            service,
            "_fetch_etf_holdings",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await service.refresh_themes()

        assert service._last_refresh > 0.0

    @pytest.mark.asyncio
    async def test_refresh_deduplicates_across_etfs(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify ticker appearing in multiple ETFs for same theme is deduplicated."""
        service = ThemeService(config, mock_repo)

        # Return same tickers for each ETF call — should be deduplicated
        with patch.object(
            service,
            "_fetch_etf_holdings",
            new_callable=AsyncMock,
            return_value=["AAPL", "MSFT", "AAPL"],
        ):
            snapshots = await service.refresh_themes()

        # Find a theme with source ETFs (not Popular Options)
        ai_theme = next(s for s in snapshots if s.name == "AI & Machine Learning")
        # AAPL should appear only once despite being in multiple ETF results
        assert ai_theme.tickers.count("AAPL") == 1
        assert ai_theme.tickers.count("MSFT") == 1
        assert ai_theme.ticker_count == 2

    @pytest.mark.asyncio
    async def test_refresh_themes_all_etfs_fail(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """All ETFs fail: theme has empty ticker list (still created)."""
        service = ThemeService(config, mock_repo)

        with patch.object(
            service,
            "_fetch_etf_holdings",
            new_callable=AsyncMock,
            return_value=[],
        ):
            snapshots = await service.refresh_themes()

        # All themes should exist but with empty tickers (except Popular Options)
        for snapshot in snapshots:
            assert snapshot.ticker_count == 0
            assert snapshot.tickers == []

    @pytest.mark.asyncio
    async def test_refresh_themes_tickers_sorted(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify tickers in snapshots are sorted alphabetically."""
        service = ThemeService(config, mock_repo)

        with patch.object(
            service,
            "_fetch_etf_holdings",
            new_callable=AsyncMock,
            return_value=["MSFT", "AAPL", "GOOGL"],
        ):
            snapshots = await service.refresh_themes()

        # Find a theme with source ETFs
        ai_theme = next(s for s in snapshots if s.name == "AI & Machine Learning")
        assert ai_theme.tickers == ["AAPL", "GOOGL", "MSFT"]


# ---------------------------------------------------------------------------
# Tests: _fetch_etf_holdings
# ---------------------------------------------------------------------------


class TestFetchEtfHoldings:
    """Tests for ThemeService._fetch_etf_holdings()."""

    @pytest.mark.asyncio
    async def test_etf_holdings_fetch_success(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify _fetch_etf_holdings returns ticker list from mock yfinance."""
        service = ThemeService(config, mock_repo)
        holdings_df = _make_holdings_df(["AAPL", "MSFT", "GOOGL"])

        with patch.object(
            ThemeService,
            "_get_top_holdings",
            return_value=holdings_df,
        ):
            result = await service._fetch_etf_holdings("ARKK")

        assert result == ["AAPL", "MSFT", "GOOGL"]

    @pytest.mark.asyncio
    async def test_etf_holdings_fetch_failure_returns_empty(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify _fetch_etf_holdings returns [] on exception (never-raises)."""
        service = ThemeService(config, mock_repo)

        with patch.object(
            ThemeService,
            "_get_top_holdings",
            side_effect=RuntimeError("Network error"),
        ):
            result = await service._fetch_etf_holdings("ARKK")

        assert result == []

    @pytest.mark.asyncio
    async def test_etf_holdings_none_returns_empty(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify _fetch_etf_holdings returns [] when holdings is None."""
        service = ThemeService(config, mock_repo)

        with patch.object(
            ThemeService,
            "_get_top_holdings",
            return_value=None,
        ):
            result = await service._fetch_etf_holdings("BADETF")

        assert result == []

    @pytest.mark.asyncio
    async def test_etf_holdings_empty_dataframe_returns_empty(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify _fetch_etf_holdings returns [] when holdings DataFrame is empty."""
        service = ThemeService(config, mock_repo)

        with patch.object(
            ThemeService,
            "_get_top_holdings",
            return_value=pd.DataFrame(),
        ):
            result = await service._fetch_etf_holdings("EMPTYETF")

        assert result == []

    @pytest.mark.asyncio
    async def test_etf_holdings_timeout_returns_empty(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify _fetch_etf_holdings returns [] on timeout (never-raises)."""
        service = ThemeService(config, mock_repo)

        import asyncio

        with patch(
            "options_arena.services.theme_service.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            result = await service._fetch_etf_holdings("SLOWETF")

        assert result == []


# ---------------------------------------------------------------------------
# Tests: get_themes
# ---------------------------------------------------------------------------


class TestGetThemes:
    """Tests for ThemeService.get_themes()."""

    @pytest.mark.asyncio
    async def test_get_themes_returns_cached(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify get_themes returns from repository cache when not stale."""
        service = ThemeService(config, mock_repo)
        # Set _last_refresh to simulate a fresh cache
        service._last_refresh = time.monotonic()

        cached_themes = [_make_theme_snapshot()]
        mock_repo.get_themes.return_value = cached_themes

        result = await service.get_themes()

        assert result == cached_themes
        mock_repo.get_themes.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_themes_triggers_refresh_when_stale(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify get_themes triggers refresh when TTL has expired."""
        service = ThemeService(config, mock_repo)
        # _last_refresh is 0.0 by default — should trigger refresh

        with patch.object(
            service,
            "refresh_themes",
            new_callable=AsyncMock,
            return_value=[_make_theme_snapshot()],
        ) as mock_refresh:
            result = await service.get_themes()

        mock_refresh.assert_awaited_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_themes_fallback_on_refresh_failure(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify get_themes falls back to cached data when refresh fails."""
        service = ThemeService(config, mock_repo)
        cached_themes = [_make_theme_snapshot()]
        mock_repo.get_themes.return_value = cached_themes

        with patch.object(
            service,
            "refresh_themes",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Refresh failed"),
        ):
            result = await service.get_themes()

        # Should fall back to repo.get_themes()
        assert result == cached_themes

    @pytest.mark.asyncio
    async def test_cache_ttl_respected(
        self, short_ttl_config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify refresh not called when cache is fresh."""
        service = ThemeService(short_ttl_config, mock_repo)
        # Set last refresh to just now
        service._last_refresh = time.monotonic()

        cached_themes = [_make_theme_snapshot()]
        mock_repo.get_themes.return_value = cached_themes

        result = await service.get_themes()

        # Should NOT trigger refresh since cache is fresh
        assert result == cached_themes
        mock_repo.get_themes.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: get_theme_ticker_set
# ---------------------------------------------------------------------------


class TestGetThemeTickerSet:
    """Tests for ThemeService.get_theme_ticker_set()."""

    @pytest.mark.asyncio
    async def test_get_theme_ticker_set(self, config: ThemeConfig, mock_repo: MagicMock) -> None:
        """Verify frozenset lookup for specific theme."""
        service = ThemeService(config, mock_repo)
        service._last_refresh = time.monotonic()

        mock_repo.get_themes.return_value = [
            _make_theme_snapshot(
                name="AI & Machine Learning",
                tickers=["AAPL", "MSFT", "GOOGL"],
            )
        ]

        result = await service.get_theme_ticker_set("AI & Machine Learning")

        assert result == frozenset({"AAPL", "MSFT", "GOOGL"})

    @pytest.mark.asyncio
    async def test_theme_ticker_set_unknown_theme(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify empty frozenset for unknown theme name."""
        service = ThemeService(config, mock_repo)
        service._last_refresh = time.monotonic()

        mock_repo.get_themes.return_value = [_make_theme_snapshot(name="AI & Machine Learning")]

        result = await service.get_theme_ticker_set("Nonexistent Theme")

        assert result == frozenset()


# ---------------------------------------------------------------------------
# Tests: get_all_theme_sets
# ---------------------------------------------------------------------------


class TestGetAllThemeSets:
    """Tests for ThemeService.get_all_theme_sets()."""

    @pytest.mark.asyncio
    async def test_get_all_theme_sets(self, config: ThemeConfig, mock_repo: MagicMock) -> None:
        """Verify all theme-to-ticker frozenset mappings returned."""
        service = ThemeService(config, mock_repo)
        service._last_refresh = time.monotonic()

        mock_repo.get_themes.return_value = [
            _make_theme_snapshot(name="AI & Machine Learning", tickers=["AAPL", "MSFT"]),
            _make_theme_snapshot(name="Cannabis", tickers=["TLRY", "CGC"]),
        ]

        result = await service.get_all_theme_sets()

        assert len(result) == 2
        assert result["AI & Machine Learning"] == frozenset({"AAPL", "MSFT"})
        assert result["Cannabis"] == frozenset({"TLRY", "CGC"})

    @pytest.mark.asyncio
    async def test_get_all_theme_sets_empty(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify empty dict when no themes exist."""
        service = ThemeService(config, mock_repo)
        service._last_refresh = time.monotonic()

        mock_repo.get_themes.return_value = []

        result = await service.get_all_theme_sets()

        assert result == {}


# ---------------------------------------------------------------------------
# Tests: _should_refresh
# ---------------------------------------------------------------------------


class TestShouldRefresh:
    """Tests for ThemeService._should_refresh()."""

    def test_should_refresh_initial(self, config: ThemeConfig, mock_repo: MagicMock) -> None:
        """Verify refresh needed when _last_refresh is 0.0 (initial state)."""
        service = ThemeService(config, mock_repo)
        assert service._should_refresh() is True

    def test_should_refresh_fresh_cache(self, config: ThemeConfig, mock_repo: MagicMock) -> None:
        """Verify no refresh needed when cache is fresh."""
        service = ThemeService(config, mock_repo)
        service._last_refresh = time.monotonic()
        assert service._should_refresh() is False

    def test_should_refresh_expired_cache(
        self, short_ttl_config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify refresh needed when cache TTL has expired."""
        service = ThemeService(short_ttl_config, mock_repo)
        # Set last refresh to well beyond TTL (1 second)
        service._last_refresh = time.monotonic() - 10.0
        assert service._should_refresh() is True


# ---------------------------------------------------------------------------
# Tests: _compute_popular_options
# ---------------------------------------------------------------------------


class TestComputePopularOptions:
    """Tests for ThemeService._compute_popular_options()."""

    @pytest.mark.asyncio
    async def test_popular_options_returns_empty_initially(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify Popular Options theme works when no scan data exists."""
        service = ThemeService(config, mock_repo)
        mock_repo.get_recent_scans.return_value = []

        result = await service._compute_popular_options()

        assert result == []

    @pytest.mark.asyncio
    async def test_popular_options_from_scan_data(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify Popular Options returns tickers from recent scans sorted by frequency."""
        service = ThemeService(config, mock_repo)

        # Mock scan runs
        scan1 = MagicMock()
        scan1.id = 1
        scan2 = MagicMock()
        scan2.id = 2
        mock_repo.get_recent_scans.return_value = [scan1, scan2]

        # Mock scores — AAPL appears in both scans, MSFT only in one
        score_aapl = MagicMock()
        score_aapl.ticker = "AAPL"
        score_msft = MagicMock()
        score_msft.ticker = "MSFT"
        score_googl = MagicMock()
        score_googl.ticker = "GOOGL"

        mock_repo.get_scores_for_scan.side_effect = [
            [score_aapl, score_msft],  # scan 1
            [score_aapl, score_googl],  # scan 2
        ]

        result = await service._compute_popular_options()

        # AAPL appears 2x, MSFT and GOOGL 1x each
        assert result[0] == "AAPL"
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_popular_options_never_raises(
        self, config: ThemeConfig, mock_repo: MagicMock
    ) -> None:
        """Verify _compute_popular_options returns [] on exception (never-raises)."""
        service = ThemeService(config, mock_repo)
        mock_repo.get_recent_scans.side_effect = RuntimeError("DB error")

        result = await service._compute_popular_options()

        assert result == []

    @pytest.mark.asyncio
    async def test_popular_options_max_50(self, config: ThemeConfig, mock_repo: MagicMock) -> None:
        """Verify Popular Options returns at most 50 tickers."""
        service = ThemeService(config, mock_repo)

        scan = MagicMock()
        scan.id = 1
        mock_repo.get_recent_scans.return_value = [scan]

        # Create 100 unique ticker scores
        scores = []
        for i in range(100):
            score = MagicMock()
            score.ticker = f"TK{i:03d}"
            scores.append(score)
        mock_repo.get_scores_for_scan.return_value = scores

        result = await service._compute_popular_options()

        assert len(result) <= 50


# ---------------------------------------------------------------------------
# Tests: _get_top_holdings static method
# ---------------------------------------------------------------------------


class TestGetTopHoldings:
    """Tests for ThemeService._get_top_holdings() static method."""

    def test_get_top_holdings_success(self) -> None:
        """Verify _get_top_holdings extracts holdings from funds_data."""
        mock_ticker = MagicMock()
        mock_funds_data = MagicMock()
        mock_funds_data.top_holdings = _make_holdings_df(["AAPL", "MSFT"])
        mock_ticker.funds_data = mock_funds_data

        result = ThemeService._get_top_holdings(mock_ticker)

        assert isinstance(result, pd.DataFrame)
        assert list(result.index) == ["AAPL", "MSFT"]

    def test_get_top_holdings_none_funds_data(self) -> None:
        """Verify _get_top_holdings returns None when funds_data is None."""
        mock_ticker = MagicMock()
        mock_ticker.funds_data = None

        result = ThemeService._get_top_holdings(mock_ticker)

        assert result is None

    def test_get_top_holdings_exception(self) -> None:
        """Verify _get_top_holdings returns None on exception."""
        mock_ticker = MagicMock()
        mock_ticker.funds_data = property(lambda self: (_ for _ in ()).throw(RuntimeError))
        # More direct: make funds_data access raise
        type(mock_ticker).funds_data = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Bad access"))
        )

        result = ThemeService._get_top_holdings(mock_ticker)

        assert result is None
