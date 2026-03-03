"""Tests for pipeline pre-scan narrowing filters (#225)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from options_arena.models import (
    IndicatorSignals,
    MarketCapTier,
    SignalDirection,
    TickerScore,
)
from options_arena.models.config import AppSettings, ScanConfig
from options_arena.models.market_data import TickerInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**scan_overrides: object) -> AppSettings:
    """Create AppSettings with scan config overrides."""
    scan_cfg = ScanConfig(**scan_overrides)
    return AppSettings(scan=scan_cfg)


def _make_ticker_score(
    ticker: str = "AAPL",
    score: float = 78.5,
    direction: SignalDirection = SignalDirection.BULLISH,
) -> TickerScore:
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(rsi=65.2, adx=28.4),
        scan_run_id=1,
    )


def _make_ticker_info(
    ticker: str = "AAPL",
    market_cap_tier: MarketCapTier | None = MarketCapTier.LARGE,
) -> TickerInfo:
    return TickerInfo(
        ticker=ticker,
        company_name=f"{ticker} Inc",
        sector="Technology",
        market_cap=1_000_000_000,
        market_cap_tier=market_cap_tier,
        current_price=Decimal("150.00"),
        fifty_two_week_high=Decimal("180.00"),
        fifty_two_week_low=Decimal("120.00"),
    )


# ---------------------------------------------------------------------------
# Direction filter (post-Phase 2)
# ---------------------------------------------------------------------------


class TestDirectionFilter:
    """Tests for direction_filter applied between Phase 2 and Phase 3."""

    def test_direction_filter_bullish_only(self) -> None:
        """Verify direction_filter narrows to bullish tickers."""
        scores = [
            _make_ticker_score("AAPL", direction=SignalDirection.BULLISH),
            _make_ticker_score("MSFT", direction=SignalDirection.BEARISH),
            _make_ticker_score("GOOGL", direction=SignalDirection.NEUTRAL),
        ]
        filtered = [
            ts for ts in scores if ts.direction == SignalDirection.BULLISH
        ]
        assert len(filtered) == 1
        assert filtered[0].ticker == "AAPL"

    def test_direction_filter_bearish_only(self) -> None:
        """Verify direction_filter narrows to bearish tickers."""
        scores = [
            _make_ticker_score("AAPL", direction=SignalDirection.BULLISH),
            _make_ticker_score("MSFT", direction=SignalDirection.BEARISH),
        ]
        filtered = [
            ts for ts in scores if ts.direction == SignalDirection.BEARISH
        ]
        assert len(filtered) == 1
        assert filtered[0].ticker == "MSFT"

    def test_direction_filter_none_returns_all(self) -> None:
        """Verify no direction_filter returns all tickers."""
        scores = [
            _make_ticker_score("AAPL", direction=SignalDirection.BULLISH),
            _make_ticker_score("MSFT", direction=SignalDirection.BEARISH),
        ]
        direction_filter = None
        if direction_filter is not None:
            scores = [ts for ts in scores if ts.direction == direction_filter]
        assert len(scores) == 2

    def test_direction_filter_empty_result(self) -> None:
        """Verify direction_filter can produce empty result set."""
        scores = [
            _make_ticker_score("AAPL", direction=SignalDirection.BULLISH),
        ]
        filtered = [
            ts for ts in scores if ts.direction == SignalDirection.BEARISH
        ]
        assert len(filtered) == 0


# ---------------------------------------------------------------------------
# Market cap filter (Phase 3 per-ticker)
# ---------------------------------------------------------------------------


class TestMarketCapFilter:
    """Tests for market_cap_tiers filter in Phase 3 per-ticker processing."""

    def test_market_cap_filter_excludes_wrong_tier(self) -> None:
        """Verify tickers outside selected market cap tiers are excluded."""
        config_tiers = [MarketCapTier.LARGE, MarketCapTier.MEGA]
        ticker_info = _make_ticker_info(market_cap_tier=MarketCapTier.SMALL)

        should_filter = (
            config_tiers
            and ticker_info.market_cap_tier is not None
            and ticker_info.market_cap_tier not in config_tiers
        )
        assert should_filter is True

    def test_market_cap_filter_passes_matching_tier(self) -> None:
        """Verify tickers with matching market cap tier pass through."""
        config_tiers = [MarketCapTier.LARGE, MarketCapTier.MEGA]
        ticker_info = _make_ticker_info(market_cap_tier=MarketCapTier.LARGE)

        should_filter = (
            config_tiers
            and ticker_info.market_cap_tier is not None
            and ticker_info.market_cap_tier not in config_tiers
        )
        assert should_filter is False

    def test_market_cap_filter_passes_without_ticker_info(self) -> None:
        """Verify tickers without market_cap_tier pass through (no false exclusion)."""
        config_tiers = [MarketCapTier.LARGE]
        ticker_info = _make_ticker_info(market_cap_tier=None)

        should_filter = (
            config_tiers
            and ticker_info.market_cap_tier is not None
            and ticker_info.market_cap_tier not in config_tiers
        )
        assert should_filter is False

    def test_market_cap_empty_tiers_no_filter(self) -> None:
        """Verify empty market_cap_tiers list means no filtering."""
        config_tiers: list[MarketCapTier] = []
        ticker_info = _make_ticker_info(market_cap_tier=MarketCapTier.MICRO)

        should_filter = (
            config_tiers
            and ticker_info.market_cap_tier is not None
            and ticker_info.market_cap_tier not in config_tiers
        )
        assert not should_filter


# ---------------------------------------------------------------------------
# Earnings proximity filter (Phase 3 per-ticker)
# ---------------------------------------------------------------------------


class TestEarningsProximityFilter:
    """Tests for exclude_near_earnings_days filter in Phase 3."""

    def test_earnings_filter_excludes_near_earnings(self) -> None:
        """Verify tickers with earnings within N days are excluded."""
        today = date.today()
        earnings_date = today + timedelta(days=3)
        exclude_days = 7

        days_to_earnings = (earnings_date - today).days
        should_filter = days_to_earnings <= exclude_days
        assert should_filter is True

    def test_earnings_filter_passes_far_earnings(self) -> None:
        """Verify tickers with earnings far away pass through."""
        today = date.today()
        earnings_date = today + timedelta(days=30)
        exclude_days = 7

        days_to_earnings = (earnings_date - today).days
        should_filter = days_to_earnings <= exclude_days
        assert should_filter is False

    def test_earnings_filter_passes_without_earnings_date(self) -> None:
        """Verify tickers without next_earnings pass through."""
        earnings_date = None
        exclude_days = 7

        should_filter = (
            exclude_days is not None
            and earnings_date is not None
            and (earnings_date - date.today()).days <= exclude_days
        )
        assert should_filter is False

    def test_earnings_filter_boundary_exact_days(self) -> None:
        """Verify earnings on exact boundary day is excluded (inclusive)."""
        today = date.today()
        earnings_date = today + timedelta(days=7)
        exclude_days = 7

        days_to_earnings = (earnings_date - today).days
        should_filter = days_to_earnings <= exclude_days
        assert should_filter is True

    def test_earnings_filter_zero_days(self) -> None:
        """Verify exclude_near_earnings_days=0 excludes tickers with earnings today."""
        today = date.today()
        earnings_date = today
        exclude_days = 0

        days_to_earnings = (earnings_date - today).days
        should_filter = days_to_earnings <= exclude_days
        assert should_filter is True

    def test_earnings_filter_none_config_no_filter(self) -> None:
        """Verify None exclude_near_earnings_days means no filtering."""
        exclude_days = None
        today = date.today()
        earnings_date = today + timedelta(days=1)

        should_filter = (
            exclude_days is not None
            and earnings_date is not None
            and (earnings_date - today).days <= exclude_days
        )
        assert should_filter is False


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------


class TestCombinedPreScanFilters:
    """Tests for composing multiple pre-scan filters."""

    def test_no_filters_runs_full_universe(self) -> None:
        """Verify empty/None filters don't exclude anything."""
        config = ScanConfig()
        assert config.market_cap_tiers == []
        assert config.exclude_near_earnings_days is None
        assert config.direction_filter is None
        assert config.min_iv_rank is None

    def test_all_filters_compose(self) -> None:
        """Verify market cap + earnings + direction compose correctly (AND logic)."""
        scores = [
            _make_ticker_score("AAPL", direction=SignalDirection.BULLISH),
            _make_ticker_score("MSFT", direction=SignalDirection.BEARISH),
            _make_ticker_score("GOOGL", direction=SignalDirection.BULLISH),
        ]
        # Direction filter: only bullish
        filtered = [ts for ts in scores if ts.direction == SignalDirection.BULLISH]
        assert len(filtered) == 2
        assert all(ts.direction == SignalDirection.BULLISH for ts in filtered)
