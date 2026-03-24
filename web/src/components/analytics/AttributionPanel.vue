<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import Select from 'primevue/select'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Skeleton from 'primevue/skeleton'
import { useToast } from 'primevue/usetoast'
import { api } from '@/composables/useApi'
import type {
  AttributionReport,
  PredictionAccuracy,
  ConditionBucketAccuracy,
} from '@/types'

const toast = useToast()
const windowDays = ref(90)
const report = ref<AttributionReport | null>(null)
const loading = ref(false)
let fetchId = 0

const windowOptions = [
  { label: '7 days', value: 7 },
  { label: '30 days', value: 30 },
  { label: '90 days', value: 90 },
  { label: '180 days', value: 180 },
  { label: '365 days', value: 365 },
]

async function fetchAttribution(): Promise<void> {
  const currentFetchId = ++fetchId
  loading.value = true
  try {
    const result = await api<AttributionReport>(
      `/api/analytics/attribution`,
      { params: { window_days: windowDays.value } },
    )
    // Guard against stale responses from rapid window changes
    if (currentFetchId === fetchId) {
      report.value = result
    }
  } catch (err) {
    if (currentFetchId === fetchId) {
      report.value = null
      toast.add({
        severity: 'error',
        summary: 'Attribution Error',
        detail: err instanceof Error ? err.message : 'Failed to load attribution data',
        life: 5000,
      })
    }
  } finally {
    if (currentFetchId === fetchId) {
      loading.value = false
    }
  }
}

/** Group condition buckets by source for display. */
function groupedConditions(
  conditions: ConditionBucketAccuracy[],
): Map<string, ConditionBucketAccuracy[]> {
  const groups = new Map<string, ConditionBucketAccuracy[]>()
  for (const c of conditions) {
    const existing = groups.get(c.source)
    if (existing) {
      existing.push(c)
    } else {
      groups.set(c.source, [c])
    }
  }
  return groups
}

function formatAccuracy(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function accuracySeverity(acc: PredictionAccuracy): 'success' | 'warn' | 'danger' {
  if (acc.accuracy >= 0.6) return 'success'
  if (acc.accuracy >= 0.45) return 'warn'
  return 'danger'
}

watch(windowDays, () => void fetchAttribution())
onMounted(() => void fetchAttribution())
</script>

<template>
  <div class="attribution-panel" data-testid="attribution-panel">
    <!-- Window selector -->
    <div class="attribution-panel__controls">
      <label class="attribution-panel__label">Window:</label>
      <Select
        v-model="windowDays"
        :options="windowOptions"
        optionLabel="label"
        optionValue="value"
        class="attribution-panel__select"
        data-testid="window-select"
      />
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="attribution-panel__skeleton">
      <Skeleton width="100%" height="2rem" class="skeleton-row" />
      <Skeleton width="100%" height="8rem" class="skeleton-row" />
      <Skeleton width="100%" height="6rem" class="skeleton-row" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!report || report.total_outcomes === 0"
      class="attribution-panel__empty"
      data-testid="attribution-empty"
    >
      <i class="pi pi-chart-bar" />
      <span>No attribution data available for this window.</span>
    </div>

    <!-- Data display -->
    <template v-else>
      <!-- Summary line -->
      <div class="attribution-panel__summary">
        {{ report.total_outcomes }} outcome{{ report.total_outcomes !== 1 ? 's' : '' }}
        from {{ report.total_recommendations }} recommendation{{ report.total_recommendations !== 1 ? 's' : '' }}
        in {{ report.window_days }}-day window
      </div>

      <!-- Section 1: Source Accuracy Table -->
      <div class="attribution-panel__section">
        <h4 class="attribution-panel__section-title">Source Accuracy</h4>
        <DataTable
          :value="report.source_accuracy"
          :rows="10"
          dataKey="source"
          size="small"
          data-testid="source-accuracy-table"
        >
          <Column field="source" header="Source" :sortable="true" />
          <Column field="total" header="Total" :sortable="true" />
          <Column field="correct" header="Correct" :sortable="true" />
          <Column field="accuracy" header="Accuracy" :sortable="true">
            <template #body="{ data }">
              <Tag
                :value="formatAccuracy((data as PredictionAccuracy).accuracy)"
                :severity="accuracySeverity(data as PredictionAccuracy)"
              />
            </template>
          </Column>
          <Column field="sample_sufficient" header="Sample">
            <template #body="{ data }">
              <Tag
                :value="(data as PredictionAccuracy).sample_sufficient ? 'Sufficient' : 'Low'"
                :severity="(data as PredictionAccuracy).sample_sufficient ? 'success' : 'warn'"
              />
            </template>
          </Column>
        </DataTable>
      </div>

      <!-- Section 2: Condition Buckets -->
      <div
        v-if="report.condition_accuracy.length > 0"
        class="attribution-panel__section"
      >
        <h4 class="attribution-panel__section-title">Condition Buckets</h4>
        <div
          v-for="[source, conditions] in groupedConditions(report.condition_accuracy)"
          :key="source"
          class="attribution-panel__condition-group"
        >
          <h5 class="attribution-panel__source-name">{{ source }}</h5>
          <DataTable
            :value="conditions"
            :rows="20"
            dataKey="condition"
            size="small"
          >
            <Column field="condition" header="Condition" :sortable="true" />
            <Column field="total" header="Total" :sortable="true" />
            <Column field="correct" header="Correct" :sortable="true" />
            <Column field="accuracy" header="Accuracy" :sortable="true">
              <template #body="{ data }">
                {{ formatAccuracy((data as ConditionBucketAccuracy).accuracy) }}
              </template>
            </Column>
          </DataTable>
        </div>
      </div>

      <!-- Section 3: Contract Guidance -->
      <div
        v-if="report.contract_guidance"
        class="attribution-panel__section"
      >
        <h4 class="attribution-panel__section-title">Contract Guidance</h4>
        <div class="attribution-panel__guidance-grid">
          <div class="guidance-item">
            <span class="guidance-label">Optimal Delta Range</span>
            <span class="guidance-value">
              {{ report.contract_guidance.optimal_delta_low.toFixed(2) }}
              &ndash;
              {{ report.contract_guidance.optimal_delta_high.toFixed(2) }}
            </span>
          </div>
          <div class="guidance-item">
            <span class="guidance-label">Delta Win Rate</span>
            <span class="guidance-value">
              {{ formatAccuracy(report.contract_guidance.delta_win_rate) }}
            </span>
          </div>
          <div class="guidance-item">
            <span class="guidance-label">Optimal DTE Range</span>
            <span class="guidance-value">
              {{ report.contract_guidance.optimal_dte_low }}d
              &ndash;
              {{ report.contract_guidance.optimal_dte_high }}d
            </span>
          </div>
          <div class="guidance-item">
            <span class="guidance-label">DTE Win Rate</span>
            <span class="guidance-value">
              {{ formatAccuracy(report.contract_guidance.dte_win_rate) }}
            </span>
          </div>
          <div class="guidance-item">
            <span class="guidance-label">Sample Count</span>
            <span class="guidance-value">
              {{ report.contract_guidance.sample_count }}
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.attribution-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.attribution-panel__controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.attribution-panel__label {
  font-size: 0.85rem;
  color: var(--p-surface-300, #aaa);
  font-family: var(--font-mono);
}

.attribution-panel__select {
  width: 130px;
}

.attribution-panel__skeleton {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.skeleton-row {
  border-radius: 0.5rem;
}

.attribution-panel__empty {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1.5rem 0;
  color: var(--p-surface-400, #888);
  font-size: 0.9rem;
}

.attribution-panel__summary {
  font-size: 0.85rem;
  color: var(--p-surface-300, #aaa);
  font-family: var(--font-mono);
}

.attribution-panel__section {
  margin-top: 0.5rem;
}

.attribution-panel__section-title {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--p-surface-200, #ccc);
}

.attribution-panel__condition-group {
  margin-bottom: 1rem;
}

.attribution-panel__source-name {
  margin: 0.5rem 0 0.25rem;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--p-surface-300, #aaa);
  font-family: var(--font-mono);
}

.attribution-panel__guidance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.75rem;
}

.guidance-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem;
  background: var(--p-surface-700, #333);
  border-radius: 0.5rem;
}

.guidance-label {
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.guidance-value {
  font-size: 1rem;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--p-surface-100, #eee);
}
</style>
