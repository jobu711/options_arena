---
name: market-recon
status: backlog
created: 2026-03-03T08:47:27Z
progress: 0%
prd: .claude/prds/market-recon.md
github: https://github.com/jobu711/options_arena/issues/201
---

# Epic: market-recon

## Overview

Add an `IntelligenceService` to the services layer that fetches 6 unused yfinance methods (analyst targets, recommendations, upgrades/downgrades, insider transactions, institutional holders, news) and wire 30 new fields through `MarketContext` to all 7 debate agents. Simultaneously wire 22 already-computed DSE indicator fields (8 dimensional scores + 10 high-signal indicators + 3 second-order Greeks + 1 direction confidence) from `TickerScore` through to agents. Phase 1 only — zero new dependencies, $0/month.

## Architecture Decisions

- **Mirror OpenBB pattern exactly**: `IntelligenceService` follows the proven `OpenBBService` structure — class-based DI (`config`, `cache`, `limiter`), 6-step method pattern (config gate → cache check → rate-limited fetch → map to typed model → cache result → outer except returns None), explicit `close()`.
- **No new dependencies**: All intelligence data from yfinance (already installed). Safe converters from `services/helpers.py` (`safe_float`, `safe_int` already exist there). DSE data already computed in scan phases.
- **Four-ratio system**: New `intelligence_ratio()` and `dse_ratio()` on MarketContext, parallel to existing `completeness_ratio()` and `enrichment_ratio()`. No cross-contamination — intelligence/DSE fields excluded from core completeness.
- **Composite score stays pure technical**: No intelligence data affects scan ranking. `intelligence_score` is informational only (computed in render, not stored).
- **Raw labeled data to agents**: Agents receive flat key-value sections (not pre-digested summaries). They cite labels in arguments per existing prompt rules.
- **Second-order Greeks from IndicatorSignals**: vanna, charm, vomma already exist as fields on `TickerScore.signals` (models/scan.py lines 89-91), mapped same as other DSE indicators — NOT from OptionGreeks.
- **Migration 010 is lightweight**: MarketContext already serializes to JSON in `ai_debates.market_context_json`. New fields serialize automatically. Migration adds optional `intelligence_snapshots` table for historical storage only.

## Technical Approach

### New Files to Create

| File | Contents |
|------|----------|
| `src/options_arena/models/intelligence.py` | 7 frozen Pydantic models: `AnalystSnapshot`, `UpgradeDowngrade`, `AnalystActivitySnapshot`, `InsiderTransaction`, `InsiderSnapshot`, `InstitutionalSnapshot`, `IntelligencePackage` |
| `src/options_arena/services/intelligence.py` | `IntelligenceService` class (6 public methods + `fetch_intelligence` aggregator, all never-raises) |
| `data/migrations/010_intelligence_tables.sql` | `intelligence_snapshots` table |
| `tests/unit/models/test_intelligence_models.py` | Model construction, validation, NaN/Inf rejection (~40 tests) |
| `tests/unit/services/test_intelligence_service.py` | Service happy path, cache, errors, config toggles (~60 tests) |
| `tests/unit/agents/test_recon_context.py` | render_context_block with intelligence + DSE sections (~40 tests) |
| `tests/unit/agents/test_recon_orchestrator.py` | build_market_context with intelligence + DSE mapping (~30 tests) |
| `tests/unit/models/test_recon_market_context.py` | MarketContext new field validators, ratio methods (~20 tests) |
| `tests/integration/test_intelligence_integration.py` | Real yfinance calls, `@pytest.mark.integration` (~15 tests) |

### Files to Modify

| File | Change |
|------|--------|
| `models/config.py` | Add `IntelligenceConfig(BaseModel)` + nest in `AppSettings` |
| `models/analysis.py` | Add 30 fields to `MarketContext` + `intelligence_ratio()` + `dse_ratio()` + validators |
| `models/__init__.py` | Re-export intelligence models |
| `agents/_parsing.py` | Add 7 sections to `render_context_block()` |
| `agents/orchestrator.py` | Extend `build_market_context()` + `run_debate_v2()` with intelligence + DSE params |
| `services/__init__.py` | Re-export `IntelligenceService` |
| `services/health.py` | Add `check_intelligence()` method |
| `cli/commands.py` | Add `--no-recon` flag, create/close `IntelligenceService`, pass to orchestrator |
| `api/app.py` | Create `IntelligenceService` in lifespan, store on `app.state`, close in shutdown |
| `api/deps.py` | Add `get_intelligence()` dependency provider |
| `api/routes/debate.py` | Fetch intelligence before debate, pass to orchestrator |

### Key Reusable Code

- `services/helpers.py`: `safe_float()`, `safe_int()`, `safe_decimal()` — already exist, use directly
- `agents/_parsing.py`: `_render_optional()` — existing helper for None/NaN-guarded rendering
- `services/cache.py`: `ServiceCache.get()/set()` — same two-tier cache instance
- `services/rate_limiter.py`: `RateLimiter` — same token bucket + semaphore
- `services/market_data.py`: `_yf_call()` pattern — replicate in IntelligenceService

### Critical yfinance Parsing Notes (verified via live testing)

- `get_recommendations()`: Filter to `period == "0m"` row; columns are **camelCase** (`strongBuy`, `strongSell`)
- `get_upgrades_downgrades()`: Date is in **index** (`GradeDate`), not a column; `Action` values abbreviated (`up`/`down`/`init`/`main`/`reit`)
- `get_insider_transactions()`: `Transaction` column is **always empty** — parse type from `Text` column; column is `Insider` not `Filer`
- `get_major_holders()`: Single `Value` column indexed by string keys; access via `df.loc[key, "Value"]`
- `get_institutional_holders()`: Percentage column is `pctHeld` (float, e.g. `0.097`), NOT `% Out`
- `get_news(count=N)`: Returns `list[dict]` with nested structure — title at `item["content"]["title"]`

## Implementation Strategy

### Dependency Chain

```
T1 (models + config) → T2 (MarketContext fields) → T3 (service) → T4 (rendering) → T5 (orchestrator) → T6 (CLI/API) → T7 (health + migration)
```

Tasks T1-T3 are foundation. T4-T5 are context wiring. T6-T7 are integration. Run linter + type checker + tests after each task.

### Risk Mitigation

- **yfinance schema drift**: All column names verified against live yfinance 1.2.0 (2026-03-02). PRD documents every field mapping with source column.
- **Context token budget**: Full intelligence + DSE adds ~30 lines (~500 tokens) to the ~2000-token context budget. Well within limits.
- **Never-raises contract**: Every `IntelligenceService` method wraps in `try/except Exception: return None`. Debate never breaks due to intelligence failure.
- **Zero regressions**: All 2,917 existing tests must pass after each task.

## Task Breakdown Preview

- [ ] T1: Intelligence models + config — Create 7 frozen Pydantic models in `models/intelligence.py`, `IntelligenceConfig` in `config.py`, re-exports. Unit tests for model construction, validation, NaN/Inf rejection.
- [ ] T2: MarketContext extension — Add 30 new fields (8 intelligence + 8 dimensional + 10 DSE individual + 3 second-order Greeks + 1 confidence), `intelligence_ratio()`, `dse_ratio()`, validators. Unit tests.
- [ ] T3: IntelligenceService — Create service in `services/intelligence.py` with 6 fetch methods + aggregator. Never-raises, cache-first, rate-limited yfinance wrapping. Unit tests (mock yfinance).
- [ ] T4: Context block rendering — Add 7 sections to `render_context_block()`: Analyst Intelligence, Insider Activity, Institutional Ownership, Signal Dimensions, Volatility Regime, Market & Flow Signals, Second-Order Greeks. Unit tests.
- [ ] T5: Orchestrator wiring — Extend `build_market_context()` to accept `intelligence` param + map DSE from `TickerScore`. Extend `run_debate_v2()` signature. Unit tests.
- [ ] T6: CLI + API integration — `--no-recon` flag in debate command, `IntelligenceService` creation/cleanup in CLI + API lifespan/deps/routes. Integration wiring tests.
- [ ] T7: Health check + migration — `check_intelligence()` in `health.py`, migration `010_intelligence_tables.sql`. Health check tests.

## Dependencies

### Internal
- `MarketContext` model (`models/analysis.py`) — 30 new fields
- `render_context_block()` (`agents/_parsing.py`) — 7 new sections
- `build_market_context()` (`agents/orchestrator.py`) — intelligence + DSE mapping
- `ServiceCache`, `RateLimiter` (`services/`) — shared infrastructure
- `TickerScore.signals` + `.dimensional_scores` (`models/scan.py`, `models/scoring.py`) — DSE source data

### External
- yfinance >=1.2.0 (already installed) — 6 unused methods
- No new dependencies

## Success Criteria (Technical)

- All 7 intelligence models pass construction + validation + serialization tests
- `IntelligenceService` returns typed models or None (never raises) for all 6 categories
- Cache hit rate >90% on repeated calls (24h TTL for analyst/institutional)
- `render_context_block()` outputs 7 new sections when data present, omits when None
- `build_market_context()` correctly maps all 30 fields from intelligence + DSE sources
- `--no-recon` flag suppresses intelligence sections; DSE sections remain
- All 2,917 existing tests pass (zero regressions)
- `intelligence_ratio()` and `dse_ratio()` correctly compute field population fractions
- Context block stays within ~500 tokens for fully-populated intelligence + DSE data
- Latency overhead <3s for `fetch_intelligence()` (parallel yfinance calls + cache)

## Estimated Effort

- **Size**: L (Large) — 7 tasks, ~9 new files, ~11 files to modify
- **Tests**: ~205 new tests across models, services, agents, integration
- **Pattern risk**: Low — mirrors proven OpenBB integration pattern exactly
- **Critical path**: T1 → T2 → T3 (models must exist before service can return them)

## Tasks Created
- [ ] #202 - Intelligence models and config (parallel: false)
- [ ] #206 - MarketContext 30-field extension (parallel: false, depends: #202)
- [ ] #207 - IntelligenceService implementation (parallel: false, depends: #202)
- [ ] #208 - Context block rendering — 7 new sections (parallel: false, depends: #206)
- [ ] #203 - Orchestrator wiring — build_market_context + run_debate_v2 (parallel: false, depends: #202, #206)
- [ ] #204 - CLI and API integration wiring (parallel: false, depends: #207, #203)
- [ ] #205 - Health check and database migration (parallel: true, depends: #207)

Total tasks: 7
Parallel tasks: 1 (#205)
Sequential tasks: 6
Estimated total effort: 36 hours

## Test Coverage Plan
Total test files planned: 9
Total test cases planned: ~205
