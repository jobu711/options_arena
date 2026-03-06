/**
 * E2E tests: Consensus panel and back-to-scan navigation on DebateResultPage.
 *
 * Covers: consensus panel visibility for v2 debates, hidden for v1,
 * back-to-scan button visibility, and navigation.
 */

import { test, expect } from '../../fixtures/base.fixture'
import { DebateResultPage } from '../../fixtures/pages/debate-result.page'
import { mockAllApis, mockGet } from '../../fixtures/mocks/api-handlers'
import { buildDebateResult } from '../../fixtures/builders/debate.builders'

const DEBATE_ID = 789
const SCAN_RUN_ID = 42

test.describe('Consensus Panel & Back-to-Scan', () => {
  test('consensus panel visible for v2 debate with agreement score', async ({ page }) => {
    await mockAllApis(page)

    const v2Debate = buildDebateResult({
      id: DEBATE_ID,
      debate_protocol: 'v2',
      agent_agreement_score: 0.75,
      agents_completed: 6,
      dissenting_agents: ['Bear', 'Contrarian'],
      contrarian_dissent: 'The bullish consensus overlooks rising treasury yields.',
    })
    await mockGet(page, `**/api/debate/${DEBATE_ID}`, v2Debate)

    const resultPage = new DebateResultPage(page)
    await resultPage.goto(DEBATE_ID)

    const panel = page.locator('[data-testid="consensus-panel"]')
    await expect(panel).toBeVisible()
    await expect(panel).toContainText('75%')
    await expect(panel).toContainText('6/8 agents')
    await expect(panel).toContainText('Bear')
    await expect(panel).toContainText('Contrarian')
    await expect(panel).toContainText('rising treasury yields')
  })

  test('consensus panel hidden for v1 debate (no agreement score)', async ({ page }) => {
    await mockAllApis(page)

    const v1Debate = buildDebateResult({
      id: DEBATE_ID,
      debate_protocol: null,
      agent_agreement_score: undefined,
    })
    await mockGet(page, `**/api/debate/${DEBATE_ID}`, v1Debate)

    const resultPage = new DebateResultPage(page)
    await resultPage.goto(DEBATE_ID)

    const panel = page.locator('[data-testid="consensus-panel"]')
    await expect(panel).toHaveCount(0)
  })

  test('back-to-scan button visible when scan_run_id present', async ({ page }) => {
    await mockAllApis(page)

    const debateFromScan = buildDebateResult({
      id: DEBATE_ID,
      scan_run_id: SCAN_RUN_ID,
    })
    await mockGet(page, `**/api/debate/${DEBATE_ID}`, debateFromScan)

    const resultPage = new DebateResultPage(page)
    await resultPage.goto(DEBATE_ID)

    const backBtn = page.locator('[data-testid="back-to-scan"]')
    await expect(backBtn).toBeVisible()
    await expect(backBtn).toContainText('Back to Scan Results')
  })

  test('back-to-scan button hidden for standalone debates', async ({ page }) => {
    await mockAllApis(page)

    const standaloneDebate = buildDebateResult({
      id: DEBATE_ID,
      scan_run_id: undefined,
    })
    await mockGet(page, `**/api/debate/${DEBATE_ID}`, standaloneDebate)

    const resultPage = new DebateResultPage(page)
    await resultPage.goto(DEBATE_ID)

    const backBtn = page.locator('[data-testid="back-to-scan"]')
    await expect(backBtn).toHaveCount(0)
  })
})
