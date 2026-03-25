<script setup lang="ts">
import { ref, onMounted } from 'vue'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Skeleton from 'primevue/skeleton'
import { useToast } from 'primevue/usetoast'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import { useAgencyStore } from '@/stores/agency'
import type { DeskType, DeskAgentResponse } from '@/types/agency'

const toast = useToast()
const store = useAgencyStore()

const queryText = ref('')
const selectedDesk = ref<DeskType | null>(null)
const tickerInput = ref('')

const deskOptions = [
  { label: 'Auto-route', value: null },
  { label: 'Trend', value: 'trend' as DeskType },
  { label: 'Volatility', value: 'volatility' as DeskType },
  { label: 'Flow', value: 'flow' as DeskType },
  { label: 'Fundamental', value: 'fundamental' as DeskType },
  { label: 'Risk', value: 'risk' as DeskType },
  { label: 'Contrarian', value: 'contrarian' as DeskType },
  { label: 'Research', value: 'research' as DeskType },
]

const DESK_COLORS: Record<string, string> = {
  trend: '#3b82f6',
  volatility: '#a855f7',
  flow: '#06b6d4',
  fundamental: '#f59e0b',
  risk: '#ef4444',
  contrarian: '#10b981',
  research: '#6366f1',
}

function deskColor(desk: string): string {
  return DESK_COLORS[desk] ?? '#888'
}

function parseTickers(): string[] | null {
  const raw = tickerInput.value.trim()
  if (!raw) return null
  return raw.split(/[,\s]+/).map((t) => t.toUpperCase()).filter(Boolean)
}

async function onSubmit(): Promise<void> {
  const q = queryText.value.trim()
  if (!q) return

  await store.submitQuery(q, selectedDesk.value, parseTickers())

  if (store.error) {
    toast.add({ severity: 'error', summary: 'Query failed', detail: store.error, life: 5000 })
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !store.loading) {
    event.preventDefault()
    onSubmit()
  }
}

function loadHistoryItem(queryId: string): void {
  store.selectFromHistory(queryId)
}

function formatResponse(text: string): string {
  // Preserve paragraph breaks in desk responses
  return text.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>')
}

function deskLabel(desk: DeskAgentResponse): string {
  return desk.desk.charAt(0).toUpperCase() + desk.desk.slice(1)
}

onMounted(() => {
  store.fetchHistory()
})
</script>

<template>
  <div class="desks-page">
    <!-- Query input section -->
    <section class="query-section">
      <h1 class="page-title">DESK AGENTS</h1>
      <p class="page-subtitle">
        Ask any question about a ticker or market condition. Queries are routed to the
        appropriate desk agent(s) automatically, or pick a specific desk.
      </p>

      <div class="query-form">
        <div class="query-row">
          <InputText
            v-model="queryText"
            placeholder="e.g. What's the risk profile for NVDA? or Is AAPL overbought?"
            class="query-input"
            :disabled="store.loading"
            @keydown="onKeydown"
            data-testid="desk-query-input"
          />
          <Button
            label="Ask"
            :loading="store.loading"
            :disabled="!queryText.trim() || store.loading"
            @click="onSubmit"
            data-testid="desk-submit-btn"
          />
        </div>
        <div class="query-options">
          <Select
            v-model="selectedDesk"
            :options="deskOptions"
            optionLabel="label"
            optionValue="value"
            placeholder="Auto-route"
            class="desk-select"
            data-testid="desk-selector"
          />
          <InputText
            v-model="tickerInput"
            placeholder="Tickers (optional, e.g. AAPL, MSFT)"
            class="ticker-input"
            :disabled="store.loading"
          />
        </div>
      </div>
    </section>

    <!-- Loading state -->
    <section v-if="store.loading" class="loading-section">
      <div class="loading-card">
        <Skeleton width="100%" height="1.5rem" class="loading-skeleton" />
        <Skeleton width="80%" height="1rem" class="loading-skeleton" />
        <Skeleton width="60%" height="1rem" class="loading-skeleton" />
        <p class="loading-text">Querying desk agents...</p>
      </div>
    </section>

    <!-- Response section -->
    <section v-if="store.currentResponse && !store.loading" class="response-section">
      <!-- Synthesis (main answer) -->
      <div class="synthesis-card">
        <div class="synthesis-header">
          <h2 class="synthesis-title">SYNTHESIS</h2>
          <ConfidenceBadge :value="store.currentResponse.confidence" />
        </div>
        <div class="synthesis-meta">
          <Tag
            v-for="desk in store.currentResponse.intent.desks"
            :key="desk"
            :value="desk"
            :style="{ background: deskColor(desk), color: '#fff' }"
            class="desk-tag"
          />
          <span
            v-if="store.currentResponse.intent.tickers.length"
            class="tickers-label"
          >
            {{ store.currentResponse.intent.tickers.join(', ') }}
          </span>
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="synthesis-body" v-html="formatResponse(store.currentResponse.synthesis)" />
      </div>

      <!-- Individual desk responses -->
      <div class="desk-grid">
        <div
          v-for="desk in store.currentResponse.desk_responses"
          :key="desk.desk"
          class="desk-response-card"
          :style="{ borderLeftColor: deskColor(desk.desk) }"
        >
          <div class="desk-header">
            <span class="desk-name">{{ deskLabel(desk) }}</span>
            <ConfidenceBadge :value="desk.confidence" />
          </div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="desk-body" v-html="formatResponse(desk.response)" />
          <div v-if="desk.tools_used.length" class="desk-tools">
            <Tag
              v-for="tool in desk.tools_used"
              :key="tool"
              :value="tool"
              severity="secondary"
              class="tool-tag"
            />
          </div>
        </div>
      </div>

      <!-- Citations -->
      <div v-if="store.currentResponse.citations.length" class="citations-card">
        <h3 class="citations-title">CITATIONS</h3>
        <div
          v-for="(cite, i) in store.currentResponse.citations"
          :key="i"
          class="citation-row"
        >
          <Tag :value="cite.desk" :style="{ background: deskColor(cite.desk), color: '#fff' }" />
          <span class="citation-source">{{ cite.source }}</span>
          <span class="citation-content">{{ cite.content }}</span>
        </div>
      </div>
    </section>

    <!-- Query history sidebar -->
    <aside v-if="store.history.length" class="history-aside">
      <h3 class="history-title">RECENT QUERIES</h3>
      <div
        v-for="item in store.history.slice(0, 10)"
        :key="item.query_id"
        class="history-item"
        :class="{ active: store.currentResponse?.query_id === item.query_id }"
        @click="loadHistoryItem(item.query_id)"
      >
        <span class="history-query">{{ item.query_text }}</span>
        <div class="history-meta">
          <Tag
            v-for="desk in item.intent.desks"
            :key="desk"
            :value="desk"
            :style="{ background: deskColor(desk), color: '#fff', fontSize: '0.65rem', padding: '0 0.3rem' }"
          />
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.desks-page {
  display: grid;
  grid-template-columns: 1fr 240px;
  grid-template-rows: auto 1fr;
  gap: 1rem;
  padding: 1rem;
  max-width: 1400px;
  margin: 0 auto;
}

.query-section {
  grid-column: 1 / -1;
}

.page-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--p-surface-100, #eee);
  margin: 0 0 0.25rem;
}

.page-subtitle {
  color: var(--p-surface-400, #999);
  font-size: 0.8rem;
  margin: 0 0 0.75rem;
}

.query-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.query-row {
  display: flex;
  gap: 0.5rem;
}

.query-input {
  flex: 1;
  font-size: 0.85rem;
}

.query-options {
  display: flex;
  gap: 0.5rem;
}

.desk-select {
  width: 160px;
  font-size: 0.8rem;
}

.ticker-input {
  width: 260px;
  font-size: 0.8rem;
}

/* Loading */
.loading-section {
  grid-column: 1 / 2;
}

.loading-card {
  background: var(--p-surface-900, #171717);
  border: 1px solid var(--p-surface-800, #262626);
  border-radius: 0.5rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.loading-skeleton {
  border-radius: 0.25rem;
}

.loading-text {
  color: var(--p-surface-400, #999);
  font-size: 0.8rem;
  margin: 0;
  font-style: italic;
}

/* Response */
.response-section {
  grid-column: 1 / 2;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.synthesis-card {
  background: var(--p-surface-900, #171717);
  border: 1px solid var(--p-surface-800, #262626);
  border-radius: 0.5rem;
  padding: 1rem;
}

.synthesis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.synthesis-title {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--p-surface-100, #eee);
  margin: 0;
}

.synthesis-meta {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.75rem;
}

.desk-tag {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tickers-label {
  font-family: var(--font-mono);
  color: var(--accent-green);
  font-size: 0.8rem;
  font-weight: 600;
}

.synthesis-body {
  color: var(--p-surface-200, #ddd);
  font-size: 0.85rem;
  line-height: 1.6;
}

/* Desk grid */
.desk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 0.75rem;
}

.desk-response-card {
  background: var(--p-surface-900, #171717);
  border: 1px solid var(--p-surface-800, #262626);
  border-left: 3px solid;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.desk-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.desk-name {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--p-surface-100, #eee);
}

.desk-body {
  color: var(--p-surface-300, #ccc);
  font-size: 0.8rem;
  line-height: 1.5;
  max-height: 300px;
  overflow-y: auto;
}

.desk-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--p-surface-800, #262626);
}

.tool-tag {
  font-size: 0.6rem;
  font-family: var(--font-mono);
}

/* Citations */
.citations-card {
  background: var(--p-surface-900, #171717);
  border: 1px solid var(--p-surface-800, #262626);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.citations-title {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--p-surface-100, #eee);
  margin: 0 0 0.5rem;
}

.citation-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0;
  font-size: 0.75rem;
  border-bottom: 1px solid var(--p-surface-800, #262626);
}

.citation-row:last-child {
  border-bottom: none;
}

.citation-source {
  font-family: var(--font-mono);
  color: var(--p-surface-400, #999);
  flex-shrink: 0;
}

.citation-content {
  color: var(--p-surface-300, #ccc);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* History sidebar */
.history-aside {
  grid-column: 2 / 3;
  grid-row: 2 / 3;
  align-self: start;
  position: sticky;
  top: 1rem;
}

.history-title {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--p-surface-400, #999);
  margin: 0 0 0.5rem;
}

.history-item {
  padding: 0.5rem;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 0.25rem;
}

.history-item:hover {
  background: var(--p-surface-800, #262626);
}

.history-item.active {
  background: var(--p-surface-800, #262626);
  border-left: 2px solid var(--accent-green);
}

.history-query {
  display: block;
  font-size: 0.75rem;
  color: var(--p-surface-200, #ddd);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 0.25rem;
}

.history-meta {
  display: flex;
  gap: 0.2rem;
  flex-wrap: wrap;
}

/* Responsive: stack on narrow screens */
@media (max-width: 800px) {
  .desks-page {
    grid-template-columns: 1fr;
  }

  .history-aside {
    grid-column: 1;
    grid-row: auto;
    position: static;
  }

  .desk-grid {
    grid-template-columns: 1fr;
  }
}
</style>
