import { type Page, type Locator } from '@playwright/test'
import { selfHealingLocator } from '../base.fixture'

export class DashboardPage {
  readonly page: Page
  readonly latestScan: Locator
  readonly healthStrip: Locator
  readonly recentDebates: Locator
  readonly newScanBtn: Locator

  constructor(page: Page) {
    this.page = page
    this.latestScan = page.locator('[data-testid="dashboard-latest-scan"]')
      .or(page.locator('[class*="latest-scan"]'))
    this.healthStrip = page.locator('[data-testid="dashboard-health-strip"]')
      .or(page.locator('[class*="health-strip"]'))
    this.recentDebates = page.locator('[data-testid="dashboard-recent-debates"]')
      .or(page.locator('[class*="recent-debates"]'))
    this.newScanBtn = selfHealingLocator(page, 'dashboard-btn-new-scan', 'New Scan', 'New Scan')
  }

  async goto(): Promise<void> {
    await this.page.goto('/')
  }

  async expectLoaded(): Promise<void> {
    // Dashboard should have at least the health strip or action buttons
    await this.page.locator('[data-testid^="dashboard"]')
      .or(this.newScanBtn)
      .first()
      .waitFor({ state: 'visible' })
  }

  async clickNewScan(): Promise<void> {
    await this.newScanBtn.click()
    await this.page.waitForURL('**/scan')
  }

}
