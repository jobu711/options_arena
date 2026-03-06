<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'
import type {
  PerformanceSummary,
  WinRateResult,
  ScoreCalibrationBucket,
  HoldingPeriodResult,
  DeltaPerformanceResult,
  OutcomeCollectionResult,
} from '@/types'
import SummaryCard from '@/components/analytics/SummaryCard.vue'
import WinRateChart from '@/components/analytics/WinRateChart.vue'
import ScoreCalibrationChart from '@/components/analytics/ScoreCalibrationChart.vue'
import HoldingPeriodTable from '@/components/analytics/HoldingPeriodTable.vue'
import DeltaPerformanceChart from '@/components/analytics/DeltaPerformanceChart.vue'

const router = useRouter()
const toast = useToast()

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

watch(lookbackDays, () => void loadSummary())
watch(bucketSize, () => {
  void api<ScoreCalibrationBucket[]>('/api/analytics/score-calibration', {
    params: { bucket_size: bucketSize.value },
  }).then(d => { calibration.value = d }).catch(() => {})
})
watch(holdingDirection, () => {
  const dirParam = holdingDirection.value === 'all' ? undefined : holdingDirection.value
  void api<HoldingPeriodResult[]>('/api/analytics/holding-period', {
    params: { direction: dirParam },
  }).then(d => { holdingPeriods.value = d }).catch(() => {})
})
watch(holdingDays, () => {
  void api<DeltaPerformanceResult[]>('/api/analytics/delta-performance', {
    params: { bucket_size: 0.1, holding_days: holdingDays.value },
  }).then(d => { deltaPerformance.value = d }).catch(() => {})
})

onMounted(() => void loadAll())
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
    <div v-else-if="summary && summary.total_contracts === 0" class="empty-state" data-testid="empty-no-contracts">
      <i class="pi pi-inbox empty-icon" />
      <p class="empty-text">No recommendations yet. Run a scan to start building analytics.</p>
      <Button label="Go to Scan" icon="pi pi-play" severity="success" size="small" @click="router.push('/scan')" />
    </div>

    <!-- Contracts but no outcomes -->
    <div v-else-if="summary && summary.total_with_outcomes === 0" class="empty-state" data-testid="empty-no-outcomes">
      <i class="pi pi-chart-bar empty-icon" />
      <p class="empty-text">
        {{ summary.total_contracts }} recommendation{{ summary.total_contracts !== 1 ? 's' : '' }}
        but no outcomes yet. Click Collect Outcomes to fetch current prices.
      </p>
      <Button label="Collect Outcomes" icon="pi pi-refresh" severity="info" :loading="collecting" @click="collectOutcomes" />
    </div>

    <!-- Data display -->
    <template v-else-if="summary">
      <SummaryCard
        :summary="summary"
        :lookback-days="lookbackDays"
        @update:lookback-days="lookbackDays = $event"
      />
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

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
  margin-top: 1.5rem;
}

@media (max-width: 768px) {
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
