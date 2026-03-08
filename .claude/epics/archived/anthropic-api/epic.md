---
name: anthropic-api
status: completed
created: 2026-03-03T10:25:40Z
completed: 2026-03-08T22:00:00Z
progress: 100%
prd: .claude/prds/anthropic-api.md
github: https://github.com/jobu711/options_arena/issues/214
---

# Epic: anthropic-api

## Overview

Add Claude/Anthropic as an alternative LLM debate provider. PydanticAI's `Model` abstraction already makes agents provider-agnostic — `build_debate_model()` returns a `Model` and all `agent.run(model=model)` calls work regardless of backend. This epic adds a `LLMProvider` enum, extends config with Anthropic fields, refactors model building into a multi-provider dispatcher, adds a health check, and wires a `--provider` CLI flag. Default remains Groq (free). No breaking changes.

## Architecture Decisions

1. **Single dispatcher pattern**: `build_debate_model()` dispatches to `_build_groq_model()` or `_build_anthropic_model()` based on `config.provider` enum. Call sites unchanged.
2. **Extended thinking in orchestrator**: `ModelSettings` is built per-run in the orchestrator, not at model construction — because Anthropic requires `temperature=1.0` when thinking is enabled, overriding the user's configured temperature.
3. **Health check always present**: `check_anthropic()` runs in `check_all()` alongside `check_groq()`. Returns unavailable (not error) when no API key configured.
4. **Config-driven, not code-branching**: All provider differences expressed via `DebateConfig` fields + `LLMProvider` enum. No scattered `if anthropic` checks beyond the two required locations (model_config dispatcher + orchestrator ModelSettings).
5. **API routes untouched**: Routes use `settings.debate` transparently — provider selection via env vars (`ARENA_DEBATE__PROVIDER=anthropic`) or future API enhancement.

## Technical Approach

### Models Layer (`models/`)
- Add `LLMProvider` StrEnum (`groq`, `anthropic`) to `enums.py`
- Add 5 fields to `DebateConfig`: `provider`, `anthropic_model`, `anthropic_api_key`, `enable_extended_thinking`, `thinking_budget_tokens`
- Add `anthropic_api_key: SecretStr | None` to `ServiceConfig` (health check key)
- Add `thinking_budget_tokens` validator (range [1024, 128000])
- Re-export `LLMProvider` from `models/__init__.py`

### Agents Layer (`agents/`)
- Refactor `build_debate_model()` into dispatcher + provider-specific builders
- Add `_build_anthropic_model()` + `_resolve_anthropic_api_key()` (mirrors Groq pattern)
- Add conditional `ModelSettings` in orchestrator for extended thinking at both v1 and v2 call sites

### Services Layer (`services/`)
- Add `check_anthropic()` to `HealthService` — mirrors `check_groq()` exactly
- Endpoint: `GET https://api.anthropic.com/v1/models` with `x-api-key` + `anthropic-version` headers
- Include in `check_all()` task list

### CLI Layer (`cli/`)
- Add `--provider` option to `debate` command (Typer auto-converts string to `LLMProvider` enum)
- Override `settings.debate` via `model_copy(update={"provider": provider})` pattern

### Dependencies
- Add `anthropic` package via `uv add anthropic` (required by pydantic-ai's `AnthropicProvider`)

## Implementation Strategy

All tasks are additive (no breaking changes) and follow a bottom-up dependency order. The models layer must land first since all other layers import from it. Agent and service changes are independent of each other. CLI wiring comes last.

## Task Breakdown Preview

- [ ] Task 1: Models — Add `LLMProvider` enum + extend `DebateConfig` and `ServiceConfig` + re-exports + unit tests
- [ ] Task 2: Agents — Refactor `build_debate_model()` into multi-provider dispatcher + unit tests
- [ ] Task 3: Orchestrator — Add conditional `ModelSettings` for extended thinking at both call sites + unit test
- [ ] Task 4: Health — Add `check_anthropic()` to `HealthService` + include in `check_all()` + unit tests
- [ ] Task 5: CLI + Dependency — Add `--provider` flag to debate command + `uv add anthropic` + verify all gates pass

## Dependencies

- **pydantic-ai** >= 1.62 (already installed) — provides `AnthropicModel`, `AnthropicProvider`
- **anthropic** SDK — required runtime dependency for the Anthropic provider
- No database migrations
- No frontend changes (CLI-only scope)

## Success Criteria (Technical)

- `options-arena debate AAPL` works unchanged (Groq default)
- `options-arena debate AAPL --provider anthropic` produces a full debate with Claude
- `options-arena health` shows both Groq and Anthropic status
- `ARENA_DEBATE__PROVIDER=anthropic` env var override works
- Extended thinking: `--provider anthropic` with `ARENA_DEBATE__ENABLE_EXTENDED_THINKING=true` passes `anthropic_thinking` in ModelSettings
- All existing tests pass (no regressions)
- ~14 new unit tests pass
- `ruff check`, `ruff format`, `mypy --strict` all clean

## Tasks Created

- [x] #215 - Add LLMProvider enum and extend DebateConfig/ServiceConfig (parallel: false)
- [x] #216 - Refactor build_debate_model() into multi-provider dispatcher (parallel: true)
- [x] #217 - Add conditional ModelSettings for extended thinking in orchestrator (parallel: true)
- [x] #218 - Add check_anthropic() health check to HealthService (parallel: true)
- [x] #219 - Add --provider CLI flag and anthropic dependency (parallel: false)

Total tasks: 5
Parallel tasks: 3 (#216, #217, #218 — after #215 completes)
Sequential tasks: 2 (#215 first, #219 last)
Estimated total effort: 8 hours

## Test Coverage Plan

Total test files planned: 3
Total test cases planned: ~20 (7 config + 6 model_config + 4 orchestrator + 6 health)

## Estimated Effort

- **Size**: Small (S)
- **Tasks**: 5
- **New production code**: ~200 lines across 7 files
- **New test code**: ~300 lines across 3 existing test files
- **New files**: 0
- **Risk**: Low — all changes additive, Groq default preserved
