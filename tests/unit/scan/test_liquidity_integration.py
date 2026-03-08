"""Integration tests for liquidity indicators through the scoring pipeline.

Verifies the end-to-end flow: computation → normalization → composite score impact.
"""

from __future__ import annotations

import pytest

from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.composite import INDICATOR_WEIGHTS, composite_score
from options_arena.scoring.normalization import (
    INVERTED_INDICATORS,
    normalize_single_ticker,
    percentile_rank_normalize,
)


class TestLiquidityIntegration:
    def test_normalization_inverts_spread(self) -> None:
        """Verify higher chain_spread_pct → lower normalized score.

        chain_spread_pct is in INVERTED_INDICATORS, so higher raw value
        (worse liquidity) should produce a lower normalized score.
        """
        assert "chain_spread_pct" in INVERTED_INDICATORS

        # Domain bounds: (0.0, 30.0)
        low_spread = IndicatorSignals(chain_spread_pct=2.0)  # tight spread (good)
        high_spread = IndicatorSignals(chain_spread_pct=25.0)  # wide spread (bad)

        norm_low = normalize_single_ticker(low_spread)
        norm_high = normalize_single_ticker(high_spread)

        # After inversion, low raw spread → high normalized score
        assert norm_low.chain_spread_pct is not None
        assert norm_high.chain_spread_pct is not None
        assert norm_low.chain_spread_pct > norm_high.chain_spread_pct

    def test_normalization_preserves_oi_depth(self) -> None:
        """Verify higher chain_oi_depth → higher normalized score.

        chain_oi_depth is NOT inverted — higher depth is better.
        """
        assert "chain_oi_depth" not in INVERTED_INDICATORS

        low_depth = IndicatorSignals(chain_oi_depth=1.0)  # low OI
        high_depth = IndicatorSignals(chain_oi_depth=5.0)  # high OI

        norm_low = normalize_single_ticker(low_depth)
        norm_high = normalize_single_ticker(high_depth)

        assert norm_low.chain_oi_depth is not None
        assert norm_high.chain_oi_depth is not None
        assert norm_high.chain_oi_depth > norm_low.chain_oi_depth

    def test_composite_with_liquidity(self) -> None:
        """Verify composite score includes liquidity weight contribution."""
        # Signals with liquidity fields populated at high values
        signals_with = IndicatorSignals(
            rsi=75.0,
            adx=60.0,
            chain_spread_pct=90.0,  # normalized (inverted) high = good
            chain_oi_depth=80.0,  # normalized high = good
        )
        # Same signals without liquidity
        signals_without = IndicatorSignals(
            rsi=75.0,
            adx=60.0,
        )

        score_with = composite_score(signals_with)
        score_without = composite_score(signals_without)

        # Both should produce valid scores
        assert score_with > 0.0
        assert score_without > 0.0
        # Scores differ because liquidity fields contribute weight
        assert score_with != pytest.approx(score_without, abs=0.01)

    def test_composite_without_liquidity(self) -> None:
        """Verify composite score unchanged when both liquidity fields are None."""
        signals = IndicatorSignals(
            rsi=75.0,
            adx=60.0,
            sma_alignment=80.0,
        )

        score = composite_score(signals)
        assert score > 0.0

        # Setting fields to None explicitly should give same result
        signals_explicit_none = IndicatorSignals(
            rsi=75.0,
            adx=60.0,
            sma_alignment=80.0,
            chain_spread_pct=None,
            chain_oi_depth=None,
        )
        score_explicit = composite_score(signals_explicit_none)
        assert score == pytest.approx(score_explicit, abs=1e-9)

    def test_backward_compat_json(self) -> None:
        """Verify pre-liquidity JSON loads with new fields as None."""
        json_str = '{"rsi": 55.0, "adx": 30.0}'
        signals = IndicatorSignals.model_validate_json(json_str)
        assert signals.chain_spread_pct is None
        assert signals.chain_oi_depth is None

        # Composite score still works
        score = composite_score(signals)
        assert score > 0.0

    def test_partial_liquidity_one_field_only(self) -> None:
        """Verify composite works with only one liquidity field populated."""
        signals_spread_only = IndicatorSignals(
            rsi=75.0,
            chain_spread_pct=50.0,
        )
        signals_depth_only = IndicatorSignals(
            rsi=75.0,
            chain_oi_depth=50.0,
        )

        score_spread = composite_score(signals_spread_only)
        score_depth = composite_score(signals_depth_only)

        assert score_spread > 0.0
        assert score_depth > 0.0

    def test_percentile_rank_with_liquidity(self) -> None:
        """Verify percentile normalization works with liquidity fields."""
        universe = {
            "AAPL": IndicatorSignals(
                rsi=70.0,
                chain_spread_pct=2.0,
                chain_oi_depth=5.0,
            ),
            "MSFT": IndicatorSignals(
                rsi=30.0,
                chain_spread_pct=15.0,
                chain_oi_depth=3.0,
            ),
            "GOOG": IndicatorSignals(
                rsi=50.0,
                chain_spread_pct=8.0,
                chain_oi_depth=4.0,
            ),
        }

        normalized = percentile_rank_normalize(universe)

        # AAPL has lowest spread (best) → after percentile-rank + inversion → highest
        assert normalized["AAPL"].chain_spread_pct is not None
        assert normalized["MSFT"].chain_spread_pct is not None
        # Note: percentile_rank_normalize does NOT invert; that's done by invert_indicators
        # But it should produce valid percentile values
        assert 0.0 <= normalized["AAPL"].chain_spread_pct <= 100.0

        # AAPL has highest OI depth → highest percentile rank
        assert normalized["AAPL"].chain_oi_depth is not None
        assert normalized["AAPL"].chain_oi_depth == pytest.approx(100.0)  # highest of 3

    def test_liquidity_weight_in_indicator_weights(self) -> None:
        """Verify both liquidity indicators are weighted in composite scoring."""
        assert "chain_spread_pct" in INDICATOR_WEIGHTS
        assert "chain_oi_depth" in INDICATOR_WEIGHTS

        total_liquidity_weight = (
            INDICATOR_WEIGHTS["chain_spread_pct"][0]
            + INDICATOR_WEIGHTS["chain_oi_depth"][0]
        )
        assert total_liquidity_weight == pytest.approx(0.06, abs=1e-9)
