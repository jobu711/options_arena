---
name: ai-agency-ml-tools
status: backlog
created: 2026-03-17T14:37:45Z
progress: 0%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 8
dependencies: [ai-agency-desk-foundation, ai-agency-advisor-routing, ai-agency-all-desks]
parallelizable_with: [ai-agency-weight-tuning, ai-agency-prompt-ab, ai-agency-strategy-mining, ai-agency-analysis-tools]
github: https://github.com/jobu711/options_arena/issues/625
---

# Epic 8: ML Desk Tools

## Overview

Wrap 4 statistical/ML indicator functions as `FunctionToolset` tools with conditional registration. 2 tools require `[ml]` optional extra (`arch`, `statsmodels`) and are omitted from toolsets when not installed. 2 tools are pure math but grouped here thematically. Register on target desks (Trend, Volatility, Fundamental, Risk, Research).

## Architecture Decisions

- **Conditional registration**: ML tools registered via `try/except ImportError` in toolset builders — tool omitted (not no-op) when deps missing
- **Graceful degradation**: Desks work with fewer tools when `[ml]` not installed
- `<<<AVAILABLE_TOOLS>>>` prompt block dynamically lists only registered tools
- `compute_macro_regime` and `hurst_exponent` have NO optional deps (pure math) but are grouped here for thematic coherence
- GARCH expects returns in `%` form — tool wrapper computes `np.log(price[t]/price[t-1]) * 100`
- Regime functions return NamedTuples — tool formats as strings, doesn't serialize

## Technical Approach

### Tool Wrappers (in `agents/_toolsets.py`)

| Tool | Source | Target Desks | Optional Dep | Notes |
|------|--------|-------------|-------------|-------|
| `compute_garch_forecast_tool` | `indicators/vol_forecast.py` | Volatility, Research | `arch`, `statsmodels` | Compute % returns from OHLCV, format annualized vol forecast |
| `compute_markov_regime_tool` | `indicators/regime_ml.py` | Trend, Risk | `statsmodels` | Compute returns from OHLCV, format regime label + probabilities |
| `compute_macro_regime_tool` | `indicators/macro.py` | Fundamental, Risk, Research | None | Pass FRED context kwargs, format regime + confidence |
| `compute_hurst_exponent_tool` | `indicators/hurst.py` | Trend, Research | None | Fetch close Series, format H value + interpretation |

### Conditional Registration Pattern

```python
def build_volatility_toolset() -> FunctionToolset:
    toolset = FunctionToolset()
    # ... base + analysis tools (always) ...
    try:
        from options_arena.indicators.vol_forecast import compute_garch_forecast
        toolset.tool(compute_garch_forecast_tool)
    except ImportError:
        pass  # [ml] not installed — vol desk works without GARCH
    return toolset
```

### Dynamic Prompt Block

```python
def render_available_tools(toolset: FunctionToolset) -> str:
    """Generate <<<AVAILABLE_TOOLS>>> block from registered tools."""
    tool_names = [t.name for t in toolset.tools]
    return "<<<AVAILABLE_TOOLS>>>\n" + "\n".join(f"- {name}" for name in tool_names) + "\n<<<END_AVAILABLE_TOOLS>>>"
```

### Toolset Builder Updates
- Update `build_trend_toolset()` — add `compute_hurst_exponent_tool` (always) + `compute_markov_regime_tool` (conditional)
- Update `build_volatility_toolset()` — add `compute_garch_forecast_tool` (conditional)
- Update `build_fundamental_toolset()` — add `compute_macro_regime_tool` (always)
- Update `build_risk_toolset()` — add `compute_macro_regime_tool` (always) + `compute_markov_regime_tool` (conditional)
- Update `build_research_toolset()` — add all 4 (2 always + 2 conditional)

## Task Breakdown Preview

- [ ] GARCH forecast + Markov regime tool wrappers (high complexity — guarded imports, % returns) + tests
- [ ] Macro regime + Hurst exponent tool wrappers (low-medium complexity) + tests
- [ ] Conditional registration in all toolset builders + `<<<AVAILABLE_TOOLS>>>` prompt block
- [ ] Toolset registration tests (mock ImportError, verify graceful degradation)

## Dependencies

- Epics 1-3 (all desks online with base tools)
- `indicators/vol_forecast.py`, `regime_ml.py`, `macro.py`, `hurst.py`
- `[ml]` optional extra (arch, statsmodels) — for conditional tools only

## Success Criteria

- All 4 tools return correctly formatted strings for valid inputs
- GARCH and Markov tools gracefully absent when `[ml]` not installed
- Toolset builds successfully with and without `[ml]` extra
- `<<<AVAILABLE_TOOLS>>>` prompt block accurately reflects registered tools
- Macro regime and Hurst always registered (no optional deps)
- ~25+ new tests (including ImportError mocking)

## Estimated Effort

3-4 issues, ~2 implementation sessions

## Tasks Created
- [ ] #626 - GARCH Forecast + Markov Regime Tool Wrappers (parallel: true)
- [ ] #627 - Macro Regime + Hurst Exponent Tool Wrappers (parallel: true)
- [ ] #628 - Conditional Registration in Toolset Builders (parallel: false)
- [ ] #629 - Integration Tests — Toolset Degradation and End-to-End (parallel: false)

Total tasks: 4
Parallel tasks: 2 (#626, #627)
Sequential tasks: 2 (#628 depends on #626+#627, #629 depends on #626+#627+#628)
Estimated total effort: 15 hours

## Test Coverage Plan
Total test files planned: 4
Total test cases planned: ~50 (11 + 12 + 13 + 15)
