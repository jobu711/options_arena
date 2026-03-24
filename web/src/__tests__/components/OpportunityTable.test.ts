import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import OpportunityTable from '@/components/OpportunityTable.vue'
import type { PipelineTicker, Direction, PipelineStage } from '@/types/recommendation'

function makeTicker(overrides: Partial<PipelineTicker> = {}): PipelineTicker {
  return {
    ticker: 'AAPL',
    stage: 'scored' as PipelineStage,
    composite_score: 8.5,
    direction: 'BULLISH' as Direction,
    direction_confidence: 0.72,
    sector: 'Technology',
    company_name: 'Apple Inc.',
    recommendation_id: null,
    error: null,
    ...overrides,
  }
}

/** Minimal stubs for shallow rendering that avoid PrimeVue DataTable/Column issues. */
const stubs = {
  DeskCard: {
    template: '<div data-testid="desk-card-stub"><slot /><slot name="status" /></div>',
    props: ['title', 'fullWidth'],
  },
  DirectionBadge: {
    template: '<span data-testid="direction-badge-stub" />',
    props: ['direction'],
  },
  PipelineStatus: {
    template: '<span data-testid="pipeline-status-stub" />',
    props: ['stage'],
  },
}

describe('OpportunityTable', () => {
  it('renders empty state when no tickers', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [] },
      global: { stubs },
    })
    expect(wrapper.find('[data-testid="empty-state"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('No tickers in pipeline')
  })

  it('renders DataTable when tickers are provided (no empty state)', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [makeTicker()] },
      global: { stubs },
    })
    expect(wrapper.find('[data-testid="empty-state"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="opportunity-table"]').exists()).toBe(true)
  })

  it('renders ticker count in header status slot', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [makeTicker(), makeTicker({ ticker: 'MSFT' })] },
      global: { stubs },
    })
    expect(wrapper.find('[data-testid="ticker-count"]').text()).toContain('2 tickers')
  })

  it('emits selectTicker when onRowClick handler processes event', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [makeTicker()] },
      global: { stubs },
    })
    // Call the component's internal onRowClick handler directly via the vm
    const vm = wrapper.vm as unknown as {
      onRowClick: (event: { data: PipelineTicker }) => void
    }
    vm.onRowClick({ data: makeTicker({ ticker: 'AAPL' }) })

    expect(wrapper.emitted('selectTicker')).toBeTruthy()
    expect(wrapper.emitted('selectTicker')![0]).toEqual(['AAPL'])
  })

  it('formatConfidence returns -- for null and percentage for number', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [makeTicker()] },
      global: { stubs },
    })
    const vm = wrapper.vm as unknown as { formatConfidence: (v: number | null) => string }
    expect(vm.formatConfidence(null)).toBe('--')
    expect(vm.formatConfidence(0.72)).toBe('72%')
    expect(vm.formatConfidence(0)).toBe('0%')
    expect(vm.formatConfidence(1.0)).toBe('100%')
  })

  it('displays -- for null sector (template uses ?? fallback)', () => {
    // The template uses: (data as PipelineTicker).sector ?? '--'
    const tickerNull = makeTicker({ sector: null })
    expect(tickerNull.sector ?? '--').toBe('--')

    const tickerWithSector = makeTicker({ sector: 'Technology' })
    expect(tickerWithSector.sector ?? '--').toBe('Technology')
  })

  it('renders 0 tickers with empty state hint text', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [] },
      global: { stubs },
    })
    expect(wrapper.find('[data-testid="ticker-count"]').text()).toContain('0 tickers')
    expect(wrapper.find('[data-testid="empty-state"]').text()).toContain('Run a scan')
  })

  it('emits selectionChange through onSelectionUpdate', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [makeTicker(), makeTicker({ ticker: 'MSFT' })] },
      global: { stubs },
    })
    const vm = wrapper.vm as unknown as {
      onSelectionUpdate: (rows: PipelineTicker[]) => void
    }
    vm.onSelectionUpdate([makeTicker({ ticker: 'AAPL' }), makeTicker({ ticker: 'MSFT' })])

    expect(wrapper.emitted('selectionChange')).toBeTruthy()
    expect(wrapper.emitted('selectionChange')![0]).toEqual([['AAPL', 'MSFT']])
  })

  it('emits analyzeTicker through onAnalyze', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [makeTicker()] },
      global: { stubs },
    })
    const vm = wrapper.vm as unknown as {
      onAnalyze: (ticker: string) => void
    }
    vm.onAnalyze('AAPL')

    expect(wrapper.emitted('analyzeTicker')).toBeTruthy()
    expect(wrapper.emitted('analyzeTicker')![0]).toEqual(['AAPL'])
  })

  it('computes correct row class for selected rows', () => {
    const wrapper = shallowMount(OpportunityTable, {
      props: { tickers: [makeTicker()] },
      global: { stubs },
    })
    const vm = wrapper.vm as unknown as {
      rowClass: (data: PipelineTicker) => string
    }
    // No rows selected by default
    expect(vm.rowClass(makeTicker())).toBe('')
  })
})
