"""Tests for map_yfinance_to_metadata() in services/universe.py.

Verifies that TickerInfo -> TickerMetadata mapping correctly resolves
sector/industry strings to typed GICS enums, classifies market cap,
preserves raw strings, and logs warnings for unmapped values.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from options_arena.models.enums import (
    DividendSource,
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
)
from options_arena.models.market_data import TickerInfo
from options_arena.services.universe import map_yfinance_to_metadata


def _make_ticker_info(
    *,
    ticker: str = "AAPL",
    company_name: str = "Apple Inc.",
    sector: str = "Technology",
    industry: str = "Consumer Electronics",
    market_cap: int | None = 3_000_000_000_000,
    current_price: str = "186.50",
    fifty_two_week_high: str = "199.62",
    fifty_two_week_low: str = "164.08",
) -> TickerInfo:
    """Build a TickerInfo with sensible defaults for testing."""
    return TickerInfo(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        industry=industry,
        market_cap=market_cap,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal(current_price),
        fifty_two_week_high=Decimal(fifty_two_week_high),
        fifty_two_week_low=Decimal(fifty_two_week_low),
    )


class TestMapYfinanceToMetadata:
    """Tests for the map_yfinance_to_metadata standalone helper."""

    def test_maps_known_sector(self) -> None:
        """Verify known yfinance sector resolves to GICSSector."""
        info = _make_ticker_info(sector="Technology")
        meta = map_yfinance_to_metadata(info)
        assert meta.sector == GICSSector.INFORMATION_TECHNOLOGY

    def test_maps_known_industry(self) -> None:
        """Verify known yfinance industry resolves to GICSIndustryGroup."""
        info = _make_ticker_info(industry="Consumer Electronics")
        meta = map_yfinance_to_metadata(info)
        assert meta.industry_group == GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT

    def test_maps_market_cap_tier(self) -> None:
        """Verify market_cap is classified to MarketCapTier."""
        info = _make_ticker_info(market_cap=3_000_000_000_000)
        meta = map_yfinance_to_metadata(info)
        assert meta.market_cap_tier == MarketCapTier.MEGA

    def test_unmapped_sector_returns_none(self) -> None:
        """Verify unknown sector string returns None sector."""
        info = _make_ticker_info(sector="Alien Technology")
        meta = map_yfinance_to_metadata(info)
        assert meta.sector is None

    def test_unmapped_industry_returns_none(self) -> None:
        """Verify unknown industry string returns None industry_group."""
        info = _make_ticker_info(industry="Space Mining")
        meta = map_yfinance_to_metadata(info)
        assert meta.industry_group is None

    def test_unmapped_sector_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify unmapped sector logs WARNING."""
        info = _make_ticker_info(sector="Alien Technology")
        with caplog.at_level(logging.WARNING, logger="options_arena.services.universe"):
            map_yfinance_to_metadata(info)
        assert any("Unmapped yfinance sector" in msg for msg in caplog.messages)

    def test_unmapped_industry_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify unmapped industry logs WARNING."""
        info = _make_ticker_info(industry="Space Mining")
        with caplog.at_level(logging.WARNING, logger="options_arena.services.universe"):
            map_yfinance_to_metadata(info)
        assert any("Unmapped yfinance industry" in msg for msg in caplog.messages)

    def test_unknown_sector_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify 'Unknown' sector does not log warning."""
        info = _make_ticker_info(sector="Unknown")
        with caplog.at_level(logging.WARNING, logger="options_arena.services.universe"):
            map_yfinance_to_metadata(info)
        assert not any("Unmapped yfinance sector" in msg for msg in caplog.messages)
        meta = map_yfinance_to_metadata(info)
        assert meta.sector is None

    def test_preserves_raw_strings(self) -> None:
        """Verify raw_sector and raw_industry preserve original text."""
        info = _make_ticker_info(sector="Technology", industry="Consumer Electronics")
        meta = map_yfinance_to_metadata(info)
        assert meta.raw_sector == "Technology"
        assert meta.raw_industry == "Consumer Electronics"

    def test_last_updated_is_utc(self) -> None:
        """Verify last_updated is set to UTC datetime."""
        info = _make_ticker_info()
        before = datetime.now(UTC)
        meta = map_yfinance_to_metadata(info)
        after = datetime.now(UTC)

        assert meta.last_updated.tzinfo is not None
        assert meta.last_updated.utcoffset() == timedelta(0)
        assert before <= meta.last_updated <= after

    def test_none_market_cap(self) -> None:
        """Verify None market_cap results in None market_cap_tier."""
        info = _make_ticker_info(market_cap=None)
        meta = map_yfinance_to_metadata(info)
        assert meta.market_cap_tier is None

    def test_case_insensitive_alias_lookup(self) -> None:
        """Verify alias lookup is case-insensitive."""
        info = _make_ticker_info(sector="TECHNOLOGY", industry="CONSUMER ELECTRONICS")
        meta = map_yfinance_to_metadata(info)
        assert meta.sector == GICSSector.INFORMATION_TECHNOLOGY
        assert meta.industry_group == GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT
