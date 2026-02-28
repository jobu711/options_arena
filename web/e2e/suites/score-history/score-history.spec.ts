/**
 * E2E tests: Score history visualization.
 *
 * Covers: ScoreHistoryChart rendering, Sparklines in scan results,
 * TickerDetailPage, Dashboard trending sections.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { mockAllApis, mockGet, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildScanRun, buildPaginatedScores } from '../../fixtures/builders/scan.builders'
import { buildDebateSummary } from '../../fixtures/builders/debate.builders'
import { buildAllHealthy } from '../../fixtures/builders/health.builders'

/** Build a mock HistoryPoint array for a ticker. */
function buildHistory(ticker: string, count: number = 5) {
  const directions = ['bullish', 'bearish', 'neutral'] as const
  return Array.from({ length: count }, (_, i) => ({
    scan_id: 100 + i,
    scan_date: `2026-02-${String(20 + i).padStart(2, '0')}T14:00:00+00:00`,
    composite_score: 5.0 + i * 0.8,
    direction: directions[i % 3],
    preset: 'sp500',
  }))
}

/** Build mock TrendingTicker array. */
function buildTrending(direction: 'bullish' | 'bearish', count: number = 3) {
  const tickers = direction === 'bullish'
    ? ['AAPL', 'NVDA', 'MSFT']
    : ['INTC', 'BA', 'WBA']
  return tickers.slice(0, count).map((ticker, i) => ({
    ticker,
    direction,
    consecutive_scans: 3 + i,
    latest_score: direction === 'bullish' ? 8.0 - i * 0.5 : 3.0 + i * 0.5,
    score_change: direction === 'bullish' ? 1.2 + i * 0.3 : -(1.2 + i * 0.3),
  }))
}

const SCAN_ID = 1

test.describe('Score History', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: SCAN_ID })],
      healthServices: buildAllHealthy(),
    })

    // Mock debate list
    await mockGet(page, pathMatcher('/api/debate'), [
      buildDebateSummary({ id: 1, ticker: 'AAPL', direction: 'bullish' }),
    ])

    // Mock trending endpoints
    await page.route('**/api/ticker/trending*', route => {
      const url = new URL(route.request().url())
      const dir = url.searchParams.get('direction') ?? 'bullish'
      return route.fulfill({
        json: buildTrending(dir as 'bullish' | 'bearish'),
      })
    })

    // Mock per-ticker history endpoints
    await page.route('**/api/ticker/*/history*', route => {
      const urlPath = new URL(route.request().url()).pathname
      const match = urlPath.match(/\/api\/ticker\/([^/]+)\/history/)
      const ticker = match ? match[1] : 'AAPL'
      return route.fulfill({ json: buildHistory(ticker) })
    })

    // Default score mock for scan results
    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: buildPaginatedScores(10) }),
    )

    // Mock scan list for compare dropdown
    await page.route(`**/api/scan/${SCAN_ID}`, route =>
      route.fulfill({ json: buildScanRun({ id: SCAN_ID }) }),
    )
  })

  test('ScoreHistoryChart renders SVG with correct number of circles on ticker page', async ({ page }) => {
    await page.goto('/ticker/AAPL')
    await page.waitForSelector('[data-testid="score-history-chart"]')

    // Chart should be visible
    const chart = page.locator('[data-testid="score-history-chart"]')
    await expect(chart).toBeVisible()

    // Should have 5 data point circles (matching our mock data)
    const circles = chart.locator('[data-testid="chart-point"]')
    await expect(circles).toHaveCount(5)
  })

  test('Sparklines appear in scan results table', async ({ page }) => {
    await page.goto(`/scan/${SCAN_ID}`)
    await page.locator('.p-datatable').waitFor({ state: 'visible' })

    // Wait for sparkline data to load (async fetch after scores load)
    await page.waitForTimeout(1000)

    // At least one sparkline should be visible
    const sparklines = page.locator('[data-testid="sparkline-chart"]')
    const count = await sparklines.count()
    expect(count).toBeGreaterThan(0)
  })

  test('TickerDetailPage shows chart and latest score', async ({ page }) => {
    await page.goto('/ticker/MSFT')
    await page.waitForSelector('[data-testid="ticker-latest-score"]')

    // Latest score should be visible
    const scoreSection = page.locator('[data-testid="ticker-latest-score"]')
    await expect(scoreSection).toBeVisible()

    // Score history chart should be present
    const chart = page.locator('[data-testid="score-history-chart"]')
    await expect(chart).toBeVisible()
  })

  test('Dashboard trending sections populated', async ({ page }) => {
    await page.goto('/')

    // Wait for dashboard to load
    await page.locator('[data-testid^="dashboard"]').first().waitFor({ state: 'visible' })

    // Trending Up section should be visible with tickers
    const trendingUp = page.locator('[data-testid="trending-up-section"]')
    await expect(trendingUp).toBeVisible()
    await expect(trendingUp).toContainText('AAPL')

    // Trending Down section should be visible
    const trendingDown = page.locator('[data-testid="trending-down-section"]')
    await expect(trendingDown).toBeVisible()
    await expect(trendingDown).toContainText('INTC')
  })

  test('TickerDrawer shows score history chart', async ({ page }) => {
    await page.goto(`/scan/${SCAN_ID}`)
    await page.locator('.p-datatable').waitFor({ state: 'visible' })

    // Click the first row to open the drawer
    await page.locator('.p-datatable-tbody tr').first().click()

    // Wait for the drawer to appear
    const drawer = page.locator('[data-testid="ticker-drawer"]')
    await expect(drawer).toBeVisible()

    // Score history section should appear in drawer
    const historySection = drawer.locator('[data-testid="drawer-score-history"]')
    await expect(historySection).toBeVisible()
  })
})
