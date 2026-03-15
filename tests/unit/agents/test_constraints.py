"""Tests for the constraint pre-check system (FR-C4, issue #530).

Validates that ``check_contract_constraints()`` correctly detects hard and soft
violations, and that ``render_constraint_warnings()`` produces spec-compliant
delimited output for agent prompt injection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.agents.constraints import (
    check_contract_constraints,
    render_constraint_warnings,
)
from options_arena.models import (
    ConstraintSeverity,
    ConstraintViolationType,
    ContractConstraint,
    ExerciseStyle,
    OptionContract,
    OptionsFilters,
    OptionType,
)


def _make_contract(
    *,
    ticker: str = "AAPL",
    option_type: OptionType = OptionType.CALL,
    strike: str = "200.00",
    expiration_offset_days: int = 45,
    bid: str = "4.50",
    ask: str = "4.80",
    last: str = "4.65",
    volume: int = 1500,
    open_interest: int = 12000,
    market_iv: float = 0.30,
) -> OptionContract:
    """Create an OptionContract with sensible defaults for testing."""
    return OptionContract(
        ticker=ticker,
        option_type=option_type,
        strike=Decimal(strike),
        expiration=datetime.now(UTC).date() + timedelta(days=expiration_offset_days),
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal(last),
        volume=volume,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=market_iv,
    )


def _default_filters() -> OptionsFilters:
    """Create default OptionsFilters for testing."""
    return OptionsFilters(
        min_dte=30,
        min_oi=100,
        max_spread_pct=0.30,
        min_volume=1,
    )


class TestExpiredContract:
    def test_expired_contract_detected_as_hard_violation(self) -> None:
        """Contract with expiration before today -> EXPIRED hard violation."""
        contract = _make_contract(expiration_offset_days=-5)
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)

        expired = [v for v in violations if v.violation_type == ConstraintViolationType.EXPIRED]
        assert len(expired) >= 1
        assert expired[0].severity == ConstraintSeverity.HARD
        assert "Expired" in expired[0].detail


class TestDTETooShort:
    def test_dte_too_short_detected(self) -> None:
        """Contract with DTE < filters.min_dte -> DTE_TOO_SHORT hard violation."""
        contract = _make_contract(expiration_offset_days=5)  # 5 days, min is 30
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)

        dte_violations = [
            v for v in violations if v.violation_type == ConstraintViolationType.DTE_TOO_SHORT
        ]
        assert len(dte_violations) == 1
        assert dte_violations[0].severity == ConstraintSeverity.HARD
        assert "DTE" in dte_violations[0].detail


class TestOITooLow:
    def test_oi_too_low_detected(self) -> None:
        """Contract with open_interest < filters.min_oi -> OI_TOO_LOW hard violation."""
        contract = _make_contract(open_interest=5)
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)

        oi_violations = [
            v for v in violations if v.violation_type == ConstraintViolationType.OI_TOO_LOW
        ]
        assert len(oi_violations) == 1
        assert oi_violations[0].severity == ConstraintSeverity.HARD
        assert "Open interest" in oi_violations[0].detail


class TestSpreadTooWide:
    def test_spread_too_wide_detected(self) -> None:
        """spread_pct = (ask - bid) / mid exceeds filters.max_spread_pct -> SPREAD_TOO_WIDE."""
        # bid=1.00, ask=2.00 -> spread=1.00, mid=1.50, spread_pct=0.6667 > 0.30
        contract = _make_contract(bid="1.00", ask="2.00")
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)

        spread_violations = [
            v for v in violations if v.violation_type == ConstraintViolationType.SPREAD_TOO_WIDE
        ]
        assert len(spread_violations) == 1
        assert spread_violations[0].severity == ConstraintSeverity.HARD
        assert "spread" in spread_violations[0].detail.lower()


class TestZeroBid:
    def test_zero_bid_detected_as_soft_violation(self) -> None:
        """bid == 0 and ask > 0 -> ZERO_BID soft violation."""
        contract = _make_contract(bid="0.00", ask="0.50")
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)

        zero_bid = [v for v in violations if v.violation_type == ConstraintViolationType.ZERO_BID]
        assert len(zero_bid) == 1
        assert zero_bid[0].severity == ConstraintSeverity.SOFT
        assert "Zero bid" in zero_bid[0].detail


class TestVolumeTooLow:
    def test_volume_too_low_detected_as_soft_violation(self) -> None:
        """volume < filters.min_volume -> VOLUME_TOO_LOW soft violation."""
        contract = _make_contract(volume=0)
        filters = OptionsFilters(
            min_dte=30,
            min_oi=100,
            max_spread_pct=0.30,
            min_volume=100,
        )

        violations = check_contract_constraints([contract], filters)

        vol_violations = [
            v for v in violations if v.violation_type == ConstraintViolationType.VOLUME_TOO_LOW
        ]
        assert len(vol_violations) == 1
        assert vol_violations[0].severity == ConstraintSeverity.SOFT
        assert "Volume" in vol_violations[0].detail


class TestValidContract:
    def test_valid_contract_returns_empty_violations(self) -> None:
        """Contract meeting all thresholds -> empty list."""
        contract = _make_contract()
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)

        assert violations == []


class TestMixedViolations:
    def test_mixed_hard_and_soft_violations(self) -> None:
        """Batch with multiple contracts, some hard some soft -> all detected."""
        # Hard: expired
        expired = _make_contract(expiration_offset_days=-10)
        # Soft: zero bid
        zero_bid = _make_contract(bid="0.00", ask="1.00")
        # Valid
        valid = _make_contract()

        filters = _default_filters()
        violations = check_contract_constraints([expired, zero_bid, valid], filters)

        hard_violations = [v for v in violations if v.severity == ConstraintSeverity.HARD]
        soft_violations = [v for v in violations if v.severity == ConstraintSeverity.SOFT]

        assert len(hard_violations) >= 1
        assert len(soft_violations) >= 1

    def test_contract_with_both_hard_and_soft_violations(self) -> None:
        """Contract with both expired AND zero bid reports both violations."""
        contract = _make_contract(expiration_offset_days=-5, bid="0.00", ask="1.00")
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)

        types = {v.violation_type for v in violations}
        assert ConstraintViolationType.EXPIRED in types
        assert ConstraintViolationType.ZERO_BID in types

    def test_boundary_oi_passes(self) -> None:
        """Contract with OI exactly at min_oi threshold should pass."""
        contract = _make_contract(open_interest=100)
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)
        oi_violations = [
            v for v in violations if v.violation_type == ConstraintViolationType.OI_TOO_LOW
        ]
        assert oi_violations == []

    def test_zero_bid_zero_ask_no_spread_violation(self) -> None:
        """When both bid and ask are zero, spread_pct is 0.0 — no spread violation."""
        contract = _make_contract(bid="0.00", ask="0.00")
        filters = _default_filters()

        violations = check_contract_constraints([contract], filters)
        spread_violations = [
            v for v in violations if v.violation_type == ConstraintViolationType.SPREAD_TOO_WIDE
        ]
        assert spread_violations == []


class TestRenderFormat:
    def test_render_format_matches_spec(self) -> None:
        """Output uses <<<CONSTRAINT_WARNINGS>>> delimiters, correct section headers."""
        violations = [
            ContractConstraint(
                contract_label="AAPL 200C 2026-04-18",
                violation_type=ConstraintViolationType.SPREAD_TOO_WIDE,
                detail="Bid-ask spread 42% exceeds 30% maximum",
                severity=ConstraintSeverity.HARD,
            ),
            ContractConstraint(
                contract_label="AAPL 210C 2026-05-16",
                violation_type=ConstraintViolationType.ZERO_BID,
                detail="Zero bid price",
                severity=ConstraintSeverity.SOFT,
            ),
        ]

        result = render_constraint_warnings(violations)

        assert result.startswith("<<<CONSTRAINT_WARNINGS>>>")
        assert result.endswith("<<<END_CONSTRAINT_WARNINGS>>>")
        assert "DO NOT recommend these contracts (hard constraint violations):" in result
        assert "EXERCISE CAUTION with these contracts (soft violations):" in result
        assert "AAPL 200C 2026-04-18: Bid-ask spread 42% exceeds 30% maximum" in result
        assert "AAPL 210C 2026-05-16: Zero bid price" in result

    def test_hard_violations_listed_before_soft(self) -> None:
        """In rendered output, hard violations section appears before soft."""
        violations = [
            ContractConstraint(
                contract_label="X",
                violation_type=ConstraintViolationType.ZERO_BID,
                detail="Zero bid",
                severity=ConstraintSeverity.SOFT,
            ),
            ContractConstraint(
                contract_label="Y",
                violation_type=ConstraintViolationType.EXPIRED,
                detail="Expired",
                severity=ConstraintSeverity.HARD,
            ),
        ]

        result = render_constraint_warnings(violations)

        hard_pos = result.index("DO NOT recommend")
        soft_pos = result.index("EXERCISE CAUTION")
        assert hard_pos < soft_pos

    def test_empty_violations_render_empty_string(self) -> None:
        """render_constraint_warnings([]) -> ''."""
        assert render_constraint_warnings([]) == ""

    def test_only_hard_violations_no_soft_section(self) -> None:
        """When only hard violations exist, soft section is omitted."""
        violations = [
            ContractConstraint(
                contract_label="X",
                violation_type=ConstraintViolationType.EXPIRED,
                detail="Expired",
                severity=ConstraintSeverity.HARD,
            ),
        ]
        result = render_constraint_warnings(violations)
        assert "DO NOT recommend" in result
        assert "EXERCISE CAUTION" not in result

    def test_only_soft_violations_no_hard_section(self) -> None:
        """When only soft violations exist, hard section is omitted."""
        violations = [
            ContractConstraint(
                contract_label="X",
                violation_type=ConstraintViolationType.ZERO_BID,
                detail="Zero bid",
                severity=ConstraintSeverity.SOFT,
            ),
        ]
        result = render_constraint_warnings(violations)
        assert "DO NOT recommend" not in result
        assert "EXERCISE CAUTION" in result


class TestContractConstraintModel:
    def test_contract_constraint_model_is_frozen(self) -> None:
        """ContractConstraint has frozen=True, assignment raises."""
        constraint = ContractConstraint(
            contract_label="AAPL 200C 2026-04-18",
            violation_type=ConstraintViolationType.EXPIRED,
            detail="Expired",
            severity=ConstraintSeverity.HARD,
        )
        with pytest.raises(ValidationError):
            constraint.contract_label = "modified"  # type: ignore[misc]

    def test_contract_constraint_json_roundtrip(self) -> None:
        """ContractConstraint survives JSON serialization roundtrip."""
        original = ContractConstraint(
            contract_label="AAPL 200C 2026-04-18",
            violation_type=ConstraintViolationType.SPREAD_TOO_WIDE,
            detail="Spread 42%",
            severity=ConstraintSeverity.HARD,
        )
        restored = ContractConstraint.model_validate_json(original.model_dump_json())
        assert restored == original
