"""Tests for ScanRequest industry_groups and themes fields (#230)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.api.schemas import ScanRequest
from options_arena.models.enums import GICSIndustryGroup


class TestScanRequestIndustryGroups:
    """Tests for industry_groups normalization on ScanRequest."""

    def test_default_empty(self) -> None:
        """Verify industry_groups defaults to empty list."""
        req = ScanRequest()
        assert req.industry_groups == []

    def test_normalize_canonical_value(self) -> None:
        """Verify canonical enum value is accepted."""
        req = ScanRequest(industry_groups=["Banks"])
        assert req.industry_groups == [GICSIndustryGroup.BANKS]

    def test_normalize_via_alias(self) -> None:
        """Verify short alias is resolved via INDUSTRY_GROUP_ALIASES."""
        req = ScanRequest(industry_groups=["semis"])
        assert req.industry_groups == [GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT]

    def test_normalize_case_insensitive(self) -> None:
        """Verify mixed case input is normalized correctly."""
        req = ScanRequest(industry_groups=["BANKS"])
        assert req.industry_groups == [GICSIndustryGroup.BANKS]

    def test_deduplicate(self) -> None:
        """Verify duplicates are removed."""
        req = ScanRequest(industry_groups=["banks", "Banks"])
        assert len(req.industry_groups) == 1
        assert req.industry_groups == [GICSIndustryGroup.BANKS]

    def test_multiple_groups(self) -> None:
        """Verify multiple distinct groups are accepted."""
        req = ScanRequest(industry_groups=["banks", "insurance", "semis"])
        assert GICSIndustryGroup.BANKS in req.industry_groups
        assert GICSIndustryGroup.INSURANCE in req.industry_groups
        assert GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT in req.industry_groups
        assert len(req.industry_groups) == 3

    def test_reject_invalid_group(self) -> None:
        """Verify ValidationError for unknown industry group."""
        with pytest.raises(ValidationError, match="Unknown industry group"):
            ScanRequest(industry_groups=["nonexistent_group_xyz"])

    def test_accepts_enum_directly(self) -> None:
        """Verify GICSIndustryGroup enum values are accepted."""
        req = ScanRequest(industry_groups=[GICSIndustryGroup.BANKS])
        assert req.industry_groups == [GICSIndustryGroup.BANKS]


class TestScanRequestThemes:
    """Tests for themes field on ScanRequest."""

    def test_default_empty(self) -> None:
        """Verify themes defaults to empty list."""
        req = ScanRequest()
        assert req.themes == []

    def test_themes_passthrough(self) -> None:
        """Verify valid theme names are accepted."""
        req = ScanRequest(themes=["AI & Machine Learning", "Clean Energy"])
        assert req.themes == ["AI & Machine Learning", "Clean Energy"]

    def test_themes_deduplicate(self) -> None:
        """Verify duplicate theme names are removed."""
        req = ScanRequest(themes=["Cybersecurity", "Cybersecurity"])
        assert req.themes == ["Cybersecurity"]

    def test_themes_reject_invalid(self) -> None:
        """Verify ValidationError for unknown theme name."""
        with pytest.raises(ValidationError, match="Unknown theme"):
            ScanRequest(themes=["nonexistent_theme_xyz"])

    def test_combined_with_industry_groups(self) -> None:
        """Verify industry_groups and themes can be set together."""
        req = ScanRequest(
            industry_groups=["semis"],
            themes=["AI & Machine Learning"],
        )
        assert req.industry_groups == [GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT]
        assert req.themes == ["AI & Machine Learning"]


class TestScanRequestBackwardCompatibility:
    """Verify new fields don't break existing ScanRequest usage."""

    def test_all_new_fields_default(self) -> None:
        """Verify new fields default without affecting existing fields."""
        req = ScanRequest()
        assert req.industry_groups == []
        assert req.themes == []
        assert req.sectors == []
        assert req.preset.value == "sp500"
