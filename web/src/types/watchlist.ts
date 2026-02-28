/** Watchlist types for the watchlist feature. */

/** A user-defined watchlist (from GET /api/watchlist). */
export interface Watchlist {
  id: number
  name: string
  created_at: string // ISO 8601
}

/** A ticker in a watchlist with enriched data. */
export interface WatchlistTicker {
  ticker: string
  added_at: string // ISO 8601
  composite_score: number | null
  direction: string | null
  last_debate_at: string | null // ISO 8601 or null
}

/** Full watchlist detail with enriched tickers (from GET /api/watchlist/:id). */
export interface WatchlistDetail {
  id: number
  name: string
  created_at: string // ISO 8601
  tickers: WatchlistTicker[]
}
