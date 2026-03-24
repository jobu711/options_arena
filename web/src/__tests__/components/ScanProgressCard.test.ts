import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ScanProgressCard from '@/components/ScanProgressCard.vue'

const DeskCardStub = {
  template: '<div data-testid="desk-card-stub"><slot /></div>',
  props: ['title'],
}

describe('ScanProgressCard', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders phase name', () => {
    const wrapper = mount(ScanProgressCard, {
      props: {
        phase: 'scoring',
        current: 10,
        total: 50,
        startedAt: new Date(),
      },
      global: { stubs: { DeskCard: DeskCardStub } },
    })
    expect(wrapper.find('.scan-progress__phase').text()).toBe('scoring')
  })

  it('renders ticker count as current/total', () => {
    const wrapper = mount(ScanProgressCard, {
      props: {
        phase: 'universe',
        current: 25,
        total: 100,
        startedAt: new Date(),
      },
      global: { stubs: { DeskCard: DeskCardStub } },
    })
    expect(wrapper.find('.scan-progress__count').text()).toBe('25 / 100 tickers')
  })

  it('renders progress bar (ProgressBar component present)', () => {
    const wrapper = mount(ScanProgressCard, {
      props: {
        phase: 'scoring',
        current: 25,
        total: 100,
        startedAt: new Date(),
      },
      global: { stubs: { DeskCard: DeskCardStub } },
    })
    // ProgressBar is globally stubbed
    expect(wrapper.find('[data-testid="progressbar-stub"]').exists()).toBe(true)
  })

  it('handles total=0 without division by zero', () => {
    const wrapper = mount(ScanProgressCard, {
      props: {
        phase: 'universe',
        current: 0,
        total: 0,
        startedAt: new Date(),
      },
      global: { stubs: { DeskCard: DeskCardStub } },
    })
    // Should render without error
    expect(wrapper.find('.scan-progress__count').text()).toBe('0 / 0 tickers')
  })

  it('displays elapsed time starting at 0s', () => {
    const now = new Date('2026-03-24T10:00:00Z')
    vi.setSystemTime(now)

    const wrapper = mount(ScanProgressCard, {
      props: {
        phase: 'scoring',
        current: 10,
        total: 50,
        startedAt: now,
      },
      global: { stubs: { DeskCard: DeskCardStub } },
    })

    expect(wrapper.find('.scan-progress__elapsed').text()).toBe('0s')
  })

  it('updates elapsed time after interval ticks', async () => {
    const now = new Date('2026-03-24T10:00:00Z')
    vi.setSystemTime(now)

    const wrapper = mount(ScanProgressCard, {
      props: {
        phase: 'scoring',
        current: 10,
        total: 50,
        startedAt: now,
      },
      global: { stubs: { DeskCard: DeskCardStub } },
    })

    // Advance time by 30 seconds
    vi.advanceTimersByTime(30_000)
    await wrapper.vm.$nextTick()

    const elapsed = wrapper.find('.scan-progress__elapsed').text()
    expect(elapsed).toBe('30s')
  })

  it('formats minutes correctly after 60+ seconds', async () => {
    const now = new Date('2026-03-24T10:00:00Z')
    vi.setSystemTime(now)

    const wrapper = mount(ScanProgressCard, {
      props: {
        phase: 'scoring',
        current: 10,
        total: 50,
        startedAt: now,
      },
      global: { stubs: { DeskCard: DeskCardStub } },
    })

    // Advance time by 90 seconds (1m 30s)
    vi.advanceTimersByTime(90_000)
    await wrapper.vm.$nextTick()

    const elapsed = wrapper.find('.scan-progress__elapsed').text()
    expect(elapsed).toBe('1m 30s')
  })
})
