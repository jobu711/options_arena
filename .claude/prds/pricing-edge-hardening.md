---
name: pricing-edge-hardening
description: Fix 2 bugs and add parametric stress tests for pricing and contract selection
status: backlog
created: 2026-03-09T14:57:03Z
---

# PRD: pricing-edge-hardening

## Executive Summary

Harden the mathematical foundations of options pricing (BSM/BAW) and contract selection
by fixing two discovered bugs and adding comprehensive parametric stress tests with
financial invariant assertions. Establishes a reusable test harness for future numerical
code verification.

## Problem Statement

### What problem are we solving?

The BAW solver and contract selection pipeline work correctly under normal market conditions
but have undocumented boundary behavior. Two concrete bugs were found during code audit:
(1) stale quotes with bid > ask inflate liquidity scores, and (2) NaN delta values from
extreme pricing inputs can corrupt contract sorting. No parametric stress tests exist to
verify financial invariants across extreme parameter combinations.

### Why is this important now?

The liquidity weighting epic (PR #384) just added `chain_spread_pct` multiplier to
`select_by_delta()`, increasing the surface area where numerical edge cases matter.
The backtesting engine (next planned epic) will rely on pricing and contract selection
correctness for historical replay — hardening now prevents compounding errors later.

## User Stories

- As a developer, I want confidence that pricing functions produce correct results for
  extreme inputs (meme stocks, near-expiry options, deep ITM/OTM) so that the debate
  agents receive valid data.
- As a developer, I want a reusable test harness so that future pricing/scoring work
  can quickly verify numerical correctness.
- As a user, I want stale or corrupted market data to be handled gracefully rather than
  silently producing incorrect contract recommendations.

## Architecture & Design

### Chosen Approach

Test Harness Module + Inline Fixes. Create `tests/harnesses/` with parameter generators
and synthetic chain factory. Fix bugs inline in `scoring/contracts.py`. Minimal production
code churn (~10 lines), maximum test coverage.

### Module Changes

- `scoring/contracts.py`: 2 guard-clause additions (no new functions, no API changes)
- `tests/harnesses/`: New package with `pricing_params.py` and `chain_factory.py`
- `tests/unit/pricing/test_stress.py`: Property-based + brute-force pricing stress tests
- `tests/unit/scoring/test_contract_edge_cases.py`: Synthetic chain edge case tests

### Data Models

No new production models. Test-only `PricingParams` and `ChainSpec` dataclasses in harness.

### Core Logic

Bug Fix 1: Clamp `spread_component` to `[0.0, 1.0]` in `_compute_liquidity_score()`.
Bug Fix 2: Skip contracts with `not math.isfinite(abs_delta)` in `select_by_delta()`.
10 financial invariant properties verified across ~200 parameter combinations.
~2K brute-force grid for numerical stability (slow marker).

## Requirements

### Functional Requirements

- FR-1: `_compute_liquidity_score()` returns values in `[0.0, 1.0]` for all inputs
- FR-2: `select_by_delta()` never passes NaN to sort key
- FR-3: BSM/BAW prices are non-negative for all valid inputs
- FR-4: Put-call parity holds for BSM within 1e-6 tolerance
- FR-5: American option price >= European option price for identical inputs
- FR-6: All 5 Greeks satisfy sign constraints (delta bounds, gamma/vega non-negative)

### Non-Functional Requirements

- NFR-1: Property-based tests complete in < 30s (CI-compatible)
- NFR-2: Brute-force grid completes in < 120s (slow marker)
- NFR-3: All existing 4,200+ tests continue to pass
- NFR-4: No new runtime dependencies

## API / CLI Surface

N/A — internal correctness hardening only.

## Testing Strategy

- Default marker: ~30 property-based invariant tests (~200 combos x 10 properties). CI-fast.
- `@pytest.mark.slow`: ~2K brute-force grid. Manual/nightly.
- ~15 synthetic chain edge case tests. CI-fast.
- Full regression: `uv run pytest tests/ -n auto -q`

## Success Criteria

- Both bugs have regression tests that fail without the fix and pass with it
- All 10 financial invariants hold across the property grid
- Zero failures in the brute-force grid
- All existing tests pass unchanged
- Test harness is importable and documented for future use

## Constraints & Assumptions

- No new runtime dependencies (test harness is test-only code)
- Tests use `pytest.mark.parametrize` (no hypothesis dependency)
- BAW critical price non-convergence is out of scope (logged warning, non-fatal)
- IV solver convergence edge cases are out of scope (separate follow-up)

## Out of Scope

- Decimal precision audit for bid/ask/mid calculations
- IV solver diagnostic message improvements
- Hypothesis property-based testing framework
- BAW critical price convergence improvements
- Negative interest rate (r < 0) support

## Dependencies

- Existing `pricing/bsm.py`, `pricing/american.py`, `pricing/dispatch.py`
- Existing `scoring/contracts.py`
- Existing `models/options.py` (OptionContract, OptionGreeks, OptionType)
