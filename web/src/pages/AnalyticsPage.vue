<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'
import type {
  WinRateResult,
  ScoreCalibrationBucket,
  HoldingPeriodResult,
  DeltaPerformanceResult,
  PerformanceSummary,
} from '@/types'

const router = useRouter()
const toast = useToast()

const loading = ref(true)
const collectLoading = ref(false)

const summary = ref<PerformanceSummary | null>(null)
const winRates = ref<WinRateResult[]>([])
const calibration = ref<ScoreCalibrationBucket[]>([])
const holdingPeriod = ref<HoldingPeriodResult[]>([])
const deltaPerf = ref<DeltaPerformanceResult[]>([])

const hasData = ref(false)

async function loadAnalytics(): Promise<void> {
  loading.value = true
  try {
    const [summaryData, winRateData, calibData, holdingData, deltaData] = await Promise.allSettled([
      api<PerformanceSummary>('/api/analytics/summary'),
      api<WinRateResult[]>('/api/analytics/win-rate'),
      api<ScoreCalibrationBucket[]>('/api/analytics/score-calibration'),
      api<HoldingPeriodResult[]>('/api/analytics/holding-period'),
      api<DeltaPerformanceResult[]>('/api/analytics/delta-performance'),
    ])
    summary.value = summaryData.status === 'fulfilled' ? summaryData.value : null
    winRates.value = winRateData.status === 'fulfilled' ? winRateData.value : []
    calibration.value = calibData.status === 'fulfilled' ? calibData.value : []
    holdingPeriod.value = holdingData.status === 'fulfilled' ? holdingData.value : []
    deltaPerf.value = deltaData.status === 'fulfilled' ? deltaData.value : []
    hasData.value = winRates.value.length > 0 || calibration.value.length > 0
  } finally {
    loading.value = false
  }
}

async function collectOutcomes(): Promise<void> {
  collectLoading.value = true
  try {
    const result = await api<{ outcomes_collected: number }>('/api/analytics/collect-outcomes', {
      method: 'POST',
    })
    toast.add({
      severity: 'success',
      summary: 'Outcomes Collected',
      detail: `${result.outcomes_collected} outcome${result.outcomes_collected !== 1 ? 's' : ''} collected.`,
      life: 5000,
    })
    await loadAnalytics()
  } catch (err: unknown) {
    if (err instanceof ApiError && err.status === 409) {
      toast.add({ severity: 'warn', summary: 'Busy', detail: 'Another operation is in progress.', life: 5000 })
    } else {
      toast.add({ severity: 'error', summary: 'Failed', detail: err instanceof Error ? err.message : 'Error', life: 5000 })
    }
  } finally {
    collectLoading.value = false
  }
}

function formatPct(val: number | null): string {
  if (val == null) return '--'
  return `${(val * 100).toFixed(1)}%`
}

function formatReturnPct(val: number | null): string {
  if (val == null) return '--'
  const prefix = val >= 0 ? '+' : ''
  return `${prefix}${val.toFixed(1)}%`
}

function directionSeverity(dir: string): 'success' | 'danger' | 'warn' {
  if (dir === 'bullish') return 'success'
  if (dir === 'bearish') return 'danger'
  return 'warn'
}

onMounted(() => {
  void loadAnalytics()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Analytics</h1>
      <Button
        label="Collect Outcomes"
        icon="pi pi-refresh"
        severity="info"
        size="small"
        :loading="collectLoading"
        data-testid="btn-collect-outcomes"
        @click="collectOutcomes"
      />
    </div>

    <div v-if="loading" class="loading-msg">Loading analytics...</div>

    <template v-else-if="!hasData && summary && summary.total_with_outcomes === 0">
      <div class="empty-state" data-testid="analytics-empty">
        <i class="pi pi-chart-bar empty-icon" />
        <p class="empty-text">No outcome data yet.</p>
        <p class="empty-hint">
          Run scans, then click "Collect Outcomes" to track how recommendations performed.
        </p>
        <Button
          label="Go to Scan"
          icon="pi pi-play"
          severity="success"
          @click="router.push('/scan')"
        />
      </div>
    </template>

    <template v-else>
      <!-- Summary Cards -->
      <section v-if="summary" class="section" data-testid="analytics-summary">
        <h2>Performance Summary (Last {{ summary.lookback_days }} days)</h2>
        <div class="summary-grid">
          <div class="summary-card">
            <span class="summary-value mono">{{ summary.total_contracts }}</span>
            <span class="summary-label">Recommendations</span>
          </div>
          <div class="summary-card">
            <span class="summary-value mono">{{ summary.total_with_outcomes }}</span>
            <span class="summary-label">With Outcomes</span>
          </div>
          <div class="summary-card">
            <span class="summary-value mono" :class="{ 'win-rate-good': (summary.overall_win_rate ?? 0) > 0.5 }">
              {{ formatPct(summary.overall_win_rate) }}
            </span>
            <span class="summary-label">Win Rate</span>
          </div>
          <div v-if="summary.avg_stock_return_pct != null" class="summary-card">
            <span class="summary-value mono" :class="summary.avg_stock_return_pct >= 0 ? 'return-pos' : 'return-neg'">
              {{ formatReturnPct(summary.avg_stock_return_pct) }}
            </span>
            <span class="summary-label">Avg Stock Return</span>
          </div>
          <div v-if="summary.best_direction" class="summary-card">
            <Tag :value="summary.best_direction" :severity="directionSeverity(summary.best_direction)" />
            <span class="summary-label">Best Direction</span>
          </div>
          <div v-if="summary.best_holding_days" class="summary-card">
            <span class="summary-value mono">{{ summary.best_holding_days }}d</span>
            <span class="summary-label">Best Holding Period</span>
          </div>
        </div>
      </section>

      <!-- Win Rate by Direction -->
      <section v-if="winRates.length > 0" class="section" data-testid="analytics-win-rate">
        <h2>Win Rate by Direction</h2>
        <div class="win-rate-cards">
          <div v-for="wr in winRates" :key="wr.direction" class="win-rate-card">
            <Tag :value="wr.direction" :severity="directionSeverity(wr.direction)" />
            <div class="wr-stats">
              <span class="wr-rate mono">{{ formatPct(wr.win_rate) }}</span>
              <span class="wr-detail">{{ wr.winners }}W / {{ wr.losers }}L ({{ wr.total_contracts }} total)</span>
            </div>
            <div class="wr-bar">
              <div class="wr-bar-fill" :style="{ width: `${wr.win_rate * 100}%` }" />
            </div>
          </div>
        </div>
      </section>

      <!-- Score Calibration -->
      <section v-if="calibration.length > 0" class="section" data-testid="analytics-calibration">
        <h2>Score Calibration</h2>
        <DataTable :value="calibration" dataKey="score_min" :rows="20" class="analytics-table">
          <Column header="Score Range">
            <template #body="{ data }">
              <span class="mono">{{ data.score_min.toFixed(0) }}-{{ data.score_max.toFixed(0) }}</span>
            </template>
          </Column>
          <Column field="contract_count" header="Contracts" />
          <Column header="Avg Return">
            <template #body="{ data }">
              <span class="mono" :class="data.avg_return_pct >= 0 ? 'return-pos' : 'return-neg'">
                {{ formatReturnPct(data.avg_return_pct) }}
              </span>
            </template>
          </Column>
          <Column header="Win Rate">
            <template #body="{ data }">
              <span class="mono">{{ formatPct(data.win_rate) }}</span>
            </template>
          </Column>
        </DataTable>
      </section>

      <!-- Holding Period -->
      <section v-if="holdingPeriod.length > 0" class="section" data-testid="analytics-holding">
        <h2>Holding Period Analysis</h2>
        <DataTable :value="holdingPeriod" dataKey="holding_days" :rows="20" class="analytics-table">
          <Column field="holding_days" header="Days" />
          <Column header="Direction">
            <template #body="{ data }">
              <Tag :value="data.direction" :severity="directionSeverity(data.direction)" />
            </template>
          </Column>
          <Column header="Avg Return">
            <template #body="{ data }">
              <span class="mono" :class="data.avg_return_pct >= 0 ? 'return-pos' : 'return-neg'">
                {{ formatReturnPct(data.avg_return_pct) }}
              </span>
            </template>
          </Column>
          <Column header="Median Return">
            <template #body="{ data }">
              <span class="mono" :class="data.median_return_pct >= 0 ? 'return-pos' : 'return-neg'">
                {{ formatReturnPct(data.median_return_pct) }}
              </span>
            </template>
          </Column>
          <Column header="Win Rate">
            <template #body="{ data }">
              <span class="mono">{{ formatPct(data.win_rate) }}</span>
            </template>
          </Column>
          <Column field="sample_size" header="Samples" />
        </DataTable>
      </section>

      <!-- Delta Performance -->
      <section v-if="deltaPerf.length > 0" class="section" data-testid="analytics-delta">
        <h2>Delta Performance</h2>
        <DataTable :value="deltaPerf" dataKey="delta_min" :rows="20" class="analytics-table">
          <Column header="Delta Range">
            <template #body="{ data }">
              <span class="mono">{{ data.delta_min.toFixed(2) }}-{{ data.delta_max.toFixed(2) }}</span>
            </template>
          </Column>
          <Column header="Avg Return">
            <template #body="{ data }">
              <span class="mono" :class="data.avg_return_pct >= 0 ? 'return-pos' : 'return-neg'">
                {{ formatReturnPct(data.avg_return_pct) }}
              </span>
            </template>
          </Column>
          <Column header="Win Rate">
            <template #body="{ data }">
              <span class="mono">{{ formatPct(data.win_rate) }}</span>
            </template>
          </Column>
          <Column field="sample_size" header="Samples" />
        </DataTable>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  margin: 0;
  flex: 1;
}

.section {
  margin-bottom: 2rem;
}

.section h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.summary-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.summary-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem 1.5rem;
  min-width: 120px;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--p-surface-100, #eee);
}

.summary-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-500, #666);
}

.win-rate-good {
  color: var(--accent-green);
}

.return-pos {
  color: var(--accent-green);
}

.return-neg {
  color: var(--accent-red);
}

.win-rate-cards {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.win-rate-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.wr-stats {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 120px;
}

.wr-rate {
  font-size: 1.25rem;
  font-weight: 700;
}

.wr-detail {
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
}

.wr-bar {
  flex: 1;
  height: 8px;
  background: var(--p-surface-700, #333);
  border-radius: 4px;
  overflow: hidden;
}

.wr-bar-fill {
  height: 100%;
  background: var(--accent-green);
  border-radius: 4px;
  transition: width 0.3s;
}

.analytics-table {
  font-size: 0.9rem;
}

.mono {
  font-family: var(--font-mono);
}

.loading-msg {
  color: var(--p-surface-400, #888);
  padding: 2rem 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  gap: 0.75rem;
  color: var(--p-surface-400, #888);
}

.empty-icon {
  font-size: 2.5rem;
  color: var(--p-surface-500, #666);
}

.empty-text {
  margin: 0;
  font-size: 1.1rem;
}

.empty-hint {
  margin: 0;
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
  max-width: 400px;
  text-align: center;
}
</style>
