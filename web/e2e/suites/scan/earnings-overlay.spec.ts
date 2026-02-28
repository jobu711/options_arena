/**
 * E2E tests: Earnings calendar overlay.
 *
 * Covers: earnings column in scan results, warning banner in drawer,
 * graceful no-data handling.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { ScanResultsPage } from '../../fixtures/pages/scan-results.page'
import { mockAllApis, mockGet } from '../../fixtures/mocks/api-handlers'
import {
  buildScanRun,
  buildPaginatedScores,
  buildTickerScore,
} from '../../fixtures/builders/scan.builders'

const SCAN_ID = 1

/** Build a future ISO date string N days from now. */
function futureDate(daysAhead: number): string {
  const d = new Date()
  d.setDate(d.getDate() + daysAhead)
  return d.toISOString().slice(0, 10)
}

test.describe('Earnings Calendar Overlay', () => {
  test('shows earnings DTE in table column', async ({ page }) => {
    await mockAllApis(page)
    await mockGet(page, `**/api/scan/${SCAN_ID}`, buildScanRun({ id: SCAN_ID }))

    // Build scores with earnings dates
    const scores = buildPaginatedScores(3)
    scores.items[0].next_earnings = futureDate(3)
    scores.items[1].next_earnings = futureDate(45)
    scores.items[2].next_earnings = null

    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: scores }),
    )

    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    // First ticker should show "3d" in red
    const firstEarnings = page.locator(`[data-testid="earnings-${scores.items[0].ticker}"]`)
    await expect(firstEarnings).toContainText('3d')

    // Second ticker should show "45d" (gray, not red)
    const secondEarnings = page.locator(`[data-testid="earnings-${scores.items[1].ticker}"]`)
    await expect(secondEarnings).toContainText('45d')

    // Third ticker should show dash
    const thirdEarnings = page.locator(`[data-testid="earnings-${scores.items[2].ticker}"]`)
    await expect(thirdEarnings).toBeVisible()
  })

  test('shows earnings warning banner in drawer when < 7 days', async ({ page }) => {
    await mockAllApis(page)
    await mockGet(page, `**/api/scan/${SCAN_ID}`, buildScanRun({ id: SCAN_ID }))

    const scores = buildPaginatedScores(3)
    scores.items[0].next_earnings = futureDate(3)

    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: scores }),
    )

    // Mock debate list for the drawer
    await page.route('**/api/debate*', route =>
      route.fulfill({ json: [] }),
    )

    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    // Open drawer for the first ticker (has earnings in 3 days)
    await resultsPage.openTickerDrawer(scores.items[0].ticker)

    // Warning banner should be visible
    const warning = page.locator('[data-testid="earnings-warning"]')
    await expect(warning).toBeVisible()
    await expect(warning).toContainText('Earnings in 3 days')
    await expect(warning).toContainText('IV crush risk')
  })

  test('no warning banner when earnings > 7 days', async ({ page }) => {
    await mockAllApis(page)
    await mockGet(page, `**/api/scan/${SCAN_ID}`, buildScanRun({ id: SCAN_ID }))

    const scores = buildPaginatedScores(3)
    scores.items[0].next_earnings = futureDate(30)

    await page.route(`**/api/scan/${SCAN_ID}/scores*`, route =>
      route.fulfill({ json: scores }),
    )

    // Mock debate list for the drawer
    await page.route('**/api/debate*', route =>
      route.fulfill({ json: [] }),
    )

    const resultsPage = new ScanResultsPage(page)
    await resultsPage.goto(SCAN_ID)

    // Open drawer for the first ticker (has earnings in 30 days)
    await resultsPage.openTickerDrawer(scores.items[0].ticker)

    // Warning banner should NOT be visible
    const warning = page.locator('[data-testid="earnings-warning"]')
    await expect(warning).toBeHidden()
  })
})
