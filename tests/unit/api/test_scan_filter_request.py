"""Tests for API ScanRequest → ScanFilterSpec mapping.

Covers:
  - Default ScanRequest fields produce expected defaults.
  - All ScanRequest fields map correctly to filter categories.
  - min_direction_confidence field maps correctly.
  - Validators reject invalid values.
  - Non-default values are correctly preserved.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.api.schemas import ScanRequest
from options_arena.models.enums import (
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
    ScanPreset,
    SignalDirection,
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAPIFilterRequest:
    """API ScanRequest field mapping and validation tests."""

    def test_default_scan_request(self) -> None:
        """Verify default ScanRequest has expected field values."""
        req = ScanRequest()
        assert req.preset == ScanPreset.SP500
        assert req.sectors == []
        assert req.industry_groups == []
        assert req.market_cap_tiers == []
        assert req.exclude_near_earnings_days is None
        assert req.direction_filter is None
        assert req.min_iv_rank is None
        assert req.custom_tickers == []
        assert req.min_price is None
        assert req.max_price is None
        assert req.min_dte is None
        assert req.max_dte is None
        assert req.min_score is None
        assert req.min_direction_confidence is None
        assert req.source == "manual"

    def test_all_fields_populated(self) -> None:
        """Verify ScanRequest accepts all fields simultaneously."""
        req = ScanRequest(
            preset=ScanPreset.FULL,
            sectors=[GICSSector.INFORMATION_TECHNOLOGY],
            industry_groups=[GICSIndustryGroup.SOFTWARE_SERVICES],
            market_cap_tiers=[MarketCapTier.MEGA, MarketCapTier.LARGE],
            exclude_near_earnings_days=7,
            direction_filter=SignalDirection.BULLISH,
            min_iv_rank=30.0,
            custom_tickers=["AAPL", "MSFT"],
            min_price=10.0,
            max_price=500.0,
            min_dte=30,
            max_dte=90,
            min_score=40.0,
            min_direction_confidence=0.6,
        )
        assert req.preset == ScanPreset.FULL
        assert req.sectors == [GICSSector.INFORMATION_TECHNOLOGY]
        assert req.market_cap_tiers == [MarketCapTier.MEGA, MarketCapTier.LARGE]
        assert req.exclude_near_earnings_days == 7
        assert req.direction_filter == SignalDirection.BULLISH
        assert req.min_iv_rank == pytest.approx(30.0)
        assert req.min_price == pytest.approx(10.0)
        assert req.max_price == pytest.approx(500.0)
        assert req.min_dte == 30
        assert req.max_dte == 90
        assert req.min_score == pytest.approx(40.0)
        assert req.min_direction_confidence == pytest.approx(0.6)

    def test_min_direction_confidence_valid_range(self) -> None:
        """Verify min_direction_confidence accepts values in [0, 1]."""
        req = ScanRequest(min_direction_confidence=0.0)
        assert req.min_direction_confidence == pytest.approx(0.0)

        req = ScanRequest(min_direction_confidence=1.0)
        assert req.min_direction_confidence == pytest.approx(1.0)

        req = ScanRequest(min_direction_confidence=0.5)
        assert req.min_direction_confidence == pytest.approx(0.5)

    def test_min_direction_confidence_rejects_negative(self) -> None:
        """Verify min_direction_confidence rejects values < 0."""
        with pytest.raises(ValidationError, match="min_direction_confidence"):
            ScanRequest(min_direction_confidence=-0.1)

    def test_min_direction_confidence_rejects_above_one(self) -> None:
        """Verify min_direction_confidence rejects values > 1."""
        with pytest.raises(ValidationError, match="min_direction_confidence"):
            ScanRequest(min_direction_confidence=1.1)

    def test_min_direction_confidence_rejects_nan(self) -> None:
        """Verify min_direction_confidence rejects NaN."""
        with pytest.raises(ValidationError, match="min_direction_confidence"):
            ScanRequest(min_direction_confidence=float("nan"))

    def test_min_direction_confidence_rejects_inf(self) -> None:
        """Verify min_direction_confidence rejects Inf."""
        with pytest.raises(ValidationError, match="min_direction_confidence"):
            ScanRequest(min_direction_confidence=float("inf"))

    def test_min_score_rejects_negative(self) -> None:
        """Verify min_score rejects negative values."""
        with pytest.raises(ValidationError, match="min_score"):
            ScanRequest(min_score=-1.0)

    def test_min_price_rejects_negative(self) -> None:
        """Verify min_price rejects non-positive values."""
        with pytest.raises(ValidationError, match="price must be positive"):
            ScanRequest(min_price=-5.0)

    def test_none_fields_are_skipped(self) -> None:
        """Verify None fields don't override defaults in filter mapping."""
        req = ScanRequest(
            min_score=None,
            min_direction_confidence=None,
            min_price=None,
            max_price=None,
            min_dte=None,
            max_dte=None,
        )
        assert req.min_score is None
        assert req.min_direction_confidence is None
        assert req.min_price is None

    # --- top_n ---

    def test_top_n_valid(self) -> None:
        """Verify top_n accepts positive integers."""
        req = ScanRequest(top_n=10)
        assert req.top_n == 10

    def test_top_n_zero_rejected(self) -> None:
        """Verify top_n rejects zero."""
        with pytest.raises(ValidationError, match="top_n"):
            ScanRequest(top_n=0)

    # --- min_dollar_volume ---

    def test_min_dollar_volume_valid(self) -> None:
        """Verify min_dollar_volume accepts non-negative finite float."""
        req = ScanRequest(min_dollar_volume=5_000_000.0)
        assert req.min_dollar_volume == pytest.approx(5_000_000.0)

    def test_min_dollar_volume_negative_rejected(self) -> None:
        """Verify min_dollar_volume rejects negative values."""
        with pytest.raises(ValidationError, match="min_dollar_volume"):
            ScanRequest(min_dollar_volume=-1.0)

    def test_min_dollar_volume_nan_rejected(self) -> None:
        """Verify min_dollar_volume rejects NaN."""
        with pytest.raises(ValidationError, match="min_dollar_volume"):
            ScanRequest(min_dollar_volume=float("nan"))

    # --- min_oi ---

    def test_min_oi_valid(self) -> None:
        """Verify min_oi accepts non-negative int."""
        req = ScanRequest(min_oi=50)
        assert req.min_oi == 50

    def test_min_oi_negative_rejected(self) -> None:
        """Verify min_oi rejects negative values."""
        with pytest.raises(ValidationError, match="non-negative"):
            ScanRequest(min_oi=-1)

    # --- min_volume ---

    def test_min_volume_valid(self) -> None:
        """Verify min_volume accepts non-negative int."""
        req = ScanRequest(min_volume=10)
        assert req.min_volume == 10

    def test_min_volume_negative_rejected(self) -> None:
        """Verify min_volume rejects negative values."""
        with pytest.raises(ValidationError, match="non-negative"):
            ScanRequest(min_volume=-1)

    # --- max_spread_pct ---

    def test_max_spread_pct_valid(self) -> None:
        """Verify max_spread_pct accepts non-negative finite float."""
        req = ScanRequest(max_spread_pct=0.15)
        assert req.max_spread_pct == pytest.approx(0.15)

    def test_max_spread_pct_negative_rejected(self) -> None:
        """Verify max_spread_pct rejects negative values."""
        with pytest.raises(ValidationError, match="max_spread_pct"):
            ScanRequest(max_spread_pct=-0.01)

    # --- delta fields ---

    def test_delta_valid(self) -> None:
        """Verify delta fields accept values in [0.0, 1.0]."""
        req = ScanRequest(
            delta_primary_min=0.25,
            delta_primary_max=0.45,
            delta_fallback_min=0.10,
            delta_fallback_max=0.80,
        )
        assert req.delta_primary_min == pytest.approx(0.25)
        assert req.delta_primary_max == pytest.approx(0.45)

    def test_delta_out_of_range_rejected(self) -> None:
        """Verify delta rejects values outside [0.0, 1.0]."""
        with pytest.raises(ValidationError, match="delta"):
            ScanRequest(delta_primary_min=1.5)

    def test_delta_primary_min_gt_max_rejected(self) -> None:
        """Verify delta_primary_min > delta_primary_max is rejected."""
        with pytest.raises(ValidationError, match="delta_primary_min"):
            ScanRequest(delta_primary_min=0.6, delta_primary_max=0.3)

    def test_delta_fallback_min_gt_max_rejected(self) -> None:
        """Verify delta_fallback_min > delta_fallback_max is rejected."""
        with pytest.raises(ValidationError, match="delta_fallback_min"):
            ScanRequest(delta_fallback_min=0.8, delta_fallback_max=0.2)

    # --- new fields defaults ---

    def test_new_options_fields_default_none(self) -> None:
        """Verify all 9 new fields default to None."""
        req = ScanRequest()
        assert req.top_n is None
        assert req.min_dollar_volume is None
        assert req.min_oi is None
        assert req.min_volume is None
        assert req.max_spread_pct is None
        assert req.delta_primary_min is None
        assert req.delta_primary_max is None
        assert req.delta_fallback_min is None
        assert req.delta_fallback_max is None

    def test_json_roundtrip(self) -> None:
        """Verify ScanRequest survives JSON serialization roundtrip."""
        req = ScanRequest(
            preset=ScanPreset.FULL,
            sectors=[GICSSector.INFORMATION_TECHNOLOGY],
            min_score=42.0,
            min_direction_confidence=0.75,
            top_n=25,
            min_dollar_volume=5_000_000.0,
            max_spread_pct=0.15,
            delta_primary_min=0.25,
            delta_primary_max=0.45,
        )
        json_str = req.model_dump_json()
        roundtrip = ScanRequest.model_validate_json(json_str)
        assert roundtrip.preset == ScanPreset.FULL
        assert roundtrip.min_score == pytest.approx(42.0)
        assert roundtrip.min_direction_confidence == pytest.approx(0.75)
        assert roundtrip.top_n == 25
        assert roundtrip.min_dollar_volume == pytest.approx(5_000_000.0)
        assert roundtrip.max_spread_pct == pytest.approx(0.15)
        assert roundtrip.delta_primary_min == pytest.approx(0.25)
        assert roundtrip.delta_primary_max == pytest.approx(0.45)
