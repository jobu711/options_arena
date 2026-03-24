import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeskAssessmentCard from '@/components/DeskAssessmentCard.vue'
import type { DeskAssessment, Direction } from '@/types/recommendation'

function makeAssessment(overrides: Partial<DeskAssessment> = {}): DeskAssessment {
  return {
    desk: 'trend',
    direction: 'BULLISH' as Direction,
    confidence: 0.72,
    summary: 'Strong upward momentum observed.',
    key_findings: ['RSI above 70', 'MACD crossover bullish', 'Above 200 SMA'],
    ...overrides,
  }
}

function mountCard(assessment: DeskAssessment = makeAssessment()) {
  return mount(DeskAssessmentCard, {
    props: { assessment },
    global: {
      stubs: {
        DeskCard: {
          template: `<div data-testid="desk-card-stub">
            <span data-testid="card-title">{{ title }}</span>
            <slot name="status" />
            <slot />
          </div>`,
          props: ['title'],
        },
        DirectionBadge: {
          template: '<span data-testid="direction-badge-stub">{{ direction }}</span>',
          props: ['direction'],
        },
        ConfidenceBadge: {
          template: '<span data-testid="confidence-badge-stub">{{ value }}</span>',
          props: ['value'],
        },
      },
    },
  })
}

describe('DeskAssessmentCard', () => {
  it('renders desk name in header as uppercase', () => {
    const wrapper = mountCard(makeAssessment({ desk: 'volatility' }))
    expect(wrapper.find('[data-testid="card-title"]').text()).toBe('VOLATILITY')
  })

  it('renders summary text', () => {
    const wrapper = mountCard(makeAssessment({ summary: 'Strong upward momentum observed.' }))
    expect(wrapper.find('.desk-assessment__summary').text()).toBe('Strong upward momentum observed.')
  })

  it('renders key findings as list', () => {
    const findings = ['Finding 1', 'Finding 2', 'Finding 3']
    const wrapper = mountCard(makeAssessment({ key_findings: findings }))
    const items = wrapper.findAll('.desk-assessment__finding')
    expect(items).toHaveLength(3)
    expect(items[0].text()).toBe('Finding 1')
    expect(items[1].text()).toBe('Finding 2')
    expect(items[2].text()).toBe('Finding 3')
  })

  it('handles empty key_findings', () => {
    const wrapper = mountCard(makeAssessment({ key_findings: [] }))
    expect(wrapper.find('.desk-assessment__findings').exists()).toBe(false)
  })

  it('applies desk-specific accent color for trend desk', () => {
    const wrapper = mountCard(makeAssessment({ desk: 'trend' }))
    const deskDiv = wrapper.find('.desk-assessment')
    expect(deskDiv.attributes('style')).toContain('#3b82f6')
  })

  it('applies desk-specific accent color for risk desk', () => {
    const wrapper = mountCard(makeAssessment({ desk: 'risk' }))
    const deskDiv = wrapper.find('.desk-assessment')
    expect(deskDiv.attributes('style')).toContain('#ef4444')
  })

  it('applies fallback accent color for unknown desk', () => {
    const wrapper = mountCard(makeAssessment({ desk: 'unknown_desk' }))
    const deskDiv = wrapper.find('.desk-assessment')
    expect(deskDiv.attributes('style')).toContain('#6b7280')
  })

  it('renders direction and confidence badges in status slot', () => {
    const wrapper = mountCard(makeAssessment({ direction: 'BEARISH', confidence: 0.85 }))
    expect(wrapper.find('[data-testid="direction-badge-stub"]').text()).toBe('BEARISH')
    expect(wrapper.find('[data-testid="confidence-badge-stub"]').text()).toBe('0.85')
  })
})
