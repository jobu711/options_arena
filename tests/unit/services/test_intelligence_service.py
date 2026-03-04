"""Unit tests for IntelligenceService.

Tests cover:
- Construction and lifecycle (close)
- fetch_analyst_targets: happy path, cache hit, config disabled, timeout, exception,
  empty DataFrame, consensus_score computed, target_upside computed
- fetch_analyst_activity: happy path, action map, date from index, cap at 10,
  upgrades/downgrades 30d counted, exception
- fetch_insider_activity: happy path, transaction type from text, NaN value → None,
  net buys 90d, buy ratio, cap at 20, exception
- fetch_institutional: happy path, major holders indexed by key, pctHeld, top 5 cap,
  exception
- fetch_news_headlines: happy path, nested title extraction, cap at 5, config disabled,
  exception
- fetch_intelligence: aggregator all populated, partial failure, all fail → None,
  disabled → None
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from options_arena.models.config import IntelligenceConfig
from options_arena.models.intelligence import (
    AnalystActivitySnapshot,
    AnalystSnapshot,
    InsiderSnapshot,
    InstitutionalSnapshot,
    IntelligencePackage,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create a mock ServiceCache."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_limiter() -> MagicMock:
    """Create a mock RateLimiter that acts as async context manager."""
    limiter = MagicMock()
    limiter.__aenter__ = AsyncMock(return_value=limiter)
    limiter.__aexit__ = AsyncMock(return_value=None)
    return limiter


@pytest.fixture
def config() -> IntelligenceConfig:
    """Default IntelligenceConfig for tests."""
    return IntelligenceConfig()


@pytest.fixture
def disabled_config() -> IntelligenceConfig:
    """IntelligenceConfig with master toggle disabled."""
    return IntelligenceConfig(enabled=False)


@pytest.fixture
def analyst_disabled_config() -> IntelligenceConfig:
    """IntelligenceConfig with analyst disabled."""
    return IntelligenceConfig(analyst_enabled=False)


@pytest.fixture
def insider_disabled_config() -> IntelligenceConfig:
    """IntelligenceConfig with insider disabled."""
    return IntelligenceConfig(insider_enabled=False)


@pytest.fixture
def institutional_disabled_config() -> IntelligenceConfig:
    """IntelligenceConfig with institutional disabled."""
    return IntelligenceConfig(institutional_enabled=False)


@pytest.fixture
def news_disabled_config() -> IntelligenceConfig:
    """IntelligenceConfig with news disabled."""
    return IntelligenceConfig(news_fallback_enabled=False)


# ---------------------------------------------------------------------------
# Helper factory — builds IntelligenceService without importing it directly
# (will fail until implementation exists)
# ---------------------------------------------------------------------------


def _make_service(
    config: IntelligenceConfig,
    cache: MagicMock,
    limiter: MagicMock,
) -> "IntelligenceService":  # noqa: F821
    from options_arena.services.intelligence import IntelligenceService

    return IntelligenceService(config=config, cache=cache, limiter=limiter)


# ---------------------------------------------------------------------------
# Helper: build yfinance-like DataFrames
# ---------------------------------------------------------------------------


def _make_analyst_targets_dict() -> dict[str, float]:
    """Build a yfinance-style analyst price targets dict."""
    return {
        "current": 185.0,
        "low": 150.0,
        "high": 220.0,
        "mean": 195.0,
        "median": 192.0,
    }


def _make_recommendations_df() -> pd.DataFrame:
    """Build a yfinance-style recommendations DataFrame."""
    return pd.DataFrame(
        {
            "period": ["0m", "-1m", "-2m", "-3m"],
            "strongBuy": [5, 3, 4, 2],
            "buy": [10, 8, 9, 7],
            "hold": [8, 6, 7, 5],
            "sell": [2, 1, 2, 1],
            "strongSell": [1, 0, 1, 0],
        }
    )


def _make_upgrades_downgrades_df() -> pd.DataFrame:
    """Build a yfinance-style upgrades/downgrades DataFrame with date in index."""
    today = date.today()
    dates = [
        today - timedelta(days=5),
        today - timedelta(days=10),
        today - timedelta(days=15),
        today - timedelta(days=60),
    ]
    df = pd.DataFrame(
        {
            "Firm": ["Goldman Sachs", "JPMorgan", "Morgan Stanley", "Citi"],
            "ToGrade": ["Outperform", "Buy", "Equal-Weight", "Sell"],
            "FromGrade": ["Neutral", "Hold", "", "Buy"],
            "Action": ["up", "up", "main", "down"],
        },
        index=pd.DatetimeIndex(dates, name="GradeDate"),
    )
    return df


def _make_insider_transactions_df() -> pd.DataFrame:
    """Build a yfinance-style insider transactions DataFrame."""
    today = date.today()
    return pd.DataFrame(
        {
            "Insider": ["John Doe", "Jane Smith", "Bob Wilson"],
            "Position": ["CEO", "CFO", "VP"],
            "Shares": [5000, 3000, 1000],
            "Value": [500000.0, float("nan"), 100000.0],
            "Text": [
                "Sale of shares on 2026-01-15",
                "Purchase of shares on 2026-01-20",
                "Gift of shares on 2026-02-01",
            ],
            "Start Date": [
                pd.Timestamp(today - timedelta(days=30)),
                pd.Timestamp(today - timedelta(days=20)),
                pd.Timestamp(today - timedelta(days=10)),
            ],
            "Transaction": ["", "", ""],  # Always empty in yfinance
        }
    )


def _make_major_holders_df() -> pd.DataFrame:
    """Build a yfinance-style major holders DataFrame."""
    return pd.DataFrame(
        {"Value": [0.02, 0.65, 0.72, 5500]},
        index=[
            "insidersPercentHeld",
            "institutionsPercentHeld",
            "institutionsFloatPercentHeld",
            "institutionsCount",
        ],
    )


def _make_institutional_holders_df() -> pd.DataFrame:
    """Build a yfinance-style institutional holders DataFrame."""
    return pd.DataFrame(
        {
            "Holder": [
                "Vanguard",
                "BlackRock",
                "State Street",
                "Fidelity",
                "Capital Research",
                "T. Rowe Price",
            ],
            "pctHeld": [0.097, 0.085, 0.045, 0.032, 0.028, 0.020],
        }
    )


def _make_news_response() -> list[dict[str, object]]:
    """Build a yfinance-style news response."""
    return [
        {"content": {"title": "Apple Beats Earnings Estimates"}},
        {"content": {"title": "AAPL Stock Rises on Strong iPhone Sales"}},
        {"content": {"title": "Apple Launches New AI Features"}},
        {"content": {"title": "Tech Sector Rallies Led by Apple"}},
        {"content": {"title": "Apple Expands Services Revenue"}},
        {"content": {"title": "Extra Headline That Should Be Capped"}},
    ]


# ===========================================================================
# TestServiceLifecycle
# ===========================================================================


class TestServiceLifecycle:
    """Test IntelligenceService construction and close."""

    @pytest.mark.asyncio
    async def test_close(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """close() should complete without error."""
        service = _make_service(config, mock_cache, mock_limiter)
        await service.close()  # Should not raise


# ===========================================================================
# TestFetchAnalystTargets
# ===========================================================================


class TestFetchAnalystTargets:
    """Tests for IntelligenceService.fetch_analyst_targets."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_snapshot(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Happy path should return a fully populated AnalystSnapshot."""
        service = _make_service(config, mock_cache, mock_limiter)
        targets_df = _make_analyst_targets_dict()
        recs_df = _make_recommendations_df()

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=targets_df)
        mock_ticker.get_recommendations = MagicMock(return_value=recs_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_targets("AAPL", 185.0)

        assert result is not None
        assert isinstance(result, AnalystSnapshot)
        assert result.ticker == "AAPL"
        assert result.target_low == pytest.approx(150.0)
        assert result.target_high == pytest.approx(220.0)
        assert result.target_mean == pytest.approx(195.0)
        assert result.target_median == pytest.approx(192.0)
        assert result.strong_buy == 5
        assert result.buy == 10
        assert result.hold == 8
        assert result.sell == 2
        assert result.strong_sell == 1

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return cached result when cache has data."""
        snapshot = AnalystSnapshot(
            ticker="AAPL",
            target_mean=195.0,
            current_price=185.0,
            strong_buy=5,
            buy=10,
            hold=8,
            sell=2,
            strong_sell=1,
            fetched_at=NOW_UTC,
        )
        mock_cache.get = AsyncMock(return_value=snapshot.model_dump_json().encode())

        service = _make_service(config, mock_cache, mock_limiter)
        result = await service.fetch_analyst_targets("AAPL", 185.0)

        assert result is not None
        assert result.ticker == "AAPL"
        assert result.target_mean == pytest.approx(195.0)

    @pytest.mark.asyncio
    async def test_config_disabled_returns_none(
        self,
        analyst_disabled_config: IntelligenceConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Should return None when analyst_enabled is False."""
        service = _make_service(analyst_disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_analyst_targets("AAPL", 185.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_master_toggle_disabled_returns_none(
        self,
        disabled_config: IntelligenceConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Should return None when master enabled toggle is False.

        The aggregator checks enabled, but individual methods also respect it
        indirectly via the aggregator. This test verifies the aggregator path.
        """
        service = _make_service(disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_intelligence("AAPL", 185.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_yfinance_timeout_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None on yfinance timeout."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(side_effect=TimeoutError("timeout"))

        with (
            patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker),
            patch(
                "options_arena.services.intelligence.asyncio.to_thread",
                side_effect=TimeoutError("timeout"),
            ),
        ):
            result = await service.fetch_analyst_targets("AAPL", 185.0)

        assert result is None

    @pytest.mark.asyncio
    async def test_yfinance_exception_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None on any yfinance exception (never-raises contract)."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(
            side_effect=RuntimeError("network error")
        )

        with (
            patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker),
            patch(
                "options_arena.services.intelligence.asyncio.to_thread",
                side_effect=RuntimeError("network error"),
            ),
        ):
            result = await service.fetch_analyst_targets("AAPL", 185.0)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_dataframe_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None when targets dict is empty and recs DataFrame is empty."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value={})
        mock_ticker.get_recommendations = MagicMock(return_value=pd.DataFrame())

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_targets("AAPL", 185.0)

        assert result is None

    @pytest.mark.asyncio
    async def test_consensus_score_computed_correctly(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """consensus_score should be computed from analyst counts.

        Formula: (5*2 + 10*1 + 8*0 + 2*-1 + 1*-2) / (26*2) = 16/52 = 0.3077
        """
        service = _make_service(config, mock_cache, mock_limiter)
        targets_df = _make_analyst_targets_dict()
        recs_df = _make_recommendations_df()

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=targets_df)
        mock_ticker.get_recommendations = MagicMock(return_value=recs_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_targets("AAPL", 185.0)

        assert result is not None
        assert result.consensus_score is not None
        # (5*2 + 10*1 + 8*0 + 2*-1 + 1*-2) = 10+10+0-2-2 = 16
        # total = 26, max = 26*2 = 52
        assert result.consensus_score == pytest.approx(16 / 52, rel=1e-4)

    @pytest.mark.asyncio
    async def test_target_upside_computed_correctly(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """target_upside_pct should be (target_mean - current_price) / current_price.

        (195.0 - 185.0) / 185.0 = 0.054054...
        """
        service = _make_service(config, mock_cache, mock_limiter)
        targets_df = _make_analyst_targets_dict()
        recs_df = _make_recommendations_df()

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=targets_df)
        mock_ticker.get_recommendations = MagicMock(return_value=recs_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_targets("AAPL", 185.0)

        assert result is not None
        assert result.target_upside_pct is not None
        assert result.target_upside_pct == pytest.approx((195.0 - 185.0) / 185.0, rel=1e-4)

    @pytest.mark.asyncio
    async def test_cache_set_called_on_success(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should cache result on successful fetch."""
        service = _make_service(config, mock_cache, mock_limiter)
        targets_df = _make_analyst_targets_dict()
        recs_df = _make_recommendations_df()

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=targets_df)
        mock_ticker.get_recommendations = MagicMock(return_value=recs_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            await service.fetch_analyst_targets("AAPL", 185.0)

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][0] == "intel:analyst:AAPL"
        assert call_args[1]["ttl"] == config.analyst_cache_ttl


# ===========================================================================
# TestFetchAnalystActivity
# ===========================================================================


class TestFetchAnalystActivity:
    """Tests for IntelligenceService.fetch_analyst_activity."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_snapshot(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Happy path should return a populated AnalystActivitySnapshot."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_upgrades_downgrades_df()

        mock_ticker = MagicMock()
        mock_ticker.get_upgrades_downgrades = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_activity("AAPL")

        assert result is not None
        assert isinstance(result, AnalystActivitySnapshot)
        assert result.ticker == "AAPL"
        assert len(result.recent_changes) == 4

    @pytest.mark.asyncio
    async def test_action_map_applied(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Actions should be mapped from abbreviations (up, down, etc.) to full names."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_upgrades_downgrades_df()

        mock_ticker = MagicMock()
        mock_ticker.get_upgrades_downgrades = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_activity("AAPL")

        assert result is not None
        actions = [change.action for change in result.recent_changes]
        assert "Upgrade" in actions
        assert "Downgrade" in actions
        assert "Maintained" in actions

    @pytest.mark.asyncio
    async def test_date_from_index_parsed(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Dates should be parsed from DataFrame index (GradeDate), not a column."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_upgrades_downgrades_df()

        mock_ticker = MagicMock()
        mock_ticker.get_upgrades_downgrades = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_activity("AAPL")

        assert result is not None
        for change in result.recent_changes:
            assert isinstance(change.date, date)

    @pytest.mark.asyncio
    async def test_recent_changes_capped_at_10(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """recent_changes should be capped at 10 entries."""
        service = _make_service(config, mock_cache, mock_limiter)

        # Create 15 rows
        today = date.today()
        dates = [today - timedelta(days=i) for i in range(15)]
        df = pd.DataFrame(
            {
                "Firm": [f"Firm_{i}" for i in range(15)],
                "ToGrade": ["Buy"] * 15,
                "FromGrade": ["Hold"] * 15,
                "Action": ["up"] * 15,
            },
            index=pd.DatetimeIndex(dates, name="GradeDate"),
        )

        mock_ticker = MagicMock()
        mock_ticker.get_upgrades_downgrades = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_activity("AAPL")

        assert result is not None
        assert len(result.recent_changes) <= 10

    @pytest.mark.asyncio
    async def test_upgrades_downgrades_30d_counted(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """upgrades_30d and downgrades_30d should count only last 30 days."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_upgrades_downgrades_df()
        # df has 2 upgrades within 30d (days 5, 10), 1 maintained (day 15),
        # 1 downgrade outside 30d (day 60)

        mock_ticker = MagicMock()
        mock_ticker.get_upgrades_downgrades = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_activity("AAPL")

        assert result is not None
        assert result.upgrades_30d == 2  # Goldman day 5, JPMorgan day 10
        assert result.downgrades_30d == 0  # Citi downgrade is at day 60
        assert result.net_sentiment_30d == 2

    @pytest.mark.asyncio
    async def test_exception_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None on any exception."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_upgrades_downgrades = MagicMock(side_effect=RuntimeError("network error"))

        with (
            patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker),
            patch(
                "options_arena.services.intelligence.asyncio.to_thread",
                side_effect=RuntimeError("network error"),
            ),
        ):
            result = await service.fetch_analyst_activity("AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_dataframe_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None when upgrades_downgrades is empty."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_upgrades_downgrades = MagicMock(return_value=pd.DataFrame())

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_analyst_activity("AAPL")

        assert result is None


# ===========================================================================
# TestFetchInsiderActivity
# ===========================================================================


class TestFetchInsiderActivity:
    """Tests for IntelligenceService.fetch_insider_activity."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_snapshot(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Happy path should return a populated InsiderSnapshot."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_insider_transactions_df()

        mock_ticker = MagicMock()
        mock_ticker.get_insider_transactions = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_insider_activity("AAPL")

        assert result is not None
        assert isinstance(result, InsiderSnapshot)
        assert result.ticker == "AAPL"
        assert len(result.transactions) == 3

    @pytest.mark.asyncio
    async def test_transaction_type_parsed_from_text(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Transaction type should be parsed from Text column, not Transaction column."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_insider_transactions_df()

        mock_ticker = MagicMock()
        mock_ticker.get_insider_transactions = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_insider_activity("AAPL")

        assert result is not None
        types = [t.transaction_type for t in result.transactions]
        assert "Sale" in types
        assert "Purchase" in types
        assert "Gift" in types

    @pytest.mark.asyncio
    async def test_value_nan_becomes_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """NaN values should be converted to None via safe_float."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_insider_transactions_df()

        mock_ticker = MagicMock()
        mock_ticker.get_insider_transactions = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_insider_activity("AAPL")

        assert result is not None
        # Jane Smith has NaN value
        jane = [t for t in result.transactions if t.insider_name == "Jane Smith"]
        assert len(jane) == 1
        assert jane[0].value is None

    @pytest.mark.asyncio
    async def test_net_buys_90d_computed(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """net_insider_buys_90d = purchases - sales within 90 days."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_insider_transactions_df()

        mock_ticker = MagicMock()
        mock_ticker.get_insider_transactions = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_insider_activity("AAPL")

        assert result is not None
        # 1 purchase - 1 sale = 0 (gift is neither)
        assert result.net_insider_buys_90d == 0

    @pytest.mark.asyncio
    async def test_buy_ratio_computed(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """insider_buy_ratio = purchases / (purchases + sales) within 90 days."""
        service = _make_service(config, mock_cache, mock_limiter)
        df = _make_insider_transactions_df()

        mock_ticker = MagicMock()
        mock_ticker.get_insider_transactions = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_insider_activity("AAPL")

        assert result is not None
        # 1 purchase, 1 sale → ratio = 1/2 = 0.5
        assert result.insider_buy_ratio is not None
        assert result.insider_buy_ratio == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_transactions_capped_at_20(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """transactions should be capped at 20 entries."""
        service = _make_service(config, mock_cache, mock_limiter)
        today = date.today()

        # Create 25 rows
        df = pd.DataFrame(
            {
                "Insider": [f"Person_{i}" for i in range(25)],
                "Position": ["Director"] * 25,
                "Shares": [100] * 25,
                "Value": [10000.0] * 25,
                "Text": ["Sale of shares"] * 25,
                "Start Date": [pd.Timestamp(today - timedelta(days=i)) for i in range(25)],
                "Transaction": [""] * 25,
            }
        )

        mock_ticker = MagicMock()
        mock_ticker.get_insider_transactions = MagicMock(return_value=df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_insider_activity("AAPL")

        assert result is not None
        assert len(result.transactions) <= 20

    @pytest.mark.asyncio
    async def test_exception_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None on any exception."""
        service = _make_service(config, mock_cache, mock_limiter)

        with patch(
            "options_arena.services.intelligence.asyncio.to_thread",
            side_effect=RuntimeError("network error"),
        ):
            result = await service.fetch_insider_activity("AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_insider_disabled_returns_none(
        self,
        insider_disabled_config: IntelligenceConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Should return None when insider_enabled is False."""
        service = _make_service(insider_disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_insider_activity("AAPL")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_dataframe_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None when insider transactions is empty."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_insider_transactions = MagicMock(return_value=pd.DataFrame())

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_insider_activity("AAPL")

        assert result is None


# ===========================================================================
# TestFetchInstitutional
# ===========================================================================


class TestFetchInstitutional:
    """Tests for IntelligenceService.fetch_institutional."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_snapshot(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Happy path should return a populated InstitutionalSnapshot."""
        service = _make_service(config, mock_cache, mock_limiter)
        major_df = _make_major_holders_df()
        inst_df = _make_institutional_holders_df()

        mock_ticker = MagicMock()
        mock_ticker.get_major_holders = MagicMock(return_value=major_df)
        mock_ticker.get_institutional_holders = MagicMock(return_value=inst_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_institutional("AAPL")

        assert result is not None
        assert isinstance(result, InstitutionalSnapshot)
        assert result.ticker == "AAPL"
        assert result.institutional_pct == pytest.approx(0.65, abs=0.01)

    @pytest.mark.asyncio
    async def test_major_holders_indexed_by_key(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Major holders data should be accessed by string index keys."""
        service = _make_service(config, mock_cache, mock_limiter)
        major_df = _make_major_holders_df()
        inst_df = _make_institutional_holders_df()

        mock_ticker = MagicMock()
        mock_ticker.get_major_holders = MagicMock(return_value=major_df)
        mock_ticker.get_institutional_holders = MagicMock(return_value=inst_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_institutional("AAPL")

        assert result is not None
        assert result.insider_pct == pytest.approx(0.02, abs=0.01)
        assert result.institutional_float_pct == pytest.approx(0.72, abs=0.01)
        assert result.institutions_count == 5500

    @pytest.mark.asyncio
    async def test_institutional_holders_pct_held(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Institutional holders should use pctHeld column."""
        service = _make_service(config, mock_cache, mock_limiter)
        major_df = _make_major_holders_df()
        inst_df = _make_institutional_holders_df()

        mock_ticker = MagicMock()
        mock_ticker.get_major_holders = MagicMock(return_value=major_df)
        mock_ticker.get_institutional_holders = MagicMock(return_value=inst_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_institutional("AAPL")

        assert result is not None
        assert len(result.top_holder_pcts) <= 5
        assert result.top_holder_pcts[0] == pytest.approx(0.097, abs=0.001)

    @pytest.mark.asyncio
    async def test_top_holders_capped_at_5(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """top_holders and top_holder_pcts should be capped at 5."""
        service = _make_service(config, mock_cache, mock_limiter)
        major_df = _make_major_holders_df()
        inst_df = _make_institutional_holders_df()  # Has 6 rows

        mock_ticker = MagicMock()
        mock_ticker.get_major_holders = MagicMock(return_value=major_df)
        mock_ticker.get_institutional_holders = MagicMock(return_value=inst_df)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_institutional("AAPL")

        assert result is not None
        assert len(result.top_holders) <= 5
        assert len(result.top_holder_pcts) <= 5
        assert "Vanguard" in result.top_holders

    @pytest.mark.asyncio
    async def test_exception_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None on any exception."""
        service = _make_service(config, mock_cache, mock_limiter)

        with patch(
            "options_arena.services.intelligence.asyncio.to_thread",
            side_effect=RuntimeError("network error"),
        ):
            result = await service.fetch_institutional("AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_institutional_disabled_returns_none(
        self,
        institutional_disabled_config: IntelligenceConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Should return None when institutional_enabled is False."""
        service = _make_service(institutional_disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_institutional("AAPL")
        assert result is None

    @pytest.mark.asyncio
    async def test_none_dataframes_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None when both major and institutional holders are None."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_major_holders = MagicMock(return_value=None)
        mock_ticker.get_institutional_holders = MagicMock(return_value=None)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_institutional("AAPL")

        assert result is None


# ===========================================================================
# TestFetchNewsHeadlines
# ===========================================================================


class TestFetchNewsHeadlines:
    """Tests for IntelligenceService.fetch_news_headlines."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_titles(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Happy path should return a list of headline strings."""
        service = _make_service(config, mock_cache, mock_limiter)
        news_data = _make_news_response()

        mock_ticker = MagicMock()
        mock_ticker.get_news = MagicMock(return_value=news_data)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_news_headlines("AAPL")

        assert result is not None
        assert isinstance(result, list)
        assert all(isinstance(h, str) for h in result)

    @pytest.mark.asyncio
    async def test_nested_title_extraction(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Titles should be extracted from item['content']['title']."""
        service = _make_service(config, mock_cache, mock_limiter)
        news_data = _make_news_response()

        mock_ticker = MagicMock()
        mock_ticker.get_news = MagicMock(return_value=news_data)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_news_headlines("AAPL")

        assert result is not None
        assert "Apple Beats Earnings Estimates" in result

    @pytest.mark.asyncio
    async def test_headlines_capped_at_5(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Headlines should be capped at 5."""
        service = _make_service(config, mock_cache, mock_limiter)
        news_data = _make_news_response()  # Has 6 items

        mock_ticker = MagicMock()
        mock_ticker.get_news = MagicMock(return_value=news_data)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_news_headlines("AAPL")

        assert result is not None
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_config_disabled_returns_none(
        self,
        news_disabled_config: IntelligenceConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Should return None when news_fallback_enabled is False."""
        service = _make_service(news_disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_news_headlines("AAPL")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None on any exception."""
        service = _make_service(config, mock_cache, mock_limiter)

        with patch(
            "options_arena.services.intelligence.asyncio.to_thread",
            side_effect=RuntimeError("network error"),
        ):
            result = await service.fetch_news_headlines("AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_news_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None when news list is empty."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_news = MagicMock(return_value=[])

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_news_headlines("AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_news_handled_gracefully(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should handle malformed news items without crashing."""
        service = _make_service(config, mock_cache, mock_limiter)
        news_data = [
            {"content": {"title": "Valid Title"}},
            {"content": {}},  # Missing title
            {"bad_key": "bad_value"},  # Missing content
            {"content": {"title": "Another Valid"}},
        ]

        mock_ticker = MagicMock()
        mock_ticker.get_news = MagicMock(return_value=news_data)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_news_headlines("AAPL")

        assert result is not None
        assert "Valid Title" in result
        assert "Another Valid" in result


# ===========================================================================
# TestFetchIntelligence
# ===========================================================================


class TestFetchIntelligence:
    """Tests for IntelligenceService.fetch_intelligence (aggregator)."""

    @pytest.mark.asyncio
    async def test_aggregator_all_populated(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return IntelligencePackage with all fields populated."""
        service = _make_service(config, mock_cache, mock_limiter)

        targets_df = _make_analyst_targets_dict()
        recs_df = _make_recommendations_df()
        ud_df = _make_upgrades_downgrades_df()
        insider_df = _make_insider_transactions_df()
        major_df = _make_major_holders_df()
        inst_df = _make_institutional_holders_df()
        news_data = _make_news_response()

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=targets_df)
        mock_ticker.get_recommendations = MagicMock(return_value=recs_df)
        mock_ticker.get_upgrades_downgrades = MagicMock(return_value=ud_df)
        mock_ticker.get_insider_transactions = MagicMock(return_value=insider_df)
        mock_ticker.get_major_holders = MagicMock(return_value=major_df)
        mock_ticker.get_institutional_holders = MagicMock(return_value=inst_df)
        mock_ticker.get_news = MagicMock(return_value=news_data)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_intelligence("AAPL", 185.0)

        assert result is not None
        assert isinstance(result, IntelligencePackage)
        assert result.ticker == "AAPL"
        assert result.analyst is not None
        assert result.analyst_activity is not None
        assert result.insider is not None
        assert result.institutional is not None
        assert result.news_headlines is not None
        assert result.intelligence_completeness() == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_aggregator_partial_failure(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return partial IntelligencePackage when some methods fail."""
        service = _make_service(config, mock_cache, mock_limiter)

        targets_df = _make_analyst_targets_dict()
        recs_df = _make_recommendations_df()
        news_data = _make_news_response()

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(return_value=targets_df)
        mock_ticker.get_recommendations = MagicMock(return_value=recs_df)
        # These will fail
        mock_ticker.get_upgrades_downgrades = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_insider_transactions = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_major_holders = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_institutional_holders = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_news = MagicMock(return_value=news_data)

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_intelligence("AAPL", 185.0)

        assert result is not None
        assert result.analyst is not None
        assert result.news_headlines is not None
        # Failed methods should be None
        assert result.intelligence_completeness() < 1.0

    @pytest.mark.asyncio
    async def test_aggregator_all_fail_returns_none(
        self, config: IntelligenceConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Should return None when all methods fail."""
        service = _make_service(config, mock_cache, mock_limiter)

        mock_ticker = MagicMock()
        mock_ticker.get_analyst_price_targets = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_recommendations = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_upgrades_downgrades = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_insider_transactions = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_major_holders = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_institutional_holders = MagicMock(side_effect=RuntimeError("fail"))
        mock_ticker.get_news = MagicMock(side_effect=RuntimeError("fail"))

        with patch("options_arena.services.intelligence.yf.Ticker", return_value=mock_ticker):
            result = await service.fetch_intelligence("AAPL", 185.0)

        assert result is None

    @pytest.mark.asyncio
    async def test_aggregator_disabled_returns_none(
        self,
        disabled_config: IntelligenceConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Should return None when master enabled toggle is False."""
        service = _make_service(disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_intelligence("AAPL", 185.0)
        assert result is None
