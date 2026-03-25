<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import ModelRoutingPanel from '@/components/ModelRoutingPanel.vue'
import MaintenancePanel from '@/components/MaintenancePanel.vue'
import { api, ApiError } from '@/composables/useApi'
import type { ConfigResponse, RoutingConfig } from '@/types'

const toast = useToast()
const loading = ref(true)
const config = ref<ConfigResponse | null>(null)
const routingConfig = ref<RoutingConfig | null>(null)

async function fetchConfig(): Promise<void> {
  loading.value = true
  try {
    config.value = await api<ConfigResponse>('/api/config')
    routingConfig.value = config.value.routing ?? null
  } catch (err: unknown) {
    const message = err instanceof ApiError ? err.message : 'Failed to load config'
    toast.add({ severity: 'error', summary: 'Config Load Failed', detail: message, life: 5000 })
  } finally {
    loading.value = false
  }
}

onMounted(fetchConfig)
</script>

<template>
  <div class="settings-page">
    <h2 class="page-title">Settings</h2>

    <!-- General config summary -->
    <div v-if="loading" class="loading-msg">Loading configuration...</div>

    <div v-else-if="config" class="config-sections">
      <div class="general-section">
        <h3 class="section-title">General</h3>
        <div class="config-grid">
          <div class="config-item">
            <span class="config-label">Provider</span>
            <span class="config-value">{{ config.provider }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">Groq API Key</span>
            <span :class="['config-value', config.groq_api_key_set ? 'status-ok' : 'status-missing']">
              {{ config.groq_api_key_set ? 'Configured' : 'Not Set' }}
            </span>
          </div>
          <div class="config-item">
            <span class="config-label">Anthropic API Key</span>
            <span :class="['config-value', config.anthropic_api_key_set ? 'status-ok' : 'status-missing']">
              {{ config.anthropic_api_key_set ? 'Configured' : 'Not Set' }}
            </span>
          </div>
          <div class="config-item">
            <span class="config-label">Agent Timeout</span>
            <span class="config-value mono">{{ config.agent_timeout }}s</span>
          </div>
          <div class="config-item">
            <span class="config-label">Scan Preset</span>
            <span class="config-value">{{ config.scan_preset_default }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">Protocol</span>
            <span class="config-value mono">{{ config.recommendation_protocol }}</span>
          </div>
        </div>
      </div>

      <!-- Maintenance Panel -->
      <MaintenancePanel />

      <!-- Model Routing Panel -->
      <ModelRoutingPanel
        :initialConfig="routingConfig"
        :provider="config.provider"
        @updated="fetchConfig"
      />
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  padding: 1.5rem 2rem;
  max-width: 900px;
}

.page-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--p-surface-100, #eee);
  margin: 0 0 1.5rem 0;
}

.loading-msg {
  color: var(--p-surface-400, #888);
  font-size: 0.9rem;
}

.config-sections {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.general-section {
  background: var(--p-surface-900, #111);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1.25rem;
}

.section-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--p-surface-200, #ccc);
  margin: 0 0 1rem 0;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.75rem;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.config-label {
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.config-value {
  font-size: 0.9rem;
  color: var(--p-surface-100, #eee);
}

.status-ok {
  color: var(--accent-green, #22c55e);
}

.status-missing {
  color: var(--p-surface-500, #666);
}

.mono {
  font-family: var(--font-mono);
}

@media (max-width: 640px) {
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
