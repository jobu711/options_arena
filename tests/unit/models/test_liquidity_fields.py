"""Tests for chain_spread_pct and chain_oi_depth fields on IndicatorSignals."""

from __future__ import annotations

import pytest

from options_arena.models.scan import IndicatorSignals


class TestLiquidityFields:
    """Verify new liquidity indicator fields on IndicatorSignals."""

    def test_default_none(self) -> None:
        """Verify new fields default to None when not provided."""
        signals = IndicatorSignals()
        assert signals.chain_spread_pct is None
        assert signals.chain_oi_depth is None

    def test_explicit_values(self) -> None:
        """Verify new fields accept valid float values."""
        signals = IndicatorSignals(chain_spread_pct=2.5, chain_oi_depth=4.3)
        assert signals.chain_spread_pct == 2.5
        assert signals.chain_oi_depth == 4.3

    def test_json_roundtrip_with_fields(self) -> None:
        """Verify JSON serialization/deserialization preserves values."""
        signals = IndicatorSignals(chain_spread_pct=5.0, chain_oi_depth=3.7)
        restored = IndicatorSignals.model_validate_json(signals.model_dump_json())
        assert restored.chain_spread_pct == pytest.approx(5.0)
        assert restored.chain_oi_depth == pytest.approx(3.7)

    def test_json_roundtrip_without_fields(self) -> None:
        """Verify backward compat: JSON without new fields produces None defaults."""
        # Simulate pre-liquidity JSON (only has rsi)
        json_str = '{"rsi": 55.0}'
        signals = IndicatorSignals.model_validate_json(json_str)
        assert signals.rsi == pytest.approx(55.0)
        assert signals.chain_spread_pct is None
        assert signals.chain_oi_depth is None

    def test_nan_sanitized_to_none(self) -> None:
        """Verify NaN in new fields is sanitized to None by model_validator."""
        signals = IndicatorSignals(
            chain_spread_pct=float("nan"),
            chain_oi_depth=float("nan"),
        )
        assert signals.chain_spread_pct is None
        assert signals.chain_oi_depth is None

    def test_inf_sanitized_to_none(self) -> None:
        """Verify Inf in new fields is sanitized to None by model_validator."""
        signals = IndicatorSignals(
            chain_spread_pct=float("inf"),
            chain_oi_depth=float("-inf"),
        )
        assert signals.chain_spread_pct is None
        assert signals.chain_oi_depth is None

    def test_zero_values_preserved(self) -> None:
        """Verify zero is a valid value (not sanitized)."""
        signals = IndicatorSignals(chain_spread_pct=0.0, chain_oi_depth=0.0)
        assert signals.chain_spread_pct == 0.0
        assert signals.chain_oi_depth == 0.0

    def test_boundary_values(self) -> None:
        """Verify domain boundary values are accepted."""
        signals = IndicatorSignals(chain_spread_pct=30.0, chain_oi_depth=6.0)
        assert signals.chain_spread_pct == 30.0
        assert signals.chain_oi_depth == 6.0
