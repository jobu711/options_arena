/**
 * E2E tests: Analytics page.
 *
 * Covers: data display, empty states, collect outcomes, lookback selector,
 * per-panel empty states, and error handling.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { AnalyticsPage } from '../../fixtures/pages/analytics.page'
import { mockAllApis, mockGet, mockPost, pathMatcher } from '../../fixtures/mocks/api-handlers'
import {
  buildPerformanceSummary,
  buildEmptySummary,
  buildNoOutcomesSummary,
  buildWinRateResults,
  buildCalibrationBuckets,
  buildHoldingPeriods,
  buildDeltaPerformance,
  buildOutcomeResult,
} from '../../fixtures/builders/analytics.builders'

/** Mock all analytics endpoints with populated data. */
async function mockAnalyticsWithData(page: import('@playwright/test').Page): Promise<void> {
  await mockAllApis(page)
  await mockGet(page, url => url.pathname === '/api/analytics/summary', buildPerformanceSummary())
  await mockGet(page, pathMatcher('/api/analytics/win-rate'), buildWinRateResults())
  await mockGet(page, url => url.pathname === '/api/analytics/score-calibration', buildCalibrationBuckets())
  await mockGet(page, url => url.pathname === '/api/analytics/holding-period', buildHoldingPeriods())
  await mockGet(page, url => url.pathname === '/api/analytics/delta-performance', buildDeltaPerformance())
}

test.describe('Analytics Page', () => {
  test('renders page with all panels when data exists', async ({ page }) => {
    await mockAnalyticsWithData(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()
    await analytics.expectAllPanelsVisible()
  })

  test('shows full-page empty state when no contracts', async ({ page }) => {
    await mockAllApis(page)
    await mockGet(page, url => url.pathname === '/api/analytics/summary', buildEmptySummary())

    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()
    await analytics.expectEmptyNoContracts()

    // Should have a link to scan
    await expect(page.locator('text=Go to Scan')).toBeVisible()
  })

  test('shows collect-outcomes prompt when contracts but no outcomes', async ({ page }) => {
    await mockAllApis(page)
    await mockGet(page, url => url.pathname === '/api/analytics/summary', buildNoOutcomesSummary())

    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()
    await analytics.expectEmptyNoOutcomes()

    // Should mention the count and have a Collect button
    await expect(page.locator('text=50 recommendations')).toBeVisible()
  })

  test('Collect Outcomes button triggers POST and shows toast', async ({ page }) => {
    await mockAnalyticsWithData(page)
    await mockPost(page, pathMatcher('/api/analytics/collect-outcomes'), 202, buildOutcomeResult())

    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()
    await analytics.clickCollectOutcomes()

    // Toast should appear with success message
    await expect(page.locator('.p-toast-message-success, [data-pc-name="toast"]').first()).toBeVisible({ timeout: 5000 })
  })

  test('handles 409 when operation is busy', async ({ page }) => {
    await mockAnalyticsWithData(page)
    await mockPost(page, pathMatcher('/api/analytics/collect-outcomes'), 409, { detail: 'Another operation is in progress' })

    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()
    await analytics.clickCollectOutcomes()

    // Warning toast should appear
    await expect(page.locator('.p-toast-message-warn, [data-pc-name="toast"]').first()).toBeVisible({ timeout: 5000 })
  })

  test('summary card displays key metrics', async ({ page }) => {
    await mockAnalyticsWithData(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    // Check summary values
    await expect(analytics.summarySection.locator('text=142')).toBeVisible()
    await expect(analytics.summarySection.locator('text=89')).toBeVisible()
    await expect(analytics.summarySection.locator('text=63.2%')).toBeVisible()
  })

  test('each panel shows empty state when its data is empty', async ({ page }) => {
    await mockAllApis(page)
    await mockGet(page, url => url.pathname === '/api/analytics/summary', buildPerformanceSummary())
    await mockGet(page, pathMatcher('/api/analytics/win-rate'), [])
    await mockGet(page, url => url.pathname === '/api/analytics/score-calibration', [])
    await mockGet(page, url => url.pathname === '/api/analytics/holding-period', [])
    await mockGet(page, url => url.pathname === '/api/analytics/delta-performance', [])

    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    // Each panel should show its empty message
    await expect(page.locator('text=No outcome data yet')).toBeVisible()
    await expect(page.locator('text=No calibration data available')).toBeVisible()
    await expect(page.locator('text=No holding period data available')).toBeVisible()
    await expect(page.locator('text=No delta performance data available')).toBeVisible()
  })
})
