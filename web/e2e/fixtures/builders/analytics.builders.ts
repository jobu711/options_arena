import type {
  PerformanceSummary,
  WinRateResult,
  ScoreCalibrationBucket,
  HoldingPeriodResult,
  DeltaPerformanceResult,
  OutcomeCollectionResult,
} from '../../../src/types'

export function buildPerformanceSummary(
  overrides: Partial<PerformanceSummary> = {},
): PerformanceSummary {
  return {
    lookback_days: 30,
    total_contracts: 142,
    total_with_outcomes: 89,
    overall_win_rate: 0.632,
    avg_stock_return_pct: 2.4,
    avg_contract_return_pct: 12.8,
    best_direction: 'bullish',
    best_holding_days: 10,
    ...overrides,
  }
}

export function buildEmptySummary(
  overrides: Partial<PerformanceSummary> = {},
): PerformanceSummary {
  return {
    lookback_days: 30,
    total_contracts: 0,
    total_with_outcomes: 0,
    overall_win_rate: null,
    avg_stock_return_pct: null,
    avg_contract_return_pct: null,
    best_direction: null,
    best_holding_days: null,
    ...overrides,
  }
}

export function buildNoOutcomesSummary(): PerformanceSummary {
  return buildPerformanceSummary({
    total_contracts: 50,
    total_with_outcomes: 0,
    overall_win_rate: null,
    avg_stock_return_pct: null,
    avg_contract_return_pct: null,
    best_direction: null,
    best_holding_days: null,
  })
}

export function buildWinRateResults(): WinRateResult[] {
  return [
    { direction: 'bullish', total_contracts: 62, winners: 45, losers: 17, win_rate: 0.726 },
    { direction: 'bearish', total_contracts: 46, winners: 30, losers: 16, win_rate: 0.652 },
    { direction: 'neutral', total_contracts: 20, winners: 9, losers: 11, win_rate: 0.45 },
  ]
}

export function buildCalibrationBuckets(): ScoreCalibrationBucket[] {
  return [
    { score_min: 0, score_max: 20, contract_count: 5, avg_return_pct: -8.2, win_rate: 0.2 },
    { score_min: 20, score_max: 40, contract_count: 12, avg_return_pct: -2.1, win_rate: 0.33 },
    { score_min: 40, score_max: 60, contract_count: 35, avg_return_pct: 3.4, win_rate: 0.54 },
    { score_min: 60, score_max: 80, contract_count: 28, avg_return_pct: 8.7, win_rate: 0.71 },
    { score_min: 80, score_max: 100, contract_count: 8, avg_return_pct: 15.3, win_rate: 0.88 },
  ]
}

export function buildHoldingPeriods(): HoldingPeriodResult[] {
  return [
    { holding_days: 1, direction: 'bullish', avg_return_pct: 1.2, median_return_pct: 0.8, win_rate: 0.55, sample_size: 45 },
    { holding_days: 5, direction: 'bullish', avg_return_pct: 3.8, median_return_pct: 2.9, win_rate: 0.62, sample_size: 42 },
    { holding_days: 10, direction: 'bullish', avg_return_pct: 6.1, median_return_pct: 4.5, win_rate: 0.68, sample_size: 38 },
    { holding_days: 20, direction: 'bullish', avg_return_pct: 8.4, median_return_pct: 5.2, win_rate: 0.72, sample_size: 30 },
  ]
}

export function buildDeltaPerformance(): DeltaPerformanceResult[] {
  return [
    { delta_min: 0.2, delta_max: 0.3, holding_days: 10, avg_return_pct: 5.2, win_rate: 0.58, sample_size: 15 },
    { delta_min: 0.3, delta_max: 0.4, holding_days: 10, avg_return_pct: 8.1, win_rate: 0.65, sample_size: 22 },
    { delta_min: 0.4, delta_max: 0.5, holding_days: 10, avg_return_pct: 6.3, win_rate: 0.62, sample_size: 18 },
    { delta_min: 0.5, delta_max: 0.6, holding_days: 10, avg_return_pct: 3.8, win_rate: 0.55, sample_size: 12 },
  ]
}

export function buildOutcomeResult(
  overrides: Partial<OutcomeCollectionResult> = {},
): OutcomeCollectionResult {
  return { outcomes_collected: 15, ...overrides }
}
