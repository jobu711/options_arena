<script setup lang="ts">
import { ref, onMounted } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'
import DeskCard from '@/components/DeskCard.vue'
import DeskAssessmentCard from '@/components/DeskAssessmentCard.vue'
import PositionCard from '@/components/PositionCard.vue'
import type { DebateResultSummary, RecommendationDetail } from '@/types'

const toast = useToast()
const summaries = ref<DebateResultSummary[]>([])
const loading = ref(false)
const tickerFilter = ref('')

// Detail dialog state
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<RecommendationDetail | null>(null)

async function fetchHistory(): Promise<void> {
  loading.value = true
  try {
    const params: Record<string, string | number> = { limit: 100 }
    const t = tickerFilter.value.trim().toUpperCase()
    if (t) params.ticker = t
    summaries.value = await api<DebateResultSummary[]>('/api/debate', { params })
  } catch (err: unknown) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load history'
    toast.add({ severity: 'error', summary: 'Load Failed', detail: msg, life: 5000 })
  } finally {
    loading.value = false
  }
}

async function openDetail(row: DebateResultSummary): Promise<void> {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await api<RecommendationDetail>(`/api/debate/${row.id}`)
  } catch (err: unknown) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load recommendation'
    toast.add({ severity: 'error', summary: 'Detail Failed', detail: msg, life: 5000 })
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

function directionSeverity(dir: string): 'success' | 'danger' | 'warn' {
  if (dir === 'bullish') return 'success'
  if (dir === 'bearish') return 'danger'
  return 'warn'
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

onMounted(fetchHistory)
</script>

<template>
  <div class="history-page" data-testid="history-page">
    <div class="page-header">
      <h2 class="page-title">Recommendation History</h2>
      <div class="header-controls">
        <InputText
          v-model="tickerFilter"
          placeholder="Filter by ticker"
          class="ticker-filter"
          data-testid="history-ticker-filter"
          @keyup.enter="fetchHistory"
        />
        <Button
          label="Search"
          icon="pi pi-search"
          size="small"
          :loading="loading"
          @click="fetchHistory"
        />
      </div>
    </div>

    <DataTable
      :value="summaries"
      :loading="loading"
      :rows="50"
      :paginator="summaries.length > 50"
      :rowsPerPageOptions="[25, 50, 100]"
      sortField="created_at"
      :sortOrder="-1"
      dataKey="id"
      size="small"
      selectionMode="single"
      @rowSelect="(e: { data: DebateResultSummary }) => openDetail(e.data)"
      :rowHover="true"
      data-testid="history-table"
      class="history-table"
    >
      <template #empty>
        <div class="empty-state">No recommendations found.</div>
      </template>
      <Column field="ticker" header="Ticker" :sortable="true" style="min-width: 80px">
        <template #body="{ data }">
          <span class="mono ticker-cell">{{ (data as DebateResultSummary).ticker }}</span>
        </template>
      </Column>
      <Column field="direction" header="Direction" :sortable="true" style="min-width: 90px">
        <template #body="{ data }">
          <Tag
            :value="(data as DebateResultSummary).direction.toUpperCase()"
            :severity="directionSeverity((data as DebateResultSummary).direction)"
          />
        </template>
      </Column>
      <Column field="confidence" header="Confidence" :sortable="true" style="min-width: 90px">
        <template #body="{ data }">
          <span class="mono">{{ ((data as DebateResultSummary).confidence * 100).toFixed(0) }}%</span>
        </template>
      </Column>
      <Column field="model_name" header="Model" :sortable="true" style="min-width: 140px">
        <template #body="{ data }">
          <span class="mono model-cell">{{ (data as DebateResultSummary).model_name }}</span>
        </template>
      </Column>
      <Column field="duration_ms" header="Duration" :sortable="true" style="min-width: 80px">
        <template #body="{ data }">
          <span class="mono">{{ ((data as DebateResultSummary).duration_ms / 1000).toFixed(1) }}s</span>
        </template>
      </Column>
      <Column field="is_fallback" header="Status" :sortable="true" style="min-width: 80px">
        <template #body="{ data }">
          <Tag
            :value="(data as DebateResultSummary).is_fallback ? 'Fallback' : 'AI'"
            :severity="(data as DebateResultSummary).is_fallback ? 'warn' : 'success'"
          />
        </template>
      </Column>
      <Column field="created_at" header="Date" :sortable="true" style="min-width: 130px">
        <template #body="{ data }">
          <span class="mono">{{ formatTimestamp((data as DebateResultSummary).created_at) }}</span>
        </template>
      </Column>
    </DataTable>

    <!-- Detail Dialog -->
    <Dialog
      v-model:visible="detailVisible"
      :header="detail ? `${detail.ticker} — Recommendation` : 'Loading...'"
      :modal="true"
      :dismissableMask="true"
      :style="{ width: '90vw', maxWidth: '1000px' }"
      data-testid="history-detail-dialog"
    >
      <div v-if="detailLoading" class="detail-loading">
        <i class="pi pi-spinner pi-spin" style="font-size: 1.5rem" />
        <span>Loading recommendation...</span>
      </div>
      <template v-else-if="detail">
        <div class="detail-meta">
          <span class="mono">{{ detail.model_used }}</span>
          <span class="mono">{{ (detail.duration_ms / 1000).toFixed(1) }}s</span>
          <span class="mono">{{ detail.total_tokens.toLocaleString() }} tokens</span>
          <span class="mono">{{ formatTimestamp(detail.created_at) }}</span>
        </div>

        <div class="detail-grid">
          <DeskCard title="POSITION" :full-width="true">
            <PositionCard :recommendation="detail.recommendation" />
          </DeskCard>

          <DeskCard
            v-for="assessment in detail.assessments"
            :key="assessment.desk"
            :title="assessment.desk.toUpperCase()"
          >
            <DeskAssessmentCard :assessment="assessment" />
          </DeskCard>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.history-page {
  padding: 1.5rem 2rem;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}

.page-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--p-surface-100, #eee);
  margin: 0;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.ticker-filter {
  width: 140px;
  text-transform: uppercase;
}

.history-table {
  font-size: 0.85rem;
}

.ticker-cell {
  font-weight: 600;
  color: var(--p-surface-100, #eee);
}

.model-cell {
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: var(--p-surface-400, #888);
}

.detail-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--p-surface-400, #888);
}

.detail-meta {
  display: flex;
  gap: 1.5rem;
  padding: 0.5rem 0 1rem;
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
  border-bottom: 1px solid var(--p-surface-700, #333);
  margin-bottom: 1rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 1rem;
}

.mono {
  font-family: var(--font-mono);
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .detail-meta {
    flex-wrap: wrap;
    gap: 0.75rem;
  }
}
</style>
