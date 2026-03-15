"""Correctness tests for all 14 pricing functions vs academic + QuantLib baselines.

Tests cover:
  - BSM European call/put prices (Hull 2018, Merton 1973)
  - BSM Greeks (analytical closed-form, Hull 2018 Ch.19)
  - BSM second-order Greeks (vanna, charm, vomma)
  - BSM IV round-trip (price -> IV solver -> price recovery)
  - BAW American call/put prices and identities (BAW 1987)
  - Dispatch functions (routing correctness)
  - Intrinsic value (boundary condition)
  - QuantLib cross-validation baselines

Reference data loaded from ``tests/audit/reference_data/*.json``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.pricing._common import intrinsic_value
from options_arena.pricing.american import (
    american_greeks,
    american_iv,
    american_price,
    american_second_order_greeks,
)
from options_arena.pricing.bsm import (
    bsm_greeks,
    bsm_iv,
    bsm_price,
    bsm_second_order_greeks,
    bsm_vega,
)
from options_arena.pricing.dispatch import (
    option_greeks,
    option_iv,
    option_price,
    option_second_order_greeks,
)

# ---------------------------------------------------------------------------
# Load reference data
# ---------------------------------------------------------------------------

_REF_DIR = Path(__file__).resolve().parent.parent / "reference_data"

with (_REF_DIR / "pricing_known_values.json").open() as _f:
    _PRICING_DATA: dict = json.load(_f)

with (_REF_DIR / "quantlib_baselines.json").open() as _f:
    _QUANTLIB_DATA: dict = json.load(_f)

# ---------------------------------------------------------------------------
# Tolerance constants (from PRD specification)
# ---------------------------------------------------------------------------

# Prices: abs=0.01, rel=0.1%
_PRICE_ABS = 0.01
_PRICE_REL = 1e-3

# Delta/Gamma: abs=0.005, rel=0.5%
_GREEK_DG_ABS = 0.005
_GREEK_DG_REL = 5e-3

# Theta/Vega/Rho: abs=0.01, rel=1.0%
_GREEK_TVR_ABS = 0.01
_GREEK_TVR_REL = 0.01

# Second-order Greeks: abs=0.01, rel=2.0%
_SECOND_ORDER_ABS = 0.01
_SECOND_ORDER_REL = 0.02

# IV round-trip: abs=0.0001, rel=0.1%
_IV_ABS = 0.0001
_IV_REL = 1e-3

# BAW American price tolerance (approximation vs BSM)
_BAW_ABS = 0.05

# American Greeks (finite difference): wider tolerance
_AMERICAN_GREEK_ABS = 0.05
_AMERICAN_GREEK_REL = 0.05


# ---------------------------------------------------------------------------
# Helper: resolve OptionType from string
# ---------------------------------------------------------------------------


def _option_type(s: str) -> OptionType:
    """Convert string to OptionType enum."""
    return OptionType.CALL if s.lower() == "call" else OptionType.PUT


# =========================================================================
# BSM Price Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBSMPriceCorrectness:
    """BSM European option pricing vs Hull (2018) and Merton (1973) references."""

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_price"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_price"]],
    )
    def test_bsm_call_price(self, case: dict) -> None:
        """Hull (2018) / Merton (1973) -- BSM European call price."""
        p = case["parameters"]
        result = bsm_price(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert result == pytest.approx(
            case["expected"]["call"],
            abs=_PRICE_ABS,
            rel=_PRICE_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_price"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_price"]],
    )
    def test_bsm_put_price(self, case: dict) -> None:
        """Hull (2018) / Merton (1973) -- BSM European put price."""
        p = case["parameters"]
        result = bsm_price(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.PUT,
        )
        assert result == pytest.approx(
            case["expected"]["put"],
            abs=_PRICE_ABS,
            rel=_PRICE_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_price"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_price"]],
    )
    def test_put_call_parity(self, case: dict) -> None:
        """Hull (2018) Ch.11 -- put-call parity: C - P = S*e^(-qT) - K*e^(-rT)."""
        p = case["parameters"]
        call = bsm_price(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        put = bsm_price(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.PUT,
        )
        parity_rhs = p["S"] * math.exp(-p["q"] * p["T"]) - p["K"] * math.exp(-p["r"] * p["T"])
        assert (call - put) == pytest.approx(parity_rhs, abs=_PRICE_ABS)


# =========================================================================
# BSM Greeks Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBSMGreeksCorrectness:
    """BSM analytical Greeks vs Hull (2018) Ch.19 and Merton (1973) references."""

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_call_delta(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM call delta = e^(-qT) * N(d1)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert greeks.delta == pytest.approx(
            case["expected"]["delta_call"],
            abs=_GREEK_DG_ABS,
            rel=_GREEK_DG_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_put_delta(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM put delta = -e^(-qT) * N(-d1)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.PUT,
        )
        assert greeks.delta == pytest.approx(
            case["expected"]["delta_put"],
            abs=_GREEK_DG_ABS,
            rel=_GREEK_DG_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_gamma(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM gamma (same for calls and puts)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert greeks.gamma == pytest.approx(
            case["expected"]["gamma"],
            abs=_GREEK_DG_ABS,
            rel=_GREEK_DG_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_vega(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM vega = S * e^(-qT) * n(d1) * sqrt(T)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert greeks.vega == pytest.approx(
            case["expected"]["vega"],
            abs=_GREEK_TVR_ABS,
            rel=_GREEK_TVR_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_call_theta(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM call theta (annualized)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert greeks.theta == pytest.approx(
            case["expected"]["theta_call"],
            abs=_GREEK_TVR_ABS,
            rel=_GREEK_TVR_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_put_theta(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM put theta (annualized)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.PUT,
        )
        assert greeks.theta == pytest.approx(
            case["expected"]["theta_put"],
            abs=_GREEK_TVR_ABS,
            rel=_GREEK_TVR_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_call_rho(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM call rho = K * T * e^(-rT) * N(d2)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert greeks.rho == pytest.approx(
            case["expected"]["rho_call"],
            abs=_GREEK_TVR_ABS,
            rel=_GREEK_TVR_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_put_rho(self, case: dict) -> None:
        """Hull (2018) Ch.19 -- BSM put rho = -K * T * e^(-rT) * N(-d2)."""
        p = case["parameters"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.PUT,
        )
        assert greeks.rho == pytest.approx(
            case["expected"]["rho_put"],
            abs=_GREEK_TVR_ABS,
            rel=_GREEK_TVR_REL,
        )


# =========================================================================
# BSM Standalone Vega Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBSMVegaStandalone:
    """Standalone bsm_vega must match the vega from bsm_greeks."""

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_greeks"]],
    )
    def test_bsm_vega_matches_greeks_vega(self, case: dict) -> None:
        """bsm_vega standalone must equal bsm_greeks.vega."""
        p = case["parameters"]
        standalone = bsm_vega(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
        )
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert standalone == pytest.approx(greeks.vega, abs=1e-10)


# =========================================================================
# BSM Second-Order Greeks Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBSMSecondOrderGreeksCorrectness:
    """BSM second-order Greeks (vanna, charm, vomma) vs analytical solutions."""

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_second_order_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_second_order_greeks"]],
    )
    def test_bsm_vanna(self, case: dict) -> None:
        """Analytical BSM vanna: -e^(-qT) * n(d1) * d2 / sigma."""
        p = case["parameters"]
        result = bsm_second_order_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=_option_type(p["option_type"]),
        )
        assert result.vanna is not None
        assert result.vanna == pytest.approx(
            case["expected"]["vanna"],
            abs=_SECOND_ORDER_ABS,
            rel=_SECOND_ORDER_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_second_order_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_second_order_greeks"]],
    )
    def test_bsm_charm(self, case: dict) -> None:
        """Analytical BSM charm: d(delta)/d(T)."""
        p = case["parameters"]
        result = bsm_second_order_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=_option_type(p["option_type"]),
        )
        assert result.charm is not None
        assert result.charm == pytest.approx(
            case["expected"]["charm"],
            abs=_SECOND_ORDER_ABS,
            rel=_SECOND_ORDER_REL,
        )

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_second_order_greeks"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_second_order_greeks"]],
    )
    def test_bsm_vomma(self, case: dict) -> None:
        """Analytical BSM vomma: vega * d1 * d2 / sigma."""
        p = case["parameters"]
        result = bsm_second_order_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=_option_type(p["option_type"]),
        )
        assert result.vomma is not None
        assert result.vomma == pytest.approx(
            case["expected"]["vomma"],
            abs=_SECOND_ORDER_ABS,
            rel=_SECOND_ORDER_REL,
        )

    def test_boundary_returns_none(self) -> None:
        """Second-order Greeks at T=0 return all None."""
        result = bsm_second_order_greeks(
            S=100.0,
            K=100.0,
            T=0.0,
            r=0.05,
            q=0.0,
            sigma=0.20,
            option_type=OptionType.CALL,
        )
        assert result.vanna is None
        assert result.charm is None
        assert result.vomma is None


# =========================================================================
# BSM IV Round-Trip Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBSMIVRoundTrip:
    """BSM IV round-trip: price -> IV solver -> recovered sigma."""

    @pytest.mark.parametrize(
        "case",
        _PRICING_DATA["bsm_iv_round_trip"],
        ids=[c["source"][:60] for c in _PRICING_DATA["bsm_iv_round_trip"]],
    )
    def test_bsm_iv_round_trip(self, case: dict) -> None:
        """IV round-trip: bsm_iv(bsm_price(sigma)) recovers sigma."""
        p = case["parameters"]
        ot = _option_type(p["option_type"])

        # First verify the price matches
        computed_price = bsm_price(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=ot,
        )
        assert computed_price == pytest.approx(
            case["expected"]["market_price"],
            abs=_PRICE_ABS,
        )

        # Then recover sigma from the price
        recovered = bsm_iv(
            market_price=case["expected"]["market_price"],
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            option_type=ot,
        )
        assert recovered == pytest.approx(
            case["expected"]["recovered_sigma"],
            abs=_IV_ABS,
            rel=_IV_REL,
        )


# =========================================================================
# BAW American Price Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBAWPriceCorrectness:
    """BAW American option pricing vs BAW (1987) identities and references."""

    def test_baw_call_q0_equals_bsm(self) -> None:
        """BAW (1987) FR-P4: when q=0, American call == BSM call exactly."""
        cases = [c for c in _PRICING_DATA["baw_price"] if c["expected"].get("american_equals_bsm")]
        assert len(cases) >= 3, "Expected at least 3 FR-P4 identity test cases"
        for case in cases:
            p = case["parameters"]
            american = american_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=OptionType.CALL,
            )
            european = bsm_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=OptionType.CALL,
            )
            assert american == pytest.approx(european, abs=1e-10), (
                f"FR-P4 violated: american={american}, bsm={european} for {case['source']}"
            )

    def test_baw_put_geq_bsm(self) -> None:
        """BAW (1987) FR-P5: American put >= BSM put always."""
        cases = [c for c in _PRICING_DATA["baw_price"] if c["expected"].get("american_geq_bsm")]
        assert len(cases) >= 5, "Expected at least 5 FR-P5 test cases"
        for case in cases:
            p = case["parameters"]
            ot = _option_type(case["expected"]["option_type"])
            american = american_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=ot,
            )
            european = bsm_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=ot,
            )
            assert american >= european - 1e-10, (
                f"FR-P5 violated: american={american} < bsm={european} for {case['source']}"
            )

    def test_baw_boundary_t0_itm_call(self) -> None:
        """BAW boundary: T=0 ITM call returns intrinsic value."""
        cases = [c for c in _PRICING_DATA["baw_price"] if "T=0 ITM call" in c["source"]]
        assert len(cases) >= 1
        for case in cases:
            p = case["parameters"]
            ot = _option_type(case["expected"]["option_type"])
            result = american_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=ot,
            )
            assert result == pytest.approx(case["expected"]["price"], abs=_PRICE_ABS)

    def test_baw_boundary_t0_itm_put(self) -> None:
        """BAW boundary: T=0 ITM put returns intrinsic value."""
        cases = [c for c in _PRICING_DATA["baw_price"] if "T=0 ITM put" in c["source"]]
        assert len(cases) >= 1
        for case in cases:
            p = case["parameters"]
            ot = _option_type(case["expected"]["option_type"])
            result = american_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=ot,
            )
            assert result == pytest.approx(case["expected"]["price"], abs=_PRICE_ABS)

    def test_baw_boundary_t0_otm(self) -> None:
        """BAW boundary: T=0 OTM options return 0."""
        cases = [c for c in _PRICING_DATA["baw_price"] if "T=0 OTM" in c["source"]]
        assert len(cases) >= 2
        for case in cases:
            p = case["parameters"]
            ot = _option_type(case["expected"]["option_type"])
            result = american_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=ot,
            )
            assert result == pytest.approx(case["expected"]["price"], abs=_PRICE_ABS)

    def test_baw_sigma0_itm_call_returns_intrinsic(self) -> None:
        """BAW boundary: sigma=0 ITM call returns intrinsic value."""
        # Use exact source match to avoid substring collision with "sigma=0.20"
        cases = [
            c
            for c in _PRICING_DATA["baw_price"]
            if c["source"] == "BAW: sigma=0 ITM call returns intrinsic"
        ]
        assert len(cases) >= 1
        for case in cases:
            p = case["parameters"]
            ot = _option_type(case["expected"]["option_type"])
            result = american_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=ot,
            )
            assert result == pytest.approx(case["expected"]["price"], abs=_PRICE_ABS)

    def test_baw_put_price_geq_intrinsic(self) -> None:
        """BAW: very deep ITM put price >= intrinsic value."""
        cases = [c for c in _PRICING_DATA["baw_price"] if c["expected"].get("price_geq_intrinsic")]
        for case in cases:
            p = case["parameters"]
            ot = _option_type(case["expected"]["option_type"])
            result = american_price(
                S=p["S"],
                K=p["K"],
                T=p["T"],
                r=p["r"],
                q=p["q"],
                sigma=p["sigma"],
                option_type=ot,
            )
            iv = intrinsic_value(p["S"], p["K"], ot)
            assert result >= iv - 1e-10


# =========================================================================
# BAW American Greeks Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBAWGreeksCorrectness:
    """BAW finite-difference Greeks -- sign correctness and range bounds."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_american_greeks_delta_range(self, option_type: OptionType) -> None:
        """BAW (1987) -- American delta must be in [-1, 1]."""
        greeks = american_greeks(
            S=100.0,
            K=100.0,
            T=1.0,
            r=0.05,
            q=0.02,
            sigma=0.20,
            option_type=option_type,
        )
        assert -1.0 <= greeks.delta <= 1.0

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_american_greeks_gamma_nonneg(self, option_type: OptionType) -> None:
        """BAW (1987) -- American gamma must be >= 0."""
        greeks = american_greeks(
            S=100.0,
            K=100.0,
            T=1.0,
            r=0.05,
            q=0.02,
            sigma=0.20,
            option_type=option_type,
        )
        assert greeks.gamma >= -1e-10

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_american_greeks_vega_nonneg(self, option_type: OptionType) -> None:
        """BAW (1987) -- American vega must be >= 0."""
        greeks = american_greeks(
            S=100.0,
            K=100.0,
            T=1.0,
            r=0.05,
            q=0.02,
            sigma=0.20,
            option_type=option_type,
        )
        assert greeks.vega >= -1e-10

    def test_american_call_delta_positive(self) -> None:
        """BAW -- American call delta must be positive."""
        greeks = american_greeks(
            S=100.0,
            K=100.0,
            T=1.0,
            r=0.05,
            q=0.02,
            sigma=0.20,
            option_type=OptionType.CALL,
        )
        assert greeks.delta > 0.0

    def test_american_put_delta_negative(self) -> None:
        """BAW -- American put delta must be negative."""
        greeks = american_greeks(
            S=100.0,
            K=100.0,
            T=1.0,
            r=0.05,
            q=0.02,
            sigma=0.20,
            option_type=OptionType.PUT,
        )
        assert greeks.delta < 0.0


# =========================================================================
# BAW American IV Round-Trip Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBAWIVRoundTrip:
    """BAW IV round-trip: american_price -> american_iv -> recovered sigma."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "option_type"),
        [
            (100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL),
            (100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.PUT),
            (100.0, 100.0, 0.5, 0.05, 0.0, 0.30, OptionType.PUT),
            (50.0, 50.0, 1.0, 0.08, 0.03, 0.40, OptionType.CALL),
        ],
        ids=["ATM call q=2%", "ATM put q=2%", "ATM put 6M", "S=50 high vol"],
    )
    def test_baw_iv_round_trip(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """BAW IV round-trip: american_iv(american_price(sigma)) recovers sigma."""
        price = american_price(S, K, T, r, q, sigma, option_type)
        recovered = american_iv(price, S, K, T, r, q, option_type)
        assert recovered == pytest.approx(sigma, abs=_IV_ABS, rel=_IV_REL)


# =========================================================================
# BAW American Second-Order Greeks Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestBAWSecondOrderGreeksCorrectness:
    """BAW second-order Greeks -- finite-difference cross-bump validation."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_american_second_order_finite(self, option_type: OptionType) -> None:
        """BAW second-order Greeks must return finite values."""
        result = american_second_order_greeks(
            S=100.0,
            K=100.0,
            T=1.0,
            r=0.05,
            q=0.02,
            sigma=0.20,
            option_type=option_type,
        )
        assert result.vanna is not None
        assert result.charm is not None
        assert result.vomma is not None
        assert math.isfinite(result.vanna)
        assert math.isfinite(result.charm)
        assert math.isfinite(result.vomma)

    def test_american_second_order_boundary(self) -> None:
        """BAW second-order Greeks at T=0 return all None."""
        result = american_second_order_greeks(
            S=100.0,
            K=100.0,
            T=0.0,
            r=0.05,
            q=0.02,
            sigma=0.20,
            option_type=OptionType.CALL,
        )
        assert result.vanna is None
        assert result.charm is None
        assert result.vomma is None


# =========================================================================
# Dispatch Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestDispatchCorrectness:
    """Dispatch layer routes correctly by ExerciseStyle."""

    def test_dispatch_european_price_matches_bsm(self) -> None:
        """Dispatch EUROPEAN routes to bsm_price."""
        direct = bsm_price(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)
        dispatched = option_price(
            ExerciseStyle.EUROPEAN,
            100.0,
            100.0,
            1.0,
            0.05,
            0.0,
            0.20,
            OptionType.CALL,
        )
        assert dispatched == pytest.approx(direct, abs=1e-12)

    def test_dispatch_american_price_matches_baw(self) -> None:
        """Dispatch AMERICAN routes to american_price."""
        direct = american_price(100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL)
        dispatched = option_price(
            ExerciseStyle.AMERICAN,
            100.0,
            100.0,
            1.0,
            0.05,
            0.02,
            0.20,
            OptionType.CALL,
        )
        assert dispatched == pytest.approx(direct, abs=1e-12)

    def test_dispatch_european_greeks_matches_bsm(self) -> None:
        """Dispatch EUROPEAN greeks routes to bsm_greeks."""
        direct = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)
        dispatched = option_greeks(
            ExerciseStyle.EUROPEAN,
            100.0,
            100.0,
            1.0,
            0.05,
            0.0,
            0.20,
            OptionType.CALL,
        )
        assert dispatched.delta == pytest.approx(direct.delta, abs=1e-12)
        assert dispatched.gamma == pytest.approx(direct.gamma, abs=1e-12)

    def test_dispatch_american_greeks_matches_baw(self) -> None:
        """Dispatch AMERICAN greeks routes to american_greeks."""
        direct = american_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL)
        dispatched = option_greeks(
            ExerciseStyle.AMERICAN,
            100.0,
            100.0,
            1.0,
            0.05,
            0.02,
            0.20,
            OptionType.CALL,
        )
        assert dispatched.delta == pytest.approx(direct.delta, abs=1e-12)

    def test_dispatch_european_iv_matches_bsm(self) -> None:
        """Dispatch EUROPEAN IV routes to bsm_iv."""
        direct = bsm_iv(10.45, 100.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)
        dispatched = option_iv(
            ExerciseStyle.EUROPEAN,
            10.45,
            100.0,
            100.0,
            1.0,
            0.05,
            0.0,
            OptionType.CALL,
        )
        assert dispatched == pytest.approx(direct, abs=1e-10)

    def test_dispatch_european_second_order_matches_bsm(self) -> None:
        """Dispatch EUROPEAN second-order routes to bsm_second_order_greeks."""
        direct = bsm_second_order_greeks(
            100.0,
            100.0,
            1.0,
            0.05,
            0.0,
            0.20,
            OptionType.CALL,
        )
        dispatched = option_second_order_greeks(
            ExerciseStyle.EUROPEAN,
            100.0,
            100.0,
            1.0,
            0.05,
            0.0,
            0.20,
            OptionType.CALL,
        )
        assert dispatched.vanna == pytest.approx(direct.vanna, abs=1e-12)  # type: ignore[arg-type]
        assert dispatched.charm == pytest.approx(direct.charm, abs=1e-12)  # type: ignore[arg-type]
        assert dispatched.vomma == pytest.approx(direct.vomma, abs=1e-12)  # type: ignore[arg-type]

    def test_dispatch_american_second_order_matches_baw(self) -> None:
        """Dispatch AMERICAN second-order routes to american_second_order_greeks."""
        direct = american_second_order_greeks(
            100.0,
            100.0,
            1.0,
            0.05,
            0.02,
            0.20,
            OptionType.CALL,
        )
        dispatched = option_second_order_greeks(
            ExerciseStyle.AMERICAN,
            100.0,
            100.0,
            1.0,
            0.05,
            0.02,
            0.20,
            OptionType.CALL,
        )
        assert dispatched.vanna == pytest.approx(direct.vanna, abs=1e-12)  # type: ignore[arg-type]


# =========================================================================
# Intrinsic Value Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestIntrinsicValueCorrectness:
    """Intrinsic value boundary condition tests."""

    @pytest.mark.parametrize(
        ("S", "K", "option_type", "expected"),
        [
            (110.0, 100.0, OptionType.CALL, 10.0),
            (90.0, 100.0, OptionType.CALL, 0.0),
            (100.0, 100.0, OptionType.CALL, 0.0),
            (90.0, 100.0, OptionType.PUT, 10.0),
            (110.0, 100.0, OptionType.PUT, 0.0),
            (100.0, 100.0, OptionType.PUT, 0.0),
            (150.0, 100.0, OptionType.CALL, 50.0),
            (50.0, 100.0, OptionType.PUT, 50.0),
        ],
        ids=[
            "ITM call",
            "OTM call",
            "ATM call",
            "ITM put",
            "OTM put",
            "ATM put",
            "deep ITM call",
            "deep ITM put",
        ],
    )
    def test_intrinsic_value(
        self,
        S: float,
        K: float,
        option_type: OptionType,
        expected: float,
    ) -> None:
        """Intrinsic value = max(S-K, 0) for calls, max(K-S, 0) for puts."""
        assert intrinsic_value(S, K, option_type) == pytest.approx(expected, abs=1e-12)


# =========================================================================
# QuantLib Cross-Validation Tests
# =========================================================================


@pytest.mark.audit_correctness
class TestQuantLibBaselines:
    """Cross-validate BSM implementation against QuantLib analytical baselines."""

    @pytest.mark.parametrize(
        "entry",
        _QUANTLIB_DATA["entries"],
        ids=[e["source"][:60] for e in _QUANTLIB_DATA["entries"]],
    )
    def test_quantlib_european_call_price(self, entry: dict) -> None:
        """QuantLib AnalyticEuropeanEngine -- BSM call price cross-check."""
        p = entry["parameters"]
        ql_call = entry["european"]["call"]["price"]
        result = bsm_price(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert result == pytest.approx(ql_call, abs=_PRICE_ABS, rel=_PRICE_REL)

    @pytest.mark.parametrize(
        "entry",
        _QUANTLIB_DATA["entries"],
        ids=[e["source"][:60] for e in _QUANTLIB_DATA["entries"]],
    )
    def test_quantlib_european_put_price(self, entry: dict) -> None:
        """QuantLib AnalyticEuropeanEngine -- BSM put price cross-check."""
        p = entry["parameters"]
        ql_put = entry["european"]["put"]["price"]
        result = bsm_price(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.PUT,
        )
        assert result == pytest.approx(ql_put, abs=_PRICE_ABS, rel=_PRICE_REL)

    @pytest.mark.parametrize(
        "entry",
        [e for e in _QUANTLIB_DATA["entries"] if "delta" in e["european"]["call"]],
        ids=[
            e["source"][:60] for e in _QUANTLIB_DATA["entries"] if "delta" in e["european"]["call"]
        ],
    )
    def test_quantlib_european_greeks(self, entry: dict) -> None:
        """QuantLib AnalyticEuropeanEngine -- BSM Greeks cross-check."""
        p = entry["parameters"]
        ql_call = entry["european"]["call"]
        greeks = bsm_greeks(
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            sigma=p["sigma"],
            option_type=OptionType.CALL,
        )
        assert greeks.delta == pytest.approx(ql_call["delta"], abs=_GREEK_DG_ABS)
        assert greeks.gamma == pytest.approx(ql_call["gamma"], abs=_GREEK_DG_ABS)
        assert greeks.vega == pytest.approx(ql_call["vega"], abs=_GREEK_TVR_ABS)

    @pytest.mark.parametrize(
        "entry",
        [e for e in _QUANTLIB_DATA["entries"] if e.get("iv_round_trip")],
        ids=[e["source"][:60] for e in _QUANTLIB_DATA["entries"] if e.get("iv_round_trip")],
    )
    def test_quantlib_iv_round_trip(self, entry: dict) -> None:
        """QuantLib cross-check -- IV round-trip for BSM prices."""
        p = entry["parameters"]
        iv_data = entry["iv_round_trip"]["call"]
        recovered = bsm_iv(
            market_price=iv_data["target_price"],
            S=p["S"],
            K=p["K"],
            T=p["T"],
            r=p["r"],
            q=p["q"],
            option_type=OptionType.CALL,
        )
        # Deep ITM / low-vol cases have wider solver tolerance
        tol = iv_data.get("tolerance", _IV_ABS)
        assert recovered == pytest.approx(
            iv_data["recovered_sigma"],
            abs=tol,
            rel=_IV_REL,
        )
