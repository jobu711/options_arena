/**
 * E2E tests: Weight Tuning tab on Analytics page.
 *
 * Covers: navigation to tab, empty state, auto-tune trigger,
 * weight comparison grid, and weight history chart rendering.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { AnalyticsPage } from '../../fixtures/pages/analytics.page'
import { mockAllApis, mockGet, mockPost, pathMatcher } from '../../fixtures/mocks/api-handlers'
import {
  buildPerformanceSummary,
  buildWinRateResults,
  buildCalibrationBuckets,
  buildHoldingPeriods,
  buildDeltaPerformance,
  buildAgentWeights,
  buildWeightHistory,
} from '../../fixtures/builders/analytics.builders'

/** Mock the base analytics endpoints (needed for the page to render data state). */
async function mockBaseAnalytics(page: import('@playwright/test').Page): Promise<void> {
  await mockAllApis(page)
  await mockGet(page, url => url.pathname === '/api/analytics/summary', buildPerformanceSummary())
  await mockGet(page, pathMatcher('/api/analytics/win-rate'), buildWinRateResults())
  await mockGet(page, url => url.pathname === '/api/analytics/score-calibration', buildCalibrationBuckets())
  await mockGet(page, url => url.pathname === '/api/analytics/holding-period', buildHoldingPeriods())
  await mockGet(page, url => url.pathname === '/api/analytics/delta-performance', buildDeltaPerformance())

  // Backtest overview endpoints (loaded on mount)
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/equity-curve', [])
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/drawdown', [])
}

/** Navigate to Analytics page and switch to Weight Tuning tab. */
async function gotoWeightTuningTab(analytics: AnalyticsPage): Promise<void> {
  await analytics.goto()
  await analytics.expectLoaded()
  await analytics.clickTab('Weight Tuning')
}

test.describe('Weight Tuning Tab', () => {
  test('navigates to weight tuning tab', async ({ page }) => {
    await mockBaseAnalytics(page)
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), buildAgentWeights())
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), buildWeightHistory())

    const analytics = new AnalyticsPage(page)
    await gotoWeightTuningTab(analytics)

    // Tab should be active and panel visible
    await analytics.expectWeightTuningTabVisible()
    await expect(analytics.autoTuneBtn).toBeVisible()
  })

  test('shows empty state when no weights', async ({ page }) => {
    await mockBaseAnalytics(page)
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), [])
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), [])

    const analytics = new AnalyticsPage(page)
    await gotoWeightTuningTab(analytics)

    await analytics.expectWeightTuningTabVisible()
    await expect(analytics.weightTuningPanel.locator('text=No tuned weights yet')).toBeVisible()
  })

  test('auto-tune button triggers computation', async ({ page }) => {
    await mockBaseAnalytics(page)
    // Start with empty weights
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), [])
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), [])

    // Mock the POST auto-tune endpoint to return populated weights
    const tuned = buildAgentWeights()
    await mockPost(page, pathMatcher('/api/analytics/weights/auto-tune'), 200, tuned)

    const analytics = new AnalyticsPage(page)
    await gotoWeightTuningTab(analytics)
    await analytics.expectWeightTuningTabVisible()

    // Before: empty state
    await expect(analytics.weightTuningPanel.locator('text=No tuned weights yet')).toBeVisible()

    // Now mock the GET endpoints to return data (store will re-fetch after auto-tune)
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), tuned)
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), buildWeightHistory())

    // Click Auto-Tune
    await analytics.autoTuneBtn.click()

    // Success toast should appear
    await expect(
      page.locator('.p-toast-message-success, [data-pc-name="toast"]').first(),
    ).toBeVisible({ timeout: 5000 })

    // Weight grid should now show agent data
    await expect(analytics.weightTuningPanel.locator('text=trend')).toBeVisible()
  })

  test('displays weight comparison grid', async ({ page }) => {
    await mockBaseAnalytics(page)
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), buildAgentWeights())
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), buildWeightHistory())

    const analytics = new AnalyticsPage(page)
    await gotoWeightTuningTab(analytics)
    await analytics.expectWeightTuningTabVisible()

    // Verify grid headers
    const panel = analytics.weightTuningPanel
    await expect(panel.locator('.grid-header:has-text("Agent")')).toBeVisible()
    await expect(panel.locator('.grid-header:has-text("Manual")')).toBeVisible()
    await expect(panel.locator('.grid-header:has-text("Tuned")')).toBeVisible()
    await expect(panel.locator('.grid-header:has-text("Delta")')).toBeVisible()
    await expect(panel.locator('.grid-header:has-text("Brier")')).toBeVisible()
    await expect(panel.locator('.grid-header:has-text("Samples")')).toBeVisible()

    // Verify agent names from seeded data
    await expect(panel.locator('text=trend')).toBeVisible()
    await expect(panel.locator('text=volatility')).toBeVisible()
    await expect(panel.locator('text=risk')).toBeVisible()
    await expect(panel.locator('text=flow')).toBeVisible()
    await expect(panel.locator('text=fundamental')).toBeVisible()

    // Verify at least one numeric value from the mock data
    // trend: manual_weight=0.200, auto_weight=0.220
    await expect(panel.locator('text=0.200')).toBeVisible()
    await expect(panel.locator('text=0.220')).toBeVisible()
  })

  test('displays weight history chart', async ({ page }) => {
    await mockBaseAnalytics(page)
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), buildAgentWeights())
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), buildWeightHistory())

    const analytics = new AnalyticsPage(page)
    await gotoWeightTuningTab(analytics)
    await analytics.expectWeightTuningTabVisible()

    // Weight History heading should be visible
    await expect(analytics.weightTuningPanel.locator('h3:has-text("Weight History")')).toBeVisible()

    // Chart.js renders to a <canvas> element inside the chart container
    await expect(analytics.weightTuningPanel.locator('.chart-container canvas')).toBeVisible()
  })

  test('shows empty chart message when no history', async ({ page }) => {
    await mockBaseAnalytics(page)
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), buildAgentWeights())
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), [])

    const analytics = new AnalyticsPage(page)
    await gotoWeightTuningTab(analytics)
    await analytics.expectWeightTuningTabVisible()

    // Should show the empty history message
    await expect(
      analytics.weightTuningPanel.locator('text=No weight history available yet'),
    ).toBeVisible()
  })

  test('Weight Tuning tab is listed among analytics tabs', async ({ page }) => {
    await mockBaseAnalytics(page)
    await mockGet(page, pathMatcher('/api/analytics/agent-weights'), [])
    await mockGet(page, pathMatcher('/api/analytics/weights/history'), [])

    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    // All 6 tabs should be visible including Weight Tuning
    await expect(
      page.locator('[data-pc-name="tab"]:has-text("Weight Tuning")'),
    ).toBeVisible()
  })
})
