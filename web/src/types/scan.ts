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

/** 8-family dimensional score breakdown. */
export interface DimensionalScores {
  trend: number | null
  iv_vol: number | null
  hv_vol: number | null
  flow: number | null
  microstructure: number | null
  fundamental: number | null
  regime: number | null
  risk: number | null
}

/** Ticker score from scan results. */
export interface TickerScore {
  ticker: string
  composite_score: number
  direction: 'bullish' | 'bearish' | 'neutral'
  signals: Record<string, number | null>
  next_earnings: string | null // ISO date string "YYYY-MM-DD" or null
  scan_run_id: number
  sector: string | null
  company_name: string | null
  industry_group: string | null
  thematic_tags: string[]
  dimensional_scores?: DimensionalScores | null
  direction_confidence?: number | null
  market_regime?: 'trending' | 'mean_reverting' | 'volatile' | 'crisis' | null
}

/** Sector option from GET /api/universe/sectors (flat, backward compat). */
export interface SectorOption {
  name: string
  ticker_count: number
}

/** Industry group info within a sector hierarchy. */
export interface IndustryGroupInfo {
  name: string
  ticker_count: number
}

/** Hierarchical sector with nested industry groups from GET /api/universe/sectors. */
export interface SectorHierarchy {
  name: string
  ticker_count: number
  industry_groups: IndustryGroupInfo[]
}

/** Investment theme from GET /api/universe/themes. */
export interface ThemeInfo {
  name: string
  ticker_count: number
  source_etfs: string[]
}

/** Paginated response wrapper. */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
}

/** Score change for a single ticker between two scans. */
export interface TickerDelta {
  ticker: string
  current_score: number
  previous_score: number
  score_change: number
  current_direction: string
  previous_direction: string | null
  is_new: boolean
}

/** Full diff between two scans. */
export interface ScanDiff {
  current_scan_id: number
  base_scan_id: number
  added: string[]
  removed: string[]
  movers: TickerDelta[]
}

/** Market regime type alias. */
export type MarketRegime = 'trending' | 'mean_reverting' | 'volatile' | 'crisis'

/** Post-scan dimensional filter parameters for ScanResultsPage. */
export interface FilterParams {
  min_score?: number
  min_confidence?: number
  min_trend?: number
  min_iv_vol?: number
  min_flow?: number
  min_risk?: number
  market_regime?: MarketRegime | null
  max_earnings_days?: number
  min_earnings_days?: number
}
