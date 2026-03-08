import type { HeatmapTicker } from '../../../src/types'

/** Build a test HeatmapTicker with sensible defaults. */
export function buildHeatmapTicker(
  overrides: Partial<HeatmapTicker> = {},
): HeatmapTicker {
  return {
    ticker: 'AAPL',
    company_name: 'Apple Inc.',
    sector: 'Information Technology',
    industry_group: 'Software & Services',
    market_cap_weight: 100,
    change_pct: 1.5,
    price: 175.5,
    volume: 5_000_000,
    ...overrides,
  }
}

/** Build a minimal set of heatmap tickers across sectors. */
export function buildHeatmapData(): HeatmapTicker[] {
  return [
    buildHeatmapTicker({ ticker: 'AAPL', company_name: 'Apple Inc.', sector: 'Information Technology', change_pct: 1.5, market_cap_weight: 100 }),
    buildHeatmapTicker({ ticker: 'MSFT', company_name: 'Microsoft Corp.', sector: 'Information Technology', change_pct: -0.8, market_cap_weight: 100 }),
    buildHeatmapTicker({ ticker: 'GOOGL', company_name: 'Alphabet Inc.', sector: 'Communication Services', change_pct: 2.1, market_cap_weight: 100 }),
    buildHeatmapTicker({ ticker: 'JPM', company_name: 'JPMorgan Chase', sector: 'Financials', change_pct: -1.2, market_cap_weight: 50 }),
    buildHeatmapTicker({ ticker: 'JNJ', company_name: 'Johnson & Johnson', sector: 'Health Care', change_pct: 0.3, market_cap_weight: 50 }),
  ]
}
