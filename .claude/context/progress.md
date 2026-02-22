# Progress

## Current State

- **Version**: 1.0.0 (planning)
- **Phase 1 MVP (v0.1.0)**: Complete (all 8 issues done)
- **PydanticAI migration**: Complete (epic closed 2026-02-20, PRs #82-#90)
- **Web UI**: Rolled back to pre-web state on 2026-02-19. Two attempts (React SPA, then Jinja2+HTMX) were removed.
- **Branch**: `master`
- **Tests**: 1,169 passing
- **Scan pipeline**: Producing 8 recommendations per run (verified 2026-02-20)

## Completed Work (Phase 1)

### Issue #18 — Models, Enums, Exceptions (Done)
### Issue #19 — Persistence Layer / SQLite (Done)
### Issue #20 — Services Layer (Done)
### Issue #21 — Technical Indicators (Done)
### Issue #14 — Analysis & Scoring Engine (Done)
### Issue #15 — AI Debate System (Done)
### Issue #16 — Reporting & CLI Integration (Done)
### Issue #17 — Comprehensive Test Suite (Done)

## Post-Phase 1 Fixes (Cherry-picked after rollback)

- `c1ab1ba` — CBOE CSV parser fix, Windows spinner crash fix, universe cache persistence
- `57b2a9c` — Switch universe source from weekly-only to full CBOE directory
- `f523d63` — Fetch S&P 500 constituents from Wikipedia for universe classification
- `d235b31` — Remove stale hooks and clear hook settings
- `9ae037c` — Add rotating file logger for persistent DEBUG output
- `c9da1c1` — Suppress aiosqlite DEBUG noise in file logger
- `5f1c472` — Filter index symbols, raise OHLCV minimum to 200, cache fetch failures
- `c225bfc` — Fix 0 option recommendations in scan pipeline
- `5942264` — Add liquidity pre-filter to scan pipeline (dollar volume + min price)
- `9c0d213` — Fix 3 cascading failures: isolate indicator try/except, SMA tiebreaker for direction ties, remove service-level delta filter

## Scan Pipeline Logic Fix (Implemented)

Four changes to resolve 0 option recommendations:

1. **Normalization: skip universally-missing indicators** — The 4 options-specific
   indicators (22% weight) were defaulting to 50.0 for all tickers, diluting score
   discrimination. Now skipped entirely; composite_score() renormalizes the remaining
   14 real indicators automatically.

2. **ADX trend threshold lowered 20.0 → 15.0** — Recovers tickers with weak trends
   (ADX 15-20) that were being classified NEUTRAL and skipped.

3. **Zero-bid filter softened** — Service layer now only rejects contracts where both
   bid AND ask are zero (truly dead). Contracts with bid=0/ask>0 pass through to the
   analysis layer. Spread filtering moved from service to analysis layer with zero-bid
   exemption (spread check is meaningless when bid=0).

4. **Delta range widened + fallback** — Primary range expanded from [0.30, 0.40] to
   [0.20, 0.50]. Fallback picks closest-to-0.35 within [0.10, 0.80] if nothing in
   primary range.

## PydanticAI Migration (Completed 2026-02-20)

Replaced hand-rolled `LLMClient`, manual JSON parsing, and custom retry logic
with PydanticAI agent framework. Epic: 8 issues (#74-#81), all merged.

- `bb3b6bd` — Install pydantic-ai, create `model_config.py` with `build_ollama_model()`
- `536f8d6` — Simplify prompts to string constants (remove `PromptMessage` class)
- `2f7f41c` — Rewrite bull/bear/risk as PydanticAI `Agent` instances with typed `output_type`
- `ff1a690` — Simplify `_parsing.py` to models + constants only (~170 → ~70 lines)
- `deeaada` — Adapt orchestrator to PydanticAI agents (`RunUsage` accumulation)
- `86cd3c3` — Delete `llm_client.py` (272 lines removed), update exports
- `9a6ec05` — Rewrite agent tests using PydanticAI `TestModel`
- `827b131` — Fix regressions: wire `num_ctx=8192`, add think-tag `@output_validator`, restore `OLLAMA_HOST` env var

Net result: ~300 lines removed from agents module, zero changes outside `agents/` + `cli.py`.

## Options Arena Rewrite (PRD Created 2026-02-21)

From-scratch rewrite of Option Alpha v3, renaming to `options_arena` (PEP 8 compliant).
PRD: `.claude/prds/options-arena.md` — status: backlog.

**Key changes from v3:**
- BAW (Barone-Adesi-Whaley) pricing for American options (fixes critical European BSM misapplication)
- `analysis/` split into `pricing/` + `scoring/` packages
- New `scan/` module replaces 430-line `cli.py` scan function
- Data-driven `IndicatorSpec` registry replaces 14 copy-paste indicator blocks
- `AppSettings` centralizes scattered constants
- `IndicatorSignals` typed model replaces `dict[str, float]` on `TickerScore`
- `DividendSource` enum + 3-tier waterfall for dividend yield extraction with dollar-rate cross-validation (FR-M7/M7.1 updated 2026-02-22)
- AI debate, reporting, web UI deferred to v2

**8 implementation phases**, ~810 tests target. No code written yet.

### PRD Updates (2026-02-22)
- FR-M3.1: Added `DividendSource` enum (`FORWARD`, `TRAILING`, `COMPUTED`, `NONE`)
- FR-M7: Expanded dividend yield spec — 3-tier waterfall from yfinance `info["dividendYield"]` > `info["trailingAnnualDividendYield"]` > `Ticker.get_dividends(period="1y")` sum / price > `0.0`. Field is `float` (never `None`), with provenance tracking. Values are decimal fractions (0.005 = 0.5%).
- FR-M7.1 (new): Waterfall detail — fall-through on `None` only (not falsy; `0.0` is valid for growth stocks). Cross-validation: when yield and dollar-rate (`dividendRate`, `trailingAnnualDividendRate`) both available, warn on >20% divergence. Audit fields `dividend_rate: float | None` and `trailing_dividend_rate: float | None` added to `TickerInfo`.
- FR-SV1: Service layer dividend extraction updated to match FR-M7.1 waterfall + dollar-rate cross-validation + `get_dividends(period="1y")` for computed tier. All yfinance `.info` keys are camelCase (`dividendYield`, `trailingAnnualDividendYield`, `dividendRate`, `trailingAnnualDividendRate`).
- FR-SV2: Corrected false assumption — yfinance option chains provide `impliedVolatility` but **no Greeks** (no delta/gamma/theta/vega/rho). All Greeks computed locally via `pricing/dispatch.py`. `impliedVolatility` passed through as `market_iv` for IV solver seed and cross-check.
- FR-S4: Removed "fallback" framing — `pricing/dispatch.py` is the sole source of Greeks for all contracts, not a fallback for missing yfinance data.
- Section 8 assumption corrected to reflect yfinance chain columns (Context7-verified).
- FR-SV3: Added Wikipedia table implementation detail — `pd.read_html(url, attrs={"id": "constituents"})` targets table by stable HTML id (not positional index). Columns: `Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Headquarters Location`, `Date added`, `CIK`, `Founded`. Ticker translation needed (`.` → `-` for yfinance). Section 8 assumption updated with column-level specificity.
- FR-M5/M5.1/M6: Expanded `AppSettings` spec with Context7-verified pydantic-settings v2 patterns. `AppSettings(BaseSettings)` is the sole `BaseSettings` subclass; `ScanConfig`, `PricingConfig`, `ServiceConfig` are nested `BaseModel` submodels. `SettingsConfigDict(env_prefix="ARENA_", env_nested_delimiter="__")` enables env overrides like `ARENA_SCAN__TOP_N=30`. Full field inventory added in FR-M5.1. No `.env` file in MVP.
- FR-P1/P2/P3: Corrected IV solver strategy (Context7-verified). BSM IV: manual Newton-Raphson (analytical vega via `norm.pdf`, quadratic convergence). BAW IV: **`scipy.optimize.brentq`** (NOT Newton-Raphson — BAW has no analytical vega w.r.t. IV; brentq is bracket-based, guaranteed convergent, no derivative needed). Dispatch routes solver by `ExerciseStyle`. scipy dependency description updated across PRD and tech-context.

## Next Up

- Begin Options Arena implementation (Phase 1: Project Bootstrap & Models)
- Options liquidity weighting in composite scoring (carry-forward from v3 backlog)

## Blockers

- None currently known.
