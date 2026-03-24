/** Score history types for ticker trend visualization. */

/** A single scan-score data point for a ticker. */
export interface HistoryPoint {
  scan_id: number
  scan_date: string // ISO 8601 UTC datetime
  composite_score: number
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  preset: string
}

/** A ticker trending in one direction over multiple consecutive scans. */
export interface TrendingTicker {
  ticker: string
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  consecutive_scans: number
  latest_score: number
  score_change: number
}
