import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PipelineStatus from '@/components/PipelineStatus.vue'
import type { PipelineStage } from '@/types/recommendation'

describe('PipelineStatus', () => {
  const stages: Array<{
    stage: PipelineStage
    label: string
    severity: string
  }> = [
    { stage: 'queued', label: 'Queued', severity: 'secondary' },
    { stage: 'scored', label: 'Scored', severity: 'info' },
    { stage: 'analyzing', label: 'Analyzing...', severity: 'warn' },
    { stage: 'ready', label: 'Ready', severity: 'success' },
    { stage: 'failed', label: 'Failed', severity: 'danger' },
  ]

  for (const { stage, label, severity } of stages) {
    it(`renders correct label "${label}" and severity "${severity}" for stage "${stage}"`, () => {
      const wrapper = mount(PipelineStatus, {
        props: { stage },
      })

      const text = wrapper.text()
      expect(text).toContain(label)
    })
  }

  it('shows spinning icon for analyzing stage', () => {
    const wrapper = mount(PipelineStatus, {
      props: { stage: 'analyzing' as PipelineStage },
    })
    expect(wrapper.find('.spin-icon').exists()).toBe(true)
  })

  it('does not show spinning icon for ready stage', () => {
    const wrapper = mount(PipelineStatus, {
      props: { stage: 'ready' as PipelineStage },
    })
    expect(wrapper.find('.spin-icon').exists()).toBe(false)
  })
})
