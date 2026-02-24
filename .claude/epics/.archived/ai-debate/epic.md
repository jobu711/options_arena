---
name: ai-debate
status: completed
created: 2026-02-24T13:43:13Z
updated: 2026-02-24T16:40:35Z
completed: 2026-02-24T16:40:35Z
progress: 100%
prd: .claude/prds/ai-debate.md
github: https://github.com/jobu711/options_arena/issues/62
---

# Epic: AI Debate System (Phase 9)

## Overview

Add a three-agent AI debate system (Bull / Bear / Risk) to Options Arena. Agents run
sequentially via PydanticAI + Ollama (Llama 3.1 8B), transforming quantitative scan
results into qualitative reasoning. Data-driven fallback when Ollama is unreachable
ensures the tool always produces a verdict.

Backend-only. Web UI and streaming deferred to Phase 11.

## Architecture Decisions

- **PydanticAI Agent framework** — module-level `Agent[DebateDeps, OutputType]` instances
  (proven pattern from prior migration). `model=None` at init, actual `OllamaModel` passed
  at `agent.run(model=...)` time.
- **Single-pass debate** — Bull -> Bear -> Risk, sequential (Ollama is single-threaded on CPU).
  No multi-round rebuttal in this phase.
- **`@dataclass` for DebateDeps and DebateResult** — `RunUsage` is a plain dataclass, not
  Pydantic-serializable. Pydantic sub-models serialized individually for persistence.
- **Data-driven fallback** — synthesizes `AgentResponse` + `TradeThesis` from quantitative
  signals when Ollama is unreachable. Fixed confidence cap of 0.3.
- **Inline prompt constants** — no template system. Version header on each prompt.
- **Existing infrastructure reuse** — `MarketContext`, `AgentResponse`, `TradeThesis` models
  already defined in `models/analysis.py`. `ai_theses` table already in `001_initial.sql`.
  Only need ALTER TABLE migration for new metadata columns.

## Technical Approach

### Existing Infrastructure (No Changes Needed)

- `models/analysis.py`: `MarketContext`, `AgentResponse`, `TradeThesis` — already defined
- `models/enums.py`: `SignalDirection`, `MacdSignal`, `SpreadType` — all needed enums exist
- `data/migrations/001_initial.sql`: `ai_theses` table — base schema exists
- `pydantic-ai`, `ollama` packages — already installed

### New Components

**Config & Data (modify existing files):**
- `models/config.py`: Add `DebateConfig(BaseModel)` nested on `AppSettings`
- `data/migrations/002_debate_columns.sql`: ALTER TABLE for token/model/duration/fallback columns
- `data/repository.py`: Add `save_debate()`, `get_debates_for_ticker()`, `DebateRow` dataclass

**Agent Module (new files in `agents/`):**
- `agents/CLAUDE.md`: Module conventions
- `agents/model_config.py`: `build_ollama_model()`, `_resolve_host()`
- `agents/_parsing.py`: `DebateDeps` dataclass, `DebateResult` dataclass
- `agents/bull.py`: Bull agent + prompt + output validator
- `agents/bear.py`: Bear agent + prompt + output validator (receives bull argument)
- `agents/risk.py`: Risk agent + prompt + output validator (receives both arguments)
- `agents/orchestrator.py`: `run_debate()`, `build_market_context()`, fallback logic
- `agents/__init__.py`: Re-exports with `__all__`

**CLI (modify existing files):**
- `cli/commands.py`: Add `debate` command with `--history`, `--fallback-only`
- `cli/rendering.py`: Add `render_debate_panels()`, `render_debate_history()`

## Implementation Strategy

Sequential implementation following dependency order. Issues 1-2 are infrastructure
(parallelizable). Issue 3 (agents) depends on issue 2. Issue 4 (orchestrator) depends
on issue 3. Issue 5 (CLI) depends on issue 4. Issue 6 (tests) spans all.

### Risk Mitigation
- PydanticAI `TestModel` enables full test coverage without Ollama installed
- Data-driven fallback ensures CLI always produces output
- Per-agent timeout (90s) + total timeout (300s) prevents hangs
- `retries=2` on PydanticAI handles malformed LLM JSON output

## Task Breakdown

- [ ] **Task 1: Config, migration, and repository** — Add `DebateConfig` to `AppSettings`, create `002_debate_columns.sql` migration, add `save_debate()` / `get_debates_for_ticker()` / `DebateRow` to repository
- [ ] **Task 2: Agent infrastructure** — Create `agents/CLAUDE.md`, `model_config.py` (`build_ollama_model`, `_resolve_host`), `_parsing.py` (`DebateDeps`, `DebateResult` dataclasses), `__init__.py` re-exports
- [ ] **Task 3: Bull, Bear, and Risk agents** — Create all three PydanticAI agent modules with system prompts, output validators, and `<think>` tag rejection
- [ ] **Task 4: Orchestrator and fallback** — Create `orchestrator.py` with `run_debate()`, `build_market_context()`, sequential agent coordination, error handling, and data-driven fallback synthesis
- [ ] **Task 5: CLI debate command and rendering** — Add `debate` command to `cli/commands.py` with `--history` and `--fallback-only` flags, add Rich panel rendering for debate output
- [ ] **Task 6: Unit and integration tests** — ~100 tests: agent tests with `TestModel`, orchestrator tests (success/timeout/fallback), parsing tests, config tests, repository tests, CLI tests, integration test

## Dependencies

### Internal (All Complete)
- **Phase 1 Models**: `MarketContext`, `AgentResponse`, `TradeThesis`, `OptionContract`
- **Phase 6 Data**: `Repository`, `Database`, migration runner
- **Phase 7 Scan**: `TickerScore` with `IndicatorSignals` and recommended contracts
- **Phase 8 CLI**: `cli/commands.py` for new `debate` command

### External (Already Installed)
- `pydantic-ai >= 1.62.0`: Agent framework
- `ollama >= 0.6.1`: Local LLM access
- User must pull model: `ollama pull llama3.1:8b`

## Success Criteria (Technical)

- `options-arena debate AAPL` completes in < 120s on CPU with Llama 3.1 8B
- Data-driven fallback produces valid `TradeThesis` when Ollama is down (confidence = 0.3)
- All three agents cite specific contracts, strikes, and Greeks from `MarketContext`
- `ai_theses` table populated with full debate transcript + metadata
- `--history` shows past debates; `--fallback-only` bypasses Ollama
- `TestModel` tests pass without Ollama installed (~100 tests)
- `ruff check .`, `pytest tests/ -v`, `mypy src/ --strict` — all green
- Existing 1,086 tests remain passing (zero regressions)
- Zero architecture boundary violations

## Tasks Created

- [ ] #64 - Config, migration, and repository (parallel: true)
- [ ] #65 - Agent infrastructure (parallel: true)
- [ ] #67 - Bull, Bear, and Risk agents (parallel: false, depends: #65)
- [ ] #63 - Orchestrator and fallback (parallel: false, depends: #64, #67)
- [ ] #66 - CLI debate command and rendering (parallel: false, depends: #63)
- [ ] #68 - Unit and integration tests (parallel: false, depends: all)

Total tasks: 6
Parallel tasks: 2 (#64, #65)
Sequential tasks: 4 (#67 → #63 → #66 → #68)

## Estimated Effort

- **6 tasks**, dependency-ordered
- Tasks 1-2 parallelizable (infrastructure)
- Task 3 depends on task 2 (agents need infrastructure)
- Task 4 depends on tasks 1 and 3 (orchestrator needs config + agents)
- Task 5 depends on task 4 (CLI needs orchestrator)
- Task 6 depends on all (tests span all modules)
- ~100 new tests, ~1,500 lines of new code, ~50 lines modified in existing files
