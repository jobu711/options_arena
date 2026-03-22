---
epic: unified-agent-system-foundation
retro_at: 2026-03-22T00:00:00Z
---

# Retrospective — unified-agent-system-foundation

## Effort

| Metric | Planned | Actual |
|--------|---------|--------|
| Total hours | 14-20h | ~0.3h (proxy from commit span: 17 min wall-clock, agent-assisted) |
| LOC (source) | 500-700 | 656 (+ ~110 modified) |
| LOC (tests) | 150-200 | 1,489 |
| Test cases | ~48 | 125 (parametrized: 120 functions) |
| Tasks | 5 | 5 |
| Commits | ~5 | 6 |

**Estimation bias**: 47-67x overestimate on hours. This is typical for agent-assisted epics — the planned hours assumed human solo development. With parallel agent execution, the epic completed in a single session.

## Scope Delta

| Planned | Delivered | Delta |
|---------|-----------|-------|
| DomainAssessment + 6 subclasses | Delivered as specified | On-scope |
| AnyAssessment discriminated union | Delivered with TypeAdapter round-trip | On-scope |
| PositionRecommendation (21 fields) | Delivered with all validators + serializers | On-scope |
| RecommendationResult | Delivered with arbitrary_types_allowed | On-scope |
| SYNTHESIS_SYSTEM_PROMPT | Delivered with 7-step protocol | On-scope |
| build_synthesis_toolset() | Delivered with 2 tools | On-scope |
| synthesis_agent + SynthesisDeps | Delivered with dynamic prompt, output validator, never-raises runner | On-scope |
| Re-exports (models + agents) | Delivered — 10 model names + 4 agent names | On-scope |
| Integration tests | Delivered — 4 integration tests including critical-marked | On-scope |

**No scope creep.** Purely additive — zero existing files' logic modified.

## Quality

- **Test coverage**: 125 tests for 656 LOC source (~1 test per 5.2 LOC)
- **Post-merge fixes**: 0 (no fixes needed after initial implementation)
- **Regressions**: 0 (1 pre-existing failure on master unrelated)
- **Lint/type issues**: 0 (ruff + mypy --strict clean from first pass)
- **Test files**: 8 (6 planned + 2 additional)

## Execution Pattern

| Wave | Tasks | Duration | Strategy |
|------|-------|----------|----------|
| 1 | #632 + #634 | ~2 min | Parallel agents (no dependencies) |
| 2 | #633 | ~4 min | Sequential (depends on #632) |
| 3 | #635 | ~7 min | Sequential (depends on #632, #633, #634) |
| 4 | #636 | ~3 min | Sequential (depends on all prior) |

**Key insight**: Wave 1 parallelization saved time — models and prompt are independent. The critical path was Wave 3 (synthesis agent) which depended on all three prior deliverables.

## Learnings

1. **Discriminated unions work cleanly**: Pydantic v2 `Discriminator("desk")` + `Tag()` pattern works exactly as specified in the PRD. JSON round-trip via `TypeAdapter` is the right deserialization approach for SQLite storage.

2. **Test count significantly exceeded estimate**: Planned ~48, delivered 125. Agent-generated tests are thorough with parametrized boundary cases (NaN, Inf, edge values). This is net positive.

3. **Frozen model + output_validator pattern**: The synthesis agent output validator needs to reconstruct frozen `PositionRecommendation` instances to strip think tags. This is the same pattern as debate agents but with more fields — consider extracting a generic `_strip_think_tags_from_model()` helper if more agents follow this pattern.

4. **Decimal field_serializer for optional fields**: `stop_loss: Decimal | None` needs a serializer that handles `None` → `None` pass-through. The pattern is: `return str(v) if v is not None else None`.

## Risks for Downstream Epics

- **orchestrator epic**: Will need to construct `SynthesisDeps` from desk agent outputs. The `assessments` field expects `list[DomainAssessment]` — each desk must produce its specific subclass.
- **desk-recommend epic**: Will extend `DeskDeps` with `output_format: Literal["text", "assessment"]` to toggle between current text output and new `DomainAssessment` structured output.
- **cutover epic**: Will need to ensure `RecommendationResult` is wire-compatible with the API and CLI rendering code that currently expects `DebateResult`.
