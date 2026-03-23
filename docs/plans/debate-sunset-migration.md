# Data Migration Plan: ai_theses Sunset

**Issue**: #736
**Status**: DEFERRED -- planning only, no production code changes
**Date**: 2026-03-23

## Overview

The `ai_theses` table is the legacy debate result storage from the v1/v2 debate system.
Since the unified agent system cutover (v3.0.0, 2026-03-22), all new analysis flows through
`run_recommendation()` and persists to `recommendation_results`. The `ai_theses` table
remains for backward-compatible reads of historical debate data.

This plan documents the migration strategy to sunset `ai_theses` and remove all
backward-compatibility code that supports dual-table lookup.

---

## 1. Source Schema: `ai_theses`

Built across 8 migrations: 001, 002, 003, 004, 005, 009, 019, 026.

| Column | Type | Nullable | Source Migration | Notes |
|--------|------|----------|-----------------|-------|
| `id` | INTEGER PRIMARY KEY | No | 001 | AUTOINCREMENT |
| `scan_run_id` | INTEGER | Yes | 001 (nullable in 002) | FK to `scan_runs(id)` |
| `ticker` | TEXT | No | 001 | |
| `bull_json` | TEXT | Yes | 001 | Serialized `AgentResponse` (trend agent in v2) |
| `bear_json` | TEXT | Yes | 001 | Serialized `AgentResponse` (static fallback in v2) |
| `risk_json` | TEXT | Yes | 001 | v1 risk agent JSON (superseded by `risk_assessment_json`) |
| `verdict_json` | TEXT | Yes | 001 | Serialized `TradeThesis` or `ExtendedTradeThesis` |
| `vol_json` | TEXT | Yes | 003 | Serialized `VolatilityThesis` |
| `rebuttal_json` | TEXT | Yes | 004 | Serialized `AgentResponse` (bull rebuttal) |
| `total_tokens` | INTEGER | No | 002 | Default 0 |
| `model_name` | TEXT | No | 002 | Default '' |
| `duration_ms` | INTEGER | No | 002 | Default 0 |
| `is_fallback` | INTEGER | No | 002 | Default 0 (boolean) |
| `created_at` | TEXT | No | 001 | ISO 8601 UTC |
| `debate_mode` | TEXT | No | 005 | Default 'full' |
| `citation_density` | REAL | No | 005 | Default 0.0 |
| `market_context_json` | TEXT | Yes | 009 | Serialized `MarketContext` |
| `flow_json` | TEXT | Yes | 019 | Serialized `FlowThesis` |
| `fundamental_json` | TEXT | Yes | 019 | Serialized `FundamentalThesis` |
| `risk_assessment_json` | TEXT | Yes | 019 (renamed in 026) | Serialized `RiskAssessment` |
| `contrarian_json` | TEXT | Yes | 019 | Serialized `ContrarianThesis` |
| `debate_protocol` | TEXT | Yes | 019 (normalized in 026) | Default 'v1', normalized to 'current' |

Indexes:
- `idx_ai_theses_ticker ON ai_theses(ticker)` (migration 002)

---

## 2. Target Schema: `recommendation_results`

Created in migration 037.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | INTEGER PRIMARY KEY | No | AUTOINCREMENT |
| `ticker` | TEXT | No | |
| `scan_run_id` | INTEGER | Yes | FK to `scan_runs(id)` |
| `direction` | TEXT | No | SignalDirection enum value |
| `confidence` | REAL | No | [0.0, 1.0] |
| `recommended_contract` | TEXT | No | Contract description string |
| `entry_price` | TEXT | No | Decimal as string |
| `entry_criteria` | TEXT | No | |
| `exit_criteria` | TEXT | No | |
| `stop_loss` | TEXT | Yes | Decimal as string |
| `take_profit` | TEXT | Yes | Decimal as string |
| `position_size_pct` | REAL | No | |
| `risk_reward_ratio` | REAL | No | |
| `recommended_strategy` | TEXT | Yes | SpreadType enum value |
| `summary` | TEXT | No | |
| `key_factors_json` | TEXT | No | JSON array of strings |
| `risk_assessment` | TEXT | No | Free-text risk assessment |
| `agent_agreement_score` | REAL | Yes | [0.0, 1.0] |
| `dissenting_desks_json` | TEXT | No | Default '[]' |
| `assessments_json` | TEXT | No | JSON array of domain assessments |
| `total_input_tokens` | INTEGER | No | Default 0 |
| `total_output_tokens` | INTEGER | No | Default 0 |
| `duration_ms` | INTEGER | No | |
| `is_fallback` | INTEGER | No | Default 0 (boolean) |
| `citation_density` | REAL | No | Default 0.0 |
| `position_rationale` | TEXT | No | Default '' |
| `strategy_rationale` | TEXT | No | Default '' |
| `max_loss_estimate` | TEXT | No | Default '' |
| `model_used` | TEXT | No | |
| `created_at` | TEXT | No | ISO 8601 UTC |

Indexes:
- `idx_recommendation_results_ticker ON recommendation_results(ticker)`
- `idx_recommendation_results_created_at ON recommendation_results(created_at DESC)`

---

## 3. Field Mapping: ai_theses -> recommendation_results

Many fields in `ai_theses` store per-agent JSON blobs that have no direct mapping to the
flat `recommendation_results` schema. The migration must extract and transform data from
these JSON blobs.

### Direct Mappings

| ai_theses Column | recommendation_results Column | Transformation |
|-----------------|------------------------------|----------------|
| `ticker` | `ticker` | None |
| `scan_run_id` | `scan_run_id` | None |
| `duration_ms` | `duration_ms` | None |
| `is_fallback` | `is_fallback` | None |
| `citation_density` | `citation_density` | None |
| `created_at` | `created_at` | None |
| `total_tokens` | `total_input_tokens` + `total_output_tokens` | Split: input = total * 0.6, output = total * 0.4 (estimate) |
| `model_name` | `model_used` | None |

### Extracted from verdict_json (TradeThesis / ExtendedTradeThesis)

| verdict_json Field | recommendation_results Column | Transformation |
|-------------------|------------------------------|----------------|
| `direction` | `direction` | SignalDirection enum value |
| `confidence` | `confidence` | Clamp to [0.0, 1.0] |
| `summary` | `summary` | None |
| `key_factors` | `key_factors_json` | `json.dumps(key_factors)` |
| `risk_assessment` | `risk_assessment` | None |
| `recommended_strategy` | `recommended_strategy` | SpreadType enum value or NULL |
| `agent_agreement_score` (Extended) | `agent_agreement_score` | None |
| `dissenting_agents` (Extended) | `dissenting_desks_json` | `json.dumps(dissenting_agents)` |

### Synthesized / Default Fields

These fields do not exist in `ai_theses` and must be synthesized with sensible defaults:

| recommendation_results Column | Default Value | Rationale |
|------------------------------|---------------|-----------|
| `recommended_contract` | `"{ticker} legacy debate"` | No contract recommendation in old format |
| `entry_price` | `"0.00"` | No entry pricing in old format |
| `entry_criteria` | `"Legacy debate — no entry criteria specified"` | |
| `exit_criteria` | `"Legacy debate — no exit criteria specified"` | |
| `stop_loss` | `NULL` | |
| `take_profit` | `NULL` | |
| `position_size_pct` | `0.02` | Conservative 2% default |
| `risk_reward_ratio` | `0.0` | Unknown |
| `assessments_json` | Reconstructed from agent JSONs | See section 4 |
| `position_rationale` | `"Migrated from legacy debate system"` | |
| `strategy_rationale` | Extracted from vol_json if available | |
| `max_loss_estimate` | Extracted from risk_assessment_json if available | |

### Assessment Reconstruction

The `assessments_json` field in `recommendation_results` stores a JSON array of domain
assessment summaries. For migrated rows, this is reconstructed from the individual agent
JSON columns:

| ai_theses Source | Assessment Desk | Extracted Fields |
|-----------------|-----------------|------------------|
| `bull_json` | `trend` | direction, confidence, summary (from argument) |
| `vol_json` | `volatility` | direction, confidence, summary (from strategy_rationale) |
| `flow_json` | `flow` | direction, confidence, summary (from gex_interpretation) |
| `fundamental_json` | `fundamental` | direction, confidence, summary (from earnings_assessment) |
| `risk_assessment_json` | `risk` | direction=neutral, confidence, summary (from max_loss_estimate) |
| `contrarian_json` | `contrarian` | direction (dissent_direction), confidence (dissent_confidence), summary (primary_challenge) |

---

## 4. Data Transformation Rules

1. **Parse verdict_json first**: Try `ExtendedTradeThesis.model_validate_json()`, fall back
   to `TradeThesis.model_validate_json()`. If both fail, skip the row (log warning).

2. **Agent JSON is optional**: Each agent JSON column may be NULL. Only include assessments
   for non-NULL agent outputs.

3. **Token split**: `total_tokens` is a single count. Split as 60/40 input/output estimate.
   This is an approximation since the original data did not distinguish.

4. **ID preservation**: Migrated rows receive new auto-increment IDs in
   `recommendation_results`. The old `ai_theses.id` is NOT preserved (the ID spaces may
   overlap). Store a mapping table for reference.

5. **Validation**: Every migrated row must pass `RecommendationRow` dataclass construction
   to ensure data integrity.

---

## 5. Code to Be Removed After Migration (~907 lines)

### api/routes/debate.py (~125 lines of dual-table lookup)

- Lines 544-594: `list_debates()` old debate summary gathering (lines gathering from
  `get_recent_debates`/`get_debates_for_ticker`, parsing verdict_json, building
  `DebateResultSummary` from old data, merge+sort logic)
- Lines 597-615: `_parse_agent_json()` helper function
- Lines 635-729: `get_debate()` backward-compat branch (ai_theses lookup, parsing
  bull/bear/vol/flow/fundamental/risk/contrarian JSON, building `DebateResultDetail`)
- Imports: `AgentResponse`, `ContrarianThesis`, `ExtendedTradeThesis`, `FlowThesis`,
  `FundamentalThesis`, `RiskAssessment`, `TradeThesis` (7 imports no longer needed)

### api/routes/export.py (~165 lines, entire file removable)

- The entire export route serves only old debate data. After migration,
  `export_debate_markdown()` is no longer needed from the API.
- Lines 1-194: Full file — reconstructs `DebateResult` from `ai_theses` row,
  calls `export_debate_markdown()`

### models/analysis.py (~350 lines of old thesis classes)

- Lines 494-529: `AgentResponse` class (36 lines)
- Lines 531-616: `TradeThesis` class (86 lines)
- Lines 619-663: `VolatilityThesis` class (45 lines)
- Lines 666-694: `FlowThesis` class (29 lines)
- Lines 697-739: `RiskAssessment` class (43 lines)
- Lines 742-771: `FundamentalThesis` class (30 lines)
- Lines 774-801: `ContrarianThesis` class (28 lines)
- Lines 804-846: `ExtendedTradeThesis` class (43 lines)
- Note: `MarketContext` (lines 58-492) stays -- used by the recommendation system

### reporting/debate_export.py (~260 lines of old debate renderers)

- Lines 39-74: `_render_agent_section()` (36 lines)
- Lines 77-101: `_render_vol_section()` (25 lines)
- Lines 104-134: `_render_flow_section()` (31 lines)
- Lines 137-173: `_render_fundamental_section()` (37 lines)
- Lines 176-219: `_render_risk_section()` (44 lines)
- Lines 222-250: `_render_contrarian_section()` (29 lines)
- Lines 336-461: `export_debate_markdown()` (126 lines)
- Lines 733-757: `export_debate_to_file()` (25 lines)
- Note: `_render_market_snapshot()`, `_render_spread_section()`,
  `export_recommendation_markdown()` and recommendation rendering functions stay

### agents/_parsing.py (~25 lines)

- Lines 132-156: `DebateResult` class definition
- Note: `strip_think_tags`, `PROMPT_RULES_APPENDIX`, `render_*_context()`,
  `compute_citation_density()` stay -- used by recommendation system

### agents/_context.py (~105 lines)

- Lines 485-589: `extract_agent_predictions()` -- only operates on `DebateResult`
- Note: `build_market_context()`, `classify_macd_signal()`, `should_recommend()`,
  `_build_model_settings()`, `effective_batch_ticker_delay()`, `DebatePhase` stay

### data/_debate.py (partial)

- `DebateRow` dataclass (lines 32-59)
- `save_debate()` method
- `get_debate_by_id()`, `get_recent_debates()`, `get_debates_for_ticker()` methods
- `save_agent_predictions()` that accept `debate_id` referencing ai_theses
- Note: Agent calibration queries, auto-tune weights, weight history stay (they
  reference `agent_predictions` table, not `ai_theses` directly)

### Total estimate: ~907 lines removable

---

## 6. Prerequisites Before Execution

1. **No active users relying on old debate IDs**: The frontend `DebateResultPage.vue` must
   be fully adapted to display `RecommendationResponse` format only. Currently it supports
   dual rendering (old `DebateResultDetail` + new `RecommendationResponse`).

2. **Data migration script tested**: Run `tools/migrate_theses.py` against a production DB
   copy. Verify row counts match. Spot-check 10+ rows for field accuracy.

3. **Verification queries**: Run the verification suite in the migration script to confirm
   all rows migrated successfully before dropping `ai_theses`.

4. **Frontend adaptation**: Remove `DebateResultDetail` rendering path from
   `DebateResultPage.vue`. Only render `RecommendationResponse`.

5. **Export route migration**: Add recommendation export endpoint that uses
   `export_recommendation_markdown()` (already exists in `reporting/debate_export.py`).

6. **Agent predictions migration**: Any `agent_predictions` rows referencing `ai_theses`
   debate IDs need to be re-linked or archived. The `recommendation_protocol` column
   (added in migration 037) can distinguish old vs new records.

7. **Backup**: Full SQLite backup before running migration.

---

## 7. Rollback Plan

### Before ai_theses DROP

1. The migration script creates a `_migration_id_map` temporary table mapping
   `old_thesis_id -> new_recommendation_id`.
2. If verification fails, delete all `recommendation_results` rows that came from
   migration (identified by `position_rationale = 'Migrated from legacy debate system'`).
3. The `ai_theses` table is untouched until explicit DROP.

### After ai_theses DROP

1. Restore from SQLite backup taken in prerequisite step 7.
2. Re-run migrations to current version.

### Code Rollback

1. All code removal is in a single commit/PR. Revert the commit to restore dual-table
   lookup and old model classes.
2. The `ai_theses` table schema is defined across 8 migrations -- these are never removed
   from the `data/migrations/` directory. A new empty DB will still create the table.

---

## 8. Migration Sequence

```
Phase 1: Data Migration (this plan)
  1. Back up production SQLite database
  2. Run tools/migrate_theses.py --dry-run to preview
  3. Run tools/migrate_theses.py to execute
  4. Run tools/migrate_theses.py --verify to validate
  5. Manual spot-check of migrated data

Phase 2: Code Cleanup (separate PR after Phase 1 verified)
  1. Remove old thesis model classes from models/analysis.py
  2. Remove export.py route entirely
  3. Remove dual-table lookup from debate.py
  4. Remove DebateResult from _parsing.py
  5. Remove extract_agent_predictions from _context.py
  6. Remove DebateRow and old debate CRUD from _debate.py
  7. Remove old debate renderers from reporting/debate_export.py
  8. Update __init__.py re-exports in all affected packages
  9. Update tests to remove old-format test cases

Phase 3: Schema Cleanup (separate migration after Phase 2 deployed)
  1. New migration: DROP TABLE ai_theses
  2. Remove _migration_id_map if created
```
