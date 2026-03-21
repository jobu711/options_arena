---
name: unified-agent-system
status: backlog
created: 2026-03-21T16:31:55Z
progress: 0%
prd: .claude/prds/unified-agent-system.md
type: parent
child_epics:
  - unified-agent-system-foundation
  - unified-agent-system-desk-recommend
  - unified-agent-system-orchestrator
  - unified-agent-system-cutover
github: null
---

# Epic: unified-agent-system (Parent)

## Overview

Replace Options Arena's dual agent architecture (6 debate agents + 7 desk agents) with a unified desk-only system. Each desk gains a "recommendation mode" producing structured `DomainAssessment` output alongside existing interactive Q&A. A new synthesis agent replaces algorithmic verdict computation (`synthesize_verdict()`), producing `PositionRecommendation` with specific contract, entry/exit criteria, and position sizing. This is a clean break — 13 debate files are deleted.

This parent epic coordinates 4 child epics executed strictly sequentially.

## Architecture Decisions

1. **Dual-instance pattern per desk**: PydanticAI enforces single `output_type` per Agent. Each desk file gains a second `Agent[DeskDeps, *Assessment]` instance sharing the same toolset. Interactive `Agent[DeskDeps, str]` instances are untouched.

2. **Discriminated union for persistence**: `AnyAssessment = Annotated[..., Discriminator("desk")]` enables polymorphic round-trip through SQLite JSON. Each `DomainAssessment` subclass has `desk: Literal[DeskType.X]` as discriminator.

3. **Forward-only analytics**: No backward compatibility with old `ai_theses` debate records in analytics. Old data viewable but excluded from new queries. `recommendation_protocol` column tags new vs old predictions.

4. **Reusable code extraction before deletion**: `build_market_context()`, `extract_agent_predictions()`, context renderers, and `PROMPT_RULES_APPENDIX` are moved from `orchestrator.py` to `_context.py` (new module) in Epic C, before `orchestrator.py` deletion in Epic D.

5. **Config continuity**: Keep `DebateConfig` name for env var backward compatibility (`ARENA_DEBATE__*`). Remove 4 dead fields, add 5 new fields.

6. **`asyncio.Semaphore`** for desk parallelism: `desk_parallelism` config (default 6) gates concurrent LLM calls. All 6 desks run in parallel by default (paid API tiers).

## Child Epic Summary

| Epic | Scope | Dependencies | Est. Tasks |
|------|-------|-------------|------------|
| `unified-agent-system-foundation` | New models (DomainAssessment hierarchy, PositionRecommendation, RecommendationResult), synthesis agent, synthesis toolset, model re-exports | None | 5 |
| `unified-agent-system-desk-recommend` | Extend DeskDeps, add recommendation agent + runner to 6 desks, 6 recommendation prompts, domain assessment cleaner | foundation | 6 |
| `unified-agent-system-orchestrator` | `run_recommendation()` orchestrator, migration 037, RecommendationMixin, extract reusable code from orchestrator.py | desk-recommend | 5 |
| `unified-agent-system-cutover` | Rewire CLI/API, delete 13 debate files, update exports, config cleanup, rewrite/remove tests, update CLAUDE.md files | orchestrator | 8 |

## Dependency Graph

```
foundation --> desk-recommend --> orchestrator --> cutover
```

Strictly sequential — each epic depends on the previous. No parallelism between epics.

## Success Criteria (Technical)

1. `options-arena debate AAPL` produces a `PositionRecommendation` with specific contract, entry/exit, sizing
2. All 6 desks produce typed `DomainAssessment` subclasses with domain-specific fields
3. Synthesis agent weighs agreement/disagreement, informed by tuned weights
4. Fallback path works: LLM unavailable → data-driven recommendation (`is_fallback=True`)
5. Historical debate data viewable via API (read-only, excluded from new analytics)
6. Interactive desk queries (`agency ask/chat`) work identically
7. Learning pipeline works with forward-only analytics (`recommendation_protocol` filtering)
8. 13 debate files deleted, 4 dead config fields removed, net code reduction
9. All tests pass (existing + ~80-100 new)

## Estimated Effort

- **Total**: ~24 tasks across 4 epics
- **Critical path**: All 4 epics sequential (~4 work sessions)
- **New files**: 12 created
- **Deleted files**: 13 removed
- **Modified files**: ~15
- **New tests**: 80-100
- **Tests to rewrite/remove**: 50-80
- **Source LOC affected**: ~7,000+
- **Test LOC affected**: ~4,900+
