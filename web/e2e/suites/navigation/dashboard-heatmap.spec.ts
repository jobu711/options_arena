/**
 * E2E tests: Dashboard heatmap integration.
 *
 * Covers: heatmap section visibility, cell rendering, click navigation,
 * and graceful degradation when the heatmap API fails.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { DashboardPage } from '../../fixtures/pages/dashboard.page'
import { mockAllApis, mockGet, mockServerError, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildScanRun } from '../../fixtures/builders/scan.builders'
import { buildAllHealthy } from '../../fixtures/builders/health.builders'
import { buildHeatmapData } from '../../fixtures/builders/heatmap.builders'

test.describe('Dashboard Heatmap', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 10 })],
      healthServices: buildAllHealthy(),
      heatmapTickers: buildHeatmapData(),
    })
    await mockGet(page, pathMatcher('/api/debate'), [])
  })

  test('heatmap section is visible on dashboard', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    const heatmapSection = page.locator('[data-testid="dashboard-heatmap"]')
    await expect(heatmapSection).toBeVisible()

    // "Market Overview" heading should be present
    await expect(page.locator('text=Market Overview')).toBeVisible()
  })

  test('heatmap cells render with ticker labels', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    // Wait for heatmap cells to appear
    const cells = page.locator('.heatmap-cell')
    await expect(cells.first()).toBeVisible()

    // Should have cells for the test tickers
    const cellCount = await cells.count()
    expect(cellCount).toBeGreaterThanOrEqual(3)

    // At least some cells should show ticker text
    const tickerLabels = page.locator('.cell-ticker')
    await expect(tickerLabels.first()).toBeVisible()
  })

  test('clicking a heatmap cell navigates to ticker page', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    // Wait for cells to render
    const firstCell = page.locator('.heatmap-cell').first()
    await expect(firstCell).toBeVisible()

    // Click the first cell
    await firstCell.click()

    // Should navigate to /ticker/:ticker
    await page.waitForURL('**/ticker/*')
    expect(page.url()).toContain('/ticker/')
  })

  test('dashboard loads when heatmap API fails', async ({ page }) => {
    // Provide non-heatmap mocks first
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 10 })],
      healthServices: buildAllHealthy(),
    })
    // Mock heatmap as error (after mockAllApis so it takes precedence)
    await page.route(pathMatcher('/api/market/heatmap'), route =>
      route.fulfill({ status: 500, json: { detail: 'Heatmap unavailable' } }),
    )

    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    // Dashboard should still function — health strip and scan card should appear
    const healthStrip = page.locator('[data-testid="dashboard-health-strip"]')
    await expect(healthStrip).toBeVisible()
  })
})
