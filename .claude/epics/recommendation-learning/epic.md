---
name: recommendation-learning
status: backlog
created: 2026-03-24T00:09:54Z
progress: 0%
prd: .claude/prds/recommendation-learning.md
type: parent
child_epics:
  - recommendation-learning-foundation
  - recommendation-learning-attribution
  - recommendation-learning-feedback
github: [Will be updated when synced to GitHub]
---

# Epic: recommendation-learning (Parent)

## Overview

Add a prediction ledger that records every intermediate decision in the recommendation
pipeline, scores them against outcomes, and feeds accuracy data back into existing learning
infrastructure. Three child epics deliver this incrementally: shared data infrastructure,
then capture/scoring/attribution and enhanced feedback loop in parallel.

## Architecture Decisions

- **New `predictions` table** rather than retrofitting existing `agent_predictions` (cleaner schema, dual FK to `recommendation_results` + `scan_runs`, context snapshot columns). Old table stays for backward compatibility.
- **Emergent regime awareness** via enriched strategy mining dimensions — no hand-coded regime classifier.
- **Stock return direction** defines prediction correctness (not contract return), isolating direction accuracy from contract selection quality.
- **6 desk sources only** — Research desk excluded from `PredictionSource` (it's interactive, doesn't produce `DomainAssessment`).
- **Contract guidance is advisory** — injected via `<<<CONTRACT_GUIDANCE>>>` prompt block, doesn't override `OptionsFilters` defaults.

## Child Epic Summary

| Epic | Scope | Dependencies | Est. Tasks | File Ownership |
|------|-------|-------------|------------|----------------|
| recommendation-learning-foundation | Models, migration, data CRUD methods | None | 5 | `models/attribution.py`, `data/_learning.py`, `data/migrations/041_*` |
| recommendation-learning-attribution | Prediction recording, scoring, attribution analysis, CLI, API | foundation | 7 | `learning/prediction_ledger.py`, `scan/phase_scoring.py`, `agents/recommendation_orchestrator.py`, `cli/outcomes.py`, `api/analytics.py` |
| recommendation-learning-feedback | Strategy mining conditions, contract guidance, weight tuner, prompt injection | foundation | 6 | `learning/strategy_book.py`, `learning/weight_tuner.py`, `learning/contract_guidance.py`, `agents/prompts/` |

## Dependency Graph

```
foundation ──┬──> attribution
             └──> feedback      (parallel, zero file overlap)
```

- **foundation** merges first — provides models + data layer both siblings depend on
- **attribution** and **feedback** run in parallel worktrees with no shared modified files
- Merge order: foundation → (attribution ∥ feedback) in any order

## Parallel Worktree Strategy

Each child epic can be developed in a separate git worktree. After `foundation` merges
to master, `attribution` and `feedback` rebase onto master and proceed independently.
No merge conflicts expected between attribution and feedback — verified zero file overlap.

## Success Criteria (Technical)

1. After 100+ scored predictions, `learn attribution` shows accuracy differences between desks
2. After 200+ scored predictions, strategy mining discovers condition-specific patterns
3. `learn tune-votes` proposals use prediction-derived per-desk accuracy
4. Direction accuracy tracked independently from recommendation P&L
5. User can trace "why was this wrong?" to specific decision points

## Estimated Effort

- **Total tasks**: ~18 across 3 child epics
- **Critical path**: foundation (5 tasks) → max(attribution 7, feedback 6) = ~12 tasks sequential
- **New code**: ~1,200-1,500 lines across models, learning, data, CLI, API
- **New tests**: ~70-85 unit + integration tests
- **No new external dependencies**
