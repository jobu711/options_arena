"""Tests for contract guidance computation and rendering."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from options_arena.learning.contract_guidance import (
    OutcomeWithDelta,
    compute_contract_guidance,
    fetch_contract_guidance,
    render_contract_guidance,
)
from options_arena.models.attribution import ContractGuidance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(
    delta: float = 0.35,
    dte: int = 30,
    is_winner: bool = True,
) -> OutcomeWithDelta:
    return OutcomeWithDelta(
        delta_at_entry=delta,
        dte_at_entry=dte,
        is_winner=is_winner,
    )


def _make_outcomes(
    count: int,
    delta: float = 0.35,
    dte: int = 30,
    win_rate: float = 0.6,
) -> list[OutcomeWithDelta]:
    """Build a list of outcomes with a target win rate."""
    winners = int(count * win_rate)
    losers = count - winners
    return [_make_outcome(delta=delta, dte=dte, is_winner=True)] * winners + [
        _make_outcome(delta=delta, dte=dte, is_winner=False)
    ] * losers


def _make_guidance(
    delta_low: float = 0.30,
    delta_high: float = 0.40,
    dte_low: int = 30,
    dte_high: int = 45,
    delta_win_rate: float = 0.70,
    dte_win_rate: float = 0.65,
    sample_count: int = 50,
) -> ContractGuidance:
    return ContractGuidance(
        optimal_delta_low=delta_low,
        optimal_delta_high=delta_high,
        optimal_dte_low=dte_low,
        optimal_dte_high=dte_high,
        delta_win_rate=delta_win_rate,
        dte_win_rate=dte_win_rate,
        sample_count=sample_count,
    )


# ---------------------------------------------------------------------------
# TestComputeContractGuidance
# ---------------------------------------------------------------------------


class TestComputeContractGuidance:
    """Tests for compute_contract_guidance()."""

    def test_sufficient_data_returns_guidance(self) -> None:
        """50 outcomes with delta/DTE in same bucket -> valid ContractGuidance."""
        outcomes = _make_outcomes(50, delta=0.35, dte=30, win_rate=0.7)
        result = compute_contract_guidance(outcomes)

        assert result is not None
        assert isinstance(result, ContractGuidance)
        assert result.sample_count == 50
        assert result.delta_win_rate == pytest.approx(0.7, abs=0.02)
        assert result.dte_win_rate == pytest.approx(0.7, abs=0.02)
        # Delta 0.35 falls in bucket 3 -> range 0.30-0.40
        assert result.optimal_delta_low == pytest.approx(0.30, abs=0.01)
        assert result.optimal_delta_high == pytest.approx(0.40, abs=0.01)
        # DTE 30 falls in bucket 2 -> range 30-45
        assert result.optimal_dte_low == 30
        assert result.optimal_dte_high == 45

    def test_insufficient_data_returns_none(self) -> None:
        """29 outcomes -> None (below MIN_GUIDANCE_SAMPLES)."""
        outcomes = _make_outcomes(29, delta=0.35, dte=30)
        result = compute_contract_guidance(outcomes)

        assert result is None

    def test_empty_outcomes_returns_none(self) -> None:
        """Empty list -> None."""
        result = compute_contract_guidance([])

        assert result is None

    def test_optimal_delta_highest_win_rate(self) -> None:
        """Bucket with 80% win rate chosen over 60% win rate."""
        # 35 outcomes in 0.30-0.40 bucket with 60% win rate
        low_wr = _make_outcomes(35, delta=0.35, dte=30, win_rate=0.6)
        # 35 outcomes in 0.40-0.50 bucket with 80% win rate
        high_wr = _make_outcomes(35, delta=0.45, dte=30, win_rate=0.8)

        outcomes = low_wr + high_wr
        result = compute_contract_guidance(outcomes)

        assert result is not None
        # Should pick the 0.40-0.50 bucket (higher win rate)
        assert result.optimal_delta_low == pytest.approx(0.40, abs=0.01)
        assert result.optimal_delta_high == pytest.approx(0.50, abs=0.01)
        assert result.delta_win_rate == pytest.approx(0.8, abs=0.02)

    def test_optimal_dte_highest_win_rate(self) -> None:
        """DTE bucket with best win rate selected."""
        # 35 outcomes in 0-15 DTE bucket with 50% win rate
        low_dte = _make_outcomes(35, delta=0.35, dte=7, win_rate=0.5)
        # 35 outcomes in 30-45 DTE bucket with 75% win rate
        high_dte = _make_outcomes(35, delta=0.35, dte=35, win_rate=0.75)

        outcomes = low_dte + high_dte
        result = compute_contract_guidance(outcomes)

        assert result is not None
        assert result.optimal_dte_low == 30
        assert result.optimal_dte_high == 45
        assert result.dte_win_rate == pytest.approx(0.75, abs=0.02)

    def test_bucket_below_threshold_excluded(self) -> None:
        """Delta bucket with 25 samples (< 30) excluded even if high win rate."""
        # 25 outcomes in 0.50-0.60 bucket with 90% win rate (excluded)
        small_bucket = _make_outcomes(25, delta=0.55, dte=30, win_rate=0.9)
        # 35 outcomes in 0.30-0.40 bucket with 60% win rate (selected)
        big_bucket = _make_outcomes(35, delta=0.35, dte=30, win_rate=0.6)

        outcomes = small_bucket + big_bucket
        result = compute_contract_guidance(outcomes)

        assert result is not None
        # Should pick 0.30-0.40 (the only bucket with >= 30 samples)
        assert result.optimal_delta_low == pytest.approx(0.30, abs=0.01)
        assert result.optimal_delta_high == pytest.approx(0.40, abs=0.01)
        assert result.delta_win_rate == pytest.approx(0.6, abs=0.02)

    def test_all_buckets_below_threshold_returns_none(self) -> None:
        """When total >= 30 but no single bucket has >= 30 -> None."""
        # 15 outcomes spread across two delta buckets
        bucket_a = _make_outcomes(15, delta=0.25, dte=30, win_rate=0.8)
        bucket_b = _make_outcomes(15, delta=0.45, dte=30, win_rate=0.6)

        outcomes = bucket_a + bucket_b
        result = compute_contract_guidance(outcomes)

        assert result is None

    def test_boundary_delta_zero(self) -> None:
        """Delta = 0.0 classified into first bucket (0.00-0.10)."""
        outcomes = _make_outcomes(35, delta=0.0, dte=30, win_rate=0.6)
        result = compute_contract_guidance(outcomes)

        assert result is not None
        assert result.optimal_delta_low == pytest.approx(0.0, abs=0.01)
        assert result.optimal_delta_high == pytest.approx(0.10, abs=0.01)

    def test_boundary_delta_one(self) -> None:
        """Delta = 1.0 classified into last bucket (1.00-1.10)."""
        outcomes = _make_outcomes(35, delta=1.0, dte=30, win_rate=0.6)
        result = compute_contract_guidance(outcomes)

        assert result is not None
        assert result.optimal_delta_low == pytest.approx(1.0, abs=0.01)

    def test_negative_delta_uses_absolute(self) -> None:
        """Negative delta (put) uses absolute value for bucketing."""
        outcomes = _make_outcomes(35, delta=-0.35, dte=30, win_rate=0.7)
        result = compute_contract_guidance(outcomes)

        assert result is not None
        # abs(-0.35) = 0.35 -> bucket 3 -> 0.30-0.40
        assert result.optimal_delta_low == pytest.approx(0.30, abs=0.01)
        assert result.optimal_delta_high == pytest.approx(0.40, abs=0.01)

    def test_large_dte_classified_correctly(self) -> None:
        """Very large DTE (365+) classified into correct bucket."""
        outcomes = _make_outcomes(35, delta=0.35, dte=365, win_rate=0.6)
        result = compute_contract_guidance(outcomes)

        assert result is not None
        # 365 // 15 = 24 -> bucket 24 -> range 360-375
        assert result.optimal_dte_low == 360
        assert result.optimal_dte_high == 375

    def test_tie_in_win_rate_deterministic(self) -> None:
        """Tie in win rate between buckets -> lower bucket selected (deterministic)."""
        bucket_a = _make_outcomes(30, delta=0.25, dte=30, win_rate=0.7)
        bucket_b = _make_outcomes(30, delta=0.45, dte=30, win_rate=0.7)

        outcomes = bucket_a + bucket_b
        result = compute_contract_guidance(outcomes)

        assert result is not None
        # Tie-break: prefer lower delta bucket
        assert result.optimal_delta_low == pytest.approx(0.20, abs=0.01)
        assert result.optimal_delta_high == pytest.approx(0.30, abs=0.01)


# ---------------------------------------------------------------------------
# TestOutcomeWithDelta validation
# ---------------------------------------------------------------------------


class TestOutcomeWithDelta:
    """Validation tests for the OutcomeWithDelta model."""

    def test_valid_construction(self) -> None:
        o = _make_outcome(delta=0.35, dte=30, is_winner=True)
        assert o.delta_at_entry == pytest.approx(0.35)
        assert o.dte_at_entry == 30
        assert o.is_winner is True

    def test_nan_delta_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _make_outcome(delta=float("nan"))

    def test_inf_delta_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _make_outcome(delta=float("inf"))

    def test_negative_dte_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            _make_outcome(dte=-1)

    def test_frozen(self) -> None:
        o = _make_outcome()
        with pytest.raises(Exception):  # noqa: B017
            o.delta_at_entry = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestRenderContractGuidance
# ---------------------------------------------------------------------------


class TestRenderContractGuidance:
    """Tests for render_contract_guidance()."""

    def test_renders_delimited_block(self) -> None:
        """Output starts with <<<CONTRACT_GUIDANCE>>> and ends with <<<END_CONTRACT_GUIDANCE>>>."""
        guidance = _make_guidance()
        text = render_contract_guidance(guidance)

        assert text.startswith("<<<CONTRACT_GUIDANCE>>>")
        assert text.endswith("<<<END_CONTRACT_GUIDANCE>>>")

    def test_includes_delta_range(self) -> None:
        """Output includes optimal delta range with win rate."""
        guidance = _make_guidance(delta_low=0.30, delta_high=0.40, delta_win_rate=0.70)
        text = render_contract_guidance(guidance)

        assert "0.30-0.40" in text
        assert "70%" in text

    def test_includes_dte_range(self) -> None:
        """Output includes optimal DTE range."""
        guidance = _make_guidance(dte_low=30, dte_high=45, dte_win_rate=0.65)
        text = render_contract_guidance(guidance)

        assert "30-45 days" in text
        assert "65%" in text

    def test_includes_sample_count(self) -> None:
        """Output includes total sample count."""
        guidance = _make_guidance(sample_count=123)
        text = render_contract_guidance(guidance)

        assert "n=123" in text

    def test_multiline_structure(self) -> None:
        """Output has correct multiline structure."""
        guidance = _make_guidance()
        lines = render_contract_guidance(guidance).split("\n")

        assert len(lines) == 4
        assert lines[0] == "<<<CONTRACT_GUIDANCE>>>"
        assert lines[3] == "<<<END_CONTRACT_GUIDANCE>>>"


# ---------------------------------------------------------------------------
# TestFetchContractGuidance
# ---------------------------------------------------------------------------


class TestFetchContractGuidance:
    """Tests for fetch_contract_guidance()."""

    @pytest.mark.asyncio
    async def test_never_raises(self) -> None:
        """Exception -> logged, returns None."""
        repo = MagicMock()
        type(repo)._db = PropertyMock(side_effect=RuntimeError("db exploded"))

        result = await fetch_contract_guidance(repo)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_rows(self) -> None:
        """No rows -> returns None."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.execute = MagicMock(return_value=mock_cursor)

        mock_db = MagicMock()
        type(mock_db).conn = PropertyMock(return_value=mock_conn)

        repo = MagicMock()
        type(repo)._db = PropertyMock(return_value=mock_db)

        result = await fetch_contract_guidance(repo)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_guidance_on_sufficient_data(self) -> None:
        """Sufficient row data -> returns ContractGuidance."""
        # Build mock rows: 35 winners + 15 losers, all same bucket
        mock_rows: list[dict[str, float | int | bool]] = []
        for _ in range(35):
            mock_rows.append({"abs_delta": 0.35, "dte": 30, "is_winner": 1})
        for _ in range(15):
            mock_rows.append({"abs_delta": 0.35, "dte": 30, "is_winner": 0})

        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=mock_rows)
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.execute = MagicMock(return_value=mock_cursor)

        mock_db = MagicMock()
        type(mock_db).conn = PropertyMock(return_value=mock_conn)

        repo = MagicMock()
        type(repo)._db = PropertyMock(return_value=mock_db)

        result = await fetch_contract_guidance(repo)

        assert result is not None
        assert isinstance(result, ContractGuidance)
        assert result.sample_count == 50
