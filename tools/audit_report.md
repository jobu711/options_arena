# Wiring Audit Report — 2026-03-19

## Summary

- **Epics audited**: 35 (32 with completion dates + 3 undated completed epics)
- **Total raw findings**: 81
- **After triage**: 10 actionable (71 false positives / intentional excluded)
- **Categories**: 59 dead exports (55 FP, 4 actionable), 4 unused config (4 actionable), 18 unregistered indicators (12 FP, 6 of which are TODO-acknowledged, leaving 2 fully actionable)

## Triage Notes

### Dead Exports (59 total → 4 actionable)

The vast majority of dead exports are **public API re-exports** in package `__init__.py` files. This project follows the **re-export pattern** where each package's `__init__.py` re-exports its public API so consumers can import from the package rather than submodules. These are intentional and expected — they exist for API stability and discoverability, even if no current internal code imports them from the package level. Tests, external consumers, and future code all rely on these exports.

**Excluded categories**:
- `agents/__init__.py` (28 exports): All 28 are public API for the agents package. Internal code imports directly from submodules (`orchestrator.py`, `model_config.py`, etc.) but the re-exports exist for external consumers and tests. Includes agent instances, deps classes, render functions, toolsets, and orchestration helpers.
- `models/__init__.py` (7 exports): Model classes re-exported for package-level import convenience. `DataConfig`, `LogConfig`, `CatalystImpact`, `RiskLevel`, `VolAssessment`, `MacroRegimeResult`, `MacroSignals`.
- `scoring/__init__.py` (8 exports): Scoring internals re-exported for testing and external use. `INDICATOR_WEIGHTS`, `compute_greeks`, `filter_contracts`, `select_by_delta`, `select_expiration`, `DEFAULT_FAMILY_WEIGHTS`, `FAMILY_INDICATOR_MAP`, `DOMAIN_BOUNDS`, `get_active_indicators`, `invert_indicators`.
- `services/__init__.py` (6 exports): Service classes and result types re-exported. `ServiceBase`, `CBOEChainProvider`, `BatchOHLCVResult`, `TickerOHLCVResult`, `ChainProvider`, `YFinanceChainProvider`.
- `pricing/__init__.py` (2 exports): `SecondOrderGreeks` and `option_price` re-exported for public API.
- `indicators/__init__.py` (3 exports): `put_call_ratio_oi`, `MarkovRegimeOutput`, `RegimeClassification` re-exported.
- Root `__init__.py` (1 export): `version` — standard package version export.

**Genuinely suspicious dead exports** (4):
1. `data/__init__.py` → `AgencyQueryRow`: Added by ai-agency-advisor-routing epic (#582). Very recent (2026-03-18). Likely intended for API layer consumption that hasn't been wired yet. Should be checked.
2. `indicators/__init__.py` → `VolSurfaceIndicators`: Re-exported but the type is used inline via direct import in `phase_options.py`. The re-export may be dead.
3. `indicators/__init__.py` → `MarkovRegimeOutput`, `RegimeClassification`: Re-exported from scientific-ml-statistical (#536) but only `compute_markov_regime` and `classify_regime_ml` are imported by consumers, not the output types.

### Unused Config Fields (4 total → 4 actionable)

All 4 config fields are genuinely unused — defined in `models/config.py` but never accessed by any runtime code.

### Unregistered Indicators (18 total → 2 genuinely dead)

The audit tool checks whether indicator functions appear in `scan/indicators.py`'s `INDICATOR_REGISTRY`. However, many indicators are legitimately called outside the registry:

**False positives — used in Phase 3 via `phase_options.py`** (3):
- `compute_vol_surface` — called at `phase_options.py:679`
- `compute_surface_indicators` — called at `phase_options.py:777`
- `compute_macro_regime` — called at `phase_options.py:289`

**False positives — used in Phase 2 via `phase_scoring.py`** (3):
- `compute_garch_forecast` — called at `phase_scoring.py:286`
- `classify_regime_ml` — called at `phase_scoring.py:329`
- `compute_markov_regime` — called at `phase_scoring.py:360`

**False positives — Phase 3 options-specific (intentional, need chain data)** (4):
- `iv_rank` — computed in Phase 3 via `compute_options_indicators()` and DSE enrichment
- `iv_percentile` — computed in Phase 3 via DSE enrichment
- `put_call_ratio_oi` — variant of `put_call_ratio_volume` (OI-based), available for Phase 3 use
- `max_pain_distance` is not flagged (it's in Phase 3 via `compute_options_indicators`)

**False positives — used outside the scan pipeline** (1):
- `classify_vol_regime` — called by `scoring/spreads.py:274,591,904` for spread strategy classification

**TODO-acknowledged — intentionally not wired, documented in scan/indicators.py** (3):
- `compute_pop` — line 712: "TODO: requires BSM d2 parameter which is not available in Phase 2"
- `compute_optimal_dte` — line 716: "TODO: requires per-contract theta"
- `compute_max_loss_ratio` — line 719: "TODO: requires account_risk_budget parameter"

**Genuinely dead — defined but never called anywhere** (4):
- `compute_vix_term_structure` (regime.py:20) — never imported or called
- `compute_risk_on_off` (regime.py:47) — never imported or called
- `compute_sector_momentum` (regime.py:70) — never imported or called
- `compute_vix_correlation` (iv_analytics.py:331) — never imported or called

Note: `map_regime_label_to_market_regime` (regime_ml.py:212) was identified by dead-code-audit epic and removed from `__init__.py` re-exports, but the function itself was not removed. It remains dead code.

---

## Actionable Findings by Epic

### deep-signal-engine (completed 2026-03-01)
**What it built**: 40 indicators across 8 dimensions (DSE mode), 6-agent debate pipeline, trend/volatility/flow/fundamental indicators.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `compute_vix_term_structure` | unregistered-indicator | `indicators/regime.py:20` | warning | Never imported or called. Added in #152. Requires VIX data not available in pipeline. |
| `compute_risk_on_off` | unregistered-indicator | `indicators/regime.py:47` | warning | Never imported or called. Added in #152. Requires HYG/LQD spread data. |
| `compute_sector_momentum` | unregistered-indicator | `indicators/regime.py:70` | warning | Never imported or called. Added in #152. Requires multi-ticker sector data. |
| `compute_vix_correlation` | unregistered-indicator | `indicators/iv_analytics.py:331` | warning | Never imported or called. Added in #155. Requires VIX series not in pipeline. |
| `CatalystImpact` | dead-export | `models/__init__.py:69` | info | Model re-export from #154. Used only in agent prompt rendering. |
| `RiskLevel` | dead-export | `models/__init__.py:69` | info | Model re-export from #154. |
| `VolAssessment` | dead-export | `models/__init__.py:69` | info | Model re-export from #154. |

### native-quant (completed 2026-03-13)
**What it built**: Yang-Zhang/Parkinson/Rogers-Satchell HV estimators, second-order Greeks, volatility surface analytics.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `ScanConfig.fit_vol_surface` | unused-config | `models/config.py:159` | warning | Config toggle for vol surface fitting. Defined but never read by any code path. Vol surface is always computed when contracts are available. |
| `VolSurfaceIndicators` | dead-export | `indicators/__init__.py:27` | info | Re-exported type, but consumers import `compute_surface_indicators` directly. |
| `SecondOrderGreeks` | dead-export | `pricing/__init__.py:3` | info | Re-exported type from native-quant. |

### volatility-intelligence (backlog, uncompleted — but code was added)
**What it built**: IV smoothing via put-call parity, mispricing detection.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `PricingConfig.use_parity_smoothing` | unused-config | `models/config.py:196` | warning | Config field added in #500 but never wired to the `compute_greeks()` function parameter of the same name in `scoring/contracts.py:165`. The function parameter defaults to `True` independently of the config. |

### scientific-ml-statistical (completed 2026-03-15)
**What it built**: GARCH/EGARCH vol forecasting, Markov-switching regime detection, FRED macro pipeline.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `MacroRegimeResult` | dead-export | `models/__init__.py:132` | info | Re-exported from #533. |
| `MacroSignals` | dead-export | `models/__init__.py:132` | info | Re-exported from #533. |
| `MarkovRegimeOutput` | dead-export | `indicators/__init__.py:19` | info | Re-exported from #536, but consumers import `compute_markov_regime` directly. |
| `RegimeClassification` | dead-export | `indicators/__init__.py:19` | info | Re-exported from #536, but consumers import `classify_regime_ml` directly. |
| `map_regime_label_to_market_regime` | unregistered-indicator | `indicators/regime_ml.py:212` | warning | Identified by dead-code-audit as dead and removed from `__init__.py`, but function body was not removed. Genuinely dead. |

### phase-5-services (completed 2026-02-23)
**What it built**: Service layer with yfinance wrapping, caching, rate limiting.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `ServiceConfig.cache_ttl_market_hours` | unused-config | `models/config.py:219` | warning | Defined in initial config (#2) but never accessed. Services use `ServiceConfig.cache_ttl` (general TTL) instead. Market-hours-aware TTL was planned but never implemented. |

### ai-agency-advisor-routing (completed 2026-03-18)
**What it built**: Advisor agent for intent classification, multi-desk routing, query persistence.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `classify_intent` | dead-export | `agents/__init__.py:20` | info | Very recent addition (#581). Re-exported for package API. |
| `AgencyQueryRow` | dead-export | `data/__init__.py:4` | info | Added in #582. Re-exported for package API. May not yet be imported by consuming code (epic just completed). |

### comp-audit (completed 2026-03-15)
**What it built**: Valuation models (DCF, DDM), correlation analysis, performance analytics, position sizing.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `compute_pop` | unregistered-indicator | `indicators/options_specific.py:140` | info | TODO in scan/indicators.py:712 — requires BSM d2 parameter. Intentionally deferred. |
| `compute_optimal_dte` | unregistered-indicator | `indicators/options_specific.py:166` | info | TODO in scan/indicators.py:716 — requires per-contract theta. Intentionally deferred. |
| `compute_max_loss_ratio` | unregistered-indicator | `indicators/options_specific.py:224` | info | TODO in scan/indicators.py:719 — requires account_risk_budget. Intentionally deferred. |

### OpenBB integration (pre-35 epic window, but config field persists)
**What it built**: OpenBB SDK enrichment for fundamentals, flow, sentiment.

| Finding | Category | File:Line | Severity | Notes |
|---------|----------|-----------|----------|-------|
| `OpenBBConfig.max_retries` | unused-config | `models/config.py:642` | warning | Config field added in #184 but never accessed by OpenBB service code. Retry logic uses hardcoded values instead. |

---

## False Positives (Excluded)

### Dead Exports — Public API Re-exports (55 findings)

These are standard re-exports in `__init__.py` files following the project's re-export pattern. They exist for API stability, test imports, and external consumption.

| Package | Count | Examples |
|---------|-------|---------|
| `agents/__init__.py` | 28 | `DeskDeps`, `DebateDeps`, `render_*_context`, agent instances, toolsets, orchestration helpers |
| `scoring/__init__.py` | 8 | `INDICATOR_WEIGHTS`, `filter_contracts`, `select_by_delta`, normalization helpers |
| `models/__init__.py` | 7 | `DataConfig`, `LogConfig`, `CatalystImpact`, `RiskLevel`, `VolAssessment`, macro models |
| `services/__init__.py` | 6 | `ServiceBase`, chain providers, batch result types |
| `indicators/__init__.py` | 3 | `put_call_ratio_oi`, `MarkovRegimeOutput`, `RegimeClassification` |
| `pricing/__init__.py` | 2 | `SecondOrderGreeks`, `option_price` |
| `__init__.py` (root) | 1 | `version` |

### Unregistered Indicators — Used Outside Registry (12 findings)

| Function | Where Used | Why Not in Registry |
|----------|-----------|-------------------|
| `iv_rank` | Phase 3 DSE enrichment | Needs option chain data (not OHLCV) |
| `iv_percentile` | Phase 3 DSE enrichment | Needs option chain data (not OHLCV) |
| `put_call_ratio_oi` | Available for Phase 3 | Needs option chain data (not OHLCV) |
| `compute_vol_surface` | `phase_options.py:679` | Phase 3 vol surface fitting |
| `compute_surface_indicators` | `phase_options.py:777` | Phase 3 surface indicator extraction |
| `compute_macro_regime` | `phase_options.py:289` | Phase 3 macro classification |
| `compute_garch_forecast` | `phase_scoring.py:286` | ML pipeline (conditional, not registry) |
| `classify_regime_ml` | `phase_scoring.py:329` | ML pipeline (conditional, not registry) |
| `compute_markov_regime` | `phase_scoring.py:360` | ML pipeline (conditional, not registry) |
| `classify_vol_regime` | `scoring/spreads.py:274,591,904` | Spread strategy helper, not scan indicator |
| `compute_pop` | TODO at scan/indicators.py:712 | Deferred — needs BSM d2 |
| `compute_optimal_dte` | TODO at scan/indicators.py:716 | Deferred — needs per-contract theta |
| `compute_max_loss_ratio` | TODO at scan/indicators.py:719 | Deferred — needs account_risk_budget |

---

## Unmapped Findings

The following findings could not be attributed to any of the 35 audited epics:

| Finding | Category | File:Line | Notes |
|---------|----------|-----------|-------|
| `ServiceConfig.cache_ttl_market_hours` | unused-config | `models/config.py:219` | Added in Issue #2 (initial bootstrap), predates all 35 epics. Config field was aspirational — market-hours-aware caching was planned but never implemented. |
| `option_price` | dead-export | `pricing/__init__.py:4` | Added in Issue #18 (pricing bootstrap). Predates all 35 epics. |
| `INDICATOR_WEIGHTS` | dead-export | `scoring/__init__.py:11` | Added in Issue #26 (package integration). Predates all 35 epics. |
| `LogConfig` | dead-export | `models/__init__.py:51` | Added during E2E test fix commit. |
| `version` | dead-export | `__init__.py:3` | Standard package version, always present. |
| `put_call_ratio_oi` | dead-export | `indicators/__init__.py:11` | Added during initial indicator port (pre-35 window). |

---

## Prioritized Action Items

### P1 — Dead Code Removal (2 functions)
Functions that exist but are never called anywhere:
1. **`compute_vix_correlation`** in `indicators/iv_analytics.py:331` — remove function + tests
2. **`map_regime_label_to_market_regime`** in `indicators/regime_ml.py:212` — remove function (already removed from `__init__.py` by dead-code-audit, but function body survived)

### P2 — Unwired Regime Indicators (3 functions)
Functions added by deep-signal-engine (#152) that require cross-ticker or external data not available in the current pipeline. Decision needed: wire them with appropriate data sources, or remove them.
1. **`compute_vix_term_structure`** in `indicators/regime.py:20` — needs VIX futures term structure data
2. **`compute_risk_on_off`** in `indicators/regime.py:47` — needs HYG/LQD spread data
3. **`compute_sector_momentum`** in `indicators/regime.py:70` — needs multi-ticker sector ETF data

### P3 — Dead Config Fields (4 fields)
Config fields defined but never read:
1. **`ScanConfig.fit_vol_surface`** — vol surface always runs; toggle never checked
2. **`PricingConfig.use_parity_smoothing`** — config field not wired to function parameter
3. **`ServiceConfig.cache_ttl_market_hours`** — market-hours TTL never implemented
4. **`OpenBBConfig.max_retries`** — retry logic uses hardcoded values

### P4 — Deferred Wiring (3 TODOs acknowledged in code)
These are documented TODOs in `scan/indicators.py` — not bugs, but incomplete features:
1. `compute_pop` — needs BSM d2
2. `compute_optimal_dte` — needs per-contract theta
3. `compute_max_loss_ratio` — needs account_risk_budget
