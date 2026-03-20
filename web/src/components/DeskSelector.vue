<script setup lang="ts">
import { ref, computed } from 'vue'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import { submitAgencyQuery } from '@/api/agency'
import { ApiError } from '@/composables/useApi'
import type { AgencyResponseData, DeskResponseSummary } from '@/api/agency'

interface DeskInfo {
  name: string
  description: string
  tools: number
  color: string
}

const DESK_INFO: Record<string, DeskInfo> = {
  trend: {
    name: 'Trend',
    description: 'Price momentum & directional analysis',
    tools: 3,
    color: 'var(--accent-green, #22c55e)',
  },
  volatility: {
    name: 'Volatility',
    description: 'IV surface & term structure analysis',
    tools: 3,
    color: 'var(--accent-purple, #a855f7)',
  },
  flow: {
    name: 'Flow',
    description: 'Options flow & unusual activity',
    tools: 3,
    color: 'var(--accent-blue, #3b82f6)',
  },
  fundamental: {
    name: 'Fundamental',
    description: 'Earnings, valuation & sector analysis',
    tools: 3,
    color: '#f59e0b',
  },
  risk: {
    name: 'Risk',
    description: 'Portfolio risk & hedging assessment',
    tools: 3,
    color: 'var(--accent-red, #ef4444)',
  },
  contrarian: {
    name: 'Contrarian',
    description: 'Challenges consensus, finds blind spots',
    tools: 2,
    color: '#06b6d4',
  },
  research: {
    name: 'Research',
    description: 'Cross-domain synthesis & overview',
    tools: 6,
    color: 'var(--p-surface-400, #888)',
  },
}

type ViewState = 'cards' | 'query' | 'response'

const viewState = ref<ViewState>('cards')
const selectedDesk = ref<string | null>(null)
const ticker = ref('')
const queryText = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const response = ref<AgencyResponseData | null>(null)

const deskKeys = Object.keys(DESK_INFO)

const selectedDeskInfo = computed<DeskInfo | null>(() =>
  selectedDesk.value ? DESK_INFO[selectedDesk.value] ?? null : null,
)

const canSubmit = computed(() => {
  const t = ticker.value.trim()
  const q = queryText.value.trim()
  return t.length > 0 && q.length > 0 && !loading.value
})

function selectDesk(key: string): void {
  selectedDesk.value = key
  error.value = null
  viewState.value = 'query'
}

function goBack(): void {
  if (viewState.value === 'response') {
    viewState.value = 'query'
  } else {
    viewState.value = 'cards'
    selectedDesk.value = null
    ticker.value = ''
    queryText.value = ''
    error.value = null
  }
}

function startOver(): void {
  viewState.value = 'cards'
  selectedDesk.value = null
  ticker.value = ''
  queryText.value = ''
  error.value = null
  response.value = null
}

async function handleSubmit(): Promise<void> {
  const t = ticker.value.trim().toUpperCase()
  const q = queryText.value.trim()
  if (!t || !q || !selectedDesk.value) return

  ticker.value = t
  loading.value = true
  error.value = null

  try {
    const result = await submitAgencyQuery({
      query: q,
      desk: selectedDesk.value,
      tickers: [t],
    })
    response.value = result
    viewState.value = 'response'
  } catch (e: unknown) {
    if (e instanceof ApiError && e.status === 409) {
      error.value = 'Analysis in progress. Please wait for the current operation to complete.'
    } else {
      error.value = e instanceof Error ? e.message : 'Failed to submit query'
    }
  } finally {
    loading.value = false
  }
}

function deskColor(desk: string): string {
  return DESK_INFO[desk.toLowerCase()]?.color ?? 'var(--p-surface-400, #888)'
}

function deskLabel(desk: string): string {
  return (DESK_INFO[desk.toLowerCase()]?.name ?? desk) + ' Desk'
}

function formatConfidence(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}
</script>

<template>
  <div class="desk-selector">
    <!-- Card View: Select a desk -->
    <div v-if="viewState === 'cards'" class="desk-grid" data-testid="desk-grid">
      <div
        v-for="key in deskKeys"
        :key="key"
        class="desk-card"
        :style="{ borderTopColor: DESK_INFO[key].color }"
        data-testid="desk-card"
        @click="selectDesk(key)"
      >
        <div class="desk-card-header">
          <span class="desk-card-name">{{ DESK_INFO[key].name }}</span>
          <Tag
            :value="`${DESK_INFO[key].tools} tools`"
            severity="secondary"
            class="desk-card-tools"
          />
        </div>
        <p class="desk-card-description">{{ DESK_INFO[key].description }}</p>
      </div>
    </div>

    <!-- Query View: Enter ticker and question -->
    <div v-if="viewState === 'query'" class="query-panel" data-testid="query-panel">
      <div class="query-header">
        <Button
          icon="pi pi-arrow-left"
          severity="secondary"
          text
          data-testid="back-button"
          @click="goBack"
        />
        <Tag
          v-if="selectedDeskInfo"
          :value="selectedDeskInfo.name + ' Desk'"
          :style="{ background: selectedDeskInfo.color, color: '#fff' }"
          class="query-desk-tag"
        />
      </div>

      <div class="query-form">
        <label class="query-label" for="ticker-input">Ticker</label>
        <InputText
          id="ticker-input"
          v-model="ticker"
          placeholder="e.g. AAPL"
          class="ticker-input"
          data-testid="ticker-input"
          :disabled="loading"
          @keyup.enter="handleSubmit"
        />

        <label class="query-label" for="query-input">Question</label>
        <Textarea
          id="query-input"
          v-model="queryText"
          placeholder="Ask a question about this ticker..."
          :rows="3"
          :autoResize="true"
          class="query-textarea"
          data-testid="query-input"
          :disabled="loading"
        />

        <Message
          v-if="error"
          severity="error"
          :closable="true"
          data-testid="error-message"
          @close="error = null"
        >
          {{ error }}
        </Message>

        <div class="query-actions">
          <Button
            label="Submit"
            icon="pi pi-send"
            severity="success"
            :disabled="!canSubmit"
            :loading="loading"
            data-testid="submit-button"
            @click="handleSubmit"
          />
        </div>
      </div>

      <div v-if="loading" class="loading-overlay" data-testid="loading-spinner">
        <ProgressSpinner
          style="width: 2.5rem; height: 2.5rem"
          strokeWidth="4"
        />
        <span class="loading-text">Analyzing {{ ticker.toUpperCase() }}...</span>
      </div>
    </div>

    <!-- Response View: Show desk results -->
    <div v-if="viewState === 'response' && response" class="response-panel" data-testid="response-panel">
      <div class="response-header">
        <Button
          icon="pi pi-arrow-left"
          severity="secondary"
          text
          data-testid="back-to-query"
          @click="goBack"
        />
        <span class="response-title">
          Results for <strong class="mono">{{ ticker }}</strong>
        </span>
        <ConfidenceBadge :value="response.confidence" />
      </div>

      <!-- Synthesis -->
      <div class="synthesis-card">
        <div class="synthesis-label">Synthesis</div>
        <p class="synthesis-text">{{ response.synthesis }}</p>
      </div>

      <!-- Desk Responses -->
      <div
        v-for="desk in response.desk_responses"
        :key="desk.desk"
        class="response-desk-card"
        :style="{ borderLeftColor: deskColor(desk.desk) }"
        data-testid="response-desk-card"
      >
        <div class="response-desk-header">
          <Tag
            :value="deskLabel(desk.desk)"
            :style="{ background: deskColor(desk.desk), color: '#fff' }"
          />
          <span class="desk-confidence mono">{{ formatConfidence(desk.confidence) }}</span>
        </div>
        <p class="response-desk-text">{{ desk.response }}</p>
        <div v-if="desk.tools_used.length > 0" class="response-desk-tools">
          <Tag
            v-for="tool in desk.tools_used"
            :key="tool"
            :value="tool"
            severity="secondary"
            class="tool-tag"
          />
        </div>
      </div>

      <!-- Citations -->
      <div v-if="response.citations.length > 0" class="citations-section">
        <div class="citations-header">Citations</div>
        <div
          v-for="(cite, i) in response.citations"
          :key="`${cite.desk}-${cite.source}-${i}`"
          class="citation-item"
        >
          <Tag
            :value="deskLabel(cite.desk)"
            :style="{ background: deskColor(cite.desk), color: '#fff' }"
            class="citation-desk"
          />
          <span class="citation-source mono">{{ cite.source }}</span>
          <span class="citation-content">{{ cite.content }}</span>
        </div>
      </div>

      <div class="response-actions">
        <Button
          label="New Query"
          icon="pi pi-refresh"
          severity="secondary"
          data-testid="new-query-button"
          @click="startOver"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Desk Grid */
.desk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
}

.desk-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-top: 4px solid;
  border-radius: 0.5rem;
  padding: 1rem 1.25rem;
  cursor: pointer;
  transition: background-color 0.15s, transform 0.1s;
}

.desk-card:hover {
  background: var(--p-surface-700, #2a2a2a);
  transform: translateY(-2px);
}

.desk-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.desk-card-name {
  font-weight: 600;
  font-size: 1rem;
  color: var(--p-surface-100, #eee);
}

.desk-card-tools {
  font-size: 0.7rem;
}

.desk-card-description {
  margin: 0;
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
  line-height: 1.4;
}

/* Query Panel */
.query-panel {
  max-width: 600px;
}

.query-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.query-desk-tag {
  font-size: 0.85rem;
}

.query-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.query-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--p-surface-300, #aaa);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ticker-input {
  max-width: 200px;
  text-transform: uppercase;
}

.query-textarea {
  width: 100%;
}

.query-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.loading-overlay {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1rem;
  padding: 0.75rem;
}

.loading-text {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}

/* Response Panel */
.response-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 800px;
}

.response-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.response-title {
  font-size: 1rem;
  color: var(--p-surface-200, #ccc);
}

.synthesis-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.synthesis-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.synthesis-text {
  margin: 0;
  font-size: 0.9rem;
  color: var(--p-surface-200, #ccc);
  line-height: 1.6;
  white-space: pre-wrap;
}

/* Desk Response Cards */
.response-desk-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-left: 4px solid;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.response-desk-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.desk-confidence {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.response-desk-text {
  margin: 0;
  font-size: 0.85rem;
  color: var(--p-surface-300, #aaa);
  line-height: 1.5;
  white-space: pre-wrap;
}

.response-desk-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.5rem;
}

.tool-tag {
  font-size: 0.7rem;
}

/* Citations */
.citations-section {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.citations-header {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.citation-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--p-surface-700, #333);
  flex-wrap: wrap;
}

.citation-item:last-child {
  border-bottom: none;
}

.citation-desk {
  flex-shrink: 0;
  font-size: 0.7rem;
}

.citation-source {
  font-size: 0.75rem;
  color: var(--accent-blue, #3b82f6);
  flex-shrink: 0;
}

.citation-content {
  font-size: 0.8rem;
  color: var(--p-surface-300, #aaa);
  word-break: break-word;
}

.response-actions {
  margin-top: 0.5rem;
}

.mono {
  font-family: var(--font-mono);
}

/* Responsive */
@media (max-width: 768px) {
  .desk-grid {
    grid-template-columns: 1fr;
  }

  .query-panel,
  .response-panel {
    max-width: 100%;
  }
}
</style>
