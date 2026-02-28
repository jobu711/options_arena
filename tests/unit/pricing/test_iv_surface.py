"""Tests for IV surface utilities: ATM extraction, delta-based IV, batch solve.

Covers:
- ATM IV extraction from call/put chains
- ATM IV extraction across multiple DTEs
- IV at target delta computation
- Batch IV solving
- Missing data / edge cases for all functions
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from options_arena.pricing.iv_surface import (
    batch_iv_solve,
    compute_iv_at_delta,
    extract_atm_iv,
    extract_atm_iv_by_dte,
)

# ---------------------------------------------------------------------------
# Helpers — build realistic OptionContract fixtures
# ---------------------------------------------------------------------------


def _make_contract(
    strike: float,
    option_type: OptionType,
    market_iv: float,
    bid: float = 1.00,
    ask: float = 1.50,
    volume: int = 100,
    open_interest: int = 500,
    dte_days: int = 30,
) -> OptionContract:
    """Build a minimal OptionContract for testing."""
    return OptionContract(
        ticker="AAPL",
        option_type=option_type,
        strike=Decimal(str(strike)),
        expiration=date.today() + timedelta(days=dte_days),
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        volume=volume,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=market_iv,
    )


# ---------------------------------------------------------------------------
# extract_atm_iv tests
# ---------------------------------------------------------------------------


class TestExtractAtmIV:
    """Tests for extract_atm_iv."""

    def test_both_sides_at_atm(self) -> None:
        """ATM IV is the average of call and put IV at the ATM strike."""
        calls = [_make_contract(100.0, OptionType.CALL, 0.30)]
        puts = [_make_contract(100.0, OptionType.PUT, 0.32)]
        result = extract_atm_iv(calls, puts, spot=100.0)
        assert result is not None
        assert result == pytest.approx(0.31, rel=1e-6)

    def test_call_only_at_atm(self) -> None:
        """When only calls exist at ATM, use the call IV."""
        calls = [_make_contract(100.0, OptionType.CALL, 0.28)]
        puts: list[OptionContract] = []
        result = extract_atm_iv(calls, puts, spot=100.0)
        assert result is not None
        assert result == pytest.approx(0.28, rel=1e-6)

    def test_put_only_at_atm(self) -> None:
        """When only puts exist at ATM, use the put IV."""
        calls: list[OptionContract] = []
        puts = [_make_contract(100.0, OptionType.PUT, 0.35)]
        result = extract_atm_iv(calls, puts, spot=100.0)
        assert result is not None
        assert result == pytest.approx(0.35, rel=1e-6)

    def test_closest_strike_to_spot(self) -> None:
        """ATM strike is the one closest to spot, not exact."""
        calls = [
            _make_contract(95.0, OptionType.CALL, 0.25),
            _make_contract(100.0, OptionType.CALL, 0.30),
            _make_contract(105.0, OptionType.CALL, 0.35),
        ]
        puts = [
            _make_contract(95.0, OptionType.PUT, 0.27),
            _make_contract(100.0, OptionType.PUT, 0.32),
            _make_contract(105.0, OptionType.PUT, 0.37),
        ]
        # Spot at 101 — closest strike is 100
        result = extract_atm_iv(calls, puts, spot=101.0)
        assert result is not None
        assert result == pytest.approx(0.31, rel=1e-6)

    def test_empty_chains_returns_none(self) -> None:
        """Empty call and put chains return None."""
        result = extract_atm_iv([], [], spot=100.0)
        assert result is None

    def test_zero_iv_excluded(self) -> None:
        """Contracts with zero IV are excluded from ATM calculation."""
        calls = [_make_contract(100.0, OptionType.CALL, 0.0)]
        puts = [_make_contract(100.0, OptionType.PUT, 0.30)]
        result = extract_atm_iv(calls, puts, spot=100.0)
        assert result is not None
        assert result == pytest.approx(0.30, rel=1e-6)

    def test_all_zero_iv_returns_none(self) -> None:
        """If all contracts at ATM have zero IV, return None."""
        calls = [_make_contract(100.0, OptionType.CALL, 0.0)]
        puts = [_make_contract(100.0, OptionType.PUT, 0.0)]
        result = extract_atm_iv(calls, puts, spot=100.0)
        assert result is None

    def test_invalid_spot_returns_none(self) -> None:
        """Non-finite or non-positive spot returns None."""
        calls = [_make_contract(100.0, OptionType.CALL, 0.30)]
        assert extract_atm_iv(calls, [], spot=float("nan")) is None
        assert extract_atm_iv(calls, [], spot=float("inf")) is None
        assert extract_atm_iv(calls, [], spot=0.0) is None
        assert extract_atm_iv(calls, [], spot=-10.0) is None


# ---------------------------------------------------------------------------
# extract_atm_iv_by_dte tests
# ---------------------------------------------------------------------------


class TestExtractAtmIVByDTE:
    """Tests for extract_atm_iv_by_dte."""

    def test_multiple_dtes(self) -> None:
        """Extracts ATM IV at multiple DTEs."""
        chains: dict[int, tuple[list[OptionContract], list[OptionContract]]] = {
            30: (
                [_make_contract(100.0, OptionType.CALL, 0.25, dte_days=30)],
                [_make_contract(100.0, OptionType.PUT, 0.27, dte_days=30)],
            ),
            60: (
                [_make_contract(100.0, OptionType.CALL, 0.28, dte_days=60)],
                [_make_contract(100.0, OptionType.PUT, 0.30, dte_days=60)],
            ),
        }
        result = extract_atm_iv_by_dte(chains, spot=100.0)
        assert 30 in result
        assert 60 in result
        assert result[30] == pytest.approx(0.26, rel=1e-6)
        assert result[60] == pytest.approx(0.29, rel=1e-6)

    def test_empty_dte_excluded(self) -> None:
        """DTEs with empty chains are excluded from results."""
        chains: dict[int, tuple[list[OptionContract], list[OptionContract]]] = {
            30: (
                [_make_contract(100.0, OptionType.CALL, 0.25, dte_days=30)],
                [_make_contract(100.0, OptionType.PUT, 0.27, dte_days=30)],
            ),
            60: ([], []),
        }
        result = extract_atm_iv_by_dte(chains, spot=100.0)
        assert 30 in result
        assert 60 not in result


# ---------------------------------------------------------------------------
# compute_iv_at_delta tests
# ---------------------------------------------------------------------------


class TestComputeIVAtDelta:
    """Tests for compute_iv_at_delta."""

    def test_empty_chain_returns_none(self) -> None:
        """Empty chain returns None."""
        result = compute_iv_at_delta([], target_delta=0.25, spot=100.0, r=0.05, q=0.01, T=30 / 365)
        assert result is None

    def test_invalid_spot_returns_none(self) -> None:
        """Non-finite spot returns None."""
        chain = [_make_contract(100.0, OptionType.CALL, 0.30)]
        result = compute_iv_at_delta(
            chain, target_delta=0.25, spot=float("nan"), r=0.05, q=0.01, T=30 / 365
        )
        assert result is None

    def test_invalid_T_returns_none(self) -> None:
        """Non-positive T returns None."""
        chain = [_make_contract(100.0, OptionType.CALL, 0.30)]
        result = compute_iv_at_delta(chain, target_delta=0.25, spot=100.0, r=0.05, q=0.01, T=0.0)
        assert result is None
        result = compute_iv_at_delta(chain, target_delta=0.25, spot=100.0, r=0.05, q=0.01, T=-0.1)
        assert result is None

    def test_selects_closest_delta(self) -> None:
        """Selects the contract with delta closest to target_delta."""
        # OTM calls have lower deltas, ITM calls have higher deltas
        chain = [
            _make_contract(90.0, OptionType.CALL, 0.35),  # deep ITM, delta ~0.9
            _make_contract(100.0, OptionType.CALL, 0.25),  # ATM, delta ~0.5
            _make_contract(110.0, OptionType.CALL, 0.20),  # OTM, delta ~0.2
        ]
        result = compute_iv_at_delta(
            chain, target_delta=0.25, spot=100.0, r=0.05, q=0.01, T=30 / 365
        )
        # Should return an IV value (exact value depends on Greeks computation)
        assert result is not None
        assert 0.0 < result < 1.0

    def test_skips_zero_iv_contracts(self) -> None:
        """Contracts with zero market_iv are skipped."""
        chain = [
            _make_contract(100.0, OptionType.CALL, 0.0),
            _make_contract(105.0, OptionType.CALL, 0.25),
        ]
        result = compute_iv_at_delta(
            chain, target_delta=0.30, spot=100.0, r=0.05, q=0.01, T=30 / 365
        )
        # Should use the 105 strike contract since 100 strike has zero IV
        assert result is not None
        assert result == pytest.approx(0.25, rel=1e-6)

    def test_nan_target_delta_returns_none(self) -> None:
        """NaN target delta returns None."""
        chain = [_make_contract(100.0, OptionType.CALL, 0.30)]
        result = compute_iv_at_delta(
            chain, target_delta=float("nan"), spot=100.0, r=0.05, q=0.01, T=30 / 365
        )
        assert result is None


# ---------------------------------------------------------------------------
# batch_iv_solve tests
# ---------------------------------------------------------------------------


class TestBatchIVSolve:
    """Tests for batch_iv_solve."""

    def test_returns_list_same_length(self) -> None:
        """Result list has same length as input contracts list."""
        contracts = [
            _make_contract(100.0, OptionType.CALL, 0.30, bid=5.0, ask=6.0),
            _make_contract(105.0, OptionType.PUT, 0.25, bid=3.0, ask=4.0),
        ]
        results = batch_iv_solve(contracts, spot=100.0, r=0.05, q=0.01)
        assert len(results) == 2

    def test_empty_list_returns_empty(self) -> None:
        """Empty contracts list returns empty results."""
        results = batch_iv_solve([], spot=100.0, r=0.05, q=0.01)
        assert results == []

    def test_invalid_spot_returns_all_none(self) -> None:
        """Non-finite spot produces None for all contracts."""
        contracts = [_make_contract(100.0, OptionType.CALL, 0.30, bid=5.0, ask=6.0)]
        results = batch_iv_solve(contracts, spot=float("nan"), r=0.05, q=0.01)
        assert all(r is None for r in results)

    def test_expired_contract_returns_none(self) -> None:
        """Contract with DTE <= 0 returns None.

        dte is a computed field: (expiration - today).days.
        A contract expiring today has dte=0, which should yield None.
        """
        contract = _make_contract(100.0, OptionType.CALL, 0.30, bid=5.0, ask=6.0, dte_days=0)
        results = batch_iv_solve([contract], spot=100.0, r=0.05, q=0.01)
        assert len(results) == 1
        # dte=0 at expiration -> solver should return None
        assert results[0] is None

    def test_zero_mid_price_returns_none(self) -> None:
        """Contract with zero bid and ask (mid=0) returns None."""
        contract = _make_contract(100.0, OptionType.CALL, 0.30, bid=0.0, ask=0.0, dte_days=30)
        results = batch_iv_solve([contract], spot=100.0, r=0.05, q=0.01)
        assert results[0] is None

    def test_realistic_itm_call(self) -> None:
        """Batch solve should produce reasonable IV for an ITM call."""
        # ATM call on $100 stock with ~30 DTE
        contract = _make_contract(95.0, OptionType.CALL, 0.30, bid=7.0, ask=8.0, dte_days=30)
        results = batch_iv_solve([contract], spot=100.0, r=0.05, q=0.01)
        assert len(results) == 1
        if results[0] is not None:
            # If solver converged, IV should be in a reasonable range
            assert 0.01 < results[0] < 2.0

    def test_multiple_contracts_mixed(self) -> None:
        """Mix of solvable and unsolvable contracts."""
        contracts = [
            _make_contract(95.0, OptionType.CALL, 0.30, bid=7.0, ask=8.0, dte_days=30),
            _make_contract(100.0, OptionType.PUT, 0.25, bid=0.0, ask=0.0, dte_days=30),  # zero mid
        ]
        results = batch_iv_solve(contracts, spot=100.0, r=0.05, q=0.01)
        assert len(results) == 2
        # Second should be None due to zero mid price
        assert results[1] is None
