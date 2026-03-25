---
name: intel-wave3-delta-engine
description: Intelligence collector orchestrator, declarative delta engine with metric table, and SQLite persistence layer
status: backlog
created: 2026-03-24T15:48:29Z
updated: 2026-03-25T14:31:33Z
effort: L
---

# PRD: intel-wave3-delta-engine

## Executive Summary

Build the intelligence data pipeline: an orchestrator that fetches all 8 data sources in parallel (`IntelligenceCollector`), a stateless change detection engine that compares consecutive snapshots using a declarative metric table (`DeltaEngine`), and SQLite persistence for snapshots, delta reports, and alert history. The delta engine uses a single `METRIC_TABLE` as the source of truth for all ~23 tracked metrics — adding a metric requires adding one line, not touching config or engine logic.

## Problem Statement

### What problem are we solving?

Individual data source services (Wave 2) produce isolated snapshots. Without an orchestrator to aggregate them and a delta engine to detect meaningful changes, the data has no context. "VIX is 22" is less useful than "VIX jumped 18% since your last scan — market shifted from risk-on to risk-off." The delta engine is what makes intelligence *actionable*.

### Why is this important now?

Wave 3 is the computational backbone. The alert system (Wave 4) evaluates delta reports. The intelligence desk agent (Wave 5) consumes snapshots and deltas. Without this layer, Waves 4-7 have no data to work with.

### Architecture Decision: Declarative Metric Table

Three approaches were evaluated:

- **A) Explicit lambda registry**: Each metric has a hand-written extractor + a dedicated `DeltaConfig` threshold field. Results in 20+ config fields, 3 touch-points per metric addition. Rejected: config explosion.
- **B) Reflection-based auto-discovery**: Walk model fields automatically. Rejected: no control over which metrics matter, can't assign categories or risk polarity.
- **C) Declarative metric table** (chosen): A single `METRIC_TABLE` tuple defines path, category, display name, default threshold, and risk polarity per metric. The engine is a generic loop. `DeltaConfig` stays lean (2 fields: `sensitivity` multiplier + `threshold_overrides` dict). Adding a metric = one line.

Crucix's `lib/delta/engine.mjs` uses the same pattern — a `METRICS` array with threshold/polarity per entry. This confirms the approach works in production.

## Requirements

### Functional Requirements

#### FR-1: Intelligence Collector (`services/intelligence_collector.py`)

Coordinator class (NOT a ServiceBase subclass — same pattern as ScanPipeline).

```python
class IntelligenceCollector:
    def __init__(
        self,
        *,
        gdelt: GdeltService,
        eia: EiaService,
        bls: BlsService,
        gscpi: GscpiService,
        treasury: TreasuryFiscalService,
        fred: FredService,
        comtrade: ComtradeService,
        usaspending: UsaSpendingService,
        config: IntelligenceConfig,
    ) -> None: ...
    async def collect_snapshot(
        self, ticker: str | None = None, company_name: str | None = None,
    ) -> IntelligenceSnapshot: ...
    async def close(self) -> None: ...
```

- Receives 8 individual service instances via DI (constructor injection, all typed)
- `collect_snapshot()`:
  1. Builds task list — only includes services where `config.enabled` for that source
  2. Fetches all enabled sources in parallel via `asyncio.gather(*tasks, return_exceptions=True)`
  3. Maps results to `IntelligenceSnapshot` 8 source fields (exception per source → None for that field)
  4. Entire call wrapped in `asyncio.wait_for(coro, timeout=config.fetch_timeout)`
  5. Total failure → `IntelligenceSnapshot.fallback()`
- Optional `ticker`/`company_name` params for ticker-specific GDELT queries
- Follows never-raises contract: catches all exceptions, logs WARNING, returns fallback
- `close()` closes all non-None sub-services

#### FR-2: Delta Engine (`services/delta.py`)

Stateless computation class — compares two `IntelligenceSnapshot`s using a declarative metric table.

##### MetricDef and METRIC_TABLE

Engine-internal types (NOT in `models/` — these are implementation detail of `services/delta.py`):

```python
class MetricDef(NamedTuple):
    path: str                       # dotted path into IntelligenceSnapshot, e.g. "macro.vix"
    category: IntelligenceCategory  # for MetricDelta.category
    display_name: str               # human-readable label
    threshold_pct: float            # default % change threshold
    risk_polarity: RiskPolarity     # UP_RISK_OFF, UP_RISK_ON, or NEUTRAL
```

**The metric table** — single source of truth for all tracked metrics (~23 entries):

```python
METRIC_TABLE: tuple[MetricDef, ...] = (
    # ── VIX & Volatility ─────────────────────────────────────────
    MetricDef("macro.vix",                      VIX,            "VIX",                      5.0,  UP_RISK_OFF),
    # ── Credit ────────────────────────────────────────────────────
    MetricDef("macro.hy_credit_spread",         CREDIT_SPREADS, "HY Credit Spread (OAS)",   5.0,  UP_RISK_OFF),
    # ── Energy ────────────────────────────────────────────────────
    MetricDef("energy.wti.value",               ENERGY,         "WTI Crude",                3.0,  NEUTRAL),
    MetricDef("energy.brent.value",             ENERGY,         "Brent Crude",              3.0,  NEUTRAL),
    MetricDef("energy.natgas.value",            ENERGY,         "Natural Gas",              3.0,  NEUTRAL),
    # ── Yield Curve ───────────────────────────────────────────────
    MetricDef("macro.yield_spread_10y2y",       YIELD_CURVE,    "10Y-2Y Spread",            10.0, UP_RISK_ON),
    MetricDef("macro.treasury_30y",             YIELD_CURVE,    "30Y Treasury",             5.0,  NEUTRAL),
    MetricDef("macro.treasury_10y",             YIELD_CURVE,    "10Y Treasury",             5.0,  NEUTRAL),
    # ── Supply Chain ──────────────────────────────────────────────
    MetricDef("supply_chain.current_value",     SUPPLY_CHAIN,   "GSCPI",                    10.0, UP_RISK_OFF),
    # ── Fiscal ────────────────────────────────────────────────────
    MetricDef("fiscal.total_debt",              FISCAL,         "National Debt",            1.0,  NEUTRAL),
    MetricDef("fiscal.avg_interest_rate",       FISCAL,         "Avg Treasury Rate",        5.0,  UP_RISK_OFF),
    MetricDef("fiscal.daily_statement.closing_balance", FISCAL, "Treasury Cash Balance",    20.0, NEUTRAL),
    # ── Trade ─────────────────────────────────────────────────────
    MetricDef("trade.us_china_semiconductor",   TRADE,          "US-China Semiconductors",  15.0, NEUTRAL),
    MetricDef("trade.us_china_energy",          TRADE,          "US-China Energy Trade",    15.0, NEUTRAL),
    # ── Defense ───────────────────────────────────────────────────
    MetricDef("defense.total_value",            DEFENSE,        "Defense Contract Spending", 20.0, NEUTRAL),
    # ── Labor ─────────────────────────────────────────────────────
    MetricDef("macro.initial_claims",           LABOR,          "Initial Jobless Claims",   10.0, UP_RISK_OFF),
    # ── Monetary ──────────────────────────────────────────────────
    MetricDef("macro.m2_yoy",                   MONETARY,       "M2 Money Supply YoY",      5.0,  UP_RISK_ON),
    MetricDef("macro.fed_balance_sheet",        MONETARY,       "Fed Balance Sheet",        3.0,  NEUTRAL),
    MetricDef("macro.mortgage_30y",             MONETARY,       "30Y Mortgage Rate",        5.0,  UP_RISK_OFF),
    # ── Inflation ─────────────────────────────────────────────────
    MetricDef("macro.core_pce_yoy",             INFLATION,      "Core PCE YoY",             5.0,  UP_RISK_OFF),
    MetricDef("macro.michigan_expectations",    INFLATION,      "Michigan Inflation Exp",   10.0, UP_RISK_OFF),
    # ── Safe Haven ────────────────────────────────────────────────
    MetricDef("macro.gold_price",               SAFE_HAVEN,     "Gold",                     3.0,  UP_RISK_OFF),
    # ── FX ────────────────────────────────────────────────────────
    MetricDef("macro.usd_index",                FX,             "USD Trade-Weighted Index",  2.0, UP_RISK_OFF),
)
```

Note: The `path` values must match the field names on `IntelligenceSnapshot` and its nested models exactly. The `macro` prefix resolves to `snapshot.macro` which is a `MacroContext` instance. Field names like `hy_credit_spread`, `initial_claims`, etc. must match the new fields added to `MacroContext` in Wave 2 FR-6.

##### DeltaEngine class

```python
class DeltaEngine:
    def __init__(self, config: DeltaConfig): ...
    def compute_delta(self, previous: IntelligenceSnapshot,
                       current: IntelligenceSnapshot) -> DeltaReport: ...
```

**`compute_delta()` flow:**
1. `_compare_numeric(previous, current)` → iterate `METRIC_TABLE`, resolve paths, compute % change, filter by threshold, classify severity
2. `_compare_counts(previous, current)` → compare count-based metrics. GDELT per-category counts are computed on-the-fly by grouping `snapshot.gdelt.articles` on `GdeltArticle.category` (not stored as fields on `GdeltSnapshot`). Defense contract count from `len(snapshot.defense.contracts)`. Total: 5 GDELT category counts + 1 defense count = 6 count metrics. Count metrics have no threshold — any absolute change ≥ 2 emitted at MODERATE.
3. `_compute_direction(numeric_deltas)` → tally risk-off vs risk-on using `RiskPolarity` annotations: `risk_off > risk_on + 1 → RISK_OFF`, `risk_on > risk_off + 1 → RISK_ON`, else `MIXED`
4. `_assemble_report(all_deltas, previous, current, direction)` → build `DeltaReport` with severity counts and summary text

##### Helper functions

**`_resolve_path(obj, path) -> float | None`** — generic dotted-path traversal with None safety:
```python
def _resolve_path(obj: object, path: str) -> float | None:
    for part in path.split("."):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj if isinstance(obj, (int, float)) and math.isfinite(obj) else None
```

**`_effective_threshold(config, defn) -> float`** — applies config overrides + sensitivity multiplier:
```python
def _effective_threshold(self, defn: MetricDef) -> float:
    override = self._config.threshold_overrides.get(defn.path)
    base = override if override is not None else defn.threshold_pct
    return base * self._config.sensitivity
```

**`_pct_change(prev, curr) -> float`** — standard % change with zero-division guard:
```python
def _pct_change(prev: float, curr: float) -> float:
    if prev == 0.0:
        return float("nan")  # division by zero → NaN, caller skips
    return (curr - prev) / abs(prev) * 100.0
```

##### Severity mapping

- `|change| > threshold × 3` → CRITICAL
- `|change| > threshold × 2` → HIGH
- `|change| > threshold × 1` → MODERATE
- Below threshold → not emitted

##### Text signal dedup

For GDELT article comparison between snapshots:
- Normalize text: lowercase, strip timestamps/numbers
- Jaccard word-level similarity > 0.7 → duplicate, skip

#### FR-3: SQLite Persistence (`data/migrations/042_intelligence.sql`)

```sql
-- Note: legacy intelligence_snapshots from migration 010 was already dropped by
-- migration 024 (drop_dead_artifacts.sql). These DROPs are safe no-ops (IF EXISTS)
-- included for clarity and idempotency.
DROP TABLE IF EXISTS intelligence_snapshots;
DROP INDEX IF EXISTS idx_intelligence_ticker_category;
DROP INDEX IF EXISTS idx_intelligence_fetched_at;

-- Global intelligence snapshots (one per collection cycle)
CREATE TABLE IF NOT EXISTS intelligence_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    completeness REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_intel_snap_captured_at
    ON intelligence_snapshots(captured_at);

-- Delta reports
CREATE TABLE IF NOT EXISTS delta_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prev_snapshot_id INTEGER NOT NULL REFERENCES intelligence_snapshots(id) ON DELETE CASCADE,
    curr_snapshot_id INTEGER NOT NULL REFERENCES intelligence_snapshots(id) ON DELETE CASCADE,
    computed_at TEXT NOT NULL,
    direction TEXT NOT NULL,
    critical_count INTEGER NOT NULL DEFAULT 0,
    high_count INTEGER NOT NULL DEFAULT 0,
    moderate_count INTEGER NOT NULL DEFAULT 0,
    deltas_json TEXT NOT NULL,
    summary TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delta_computed_at
    ON delta_reports(computed_at);

-- Alert history (schema created here for migration ordering, logic in Wave 4)
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    source_delta_id INTEGER REFERENCES delta_reports(id) ON DELETE SET NULL,
    fingerprint TEXT NOT NULL,
    cooldown_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_fingerprint ON alert_history(fingerprint);
CREATE INDEX IF NOT EXISTS idx_alert_created_at ON alert_history(created_at);
CREATE INDEX IF NOT EXISTS idx_alert_status ON alert_history(status);
```

#### FR-4: Repository Mixin (`data/_intelligence.py`)

```python
class IntelligenceMixin(RepositoryBase):
    async def save_intelligence_snapshot(self, snapshot: IntelligenceSnapshot) -> int
    async def get_latest_snapshot(self) -> IntelligenceSnapshot | None
    async def get_snapshots_since(self, since: datetime, limit: int = 48) -> list[IntelligenceSnapshot]
    async def save_delta_report(self, report: DeltaReport) -> int
    async def get_latest_delta(self) -> DeltaReport | None
    async def save_alert(self, alert: AlertRecord) -> int
    async def get_alerts(self, *, tier: AlertTier | None = None,
                         status: AlertStatus | None = None, limit: int = 50) -> list[AlertRecord]
    async def acknowledge_alert(self, alert_id: int) -> None
    async def get_alert_count_since(self, fingerprint: str, since: datetime) -> int
    async def cleanup_old_snapshots(self, retention_days: int) -> int
```

- Add `IntelligenceMixin` to `Repository` class MRO in `data/repository.py`, after `LearningMixin` (last position): `Repository(ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin, SpreadsMixin, AgencyMixin, RecommendationMixin, LearningMixin, IntelligenceMixin)`
- All methods return typed Pydantic models, never raw dicts
- Parameterized SQL queries (no injection)
- `await db.commit()` after every write
- Snapshot serialization via `model_dump_json()` / `model_validate_json()`
- `cleanup_old_snapshots` deletes snapshots older than `retention_days`, returns count of deleted rows. Cascades: also deletes delta_reports referencing deleted snapshots (via FK with ON DELETE CASCADE — add to CREATE TABLE).

### Non-Functional Requirements

- `DeltaEngine.compute_delta()` is a pure function (no I/O) — testable without mocking
- `IntelligenceCollector` follows never-raises contract
- All repository methods return typed Pydantic models
- Parameterized SQL queries (no injection)
- `await db.commit()` after every write
- Snapshot JSON uses `model_dump_json()` / `model_validate_json()` for serialization
- `_resolve_path()` rejects non-finite values via `math.isfinite()` (NaN/Inf defense)
- `_pct_change()` returns `float("nan")` for zero-division (caller skips NaN results)

## Wave 1 Impact (Must Update Before Wave 3)

The following amendments to Wave 1 (`intel-wave1-foundation`) are required:

| File | Change |
|------|--------|
| `models/enums.py` | Expand `IntelligenceCategory` from 8 → 14 values: add `trade`, `defense`, `monetary`, `inflation`, `safe_haven`, `fx`. These ensure delta reports group metrics under semantically correct headings. |
| `models/enums.py` | Add `RiskPolarity` StrEnum with values: `up_risk_off`, `up_risk_on`, `neutral` |
| `models/config.py` | Replace `DeltaConfig` — remove 5 individual threshold fields, replace with `sensitivity: float = 1.0` and `threshold_overrides: dict[str, float] = {}`. Note: `threshold_overrides` is `dict[str, float]` — this is config input (env var override map), not domain data, so it is exempt from the no-raw-dicts rule. |

## Success Criteria

- Delta engine unit tests: parametrized over `METRIC_TABLE` — threshold crossings at exactly 1×, 2×, 3× produce correct severity
- Direction logic works for all 3 cases (RISK_ON, RISK_OFF, MIXED)
- Sensitivity multiplier: `sensitivity=0.5` doubles effective sensitivity
- Threshold overrides: override one metric via `threshold_overrides`, verify others use defaults
- `_resolve_path` handles None at each level, non-finite values, nested paths (3+ levels)
- **Path coverage test**: iterate all `METRIC_TABLE` paths against a fully-populated `IntelligenceSnapshot` fixture (all source fields + MacroContext non-None) and assert every path resolves to a non-None value. This validates that `METRIC_TABLE` paths stay in sync with model field names.
- `_pct_change` returns NaN for zero previous value (no division-by-zero crash)
- Count metrics: GDELT category changes, defense contract count
- Text dedup catches near-duplicates (Jaccard > 0.7)
- Collector tests: partial failure (1-7 sources down) → partial snapshot, total failure → fallback
- Disabled services not called by collector
- Repository tests: save/get roundtrip, cleanup removes old data
- Migration 042 drops legacy 010 table
- `uv run mypy src/ --strict` passes
- `uv run ruff check . --fix && uv run ruff format .` passes
- `uv run pytest -m "not exhaustive" -n auto -q` passes

## Out of Scope

- Alert evaluation logic (Wave 4) — `alert_history` table created here but not written to by Wave 3
- Agent consumption of delta data (Wave 5)
- API endpoints for intelligence data (Wave 7)
- Frontend display of intelligence/deltas (Wave 7)

## Constraints & Assumptions

- `DeltaEngine` is stateless — no persistence, no I/O, no side effects
- `IntelligenceCollector` is NOT a `ServiceBase` subclass — it's an orchestrator (same pattern as `ScanPipeline`)
- `MetricDef` and `METRIC_TABLE` are engine-internal — NOT in `models/`. They are implementation detail of `services/delta.py`.
- `RiskPolarity` enum IS in `models/enums.py` because it's used by `MetricDelta`'s `risk_polarity` field if we later want to expose it on the model. However, the current design only uses it engine-internally. If we decide to keep it engine-internal, it moves to `services/delta.py`.
- The `path` strings in `METRIC_TABLE` are coupled to field names on `IntelligenceSnapshot`, `MacroContext`, and nested snapshot models. If field names change, the paths must be updated. This is acceptable because field renames are rare and would break other code too.
- Migration 042 drops the legacy `intelligence_snapshots` table from migration 010. No production data exists in this table.
- `delta_reports` should have `ON DELETE CASCADE` on the `prev_snapshot_id` and `curr_snapshot_id` foreign keys to support `cleanup_old_snapshots`.

## Dependencies

- **Wave 1** (intel-wave1-foundation) — models must exist. Must be amended with `trade`/`defense` categories, `RiskPolarity` enum, and simplified `DeltaConfig`.
- **Wave 2** (intel-wave2-data-sources) — all 7 services + FRED expansion must exist for collector to orchestrate.

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/services/intelligence_collector.py` | **Create** |
| `src/options_arena/services/delta.py` | **Create** — `MetricDef`, `METRIC_TABLE`, `DeltaEngine`, `_resolve_path` |
| `src/options_arena/services/__init__.py` | Modify — add exports |
| `data/migrations/042_intelligence.sql` | **Create** — drops legacy 010, creates 3 tables with indexes |
| `src/options_arena/data/_intelligence.py` | **Create** — repository mixin |
| `src/options_arena/data/repository.py` | Modify — add IntelligenceMixin to MRO |
| `tests/unit/services/test_intelligence_collector.py` | **Create** |
| `tests/unit/services/test_delta.py` | **Create** |
| `tests/unit/data/test_intelligence_mixin.py` | **Create** |
