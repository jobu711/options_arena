---
name: dead-code-cleanup-refactor
status: backlog
created: 2026-03-23T13:21:12Z
progress: 0%
prd: .claude/prds/dead-code-cleanup.md
parent_epic: dead-code-cleanup
depends_on: []
worktree: ../wt-refactor
branch: epic/dead-code-cleanup-refactor
github: https://github.com/jobu711/options_arena/issues/709
---

# Epic: dead-code-cleanup-refactor

## Overview

Wave 2: Delete dead debate rendering functions and domain-specific context renderers,
extract shared helpers to reduce duplication, and simplify over-complex patterns. Mix
of deletion (~910 lines) and refactoring (~175 lines net reduction).

## Scope Boundary

### In Scope
- FR-2.1: Delete 10 dead debate rendering functions from `cli/rendering.py` (~490 lines)
- FR-2.2: Delete 5 dead domain-specific context renderers from `agents/_parsing.py` (~420 lines)
- FR-2.3: De-duplicate `_contracts_to_cache_bytes`/`_cache_bytes_to_contracts`
- FR-2.4: Extract `_check_api_provider()` in `services/health.py`
- FR-2.5: Extract `FiniteFieldsMixin` for config validators
- FR-2.6: Fix `enrichment_ratio()` dead code path

### Out of Scope (handled by sibling epics)
- Individual dead function/model deletion (Wave 1: quickwins)
- IntelligenceService, dead endpoints, eval harness (Wave 3: orphans)
- process_ticker_options refactor, debate sunset (Wave 4: sunset)

## Technical Approach

### FR-2.1: Dead debate rendering (~490 lines)
Delete from `cli/rendering.py`:
- `render_volatility_panel` (line 183)
- `render_flow_panel` (line 233)
- `render_fundamental_panel` (line 275)
- `render_risk_panel` (line 322)
- `render_contrarian_panel` (line 374)
- `render_spread_panel` (line 416)
- `render_debate_panels` (line 470)
- `_build_agent_panel_text` (line 553)
- `_build_verdict_panel_text` (line 588)
- `render_batch_summary_table` (line 675)

Update/delete 4 test files:
- `tests/unit/cli/test_rendering.py`
- `tests/unit/cli/test_rendering_v2.py`
- `tests/unit/cli/test_spread_rendering.py`
- `tests/unit/cli/test_batch_debate.py`

### FR-2.2: Dead context renderers (~420 lines)
Delete from `agents/_parsing.py`:
- `_render_identity_block` (line 192-227)
- `render_trend_context` (line 230-270)
- `render_volatility_context` (line 273-393)
- `render_flow_context` (line 396-440)
- `render_fundamental_context` (line 443-578)
- `render_macro_context` (line 581-608)

Remove re-exports from `agents/__init__.py`.

Update/delete ~5 test files:
- `tests/unit/agents/test_domain_renderers.py`
- `tests/unit/agents/test_macro_rendering.py`
- `tests/unit/agents/test_neural_context.py`
- `tests/unit/agents/test_vol_rendering.py`
- `tests/unit/agents/test_volatility_ml_context.py`

### FR-2.3: De-duplicate cache serialization
Extract `_contracts_to_cache_bytes` / `_cache_bytes_to_contracts` from both
`services/options_data.py:126-134` and `services/cboe_provider.py:220-228` into
`services/helpers.py`. Update both importers.

### FR-2.4: Health check consolidation
Extract shared `_check_api_provider(name, url, headers, timeout)` method from
`check_groq()` (line 117) and `check_anthropic()` (line 210) in `services/health.py`.
Both methods share ~80 lines of identical status-code branching.

### FR-2.5: Config validator mixin
Create `FiniteFieldsMixin` with the shared `validate_all_finite` model validator.
Apply to 9 config classes in `models/config.py` that currently duplicate the same
~9-line validator. Net reduction ~80 lines.

### FR-2.6: enrichment_ratio dead path
- `MarketContext.enrichment_ratio()` in `models/analysis.py:275-281` returns hardcoded `0.0`
- `agents/_parsing.py:915` has always-true conditional checking `enrichment_ratio() == 0.0`
- Options: (a) delete method + remove dead conditional, or (b) make ratio functional
- Recommendation: delete method, remove conditional, always append "enrichment not available" note

## Task Breakdown Preview

- [ ] Task 1: Delete 10 dead debate rendering functions from rendering.py
- [ ] Task 2: Update/delete 4 rendering test files
- [ ] Task 3: Delete 5+1 dead context renderers from _parsing.py + remove re-exports
- [ ] Task 4: Update/delete ~5 context renderer test files
- [ ] Task 5: Extract cache serialization helpers to services/helpers.py
- [ ] Task 6: Extract _check_api_provider in health.py
- [ ] Task 7: Extract FiniteFieldsMixin + apply to 9 config classes
- [ ] Task 8: Fix enrichment_ratio dead code path
- [ ] Task 9: Verification — lint + typecheck + tests + docs regen

## Shared File Conflicts (with sibling epics)

| File | This epic | Conflict with |
|------|-----------|---------------|
| `models/config.py` | FiniteFieldsMixin | quickwins (del num_ctx), orphans (del IntelligenceConfig) |
| `models/analysis.py` | enrichment_ratio | quickwins (del ContractConstraint), sunset (thesis classes) |
| `agents/__init__.py` | del renderer re-exports | quickwins (del dead re-exports) |

Resolution: rebase onto master after quickwins merges. Conflicts are non-overlapping line ranges.

## Dependencies

- None (executes in parallel, merges second)

## Success Criteria

- `rendering.py` drops from ~1,019 to ~530 lines
- `_parsing.py` drops by ~420 lines
- Zero duplicate `_contracts_to_cache_bytes` implementations
- `check_groq`/`check_anthropic` share a common helper
- 9 config validators replaced by single mixin
- `enrichment_ratio()` dead path removed
- All tests pass

## Estimated Effort

- 9 tasks
- ~2-3 hours wall-clock
- Merges second (rebase after quickwins)

## Tasks Created
- [ ] #712 - Delete 10 dead debate rendering functions from rendering.py (parallel: true)
- [ ] #717 - Update/delete 4 rendering test files (parallel: false, depends: #712)
- [ ] #725 - Delete 6 dead context renderers from _parsing.py + remove re-exports (parallel: true)
- [ ] #715 - Update/delete 5 context renderer test files (parallel: false, depends: #725)
- [ ] #719 - Extract cache serialization helpers to services/helpers.py (parallel: true)
- [ ] #728 - Extract _check_api_provider in health.py (parallel: true)
- [ ] #716 - Extract FiniteFieldsMixin + apply to 10 config classes (parallel: true)
- [ ] #721 - Fix enrichment_ratio dead code path (parallel: false, depends: #725)
- [ ] #729 - Verification — lint + typecheck + tests + docs regen (parallel: false, depends: all)

Total tasks: 9
Parallel tasks: 5 (#712, #725, #719, #728, #716)
Sequential tasks: 4 (#717→#712, #715→#725, #721→#725, #729→all)
Estimated total effort: 3.0 hours

## Test Coverage Plan
Total test files planned: 4 new
Total test cases planned: ~20 new test cases
- `tests/unit/services/test_cache_serialization.py` (6 cases)
- `tests/unit/services/test_health_provider_helper.py` (7 cases)
- `tests/unit/models/test_finite_fields_mixin.py` (7 cases)
- `tests/unit/models/test_enrichment_ratio_cleanup.py` (3 cases, optional)
