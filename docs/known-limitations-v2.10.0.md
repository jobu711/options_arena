# Known Limitations — v2.10.0

Findings from the v2.10.0 release audit that were triaged as P2-P4 (not blocking release).
Each finding references its source auditor and original identifier.

## P2 — Should Fix (next sprint)

### Code Quality
- **Raw string categorical fields** [code-reviewer]: `models/analysis.py` uses `str | None` for `ml_regime`, `vol_regime_label`, `agent_name` fields that should be StrEnums.
- **Raw dict fields** [code-reviewer]: `models/valuation.py:74` (`CompositeValuation.weights_used`), `api/routes/health.py:21` (health check return), `services/financial_datasets.py:319` (`_api_get` return).
- **Import boundary violation** [architect-reviewer]: `scoring/contracts.py:24` imports from `pricing.iv_smoothing` instead of through `pricing` package re-export.

### Missing Features
- **weasyprint unused** [dep-auditor]: `[pdf]` optional dependency group declared but no `import weasyprint` exists. PDF export not implemented.

### Security Hardening
- **OpenAPI docs exposed** [security-auditor]: Swagger UI at `/docs` and ReDoc at `/redoc` are accessible without gating behind a `--dev` flag.
- **model_cache_dir traversal** [security-auditor]: `MLConfig.model_cache_dir` path could theoretically traverse outside project root (partially mitigated by P1-5 fix on joblib.load, but config validator not added).

### Formula Improvement
- **BSM in vol_surface.py omits dividend yield** [oa-python-reviewer]: `_standalone_implied_move()` Breeden-Litzenberger probability uses vanilla BSM without continuous dividend yield `q`. Overprices calls for high-dividend stocks.
- **Surface fields not wired** [architect-reviewer]: `iv_surface_residual`, `surface_fit_r2`, `surface_is_1d` defined on MarketContext but never populated in `build_market_context()`.

### Bug Fixes
- **Discarded gather results** [bug-auditor]: `scan/phase_scoring.py:259` `asyncio.gather(*tasks, return_exceptions=True)` return value not inspected; ML failures invisible.

## P3 — Quality (plan for future)

- 4 missing `math.isfinite()` validators on confidence/probability fields
- 3 unbounded SELECT queries without LIMIT (metadata, holding period, equity curve)
- ALTER TABLE idempotency in later migrations (partial, core fix in P1-6)
- WebSocket event backpressure gaps
- GPL (docutils) and LGPLv3 (frozendict) transitive dependencies
- R-squared can be negative in vol_surface regression (unreported)
- pydantic-ai meta vs slim version skew

## P4 — Cosmetic (informational)

- No authentication on API endpoints (by design — loopback-only)
- CORS `allow_credentials=True` unnecessarily enabled
- WebSocket origin check does not verify port
- Rate limiter globally keyed on loopback address
- SPA catch-all serves any file in `web/dist/`
- CLAUDE.md indicator weight table outdated (shows 19, code has 27)
- Yang-Zhang HV comment says "Close-to-close" but code computes close-to-open (math is correct)
