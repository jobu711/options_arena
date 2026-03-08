"""Tests for liquidity indicator scoring configuration."""

from __future__ import annotations

import pytest

from options_arena.scoring.composite import INDICATOR_WEIGHTS
from options_arena.scoring.dimensional import FAMILY_INDICATOR_MAP
from options_arena.scoring.normalization import DOMAIN_BOUNDS, INVERTED_INDICATORS


class TestLiquidityWeightConfig:
    def test_weights_has_21_entries(self) -> None:
        """Verify INDICATOR_WEIGHTS now has 21 entries."""
        assert len(INDICATOR_WEIGHTS) == 21

    def test_weights_sum_to_one(self) -> None:
        """Verify weight sum = 1.0 within 1e-9."""
        total = sum(w for w, _ in INDICATOR_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_chain_spread_pct_weight(self) -> None:
        """Verify chain_spread_pct has correct weight and category."""
        assert "chain_spread_pct" in INDICATOR_WEIGHTS
        w, cat = INDICATOR_WEIGHTS["chain_spread_pct"]
        assert w == pytest.approx(0.04)
        assert cat == "liquidity"

    def test_chain_oi_depth_weight(self) -> None:
        """Verify chain_oi_depth has correct weight and category."""
        assert "chain_oi_depth" in INDICATOR_WEIGHTS
        w, cat = INDICATOR_WEIGHTS["chain_oi_depth"]
        assert w == pytest.approx(0.02)
        assert cat == "liquidity"

    def test_chain_spread_pct_inverted(self) -> None:
        """Verify chain_spread_pct is in INVERTED_INDICATORS."""
        assert "chain_spread_pct" in INVERTED_INDICATORS

    def test_chain_oi_depth_not_inverted(self) -> None:
        """Verify chain_oi_depth is NOT in INVERTED_INDICATORS."""
        assert "chain_oi_depth" not in INVERTED_INDICATORS

    def test_domain_bounds_chain_spread_pct(self) -> None:
        """Verify domain bounds (0.0, 30.0) for chain_spread_pct."""
        assert "chain_spread_pct" in DOMAIN_BOUNDS
        lo, hi = DOMAIN_BOUNDS["chain_spread_pct"]
        assert lo == 0.0
        assert hi == 30.0

    def test_domain_bounds_chain_oi_depth(self) -> None:
        """Verify domain bounds (0.0, 6.0) for chain_oi_depth."""
        assert "chain_oi_depth" in DOMAIN_BOUNDS
        lo, hi = DOMAIN_BOUNDS["chain_oi_depth"]
        assert lo == 0.0
        assert hi == 6.0

    def test_microstructure_family_contains_new_fields(self) -> None:
        """Verify both new fields in microstructure family."""
        micro = FAMILY_INDICATOR_MAP["microstructure"]
        assert "chain_spread_pct" in micro
        assert "chain_oi_depth" in micro
