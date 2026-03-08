# Research: anthropic-api

## PRD Summary

Add Claude/Anthropic as an alternative LLM debate provider alongside existing Groq. Users select provider via `--provider` CLI flag (default: `groq`). When `anthropic` is selected, all debate agents use Claude with optional extended thinking. PydanticAI's `Model` abstraction already makes agents provider-agnostic — `build_debate_model()` returns a `Model` interface, and all `agent.run(model=model)` calls work regardless of backend.

## Relevant Existing Modules

| Module | Relevance |
|--------|-----------|
| `models/enums.py` | Add `LLMProvider` StrEnum — follows pattern of 19 existing StrEnums |
| `models/config.py` | Extend `DebateConfig` (5 new fields) + `ServiceConfig` (1 new field) |
| `models/__init__.py` | Re-export `LLMProvider` |
| `agents/model_config.py` | Refactor `build_debate_model()` from Groq-only to multi-provider dispatcher |
| `agents/orchestrator.py` | Conditional `ModelSettings` for extended thinking (lines ~527-528, ~1487-1488) |
| `services/health.py` | Add `check_anthropic()` following exact `check_groq()` pattern |
| `cli/commands.py` | Add `--provider` option to `debate` command |
| `api/routes/debate.py` | **No changes needed** — already uses `settings.debate` transparently |
| `pyproject.toml` | Add `anthropic` dependency for pydantic-ai provider support |

## Existing Patterns to Reuse

### 1. API Key Resolution (model_config.py)
```python
def _resolve_api_key(config: DebateConfig) -> str | None:
    if config.api_key is not None:
        return config.api_key.get_secret_value()
    return os.environ.get("GROQ_API_KEY")
```
Replicate for Anthropic: `config.anthropic_api_key > ANTHROPIC_API_KEY env > None`.

### 2. Health Check (services/health.py — check_groq)
- Resolve API key from `ServiceConfig > env > None`
- Hit API endpoint with auth header + `asyncio.wait_for(timeout=10.0)`
- Measure latency via `time.monotonic()`
- Return `HealthStatus(service_name=..., available=..., latency_ms=..., error=...)`
- Never raises — all exceptions caught

### 3. Config Override (cli/commands.py)
```python
config = settings.debate
if fallback_only:
    config = settings.debate.model_copy(update={...})
```
Same pattern for `--provider` override.

### 4. TestModel Mocking (tests/unit/agents/)
```python
models.ALLOW_MODEL_REQUESTS = False  # module-level
with bull_agent.override(model=TestModel()):
    result = await bull_agent.run("test", deps=deps)
```

### 5. httpx Mocking (tests/unit/services/test_health.py)
```python
mock_response = httpx.Response(status_code=200, json={...}, request=httpx.Request("GET", "test"))
service._client.get = AsyncMock(return_value=mock_response)
```

## Existing Code to Extend

| File | What Exists | What Changes |
|------|-------------|-------------|
| `models/enums.py` | 19 StrEnums (lines 1-213) | Add `LLMProvider` after `GICSSector` |
| `models/config.py` | `DebateConfig` (lines 169-264) with Groq fields, validators | Add `provider`, `anthropic_model`, `anthropic_api_key`, `enable_extended_thinking`, `thinking_budget_tokens` fields + validator |
| `models/config.py` | `ServiceConfig` (lines 135-147) with `groq_api_key` | Add `anthropic_api_key: SecretStr \| None = None` |
| `agents/model_config.py` | `build_debate_model()` + `_resolve_api_key()` (57 lines total) | Refactor into dispatcher + `_build_groq_model()` + `_build_anthropic_model()` + `_resolve_anthropic_api_key()` |
| `agents/orchestrator.py` | `settings = ModelSettings(temperature=config.temperature)` at 2 call sites | Add conditional for `enable_extended_thinking` (Anthropic requires `temperature=1.0` + `anthropic_thinking` dict) |
| `services/health.py` | `check_groq()` (lines 112-218) + `check_all()` | Add `check_anthropic()` + include in `check_all()` |
| `cli/commands.py` | `debate()` command with `--export`, `--fallback-only`, `--batch` | Add `--provider` Typer Option |

## Potential Conflicts

### None Breaking
- Default provider is `groq` — existing behavior completely unchanged
- All `agent.run(model=model)` call sites already use the `Model` base type
- `DebateConfig` is NOT frozen — `model_copy(update={...})` works
- API routes use `settings.debate` transparently — no API changes needed

### Minor Considerations
1. **Extended thinking overrides temperature**: Anthropic requires `temperature=1.0` when thinking is enabled, which silently ignores user's `config.temperature`. Document in help text.
2. **Agent-level `model_settings`**: Bull/bear/risk agents have `model_settings=ModelSettings(extra_body={"num_ctx": 8192})` at init — this is Groq-specific (`num_ctx`). For Anthropic, this key is ignored (no harm, Anthropic just ignores unknown body params).
3. **pydantic-ai anthropic extras**: Need to verify if `pydantic-ai>=1.62` auto-installs `anthropic` SDK or requires explicit dependency. Context7 query recommended.

## Open Questions

1. **pydantic-ai[anthropic] extras**: Does `pydantic-ai>=1.62` bundle `AnthropicModel`/`AnthropicProvider` out of the box, or do we need `uv add anthropic` separately? (Verify via Context7 or `uv pip show`)
2. **Anthropic API models endpoint**: PRD specifies `GET /v1/models` with `x-api-key` header for health check. Verify this endpoint exists and returns 200 for valid keys.
3. **Web UI provider selection**: PRD explicitly scopes this to CLI only (`--provider` flag). Future work could add a provider dropdown to the Vue SPA debate form.

## Recommended Architecture

### Implementation Flow
```
Step 1: models/ — LLMProvider enum, DebateConfig fields, ServiceConfig field, re-exports
Step 2: agents/model_config.py — Multi-provider dispatcher
Step 3: agents/orchestrator.py — Conditional ModelSettings for extended thinking
Step 4: services/health.py — check_anthropic() method
Step 5: cli/commands.py — --provider flag + config override
Step 6: pyproject.toml — Add anthropic dependency
Step 7: Tests for all above
Step 8: Verification (ruff + pytest + mypy)
```

### Key Design Decisions
- **Single `build_debate_model()` entry point** dispatches to `_build_groq_model()` or `_build_anthropic_model()` — keeps call sites unchanged
- **Extended thinking handled in orchestrator**, not model_config — because `ModelSettings` is passed per-run, not at model construction
- **Health check always runs** for Anthropic (like Groq) — returns unavailable if no key configured, never raises

## Test Strategy Preview

### Existing Test Infrastructure
- `tests/unit/agents/test_model_config.py` (87 lines) — already covers Groq model building
- `tests/unit/models/test_config.py` — covers AppSettings, env vars, validators
- `tests/unit/services/test_health.py` — covers `check_groq()` with httpx mocks

### New Tests Required (14 total)
| Test File | Tests | Description |
|-----------|-------|-------------|
| `tests/unit/agents/test_model_config.py` | 5 | Anthropic model building, API key resolution, missing key error, provider dispatch, enum values |
| `tests/unit/models/test_config.py` | 3 | Default provider is groq, Anthropic field defaults, thinking_budget_tokens validator |
| `tests/unit/services/test_health.py` | 4 | Anthropic no key, success (mocked), invalid key 401, included in check_all |
| `tests/unit/agents/test_orchestrator.py` | 1 | Extended thinking ModelSettings construction |
| `tests/integration/` | 1 | Full debate with Anthropic (requires ANTHROPIC_API_KEY, @pytest.mark.integration) |

### Mocking Strategies
- **Model building**: Monkeypatch `os.environ` for API key tests; no real API calls
- **Health checks**: `AsyncMock` on `service._client.get` with fake `httpx.Response`
- **Orchestrator**: `TestModel` override — already used extensively in existing tests
- **Config**: Direct construction with explicit field values

## Estimated Complexity

**Size: Small (S)**

**Justification:**
- 10 production files modified (mostly additive — new fields, new functions, new method)
- 0 new files (all changes extend existing modules)
- 3 test files extended
- No database migrations
- No breaking changes
- No new async patterns — all existing patterns reused
- Architecture already supports multi-provider via PydanticAI `Model` abstraction
- Estimated ~200 lines of new production code, ~300 lines of new tests
