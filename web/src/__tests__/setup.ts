/**
 * Global test setup for Vitest.
 *
 * - Configures jsdom environment globals
 * - Stubs PrimeVue components used across tests
 */

import { config } from '@vue/test-utils'

// Stub PrimeVue components globally so they don't error during mount.
// Component tests should stub domain-specific child components individually.
config.global.stubs = {
  // PrimeVue primitives -- stubs preserve attrs (including data-testid)
  Tag: {
    template: '<span data-testid="tag-stub" v-bind="$attrs"><slot /></span>',
    inheritAttrs: false,
    props: ['severity', 'value'],
  },
  Button: {
    template: '<button v-bind="$attrs" @click="$emit(\'click\', $event)">{{ label }}<slot /></button>',
    inheritAttrs: true,
    props: ['label', 'icon', 'size', 'severity', 'outlined', 'text', 'disabled'],
    emits: ['click'],
  },
  ProgressBar: {
    template: '<div data-testid="progressbar-stub" v-bind="$attrs" />',
    inheritAttrs: false,
    props: ['value', 'showValue'],
  },
  DataTable: {
    template: '<table data-testid="datatable-stub" v-bind="$attrs"><slot /></table>',
    inheritAttrs: false,
    props: ['value', 'selection', 'sortMode', 'sortField', 'sortOrder', 'scrollable', 'scrollHeight', 'virtualScrollerOptions', 'dataKey', 'rowClass', 'rows', 'size'],
    emits: ['row-click', 'update:selection'],
  },
  Column: {
    template: '<col data-testid="column-stub" />',
    props: ['field', 'header', 'sortable', 'selectionMode', 'style'],
  },
  Select: {
    template: '<select data-testid="select-stub" v-bind="$attrs" />',
    inheritAttrs: false,
    props: ['modelValue', 'options', 'optionLabel', 'optionValue'],
    emits: ['update:modelValue'],
  },
  Skeleton: {
    template: '<div data-testid="skeleton-stub" />',
    props: ['width', 'height'],
  },
}
