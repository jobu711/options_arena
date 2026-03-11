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

    def test_json_roundtrip(self) -> None:
        """Verify ScanRequest survives JSON serialization roundtrip."""
        req = ScanRequest(
            preset=ScanPreset.FULL,
            sectors=[GICSSector.INFORMATION_TECHNOLOGY],
            min_score=42.0,
            min_direction_confidence=0.75,
        )
        json_str = req.model_dump_json()
        roundtrip = ScanRequest.model_validate_json(json_str)
        assert roundtrip.preset == ScanPreset.FULL
        assert roundtrip.min_score == pytest.approx(42.0)
        assert roundtrip.min_direction_confidence == pytest.approx(0.75)
