---
name: dead-code-cleanup-quickwins
status: backlog
created: 2026-03-23T13:21:12Z
progress: 0%
prd: .claude/prds/dead-code-cleanup.md
parent_epic: dead-code-cleanup
depends_on: []
worktree: ../wt-quickwins
branch: epic/dead-code-cleanup-quickwins
github: null
---

# Epic: dead-code-cleanup-quickwins

## Overview

Wave 1: Delete dead functions, models, fields, types, test fixtures, and stale flags
across all modules. Every item has zero production callers confirmed by grep. All
quick-win deletions with zero risk of behavioral change.

## Scope Boundary

### In Scope
- FR-1.1: agents/ dead code (should_debate, _log_completeness_breakdown, DebateProgressCallback, extract_agent_predictions, constraints.py full removal, _run_unimplemented, _IMPLEMENTED_DESKS, 7 delegate functions, stale desk prompt comments)
- FR-1.2: indicators/ dead functions (6 functions + 4 IndicatorSignals fields + __init__.py cleanup)
- FR-1.3: models/ + data/ dead code (num_ctx, MacroSignals, MacroRegimeResult, AgentMemory, save_agent_memory, get_agent_memories, get_recommended_contract_id, save_debate, save_agent_predictions, get_eval_definition singular, _cached_fetch)
- FR-1.4: api/ + reporting/ + cli/ dead code (AgencyQueryStarted, export_debate_to_file, DebateProgressBridge, --no-recon flag)
- FR-1.5: web/ dead code (types/agency.ts, getAgencyQuery, debate store dead members, DebateOptions, IndicatorAttributionResult, SectorOption, OpenBB enrichment fields + rendering)
- FR-1.6: tests/ cleanup (fixtures, docstrings, orchestration_known_values.json, CLAUDE.md)

### Out of Scope (handled by sibling epics)
- Debate rendering functions (Wave 2: refactor)
- Domain-specific context renderers (Wave 2: refactor)
- Shared helper extraction (Wave 2: refactor)
- IntelligenceService removal (Wave 3: orphans)
- Dead API endpoints (Wave 3: orphans)
- Eval harness removal (Wave 3: orphans)
- process_ticker_options refactor (Wave 4: sunset)
- Old debate backward-compat sunset (Wave 4: sunset)

## Technical Approach

### Strategy
Pure deletion — no refactoring, no new code. For each item:
1. Delete the function/class/field
2. Remove from `__init__.py` re-exports
3. Delete or update tests that exercise the deleted code
4. Run `uv run ruff check . --fix && uv run ruff format .`
5. Run `uv run pytest -m "not exhaustive" -n auto -q`

### agents/ cleanup details
- `should_debate()` in `_context.py:41-49` — delete function, update 3 test files
- `_log_completeness_breakdown()` in `_context.py:446-482` — delete (zero callers anywhere)
- `DebateProgressCallback` in `_context.py:629-630` — delete type alias
- `extract_agent_predictions()` in `_context.py` (~105 lines) — delete, update `__init__.py`
- `constraints.py` (183 lines) — delete entire file. Also delete `ConstraintSeverity`, `ConstraintViolationType` from `models/enums.py` and `ContractConstraint` from `models/analysis.py`. Delete `test_constraints.py` (~336 lines)
- `_run_unimplemented()` in `_routing.py:418-428` — delete
- `_IMPLEMENTED_DESKS` in `_routing.py:432-442` — delete, update test
- 7 delegate functions in `_routing.py:341-415` — replace with direct refs in `_desk_runners` dict
- Update stale debate-mode comments in 7 desk prompt files

### indicators/ cleanup details
- Delete from `regime.py`: `compute_vix_term_structure` (20-44), `compute_risk_on_off` (47-67), `compute_sector_momentum` (70-90)
- Delete from `iv_analytics.py`: `compute_vix_correlation` (331-368)
- Delete from `options_specific.py`: `put_call_ratio_oi` (71-78)
- Delete from `regime_ml.py`: `map_regime_label_to_market_regime` (212-227)
- Remove from `indicators/__init__.py` re-exports
- Remove `IndicatorSignals` fields: `vix_term_structure`, `risk_on_off_score`, `sector_relative_momentum`, `vix_correlation` from `models/scan.py`
- Update `dimensional.py` `FAMILY_INDICATOR_MAP` to remove references to deleted fields

### models/ + data/ cleanup details
- `DebateConfig.num_ctx` field + validator in `models/config.py:330,412-417`
- `MacroSignals` + `MacroRegimeResult` in `models/macro.py:113-175`
- `AgentMemory` in `models/strategy.py:111-151`
- `save_agent_memory()` + `get_agent_memories()` in `data/_learning.py:265,301`
- `get_recommended_contract_id()` in `data/_debate.py:167`
- `save_debate()` in `data/_debate.py:65` (~70 lines)
- `save_agent_predictions()` in `data/_debate.py:135` (~50 lines)
- `get_eval_definition()` (singular) in `data/_eval.py:124-142`
- `_cached_fetch()` in `services/base.py` (~38 lines)

### api/ + reporting/ + cli/ cleanup details
- `AgencyQueryStarted` in `api/schemas.py:935-939`
- `export_debate_to_file` in `reporting/debate_export.py:733-758` + re-export
- `DebateProgressBridge` in `api/ws.py` (~32 lines)
- `--no-recon` flag from debate CLI command (~15 lines across 3 functions)

### web/ cleanup details
- Delete `web/src/types/agency.ts` entirely, remove re-exports from `types/index.ts`
- Delete `getAgencyQuery()` from `web/src/api/agency.ts`
- Delete `debates` ref + `fetchDebates()` from `web/src/stores/debate.ts`
- Delete `DebateOptions` interface + unused `options` param from `startDebate()`
- Delete `IndicatorAttributionResult` from `types/analytics.ts`
- Delete `SectorOption` from `types/scan.ts`
- Remove 12 OpenBB enrichment fields from `types/debate.ts:70-81`
- Remove enrichment rendering from `DebateResultPage.vue:236-301` (~60 lines)

### tests/ cleanup details
- Delete `mock_debate_config` from `tests/unit/agents/conftest.py:132-139`
- Delete 6 unused fixtures from `tests/unit/scoring/conftest.py`
- Fix stale docstrings in `test_benchmarks.py` and performance `conftest.py`
- Delete or update `orchestration_known_values.json`
- Update `api/CLAUDE.md` ConfigResponse example

## Task Breakdown Preview

- [ ] Task 1: agents/ dead code — delete should_debate, _log_completeness_breakdown, DebateProgressCallback, extract_agent_predictions from _context.py
- [ ] Task 2: agents/ constraints — delete constraints.py + related enums/models + test_constraints.py
- [ ] Task 3: agents/ routing — delete _run_unimplemented, _IMPLEMENTED_DESKS, replace 7 delegates with direct refs
- [ ] Task 4: agents/ prompts — update stale debate-mode comments in 7 desk prompt files
- [ ] Task 5: indicators/ — delete 6 dead functions + remove 4 IndicatorSignals fields + update dimensional.py
- [ ] Task 6: models/ + data/ — delete dead models, config fields, data methods, _cached_fetch
- [ ] Task 7: api/ + reporting/ + cli/ — delete AgencyQueryStarted, export_debate_to_file, DebateProgressBridge, --no-recon flag
- [ ] Task 8: web/ — delete dead types, store members, enrichment fields + rendering
- [ ] Task 9: tests/ — delete dead fixtures, fix docstrings, update reference data + CLAUDE.md
- [ ] Task 10: Verification — run full lint + typecheck + test suite, regenerate docs

## Dependencies

- None (this is the first epic to merge)

## Success Criteria

- All items from FR-1.1 through FR-1.6 deleted
- Zero ruff lint errors
- Zero mypy errors
- All tests pass
- `__init__.py` re-exports match actual usage
- No dead `IndicatorSignals` fields remain

## Estimated Effort

- 10 tasks, all quick-win deletions
- ~1-2 hours wall-clock
- Merges first (clean merge to master)
