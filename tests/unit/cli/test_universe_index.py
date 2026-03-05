"""Tests for ``universe index`` CLI command.

Mocks all services (UniverseService, MarketDataService, Database, Repository)
to verify command wiring, progress output, and error isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from options_arena.cli.app import app
from options_arena.models.enums import DividendSource, MarketCapTier
from options_arena.models.market_data import TickerInfo
from options_arena.models.metadata import MetadataCoverage, TickerMetadata
from options_arena.utils.exceptions import DataSourceUnavailableError

runner = CliRunner()


def _make_ticker_info(ticker: str) -> TickerInfo:
    """Create a realistic TickerInfo for testing."""
    return TickerInfo(
        ticker=ticker,
        company_name=f"{ticker} Corp",
        sector="Information Technology",
        industry="Software—Application",
        market_cap=50_000_000_000,
        market_cap_tier=MarketCapTier.LARGE,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("150.00"),
        fifty_two_week_high=Decimal("180.00"),
        fifty_two_week_low=Decimal("120.00"),
    )


def _make_ticker_metadata(ticker: str) -> TickerMetadata:
    """Create a TickerMetadata for testing."""
    return TickerMetadata(
        ticker=ticker,
        sector=None,
        industry_group=None,
        market_cap_tier=MarketCapTier.LARGE,
        company_name=f"{ticker} Corp",
        raw_sector="Information Technology",
        raw_industry="Software—Application",
        last_updated=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _make_coverage(
    total: int = 3,
    with_sector: int = 2,
    with_ig: int = 1,
) -> MetadataCoverage:
    """Create a MetadataCoverage for testing."""
    return MetadataCoverage(
        total=total,
        with_sector=with_sector,
        with_industry_group=with_ig,
        coverage=with_sector / total if total > 0 else 0.0,
    )


class TestUniverseIndex:
    """Tests for the ``universe index`` command."""

    def test_command_exists(self) -> None:
        """Verify 'universe index' is a registered subcommand."""
        result = runner.invoke(app, ["universe", "index", "--help"])
        assert result.exit_code == 0
        assert "Bulk-index" in result.output

    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.UniverseService")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    def test_default_args(
        self,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_universe_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Verify default --concurrency=5, --max-age=30, --force=False."""
        # Setup mocks
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers.return_value = ["AAPL", "MSFT"]
        mock_universe_cls.return_value = mock_universe
        mock_market = AsyncMock()
        mock_market.fetch_ticker_info.return_value = _make_ticker_info("AAPL")
        mock_market_cls.return_value = mock_market
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        # Coverage = 0 triggers full index
        mock_repo.get_metadata_coverage.return_value = _make_coverage(total=0)

        with patch(
            "options_arena.services.universe.map_yfinance_to_metadata",
            return_value=_make_ticker_metadata("AAPL"),
        ):
            result = runner.invoke(app, ["universe", "index"])

        assert result.exit_code == 0
        # Default behaviour: indexes all tickers since coverage is 0
        assert mock_market.fetch_ticker_info.await_count == 2
        mock_db.close.assert_awaited_once()

    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.UniverseService")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    def test_force_flag_indexes_all(
        self,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_universe_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Verify --force bypasses staleness check and indexes everything."""
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers.return_value = ["AAPL", "MSFT", "GOOG"]
        mock_universe_cls.return_value = mock_universe
        mock_market = AsyncMock()
        mock_market.fetch_ticker_info.return_value = _make_ticker_info("AAPL")
        mock_market_cls.return_value = mock_market
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_repo.get_metadata_coverage.return_value = _make_coverage(total=3)

        with patch(
            "options_arena.services.universe.map_yfinance_to_metadata",
            return_value=_make_ticker_metadata("AAPL"),
        ):
            result = runner.invoke(app, ["universe", "index", "--force"])

        assert result.exit_code == 0
        # --force should process ALL 3 tickers, not just stale ones
        assert mock_market.fetch_ticker_info.await_count == 3
        # Should NOT call get_stale_tickers when --force is True
        mock_repo.get_stale_tickers.assert_not_awaited()

    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.UniverseService")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    def test_ticker_failure_does_not_crash(
        self,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_universe_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Verify individual ticker error is logged and skipped, not crash."""
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers.return_value = ["AAPL", "BAD", "MSFT"]
        mock_universe_cls.return_value = mock_universe
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_repo.get_metadata_coverage.return_value = _make_coverage(total=0)

        # BAD ticker raises, others succeed
        async def _fetch_ticker_info(ticker: str) -> TickerInfo:
            if ticker == "BAD":
                raise DataSourceUnavailableError("yfinance", "timeout")
            return _make_ticker_info(ticker)

        mock_market = AsyncMock()
        mock_market.fetch_ticker_info.side_effect = _fetch_ticker_info
        mock_market_cls.return_value = mock_market

        with patch(
            "options_arena.services.universe.map_yfinance_to_metadata",
            return_value=_make_ticker_metadata("AAPL"),
        ):
            result = runner.invoke(app, ["universe", "index", "--force"])

        assert result.exit_code == 0
        # 3 tickers attempted, 1 failed
        assert "Failed this run" in result.output
        assert "Indexed this run" in result.output

    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.UniverseService")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    def test_final_report_shows_coverage(
        self,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_universe_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Verify final output includes sector coverage percentage."""
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers.return_value = ["AAPL"]
        mock_universe_cls.return_value = mock_universe
        mock_market = AsyncMock()
        mock_market.fetch_ticker_info.return_value = _make_ticker_info("AAPL")
        mock_market_cls.return_value = mock_market
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        mock_repo.get_metadata_coverage.return_value = _make_coverage(
            total=100, with_sector=75, with_ig=50
        )

        with patch(
            "options_arena.services.universe.map_yfinance_to_metadata",
            return_value=_make_ticker_metadata("AAPL"),
        ):
            result = runner.invoke(app, ["universe", "index", "--force"])

        assert result.exit_code == 0
        # Sector coverage = 75/100 = 75.0%
        assert "75.0%" in result.output
        assert "Sector coverage" in result.output

    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.UniverseService")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    def test_empty_universe(
        self,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_universe_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Verify graceful handling when CBOE returns no tickers."""
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers.return_value = []
        mock_universe_cls.return_value = mock_universe
        mock_market = AsyncMock()
        mock_market_cls.return_value = mock_market
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        result = runner.invoke(app, ["universe", "index", "--force"])

        assert result.exit_code == 0
        assert "nothing to index" in result.output.lower()
        # No fetch_ticker_info calls expected
        mock_market.fetch_ticker_info.assert_not_awaited()

    @patch("options_arena.cli.commands.Database")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.MarketDataService")
    @patch("options_arena.cli.commands.UniverseService")
    @patch("options_arena.cli.commands.ServiceCache")
    @patch("options_arena.cli.commands.RateLimiter")
    def test_all_tickers_fresh_skips_work(
        self,
        mock_limiter_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_universe_cls: MagicMock,
        mock_market_cls: MagicMock,
        mock_repo_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Verify no fetches when all tickers are fresh and not --force."""
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers.return_value = ["AAPL", "MSFT"]
        mock_universe_cls.return_value = mock_universe
        mock_market = AsyncMock()
        mock_market_cls.return_value = mock_market
        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        # 2 tickers in DB, none stale, none missing
        mock_repo.get_metadata_coverage.return_value = _make_coverage(total=2)
        mock_repo.get_stale_tickers.return_value = []
        mock_repo.get_all_ticker_metadata.return_value = [
            _make_ticker_metadata("AAPL"),
            _make_ticker_metadata("MSFT"),
        ]

        result = runner.invoke(app, ["universe", "index"])

        assert result.exit_code == 0
        assert "nothing to index" in result.output.lower()
        mock_market.fetch_ticker_info.assert_not_awaited()
