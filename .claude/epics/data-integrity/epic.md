---
name: data-integrity
status: backlog
created: 2026-02-26T09:02:19Z
progress: 0%
prd: .claude/prds/data-integrity.md
github: https://github.com/jobu711/options_arena/issues/114
---

# Epic: data-integrity

## Overview

End-to-end data integrity hardening across all pipeline layers. Adds Pydantic validators
at model boundaries (OHLCV, OptionGreeks), rejects invalid data at service ingestion
(zero-price fallback elimination), introduces MarketContext completeness validation with
a debate quality gate, and hardens cache TTL validation. Goal: fail-fast on bad data
instead of silent degradation.

## Architecture Decisions

- **Validators at model boundaries**: Use Pydantic `field_validator` and `model_validator`
  on frozen models (OHLCV, OptionGreeks). These execute during construction with negligible
  overhead — no runtime performance impact.
- **No feature flags**: Audit test fixtures first (task 5), then add validators. Simpler
  than a flag-based rollout since the test suite is comprehensive.
- **`float | None` for optional indicators**: MarketContext fields that may be unavailable
  become `float | None` instead of silently defaulting to `0.0`. Context rendering and
  CLI display adapt to show "N/A" for None values.
- **Completeness threshold**: 60% minimum populated fields before LLM debate proceeds.
  Below threshold: data-driven fallback with logged reason. This reuses the existing
  fallback infrastructure — no new patterns needed.
- **No new dependencies**: All validation uses stdlib (`math`, `decimal`) and Pydantic.

## Technical Approach

### Models Layer (`models/`)
- OHLCV: Add `field_validator` on price fields (> 0, finite), volume (>= 0).
  Add `model_validator(mode="after")` for candle consistency (high >= low, prices within range).
- OptionGreeks: Add `math.isfinite()` validators on `theta` and `rho`, matching the
  existing pattern on `gamma`/`vega`.
- MarketContext: Change `iv_rank`, `iv_percentile`, `atm_iv_30d`, `put_call_ratio` from
  `float` to `float | None`. Add `completeness_ratio()` method.

### Services Layer (`services/`)
- `market_data.py`: Replace `safe_decimal(price) or Decimal("0")` with a check that raises
  `TickerNotFoundError` when price is None or <= 0. Bid/ask zero-fallback kept (legitimate
  for illiquid contracts).
- `cache.py`: Reject negative TTL in `set()` with `ValueError`.

### Agents Layer (`agents/`)
- `orchestrator.py`: Update `build_market_context()` to pass `None` instead of `0.0` for
  unavailable indicators. Add completeness check before bull agent invocation — below 60%
  triggers data-driven fallback.
- Update context rendering to handle `None` fields (show "N/A").

### Scoring Layer (`scoring/`)
- Verify existing `math.isfinite()` guards in `normalization.py` handle fully-NaN
  indicator series. Add explicit test cases.

## Implementation Strategy

**Order matters**: Task 5 (test fixture audit) should run early to identify which tests
construct models with zero/placeholder data. Then validators can be added without surprise
breakage. However, tasks 1-4 can be implemented in parallel if fixture issues are fixed
alongside each task.

**Recommended sequence**: Task 1 + Task 5 together (model validators + fixture fixes),
then Task 2 (service guards), then Task 3 (MarketContext + quality gate), then Task 4
(cache + NaN verification).

## Task Breakdown Preview

- [ ] Task 1: OHLCV candle integrity validators + OptionGreeks theta/rho NaN defense (FR-1 + FR-2)
- [ ] Task 2: Reject zero prices at service ingestion (FR-3)
- [ ] Task 3: MarketContext completeness validation + debate quality gate (FR-4 + FR-7)
- [ ] Task 4: Cache TTL validation + indicator NaN propagation guard (FR-5 + FR-6)
- [ ] Task 5: Test fixture audit and cleanup (cross-cutting)

## Dependencies

### Internal
- **Models module** — primary target (Tasks 1, 3)
- **Services module** — ingestion + cache (Tasks 2, 4)
- **Agents module** — orchestrator + context rendering (Task 3)
- **Scoring module** — verification only (Task 4)
- **Tests** — fixture updates across all modules (Task 5)

### External
- None — all changes are internal validation logic

## Success Criteria (Technical)

- Zero-price `Decimal("0")` never appears in `Quote.price` or `TickerInfo.current_price`
- OHLCV `model_validator` rejects all impossible candles (high < low, zero prices)
- All 5 Greeks fields (`delta`, `gamma`, `theta`, `vega`, `rho`) have `math.isfinite()` defense
- No MarketContext indicator field silently defaults to `0.0` when unavailable
- Debate quality gate enforces 60% completeness minimum
- Cache `set()` rejects negative TTL
- All 1,402 existing tests pass (zero regressions)
- 40-60 new tests covering all validator positive/negative/edge cases

## Estimated Effort

- **5 tasks**, ~40-60 new tests total
- Tasks 1-2 are focused model/service changes (~15-20 tests each)
- Task 3 is the most complex (MarketContext type changes ripple to rendering + debate)
- Tasks 4-5 are small verification/cleanup tasks
- Critical path: Task 1 → Task 3 → Task 5

## Tasks Created

- [ ] #115 - OHLCV candle integrity validators + OptionGreeks theta/rho NaN defense (parallel: true)
- [ ] #116 - Reject zero prices at service ingestion (parallel: true)
- [ ] #117 - MarketContext completeness validation + debate quality gate (parallel: false, depends: #115)
- [ ] #118 - Cache TTL validation + indicator NaN propagation guard (parallel: true)
- [ ] #119 - Test fixture audit and cleanup (parallel: false, depends: #115-#118)

Total tasks: 5
Parallel tasks: 3 (#115, #116, #118 can run concurrently)
Sequential tasks: 2 (#117 after #115; #119 after all)
Estimated total effort: 17-25 hours
Estimated new tests: ~46
