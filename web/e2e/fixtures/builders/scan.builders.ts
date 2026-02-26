import type { ScanRun, TickerScore, PaginatedResponse } from '../../../src/types'

let scanIdCounter = 1000

export function buildScanRun(overrides: Partial<ScanRun> = {}): ScanRun {
  return {
    id: scanIdCounter++,
    started_at: '2026-02-26T14:00:00+00:00',
    completed_at: '2026-02-26T14:05:00+00:00',
    preset: 'sp500',
    tickers_scanned: 503,
    tickers_scored: 487,
    recommendations: 50,
    ...overrides,
  }
}

const TICKERS = [
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B',
  'JPM', 'V', 'UNH', 'XOM', 'JNJ', 'PG', 'MA', 'HD', 'CVX', 'MRK',
  'ABBV', 'LLY', 'PEP', 'KO', 'COST', 'AVGO', 'TMO', 'MCD', 'WMT',
  'CSCO', 'ACN', 'ABT', 'DHR', 'NEE', 'LIN', 'TXN', 'PM', 'UNP',
  'RTX', 'BMY', 'SCHW', 'AMGN', 'HON', 'COP', 'LOW', 'MS', 'INTC',
  'QCOM', 'ELV', 'INTU', 'ADP', 'SBUX',
] as const

const DIRECTIONS: Array<'bullish' | 'bearish' | 'neutral'> = ['bullish', 'bearish', 'neutral']

export function buildTickerScore(overrides: Partial<TickerScore> = {}): TickerScore {
  return {
    ticker: 'AAPL',
    composite_score: 7.3,
    direction: 'bullish',
    signals: {
      rsi_14: 55.2, sma_20: 1.02, sma_50: 0.98, sma_200: 1.05,
      macd_signal: 0.5, bb_width: 0.12, obv_trend: 0.8, atr_14: 3.2,
      vwap_ratio: 1.01, adx_14: 28.5, stoch_k: 62.1, stoch_d: 58.4,
      cci_20: 45.0, williams_r: -38.0, roc_12: 2.1, mfi_14: 55.0,
      cmf_20: 0.08, keltner_position: 0.6,
    },
    scan_run_id: 1,
    ...overrides,
  }
}

export function buildPaginatedScores(
  count: number = 50,
  overrides: Partial<PaginatedResponse<TickerScore>> = {},
): PaginatedResponse<TickerScore> {
  const items = TICKERS.slice(0, count).map((ticker, i) =>
    buildTickerScore({
      ticker,
      composite_score: parseFloat((9.0 - i * 0.15).toFixed(1)),
      direction: DIRECTIONS[i % 3],
      scan_run_id: 1,
    }),
  )
  return {
    items,
    total: count,
    page: 1,
    pages: Math.ceil(count / 50),
    ...overrides,
  }
}

/** Build an empty paginated response (for empty-state tests). */
export function buildEmptyScores(): PaginatedResponse<TickerScore> {
  return { items: [], total: 0, page: 1, pages: 0 }
}
