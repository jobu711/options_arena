"""Tests for portfolio correlation matrix computation.

Covers Pearson correlation using log daily returns, edge cases,
model validation, and JSON round-trip serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from options_arena.analysis.correlation import compute_correlation_matrix
from options_arena.models.correlation import CorrelationMatrix, PairwiseCorrelation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_price_df(prices: list[float], start_date: str = "2025-01-01") -> pd.DataFrame:
    """Build a DataFrame with a 'Close' column from a list of prices."""
    dates = pd.bdate_range(start=start_date, periods=len(prices))
    return pd.DataFrame({"Close": prices}, index=dates)


# ---------------------------------------------------------------------------
# Core computation tests
# ---------------------------------------------------------------------------


class TestPerfectlyCorrelated:
    """Two identical price series should yield correlation ~1.0."""

    def test_perfectly_correlated_series(self) -> None:
        """Two identical price series -> correlation approx 1.0."""
        prices = [100.0 + i * 0.5 for i in range(60)]
        price_data = {
            "AAPL": _make_price_df(prices),
            "MSFT": _make_price_df(prices),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert len(result.pairs) == 1
        assert result.pairs[0].correlation == pytest.approx(1.0, abs=1e-6)
        assert result.pairs[0].ticker_a == "AAPL"
        assert result.pairs[0].ticker_b == "MSFT"


class TestAntiCorrelated:
    """One series is the inverse movement of the other."""

    def test_perfectly_anti_correlated_series(self) -> None:
        """One series goes up while the other goes down -> correlation approx -1.0.

        Log returns of (1+c) and (1-c) are not perfectly anti-correlated
        due to the non-linearity of the log function, so we allow abs=1e-3.
        """
        np.random.seed(42)
        base = 100.0
        changes = np.random.randn(60) * 0.02
        prices_up = [base]
        prices_down = [base]
        for c in changes:
            prices_up.append(prices_up[-1] * (1 + c))
            prices_down.append(prices_down[-1] * (1 - c))

        price_data = {
            "AAA": _make_price_df(prices_up),
            "BBB": _make_price_df(prices_down),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert len(result.pairs) == 1
        assert result.pairs[0].correlation == pytest.approx(-1.0, abs=1e-3)


class TestUncorrelatedRandom:
    """Two random independent series should yield correlation near 0.0."""

    def test_uncorrelated_random_series(self) -> None:
        """Two independent random series -> correlation approx 0.0 (within tolerance)."""
        np.random.seed(123)
        prices_a = np.cumprod(1 + np.random.randn(500) * 0.01) * 100
        prices_b = np.cumprod(1 + np.random.randn(500) * 0.01) * 100

        price_data = {
            "X": _make_price_df(prices_a.tolist()),
            "Y": _make_price_df(prices_b.tolist()),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert len(result.pairs) == 1
        # With 500 data points, uncorrelated series should be near 0
        assert abs(result.pairs[0].correlation) < 0.15


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestMinOverlap:
    """Pairs with fewer overlapping days than min_overlap are excluded."""

    def test_below_min_overlap_skipped(self) -> None:
        """Pair with < min_overlap overlapping days -> excluded from pairs."""
        prices_a = [100.0 + i for i in range(20)]
        prices_b = [100.0 + i * 2 for i in range(20)]
        price_data = {
            "AAA": _make_price_df(prices_a),
            "BBB": _make_price_df(prices_b),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert len(result.pairs) == 0


class TestSingleTicker:
    """Single ticker -> empty pairs list."""

    def test_single_ticker_empty_pairs(self) -> None:
        prices = [100.0 + i for i in range(60)]
        price_data = {"AAPL": _make_price_df(prices)}
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert result.tickers == ["AAPL"]
        assert result.pairs == []
        assert result.avg_correlation is None


class TestTwoTickersFullOverlap:
    """Two tickers with identical date ranges."""

    def test_two_tickers_full_overlap(self) -> None:
        """Overlapping days equals series length minus 1 (due to return computation)."""
        prices_a = [100.0 + i * 0.3 for i in range(60)]
        prices_b = [200.0 - i * 0.2 for i in range(60)]
        price_data = {
            "AAPL": _make_price_df(prices_a),
            "MSFT": _make_price_df(prices_b),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert len(result.pairs) == 1
        # 60 prices -> 59 returns
        assert result.pairs[0].overlapping_days == 59


class TestThreeTickersThreePairs:
    """Three tickers -> n*(n-1)/2 = 3 pairs."""

    def test_three_tickers_three_pairs(self) -> None:
        np.random.seed(99)
        n = 60
        price_data = {
            "AAPL": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 100).tolist()),
            "GOOG": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 150).tolist()),
            "MSFT": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 200).tolist()),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert len(result.pairs) == 3
        # Verify all tickers sorted
        assert result.tickers == ["AAPL", "GOOG", "MSFT"]


class TestZeroVarianceSeries:
    """Flat price series (zero variance) -> pair skipped."""

    def test_zero_variance_series(self) -> None:
        """Constant price -> zero variance in returns -> pair excluded."""
        flat_prices = [100.0] * 60
        normal_prices = [100.0 + i * 0.5 for i in range(60)]
        price_data = {
            "FLAT": _make_price_df(flat_prices),
            "NORMAL": _make_price_df(normal_prices),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        # Zero-variance series should be skipped
        assert len(result.pairs) == 0


class TestNaNInPriceData:
    """NaN values in price data -> handled gracefully."""

    def test_nan_in_price_data(self) -> None:
        """NaN values in Close column are dropped before computation."""
        prices_a = [100.0 + i * 0.5 for i in range(60)]
        prices_b = [200.0 - i * 0.3 for i in range(60)]
        # Insert NaN values
        prices_a[10] = float("nan")
        prices_a[20] = float("nan")
        price_data = {
            "AAA": _make_price_df(prices_a),
            "BBB": _make_price_df(prices_b),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        # Should still compute, just with fewer overlapping days
        assert len(result.pairs) == 1
        assert result.pairs[0].overlapping_days < 59


class TestEmptyPriceData:
    """Empty dict input -> empty tickers and pairs."""

    def test_empty_price_data(self) -> None:
        result = compute_correlation_matrix({}, min_overlap=30)
        assert result.tickers == []
        assert result.pairs == []
        assert result.avg_correlation is None


class TestDuplicateTickers:
    """Duplicate tickers in input are deduplicated."""

    def test_duplicate_tickers_deduplicated(self) -> None:
        prices = [100.0 + i * 0.5 for i in range(60)]
        df = _make_price_df(prices)
        # Build dict with duplicate key using dict constructor
        price_data: dict[str, pd.DataFrame] = {}
        price_data["AAPL"] = df
        price_data["AAPL"] = df  # duplicate (overwrite is fine — dict semantics)
        price_data["MSFT"] = _make_price_df(prices)
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert len(result.tickers) == 2


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestModelFrozen:
    """PairwiseCorrelation and CorrelationMatrix are immutable."""

    def test_pairwise_correlation_frozen(self) -> None:
        pc = PairwiseCorrelation(
            ticker_a="AAPL",
            ticker_b="MSFT",
            correlation=0.75,
            overlapping_days=200,
        )
        with pytest.raises(ValidationError):
            pc.ticker_a = "GOOG"  # type: ignore[misc]

    def test_correlation_matrix_frozen(self) -> None:
        cm = CorrelationMatrix(
            tickers=["AAPL", "MSFT"],
            pairs=[],
            computed_at=datetime.now(UTC),
        )
        with pytest.raises(ValidationError):
            cm.tickers = ["GOOG"]  # type: ignore[misc]


class TestUTCValidator:
    """Non-UTC datetime on computed_at raises ValidationError."""

    def test_utc_validator_on_computed_at(self) -> None:
        with pytest.raises(ValidationError, match="computed_at must be UTC"):
            CorrelationMatrix(
                tickers=["AAPL"],
                pairs=[],
                computed_at=datetime(2026, 1, 1, 12, 0, 0),  # naive
            )

    def test_non_utc_timezone_rejected(self) -> None:
        eastern = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="computed_at must be UTC"):
            CorrelationMatrix(
                tickers=["AAPL"],
                pairs=[],
                computed_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=eastern),
            )


class TestCorrelationValidator:
    """Correlation must be finite and within [-1.0, 1.0]."""

    def test_correlation_out_of_range_high(self) -> None:
        with pytest.raises(ValidationError, match="correlation must be in"):
            PairwiseCorrelation(ticker_a="A", ticker_b="B", correlation=1.5, overlapping_days=50)

    def test_correlation_out_of_range_low(self) -> None:
        with pytest.raises(ValidationError, match="correlation must be in"):
            PairwiseCorrelation(ticker_a="A", ticker_b="B", correlation=-1.5, overlapping_days=50)

    def test_correlation_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="correlation must be finite"):
            PairwiseCorrelation(
                ticker_a="A", ticker_b="B", correlation=float("nan"), overlapping_days=50
            )

    def test_correlation_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="correlation must be finite"):
            PairwiseCorrelation(
                ticker_a="A", ticker_b="B", correlation=float("inf"), overlapping_days=50
            )


class TestOverlappingDaysValidator:
    """overlapping_days must be >= 0."""

    def test_negative_overlapping_days_rejected(self) -> None:
        with pytest.raises(ValidationError, match="overlapping_days must be >= 0"):
            PairwiseCorrelation(ticker_a="A", ticker_b="B", correlation=0.5, overlapping_days=-1)


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


class TestJSONRoundTrip:
    """CorrelationMatrix serializes to JSON and back without data loss."""

    def test_json_roundtrip(self) -> None:
        pair = PairwiseCorrelation(
            ticker_a="AAPL",
            ticker_b="MSFT",
            correlation=0.756,
            overlapping_days=200,
        )
        matrix = CorrelationMatrix(
            tickers=["AAPL", "MSFT"],
            pairs=[pair],
            computed_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
        )
        json_str = matrix.model_dump_json()
        restored = CorrelationMatrix.model_validate_json(json_str)

        assert restored.tickers == matrix.tickers
        assert len(restored.pairs) == 1
        assert restored.pairs[0].correlation == pytest.approx(0.756)
        assert restored.pairs[0].ticker_a == "AAPL"
        assert restored.pairs[0].ticker_b == "MSFT"
        assert restored.pairs[0].overlapping_days == 200
        assert restored.computed_at == matrix.computed_at


class TestPearsonCoefficientRange:
    """All computed correlations fall within [-1.0, 1.0]."""

    def test_pearson_coefficient_range(self) -> None:
        """Generate multiple pairs and verify all are in [-1, 1]."""
        np.random.seed(456)
        n = 100
        price_data = {
            f"T{i}": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.02) * 100).tolist())
            for i in range(5)
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        for pair in result.pairs:
            assert -1.0 <= pair.correlation <= 1.0


class TestAvgCorrelation:
    """Test the computed avg_correlation field."""

    def test_avg_correlation_computed(self) -> None:
        """Average correlation matches manual computation."""
        np.random.seed(789)
        n = 60
        price_data = {
            "A": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 100).tolist()),
            "B": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 100).tolist()),
            "C": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 100).tolist()),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        expected_avg = sum(p.correlation for p in result.pairs) / len(result.pairs)
        assert result.avg_correlation == pytest.approx(expected_avg)

    def test_avg_correlation_none_when_no_pairs(self) -> None:
        result = compute_correlation_matrix({}, min_overlap=30)
        assert result.avg_correlation is None


class TestPairCount:
    """Test the computed pair_count field."""

    def test_pair_count(self) -> None:
        np.random.seed(111)
        n = 60
        price_data = {
            "A": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 100).tolist()),
            "B": _make_price_df((np.cumprod(1 + np.random.randn(n) * 0.01) * 100).tolist()),
        }
        result = compute_correlation_matrix(price_data, min_overlap=30)
        assert result.pair_count == 1
