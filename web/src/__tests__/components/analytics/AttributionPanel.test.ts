import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AttributionPanel from '@/components/analytics/AttributionPanel.vue'
import type { AttributionReport, PredictionAccuracy, ContractGuidance } from '@/types/recommendation'

// Mock useApi
vi.mock('@/composables/useApi', () => ({
  api: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
}))

// Mock PrimeVue useToast
vi.mock('primevue/usetoast', () => ({
  useToast: () => ({ add: vi.fn(), removeGroup: vi.fn(), removeAllGroups: vi.fn() }),
}))

function makeReport(overrides: Partial<AttributionReport> = {}): AttributionReport {
  return {
    window_days: 90,
    total_recommendations: 50,
    total_outcomes: 30,
    source_accuracy: [
      { source: 'trend', total: 20, correct: 14, accuracy: 0.7, sample_sufficient: true },
      { source: 'volatility', total: 15, correct: 6, accuracy: 0.4, sample_sufficient: true },
    ],
    condition_accuracy: [],
    contract_guidance: null,
    ...overrides,
  }
}

function makeGuidance(overrides: Partial<ContractGuidance> = {}): ContractGuidance {
  return {
    optimal_delta_low: 0.3,
    optimal_delta_high: 0.5,
    optimal_dte_low: 30,
    optimal_dte_high: 60,
    delta_win_rate: 0.65,
    dte_win_rate: 0.72,
    sample_count: 25,
    ...overrides,
  }
}

describe('AttributionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders source accuracy table when data is available', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockResolvedValueOnce(makeReport())

    const wrapper = mount(AttributionPanel)
    await flushPromises()

    expect(wrapper.find('[data-testid="source-accuracy-table"]').exists()).toBe(true)
    // Summary line
    expect(wrapper.text()).toContain('30 outcomes')
    expect(wrapper.text()).toContain('50 recommendations')
  })

  it('shows empty state when no data', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockResolvedValueOnce(makeReport({ total_outcomes: 0 }))

    const wrapper = mount(AttributionPanel)
    await flushPromises()

    expect(wrapper.find('[data-testid="attribution-empty"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('No attribution data available')
  })

  it('shows empty state when API returns null (error)', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockRejectedValueOnce(new Error('Network error'))

    const wrapper = mount(AttributionPanel)
    await flushPromises()

    expect(wrapper.find('[data-testid="attribution-empty"]').exists()).toBe(true)
  })

  it('renders contract guidance when present', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockResolvedValueOnce(makeReport({
      contract_guidance: makeGuidance(),
    }))

    const wrapper = mount(AttributionPanel)
    await flushPromises()

    // Check for guidance section
    expect(wrapper.text()).toContain('Contract Guidance')
    expect(wrapper.text()).toContain('0.30')
    expect(wrapper.text()).toContain('0.50')
    expect(wrapper.text()).toContain('30d')
    expect(wrapper.text()).toContain('60d')
    expect(wrapper.text()).toContain('25')
  })

  it('shows empty state for null contract_guidance', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockResolvedValueOnce(makeReport({ contract_guidance: null }))

    const wrapper = mount(AttributionPanel)
    await flushPromises()

    // Contract guidance section should not be rendered
    expect(wrapper.text()).not.toContain('Contract Guidance')
    // But source accuracy should still render
    expect(wrapper.find('[data-testid="source-accuracy-table"]').exists()).toBe(true)
  })

  it('renders condition buckets grouped by source', async () => {
    const { api } = await import('@/composables/useApi')
    const mockApi = vi.mocked(api)
    mockApi.mockResolvedValueOnce(makeReport({
      condition_accuracy: [
        { source: 'trend', condition: 'adx_strong', total: 10, correct: 7, accuracy: 0.7 },
        { source: 'trend', condition: 'rsi_oversold', total: 8, correct: 5, accuracy: 0.625 },
        { source: 'volatility', condition: 'iv_rank_low', total: 12, correct: 4, accuracy: 0.333 },
      ],
    }))

    const wrapper = mount(AttributionPanel)
    await flushPromises()

    expect(wrapper.text()).toContain('Condition Buckets')
    expect(wrapper.text()).toContain('trend')
    expect(wrapper.text()).toContain('volatility')
  })
})
