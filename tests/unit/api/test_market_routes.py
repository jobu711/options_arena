"""Tests for GET /api/market/heatmap endpoint and HeatmapTicker schema."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from options_arena.api.schemas import HeatmapTicker
from options_arena.models.enums import GICSIndustryGroup, GICSSector, MarketCapTier
from options_arena.models.metadata import TickerMetadata
from options_arena.services.market_data import BatchQuote
from options_arena.services.universe import SP500Constituent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_constituent(ticker: str, sector: str = "Information Technology") -> SP500Constituent:
    return SP500Constituent(ticker=ticker, sector=sector)


def _make_batch_quote(
    ticker: str,
    price: float = 150.0,
    change_pct: float = 1.5,
    volume: int = 1_000_000,
) -> BatchQuote:
    return BatchQuote(ticker=ticker, price=price, change_pct=change_pct, volume=volume)


def _make_metadata(
    ticker: str,
    sector: GICSSector = GICSSector.INFORMATION_TECHNOLOGY,
    industry_group: GICSIndustryGroup = GICSIndustryGroup.SOFTWARE_SERVICES,
    market_cap_tier: MarketCapTier = MarketCapTier.MEGA,
    company_name: str = "Apple Inc.",
) -> TickerMetadata:
    return TickerMetadata(
        ticker=ticker,
        sector=sector,
        industry_group=industry_group,
        market_cap_tier=market_cap_tier,
        company_name=company_name,
        last_updated=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# HeatmapTicker schema tests
# ---------------------------------------------------------------------------


class TestHeatmapTickerSchema:
    """Validate HeatmapTicker model behavior."""

    def test_valid_construction(self) -> None:
        """Verify valid data constructs successfully."""
        ht = HeatmapTicker(
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Information Technology",
            industry_group="Software & Services",
            market_cap_weight=100.0,
            change_pct=2.5,
            price=175.0,
            volume=5_000_000,
        )
        assert ht.ticker == "AAPL"
        assert ht.price == pytest.approx(175.0)
        assert ht.change_pct == pytest.approx(2.5)

    def test_frozen_model(self) -> None:
        """Verify HeatmapTicker is immutable."""
        ht = HeatmapTicker(
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="IT",
            industry_group="Software",
            market_cap_weight=100.0,
            change_pct=1.0,
            price=175.0,
            volume=1_000,
        )
        with pytest.raises(ValidationError):
            ht.price = 200.0  # type: ignore[misc]

    def test_isfinite_rejects_nan_price(self) -> None:
        """Verify NaN price raises ValidationError."""
        with pytest.raises(ValidationError, match="price must be finite"):
            HeatmapTicker(
                ticker="BAD",
                company_name="Bad Corp",
                sector="IT",
                industry_group="Software",
                market_cap_weight=10.0,
                change_pct=0.0,
                price=float("nan"),
                volume=100,
            )

    def test_isfinite_rejects_nan_change_pct(self) -> None:
        """Verify NaN change_pct raises ValidationError."""
        with pytest.raises(ValidationError, match="change_pct must be finite"):
            HeatmapTicker(
                ticker="BAD",
                company_name="Bad Corp",
                sector="IT",
                industry_group="Software",
                market_cap_weight=10.0,
                change_pct=float("nan"),
                price=100.0,
                volume=100,
            )

    def test_isfinite_rejects_inf_price(self) -> None:
        """Verify infinite price raises ValidationError."""
        with pytest.raises(ValidationError, match="price must be finite"):
            HeatmapTicker(
                ticker="BAD",
                company_name="Bad Corp",
                sector="IT",
                industry_group="Software",
                market_cap_weight=10.0,
                change_pct=0.0,
                price=math.inf,
                volume=100,
            )

    def test_negative_price_rejected(self) -> None:
        """Verify negative price raises ValidationError."""
        with pytest.raises(ValidationError, match="price must be positive"):
            HeatmapTicker(
                ticker="BAD",
                company_name="Bad Corp",
                sector="IT",
                industry_group="Software",
                market_cap_weight=10.0,
                change_pct=0.0,
                price=-5.0,
                volume=100,
            )

    def test_none_change_pct_accepted(self) -> None:
        """Verify None change_pct passes validation."""
        ht = HeatmapTicker(
            ticker="AAPL",
            company_name="Apple",
            sector="IT",
            industry_group="Software",
            market_cap_weight=100.0,
            change_pct=None,
            price=175.0,
            volume=1_000,
        )
        assert ht.change_pct is None

    def test_json_roundtrip(self) -> None:
        """Verify JSON serialization roundtrip."""
        ht = HeatmapTicker(
            ticker="MSFT",
            company_name="Microsoft Corp.",
            sector="Information Technology",
            industry_group="Software & Services",
            market_cap_weight=100.0,
            change_pct=-0.5,
            price=420.0,
            volume=2_000_000,
        )
        restored = HeatmapTicker.model_validate_json(ht.model_dump_json())
        assert restored == ht


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHeatmapEndpoint:
    """Validate GET /api/market/heatmap endpoint."""

    async def test_returns_heatmap_data(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify endpoint returns list of HeatmapTicker."""
        constituents = [_make_constituent("AAPL"), _make_constituent("MSFT")]
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
        mock_market_data.fetch_batch_daily_changes = AsyncMock(
            return_value=[_make_batch_quote("AAPL"), _make_batch_quote("MSFT")]
        )
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["ticker"] == "AAPL"
        assert data[1]["ticker"] == "MSFT"

    async def test_metadata_join_populates_fields(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify sector, company_name, market_cap_weight from metadata."""
        constituents = [_make_constituent("AAPL")]
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
        mock_market_data.fetch_batch_daily_changes = AsyncMock(
            return_value=[_make_batch_quote("AAPL")]
        )
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[_make_metadata("AAPL")])

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        assert item["company_name"] == "Apple Inc."
        assert item["sector"] == "Information Technology"
        assert item["industry_group"] == "Software & Services"
        assert item["market_cap_weight"] == pytest.approx(100.0)

    async def test_missing_metadata_uses_fallback(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify Unknown sector and weight=10 when metadata absent."""
        constituents = [_make_constituent("XYZ", sector="")]
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
        mock_market_data.fetch_batch_daily_changes = AsyncMock(
            return_value=[_make_batch_quote("XYZ")]
        )
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        assert item["sector"] == "Unknown"
        assert item["company_name"] == "XYZ"
        assert item["industry_group"] == "Unknown"
        assert item["market_cap_weight"] == pytest.approx(10.0)

    async def test_missing_quote_omits_ticker(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify tickers without BatchQuote are omitted from response."""
        constituents = [_make_constituent("AAPL"), _make_constituent("GOOG")]
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
        # Only AAPL has a quote — GOOG should be omitted
        mock_market_data.fetch_batch_daily_changes = AsyncMock(
            return_value=[_make_batch_quote("AAPL")]
        )
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    async def test_market_cap_weight_mapping(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify mega=100, large=50, mid=20, small=8, micro=3."""
        tiers_and_weights: list[tuple[str, MarketCapTier, float]] = [
            ("MEGA", MarketCapTier.MEGA, 100.0),
            ("LRG", MarketCapTier.LARGE, 50.0),
            ("MID", MarketCapTier.MID, 20.0),
            ("SML", MarketCapTier.SMALL, 8.0),
            ("MCR", MarketCapTier.MICRO, 3.0),
        ]
        constituents = [_make_constituent(t) for t, _, _ in tiers_and_weights]
        quotes = [_make_batch_quote(t) for t, _, _ in tiers_and_weights]
        metadata = [_make_metadata(t, market_cap_tier=tier) for t, tier, _ in tiers_and_weights]

        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
        mock_market_data.fetch_batch_daily_changes = AsyncMock(return_value=quotes)
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=metadata)

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5

        for item, (_, _, expected_weight) in zip(data, tiers_and_weights, strict=True):
            assert item["market_cap_weight"] == pytest.approx(expected_weight)

    async def test_empty_universe_returns_empty(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify empty universe returns empty list (200 OK, not 500)."""
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_all_tickers_fail_returns_empty(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify all tickers failing fetch returns empty list."""
        constituents = [_make_constituent("AAPL")]
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
        mock_market_data.fetch_batch_daily_changes = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_constituent_sector_fallback(
        self,
        client: AsyncClient,
        mock_universe: AsyncMock,
        mock_market_data: AsyncMock,
        mock_repo: AsyncMock,
    ) -> None:
        """Verify SP500Constituent.sector used when metadata has no sector."""
        constituents = [_make_constituent("AAPL", sector="Health Care")]
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
        mock_market_data.fetch_batch_daily_changes = AsyncMock(
            return_value=[_make_batch_quote("AAPL")]
        )
        # Metadata exists but sector is None
        meta = TickerMetadata(
            ticker="AAPL",
            sector=None,
            industry_group=None,
            market_cap_tier=MarketCapTier.MEGA,
            company_name="Apple Inc.",
            last_updated=datetime.now(UTC),
        )
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[meta])

        resp = await client.get("/api/market/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["sector"] == "Health Care"
        assert data[0]["market_cap_weight"] == pytest.approx(100.0)
