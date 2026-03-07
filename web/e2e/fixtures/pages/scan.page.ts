import { type Page, type Locator, expect } from '@playwright/test'
import { selfHealingLocator } from '../base.fixture'

export class ScanPage {
  readonly page: Page
  readonly title: Locator
  readonly startScanBtn: Locator
  readonly cancelScanBtn: Locator
  readonly presetSelector: Locator
  readonly scanListTable: Locator
  readonly emptyState: Locator
  readonly progressTracker: Locator

  constructor(page: Page) {
    this.page = page
    this.title = page.locator('[data-testid="scan-title"]').or(page.locator('h1'))
    this.startScanBtn = selfHealingLocator(page, 'start-scan-btn', 'Run Scan', 'Run Scan')
    this.cancelScanBtn = selfHealingLocator(page, 'cancel-scan-btn', 'Cancel Scan', 'Cancel')
    this.presetSelector = page.locator('[data-testid="preset-selector"]')
    this.scanListTable = page.locator('[data-testid="scan-list-table"]')
      .or(page.locator('.p-datatable'))
    this.emptyState = page.locator('[data-testid="scan-list-empty"]')
      .or(page.locator('[data-testid="empty-state"]'))
    this.progressTracker = page.locator('[data-testid="progress-tracker"]')
  }

  async goto(): Promise<void> {
    await this.page.goto('/scan')
    await this.title.waitFor({ state: 'visible' })
  }

  async selectPreset(preset: 'full' | 'sp500' | 'etfs'): Promise<void> {
    await this.page.locator(`[data-testid="preset-card-${preset}"]`).click()
  }

  async startScan(): Promise<void> {
    await this.startScanBtn.click()
  }

  async cancelScan(): Promise<void> {
    await this.cancelScanBtn.click()
  }

  async expectProgressVisible(): Promise<void> {
    await expect(this.progressTracker).toBeVisible({ timeout: 5_000 })
  }

  async expectProgressHidden(): Promise<void> {
    await expect(this.progressTracker).toBeHidden({ timeout: 10_000 })
  }

  async expectStartButtonDisabled(): Promise<void> {
    await expect(this.startScanBtn).toBeDisabled()
  }

  async expectStartButtonEnabled(): Promise<void> {
    await expect(this.startScanBtn).toBeEnabled()
  }

  async getScanListRowCount(): Promise<number> {
    return this.page.locator('.p-datatable-tbody tr').count()
  }
}
