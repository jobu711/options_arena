"""Unit tests for the ScanEnrichment frozen envelope model.

Tests cover:
- Default construction (all None)
- Full construction with all fields populated
- Frozen immutability enforcement
- NaN/Inf rejection on prob_profit_neural and macro floats
- prob_profit_neural [0.0, 1.0] range validation
- JSON serialization roundtrip
- SpreadAnalysis field acceptance
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models import MacroRegime, ScanEnrichment
from options_arena.models.financial_datasets import FinancialDatasetsPackage
from tests.factories import make_spread_analysis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_fd_package() -> FinancialDatasetsPackage:
    """Create a minimal FinancialDatasetsPackage for testing."""
    return FinancialDatasetsPackage(
        ticker="AAPL",
        fetched_at=datetime(2026, 3, 24, 12, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScanEnrichment:
    """Tests for the ScanEnrichment frozen envelope model."""

    def test_default_construction(self) -> None:
        """All fields None when no args provided."""
        enrichment = ScanEnrichment()
        assert enrichment.spread_analysis is None
        assert enrichment.prob_profit_neural is None
        assert enrichment.macro_regime is None
        assert enrichment.macro_yield_spread is None
        assert enrichment.macro_fed_funds_rate is None
        assert enrichment.macro_vix_level is None
        assert enrichment.next_earnings is None
        assert enrichment.fd_package is None

    def test_full_construction(self, sample_fd_package: FinancialDatasetsPackage) -> None:
        """All fields populated from valid data."""
        spread = make_spread_analysis()
        enrichment = ScanEnrichment(
            spread_analysis=spread,
            prob_profit_neural=0.72,
            macro_regime=MacroRegime.EXPANSIONARY,
            macro_yield_spread=1.25,
            macro_fed_funds_rate=5.25,
            macro_vix_level=18.5,
            next_earnings=date(2026, 4, 24),
            fd_package=sample_fd_package,
        )
        assert enrichment.spread_analysis is spread
        assert enrichment.prob_profit_neural == pytest.approx(0.72)
        assert enrichment.macro_regime is MacroRegime.EXPANSIONARY
        assert enrichment.macro_yield_spread == pytest.approx(1.25)
        assert enrichment.macro_fed_funds_rate == pytest.approx(5.25)
        assert enrichment.macro_vix_level == pytest.approx(18.5)
        assert enrichment.next_earnings == date(2026, 4, 24)
        assert enrichment.fd_package is sample_fd_package

    def test_frozen_rejects_mutation(self) -> None:
        """Assignment to field raises ValidationError."""
        enrichment = ScanEnrichment(prob_profit_neural=0.5)
        with pytest.raises(ValidationError):
            enrichment.prob_profit_neural = 0.8  # type: ignore[misc]

    def test_prob_profit_nan_rejected(self) -> None:
        """NaN prob_profit_neural raises ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(prob_profit_neural=float("nan"))

    def test_prob_profit_inf_rejected(self) -> None:
        """Inf prob_profit_neural raises ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(prob_profit_neural=float("inf"))

    def test_prob_profit_negative_inf_rejected(self) -> None:
        """-Inf prob_profit_neural raises ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(prob_profit_neural=float("-inf"))

    def test_prob_profit_out_of_range(self) -> None:
        """prob_profit_neural > 1.0 or < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            ScanEnrichment(prob_profit_neural=1.5)
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            ScanEnrichment(prob_profit_neural=-0.1)

    def test_prob_profit_boundary_values(self) -> None:
        """prob_profit_neural at 0.0 and 1.0 are accepted."""
        e0 = ScanEnrichment(prob_profit_neural=0.0)
        assert e0.prob_profit_neural == pytest.approx(0.0)
        e1 = ScanEnrichment(prob_profit_neural=1.0)
        assert e1.prob_profit_neural == pytest.approx(1.0)

    def test_macro_nan_rejected(self) -> None:
        """NaN macro floats raise ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(macro_yield_spread=float("nan"))
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(macro_fed_funds_rate=float("nan"))
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(macro_vix_level=float("nan"))

    def test_macro_inf_rejected(self) -> None:
        """Inf macro floats raise ValidationError."""
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(macro_yield_spread=float("inf"))
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(macro_fed_funds_rate=float("-inf"))
        with pytest.raises(ValidationError, match="finite"):
            ScanEnrichment(macro_vix_level=float("inf"))

    def test_macro_negative_values_accepted(self) -> None:
        """Negative macro float values are valid (e.g. inverted yield curve)."""
        enrichment = ScanEnrichment(
            macro_yield_spread=-0.5,
            macro_fed_funds_rate=0.25,
            macro_vix_level=12.0,
        )
        assert enrichment.macro_yield_spread == pytest.approx(-0.5)

    def test_json_roundtrip(self, sample_fd_package: FinancialDatasetsPackage) -> None:
        """model_dump_json -> model_validate_json preserves all fields."""
        spread = make_spread_analysis()
        original = ScanEnrichment(
            spread_analysis=spread,
            prob_profit_neural=0.65,
            macro_regime=MacroRegime.CONTRACTIONARY,
            macro_yield_spread=-0.25,
            macro_fed_funds_rate=4.75,
            macro_vix_level=28.3,
            next_earnings=date(2026, 5, 15),
            fd_package=sample_fd_package,
        )
        json_str = original.model_dump_json()
        restored = ScanEnrichment.model_validate_json(json_str)
        assert restored.prob_profit_neural == pytest.approx(0.65)
        assert restored.macro_regime is MacroRegime.CONTRACTIONARY
        assert restored.macro_yield_spread == pytest.approx(-0.25)
        assert restored.macro_fed_funds_rate == pytest.approx(4.75)
        assert restored.macro_vix_level == pytest.approx(28.3)
        assert restored.next_earnings == date(2026, 5, 15)
        assert restored.fd_package is not None
        assert restored.fd_package.ticker == "AAPL"
        assert restored.spread_analysis is not None
        assert restored.spread_analysis.pop_estimate == pytest.approx(
            original.spread_analysis.pop_estimate  # type: ignore[union-attr]
        )

    def test_json_roundtrip_empty(self) -> None:
        """Empty ScanEnrichment survives JSON roundtrip."""
        original = ScanEnrichment()
        json_str = original.model_dump_json()
        restored = ScanEnrichment.model_validate_json(json_str)
        assert restored == original

    def test_spread_analysis_accepted(self) -> None:
        """SpreadAnalysis instance accepted in spread_analysis field."""
        spread = make_spread_analysis()
        enrichment = ScanEnrichment(spread_analysis=spread)
        assert enrichment.spread_analysis is not None
        assert enrichment.spread_analysis.net_premium == Decimal("2.50")
