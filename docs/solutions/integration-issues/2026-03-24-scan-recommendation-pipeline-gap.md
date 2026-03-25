---
title: "Scan→Recommendation pipeline gap: enrichment data silently discarded"
date: 2026-03-24
module: options_arena.agents.recommendation_orchestrator
problem_type: integration_issues
severity: critical
symptoms:
  - "Spread data computed and persisted but never appears in recommendation output"
  - "Macro/neural fields on OptionsResult are None in MarketContext despite being populated in scan"
  - "Parameters marked # noqa: ARG001 (unused) on run_recommendation()"
  - "Agent prompts contain no spread, macro, or trajectory context"
  - "Features appear to work in isolation but produce no visible effect end-to-end"
tags:
  - pipeline-wiring
  - scan-enrichment
  - parameter-threading
  - dead-feature
  - run_recommendation
  - spread_analysis
  - macro_regime
  - prob_profit_neural
root_cause: "Flat parameter list on run_recommendation() requires 4 coordinated edits per new feature; epics consistently miss 2-3 of them"
---

## Problem

Audit of 34 merged epics found that multiple features were implemented in the scan
pipeline but never reached the recommendation agents or user-facing output:

- **multi-leg-strategies**: `spread_analysis` parameter added to `run_recommendation()`
  but marked `# noqa: ARG001` (unused). No caller passes it. Spreads computed, persisted
  to DB, but agents never see them.
- **scientific-ml-neural**: `prob_profit_neural` computed on `OptionsResult` but
  `run_recommendation()` doesn't accept or forward it to `build_market_context()`.
- **scientific-ml-statistical** (pre-fix): Same pattern — macro fields on `OptionsResult`
  not threaded through to agents.

Pattern: data flows scan → `OptionsResult` → **gap** → `run_recommendation()` → agents.

## Root Cause

Adding scan-phase data to the recommendation pipeline requires **4 coordinated edits**:

1. Add parameter to `run_recommendation()` signature
2. Add same parameter to CLI call site (`cli/commands.py`)
3. Add same parameter to API call site (`api/routes/debate.py`)
4. Thread parameter through `_run_recommendation_pipeline()` → `build_market_context()`

Each edit is in a different file with no compile-time enforcement that they stay in sync.
Epics consistently complete step 1 (or skip it entirely) and miss steps 2-4. The linter
catches unused parameters, but the fix is `# noqa` suppression instead of wiring.

No error is raised — `None` defaults cause silent degradation. The feature appears to
"work" because the scan computes data and tests pass at the unit level, but the data
never reaches its destination.

## Solution

Replace the flat parameter list with a **single envelope model** (`ScanEnrichment`):

```python
class ScanEnrichment(BaseModel):
    """All scan-phase data that flows to the recommendation phase."""
    model_config = ConfigDict(frozen=True)

    spread_analysis: SpreadAnalysis | None = None
    prob_profit_neural: float | None = None
    macro_regime: MacroRegime | None = None
    macro_yield_spread: float | None = None
    macro_fed_funds_rate: float | None = None
    macro_vix_level: float | None = None
    next_earnings: date | None = None
    fd_package: FinancialDatasetsPackage | None = None
```

`run_recommendation()` accepts `enrichment: ScanEnrichment | None = None` instead of
individual parameters. Callers construct the envelope from `OptionsResult` in one place.
Future epics add a field to the model — callers already build it from `OptionsResult`,
so new data flows through without touching any signatures.

## Prevention Rule

**Never add individual enrichment parameters to `run_recommendation()`.** All scan-phase
data goes through `ScanEnrichment`. When a new epic computes data during the scan:

1. Add field to `ScanEnrichment` (one file)
2. Populate it in `OptionsResult` (already done by the epic)
3. Unpack it in `_run_recommendation_pipeline()` → `build_market_context()` (one file)

This reduces 4 coordinated edits across 4 files to 1 edit in 1 file (step 3), since
the envelope construction from `OptionsResult` is generic.

**Detection heuristic**: Any `# noqa: ARG001` on `run_recommendation()` is a bug, not
a style choice. Grep for it periodically.

## Related

- PRD: `.claude/prds/pipeline-wiring-fix.md`
- Epic audit memory: `memory/project_epic_audit_2026_03_24.md`
- `build_market_context()` in `agents/_context.py` — the downstream consumer
- `OptionsResult` in `scan/models.py` — the upstream producer
- `run_recommendation()` in `agents/recommendation_orchestrator.py` — the broken bridge
