/** Scan run metadata from GET /api/scan. */
export interface ScanRun {
  id: number
  started_at: string
  completed_at: string | null
  preset: 'full' | 'sp500' | 'etfs'
  tickers_scanned: number
  tickers_scored: number
  recommendations: number
}

/** Ticker score from scan results. */
export interface TickerScore {
  ticker: string
  composite_score: number
  direction: 'bullish' | 'bearish' | 'neutral'
  signals: Record<string, number | null>
  scan_run_id: number
}

/** Paginated response wrapper. */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
}

/** Option Greeks computed by pricing engine. */
export interface OptionGreeks {
  delta: number
  gamma: number
  theta: number
  vega: number
  rho: number
  pricing_model: 'bsm' | 'baw'
}

/** Recommended option contract from GET /api/scan/:id/scores/:ticker. */
export interface OptionContract {
  ticker: string
  option_type: 'call' | 'put'
  strike: string
  expiration: string
  bid: string
  ask: string
  last: string
  volume: number
  open_interest: number
  exercise_style: 'american' | 'european'
  market_iv: number
  greeks: OptionGreeks | null
  mid: string
  spread: string
  dte: number
}

/** Ticker detail with score + recommended contracts. */
export interface TickerDetail {
  ticker: string
  composite_score: number
  direction: 'bullish' | 'bearish' | 'neutral'
  contracts: OptionContract[]
}

