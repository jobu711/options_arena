"""Tests for chain_spread_pct and chain_oi_depth computation."""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from options_arena.scan.indicators import compute_phase3_indicators


def _make_contract(
    bid: float,
    ask: float,
    open_interest: int,
    *,
    strike: float = 100.0,
    volume: int = 100,
) -> OptionContract:
    """Build a minimal OptionContract for testing."""
    return OptionContract(
        ticker="TEST",
        option_type=OptionType.CALL,
        strike=Decimal(str(strike)),
        expiration=date.today() + timedelta(days=30),
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        volume=volume,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.25,
    )


def _make_close_series(n: int = 250, start: float = 100.0) -> pd.Series:
    """Build a simple close price series for compute_phase3_indicators."""
    dates = pd.bdate_range(end=date.today(), periods=n)
    prices = np.linspace(start, start * 1.1, len(dates))
    return pd.Series(prices, index=dates)


class TestChainSpreadPct:
    def test_basic_computation(self) -> None:
        """Verify OI-weighted spread percentage with known values."""
        # Contract: bid=99, ask=101, mid=100, spread=2, spread_pct=2.0%
        # OI=1000
        contracts = [_make_contract(99.0, 101.0, 1000)]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_spread_pct is not None
        assert signals.chain_spread_pct == pytest.approx(2.0, abs=0.01)

    def test_zero_mid_excluded(self) -> None:
        """Verify contracts with bid=ask=0 are excluded from spread calc."""
        contracts = [
            _make_contract(0.0, 0.0, 500),  # zero mid, excluded
            _make_contract(99.0, 101.0, 1000),  # valid
        ]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_spread_pct is not None
        assert signals.chain_spread_pct == pytest.approx(2.0, abs=0.01)

    def test_single_contract(self) -> None:
        """Verify single contract returns its spread percentage."""
        # bid=9.5, ask=10.5, mid=10, spread=1, spread_pct=10%
        contracts = [_make_contract(9.5, 10.5, 500)]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_spread_pct is not None
        assert signals.chain_spread_pct == pytest.approx(10.0, abs=0.01)

    def test_oi_weighting(self) -> None:
        """Verify higher-OI contracts dominate the average."""
        contracts = [
            _make_contract(99.0, 101.0, 9000),  # 2% spread, high OI
            _make_contract(90.0, 110.0, 1000),  # 20% spread, low OI
        ]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_spread_pct is not None
        # Weighted: (2.0 * 9000 + 20.0 * 1000) / 10000 = 3.8
        assert signals.chain_spread_pct == pytest.approx(3.8, abs=0.1)

    def test_empty_chain_returns_none(self) -> None:
        """Verify empty contract list returns None."""
        close = _make_close_series()
        signals = compute_phase3_indicators([], 100.0, close, 0.0, None, None)
        assert signals.chain_spread_pct is None
        assert signals.chain_oi_depth is None


class TestChainOiDepth:
    def test_basic_computation(self) -> None:
        """Verify log10(total_oi + 1) with known values."""
        # total_oi = 1000, log10(1001) ~ 3.0004
        contracts = [_make_contract(99.0, 101.0, 1000)]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_oi_depth is not None
        assert signals.chain_oi_depth == pytest.approx(math.log10(1001), abs=0.001)

    def test_zero_oi(self) -> None:
        """Verify zero total OI returns log10(1) = 0.0."""
        contracts = [_make_contract(99.0, 101.0, 0)]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_oi_depth is not None
        assert signals.chain_oi_depth == pytest.approx(0.0, abs=0.001)

    def test_large_oi(self) -> None:
        """Verify large OI (1M+) returns ~6.0."""
        contracts = [_make_contract(99.0, 101.0, 1_000_000)]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_oi_depth is not None
        assert signals.chain_oi_depth == pytest.approx(math.log10(1_000_001), abs=0.001)

    def test_single_contract(self) -> None:
        """Verify single contract sums correctly."""
        contracts = [_make_contract(99.0, 101.0, 500)]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_oi_depth is not None
        assert signals.chain_oi_depth == pytest.approx(math.log10(501), abs=0.001)

    def test_multiple_contracts_sum_oi(self) -> None:
        """Verify OI is summed across all contracts."""
        contracts = [
            _make_contract(99.0, 101.0, 500),
            _make_contract(95.0, 105.0, 500),
        ]
        close = _make_close_series()
        signals = compute_phase3_indicators(contracts, 100.0, close, 0.0, None, None)
        assert signals.chain_oi_depth is not None
        assert signals.chain_oi_depth == pytest.approx(math.log10(1001), abs=0.001)
