<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressTracker from '@/components/ProgressTracker.vue'
import { useScanStore } from '@/stores/scan'
import { useOperationStore } from '@/stores/operation'
import { useWebSocket } from '@/composables/useWebSocket'
import { api, ApiError } from '@/composables/useApi'
import type { ScanEvent } from '@/types/ws'
import type { SectorOption } from '@/types'

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

// Sector filter state
const sectorOptions = ref<Array<{ name: string; value: string }>>([])
const selectedSectors = ref<string[]>([])

async function fetchSectors(): Promise<void> {
  try {
    const data = await api<SectorOption[]>('/api/universe/sectors')
    sectorOptions.value = data.map((s) => ({
      name: `${s.name} (${s.ticker_count})`,
      value: s.name,
    }))
  } catch {
    sectorOptions.value = []
  }
}

// WebSocket connection for live scan progress
let wsClose: (() => void) | null = null

async function runScan(): Promise<void> {
  try {
    opStore.start('scan')
    const scanId = await scanStore.startScan(
      selectedPreset.value,
      selectedSectors.value.length > 0 ? selectedSectors.value : undefined,
    )

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
})
onUnmounted(() => wsClose?.())
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
      <MultiSelect
        v-model="selectedSectors"
        :options="sectorOptions"
        optionLabel="name"
        optionValue="value"
        display="chip"
        filter
        placeholder="Filter by sector"
        :disabled="scanStore.isScanning || opStore.inProgress"
        class="sector-filter"
        data-testid="sector-filter"
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
    <div v-if="selectedSectors.length > 0" class="active-filter-info" data-testid="active-sector-filter">
      Filtering by {{ selectedSectors.length }} sector{{ selectedSectors.length > 1 ? 's' : '' }}:
      {{ selectedSectors.join(', ') }}
    </div>

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

.mono {
  font-family: var(--font-mono);
}

.preset-tag {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-green);
}

.empty-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-400, #888);
}
</style>
