"""Deterministic constraint pre-check for option contracts entering debate.

Validates recommended contracts against hard and soft constraint rules before
they enter the debate pipeline. Hard violations (expired, DTE too short, OI too
low, spread too wide) disqualify contracts entirely. Soft violations (zero bid,
volume too low) generate caution warnings injected into agent context.

No LLM calls — pure deterministic logic operating on Pydantic models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from options_arena.models import (
    ConstraintSeverity,
    ConstraintViolationType,
    ContractConstraint,
    OptionContract,
    OptionsFilters,
)


def _contract_label(contract: OptionContract) -> str:
    """Build a human-readable label for a contract: 'AAPL 200C 2026-04-18'."""
    type_suffix = "C" if contract.option_type.value == "call" else "P"
    return f"{contract.ticker} {contract.strike}{type_suffix} {contract.expiration.isoformat()}"


def _spread_pct(contract: OptionContract) -> float:
    """Compute bid-ask spread as a fraction of mid price.

    Returns 0.0 when mid is zero (both bid and ask are zero) to avoid
    division by zero. The zero-bid case is caught separately as a soft
    violation.
    """
    mid = contract.mid
    if mid == Decimal("0"):
        return 0.0
    spread = contract.ask - contract.bid
    return float(spread / mid)


def check_contract_constraints(
    contracts: list[OptionContract],
    filters: OptionsFilters,
) -> list[ContractConstraint]:
    """Check contracts against hard and soft constraint rules.

    Parameters
    ----------
    contracts
        Recommended option contracts to validate.
    filters
        Option chain filters containing threshold values.

    Returns
    -------
    list[ContractConstraint]
        All violations found across all contracts. May be empty if all
        contracts pass all checks.
    """
    violations: list[ContractConstraint] = []
    today = datetime.now(UTC).date()

    for contract in contracts:
        label = _contract_label(contract)

        # --- Hard constraints ---

        # Expired contract
        if contract.expiration < today:
            violations.append(
                ContractConstraint(
                    contract_label=label,
                    violation_type=ConstraintViolationType.EXPIRED,
                    detail=f"Expired on {contract.expiration.isoformat()}",
                    severity=ConstraintSeverity.HARD,
                )
            )

        # DTE too short
        dte = (contract.expiration - today).days
        if dte < filters.min_dte:
            violations.append(
                ContractConstraint(
                    contract_label=label,
                    violation_type=ConstraintViolationType.DTE_TOO_SHORT,
                    detail=f"DTE {dte} < minimum {filters.min_dte}",
                    severity=ConstraintSeverity.HARD,
                )
            )

        # OI too low
        if contract.open_interest < filters.min_oi:
            violations.append(
                ContractConstraint(
                    contract_label=label,
                    violation_type=ConstraintViolationType.OI_TOO_LOW,
                    detail=(f"Open interest {contract.open_interest} < minimum {filters.min_oi}"),
                    severity=ConstraintSeverity.HARD,
                )
            )

        # Spread too wide
        spread_fraction = _spread_pct(contract)
        if spread_fraction > filters.max_spread_pct:
            violations.append(
                ContractConstraint(
                    contract_label=label,
                    violation_type=ConstraintViolationType.SPREAD_TOO_WIDE,
                    detail=(
                        f"Bid-ask spread {spread_fraction:.0%} "
                        f"exceeds {filters.max_spread_pct:.0%} maximum"
                    ),
                    severity=ConstraintSeverity.HARD,
                )
            )

        # --- Soft constraints ---

        # Zero bid
        if contract.bid == Decimal("0") and contract.ask > Decimal("0"):
            violations.append(
                ContractConstraint(
                    contract_label=label,
                    violation_type=ConstraintViolationType.ZERO_BID,
                    detail="Zero bid price",
                    severity=ConstraintSeverity.SOFT,
                )
            )

        # Volume too low
        if contract.volume < filters.min_volume:
            violations.append(
                ContractConstraint(
                    contract_label=label,
                    violation_type=ConstraintViolationType.VOLUME_TOO_LOW,
                    detail=(f"Volume {contract.volume} < minimum {filters.min_volume}"),
                    severity=ConstraintSeverity.SOFT,
                )
            )

    return violations


def render_constraint_warnings(violations: list[ContractConstraint]) -> str:
    """Render constraint violations as delimited text for agent prompt injection.

    Hard violations are listed before soft violations. Returns empty string
    when no violations exist.

    Format::

        <<<CONSTRAINT_WARNINGS>>>
        DO NOT recommend these contracts (hard constraint violations):
        - AAPL 200C 2026-04-18: Bid-ask spread 42% exceeds 30% maximum
        EXERCISE CAUTION with these contracts (soft violations):
        - AAPL 210C 2026-05-16: Zero bid price
        <<<END_CONSTRAINT_WARNINGS>>>
    """
    if not violations:
        return ""

    hard = [v for v in violations if v.severity == ConstraintSeverity.HARD]
    soft = [v for v in violations if v.severity == ConstraintSeverity.SOFT]

    lines: list[str] = ["<<<CONSTRAINT_WARNINGS>>>"]

    if hard:
        lines.append("DO NOT recommend these contracts (hard constraint violations):")
        for v in hard:
            lines.append(f"- {v.contract_label}: {v.detail}")

    if soft:
        lines.append("EXERCISE CAUTION with these contracts (soft violations):")
        for v in soft:
            lines.append(f"- {v.contract_label}: {v.detail}")

    lines.append("<<<END_CONSTRAINT_WARNINGS>>>")
    return "\n".join(lines)
