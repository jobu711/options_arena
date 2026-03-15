---
name: scientific-ml-neural
status: backlog
created: 2026-03-15T14:00:00Z
progress: 0%
prd: .claude/prds/scientific-ml-integration.md
parent: .claude/epics/scientific-ml-integration
github: [Will be updated when synced to GitHub]
---

# Epic C: Neural Models (PyTorch Lightning)

## Overview

Integrate PyTorch Lightning for neural IV surface fitting and LSTM price trajectory forecasting. These non-parametric models complement the existing BSM/BAW parametric pricing and spline-based vol surface fitting. All models run on CPU by default (GPU optional), with graceful fallback to existing methods when PyTorch is unavailable.

**Shared research**: `.claude/epics/scientific-ml-integration/research.md`

## Architecture Decisions

1. **Separate dependency group** — `pytorch-lightning >=2.3`, `torch >=2.3` in `[project.optional-dependencies] neural = [...]`. Separate from `ml` group due to large size (~2GB).
2. **Guarded imports** — `_get_lightning()` / `_get_torch()` pattern. Neural models return None when deps unavailable. Existing spline/BSM methods serve as automatic fallback.
3. **Checkpoint persistence** — Trained model checkpoints stored in `data/model_cache/` (gitignored). Per-ticker checkpoints for IV surface (warm-start on subsequent scans).
4. **CPU-first** — All models configured for CPU execution. GPU acceleration is optional performance enhancement, not a requirement.
5. **Pricing module boundary** — `pricing/neural_surface.py` and `pricing/trajectory.py` encapsulate PyTorch internals but expose scalar `float` / typed model interfaces consistent with existing `pricing/` conventions.

## New Files (2)

| File | Module | Purpose |
|------|--------|---------|
| `pricing/neural_surface.py` | pricing | PyTorch Lightning MLP IV surface fitter |
| `pricing/trajectory.py` | pricing | LSTM price trajectory forecasting |

## Modified Files (6)

| File | Change |
|------|--------|
| `indicators/vol_surface.py` | Neural surface as alternative fitter in `compute_vol_surface()` |
| `scan/phase_options.py` | Neural surface + trajectory model integration |
| `agents/volatility.py` | Consume neural surface residuals + trajectory probs |
| `agents/_parsing.py` | Render neural probability context |
| `models/config.py` | `enable_neural_surface`, `enable_trajectory`, `surface_method` config |
| `models/analysis.py` | `prob_profit_neural` field on `MarketContext` |

## New Dependencies

- `pytorch-lightning >=2.3` — Apache 2.0, neural training framework
- `torch >=2.3` — BSD, PyTorch backend (~2GB combined)

## Issues

### C1: Neural IV Surface Model
**FR**: FR-S8a
**Description**: Implement `IVSurfaceNet(L.LightningModule)` in `pricing/neural_surface.py` — MLP that maps (log_moneyness, dte_normalized) to IV. Architecture: 3 hidden layers, 64 units, ReLU + BatchNorm, softplus output (positive IV). Training harness for per-ticker fitting on live chain data. Checkpoint save/load for warm-start.
**New files**: `pricing/neural_surface.py`
**Modified files**: `models/config.py`
**Est. tests**: ~20
**Acceptance criteria**:
- [ ] MLP architecture: 2-input, 3x64 hidden, 1-output with softplus
- [ ] Training on (log_moneyness, dte, IV) triples from chain data
- [ ] MSE loss + L2 regularization
- [ ] Checkpoint persistence in `data/model_cache/`
- [ ] Guarded PyTorch import — returns None when not installed
- [ ] Config flag `enable_neural_surface: bool = False`

### C2: Neural Surface Pipeline Integration
**FR**: FR-S8b
**Description**: Integrate neural IV surface as alternative fitter in `compute_vol_surface()`. Config flag `surface_method: Literal["spline", "neural"] = "spline"`. Falls back to spline when: <30 data points, Lightning not installed, training timeout. Wire into `scan/phase_options.py`.
**Modified files**: `indicators/vol_surface.py`, `scan/phase_options.py`
**Depends on**: C1
**Est. tests**: ~10
**Acceptance criteria**:
- [ ] `surface_method` config selects spline vs neural
- [ ] Automatic fallback to spline on any neural failure
- [ ] Neural surface results compatible with `VolSurfaceResult`
- [ ] Pipeline integration gated by config

### C3: LSTM Trajectory Forecasting Model
**FR**: FR-S9a
**Description**: Implement `TrajectoryLSTM(L.LightningModule)` in `pricing/trajectory.py` — LSTM that produces probabilistic price trajectories. Input: 60-day sequence of (OHLCV + indicators). Output: per-horizon (mean, std) for lognormal distribution at 30/60/90 DTE. Derive `prob_profit_neural` from predicted distribution.
**New files**: `pricing/trajectory.py`
**Modified files**: `models/analysis.py`
**Est. tests**: ~20
**Acceptance criteria**:
- [ ] LSTM: 2 layers, 128 hidden, dropout 0.2, 8-feature input
- [ ] Output: (mean, std) at 30/60/90 DTE horizons
- [ ] `prob_profit_neural` = P(S_T > strike) from predicted distribution
- [ ] Guarded PyTorch import — returns None when not installed
- [ ] Falls back to BSM lognormal assumption when model unavailable

### C4: Trajectory Integration + Agent Enrichment
**FR**: FR-S9b
**Description**: Wire trajectory model into pipeline and agent prompts. `prob_profit_neural` available to all agents as supplementary probability estimate. Render in `agents/_parsing.py`. Enrich Volatility Agent with neural surface residuals context.
**Modified files**: `agents/volatility.py`, `agents/_parsing.py`, `models/config.py`
**Depends on**: C1, C3
**Est. tests**: ~10
**Acceptance criteria**:
- [ ] `prob_profit_neural` rendered in agent context when available
- [ ] Volatility Agent receives neural surface vs spline comparison
- [ ] Config flag `enable_trajectory: bool = False`
- [ ] All features no-op when config flags are False
- [ ] Existing tests pass with default config

## Dependency Graph

```
Epic A (config infra from A1 required)
 |
 v
C1 (neural surface model) ──→ C2 (surface integration)
                                                        \
C3 (LSTM trajectory) ───────────────────────────────────→ C4 (trajectory + agent enrichment)
```

C1 and C3 can run in parallel. C2 depends on C1. C4 depends on C1 and C3.

## Estimated Effort

- **Size**: L (~2-3 sessions)
- **Tests**: ~60 new tests
- **Risk**: Medium — PyTorch Lightning is the project's first neural integration. CPU-only training may be slow for larger chains.

## Success Criteria

| Metric | Target |
|--------|--------|
| Neural surface R² vs spline | >5% improvement on liquid chains |
| Neural surface inference latency | <50ms per ticker |
| Trajectory inference latency | <100ms per ticker |
| Existing test suite | 100% pass (zero regressions) |
| Default config behavior | Identical to current — all features off |
