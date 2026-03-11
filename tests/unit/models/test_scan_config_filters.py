"""Tests for pre-scan filter fields that moved to filter models (#225).

Originally tested on ScanConfig directly; now validates the same behavior on
UniverseFilters, OptionsFilters, and ScoringFilters.
"""

from __future__ import annotations

import math

import pytest

from options_arena.models.config import ScanConfig
from options_arena.models.enums import MarketCapTier, SignalDirection
from options_arena.models.filters import (
    OptionsFilters,
    ScoringFilters,
    UniverseFilters,
)


class TestScanConfigFilters:
    """Tests for the pre-scan filter fields on UniverseFilters, ScoringFilters, OptionsFilters."""

    def test_market_cap_tiers_default_empty(self) -> None:
        """Verify market_cap_tiers defaults to empty list."""
        config = UniverseFilters()
        assert config.market_cap_tiers == []

    def test_market_cap_tiers_accepts_enum(self) -> None:
        """Verify market_cap_tiers accepts MarketCapTier enums."""
        config = UniverseFilters(market_cap_tiers=[MarketCapTier.LARGE, MarketCapTier.MEGA])
        assert MarketCapTier.LARGE in config.market_cap_tiers
        assert MarketCapTier.MEGA in config.market_cap_tiers

    def test_market_cap_tiers_accepts_strings(self) -> None:
        """Verify market_cap_tiers accepts lowercase strings."""
        config = UniverseFilters(market_cap_tiers=["large", "mega"])
        assert MarketCapTier.LARGE in config.market_cap_tiers
        assert MarketCapTier.MEGA in config.market_cap_tiers

    def test_market_cap_tiers_deduplication(self) -> None:
        """Verify duplicate tiers are removed via dict.fromkeys."""
        config = UniverseFilters(market_cap_tiers=["large", "large", "mega"])
        assert len(config.market_cap_tiers) == 2

    def test_exclude_near_earnings_days_none_default(self) -> None:
        """Verify exclude_near_earnings_days defaults to None."""
        config = OptionsFilters()
        assert config.exclude_near_earnings_days is None

    def test_exclude_near_earnings_days_accepts_int(self) -> None:
        """Verify exclude_near_earnings_days accepts integer values."""
        config = OptionsFilters(exclude_near_earnings_days=7)
        assert config.exclude_near_earnings_days == 7

    def test_direction_filter_none_default(self) -> None:
        """Verify direction_filter defaults to None."""
        config = ScoringFilters()
        assert config.direction_filter is None

    def test_direction_filter_accepts_enum(self) -> None:
        """Verify direction_filter accepts SignalDirection enum."""
        config = ScoringFilters(direction_filter=SignalDirection.BULLISH)
        assert config.direction_filter == SignalDirection.BULLISH

    def test_direction_filter_accepts_string(self) -> None:
        """Verify direction_filter accepts string value."""
        config = ScoringFilters(direction_filter="bearish")
        assert config.direction_filter == SignalDirection.BEARISH

    def test_min_iv_rank_none_default(self) -> None:
        """Verify min_iv_rank defaults to None."""
        config = OptionsFilters()
        assert config.min_iv_rank is None

    def test_min_iv_rank_accepts_valid_float(self) -> None:
        """Verify min_iv_rank accepts values in [0, 100]."""
        config = OptionsFilters(min_iv_rank=50.0)
        assert config.min_iv_rank == 50.0

    def test_min_iv_rank_rejects_out_of_range(self) -> None:
        """Verify min_iv_rank rejects values outside [0, 100]."""
        with pytest.raises(ValueError, match="min_iv_rank"):
            OptionsFilters(min_iv_rank=101.0)

    def test_min_iv_rank_rejects_negative(self) -> None:
        """Verify min_iv_rank rejects negative values."""
        with pytest.raises(ValueError, match="min_iv_rank"):
            OptionsFilters(min_iv_rank=-1.0)

    def test_min_iv_rank_rejects_nan(self) -> None:
        """Verify min_iv_rank rejects NaN."""
        with pytest.raises(ValueError, match="min_iv_rank"):
            OptionsFilters(min_iv_rank=float("nan"))

    def test_min_iv_rank_rejects_inf(self) -> None:
        """Verify min_iv_rank rejects Infinity."""
        with pytest.raises(ValueError, match="min_iv_rank"):
            OptionsFilters(min_iv_rank=math.inf)

    def test_all_filters_backward_compatible(self) -> None:
        """Verify default ScanConfig has no filters active via ScanFilterSpec."""
        config = ScanConfig()
        assert config.filters.universe.market_cap_tiers == []
        assert config.filters.options.exclude_near_earnings_days is None
        assert config.filters.scoring.direction_filter is None
        assert config.filters.options.min_iv_rank is None
        # Existing fields still have their defaults
        assert config.filters.options.top_n == 50
        assert config.filters.universe.sectors == []

    def test_min_iv_rank_boundary_zero(self) -> None:
        """Verify min_iv_rank=0 is valid (effectively no filter)."""
        config = OptionsFilters(min_iv_rank=0.0)
        assert config.min_iv_rank == 0.0

    def test_min_iv_rank_boundary_hundred(self) -> None:
        """Verify min_iv_rank=100 is valid (strictest filter)."""
        config = OptionsFilters(min_iv_rank=100.0)
        assert config.min_iv_rank == 100.0
