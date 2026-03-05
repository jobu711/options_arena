<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import InputNumber from 'primevue/inputnumber'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressTracker from '@/components/ProgressTracker.vue'
import SectorTree from '@/components/SectorTree.vue'
import { useScanStore } from '@/stores/scan'
import { useOperationStore } from '@/stores/operation'
import { useWebSocket } from '@/composables/useWebSocket'
import { api, ApiError } from '@/composables/useApi'
import ThemeChips from '@/components/scan/ThemeChips.vue'
import type { ScanEvent } from '@/types/ws'
import type { SectorHierarchy, ThemeInfo } from '@/types'

const router = useRouter()
const toast = useToast()
const scanStore = useScanStore()
const opStore = useOperationStore()

const SCAN_PHASES = ['universe', 'scoring', 'options', 'persist']

const presetOptions = [
  { label: 'S&P 500', value: 'sp500' },
  { label: 'Full Universe', value: 'full' },
  { label: 'ETFs', value: 'etfs' },
]
const selectedPreset = ref('sp500')

// Sector + industry group filter state (hierarchical tree)
const sectorHierarchy = ref<SectorHierarchy[]>([])
const selectedSectors = ref<string[]>([])
const selectedIndustryGroups = ref<string[]>([])

// Pre-scan filter state
const marketCapOptions = [
  { label: 'Mega', value: 'mega' },
  { label: 'Large', value: 'large' },
  { label: 'Mid', value: 'mid' },
  { label: 'Small', value: 'small' },
  { label: 'Micro', value: 'micro' },
]
const selectedMarketCaps = ref<string[]>([])
const excludeEarningsDays = ref<number | null>(null)
const directionOptions = [
  { label: 'Any Direction', value: null },
  { label: 'Bullish Only', value: 'bullish' },
  { label: 'Bearish Only', value: 'bearish' },
  { label: 'Neutral Only', value: 'neutral' },
]
const selectedDirection = ref<string | null>(null)
const minIvRank = ref<number | null>(null)

async function fetchSectors(): Promise<void> {
  try {
    sectorHierarchy.value = await api<SectorHierarchy[]>('/api/universe/sectors')
  } catch {
    sectorHierarchy.value = []
  }
}

// Theme filter state
const availableThemes = ref<ThemeInfo[]>([])
const selectedThemes = ref<string[]>([])

async function fetchThemes(): Promise<void> {
  try {
    availableThemes.value = await api<ThemeInfo[]>('/api/universe/themes')
  } catch {
    availableThemes.value = []
  }
}

// WebSocket connection for live scan progress
let wsClose: (() => void) | null = null

async function runScan(): Promise<void> {
  try {
    opStore.start('scan')
    const scanId = await scanStore.startScan({
      preset: selectedPreset.value,
      sectors: selectedSectors.value.length > 0 ? selectedSectors.value : undefined,
      industryGroups: selectedIndustryGroups.value.length > 0 ? selectedIndustryGroups.value : undefined,
      themes: selectedThemes.value.length > 0 ? selectedThemes.value : undefined,
      market_cap_tiers: selectedMarketCaps.value,
      exclude_near_earnings_days: excludeEarningsDays.value,
      direction_filter: selectedDirection.value,
      min_iv_rank: minIvRank.value,
    })

    // Connect to WebSocket for progress updates
    const { close } = useWebSocket<ScanEvent>({
      url: `/ws/scan/${scanId}`,
      onMessage(event) {
        switch (event.type) {
          case 'progress':
            scanStore.updateProgress(event)
            break
          case 'error':
            scanStore.addError(event)
            toast.add({ severity: 'warn', summary: 'Scan Warning', detail: event.message, life: 5000 })
            break
          case 'complete':
            scanStore.setComplete(event)
            opStore.finish()
            close()  // Stop reconnection — terminal event
            if (event.cancelled) {
              toast.add({ severity: 'info', summary: 'Scan Cancelled', life: 3000 })
            } else {
              toast.add({ severity: 'success', summary: 'Scan Complete', detail: `Scan #${event.scan_id} finished`, life: 5000 })
              void scanStore.fetchScans()
            }
            break
        }
      },
    })
    wsClose = close
  } catch (e) {
    opStore.finish()
    scanStore.reset()
    const msg = e instanceof ApiError ? e.message : 'Failed to start scan'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

async function handleCancel(): Promise<void> {
  try {
    await scanStore.cancelScan()
    toast.add({ severity: 'info', summary: 'Cancelling...', detail: 'Scan cancellation requested', life: 3000 })
  } catch {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to cancel scan', life: 5000 })
  }
}

function viewResults(scanId: number): void {
  router.push(`/scan/${scanId}`)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

onMounted(() => {
  void scanStore.fetchScans()
  void fetchSectors()
  void fetchThemes()
})
onUnmounted(() => {
  wsClose?.()
  if (opStore.inProgress) opStore.finish()
})
</script>

<template>
  <div class="page">
    <h1 data-testid="scan-title">Scan</h1>

    <!-- Launch Panel -->
    <div class="launch-panel">
      <Select
        v-model="selectedPreset"
        :options="presetOptions"
        optionLabel="label"
        optionValue="value"
        placeholder="Select preset"
        :disabled="scanStore.isScanning || opStore.inProgress"
        data-testid="preset-selector"
      />
      <SectorTree
        :sectors="sectorHierarchy"
        :selectedSectors="selectedSectors"
        :selectedIndustryGroups="selectedIndustryGroups"
        :disabled="scanStore.isScanning || opStore.inProgress"
        data-testid="sector-tree"
        @update:selectedSectors="(v: string[]) => selectedSectors = v"
        @update:selectedIndustryGroups="(v: string[]) => selectedIndustryGroups = v"
      />
      <Button
        label="Run Scan"
        icon="pi pi-play"
        severity="success"
        :disabled="scanStore.isScanning || opStore.inProgress"
        :loading="scanStore.isScanning"
        data-testid="start-scan-btn"
        @click="runScan()"
      />
    </div>
    <!-- Pre-scan Filters -->
    <div class="filter-row">
      <MultiSelect
        v-model="selectedMarketCaps"
        :options="marketCapOptions"
        optionLabel="label"
        optionValue="value"
        display="chip"
        placeholder="Market cap tiers"
        :disabled="scanStore.isScanning || opStore.inProgress"
        class="cap-filter"
        data-testid="market-cap-filter"
      />
      <Select
        v-model="selectedDirection"
        :options="directionOptions"
        optionLabel="label"
        optionValue="value"
        placeholder="Direction"
        :disabled="scanStore.isScanning || opStore.inProgress"
        data-testid="direction-filter"
      />
      <InputNumber
        v-model="excludeEarningsDays"
        placeholder="Exclude earnings (days)"
        :min="0"
        :max="90"
        :disabled="scanStore.isScanning || opStore.inProgress"
        showButtons
        suffix=" days"
        data-testid="earnings-filter"
      />
      <InputNumber
        v-model="minIvRank"
        placeholder="Min IV Rank"
        :min="0"
        :max="100"
        :disabled="scanStore.isScanning || opStore.inProgress"
        showButtons
        suffix="%"
        data-testid="iv-rank-filter"
      />
    </div>

    <div v-if="selectedSectors.length > 0 || selectedIndustryGroups.length > 0" class="active-filter-info" data-testid="active-sector-filter">
      <span v-if="selectedSectors.length > 0">
        Filtering by {{ selectedSectors.length }} sector{{ selectedSectors.length > 1 ? 's' : '' }}:
        {{ selectedSectors.join(', ') }}
      </span>
      <span v-if="selectedIndustryGroups.length > 0">
        {{ selectedSectors.length > 0 ? ' | ' : '' }}{{ selectedIndustryGroups.length }} industry group{{ selectedIndustryGroups.length > 1 ? 's' : '' }}:
        {{ selectedIndustryGroups.join(', ') }}
      </span>
    </div>

    <!-- Theme Chips (pre-scan filter) -->
    <ThemeChips
      :themes="availableThemes"
      v-model:selectedThemes="selectedThemes"
    />

    <!-- Progress Panel -->
    <ProgressTracker
      v-if="scanStore.isScanning && scanStore.progress"
      :phases="SCAN_PHASES"
      :current-phase="scanStore.progress.phase"
      :current="scanStore.progress.current"
      :total="scanStore.progress.total"
      class="progress-panel"
      @cancel="handleCancel()"
    />

    <!-- Past Scans -->
    <section class="section">
      <h2>Past Scans</h2>
      <DataTable
        :value="scanStore.scans"
        :loading="scanStore.loading && !scanStore.isScanning"
        dataKey="id"
        :rows="10"
        responsiveLayout="scroll"
        class="scans-table"
        data-testid="scan-list-table"
        @row-click="(e: { data: { id: number } }) => viewResults(e.data.id)"
      >
        <Column header="ID" field="id" :style="{ width: '60px' }">
          <template #body="{ data }">
            <span class="mono">#{{ data.id }}</span>
          </template>
        </Column>
        <Column header="Preset" field="preset">
          <template #body="{ data }">
            <span class="preset-tag">{{ (data.preset as string).toUpperCase() }}</span>
            <span v-if="data.source === 'watchlist'" class="source-tag">WL</span>
          </template>
        </Column>
        <Column header="Scanned" field="tickers_scanned">
          <template #body="{ data }">
            <span class="mono">{{ data.tickers_scanned.toLocaleString() }}</span>
          </template>
        </Column>
        <Column header="Scored" field="tickers_scored">
          <template #body="{ data }">
            <span class="mono">{{ data.tickers_scored.toLocaleString() }}</span>
          </template>
        </Column>
        <Column header="Recs" field="recommendations">
          <template #body="{ data }">
            <span class="mono">{{ data.recommendations }}</span>
          </template>
        </Column>
        <Column header="Date" field="started_at">
          <template #body="{ data }">{{ formatDate(data.started_at) }}</template>
        </Column>
        <template #empty>
          <div class="empty-msg" data-testid="scan-list-empty">No scans yet. Run your first scan above.</div>
        </template>
      </DataTable>
    </section>
  </div>
</template>

<style scoped>
.launch-panel {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.sector-filter {
  min-width: 250px;
  max-width: 500px;
}

.filter-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.cap-filter {
  min-width: 200px;
  max-width: 400px;
}

.active-filter-info {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
  margin-bottom: 1rem;
}

.progress-panel {
  margin-bottom: 1.5rem;
}

.section {
  margin-top: 1rem;
}

.section h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.scans-table :deep(tr) {
  cursor: pointer;
}

.scans-table :deep(tr:hover td) {
  background: var(--p-surface-700, #2a2a2a) !important;
}

.mono {
  font-family: var(--font-mono);
}

.preset-tag {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-green);
}

.source-tag {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--accent-blue);
  margin-left: 0.4rem;
  padding: 0.1rem 0.3rem;
  border: 1px solid var(--accent-blue);
  border-radius: 0.25rem;
  vertical-align: middle;
}

.empty-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-400, #888);
}
</style>
