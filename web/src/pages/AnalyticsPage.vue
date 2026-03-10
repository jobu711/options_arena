<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'
import { useBacktestStore } from '@/stores/backtest'
import type {
  PerformanceSummary,
  WinRateResult,
  ScoreCalibrationBucket,
  HoldingPeriodResult,
  DeltaPerformanceResult,
  OutcomeCollectionResult,
} from '@/types'

// Existing analytics components
import SummaryCard from '@/components/analytics/SummaryCard.vue'
import WinRateChart from '@/components/analytics/WinRateChart.vue'
import ScoreCalibrationChart from '@/components/analytics/ScoreCalibrationChart.vue'
import HoldingPeriodTable from '@/components/analytics/HoldingPeriodTable.vue'
import DeltaPerformanceChart from '@/components/analytics/DeltaPerformanceChart.vue'

// Backtest chart components
import EquityCurveChart from '@/components/analytics/EquityCurveChart.vue'
import DrawdownChart from '@/components/analytics/DrawdownChart.vue'
import SectorPerformanceChart from '@/components/analytics/SectorPerformanceChart.vue'
import DTEPerformanceChart from '@/components/analytics/DTEPerformanceChart.vue'
import IVPerformanceChart from '@/components/analytics/IVPerformanceChart.vue'
import GreeksDecompositionChart from '@/components/analytics/GreeksDecompositionChart.vue'
import HoldingComparisonTable from '@/components/analytics/HoldingComparisonTable.vue'
import AgentAccuracyHeatmap from '@/components/analytics/AgentAccuracyHeatmap.vue'

const router = useRouter()
const toast = useToast()
const backtestStore = useBacktestStore()

// --- Tab state ---
const activeTab = ref<string | number>('overview')

// --- Existing analytics state ---
const loading = ref(true)
const collecting = ref(false)
const lookbackDays = ref(30)
const bucketSize = ref(10)
const holdingDirection = ref('all')
const holdingDays = ref(10)

const summary = ref<PerformanceSummary | null>(null)
const winRates = ref<WinRateResult[]>([])
const calibration = ref<ScoreCalibrationBucket[]>([])
const holdingPeriods = ref<HoldingPeriodResult[]>([])
const deltaPerformance = ref<DeltaPerformanceResult[]>([])

const lookbackOptions = [
  { label: '7 days', value: 7 },
  { label: '14 days', value: 14 },
  { label: '30 days', value: 30 },
  { label: '60 days', value: 60 },
  { label: '90 days', value: 90 },
]

// --- Data loading ---
async function loadSummary(): Promise<void> {
  summary.value = await api<PerformanceSummary>('/api/analytics/summary', {
    params: { lookback_days: lookbackDays.value },
  })
}

async function loadDetails(): Promise<void> {
  const dirParam = holdingDirection.value === 'all' ? undefined : holdingDirection.value
  const [wr, cal, hp, dp] = await Promise.all([
    api<WinRateResult[]>('/api/analytics/win-rate').catch(() => [] as WinRateResult[]),
    api<ScoreCalibrationBucket[]>('/api/analytics/score-calibration', {
      params: { bucket_size: bucketSize.value },
    }).catch(() => [] as ScoreCalibrationBucket[]),
    api<HoldingPeriodResult[]>('/api/analytics/holding-period', {
      params: { direction: dirParam },
    }).catch(() => [] as HoldingPeriodResult[]),
    api<DeltaPerformanceResult[]>('/api/analytics/delta-performance', {
      params: { bucket_size: 0.1, holding_days: holdingDays.value },
    }).catch(() => [] as DeltaPerformanceResult[]),
  ])
  winRates.value = wr
  calibration.value = cal
  holdingPeriods.value = hp
  deltaPerformance.value = dp
}

async function loadAll(): Promise<void> {
  loading.value = true
  try {
    await loadSummary()
    if (summary.value && summary.value.total_contracts > 0) {
      await loadDetails()
    }
  } finally {
    loading.value = false
  }
}

async function collectOutcomes(): Promise<void> {
  collecting.value = true
  try {
    const result = await api<OutcomeCollectionResult>('/api/analytics/collect-outcomes', {
      method: 'POST',
    })
    toast.add({
      severity: 'success',
      summary: 'Outcomes Collected',
      detail: `${result.outcomes_collected} outcome${result.outcomes_collected !== 1 ? 's' : ''} collected.`,
      life: 5000,
    })
    await loadAll()
    // Reset backtest tabs so they reload fresh data
    backtestStore.resetLoadedTabs()
  } catch (err: unknown) {
    if (err instanceof ApiError && err.status === 409) {
      toast.add({
        severity: 'warn',
        summary: 'Operation Busy',
        detail: 'Another operation is in progress.',
        life: 5000,
      })
    } else {
      toast.add({
        severity: 'error',
        summary: 'Collection Failed',
        detail: err instanceof Error ? err.message : 'Failed to collect outcomes',
        life: 5000,
      })
    }
  } finally {
    collecting.value = false
  }
}

// --- Tab change handler (lazy loading) ---
async function onTabChange(value: string | number): Promise<void> {
  activeTab.value = value
  const tabName = String(value)
  if (tabName === 'overview') {
    await backtestStore.loadOverviewTab()
  } else if (tabName === 'agents') {
    await backtestStore.loadAgentsTab()
  } else if (tabName === 'segments') {
    await backtestStore.loadSegmentsTab()
  } else if (tabName === 'greeks') {
    await backtestStore.loadGreeksTab()
  } else if (tabName === 'holding') {
    await backtestStore.loadHoldingTab()
  }
}

// --- Watchers for existing analytics filters ---
watch(lookbackDays, () => void loadSummary())
watch(bucketSize, () => {
  void api<ScoreCalibrationBucket[]>('/api/analytics/score-calibration', {
    params: { bucket_size: bucketSize.value },
  })
    .then(d => {
      calibration.value = d
    })
    .catch(() => {})
})
watch(holdingDirection, () => {
  const dirParam = holdingDirection.value === 'all' ? undefined : holdingDirection.value
  void api<HoldingPeriodResult[]>('/api/analytics/holding-period', {
    params: { direction: dirParam },
  })
    .then(d => {
      holdingPeriods.value = d
    })
    .catch(() => {})
})
watch(holdingDays, () => {
  void api<DeltaPerformanceResult[]>('/api/analytics/delta-performance', {
    params: { bucket_size: 0.1, holding_days: holdingDays.value },
  })
    .then(d => {
      deltaPerformance.value = d
    })
    .catch(() => {})
})

onMounted(async () => {
  await loadAll()
  // Also load the default Overview backtest tab
  await backtestStore.loadOverviewTab()
})
</script>

<template>
  <div class="page" data-testid="analytics-page">
    <div class="page-header">
      <h1>Analytics</h1>
      <div class="header-actions">
        <Select
          v-model="lookbackDays"
          :options="lookbackOptions"
          optionLabel="label"
          optionValue="value"
          data-testid="lookback-select"
          class="lookback-select"
        />
        <Button
          label="Collect Outcomes"
          icon="pi pi-refresh"
          severity="info"
          size="small"
          :loading="collecting"
          data-testid="btn-collect-outcomes"
          @click="collectOutcomes"
        />
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="pi pi-spinner pi-spin" style="font-size: 1.5rem" />
      <span>Loading analytics...</span>
    </div>

    <!-- No contracts -->
    <div
      v-else-if="summary && summary.total_contracts === 0"
      class="empty-state"
      data-testid="empty-no-contracts"
    >
      <i class="pi pi-inbox empty-icon" />
      <p class="empty-text">No recommendations yet. Run a scan to start building analytics.</p>
      <Button
        label="Go to Scan"
        icon="pi pi-play"
        severity="success"
        size="small"
        @click="router.push('/scan')"
      />
    </div>

    <!-- Contracts but no outcomes -->
    <div
      v-else-if="summary && summary.total_with_outcomes === 0"
      class="empty-state"
      data-testid="empty-no-outcomes"
    >
      <i class="pi pi-chart-bar empty-icon" />
      <p class="empty-text">
        {{ summary.total_contracts }}
        recommendation{{ summary.total_contracts !== 1 ? 's' : '' }} but no outcomes yet. Click
        Collect Outcomes to fetch current prices.
      </p>
      <Button
        label="Collect Outcomes"
        icon="pi pi-refresh"
        severity="info"
        :loading="collecting"
        @click="collectOutcomes"
      />
    </div>

    <!-- Data display with tabs -->
    <template v-else-if="summary">
      <SummaryCard
        :summary="summary"
        :lookback-days="lookbackDays"
        @update:lookback-days="lookbackDays = $event"
      />

      <Tabs :value="activeTab" @update:value="onTabChange" class="analytics-tabs">
        <TabList>
          <Tab value="overview">Overview</Tab>
          <Tab value="agents">Agents</Tab>
          <Tab value="segments">Segments</Tab>
          <Tab value="greeks">Greeks</Tab>
          <Tab value="holding">Holding</Tab>
        </TabList>
        <TabPanels>
          <!-- Overview Tab -->
          <TabPanel value="overview">
            <div class="tab-content">
              <div class="charts-row">
                <EquityCurveChart :data="backtestStore.equityCurve" />
                <DrawdownChart :data="backtestStore.drawdown" />
              </div>
              <div class="analytics-grid">
                <WinRateChart :data="winRates" />
                <ScoreCalibrationChart
                  :data="calibration"
                  :bucket-size="bucketSize"
                  @update:bucket-size="bucketSize = $event"
                />
                <HoldingPeriodTable
                  :data="holdingPeriods"
                  :direction="holdingDirection"
                  @update:direction="holdingDirection = $event"
                />
                <DeltaPerformanceChart
                  :data="deltaPerformance"
                  :holding-days="holdingDays"
                  @update:holding-days="holdingDays = $event"
                />
              </div>
            </div>
          </TabPanel>

          <!-- Agents Tab -->
          <TabPanel value="agents">
            <div class="tab-content">
              <AgentAccuracyHeatmap
                :accuracy="backtestStore.agentAccuracy"
                :calibration="backtestStore.agentCalibration"
              />
            </div>
          </TabPanel>

          <!-- Segments Tab -->
          <TabPanel value="segments">
            <div class="tab-content">
              <div class="analytics-grid">
                <SectorPerformanceChart :data="backtestStore.sectorPerformance" />
                <DTEPerformanceChart :data="backtestStore.dtePerformance" />
                <IVPerformanceChart :data="backtestStore.ivPerformance" />
              </div>
            </div>
          </TabPanel>

          <!-- Greeks Tab -->
          <TabPanel value="greeks">
            <div class="tab-content">
              <GreeksDecompositionChart :data="backtestStore.greeksDecomposition" />
            </div>
          </TabPanel>

          <!-- Holding Tab -->
          <TabPanel value="holding">
            <div class="tab-content">
              <HoldingComparisonTable :data="backtestStore.holdingComparison" />
            </div>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </template>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.lookback-select {
  width: 130px;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 3rem 1rem;
  color: var(--p-surface-400, #888);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  color: var(--p-surface-400, #888);
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-500, #666);
}

.empty-text {
  margin: 0 0 1rem;
  font-size: 0.9rem;
  text-align: center;
  max-width: 400px;
}

.analytics-tabs {
  margin-top: 1.5rem;
}

.tab-content {
  padding: 1rem 0;
}

.charts-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
}

@media (max-width: 768px) {
  .charts-row {
    grid-template-columns: 1fr;
  }

  .analytics-grid {
    grid-template-columns: 1fr;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }
}
</style>
