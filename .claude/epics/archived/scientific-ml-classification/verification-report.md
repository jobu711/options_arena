---
epic: scientific-ml-classification
verified_at: 2026-03-16T14:00:00Z
result: 28 PASS, 2 WARN, 2 FAIL, 0 SKIP
tests: 91 passed, 0 failed
---

# Verification Report: scientific-ml-classification

## Test Results

- **91 tests passed, 0 failed** (25.93s)
- `test_train_regime_classifier.py`: 28 passed
- `test_regime_ml_classify.py`: 18 passed
- `test_clustering.py`: 25 passed
- `test_flow_anomalies.py`: 16 passed

## Traceability Matrix

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| **Task #540 — Offline Regime Classifier Training Script** | | |
| 540.1 | GBM classifier with configurable hyperparameters | PASS | `train_regime_classifier.py:244` — `GradientBoostingClassifier`, CLI args `--n-estimators`, `--max-depth`, `--learning-rate` |
| 540.2 | 9-feature extraction from IndicatorSignals | WARN | 9 features extracted but 2 differ from spec: `roc` + `sma_alignment` instead of `MACD` + `IV-HV spread`. Code is internally consistent. |
| 540.3 | 5-class regime labels | PASS | `REGIME_LABELS` constant with all 5 classes; `label_regime()` heuristic assigns all 5 |
| 540.4 | Cross-validation + classification_report | PASS | `run_cross_validation()` uses `cross_val_score`; `classification_report` called in `main()` |
| 540.5 | joblib serialization (not sklearn.externals) | PASS | `import joblib` directly in `save_model()` and `load_model()` |
| 540.6 | Guarded sklearn import with clear error message | PASS | `_get_sklearn()` with try/except ImportError and install instructions |
| 540.7 | data/model_cache/ created + gitignored | PASS | `path.parent.mkdir(parents=True, exist_ok=True)` + `.gitignore` has `data/model_cache/*.pkl` |
| 540.8 | argparse CLI | PASS | `_build_parser()` with full argparse CLI, `if __name__ == "__main__": main()` |
| **Task #541 — ML Regime Inference in Pipeline** | | |
| 541.1 | classify_regime_ml() function | PASS | `indicators/regime_ml.py:334` |
| 541.2 | RegimeClassification NamedTuple | PASS | NamedTuple with `predicted_regime`, `probabilities`, `confidence` |
| 541.3 | Returns None on error conditions | PASS | All 3 failure paths return None |
| 541.4 | Guarded sklearn + joblib import | PASS | `_get_joblib()` guards with try/except |
| 541.5 | enable_ml_regime config flag | PASS | `MLConfig.enable_ml_regime: bool = False` in config.py |
| 541.6 | IndicatorSignals.ml_regime_confidence | PASS | `scan.py:163` — `ml_regime_confidence: float | None = None` |
| 541.7 | MarketContext.ml_regime + ml_regime_confidence | PASS | `analysis.py:207-208` — both fields present |
| 541.8 | Phase 2 pipeline wiring | WARN | Confidence stored via `_compute_ml_regime_classifications()`. But `predicted_regime` string is NOT propagated to `MarketContext.ml_regime`. |
| **Task #542 — Contract Greeks Clustering** | | |
| 542.1 | cluster_contracts_by_greeks() function | PASS | `scoring/clustering.py:221` |
| 542.2 | K-means on min-max normalized Greeks | PASS | `MinMaxScaler` + `KMeans.fit_predict()` on delta/gamma/theta/vega |
| 542.3 | Semantic cluster labels | PASS | 4 labels: high-gamma, income, vol-play, directional via centroid analysis |
| 542.4 | ClusteringResult Pydantic model | PASS | `BaseModel` with `frozen=True`, clusters/n_clusters/silhouette_score |
| 542.5 | Graceful degradation <10 contracts | PASS | `_MIN_CONTRACTS = 10`, returns `_empty_result()` |
| 542.6 | enable_clustering config flag | PASS | `MLConfig.enable_clustering: bool = False` |
| 542.7 | Guarded sklearn import | PASS | `_get_kmeans()` and `_get_scaler()` both guarded |
| 542.8 | Integration in scoring/contracts.py | FAIL | Function defined and re-exported but **never called** from contracts.py or pipeline. Dead code. |
| **Task #543 — Flow Anomaly Detection** | | |
| 543.1 | detect_flow_anomalies() function | PASS | `indicators/flow_analytics.py:345` |
| 543.2 | Isolation Forest on 4-feature matrix | PASS | 4 features: vol/OI ratio, log call/put ratio, vol/avg ratio, large trade concentration |
| 543.3 | FlowAnomalyResult NamedTuple | PASS | NamedTuple with anomaly_score, is_anomalous, feature_contributions |
| 543.4 | Returns None when sklearn missing or <20 rows | PASS | `_MIN_ANOMALY_ROWS = 20`, guarded import |
| 543.5 | enable_flow_anomaly config flag | PASS | `MLConfig.enable_flow_anomaly: bool = False` |
| 543.6 | IndicatorSignals.flow_anomaly_score | PASS | `scan.py:166` — field present, defaults to None |
| 543.7 | MarketContext.flow_anomaly_score | PASS | `analysis.py:204` — field present |
| 543.8 | Agent context rendering + pipeline wiring | FAIL | `render_flow_context()` does NOT include `flow_anomaly_score`. No pipeline phase calls `detect_flow_anomalies()` to populate the field. |

## Git Commit Traces

| Task | Commit | Message |
|------|--------|---------|
| #540 | `ebb24ae` | feat: add offline regime classifier training script (#540) |
| #541 | `a398fb2` | feat: add ML regime classification inference in pipeline (#541) |
| #543 | `5195306` | feat: add flow anomaly detection via Isolation Forest (#543) |
| #542 | `ebb24ae` | (bundled with #540 commit — no separate commit) |
| fix  | `3fc2990` | fix: update 15 stale test expectations |

## Summary

- **28/32 PASS** (87.5%)
- **2 WARN**: Feature spec drift (540.2), incomplete MarketContext propagation (541.8)
- **2 FAIL**: Missing pipeline integration for clustering (542.8) and flow anomaly agent rendering + pipeline wiring (543.8)
- **0 SKIP**

## FAIL Details

### 542.8 — Clustering not integrated in contracts.py
`cluster_contracts_by_greeks()` is fully implemented, tested, and re-exported from `scoring/__init__.py`, but is never called from `scoring/contracts.py` or any pipeline code. The `enable_clustering` config flag exists but is never checked at runtime. This is dead code.

### 543.8 — Flow anomaly not rendered or wired in pipeline
`detect_flow_anomalies()` is fully implemented and tested. Model fields exist on `IndicatorSignals` and `MarketContext`. However:
1. No pipeline phase calls `detect_flow_anomalies()` to populate `IndicatorSignals.flow_anomaly_score`
2. `render_flow_context()` in `agents/_parsing.py` does not render `flow_anomaly_score`

Both FAILs are **integration gaps** — the core ML logic works, but it's not wired into the runtime pipeline.
