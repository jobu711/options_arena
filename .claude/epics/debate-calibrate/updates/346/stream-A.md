# Task #346 — Domain context renderers + prompt calibration

## Status: Complete

## Changes Made

### `src/options_arena/agents/_parsing.py`
- Added `_render_identity_block(ctx: MarketContext) -> list[str]` — shared identity fields for all domain renderers (TICKER, PRICE, 52W HIGH/LOW, SECTOR, DTE, TARGET STRIKE, TARGET DELTA, EXERCISE, DIV YIELD, NEXT EARNINGS + warning)
- Added `render_trend_context(ctx: MarketContext) -> str` — identity + RSI(14), MACD, ADX, SMA ALIGNMENT, STOCHASTIC RSI, REL VOLUME, RSI DIVERGENCE, dim_trend
- Added `render_volatility_context(ctx: MarketContext) -> str` — identity + IV RANK, IV PERCENTILE, ATM IV 30D, BB WIDTH, ATR%, VOL REGIME, IV-HV SPREAD, SKEW RATIO, VIX TERM STRUCTURE, EXPECTED MOVE, EXPECTED MOVE RATIO, VEGA, VOMMA, dim_iv_vol, dim_hv_vol
- Added `render_flow_context(ctx: MarketContext) -> str` — identity + PUT/CALL RATIO, MAX PAIN DISTANCE %, GEX, UNUSUAL ACTIVITY SCORE, NET CALL/PUT PREMIUM, OPTIONS PUT/CALL RATIO, REL VOLUME, dim_flow, dim_microstructure
- Added `render_fundamental_context(ctx: MarketContext) -> str` — identity + P/E, FORWARD P/E, PEG, P/B, DEBT/EQUITY, REVENUE GROWTH, PROFIT MARGIN, SHORT RATIO, SHORT % OF FLOAT, analyst fields, insider fields, institutional ownership, news sentiment, dim_fundamental
- Updated `PROMPT_RULES_APPENDIX` from v2.0 to v3.0: removed COMPOSITE SCORE anchor lines, replaced with domain-neutral calibration language
- `render_context_block()` left UNCHANGED

### `src/options_arena/agents/__init__.py`
- Added re-exports for 4 new renderers: `render_trend_context`, `render_volatility_context`, `render_flow_context`, `render_fundamental_context`

### `tests/unit/agents/test_domain_renderers.py` (NEW)
- 34 test cases across 7 test classes
- TestRenderIdentityBlock: 8 tests (ticker/price/range, DTE/strike/delta, sector/exercise/div, earnings warnings, no-earnings, excludes scan conclusions)
- TestRenderTrendContext: 7 tests (includes indicators, excludes COMPOSITE SCORE, excludes DIRECTION, handles None, handles NaN, identity block present, excludes vol indicators)
- TestRenderVolatilityContext: 4 tests (includes vol indicators, excludes scan conclusions, handles all None, vol regime labels)
- TestRenderFlowContext: 3 tests (includes flow indicators, excludes scan conclusions, handles None)
- TestRenderFundamentalContext: 5 tests (includes fundamental indicators, excludes scan conclusions, handles all None, news sentiment with headlines, None fundamental fields)
- TestPromptRulesAppendix: 6 tests (no COMPOSITE SCORE, domain-neutral language, confidence scale preserved, citation rules preserved, Greeks preserved, version updated)
- TestNoDomainRendererHasScanConclusions: 1 parametric test across all 4 renderers

### `tests/unit/agents/test_prompt_enhancements.py`
- Updated 3 existing tests to check for "Domain-specific calibration" instead of "Data anchors" (reflecting PROMPT_RULES_APPENDIX update)

## Verification
- `ruff check` + `ruff format`: clean
- `mypy --strict` on source files: clean
- All 408 agent unit tests pass (including 34 new + 3 updated)
