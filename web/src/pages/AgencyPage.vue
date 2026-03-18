<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Panel from 'primevue/panel'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'
import { useAgencyStore } from '@/stores/agency'
import { formatDateTime } from '@/utils/formatters'
import type { AgencyResponseData, DeskResponseSummary } from '@/api/agency'

const agencyStore = useAgencyStore()
const queryText = ref('')
const selectedDesk = ref<string | null>(null)
const messageContainer = ref<HTMLElement | null>(null)

const deskOptions = [
  { label: 'Auto-route', value: null },
  { label: 'Trend', value: 'trend' },
  { label: 'Volatility', value: 'volatility' },
  { label: 'Flow', value: 'flow' },
  { label: 'Fundamental', value: 'fundamental' },
  { label: 'Risk', value: 'risk' },
  { label: 'Contrarian', value: 'contrarian' },
]

const canSubmit = computed(() => queryText.value.trim().length > 0 && !agencyStore.loading)

/** Color accent per desk type. */
function deskColor(desk: string): string {
  const colors: Record<string, string> = {
    trend: 'var(--accent-green, #22c55e)',
    volatility: 'var(--accent-purple, #a855f7)',
    flow: 'var(--accent-blue, #3b82f6)',
    fundamental: '#f59e0b',
    risk: 'var(--accent-red, #ef4444)',
    contrarian: '#06b6d4',
    research: 'var(--p-surface-400, #888)',
  }
  return colors[desk.toLowerCase()] ?? 'var(--p-surface-400, #888)'
}

/** Capitalize desk name for display. */
function deskLabel(desk: string): string {
  return desk.charAt(0).toUpperCase() + desk.slice(1) + ' Desk'
}

/** Format confidence as percentage. */
function formatConfidence(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

/** Scroll message container to bottom after new messages. */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

async function handleSubmit(): Promise<void> {
  const text = queryText.value.trim()
  if (!text) return
  queryText.value = ''
  await agencyStore.submitQuery(text, selectedDesk.value)
  await scrollToBottom()
}

/** Load a past query into the conversation view. */
function loadFromHistory(response: AgencyResponseData): void {
  // Check if already in messages to avoid duplicates
  const exists = agencyStore.messages.some(
    (m) => m.role === 'assistant' && m.response?.query_id === response.query_id,
  )
  if (exists) return

  agencyStore.messages.push(
    {
      id: `user-hist-${response.query_id}`,
      role: 'user',
      content: response.query_text,
      response: null,
      timestamp: response.created_at,
    },
    {
      id: `assistant-hist-${response.query_id}`,
      role: 'assistant',
      content: response.synthesis,
      response,
      timestamp: response.created_at,
    },
  )
  void scrollToBottom()
}

onMounted(() => {
  void agencyStore.loadHistory()
})
</script>

<template>
  <div class="agency-layout">
    <!-- History Sidebar -->
    <aside class="history-sidebar">
      <div class="sidebar-header">
        <h3>History</h3>
      </div>
      <div
        v-if="agencyStore.history.length === 0"
        class="sidebar-empty"
      >
        No previous queries.
      </div>
      <div v-else class="history-list">
        <div
          v-for="item in agencyStore.history"
          :key="item.query_id"
          class="history-item"
          @click="loadFromHistory(item)"
        >
          <div class="history-query">{{ item.query_text }}</div>
          <div class="history-meta">
            <ConfidenceBadge :value="item.confidence" />
            <span class="history-date">{{ formatDateTime(item.created_at) }}</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Chat Area -->
    <div class="chat-area">
      <div class="chat-header">
        <h1>AI Agency</h1>
        <p class="chat-subtitle">
          Ask questions about options, volatility, risk, and market trends.
          Queries are routed to specialized desk agents.
        </p>
      </div>

      <!-- Message List -->
      <div
        ref="messageContainer"
        class="message-list"
        data-testid="agency-messages"
      >
        <!-- Empty State -->
        <div
          v-if="agencyStore.messages.length === 0 && !agencyStore.loading"
          class="empty-state"
        >
          <i class="pi pi-comments empty-icon" />
          <p class="empty-text">Ask your first question to get started.</p>
        </div>

        <!-- Messages -->
        <div
          v-for="msg in agencyStore.messages"
          :key="msg.id"
          class="message-row"
          :class="{ 'message-row--user': msg.role === 'user', 'message-row--assistant': msg.role === 'assistant' }"
        >
          <!-- User Message -->
          <div v-if="msg.role === 'user'" class="user-bubble" data-testid="agency-user-message">
            {{ msg.content }}
          </div>

          <!-- Assistant Response -->
          <div
            v-else-if="msg.response"
            class="assistant-response"
            data-testid="agency-response"
          >
            <!-- Synthesis -->
            <div class="response-synthesis">
              <div class="response-header">
                <span class="response-label">Agency Response</span>
                <ConfidenceBadge :value="msg.response.confidence" />
              </div>
              <p class="synthesis-text">{{ msg.response.synthesis }}</p>
            </div>

            <!-- Desk Responses -->
            <div
              v-for="desk in msg.response.desk_responses"
              :key="desk.desk"
              class="desk-card"
              :style="{ borderLeftColor: deskColor(desk.desk) }"
            >
              <div class="desk-header">
                <Tag
                  :value="deskLabel(desk.desk)"
                  :style="{ background: deskColor(desk.desk), color: '#fff' }"
                  data-testid="desk-badge"
                />
                <span class="desk-confidence mono">{{ formatConfidence(desk.confidence) }}</span>
              </div>
              <p class="desk-text">{{ desk.response }}</p>
              <div v-if="desk.tools_used.length > 0" class="desk-tools">
                <Tag
                  v-for="tool in desk.tools_used"
                  :key="tool"
                  :value="tool"
                  severity="secondary"
                  class="tool-tag"
                  data-testid="tool-badge"
                />
              </div>
            </div>

            <!-- Citations -->
            <Panel
              v-if="msg.response.citations.length > 0"
              header="Citations"
              :toggleable="true"
              :collapsed="true"
              class="citations-panel"
            >
              <div
                v-for="(cite, i) in msg.response.citations"
                :key="i"
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
            </Panel>
          </div>
        </div>

        <!-- Loading Spinner -->
        <div
          v-if="agencyStore.loading"
          class="loading-row"
          data-testid="agency-loading"
        >
          <ProgressSpinner
            style="width: 2rem; height: 2rem;"
            strokeWidth="4"
          />
          <span class="loading-text">Analyzing...</span>
        </div>
      </div>

      <!-- Error Message -->
      <Message
        v-if="agencyStore.error"
        severity="error"
        :closable="true"
        data-testid="agency-error"
        @close="agencyStore.error = null"
      >
        {{ agencyStore.error }}
      </Message>

      <!-- Input Area -->
      <form class="input-area" @submit.prevent="handleSubmit">
        <Select
          v-model="selectedDesk"
          :options="deskOptions"
          optionLabel="label"
          optionValue="value"
          placeholder="Auto-route"
          class="desk-select"
          data-testid="agency-desk-select"
        />
        <InputText
          v-model="queryText"
          placeholder="Ask about options, volatility, risk..."
          class="query-input"
          data-testid="agency-input"
          :disabled="agencyStore.loading"
          @keyup.enter="handleSubmit"
        />
        <Button
          icon="pi pi-send"
          severity="success"
          :disabled="!canSubmit"
          :loading="agencyStore.loading"
          data-testid="agency-submit"
          @click="handleSubmit"
        />
      </form>
    </div>
  </div>
</template>

<style scoped>
.agency-layout {
  display: flex;
  gap: 1rem;
  height: calc(100vh - 5rem);
  min-height: 400px;
}

/* History Sidebar */
.history-sidebar {
  width: 280px;
  flex-shrink: 0;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--p-surface-700, #333);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 0.9rem;
  color: var(--p-surface-300, #aaa);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.sidebar-empty {
  padding: 1.5rem 1rem;
  text-align: center;
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.history-item {
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  cursor: pointer;
  margin-bottom: 0.25rem;
  transition: background-color 0.15s;
}

.history-item:hover {
  background: var(--p-surface-700, #2a2a2a);
}

.history-query {
  font-size: 0.85rem;
  color: var(--p-surface-200, #ccc);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 0.25rem;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.history-date {
  font-size: 0.7rem;
  color: var(--p-surface-500, #666);
}

/* Chat Area */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  margin-bottom: 0.75rem;
}

.chat-header h1 {
  margin: 0 0 0.25rem 0;
}

.chat-subtitle {
  margin: 0;
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}

/* Message List */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.message-row {
  display: flex;
}

.message-row--user {
  justify-content: flex-end;
}

.message-row--assistant {
  justify-content: flex-start;
}

/* User Bubble */
.user-bubble {
  max-width: 70%;
  background: var(--accent-blue, #3b82f6);
  color: #fff;
  padding: 0.75rem 1rem;
  border-radius: 1rem 1rem 0.25rem 1rem;
  font-size: 0.9rem;
  word-break: break-word;
}

/* Assistant Response */
.assistant-response {
  max-width: 85%;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.response-synthesis {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.response-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.response-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
  font-weight: 600;
}

.synthesis-text {
  margin: 0;
  font-size: 0.9rem;
  color: var(--p-surface-200, #ccc);
  line-height: 1.6;
  white-space: pre-wrap;
}

/* Desk Card */
.desk-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-left: 4px solid;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}

.desk-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.desk-confidence {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.desk-text {
  margin: 0;
  font-size: 0.85rem;
  color: var(--p-surface-300, #aaa);
  line-height: 1.5;
  white-space: pre-wrap;
}

.desk-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.5rem;
}

.tool-tag {
  font-size: 0.7rem;
}

/* Citations Panel */
.citations-panel {
  font-size: 0.85rem;
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

/* Loading */
.loading-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
}

.loading-text {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}

/* Empty State */
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
  margin: 0;
  font-size: 0.9rem;
}

/* Input Area */
.input-area {
  display: flex;
  gap: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--p-surface-700, #333);
}

.desk-select {
  width: 160px;
  flex-shrink: 0;
}

.query-input {
  flex: 1;
}

.mono {
  font-family: var(--font-mono);
}

/* Responsive — stack sidebar below on narrow viewports */
@media (max-width: 768px) {
  .agency-layout {
    flex-direction: column;
    height: auto;
  }

  .history-sidebar {
    width: 100%;
    max-height: 200px;
  }

  .chat-area {
    min-height: 60vh;
  }

  .user-bubble {
    max-width: 85%;
  }

  .assistant-response {
    max-width: 100%;
  }

  .input-area {
    flex-wrap: wrap;
  }

  .desk-select {
    width: 100%;
  }
}
</style>
