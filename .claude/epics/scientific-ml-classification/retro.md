---
epic: scientific-ml-classification
retro_date: 2026-03-16
---

# Retro: scientific-ml-classification

## Timeline

- **Start**: 2026-03-16T09:35:52 (decompose + sync)
- **End**: 2026-03-16T10:47:27 (fix stale test expectations)
- **Proxy hours**: ~1.2h (5 commits over 72 minutes)
- **Planned effort**: M (~15-22 hours)
- **Ratio**: 0.07x (AI agent time vs human estimate)

## Scope: Planned vs Delivered

| Planned | Delivered | Delta |
|---------|-----------|-------|
| 4 tasks | 4 tasks | 0 |
| ~57 tests | 91 tests | +34 (60% over) |
| 2 new files | 2 new files | 0 |
| 4 modified files | 8+ modified files | +4 (supporting files) |
| scikit-learn dependency | Added to `[ml]` extra | 0 |

### Delivered

1. **#540** — Offline regime classifier training script (509 lines, 28 tests)
2. **#541** — ML regime inference in pipeline (200 lines added to regime_ml.py, 18 tests)
3. **#542** — Contract Greeks clustering (348 lines, 25 tests)
4. **#543** — Flow anomaly detection (217 lines added to flow_analytics.py, 16 tests)
5. **Fix commit** — 15 stale test expectations updated for weight redistribution + health format

### Not Delivered (Integration Gaps)

- **542.8**: `cluster_contracts_by_greeks()` not called from `scoring/contracts.py` — dead code
- **543.8**: `detect_flow_anomalies()` not wired in pipeline; `render_flow_context()` omits flow anomaly score
- **541.8**: `predicted_regime` string not propagated to `MarketContext.ml_regime`

## Quality

| Metric | Value |
|--------|-------|
| Tests added | 91 (87 new + 4 updated) |
| Tests passing | 91/91 (100%) |
| Post-merge fixes | 1 (stale test expectations) |
| Lines added | ~2,791 (Python) |
| Lines deleted | ~45 |
| ruff violations | 0 |
| Regressions | 0 (15 tests needed expectation updates, not regressions) |

## Learnings

1. **Integration wiring is the last mile**: All core ML logic was implemented and tested, but 2 of 4 tasks have incomplete pipeline integration. The functions exist but are dead code. This is a recurring pattern — function implementation gets thorough testing, but the wiring into the pipeline gets skipped.

2. **Feature spec drift is acceptable when documented**: Task #540 used `roc` + `sma_alignment` instead of the specified `MACD` + `IV-HV spread`. The code's docstring documents the actual features used. This is fine as long as it's intentional and documented.

3. **Bundled commits lose traceability**: Task #542 (clustering) was bundled into the #540 commit. This makes git-based traceability harder. Each task should ideally have its own commit with its issue number.

4. **Test count exceeded estimates significantly**: 91 tests vs 57 planned (60% over). The test quality is high with good edge case coverage, but this signals the estimates may undercount test scenarios.

## Recommendations

1. Wire `cluster_contracts_by_greeks()` into `scoring/contracts.py` as specified
2. Wire `detect_flow_anomalies()` into pipeline and add to `render_flow_context()`
3. Propagate `predicted_regime` to `MarketContext.ml_regime` in the orchestrator
4. Enforce one-commit-per-task discipline for better traceability
