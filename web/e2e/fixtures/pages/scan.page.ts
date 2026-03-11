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
  readonly advancedPanel: Locator
  readonly confidenceFilter: Locator
  readonly customTickersFilter: Locator
  readonly topNFilter: Locator
  readonly minDollarVolFilter: Locator
  readonly minOiFilter: Locator
  readonly minVolFilter: Locator
  readonly maxSpreadFilter: Locator
  readonly deltaPrimaryMinFilter: Locator
  readonly deltaPrimaryMaxFilter: Locator
  readonly deltaFallbackMinFilter: Locator
  readonly deltaFallbackMaxFilter: Locator

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
    this.advancedPanel = page.locator('[data-testid="advanced-options-panel"]')
    this.confidenceFilter = page.locator('[data-testid="confidence-filter"]')
    this.customTickersFilter = page.locator('[data-testid="custom-tickers-filter"]')
    this.topNFilter = page.locator('[data-testid="top-n-filter"]')
    this.minDollarVolFilter = page.locator('[data-testid="min-dollar-vol-filter"]')
    this.minOiFilter = page.locator('[data-testid="min-oi-filter"]')
    this.minVolFilter = page.locator('[data-testid="min-vol-filter"]')
    this.maxSpreadFilter = page.locator('[data-testid="max-spread-filter"]')
    this.deltaPrimaryMinFilter = page.locator('[data-testid="delta-primary-min-filter"]')
    this.deltaPrimaryMaxFilter = page.locator('[data-testid="delta-primary-max-filter"]')
    this.deltaFallbackMinFilter = page.locator('[data-testid="delta-fallback-min-filter"]')
    this.deltaFallbackMaxFilter = page.locator('[data-testid="delta-fallback-max-filter"]')
  }

  async goto(): Promise<void> {
    await this.page.goto('/scan')
    await this.title.waitFor({ state: 'visible' })
  }

  async selectPreset(preset: 'full' | 'sp500' | 'etfs' | 'nasdaq100' | 'russell2000' | 'most_active'): Promise<void> {
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

  async expandAdvancedPanel(): Promise<void> {
    const header = this.advancedPanel.locator('.p-panel-header')
    await header.click()
    // Wait for the panel content to become visible
    await this.advancedPanel.locator('.p-panel-content').waitFor({ state: 'visible' })
  }
}
