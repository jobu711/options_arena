import { type Page, type Locator, expect } from '@playwright/test'

export class DebateResultPage {
  readonly page: Page
  readonly bullCard: Locator
  readonly bearCard: Locator
  readonly riskCard: Locator
  readonly thesisCard: Locator
  readonly exportMdBtn: Locator
  readonly exportPdfBtn: Locator
  readonly fallbackBadge: Locator
  readonly directionBadge: Locator

  constructor(page: Page) {
    this.page = page
    this.bullCard = page.locator('[data-testid="agent-card-bull"]')
      .or(page.locator('[class*="agent-card"]:has-text("Bull")'))
    this.bearCard = page.locator('[data-testid="agent-card-bear"]')
      .or(page.locator('[class*="agent-card"]:has-text("Bear")'))
    this.riskCard = page.locator('[data-testid="agent-card-risk"]')
      .or(page.locator('[class*="agent-card"]:has-text("Risk")'))
    this.thesisCard = page.locator('[data-testid="thesis-card"]')
    this.exportMdBtn = page.locator('[data-testid="debate-export-md"]')
      .or(page.locator('button:has-text("Export MD")'))
    this.exportPdfBtn = page.locator('[data-testid="debate-export-pdf"]')
      .or(page.locator('button:has-text("PDF")'))
    this.fallbackBadge = page.locator('[data-testid="fallback-badge"]')
    this.directionBadge = page.locator('[data-testid="thesis-direction"]')
      .or(page.locator('[data-testid="direction-badge"]'))
  }

  async goto(debateId: number): Promise<void> {
    // Wait for the debate API response to complete before proceeding
    const responsePromise = this.page.waitForResponse(
      resp => resp.url().includes(`/api/debate/${debateId}`) && resp.status() === 200,
    )
    await this.page.goto(`/debate/${debateId}`)
    await responsePromise
    // Wait for thesis card (present in both normal and fallback results)
    await this.thesisCard.waitFor({ state: 'visible', timeout: 5_000 })
  }

  async expectBullCardVisible(): Promise<void> {
    await expect(this.bullCard).toBeVisible()
  }

  async expectBearCardVisible(): Promise<void> {
    await expect(this.bearCard).toBeVisible()
  }

  async expectThesisVisible(): Promise<void> {
    await expect(this.thesisCard).toBeVisible()
  }

  async expectAgentConfidence(agent: 'bull' | 'bear' | 'risk', minConfidence: number): Promise<void> {
    const card = agent === 'bull' ? this.bullCard : agent === 'bear' ? this.bearCard : this.riskCard
    const confidenceText = await card
      .locator('[data-testid^="agent-confidence"]')
      .or(card.locator('[class*="confidence"]'))
      .innerText()
    // Parse "72%" or "0.72"
    const value = confidenceText.includes('%')
      ? parseFloat(confidenceText) / 100
      : parseFloat(confidenceText)
    expect(value).toBeGreaterThanOrEqual(minConfidence)
  }

  async expectKeyPoints(agent: 'bull' | 'bear', minCount: number): Promise<void> {
    const card = agent === 'bull' ? this.bullCard : this.bearCard
    const points = card.locator('li, [class*="key-point"]')
    await expect(points).toHaveCount(expect.any(Number) as unknown as number)
    const count = await points.count()
    expect(count).toBeGreaterThanOrEqual(minCount)
  }

  async expectDirection(direction: 'bullish' | 'bearish' | 'neutral'): Promise<void> {
    await expect(this.directionBadge).toContainText(direction, { ignoreCase: true })
  }

  async expectFallbackVisible(): Promise<void> {
    await expect(this.fallbackBadge).toBeVisible()
  }

  async expectExportButtonsVisible(): Promise<void> {
    await expect(this.exportMdBtn).toBeVisible()
    await expect(this.exportPdfBtn).toBeVisible()
  }

  async clickExportMarkdown(): Promise<void> {
    const downloadPromise = this.page.waitForEvent('download')
    await this.exportMdBtn.click()
    return void (await downloadPromise)
  }
}
