"""Tests for audit framework models, enums, and MATH_FUNCTION_REGISTRY.

Covers:
- AuditSeverity and AuditLayer StrEnum values and roundtrip
- AuditFinding frozen model, JSON roundtrip, optional fields
- AuditLayerSummary coverage_pct validation (range, NaN rejection)
- AuditReport UTC validation, JSON roundtrip, frozen mutation
- MATH_FUNCTION_REGISTRY count, callability, no duplicates
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from options_arena.models.audit import AuditFinding, AuditLayerSummary, AuditReport
from options_arena.models.enums import AuditLayer, AuditSeverity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(**overrides: object) -> AuditFinding:
    """Create a minimal AuditFinding with optional overrides."""
    defaults: dict[str, object] = {
        "function_name": "bsm_price",
        "layer": AuditLayer.CORRECTNESS,
        "severity": AuditSeverity.INFO,
        "description": "Test finding",
    }
    defaults.update(overrides)
    return AuditFinding(**defaults)  # type: ignore[arg-type]


def _make_layer_summary(**overrides: object) -> AuditLayerSummary:
    """Create a minimal AuditLayerSummary with optional overrides."""
    defaults: dict[str, object] = {
        "layer": AuditLayer.CORRECTNESS,
        "total_functions": 10,
        "tested_functions": 8,
        "passed": 7,
        "failed": 1,
        "coverage_pct": 0.8,
        "findings": [],
    }
    defaults.update(overrides)
    return AuditLayerSummary(**defaults)  # type: ignore[arg-type]


def _make_report(**overrides: object) -> AuditReport:
    """Create a minimal AuditReport with optional overrides."""
    defaults: dict[str, object] = {
        "generated_at": datetime.now(UTC),
        "layers": [],
        "total_findings": 0,
        "critical_count": 0,
        "warning_count": 0,
        "info_count": 0,
    }
    defaults.update(overrides)
    return AuditReport(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# AuditSeverity enum tests
# ===========================================================================


class TestAuditSeverity:
    """Tests for the AuditSeverity StrEnum."""

    def test_values(self) -> None:
        """Verify all severity levels exist with correct string values."""
        assert AuditSeverity.CRITICAL == "critical"
        assert AuditSeverity.WARNING == "warning"
        assert AuditSeverity.INFO == "info"

    def test_member_count(self) -> None:
        """Verify exactly 3 severity levels."""
        assert len(AuditSeverity) == 3

    def test_strenum_roundtrip(self) -> None:
        """Verify StrEnum serializes/deserializes correctly."""
        for member in AuditSeverity:
            assert AuditSeverity(member.value) is member
            assert str(member) == member.value

    def test_is_strenum(self) -> None:
        """Verify AuditSeverity is a StrEnum subclass."""
        from enum import StrEnum

        assert issubclass(AuditSeverity, StrEnum)


# ===========================================================================
# AuditLayer enum tests
# ===========================================================================


class TestAuditLayer:
    """Tests for the AuditLayer StrEnum."""

    def test_values(self) -> None:
        """Verify all layer values exist with correct string values."""
        assert AuditLayer.CORRECTNESS == "correctness"
        assert AuditLayer.STABILITY == "stability"
        assert AuditLayer.PERFORMANCE == "performance"
        assert AuditLayer.DISCOVERY == "discovery"

    def test_member_count(self) -> None:
        """Verify exactly 4 audit layers."""
        assert len(AuditLayer) == 4

    def test_strenum_roundtrip(self) -> None:
        """Verify StrEnum serializes/deserializes correctly."""
        for member in AuditLayer:
            assert AuditLayer(member.value) is member

    def test_is_strenum(self) -> None:
        """Verify AuditLayer is a StrEnum subclass."""
        from enum import StrEnum

        assert issubclass(AuditLayer, StrEnum)


# ===========================================================================
# AuditFinding tests
# ===========================================================================


class TestAuditFinding:
    """Tests for the AuditFinding frozen Pydantic model."""

    def test_json_roundtrip(self) -> None:
        """Verify full JSON serialization/deserialization."""
        finding = _make_finding(
            expected_value=1.0,
            actual_value=1.001,
            tolerance=0.01,
            source="Hull (2018) Table 13.2",
            proposed_test="test_bsm_price_hull_table_13_2",
        )
        roundtripped = AuditFinding.model_validate_json(finding.model_dump_json())
        assert roundtripped == finding

    def test_frozen(self) -> None:
        """Verify frozen model rejects mutation."""
        finding = _make_finding()
        with pytest.raises(ValidationError):
            finding.function_name = "other_function"  # type: ignore[misc]

    def test_optional_fields(self) -> None:
        """Verify optional fields default to None."""
        finding = _make_finding()
        assert finding.expected_value is None
        assert finding.actual_value is None
        assert finding.tolerance is None
        assert finding.source is None
        assert finding.proposed_test is None

    def test_rejects_nan_expected_value(self) -> None:
        """Verify expected_value rejects NaN."""
        with pytest.raises(ValidationError, match="finite"):
            _make_finding(expected_value=float("nan"))

    def test_rejects_inf_actual_value(self) -> None:
        """Verify actual_value rejects Inf."""
        with pytest.raises(ValidationError, match="finite"):
            _make_finding(actual_value=float("inf"))

    def test_rejects_nan_tolerance(self) -> None:
        """Verify tolerance rejects NaN."""
        with pytest.raises(ValidationError, match="finite"):
            _make_finding(tolerance=float("nan"))

    def test_accepts_none_numeric_fields(self) -> None:
        """Verify None is accepted for optional numeric fields."""
        finding = _make_finding(
            expected_value=None,
            actual_value=None,
            tolerance=None,
        )
        assert finding.expected_value is None
        assert finding.actual_value is None
        assert finding.tolerance is None


# ===========================================================================
# AuditLayerSummary tests
# ===========================================================================


class TestAuditLayerSummary:
    """Tests for the AuditLayerSummary frozen Pydantic model."""

    def test_coverage_pct_validates_range(self) -> None:
        """Verify coverage_pct rejects values outside [0.0, 1.0]."""
        with pytest.raises(ValidationError, match="coverage_pct"):
            _make_layer_summary(coverage_pct=1.5)

        with pytest.raises(ValidationError, match="coverage_pct"):
            _make_layer_summary(coverage_pct=-0.1)

    def test_coverage_pct_rejects_nan(self) -> None:
        """Verify coverage_pct rejects NaN."""
        with pytest.raises(ValidationError, match="finite"):
            _make_layer_summary(coverage_pct=float("nan"))

    def test_coverage_pct_rejects_inf(self) -> None:
        """Verify coverage_pct rejects Inf."""
        with pytest.raises(ValidationError, match="finite"):
            _make_layer_summary(coverage_pct=float("inf"))

    def test_coverage_pct_boundary_values(self) -> None:
        """Verify coverage_pct accepts 0.0 and 1.0 (boundary values)."""
        summary_zero = _make_layer_summary(coverage_pct=0.0)
        assert summary_zero.coverage_pct == pytest.approx(0.0)

        summary_one = _make_layer_summary(coverage_pct=1.0)
        assert summary_one.coverage_pct == pytest.approx(1.0)

    def test_json_roundtrip(self) -> None:
        """Verify full JSON serialization/deserialization."""
        finding = _make_finding()
        summary = _make_layer_summary(findings=[finding])
        roundtripped = AuditLayerSummary.model_validate_json(summary.model_dump_json())
        assert roundtripped == summary

    def test_frozen(self) -> None:
        """Verify frozen model rejects mutation."""
        summary = _make_layer_summary()
        with pytest.raises(ValidationError):
            summary.total_functions = 99  # type: ignore[misc]

    def test_empty_findings_list(self) -> None:
        """Verify empty findings list is valid."""
        summary = _make_layer_summary(findings=[])
        assert summary.findings == []


# ===========================================================================
# AuditReport tests
# ===========================================================================


class TestAuditReport:
    """Tests for the AuditReport frozen Pydantic model."""

    def test_utc_validation(self) -> None:
        """Verify generated_at rejects naive datetimes."""
        with pytest.raises(ValidationError, match="UTC"):
            _make_report(generated_at=datetime(2024, 1, 1, 12, 0, 0))  # noqa: DTZ001

    def test_utc_validation_non_utc_tz(self) -> None:
        """Verify generated_at rejects non-UTC timezones."""
        from datetime import timedelta

        non_utc = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            _make_report(generated_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=non_utc))

    def test_utc_accepts_valid(self) -> None:
        """Verify generated_at accepts UTC datetimes."""
        report = _make_report(generated_at=datetime.now(UTC))
        assert report.generated_at.utcoffset() is not None
        assert report.generated_at.utcoffset().total_seconds() == 0.0

    def test_json_roundtrip(self) -> None:
        """Verify full JSON serialization/deserialization."""
        finding = _make_finding()
        summary = _make_layer_summary(findings=[finding])
        report = _make_report(
            layers=[summary],
            total_findings=1,
            info_count=1,
        )
        roundtripped = AuditReport.model_validate_json(report.model_dump_json())
        assert roundtripped == report

    def test_frozen(self) -> None:
        """Verify frozen model rejects mutation."""
        report = _make_report()
        with pytest.raises(ValidationError):
            report.total_findings = 99  # type: ignore[misc]

    def test_empty_layers(self) -> None:
        """Verify empty layers list is valid."""
        report = _make_report(layers=[])
        assert report.layers == []

    def test_full_report_construction(self) -> None:
        """Verify a fully populated report constructs correctly."""
        findings = [
            _make_finding(severity=AuditSeverity.CRITICAL, description="Critical issue"),
            _make_finding(severity=AuditSeverity.WARNING, description="Warning issue"),
            _make_finding(severity=AuditSeverity.INFO, description="Info note"),
        ]
        summary = _make_layer_summary(
            findings=findings,
            total_functions=10,
            tested_functions=10,
            passed=7,
            failed=3,
            coverage_pct=1.0,
        )
        report = _make_report(
            layers=[summary],
            total_findings=3,
            critical_count=1,
            warning_count=1,
            info_count=1,
        )
        assert report.total_findings == 3
        assert report.critical_count == 1
        assert report.warning_count == 1
        assert report.info_count == 1
        assert len(report.layers) == 1
        assert len(report.layers[0].findings) == 3


# ===========================================================================
# MATH_FUNCTION_REGISTRY tests
# ===========================================================================


class TestMathFunctionRegistry:
    """Tests for the MATH_FUNCTION_REGISTRY in tests/audit/conftest.py."""

    def test_registry_count(self) -> None:
        """Verify registry contains exactly 87 functions."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        assert len(MATH_FUNCTION_REGISTRY) == 87, (
            f"Expected 87 functions, got {len(MATH_FUNCTION_REGISTRY)}"
        )

    def test_all_callables(self) -> None:
        """Verify all registry values are callable."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        for key, func in MATH_FUNCTION_REGISTRY.items():
            assert callable(func), f"Registry entry '{key}' is not callable: {type(func)}"

    def test_no_duplicate_keys(self) -> None:
        """Verify no duplicate function keys (dict inherently prevents this)."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        # Dict keys are unique by construction, but verify the count matches
        # the number of unique keys to catch any dict-update-in-place issues.
        keys = list(MATH_FUNCTION_REGISTRY.keys())
        assert len(keys) == len(set(keys)), "Duplicate keys found in registry"

    def test_key_format(self) -> None:
        """Verify all keys follow 'module.submodule.function_name' format."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        for key in MATH_FUNCTION_REGISTRY:
            parts = key.split(".")
            assert len(parts) >= 3, f"Key '{key}' does not have at least 3 dot-separated parts"

    def test_pricing_functions_present(self) -> None:
        """Verify key pricing functions are in the registry."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        expected_pricing = [
            "pricing.bsm.bsm_price",
            "pricing.bsm.bsm_greeks",
            "pricing.bsm.bsm_iv",
            "pricing.american.american_price",
            "pricing.american.american_greeks",
            "pricing.american.american_iv",
            "pricing.dispatch.option_price",
            "pricing.dispatch.option_greeks",
            "pricing.dispatch.option_iv",
        ]
        for key in expected_pricing:
            assert key in MATH_FUNCTION_REGISTRY, f"Missing pricing function: {key}"

    def test_indicator_functions_present(self) -> None:
        """Verify key indicator functions are in the registry."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        expected_indicators = [
            "indicators.oscillators.rsi",
            "indicators.trend.adx",
            "indicators.volatility.bb_width",
            "indicators.volume.obv_trend",
            "indicators.moving_averages.sma_alignment",
            "indicators.options_specific.iv_rank",
            "indicators.hv_estimators.compute_hv_yang_zhang",
        ]
        for key in expected_indicators:
            assert key in MATH_FUNCTION_REGISTRY, f"Missing indicator function: {key}"

    def test_scoring_functions_present(self) -> None:
        """Verify key scoring functions are in the registry."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        expected_scoring = [
            "scoring.normalization.percentile_rank_normalize",
            "scoring.composite.composite_score",
            "scoring.direction.determine_direction",
            "scoring.dimensional.compute_dimensional_scores",
            "scoring.contracts.recommend_contracts",
        ]
        for key in expected_scoring:
            assert key in MATH_FUNCTION_REGISTRY, f"Missing scoring function: {key}"

    def test_no_none_values(self) -> None:
        """Verify no registry values are None."""
        from tests.audit.conftest import MATH_FUNCTION_REGISTRY

        for key, func in MATH_FUNCTION_REGISTRY.items():
            assert func is not None, f"Registry entry '{key}' is None"


# ===========================================================================
# Re-export tests
# ===========================================================================


class TestReExports:
    """Verify audit models and enums are re-exported from models package."""

    def test_audit_enums_importable(self) -> None:
        """Verify AuditSeverity and AuditLayer importable from models package."""
        from options_arena.models import AuditLayer, AuditSeverity

        assert AuditSeverity.CRITICAL == "critical"
        assert AuditLayer.CORRECTNESS == "correctness"

    def test_audit_models_importable(self) -> None:
        """Verify all audit models importable from models package."""
        from options_arena.models import AuditFinding, AuditLayerSummary, AuditReport

        # Quick smoke check
        assert AuditFinding is not None
        assert AuditLayerSummary is not None
        assert AuditReport is not None
