"""Integration tests for native-quant API schema exposure.

Verifies:
  - DebateResultDetail schema includes new MarketContext fields
    (hv_yang_zhang, skew_25d, smile_curvature, prob_above_current)
  - DebateResultDetail schema includes second-order Greek fields
    (target_vanna, target_charm, target_vomma)
  - RecommendedContract exposes vanna/charm/vomma in API serialization
  - Schema backward compatibility (all new fields are optional/nullable)
  - JSON serialization round-trip for new fields
  - OptionGreeks includes second-order Greeks in serialized output

Issue #492 — native-quant epic final validation.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from options_arena.api.schemas import DebateResultDetail
from options_arena.models.analytics import RecommendedContract
from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    OptionType,
    PricingModel,
    SignalDirection,
)
from options_arena.models.options import OptionContract, OptionGreeks

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_debate_detail(**overrides: object) -> DebateResultDetail:
    """Build a minimal DebateResultDetail with sensible defaults."""
    defaults: dict[str, object] = {
        "id": 1,
        "ticker": "AAPL",
        "is_fallback": False,
        "model_name": "llama-3.3-70b-versatile",
        "duration_ms": 2500,
        "total_tokens": 5000,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return DebateResultDetail(**defaults)


def _make_recommended_contract(**overrides: object) -> RecommendedContract:
    """Build a RecommendedContract with sensible defaults + second-order Greeks."""
    defaults: dict[str, object] = {
        "scan_run_id": 1,
        "ticker": "AAPL",
        "option_type": OptionType.CALL,
        "strike": Decimal("185.00"),
        "bid": Decimal("5.00"),
        "ask": Decimal("5.50"),
        "last": Decimal("5.25"),
        "expiration": date.today() + timedelta(days=45),
        "volume": 500,
        "open_interest": 2000,
        "market_iv": 0.28,
        "exercise_style": ExerciseStyle.AMERICAN,
        "delta": 0.35,
        "gamma": 0.03,
        "theta": -0.05,
        "vega": 0.20,
        "rho": 0.01,
        "vanna": 0.012,
        "charm": -0.004,
        "vomma": 0.15,
        "pricing_model": PricingModel.BAW,
        "greeks_source": GreeksSource.COMPUTED,
        "entry_stock_price": Decimal("185.50"),
        "entry_mid": Decimal("5.25"),
        "direction": SignalDirection.BULLISH,
        "composite_score": 72.5,
        "risk_free_rate": 0.045,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return RecommendedContract(**defaults)


# ---------------------------------------------------------------------------
# DebateResultDetail — MarketContext fields
# ---------------------------------------------------------------------------


class TestDebateResultDetailNativeQuant:
    """DebateResultDetail exposes native-quant vol surface + HV metrics."""

    def test_hv_yang_zhang_field_present(self) -> None:
        """hv_yang_zhang is accepted and stored on DebateResultDetail."""
        detail = _make_debate_detail(hv_yang_zhang=0.25)
        assert detail.hv_yang_zhang == pytest.approx(0.25, rel=1e-6)

    def test_skew_25d_field_present(self) -> None:
        """skew_25d is accepted and stored on DebateResultDetail."""
        detail = _make_debate_detail(skew_25d=0.03)
        assert detail.skew_25d == pytest.approx(0.03, rel=1e-6)

    def test_smile_curvature_field_present(self) -> None:
        """smile_curvature is accepted and stored on DebateResultDetail."""
        detail = _make_debate_detail(smile_curvature=1.5)
        assert detail.smile_curvature == pytest.approx(1.5, rel=1e-6)

    def test_prob_above_current_field_present(self) -> None:
        """prob_above_current is accepted and stored on DebateResultDetail."""
        detail = _make_debate_detail(prob_above_current=0.52)
        assert detail.prob_above_current == pytest.approx(0.52, rel=1e-6)

    def test_all_native_quant_fields_together(self) -> None:
        """All 4 native-quant MarketContext fields coexist on the same detail."""
        detail = _make_debate_detail(
            hv_yang_zhang=0.25,
            skew_25d=0.03,
            smile_curvature=1.5,
            prob_above_current=0.52,
        )
        assert detail.hv_yang_zhang == pytest.approx(0.25, rel=1e-6)
        assert detail.skew_25d == pytest.approx(0.03, rel=1e-6)
        assert detail.smile_curvature == pytest.approx(1.5, rel=1e-6)
        assert detail.prob_above_current == pytest.approx(0.52, rel=1e-6)


# ---------------------------------------------------------------------------
# DebateResultDetail — Second-order Greeks
# ---------------------------------------------------------------------------


class TestDebateResultDetailSecondOrderGreeks:
    """DebateResultDetail exposes target contract second-order Greeks."""

    def test_target_vanna_field_present(self) -> None:
        """target_vanna is accepted on DebateResultDetail."""
        detail = _make_debate_detail(target_vanna=0.012)
        assert detail.target_vanna == pytest.approx(0.012, rel=1e-6)

    def test_target_charm_field_present(self) -> None:
        """target_charm is accepted on DebateResultDetail."""
        detail = _make_debate_detail(target_charm=-0.004)
        assert detail.target_charm == pytest.approx(-0.004, rel=1e-6)

    def test_target_vomma_field_present(self) -> None:
        """target_vomma is accepted on DebateResultDetail."""
        detail = _make_debate_detail(target_vomma=0.15)
        assert detail.target_vomma == pytest.approx(0.15, rel=1e-6)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestSchemaBackwardCompatibility:
    """New fields are all optional — old data without them still works."""

    def test_no_native_quant_fields_creates_valid_detail(self) -> None:
        """DebateResultDetail without native-quant fields defaults to None."""
        detail = _make_debate_detail()
        assert detail.hv_yang_zhang is None
        assert detail.skew_25d is None
        assert detail.smile_curvature is None
        assert detail.prob_above_current is None
        assert detail.target_vanna is None
        assert detail.target_charm is None
        assert detail.target_vomma is None

    def test_partial_native_quant_fields(self) -> None:
        """Partially populating native-quant fields leaves others as None."""
        detail = _make_debate_detail(hv_yang_zhang=0.25, skew_25d=0.03)
        assert detail.hv_yang_zhang == pytest.approx(0.25, rel=1e-6)
        assert detail.skew_25d == pytest.approx(0.03, rel=1e-6)
        assert detail.smile_curvature is None
        assert detail.prob_above_current is None

    def test_existing_openbb_fields_unaffected(self) -> None:
        """Existing OpenBB enrichment fields still work alongside native-quant."""
        detail = _make_debate_detail(
            pe_ratio=25.0,
            forward_pe=22.0,
            enrichment_ratio=0.6,
            hv_yang_zhang=0.25,
        )
        assert detail.pe_ratio == pytest.approx(25.0, rel=1e-6)
        assert detail.forward_pe == pytest.approx(22.0, rel=1e-6)
        assert detail.enrichment_ratio == pytest.approx(0.6, rel=1e-6)
        assert detail.hv_yang_zhang == pytest.approx(0.25, rel=1e-6)


# ---------------------------------------------------------------------------
# JSON serialization round-trip
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    """Native-quant fields survive JSON serialization round-trip."""

    def test_debate_detail_json_roundtrip(self) -> None:
        """DebateResultDetail with native-quant fields survives JSON round-trip."""
        detail = _make_debate_detail(
            hv_yang_zhang=0.2534,
            skew_25d=0.031,
            smile_curvature=1.48,
            prob_above_current=0.515,
            target_vanna=0.012,
            target_charm=-0.004,
            target_vomma=0.15,
        )
        json_str = detail.model_dump_json()
        restored = DebateResultDetail.model_validate_json(json_str)
        assert restored.hv_yang_zhang == pytest.approx(0.2534, rel=1e-6)
        assert restored.skew_25d == pytest.approx(0.031, rel=1e-6)
        assert restored.smile_curvature == pytest.approx(1.48, rel=1e-6)
        assert restored.prob_above_current == pytest.approx(0.515, rel=1e-6)
        assert restored.target_vanna == pytest.approx(0.012, rel=1e-6)
        assert restored.target_charm == pytest.approx(-0.004, rel=1e-6)
        assert restored.target_vomma == pytest.approx(0.15, rel=1e-6)

    def test_debate_detail_json_includes_native_quant_keys(self) -> None:
        """JSON output explicitly includes native-quant field keys."""
        detail = _make_debate_detail(
            hv_yang_zhang=0.25,
            skew_25d=0.03,
        )
        data = json.loads(detail.model_dump_json())
        assert "hv_yang_zhang" in data
        assert "skew_25d" in data
        assert "smile_curvature" in data
        assert "prob_above_current" in data
        assert "target_vanna" in data
        assert "target_charm" in data
        assert "target_vomma" in data

    def test_recommended_contract_json_includes_second_order_greeks(self) -> None:
        """RecommendedContract JSON output includes vanna/charm/vomma."""
        contract = _make_recommended_contract()
        data = json.loads(contract.model_dump_json())
        assert data["vanna"] == pytest.approx(0.012, rel=1e-6)
        assert data["charm"] == pytest.approx(-0.004, rel=1e-6)
        assert data["vomma"] == pytest.approx(0.15, rel=1e-6)

    def test_recommended_contract_json_roundtrip(self) -> None:
        """RecommendedContract with second-order Greeks survives JSON round-trip."""
        contract = _make_recommended_contract()
        json_str = contract.model_dump_json()
        restored = RecommendedContract.model_validate_json(json_str)
        assert restored.vanna == pytest.approx(0.012, rel=1e-6)
        assert restored.charm == pytest.approx(-0.004, rel=1e-6)
        assert restored.vomma == pytest.approx(0.15, rel=1e-6)


# ---------------------------------------------------------------------------
# OptionGreeks second-order serialization
# ---------------------------------------------------------------------------


class TestOptionGreeksSecondOrder:
    """OptionGreeks model includes vanna/charm/vomma in API serialization."""

    def test_option_greeks_with_second_order(self) -> None:
        """OptionGreeks accepts vanna/charm/vomma."""
        greeks = OptionGreeks(
            delta=0.35,
            gamma=0.03,
            theta=-0.05,
            vega=0.20,
            rho=0.01,
            vanna=0.012,
            charm=-0.004,
            vomma=0.15,
            pricing_model=PricingModel.BAW,
        )
        assert greeks.vanna == pytest.approx(0.012, rel=1e-6)
        assert greeks.charm == pytest.approx(-0.004, rel=1e-6)
        assert greeks.vomma == pytest.approx(0.15, rel=1e-6)

    def test_option_greeks_second_order_in_json(self) -> None:
        """OptionGreeks JSON includes vanna/charm/vomma keys."""
        greeks = OptionGreeks(
            delta=0.35,
            gamma=0.03,
            theta=-0.05,
            vega=0.20,
            rho=0.01,
            vanna=0.012,
            charm=-0.004,
            vomma=0.15,
            pricing_model=PricingModel.BAW,
        )
        data = json.loads(greeks.model_dump_json())
        assert "vanna" in data
        assert "charm" in data
        assert "vomma" in data

    def test_option_greeks_second_order_defaults_none(self) -> None:
        """OptionGreeks without second-order Greeks defaults them to None."""
        greeks = OptionGreeks(
            delta=0.35,
            gamma=0.03,
            theta=-0.05,
            vega=0.20,
            rho=0.01,
            pricing_model=PricingModel.BAW,
        )
        assert greeks.vanna is None
        assert greeks.charm is None
        assert greeks.vomma is None

    def test_option_greeks_second_order_validation(self) -> None:
        """OptionGreeks rejects non-finite second-order Greek values."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptionGreeks(
                delta=0.35,
                gamma=0.03,
                theta=-0.05,
                vega=0.20,
                rho=0.01,
                vanna=float("inf"),
                pricing_model=PricingModel.BAW,
            )

    def test_option_contract_greeks_propagate_second_order(self) -> None:
        """OptionContract with OptionGreeks propagates vanna/charm/vomma in JSON."""
        greeks = OptionGreeks(
            delta=0.35,
            gamma=0.03,
            theta=-0.05,
            vega=0.20,
            rho=0.01,
            vanna=0.012,
            charm=-0.004,
            vomma=0.15,
            pricing_model=PricingModel.BAW,
        )
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date.today() + timedelta(days=45),
            bid=Decimal("5.00"),
            ask=Decimal("5.50"),
            last=Decimal("5.25"),
            volume=500,
            open_interest=2000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.28,
            greeks=greeks,
        )
        data = json.loads(contract.model_dump_json())
        greeks_data = data["greeks"]
        assert greeks_data["vanna"] == pytest.approx(0.012, rel=1e-6)
        assert greeks_data["charm"] == pytest.approx(-0.004, rel=1e-6)
        assert greeks_data["vomma"] == pytest.approx(0.15, rel=1e-6)
