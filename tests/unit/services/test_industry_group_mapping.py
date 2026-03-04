"""Tests for industry group mapping and filtering helpers.

Covers:
  - build_industry_group_map with known, unknown, empty, and case-insensitive inputs.
  - filter_by_industry_groups with matching, empty filter, and no-match cases.
  - Hyphenated yfinance industry strings (em dash and ASCII dash variants).
"""

from __future__ import annotations

from options_arena.models.enums import GICSIndustryGroup
from options_arena.services.universe import (
    build_industry_group_map,
    filter_by_industry_groups,
)

# ---------------------------------------------------------------------------
# build_industry_group_map tests
# ---------------------------------------------------------------------------


class TestBuildIndustryGroupMap:
    """build_industry_group_map maps yfinance industry strings to GICSIndustryGroup."""

    def test_maps_known_industry(self) -> None:
        """Verify 'Semiconductors' maps to SEMICONDUCTORS_EQUIPMENT."""
        data = {"NVDA": "Semiconductors"}
        result = build_industry_group_map(data)
        assert result == {"NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT}

    def test_maps_hyphenated_industry_em_dash(self) -> None:
        """Verify 'Software\u2014Application' (em dash) maps to SOFTWARE_SERVICES."""
        data = {"CRM": "Software\u2014Application"}
        result = build_industry_group_map(data)
        assert result == {"CRM": GICSIndustryGroup.SOFTWARE_SERVICES}

    def test_maps_hyphenated_industry_ascii_dash(self) -> None:
        """Verify 'Software - Application' (ASCII dash) maps to SOFTWARE_SERVICES."""
        data = {"ORCL": "Software - Application"}
        result = build_industry_group_map(data)
        assert result == {"ORCL": GICSIndustryGroup.SOFTWARE_SERVICES}

    def test_maps_internet_retail_to_retailing(self) -> None:
        """Verify 'Internet Retail' maps to RETAILING."""
        data = {"AMZN": "Internet Retail"}
        result = build_industry_group_map(data)
        assert result == {"AMZN": GICSIndustryGroup.RETAILING}

    def test_maps_biotechnology_to_pharma_biotech(self) -> None:
        """Verify 'Biotechnology' maps to PHARMA_BIOTECH."""
        data = {"MRNA": "Biotechnology"}
        result = build_industry_group_map(data)
        assert result == {"MRNA": GICSIndustryGroup.PHARMA_BIOTECH}

    def test_maps_banks_diversified(self) -> None:
        """Verify 'Banks\u2014Diversified' maps to BANKS."""
        data = {"JPM": "Banks\u2014Diversified"}
        result = build_industry_group_map(data)
        assert result == {"JPM": GICSIndustryGroup.BANKS}

    def test_unknown_industry_excluded(self) -> None:
        """Verify unmapped industry is excluded from result dict, not an error."""
        data = {
            "NVDA": "Semiconductors",
            "FAKE": "Underwater Basket Weaving",
        }
        result = build_industry_group_map(data)
        assert "NVDA" in result
        assert "FAKE" not in result
        assert len(result) == 1

    def test_empty_input(self) -> None:
        """Verify empty dict input returns empty dict."""
        result = build_industry_group_map({})
        assert result == {}

    def test_case_insensitive(self) -> None:
        """Verify 'semiconductors' (lowercase) maps correctly."""
        data = {"NVDA": "semiconductors"}
        result = build_industry_group_map(data)
        assert result == {"NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT}

    def test_whitespace_handling(self) -> None:
        """Verify leading/trailing whitespace is stripped before lookup."""
        data = {"NVDA": "  Semiconductors  "}
        result = build_industry_group_map(data)
        assert result == {"NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT}

    def test_multiple_tickers(self) -> None:
        """Verify multiple tickers are all mapped correctly."""
        data = {
            "NVDA": "Semiconductors",
            "CRM": "Software\u2014Application",
            "JPM": "Banks\u2014Diversified",
            "XOM": "Oil & Gas Integrated",
        }
        result = build_industry_group_map(data)
        assert result["NVDA"] == GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT
        assert result["CRM"] == GICSIndustryGroup.SOFTWARE_SERVICES
        assert result["JPM"] == GICSIndustryGroup.BANKS
        assert result["XOM"] == GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS
        assert len(result) == 4


# ---------------------------------------------------------------------------
# GICS Sub-Industry (CSV) string mapping tests
# ---------------------------------------------------------------------------


class TestGICSSubIndustryMapping:
    """GICS Sub-Industry strings from S&P 500 CSV map through build_industry_group_map."""

    def test_application_software(self) -> None:
        result = build_industry_group_map({"MSFT": "Application Software"})
        assert result["MSFT"] == GICSIndustryGroup.SOFTWARE_SERVICES

    def test_diversified_banks(self) -> None:
        result = build_industry_group_map({"JPM": "Diversified Banks"})
        assert result["JPM"] == GICSIndustryGroup.BANKS

    def test_regional_banks(self) -> None:
        result = build_industry_group_map({"KEY": "Regional Banks"})
        assert result["KEY"] == GICSIndustryGroup.BANKS

    def test_technology_hardware(self) -> None:
        result = build_industry_group_map({"AAPL": "Technology Hardware Storage & Peripherals"})
        assert result["AAPL"] == GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT

    def test_managed_health_care(self) -> None:
        result = build_industry_group_map({"UNH": "Managed Health Care"})
        assert result["UNH"] == GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES

    def test_interactive_media(self) -> None:
        result = build_industry_group_map({"GOOG": "Interactive Media & Services"})
        assert result["GOOG"] == GICSIndustryGroup.MEDIA_ENTERTAINMENT

    def test_broadline_retail(self) -> None:
        result = build_industry_group_map({"AMZN": "Broadline Retail"})
        assert result["AMZN"] == GICSIndustryGroup.RETAILING

    def test_electric_utilities(self) -> None:
        result = build_industry_group_map({"NEE": "Electric Utilities"})
        assert result["NEE"] == GICSIndustryGroup.UTILITIES

    def test_data_center_reits(self) -> None:
        result = build_industry_group_map({"EQIX": "Data Center REITs"})
        assert result["EQIX"] == GICSIndustryGroup.EQUITY_REITS

    def test_integrated_oil_gas(self) -> None:
        result = build_industry_group_map({"XOM": "Integrated Oil & Gas"})
        assert result["XOM"] == GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS

    def test_life_sciences(self) -> None:
        result = build_industry_group_map({"TMO": "Life Sciences Tools & Services"})
        assert result["TMO"] == GICSIndustryGroup.PHARMA_BIOTECH

    def test_passenger_airlines(self) -> None:
        result = build_industry_group_map({"DAL": "Passenger Airlines"})
        assert result["DAL"] == GICSIndustryGroup.TRANSPORTATION

    def test_semiconductor_materials_equipment(self) -> None:
        result = build_industry_group_map({"AMAT": "Semiconductor Materials & Equipment"})
        assert result["AMAT"] == GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT

    def test_transaction_payment_processing(self) -> None:
        result = build_industry_group_map({"V": "Transaction & Payment Processing Services"})
        assert result["V"] == GICSIndustryGroup.DIVERSIFIED_FINANCIALS

    def test_construction_materials(self) -> None:
        result = build_industry_group_map({"VMC": "Construction Materials"})
        assert result["VMC"] == GICSIndustryGroup.MATERIALS


# ---------------------------------------------------------------------------
# filter_by_industry_groups tests
# ---------------------------------------------------------------------------


class TestFilterByIndustryGroups:
    """filter_by_industry_groups filters tickers by industry group membership."""

    def test_filters_matching_tickers(self) -> None:
        """Verify only tickers in selected groups are returned."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
            "JPM": GICSIndustryGroup.BANKS,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "CRM", "JPM"],
            industry_groups=[GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT],
            ig_map=ig_map,
        )
        assert result == ["NVDA"]

    def test_multiple_groups_or_logic(self) -> None:
        """Verify multiple industry groups use OR logic."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
            "JPM": GICSIndustryGroup.BANKS,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "CRM", "JPM"],
            industry_groups=[
                GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
                GICSIndustryGroup.SOFTWARE_SERVICES,
            ],
            ig_map=ig_map,
        )
        assert result == ["NVDA", "CRM"]

    def test_empty_filter_returns_all(self) -> None:
        """Verify empty group list returns all tickers unchanged."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "JPM": GICSIndustryGroup.BANKS,
        }
        tickers = ["NVDA", "JPM", "TSLA"]
        result = filter_by_industry_groups(
            tickers=tickers,
            industry_groups=[],
            ig_map=ig_map,
        )
        assert result == tickers

    def test_no_matches_returns_empty(self) -> None:
        """Verify empty result when no tickers match selected groups."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "CRM"],
            industry_groups=[GICSIndustryGroup.BANKS],
            ig_map=ig_map,
        )
        assert result == []

    def test_ticker_not_in_map_excluded(self) -> None:
        """Verify tickers not in ig_map are excluded when filtering is active."""
        ig_map = {
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
        }
        result = filter_by_industry_groups(
            tickers=["NVDA", "UNKNOWN"],
            industry_groups=[GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT],
            ig_map=ig_map,
        )
        assert result == ["NVDA"]

    def test_preserves_order(self) -> None:
        """Verify filter preserves input order of tickers."""
        ig_map = {
            "CRM": GICSIndustryGroup.SOFTWARE_SERVICES,
            "NVDA": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
        }
        result = filter_by_industry_groups(
            tickers=["CRM", "NVDA"],
            industry_groups=[
                GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
                GICSIndustryGroup.SOFTWARE_SERVICES,
            ],
            ig_map=ig_map,
        )
        assert result == ["CRM", "NVDA"]

    def test_empty_tickers_returns_empty(self) -> None:
        """Verify empty ticker list returns empty."""
        result = filter_by_industry_groups(
            tickers=[],
            industry_groups=[GICSIndustryGroup.BANKS],
            ig_map={},
        )
        assert result == []
