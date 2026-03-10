"""Tests for _PHASE3_FIELDS including liquidity indicators."""

from __future__ import annotations

from options_arena.models.scan import IndicatorSignals
from options_arena.scan.phase_options import _PHASE3_FIELDS


class TestPhase3FieldsLiquidity:
    def test_chain_spread_pct_in_phase3_fields(self) -> None:
        """Verify chain_spread_pct is in _PHASE3_FIELDS."""
        assert "chain_spread_pct" in _PHASE3_FIELDS

    def test_chain_oi_depth_in_phase3_fields(self) -> None:
        """Verify chain_oi_depth is in _PHASE3_FIELDS."""
        assert "chain_oi_depth" in _PHASE3_FIELDS

    def test_phase3_fields_match_indicator_signals(self) -> None:
        """Verify all _PHASE3_FIELDS are valid IndicatorSignals field names."""
        valid_fields = set(IndicatorSignals.model_fields.keys())
        for field_name in _PHASE3_FIELDS:
            assert field_name in valid_fields, f"{field_name!r} not in IndicatorSignals"
