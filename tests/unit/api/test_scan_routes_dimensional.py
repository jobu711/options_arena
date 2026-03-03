"""Tests for API dimensional filtering on GET /api/scan/{id}/scores (#224)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.models import (
    IndicatorSignals,
    MarketCapTier,
    MarketRegime,
    SignalDirection,
    TickerScore,
)
from options_arena.models.scoring import DimensionalScores

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(
    ticker: str = "AAPL",
    score: float = 78.5,
    direction: SignalDirection = SignalDirection.BULLISH,
    direction_confidence: float | None = None,
    market_regime: MarketRegime | None = None,
    dimensional_scores: DimensionalScores | None = None,
    next_earnings: date | None = None,
) -> TickerScore:
    ts = TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(rsi=65.2, adx=28.4),
        scan_run_id=1,
    )
    ts.direction_confidence = direction_confidence
    ts.market_regime = market_regime
    ts.dimensional_scores = dimensional_scores
    ts.next_earnings = next_earnings
    return ts


def _make_dim(
    trend: float | None = 50.0,
    iv_vol: float | None = 50.0,
    flow: float | None = 50.0,
    risk: float | None = 50.0,
) -> DimensionalScores:
    return DimensionalScores(trend=trend, iv_vol=iv_vol, flow=flow, risk=risk)


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


class TestDimensionalFiltering:
    """Tests for the 8 new dimensional filter params."""

    @pytest.mark.asyncio
    async def test_filter_min_confidence(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify min_confidence excludes tickers below threshold."""
        scores = [
            _make_ticker_score(ticker="AAPL", direction_confidence=0.8),
            _make_ticker_score(ticker="MSFT", direction_confidence=0.3),
            _make_ticker_score(ticker="GOOGL", direction_confidence=None),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_confidence=0.5")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_market_regime(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify market_regime filters to exact match."""
        scores = [
            _make_ticker_score(ticker="AAPL", market_regime=MarketRegime.TRENDING),
            _make_ticker_score(ticker="MSFT", market_regime=MarketRegime.VOLATILE),
            _make_ticker_score(ticker="GOOGL", market_regime=None),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?market_regime=trending")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_min_trend(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify min_trend filters dimensional_scores.trend."""
        scores = [
            _make_ticker_score(ticker="AAPL", dimensional_scores=_make_dim(trend=80.0)),
            _make_ticker_score(ticker="MSFT", dimensional_scores=_make_dim(trend=30.0)),
            _make_ticker_score(ticker="GOOGL"),  # None dimensional_scores
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_trend=50")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_min_iv_vol(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify min_iv_vol filters dimensional_scores.iv_vol."""
        scores = [
            _make_ticker_score(ticker="AAPL", dimensional_scores=_make_dim(iv_vol=70.0)),
            _make_ticker_score(ticker="MSFT", dimensional_scores=_make_dim(iv_vol=20.0)),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_iv_vol=50")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_min_flow(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify min_flow filters dimensional_scores.flow."""
        scores = [
            _make_ticker_score(ticker="AAPL", dimensional_scores=_make_dim(flow=80.0)),
            _make_ticker_score(ticker="MSFT", dimensional_scores=_make_dim(flow=10.0)),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_flow=50")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_min_risk(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify min_risk filters dimensional_scores.risk."""
        scores = [
            _make_ticker_score(ticker="AAPL", dimensional_scores=_make_dim(risk=60.0)),
            _make_ticker_score(ticker="MSFT", dimensional_scores=_make_dim(risk=10.0)),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_risk=40")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_max_earnings_days(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify max_earnings_days excludes tickers with earnings too far away."""
        today = date.today()
        scores = [
            _make_ticker_score(ticker="AAPL", next_earnings=today + timedelta(days=5)),
            _make_ticker_score(ticker="MSFT", next_earnings=today + timedelta(days=30)),
            _make_ticker_score(ticker="GOOGL", next_earnings=None),  # no earnings
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?max_earnings_days=14")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_min_earnings_days(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify min_earnings_days includes only tickers with earnings soon enough."""
        today = date.today()
        scores = [
            _make_ticker_score(ticker="AAPL", next_earnings=today + timedelta(days=20)),
            _make_ticker_score(ticker="MSFT", next_earnings=today + timedelta(days=3)),
            _make_ticker_score(ticker="GOOGL", next_earnings=None),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_earnings_days=10")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_no_filters_returns_all(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify omitting all filters returns full result set (backward compat)."""
        scores = [
            _make_ticker_score(ticker="AAPL"),
            _make_ticker_score(ticker="MSFT"),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_combined_filters(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify multiple filters compose correctly (AND logic)."""
        scores = [
            _make_ticker_score(
                ticker="AAPL",
                direction_confidence=0.8,
                market_regime=MarketRegime.TRENDING,
                dimensional_scores=_make_dim(trend=80.0),
            ),
            _make_ticker_score(
                ticker="MSFT",
                direction_confidence=0.8,
                market_regime=MarketRegime.VOLATILE,
                dimensional_scores=_make_dim(trend=80.0),
            ),
            _make_ticker_score(
                ticker="GOOGL",
                direction_confidence=0.3,
                market_regime=MarketRegime.TRENDING,
                dimensional_scores=_make_dim(trend=80.0),
            ),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get(
            "/api/scan/1/scores?min_confidence=0.5&market_regime=trending&min_trend=50"
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_sort_by_direction_confidence(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify sort=direction_confidence orders results correctly."""
        scores = [
            _make_ticker_score(ticker="AAPL", direction_confidence=0.3),
            _make_ticker_score(ticker="MSFT", direction_confidence=0.9),
            _make_ticker_score(ticker="GOOGL", direction_confidence=0.6),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?sort=direction_confidence&order=desc")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items[0]["ticker"] == "MSFT"
        assert items[1]["ticker"] == "GOOGL"
        assert items[2]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_sort_by_direction_confidence_none_to_end(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify None direction_confidence sorts to end."""
        scores = [
            _make_ticker_score(ticker="AAPL", direction_confidence=None),
            _make_ticker_score(ticker="MSFT", direction_confidence=0.9),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?sort=direction_confidence&order=desc")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items[0]["ticker"] == "MSFT"
        assert items[1]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_with_null_dimensional_scores(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Pre-migration tickers (null dimensional_scores) excluded by filters."""
        scores = [
            _make_ticker_score(ticker="AAPL", dimensional_scores=_make_dim(trend=80.0)),
            _make_ticker_score(ticker="MSFT"),  # None dimensional_scores
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_trend=0")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_filter_boundary_values(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify filters at exact boundary values (inclusive)."""
        scores = [
            _make_ticker_score(
                ticker="AAPL",
                direction_confidence=0.5,
                dimensional_scores=_make_dim(trend=50.0),
            ),
        ]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?min_confidence=0.5&min_trend=50")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_invalid_market_regime_ignored(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify invalid market_regime value is silently ignored."""
        scores = [_make_ticker_score(ticker="AAPL")]
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        resp = await client.get("/api/scan/1/scores?market_regime=invalid")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestScanRequestExtensions:
    """Tests for ScanRequest pre-scan filter fields."""

    def test_scan_request_market_cap_tiers(self) -> None:
        """Verify ScanRequest accepts and validates market_cap_tiers."""
        from options_arena.api.schemas import ScanRequest

        req = ScanRequest(market_cap_tiers=["large", "mega"])
        assert MarketCapTier.LARGE in req.market_cap_tiers
        assert MarketCapTier.MEGA in req.market_cap_tiers

    def test_scan_request_market_cap_dedup(self) -> None:
        """Verify ScanRequest deduplicates market_cap_tiers."""
        from options_arena.api.schemas import ScanRequest

        req = ScanRequest(market_cap_tiers=["large", "large", "mega"])
        assert len(req.market_cap_tiers) == 2

    def test_scan_request_exclude_near_earnings(self) -> None:
        """Verify ScanRequest accepts exclude_near_earnings_days."""
        from options_arena.api.schemas import ScanRequest

        req = ScanRequest(exclude_near_earnings_days=7)
        assert req.exclude_near_earnings_days == 7

    def test_scan_request_defaults(self) -> None:
        """Verify ScanRequest defaults are backward compatible."""
        from options_arena.api.schemas import ScanRequest

        req = ScanRequest()
        assert req.market_cap_tiers == []
        assert req.exclude_near_earnings_days is None
