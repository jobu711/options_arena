/** Scan run metadata from GET /api/scan. */
export interface ScanRun {
  id: number
  started_at: string
  completed_at: string | null
  preset: 'full' | 'sp500' | 'etfs' | 'nasdaq100' | 'russell2000' | 'most_active'
  source: 'manual'
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

/** Recommended contract from analytics endpoints. */
export interface RecommendedContract {
  id: number | null
  scan_run_id: number
  ticker: string
  option_type: 'call' | 'put'
  strike: string // Decimal as string
  bid: string
  ask: string
  last: string | null
  expiration: string // ISO date
  volume: number
  open_interest: number
  market_iv: number
  delta: number | null
  gamma: number | null
  theta: number | null
  vega: number | null
  direction: 'bullish' | 'bearish' | 'neutral'
  composite_score: number
  entry_stock_price: string | null
  entry_mid: string
  created_at: string
}

/** Ticker info from GET /api/ticker/{ticker}/info. */
export interface TickerInfoResponse {
  ticker: string
  company_name: string
  sector: string
  market_cap: number | null
  market_cap_tier: string | null
  current_price: string // Decimal serialized as string
  fifty_two_week_high: string // Decimal as string
  fifty_two_week_low: string // Decimal as string
  dividend_yield: number
}

/** Scan preset info from GET /api/universe/preset-info. */
export interface PresetInfo {
  preset: string
  label: string
  description: string
  estimated_count: number
}

/** Pre-scan filter payload emitted by PreScanFilters component. */
export interface PreScanFilterPayload {
  preset?: string
  sectors?: string[]
  industryGroups?: string[]
  market_cap_tiers?: string[]
  exclude_near_earnings_days?: number | null
  direction_filter?: string | null
  min_iv_rank?: number | null
  min_price?: number | null
  max_price?: number | null
  min_dte?: number | null
  max_dte?: number | null
  min_score?: number | null
  min_direction_confidence?: number | null
  custom_tickers?: string[]
  top_n?: number | null
  min_dollar_volume?: number | null
  min_oi?: number | null
  min_volume?: number | null
  max_spread_pct?: number | null
  delta_primary_min?: number | null
  delta_primary_max?: number | null
  delta_fallback_min?: number | null
  delta_fallback_max?: number | null
}

/** Single ticker entry for S&P 500 heatmap treemap. */
export interface HeatmapTicker {
  ticker: string
  company_name: string
  sector: string
  industry_group: string
  market_cap_weight: number
  change_pct: number | null
  price: string
  volume: number
}

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
