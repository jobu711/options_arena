"""Unit tests for MarketContext 30-field extension (Issue #206).

Tests cover:
- 8 Arena Recon intelligence fields (analyst, insider, institutional)
- 22 DSE fields (dimensional scores, indicators, second-order Greeks, confidence)
- intelligence_ratio() method
- dse_ratio() method
- Existing completeness_ratio() and enrichment_ratio() are NOT affected by new fields
- NaN/Inf rejection on all new float fields via validate_optional_finite
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models.analysis import MarketContext
from options_arena.models.enums import ExerciseStyle, MacdSignal

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_ctx(**overrides: object) -> MarketContext:
    """Build a minimal valid MarketContext with optional overrides."""
    defaults: dict[str, object] = dict(
        ticker="TEST",
        current_price=Decimal("100.00"),
        price_52w_high=Decimal("120.00"),
        price_52w_low=Decimal("80.00"),
        rsi_14=50.0,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        next_earnings=date(2026, 4, 1),
        dte_target=45,
        target_strike=Decimal("105.00"),
        target_delta=0.35,
        sector="Technology",
        dividend_yield=0.01,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 3, 3, tzinfo=UTC),
    )
    defaults.update(overrides)
    return MarketContext(**defaults)


# ---------------------------------------------------------------------------
# Intelligence field names (float only for NaN/Inf tests)
# ---------------------------------------------------------------------------
INTELLIGENCE_FLOAT_FIELDS: list[str] = [
    "analyst_target_mean",
    "analyst_target_upside_pct",
    "analyst_consensus_score",
    "insider_buy_ratio",
    "institutional_pct",
]

INTELLIGENCE_INT_FIELDS: list[str] = [
    "analyst_upgrades_30d",
    "analyst_downgrades_30d",
    "insider_net_buys_90d",
]

DSE_FIELDS: list[str] = [
    "dim_trend",
    "dim_iv_vol",
    "dim_hv_vol",
    "dim_flow",
    "dim_microstructure",
    "dim_fundamental",
    "dim_regime",
    "dim_risk",
    "vol_regime",
    "iv_hv_spread",
    "gex",
    "unusual_activity_score",
    "skew_ratio",
    "vix_term_structure",
    "market_regime",
    "rsi_divergence",
    "expected_move",
    "expected_move_ratio",
    "target_vanna",
    "target_charm",
    "target_vomma",
    "direction_confidence",
]


# ===========================================================================
# TestMarketContextIntelligenceFields
# ===========================================================================


class TestMarketContextIntelligenceFields:
    """Test the 8 Arena Recon intelligence fields on MarketContext."""

    def test_all_intelligence_fields_default_none(self) -> None:
        ctx = _make_ctx()
        for field_name in INTELLIGENCE_FLOAT_FIELDS + INTELLIGENCE_INT_FIELDS:
            assert getattr(ctx, field_name) is None, f"{field_name} should default to None"

    def test_intelligence_fields_accept_valid_floats(self) -> None:
        ctx = _make_ctx(
            analyst_target_mean=150.0,
            analyst_target_upside_pct=0.25,
            analyst_consensus_score=-0.5,
            insider_buy_ratio=0.7,
            institutional_pct=0.85,
        )
        assert ctx.analyst_target_mean == 150.0
        assert ctx.analyst_target_upside_pct == 0.25
        assert ctx.analyst_consensus_score == -0.5
        assert ctx.insider_buy_ratio == 0.7
        assert ctx.institutional_pct == 0.85

    @pytest.mark.parametrize("field_name", INTELLIGENCE_FLOAT_FIELDS)
    def test_intelligence_fields_reject_nan(self, field_name: str) -> None:
        with pytest.raises(ValidationError, match="must be finite"):
            _make_ctx(**{field_name: float("nan")})

    @pytest.mark.parametrize("field_name", INTELLIGENCE_FLOAT_FIELDS)
    def test_intelligence_fields_reject_inf(self, field_name: str) -> None:
        with pytest.raises(ValidationError, match="must be finite"):
            _make_ctx(**{field_name: float("inf")})

    @pytest.mark.parametrize("field_name", INTELLIGENCE_FLOAT_FIELDS)
    def test_intelligence_fields_reject_neg_inf(self, field_name: str) -> None:
        with pytest.raises(ValidationError, match="must be finite"):
            _make_ctx(**{field_name: float("-inf")})

    def test_int_fields_accept_valid_ints(self) -> None:
        ctx = _make_ctx(
            analyst_upgrades_30d=5,
            analyst_downgrades_30d=2,
            insider_net_buys_90d=-3,
        )
        assert ctx.analyst_upgrades_30d == 5
        assert ctx.analyst_downgrades_30d == 2
        assert ctx.insider_net_buys_90d == -3

    def test_int_fields_accept_zero(self) -> None:
        ctx = _make_ctx(
            analyst_upgrades_30d=0,
            analyst_downgrades_30d=0,
            insider_net_buys_90d=0,
        )
        assert ctx.analyst_upgrades_30d == 0
        assert ctx.analyst_downgrades_30d == 0
        assert ctx.insider_net_buys_90d == 0


# ===========================================================================
# TestMarketContextDSEFields
# ===========================================================================


class TestMarketContextDSEFields:
    """Test the 22 DSE fields on MarketContext."""

    def test_all_dse_fields_default_none(self) -> None:
        ctx = _make_ctx()
        for field_name in DSE_FIELDS:
            assert getattr(ctx, field_name) is None, f"{field_name} should default to None"

    def test_dse_fields_accept_valid_floats(self) -> None:
        overrides = {name: 50.0 for name in DSE_FIELDS}
        ctx = _make_ctx(**overrides)
        for field_name in DSE_FIELDS:
            assert getattr(ctx, field_name) == 50.0

    @pytest.mark.parametrize("field_name", DSE_FIELDS)
    def test_dse_fields_reject_nan(self, field_name: str) -> None:
        with pytest.raises(ValidationError, match="must be finite"):
            _make_ctx(**{field_name: float("nan")})

    @pytest.mark.parametrize("field_name", DSE_FIELDS)
    def test_dse_fields_reject_inf(self, field_name: str) -> None:
        with pytest.raises(ValidationError, match="must be finite"):
            _make_ctx(**{field_name: float("inf")})

    def test_second_order_greeks_accept_valid(self) -> None:
        ctx = _make_ctx(
            target_vanna=0.05,
            target_charm=-0.02,
            target_vomma=0.01,
        )
        assert ctx.target_vanna == 0.05
        assert ctx.target_charm == -0.02
        assert ctx.target_vomma == 0.01

    def test_second_order_greeks_accept_negative(self) -> None:
        ctx = _make_ctx(
            target_vanna=-1.5,
            target_charm=-3.0,
            target_vomma=-0.5,
        )
        assert ctx.target_vanna == -1.5
        assert ctx.target_charm == -3.0
        assert ctx.target_vomma == -0.5

    def test_direction_confidence_accepts_valid(self) -> None:
        ctx = _make_ctx(direction_confidence=0.85)
        assert ctx.direction_confidence == 0.85

    def test_direction_confidence_accepts_boundary_values(self) -> None:
        ctx_zero = _make_ctx(direction_confidence=0.0)
        assert ctx_zero.direction_confidence == 0.0
        ctx_one = _make_ctx(direction_confidence=1.0)
        assert ctx_one.direction_confidence == 1.0

    def test_dimensional_scores_accept_valid(self) -> None:
        dim_fields = [
            "dim_trend",
            "dim_iv_vol",
            "dim_hv_vol",
            "dim_flow",
            "dim_microstructure",
            "dim_fundamental",
            "dim_regime",
            "dim_risk",
        ]
        overrides = {name: 75.0 for name in dim_fields}
        ctx = _make_ctx(**overrides)
        for field_name in dim_fields:
            assert getattr(ctx, field_name) == 75.0

    def test_high_signal_indicators_accept_valid(self) -> None:
        ctx = _make_ctx(
            vol_regime=2.0,
            iv_hv_spread=0.15,
            gex=-500_000_000.0,
            unusual_activity_score=80.0,
            skew_ratio=1.05,
            vix_term_structure=0.03,
            market_regime=1.0,
            rsi_divergence=-0.5,
            expected_move=12.50,
            expected_move_ratio=0.08,
        )
        assert ctx.vol_regime == 2.0
        assert ctx.iv_hv_spread == 0.15
        assert ctx.gex == -500_000_000.0
        assert ctx.unusual_activity_score == 80.0
        assert ctx.skew_ratio == 1.05
        assert ctx.vix_term_structure == 0.03
        assert ctx.market_regime == 1.0
        assert ctx.rsi_divergence == -0.5
        assert ctx.expected_move == 12.50
        assert ctx.expected_move_ratio == 0.08


# ===========================================================================
# TestIntelligenceRatio
# ===========================================================================


class TestIntelligenceRatio:
    """Test the intelligence_ratio() method."""

    def test_all_populated(self) -> None:
        ctx = _make_ctx(
            analyst_target_mean=150.0,
            analyst_target_upside_pct=0.25,
            analyst_consensus_score=0.5,
            analyst_upgrades_30d=5,
            analyst_downgrades_30d=2,
            insider_net_buys_90d=3,
            insider_buy_ratio=0.7,
            institutional_pct=0.85,
        )
        assert ctx.intelligence_ratio() == pytest.approx(1.0)

    def test_all_none(self) -> None:
        ctx = _make_ctx()
        assert ctx.intelligence_ratio() == pytest.approx(0.0)

    def test_partial(self) -> None:
        # 4 of 8 fields populated
        ctx = _make_ctx(
            analyst_target_mean=150.0,
            analyst_target_upside_pct=0.25,
            analyst_upgrades_30d=5,
            insider_buy_ratio=0.7,
        )
        assert ctx.intelligence_ratio() == pytest.approx(4.0 / 8.0)

    def test_single_field(self) -> None:
        ctx = _make_ctx(analyst_target_mean=100.0)
        assert ctx.intelligence_ratio() == pytest.approx(1.0 / 8.0)

    def test_zero_valued_fields_count_as_populated(self) -> None:
        """0 is not None -- a zero value means data was fetched."""
        ctx = _make_ctx(
            analyst_target_mean=0.0,
            analyst_upgrades_30d=0,
            analyst_downgrades_30d=0,
            insider_net_buys_90d=0,
        )
        assert ctx.intelligence_ratio() == pytest.approx(4.0 / 8.0)


# ===========================================================================
# TestDSERatio
# ===========================================================================


class TestDSERatio:
    """Test the dse_ratio() method."""

    def test_all_populated(self) -> None:
        overrides = {name: 50.0 for name in DSE_FIELDS}
        ctx = _make_ctx(**overrides)
        assert ctx.dse_ratio() == pytest.approx(1.0)

    def test_all_none(self) -> None:
        ctx = _make_ctx()
        assert ctx.dse_ratio() == pytest.approx(0.0)

    def test_partial(self) -> None:
        # 11 of 22 fields populated
        half_fields = DSE_FIELDS[:11]
        overrides = {name: 42.0 for name in half_fields}
        ctx = _make_ctx(**overrides)
        assert ctx.dse_ratio() == pytest.approx(11.0 / 22.0)

    def test_single_field(self) -> None:
        ctx = _make_ctx(dim_trend=80.0)
        assert ctx.dse_ratio() == pytest.approx(1.0 / 22.0)

    def test_zero_valued_fields_count_as_populated(self) -> None:
        """0.0 is not None -- a zero value means data was computed."""
        ctx = _make_ctx(dim_trend=0.0, dim_risk=0.0, gex=0.0)
        assert ctx.dse_ratio() == pytest.approx(3.0 / 22.0)


# ===========================================================================
# TestExistingRatiosUnchanged
# ===========================================================================


class TestExistingRatiosUnchanged:
    """Ensure completeness_ratio() and enrichment_ratio() are NOT affected by new fields."""

    def test_completeness_ratio_excludes_new_fields(self) -> None:
        """Adding new fields with non-None values should NOT change completeness_ratio."""
        ctx_base = _make_ctx()
        base_ratio = ctx_base.completeness_ratio()

        # Set ALL 30 new fields to non-None values
        all_new: dict[str, object] = {name: 50.0 for name in DSE_FIELDS}
        all_new.update({name: 10.0 for name in INTELLIGENCE_FLOAT_FIELDS})
        all_new.update({name: 5 for name in INTELLIGENCE_INT_FIELDS})
        ctx_full = _make_ctx(**all_new)

        assert ctx_full.completeness_ratio() == pytest.approx(base_ratio)

    def test_enrichment_ratio_excludes_new_fields(self) -> None:
        """Adding new fields with non-None values should NOT change enrichment_ratio."""
        ctx_base = _make_ctx()
        base_ratio = ctx_base.enrichment_ratio()

        # Set ALL 30 new fields to non-None values
        all_new: dict[str, object] = {name: 50.0 for name in DSE_FIELDS}
        all_new.update({name: 10.0 for name in INTELLIGENCE_FLOAT_FIELDS})
        all_new.update({name: 5 for name in INTELLIGENCE_INT_FIELDS})
        ctx_full = _make_ctx(**all_new)

        assert ctx_full.enrichment_ratio() == pytest.approx(base_ratio)

    def test_completeness_ratio_still_works_with_core_fields(self) -> None:
        """Verify completeness_ratio still works correctly with its existing fields."""
        ctx = _make_ctx(
            iv_rank=45.0,
            iv_percentile=52.0,
            atm_iv_30d=0.28,
            put_call_ratio=0.85,
            adx=25.0,
            sma_alignment=70.0,
            bb_width=0.15,
            atr_pct=2.5,
            stochastic_rsi=0.4,
            relative_volume=1.2,
            max_pain_distance=0.05,
        )
        # 11 of 11 checkable fields populated (no contract_mid, so no Greeks)
        assert ctx.completeness_ratio() == pytest.approx(1.0)

    def test_enrichment_ratio_still_works_with_openbb_fields(self) -> None:
        """Verify enrichment_ratio still works correctly with its existing fields."""
        ctx = _make_ctx(
            pe_ratio=25.0,
            forward_pe=22.0,
            peg_ratio=1.5,
            price_to_book=5.0,
            debt_to_equity=0.8,
            revenue_growth=0.15,
            profit_margin=0.22,
            net_call_premium=1_000_000.0,
            net_put_premium=500_000.0,
            options_put_call_ratio=0.75,
            news_sentiment=0.3,
        )
        # 11 of 11 enrichment fields populated
        assert ctx.enrichment_ratio() == pytest.approx(1.0)
