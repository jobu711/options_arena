"""Tests for TickerScore dimensional scoring fields (market_regime)."""

import pytest
from pydantic import ValidationError

from options_arena.models import (
    IndicatorSignals,
    MarketRegime,
    SignalDirection,
    TickerScore,
)
from options_arena.models.scoring import DimensionalScores


def _make_ticker_score(**overrides: object) -> TickerScore:
    """Build a TickerScore with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "composite_score": 78.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1),
    }
    defaults.update(overrides)
    return TickerScore(**defaults)  # type: ignore[arg-type]


class TestTickerScoreMarketRegimeField:
    """Tests for the market_regime field on TickerScore."""

    def test_market_regime_none_default(self) -> None:
        """Verify market_regime defaults to None."""
        ts = _make_ticker_score()
        assert ts.market_regime is None

    def test_market_regime_trending(self) -> None:
        """Verify TRENDING value is accepted."""
        ts = _make_ticker_score(market_regime=MarketRegime.TRENDING)
        assert ts.market_regime is MarketRegime.TRENDING
        assert ts.market_regime == "trending"

    def test_market_regime_mean_reverting(self) -> None:
        """Verify MEAN_REVERTING value is accepted."""
        ts = _make_ticker_score(market_regime=MarketRegime.MEAN_REVERTING)
        assert ts.market_regime is MarketRegime.MEAN_REVERTING

    def test_market_regime_volatile(self) -> None:
        """Verify VOLATILE value is accepted."""
        ts = _make_ticker_score(market_regime=MarketRegime.VOLATILE)
        assert ts.market_regime is MarketRegime.VOLATILE

    def test_market_regime_crisis(self) -> None:
        """Verify CRISIS value is accepted."""
        ts = _make_ticker_score(market_regime=MarketRegime.CRISIS)
        assert ts.market_regime is MarketRegime.CRISIS

    def test_market_regime_from_string(self) -> None:
        """Verify string 'volatile' coerces to MarketRegime enum."""
        ts = _make_ticker_score(market_regime="volatile")
        assert ts.market_regime is MarketRegime.VOLATILE

    def test_market_regime_invalid_value_rejected(self) -> None:
        """Verify invalid market_regime value raises ValidationError."""
        with pytest.raises(ValidationError):
            _make_ticker_score(market_regime="unknown_regime")

    def test_ticker_score_json_roundtrip_with_all_new_fields(self) -> None:
        """Verify model_dump_json/model_validate_json roundtrip with dimensional data."""
        dim_scores = DimensionalScores(
            trend=75.0,
            iv_vol=60.0,
            hv_vol=45.0,
            flow=30.0,
            microstructure=50.0,
            fundamental=80.0,
            regime=55.0,
            risk=25.0,
        )
        ts = _make_ticker_score(
            dimensional_scores=dim_scores,
            direction_confidence=0.73,
            market_regime=MarketRegime.VOLATILE,
        )
        json_str = ts.model_dump_json()
        restored = TickerScore.model_validate_json(json_str)

        assert restored.dimensional_scores is not None
        assert restored.dimensional_scores.trend == pytest.approx(75.0)
        assert restored.direction_confidence == pytest.approx(0.73)
        assert restored.market_regime is MarketRegime.VOLATILE

    def test_ticker_score_json_roundtrip_with_none_fields(self) -> None:
        """Verify roundtrip works when dimensional fields are None."""
        ts = _make_ticker_score()
        json_str = ts.model_dump_json()
        restored = TickerScore.model_validate_json(json_str)

        assert restored.dimensional_scores is None
        assert restored.direction_confidence is None
        assert restored.market_regime is None

    def test_market_regime_mutable(self) -> None:
        """Verify TickerScore (NOT frozen) allows setting market_regime after init."""
        ts = _make_ticker_score()
        assert ts.market_regime is None
        ts.market_regime = MarketRegime.CRISIS
        assert ts.market_regime is MarketRegime.CRISIS

    def test_all_market_regime_values_accepted(self) -> None:
        """Verify all 4 MarketRegime enum values work on TickerScore."""
        for regime in MarketRegime:
            ts = _make_ticker_score(market_regime=regime)
            assert ts.market_regime is regime
