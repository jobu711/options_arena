"""Tests for ScanRequest pre-scan fields and PresetInfo added in #285."""

from __future__ import annotations

from options_arena.api.schemas import PresetInfo, ScanRequest


class TestScanRequestNewFields:
    """Tests for min_price, max_price, min_dte, max_dte on ScanRequest."""

    def test_optional_fields_default_to_none(self) -> None:
        """All new fields default to None for backward compatibility."""
        req = ScanRequest()
        assert req.min_price is None
        assert req.max_price is None
        assert req.min_dte is None
        assert req.max_dte is None

    def test_all_new_fields_populated(self) -> None:
        """All new fields can be set together."""
        req = ScanRequest(
            min_price=10.0,
            max_price=500.0,
            min_dte=7,
            max_dte=90,
        )
        assert req.min_price == 10.0
        assert req.max_price == 500.0
        assert req.min_dte == 7
        assert req.max_dte == 90

    def test_partial_fields(self) -> None:
        """Some new fields set, others remain None."""
        req = ScanRequest(max_price=200.0, min_dte=14)
        assert req.min_price is None
        assert req.max_price == 200.0
        assert req.min_dte == 14
        assert req.max_dte is None

    def test_backward_compatible_with_existing_fields(self) -> None:
        """Existing fields still work alongside new fields."""
        req = ScanRequest(
            preset="sp500",
            max_price=1000.0,
            min_dte=30,
            max_dte=60,
        )
        assert req.preset == "sp500"
        assert req.max_price == 1000.0
        assert req.min_dte == 30
        assert req.max_dte == 60


class TestPresetInfo:
    """Tests for PresetInfo schema."""

    def test_preset_info_construction(self) -> None:
        """PresetInfo accepts all required fields."""
        info = PresetInfo(
            preset="sp500",
            label="S&P 500",
            description="S&P 500 constituents",
            estimated_count=503,
        )
        assert info.preset == "sp500"
        assert info.label == "S&P 500"
        assert info.description == "S&P 500 constituents"
        assert info.estimated_count == 503

    def test_preset_info_serialization_roundtrip(self) -> None:
        """PresetInfo survives JSON roundtrip."""
        info = PresetInfo(
            preset="nasdaq100",
            label="NASDAQ-100",
            description="NASDAQ-100 large-cap tech-heavy index",
            estimated_count=100,
        )
        json_str = info.model_dump_json()
        restored = PresetInfo.model_validate_json(json_str)
        assert restored == info

    def test_preset_info_model_dump(self) -> None:
        """model_dump() returns expected dict shape."""
        info = PresetInfo(
            preset="full",
            label="Full Universe",
            description="All CBOE optionable tickers",
            estimated_count=5000,
        )
        data = info.model_dump()
        assert data == {
            "preset": "full",
            "label": "Full Universe",
            "description": "All CBOE optionable tickers",
            "estimated_count": 5000,
        }

    def test_preset_info_requires_all_fields(self) -> None:
        """PresetInfo requires all four fields."""
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PresetInfo(preset="sp500")  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            PresetInfo(preset="sp500", label="S&P 500")  # type: ignore[call-arg]
