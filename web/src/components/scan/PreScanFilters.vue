<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import InputNumber from 'primevue/inputnumber'
import SectorTree from '@/components/SectorTree.vue'
import PresetCard from '@/components/scan/PresetCard.vue'
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

const presetIconMap: Record<string, string> = {
  sp500: 'pi-building',
  full: 'pi-globe',
  etfs: 'pi-chart-bar',
  nasdaq100: 'pi-desktop',
  russell2000: 'pi-th-large',
  most_active: 'pi-bolt',
}

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
// Clear helpers (exposed to parent)
// ---------------------------------------------------------------------------

function clearFilter(key: string): void {
  const defaults: Record<string, () => void> = {
    direction_filter: () => { selectedDirection.value = null },
    market_cap_tiers: () => { selectedMarketCaps.value = [] },
    min_iv_rank: () => { minIvRank.value = null },
    min_score: () => { minScore.value = null },
    exclude_near_earnings_days: () => { excludeEarningsDays.value = null },
    min_price: () => { minPrice.value = null },
    max_price: () => { maxPrice.value = null },
    price_range: () => { minPrice.value = null; maxPrice.value = null },
    min_dte: () => { minDte.value = null },
    max_dte: () => { maxDte.value = null },
    dte_range: () => { minDte.value = null; maxDte.value = null },
    sectors: () => { selectedSectors.value = [] },
    industry_groups: () => { selectedIndustryGroups.value = [] },
  }
  defaults[key]?.()
}

function clearAll(): void {
  selectedMarketCaps.value = []
  selectedDirection.value = null
  excludeEarningsDays.value = null
  minIvRank.value = null
  minScore.value = null
  minPrice.value = null
  maxPrice.value = null
  minDte.value = null
  maxDte.value = null
  selectedSectors.value = []
  selectedIndustryGroups.value = []
}

defineExpose({ clearFilter, clearAll })

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
    <!-- Section 1: Select Universe -->
    <div class="filter-section">
      <h3 class="section-title">Select Universe</h3>
      <div class="preset-grid" data-testid="preset-selector">
        <PresetCard
          v-for="opt in presetOptions"
          :key="opt.value"
          :preset="opt.value"
          :label="opt.label"
          :description="opt.description"
          :count="opt.count"
          :icon="presetIconMap[opt.value] ?? 'pi-circle'"
          :selected="selectedPreset === opt.value"
          :disabled="disabled"
          @select="selectedPreset = $event"
        />
      </div>
    </div>

    <!-- Section 2: Strategy -->
    <div class="filter-section">
      <h3 class="section-title">Strategy</h3>
      <div class="filter-card">
        <div class="filter-grid">
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
          </div>
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
          </div>
        </div>
      </div>
    </div>

    <!-- Section 3: Price & Expiry -->
    <div class="filter-section">
      <h3 class="section-title">Price & Expiry</h3>
      <div class="filter-card">
        <div class="filter-grid">
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
          </div>
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
          </div>
        </div>
      </div>
    </div>

    <!-- Section 4: Sectors -->
    <div class="filter-section">
      <h3 class="section-title">Sectors</h3>
      <SectorTree
        :sectors="sectorHierarchy"
        :selectedSectors="selectedSectors"
        :selectedIndustryGroups="selectedIndustryGroups"
        :disabled="disabled"
        data-testid="sector-tree"
        @update:selectedSectors="(v: string[]) => (selectedSectors = v)"
        @update:selectedIndustryGroups="(v: string[]) => (selectedIndustryGroups = v)"
      />
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
    </div>
  </div>
</template>

<style scoped>
.pre-scan-filters {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1rem;
}

.filter-section {
  /* No background needed, just groups content */
}

.section-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--p-surface-300, #aaa);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.75rem;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.75rem;
}

.filter-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}

.filter-label {
  display: block;
  font-size: 0.85rem;
  color: var(--p-surface-300, #aaa);
  margin-bottom: 0.35rem;
  font-weight: 500;
}

.active-filter-info {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
  margin-top: 0.5rem;
}
</style>
