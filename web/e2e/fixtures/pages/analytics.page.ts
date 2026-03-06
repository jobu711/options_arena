import { type Page, type Locator, expect } from '@playwright/test'

export class AnalyticsPage {
  readonly page: Page
  readonly pageRoot: Locator
  readonly collectBtn: Locator
  readonly lookbackSelect: Locator
  readonly summarySection: Locator
  readonly winRatePanel: Locator
  readonly calibrationPanel: Locator
  readonly holdingPanel: Locator
  readonly deltaPanel: Locator

  constructor(page: Page) {
    this.page = page
    this.pageRoot = page.locator('[data-testid="analytics-page"]')
    this.collectBtn = page.locator('[data-testid="btn-collect-outcomes"]')
    this.lookbackSelect = page.locator('[data-testid="lookback-select"]')
    this.summarySection = page.locator('[data-testid="analytics-summary"]')
    this.winRatePanel = page.locator('[data-testid="analytics-win-rate"]')
    this.calibrationPanel = page.locator('[data-testid="analytics-calibration"]')
    this.holdingPanel = page.locator('[data-testid="analytics-holding"]')
    this.deltaPanel = page.locator('[data-testid="analytics-delta"]')
  }

  async goto(): Promise<void> {
    await this.page.goto('/analytics')
  }

  async expectLoaded(): Promise<void> {
    await expect(this.pageRoot).toBeVisible()
  }

  async expectEmptyNoContracts(): Promise<void> {
    await expect(this.page.locator('[data-testid="empty-no-contracts"]')).toBeVisible()
  }

  async expectEmptyNoOutcomes(): Promise<void> {
    await expect(this.page.locator('[data-testid="empty-no-outcomes"]')).toBeVisible()
  }

  async expectAllPanelsVisible(): Promise<void> {
    await expect(this.summarySection).toBeVisible()
    await expect(this.winRatePanel).toBeVisible()
    await expect(this.calibrationPanel).toBeVisible()
    await expect(this.holdingPanel).toBeVisible()
    await expect(this.deltaPanel).toBeVisible()
  }

  async clickCollectOutcomes(): Promise<void> {
    await this.collectBtn.click()
  }
}
