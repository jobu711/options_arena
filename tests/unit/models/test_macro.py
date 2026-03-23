"""Tests for MacroContext and FredSeriesConfig models.

Covers: construction, validation, NaN/Inf rejection, completeness_ratio,
fallback classmethod, JSON roundtrip, frozen immutability, and edge cases.
"""

import pytest
from pydantic import ValidationError

from options_arena.models.enums import FredTransform
from options_arena.models.macro import (
    FredSeriesConfig,
    MacroContext,
)

# ---------------------------------------------------------------------------
# FredSeriesConfig
# ---------------------------------------------------------------------------


class TestFredSeriesConfig:
    """Tests for the FredSeriesConfig NamedTuple."""

    def test_construction(self) -> None:
        """FredSeriesConfig stores all four fields with FredTransform enum."""
        cfg = FredSeriesConfig(
            series_id="DGS10",
            display_name="10-Year Treasury",
            ttl_hours=24,
            transform=FredTransform.PCT_TO_DECIMAL,
        )
        assert cfg.series_id == "DGS10"
        assert cfg.display_name == "10-Year Treasury"
        assert cfg.ttl_hours == 24
        assert cfg.transform == FredTransform.PCT_TO_DECIMAL

    def test_is_namedtuple(self) -> None:
        """FredSeriesConfig is a NamedTuple (immutable, iterable)."""
        cfg = FredSeriesConfig("DGS2", "2-Year Treasury", 24, FredTransform.PCT_TO_DECIMAL)
        assert isinstance(cfg, tuple)
        assert len(cfg) == 4

    def test_field_access_by_index(self) -> None:
        """NamedTuple fields are accessible by index."""
        cfg = FredSeriesConfig("VIXCLS", "VIX", 24, FredTransform.PASSTHROUGH)
        assert cfg[0] == "VIXCLS"
        assert cfg[3] == FredTransform.PASSTHROUGH

    def test_yoy_pct_change_transform(self) -> None:
        """YOY_PCT_CHANGE transform for CPI and INDPRO."""
        cfg = FredSeriesConfig("CPIAUCSL", "CPI YoY", 168, FredTransform.YOY_PCT_CHANGE)
        assert cfg.transform == FredTransform.YOY_PCT_CHANGE
        assert cfg.ttl_hours == 168


# ---------------------------------------------------------------------------
# MacroContext — construction
# ---------------------------------------------------------------------------


class TestMacroContextConstruction:
    """Tests for MacroContext model construction."""

    @pytest.mark.critical
    def test_all_none_default(self) -> None:
        """MacroContext() with no args creates all-None instance."""
        ctx = MacroContext()
        assert ctx.treasury_10y is None
        assert ctx.treasury_2y is None
        assert ctx.yield_spread_10y2y is None
        assert ctx.fed_funds_rate is None
        assert ctx.vix is None
        assert ctx.cpi_yoy is None
        assert ctx.industrial_production_yoy is None
        assert ctx.unemployment_rate is None

    def test_fully_populated(self) -> None:
        """MacroContext with all fields populated."""
        ctx = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.042,
            yield_spread_10y2y=0.003,
            fed_funds_rate=0.0525,
            vix=18.5,
            cpi_yoy=3.2,
            industrial_production_yoy=1.5,
            unemployment_rate=0.035,
        )
        assert ctx.treasury_10y == pytest.approx(0.045, rel=1e-6)
        assert ctx.treasury_2y == pytest.approx(0.042, rel=1e-6)
        assert ctx.yield_spread_10y2y == pytest.approx(0.003, rel=1e-6)
        assert ctx.fed_funds_rate == pytest.approx(0.0525, rel=1e-6)
        assert ctx.vix == pytest.approx(18.5, rel=1e-6)
        assert ctx.cpi_yoy == pytest.approx(3.2, rel=1e-6)
        assert ctx.industrial_production_yoy == pytest.approx(1.5, rel=1e-6)
        assert ctx.unemployment_rate == pytest.approx(0.035, rel=1e-6)

    def test_partial_population(self) -> None:
        """MacroContext with only some fields set."""
        ctx = MacroContext(treasury_10y=0.045, vix=20.0)
        assert ctx.treasury_10y == pytest.approx(0.045, rel=1e-6)
        assert ctx.treasury_2y is None
        assert ctx.vix == pytest.approx(20.0, rel=1e-6)
        assert ctx.unemployment_rate is None

    def test_negative_yield_spread_valid(self) -> None:
        """Inverted yield curve (negative spread) is valid."""
        ctx = MacroContext(yield_spread_10y2y=-0.005)
        assert ctx.yield_spread_10y2y == pytest.approx(-0.005, rel=1e-6)

    def test_zero_values_valid(self) -> None:
        """Zero values are valid (not treated as None)."""
        ctx = MacroContext(treasury_10y=0.0, vix=0.0)
        assert ctx.treasury_10y == pytest.approx(0.0, abs=1e-9)
        assert ctx.vix == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# MacroContext — validation
# ---------------------------------------------------------------------------


class TestMacroContextValidation:
    """Tests for MacroContext field validation (NaN/Inf rejection)."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "treasury_10y",
            "treasury_2y",
            "yield_spread_10y2y",
            "fed_funds_rate",
            "vix",
            "cpi_yoy",
            "industrial_production_yoy",
            "unemployment_rate",
        ],
    )
    def test_nan_rejected(self, field_name: str) -> None:
        """NaN is rejected on all numeric fields."""
        with pytest.raises(ValidationError, match="finite"):
            MacroContext(**{field_name: float("nan")})

    @pytest.mark.parametrize(
        "field_name",
        [
            "treasury_10y",
            "treasury_2y",
            "yield_spread_10y2y",
            "fed_funds_rate",
            "vix",
            "cpi_yoy",
            "industrial_production_yoy",
            "unemployment_rate",
        ],
    )
    def test_positive_inf_rejected(self, field_name: str) -> None:
        """Positive infinity is rejected on all numeric fields."""
        with pytest.raises(ValidationError, match="finite"):
            MacroContext(**{field_name: float("inf")})

    @pytest.mark.parametrize(
        "field_name",
        [
            "treasury_10y",
            "treasury_2y",
            "yield_spread_10y2y",
            "fed_funds_rate",
            "vix",
            "cpi_yoy",
            "industrial_production_yoy",
            "unemployment_rate",
        ],
    )
    def test_negative_inf_rejected(self, field_name: str) -> None:
        """Negative infinity is rejected on all numeric fields."""
        with pytest.raises(ValidationError, match="finite"):
            MacroContext(**{field_name: float("-inf")})

    def test_none_passes_validation(self) -> None:
        """None values pass validation (they are valid for optional fields)."""
        ctx = MacroContext(treasury_10y=None, vix=None)
        assert ctx.treasury_10y is None
        assert ctx.vix is None


# ---------------------------------------------------------------------------
# MacroContext — frozen
# ---------------------------------------------------------------------------


class TestMacroContextFrozen:
    """Tests for MacroContext immutability."""

    def test_frozen_rejects_attribute_reassignment(self) -> None:
        """Frozen model rejects attribute reassignment."""
        ctx = MacroContext(treasury_10y=0.045)
        with pytest.raises(ValidationError):
            ctx.treasury_10y = 0.050  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MacroContext — completeness_ratio
# ---------------------------------------------------------------------------


class TestMacroContextCompleteness:
    """Tests for MacroContext.completeness_ratio()."""

    def test_all_none_returns_zero(self) -> None:
        """All-None instance returns 0.0 completeness."""
        ctx = MacroContext()
        assert ctx.completeness_ratio() == pytest.approx(0.0, abs=1e-9)

    def test_fully_populated_returns_one(self) -> None:
        """All fields populated returns 1.0 completeness."""
        ctx = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.042,
            yield_spread_10y2y=0.003,
            fed_funds_rate=0.0525,
            vix=18.5,
            cpi_yoy=3.2,
            industrial_production_yoy=1.5,
            unemployment_rate=0.035,
        )
        assert ctx.completeness_ratio() == pytest.approx(1.0, abs=1e-9)

    def test_half_populated(self) -> None:
        """4 of 8 fields populated returns 0.5."""
        ctx = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.042,
            vix=18.5,
            unemployment_rate=0.035,
        )
        assert ctx.completeness_ratio() == pytest.approx(0.5, abs=1e-9)

    def test_single_field_populated(self) -> None:
        """1 of 8 fields populated returns 0.125."""
        ctx = MacroContext(vix=20.0)
        assert ctx.completeness_ratio() == pytest.approx(0.125, abs=1e-9)

    def test_zero_values_count_as_populated(self) -> None:
        """Zero values (0.0) count as populated, not None."""
        ctx = MacroContext(treasury_10y=0.0, vix=0.0)
        assert ctx.completeness_ratio() == pytest.approx(0.25, abs=1e-9)


# ---------------------------------------------------------------------------
# MacroContext — fallback
# ---------------------------------------------------------------------------


class TestMacroContextFallback:
    """Tests for MacroContext.fallback() classmethod."""

    def test_fallback_returns_all_none(self) -> None:
        """fallback() returns an all-None MacroContext instance."""
        ctx = MacroContext.fallback()
        assert isinstance(ctx, MacroContext)
        assert ctx.completeness_ratio() == pytest.approx(0.0, abs=1e-9)
        assert ctx.treasury_10y is None
        assert ctx.vix is None

    def test_fallback_is_frozen(self) -> None:
        """Fallback instance is frozen like any other MacroContext."""
        ctx = MacroContext.fallback()
        with pytest.raises(ValidationError):
            ctx.treasury_10y = 0.045  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MacroContext — JSON roundtrip
# ---------------------------------------------------------------------------


class TestMacroContextSerialization:
    """Tests for MacroContext JSON serialization roundtrip."""

    def test_json_roundtrip_fully_populated(self) -> None:
        """Fully populated MacroContext survives JSON roundtrip."""
        original = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.042,
            yield_spread_10y2y=0.003,
            fed_funds_rate=0.0525,
            vix=18.5,
            cpi_yoy=3.2,
            industrial_production_yoy=1.5,
            unemployment_rate=0.035,
        )
        json_str = original.model_dump_json()
        restored = MacroContext.model_validate_json(json_str)
        assert restored == original

    def test_json_roundtrip_all_none(self) -> None:
        """All-None MacroContext survives JSON roundtrip."""
        original = MacroContext()
        json_str = original.model_dump_json()
        restored = MacroContext.model_validate_json(json_str)
        assert restored == original

    def test_json_roundtrip_partial(self) -> None:
        """Partially populated MacroContext survives JSON roundtrip."""
        original = MacroContext(treasury_10y=0.045, vix=18.5)
        json_str = original.model_dump_json()
        restored = MacroContext.model_validate_json(json_str)
        assert restored == original

    def test_model_dump_contains_all_fields(self) -> None:
        """model_dump() includes all 8 fields even when None."""
        ctx = MacroContext()
        dump = ctx.model_dump()
        expected_fields = {
            "treasury_10y",
            "treasury_2y",
            "yield_spread_10y2y",
            "fed_funds_rate",
            "vix",
            "cpi_yoy",
            "industrial_production_yoy",
            "unemployment_rate",
        }
        assert set(dump.keys()) == expected_fields


# ---------------------------------------------------------------------------
# Field count verification
# ---------------------------------------------------------------------------


class TestMacroContextFieldCount:
    """Verify MacroContext has exactly 8 fields."""

    def test_field_count(self) -> None:
        """MacroContext has exactly 8 fields."""
        fields = MacroContext.model_fields
        assert len(fields) == 8

    def test_field_names(self) -> None:
        """MacroContext field names match expected set."""
        expected = {
            "treasury_10y",
            "treasury_2y",
            "yield_spread_10y2y",
            "fed_funds_rate",
            "vix",
            "cpi_yoy",
            "industrial_production_yoy",
            "unemployment_rate",
        }
        assert set(MacroContext.model_fields.keys()) == expected
