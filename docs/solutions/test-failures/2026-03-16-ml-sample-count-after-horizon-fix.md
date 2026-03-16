---
title: "ML trajectory tests fail after dropping fabricated zero targets"
date: 2026-03-16
module: options_arena.scan.phase_options
problem_type: test_failure
severity: high
symptoms:
  - "test_trajectory_called_when_enabled fails with 0 valid samples"
  - "test_feature_building_uses_correct_sequence_length assertion fails on len(features)"
  - "fit_trajectory_model receives empty features_seq list"
tags:
  - trajectory
  - ml-pipeline
  - test-data-size
  - zero-targets
  - fabricated-data
root_cause: "Fixing fabricated 0.0 targets reduced valid sample count; test OHLCV data too short for seq_len + max_horizon"
---

## Problem

After fixing `_compute_trajectory_prob` to drop samples where `i + max_horizon >= len(ohlcv_list)`
instead of fabricating `0.0` target returns, multiple trajectory tests started failing.
Tests used minimal OHLCV bar counts (n=50, n=100) that were sufficient when zero-padding
was allowed but insufficient after the fix.

Example: with `seq_len=20`, `max_horizon=30`, and `n=50` bars, the feature loop starts
at `i=20` but `20 + 30 = 50 >= 50`, so ALL samples are dropped. The model receives an
empty feature list and returns `None`.

## Root Cause

The original code fabricated `0.0` targets for samples near the end of the OHLCV series:

```python
# BAD: fabricates zero returns when horizon extends past data
if i + h >= len(ohlcv_list):
    targets.append(0.0)
```

This biased training data toward zero returns. The fix drops these samples entirely:

```python
# GOOD: skip samples with incomplete horizons
if i + max_horizon >= len(ohlcv_list):
    features_seq.pop()
    continue
```

But tests assumed the old sample count formula: `n - seq_len`. The correct formula after
the fix is: `n - seq_len - max_horizon`.

## Solution

Updated test data sizes to ensure enough valid samples exist:

| Test | Before | After | Rationale |
|------|--------|-------|-----------|
| `test_trajectory_called_when_enabled` | n=100 | n=200 | seq_len=60, max_horizon=90, need >= 152 |
| `test_feature_building_uses_correct_sequence_length` | n=50 | n=80 | seq_len=20, max_horizon=30, yields 30 valid |

Updated assertion: `len(features) == n - seq_len - max_horizon` (was `n - seq_len`).

## Prevention Rule

**When building ML training data from time series, the minimum bar count is
`seq_len + max_horizon + min_samples`.** Tests must use this formula. When fixing
data preparation logic (removing padding, changing windowing), immediately update
ALL test data sizes using the corrected formula. Add a comment documenting the
formula in each test: `# Need: seq_len + max_horizon + expected_samples bars`.

## Related

- PR #555 (CodeRabbit review — "fabricated zero targets" suggestion)
- `src/options_arena/scan/phase_options.py` (`_compute_trajectory_prob`)
- `tests/unit/scan/test_phase_options_trajectory.py`
