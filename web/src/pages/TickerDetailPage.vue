<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import DirectionBadge from '@/components/DirectionBadge.vue'
import ScoreHistoryChart from '@/components/ScoreHistoryChart.vue'
import { api } from '@/composables/useApi'
import type { HistoryPoint, DebateResultSummary } from '@/types'

const route = useRoute()
const router = useRouter()

const ticker = String(route.params.ticker).toUpperCase()
const history = ref<HistoryPoint[]>([])
const debates = ref<DebateResultSummary[]>([])
const loading = ref(true)

const latestPoint = ref<HistoryPoint | null>(null)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatConfidence(val: number): string {
  return `${(val * 100).toFixed(0)}%`
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const [historyData, debateData] = await Promise.all([
      api<HistoryPoint[]>(`/api/ticker/${ticker}/history`, { params: { limit: 20 } }),
      api<DebateResultSummary[]>('/api/debate', { params: { ticker, limit: 10 } }),
    ])
    history.value = historyData
    debates.value = debateData
    latestPoint.value = historyData.length > 0 ? historyData[historyData.length - 1] : null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadData()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <Button
        icon="pi pi-arrow-left"
        severity="secondary"
        size="small"
        text
        @click="router.back()"
      />
      <h1>{{ ticker }}</h1>
    </div>

    <div v-if="loading" class="loading-msg">Loading...</div>

    <template v-else>
      <!-- Latest Score Summary -->
      <section v-if="latestPoint" class="section" data-testid="ticker-latest-score">
        <div class="latest-summary">
          <span class="score-value mono">{{ latestPoint.composite_score.toFixed(1) }}</span>
          <DirectionBadge :direction="latestPoint.direction" />
          <span class="score-date">as of {{ formatDate(latestPoint.scan_date) }}</span>
        </div>
      </section>

      <!-- Score History Chart -->
      <section class="section">
        <h2>Score History</h2>
        <ScoreHistoryChart :history="history" />
      </section>

      <!-- Past Debates -->
      <section class="section">
        <h2>Past Debates</h2>
        <div v-if="debates.length === 0" class="muted">No debates for this ticker yet.</div>
        <div v-else class="debate-list" data-testid="ticker-debates">
          <div
            v-for="d in debates"
            :key="d.id"
            class="debate-row"
            @click="router.push(`/debate/${d.id}`)"
          >
            <DirectionBadge :direction="d.direction as 'bullish' | 'bearish' | 'neutral'" />
            <span class="mono debate-conf">{{ formatConfidence(d.confidence) }}</span>
            <span class="debate-model">{{ d.model_name }}</span>
            <span class="debate-date">{{ formatDate(d.created_at) }}</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.page-header h1 {
  margin: 0;
  font-family: var(--font-mono);
}

.section {
  margin-bottom: 2rem;
}

.section h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.latest-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.score-value {
  font-size: 2rem;
  font-weight: 700;
}

.score-date {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
}

.debate-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.debate-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: border-color 0.15s;
}

.debate-row:hover {
  border-color: var(--p-surface-500, #666);
}

.debate-conf {
  font-size: 0.875rem;
  color: var(--p-surface-300, #aaa);
}

.debate-model {
  font-size: 0.75rem;
  color: var(--p-surface-500, #666);
}

.debate-date {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--p-surface-500, #666);
}

.mono {
  font-family: var(--font-mono);
}

.muted {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
}

.loading-msg {
  color: var(--p-surface-400, #888);
  padding: 2rem 0;
}
</style>
