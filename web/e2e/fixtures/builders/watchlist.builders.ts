import type { Watchlist, WatchlistDetail, WatchlistTicker } from '../../../src/types/watchlist'

let watchlistIdCounter = 100

export function buildWatchlist(overrides: Partial<Watchlist> = {}): Watchlist {
  return {
    id: watchlistIdCounter++,
    name: 'Tech Stocks',
    created_at: '2026-02-26T14:00:00+00:00',
    ...overrides,
  }
}

export function buildWatchlistTicker(overrides: Partial<WatchlistTicker> = {}): WatchlistTicker {
  return {
    ticker: 'AAPL',
    added_at: '2026-02-26T15:00:00+00:00',
    composite_score: 7.3,
    direction: 'bullish',
    last_debate_at: '2026-02-26T16:00:00+00:00',
    ...overrides,
  }
}

export function buildWatchlistDetail(overrides: Partial<WatchlistDetail> = {}): WatchlistDetail {
  return {
    id: 1,
    name: 'Tech Stocks',
    created_at: '2026-02-26T14:00:00+00:00',
    tickers: [
      buildWatchlistTicker({ ticker: 'AAPL', composite_score: 7.3, direction: 'bullish' }),
      buildWatchlistTicker({ ticker: 'MSFT', composite_score: 6.8, direction: 'bullish' }),
      buildWatchlistTicker({ ticker: 'GOOGL', composite_score: 5.2, direction: 'neutral' }),
    ],
    ...overrides,
  }
}

export function buildEmptyWatchlistDetail(id = 1, name = 'My Watchlist'): WatchlistDetail {
  return {
    id,
    name,
    created_at: '2026-02-26T14:00:00+00:00',
    tickers: [],
  }
}
