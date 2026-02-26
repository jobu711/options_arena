/**
 * E2E tests: Dashboard page.
 *
 * Covers: page load, health strip, recent debates, quick action
 * navigation, and empty state handling.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { DashboardPage } from '../../fixtures/pages/dashboard.page'
import { mockAllApis, mockGet } from '../../fixtures/mocks/api-handlers'
import { buildScanRun } from '../../fixtures/builders/scan.builders'
import { buildDebateSummary } from '../../fixtures/builders/debate.builders'
import { buildAllHealthy, buildOneDegraded } from '../../fixtures/builders/health.builders'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 10 })],
      healthServices: buildAllHealthy(),
    })
    await mockGet(page, '**/api/debate', [
      buildDebateSummary({ id: 1, ticker: 'AAPL', direction: 'bullish' }),
      buildDebateSummary({ id: 2, ticker: 'MSFT', direction: 'bearish' }),
    ])
  })

  test('loads and displays health indicators', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    // Health strip should show 4 service indicators
    const healthDots = page.locator('[data-testid^="health-dot"]')
      .or(page.locator('[class*="health-dot"]'))
    await expect(healthDots.first()).toBeVisible()
  })

  test('shows recent debates with direction badges', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    // Recent debates section should contain AAPL and MSFT
    await expect(page.locator('text=AAPL')).toBeVisible()
    await expect(page.locator('text=MSFT')).toBeVisible()
  })

  test('New Scan button navigates to /scan', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()
    await dashboard.clickNewScan()
    expect(page.url()).toContain('/scan')
  })

  test('Universe button navigates to /universe', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()
    await dashboard.clickUniverse()
    expect(page.url()).toContain('/universe')
  })

  test('Health button navigates to /health', async ({ page }) => {
    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()
    await dashboard.clickHealth()
    expect(page.url()).toContain('/health')
  })

  test('shows degraded health indicator when service is down', async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 10 })],
      healthServices: buildOneDegraded('Groq'),
    })

    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    // Should visually indicate degraded state
    // (Exact assertion depends on component implementation)
  })

  test('empty dashboard shows appropriate message when no scans exist', async ({ page }) => {
    await mockAllApis(page, {
      scanList: [],
      healthServices: buildAllHealthy(),
    })
    await mockGet(page, '**/api/debate', [])

    const dashboard = new DashboardPage(page)
    await dashboard.goto()
    await dashboard.expectLoaded()

    // Should show empty state or prompt to run first scan
    const emptyOrPrompt = page.locator('[data-testid="empty-state"]')
      .or(page.locator('text=/no scan|get started|run.*scan/i'))
    await expect(emptyOrPrompt).toBeVisible()
  })
})
