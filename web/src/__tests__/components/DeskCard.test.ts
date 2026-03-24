import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeskCard from '@/components/DeskCard.vue'

describe('DeskCard', () => {
  it('renders title in header', () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'TEST TITLE' },
    })
    expect(wrapper.find('.desk-card__title').text()).toBe('TEST TITLE')
  })

  it('shows body content by default', () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'Card' },
      slots: { default: '<p>Body content</p>' },
    })
    const body = wrapper.find('.desk-card__body')
    expect(body.exists()).toBe(true)
    // v-show keeps element in DOM but may set display: none
    expect((body.element as HTMLElement).style.display).not.toBe('none')
    expect(body.text()).toContain('Body content')
  })

  it('hides body when collapsed prop is true', () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'Card', collapsed: true },
      slots: { default: '<p>Body content</p>' },
    })
    const body = wrapper.find('.desk-card__body')
    expect(body.exists()).toBe(true)
    // v-show sets display: none
    expect((body.element as HTMLElement).style.display).toBe('none')
  })

  it('emits update:collapsed on header click', async () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'Card', collapsed: false },
    })
    await wrapper.find('.desk-card__header').trigger('click')

    expect(wrapper.emitted('update:collapsed')).toBeTruthy()
    expect(wrapper.emitted('update:collapsed')![0]).toEqual([true])
  })

  it('emits update:collapsed with false when currently collapsed', async () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'Card', collapsed: true },
    })
    await wrapper.find('.desk-card__header').trigger('click')

    expect(wrapper.emitted('update:collapsed')![0]).toEqual([false])
  })

  it('applies full-width class when fullWidth prop set', () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'Card', fullWidth: true },
    })
    expect(wrapper.find('.desk-card--full-width').exists()).toBe(true)
  })

  it('does not apply full-width class by default', () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'Card' },
    })
    expect(wrapper.find('.desk-card--full-width').exists()).toBe(false)
  })

  it('renders status slot in header', () => {
    const wrapper = mount(DeskCard, {
      props: { title: 'Card' },
      slots: { status: '<span class="test-status">Active</span>' },
    })
    expect(wrapper.find('.test-status').text()).toBe('Active')
  })
})
