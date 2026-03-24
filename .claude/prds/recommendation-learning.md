---
name: recommendation-learning
description: Prediction ledger + emergent regime learning to make recommendations smarter over time
status: planned
created: 2026-03-23T23:18:05Z
---

# PRD: recommendation-learning

## Executive Summary

Add a prediction ledger that records every intermediate decision in the recommendation
pipeline (scan direction, per-desk direction calls, contract selection parameters), scores
them against outcomes, and feeds accuracy data back into the existing learning infrastructure.
Market regime awareness emerges from enriched strategy mining dimensions rather than
hand-coded classification. The system gets smarter over time with human approval gates on
all weight and pattern changes.

## Problem Statement

### What problem are we solving?

The system evaluates only the final output (recommendation P&L) but cannot attribute success
or failure to specific intermediate decisions. When a recommendation is wrong, there is no
way to determine whether the scan pipeline called direction incorrectly, a specific desk gave
bad advice, or the contract selection parameters were suboptimal. Without this attribution,
weight tuning and strategy mining operate on noisy aggregate signals instead of precise
per-decision accuracy.

### Why is this important now?

v3.0 is complete with all infrastructure in place: outcome tracking at T+1/T+5/T+10/T+20,
weight tuning (indicator + vote), strategy mining with playbook, confidence decay, and
prompt injection. The system has some historical outcome data but not yet enough to have
self-corrected meaningfully. This is the right time to add the sensor layer (prediction
recording) before accumulating more data, so every future recommendation contributes to
the learning loop.

## User Stories

### US-1: See what's working
**As a user**, I want to run `learn attribution` and see which decision points (scan
direction, each desk, contract selection) are accurate and which are not, so I can
understand where the system is strong and weak.
**Acceptance criteria**: Attribution report shows accuracy % per prediction source, with
sample counts. No results shown for sources with < 10 outcomes.

### US-2: See what's working in different conditions
**As a user**, I want attribution accuracy sliced by market conditions (ADX strength,
IV rank, volatility level) so I can understand when the system works well vs. poorly.
**Acceptance criteria**: Report shows accuracy per source per condition bucket. Only
buckets with >= 20 samples are shown.

### US-3: Approve smarter weights
**As a user**, I want `learn tune-votes` to propose desk vote weight changes based on
per-desk accuracy data (not just overall agent accuracy), with my approval required before
changes take effect.
**Acceptance criteria**: Proposed weights shown with current vs. proposed, change %, and
reason. Changes only applied after explicit user confirmation.

### US-4: Discover condition-specific patterns
**As a user**, I want strategy mining to discover patterns that include market condition
dimensions (e.g., "Trend desk is 89% accurate when ADX > 25 and IV Rank < 30") and inject
them into agent prompts after my approval.
**Acceptance criteria**: Mined patterns include condition dimensions. Chi-squared
significance test (p < 0.05) and minimum sample thresholds enforced. Approved patterns
rendered in `<<<LEARNED_PATTERNS>>>` block.

### US-5: Get contract selection guidance
**As a user**, I want the system to learn which delta ranges and DTE ranges produce the
best outcomes and feed that back into the synthesis agent's contract selection.
**Acceptance criteria**: `<<<CONTRACT_GUIDANCE>>>` block injected into synthesis prompt
showing optimal delta/DTE ranges based on outcome data. Only shown when sufficient data
exists (>= 30 outcomes).

### US-6: Automatic prediction scoring
**As a user**, I want `outcomes collect` to automatically score all predictions associated
with collected outcomes, so I don't need a separate step.
**Acceptance criteria**: After outcome collection, all predictions for that recommendation
are marked `was_correct`. No additional user action required.

## Architecture & Design

### Chosen Approach

**Prediction Ledger with Emergent Regime** — a single prediction recording pattern for all
decision points, with market regime awareness emerging from enriched strategy mining
dimensions rather than a hand-coded regime classifier.

**Rationale**: The system already has weight tuning, strategy mining, confidence decay, and
prompt injection. The only missing piece is the sensor layer (recording intermediate
predictions). Adding one table and one scorer, then feeding data into existing infrastructure,
is far simpler than building separate tracking systems for each pipeline layer.

### Module Changes

| Module | Changes |
|--------|---------|
| `learning/` | New `prediction_ledger.py` (~400-500 lines). Enhanced `strategy_book.py` with condition dimensions. Enhanced `weight_tuner.py` to accept per-desk accuracy from predictions. |
| `models/` | New `PredictionSource` StrEnum, `Prediction` model, `PredictionAccuracy` report model in `attribution.py` (~100 lines) |
| `data/` | New `LearningMixin` methods for prediction CRUD + accuracy queries. 1-2 new migrations (predictions table + indexes) |
| `agents/` | `recommendation_orchestrator.py` — persist `Prediction` per desk after assessments. Inject `<<<CONTRACT_GUIDANCE>>>` block into synthesis |
| `scan/` | Phase 2 — persist `Prediction` for direction determination with context snapshot |
| `cli/` | New `learn attribution` subcommand. Enhanced `learn tune-votes` output |
| `api/` | New `GET /api/analytics/attribution` endpoint |

### Data Models

```python
# models/attribution.py

class PredictionSource(StrEnum):
    """Decision point that produced a prediction."""
    SCAN_DIRECTION = "scan_direction"
    DESK_TREND = "desk_trend"
    DESK_VOLATILITY = "desk_volatility"
    DESK_FLOW = "desk_flow"
    DESK_FUNDAMENTAL = "desk_fundamental"
    DESK_RISK = "desk_risk"
    DESK_CONTRARIAN = "desk_contrarian"
    DESK_RESEARCH = "desk_research"
    SYNTHESIS = "synthesis"

class Prediction(BaseModel, frozen=True):
    """An intermediate decision that can be scored against reality."""
    id: int
    recommendation_id: int | None = None  # None for scan-phase predictions
    scan_run_id: int | None = None        # set for scan-phase predictions
    ticker: str
    source: PredictionSource
    predicted_direction: SignalDirection
    confidence: float  # 0.0-1.0, isfinite + range validated
    # Key indicator values at decision time for dimensional slicing
    adx: float | None = None
    iv_rank: float | None = None
    atr_pct: float | None = None
    rsi: float | None = None
    # Filled after outcome collection
    was_correct: bool | None = None

    # Validators: isfinite() before range check on confidence
    # model_validator: at least one of recommendation_id or scan_run_id must be set

class PredictionAccuracy(BaseModel, frozen=True):
    """Accuracy stats for a prediction source."""
    source: PredictionSource
    total: int
    correct: int
    accuracy: float  # correct / total
    sample_sufficient: bool  # total >= minimum threshold

class ConditionBucketAccuracy(BaseModel, frozen=True):
    """Accuracy for a source within a condition bucket."""
    source: PredictionSource
    condition: str  # e.g. "adx_strong", "iv_rank_low"
    total: int
    correct: int
    accuracy: float

class ContractGuidance(BaseModel, frozen=True):
    """Learned optimal contract parameters."""
    optimal_delta_low: float
    optimal_delta_high: float
    optimal_dte_low: int
    optimal_dte_high: int
    delta_win_rate: float
    dte_win_rate: float
    sample_count: int

class AttributionReport(BaseModel, frozen=True):
    """Full attribution output."""
    window_days: int
    total_recommendations: int
    total_outcomes: int
    source_accuracy: list[PredictionAccuracy]
    condition_accuracy: list[ConditionBucketAccuracy]
    contract_guidance: ContractGuidance | None
```

### Core Logic

#### Prediction Recording

**Scan pipeline** (Phase 2): After `determine_direction()`, create a `Prediction` with
`source=SCAN_DIRECTION`, the predicted direction, and a context snapshot of ADX, IV Rank,
ATR%, RSI from the just-computed `IndicatorSignals`.

**Recommendation orchestrator**: After each desk returns `DomainAssessment`, create a
`Prediction` with `source=DESK_*`, the desk's direction call, confidence, and the same
context snapshot from `MarketContext`.

**Synthesis**: After synthesis agent returns `PositionRecommendation`, create a `Prediction`
with `source=SYNTHESIS` and the final direction.

All predictions persisted in a single `predictions` DB table.

#### Prediction Scoring

Triggered automatically during `outcomes collect`. Two paths:

**Desk/synthesis predictions** (have `recommendation_id`):
1. Determine actual direction from price movement (positive P&L = direction was correct)
2. Update all `Prediction` rows for that `recommendation_id`: set `was_correct`

**Scan direction predictions** (have `scan_run_id` + `ticker`):
1. Link via ticker: find the outcome's ticker, match to scan predictions for the same ticker
2. Use the same direction-correctness logic
3. If a ticker was scanned but never recommended, scan predictions remain unscored (expected)

Both paths use a single batch commit at the end of outcome collection.

#### Attribution Analysis

`learning/prediction_ledger.py` provides:
- `compute_attribution(predictions: list[Prediction]) -> AttributionReport`
- Groups predictions by source, computes accuracy
- Groups by source × condition bucket (ADX bucket, IV Rank bucket, etc.), computes accuracy
- Minimum sample thresholds (10 for source-level, 20 for condition-level)
- Returns typed `AttributionReport`

#### Strategy Mining Enhancement

Extend `OutcomeWithContext` to include the condition dimensions (ADX bucket, IV Rank bucket,
volatility bucket). The existing `mine_patterns()` → `filter_significant()` →
`generate_rules()` pipeline handles the rest — significance testing, minimum samples,
rule generation, prompt rendering. Regime awareness emerges from the mined patterns.

#### Contract Guidance

New function: `compute_contract_guidance(outcomes) -> ContractGuidance | None`
- Bucket outcomes by delta range (0.10 increments) and DTE range (15-day increments)
- Find ranges with highest win rate and sufficient samples (>= 30)
- Return as `ContractGuidance` or `None` if insufficient data
- Rendered as `<<<CONTRACT_GUIDANCE>>>` block in synthesis prompt

#### Enhanced Weight Tuning

`compute_auto_tune_weights()` currently takes `list[AgentAccuracyReport]`. Enhance to
accept prediction-derived accuracy per desk. No interface change needed — just better
input data from the predictions table instead of the current coarser accuracy query.

### Database Schema

```sql
-- New table
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER REFERENCES recommendation_results(id),  -- NULL for scan-phase
    scan_run_id INTEGER REFERENCES scan_runs(id),                     -- NULL for desk-phase
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,           -- PredictionSource value
    predicted_direction TEXT NOT NULL,  -- SignalDirection value
    confidence REAL NOT NULL,
    adx REAL,
    iv_rank REAL,
    atr_pct REAL,
    rsi REAL,
    was_correct INTEGER,           -- NULL until scored, 0 or 1
    created_at TEXT NOT NULL,
    -- At least one FK must be set (enforced in application layer)
    UNIQUE(recommendation_id, source),
    UNIQUE(scan_run_id, ticker, source)
);

CREATE INDEX idx_predictions_source ON predictions(source);
CREATE INDEX idx_predictions_was_correct ON predictions(was_correct) WHERE was_correct IS NOT NULL;
CREATE INDEX idx_predictions_rec_id ON predictions(recommendation_id) WHERE recommendation_id IS NOT NULL;
CREATE INDEX idx_predictions_scan_id ON predictions(scan_run_id) WHERE scan_run_id IS NOT NULL;
CREATE INDEX idx_predictions_ticker ON predictions(ticker);
```

## Requirements

### Functional Requirements

1. Every recommendation persists one `Prediction` per desk + one for scan direction + one for synthesis
2. `outcomes collect` automatically scores predictions — no separate command
3. `learn attribution` displays per-source accuracy with condition bucketing
4. `learn tune-votes` uses prediction-derived accuracy (not just overall agent accuracy)
5. Strategy mining includes ADX/volatility condition dimensions
6. `<<<CONTRACT_GUIDANCE>>>` block injected into synthesis prompt when sufficient data exists
7. All weight changes and pattern approvals require human confirmation
8. Minimum sample thresholds enforced everywhere (10 source-level, 20 condition-level, 30 contract guidance)

### Non-Functional Requirements

1. Prediction recording adds < 50ms to recommendation pipeline (simple INSERT)
2. Scoring adds < 100ms to outcome collection (batch UPDATE)
3. Attribution report computes in < 2s for 1,000 predictions
4. No new external dependencies — uses existing `aiosqlite`, `statistics`, `math`
5. All new code follows never-raises contract for orchestration functions
6. All float fields use `isfinite()` guards before range checks

## API / CLI Surface

### CLI

| Command | Purpose |
|---------|---------|
| `learn attribution [--window-days 90]` | Full attribution report: per-source accuracy + condition slicing |
| `learn attribution --source desk_trend` | Filter to a single prediction source |

### API

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/analytics/attribution` | GET | `AttributionReport` |
| `/api/analytics/attribution?source=desk_trend` | GET | Filtered `AttributionReport` |

### Enhanced Existing Commands

| Command | Enhancement |
|---------|-------------|
| `outcomes collect` | Now also scores predictions automatically |
| `learn tune-votes` | Shows prediction-derived per-desk accuracy as basis for proposals |
| `learn mine` | Mines with condition dimensions (ADX bucket, IV bucket, vol bucket) |
| `learn playbook` | Displays patterns that include condition-based rules |

## Testing Strategy

### Unit Tests (~60-70 new tests)

- **Prediction model**: Validation (confidence range, isfinite guards, source enum)
- **Scoring**: Parametrized correct/incorrect marking based on direction vs. actual P&L
- **Attribution**: Accuracy computation, condition bucketing, minimum sample thresholds, empty data
- **Contract guidance**: Delta/DTE bucketing, optimal range selection, insufficient data returns None
- **Strategy mining extension**: Condition dimensions flow through mine → filter → generate → render
- **NaN/Inf defense**: Non-finite confidence, non-finite indicator values in context snapshot

### Integration Tests (~10-15 new tests)

- Full loop: recommend → persist predictions → collect outcome → score → attribution
- Weight tuning with prediction data: verify improved accuracy input
- Strategy mining with condition dimensions: verify new patterns include conditions
- Cold start: zero predictions → attribution returns empty report, no crash
- Contract guidance with insufficient data → `None`, no prompt block injected

### Edge Cases

- Desk returns fallback assessment (LLM failure) → prediction recorded with `confidence=0.2`, included in accuracy but flagged
- All desks agree but wrong → all marked incorrect, system-level signal
- Recommendation has no outcome yet → predictions exist with `was_correct=None`, excluded from attribution
- Context snapshot has `None` indicator values → excluded from condition bucketing for that dimension
- Duplicate scoring (outcomes collected twice) → UNIQUE constraint prevents duplicate predictions, scoring is idempotent

### Migration Tests

- `predictions` table created with correct schema
- Indexes created
- Existing data unaffected
- Foreign key to `recommendations` enforced

## Success Criteria

1. After 100+ scored predictions, `learn attribution` shows statistically meaningful accuracy differences between desks
2. After 200+ scored predictions with condition data, strategy mining discovers condition-specific patterns that were not visible before
3. `learn tune-votes` proposals based on prediction accuracy produce measurably different weights than the current overall-accuracy approach
4. Direction accuracy (scan pipeline) is tracked independently from recommendation P&L, enabling targeted indicator weight tuning
5. User can answer "why was this recommendation wrong?" by checking which decision points were incorrect

## Constraints & Assumptions

- Requires existing outcome collection to be running (`outcomes collect`) — predictions are only valuable once scored
- Minimum ~100 scored recommendations before attribution is statistically useful
- Context snapshot captures only 4 key indicators (ADX, IV Rank, ATR%, RSI) — not all 27, to keep the table lean. More can be added later if needed
- Condition bucketing uses simple thresholds (ADX: <20/20-30/>30, IV Rank: <30/30-70/>70, etc.) — not dynamic clustering
- Contract guidance is advisory (prompt injection) not prescriptive (doesn't override `OptionsFilters` defaults)

## Out of Scope

- **Explicit regime classifier** — regime awareness emerges from strategy mining dimensions instead
- **A/B testing** — parallel recommendation paths with different weights/prompts. Future PRD if needed after this proves value
- **New external data sources** — earnings, unusual flow, cross-asset. Future PRD once attribution identifies specific signal gaps
- **User feedback UI** — thumbs up/down on recommendations. Can be layered on as a `PredictionSource` later
- **Automated scheduling** — running `outcomes collect` and `learn attribution` on a cron. Manual for now
- **Web UI for attribution** — API endpoint provided, frontend visualization is a separate task

## Dependencies

- **Internal**: Existing outcome collection pipeline, weight tuner, strategy mining, synthesis prompt injection
- **External**: None — uses only existing dependencies (aiosqlite, statistics, math)
- **Data**: Requires `recommendation_results` table (migration 037) and `scan_runs` table. New migration adds `predictions` table
