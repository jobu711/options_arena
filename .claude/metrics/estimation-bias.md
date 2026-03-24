# Estimation Bias Tracker

Historical ratio of proxy hours to planned hours across epics.

| Epic | Planned (h) | Proxy (h) | Ratio | Notes |
|------|-------------|-----------|-------|-------|
| agent-calibration | 35 | 1.5 | 0.04 | |
| repository-decomposition | 7 | 1.5 | 0.21 | |
| pipeline-phase-extraction | 12 | 1.0 | 0.08 | |
| backtesting-engine | 84 | 0.5 | 0.006 | |
| service-layer-unification | 21 | 0.6 | 0.03 | |
| pre-scan-filters | 35 | 3.4 | 0.10 | Highest ratio |
| mathematical-computation-audit | 80 | 2.4 | 0.03 | |
| scientific-ml-statistical | 35 | 1.5 | 0.04 | |
| scientific-ml-classification | 18 | 1.2 | 0.07 | |
| scientific-ml-neural | 22 | 1.1 | 0.05 | |
| dead-code-audit | 18 | 1.1 | 0.06 | 20 post-merge fixes |
| ai-agency-desk-foundation | 18 | 0.5 | 0.03 | |
| ai-agency-analysis-tools | 14 | 0.5 | 0.04 | |
| ai-agency-ml-tools | 15 | 1.0 | 0.07 | |
| unified-agent-system-foundation | 17 | 0.3 | 0.02 | |
| recommendation-learning-foundation | 11 | 0.3 | 0.03 | |

## Summary Statistics

- **Median ratio**: 0.04
- **Mean ratio**: 0.05
- **Range**: 0.006 - 0.21
- **Observation**: Planned hours consistently overestimate by ~20-25x. Claude proxy hours cluster at 0.3-1.5h regardless of planned scope.
