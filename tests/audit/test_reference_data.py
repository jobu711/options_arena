"""Schema validation tests for audit reference data JSON fixtures.

Validates that all JSON fixtures:
- Load correctly as valid JSON
- Contain required fields (source, parameters, expected values)
- Have numeric parameter types
- Cover all expected function categories
- Have academic source citations
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent / "reference_data"
PRICING_PATH = REFERENCE_DIR / "pricing_known_values.json"
INDICATOR_PATH = REFERENCE_DIR / "indicator_known_values.json"
SCORING_PATH = REFERENCE_DIR / "scoring_known_values.json"
ORCHESTRATION_PATH = REFERENCE_DIR / "orchestration_known_values.json"
QUANTLIB_PATH = REFERENCE_DIR / "quantlib_baselines.json"


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file and return its contents."""
    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _is_numeric(value: object) -> bool:
    """Check if a value is numeric (int or float)."""
    return isinstance(value, (int, float))


def _has_source(entry: dict[str, Any]) -> bool:
    """Check if an entry has a non-empty source field."""
    return isinstance(entry.get("source"), str) and len(entry["source"]) > 0


def _validate_numeric_params(params: dict[str, Any]) -> list[str]:
    """Validate that standard pricing parameters are numeric."""
    errors: list[str] = []
    numeric_keys = {"S", "K", "T", "r", "q", "sigma"}
    for key in numeric_keys:
        if key in params:
            val = params[key]
            if not _is_numeric(val):
                errors.append(f"Parameter '{key}' is not numeric: {val!r}")
            elif isinstance(val, float) and not math.isfinite(val):
                errors.append(f"Parameter '{key}' is not finite: {val}")
    return errors


# ---------------------------------------------------------------------------
# Pricing Known Values
# ---------------------------------------------------------------------------


class TestPricingKnownValues:
    """Validate pricing_known_values.json structure and content."""

    def test_json_loads(self) -> None:
        """Verify pricing JSON is valid and loads without error."""
        data = _load_json(PRICING_PATH)
        assert isinstance(data, dict)
        assert "metadata" in data

    def test_has_required_categories(self) -> None:
        """Verify all pricing function categories are present."""
        data = _load_json(PRICING_PATH)
        required_categories = [
            "bsm_price",
            "bsm_greeks",
            "bsm_second_order_greeks",
            "bsm_iv_round_trip",
            "baw_price",
        ]
        for cat in required_categories:
            assert cat in data, f"Missing category: {cat}"
            assert len(data[cat]) > 0, f"Category '{cat}' is empty"

    def test_bsm_price_has_minimum_entries(self) -> None:
        """Verify BSM price has at least 20 parameter combinations."""
        data = _load_json(PRICING_PATH)
        assert len(data["bsm_price"]) >= 20

    def test_bsm_greeks_has_minimum_entries(self) -> None:
        """Verify BSM Greeks has at least 20 parameter combinations."""
        data = _load_json(PRICING_PATH)
        assert len(data["bsm_greeks"]) >= 20

    def test_baw_price_has_minimum_entries(self) -> None:
        """Verify BAW price has at least 20 parameter combinations."""
        data = _load_json(PRICING_PATH)
        assert len(data["baw_price"]) >= 20

    def test_bsm_price_entries_have_source(self) -> None:
        """Every BSM price entry must cite its academic source."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_price"]):
            assert _has_source(entry), f"bsm_price[{i}] missing source field"

    def test_bsm_greeks_entries_have_source(self) -> None:
        """Every BSM Greeks entry must cite its academic source."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_greeks"]):
            assert _has_source(entry), f"bsm_greeks[{i}] missing source field"

    def test_baw_price_entries_have_source(self) -> None:
        """Every BAW price entry must cite its academic source."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["baw_price"]):
            assert _has_source(entry), f"baw_price[{i}] missing source field"

    def test_second_order_greeks_entries_have_source(self) -> None:
        """Every second-order Greeks entry must cite its academic source."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_second_order_greeks"]):
            assert _has_source(entry), f"bsm_second_order_greeks[{i}] missing source"

    def test_iv_round_trip_entries_have_source(self) -> None:
        """Every IV round-trip entry must cite its academic source."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_iv_round_trip"]):
            assert _has_source(entry), f"bsm_iv_round_trip[{i}] missing source"

    def test_bsm_price_parameter_types(self) -> None:
        """All pricing parameters must be numeric."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_price"]):
            params = entry["parameters"]
            errors = _validate_numeric_params(params)
            assert not errors, f"bsm_price[{i}]: {errors}"

    def test_bsm_greeks_parameter_types(self) -> None:
        """All Greeks parameters must be numeric."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_greeks"]):
            params = entry["parameters"]
            errors = _validate_numeric_params(params)
            assert not errors, f"bsm_greeks[{i}]: {errors}"

    def test_bsm_price_expected_values_are_numeric(self) -> None:
        """Expected call/put prices must be numeric."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_price"]):
            expected = entry["expected"]
            assert _is_numeric(expected["call"]), f"bsm_price[{i}].call not numeric"
            assert _is_numeric(expected["put"]), f"bsm_price[{i}].put not numeric"

    def test_bsm_greeks_expected_values_are_numeric(self) -> None:
        """Expected Greeks values must be numeric."""
        data = _load_json(PRICING_PATH)
        greek_keys = ["delta_call", "delta_put", "gamma", "vega", "theta_call", "theta_put"]
        for i, entry in enumerate(data["bsm_greeks"]):
            expected = entry["expected"]
            for key in greek_keys:
                assert _is_numeric(expected[key]), f"bsm_greeks[{i}].{key} not numeric"

    def test_second_order_greeks_expected_are_numeric(self) -> None:
        """Expected second-order Greeks must be numeric."""
        data = _load_json(PRICING_PATH)
        for i, entry in enumerate(data["bsm_second_order_greeks"]):
            expected = entry["expected"]
            for key in ("vanna", "charm", "vomma"):
                assert _is_numeric(expected[key]), (
                    f"bsm_second_order_greeks[{i}].{key} not numeric"
                )


# ---------------------------------------------------------------------------
# Indicator Known Values
# ---------------------------------------------------------------------------


class TestIndicatorKnownValues:
    """Validate indicator_known_values.json structure and content."""

    def test_json_loads(self) -> None:
        """Verify indicator JSON is valid and loads without error."""
        data = _load_json(INDICATOR_PATH)
        assert isinstance(data, dict)
        assert "metadata" in data

    def test_all_core_indicators_covered(self) -> None:
        """Verify all core indicator functions have reference values."""
        data = _load_json(INDICATOR_PATH)
        required_indicators = [
            "rsi",
            "macd",
            "bollinger_bands",
            "adx",
            "atr_percent",
        ]
        for indicator in required_indicators:
            assert indicator in data, f"Missing indicator: {indicator}"
            assert len(data[indicator]) >= 3, f"Indicator '{indicator}' has fewer than 3 entries"

    def test_rsi_entries_have_source(self) -> None:
        """Every RSI entry must cite its academic source."""
        data = _load_json(INDICATOR_PATH)
        for i, entry in enumerate(data["rsi"]):
            assert _has_source(entry), f"rsi[{i}] missing source field"

    def test_macd_entries_have_source(self) -> None:
        """Every MACD entry must cite its academic source."""
        data = _load_json(INDICATOR_PATH)
        for i, entry in enumerate(data["macd"]):
            assert _has_source(entry), f"macd[{i}] missing source field"

    def test_bollinger_bands_entries_have_source(self) -> None:
        """Every Bollinger Bands entry must cite its academic source."""
        data = _load_json(INDICATOR_PATH)
        for i, entry in enumerate(data["bollinger_bands"]):
            assert _has_source(entry), f"bollinger_bands[{i}] missing source field"

    def test_adx_entries_have_source(self) -> None:
        """Every ADX entry must cite its academic source."""
        data = _load_json(INDICATOR_PATH)
        for i, entry in enumerate(data["adx"]):
            assert _has_source(entry), f"adx[{i}] missing source field"

    def test_additional_indicators_present(self) -> None:
        """Verify additional indicators have reference values."""
        data = _load_json(INDICATOR_PATH)
        optional_indicators = [
            "williams_r",
            "stochastic_rsi",
            "rate_of_change",
        ]
        for indicator in optional_indicators:
            assert indicator in data, f"Missing optional indicator: {indicator}"

    def test_rsi_entries_have_expected(self) -> None:
        """RSI entries must have expected values."""
        data = _load_json(INDICATOR_PATH)
        for i, entry in enumerate(data["rsi"]):
            assert "expected" in entry, f"rsi[{i}] missing expected field"


# ---------------------------------------------------------------------------
# Scoring Known Values
# ---------------------------------------------------------------------------


class TestScoringKnownValues:
    """Validate scoring_known_values.json structure and content."""

    def test_json_loads(self) -> None:
        """Verify scoring JSON is valid and loads without error."""
        data = _load_json(SCORING_PATH)
        assert isinstance(data, dict)
        assert "metadata" in data

    def test_has_required_categories(self) -> None:
        """Verify all scoring function categories are present."""
        data = _load_json(SCORING_PATH)
        required = [
            "percentile_rank_normalize",
            "composite_score",
            "direction_determination",
        ]
        for cat in required:
            assert cat in data, f"Missing scoring category: {cat}"
            assert len(data[cat]) > 0, f"Category '{cat}' is empty"

    def test_direction_entries_have_source(self) -> None:
        """Every direction determination entry must cite its source."""
        data = _load_json(SCORING_PATH)
        for i, entry in enumerate(data["direction_determination"]):
            assert _has_source(entry), f"direction_determination[{i}] missing source"

    def test_direction_entries_have_expected(self) -> None:
        """Every direction entry must have expected direction."""
        data = _load_json(SCORING_PATH)
        for i, entry in enumerate(data["direction_determination"]):
            assert "expected" in entry, f"direction_determination[{i}] missing expected"
            expected = entry["expected"]
            assert "direction" in expected, (
                f"direction_determination[{i}] missing expected.direction"
            )

    def test_direction_has_minimum_entries(self) -> None:
        """Direction determination should have at least 5 test cases."""
        data = _load_json(SCORING_PATH)
        assert len(data["direction_determination"]) >= 5

    def test_inverted_indicators_documented(self) -> None:
        """Inverted indicators section must be present."""
        data = _load_json(SCORING_PATH)
        assert "inverted_indicators" in data
        assert len(data["inverted_indicators"]) > 0


# ---------------------------------------------------------------------------
# Orchestration Known Values
# ---------------------------------------------------------------------------


class TestOrchestrationKnownValues:
    """Validate orchestration_known_values.json structure and content."""

    def test_json_loads(self) -> None:
        """Verify orchestration JSON is valid and loads without error."""
        data = _load_json(ORCHESTRATION_PATH)
        assert isinstance(data, dict)
        assert "metadata" in data

    def test_has_required_categories(self) -> None:
        """Verify all orchestration function categories are present."""
        data = _load_json(ORCHESTRATION_PATH)
        required = [
            "log_odds_pool",
            "shannon_entropy",
            "agreement_score",
        ]
        for cat in required:
            assert cat in data, f"Missing orchestration category: {cat}"
            assert len(data[cat]) > 0, f"Category '{cat}' is empty"

    def test_log_odds_pool_entries_have_source(self) -> None:
        """Every log-odds pool entry must cite Bordley (1982)."""
        data = _load_json(ORCHESTRATION_PATH)
        for i, entry in enumerate(data["log_odds_pool"]):
            assert _has_source(entry), f"log_odds_pool[{i}] missing source"

    def test_log_odds_pool_entries_have_numeric_expected(self) -> None:
        """Log-odds pool expected values must be numeric or have value_finite flag."""
        data = _load_json(ORCHESTRATION_PATH)
        for i, entry in enumerate(data["log_odds_pool"]):
            expected = entry["expected"]
            has_value = "value" in expected and _is_numeric(expected["value"])
            has_flag = "value_finite" in expected
            assert has_value or has_flag, (
                f"log_odds_pool[{i}] expected has neither numeric value nor value_finite flag"
            )

    def test_shannon_entropy_entries_have_source(self) -> None:
        """Every Shannon entropy entry must cite its source."""
        data = _load_json(ORCHESTRATION_PATH)
        for i, entry in enumerate(data["shannon_entropy"]):
            assert _has_source(entry), f"shannon_entropy[{i}] missing source"

    def test_shannon_entropy_expected_numeric(self) -> None:
        """Shannon entropy expected values must be numeric."""
        data = _load_json(ORCHESTRATION_PATH)
        for i, entry in enumerate(data["shannon_entropy"]):
            expected = entry["expected"]
            assert "value" in expected and _is_numeric(expected["value"]), (
                f"shannon_entropy[{i}] expected.value not numeric"
            )

    def test_agreement_score_entries_have_source(self) -> None:
        """Every agreement score entry must cite its source."""
        data = _load_json(ORCHESTRATION_PATH)
        for i, entry in enumerate(data["agreement_score"]):
            assert _has_source(entry), f"agreement_score[{i}] missing source"

    def test_agreement_score_expected_numeric(self) -> None:
        """Agreement score expected values must be numeric."""
        data = _load_json(ORCHESTRATION_PATH)
        for i, entry in enumerate(data["agreement_score"]):
            expected = entry["expected"]
            assert "value" in expected and _is_numeric(expected["value"]), (
                f"agreement_score[{i}] expected.value not numeric"
            )

    def test_log_odds_pool_has_minimum_entries(self) -> None:
        """Log-odds pool should have at least 5 test cases."""
        data = _load_json(ORCHESTRATION_PATH)
        assert len(data["log_odds_pool"]) >= 5

    def test_shannon_entropy_has_minimum_entries(self) -> None:
        """Shannon entropy should have at least 5 test cases."""
        data = _load_json(ORCHESTRATION_PATH)
        assert len(data["shannon_entropy"]) >= 5

    def test_agreement_score_has_minimum_entries(self) -> None:
        """Agreement score should have at least 5 test cases."""
        data = _load_json(ORCHESTRATION_PATH)
        assert len(data["agreement_score"]) >= 5


# ---------------------------------------------------------------------------
# QuantLib Baselines
# ---------------------------------------------------------------------------


class TestQuantLibBaselines:
    """Validate quantlib_baselines.json structure and content."""

    def test_json_loads(self) -> None:
        """Verify QuantLib baselines JSON is valid."""
        data = _load_json(QUANTLIB_PATH)
        assert isinstance(data, dict)
        assert "metadata" in data
        assert "entries" in data

    def test_schema_matches_expected(self) -> None:
        """Verify JSON schema has metadata and entries arrays."""
        data = _load_json(QUANTLIB_PATH)
        metadata = data["metadata"]
        assert "description" in metadata
        assert "parameter_grid" in metadata
        assert isinstance(data["entries"], list)
        assert len(data["entries"]) > 0

    def test_entries_have_required_fields(self) -> None:
        """Every entry must have source, parameters, european, and american sections."""
        data = _load_json(QUANTLIB_PATH)
        for i, entry in enumerate(data["entries"]):
            assert _has_source(entry), f"entries[{i}] missing source"
            assert "parameters" in entry, f"entries[{i}] missing parameters"
            assert "european" in entry, f"entries[{i}] missing european"
            assert "american" in entry, f"entries[{i}] missing american"

    def test_parameter_types_numeric(self) -> None:
        """All parameters in entries must be numeric."""
        data = _load_json(QUANTLIB_PATH)
        for i, entry in enumerate(data["entries"]):
            errors = _validate_numeric_params(entry["parameters"])
            assert not errors, f"entries[{i}]: {errors}"

    def test_parameter_grid_documented(self) -> None:
        """Parameter grid in metadata must document all dimensions."""
        data = _load_json(QUANTLIB_PATH)
        grid = data["metadata"]["parameter_grid"]
        required_dims = ["S", "K", "T", "r", "q", "sigma"]
        for dim in required_dims:
            assert dim in grid, f"Missing parameter dimension: {dim}"
            assert isinstance(grid[dim], list), f"Grid dimension '{dim}' not a list"
            assert len(grid[dim]) > 0, f"Grid dimension '{dim}' is empty"

    def test_entries_have_european_prices(self) -> None:
        """European section should have call and put data."""
        data = _load_json(QUANTLIB_PATH)
        for i, entry in enumerate(data["entries"]):
            euro = entry["european"]
            assert "call" in euro or "put" in euro, (
                f"entries[{i}].european has neither call nor put"
            )

    def test_iv_round_trip_section_present(self) -> None:
        """Most entries should have IV round-trip data."""
        data = _load_json(QUANTLIB_PATH)
        has_iv = sum(1 for e in data["entries"] if "iv_round_trip" in e)
        assert has_iv > 0, "No entries have iv_round_trip section"


# ---------------------------------------------------------------------------
# Cross-fixture consistency
# ---------------------------------------------------------------------------


class TestCrossFixtureConsistency:
    """Validate consistency across all JSON fixture files."""

    _ALL_PATHS = (
        PRICING_PATH,
        INDICATOR_PATH,
        SCORING_PATH,
        ORCHESTRATION_PATH,
        QUANTLIB_PATH,
    )

    def test_all_fixtures_exist(self) -> None:
        """All required fixture files must exist."""
        for path in self._ALL_PATHS:
            assert path.exists(), f"Missing fixture file: {path.name}"

    def test_all_fixtures_have_metadata(self) -> None:
        """All fixture files must have a metadata section."""
        for path in self._ALL_PATHS:
            data = _load_json(path)
            assert "metadata" in data, f"{path.name} missing metadata"

    def test_pricing_and_quantlib_params_overlap(self) -> None:
        """At least one param combo in both pricing and QuantLib."""
        pricing = _load_json(PRICING_PATH)
        quantlib = _load_json(QUANTLIB_PATH)

        pricing_params: set[tuple[float, ...]] = set()
        for entry in pricing["bsm_price"]:
            p = entry["parameters"]
            pricing_params.add((p["S"], p["K"], p["T"], p["r"], p["q"], p["sigma"]))

        quantlib_params: set[tuple[float, ...]] = set()
        for entry in quantlib["entries"]:
            p = entry["parameters"]
            quantlib_params.add((p["S"], p["K"], p["T"], p["r"], p.get("q", 0.0), p["sigma"]))

        overlap = pricing_params & quantlib_params
        assert len(overlap) > 0, "No parameter overlap between pricing and QuantLib fixtures"

    def test_no_empty_fixtures(self) -> None:
        """No fixture file should be empty or have zero entries."""
        for path in self._ALL_PATHS:
            data = _load_json(path)
            # Every fixture: at least 2 top-level keys (metadata + data)
            assert len(data) >= 2, f"{path.name} has fewer than 2 top-level keys"
