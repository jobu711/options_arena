---
name: scientific-ml-integration
status: split
created: 2026-03-15T13:38:21Z
progress: 0%
prd: .claude/prds/scientific-ml-integration.md
github: [Will be updated when synced to GitHub]
---

# Epic: scientific-ml-integration (Parent — Split into 3 Child Epics)

## Overview

This epic has been decomposed into 3 child epics matching the PRD's delivery structure (lines 483-537). The original monolithic 9-task breakdown was incorrectly merged; the PRD explicitly defines 3 independent epics with distinct dependency groups and timelines.

## Child Epics

| Epic | Directory | Focus | Issues | Dependencies | Size |
|------|-----------|-------|--------|-------------|------|
| **A** | `scientific-ml-statistical/` | arch + statsmodels + FRED | 5 (A1-A5) | None (foundation) | L (~3-4 sessions) |
| **B** | `scientific-ml-classification/` | scikit-learn | 4 (B1-B4) | Epic A complete | M (~2 sessions) |
| **C** | `scientific-ml-neural/` | PyTorch Lightning | 4 (C1-C4) | Epic A config infra (A1) | L (~2-3 sessions) |

## Dependency Graph

```
Epic A: Statistical Foundation (5 issues)
    |   A1 (FRED) → A2 (macro regime) → A5 (pipeline wiring)
    |   A3 (GARCH) → A4 (Markov) ────→ A5
    |
    ├──→ Epic B: ML Classification (4 issues)
    |       B1 (training) → B2 (inference)
    |       B3 (clustering), B4 (anomaly) — independent
    |
    └──→ Epic C: Neural Models (4 issues)  [parallel with B]
            C1 (surface) → C2 (integration)
            C3 (trajectory) → C4 (agent enrichment)
```

Epic B and Epic C can run in parallel after Epic A completes.

## Shared Resources

- **Research**: `research.md` (in this directory) — shared reference for all 3 epics
- **PRD**: `.claude/prds/scientific-ml-integration.md` — single PRD covers all 3 epics
- **Cross-PRD contracts**: WeightSnapshot (ai-agency owns), additive context rendering, Volatility Agent non-conflicting sections

## Totals

| Metric | Value |
|--------|-------|
| Total issues | 13 (5 + 4 + 4) |
| New files | 8 |
| Modified files | ~15 unique |
| New dependencies | 4 (arch, statsmodels, scikit-learn, torch/lightning) |
| Estimated tests | ~220 |
| Estimated sessions | ~7-9 total |
