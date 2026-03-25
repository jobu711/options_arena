---
name: intel-wave1-foundation
description: Foundation models, enums, and config classes for market intelligence integration
status: backlog
created: 2026-03-24T15:48:29Z
updated: 2026-03-24T16:07:20Z
effort: M
---

# PRD: intel-wave1-foundation

## Executive Summary

Establish the typed data shapes (Pydantic models, StrEnums, config classes) that every subsequent intelligence wave depends on. No external API calls, no business logic — purely `models/` and `config.py` changes. This is the foundation that unlocks Waves 2-7.

## Problem Statement

### What problem are we solving?

Options Arena has no data models for intelligence data (news events, energy prices, labor statistics, supply chain pressure, delta reports, or alerts). Before any external data source can be integrated, the typed shapes must exist so that services can return them, agents can consume them, and the API can serialize them.

### Why is this important now?

This is Wave 1 of the Market Intelligence integration epic. Every subsequent wave (data source services, delta engine, alert system, intelligence desk agent) depends on these models existing. Blocking dependency for the entire epic.

## Architecture & Design

### Chosen Approach

Pure data shape layer — models, enums, config only. No I/O, no business logic. Two new model files split by concern: source-specific snapshots in one file, aggregate/engine/alert models in another.

### Module Changes

| File | Action |
|------|--------|
| `src/options_arena/models/enums.py` | Modify — add 8 StrEnums + `DeskType.INTELLIGENCE` |
| `src/options_arena/models/intelligence_sources.py` | **Create** — GDELT, EIA, BLS, GSCPI, Treasury snapshot models |
| `src/options_arena/models/intelligence.py` | **Create** — aggregate container, delta, alert models + IntelligenceAssessment |
| `src/options_arena/models/config.py` | Modify — add 8 config classes + wire into AppSettings |
| `src/options_arena/models/recommendation.py` | Modify — update AnyAssessment union |
| `src/options_arena/models/__init__.py` | Modify — re-export new models |
| `src/options_arena/agents/_desk_deps.py` | Modify — add 2 optional fields |
| `tests/unit/models/test_intelligence_sources.py` | **Create** |
| `tests/unit/models/test_intelligence.py` | **Create** |

### Data Models

Two files split by concern:

**`intelligence_sources.py`** — Data source snapshot shapes (frozen):

| Model | Fields | Notes |
|-------|--------|-------|
| `GdeltArticle` | title, url, published_at (UTC), domain, country (str\|None), category (GdeltCategory) | Single news article |
| `GdeltSnapshot` | articles (list[GdeltArticle]), article_count (int), avg_tone (float\|None), fetched_at (UTC) | `completeness_ratio()` method |
| `EnergySeries` | series_id, display_name, value (float), previous_value (float\|None), unit, period | Single EIA series reading |
| `EnergySnapshot` | wti/brent/natgas/inventories (EnergySeries\|None each), brent_wti_spread (float\|None), inventory_wow_change (float\|None), signal (EnergySignal) | `completeness_ratio()` method |
| `BlsSeries` | series_id, display_name, value (float), previous_value (float\|None), period, mom_change (float\|None) | Single BLS series reading |
| `LaborSnapshot` | cpi_u/core_cpi/unemployment/nfp/ppi (BlsSeries\|None each) | `completeness_ratio()` method |
| `SupplyChainSnapshot` | current_value (float), previous_value (float\|None), pressure (SupplyChainPressure), trend_direction (SignalDirection), fetched_at (UTC) | NY Fed GSCPI |
| `FiscalSnapshot` | total_debt (float), avg_interest_rate (float\|None), effective_date (date), fetched_at (UTC) | US Treasury fiscal data |

**`intelligence.py`** — Aggregate, delta, alert, and agent output models:

| Model | Fields | Notes |
|-------|--------|-------|
| `IntelligenceSnapshot` | gdelt/energy/labor/supply_chain/fiscal (all \|None), macro (MacroContext\|None), fetched_at (UTC) | `completeness_ratio()`, classmethod `fallback()` |
| `MetricDelta` | category (IntelligenceCategory), metric_name, previous_value (float), current_value (float), change_pct (float\|None), change_absolute (float\|None), severity (SignalSeverity), description | Single changed metric |
| `DeltaReport` | report_id (int\|None), previous_snapshot_id (int), current_snapshot_id (int), computed_at (UTC), deltas (list[MetricDelta]), overall_direction (MarketDirectionBias), critical_count (int), high_count (int), moderate_count (int), summary (str) | Full change report |
| `AlertRecord` | alert_id (int\|None), tier (AlertTier), title, body, severity (SignalSeverity), status (AlertStatus), source_delta_id (int\|None), fingerprint (str), cooldown_count (int), created_at (UTC), acknowledged_at (datetime\|None) | Persisted alert |
| `IntelligenceAssessment(DomainAssessment)` | desk=INTELLIGENCE, market_regime_label (str\|None), key_risk_events (list[str]), directional_bias (MarketDirectionBias\|None), event_catalysts (list[str]), macro_summary (str\|None), cross_correlation_notes (str\|None) | 7th desk agent output |

All models follow project rules:
- `ConfigDict(frozen=True)` on all snapshot models
- `math.isfinite()` before range checks on float validators
- UTC validator on datetime fields
- `X | None` not `Optional[X]`
- `field_serializer` on any Decimal fields

## Requirements

### Functional Requirements

#### FR-1: New StrEnum classes in `enums.py`

Add to existing `src/options_arena/models/enums.py`:

| Enum | Values | Purpose |
|------|--------|---------|
| `IntelligenceCategory` | vix, credit_spreads, energy, yield_curve, supply_chain, news_events, labor, fiscal | Delta engine metric categories |
| `SignalSeverity` | critical, high, moderate | Delta engine severity classification |
| `MarketDirectionBias` | risk_on, risk_off, mixed | Overall market direction from delta analysis |
| `AlertTier` | flash, priority, routine | Alert priority tier |
| `AlertStatus` | active, suppressed, acknowledged | Alert lifecycle status |
| `GdeltCategory` | conflict, economy, health, crisis, other | News event categorization |
| `EnergySignal` | price_spike, inventory_surprise, spread_anomaly, normal | EIA energy signals |
| `SupplyChainPressure` | elevated, normal, loose | NY Fed GSCPI classification |

Add `INTELLIGENCE = "intelligence"` to existing `DeskType` enum.

#### FR-2: Data source snapshot models (`models/intelligence_sources.py`)

New file: `src/options_arena/models/intelligence_sources.py`. All frozen snapshots.

Models: `GdeltArticle`, `GdeltSnapshot`, `EnergySeries`, `EnergySnapshot`, `BlsSeries`, `LaborSnapshot`, `SupplyChainSnapshot`, `FiscalSnapshot` (see Data Models table above for field specs).

Each snapshot model with optional fields implements `completeness_ratio() -> float` following the `MacroContext` pattern in `src/options_arena/models/macro.py`.

#### FR-3: Aggregate, delta, alert, and agent models (`models/intelligence.py`)

New file: `src/options_arena/models/intelligence.py`.

Models: `IntelligenceSnapshot`, `MetricDelta`, `DeltaReport`, `AlertRecord`, `IntelligenceAssessment` (see Data Models table above for field specs).

`IntelligenceSnapshot` includes:
- `completeness_ratio()` — fraction of 6 source fields that are non-None
- `fallback()` classmethod — returns all-None instance for graceful degradation

`IntelligenceAssessment` inherits from `DomainAssessment` with `desk: Literal[DeskType.INTELLIGENCE] = DeskType.INTELLIGENCE` and 6 domain-specific fields.

#### FR-4: Config classes in `config.py`

Add to existing `src/options_arena/models/config.py`. All `BaseModel` with `FiniteFieldsMixin`, NOT `BaseSettings`.

**Data source configs (one per source):**

| Config | Key Fields |
|--------|------------|
| `GdeltConfig` | enabled (bool=True), request_timeout (float=15.0), cache_ttl (int=900), max_articles (int=50) |
| `EiaConfig` | enabled (bool=True), api_key (SecretStr\|None), request_timeout (float=10.0), cache_ttl (int=3600) |
| `BlsConfig` | enabled (bool=True), api_key (SecretStr\|None), request_timeout (float=15.0), cache_ttl (int=86400) |
| `GscpiConfig` | enabled (bool=True), request_timeout (float=15.0), cache_ttl (int=86400) |
| `TreasuryConfig` | enabled (bool=True), request_timeout (float=10.0), cache_ttl (int=86400) |

**Engine configs (split by concern):**

| Config | Key Fields |
|--------|------------|
| `IntelligenceConfig` | enabled (bool=False, opt-in), fetch_timeout (float=30.0), snapshot_retention_days (int=90) |
| `DeltaConfig` | delta_vix_threshold_pct (float=5.0), delta_credit_spread_threshold_pct (float=5.0), delta_energy_threshold_pct (float=3.0), delta_yield_curve_threshold_pct (float=10.0), delta_supply_chain_threshold_pct (float=10.0) |
| `AlertConfig` | enable_alerts (bool=False), flash_cooldown_seconds (int=300), priority_cooldown_seconds (int=3600), routine_cooldown_seconds (int=14400), flash_hourly_cap (int=5), priority_hourly_cap (int=20), routine_hourly_cap (int=50) |

Wire all into `AppSettings`:
```python
gdelt: GdeltConfig = GdeltConfig()
eia: EiaConfig = EiaConfig()
bls: BlsConfig = BlsConfig()
gscpi: GscpiConfig = GscpiConfig()
treasury_fiscal: TreasuryConfig = TreasuryConfig()
intelligence: IntelligenceConfig = IntelligenceConfig()
delta: DeltaConfig = DeltaConfig()
alerts: AlertConfig = AlertConfig()
```

Env override examples:
- `ARENA_EIA__API_KEY=your_key` → `settings.eia.api_key`
- `ARENA_INTELLIGENCE__ENABLED=true` → `settings.intelligence.enabled`
- `ARENA_DELTA__DELTA_VIX_THRESHOLD_PCT=3.0` → `settings.delta.delta_vix_threshold_pct`
- `ARENA_ALERTS__FLASH_COOLDOWN_SECONDS=600` → `settings.alerts.flash_cooldown_seconds`

#### FR-5: Update AnyAssessment discriminated union

In `src/options_arena/models/recommendation.py`, add to the `AnyAssessment` union:
```python
| Annotated[IntelligenceAssessment, Tag(DeskType.INTELLIGENCE)]
```

Import `IntelligenceAssessment` from `models.intelligence`.

#### FR-6: Extend DeskDeps

In `src/options_arena/agents/_desk_deps.py`, add two optional fields:
```python
from options_arena.models.intelligence import IntelligenceSnapshot, DeltaReport

intelligence_snapshot: IntelligenceSnapshot | None = None
delta_report: DeltaReport | None = None
```

#### FR-7: Re-exports

Update `src/options_arena/models/__init__.py` to re-export all new models and enums from both `intelligence_sources.py` and `intelligence.py`.

### Non-Functional Requirements

- All new models must pass `uv run mypy src/ --strict`
- JSON roundtrip: `Model.model_validate_json(m.model_dump_json()) == m` for all frozen models
- Zero runtime impact when `intelligence.enabled = False`
- No new pip dependencies

## Testing Strategy

New test files:

**`tests/unit/models/test_intelligence_sources.py`:**
- Each snapshot model: frozen mutation rejected, validators reject NaN/Inf, UTC enforcement on datetime fields
- `completeness_ratio()`: returns 0.0 for all-None, 1.0 for fully populated, correct fraction for partial
- JSON roundtrip for each frozen model
- `EnergySnapshot.signal` defaults to `EnergySignal.NORMAL`

**`tests/unit/models/test_intelligence.py`:**
- `IntelligenceSnapshot`: frozen, `completeness_ratio()`, `fallback()` returns valid instance with completeness 0.0
- `MetricDelta`: category is `IntelligenceCategory` enum (rejects raw strings outside enum), `isfinite()` on floats
- `DeltaReport`: frozen, `critical_count >= 0`, `overall_direction` is valid `MarketDirectionBias`
- `AlertRecord`: frozen, `tier` is `AlertTier`, `cooldown_count >= 0`, UTC on `created_at`
- `IntelligenceAssessment`: inherits `DomainAssessment`, `desk == DeskType.INTELLIGENCE`, confidence [0,1], all 6 domain fields present
- AnyAssessment union roundtrip: serialize `IntelligenceAssessment`, deserialize via `AnyAssessment`, verify type preserved

Mark primary happy-path tests with `@pytest.mark.critical`.

## Success Criteria

- `uv run ruff check . --fix && uv run ruff format .` passes
- `uv run mypy src/ --strict` passes
- `uv run pytest tests/unit/models/test_intelligence.py tests/unit/models/test_intelligence_sources.py -v` passes
- All frozen models reject mutation
- All float validators reject NaN/Inf
- All datetime validators reject naive and non-UTC
- `IntelligenceSnapshot.fallback()` returns valid instance
- AnyAssessment discriminated union round-trips `IntelligenceAssessment` correctly

## Constraints & Assumptions

- Only `AppSettings` is `BaseSettings`; all new configs are plain `BaseModel`
- `DeskType.INTELLIGENCE` must not break existing 6-desk orchestration when intelligence is disabled
- `DeskDeps` extension must be backward-compatible (new fields default to `None`)
- No Decimal fields expected in intelligence models (prices aren't tracked) — all `float` for ratios/indicators

## Out of Scope

- Any external API calls (Wave 2)
- Business logic or computation (Wave 3)
- Database persistence / migrations (Wave 3)
- Alert evaluation logic (Wave 4)
- Agent implementation (Wave 5)
- Synthesis prompt changes (Wave 6)
- API endpoints / frontend changes (Wave 7)

## Dependencies

- None — this is the foundation wave with no external dependencies
