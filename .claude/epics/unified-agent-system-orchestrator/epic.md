---
name: unified-agent-system-orchestrator
status: backlog
created: 2026-03-21T16:31:55Z
progress: 0%
prd: .claude/prds/unified-agent-system.md
parent_epic: unified-agent-system
depends_on:
  - unified-agent-system-desk-recommend
github: https://github.com/jobu711/options_arena/issues/646
---

# Epic: unified-agent-system-orchestrator

## Overview

Create the recommendation orchestrator (`run_recommendation()`), persistence layer (migration 037 + `RecommendationMixin`), and extract reusable code from `orchestrator.py` into a shared module. This epic wires desk recommendation agents + synthesis agent into a 3-phase pipeline with parallel execution, fallback handling, and persistence. The old `orchestrator.py` is NOT deleted here — that's Epic D.

## Scope Boundary

### In Scope
- Extract reusable functions from `orchestrator.py` → new `agents/_context.py`
- Create `agents/recommendation_orchestrator.py` — `run_recommendation()` 3-phase pipeline
- Create `data/migrations/037_recommendation_results.sql` — new table + `recommendation_protocol` column
- Create `data/_recommendation.py` — `RecommendationMixin` (save/get/list)
- Wire `RecommendationMixin` into `data/repository.py`
- Integration tests for orchestrator (success, partial failure, full fallback, timeout)
- Persistence round-trip tests

### Out of Scope (handled by sibling epics)
- Foundation models (foundation — done)
- Desk recommendation agents (desk-recommend — done)
- CLI/API wiring (cutover)
- Debate code deletion (cutover)
- Old `orchestrator.py` stays alive — both old and new orchestrators coexist

## Architecture Decisions

- **Reusable code extraction**: Move from `orchestrator.py` to new `agents/_context.py`:
  - `build_market_context()` (~350 LOC)
  - `extract_agent_predictions()` (~100 LOC)
  - `compute_citation_density()` (~30 LOC)
  - `_build_model_settings()` (~30 LOC)
  - `should_debate()` → add `should_recommend()` alias
  - Update `orchestrator.py` to import from `_context.py` (preserve backward compat during transition)

- **3-phase pipeline**:
  - Phase 0: Build `MarketContext`, populate `DeskDeps` with scan data
  - Phase 1 (parallel): 6 desk recommendation agents via `asyncio.gather(return_exceptions=True)`, gated by `asyncio.Semaphore(config.desk_parallelism)`
  - Phase 2 (sequential): Synthesis agent → `PositionRecommendation`
  - Phase 3: Persist to `recommendation_results` + extract `agent_predictions`

- **Never-raises contract**: `run_recommendation()` catches all exceptions → data-driven fallback `RecommendationResult(is_fallback=True)`.

- **Fallback `DomainAssessment`**: Failed desks produce `DomainAssessment(confidence=0.2, direction=NEUTRAL)` with the correct subclass type.

- **Migration 037**: `recommendation_results` table + `recommendation_protocol TEXT` column on `agent_predictions` with backfill to `'debate_v1'`.

## Technical Approach

### Code Extraction (`agents/_context.py`)

New module receives functions moved from `orchestrator.py`. Old `orchestrator.py` gets import-forwarding (`from ._context import build_market_context`) to preserve backward compat until Epic D deletes it.

### Recommendation Orchestrator (`agents/recommendation_orchestrator.py`)

```python
async def run_recommendation(
    ticker: str,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService | None = None,
    scan_run_id: int | None = None,
    spread_analysis: SpreadAnalysis | None = None,
    progress_callback: RecommendationProgressCallback | None = None,
) -> RecommendationResult:
    """Never-raises 3-phase recommendation pipeline."""
```

### Persistence (`data/_recommendation.py`)

```python
class RecommendationMixin:
    async def save_recommendation(self, result: RecommendationResult, scan_run_id: int | None) -> int
    async def get_recommendation_by_id(self, rec_id: int) -> RecommendationRow | None
    async def get_recent_recommendations(self, limit: int = 20) -> list[RecommendationRow]
    async def get_recommendations_for_ticker(self, ticker: str, limit: int = 5) -> list[RecommendationRow]
```

### Migration 037

```sql
CREATE TABLE IF NOT EXISTS recommendation_results (...);
CREATE INDEX idx_recommendation_results_ticker ...;
CREATE INDEX idx_recommendation_results_created_at ...;
ALTER TABLE agent_predictions ADD COLUMN recommendation_protocol TEXT NOT NULL DEFAULT 'debate_v1';
```

## Task Breakdown Preview

- [ ] Task 1: Extract reusable functions from `orchestrator.py` → `agents/_context.py`, update imports
- [ ] Task 2: Create `data/migrations/037_recommendation_results.sql`
- [ ] Task 3: Create `data/_recommendation.py` — `RecommendationMixin`, wire into `repository.py`
- [ ] Task 4: Create `agents/recommendation_orchestrator.py` — `run_recommendation()` pipeline
- [ ] Task 5: Integration tests — orchestrator (success/partial/full-failure/timeout) + persistence round-trip

## Dependencies

- **unified-agent-system-desk-recommend**: All 6 desk recommendation runners must exist
- **unified-agent-system-foundation**: All models + synthesis agent must exist
- Uses existing: `build_debate_model()` from `model_config.py`, `DeskDeps` from `_desk_deps.py`

## Success Criteria

- `run_recommendation()` produces valid `RecommendationResult` with `TestModel`
- Parallel desk execution works (6 desks via `asyncio.gather`)
- Partial failure: 2 desks fail → fallback assessments → synthesis still runs
- Full failure: all desks fail → data-driven fallback `RecommendationResult`
- Synthesis failure: desks succeed → fallback recommendation from assessments
- Persistence round-trip: save → get by ID → models match
- Migration 037 runs cleanly on existing DB
- Old `orchestrator.py` still works (imports forwarded from `_context.py`)
- `ruff check`, `pytest`, `mypy --strict` all pass

## Tasks Created

- [ ] #647 - Extract reusable functions from orchestrator.py to _context.py (parallel: true)
- [ ] #648 - Create migration 037 — recommendation_results table (parallel: true)
- [ ] #649 - Create RecommendationMixin and wire into Repository (parallel: false, depends: #648)
- [ ] #650 - Create recommendation_orchestrator.py — run_recommendation() pipeline (parallel: false, depends: #647, #649)
- [ ] #651 - Integration tests — orchestrator + persistence round-trip (parallel: false, depends: #650)

Total tasks: 5
Parallel tasks: 2 (Wave 1: #647+#648 simultaneous; Wave 2: #649; Wave 3: #650; Wave 4: #651)
Sequential tasks: 3
Estimated total effort: 17-24 hours

## Test Coverage Plan
Total test files planned: 5
Total test cases planned: ~42

## Estimated Effort

- 5 tasks
- ~800-1,000 LOC new (orchestrator + persistence + migration + _context.py)
- ~200-300 LOC new tests (12-16 test cases)
- Medium-high risk — parallel async orchestration, migration, code extraction
