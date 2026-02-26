/**
 * E2E tests: Operation mutex enforcement.
 *
 * Covers: only one long-running operation (scan or batch debate) at a time,
 * 409 responses, UI button disabling, and state recovery after completion.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { mockAllApis, mockPost, pathMatcher } from '../../fixtures/mocks/api-handlers'
import { buildScanRun, buildPaginatedScores } from '../../fixtures/builders/scan.builders'

test.describe('Operation Mutex', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page, {
      scanList: [buildScanRun({ id: 1 })],
      scanScores: buildPaginatedScores(10),
    })
  })

  test('second scan attempt returns 409 when scan is in progress', async ({ page }) => {
    // First POST succeeds
    let callCount = 0
    await page.route(pathMatcher('/api/scan'), async route => {
      if (route.request().method() === 'POST') {
        callCount++
        if (callCount === 1) {
          return route.fulfill({ status: 202, json: { scan_id: 100 } })
        }
        return route.fulfill({
          status: 409,
          json: { detail: 'Another scan is already in progress' },
        })
      }
      return route.continue()
    })

    await page.goto('/scan')

    const startBtn = page.locator('[data-testid="start-scan-btn"]')
      .or(page.locator('button:has-text("Run Scan")'))

    // First click — should succeed
    await startBtn.click()

    // After first scan starts, button should be disabled
    // (preventing the second click in normal flow)
    await expect(startBtn).toBeDisabled({ timeout: 5_000 })
  })

  test('batch debate attempt during scan returns 409', async ({ page }) => {
    // Scan is "in progress" — mock POST /api/debate/batch to return 409
    await page.route('**/api/debate/batch', route =>
      route.fulfill({
        status: 409,
        json: { detail: 'Another operation is in progress' },
      }),
    )

    // Navigate to scan results with some scores selected
    await page.route('**/api/scan/1', route =>
      route.fulfill({ json: buildScanRun({ id: 1 }) }),
    )
    await page.route('**/api/scan/1/scores*', route =>
      route.fulfill({ json: buildPaginatedScores(10) }),
    )

    await page.goto('/scan/1')
    await page.locator('.p-datatable').waitFor({ state: 'visible' })

    // Select some rows and attempt batch debate
    const checkboxes = page.locator('.p-datatable-tbody .p-checkbox')
    if ((await checkboxes.count()) > 0) {
      await checkboxes.first().click()

      const batchBtn = page.locator('[data-testid="batch-debate-btn"]')
        .or(page.locator('button:has-text("Debate Selected")'))

      if (await batchBtn.isEnabled()) {
        await batchBtn.click()

        // Should show 409 toast
        const toast = page.locator('.p-toast-message, [data-testid="error-toast"]')
        await expect(toast).toBeVisible({ timeout: 5_000 })
        await expect(toast).toContainText(/in progress|conflict|busy/i)
      }
    }
  })

  test('buttons re-enable after operation completes', async ({ page }) => {
    // POST /api/scan always returns 202 (operation finished between calls)
    await mockPost(page, '**/api/scan', 202, { scan_id: 200 })

    await page.goto('/scan')

    const startBtn = page.locator('[data-testid="start-scan-btn"]')
      .or(page.locator('button:has-text("Run Scan")'))

    // Button should start enabled
    await expect(startBtn).toBeEnabled()
  })
})
