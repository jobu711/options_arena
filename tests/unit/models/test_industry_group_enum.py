"""Unit tests for GICSIndustryGroup enum, INDUSTRY_GROUP_ALIASES, and SECTOR_TO_INDUSTRY_GROUPS.

Tests:
  - Exactly 26 members matching GICS 2023 standard
  - StrEnum subclass check
  - Construction from canonical values
  - Alias resolution: lowercase, short names, hyphenated, underscored, yfinance
  - SECTOR_TO_INDUSTRY_GROUPS covers all 11 sectors
  - Every industry group maps to exactly one parent sector
  - Invalid value raises ValueError
"""

import pytest

from options_arena.models import (
    INDUSTRY_GROUP_ALIASES,
    SECTOR_TO_INDUSTRY_GROUPS,
    GICSIndustryGroup,
    GICSSector,
)

# ---------------------------------------------------------------------------
# GICSIndustryGroup enum basics
# ---------------------------------------------------------------------------


class TestGICSIndustryGroup:
    def test_enum_has_26_members(self) -> None:
        """Verify exactly 26 industry groups defined (GICS 2023 standard).

        26 groups across 11 sectors. Materials and Utilities each have a single
        industry group sharing their sector name.
        """
        assert len(GICSIndustryGroup) == 26

    def test_is_str_enum(self) -> None:
        """Verify GICSIndustryGroup is a StrEnum subclass."""
        from enum import StrEnum

        assert issubclass(GICSIndustryGroup, StrEnum)

    def test_construct_from_canonical_value(self) -> None:
        """Verify GICSIndustryGroup('Software & Services') works."""
        assert GICSIndustryGroup("Software & Services") is GICSIndustryGroup.SOFTWARE_SERVICES
        assert GICSIndustryGroup("Banks") is GICSIndustryGroup.BANKS
        assert (
            GICSIndustryGroup("Semiconductors & Semiconductor Equipment")
            is GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        )

    def test_canonical_values_match_gics_2023(self) -> None:
        """Verify canonical values match GICS 2023 standard names."""
        expected_values = {
            "Telecommunication Services",
            "Media & Entertainment",
            "Automobiles & Components",
            "Consumer Durables & Apparel",
            "Consumer Services",
            "Retailing",
            "Food & Staples Retailing",
            "Food Beverage & Tobacco",
            "Household & Personal Products",
            "Energy Equipment & Services",
            "Oil Gas & Consumable Fuels",
            "Banks",
            "Diversified Financials",
            "Insurance",
            "Health Care Equipment & Services",
            "Pharmaceuticals Biotechnology & Life Sciences",
            "Capital Goods",
            "Commercial & Professional Services",
            "Transportation",
            "Semiconductors & Semiconductor Equipment",
            "Software & Services",
            "Technology Hardware & Equipment",
            "Materials",
            "Equity Real Estate Investment Trusts",
            "Real Estate Management & Development",
            "Utilities",
        }
        actual_values = {g.value for g in GICSIndustryGroup}
        assert actual_values == expected_values
        assert len(expected_values) == 26

    def test_string_serialization(self) -> None:
        """Verify string conversion matches enum value."""
        assert str(GICSIndustryGroup.SOFTWARE_SERVICES) == "Software & Services"
        assert str(GICSIndustryGroup.BANKS) == "Banks"

    def test_invalid_value_raises(self) -> None:
        """Verify ValueError for unknown industry group string."""
        with pytest.raises(ValueError):
            GICSIndustryGroup("Nonexistent Group")


# ---------------------------------------------------------------------------
# INDUSTRY_GROUP_ALIASES
# ---------------------------------------------------------------------------


class TestIndustryGroupAliases:
    def test_all_canonical_lowercase_present(self) -> None:
        """Every canonical industry group name (lowered) should be in aliases."""
        for group in GICSIndustryGroup:
            key = group.value.lower()
            assert key in INDUSTRY_GROUP_ALIASES, f"Missing canonical alias for {group.value!r}"
            assert INDUSTRY_GROUP_ALIASES[key] is group

    def test_alias_resolution_short_names(self) -> None:
        """Verify short aliases resolve to correct groups."""
        aliases = INDUSTRY_GROUP_ALIASES
        assert aliases["semiconductors"] is GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        assert aliases["software"] is GICSIndustryGroup.SOFTWARE_SERVICES
        assert aliases["banks"] is GICSIndustryGroup.BANKS
        assert aliases["pharma"] is GICSIndustryGroup.PHARMA_BIOTECH
        assert aliases["biotech"] is GICSIndustryGroup.PHARMA_BIOTECH
        assert aliases["semis"] is GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        assert aliases["reits"] is GICSIndustryGroup.EQUITY_REITS
        assert aliases["media"] is GICSIndustryGroup.MEDIA_ENTERTAINMENT
        assert aliases["retail"] is GICSIndustryGroup.RETAILING
        assert aliases["hardware"] is GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT

    def test_alias_resolution_hyphenated(self) -> None:
        """Verify hyphenated variants resolve correctly."""
        assert INDUSTRY_GROUP_ALIASES["software-services"] is GICSIndustryGroup.SOFTWARE_SERVICES
        assert (
            INDUSTRY_GROUP_ALIASES["semiconductors-equipment"]
            is GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        )
        assert INDUSTRY_GROUP_ALIASES["pharma-biotech"] is GICSIndustryGroup.PHARMA_BIOTECH
        assert INDUSTRY_GROUP_ALIASES["capital-goods"] is GICSIndustryGroup.CAPITAL_GOODS

    def test_alias_resolution_underscored(self) -> None:
        """Verify underscored variants resolve correctly."""
        assert INDUSTRY_GROUP_ALIASES["software_services"] is GICSIndustryGroup.SOFTWARE_SERVICES
        assert (
            INDUSTRY_GROUP_ALIASES["semiconductors_equipment"]
            is GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        )
        assert INDUSTRY_GROUP_ALIASES["pharma_biotech"] is GICSIndustryGroup.PHARMA_BIOTECH
        assert INDUSTRY_GROUP_ALIASES["capital_goods"] is GICSIndustryGroup.CAPITAL_GOODS

    def test_yfinance_industry_mappings(self) -> None:
        """Verify yfinance industry field values resolve correctly."""
        # Software
        assert (
            INDUSTRY_GROUP_ALIASES["software\u2014application"]
            is GICSIndustryGroup.SOFTWARE_SERVICES
        )
        assert (
            INDUSTRY_GROUP_ALIASES["software - application"] is GICSIndustryGroup.SOFTWARE_SERVICES
        )
        # Retail
        assert INDUSTRY_GROUP_ALIASES["internet retail"] is GICSIndustryGroup.RETAILING
        # Biotech / Pharma
        assert INDUSTRY_GROUP_ALIASES["biotechnology"] is GICSIndustryGroup.PHARMA_BIOTECH
        assert (
            INDUSTRY_GROUP_ALIASES["drug manufacturers\u2014general"]
            is GICSIndustryGroup.PHARMA_BIOTECH
        )
        # Autos
        assert (
            INDUSTRY_GROUP_ALIASES["auto manufacturers"]
            is GICSIndustryGroup.AUTOMOBILES_COMPONENTS
        )
        # Capital Goods
        assert INDUSTRY_GROUP_ALIASES["aerospace & defense"] is GICSIndustryGroup.CAPITAL_GOODS
        # Transportation
        assert INDUSTRY_GROUP_ALIASES["airlines"] is GICSIndustryGroup.TRANSPORTATION
        assert INDUSTRY_GROUP_ALIASES["railroads"] is GICSIndustryGroup.TRANSPORTATION
        # Banks
        assert INDUSTRY_GROUP_ALIASES["banks\u2014diversified"] is GICSIndustryGroup.BANKS
        # Financials
        assert (
            INDUSTRY_GROUP_ALIASES["credit services"] is GICSIndustryGroup.DIVERSIFIED_FINANCIALS
        )

    def test_all_aliases_map_to_valid_group(self) -> None:
        """Every alias value must be a valid GICSIndustryGroup member."""
        for alias, group in INDUSTRY_GROUP_ALIASES.items():
            assert isinstance(group, GICSIndustryGroup), f"Alias {alias!r} maps to invalid group"


# ---------------------------------------------------------------------------
# SECTOR_TO_INDUSTRY_GROUPS
# ---------------------------------------------------------------------------


class TestSectorToIndustryGroups:
    def test_covers_all_11_sectors(self) -> None:
        """Verify all 11 GICSSector values have entries in SECTOR_TO_INDUSTRY_GROUPS."""
        for sector in GICSSector:
            assert sector in SECTOR_TO_INDUSTRY_GROUPS, (
                f"Sector {sector.value!r} missing from SECTOR_TO_INDUSTRY_GROUPS"
            )

    def test_no_extra_sectors(self) -> None:
        """Verify no extra keys beyond the 11 sectors."""
        assert set(SECTOR_TO_INDUSTRY_GROUPS.keys()) == set(GICSSector)

    def test_all_groups_mapped_to_exactly_one_sector(self) -> None:
        """Verify every GICSIndustryGroup appears in exactly one sector mapping."""
        group_to_sector: dict[GICSIndustryGroup, GICSSector] = {}
        for sector, groups in SECTOR_TO_INDUSTRY_GROUPS.items():
            for group in groups:
                assert group not in group_to_sector, (
                    f"Industry group {group.value!r} mapped to both "
                    f"{group_to_sector[group].value!r} and {sector.value!r}"
                )
                group_to_sector[group] = sector

        # Every enum member must appear
        assert set(group_to_sector.keys()) == set(GICSIndustryGroup)

    def test_total_groups_sum_to_26(self) -> None:
        """Verify all sector mappings together contain exactly 26 groups."""
        total = sum(len(groups) for groups in SECTOR_TO_INDUSTRY_GROUPS.values())
        assert total == 26

    def test_communication_services_groups(self) -> None:
        """Verify Communication Services has the correct 2 groups."""
        groups = SECTOR_TO_INDUSTRY_GROUPS[GICSSector.COMMUNICATION_SERVICES]
        assert len(groups) == 2
        assert GICSIndustryGroup.TELECOMMUNICATION_SERVICES in groups
        assert GICSIndustryGroup.MEDIA_ENTERTAINMENT in groups

    def test_information_technology_groups(self) -> None:
        """Verify Information Technology has the correct 3 groups."""
        groups = SECTOR_TO_INDUSTRY_GROUPS[GICSSector.INFORMATION_TECHNOLOGY]
        assert len(groups) == 3
        assert GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT in groups
        assert GICSIndustryGroup.SOFTWARE_SERVICES in groups
        assert GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT in groups

    def test_materials_has_single_group(self) -> None:
        """Verify Materials sector has exactly 1 group."""
        groups = SECTOR_TO_INDUSTRY_GROUPS[GICSSector.MATERIALS]
        assert len(groups) == 1
        assert GICSIndustryGroup.MATERIALS in groups

    def test_utilities_has_single_group(self) -> None:
        """Verify Utilities sector has exactly 1 group."""
        groups = SECTOR_TO_INDUSTRY_GROUPS[GICSSector.UTILITIES]
        assert len(groups) == 1
        assert GICSIndustryGroup.UTILITIES in groups
