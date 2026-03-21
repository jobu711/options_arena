---
name: unified-agent-system-cutover
status: backlog
created: 2026-03-21T16:31:55Z
progress: 0%
prd: .claude/prds/unified-agent-system.md
parent_epic: unified-agent-system
depends_on:
  - unified-agent-system-orchestrator
github: null
---

# Epic: unified-agent-system-cutover

## Overview

The big bang cutover: rewire CLI and API to use `run_recommendation()`, delete all 13 debate-specific files, clean up exports and config, adapt reporting, and rewrite/remove ~50-80 debate tests. This is the final epic that completes the unification. After this epic, the debate system is gone and the recommendation system is the sole path.

## Scope Boundary

### In Scope
- Rewrite CLI `debate` command to use `run_recommendation()`, render `PositionRecommendation`
- Rewrite API debate routes to use `run_recommendation()`, return `RecommendationResult`
- Update `api/schemas.py` with recommendation response schemas
- Update `reporting/debate_export.py` for new model shape
- Update `agents/__init__.py` — replace debate exports with recommendation exports
- Delete 13 debate files: 6 debate agents, 1 orchestrator, 6 debate prompts
- Clean up `_parsing.py` — remove `DebateDeps`, `DebateResult` (moved/dead)
- Update `DebateConfig` — remove 4 dead fields, add 5 new fields, rename `min_debate_score`
- Backward compat: `GET /api/debate/{id}` checks both `ai_theses` and `recommendation_results`
- Update/rewrite affected tests (~50-80 debate tests)
- Update module CLAUDE.md files (agents/, models/, data/)
- Full regression suite

### Out of Scope
- Frontend `DebateResultPage.vue` rewrite (PRD marks as adapt-only, no UX redesign)
- WebSocket progress refactoring (reuse existing pattern, adapt event names)
- New desk agents beyond existing 6

## Architecture Decisions

- **Backward compat API**: `GET /api/debate/{id}` checks `recommendation_results` first (new IDs), then `ai_theses` (old IDs). Returns appropriate schema per table. Old data is read-only.
- **Config cleanup**: Remove `enable_volatility_agent`, `enable_rebuttal`, `phase1_parallelism`, `phase1_batch_delay`. Add `synthesis_timeout`, `recommendation_protocol`, `min_recommendation_score`, `desk_parallelism`, `disabled_desks`. Grep for all usages before removal.
- **`should_debate()` → `should_recommend()`**: Rename function, update callers. Same logic, reads from `min_recommendation_score`.
- **Test strategy**: Write new recommendation tests first (CLI rendering, API schemas, regression). Then delete old debate tests. Never leave a gap where both are absent.
- **Learning module adaptation**: `tune_vote_weights()` queries filter by `WHERE recommendation_protocol = 'unified_v1'`. Tuned weights injected into synthesis prompt via `SynthesisDeps.tuned_weights`.

## Technical Approach

### CLI Rewrite (`cli/commands.py`)

- `_debate_async()` → calls `run_recommendation()` instead of `run_debate()`
- `_batch_async()` → iterates with `run_recommendation()` per ticker
- Rendering: Replace agent panels with domain assessment panels + position recommendation
- Export: `debate_export.py` adapted for `RecommendationResult`
- `--fallback-only` flag preserved

### API Rewrite (`api/routes/debate.py`)

- `POST /api/debate` → starts `run_recommendation()` as background task
- `GET /api/debate/{id}` → checks both tables, returns appropriate schema
- `POST /api/debate/batch` → iterates with `run_recommendation()`
- WebSocket: `WS /ws/debate/{id}` → adapted progress events (parallel desk progress + synthesis)
- Response schemas: `RecommendationResult` serialization

### File Deletion (13 files)

```
agents/trend_agent.py
agents/volatility.py
agents/flow_agent.py
agents/fundamental_agent.py
agents/risk.py
agents/contrarian_agent.py
agents/orchestrator.py
agents/prompts/trend_agent.py
agents/prompts/volatility.py
agents/prompts/flow_agent.py
agents/prompts/fundamental_agent.py
agents/prompts/risk.py
agents/prompts/contrarian_agent.py
```

### Config Changes (`models/config.py`)

Remove: `enable_volatility_agent`, `enable_rebuttal`, `phase1_parallelism`, `phase1_batch_delay`
Add: `synthesis_timeout: float = 90.0`, `recommendation_protocol: str = "unified_v1"`, `min_recommendation_score: float = 30.0`, `desk_parallelism: int = 6`, `disabled_desks: list[str] = []`
Rename: `min_debate_score` → `min_recommendation_score`

## Task Breakdown Preview

- [ ] Task 1: Rewrite CLI `debate` command to use `run_recommendation()`, update rendering
- [ ] Task 2: Rewrite API debate routes to use `run_recommendation()`, update schemas
- [ ] Task 3: Update `reporting/debate_export.py` for `RecommendationResult` shape
- [ ] Task 4: Update `agents/__init__.py` — replace debate exports with recommendation exports
- [ ] Task 5: Update `DebateConfig` — remove dead fields, add new fields
- [ ] Task 6: Delete 13 debate files, clean up `_parsing.py`, remove `DebateDeps`/`DebateResult`
- [ ] Task 7: Rewrite/remove debate tests, add recommendation regression tests
- [ ] Task 8: Update module CLAUDE.md files, full regression suite, learning module filter adaptation

## Dependencies

- **unified-agent-system-orchestrator**: `run_recommendation()` must work end-to-end before rewiring callers
- All 3 prior epics must be complete and verified
- Grep for all debate-specific imports before deletion to ensure zero remaining importers

## Success Criteria

- `options-arena debate AAPL` works with recommendation system
- `POST /api/debate` returns `RecommendationResult`
- `GET /api/debate/{old_id}` still returns old debate data
- `GET /api/debate/{new_id}` returns recommendation data
- All 13 debate files deleted, zero import errors
- `DebateConfig` has no dead fields
- Interactive desk queries (`agency ask/chat`) unchanged
- Learning module queries filter by `recommendation_protocol`
- Full test suite passes: `ruff check`, `pytest tests/ -v`, `mypy --strict`
- Manual verification: CLI single + batch, API single + batch, web UI

## Estimated Effort

- 8 tasks
- ~600-800 LOC modified (CLI + API + reporting + config + exports)
- ~1,200 LOC deleted (13 debate files)
- ~400-600 LOC test changes (rewrite/remove old + add new)
- High risk — widest blast radius, most files touched. Mitigated by: all prior epics verified, grep before delete, test-first approach
