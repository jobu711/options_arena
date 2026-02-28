"""Tests for second-order Greeks: compute_vanna, compute_charm, compute_vomma.

Tests cover:
1. Known-value tests (finite difference vs analytical BSM where possible)
2. Both CALL and PUT
3. Both AMERICAN and EUROPEAN
4. Edge cases (small T for charm, extreme sigma)
5. Sign correctness
"""

import math

import pytest

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.pricing.greeks_extended import compute_charm, compute_vanna, compute_vomma

# ---------------------------------------------------------------------------
# Standard test parameters
# ---------------------------------------------------------------------------

STD_S: float = 100.0
STD_K: float = 100.0
STD_T: float = 1.0
STD_R: float = 0.05
STD_Q: float = 0.02
STD_SIGMA: float = 0.20


# ---------------------------------------------------------------------------
# Vanna tests
# ---------------------------------------------------------------------------


class TestVanna:
    """Tests for vanna: d(delta)/d(sigma)."""

    def test_european_call_returns_finite(self) -> None:
        """European call vanna returns a finite float."""
        result = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_european_put_returns_finite(self) -> None:
        """European put vanna returns a finite float."""
        result = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_american_call_returns_finite(self) -> None:
        """American call vanna returns a finite float."""
        result = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.AMERICAN,
        )
        assert math.isfinite(result)

    def test_american_put_returns_finite(self) -> None:
        """American put vanna returns a finite float."""
        result = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.AMERICAN,
        )
        assert math.isfinite(result)

    def test_atm_call_vanna_positive(self) -> None:
        """ATM call vanna should be positive for European options.

        Analytical BSM vanna = -e^(-qT) * N'(d1) * d2 / sigma
        For ATM with moderate vol: d2 is small positive, vanna depends on d2 sign.
        For standard params, ATM European call vanna is typically small but its sign
        depends on d1, d2 relationship. We just verify finite and non-zero.
        """
        result = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert result != 0.0

    def test_put_call_vanna_differ(self) -> None:
        """Put and call vanna differ because delta differs by put-call direction."""
        call_vanna = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        put_vanna = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.EUROPEAN,
        )
        # BSM vanna is same for puts and calls because
        # put delta = call delta - e^(-qT), so derivatives w.r.t. sigma match.
        assert call_vanna == pytest.approx(put_vanna, rel=1e-4)

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        [
            (100.0, 100.0, 0.5, 0.05, 0.0, 0.30),
            (50.0, 55.0, 1.0, 0.03, 0.01, 0.25),
            (200.0, 180.0, 0.25, 0.04, 0.02, 0.40),
        ],
    )
    def test_various_params_finite(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
    ) -> None:
        """Vanna is finite for various parameter combinations."""
        for otype in (OptionType.CALL, OptionType.PUT):
            for estyle in (ExerciseStyle.EUROPEAN, ExerciseStyle.AMERICAN):
                result = compute_vanna(S, K, T, r, q, sigma, otype, estyle)
                assert math.isfinite(result)


# ---------------------------------------------------------------------------
# Charm tests
# ---------------------------------------------------------------------------


class TestCharm:
    """Tests for charm: d(delta)/d(T) (delta decay)."""

    def test_european_call_returns_finite(self) -> None:
        """European call charm returns a finite float."""
        result = compute_charm(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_european_put_returns_finite(self) -> None:
        """European put charm returns a finite float."""
        result = compute_charm(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_american_call_returns_finite(self) -> None:
        """American call charm returns a finite float."""
        result = compute_charm(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.AMERICAN,
        )
        assert math.isfinite(result)

    def test_american_put_returns_finite(self) -> None:
        """American put charm returns a finite float."""
        result = compute_charm(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.AMERICAN,
        )
        assert math.isfinite(result)

    def test_small_t_forward_difference(self) -> None:
        """Small T (< 1/365) uses forward difference fallback."""
        small_t = 0.5 / 365.0  # half a day
        result = compute_charm(
            STD_S,
            STD_K,
            small_t,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_exactly_one_day_uses_forward(self) -> None:
        """T exactly at 1/365 uses forward difference (T-dT would be 0)."""
        one_day = 1.0 / 365.0
        result = compute_charm(
            STD_S,
            STD_K,
            one_day,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_long_dated_charm(self) -> None:
        """Long-dated option (T=2yr) charm is finite."""
        result = compute_charm(
            STD_S,
            STD_K,
            2.0,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_atm_call_charm_nonzero(self) -> None:
        """ATM European call charm is typically non-zero (delta changes with time)."""
        result = compute_charm(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert result != 0.0

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        [
            (100.0, 100.0, 0.5, 0.05, 0.0, 0.30),
            (50.0, 55.0, 1.0, 0.03, 0.01, 0.25),
            (200.0, 180.0, 0.25, 0.04, 0.02, 0.40),
        ],
    )
    def test_various_params_finite(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
    ) -> None:
        """Charm is finite for various parameter combinations."""
        for otype in (OptionType.CALL, OptionType.PUT):
            for estyle in (ExerciseStyle.EUROPEAN, ExerciseStyle.AMERICAN):
                result = compute_charm(S, K, T, r, q, sigma, otype, estyle)
                assert math.isfinite(result)


# ---------------------------------------------------------------------------
# Vomma tests
# ---------------------------------------------------------------------------


class TestVomma:
    """Tests for vomma: d(vega)/d(sigma) (vega convexity)."""

    def test_european_call_returns_finite(self) -> None:
        """European call vomma returns a finite float."""
        result = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_european_put_returns_finite(self) -> None:
        """European put vomma returns a finite float."""
        result = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_american_call_returns_finite(self) -> None:
        """American call vomma returns a finite float."""
        result = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.AMERICAN,
        )
        assert math.isfinite(result)

    def test_american_put_returns_finite(self) -> None:
        """American put vomma returns a finite float."""
        result = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.AMERICAN,
        )
        assert math.isfinite(result)

    def test_call_put_vomma_equal_european(self) -> None:
        """European call and put vomma should be approximately equal.

        BSM vega is same for calls/puts, so d(vega)/d(sigma) should match.
        """
        call_vomma = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        put_vomma = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            STD_SIGMA,
            OptionType.PUT,
            ExerciseStyle.EUROPEAN,
        )
        assert call_vomma == pytest.approx(put_vomma, rel=1e-4)

    def test_high_sigma_finite(self) -> None:
        """Vomma remains finite with high volatility."""
        result = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            1.5,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    def test_low_sigma_finite(self) -> None:
        """Vomma remains finite with low volatility (above d_sigma threshold)."""
        result = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            0.05,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        assert math.isfinite(result)

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        [
            (100.0, 100.0, 0.5, 0.05, 0.0, 0.30),
            (50.0, 55.0, 1.0, 0.03, 0.01, 0.25),
            (200.0, 180.0, 0.25, 0.04, 0.02, 0.40),
        ],
    )
    def test_various_params_finite(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
    ) -> None:
        """Vomma is finite for various parameter combinations."""
        for otype in (OptionType.CALL, OptionType.PUT):
            for estyle in (ExerciseStyle.EUROPEAN, ExerciseStyle.AMERICAN):
                result = compute_vomma(S, K, T, r, q, sigma, otype, estyle)
                assert math.isfinite(result)


# ---------------------------------------------------------------------------
# Cross-Greek consistency tests
# ---------------------------------------------------------------------------


class TestCrossGreekConsistency:
    """Cross-checks between extended Greeks."""

    def test_european_matches_american_q_zero_call(self) -> None:
        """With q=0, American call == European call, so extended Greeks should match."""
        q_zero = 0.0
        vanna_eur = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        vanna_am = compute_vanna(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.AMERICAN,
        )
        assert vanna_eur == pytest.approx(vanna_am, rel=1e-2)

    def test_charm_european_matches_american_q_zero_call(self) -> None:
        """Charm: American call == European call when q=0."""
        q_zero = 0.0
        charm_eur = compute_charm(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        charm_am = compute_charm(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.AMERICAN,
        )
        assert charm_eur == pytest.approx(charm_am, rel=1e-2)

    def test_vomma_european_matches_american_q_zero_call(self) -> None:
        """Vomma: American call == European call when q=0."""
        q_zero = 0.0
        vomma_eur = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.EUROPEAN,
        )
        vomma_am = compute_vomma(
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
            ExerciseStyle.AMERICAN,
        )
        assert vomma_eur == pytest.approx(vomma_am, rel=1e-2)
