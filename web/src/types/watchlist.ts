/** Watchlist data types for the watchlist management UI. */

export interface Watchlist {
  id: number
  name: string
  description: string | null
  created_at: string // ISO 8601
  updated_at: string // ISO 8601
}

export interface WatchlistTicker {
  id: number
  watchlist_id: number
  ticker: string
  added_at: string // ISO 8601
}

export interface WatchlistDetail extends Watchlist {
  tickers: WatchlistTicker[]
}
