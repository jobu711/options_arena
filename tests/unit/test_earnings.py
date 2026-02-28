"""Tests for earnings calendar overlay — service method, prompt injection, pipeline.

Covers:
  - MarketDataService.fetch_earnings_date() (mock yfinance, caching, None handling)
  - Prompt injection in render_context_block() (warning appears/doesn't based on date)
  - TickerScore.next_earnings field (serialization, None handling)
  - Pipeline integration (earnings_dates propagation)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_arena.agents._parsing import render_context_block
from options_arena.models.analysis import MarketContext
from options_arena.models.config import ServiceConfig
from options_arena.models.enums import ExerciseStyle, MacdSignal, SignalDirection
from options_arena.models.scan import IndicatorSignals, TickerScore
from options_arena.services.cache import ServiceCache
from options_arena.services.market_data import (
    MarketDataService,
    _deserialize_earnings_date,
    _serialize_earnings_date,
)
from options_arena.services.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> ServiceConfig:
    return ServiceConfig()


@pytest.fixture
def cache(config: ServiceConfig) -> ServiceCache:
    return ServiceCache(config, db_path=None, max_size=100)


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(rate=1000.0, max_concurrent=100)


@pytest.fixture
def service(config: ServiceConfig, cache: ServiceCache, limiter: RateLimiter) -> MarketDataService:
    return MarketDataService(config=config, cache=cache, limiter=limiter)


def _make_market_context(
    *,
    next_earnings: date | None = None,
    ticker: str = "AAPL",
) -> MarketContext:
    """Build a minimal MarketContext for prompt tests."""
    return MarketContext(
        ticker=ticker,
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("200.00"),
        price_52w_low=Decimal("140.00"),
        rsi_14=55.0,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        next_earnings=next_earnings,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime.now(UTC),
        composite_score=72.5,
        direction_signal=SignalDirection.BULLISH,
    )


# ---------------------------------------------------------------------------
# Service method tests: fetch_earnings_date()
# ---------------------------------------------------------------------------


class TestFetchEarningsDate:
    """Tests for MarketDataService.fetch_earnings_date()."""

    @pytest.mark.asyncio
    async def test_returns_date_from_yfinance_calendar(self, service: MarketDataService) -> None:
        """Should return the nearest future earnings date from calendar."""
        future_date = date.today() + timedelta(days=10)
        calendar_data: dict[str, Any] = {
            "Earnings Date": [pd.Timestamp(future_date)],
        }

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = calendar_data
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("AAPL")

        assert result == future_date

    @pytest.mark.asyncio
    async def test_returns_none_when_no_calendar(self, service: MarketDataService) -> None:
        """Should return None when calendar is empty."""
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = {}
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("BADTK")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_calendar_is_none(self, service: MarketDataService) -> None:
        """Should return None when calendar property returns None."""
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = None
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_exception(self, service: MarketDataService) -> None:
        """Should return None gracefully when yfinance raises."""
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            type(mock_obj).calendar = property(
                lambda _: (_ for _ in ()).throw(RuntimeError("boom"))
            )
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("FAIL")

        assert result is None

    @pytest.mark.asyncio
    async def test_picks_earliest_future_date(self, service: MarketDataService) -> None:
        """Should pick the earliest future date from multiple entries."""
        d1 = date.today() + timedelta(days=20)
        d2 = date.today() + timedelta(days=5)
        calendar_data: dict[str, Any] = {
            "Earnings Date": [pd.Timestamp(d1), pd.Timestamp(d2)],
        }

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = calendar_data
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("AAPL")

        assert result == d2

    @pytest.mark.asyncio
    async def test_ignores_past_dates(self, service: MarketDataService) -> None:
        """Should ignore past earnings dates."""
        past_date = date.today() - timedelta(days=5)
        future_date = date.today() + timedelta(days=15)
        calendar_data: dict[str, Any] = {
            "Earnings Date": [pd.Timestamp(past_date), pd.Timestamp(future_date)],
        }

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = calendar_data
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("AAPL")

        assert result == future_date

    @pytest.mark.asyncio
    async def test_all_past_dates_returns_none(self, service: MarketDataService) -> None:
        """Should return None if all earnings dates are in the past."""
        past1 = date.today() - timedelta(days=30)
        past2 = date.today() - timedelta(days=5)
        calendar_data: dict[str, Any] = {
            "Earnings Date": [pd.Timestamp(past1), pd.Timestamp(past2)],
        }

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = calendar_data
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("AAPL")

        assert result is None

    @pytest.mark.asyncio
    async def test_caches_result(
        self,
        service: MarketDataService,
    ) -> None:
        """Should cache the result and serve from cache on second call."""
        future_date = date.today() + timedelta(days=10)
        calendar_data: dict[str, Any] = {
            "Earnings Date": [pd.Timestamp(future_date)],
        }

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = calendar_data
            mock_ticker_cls.return_value = mock_obj

            first = await service.fetch_earnings_date("AAPL")
            second = await service.fetch_earnings_date("AAPL")

        assert first == future_date
        assert second == future_date
        # Second call should NOT have called yfinance again (only 1 Ticker creation)
        assert mock_ticker_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_caches_none_result(
        self,
        service: MarketDataService,
    ) -> None:
        """Should cache None results to avoid re-fetching."""
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = {}
            mock_ticker_cls.return_value = mock_obj

            first = await service.fetch_earnings_date("NOTICKER")
            second = await service.fetch_earnings_date("NOTICKER")

        assert first is None
        assert second is None
        # Only one yfinance call — second served from cache
        assert mock_ticker_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_handles_string_dates(self, service: MarketDataService) -> None:
        """Should handle date values returned as strings."""
        future_date = date.today() + timedelta(days=7)
        calendar_data: dict[str, Any] = {
            "Earnings Date": [future_date.isoformat()],
        }

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_obj = MagicMock()
            mock_obj.calendar = calendar_data
            mock_ticker_cls.return_value = mock_obj

            result = await service.fetch_earnings_date("AAPL")

        assert result == future_date


# ---------------------------------------------------------------------------
# Serialization helper tests
# ---------------------------------------------------------------------------


class TestEarningsDateSerialization:
    """Tests for _serialize_earnings_date / _deserialize_earnings_date."""

    def test_roundtrip_with_date(self) -> None:
        d = date(2026, 4, 15)
        serialized = _serialize_earnings_date(d)
        assert isinstance(serialized, bytes)
        result = _deserialize_earnings_date(serialized)
        assert result == d

    def test_roundtrip_with_none(self) -> None:
        serialized = _serialize_earnings_date(None)
        assert serialized == b"null"
        result = _deserialize_earnings_date(serialized)
        assert result is None

    def test_serialize_format(self) -> None:
        d = date(2026, 1, 5)
        assert _serialize_earnings_date(d) == b"2026-01-05"


# ---------------------------------------------------------------------------
# Prompt injection tests: render_context_block
# ---------------------------------------------------------------------------


class TestEarningsPromptInjection:
    """Tests for earnings warning in render_context_block()."""

    def test_no_warning_when_no_earnings(self) -> None:
        """Context block should have no earnings lines when next_earnings is None."""
        ctx = _make_market_context(next_earnings=None)
        block = render_context_block(ctx)
        assert "EARNINGS" not in block
        assert "IV crush" not in block

    def test_no_warning_when_earnings_far(self) -> None:
        """Context block should show earnings date but no warning when > 7 days."""
        far_date = date.today() + timedelta(days=30)
        ctx = _make_market_context(next_earnings=far_date)
        block = render_context_block(ctx)
        assert "NEXT EARNINGS:" in block
        assert "30d" in block
        assert "WARNING:" not in block
        assert "IV crush" not in block

    def test_warning_when_earnings_within_7_days(self) -> None:
        """Context block should include IV crush warning when earnings < 7 days."""
        near_date = date.today() + timedelta(days=3)
        ctx = _make_market_context(next_earnings=near_date)
        block = render_context_block(ctx)
        assert "NEXT EARNINGS:" in block
        assert "WARNING:" in block
        assert "IV crush risk is elevated" in block
        assert "3 days" in block

    def test_warning_on_earnings_day(self) -> None:
        """Context block should warn when earnings are today (0 days)."""
        ctx = _make_market_context(next_earnings=date.today())
        block = render_context_block(ctx)
        assert "WARNING:" in block
        assert "0 days" in block

    def test_warning_exactly_7_days(self) -> None:
        """Context block should include warning at exactly 7 days."""
        seven_days = date.today() + timedelta(days=7)
        ctx = _make_market_context(next_earnings=seven_days)
        block = render_context_block(ctx)
        assert "WARNING:" in block
        assert "7 days" in block

    def test_no_warning_at_8_days(self) -> None:
        """Context block should NOT include warning at 8 days."""
        eight_days = date.today() + timedelta(days=8)
        ctx = _make_market_context(next_earnings=eight_days)
        block = render_context_block(ctx)
        assert "NEXT EARNINGS:" in block
        assert "WARNING:" not in block


# ---------------------------------------------------------------------------
# TickerScore.next_earnings field tests
# ---------------------------------------------------------------------------


class TestTickerScoreNextEarnings:
    """Tests for the next_earnings field on TickerScore."""

    def test_default_is_none(self) -> None:
        ts = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        assert ts.next_earnings is None

    def test_set_earnings_date(self) -> None:
        d = date(2026, 4, 15)
        ts = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
            next_earnings=d,
        )
        assert ts.next_earnings == d

    def test_json_roundtrip_with_earnings(self) -> None:
        d = date(2026, 4, 15)
        ts = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
            next_earnings=d,
        )
        json_str = ts.model_dump_json()
        restored = TickerScore.model_validate_json(json_str)
        assert restored.next_earnings == d
        assert restored.ticker == "AAPL"

    def test_json_roundtrip_without_earnings(self) -> None:
        ts = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        json_str = ts.model_dump_json()
        restored = TickerScore.model_validate_json(json_str)
        assert restored.next_earnings is None

    def test_mutable_assignment(self) -> None:
        """TickerScore is NOT frozen — next_earnings can be set after construction."""
        ts = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        assert ts.next_earnings is None
        ts.next_earnings = date(2026, 3, 15)
        assert ts.next_earnings == date(2026, 3, 15)


# ---------------------------------------------------------------------------
# Pipeline model tests (earnings_dates field)
# ---------------------------------------------------------------------------


class TestOptionsResultEarnings:
    """Tests for earnings_dates on OptionsResult."""

    def test_default_empty(self) -> None:
        from options_arena.scan.models import OptionsResult

        result = OptionsResult(
            recommendations={},
            risk_free_rate=0.05,
        )
        assert result.earnings_dates == {}

    def test_with_earnings_dates(self) -> None:
        from options_arena.scan.models import OptionsResult

        d = date(2026, 4, 15)
        result = OptionsResult(
            recommendations={},
            risk_free_rate=0.05,
            earnings_dates={"AAPL": d},
        )
        assert result.earnings_dates["AAPL"] == d


class TestScanResultEarnings:
    """Tests for earnings_dates on ScanResult."""

    def test_default_empty(self) -> None:
        from options_arena.models import ScanPreset, ScanRun
        from options_arena.scan.models import ScanResult

        result = ScanResult(
            scan_run=ScanRun(
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                preset=ScanPreset.SP500,
                tickers_scanned=100,
                tickers_scored=50,
                recommendations=10,
            ),
            scores=[],
            recommendations={},
            risk_free_rate=0.05,
        )
        assert result.earnings_dates == {}

    def test_with_earnings_data(self) -> None:
        from options_arena.models import ScanPreset, ScanRun
        from options_arena.scan.models import ScanResult

        d = date(2026, 4, 15)
        result = ScanResult(
            scan_run=ScanRun(
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                preset=ScanPreset.SP500,
                tickers_scanned=100,
                tickers_scored=50,
                recommendations=10,
            ),
            scores=[],
            recommendations={},
            risk_free_rate=0.05,
            earnings_dates={"AAPL": d},
        )
        assert result.earnings_dates["AAPL"] == d


# ---------------------------------------------------------------------------
# build_market_context earnings parameter test
# ---------------------------------------------------------------------------


class TestBuildMarketContextEarnings:
    """Tests for build_market_context earnings parameter."""

    def test_next_earnings_passed_through(self) -> None:
        from options_arena.agents.orchestrator import build_market_context
        from options_arena.models import Quote, TickerInfo

        d = date(2026, 4, 15)
        ticker_score = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        quote = Quote(
            ticker="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.40"),
            ask=Decimal("185.60"),
            volume=1000000,
            timestamp=datetime.now(UTC),
        )
        ticker_info = TickerInfo(
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Technology",
            current_price=Decimal("185.50"),
            fifty_two_week_high=Decimal("200.00"),
            fifty_two_week_low=Decimal("140.00"),
        )

        ctx = build_market_context(ticker_score, quote, ticker_info, contracts=[], next_earnings=d)
        assert ctx.next_earnings == d

    def test_next_earnings_defaults_to_none(self) -> None:
        from options_arena.agents.orchestrator import build_market_context
        from options_arena.models import Quote, TickerInfo

        ticker_score = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        quote = Quote(
            ticker="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.40"),
            ask=Decimal("185.60"),
            volume=1000000,
            timestamp=datetime.now(UTC),
        )
        ticker_info = TickerInfo(
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Technology",
            current_price=Decimal("185.50"),
            fifty_two_week_high=Decimal("200.00"),
            fifty_two_week_low=Decimal("140.00"),
        )

        ctx = build_market_context(ticker_score, quote, ticker_info, contracts=[])
        assert ctx.next_earnings is None
