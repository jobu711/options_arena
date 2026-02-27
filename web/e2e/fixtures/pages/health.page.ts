import { type Page, type Locator, expect } from '@playwright/test'

export class HealthPage {
  readonly page: Page
  readonly refreshBtn: Locator

  constructor(page: Page) {
    this.page = page
    this.refreshBtn = page.locator('[data-testid="health-refresh-btn"]')
      .or(page.locator('button:has-text("Re-check")'))
  }

  async goto(): Promise<void> {
    await this.page.goto('/health')
  }

  serviceCard(serviceName: string): Locator {
    return this.page.locator(`[data-testid="health-card-${serviceName.toLowerCase().replace(/\s/g, '-')}"]`)
      .or(this.page.locator(`[class*="health-card"]:has-text("${serviceName}")`))
  }

  serviceDot(serviceName: string): Locator {
    return this.page.locator(`[data-testid="health-dot-${serviceName.toLowerCase().replace(/\s/g, '-')}"]`)
      .or(this.serviceCard(serviceName).locator('[class*="health-dot"], [class*="dot"]'))
  }

  async expectServiceHealthy(serviceName: string): Promise<void> {
    const card = this.serviceCard(serviceName)
    await expect(card).toBeVisible()
  }

  async expectServiceDown(serviceName: string): Promise<void> {
    const card = this.serviceCard(serviceName)
    await expect(card).toBeVisible()
    // Should contain an error message or red indicator
    await expect(card).toContainText(/unreachable|down|error|refused/i)
  }

  async expectAllServicesVisible(): Promise<void> {
    for (const svc of ['Yahoo Finance', 'FRED', 'CBOE', 'Groq']) {
      await expect(this.serviceCard(svc)).toBeVisible()
    }
  }

  async refresh(): Promise<void> {
    await this.refreshBtn.click()
  }
}
