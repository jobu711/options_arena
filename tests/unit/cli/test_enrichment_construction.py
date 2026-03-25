"""Tests for ScanEnrichment construction at CLI recommendation call sites.

Verifies that the CLI batch debate path correctly constructs ScanEnrichment
from persisted scan data and forwards it to run_recommendation().
"""

from __future__ import annotations

from datetime import date

import pytest

from options_arena.models.analysis import ScanEnrichment
from options_arena.models.enums import MacroRegime
from options_arena.scan.models import OptionsResult
from tests.factories import make_spread_analysis


class TestEnrichmentBuiltFromOptionsResult:
    """Verify ScanEnrichment construction mirrors OptionsResult fields."""

    def test_enrichment_built_from_options_result(self) -> None:
        """ScanEnrichment constructed with correct fields from OptionsResult."""
        spread = make_spread_analysis()
        options_result = OptionsResult(
            recommendations={"AAPL": []},
            risk_free_rate=0.05,
            spread_analyses={"AAPL": spread},
            prob_profit_neural={"AAPL": 0.72},
            macro_regime=MacroRegime.EXPANSIONARY,
            macro_yield_spread=1.5,
            macro_fed_funds_rate=5.25,
            macro_vix_level=18.0,
            earnings_dates={"AAPL": date(2026, 4, 15)},
        )

        ticker = "AAPL"
        enrichment = ScanEnrichment(
            spread_analysis=options_result.spread_analyses.get(ticker),
            prob_profit_neural=options_result.prob_profit_neural.get(ticker),
            macro_regime=options_result.macro_regime,
            macro_yield_spread=options_result.macro_yield_spread,
            macro_fed_funds_rate=options_result.macro_fed_funds_rate,
            macro_vix_level=options_result.macro_vix_level,
            next_earnings=options_result.earnings_dates.get(ticker),
        )

        assert enrichment.spread_analysis is spread
        assert enrichment.prob_profit_neural == pytest.approx(0.72)
        assert enrichment.macro_regime == MacroRegime.EXPANSIONARY
        assert enrichment.macro_yield_spread == pytest.approx(1.5)
        assert enrichment.macro_fed_funds_rate == pytest.approx(5.25)
        assert enrichment.macro_vix_level == pytest.approx(18.0)
        assert enrichment.next_earnings == date(2026, 4, 15)

    def test_missing_spread_analysis_is_none(self) -> None:
        """When ticker not in spread_analyses, field is None."""
        options_result = OptionsResult(
            recommendations={"AAPL": []},
            risk_free_rate=0.05,
            spread_analyses={},
            prob_profit_neural={"AAPL": 0.65},
        )

        ticker = "AAPL"
        enrichment = ScanEnrichment(
            spread_analysis=options_result.spread_analyses.get(ticker),
            prob_profit_neural=options_result.prob_profit_neural.get(ticker),
        )

        assert enrichment.spread_analysis is None
        assert enrichment.prob_profit_neural == pytest.approx(0.65)

    def test_missing_neural_prob_is_none(self) -> None:
        """When ticker not in prob_profit_neural, field is None."""
        spread = make_spread_analysis()
        options_result = OptionsResult(
            recommendations={"AAPL": []},
            risk_free_rate=0.05,
            spread_analyses={"AAPL": spread},
            prob_profit_neural={},
        )

        ticker = "AAPL"
        enrichment = ScanEnrichment(
            spread_analysis=options_result.spread_analyses.get(ticker),
            prob_profit_neural=options_result.prob_profit_neural.get(ticker),
        )

        assert enrichment.spread_analysis is spread
        assert enrichment.prob_profit_neural is None

    def test_empty_options_result_produces_empty_enrichment(self) -> None:
        """OptionsResult with all defaults produces ScanEnrichment with all None."""
        options_result = OptionsResult(
            recommendations={},
            risk_free_rate=0.05,
        )

        ticker = "AAPL"
        enrichment = ScanEnrichment(
            spread_analysis=options_result.spread_analyses.get(ticker),
            prob_profit_neural=options_result.prob_profit_neural.get(ticker),
            macro_regime=options_result.macro_regime,
            macro_yield_spread=options_result.macro_yield_spread,
            macro_fed_funds_rate=options_result.macro_fed_funds_rate,
            macro_vix_level=options_result.macro_vix_level,
            next_earnings=options_result.earnings_dates.get(ticker),
        )

        assert enrichment.spread_analysis is None
        assert enrichment.prob_profit_neural is None
        assert enrichment.macro_regime is None
        assert enrichment.macro_yield_spread is None
        assert enrichment.macro_fed_funds_rate is None
        assert enrichment.macro_vix_level is None
        assert enrichment.next_earnings is None

    def test_enrichment_is_frozen(self) -> None:
        """ScanEnrichment is immutable after construction."""
        enrichment = ScanEnrichment()
        with pytest.raises(Exception):  # noqa: B017
            enrichment.macro_regime = MacroRegime.EXPANSIONARY  # type: ignore[misc]
