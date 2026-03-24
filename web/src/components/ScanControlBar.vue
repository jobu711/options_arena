<script setup lang="ts">
import { ref, computed } from 'vue'
import Button from 'primevue/button'
import DeskCard from '@/components/DeskCard.vue'
import PreScanFilters from '@/components/scan/PreScanFilters.vue'
import { usePipelineStore } from '@/stores/pipeline'
import { useScanStore } from '@/stores/scan'
import type { PreScanFilterPayload } from '@/types'

const emit = defineEmits<{
  analyzeSelected: []
  analyzeTopN: [limit: number]
}>()

const pipelineStore = usePipelineStore()
const scanStore = useScanStore()

// --- Local state ---
const showFilters = ref(false)
const filterPayload = ref<PreScanFilterPayload>({})
const cardCollapsed = ref(false)

// --- Computed ---
const isScanning = computed(() => pipelineStore.phase === 'scanning')
const hasScored = computed(() => pipelineStore.phase === 'scanned')
const canAnalyze = computed(
  () => hasScored.value && pipelineStore.selectedCount > 0,
)
const selectedCount = computed(() => pipelineStore.selectedCount)
const presetLabel = computed(() => {
  const presetMap: Record<string, string> = {
    sp500: 'S&P 500',
    full: 'Full Universe',
    etfs: 'ETFs',
    nasdaq100: 'NASDAQ 100',
    russell2000: 'Russell 2000',
    most_active: 'Most Active',
  }
  return presetMap[filterPayload.value.preset ?? 'sp500'] ?? filterPayload.value.preset ?? 'S&P 500'
})

// --- Actions ---
function toggleFilters(): void {
  showFilters.value = !showFilters.value
}

function onFilterUpdate(payload: PreScanFilterPayload): void {
  filterPayload.value = payload
}

const isLaunching = ref(false)

async function runScan(): Promise<void> {
  if (isLaunching.value || isScanning.value) return
  isLaunching.value = true
  const payload = filterPayload.value
  try {
    await pipelineStore.startScan({
      preset: payload.preset ?? 'sp500',
      sectors: payload.sectors,
      customTickers: payload.custom_tickers,
      source: 'manual',
    })
  } catch {
    // Error captured by pipeline store
  } finally {
    isLaunching.value = false
  }
}

async function cancelScan(): Promise<void> {
  try {
    await scanStore.cancelScan()
  } catch {
    // Error already captured by scanStore
  }
}

function analyzeSelected(): void {
  emit('analyzeSelected')
}

function analyzeTopN(limit: number): void {
  emit('analyzeTopN', limit)
}
</script>

<template>
  <DeskCard
    title="SCAN CONTROL"
    :full-width="true"
    v-model:collapsed="cardCollapsed"
  >
    <div class="scan-control-bar">
      <!-- Main control row -->
      <div class="control-row">
        <!-- Preset indicator -->
        <div class="preset-indicator" data-testid="preset-indicator">
          <i class="pi pi-database preset-icon" />
          <span class="preset-label">{{ presetLabel }}</span>
        </div>

        <!-- Filters toggle -->
        <Button
          :label="showFilters ? 'Hide Filters' : 'Filters'"
          :icon="showFilters ? 'pi pi-filter-slash' : 'pi pi-filter'"
          size="small"
          severity="secondary"
          :outlined="!showFilters"
          data-testid="filters-toggle"
          @click="toggleFilters"
        />

        <!-- Spacer -->
        <div class="control-spacer" />

        <!-- Run / Cancel buttons -->
        <Button
          v-if="!isScanning"
          label="Run Scan"
          icon="pi pi-play"
          size="small"
          severity="success"
          data-testid="run-scan-btn"
          @click="runScan"
        />
        <Button
          v-if="isScanning"
          label="Cancel"
          icon="pi pi-times"
          size="small"
          severity="danger"
          outlined
          data-testid="cancel-scan-btn"
          @click="cancelScan"
        />

        <!-- Analyze buttons -->
        <Button
          v-if="canAnalyze"
          :label="`Analyze Selected (${selectedCount})`"
          icon="pi pi-bolt"
          size="small"
          severity="info"
          data-testid="analyze-selected-btn"
          @click="analyzeSelected"
        />
        <Button
          v-if="hasScored && selectedCount === 0"
          label="Analyze Top 5"
          icon="pi pi-star"
          size="small"
          severity="info"
          outlined
          data-testid="analyze-top5-btn"
          @click="analyzeTopN(5)"
        />
      </div>

      <!-- Collapsible filter panel -->
      <div v-show="showFilters" class="filter-panel" data-testid="filter-panel">
        <PreScanFilters :disabled="isScanning" @update:filters="onFilterUpdate" />
      </div>
    </div>
  </DeskCard>
</template>

<style scoped>
.scan-control-bar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.control-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.preset-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.75rem;
  background: var(--p-surface-700, #333);
  border-radius: 0.375rem;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--p-surface-200, #ccc);
}

.preset-icon {
  font-size: 0.75rem;
  color: var(--accent-blue);
}

.preset-label {
  font-weight: 500;
}

.control-spacer {
  flex: 1;
}

.filter-panel {
  border-top: 1px solid var(--p-surface-700, #333);
  padding-top: 1rem;
}
</style>
