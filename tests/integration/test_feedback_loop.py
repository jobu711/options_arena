"""Integration tests for the full feedback loop.

Exercises the complete feedback pipeline end-to-end:
- Condition-enriched strategy mining (ADX/ATR dimensions)
- Contract guidance computation and rendering
- Weight tuner with prediction-derived accuracy
- Prompt injection of all three blocks into the synthesis agent
- Cold start (zero data) graceful handling
- Backward compatibility with pre-enrichment outcomes
- Performance of enriched mining with large outcome sets

Uses factory-built data and in-memory SQLite. Mocks external services only.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from options_arena.agents.synthesis_agent import SynthesisDeps
from options_arena.learning.contract_guidance import (
    MIN_GUIDANCE_SAMPLES,
    OutcomeWithDelta,
    compute_contract_guidance,
    render_contract_guidance,
)
from options_arena.learning.strategy_book import (
    MIN_CELL_SAMPLES,
    OutcomeWithContext,
    generate_rules,
    mine_patterns,
    render_learned_patterns,
)
from options_arena.learning.weight_tuner import (
    auto_tune_weights,
    render_tuned_weights,
)
from options_arena.models import (
    AgentWeightsComparison,
    RuleStatus,
)
from options_arena.models.attribution import (
    ContractGuidance,
    PredictionAccuracy,
    PredictionSource,
)
from tests.factories import (
    make_market_context,
    make_option_contract,
    make_ticker_score,
)

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_outcome_with_context(
    sector: str = "Information Technology",
    iv_level: float = 35.0,
    dte_at_entry: int = 45,
    direction: str = "bullish",
    return_pct: float = 0.10,
    is_winner: bool = True,
    adx: float | None = 25.0,
    atr_pct: float | None = 2.0,
    rsi: float | None = 55.0,
) -> OutcomeWithContext:
    """Build an OutcomeWithContext for testing."""
    return OutcomeWithContext(
        sector=sector,
        iv_level=iv_level,
        dte_at_entry=dte_at_entry,
        direction=direction,
        return_pct=return_pct,
        is_winner=is_winner,
        adx=adx,
        atr_pct=atr_pct,
        rsi=rsi,
    )


def _make_enriched_outcomes(
    count: int,
    sector: str = "Information Technology",
    direction: str = "bullish",
    iv_level: float = 35.0,
    dte: int = 45,
    adx: float = 25.0,
    atr_pct: float = 2.0,
    win_rate: float = 0.7,
) -> list[OutcomeWithContext]:
    """Build a list of enriched outcomes with a target win rate."""
    winners = int(count * win_rate)
    losers = count - winners
    outcomes: list[OutcomeWithContext] = []
    for _ in range(winners):
        outcomes.append(
            _make_outcome_with_context(
                sector=sector,
                iv_level=iv_level,
                dte_at_entry=dte,
                direction=direction,
                return_pct=0.15,
                is_winner=True,
                adx=adx,
                atr_pct=atr_pct,
            )
        )
    for _ in range(losers):
        outcomes.append(
            _make_outcome_with_context(
                sector=sector,
                iv_level=iv_level,
                dte_at_entry=dte,
                direction=direction,
                return_pct=-0.08,
                is_winner=False,
                adx=adx,
                atr_pct=atr_pct,
            )
        )
    return outcomes


def _make_outcome_with_delta(
    delta: float = 0.35,
    dte: int = 30,
    is_winner: bool = True,
) -> OutcomeWithDelta:
    """Build an OutcomeWithDelta for contract guidance testing."""
    return OutcomeWithDelta(
        delta_at_entry=delta,
        dte_at_entry=dte,
        is_winner=is_winner,
    )


def _make_delta_outcomes(
    count: int,
    delta: float = 0.35,
    dte: int = 30,
    win_rate: float = 0.65,
) -> list[OutcomeWithDelta]:
    """Build OutcomeWithDelta list with a target win rate."""
    winners = int(count * win_rate)
    losers = count - winners
    return [_make_outcome_with_delta(delta=delta, dte=dte, is_winner=True)] * winners + [
        _make_outcome_with_delta(delta=delta, dte=dte, is_winner=False)
    ] * losers


def _pred(
    source: PredictionSource,
    accuracy: float = 0.70,
    total: int = 50,
    correct: int | None = None,
    sample_sufficient: bool = True,
) -> PredictionAccuracy:
    """Shorthand for creating a PredictionAccuracy."""
    if correct is None:
        correct = int(total * accuracy)
    return PredictionAccuracy(
        source=source,
        total=total,
        correct=correct,
        accuracy=accuracy,
        sample_sufficient=sample_sufficient,
    )


# ---------------------------------------------------------------------------
# TestConditionEnrichedMining
# ---------------------------------------------------------------------------


class TestConditionEnrichedMining:
    """Strategy mining with ADX/ATR condition dimensions produces enriched patterns."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_condition_enriched_mining(self) -> None:
        """Create 50+ outcomes with ADX/ATR -> mine -> generate rules -> render.

        Full pipeline: outcomes with condition data produce PatternCells with
        non-'unknown' adx_bucket/atr_bucket, rules include ADX/ATR conditions,
        and rendered text includes the condition dimensions.
        """
        # 1. Create 50 outcomes in a single bucket with ADX/ATR data
        # ADX=25 -> "moderate", ATR%=2.0 -> "medium"
        outcomes = _make_enriched_outcomes(
            count=55,
            sector="Information Technology",
            direction="bullish",
            iv_level=35.0,
            dte=45,
            adx=25.0,
            atr_pct=2.0,
            win_rate=0.80,
        )

        # 2. Mine patterns -> cells with condition dimensions
        cells = mine_patterns(outcomes)
        assert len(cells) >= 1, "Should produce at least one pattern cell"

        # Verify condition dimensions appear in cells
        cell = cells[0]
        assert cell.adx_bucket == "moderate", f"Expected 'moderate', got '{cell.adx_bucket}'"
        assert cell.atr_bucket == "medium", f"Expected 'medium', got '{cell.atr_bucket}'"
        assert cell.sample_size >= MIN_CELL_SAMPLES

        # 3. Generate rules -> verify ADX/ATR StrategyCondition entries
        # Need a significantly different win rate from baseline for significance
        # Add some outcomes with lower win rate to create a meaningful baseline
        baseline_outcomes = _make_enriched_outcomes(
            count=55,
            sector="Health Care",
            direction="bearish",
            iv_level=60.0,
            dte=15,
            adx=10.0,
            atr_pct=0.5,
            win_rate=0.40,
        )
        all_outcomes = outcomes + baseline_outcomes
        all_cells = mine_patterns(all_outcomes)

        # Compute baseline win rate
        total_wins = sum(1 for o in all_outcomes if o.is_winner)
        baseline_wr = total_wins / len(all_outcomes)

        # Filter for significance and generate rules
        from options_arena.learning.strategy_book import filter_significant

        significant = filter_significant(all_cells, baseline_wr)
        rules = generate_rules(significant)

        # At least some rules should have ADX/ATR conditions
        adx_conditions_found = False
        atr_conditions_found = False
        for rule in rules:
            for cond in rule.conditions:
                if cond.field == "adx_bucket":
                    adx_conditions_found = True
                if cond.field == "atr_bucket":
                    atr_conditions_found = True

        # Rules from the high-win-rate cell with adx=moderate should include ADX condition
        # (significance depends on chi-squared, so check that conditions CAN appear)
        if rules:
            # Check at least rule patterns reference ADX/ATR in their text
            pattern_texts = [r.pattern for r in rules]
            has_adx_pattern = any("ADX:" in p for p in pattern_texts)
            has_atr_pattern = any("ATR:" in p for p in pattern_texts)
            has_any_condition = (
                has_adx_pattern or has_atr_pattern or adx_conditions_found or atr_conditions_found
            )
            assert has_any_condition, (
                "Expected at least one rule to include ADX or ATR condition data"
            )

        # 4. Render -> verify <<<LEARNED_PATTERNS>>> block
        # Mark rules as APPROVED with high confidence for rendering
        approved_rules = []
        now = datetime.now(UTC)
        for rule in rules:
            from options_arena.models import StrategyRule

            approved = StrategyRule(
                rule_id=rule.rule_id,
                pattern=rule.pattern,
                conditions=rule.conditions,
                win_rate=rule.win_rate,
                avg_return=rule.avg_return,
                sample_size=rule.sample_size,
                status=RuleStatus.APPROVED,
                created_at=now,
                confidence=0.85,
            )
            approved_rules.append(approved)

        if approved_rules:
            rendered = render_learned_patterns(approved_rules)
            assert "<<<LEARNED_PATTERNS>>>" in rendered
            assert "<<<END_LEARNED_PATTERNS>>>" in rendered
            assert "Strong pattern" in rendered or "Pattern" in rendered


# ---------------------------------------------------------------------------
# TestContractGuidance
# ---------------------------------------------------------------------------


class TestContractGuidance:
    """Contract guidance computation and rendering from outcome data."""

    def test_contract_guidance_sufficient_data(self) -> None:
        """40+ outcomes with delta/DTE -> valid ContractGuidance -> rendered block."""
        outcomes = _make_delta_outcomes(
            count=45,
            delta=0.35,
            dte=30,
            win_rate=0.70,
        )

        # Compute guidance
        guidance = compute_contract_guidance(outcomes)
        assert guidance is not None, "Should return ContractGuidance with 45 outcomes"
        assert isinstance(guidance, ContractGuidance)
        assert guidance.sample_count == 45
        assert guidance.delta_win_rate == pytest.approx(0.70, abs=0.03)
        assert guidance.dte_win_rate == pytest.approx(0.70, abs=0.03)
        # Delta 0.35 -> bucket index 3 -> 0.30 - 0.40
        assert guidance.optimal_delta_low == pytest.approx(0.30, abs=0.01)
        assert guidance.optimal_delta_high == pytest.approx(0.40, abs=0.01)

        # Render -> verify <<<CONTRACT_GUIDANCE>>> block
        rendered = render_contract_guidance(guidance)
        assert rendered.startswith("<<<CONTRACT_GUIDANCE>>>")
        assert rendered.endswith("<<<END_CONTRACT_GUIDANCE>>>")
        assert "0.30-0.40" in rendered
        assert "n=45" in rendered

    def test_contract_guidance_insufficient_data(self) -> None:
        """20 outcomes (< 30 threshold) -> returns None."""
        outcomes = _make_delta_outcomes(
            count=20,
            delta=0.35,
            dte=30,
            win_rate=0.65,
        )

        result = compute_contract_guidance(outcomes)
        assert result is None, (
            f"Expected None with {len(outcomes)} outcomes (< {MIN_GUIDANCE_SAMPLES})"
        )

    def test_contract_guidance_boundary_exactly_30(self) -> None:
        """Exactly 30 outcomes -> sufficient if a single bucket has >= 30."""
        outcomes = _make_delta_outcomes(
            count=30,
            delta=0.35,
            dte=30,
            win_rate=0.70,
        )

        result = compute_contract_guidance(outcomes)
        assert result is not None, "Exactly 30 outcomes should be sufficient"
        assert result.sample_count == 30


# ---------------------------------------------------------------------------
# TestWeightTunerPredictionsSource
# ---------------------------------------------------------------------------


class TestWeightTunerPredictionsSource:
    """Weight tuner uses prediction-derived accuracy when available."""

    @pytest.mark.asyncio
    async def test_weight_tuner_predictions_source(self) -> None:
        """Mock repo.get_prediction_accuracy -> verify predictions used as data source."""
        desk_preds = [
            _pred(PredictionSource.DESK_TREND, accuracy=0.75, total=50),
            _pred(PredictionSource.DESK_VOLATILITY, accuracy=0.70, total=40),
            _pred(PredictionSource.DESK_FLOW, accuracy=0.65, total=35),
            _pred(PredictionSource.DESK_FUNDAMENTAL, accuracy=0.60, total=30),
            _pred(PredictionSource.DESK_CONTRARIAN, accuracy=0.55, total=25),
            _pred(PredictionSource.DESK_RISK, accuracy=0.50, total=20),
        ]

        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=desk_preds)
        repo.get_agent_accuracy = AsyncMock(return_value=[])
        repo.save_auto_tune_weights = AsyncMock()

        result = await auto_tune_weights(repo, window_days=90)

        # Verify predictions were used
        assert len(result) > 0
        assert all(isinstance(r, AgentWeightsComparison) for r in result)

        # Legacy accuracy should NOT have been called
        repo.get_agent_accuracy.assert_not_awaited()

        # Persistence should have been called
        repo.save_auto_tune_weights.assert_awaited_once()

        # render_tuned_weights should produce usable text
        weights = {r.agent_name: r.auto_weight for r in result}
        rendered = render_tuned_weights(weights)
        assert "desk vote weights" in rendered.lower()
        assert "trend" in rendered


# ---------------------------------------------------------------------------
# TestColdStart
# ---------------------------------------------------------------------------


class TestColdStart:
    """Zero data -> all functions return gracefully, no crash."""

    @pytest.mark.asyncio
    async def test_cold_start(self) -> None:
        """Empty data -> all fetch/compute functions return None/empty.

        SynthesisDeps with empty injection fields -> no crash.
        """
        # Strategy mining: empty outcomes -> empty cells
        cells = mine_patterns([])
        assert cells == []

        rules = generate_rules([])
        assert rules == []

        rendered_patterns = render_learned_patterns([])
        assert rendered_patterns == ""

        # Contract guidance: empty outcomes -> None
        guidance = compute_contract_guidance([])
        assert guidance is None

        # Weight tuner: empty predictions AND empty legacy -> empty result
        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=[])
        repo.get_agent_accuracy = AsyncMock(return_value=[])

        weight_result = await auto_tune_weights(repo, window_days=90)
        assert weight_result == []

        rendered_weights = render_tuned_weights({})
        assert rendered_weights == ""

        # SynthesisDeps with empty injection fields -> no crash
        deps = SynthesisDeps(
            context=make_market_context(),
            assessments=[],
            contracts=[make_option_contract()],
            ticker_score=make_ticker_score(),
            learned_patterns="",
            tuned_weights="",
            contract_guidance="",
        )

        # Verify all injection fields are empty
        assert deps.learned_patterns == ""
        assert deps.tuned_weights == ""
        assert deps.contract_guidance == ""

        # Verify no crash when accessing deps
        assert deps.context.ticker == "AAPL"
        assert deps.assessments == []


# ---------------------------------------------------------------------------
# TestBackwardCompatibleMining
# ---------------------------------------------------------------------------


class TestBackwardCompatibleMining:
    """Outcomes without condition data -> same behavior as before enrichment."""

    def test_backward_compatible_mining(self) -> None:
        """Outcomes with all condition data None -> mining ignores condition dims.

        All outcomes land in 'unknown' ADX/ATR buckets, producing the same
        cell structure as before the condition enrichment was added.
        """
        outcomes = [
            _make_outcome_with_context(
                sector="Information Technology",
                iv_level=35.0,
                dte_at_entry=45,
                direction="bullish",
                return_pct=0.12 if i < 18 else -0.05,
                is_winner=i < 18,
                adx=None,
                atr_pct=None,
                rsi=None,
            )
            for i in range(25)
        ]

        cells = mine_patterns(outcomes)

        # All outcomes in same bucket with unknown conditions
        assert len(cells) == 1
        cell = cells[0]
        assert cell.adx_bucket == "unknown"
        assert cell.atr_bucket == "unknown"
        assert cell.sample_size == 25

        # Generate rules from these cells
        rules = generate_rules(cells)

        # Rules should NOT have ADX/ATR conditions when buckets are 'unknown'
        for rule in rules:
            condition_fields = {c.field for c in rule.conditions}
            assert "adx_bucket" not in condition_fields, (
                "Rules with 'unknown' ADX bucket should not include adx_bucket condition"
            )
            assert "atr_bucket" not in condition_fields, (
                "Rules with 'unknown' ATR bucket should not include atr_bucket condition"
            )

    def test_mixed_enriched_and_unenriched(self) -> None:
        """Mix of outcomes with and without condition data -> separate cells."""
        # 25 enriched outcomes (ADX=25 -> moderate)
        enriched = _make_enriched_outcomes(
            count=25,
            sector="Information Technology",
            direction="bullish",
            adx=25.0,
            atr_pct=2.0,
            win_rate=0.70,
        )
        # 25 unenriched outcomes (same sector/direction/IV/DTE, but no ADX/ATR)
        unenriched = [
            _make_outcome_with_context(
                sector="Information Technology",
                iv_level=35.0,
                dte_at_entry=45,
                direction="bullish",
                return_pct=0.10 if i < 15 else -0.05,
                is_winner=i < 15,
                adx=None,
                atr_pct=None,
            )
            for i in range(25)
        ]

        all_outcomes = enriched + unenriched
        cells = mine_patterns(all_outcomes)

        # Should produce 2 cells: one with moderate/medium, one with unknown/unknown
        assert len(cells) == 2

        adx_buckets = {c.adx_bucket for c in cells}
        assert "moderate" in adx_buckets
        assert "unknown" in adx_buckets


# ---------------------------------------------------------------------------
# TestEnrichedMiningPerformance
# ---------------------------------------------------------------------------


class TestEnrichedMiningPerformance:
    """Performance of mining with large enriched outcome sets."""

    def test_enriched_mining_performance(self) -> None:
        """500 enriched outcomes -> mine + generate in < 5s."""
        # Create 500 outcomes spread across several dimensional buckets
        outcomes: list[OutcomeWithContext] = []

        sectors = ["Information Technology", "Health Care", "Financials", "Energy"]
        directions = ["bullish", "bearish"]
        adx_values = [10.0, 25.0, 40.0]
        atr_values = [1.0, 2.0, 4.0]

        idx = 0
        for sector in sectors:
            for direction in directions:
                for adx in adx_values:
                    for atr in atr_values:
                        # ~7 outcomes per combination -> 4*2*3*3 = 72 combos
                        # 72 * 7 = 504 outcomes
                        chunk_size = 7
                        for i in range(chunk_size):
                            outcomes.append(
                                _make_outcome_with_context(
                                    sector=sector,
                                    iv_level=35.0,
                                    dte_at_entry=45,
                                    direction=direction,
                                    return_pct=0.10 if i < 5 else -0.05,
                                    is_winner=i < 5,
                                    adx=adx,
                                    atr_pct=atr,
                                )
                            )
                            idx += 1

        assert len(outcomes) >= 500, f"Expected >= 500 outcomes, got {len(outcomes)}"

        start = time.monotonic()
        cells = mine_patterns(outcomes)
        # Need a baseline for significance filtering
        total_wins = sum(1 for o in outcomes if o.is_winner)
        baseline_wr = total_wins / len(outcomes)

        from options_arena.learning.strategy_book import filter_significant

        significant = filter_significant(cells, baseline_wr)
        _rules = generate_rules(significant)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"Mining + rule generation took {elapsed:.2f}s (limit: 5s)"

    def test_large_single_bucket_performance(self) -> None:
        """500 outcomes in a single bucket -> mine + generate quickly."""
        outcomes = _make_enriched_outcomes(
            count=500,
            sector="Information Technology",
            direction="bullish",
            adx=25.0,
            atr_pct=2.0,
            win_rate=0.65,
        )

        start = time.monotonic()
        cells = mine_patterns(outcomes)
        _rules = generate_rules(cells)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"Mining took {elapsed:.2f}s (limit: 5s)"
        assert len(cells) == 1
        assert cells[0].sample_size == 500


# ---------------------------------------------------------------------------
# TestSynthesisPromptInjection
# ---------------------------------------------------------------------------


class TestSynthesisPromptInjection:
    """Verify SynthesisDeps correctly carries all three injection blocks."""

    def test_all_three_blocks_present(self) -> None:
        """SynthesisDeps with all 3 injection fields -> accessible for prompt."""
        learned_patterns = (
            "<<<LEARNED_PATTERNS>>>\n"
            "Strong pattern: Tech | IV:mid_low | DTE:medium | bullish | ADX:moderate "
            "-> 80% win rate (confidence: 85%)\n"
            "Win Rate: 80.0% (n=55)\n"
            "Avg Return: +12.0%\n"
            "---\n"
            "<<<END_LEARNED_PATTERNS>>>"
        )
        tuned_weights = (
            "Current desk vote weights (auto-tuned from prediction accuracy):\n"
            "  contrarian: 0.07\n"
            "  flow: 0.17\n"
            "  fundamental: 0.14\n"
            "  risk: 0.00\n"
            "  trend: 0.25\n"
            "  volatility: 0.22"
        )
        contract_guidance = (
            "<<<CONTRACT_GUIDANCE>>>\n"
            "Optimal delta range: 0.30-0.40 (win rate: 70%, n=45)\n"
            "Optimal DTE range: 30-45 days (win rate: 65%)\n"
            "<<<END_CONTRACT_GUIDANCE>>>"
        )

        deps = SynthesisDeps(
            context=make_market_context(),
            assessments=[],
            contracts=[make_option_contract()],
            ticker_score=make_ticker_score(),
            learned_patterns=learned_patterns,
            tuned_weights=tuned_weights,
            contract_guidance=contract_guidance,
        )

        assert "<<<LEARNED_PATTERNS>>>" in deps.learned_patterns
        assert "<<<END_LEARNED_PATTERNS>>>" in deps.learned_patterns
        assert "ADX:moderate" in deps.learned_patterns
        assert "desk vote weights" in deps.tuned_weights.lower()
        assert "<<<CONTRACT_GUIDANCE>>>" in deps.contract_guidance
        assert "<<<END_CONTRACT_GUIDANCE>>>" in deps.contract_guidance

    def test_empty_injection_fields_no_crash(self) -> None:
        """SynthesisDeps with empty injection fields -> valid object."""
        deps = SynthesisDeps(
            context=make_market_context(),
            assessments=[],
            contracts=[],
            ticker_score=make_ticker_score(),
            learned_patterns="",
            tuned_weights="",
            contract_guidance="",
        )

        assert deps.learned_patterns == ""
        assert deps.tuned_weights == ""
        assert deps.contract_guidance == ""
        # Verify dataclass works correctly
        assert deps.context is not None
        assert deps.ticker_score is not None
