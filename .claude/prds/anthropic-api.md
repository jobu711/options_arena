# Plan: Add Claude/Anthropic as Debate Provider

## Context

Options Arena currently uses Groq (free tier, Llama 3.3 70B) as its sole LLM provider for the AI debate system. Adding Claude as an alternative provider gives users access to higher-quality reasoning when they want it, while keeping Groq as the free default. PydanticAI already abstracts the model layer — agents use `model=None` at init and receive a `Model` at `run()` time, so the orchestrator is already provider-agnostic.

## Approach

Add a `--provider` CLI flag (`groq` | `anthropic`) that routes all debate agents through the selected provider. Default stays `groq` (free). When `anthropic` is selected, all agents use Claude with optional extended thinking.

## Files to Modify

| File | Change |
|------|--------|
| `src/options_arena/models/enums.py` | Add `LLMProvider` StrEnum (`groq`, `anthropic`) |
| `src/options_arena/models/config.py` | Add Anthropic fields to `DebateConfig` + `anthropic_api_key` to `ServiceConfig` |
| `src/options_arena/models/__init__.py` | Re-export `LLMProvider` |
| `src/options_arena/agents/model_config.py` | Extend `build_debate_model()` to support Anthropic via `AnthropicModel` |
| `src/options_arena/services/health.py` | Add `check_anthropic()` health check |
| `src/options_arena/cli/commands.py` | Add `--provider` option to `debate` command |
| `src/options_arena/api/routes/debate.py` | No changes needed — already uses `settings.debate` which will carry the provider |
| `pyproject.toml` | Add `anthropic` extra to `pydantic-ai` dependency |

## New Files

None.

## Step-by-Step Implementation

### Step 1: Add `LLMProvider` enum
**File**: `src/options_arena/models/enums.py`

```python
class LLMProvider(StrEnum):
    GROQ = "groq"
    ANTHROPIC = "anthropic"
```

Re-export from `models/__init__.py`.

### Step 2: Extend `DebateConfig`
**File**: `src/options_arena/models/config.py`

Add fields to `DebateConfig`:
```python
provider: LLMProvider = LLMProvider.GROQ
anthropic_model: str = "claude-sonnet-4-5-20250929"
anthropic_api_key: SecretStr | None = None
enable_extended_thinking: bool = False
thinking_budget_tokens: int = 5000
```

Add validator for `thinking_budget_tokens` (must be in [1024, 128000]).

Also add `anthropic_api_key: SecretStr | None = None` to `ServiceConfig` for the health check (mirrors `groq_api_key` pattern).

Env var overrides:
- `ARENA_DEBATE__PROVIDER=anthropic`
- `ARENA_DEBATE__ANTHROPIC_API_KEY=sk-ant-...`
- `ARENA_DEBATE__ANTHROPIC_MODEL=claude-sonnet-4-5-20250929`
- `ARENA_DEBATE__ENABLE_EXTENDED_THINKING=true`
- `ARENA_SERVICE__ANTHROPIC_API_KEY=sk-ant-...` (for health check)
- Also check `ANTHROPIC_API_KEY` env var as fallback (mirrors `GROQ_API_KEY` pattern)

### Step 3: Extend `build_debate_model()`
**File**: `src/options_arena/agents/model_config.py`

Add Anthropic model builder alongside existing Groq builder:

```python
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

def build_debate_model(config: DebateConfig) -> Model:
    if config.provider == LLMProvider.ANTHROPIC:
        return _build_anthropic_model(config)
    return _build_groq_model(config)

def _build_groq_model(config: DebateConfig) -> Model:
    # existing logic (extract from current build_debate_model)
    ...

def _build_anthropic_model(config: DebateConfig) -> Model:
    api_key = _resolve_anthropic_api_key(config)
    if api_key is None:
        raise ValueError(
            "Anthropic API key required. Set ARENA_DEBATE__ANTHROPIC_API_KEY "
            "or ANTHROPIC_API_KEY env var."
        )
    provider = AnthropicProvider(api_key=api_key)
    return AnthropicModel(config.anthropic_model, provider=provider)

def _resolve_anthropic_api_key(config: DebateConfig) -> str | None:
    if config.anthropic_api_key is not None:
        return config.anthropic_api_key.get_secret_value()
    return os.environ.get("ANTHROPIC_API_KEY")
```

### Step 4: Handle extended thinking in orchestrator
**File**: `src/options_arena/agents/orchestrator.py`

In `_run_agents()`, build `ModelSettings` conditionally:

```python
settings = ModelSettings(temperature=config.temperature)

# Extended thinking for Anthropic (Claude Sonnet/Opus)
if config.provider == LLMProvider.ANTHROPIC and config.enable_extended_thinking:
    settings = ModelSettings(
        temperature=1.0,  # Anthropic requires temperature=1 with thinking
        anthropic_thinking={
            "type": "enabled",
            "budget_tokens": config.thinking_budget_tokens,
        },
    )
```

Note: Anthropic requires `temperature=1.0` when extended thinking is enabled. This is a documented constraint.

The `model` variable is already typed as `Model` and passed to all `agent.run()` calls — no other changes needed in the orchestrator.

### Step 5: Add health check for Anthropic
**File**: `src/options_arena/services/health.py`

Add `check_anthropic()` method following the exact `check_groq()` pattern:
- Resolve API key: `ServiceConfig.anthropic_api_key` > `ANTHROPIC_API_KEY` env > unavailable
- Hit `https://api.anthropic.com/v1/models` with `x-api-key` header + `anthropic-version: 2023-06-01`
- Return `HealthStatus(service_name="anthropic", ...)`
- Add to `check_all()` tasks list

### Step 6: Add `--provider` CLI flag
**File**: `src/options_arena/cli/commands.py`

Add to `debate()` command signature:
```python
provider: LLMProvider = typer.Option(
    LLMProvider.GROQ, "--provider", help="LLM provider: groq (free) or anthropic"
),
```

In `_debate_async()` and `_batch_async()`, override config:
```python
settings = AppSettings()
if provider != settings.debate.provider:
    settings.debate.provider = provider
```

Note: `DebateConfig` is NOT frozen (it's a plain BaseModel), so field assignment works.

### Step 7: Add `pydantic-ai[anthropic]` dependency
**File**: `pyproject.toml`

The `pydantic-ai` package bundles Anthropic support. Verify it works with current version (>=1.62.0). If the anthropic SDK isn't auto-installed, add explicitly:
```
uv add anthropic
```

## Testing Strategy

### Unit Tests (new test file: `tests/unit/agents/test_model_config.py`)
1. `test_build_groq_model` — existing behavior preserved
2. `test_build_anthropic_model` — returns `AnthropicModel` with correct config
3. `test_anthropic_missing_api_key_raises` — ValueError with clear message
4. `test_resolve_anthropic_api_key_priority` — config > env > None
5. `test_provider_enum_values` — `LLMProvider` has exactly 2 members

### Unit Tests (extend `tests/unit/models/test_config.py`)
6. `test_debate_config_defaults_provider_groq` — default provider is groq
7. `test_debate_config_anthropic_fields` — anthropic_model, api_key, thinking defaults
8. `test_thinking_budget_validator` — rejects out-of-range values

### Unit Tests (extend `tests/unit/services/test_health.py`)
9. `test_check_anthropic_no_api_key` — returns unavailable
10. `test_check_anthropic_success` — mocked HTTP response returns available
11. `test_check_anthropic_invalid_key` — 401 → unavailable
12. `test_check_all_includes_anthropic` — verify anthropic in results

### Integration Test (mark with `@pytest.mark.integration`)
13. `test_debate_with_anthropic` — requires `ANTHROPIC_API_KEY` env var

### Orchestrator Tests (extend existing)
14. `test_extended_thinking_settings` — verify ModelSettings built correctly when enabled

## Verification

```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

Manual verification:
```bash
# Groq (existing, should work unchanged)
options-arena debate AAPL

# Anthropic
ANTHROPIC_API_KEY=sk-ant-... options-arena debate AAPL --provider anthropic

# Health check shows both providers
options-arena health
```
