/**
 * E2E tests: Analytics Dashboard — Backtest tabs.
 *
 * Covers: all 5 tabs (Overview, Agents, Segments, Greeks, Holding),
 * tab switching, empty states, chart rendering with seeded data,
 * and canvas presence for Chart.js components.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { AnalyticsPage } from '../../fixtures/pages/analytics.page'
import { mockAllApis, mockGet, pathMatcher } from '../../fixtures/mocks/api-handlers'
import {
  buildPerformanceSummary,
  buildWinRateResults,
  buildCalibrationBuckets,
  buildHoldingPeriods,
  buildDeltaPerformance,
  buildEquityCurve,
  buildDrawdown,
  buildSectorPerformance,
  buildDTEBuckets,
  buildIVBuckets,
  buildGreeksDecomposition,
  buildHoldingComparison,
  buildAgentAccuracy,
  buildAgentCalibration,
} from '../../fixtures/builders/analytics.builders'

/** Mock all analytics + backtest endpoints with populated data. */
async function mockAllBacktestApis(page: import('@playwright/test').Page): Promise<void> {
  await mockAllApis(page)

  // Base analytics endpoints
  await mockGet(page, url => url.pathname === '/api/analytics/summary', buildPerformanceSummary())
  await mockGet(page, pathMatcher('/api/analytics/win-rate'), buildWinRateResults())
  await mockGet(page, url => url.pathname === '/api/analytics/score-calibration', buildCalibrationBuckets())
  await mockGet(page, url => url.pathname === '/api/analytics/holding-period', buildHoldingPeriods())
  await mockGet(page, url => url.pathname === '/api/analytics/delta-performance', buildDeltaPerformance())

  // Backtest endpoints
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/equity-curve', buildEquityCurve())
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/drawdown', buildDrawdown())
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/sector-performance', buildSectorPerformance())
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/dte-performance', buildDTEBuckets())
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/iv-performance', buildIVBuckets())
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/greeks-decomposition', buildGreeksDecomposition())
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/holding-comparison', buildHoldingComparison())

  // Agent analytics endpoints (used by Agents tab)
  await mockGet(page, pathMatcher('/api/analytics/agent-accuracy'), buildAgentAccuracy())
  await mockGet(page, pathMatcher('/api/analytics/agent-calibration'), buildAgentCalibration())
}

/** Mock all endpoints with empty backtest data. */
async function mockEmptyBacktestApis(page: import('@playwright/test').Page): Promise<void> {
  await mockAllApis(page)

  await mockGet(page, url => url.pathname === '/api/analytics/summary', buildPerformanceSummary())
  await mockGet(page, pathMatcher('/api/analytics/win-rate'), buildWinRateResults())
  await mockGet(page, url => url.pathname === '/api/analytics/score-calibration', buildCalibrationBuckets())
  await mockGet(page, url => url.pathname === '/api/analytics/holding-period', buildHoldingPeriods())
  await mockGet(page, url => url.pathname === '/api/analytics/delta-performance', buildDeltaPerformance())

  // Empty backtest data
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/equity-curve', [])
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/drawdown', [])
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/sector-performance', [])
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/dte-performance', [])
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/iv-performance', [])
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/greeks-decomposition', [])
  await mockGet(page, url => url.pathname === '/api/analytics/backtest/holding-comparison', [])
  await mockGet(page, pathMatcher('/api/analytics/agent-accuracy'), [])
  await mockGet(page, pathMatcher('/api/analytics/agent-calibration'), { agent_name: null, buckets: [], sample_size: 0 })
}

test.describe('Analytics Dashboard — Overview Tab', () => {
  test('overview tab shows equity curve and drawdown charts', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()
    await analytics.expectOverviewChartsVisible()
  })

  test('equity curve chart renders a canvas element', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    // Chart.js renders to <canvas>
    await expect(analytics.equityCurveChart.locator('canvas')).toBeVisible()
  })

  test('drawdown chart renders a canvas element', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await expect(analytics.drawdownChart.locator('canvas')).toBeVisible()
  })

  test('overview tab shows empty state when no equity curve data', async ({ page }) => {
    await mockEmptyBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await expect(analytics.equityCurveChart.locator('text=No equity curve data available')).toBeVisible()
    await expect(analytics.drawdownChart.locator('text=No drawdown data available')).toBeVisible()
  })
})

test.describe('Analytics Dashboard — Agents Tab', () => {
  test('agents tab shows accuracy heatmap', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Agents')
    await analytics.expectAgentsTabVisible()
  })

  test('agents tab shows agent names', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Agents')
    await analytics.expectAgentsTabVisible()

    // Should display agent names from seeded data
    await expect(analytics.agentAccuracyHeatmap.locator('text=trend')).toBeVisible()
    await expect(analytics.agentAccuracyHeatmap.locator('text=bear')).toBeVisible()
  })

  test('agents tab shows empty state when no accuracy data', async ({ page }) => {
    await mockEmptyBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Agents')
    await expect(analytics.agentAccuracyHeatmap.locator('text=No agent accuracy data available')).toBeVisible()
  })
})

test.describe('Analytics Dashboard — Segments Tab', () => {
  test('segments tab shows sector, DTE, and IV charts', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Segments')
    await analytics.expectSegmentsTabVisible()
  })

  test('sector performance chart renders a canvas', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Segments')
    await expect(analytics.sectorPerformanceChart.locator('canvas')).toBeVisible()
  })

  test('segments tab shows empty state when no data', async ({ page }) => {
    await mockEmptyBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Segments')
    await expect(analytics.sectorPerformanceChart.locator('text=No sector performance data available')).toBeVisible()
  })
})

test.describe('Analytics Dashboard — Greeks Tab', () => {
  test('greeks tab shows decomposition chart', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Greeks')
    await analytics.expectGreeksTabVisible()
  })

  test('greeks chart renders a canvas element', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Greeks')
    await expect(analytics.greeksDecompositionChart.locator('canvas')).toBeVisible()
  })

  test('greeks tab shows empty state when no data', async ({ page }) => {
    await mockEmptyBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Greeks')
    await expect(analytics.greeksDecompositionChart.locator('text=No Greeks decomposition data available')).toBeVisible()
  })
})

test.describe('Analytics Dashboard — Holding Tab', () => {
  test('holding tab shows comparison table', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Holding')
    await analytics.expectHoldingTabVisible()
  })

  test('holding table displays data rows', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Holding')
    await analytics.expectHoldingTabVisible()

    // Should display at least one data row (PrimeVue DataTable rows)
    await expect(analytics.holdingComparisonTable.locator('.p-datatable-tbody tr').first()).toBeVisible()
  })

  test('holding tab shows empty state when no data', async ({ page }) => {
    await mockEmptyBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    await analytics.clickTab('Holding')
    await expect(analytics.holdingComparisonTable.locator('text=No holding period comparison data available')).toBeVisible()
  })
})

test.describe('Analytics Dashboard — Tab Switching', () => {
  test('switching tabs loads different content', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    // Default: Overview tab
    await analytics.expectOverviewChartsVisible()

    // Switch to Segments
    await analytics.clickTab('Segments')
    await analytics.expectSegmentsTabVisible()

    // Switch to Greeks
    await analytics.clickTab('Greeks')
    await analytics.expectGreeksTabVisible()

    // Switch to Holding
    await analytics.clickTab('Holding')
    await analytics.expectHoldingTabVisible()
  })

  test('switching back to Overview preserves charts', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()
    await analytics.expectOverviewChartsVisible()

    // Navigate away
    await analytics.clickTab('Agents')
    await analytics.expectAgentsTabVisible()

    // Come back
    await analytics.clickTab('Overview')
    await analytics.expectOverviewChartsVisible()
  })

  test('all five tabs are visible in tab list', async ({ page }) => {
    await mockAllBacktestApis(page)
    const analytics = new AnalyticsPage(page)
    await analytics.goto()
    await analytics.expectLoaded()

    const tabLabels = ['Overview', 'Agents', 'Segments', 'Greeks', 'Holding']
    for (const label of tabLabels) {
      await expect(page.locator(`[data-pc-name="tab"]:has-text("${label}")`)).toBeVisible()
    }
  })
})
