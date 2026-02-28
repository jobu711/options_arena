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
  next_earnings: string | null // ISO date string "YYYY-MM-DD" or null
  scan_run_id: number
}

/** Paginated response wrapper. */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
}
