---
issue: 158
title: Pipeline integration & E2E validation
analyzed: 2026-02-28T18:48:25Z
estimated_hours: 18
parallelization_factor: 2.5
---

# Parallel Work Analysis: Issue #158

## Overview

Wire all ~40 new DSE indicators into the scan pipeline, switch Phase 2 to dimensional
scoring, connect the 6-agent debate protocol to CLI/API/export, and validate end-to-end
with integration tests. All foundational components (indicators, models, agents, scoring)
are already implemented — this is pure integration wiring and validation.

## Parallel Streams

### Stream A: Pipeline Indicator Wiring
**Scope**: Expand INDICATOR_REGISTRY from 14 to ~54 entries, update Phase 2 to use
dimensional scoring and direction signal computation, thread universe data through phases.
**Files**:
- `src/options_arena/scan/pipeline.py` (modify Phase 2)
- `src/options_arena/scan/indicators.py` (expand INDICATOR_REGISTRY + InputShape)
- `src/options_arena/scan/models.py` (add universe_data to phase results if needed)
**Agent Type**: general-purpose
**Can Start**: immediately
**Estimated Hours**: 6
**Dependencies**: none

### Stream B: Debate Protocol Wiring
**Scope**: Wire `run_debate_v2()` into CLI debate command, API debate routes, and reporting
export. Render ExtendedTradeThesis fields (contrarian dissent, agreement score, dimensional
scores) in all output formats.
**Files**:
- `src/options_arena/cli/commands.py` (switch to run_debate_v2, render ExtendedTradeThesis)
- `src/options_arena/cli/rendering.py` (new render_extended_verdict_panels)
- `src/options_arena/api/routes/debate.py` (return ExtendedTradeThesis)
- `src/options_arena/api/routes/scan.py` (include DimensionalScores)
- `src/options_arena/api/schemas.py` (new response schemas)
- `src/options_arena/reporting/debate_export.py` (contrarian section, agreement score)
**Agent Type**: general-purpose
**Can Start**: immediately
**Estimated Hours**: 8
**Dependencies**: none

### Stream C: Integration Tests & Regression
**Scope**: Write E2E tests for scan→dimensional scoring→debate flow, pipeline timing
validation, and regression tests confirming backward compatibility.
**Files**:
- `tests/integration/test_e2e_dse.py` (create new)
- `tests/integration/test_pipeline_timing.py` (create new)
**Agent Type**: general-purpose
**Can Start**: after Streams A and B complete
**Estimated Hours**: 4
**Dependencies**: Stream A, Stream B

## Coordination Points

### Shared Files
- `src/options_arena/scan/pipeline.py` — Stream A only (no conflict)
- `src/options_arena/agents/orchestrator.py` — Stream B only (no conflict)
- `src/options_arena/models/` — read-only for both streams (models already exist)
- `src/options_arena/scoring/dimensional.py` — read-only import (already implemented)

### Sequential Requirements
1. Stream A and Stream B can run fully in parallel (different file sets)
2. Stream C (tests) must wait for both A and B to complete
3. Final verification (ruff, mypy, pytest) runs after all streams

## Conflict Risk Assessment
- **Low Risk**: Streams A and B work on completely different file sets (scan/ vs cli/+api/+reporting/)
- No shared files are modified by multiple streams
- Models and scoring modules are read-only imports for both streams

## Parallelization Strategy

**Recommended Approach**: hybrid

Launch Streams A & B simultaneously (zero file conflicts — scan pipeline vs debate output).
Start Stream C when both complete (needs integrated pipeline + debate wiring for E2E tests).

```
Time →
Stream A (Pipeline):  [████████████████]
Stream B (Debate):    [████████████████████████]
Stream C (Tests):                               [████████████]
                      ^--- parallel ---^        ^-- sequential --^
```

## Expected Timeline

With parallel execution:
- Wall time: ~12 hours (max(A,B) + C)
- Total work: 18 hours
- Efficiency gain: 33%

Without parallel execution:
- Wall time: 18 hours

## Notes

- All DSE components (indicators, models, agents, dimensional scoring) are already
  implemented and tested individually. This task is purely integration wiring.
- The `run_debate_v2()` function already exists in the orchestrator — Stream B just
  needs to call it instead of `run_debate()`.
- Backward compatibility: `DebateConfig.use_legacy_protocol: bool = False` flag
  already exists for 3-agent fallback.
- New indicators need appropriate `InputShape` variants — some (IV analytics, flow,
  fundamental, regime) require data beyond OHLCV (option chains, universe data,
  ticker info). These may need new InputShape variants or separate computation paths
  outside the existing INDICATOR_REGISTRY pattern.
- Pipeline timing target: <190s for full universe scan.
