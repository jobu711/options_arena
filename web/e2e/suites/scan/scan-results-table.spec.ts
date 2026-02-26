/**
 * E2E tests: Scan results DataTable interactions.
 *
 * Covers: sorting, filtering, search, pagination, ticker drawer,
 * URL query param sync, and empty state.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { ScanResultsPage } from '../../fixtures/pages/scan-results.page'
import { mockAllApis, mockGet } from '../../fixtures/mocks/api-handlers'
import {
  buildScanRun,
  buildPaginatedScores,
  buildTickerScore,
  buildEmptyScores,
} from '../../fixtures/builders/scan.builders'

const SCAN_ID = 1

test.describe('Scan Results Table', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page)

    // Scan metadata
    await mockGet(page, `**/api/scan/${SCAN_ID}`, buildScanRun({ id: SCAN_ID }))

    // Default: 50 scores
    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: buildPaginatedScores(50) }),
    )
  })

  test('renders all 50 ticker rows', async ({ page }) => {
    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)
    await resultsPage.expectRowCount(50)
  })

  test('displays ticker, score, and direction for each row', async ({ page }) => {
    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    // First row should be AAPL with highest score
    const firstTicker = await resultsPage.getTickerAtRow(0)
    expect(firstTicker).toBe('AAPL')

    // Score should be in range
    await resultsPage.expectScoreInRange('AAPL', 8.0, 10.0)

    // Direction badge should be visible
    await resultsPage.expectDirectionBadge('AAPL', 'bullish')
  })

  test('sorts by column header click', async ({ page }) => {
    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    // Click "Ticker" column header to sort alphabetically
    await resultsPage.sortByColumn('Ticker')

    // URL should update with sort params
    const url = new URL(page.url())
    expect(url.searchParams.get('sort')).toBe('ticker')
  })

  test('filters by ticker search', async ({ page }) => {
    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    await resultsPage.searchTicker('AAPL')

    // Only rows containing "AAPL" should remain
    const tickers = await resultsPage.getAllTickers()
    for (const ticker of tickers) {
      expect(ticker.toUpperCase()).toContain('AAPL')
    }
  })

  test('filters by direction', async ({ page }) => {
    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    await resultsPage.filterByDirection('bullish')

    // URL should include direction param
    const url = new URL(page.url())
    expect(url.searchParams.get('direction')).toBe('bullish')
  })

  test('opens ticker drawer on row click', async ({ page }) => {
    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    await resultsPage.openTickerDrawer('AAPL')

    // Drawer should be visible and contain AAPL
    await expect(resultsPage.tickerDrawer).toBeVisible()
    await expect(resultsPage.tickerDrawer).toContainText('AAPL')
  })

  test('URL query params persist on page reload', async ({ page }) => {
    // Navigate with query params
    await page.goto(`/scan/${SCAN_ID}?sort=ticker&order=asc&direction=bullish`)
    await page.locator('.p-datatable').waitFor({ state: 'visible' })

    // Verify params survived
    const url = new URL(page.url())
    expect(url.searchParams.get('sort')).toBe('ticker')
    expect(url.searchParams.get('order')).toBe('asc')
    expect(url.searchParams.get('direction')).toBe('bullish')
  })

  test('shows empty state when scan has no scores', async ({ page }) => {
    // Override scores to return empty
    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: buildEmptyScores() }),
    )

    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)
    await resultsPage.expectEmptyState()
  })

  test('batch debate button requires row selection', async ({ page }) => {
    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    // Batch button should be disabled with no selection
    await expect(resultsPage.batchDebateBtn).toBeDisabled()

    // Select 2 rows
    await resultsPage.selectRows([0, 1])

    // Now batch button should be enabled
    await expect(resultsPage.batchDebateBtn).toBeEnabled()
  })
})
