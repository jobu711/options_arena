"""Tests for native quant fields on IndicatorSignals, MarketContext, and RecommendedContract.

Issue #491: Validates the 4 new IndicatorSignals fields (hv_yang_zhang, skew_25d,
smile_curvature, prob_above_current), 4 new MarketContext fields (same names, with
probability validator on prob_above_current), and 3 new RecommendedContract Greek
fields (vanna, charm, vomma). Also covers migration 032 and persistence roundtrip.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from options_arena.models.analysis import MarketContext
from options_arena.models.analytics import RecommendedContract
from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    MacdSignal,
    OptionType,
    PricingModel,
    ScanPreset,
    SignalDirection,
)
from options_arena.models.scan import IndicatorSignals, ScanRun

pytestmark = pytest.mark.critical


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market_context(**overrides: object) -> MarketContext:
    """Build a minimal MarketContext with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.00"),
        "price_52w_high": Decimal("200.00"),
        "price_52w_low": Decimal("140.00"),
        "macd_signal": MacdSignal.BULLISH_CROSSOVER,
        "next_earnings": date(2026, 4, 25),
        "dte_target": 45,
        "target_strike": Decimal("185.00"),
        "target_delta": 0.35,
        "sector": "Information Technology",
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime(2026, 3, 13, 14, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return MarketContext(**defaults)  # type: ignore[arg-type]


def _make_recommended_contract(
    scan_run_id: int = 1,
    **overrides: object,
) -> RecommendedContract:
    """Build a RecommendedContract with sensible defaults."""
    defaults: dict[str, object] = {
        "scan_run_id": scan_run_id,
        "ticker": "AAPL",
        "option_type": OptionType.CALL,
        "strike": Decimal("185.50"),
        "expiration": date(2026, 4, 15),
        "bid": Decimal("5.20"),
        "ask": Decimal("5.60"),
        "last": Decimal("5.40"),
        "volume": 1200,
        "open_interest": 5000,
        "market_iv": 0.32,
        "exercise_style": ExerciseStyle.AMERICAN,
        "delta": 0.45,
        "gamma": 0.03,
        "theta": -0.12,
        "vega": 0.15,
        "rho": 0.02,
        "pricing_model": PricingModel.BAW,
        "greeks_source": GreeksSource.COMPUTED,
        "entry_stock_price": Decimal("182.30"),
        "entry_mid": Decimal("5.40"),
        "direction": SignalDirection.BULLISH,
        "composite_score": 78.5,
        "risk_free_rate": 0.045,
        "created_at": datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return RecommendedContract(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# IndicatorSignals — native quant fields
# ===========================================================================


class TestIndicatorSignalsNativeQuant:
    """Verify 4 new IndicatorSignals fields for native quant."""

    def test_default_none(self) -> None:
        """New fields default to None when not provided."""
        signals = IndicatorSignals()
        assert signals.hv_yang_zhang is None
        assert signals.skew_25d is None
        assert signals.smile_curvature is None
        assert signals.prob_above_current is None

    def test_explicit_values(self) -> None:
        """New fields accept valid float values."""
        signals = IndicatorSignals(
            hv_yang_zhang=0.25,
            skew_25d=-0.05,
            smile_curvature=0.012,
            prob_above_current=0.55,
        )
        assert signals.hv_yang_zhang == pytest.approx(0.25)
        assert signals.skew_25d == pytest.approx(-0.05)
        assert signals.smile_curvature == pytest.approx(0.012)
        assert signals.prob_above_current == pytest.approx(0.55)

    def test_nan_sanitized_to_none(self) -> None:
        """NaN in new fields is sanitized to None by model_validator."""
        signals = IndicatorSignals(
            hv_yang_zhang=float("nan"),
            skew_25d=float("nan"),
            smile_curvature=float("nan"),
            prob_above_current=float("nan"),
        )
        assert signals.hv_yang_zhang is None
        assert signals.skew_25d is None
        assert signals.smile_curvature is None
        assert signals.prob_above_current is None

    def test_inf_sanitized_to_none(self) -> None:
        """Inf in new fields is sanitized to None by model_validator."""
        signals = IndicatorSignals(
            hv_yang_zhang=float("inf"),
            skew_25d=float("-inf"),
            smile_curvature=float("inf"),
            prob_above_current=float("-inf"),
        )
        assert signals.hv_yang_zhang is None
        assert signals.skew_25d is None
        assert signals.smile_curvature is None
        assert signals.prob_above_current is None

    def test_json_roundtrip_with_fields(self) -> None:
        """JSON serialization/deserialization preserves values."""
        signals = IndicatorSignals(
            hv_yang_zhang=0.30,
            skew_25d=-0.08,
            smile_curvature=0.015,
            prob_above_current=0.62,
        )
        restored = IndicatorSignals.model_validate_json(signals.model_dump_json())
        assert restored.hv_yang_zhang == pytest.approx(0.30)
        assert restored.skew_25d == pytest.approx(-0.08)
        assert restored.smile_curvature == pytest.approx(0.015)
        assert restored.prob_above_current == pytest.approx(0.62)

    def test_json_roundtrip_without_new_fields(self) -> None:
        """Backward compat: JSON without new fields produces None defaults."""
        json_str = '{"rsi": 55.0}'
        signals = IndicatorSignals.model_validate_json(json_str)
        assert signals.rsi == pytest.approx(55.0)
        assert signals.hv_yang_zhang is None
        assert signals.skew_25d is None
        assert signals.smile_curvature is None
        assert signals.prob_above_current is None

    def test_existing_fields_unchanged(self) -> None:
        """Existing indicator fields still work after adding new fields."""
        signals = IndicatorSignals(rsi=65.0, adx=28.0, bb_width=42.0)
        assert signals.rsi == pytest.approx(65.0)
        assert signals.adx == pytest.approx(28.0)
        assert signals.bb_width == pytest.approx(42.0)

    def test_negative_values_allowed(self) -> None:
        """skew_25d can be negative (puts more expensive than calls)."""
        signals = IndicatorSignals(skew_25d=-0.15)
        assert signals.skew_25d == pytest.approx(-0.15)


# ===========================================================================
# MarketContext — native quant fields
# ===========================================================================


class TestMarketContextNativeQuant:
    """Verify 4 new MarketContext fields for native quant."""

    def test_default_none(self) -> None:
        """New fields default to None when not provided."""
        ctx = _make_market_context()
        assert ctx.hv_yang_zhang is None
        assert ctx.skew_25d is None
        assert ctx.smile_curvature is None
        assert ctx.prob_above_current is None

    def test_explicit_values(self) -> None:
        """New fields accept valid float values."""
        ctx = _make_market_context(
            hv_yang_zhang=0.22,
            skew_25d=-0.04,
            smile_curvature=0.01,
            prob_above_current=0.48,
        )
        assert ctx.hv_yang_zhang == pytest.approx(0.22)
        assert ctx.skew_25d == pytest.approx(-0.04)
        assert ctx.smile_curvature == pytest.approx(0.01)
        assert ctx.prob_above_current == pytest.approx(0.48)

    def test_prob_above_current_rejects_greater_than_one(self) -> None:
        """prob_above_current > 1.0 is rejected."""
        with pytest.raises(Exception, match="prob_above_current"):
            _make_market_context(prob_above_current=1.01)

    def test_prob_above_current_rejects_negative(self) -> None:
        """prob_above_current < 0.0 is rejected."""
        with pytest.raises(Exception, match="prob_above_current"):
            _make_market_context(prob_above_current=-0.01)

    def test_prob_above_current_boundary_zero(self) -> None:
        """prob_above_current = 0.0 is accepted."""
        ctx = _make_market_context(prob_above_current=0.0)
        assert ctx.prob_above_current == pytest.approx(0.0)

    def test_prob_above_current_boundary_one(self) -> None:
        """prob_above_current = 1.0 is accepted."""
        ctx = _make_market_context(prob_above_current=1.0)
        assert ctx.prob_above_current == pytest.approx(1.0)

    def test_prob_above_current_rejects_nan(self) -> None:
        """prob_above_current NaN is rejected by the validator."""
        with pytest.raises(Exception, match="finite"):
            _make_market_context(prob_above_current=float("nan"))

    def test_hv_yang_zhang_rejects_nan(self) -> None:
        """hv_yang_zhang NaN is rejected by validate_optional_finite."""
        with pytest.raises(Exception, match="finite"):
            _make_market_context(hv_yang_zhang=float("nan"))

    def test_skew_25d_rejects_inf(self) -> None:
        """skew_25d Inf is rejected by validate_optional_finite."""
        with pytest.raises(Exception, match="finite"):
            _make_market_context(skew_25d=float("inf"))

    def test_smile_curvature_rejects_inf(self) -> None:
        """smile_curvature Inf is rejected by validate_optional_finite."""
        with pytest.raises(Exception, match="finite"):
            _make_market_context(smile_curvature=float("-inf"))


# ===========================================================================
# RecommendedContract — second-order Greek fields
# ===========================================================================


class TestRecommendedContractSecondOrderGreeks:
    """Verify 3 new Greek fields on RecommendedContract."""

    def test_default_none(self) -> None:
        """New Greek fields default to None when not provided."""
        contract = _make_recommended_contract()
        assert contract.vanna is None
        assert contract.charm is None
        assert contract.vomma is None

    def test_explicit_values(self) -> None:
        """New Greek fields accept valid float values."""
        contract = _make_recommended_contract(
            vanna=0.0012,
            charm=-0.003,
            vomma=0.0045,
        )
        assert contract.vanna == pytest.approx(0.0012)
        assert contract.charm == pytest.approx(-0.003)
        assert contract.vomma == pytest.approx(0.0045)

    def test_rejects_nan(self) -> None:
        """NaN on second-order Greeks is rejected."""
        with pytest.raises(Exception, match="finite"):
            _make_recommended_contract(vanna=float("nan"))

    def test_rejects_inf(self) -> None:
        """Inf on second-order Greeks is rejected."""
        with pytest.raises(Exception, match="finite"):
            _make_recommended_contract(charm=float("inf"))

    def test_negative_allowed(self) -> None:
        """Negative values are valid for second-order Greeks (charm is often negative)."""
        contract = _make_recommended_contract(
            vanna=-0.001,
            charm=-0.005,
            vomma=-0.002,
        )
        assert contract.vanna == pytest.approx(-0.001)
        assert contract.charm == pytest.approx(-0.005)
        assert contract.vomma == pytest.approx(-0.002)

    def test_backward_compat_json(self) -> None:
        """Old JSON without vanna/charm/vomma deserializes to None defaults."""
        contract = _make_recommended_contract()
        data = contract.model_dump()
        # Simulate pre-migration data: remove the new fields
        del data["vanna"]
        del data["charm"]
        del data["vomma"]
        restored = RecommendedContract.model_validate(data)
        assert restored.vanna is None
        assert restored.charm is None
        assert restored.vomma is None

    def test_existing_greeks_unchanged(self) -> None:
        """Existing first-order Greek fields still work."""
        contract = _make_recommended_contract()
        assert contract.delta == pytest.approx(0.45)
        assert contract.gamma == pytest.approx(0.03)
        assert contract.theta == pytest.approx(-0.12)
        assert contract.vega == pytest.approx(0.15)
        assert contract.rho == pytest.approx(0.02)

    def test_json_roundtrip_with_second_order(self) -> None:
        """JSON roundtrip preserves second-order Greek values."""
        contract = _make_recommended_contract(
            vanna=0.0015,
            charm=-0.004,
            vomma=0.006,
        )
        restored = RecommendedContract.model_validate_json(contract.model_dump_json())
        assert restored.vanna == pytest.approx(0.0015)
        assert restored.charm == pytest.approx(-0.004)
        assert restored.vomma == pytest.approx(0.006)


# ===========================================================================
# Migration 032 & persistence roundtrip
# ===========================================================================

pytestmark_db = pytest.mark.db


@pytest.mark.db
class TestMigration032:
    """Verify migration 032 applies cleanly and persistence roundtrip works."""

    @pytest.mark.asyncio
    async def test_migration_adds_columns(self) -> None:
        """Migration 032 adds vanna, charm, vomma columns to recommended_contracts."""
        from options_arena.data.database import Database

        db = Database(":memory:")
        await db.connect()
        try:
            conn = db.conn
            async with conn.execute("PRAGMA table_info(recommended_contracts)") as cursor:
                rows = await cursor.fetchall()
            columns = {row[1]: row[2] for row in rows}
            assert "vanna" in columns
            assert columns["vanna"] == "REAL"
            assert "charm" in columns
            assert columns["charm"] == "REAL"
            assert "vomma" in columns
            assert columns["vomma"] == "REAL"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_persistence_roundtrip_with_greeks(self) -> None:
        """Contracts with second-order Greeks survive save -> get roundtrip."""
        from options_arena.data.database import Database
        from options_arena.data.repository import Repository

        db = Database(":memory:")
        await db.connect()
        try:
            repo = Repository(db)
            scan = ScanRun(
                started_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                completed_at=datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
                preset=ScanPreset.SP500,
                tickers_scanned=500,
                tickers_scored=450,
                recommendations=1,
            )
            scan_id = await repo.save_scan_run(scan)

            contract = _make_recommended_contract(
                scan_run_id=scan_id,
                vanna=0.0012,
                charm=-0.003,
                vomma=0.0045,
            )
            await repo.save_recommended_contracts(scan_id, [contract])

            loaded = await repo.get_contracts_for_scan(scan_id)
            assert len(loaded) == 1
            c = loaded[0]
            assert c.vanna == pytest.approx(0.0012)
            assert c.charm == pytest.approx(-0.003)
            assert c.vomma == pytest.approx(0.0045)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_persistence_roundtrip_null_greeks(self) -> None:
        """Contracts without second-order Greeks persist as NULL, load as None."""
        from options_arena.data.database import Database
        from options_arena.data.repository import Repository

        db = Database(":memory:")
        await db.connect()
        try:
            repo = Repository(db)
            scan = ScanRun(
                started_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                completed_at=datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
                preset=ScanPreset.SP500,
                tickers_scanned=500,
                tickers_scored=450,
                recommendations=1,
            )
            scan_id = await repo.save_scan_run(scan)

            contract = _make_recommended_contract(scan_run_id=scan_id)
            await repo.save_recommended_contracts(scan_id, [contract])

            loaded = await repo.get_contracts_for_scan(scan_id)
            assert len(loaded) == 1
            c = loaded[0]
            assert c.vanna is None
            assert c.charm is None
            assert c.vomma is None
        finally:
            await db.close()
