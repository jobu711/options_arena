---
name: ai-debate-enhance
status: backlog
created: 2026-02-24T21:42:38Z
updated: 2026-02-24T21:49:24Z
progress: 0%
prd: .claude/prds/ai-debate-enhance.md
github: [Will be updated when synced to GitHub]
---

# Epic: AI Debate System Enhancements (Parent)

## Overview

Parent epic coordinating 7 child epics that enhance the Phase 9 AI debate system.

## Child Epics

| # | Epic | Phase | PRD Reqs | Depends On |
|---|------|-------|----------|------------|
| 1 | `debate-expand-context` | A | FR-A1, FR-A2 | None |
| 2 | `debate-enhance-prompts` | A | FR-A3, FR-A4, FR-A5 | Epic 1 |
| 3 | `debate-pre-screening` | B | FR-B3 | None |
| 4 | `debate-volatility-agent` | B | FR-B1 | Epics 1, 3 |
| 5 | `debate-bull-rebuttal` | B | FR-B2 | Epics 1, 3 |
| 6 | `debate-batch-mode` | C | FR-C1 | Epics 1-5 |
| 7 | `debate-export` | C | FR-C2 | Epic 6 |

## Elegance Principles

1. **Compose, don't duplicate** — Shared `PROMPT_RULES_APPENDIX` constant instead of
   copy-pasting calibration/citation rules into 3+ agent prompts.
2. **Extract, don't repeat** — `build_cleaned_agent_response()` in `_parsing.py` replaces
   77 lines of identical output validator code across 3 agents.
3. **Render dynamically** — `render_context_block()` iterates new fields conditionally
   instead of hardcoding each line.
4. **Extract `_debate_single()`** — Factor the existing debate command's data-fetching +
   debate-running logic into a reusable async function. Batch calls it in a loop.
5. **Flat model, flat text** — Keep `MarketContext` flat (individual fields, not nested
   models). The flat pattern is proven. Add fields with defaults for backward compat.
