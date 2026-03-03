<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import type { FilterParams } from '@/types'

interface Props {
  currentFilters: FilterParams
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'preset-applied': [filters: FilterParams]
  'clear-all': []
}>()

interface Preset {
  key: string
  label: string
  filters: FilterParams
}

const PRESETS: Preset[] = [
  { key: 'HIGH_IV', label: 'High IV Setups', filters: { min_iv_vol: 70, min_confidence: 50 } },
  { key: 'MOMENTUM', label: 'Momentum', filters: { min_trend: 70, min_confidence: 60, market_regime: 'trending' } },
  { key: 'MEAN_REVERSION', label: 'Mean Reversion', filters: { min_trend: 30, market_regime: 'mean_reverting' } },
  { key: 'INCOME', label: 'Income/Theta', filters: { min_iv_vol: 50, min_risk: 30 } },
  { key: 'EARNINGS', label: 'Earnings Plays', filters: { max_earnings_days: 14 } },
  { key: 'LOW_RISK', label: 'Low Risk', filters: { min_risk: 20, min_confidence: 60 } },
]

function filtersMatch(a: FilterParams, b: FilterParams): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof FilterParams>
  for (const key of keys) {
    const va = a[key]
    const vb = b[key]
    if ((va ?? undefined) !== (vb ?? undefined)) return false
  }
  return true
}

const activePresetKey = computed<string | null>(() => {
  for (const preset of PRESETS) {
    if (filtersMatch(props.currentFilters, preset.filters)) return preset.key
  }
  return null
})

const hasActiveFilters = computed(() => {
  return Object.values(props.currentFilters).some((v) => v !== undefined && v !== null)
})
</script>

<template>
  <div class="filter-presets" data-testid="filter-presets">
    <Button
      v-for="preset in PRESETS"
      :key="preset.key"
      :label="preset.label"
      size="small"
      :severity="activePresetKey === preset.key ? 'info' : 'secondary'"
      :outlined="activePresetKey !== preset.key"
      :data-testid="`preset-${preset.key}`"
      @click="emit('preset-applied', { ...preset.filters })"
    />
    <Button
      v-if="hasActiveFilters"
      label="Clear All"
      icon="pi pi-times"
      size="small"
      severity="danger"
      text
      data-testid="preset-clear-all"
      @click="emit('clear-all')"
    />
  </div>
</template>

<style scoped>
.filter-presets {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}
</style>
