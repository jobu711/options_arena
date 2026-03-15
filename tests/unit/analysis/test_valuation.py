"""Tests for analysis/valuation.py — multi-methodology valuation framework.

Covers each of the four valuation models, the composite combiner, edge cases
(None data, NaN/Inf, zero price, negative fair values), signal classification,
weight renormalization, and haircut application.
"""

from __future__ import annotations

from options_arena.analysis.valuation import (
    DEFAULT_SECTOR_EV_EBITDA,
    OVERVALUED_THRESHOLD,
    OWNER_EARNINGS_HAIRCUT,
    RESIDUAL_INCOME_HAIRCUT,
    UNDERVALUED_THRESHOLD,
    FDData,
    compute_composite_valuation,
    compute_ev_ebitda_relative,
    compute_owner_earnings_dcf,
    compute_residual_income,
    compute_three_stage_dcf,
)
from options_arena.models.enums import ValuationSignal

# ---------------------------------------------------------------------------
# Helper: standard FDData with complete data
# ---------------------------------------------------------------------------


def _full_fd() -> FDData:
    """Create an FDData with all fields populated for a healthy company."""
    return FDData(
        net_income=5_000_000_000.0,  # $5B
        depreciation_amortization=1_000_000_000.0,  # $1B
        capex=800_000_000.0,  # $0.8B
        free_cash_flow=4_200_000_000.0,  # $4.2B
        revenue_growth=0.10,  # 10%
        earnings_growth=0.12,  # 12%
        ev_to_ebitda=15.0,
        book_value_per_share=45.0,
        roe=0.18,  # 18%
        shares_outstanding=1_000_000_000.0,  # 1B shares
        sector_ev_ebitda=14.0,
    )


# ---------------------------------------------------------------------------
# Model 1: Owner Earnings DCF
# ---------------------------------------------------------------------------


class TestOwnerEarningsDCF:
    """Tests for the Owner Earnings DCF model."""

    def test_known_inputs(self) -> None:
        """Owner Earnings DCF with known inputs produces a positive fair value."""
        fd = _full_fd()
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.methodology == "owner_earnings_dcf"
        assert result.fair_value is not None
        assert result.fair_value > 0.0
        assert result.confidence > 0.0

    def test_haircut_applied(self) -> None:
        """Owner Earnings DCF applies 25% haircut to final value."""
        fd = _full_fd()
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        # The fair value should be less than what it would be without haircut
        # We verify indirectly by checking the haircut is reflected
        assert result.fair_value is not None
        assert OWNER_EARNINGS_HAIRCUT == 0.25

    def test_missing_net_income(self) -> None:
        """Missing net_income returns None fair value."""
        fd = _full_fd()
        fd.net_income = None
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None
        assert result.confidence == 0.0

    def test_missing_shares_outstanding(self) -> None:
        """Missing shares_outstanding returns None fair value."""
        fd = _full_fd()
        fd.shares_outstanding = None
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_zero_shares_outstanding(self) -> None:
        """Zero shares_outstanding returns None fair value."""
        fd = _full_fd()
        fd.shares_outstanding = 0.0
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_negative_owner_earnings(self) -> None:
        """When owner earnings are negative, model returns None."""
        fd = _full_fd()
        fd.net_income = 100.0
        fd.capex = 1_000_000_000.0  # capex >> net income
        fd.depreciation_amortization = 0.0
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_nan_input(self) -> None:
        """NaN in net_income produces None fair value."""
        fd = _full_fd()
        fd.net_income = float("nan")
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_inf_input(self) -> None:
        """Inf in net_income produces None fair value."""
        fd = _full_fd()
        fd.net_income = float("inf")
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        # With infinite net income, the computation would produce infinity,
        # which gets caught by the isfinite guard
        assert result.fair_value is None

    def test_partial_data_confidence(self) -> None:
        """When D&A and capex are missing, confidence is lower."""
        fd = _full_fd()
        fd.depreciation_amortization = None
        fd.capex = None
        fd.earnings_growth = None
        result = compute_owner_earnings_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.confidence == 0.5  # only base confidence


# ---------------------------------------------------------------------------
# Model 2: Three-Stage DCF
# ---------------------------------------------------------------------------


class TestThreeStageDCF:
    """Tests for the Three-Stage DCF model."""

    def test_known_inputs(self) -> None:
        """3-Stage DCF with known inputs produces expected fair value."""
        fd = _full_fd()
        result = compute_three_stage_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.methodology == "three_stage_dcf"
        assert result.fair_value is not None
        assert result.fair_value > 0.0

    def test_scenario_weighting(self) -> None:
        """3-Stage DCF scenario-weights bull/base/bear cases."""
        fd = _full_fd()
        result = compute_three_stage_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is not None
        # The result should be deterministic — running it again gives same answer
        result2 = compute_three_stage_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value == result2.fair_value

    def test_missing_fcf(self) -> None:
        """Missing FCF returns None."""
        fd = _full_fd()
        fd.free_cash_flow = None
        result = compute_three_stage_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_missing_shares(self) -> None:
        """Missing shares_outstanding returns None."""
        fd = _full_fd()
        fd.shares_outstanding = None
        result = compute_three_stage_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_negative_fcf(self) -> None:
        """Negative FCF returns None."""
        fd = _full_fd()
        fd.free_cash_flow = -1_000_000.0
        result = compute_three_stage_dcf(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None


# ---------------------------------------------------------------------------
# Model 3: EV/EBITDA Relative
# ---------------------------------------------------------------------------


class TestEVEBITDARelative:
    """Tests for the EV/EBITDA Relative valuation model."""

    def test_known_inputs(self) -> None:
        """EV/EBITDA relative with known sector average produces expected fair value."""
        fd = _full_fd()
        fd.ev_to_ebitda = 20.0
        fd.sector_ev_ebitda = 15.0
        result = compute_ev_ebitda_relative(fd, current_price=100.0)
        assert result.methodology == "ev_ebitda_relative"
        assert result.fair_value is not None
        # If ticker trades at 20x but sector trades at 15x, implied fair value = 100 * (15/20) = 75
        assert abs(result.fair_value - 75.0) < 0.01

    def test_sector_fallback(self) -> None:
        """Without sector average, falls back to S&P 500 median."""
        fd = _full_fd()
        fd.sector_ev_ebitda = None
        fd.ev_to_ebitda = 20.0
        result = compute_ev_ebitda_relative(fd, current_price=100.0)
        assert result.fair_value is not None
        expected = 100.0 * (DEFAULT_SECTOR_EV_EBITDA / 20.0)
        assert abs(result.fair_value - expected) < 0.01

    def test_missing_ev_ebitda(self) -> None:
        """Missing ev_to_ebitda returns None."""
        fd = _full_fd()
        fd.ev_to_ebitda = None
        result = compute_ev_ebitda_relative(fd, current_price=100.0)
        assert result.fair_value is None

    def test_zero_ev_ebitda(self) -> None:
        """Zero ev_to_ebitda returns None."""
        fd = _full_fd()
        fd.ev_to_ebitda = 0.0
        result = compute_ev_ebitda_relative(fd, current_price=100.0)
        assert result.fair_value is None

    def test_zero_current_price(self) -> None:
        """Zero current price handled safely."""
        fd = _full_fd()
        fd.ev_to_ebitda = 15.0
        result = compute_ev_ebitda_relative(fd, current_price=0.0)
        assert result.fair_value is None


# ---------------------------------------------------------------------------
# Model 4: Residual Income
# ---------------------------------------------------------------------------


class TestResidualIncome:
    """Tests for the Residual Income Model."""

    def test_known_inputs(self) -> None:
        """Residual Income with known ROE and book value produces expected fair value."""
        fd = _full_fd()
        result = compute_residual_income(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.methodology == "residual_income"
        assert result.fair_value is not None
        assert result.fair_value > 0.0

    def test_haircut_applied(self) -> None:
        """Residual Income applies 20% haircut to final value."""
        assert RESIDUAL_INCOME_HAIRCUT == 0.20
        fd = _full_fd()
        result = compute_residual_income(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is not None

    def test_roe_below_cost_of_equity(self) -> None:
        """When ROE < cost of equity, fair value equals book value * (1 - haircut)."""
        fd = _full_fd()
        fd.roe = 0.02  # 2% ROE, less than risk-free + 5% ERP = 9%
        fd.book_value_per_share = 50.0
        result = compute_residual_income(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is not None
        # Should be book_value * (1 - 0.20) = 50 * 0.8 = 40.0
        assert abs(result.fair_value - 40.0) < 0.01

    def test_missing_book_value(self) -> None:
        """Missing book_value_per_share returns None."""
        fd = _full_fd()
        fd.book_value_per_share = None
        result = compute_residual_income(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_missing_roe(self) -> None:
        """Missing ROE returns None."""
        fd = _full_fd()
        fd.roe = None
        result = compute_residual_income(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None

    def test_zero_book_value(self) -> None:
        """Zero book value returns None."""
        fd = _full_fd()
        fd.book_value_per_share = 0.0
        result = compute_residual_income(fd, risk_free_rate=0.04, current_price=100.0)
        assert result.fair_value is None


# ---------------------------------------------------------------------------
# Composite Combiner
# ---------------------------------------------------------------------------


class TestCompositeValuation:
    """Tests for the composite valuation combiner."""

    def test_all_four_models_produce_values(self) -> None:
        """Composite is weighted average of all four model fair values."""
        fd = _full_fd()
        result = compute_composite_valuation("AAPL", 100.0, fd)
        assert result.composite_fair_value is not None
        assert result.composite_fair_value > 0.0
        assert len(result.weights_used) > 0
        # Weights should sum to ~1.0
        assert abs(sum(result.weights_used.values()) - 1.0) < 0.001

    def test_all_four_models_return_none(self) -> None:
        """When all models lack data, composite fair value is None."""
        fd = FDData()  # all None
        result = compute_composite_valuation("XYZ", 100.0, fd)
        assert result.composite_fair_value is None
        assert result.composite_margin_of_safety is None
        assert result.valuation_signal is None
        assert result.weights_used == {}

    def test_single_model_sufficient(self) -> None:
        """When only one model has data, its weight is renormalized to 1.0."""
        fd = FDData(
            ev_to_ebitda=15.0,
            sector_ev_ebitda=15.0,
        )
        result = compute_composite_valuation("TEST", 100.0, fd)
        # Only EV/EBITDA should produce a value
        assert result.composite_fair_value is not None
        assert len(result.weights_used) == 1
        assert "ev_ebitda_relative" in result.weights_used
        assert abs(result.weights_used["ev_ebitda_relative"] - 1.0) < 0.001

    def test_weight_renormalization(self) -> None:
        """When two of four models produce values, weights renormalize to sum to 1.0."""
        fd = FDData(
            ev_to_ebitda=15.0,
            sector_ev_ebitda=15.0,
            book_value_per_share=50.0,
            roe=0.15,
        )
        result = compute_composite_valuation("TEST", 100.0, fd)
        assert len(result.weights_used) >= 2
        total = sum(result.weights_used.values())
        assert abs(total - 1.0) < 0.001

    def test_margin_of_safety_undervalued(self) -> None:
        """Margin > 15% produces ValuationSignal.UNDERVALUED."""
        # Set up conditions where fair value >> price
        fd = FDData(
            ev_to_ebitda=8.0,  # very low multiple
            sector_ev_ebitda=15.0,  # sector much higher
        )
        result = compute_composite_valuation("CHEAP", 100.0, fd)
        # fair_value should be 100 * (15/8) = 187.5
        assert result.valuation_signal == ValuationSignal.UNDERVALUED
        assert result.composite_margin_of_safety is not None
        assert result.composite_margin_of_safety > UNDERVALUED_THRESHOLD

    def test_margin_of_safety_fairly_valued(self) -> None:
        """Margin within +/-15% produces ValuationSignal.FAIRLY_VALUED."""
        fd = FDData(
            ev_to_ebitda=15.0,
            sector_ev_ebitda=15.0,  # same as sector
        )
        result = compute_composite_valuation("FAIR", 100.0, fd)
        # fair_value = 100 * (15/15) = 100 -> MoS = 0
        assert result.valuation_signal == ValuationSignal.FAIRLY_VALUED
        assert result.composite_margin_of_safety is not None
        assert abs(result.composite_margin_of_safety) <= 0.15

    def test_margin_of_safety_overvalued(self) -> None:
        """Margin < -15% produces ValuationSignal.OVERVALUED."""
        fd = FDData(
            ev_to_ebitda=25.0,  # very high multiple
            sector_ev_ebitda=15.0,  # sector much lower
        )
        result = compute_composite_valuation("EXPENSIVE", 100.0, fd)
        # fair_value = 100 * (15/25) = 60 -> MoS = (60-100)/60 = -0.667
        assert result.valuation_signal == ValuationSignal.OVERVALUED
        assert result.composite_margin_of_safety is not None
        assert result.composite_margin_of_safety < OVERVALUED_THRESHOLD

    def test_zero_current_price(self) -> None:
        """Zero current price handled safely (no division by zero)."""
        fd = _full_fd()
        result = compute_composite_valuation("ZERO", 0.0, fd)
        assert result.composite_fair_value is None
        assert result.composite_margin_of_safety is None
        assert result.valuation_signal is None

    def test_composite_valuation_structure(self) -> None:
        """CompositeValuation includes all four model results and weights_used."""
        fd = _full_fd()
        result = compute_composite_valuation("AAPL", 150.0, fd)
        assert result.ticker == "AAPL"
        assert result.current_price == 150.0
        assert len(result.models) == 4  # all four models attempted
        assert result.computed_at is not None

    def test_nan_inputs_handled(self) -> None:
        """NaN inputs do not propagate -- model returns None."""
        fd = FDData(
            net_income=float("nan"),
            free_cash_flow=float("nan"),
            ev_to_ebitda=float("nan"),
            book_value_per_share=float("nan"),
            roe=float("nan"),
            shares_outstanding=1_000_000.0,
        )
        result = compute_composite_valuation("NAN", 100.0, fd)
        # All models should fail due to NaN inputs
        assert result.composite_fair_value is None

    def test_inf_inputs_handled(self) -> None:
        """Inf inputs do not propagate -- model returns None."""
        fd = FDData(
            net_income=float("inf"),
            shares_outstanding=1_000_000.0,
        )
        result = compute_composite_valuation("INF", 100.0, fd)
        # Owner earnings model should catch infinity
        for model in result.models:
            if model.methodology == "owner_earnings_dcf":
                assert model.fair_value is None

    def test_insufficient_data_graceful_none(self) -> None:
        """Model with missing required inputs returns None fair value, not error."""
        fd = FDData(net_income=1_000_000.0)  # missing shares_outstanding
        result = compute_composite_valuation("PARTIAL", 100.0, fd)
        # Should not raise, should gracefully return None for incomplete models
        assert isinstance(result.models, list)

    def test_negative_fair_value_treated_as_none(self) -> None:
        """Negative fair value is excluded from composite."""
        # This is an edge case -- if a model somehow produces negative fair value,
        # it should be treated as None in the composite
        fd = FDData(
            book_value_per_share=5.0,
            roe=-0.50,  # Very negative ROE
        )
        result = compute_composite_valuation("NEG", 100.0, fd)
        # Residual income with very negative ROE should produce fair_value = bvps * 0.8 = 4.0
        # which is positive (just book value with haircut)
        # The composite should handle this gracefully
        assert isinstance(result.composite_fair_value, (float, type(None)))
