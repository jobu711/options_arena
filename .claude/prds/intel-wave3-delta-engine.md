---
name: intel-wave3-delta-engine
description: Intelligence collector orchestrator, delta/change detection engine, and SQLite persistence layer
status: backlog
created: 2026-03-24T15:48:29Z
effort: L
---

# PRD: intel-wave3-delta-engine

## Executive Summary

Build the intelligence data pipeline: an orchestrator that fetches all data sources in parallel (`IntelligenceCollector`), a stateless change detection engine that compares consecutive snapshots (`DeltaEngine`), and SQLite persistence for snapshots, delta reports, and alert history. This is the computational core that transforms raw data into actionable signals.

## Problem Statement

### What problem are we solving?

Individual data source services (Wave 2) produce isolated snapshots. Without an orchestrator to aggregate them and a delta engine to detect meaningful changes, the data has no context. "VIX is 22" is less useful than "VIX jumped 18% since your last scan — market shifted from risk-on to risk-off." The delta engine is what makes intelligence *actionable*.

### Why is this important now?

Wave 3 is the computational backbone. The alert system (Wave 4) evaluates delta reports. The intelligence desk agent (Wave 5) consumes snapshots and deltas. Without this layer, Waves 4-7 have no data to work with.

## Requirements

### Functional Requirements

#### FR-1: Intelligence Collector (`services/intelligence_collector.py`)

Coordinator class (NOT a ServiceBase subclass — same pattern as ScanPipeline).

```python
class IntelligenceCollector:
    def __init__(self, *, gdelt, eia, bls, gscpi, treasury, fred, config): ...
    async def collect_snapshot(self, ticker=None, company_name=None) -> IntelligenceSnapshot: ...
    async def close(self) -> None: ...
```

- Receives individual service instances via DI (constructor injection)
- `collect_snapshot()` fetches all enabled sources in parallel via `asyncio.gather(*tasks, return_exceptions=True)`
- Entire call wrapped in `asyncio.wait_for(coro, timeout=config.fetch_timeout)`
- Exceptions per source → None for that field (partial data OK)
- Total failure → `IntelligenceSnapshot.fallback()`
- Optional `ticker`/`company_name` params for ticker-specific GDELT queries
- `close()` closes all non-None sub-services

#### FR-2: Delta Engine (`services/delta.py`)

Stateless computation class — compares two IntelligenceSnapshots.

```python
class DeltaEngine:
    def __init__(self, config: IntelligenceConfig): ...
    def compute_delta(self, previous: IntelligenceSnapshot,
                       current: IntelligenceSnapshot) -> DeltaReport: ...
```

**Numeric metric comparison** (% change with configurable thresholds):
- VIX: from MacroContext.vix (threshold: `delta_vix_threshold_pct`, default 5%)
- Credit spreads: from FRED BAMLH0A0HYM2 (threshold: `delta_credit_spread_threshold_pct`, default 5%)
- WTI crude: from EnergySnapshot.wti (threshold: `delta_energy_threshold_pct`, default 3%)
- Yield curve 10Y-2Y: from MacroContext.yield_spread_10y2y (threshold: `delta_yield_curve_threshold_pct`, default 10%)
- GSCPI: from SupplyChainSnapshot.current_value (threshold: 10%)

**Severity mapping:**
- `|change| > threshold * 3` → CRITICAL
- `|change| > threshold * 2` → HIGH
- `|change| > threshold` → MODERATE

**Count metric comparison** (absolute change):
- News article count by category
- Urgent signal count

**Overall direction computation:**
- Risk-sensitive keys: VIX (up = risk-off), credit spreads (up = risk-off), yield curve inversion (more negative = risk-off)
- Count risk-off escalations vs risk-on de-escalations
- If risk-off > risk-on + 1 → RISK_OFF; if risk-on > risk-off + 1 → RISK_ON; else MIXED

**Text signal dedup:**
- Normalize text: lowercase, strip timestamps/numbers
- Jaccard word-level similarity > 0.7 → duplicate

#### FR-3: SQLite Persistence (`data/migrations/042_intelligence.sql`)

Three tables:

```sql
-- Intelligence snapshots
CREATE TABLE IF NOT EXISTS intelligence_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    completeness REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Delta reports
CREATE TABLE IF NOT EXISTS delta_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prev_snapshot_id INTEGER NOT NULL REFERENCES intelligence_snapshots(id),
    curr_snapshot_id INTEGER NOT NULL REFERENCES intelligence_snapshots(id),
    computed_at TEXT NOT NULL,
    direction TEXT NOT NULL,
    critical_count INTEGER NOT NULL DEFAULT 0,
    high_count INTEGER NOT NULL DEFAULT 0,
    moderate_count INTEGER NOT NULL DEFAULT 0,
    deltas_json TEXT NOT NULL,
    summary TEXT NOT NULL
);

-- Alert history (used by Wave 4, created here for migration ordering)
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    source_delta_id INTEGER REFERENCES delta_reports(id),
    fingerprint TEXT NOT NULL,
    cooldown_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT
);
```

With appropriate indexes on `captured_at`, `computed_at`, `fingerprint`, `created_at`.

#### FR-4: Repository Mixin (`data/_intelligence.py`)

```python
class IntelligenceMixin(RepositoryBase):
    async def save_intelligence_snapshot(self, snapshot) -> int
    async def get_latest_snapshot(self) -> IntelligenceSnapshot | None
    async def get_snapshots_since(self, since, limit=48) -> list[IntelligenceSnapshot]
    async def save_delta_report(self, report) -> int
    async def get_latest_delta(self) -> DeltaReport | None
    async def save_alert(self, alert) -> int
    async def get_alerts(self, *, tier=None, status=None, limit=50) -> list[AlertRecord]
    async def acknowledge_alert(self, alert_id) -> None
    async def get_alert_count_since(self, fingerprint, since) -> int
    async def cleanup_old_snapshots(self, retention_days) -> int
```

Add `IntelligenceMixin` to `Repository` class MRO in `data/repository.py`.

### Non-Functional Requirements

- DeltaEngine.compute_delta() is a pure function (no I/O) — testable without mocking
- IntelligenceCollector follows never-raises contract
- All repository methods return typed Pydantic models
- Parameterized SQL queries (no injection)
- `await db.commit()` after every write
- Snapshot JSON uses `model_dump_json()` / `model_validate_json()` for serialization

## Success Criteria

- Delta engine unit tests: threshold crossings produce correct severity, direction logic works for all 3 cases, dedup catches near-duplicates
- Collector tests: partial failure (1 source down) still returns partial snapshot, total failure returns fallback
- Repository tests: save/get roundtrip, cleanup removes old data
- `uv run pytest -m "not exhaustive" -n auto -q` passes

## Out of Scope

- Alert evaluation logic (Wave 4)
- Agent consumption of delta data (Wave 5)
- API endpoints (Wave 7)

## Dependencies

- **Wave 1** (intel-wave1-foundation) — models must exist
- **Wave 2** (intel-wave2-data-sources) — services must exist for collector to orchestrate

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/services/intelligence_collector.py` | **Create** |
| `src/options_arena/services/delta.py` | **Create** |
| `src/options_arena/services/__init__.py` | Modify — add exports |
| `data/migrations/042_intelligence.sql` | **Create** |
| `src/options_arena/data/_intelligence.py` | **Create** — repository mixin |
| `src/options_arena/data/repository.py` | Modify — add IntelligenceMixin to MRO |
| `tests/unit/services/test_intelligence_collector.py` | **Create** |
| `tests/unit/services/test_delta.py` | **Create** |
| `tests/unit/data/test_intelligence_mixin.py` | **Create** |
