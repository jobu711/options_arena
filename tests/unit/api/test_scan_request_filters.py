"""Tests for ScanRequest pre-scan filter fields (#225)."""

from __future__ import annotations

from options_arena.api.schemas import ScanRequest
from options_arena.models import MarketCapTier, SignalDirection


class TestScanRequestFilters:
    """Tests for direction_filter and min_iv_rank on ScanRequest."""

    def test_direction_filter_default_none(self) -> None:
        """Verify direction_filter defaults to None."""
        req = ScanRequest()
        assert req.direction_filter is None

    def test_direction_filter_accepts_string(self) -> None:
        """Verify direction_filter accepts valid string values."""
        req = ScanRequest(direction_filter="bullish")
        assert req.direction_filter == SignalDirection.BULLISH

    def test_direction_filter_accepts_enum(self) -> None:
        """Verify direction_filter accepts SignalDirection enum."""
        req = ScanRequest(direction_filter=SignalDirection.BEARISH)
        assert req.direction_filter == SignalDirection.BEARISH

    def test_min_iv_rank_default_none(self) -> None:
        """Verify min_iv_rank defaults to None."""
        req = ScanRequest()
        assert req.min_iv_rank is None

    def test_min_iv_rank_accepts_float(self) -> None:
        """Verify min_iv_rank accepts valid float."""
        req = ScanRequest(min_iv_rank=50.0)
        assert req.min_iv_rank == 50.0

    def test_all_prescan_filters_default_backward_compatible(self) -> None:
        """Verify ScanRequest defaults are fully backward compatible."""
        req = ScanRequest()
        assert req.market_cap_tiers == []
        assert req.exclude_near_earnings_days is None
        assert req.direction_filter is None
        assert req.min_iv_rank is None
        assert req.sectors == []

    def test_combined_prescan_filters(self) -> None:
        """Verify all pre-scan filter fields can be set together."""
        req = ScanRequest(
            market_cap_tiers=["large", "mega"],
            exclude_near_earnings_days=7,
            direction_filter="bullish",
            min_iv_rank=30.0,
        )
        assert MarketCapTier.LARGE in req.market_cap_tiers
        assert MarketCapTier.MEGA in req.market_cap_tiers
        assert req.exclude_near_earnings_days == 7
        assert req.direction_filter == SignalDirection.BULLISH
        assert req.min_iv_rank == 30.0
