---
name: ai-agency-analysis-tools
status: completed
created: 2026-03-17T14:37:45Z
progress: 100%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 7
dependencies: [ai-agency-desk-foundation, ai-agency-advisor-routing, ai-agency-all-desks]
parallelizable_with: [ai-agency-weight-tuning, ai-agency-prompt-ab, ai-agency-strategy-mining, ai-agency-ml-tools]
github: https://github.com/jobu711/options_arena/issues/619
---

# Epic 7: Analysis & HV Desk Tools

## Overview

Wrap 5 pure-math functions from `analysis/` and `indicators/hv_estimators` as `FunctionToolset` tools. Register on target desks (Fundamental, Risk, Volatility, Research). No optional dependencies — these tools are always available.

## Architecture Decisions

- Tools are thin adapters: call underlying function, format output as string, handle None/errors
- Tools return formatted strings per Tool Return Convention (`f"{label}: {value}"`)
- Never-raises: return `f"Error: {message}"` on failure
- Each tool appends its name to `ctx.deps.tools_used`
- `analysis/__init__.py` updated to re-export all 4 functions (currently only `compute_composite_valuation`)
- `FDData` is a plain `@dataclass` — tool wrapper constructs it from service/prompt data
- `compute_correlation_matrix` needs `dict[str, pd.DataFrame]` — tool fetches OHLCV for each ticker

## Technical Approach

### Tool Wrappers (in `agents/_toolsets.py`)

| Tool | Source | Target Desks | Wrapper Notes |
|------|--------|-------------|---------------|
| `compute_composite_valuation_tool` | `analysis/valuation.py` | Fundamental, Research | Build `FDData` from fundamentals context; format `CompositeValuation` as string |
| `compute_correlation_matrix_tool` | `analysis/correlation.py` | Risk | Fetch OHLCV for 2-5 tickers via `market_data.fetch_ohlcv()`, build DataFrame dict |
| `compute_risk_adjusted_metrics_tool` | `analysis/performance.py` | Risk | Query outcome returns from Repository, build float lists |
| `compute_position_size_tool` | `analysis/position_sizing.py` | Risk, Research | Pass IV from quote/chain data, format `PositionSizeResult` |
| `compute_hv_yang_zhang_tool` | `indicators/hv_estimators.py` | Volatility, Research | Fetch OHLCV, split into O/H/L/C Series, format annualized vol |

### Toolset Builder Updates
- Update `build_volatility_toolset()` — add `compute_hv_yang_zhang_tool`
- Update `build_fundamental_toolset()` — add `compute_composite_valuation_tool`
- Update `build_risk_toolset()` — add `compute_position_size_tool`, `compute_risk_adjusted_metrics_tool`, `compute_correlation_matrix_tool`
- Update `build_research_toolset()` — add `compute_composite_valuation_tool`, `compute_position_size_tool`, `compute_hv_yang_zhang_tool`

### Prompt Updates
- Update desk prompts to mention analysis tools in `<<<AVAILABLE_TOOLS>>>` block
- Risk desk budget already 5 (sufficient for 3 new tools under budget)

## Task Breakdown Preview

- [ ] Valuation + position sizing tool wrappers (low complexity) + tests
- [ ] Correlation matrix + risk-adjusted metrics tool wrappers (medium complexity) + tests
- [ ] Yang-Zhang HV tool wrapper (medium — OHLC Series splitting) + tests
- [ ] Register all 5 tools on target desks + update prompts + integration tests

## Dependencies

- Epics 1-3 (all desks online with base tools)
- `analysis/` module (valuation, correlation, performance, position_sizing)
- `indicators/hv_estimators.py`

## Success Criteria

- All 5 tools return correctly formatted strings for valid inputs
- All 5 tools return `"Error: ..."` strings for None/invalid inputs
- Tools registered on correct desks only (no cross-domain leakage)
- Underlying functions called with correct args (verified via mocks)
- `analysis/__init__.py` re-exports all 4 analysis functions
- ~25+ new tests

## Estimated Effort

3-4 issues, ~2 implementation sessions

## Tasks Created
- [ ] #620 - Valuation & Position Sizing Tool Wrappers (parallel: true)
- [ ] #621 - Correlation Matrix & Risk-Adjusted Metrics Tool Wrappers (parallel: true)
- [ ] #622 - Yang-Zhang Historical Volatility Tool Wrapper (parallel: true)
- [ ] #623 - Register Analysis Tools on Desks & Update Prompts (parallel: false)

Total tasks: 4
Parallel tasks: 3 (#620, #621, #622)
Sequential tasks: 1 (#623 depends on #620-#622)
Estimated total effort: 12-16 hours

## Test Coverage Plan
Total test files planned: 4
Total test cases planned: ~30
