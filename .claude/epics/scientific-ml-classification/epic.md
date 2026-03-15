---
name: scientific-ml-classification
status: backlog
created: 2026-03-15T14:00:00Z
progress: 0%
prd: .claude/prds/scientific-ml-integration.md
parent: .claude/epics/scientific-ml-integration
github: [Will be updated when synced to GitHub]
---

# Epic B: ML Classification & Scoring (scikit-learn)

## Overview

Integrate `scikit-learn` for ML-based market regime classification, contract Greeks clustering, and options flow anomaly detection. Builds on indicator signals and config infrastructure established by Epic A (Statistical Foundation).

**Shared research**: `.claude/epics/scientific-ml-integration/research.md`

## Architecture Decisions

1. **Optional dependency** — `scikit-learn >=1.5` added to `[project.optional-dependencies] ml = [...]` group alongside `arch` and `statsmodels`.
2. **Offline training, online inference** — Training scripts live in `tools/`. Pipeline only runs inference from pre-trained model checkpoints stored in `data/model_cache/` (gitignored).
3. **Guarded imports** — `_get_sklearn()` pattern returns None when not installed. All functions return None gracefully.
4. **Indicator module purity** — `indicators/regime_ml.py` (extended) and `indicators/flow_analytics.py` (extended) return `NamedTuple | None`. No Pydantic models.
5. **Scoring module boundary** — `scoring/clustering.py` takes `list[OptionContract]`, returns typed model. Imports `pricing/dispatch` only.

## New Files (2)

| File | Module | Purpose |
|------|--------|---------|
| `tools/train_regime_classifier.py` | tools | Offline GBM regime classifier training script |
| `scoring/clustering.py` | scoring | K-means contract clustering by Greeks profile |

## Modified Files (4)

| File | Change |
|------|--------|
| `indicators/regime_ml.py` | Add `classify_regime_ml()` inference function |
| `indicators/flow_analytics.py` | Add `detect_flow_anomalies()` via Isolation Forest |
| `scoring/contracts.py` | Optional clustering call after Greeks computation |
| `models/config.py` | `enable_ml_regime`, `enable_clustering`, `enable_flow_anomaly` flags |

## New Dependencies

- `scikit-learn >=1.5` — BSD, classifiers + clustering + anomaly (~30MB)

## Issues

### B1: Offline Regime Classifier Training Script
**FR**: FR-S4a
**Description**: Create `tools/train_regime_classifier.py` — offline script that trains a GBM classifier on historical scan data. Feature vector from Phase 2 indicators (RSI, ADX, ATR/price, volume ratio, IV rank, IV-HV spread, put-call ratio, Bollinger %B, MACD histogram). Labels: trending-up, trending-down, mean-reverting, high-volatility, low-volatility. Saves trained model to `data/model_cache/regime_classifier.pkl`.
**New files**: `tools/train_regime_classifier.py`
**Est. tests**: ~15
**Acceptance criteria**:
- [ ] GBM classifier with configurable hyperparameters
- [ ] Feature extraction from historical `IndicatorSignals`
- [ ] Cross-validation with classification report
- [ ] Model serialization to `data/model_cache/`
- [ ] Guarded scikit-learn import with clear error message

### B2: ML Regime Inference in Pipeline
**FR**: FR-S4b
**Description**: Add `classify_regime_ml()` to `indicators/regime_ml.py` — loads pre-trained GBM model and classifies current market regime from indicator feature vector. Returns class probabilities. Config-gated via `enable_ml_regime: bool = False`.
**Modified files**: `indicators/regime_ml.py`, `models/config.py`
**Depends on**: B1, Epic A (indicators for feature vectors)
**Est. tests**: ~15
**Acceptance criteria**:
- [ ] Loads model from `data/model_cache/regime_classifier.pkl`
- [ ] Returns `RegimeClassification` with class probabilities
- [ ] Returns None when model not found or scikit-learn not installed
- [ ] Config flag gates execution in pipeline

### B3: Contract Greeks Clustering
**FR**: FR-S6
**Description**: Implement `cluster_contracts_by_greeks()` in `scoring/clustering.py` using K-means on normalized (delta, gamma, theta, vega) vectors. Assign cluster labels via centroid analysis. Integrate into `scoring/contracts.py` after Greeks computation for debate context.
**New files**: `scoring/clustering.py`
**Modified files**: `scoring/contracts.py`
**Est. tests**: ~15
**Acceptance criteria**:
- [ ] K-means clustering on min-max normalized Greeks vectors
- [ ] Cluster labels: "high-gamma", "income", "vol-play", "directional"
- [ ] Degrades to empty dict when <10 contracts with valid Greeks
- [ ] Config flag `enable_clustering: bool = False` gates execution
- [ ] Guarded scikit-learn import

### B4: Flow Anomaly Detection
**FR**: FR-S7
**Description**: Add `detect_flow_anomalies()` to `indicators/flow_analytics.py` using Isolation Forest. Features: volume/OI ratio, call/put volume ratio, volume vs 20d average, large trade concentration. Flags unusual patterns for Flow Agent context.
**Modified files**: `indicators/flow_analytics.py`
**Depends on**: B2 (shares config infra)
**Est. tests**: ~10
**Acceptance criteria**:
- [ ] Isolation Forest on flow feature matrix
- [ ] Returns `FlowAnomalyResult` with anomaly scores and flags
- [ ] Returns None when scikit-learn not installed or insufficient data
- [ ] Config flag `enable_flow_anomaly: bool = False`

## Dependency Graph

```
Epic A (must complete first)
 |
 v
B1 (training script) ──→ B2 (ML regime inference)
                                                    \
B3 (contract clustering)                             → all wired in pipeline
                                                    /
B4 (flow anomaly detection) ────────────────────────
```

B1 must precede B2. B3 and B4 are independent of each other and B1/B2.

## Estimated Effort

- **Size**: M (~2 sessions)
- **Tests**: ~55 new tests
- **Risk**: Low — scikit-learn APIs are stable and well-documented

## Success Criteria

| Metric | Target |
|--------|--------|
| ML regime inference latency | <100ms per ticker |
| Contract clustering populated | >60% of chains with 10+ contracts |
| Existing test suite | 100% pass (zero regressions) |
| Default config behavior | Identical to current — all features off |
