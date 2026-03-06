"""Unit tests for the macd field on IndicatorSignals.

Tests cover:
- Default value (None)
- Accepts valid float values (positive, negative, zero)
- NaN normalized to None by _normalize_non_finite model validator
- Inf/-Inf normalized to None by _normalize_non_finite model validator
- JSON serialization roundtrip with macd set
"""

from __future__ import annotations

import pytest

from options_arena.models import IndicatorSignals


class TestIndicatorSignalsMacd:
    """Tests for the macd field on IndicatorSignals."""

    def test_macd_field_default_none(self) -> None:
        """Verify macd field defaults to None."""
        signals = IndicatorSignals()
        assert signals.macd is None

    def test_macd_field_accepts_float(self) -> None:
        """Verify macd field accepts valid float values (positive, negative, zero)."""
        # Positive MACD (bullish crossover)
        signals_pos = IndicatorSignals(macd=65.0)
        assert signals_pos.macd == pytest.approx(65.0)

        # Negative MACD (bearish crossover)
        signals_neg = IndicatorSignals(macd=-12.5)
        assert signals_neg.macd == pytest.approx(-12.5)

        # Zero MACD (at crossover)
        signals_zero = IndicatorSignals(macd=0.0)
        assert signals_zero.macd == pytest.approx(0.0)

    def test_macd_nan_normalized_to_none(self) -> None:
        """Verify NaN is normalized to None by _normalize_non_finite."""
        signals = IndicatorSignals(macd=float("nan"))
        assert signals.macd is None

    def test_macd_inf_normalized_to_none(self) -> None:
        """Verify Inf is normalized to None by _normalize_non_finite."""
        signals_pos_inf = IndicatorSignals(macd=float("inf"))
        assert signals_pos_inf.macd is None

        signals_neg_inf = IndicatorSignals(macd=float("-inf"))
        assert signals_neg_inf.macd is None

    def test_json_roundtrip(self) -> None:
        """Verify model_validate_json(m.model_dump_json()) == m with macd set."""
        signals = IndicatorSignals(macd=42.7, rsi=65.0, adx=72.0)
        json_str = signals.model_dump_json()
        restored = IndicatorSignals.model_validate_json(json_str)
        assert restored == signals
        assert restored.macd == pytest.approx(42.7)
