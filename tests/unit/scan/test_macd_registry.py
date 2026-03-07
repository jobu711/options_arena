"""Tests for MACD registration in INDICATOR_REGISTRY.

Verifies that the macd() function is registered in the scan pipeline's
indicator registry with the correct field name, function reference, and
input shape.
"""

from __future__ import annotations

from options_arena.indicators import macd
from options_arena.scan.indicators import INDICATOR_REGISTRY, InputShape


class TestMacdRegistry:
    """MACD indicator is properly registered in INDICATOR_REGISTRY."""

    def test_registry_contains_macd(self) -> None:
        """Verify INDICATOR_REGISTRY contains an entry with field_name='macd'."""
        field_names = {spec.field_name for spec in INDICATOR_REGISTRY}
        assert "macd" in field_names

    def test_registry_count_is_15(self) -> None:
        """Verify registry has exactly 15 entries (was 14 before MACD)."""
        assert len(INDICATOR_REGISTRY) == 15

    def test_macd_spec_input_shape_is_close(self) -> None:
        """Verify MACD uses InputShape.CLOSE (takes close price series)."""
        spec = next(s for s in INDICATOR_REGISTRY if s.field_name == "macd")
        assert spec.input_shape is InputShape.CLOSE

    def test_macd_spec_function_is_macd(self) -> None:
        """Verify the registered function is the macd function from indicators."""
        spec = next(s for s in INDICATOR_REGISTRY if s.field_name == "macd")
        assert spec.func is macd

    def test_macd_appears_in_trend_section(self) -> None:
        """Verify MACD appears after supertrend in the registry order.

        The registry is ordered by category. MACD should be in the Trend
        section, after the existing supertrend entry.
        """
        field_names = [spec.field_name for spec in INDICATOR_REGISTRY]
        supertrend_idx = field_names.index("supertrend")
        macd_idx = field_names.index("macd")
        assert macd_idx == supertrend_idx + 1, (
            f"macd should appear directly after supertrend, "
            f"but supertrend is at {supertrend_idx} and macd at {macd_idx}"
        )
