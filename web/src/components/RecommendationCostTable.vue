<script setup lang="ts">
import { ref } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Panel from 'primevue/panel'
import type { RecommendationCostDetail, DeskCostDetail } from '@/types'
import { formatDateTime } from '@/utils/formatters'

interface Props {
  costs: RecommendationCostDetail[]
  loading: boolean
}

defineProps<Props>()

const expandedRows = ref<Record<string, boolean>>({})

const tokenFormatter = new Intl.NumberFormat('en-US')

function formatTokens(tokens: number): string {
  return tokenFormatter.format(tokens)
}

function formatDuration(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`
}

function tierSeverity(tier: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' | 'contrast' | undefined {
  switch (tier.toUpperCase()) {
    case 'FAST':
      return 'success'
    case 'STANDARD':
      return 'info'
    case 'PREMIUM':
      return 'warn'
    default:
      return 'secondary'
  }
}

function statusSeverity(status: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' | 'contrast' | undefined {
  switch (status.toUpperCase()) {
    case 'SUCCESS':
      return 'success'
    case 'FALLBACK':
      return 'warn'
    default:
      return 'secondary'
  }
}

</script>

<template>
  <Panel
    header="Recommendation Costs"
    :toggleable="true"
    :collapsed="true"
    data-testid="recommendation-cost-panel"
  >
    <DataTable
      v-if="costs.length > 0"
      :value="costs"
      :loading="loading"
      dataKey="ticker"
      v-model:expandedRows="expandedRows"
      :rows="10"
      class="cost-table"
      data-testid="recommendation-cost-table"
    >
      <Column :expander="true" headerStyle="width: 3rem" />
      <Column field="ticker" header="Ticker">
        <template #body="{ data }: { data: RecommendationCostDetail }">
          <span class="mono ticker-cell">{{ data.ticker }}</span>
        </template>
      </Column>
      <Column field="created_at" header="Timestamp">
        <template #body="{ data }: { data: RecommendationCostDetail }">
          <span class="timestamp-cell">{{ formatDateTime(data.created_at) }}</span>
        </template>
      </Column>
      <Column field="total_tokens" header="Total Tokens">
        <template #body="{ data }: { data: RecommendationCostDetail }">
          <span class="mono">{{ formatTokens(data.total_tokens) }}</span>
        </template>
      </Column>
      <Column field="duration_ms" header="Duration">
        <template #body="{ data }: { data: RecommendationCostDetail }">
          <span class="mono">{{ formatDuration(data.duration_ms) }}</span>
        </template>
      </Column>
      <Column header="Status">
        <template #body="{ data }: { data: RecommendationCostDetail }">
          <Tag
            :value="data.is_fallback ? 'Fallback' : 'OK'"
            :severity="data.is_fallback ? 'warn' : 'success'"
          />
        </template>
      </Column>

      <!-- Row expansion: per-desk details -->
      <template #expansion="{ data }: { data: RecommendationCostDetail }">
        <div class="expansion-content">
          <h4 class="expansion-title">Desk Details</h4>
          <DataTable
            v-if="data.desk_details.length > 0"
            :value="data.desk_details"
            dataKey="desk"
            class="desk-detail-table"
          >
            <Column field="desk" header="Desk">
              <template #body="{ data: desk }: { data: DeskCostDetail }">
                <span class="desk-name">{{ desk.desk }}</span>
              </template>
            </Column>
            <Column field="tier" header="Tier">
              <template #body="{ data: desk }: { data: DeskCostDetail }">
                <Tag :value="desk.tier" :severity="tierSeverity(desk.tier)" />
              </template>
            </Column>
            <Column field="model_used" header="Model">
              <template #body="{ data: desk }: { data: DeskCostDetail }">
                <span class="mono model-cell">{{ desk.model_used || '--' }}</span>
              </template>
            </Column>
            <Column field="input_tokens" header="Input Tokens">
              <template #body="{ data: desk }: { data: DeskCostDetail }">
                <span class="mono">{{ formatTokens(desk.input_tokens) }}</span>
              </template>
            </Column>
            <Column field="output_tokens" header="Output Tokens">
              <template #body="{ data: desk }: { data: DeskCostDetail }">
                <span class="mono">{{ formatTokens(desk.output_tokens) }}</span>
              </template>
            </Column>
            <Column field="duration_ms" header="Duration">
              <template #body="{ data: desk }: { data: DeskCostDetail }">
                <span class="mono">{{ formatDuration(desk.duration_ms) }}</span>
              </template>
            </Column>
            <Column field="status" header="Status">
              <template #body="{ data: desk }: { data: DeskCostDetail }">
                <Tag :value="desk.status" :severity="statusSeverity(desk.status)" />
              </template>
            </Column>
          </DataTable>
          <p v-else class="no-desk-details">No desk details available.</p>
        </div>
      </template>

      <template #empty>
        <div class="empty-state" data-testid="cost-table-empty">
          <i class="pi pi-dollar empty-icon" />
          <p class="empty-text">No recommendations yet.</p>
        </div>
      </template>
    </DataTable>

    <div v-else-if="!loading" class="empty-state" data-testid="cost-table-empty">
      <i class="pi pi-dollar empty-icon" />
      <p class="empty-text">No recommendations yet.</p>
    </div>
  </Panel>
</template>

<style scoped>
.cost-table {
  font-size: 0.9rem;
}

.mono {
  font-family: var(--font-mono);
}

.ticker-cell {
  font-weight: 600;
}

.timestamp-cell {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.expansion-content {
  padding: 0.75rem 1rem;
}

.expansion-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--p-surface-300, #aaa);
  margin: 0 0 0.5rem 0;
}

.desk-detail-table {
  font-size: 0.85rem;
}

.desk-name {
  text-transform: capitalize;
  font-weight: 500;
}

.model-cell {
  font-size: 0.8rem;
  color: var(--p-surface-300, #aaa);
}

.no-desk-details {
  font-size: 0.8rem;
  color: var(--p-surface-500, #666);
  margin: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem 1rem;
  color: var(--p-surface-400, #888);
}

.empty-icon {
  font-size: 1.75rem;
  margin-bottom: 0.5rem;
  color: var(--p-surface-500, #666);
}

.empty-text {
  margin: 0;
  font-size: 0.875rem;
}
</style>
