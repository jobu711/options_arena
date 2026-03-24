import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScanControlBar from '@/components/ScanControlBar.vue'
import { usePipelineStore } from '@/stores/pipeline'

// Mock both stores and useApi
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

// Need to mock the scan store as well since it's used in the component
vi.mock('@/stores/scan', () => ({
  useScanStore: () => ({
    startScan: vi.fn().mockResolvedValue(undefined),
    cancelScan: vi.fn().mockResolvedValue(undefined),
  }),
}))

/** Custom Button stub that preserves data-testid and label, and emits click properly. */
const ButtonStub = {
  name: 'Button',
  inheritAttrs: true,
  props: ['label', 'icon', 'size', 'severity', 'outlined', 'text', 'disabled'],
  template: '<button v-bind="$attrs" @click="$emit(\'click\', $event)">{{ label }}</button>',
  emits: ['click'],
}

function mountControl() {
  return mount(ScanControlBar, {
    global: {
      stubs: {
        DeskCard: {
          template: '<div data-testid="desk-card-stub"><slot /></div>',
          props: ['title', 'fullWidth', 'collapsed'],
          emits: ['update:collapsed'],
        },
        PreScanFilters: {
          template: '<div data-testid="prescan-filters-stub" />',
          props: ['disabled'],
          emits: ['update:filters'],
        },
        Button: ButtonStub,
      },
    },
  })
}

describe('ScanControlBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders Run Scan button in idle phase', () => {
    const store = usePipelineStore()
    store.phase = 'idle'

    const wrapper = mountControl()
    expect(wrapper.find('[data-testid="run-scan-btn"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cancel-scan-btn"]').exists()).toBe(false)
  })

  it('hides Run Scan and shows Cancel during active scan', () => {
    const store = usePipelineStore()
    store.phase = 'scanning'

    const wrapper = mountControl()
    expect(wrapper.find('[data-testid="run-scan-btn"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="cancel-scan-btn"]').exists()).toBe(true)
  })

  it('shows Cancel button during active scan with Cancel text', () => {
    const store = usePipelineStore()
    store.phase = 'scanning'

    const wrapper = mountControl()
    const cancelBtn = wrapper.find('[data-testid="cancel-scan-btn"]')
    expect(cancelBtn.exists()).toBe(true)
    expect(cancelBtn.text()).toContain('Cancel')
  })

  it('toggles filter panel visibility', async () => {
    const wrapper = mountControl()

    // Filter panel should start hidden (v-show)
    const filterPanel = wrapper.find('[data-testid="filter-panel"]')
    expect((filterPanel.element as HTMLElement).style.display).toBe('none')

    // Click filters toggle
    const toggleBtn = wrapper.find('[data-testid="filters-toggle"]')
    expect(toggleBtn.exists()).toBe(true)
    await toggleBtn.trigger('click')

    // Filter panel should be visible
    expect((filterPanel.element as HTMLElement).style.display).not.toBe('none')
  })

  it('emits analyzeSelected when analyze button clicked', async () => {
    const store = usePipelineStore()
    store.phase = 'scanned'
    store.setSelectedForAnalysis(['AAPL', 'MSFT'])

    const wrapper = mountControl()
    const analyzeBtn = wrapper.find('[data-testid="analyze-selected-btn"]')
    expect(analyzeBtn.exists()).toBe(true)

    await analyzeBtn.trigger('click')
    expect(wrapper.emitted('analyzeSelected')).toBeTruthy()
  })

  it('emits analyzeTopN on Analyze Top 5 click', async () => {
    const store = usePipelineStore()
    store.phase = 'scanned'

    const wrapper = mountControl()
    const topNBtn = wrapper.find('[data-testid="analyze-top5-btn"]')
    expect(topNBtn.exists()).toBe(true)

    await topNBtn.trigger('click')
    expect(wrapper.emitted('analyzeTopN')).toBeTruthy()
    expect(wrapper.emitted('analyzeTopN')![0]).toEqual([5])
  })

  it('does not show analyze buttons in idle phase', () => {
    const store = usePipelineStore()
    store.phase = 'idle'

    const wrapper = mountControl()
    expect(wrapper.find('[data-testid="analyze-selected-btn"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="analyze-top5-btn"]').exists()).toBe(false)
  })
})
