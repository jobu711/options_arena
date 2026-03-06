"""Tests for new ScanPreset members added in #285 (pre-scan epic)."""

from __future__ import annotations

from enum import StrEnum

from options_arena.models import ScanPreset


class TestScanPresetNewMembers:
    """Tests for NASDAQ100, RUSSELL2000, MOST_ACTIVE enum members."""

    def test_scan_preset_has_exactly_six_members(self) -> None:
        """ScanPreset should have 6 members after adding 3 new presets."""
        assert len(ScanPreset) == 6

    def test_scan_preset_is_str_enum(self) -> None:
        assert issubclass(ScanPreset, StrEnum)

    def test_nasdaq100_value(self) -> None:
        assert ScanPreset.NASDAQ100 == "nasdaq100"
        assert ScanPreset.NASDAQ100.value == "nasdaq100"

    def test_russell2000_value(self) -> None:
        assert ScanPreset.RUSSELL2000 == "russell2000"
        assert ScanPreset.RUSSELL2000.value == "russell2000"

    def test_most_active_value(self) -> None:
        assert ScanPreset.MOST_ACTIVE == "most_active"
        assert ScanPreset.MOST_ACTIVE.value == "most_active"

    def test_new_presets_string_serialization(self) -> None:
        """StrEnum members serialize to their string value."""
        assert str(ScanPreset.NASDAQ100) == "nasdaq100"
        assert str(ScanPreset.RUSSELL2000) == "russell2000"
        assert str(ScanPreset.MOST_ACTIVE) == "most_active"

    def test_new_presets_roundtrip(self) -> None:
        """Verify string -> enum -> string roundtrip for new members."""
        for member in (ScanPreset.NASDAQ100, ScanPreset.RUSSELL2000, ScanPreset.MOST_ACTIVE):
            assert ScanPreset(str(member)) is member

    def test_exhaustive_iteration_includes_new_members(self) -> None:
        """All 6 members appear in iteration."""
        expected = {
            ScanPreset.FULL,
            ScanPreset.SP500,
            ScanPreset.ETFS,
            ScanPreset.NASDAQ100,
            ScanPreset.RUSSELL2000,
            ScanPreset.MOST_ACTIVE,
        }
        assert set(ScanPreset) == expected

    def test_original_members_unchanged(self) -> None:
        """Original 3 members still have their expected values."""
        assert ScanPreset.FULL == "full"
        assert ScanPreset.SP500 == "sp500"
        assert ScanPreset.ETFS == "etfs"
