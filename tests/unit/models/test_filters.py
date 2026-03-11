"""Tests for filter models — UniverseFilters, ScoringFilters, OptionsFilters, ScanFilterSpec.

Covers construction defaults, validation, cross-field constraints, normalization,
frozen immutability, and JSON round-trip serialization.
"""

import pytest
from pydantic import ValidationError

from options_arena.models.config import ScanConfig
from options_arena.models.enums import (
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
    ScanPreset,
    SignalDirection,
)
from options_arena.models.filters import (
    OptionsFilters,
    ScanFilterSpec,
    ScoringFilters,
    UniverseFilters,
)

# ---------------------------------------------------------------------------
# TestUniverseFilters
# ---------------------------------------------------------------------------


class TestUniverseFilters:
    """Tests for UniverseFilters (Phase 1 scan pipeline filters)."""

    def test_defaults_match_current_scan_config(self) -> None:
        """Verify UniverseFilters defaults align with ScanConfig.filters.universe defaults."""
        uf = UniverseFilters()
        sc = ScanConfig()
        assert uf.preset == ScanPreset.SP500
        assert uf.sectors == sc.filters.universe.sectors
        assert uf.industry_groups == sc.filters.universe.industry_groups
        assert uf.custom_tickers == sc.filters.universe.custom_tickers
        assert uf.market_cap_tiers == sc.filters.universe.market_cap_tiers
        assert uf.ohlcv_min_bars == sc.filters.universe.ohlcv_min_bars
        assert uf.min_price == sc.filters.universe.min_price

    def test_frozen_rejects_mutation(self) -> None:
        """Frozen model must reject attribute reassignment."""
        uf = UniverseFilters()
        with pytest.raises(ValidationError):
            uf.min_price = 20.0  # type: ignore[misc]

    def test_sectors_normalization(self) -> None:
        """Sector aliases should resolve and deduplicate."""
        uf = UniverseFilters(sectors=["tech", "Technology", "Information Technology"])
        assert len(uf.sectors) == 1
        assert uf.sectors[0] == GICSSector.INFORMATION_TECHNOLOGY

    def test_industry_groups_normalization(self) -> None:
        """Industry group aliases should resolve and deduplicate."""
        uf = UniverseFilters(industry_groups=["semis", "Semiconductors & Semiconductor Equipment"])
        assert len(uf.industry_groups) == 1
        assert uf.industry_groups[0] == GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT

    def test_custom_tickers_uppercase_strip_dedup(self) -> None:
        """Custom tickers should be uppercased, stripped, and deduplicated."""
        uf = UniverseFilters(custom_tickers=["aapl", " AAPL ", "MSFT", "msft"])
        assert uf.custom_tickers == ["AAPL", "MSFT"]

    def test_custom_tickers_rejects_invalid_format(self) -> None:
        """Invalid ticker format should raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            UniverseFilters(custom_tickers=["AAPL", "BAD TICKER!"])

    def test_custom_tickers_rejects_over_200(self) -> None:
        """More than 200 unique tickers should raise ValidationError."""
        tickers = [f"T{i:04d}" for i in range(201)]
        with pytest.raises(ValidationError, match="exceeds 200"):
            UniverseFilters(custom_tickers=tickers)

    def test_market_cap_tiers_dedup(self) -> None:
        """Market cap tiers should be deduplicated."""
        uf = UniverseFilters(market_cap_tiers=["mega", "mega", "large"])
        assert uf.market_cap_tiers == [MarketCapTier.MEGA, MarketCapTier.LARGE]

    def test_min_price_rejects_nan(self) -> None:
        """NaN min_price should be rejected by the all-finite model validator."""
        with pytest.raises(ValidationError, match="finite"):
            UniverseFilters(min_price=float("nan"))

    def test_min_price_rejects_negative(self) -> None:
        """Negative min_price should be rejected."""
        with pytest.raises(ValidationError, match=r">=\s*0"):
            UniverseFilters(min_price=-1.0)

    def test_max_price_rejects_inf(self) -> None:
        """Inf max_price should be rejected."""
        with pytest.raises(ValidationError, match="finite"):
            UniverseFilters(max_price=float("inf"))

    def test_min_price_exceeds_max_price(self) -> None:
        """min_price > max_price should be rejected by cross-field validator."""
        with pytest.raises(ValidationError, match="must not exceed"):
            UniverseFilters(min_price=100.0, max_price=50.0)

    def test_ohlcv_min_bars_rejects_below_5(self) -> None:
        """ohlcv_min_bars below 5 should be rejected."""
        with pytest.raises(ValidationError, match=r">=\s*5"):
            UniverseFilters(ohlcv_min_bars=4)

    def test_json_roundtrip(self) -> None:
        """JSON serialization roundtrip must preserve all fields."""
        uf = UniverseFilters(
            preset=ScanPreset.NASDAQ100,
            sectors=[GICSSector.ENERGY],
            custom_tickers=["AAPL", "MSFT"],
            min_price=5.0,
            max_price=500.0,
        )
        restored = UniverseFilters.model_validate_json(uf.model_dump_json())
        assert restored == uf


# ---------------------------------------------------------------------------
# TestScoringFilters
# ---------------------------------------------------------------------------


class TestScoringFilters:
    """Tests for ScoringFilters (post-Phase 2 scoring filters)."""

    def test_defaults(self) -> None:
        """Default construction should succeed with expected values."""
        sf = ScoringFilters()
        assert sf.direction_filter is None
        assert sf.min_score == 0.0
        assert sf.min_direction_confidence == 0.0

    def test_min_score_rejects_below_zero(self) -> None:
        """min_score below 0 should be rejected."""
        with pytest.raises(ValidationError):
            ScoringFilters(min_score=-1.0)

    def test_min_score_rejects_above_100(self) -> None:
        """min_score above 100 should be rejected."""
        with pytest.raises(ValidationError):
            ScoringFilters(min_score=101.0)

    def test_min_score_rejects_nan(self) -> None:
        """NaN min_score should be rejected."""
        with pytest.raises(ValidationError, match="finite"):
            ScoringFilters(min_score=float("nan"))

    def test_min_direction_confidence_rejects_below_zero(self) -> None:
        """min_direction_confidence below 0 should be rejected."""
        with pytest.raises(ValidationError):
            ScoringFilters(min_direction_confidence=-0.1)

    def test_min_direction_confidence_rejects_above_one(self) -> None:
        """min_direction_confidence above 1 should be rejected."""
        with pytest.raises(ValidationError):
            ScoringFilters(min_direction_confidence=1.1)

    def test_direction_filter_accepts_all_directions(self) -> None:
        """All SignalDirection values should be accepted."""
        for direction in SignalDirection:
            sf = ScoringFilters(direction_filter=direction)
            assert sf.direction_filter == direction

    def test_frozen_rejects_mutation(self) -> None:
        """Frozen model must reject attribute reassignment."""
        sf = ScoringFilters()
        with pytest.raises(ValidationError):
            sf.min_score = 50.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestOptionsFilters
# ---------------------------------------------------------------------------


class TestOptionsFilters:
    """Tests for OptionsFilters (Phase 3 option chain filters)."""

    def test_defaults_match_current_pricing_config(self) -> None:
        """Verify OptionsFilters defaults match PricingConfig and ScanConfig defaults."""
        of = OptionsFilters()
        assert of.top_n == 50
        assert of.min_dollar_volume == 10_000_000.0
        assert of.min_dte == 30
        assert of.max_dte == 365
        assert of.min_oi == 100
        assert of.min_volume == 1
        assert of.max_spread_pct == pytest.approx(0.30)
        assert of.delta_primary_min == 0.20
        assert of.delta_primary_max == 0.50
        assert of.delta_fallback_min == 0.10
        assert of.delta_fallback_max == 0.80

    def test_min_dte_exceeds_max_dte(self) -> None:
        """min_dte > max_dte should be rejected by cross-field validator."""
        with pytest.raises(ValidationError, match="must not exceed"):
            OptionsFilters(min_dte=100, max_dte=30)

    def test_delta_primary_outside_fallback(self) -> None:
        """Primary delta range must be within fallback range."""
        # delta_primary_min < delta_fallback_min
        with pytest.raises(ValidationError, match="fallback_min"):
            OptionsFilters(delta_primary_min=0.05, delta_fallback_min=0.10)
        # delta_primary_max > delta_fallback_max
        with pytest.raises(ValidationError, match="fallback_max"):
            OptionsFilters(delta_primary_max=0.90, delta_fallback_max=0.80)

    def test_delta_primary_min_exceeds_max(self) -> None:
        """delta_primary_min > delta_primary_max should be rejected."""
        with pytest.raises(ValidationError, match="primary_min.*primary_max"):
            OptionsFilters(delta_primary_min=0.60, delta_primary_max=0.40)

    def test_top_n_rejects_zero(self) -> None:
        """top_n of 0 should be rejected."""
        with pytest.raises(ValidationError, match=r">=\s*1"):
            OptionsFilters(top_n=0)

    def test_min_iv_rank_rejects_below_zero(self) -> None:
        """min_iv_rank below 0 should be rejected."""
        with pytest.raises(ValidationError):
            OptionsFilters(min_iv_rank=-1.0)

    def test_min_iv_rank_rejects_above_100(self) -> None:
        """min_iv_rank above 100 should be rejected."""
        with pytest.raises(ValidationError):
            OptionsFilters(min_iv_rank=101.0)

    def test_max_spread_pct_rejects_nan(self) -> None:
        """NaN max_spread_pct should be rejected."""
        with pytest.raises(ValidationError, match="finite"):
            OptionsFilters(max_spread_pct=float("nan"))

    def test_all_finite_validator(self) -> None:
        """All float fields must be finite — inject Inf via a field."""
        with pytest.raises(ValidationError, match="finite"):
            OptionsFilters(min_dollar_volume=float("inf"))

    def test_frozen_rejects_mutation(self) -> None:
        """Frozen model must reject attribute reassignment."""
        of = OptionsFilters()
        with pytest.raises(ValidationError):
            of.top_n = 100  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        """JSON serialization roundtrip must preserve all fields."""
        of = OptionsFilters(
            top_n=25,
            min_dte=7,
            max_dte=90,
            min_iv_rank=30.0,
            exclude_near_earnings_days=7,
        )
        restored = OptionsFilters.model_validate_json(of.model_dump_json())
        assert restored == of

    def test_delta_fields_reject_nan(self) -> None:
        """Delta fields must reject NaN."""
        with pytest.raises(ValidationError, match="finite"):
            OptionsFilters(delta_primary_min=float("nan"))

    def test_delta_fields_reject_out_of_range(self) -> None:
        """Delta fields must be in [0, 1]."""
        with pytest.raises(ValidationError):
            OptionsFilters(delta_primary_min=1.5)
        with pytest.raises(ValidationError):
            OptionsFilters(delta_fallback_max=-0.1)

    def test_min_oi_rejects_negative(self) -> None:
        """min_oi must be >= 0."""
        with pytest.raises(ValidationError):
            OptionsFilters(min_oi=-1)

    def test_min_volume_rejects_negative(self) -> None:
        """min_volume must be >= 0."""
        with pytest.raises(ValidationError):
            OptionsFilters(min_volume=-1)

    def test_min_dte_rejects_negative(self) -> None:
        """min_dte must be >= 0."""
        with pytest.raises(ValidationError):
            OptionsFilters(min_dte=-1)

    def test_max_dte_rejects_zero(self) -> None:
        """max_dte must be >= 1."""
        with pytest.raises(ValidationError):
            OptionsFilters(max_dte=0)

    def test_delta_fallback_min_exceeds_max(self) -> None:
        """delta_fallback_min > delta_fallback_max should be rejected."""
        with pytest.raises(ValidationError, match="fallback_min.*fallback_max"):
            OptionsFilters(delta_fallback_min=0.90, delta_fallback_max=0.50)


# ---------------------------------------------------------------------------
# TestScanFilterSpec
# ---------------------------------------------------------------------------


class TestScanFilterSpec:
    """Tests for ScanFilterSpec (composite filter container)."""

    def test_default_construction(self) -> None:
        """ScanFilterSpec() with no args should construct with nested defaults."""
        spec = ScanFilterSpec()
        assert isinstance(spec.universe, UniverseFilters)
        assert isinstance(spec.scoring, ScoringFilters)
        assert isinstance(spec.options, OptionsFilters)

    def test_nested_frozen(self) -> None:
        """Nested models should also be frozen."""
        spec = ScanFilterSpec()
        with pytest.raises(ValidationError):
            spec.universe = UniverseFilters()  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        """Full JSON roundtrip must preserve all nested values."""
        spec = ScanFilterSpec(
            universe=UniverseFilters(preset=ScanPreset.FULL, min_price=5.0),
            scoring=ScoringFilters(min_score=50.0),
            options=OptionsFilters(top_n=10, min_dte=7),
        )
        restored = ScanFilterSpec.model_validate_json(spec.model_dump_json())
        assert restored == spec

    def test_model_dump_json_for_persistence(self) -> None:
        """model_dump_json() should produce valid JSON string."""
        spec = ScanFilterSpec()
        json_str = spec.model_dump_json()
        assert isinstance(json_str, str)
        assert "universe" in json_str
        assert "scoring" in json_str
        assert "options" in json_str

    def test_custom_overrides(self) -> None:
        """Non-default values should be preserved through construction."""
        spec = ScanFilterSpec(
            universe=UniverseFilters(
                preset=ScanPreset.NASDAQ100,
                sectors=[GICSSector.ENERGY, GICSSector.FINANCIALS],
                custom_tickers=["AAPL"],
                min_price=25.0,
                max_price=1000.0,
            ),
            scoring=ScoringFilters(
                direction_filter=SignalDirection.BULLISH,
                min_score=60.0,
                min_direction_confidence=0.7,
            ),
            options=OptionsFilters(
                top_n=25,
                min_dte=14,
                max_dte=60,
                min_iv_rank=40.0,
                exclude_near_earnings_days=5,
            ),
        )
        assert spec.universe.preset == ScanPreset.NASDAQ100
        assert len(spec.universe.sectors) == 2
        assert spec.scoring.direction_filter == SignalDirection.BULLISH
        assert spec.scoring.min_score == 60.0
        assert spec.scoring.min_direction_confidence == 0.7
        assert spec.options.top_n == 25
        assert spec.options.min_iv_rank == 40.0
        assert spec.options.exclude_near_earnings_days == 5
