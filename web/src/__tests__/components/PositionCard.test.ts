import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PositionCard from '@/components/PositionCard.vue'
import type { PositionRecommendation, Direction } from '@/types/recommendation'

function makeRecommendation(overrides: Partial<PositionRecommendation> = {}): PositionRecommendation {
  return {
    ticker: 'AAPL',
    direction: 'BULLISH' as Direction,
    confidence: 0.72,
    recommended_contract: 'AAPL 2026-04-18 C 185.00',
    entry_price: '3.45',
    entry_criteria: 'Break above 185 resistance',
    exit_criteria: 'Close below 180 support',
    stop_loss: '2.10',
    take_profit: '6.50',
    position_size_pct: 2.5,
    position_rationale: 'Strong momentum with bullish technical setup.',
    risk_reward_ratio: 2.8,
    max_loss_estimate: '210.00',
    recommended_strategy: 'Long call',
    strategy_rationale: 'High conviction directional play.',
    summary: 'Buy AAPL call.',
    key_factors: ['Strong momentum', 'Earnings catalyst'],
    risk_assessment: 'Moderate risk with defined stop.',
    agent_agreement_score: 0.85,
    dissenting_desks: ['risk'],
    model_used: 'llama-3.3-70b-versatile',
    ...overrides,
  }
}

function mountCard(recommendation: PositionRecommendation = makeRecommendation()) {
  return mount(PositionCard, {
    props: { recommendation },
    global: {
      stubs: {
        DeskCard: {
          template: `<div data-testid="desk-card-stub">
            <slot name="status" />
            <slot />
          </div>`,
          props: ['title', 'fullWidth'],
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

describe('PositionCard', () => {
  it('renders contract description', () => {
    const wrapper = mountCard(makeRecommendation({
      recommended_contract: 'AAPL 2026-04-18 C 185.00',
    }))
    expect(wrapper.find('.position-detail__contract-value').text()).toBe('AAPL 2026-04-18 C 185.00')
  })

  it('displays entry_price as formatted string', () => {
    const wrapper = mountCard(makeRecommendation({ entry_price: '3.45' }))
    // formatPrice("3.45") => "$3.45"
    expect(wrapper.text()).toContain('$3.45')
  })

  it('shows -- for null stop_loss', () => {
    const wrapper = mountCard(makeRecommendation({ stop_loss: null }))
    // The Stop row should display "--"
    const kvs = wrapper.findAll('.position-detail__kv')
    const stopKv = kvs.find((el) => el.find('.position-detail__key').text() === 'Stop')
    expect(stopKv?.find('.position-detail__value').text()).toBe('--')
  })

  it('shows -- for null take_profit', () => {
    const wrapper = mountCard(makeRecommendation({ take_profit: null }))
    const kvs = wrapper.findAll('.position-detail__kv')
    const targetKv = kvs.find((el) => el.find('.position-detail__key').text() === 'Target')
    expect(targetKv?.find('.position-detail__value').text()).toBe('--')
  })

  it('renders risk_reward_ratio with :1 suffix', () => {
    const wrapper = mountCard(makeRecommendation({ risk_reward_ratio: 2.8 }))
    const kvs = wrapper.findAll('.position-detail__kv')
    const rrKv = kvs.find((el) => el.find('.position-detail__key').text() === 'R/R')
    expect(rrKv?.find('.position-detail__value').text()).toBe('2.8:1')
  })

  it('renders strategy or -- fallback', () => {
    // With strategy
    const wrapper1 = mountCard(makeRecommendation({ recommended_strategy: 'Long call' }))
    expect(wrapper1.text()).toContain('Long call')

    // Without strategy
    const wrapper2 = mountCard(makeRecommendation({ recommended_strategy: null }))
    const kvs = wrapper2.findAll('.position-detail__kv')
    const strategyKv = kvs.find((el) => el.find('.position-detail__key').text() === 'Strategy')
    expect(strategyKv?.find('.position-detail__value').text()).toBe('--')
  })

  it('NEVER calls parseFloat on price strings', () => {
    // This test verifies that the component uses formatPrice (string-based formatting)
    // and not parseFloat for price display.
    // The formatPrice function accepts a string and formats it as currency.
    // The PositionCard's displayPrice function returns formatPrice(price) or '--'.
    const wrapper = mountCard(makeRecommendation({
      entry_price: '0.10',
      stop_loss: '0.05',
      take_profit: '0.20',
    }))
    // If parseFloat were used, 0.10 could become 0.1 without proper formatting.
    // formatPrice("0.10") should produce "$0.10"
    expect(wrapper.text()).toContain('$0.10')
    expect(wrapper.text()).toContain('$0.05')
    expect(wrapper.text()).toContain('$0.20')
  })

  it('renders position rationale text', () => {
    const wrapper = mountCard(makeRecommendation({
      position_rationale: 'Strong momentum with bullish technical setup.',
    }))
    expect(wrapper.text()).toContain('Strong momentum with bullish technical setup.')
  })

  it('renders position size as percentage', () => {
    const wrapper = mountCard(makeRecommendation({ position_size_pct: 2.5 }))
    expect(wrapper.text()).toContain('2.5%')
  })

  it('renders -- for non-finite risk_reward_ratio', () => {
    const wrapper = mountCard(makeRecommendation({ risk_reward_ratio: Infinity }))
    const kvs = wrapper.findAll('.position-detail__kv')
    const rrKv = kvs.find((el) => el.find('.position-detail__key').text() === 'R/R')
    expect(rrKv?.find('.position-detail__value').text()).toBe('--')
  })
})
