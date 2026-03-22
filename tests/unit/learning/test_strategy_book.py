"""Tests for strategy mining algorithms in learning/strategy_book.py."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from options_arena.learning.strategy_book import (
    MIN_CELL_SAMPLES,
    MIN_TOTAL_OUTCOMES,
    OutcomeWithContext,
    PatternCell,
    filter_significant,
    generate_rules,
    mine_patterns,
    render_learned_patterns,
    run_strategy_mining,
)
from options_arena.models import (
    ConditionOperator,
    RuleStatus,
    StrategyCondition,
    StrategyRule,
)

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(
    sector: str = "Information Technology",
    iv_rank: float = 60.0,
    dte_at_entry: int = 45,
    direction: str = "bullish",
    return_pct: float = 0.15,
    is_winner: bool = True,
) -> OutcomeWithContext:
    return OutcomeWithContext(
        sector=sector,
        iv_rank=iv_rank,
        dte_at_entry=dte_at_entry,
        direction=direction,
        return_pct=return_pct,
        is_winner=is_winner,
    )


def _make_cell(
    sector: str = "Information Technology",
    iv_bucket: str = "mid_high",
    dte_bucket: str = "medium",
    direction: str = "bullish",
    win_rate: float = 0.75,
    avg_return: float = 0.10,
    sample_size: int = 30,
) -> PatternCell:
    return PatternCell(
        sector=sector,
        iv_bucket=iv_bucket,
        dte_bucket=dte_bucket,
        direction=direction,
        win_rate=win_rate,
        avg_return=avg_return,
        sample_size=sample_size,
    )


def _make_rule(
    rule_id: str = "rule_test",
    status: RuleStatus = RuleStatus.APPROVED,
    win_rate: float = 0.70,
    avg_return: float = 0.12,
    sample_size: int = 40,
    confidence: float = 0.5,
) -> StrategyRule:
    return StrategyRule(
        rule_id=rule_id,
        pattern="Tech | IV mid_high | DTE medium | bullish -> 70% win rate",
        conditions=[
            StrategyCondition(
                field="sector",
                operator=ConditionOperator.EQ,
                value="Information Technology",
            )
        ],
        win_rate=win_rate,
        avg_return=avg_return,
        sample_size=sample_size,
        status=status,
        created_at=_NOW,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# mine_patterns
# ---------------------------------------------------------------------------


class TestMinePatterns:
    def test_groups_by_dimensions(self) -> None:
        """Verify outcomes are grouped by sector x IV x DTE x direction."""
        outcomes = [
            _make_outcome(sector="Tech", iv_rank=60, dte_at_entry=45, direction="bullish")
            for _ in range(25)
        ]
        cells = mine_patterns(outcomes)
        assert len(cells) == 1
        assert cells[0].sector == "Tech"
        assert cells[0].iv_bucket == "mid_high"
        assert cells[0].dte_bucket == "medium"
        assert cells[0].direction == "bullish"

    def test_filters_below_min_samples(self) -> None:
        """Verify cells with < MIN_CELL_SAMPLES are excluded."""
        outcomes = [_make_outcome() for _ in range(MIN_CELL_SAMPLES - 1)]
        cells = mine_patterns(outcomes)
        assert len(cells) == 0

    def test_boundary_min_samples(self) -> None:
        """Verify exactly MIN_CELL_SAMPLES outcomes produce a cell."""
        outcomes = [_make_outcome() for _ in range(MIN_CELL_SAMPLES)]
        cells = mine_patterns(outcomes)
        assert len(cells) == 1
        assert cells[0].sample_size == MIN_CELL_SAMPLES

    def test_computes_win_rate(self) -> None:
        """Verify win_rate = wins / total per cell."""
        winners = [_make_outcome(is_winner=True) for _ in range(15)]
        losers = [_make_outcome(is_winner=False) for _ in range(5)]
        cells = mine_patterns(winners + losers)
        assert len(cells) == 1
        assert cells[0].win_rate == pytest.approx(0.75, abs=0.01)

    def test_computes_avg_return(self) -> None:
        """Verify avg_return is mean of P&L returns per cell."""
        outcomes = [_make_outcome(return_pct=0.10) for _ in range(10)] + [
            _make_outcome(return_pct=0.20) for _ in range(10)
        ]
        cells = mine_patterns(outcomes)
        assert len(cells) == 1
        assert cells[0].avg_return == pytest.approx(0.15, abs=0.01)

    def test_empty_input(self) -> None:
        """Verify empty outcomes list returns empty cells list."""
        assert mine_patterns([]) == []

    def test_multiple_groups(self) -> None:
        """Verify outcomes split across dimensions produce multiple cells."""
        tech = [_make_outcome(sector="Tech") for _ in range(25)]
        energy = [_make_outcome(sector="Energy") for _ in range(25)]
        cells = mine_patterns(tech + energy)
        assert len(cells) == 2
        sectors = {c.sector for c in cells}
        assert sectors == {"Tech", "Energy"}


# ---------------------------------------------------------------------------
# test_significance
# ---------------------------------------------------------------------------


class TestFilterSignificant:
    def test_significant_pattern_passes(self) -> None:
        """Verify a cell with win rate far above baseline passes."""
        cell = _make_cell(win_rate=0.90, sample_size=50)
        result = filter_significant([cell], baseline_win_rate=0.50)
        assert len(result) == 1

    def test_insignificant_pattern_filtered(self) -> None:
        """Verify a cell close to baseline win rate is filtered."""
        cell = _make_cell(win_rate=0.52, sample_size=30)
        result = filter_significant([cell], baseline_win_rate=0.50)
        assert len(result) == 0

    def test_all_insignificant_returns_empty(self) -> None:
        """Verify returns empty list when no significant patterns."""
        cells = [
            _make_cell(win_rate=0.51, sample_size=20),
            _make_cell(win_rate=0.49, sample_size=20, sector="Energy"),
        ]
        result = filter_significant(cells, baseline_win_rate=0.50)
        assert len(result) == 0

    def test_empty_cells(self) -> None:
        """Verify empty input returns empty output."""
        assert filter_significant([], baseline_win_rate=0.5) == []

    def test_baseline_zero_returns_empty(self) -> None:
        """Verify degenerate baseline returns empty."""
        cell = _make_cell(win_rate=0.8, sample_size=50)
        assert filter_significant([cell], baseline_win_rate=0.0) == []

    def test_baseline_one_returns_empty(self) -> None:
        """Verify degenerate baseline returns empty."""
        cell = _make_cell(win_rate=0.8, sample_size=50)
        assert filter_significant([cell], baseline_win_rate=1.0) == []

    def test_significant_below_baseline(self) -> None:
        """Verify a significantly low win rate also passes chi-squared."""
        cell = _make_cell(win_rate=0.10, sample_size=50)
        result = filter_significant([cell], baseline_win_rate=0.50)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# generate_rules
# ---------------------------------------------------------------------------


class TestGenerateRules:
    def test_creates_rule_per_cell(self) -> None:
        """Verify one StrategyRule per significant PatternCell."""
        cells = [_make_cell(), _make_cell(sector="Energy")]
        rules = generate_rules(cells)
        assert len(rules) == 2

    def test_rule_status_is_candidate(self) -> None:
        """Verify all generated rules have status=CANDIDATE."""
        rules = generate_rules([_make_cell()])
        assert all(r.status == RuleStatus.CANDIDATE for r in rules)

    def test_rule_id_unique(self) -> None:
        """Verify each rule has a unique rule_id."""
        cells = [_make_cell(), _make_cell(sector="Energy")]
        rules = generate_rules(cells)
        ids = [r.rule_id for r in rules]
        assert len(ids) == len(set(ids))

    def test_rule_conditions_include_sector(self) -> None:
        """Verify conditions include sector condition."""
        rules = generate_rules([_make_cell(sector="Financials")])
        assert len(rules) == 1
        sector_conds = [c for c in rules[0].conditions if c.field == "sector"]
        assert len(sector_conds) == 1
        assert sector_conds[0].value == "Financials"

    def test_rule_conditions_include_direction(self) -> None:
        """Verify conditions include direction condition."""
        rules = generate_rules([_make_cell(direction="bearish")])
        dir_conds = [c for c in rules[0].conditions if c.field == "direction"]
        assert len(dir_conds) == 1
        assert dir_conds[0].value == "bearish"

    def test_empty_input(self) -> None:
        """Verify empty cells returns empty rules."""
        assert generate_rules([]) == []

    def test_pattern_is_human_readable(self) -> None:
        """Verify pattern contains key dimensional info."""
        rules = generate_rules([_make_cell(sector="Health Care")])
        assert "Health Care" in rules[0].pattern
        assert "mid_high" in rules[0].pattern
        assert "medium" in rules[0].pattern


# ---------------------------------------------------------------------------
# render_learned_patterns
# ---------------------------------------------------------------------------


class TestRenderLearnedPatterns:
    def test_renders_approved_only(self) -> None:
        """Verify only approved rules appear in output."""
        rules = [
            _make_rule(rule_id="r1", status=RuleStatus.APPROVED, confidence=0.6),
            _make_rule(rule_id="r2", status=RuleStatus.CANDIDATE, confidence=0.6),
            _make_rule(rule_id="r3", status=RuleStatus.REJECTED, confidence=0.6),
        ]
        text = render_learned_patterns(rules)
        assert "<<<LEARNED_PATTERNS>>>" in text
        assert "<<<END_LEARNED_PATTERNS>>>" in text
        # Only one rule should be rendered (approved with confidence >= 0.3)
        assert text.count("Pattern:") == 1

    def test_empty_when_no_approved(self) -> None:
        """Verify returns empty string when no approved rules."""
        rules = [_make_rule(status=RuleStatus.CANDIDATE)]
        assert render_learned_patterns(rules) == ""

    def test_empty_list(self) -> None:
        """Verify returns empty string for empty input."""
        assert render_learned_patterns([]) == ""

    def test_format_includes_delimiters(self) -> None:
        """Verify output includes <<<LEARNED_PATTERNS>>> delimiters."""
        text = render_learned_patterns([_make_rule(confidence=0.5)])
        assert text.startswith("<<<LEARNED_PATTERNS>>>")
        assert text.endswith("<<<END_LEARNED_PATTERNS>>>")

    def test_format_includes_stats(self) -> None:
        """Verify output includes win rate, sample size, avg return."""
        text = render_learned_patterns(
            [_make_rule(win_rate=0.7, avg_return=0.12, sample_size=40, confidence=0.5)]
        )
        assert "70.0%" in text
        assert "n=40" in text
        assert "+12.0%" in text


class TestRenderLearnedPatternsConfidence:
    """Tests for confidence-weighted pattern rendering."""

    def test_excludes_below_threshold(self) -> None:
        """Verify rules with confidence < 0.3 are excluded."""
        rules = [
            _make_rule(rule_id="low", confidence=0.29),
            _make_rule(rule_id="high", confidence=0.5),
        ]
        text = render_learned_patterns(rules)
        # Only the high-confidence rule should appear
        assert text.count("Pattern:") == 1
        assert "confidence: 50%" in text

    def test_sorts_by_confidence_descending(self) -> None:
        """Verify rules are sorted by confidence descending."""
        rules = [
            _make_rule(rule_id="r_low", confidence=0.4, win_rate=0.60),
            _make_rule(rule_id="r_high", confidence=0.9, win_rate=0.80),
            _make_rule(rule_id="r_mid", confidence=0.6, win_rate=0.70),
        ]
        text = render_learned_patterns(rules)
        # Find positions of confidence percentages
        pos_90 = text.index("confidence: 90%")
        pos_60 = text.index("confidence: 60%")
        pos_40 = text.index("confidence: 40%")
        assert pos_90 < pos_60 < pos_40

    def test_strong_pattern_label(self) -> None:
        """Verify rules with confidence >= 0.8 get 'Strong pattern:' prefix."""
        rules = [_make_rule(confidence=0.85)]
        text = render_learned_patterns(rules)
        assert "Strong pattern:" in text
        assert text.count("Pattern:") == 0  # no bare "Pattern:" prefix

    def test_regular_pattern_label(self) -> None:
        """Verify rules with confidence < 0.8 get 'Pattern:' prefix."""
        rules = [_make_rule(confidence=0.5)]
        text = render_learned_patterns(rules)
        assert "Pattern:" in text
        assert "Strong pattern:" not in text

    def test_confidence_percentage_in_output(self) -> None:
        """Verify confidence is rendered as a percentage in the output."""
        rules = [_make_rule(confidence=0.73)]
        text = render_learned_patterns(rules)
        assert "(confidence: 73%)" in text

    def test_all_below_threshold_returns_empty(self) -> None:
        """Verify empty string when all approved rules have confidence < 0.3."""
        rules = [
            _make_rule(rule_id="r1", confidence=0.1),
            _make_rule(rule_id="r2", confidence=0.29),
        ]
        assert render_learned_patterns(rules) == ""

    def test_empty_rules_returns_empty(self) -> None:
        """Verify empty string for empty rules list."""
        assert render_learned_patterns([]) == ""

    def test_truncation_still_works(self) -> None:
        """Verify truncation at MAX_PATTERN_TEXT_CHARS still works with confidence."""
        from options_arena.learning.strategy_book import MAX_PATTERN_TEXT_CHARS

        # Create many rules that will exceed the char limit
        rules = [_make_rule(rule_id=f"rule_{i}", confidence=0.5 + i * 0.01) for i in range(50)]
        text = render_learned_patterns(rules)
        assert len(text) <= MAX_PATTERN_TEXT_CHARS + len("\n<<<END_LEARNED_PATTERNS>>>")
        assert text.endswith("<<<END_LEARNED_PATTERNS>>>")
        assert text.startswith("<<<LEARNED_PATTERNS>>>")

    def test_boundary_confidence_exactly_030(self) -> None:
        """Verify rule with confidence exactly 0.3 is included."""
        rules = [_make_rule(confidence=0.3)]
        text = render_learned_patterns(rules)
        assert "Pattern:" in text
        assert "confidence: 30%" in text

    def test_boundary_confidence_exactly_080(self) -> None:
        """Verify rule with confidence exactly 0.8 gets 'Strong pattern:' prefix."""
        rules = [_make_rule(confidence=0.8)]
        text = render_learned_patterns(rules)
        assert "Strong pattern:" in text
        assert "confidence: 80%" in text

    def test_mixed_statuses_only_approved_rendered(self) -> None:
        """Verify only APPROVED rules are rendered regardless of confidence."""
        rules = [
            _make_rule(rule_id="a", status=RuleStatus.APPROVED, confidence=0.9),
            _make_rule(rule_id="b", status=RuleStatus.CANDIDATE, confidence=0.9),
            _make_rule(rule_id="c", status=RuleStatus.REJECTED, confidence=0.9),
        ]
        text = render_learned_patterns(rules)
        # Count pattern lines (Strong pattern or Pattern) — should be exactly 1
        strong_count = text.count("Strong pattern:")
        pattern_count = text.count("Pattern:")
        # "Strong pattern:" does not contain a bare "Pattern:" so we count both
        assert strong_count == 1
        assert pattern_count == 0  # the one match is "Strong pattern:", not "Pattern:"


# ---------------------------------------------------------------------------
# run_strategy_mining (orchestration)
# ---------------------------------------------------------------------------


class TestRunStrategyMining:
    @pytest.mark.asyncio
    async def test_returns_empty_below_minimum(self) -> None:
        """Verify returns empty list when < MIN_TOTAL_OUTCOMES outcomes."""
        repo = MagicMock()
        repo._db = MagicMock()
        repo._db.conn = MagicMock()

        # Simulate < 100 outcomes
        cursor_mock = AsyncMock()
        cursor_mock.fetchall = AsyncMock(return_value=[])
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=cursor_mock)
        ctx.__aexit__ = AsyncMock(return_value=False)
        repo._db.conn.execute = MagicMock(return_value=ctx)

        result = await run_strategy_mining(repo)
        assert result == []

    @pytest.mark.asyncio
    async def test_never_raises(self) -> None:
        """Verify orchestration catches exceptions and returns empty list."""
        repo = MagicMock()
        repo._db = MagicMock()
        repo._db.conn = MagicMock()
        repo._db.conn.execute = MagicMock(side_effect=RuntimeError("DB error"))

        result = await run_strategy_mining(repo)
        assert result == []

    @pytest.mark.asyncio
    async def test_saves_rules_to_repository(self) -> None:
        """Verify generated rules are persisted via repository."""
        repo = MagicMock()
        repo._db = MagicMock()
        repo._db.conn = MagicMock()
        repo.save_strategy_rule = AsyncMock()

        # Create enough mock rows to produce outcomes
        mock_rows = []
        for i in range(MIN_TOTAL_OUTCOMES + 20):
            row = MagicMock()
            row.__getitem__ = MagicMock(
                side_effect=lambda key, i=i: {
                    "ticker": "AAPL",
                    "direction": "bullish",
                    "market_iv": 0.6,
                    "dte_at_entry": 45,
                    "contract_return_pct": 0.1 if i % 2 == 0 else -0.05,
                    "is_winner": i % 2 == 0,
                    "sector": "Information Technology",
                }[key]
            )
            mock_rows.append(row)

        cursor_mock = AsyncMock()
        cursor_mock.fetchall = AsyncMock(return_value=mock_rows)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=cursor_mock)
        ctx.__aexit__ = AsyncMock(return_value=False)
        repo._db.conn.execute = MagicMock(return_value=ctx)

        result = await run_strategy_mining(repo)
        # With enough homogeneous outcomes, mining should find patterns
        # (exact count depends on significance, but at least verifies the pipeline runs)
        # The key assertion: if rules generated, they should be saved
        assert repo.save_strategy_rule.call_count == len(result)
