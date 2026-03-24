import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentConsensus from '@/components/AgentConsensus.vue'
import type { DeskAssessment, Direction } from '@/types/recommendation'

function makeAssessment(desk: string, direction: Direction = 'BULLISH', confidence = 0.72): DeskAssessment {
  return {
    desk,
    direction,
    confidence,
    summary: `Summary for ${desk}`,
    key_findings: [`Finding from ${desk}`],
  }
}

const ALL_SIX_DESKS: DeskAssessment[] = [
  makeAssessment('trend', 'BULLISH', 0.8),
  makeAssessment('volatility', 'BEARISH', 0.65),
  makeAssessment('flow', 'BULLISH', 0.7),
  makeAssessment('fundamental', 'NEUTRAL', 0.55),
  makeAssessment('risk', 'BEARISH', 0.6),
  makeAssessment('contrarian', 'BULLISH', 0.75),
]

function mountConsensus(props: {
  ticker: string
  assessments: DeskAssessment[]
  overallDirection: Direction
  overallConfidence: number
}) {
  return mount(AgentConsensus, {
    props,
    global: {
      stubs: {
        DeskCard: {
          template: `<div data-testid="desk-card-stub">
            <slot name="status" />
            <slot />
          </div>`,
          props: ['title', 'fullWidth'],
        },
      },
    },
  })
}

describe('AgentConsensus', () => {
  it('renders overall direction and confidence in header', () => {
    const wrapper = mountConsensus({
      ticker: 'AAPL',
      assessments: ALL_SIX_DESKS,
      overallDirection: 'BULLISH',
      overallConfidence: 0.72,
    })
    const headerText = wrapper.find('.consensus-header-text')
    expect(headerText.text()).toContain('AAPL')
    expect(headerText.text()).toContain('BULLISH')
    expect(headerText.text()).toContain('72%')
  })

  it('renders all 6 desk summaries', () => {
    const wrapper = mountConsensus({
      ticker: 'AAPL',
      assessments: ALL_SIX_DESKS,
      overallDirection: 'BULLISH',
      overallConfidence: 0.72,
    })
    const cells = wrapper.findAll('[data-testid="consensus-cell"]')
    expect(cells).toHaveLength(6)

    // Check desk names
    const names = cells.map((c) => c.find('.consensus-cell__name').text())
    expect(names).toContain('trend')
    expect(names).toContain('volatility')
    expect(names).toContain('flow')
    expect(names).toContain('fundamental')
    expect(names).toContain('risk')
    expect(names).toContain('contrarian')
  })

  it('handles partial desks (3 of 6)', () => {
    const partialDesks: DeskAssessment[] = [
      makeAssessment('trend', 'BULLISH', 0.8),
      makeAssessment('volatility', 'BEARISH', 0.65),
      makeAssessment('risk', 'BEARISH', 0.6),
    ]

    const wrapper = mountConsensus({
      ticker: 'MSFT',
      assessments: partialDesks,
      overallDirection: 'BEARISH',
      overallConfidence: 0.68,
    })

    // Still renders 6 cells (one per expected desk)
    const cells = wrapper.findAll('[data-testid="consensus-cell"]')
    expect(cells).toHaveLength(6)

    // Missing desks show placeholder
    const placeholders = wrapper.findAll('.consensus-cell__placeholder')
    // 3 desks missing => 3 * 2 placeholders (arrow + confidence per missing desk)
    expect(placeholders.length).toBe(6)
  })

  it('renders ticker in header text', () => {
    const wrapper = mountConsensus({
      ticker: 'TSLA',
      assessments: [makeAssessment('trend')],
      overallDirection: 'NEUTRAL',
      overallConfidence: 0.5,
    })
    expect(wrapper.find('.consensus-header-text').text()).toContain('TSLA')
  })

  it('renders confidence percentages for present desks', () => {
    const wrapper = mountConsensus({
      ticker: 'AAPL',
      assessments: [makeAssessment('trend', 'BULLISH', 0.85)],
      overallDirection: 'BULLISH',
      overallConfidence: 0.85,
    })

    const confidenceEls = wrapper.findAll('.consensus-cell__confidence')
    // Only 1 desk has data, so only 1 confidence element
    expect(confidenceEls).toHaveLength(1)
    expect(confidenceEls[0].text()).toBe('85%')
  })

  it('applies bullish direction class to header for bullish direction', () => {
    const wrapper = mountConsensus({
      ticker: 'AAPL',
      assessments: ALL_SIX_DESKS,
      overallDirection: 'BULLISH',
      overallConfidence: 0.72,
    })
    const header = wrapper.find('.consensus-header-text')
    expect(header.classes()).toContain('arrow--bullish')
  })

  it('applies bearish direction class to header for bearish direction', () => {
    const wrapper = mountConsensus({
      ticker: 'AAPL',
      assessments: ALL_SIX_DESKS,
      overallDirection: 'BEARISH',
      overallConfidence: 0.72,
    })
    const header = wrapper.find('.consensus-header-text')
    expect(header.classes()).toContain('arrow--bearish')
  })
})
