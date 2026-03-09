---
epic: agent-calibration
verified_at: 2026-03-09T20:30:00Z
result: PASS
pass: 25
warn: 3
fail: 0
skip: 0
total_tests: 84
tests_passing: 84
---

# Verification Report: agent-calibration

## Traceability Matrix

| # | Requirement | Source | Evidence | Status |
|---|-------------|--------|----------|--------|
| FR1.1 | AgentAccuracyReport model (frozen, validated) | PRD FR1 | analytics.py:654-701 | PASS |
| FR1.2 | math.isfinite() on all float fields | PRD FR1 | analytics.py:669,679,689 | PASS |
| FR1.3 | direction_hit_rate [0.0, 1.0] | PRD FR1 | analytics.py:671-672 | PASS |
| FR1.4 | brier_score [0.0, 1.0] | PRD FR1 | analytics.py:691-692 | PASS |
| FR1.5 | sample_size >= 0 | PRD FR1 | analytics.py:698-700 | PASS |
| FR1.6 | get_agent_accuracy(window_days) | PRD FR1 | repository.py:1516-1588 | PASS |
| FR1.7 | 10-sample minimum enforced | PRD FR1 | repository.py:1571 HAVING >= 10 | PASS |
| FR2.1 | CalibrationBucket model (frozen, validated) | PRD FR2 | analytics.py:704-752 | PASS |
| FR2.2 | AgentCalibrationData model (frozen) | PRD FR2 | analytics.py:755-770 | PASS |
| FR2.3 | get_agent_calibration(agent_name) | PRD FR2 | repository.py:1590-1673 | PASS |
| FR3.1 | AgentWeightsComparison model (frozen) | PRD FR3 | analytics.py:773-811 | PASS |
| FR3.2 | compute_auto_tune_weights pure function | PRD FR3 | orchestrator.py:912-944 | PASS |
| FR3.3 | Floor=0.05, cap=0.35, risk=0.0, sum=0.85 | PRD FR3 | orchestrator.py:924-942 | PASS |
| FR3.4 | <10 samples keep manual weight | PRD FR3 | orchestrator.py:921 | PASS |
| FR3.5 | auto_tune_weights migration | PRD FR3 | 028_auto_tune_weights.sql | PASS |
| FR3.6 | DebateConfig.auto_tune_weights = False | PRD FR3 | config.py:341 | PASS |
| FR4.1 | synthesize_verdict vote_weights param | PRD FR4 | orchestrator.py:1134 | PASS |
| FR4.2 | run_debate loads auto-tuned weights | PRD FR4 | orchestrator.py:1373-1382 | PASS |
| FR4.3 | synthesize_verdict remains pure | PRD FR4 | orchestrator.py:1163 (no I/O) | PASS |
| FR5.1 | CLI agent-accuracy --window | PRD FR5 | outcomes.py:249-302 | PASS |
| FR5.2 | CLI calibration --agent | PRD FR5 | outcomes.py:305-362 | PASS |
| FR5.3 | CLI agent-weights | PRD FR5 | outcomes.py:365-419 | PASS |
| FR6.1 | GET /api/analytics/agent-accuracy | PRD FR6 | analytics.py:152-160 | PASS |
| FR6.2 | GET /api/analytics/agent-calibration | PRD FR6 | analytics.py:163-171 | PASS |
| FR6.3 | GET /api/analytics/agent-weights | PRD FR6 | analytics.py:174-181 | PASS |
| NFR1 | Composite index on agent_predictions | PRD NFR1 | 027_agent_accuracy_index.sql | PASS |
| NFR3.1 | Manual weights remain default | PRD NFR3 | orchestrator.py:902-909 | PASS |
| NFR3.2 | auto_tune_weights defaults False | PRD NFR3 | config.py:341 | PASS |

## Warnings (non-blocking)

| # | Item | Details |
|---|------|---------|
| W1 | CalibrationBucket bucket_high=1.01 | Last bucket uses 1.01 internally for inclusive capture of confidence=1.0, clamped to 1.0 via min() before model construction. Working correctly. |
| W2 | Neutral direction handling | Neutral predictions scored as misses. Intentional design choice per WHERE clause. |
| W3 | Weight normalization edge case | If all directional agents have zero weight (impossible given 0.05 floor), normalization skipped safely via `if total > 0` guard. |

## Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| tests/unit/models/test_agent_calibration_models.py | 33 | PASS |
| tests/unit/data/test_agent_calibration_queries.py | 13 | PASS |
| tests/unit/agents/test_weight_computation.py | 9 | PASS |
| tests/unit/agents/test_orchestrator_weights.py | 4 | PASS |
| tests/unit/cli/test_outcomes_calibration.py | 7 | PASS |
| tests/unit/api/test_analytics_routes.py (calibration subset) | 8 | PASS |
| tests/integration/test_calibration_pipeline.py | 9 | PASS |
| **Total** | **84** | **ALL PASS** |

Target: 35+ tests. Actual: 84 tests (240% of target).

## Git Commit Traces

| Task | Issue | Commit | Message |
|------|-------|--------|---------|
| #411 | Foundation | dfe57d8 | feat(#411): add agent calibration models, config, and migrations |
| #413 | Repository | f94f4f4 | feat(#413): add agent calibration repository queries |
| #415 | Weights+Orchestrator | 324627a | feat(#415): add auto-tune weight computation and orchestrator integration |
| #410 | CLI Commands | abd7b07 | feat(#410): add agent-accuracy, calibration, and agent-weights CLI commands |
| #412 | API Endpoints | f2f2623 | feat(#412): add agent calibration API endpoints |
| #414 | Integration Tests | c542c91 | feat(#414): add end-to-end calibration pipeline integration tests |

## Exports

All 4 new models exported from `models/__init__.py`: AgentAccuracyReport, AgentCalibrationData, AgentWeightsComparison, CalibrationBucket.

## Result

**25/25 PASS, 0 FAIL, 3 WARN (non-blocking)**

Epic is verified and ready for merge.
