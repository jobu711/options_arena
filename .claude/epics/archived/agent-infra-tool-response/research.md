# Research: agent-infra-tool-response

## PRD Summary

Wrap all 23 desk agent tools in `agents/_toolsets.py` with a structured `ToolResponse[T]`
generic Pydantic model that includes status, summary, data payload, and recovery guidance
(`next_actions`). Tools keep returning `str` via `model_dump_json()` — zero change to
PydanticAI tool signatures. Update desk recommendation prompts to reference the format.
Add `ToolStatus` StrEnum (SUCCESS, WARNING, ERROR).

## Relevant Existing Modules

- `agents/_toolsets.py` (1816 lines) — All 23 tool functions + 8 toolset builders. Primary refactor target.
- `agents/_desk_deps.py` — `DeskDeps` dataclass with `tools_used: list[str]` tracking.
- `agents/prompts/recommend_*.py` (6 files) — Recommendation prompts that need ToolResponse format section.
- `agents/prompts/synthesis.py` — Synthesis prompt; synthesis tools also need ToolResponse treatment.
- `models/enums.py` — Existing `StrEnum` patterns (`VolRegime`, `RuleStatus`, etc.) to follow for `ToolStatus`.
- `models/recommendation.py` — `DomainAssessment` hierarchy, `PositionRecommendation`, `RecommendationResult`.
- `models/__init__.py` — Re-export index; needs `ToolResponse` + `ToolStatus` added.
- `models/_validators.py` — Shared validator helpers (`validate_unit_interval`, `validate_non_empty_list`).

## Existing Patterns to Reuse

### Never-Raises Tool Contract
All 23 tools already follow try/except → return string pattern. `ToolResponse` wraps
both success and error paths without changing this contract.

### StrEnum Pattern (for ToolStatus)
```python
class VolRegime(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    ...
```
`ToolStatus` follows same lowercase-value convention.

### Frozen Pydantic Model Pattern
`DomainAssessment`, `DeskResponse`, `Quote` all use `ConfigDict(frozen=True)`.
`ToolResponse` should follow this pattern.

### tools_used Tracking
`ctx.deps.tools_used.append(tool_name)` called on ALL paths (success, validation, error).
ToolResponse refactoring must preserve this pattern exactly.

### Ticker Validation
`_validate_ticker(ticker)` helper returns error string or `None`. ToolResponse must wrap
validation failures as `status=ERROR` with appropriate `next_actions`.

### Re-export Pattern
`models/__init__.py` re-exports all public types. `ToolResponse` and `ToolStatus` must be added.

## Existing Code to Extend

### `agents/_toolsets.py` — All 23 Tool Functions

**Market Data Tools (5):**
1. `fetch_quote` — Quote (price, bid/ask, volume, 52W range)
2. `fetch_vol_surface_slice` — IV by strike/expiry (up to 10 contracts)
3. `compute_iv_for_strike` — Closest strike IV details
4. `fetch_correlation` — Pairwise return correlations (max 5 tickers)
5. `fetch_related_ohlcv` — Last 5 OHLCV bars

**Options/Flow Tools (3):**
6. `fetch_chain_summary` — Call/put totals, OI, volume, ratios
7. `fetch_unusual_activity` — Contracts with volume > 3x OI (top 5)
8. `fetch_portfolio_exposure` — Historical recommended contracts (limit 10)

**Fundamental/Technical Tools (5):**
9. `compute_indicator_on_demand` — RSI, MACD, SMA alignment, ADX
10. `fetch_earnings_history` — Sector, industry, market cap, dividend, next earnings
11. `fetch_sector_comparison` — Fundamentals with sector context
12. `fetch_debate_history` — Prior AI debate history (limit 3)
13. `compute_composite_valuation_tool` — Multi-methodology valuation (DCF, DDM, etc.)

**Risk & Position Sizing Tools (5):**
14. `compute_position_size_tool` — Volatility-regime-aware allocation
15. `compute_correlation_matrix_tool` — Pairwise correlation matrix (max 5 tickers)
16. `compute_risk_adjusted_metrics_tool` — Sharpe, Sortino, max drawdown
17. `compute_hv_yang_zhang_tool` — Yang-Zhang HV estimator
18. `compute_macro_regime_tool` — Yield spread, unemployment, Fed funds → macro classification

**ML Tools (3 conditional on `[ml]` extra):**
19. `compute_garch_forecast_tool` — GARCH(1,1) volatility forecast (requires `arch`)
20. `compute_markov_regime_tool` — 2/3-regime Markov-switching (requires `statsmodels`)
21. `compute_hurst_exponent_tool` — R/S analysis → trending/mean-reverting

**Synthesis Tools (2 lightweight, pre-fetched data):**
22. `synth_fetch_current_quote` — MarketContext snapshot
23. `synth_fetch_chain_summary` — Contract list summary with Greeks

### `agents/prompts/recommend_*.py` — 6 Recommendation Prompts

| File | Prompt Constant | Output Model |
|------|----------------|--------------|
| `recommend_trend.py` | `RECOMMEND_TREND_PROMPT` | `TrendAssessment` |
| `recommend_volatility.py` | `RECOMMEND_VOLATILITY_PROMPT` | `VolatilityAssessment` |
| `recommend_flow.py` | `RECOMMEND_FLOW_PROMPT` | `FlowAssessment` |
| `recommend_fundamental.py` | `RECOMMEND_FUNDAMENTAL_PROMPT` | `FundamentalAssessment` |
| `recommend_risk.py` | `RECOMMEND_RISK_PROMPT` | `RiskDeskAssessment` |
| `recommend_contrarian.py` | `RECOMMEND_CONTRARIAN_PROMPT` | `ContrarianAssessment` |

Note: Research desk has NO recommendation prompt yet (not in unified recommendation phase).
The epic says 7 prompts but only 6 exist. Research recommendation will come in a later epic.

### Prompt Structure (All 6 Identical Template)
```
- VERSION header
- Task description
- Required output fields (JSON schema)
- Domain-specific fields with calibration guidance
- Analysis guidelines (cite data, min 3 key_factors, min 2 risks)
- PROMPT_RULES_APPENDIX (appended at end)
```

Each prompt needs a new section describing the ToolResponse JSON format and how to
interpret `status`, `next_actions` when tool results indicate partial or missing data.

### `models/tool_response.py` — NEW FILE

No existing `ToolResponse` or `ToolStatus` in codebase (grep confirmed). Safe to create.
No existing `Generic[T]` Pydantic models in the project — this would be the first.

## Potential Conflicts

### Generic[T] Novelty
The codebase has zero `Generic[T]` Pydantic models. Introducing `ToolResponse[T]` adds
a new pattern. **Mitigation**: Keep it simple — Pydantic v2 natively supports generics.
The `T` parameter is for typed payloads serialized to JSON string. Agents see the JSON,
not the Python type.

### Synthesis Tools Use `RunContext[object]` Not `RunContext[DeskDeps]`
The 2 synthesis tools use `ctx: RunContext[object]` with attribute access (`ctx.deps.context`),
not `RunContext[DeskDeps]`. They do NOT call `ctx.deps.tools_used.append()`.
**Mitigation**: Synthesis tools still get ToolResponse wrapping but skip `tools_used` tracking
(matching current behavior). Alternatively, if SynthesisDeps gets `tools_used`, add tracking.

### Prompt Token Budget
Adding a ToolResponse format section to 6 prompts increases token count. Current prompts
are <8000 chars each (module constraint).
**Mitigation**: Keep the section brief (~200-300 chars). Example:
```
## Tool Response Format
Tools return JSON: {"status": "success|warning|error", "summary": "...", "data": ..., "next_actions": [...]}
When status is "error" or "warning", follow the next_actions guidance to adjust your assessment.
```

### No `_sanitize_error()` Helper
Current tools use generic error messages (`"Error: could not fetch X for {ticker}"`).
The epic proposes `_sanitize(exc)` for sanitized exception details.
**Mitigation**: Create `_sanitize_error(exc: Exception, max_len: int = 120) -> str` helper
in `_toolsets.py`. Truncate, strip credentials, extract meaningful message.

## Open Questions

1. **Research recommendation prompt**: Epic says 7 prompts but only 6 exist. Should we
   create `recommend_research.py` in this epic or defer to a later epic?
   **Recommendation**: Defer — out of scope for this mechanical refactoring epic.

2. **Synthesis tools**: The 2 synthesis tools use `RunContext[object]`, not `DeskDeps`.
   Should they get ToolResponse treatment? The PRD lists them in the 23 tools.
   **Recommendation**: Yes — include them. ToolResponse is beneficial regardless of deps type.

3. **`data` field typing**: Should `ToolResponse[T]` use a generic `T` for the data field,
   or should `data` be `str | None` (pre-formatted text)?
   **Recommendation**: Use `Generic[T]` for type safety, but in practice most tools will use
   `ToolResponse[str]` or `ToolResponse[dict[str, Any]]`. The key value is in `status`,
   `summary`, and `next_actions` — not the data field's type.

4. **WARNING status criteria**: What constitutes "partial data"? Example: fetch_correlation
   returns 3 of 5 requested tickers' correlations. Should this be WARNING?
   **Recommendation**: Define per-tool criteria. WARNING when core data is available but
   some enrichment is missing. ERROR when the primary data request failed entirely.

## Recommended Architecture

### New Model (`models/tool_response.py`)
```python
class ToolStatus(StrEnum):
    SUCCESS = "success"
    WARNING = "warning"  # partial data available
    ERROR = "error"       # no data, agent should adjust

T = TypeVar("T")

class ToolResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)
    status: ToolStatus
    summary: str                         # one-line for agent context window
    data: T | None = None                # typed payload (serialized to JSON)
    next_actions: list[str] = Field(default_factory=list)  # recovery guidance
```

### Refactoring Pattern (per tool)
```python
# BEFORE
async def fetch_quote(ctx: RunContext[DeskDeps], ticker: str) -> str:
    tool_name = "fetch_quote"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return err
    try:
        quote = await ctx.deps.market_data.fetch_quote(ticker)
        lines = [f"Quote for {ticker}:", ...]
        ctx.deps.tools_used.append(tool_name)
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("fetch_quote failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return f"Error: could not fetch quote for {ticker}"

# AFTER
async def fetch_quote(ctx: RunContext[DeskDeps], ticker: str) -> str:
    tool_name = "fetch_quote"
    if err := _validate_ticker(ticker):
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=err,
            next_actions=["reduce confidence", "note data gap"],
        ).model_dump_json()
    try:
        quote = await ctx.deps.market_data.fetch_quote(ticker)
        lines = [f"Quote for {ticker}:", ...]
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary=f"{ticker}: ${quote.price} bid={quote.bid} ask={quote.ask}",
            data="\n".join(lines),
            next_actions=["assess current price vs 52W range", "note bid-ask spread"],
        ).model_dump_json()
    except Exception as exc:
        logger.debug("fetch_quote failed for %s: %s", ticker, exc)
        ctx.deps.tools_used.append(tool_name)
        return ToolResponse[str](
            status=ToolStatus.ERROR,
            summary=f"Quote unavailable for {ticker}: {_sanitize_error(exc)}",
            next_actions=["set price fields to None", "reduce confidence by 0.1", "note data gap in risks"],
        ).model_dump_json()
```

### Task Batching Strategy
Refactor tools in 5 batches by functional group:
1. **Model + enum + helper**: `ToolResponse[T]`, `ToolStatus`, `_sanitize_error()`
2. **Market data tools** (5): fetch_quote, fetch_vol_surface_slice, compute_iv_for_strike, fetch_correlation, fetch_related_ohlcv
3. **Options/flow + fundamental tools** (8): fetch_chain_summary, fetch_unusual_activity, fetch_portfolio_exposure, compute_indicator_on_demand, fetch_earnings_history, fetch_sector_comparison, fetch_debate_history, compute_composite_valuation_tool
4. **Risk + ML tools** (8): compute_position_size_tool, compute_correlation_matrix_tool, compute_risk_adjusted_metrics_tool, compute_hv_yang_zhang_tool, compute_macro_regime_tool, compute_garch_forecast_tool, compute_markov_regime_tool, compute_hurst_exponent_tool
5. **Synthesis tools + prompts + tests** (2 tools + 6 prompts): synth_fetch_current_quote, synth_fetch_chain_summary, all 6 recommend_*.py updates, comprehensive tests

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/agents/test_toolsets.py` — main toolset tests with `_make_mock_ctx()`, `_make_deps()` helpers
- `tests/unit/agents/test_*_desk.py` — 7 desk agent tests
- `tests/unit/agents/test_*_desk_recommend.py` — 6 recommendation agent tests
- `tests/unit/agents/test_*_tools.py` — specific tool tests (ml_tools, analysis_tools)
- `tests/integration/test_all_desks_integration.py` — integration tests

### New Test Approach
```python
# For each of 23 tools:
async def test_fetch_quote_success_returns_tool_response():
    result = await fetch_quote(ctx, "AAPL")
    parsed = json.loads(result)
    assert parsed["status"] == "success"
    assert "AAPL" in parsed["summary"]
    assert parsed["data"] is not None
    assert len(parsed["next_actions"]) > 0

async def test_fetch_quote_error_returns_tool_response():
    deps.market_data.fetch_quote = AsyncMock(side_effect=Exception("timeout"))
    result = await fetch_quote(ctx, "AAPL")
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert parsed["data"] is None
    assert len(parsed["next_actions"]) > 0
    assert "fetch_quote" in deps.tools_used

async def test_fetch_quote_invalid_ticker():
    result = await fetch_quote(ctx, "INVALID!!!")
    parsed = json.loads(result)
    assert parsed["status"] == "error"
```

### Test Count Estimate
- 23 tools × 2-3 test cases each = ~50-70 new tests
- 1 model test file for `ToolResponse` + `ToolStatus` = ~10-15 tests
- Total: ~60-85 new tests

## Estimated Complexity

**Medium** — Mechanical refactoring with clear pattern, but touches all 23 tools (1816 lines)
plus 6 recommendation prompts. Risk is in consistency (applying the same pattern correctly
23 times with tool-specific `next_actions` for each failure mode).

- **New code**: ~100 LOC (model + enum + helper)
- **Modified code**: ~600-800 LOC (23 tools in _toolsets.py)
- **Prompt changes**: ~300 chars × 6 prompts
- **Tests**: ~300-400 LOC (new test cases)
- **Tasks**: 5 (model, 3 tool batches, prompts+tests)
