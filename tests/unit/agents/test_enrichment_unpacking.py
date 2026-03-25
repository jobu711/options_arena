"""Tests for ScanEnrichment unpacking in the recommendation orchestrator.

Verifies that ``run_recommendation()`` correctly unpacks ``ScanEnrichment``
fields and passes them through ``build_market_context()`` into the resulting
``MarketContext``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic_ai import models

from options_arena.agents._context import build_market_context
from options_arena.models import (
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
    MacroRegime,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    ScanEnrichment,
    SignalDirection,
    TickerInfo,
    TickerScore,
)

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ticker_score() -> TickerScore:
    """Bullish ticker score for AAPL."""
    return TickerScore(
        ticker="AAPL",
        composite_score=72.5,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(
            rsi=62.3,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
            atr_pct=15.3,
            obv=65.0,
            relative_volume=55.0,
        ),
        scan_run_id=1,
    )


@pytest.fixture()
def quote() -> Quote:
    return Quote(
        ticker="AAPL",
        price=Decimal("185.50"),
        bid=Decimal("185.48"),
        ask=Decimal("185.52"),
        volume=42_000_000,
        timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture()
def ticker_info() -> TickerInfo:
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=2_800_000_000_000,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("185.50"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
    )


@pytest.fixture()
def contracts() -> list[OptionContract]:
    return [
        OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("190.00"),
            expiration=date(2026, 5, 15),
            bid=Decimal("4.50"),
            ask=Decimal("4.80"),
            last=Decimal("4.65"),
            volume=1500,
            open_interest=12000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.285,
            greeks=OptionGreeks(
                delta=0.35,
                gamma=0.025,
                theta=-0.045,
                vega=0.32,
                rho=0.08,
                pricing_model=PricingModel.BAW,
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Tests: ScanEnrichment unpacking
# ---------------------------------------------------------------------------


class TestEnrichmentUnpacking:
    """Verify ScanEnrichment fields flow through build_market_context()."""

    def test_none_enrichment_defaults(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contracts: list[OptionContract],
    ) -> None:
        """enrichment=None produces same behavior as before (all enrichment fields None)."""
        enrich = ScanEnrichment()
        context = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            contracts,
            next_earnings=enrich.next_earnings,
            fd_package=enrich.fd_package,
            macro_regime=enrich.macro_regime,
            macro_yield_spread=enrich.macro_yield_spread,
            macro_fed_funds_rate=enrich.macro_fed_funds_rate,
            macro_vix_level=enrich.macro_vix_level,
            prob_profit_neural=enrich.prob_profit_neural,
        )

        # All enrichment-sourced fields should be None
        assert context.next_earnings is None
        assert context.macro_regime is None
        assert context.yield_spread is None
        assert context.fed_funds_rate is None
        assert context.vix_level is None
        assert context.prob_profit_neural is None

        # Core fields from ticker_score/quote should still be populated
        assert context.ticker == "AAPL"
        assert context.current_price == Decimal("185.50")
        assert context.rsi_14 == pytest.approx(62.3, abs=0.01)

    def test_enrichment_populates_market_context(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contracts: list[OptionContract],
    ) -> None:
        """ScanEnrichment fields flow through to MarketContext."""
        enrich = ScanEnrichment(
            macro_regime=MacroRegime.EXPANSIONARY,
            macro_yield_spread=1.85,
            macro_fed_funds_rate=5.25,
            macro_vix_level=18.5,
            prob_profit_neural=0.72,
            next_earnings=date(2026, 4, 25),
        )
        context = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            contracts,
            next_earnings=enrich.next_earnings,
            fd_package=enrich.fd_package,
            macro_regime=enrich.macro_regime,
            macro_yield_spread=enrich.macro_yield_spread,
            macro_fed_funds_rate=enrich.macro_fed_funds_rate,
            macro_vix_level=enrich.macro_vix_level,
            prob_profit_neural=enrich.prob_profit_neural,
        )

        assert context.macro_regime == MacroRegime.EXPANSIONARY
        assert context.yield_spread == pytest.approx(1.85, abs=0.01)
        assert context.fed_funds_rate == pytest.approx(5.25, abs=0.01)
        assert context.vix_level == pytest.approx(18.5, abs=0.1)
        assert context.prob_profit_neural == pytest.approx(0.72, abs=0.01)
        assert context.next_earnings == date(2026, 4, 25)

    def test_macro_fields_unpacked(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contracts: list[OptionContract],
    ) -> None:
        """macro_regime, yield_spread, fed_funds_rate, vix_level reach build_market_context."""
        enrich = ScanEnrichment(
            macro_regime=MacroRegime.CONTRACTIONARY,
            macro_yield_spread=-0.45,
            macro_fed_funds_rate=4.75,
            macro_vix_level=32.1,
        )
        context = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            contracts,
            next_earnings=enrich.next_earnings,
            fd_package=enrich.fd_package,
            macro_regime=enrich.macro_regime,
            macro_yield_spread=enrich.macro_yield_spread,
            macro_fed_funds_rate=enrich.macro_fed_funds_rate,
            macro_vix_level=enrich.macro_vix_level,
            prob_profit_neural=enrich.prob_profit_neural,
        )

        assert context.macro_regime == MacroRegime.CONTRACTIONARY
        assert context.yield_spread == pytest.approx(-0.45, abs=0.01)
        assert context.fed_funds_rate == pytest.approx(4.75, abs=0.01)
        assert context.vix_level == pytest.approx(32.1, abs=0.1)
        # Non-macro fields remain None
        assert context.prob_profit_neural is None
        assert context.next_earnings is None

    def test_prob_profit_neural_unpacked(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contracts: list[OptionContract],
    ) -> None:
        """prob_profit_neural reaches MarketContext."""
        enrich = ScanEnrichment(prob_profit_neural=0.88)
        context = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            contracts,
            next_earnings=enrich.next_earnings,
            fd_package=enrich.fd_package,
            macro_regime=enrich.macro_regime,
            macro_yield_spread=enrich.macro_yield_spread,
            macro_fed_funds_rate=enrich.macro_fed_funds_rate,
            macro_vix_level=enrich.macro_vix_level,
            prob_profit_neural=enrich.prob_profit_neural,
        )

        assert context.prob_profit_neural == pytest.approx(0.88, abs=0.01)
        # Other enrichment fields remain None
        assert context.macro_regime is None
        assert context.next_earnings is None

    def test_next_earnings_unpacked(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contracts: list[OptionContract],
    ) -> None:
        """next_earnings date flows through."""
        earnings_date = date(2026, 5, 1)
        enrich = ScanEnrichment(next_earnings=earnings_date)
        context = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            contracts,
            next_earnings=enrich.next_earnings,
            fd_package=enrich.fd_package,
            macro_regime=enrich.macro_regime,
            macro_yield_spread=enrich.macro_yield_spread,
            macro_fed_funds_rate=enrich.macro_fed_funds_rate,
            macro_vix_level=enrich.macro_vix_level,
            prob_profit_neural=enrich.prob_profit_neural,
        )

        assert context.next_earnings == earnings_date

    def test_partial_enrichment(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contracts: list[OptionContract],
    ) -> None:
        """Partial enrichment (only some fields set) passes through correctly."""
        enrich = ScanEnrichment(
            macro_regime=MacroRegime.TRANSITIONAL,
            prob_profit_neural=0.55,
        )
        context = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            contracts,
            next_earnings=enrich.next_earnings,
            fd_package=enrich.fd_package,
            macro_regime=enrich.macro_regime,
            macro_yield_spread=enrich.macro_yield_spread,
            macro_fed_funds_rate=enrich.macro_fed_funds_rate,
            macro_vix_level=enrich.macro_vix_level,
            prob_profit_neural=enrich.prob_profit_neural,
        )

        assert context.macro_regime == MacroRegime.TRANSITIONAL
        assert context.prob_profit_neural == pytest.approx(0.55, abs=0.01)
        # Unset fields remain None
        assert context.yield_spread is None
        assert context.fed_funds_rate is None
        assert context.vix_level is None
        assert context.next_earnings is None
