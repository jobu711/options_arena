<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import Panel from 'primevue/panel'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import InputNumber from 'primevue/inputnumber'
import Badge from 'primevue/badge'
import SectorTree from '@/components/SectorTree.vue'
import { api } from '@/composables/useApi'
import type { SectorHierarchy, PresetInfo, PreScanFilterPayload } from '@/types'

interface Props {
  disabled?: boolean
}

withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:filters': [payload: PreScanFilterPayload]
}>()

// ---------------------------------------------------------------------------
// Panel 1: Universe
// ---------------------------------------------------------------------------

const presetOptions = ref<Array<{ label: string; value: string; description: string; count: number }>>([
  { label: 'S&P 500', value: 'sp500', description: 'Large-cap U.S. equities', count: 0 },
  { label: 'Full Universe', value: 'full', description: 'All CBOE optionable tickers', count: 0 },
  { label: 'ETFs', value: 'etfs', description: 'Exchange-traded funds', count: 0 },
  { label: 'NASDAQ 100', value: 'nasdaq100', description: 'Top NASDAQ-listed companies', count: 0 },
  { label: 'Russell 2000', value: 'russell2000', description: 'Small-cap U.S. equities', count: 0 },
  { label: 'Most Active', value: 'most_active', description: 'Highest options volume today', count: 0 },
])
const selectedPreset = ref('sp500')

const sectorHierarchy = ref<SectorHierarchy[]>([])
const selectedSectors = ref<string[]>([])
const selectedIndustryGroups = ref<string[]>([])

async function fetchPresetInfo(): Promise<void> {
  try {
    const infos = await api<PresetInfo[]>('/api/universe/preset-info')
    for (const info of infos) {
      const opt = presetOptions.value.find((o) => o.value === info.preset)
      if (opt) {
        opt.count = info.estimated_count
        opt.label = info.label
        opt.description = info.description
      }
    }
  } catch {
    // Graceful fallback — counts stay at 0
  }
}

async function fetchSectors(): Promise<void> {
  try {
    sectorHierarchy.value = await api<SectorHierarchy[]>('/api/universe/sectors')
  } catch {
    sectorHierarchy.value = []
  }
}

const selectedPresetOption = computed(() =>
  presetOptions.value.find((o) => o.value === selectedPreset.value),
)

// ---------------------------------------------------------------------------
// Panel 2: Strategy
// ---------------------------------------------------------------------------

const marketCapOptions = [
  { label: 'Mega', value: 'mega' },
  { label: 'Large', value: 'large' },
  { label: 'Mid', value: 'mid' },
  { label: 'Small', value: 'small' },
  { label: 'Micro', value: 'micro' },
]
const selectedMarketCaps = ref<string[]>([])

const directionOptions = [
  { label: 'Any Direction', value: null },
  { label: 'Bullish Only', value: 'bullish' },
  { label: 'Bearish Only', value: 'bearish' },
  { label: 'Neutral Only', value: 'neutral' },
]
const selectedDirection = ref<string | null>(null)
const excludeEarningsDays = ref<number | null>(null)
const minIvRank = ref<number | null>(null)
const minScore = ref<number | null>(null)

// ---------------------------------------------------------------------------
// Panel 3: Price & Expiry
// ---------------------------------------------------------------------------

const minPrice = ref<number | null>(null)
const maxPrice = ref<number | null>(null)
const minDte = ref<number | null>(null)
const maxDte = ref<number | null>(null)

// ---------------------------------------------------------------------------
// Active filter counts per panel
// ---------------------------------------------------------------------------

const universeFilterCount = computed(() => {
  let count = 0
  if (selectedPreset.value !== 'sp500') count++
  if (selectedSectors.value.length > 0) count++
  if (selectedIndustryGroups.value.length > 0) count++
  return count
})

const strategyFilterCount = computed(() => {
  let count = 0
  if (selectedMarketCaps.value.length > 0) count++
  if (selectedDirection.value != null) count++
  if (excludeEarningsDays.value != null) count++
  if (minIvRank.value != null) count++
  if (minScore.value != null) count++
  return count
})

const priceExpiryFilterCount = computed(() => {
  let count = 0
  if (minPrice.value != null) count++
  if (maxPrice.value != null) count++
  if (minDte.value != null) count++
  if (maxDte.value != null) count++
  return count
})

// ---------------------------------------------------------------------------
// Emit aggregated payload on any change
// ---------------------------------------------------------------------------

function emitFilters(): void {
  const payload: PreScanFilterPayload = {
    preset: selectedPreset.value,
    sectors: selectedSectors.value.length > 0 ? selectedSectors.value : undefined,
    industryGroups: selectedIndustryGroups.value.length > 0 ? selectedIndustryGroups.value : undefined,
    market_cap_tiers: selectedMarketCaps.value.length > 0 ? selectedMarketCaps.value : undefined,
    exclude_near_earnings_days: excludeEarningsDays.value,
    direction_filter: selectedDirection.value,
    min_iv_rank: minIvRank.value,
    min_price: minPrice.value,
    max_price: maxPrice.value,
    min_dte: minDte.value,
    max_dte: maxDte.value,
    min_score: minScore.value,
  }
  emit('update:filters', payload)
}

// Watch all filter state and emit on change
watch(
  [
    selectedPreset,
    selectedSectors,
    selectedIndustryGroups,
    selectedMarketCaps,
    selectedDirection,
    excludeEarningsDays,
    minIvRank,
    minScore,
    minPrice,
    maxPrice,
    minDte,
    maxDte,
  ],
  () => emitFilters(),
  { deep: true, immediate: true },
)

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void fetchPresetInfo()
  void fetchSectors()
})
</script>

<template>
  <div class="pre-scan-filters">
    <!-- Panel 1: Universe -->
    <Panel :toggleable="true" :collapsed="false">
      <template #header>
        <div class="panel-header">
          <span>Universe</span>
          <Badge
            v-if="universeFilterCount > 0"
            :value="String(universeFilterCount)"
            severity="info"
            class="filter-badge"
          />
        </div>
      </template>

      <div class="filter-group">
        <label class="filter-label">Scan Preset</label>
        <Select
          v-model="selectedPreset"
          :options="presetOptions"
          optionLabel="label"
          optionValue="value"
          placeholder="Select preset"
          :disabled="disabled"
          class="preset-select"
          data-testid="preset-selector"
        >
          <template #option="{ option }">
            <div class="preset-option">
              <span class="preset-option-label">{{ option.label }}</span>
              <Badge
                v-if="option.count > 0"
                :value="option.count.toLocaleString()"
                severity="secondary"
                class="preset-count"
              />
            </div>
          </template>
          <template #value="{ value }">
            <div v-if="value" class="preset-option">
              <span>{{ presetOptions.find((o) => o.value === value)?.label ?? value }}</span>
              <Badge
                v-if="selectedPresetOption && selectedPresetOption.count > 0"
                :value="selectedPresetOption.count.toLocaleString()"
                severity="secondary"
                class="preset-count"
              />
            </div>
          </template>
        </Select>
        <small v-if="selectedPresetOption" class="description">
          {{ selectedPresetOption.description }}
        </small>
      </div>

      <div class="filter-group">
        <SectorTree
          :sectors="sectorHierarchy"
          :selectedSectors="selectedSectors"
          :selectedIndustryGroups="selectedIndustryGroups"
          :disabled="disabled"
          data-testid="sector-tree"
          @update:selectedSectors="(v: string[]) => (selectedSectors = v)"
          @update:selectedIndustryGroups="(v: string[]) => (selectedIndustryGroups = v)"
        />
      </div>

      <div
        v-if="selectedSectors.length > 0 || selectedIndustryGroups.length > 0"
        class="active-filter-info"
        data-testid="active-sector-filter"
      >
        <span v-if="selectedSectors.length > 0">
          Filtering by {{ selectedSectors.length }} sector{{
            selectedSectors.length > 1 ? 's' : ''
          }}:
          {{ selectedSectors.join(', ') }}
        </span>
        <span v-if="selectedIndustryGroups.length > 0">
          {{ selectedSectors.length > 0 ? ' | ' : ''
          }}{{ selectedIndustryGroups.length }} industry group{{
            selectedIndustryGroups.length > 1 ? 's' : ''
          }}:
          {{ selectedIndustryGroups.join(', ') }}
        </span>
      </div>
    </Panel>

    <!-- Panel 2: Strategy -->
    <Panel :toggleable="true" :collapsed="true">
      <template #header>
        <div class="panel-header">
          <span>Strategy</span>
          <Badge
            v-if="strategyFilterCount > 0"
            :value="String(strategyFilterCount)"
            severity="info"
            class="filter-badge"
          />
        </div>
      </template>

      <div class="filter-row">
        <div class="filter-group">
          <label class="filter-label">Market Cap</label>
          <MultiSelect
            v-model="selectedMarketCaps"
            :options="marketCapOptions"
            optionLabel="label"
            optionValue="value"
            display="chip"
            placeholder="All market caps"
            :disabled="disabled"
            class="cap-filter"
            data-testid="market-cap-filter"
          />
        </div>

        <div class="filter-group">
          <label class="filter-label">Direction</label>
          <Select
            v-model="selectedDirection"
            :options="directionOptions"
            optionLabel="label"
            optionValue="value"
            placeholder="Direction"
            :disabled="disabled"
            data-testid="direction-filter"
          />
        </div>
      </div>

      <div class="filter-row">
        <div class="filter-group">
          <label class="filter-label">Exclude Near Earnings</label>
          <InputNumber
            v-model="excludeEarningsDays"
            placeholder="Days before earnings"
            :min="0"
            :max="90"
            :disabled="disabled"
            showButtons
            suffix=" days"
            data-testid="earnings-filter"
          />
          <small class="description">Exclude tickers with earnings within N days</small>
        </div>

        <div class="filter-group">
          <label class="filter-label">Min IV Rank</label>
          <InputNumber
            v-model="minIvRank"
            placeholder="Min IV Rank"
            :min="0"
            :max="100"
            :disabled="disabled"
            showButtons
            suffix="%"
            data-testid="iv-rank-filter"
          />
          <small class="description">Only include tickers above this IV rank percentile</small>
        </div>
      </div>

      <div class="filter-row">
        <div class="filter-group">
          <label class="filter-label">Min Composite Score</label>
          <InputNumber
            v-model="minScore"
            placeholder="Min score"
            :min="0"
            :max="100"
            :step="5"
            :minFractionDigits="0"
            :maxFractionDigits="0"
            :disabled="disabled"
            showButtons
            data-testid="min-score-filter"
          />
          <small class="description">Only include tickers scoring above this threshold (0-100)</small>
        </div>
      </div>

    </Panel>

    <!-- Panel 3: Price & Expiry -->
    <Panel :toggleable="true" :collapsed="true">
      <template #header>
        <div class="panel-header">
          <span>Price &amp; Expiry</span>
          <Badge
            v-if="priceExpiryFilterCount > 0"
            :value="String(priceExpiryFilterCount)"
            severity="info"
            class="filter-badge"
          />
        </div>
      </template>

      <div class="filter-row">
        <div class="filter-group">
          <label class="filter-label">Min Stock Price</label>
          <InputNumber
            v-model="minPrice"
            mode="currency"
            currency="USD"
            locale="en-US"
            :min="0.01"
            :disabled="disabled"
            placeholder="No minimum"
            data-testid="min-price-filter"
          />
          <small class="description">Minimum underlying stock price to include</small>
        </div>

        <div class="filter-group">
          <label class="filter-label">Max Stock Price</label>
          <InputNumber
            v-model="maxPrice"
            mode="currency"
            currency="USD"
            locale="en-US"
            :min="0.01"
            :disabled="disabled"
            placeholder="No maximum"
            data-testid="max-price-filter"
          />
          <small class="description">Maximum underlying stock price to include</small>
        </div>
      </div>

      <div class="filter-row">
        <div class="filter-group">
          <label class="filter-label">Min DTE</label>
          <InputNumber
            v-model="minDte"
            :min="1"
            :max="730"
            :disabled="disabled"
            showButtons
            suffix=" days"
            placeholder="No minimum"
            data-testid="min-dte-filter"
          />
          <small class="description">Minimum days to expiration for option contracts</small>
        </div>

        <div class="filter-group">
          <label class="filter-label">Max DTE</label>
          <InputNumber
            v-model="maxDte"
            :min="1"
            :max="730"
            :disabled="disabled"
            showButtons
            suffix=" days"
            placeholder="No maximum"
            data-testid="max-dte-filter"
          />
          <small class="description">Maximum days to expiration for option contracts</small>
        </div>
      </div>
    </Panel>
  </div>
</template>

<style scoped>
.pre-scan-filters {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.filter-badge {
  font-size: 0.7rem;
}

.filter-group {
  margin-bottom: 0.75rem;
}

.filter-group:last-child {
  margin-bottom: 0;
}

.filter-label {
  display: block;
  font-size: 0.85rem;
  color: var(--p-surface-300, #aaa);
  margin-bottom: 0.35rem;
  font-weight: 500;
}

.description {
  display: block;
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
  margin-top: 0.25rem;
}

.filter-row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.filter-row > .filter-group {
  flex: 1;
  min-width: 200px;
}

.preset-select {
  width: 100%;
  max-width: 400px;
}

.preset-option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.preset-option-label {
  flex: 1;
}

.preset-count {
  font-size: 0.7rem;
}

.cap-filter {
  min-width: 200px;
  max-width: 400px;
}

.active-filter-info {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}
</style>
