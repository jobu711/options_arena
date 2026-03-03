<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import Panel from 'primevue/panel'
import Slider from 'primevue/slider'
import Select from 'primevue/select'
import InputNumber from 'primevue/inputnumber'
import type { FilterParams, MarketRegime } from '@/types'

interface Props {
  modelValue: FilterParams
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [value: FilterParams] }>()

// Local state for debounced slider inputs
const minScore = ref(props.modelValue.min_score ?? 0)
const minConfidence = ref(props.modelValue.min_confidence ?? 0)
const minTrend = ref(props.modelValue.min_trend ?? 0)
const minIvVol = ref(props.modelValue.min_iv_vol ?? 0)
const minFlow = ref(props.modelValue.min_flow ?? 0)
const minRisk = ref(props.modelValue.min_risk ?? 0)
const marketRegime = ref<MarketRegime | null>(props.modelValue.market_regime ?? null)
const maxEarningsDays = ref<number | null>(props.modelValue.max_earnings_days ?? null)
const minEarningsDays = ref<number | null>(props.modelValue.min_earnings_days ?? null)

const regimeOptions = [
  { label: 'All Regimes', value: null },
  { label: 'Trending', value: 'trending' },
  { label: 'Mean Reverting', value: 'mean_reverting' },
  { label: 'Volatile', value: 'volatile' },
  { label: 'Crisis', value: 'crisis' },
]

// Count active filters for badge
const activeFilterCount = computed(() => {
  let count = 0
  if (minScore.value > 0) count++
  if (minConfidence.value > 0) count++
  if (minTrend.value > 0) count++
  if (minIvVol.value > 0) count++
  if (minFlow.value > 0) count++
  if (minRisk.value > 0) count++
  if (marketRegime.value) count++
  if (maxEarningsDays.value !== null) count++
  if (minEarningsDays.value !== null) count++
  return count
})

const panelHeader = computed(() => {
  const base = 'Advanced Filters'
  return activeFilterCount.value > 0 ? `${base} (${activeFilterCount.value})` : base
})

// Sync props → local state when parent changes (e.g., preset applied)
watch(
  () => props.modelValue,
  (v) => {
    minScore.value = v.min_score ?? 0
    minConfidence.value = v.min_confidence ?? 0
    minTrend.value = v.min_trend ?? 0
    minIvVol.value = v.min_iv_vol ?? 0
    minFlow.value = v.min_flow ?? 0
    minRisk.value = v.min_risk ?? 0
    marketRegime.value = v.market_regime ?? null
    maxEarningsDays.value = v.max_earnings_days ?? null
    minEarningsDays.value = v.min_earnings_days ?? null
  },
  { deep: true },
)

// Debounce slider changes
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function emitFilters(): void {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    const filters: FilterParams = {}
    if (minScore.value > 0) filters.min_score = minScore.value
    if (minConfidence.value > 0) filters.min_confidence = minConfidence.value
    if (minTrend.value > 0) filters.min_trend = minTrend.value
    if (minIvVol.value > 0) filters.min_iv_vol = minIvVol.value
    if (minFlow.value > 0) filters.min_flow = minFlow.value
    if (minRisk.value > 0) filters.min_risk = minRisk.value
    if (marketRegime.value) filters.market_regime = marketRegime.value
    if (maxEarningsDays.value !== null) filters.max_earnings_days = maxEarningsDays.value
    if (minEarningsDays.value !== null) filters.min_earnings_days = minEarningsDays.value
    emit('update:modelValue', filters)
  }, 300)
}

function onSelectChange(): void {
  // Selects and inputs emit immediately (no debounce needed)
  if (debounceTimer) clearTimeout(debounceTimer)
  const filters: FilterParams = {}
  if (minScore.value > 0) filters.min_score = minScore.value
  if (minConfidence.value > 0) filters.min_confidence = minConfidence.value
  if (minTrend.value > 0) filters.min_trend = minTrend.value
  if (minIvVol.value > 0) filters.min_iv_vol = minIvVol.value
  if (minFlow.value > 0) filters.min_flow = minFlow.value
  if (minRisk.value > 0) filters.min_risk = minRisk.value
  if (marketRegime.value) filters.market_regime = marketRegime.value
  if (maxEarningsDays.value !== null) filters.max_earnings_days = maxEarningsDays.value
  if (minEarningsDays.value !== null) filters.min_earnings_days = minEarningsDays.value
  emit('update:modelValue', filters)
}
</script>

<template>
  <Panel :header="panelHeader" :toggleable="true" :collapsed="true" data-testid="scan-filter-panel">
    <div class="filter-grid">
      <div class="filter-item">
        <label class="filter-label">Min Score: {{ minScore }}</label>
        <Slider v-model="minScore" :min="0" :max="100" data-testid="filter-min-score" @change="emitFilters()" />
      </div>
      <div class="filter-item">
        <label class="filter-label">Min Confidence: {{ minConfidence }}%</label>
        <Slider v-model="minConfidence" :min="0" :max="100" data-testid="filter-min-confidence" @change="emitFilters()" />
      </div>
      <div class="filter-item">
        <label class="filter-label">Min Trend: {{ minTrend }}</label>
        <Slider v-model="minTrend" :min="0" :max="100" data-testid="filter-min-trend" @change="emitFilters()" />
      </div>
      <div class="filter-item">
        <label class="filter-label">Min IV/Vol: {{ minIvVol }}</label>
        <Slider v-model="minIvVol" :min="0" :max="100" data-testid="filter-min-iv-vol" @change="emitFilters()" />
      </div>
      <div class="filter-item">
        <label class="filter-label">Min Flow: {{ minFlow }}</label>
        <Slider v-model="minFlow" :min="0" :max="100" data-testid="filter-min-flow" @change="emitFilters()" />
      </div>
      <div class="filter-item">
        <label class="filter-label">Min Risk: {{ minRisk }}</label>
        <Slider v-model="minRisk" :min="0" :max="100" data-testid="filter-min-risk" @change="emitFilters()" />
      </div>
      <div class="filter-item">
        <label class="filter-label">Market Regime</label>
        <Select
          v-model="marketRegime"
          :options="regimeOptions"
          optionLabel="label"
          optionValue="value"
          placeholder="All Regimes"
          size="small"
          data-testid="filter-market-regime"
          @change="onSelectChange()"
        />
      </div>
      <div class="filter-item">
        <label class="filter-label">Max Earnings Days</label>
        <InputNumber
          v-model="maxEarningsDays"
          :min="0"
          :max="90"
          placeholder="Any"
          size="small"
          showButtons
          data-testid="filter-max-earnings"
          @input="onSelectChange()"
        />
      </div>
      <div class="filter-item">
        <label class="filter-label">Min Earnings Days</label>
        <InputNumber
          v-model="minEarningsDays"
          :min="0"
          :max="90"
          placeholder="Any"
          size="small"
          showButtons
          data-testid="filter-min-earnings"
          @input="onSelectChange()"
        />
      </div>
    </div>
  </Panel>
</template>

<style scoped>
.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  padding: 0.5rem 0;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.filter-label {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}
</style>
