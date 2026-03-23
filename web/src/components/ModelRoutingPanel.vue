<script setup lang="ts">
import { ref, watch } from 'vue'
import Panel from 'primevue/panel'
import ToggleSwitch from 'primevue/toggleswitch'
import Slider from 'primevue/slider'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'
import type { RoutingConfig } from '@/types'

interface Props {
  initialConfig: RoutingConfig | null
}

const props = defineProps<Props>()
const emit = defineEmits<{ updated: [] }>()
const toast = useToast()

// Local reactive form state
const enabled = ref(false)
const thresholdFast = ref(0.3)
const thresholdPremium = ref(0.7)
const fastModel = ref('')
const premiumModel = ref('')
const costEntries = ref<Array<{ model: string; cost: number }>>([])
const isOverride = ref(false)

const applyLoading = ref(false)
const resetLoading = ref(false)

// New cost entry form
const newModelName = ref('')

function syncFromConfig(config: RoutingConfig | null): void {
  if (!config) {
    enabled.value = false
    thresholdFast.value = 0.3
    thresholdPremium.value = 0.7
    fastModel.value = ''
    premiumModel.value = ''
    costEntries.value = []
    isOverride.value = false
    return
  }
  enabled.value = config.enable_model_routing
  thresholdFast.value = config.complexity_threshold_fast
  thresholdPremium.value = config.complexity_threshold_premium
  fastModel.value = config.fast_model
  premiumModel.value = config.premium_model
  costEntries.value = Object.entries(config.cost_per_million_tokens).map(
    ([model, cost]) => ({ model, cost }),
  )
  isOverride.value = config.is_override
}

// Initialize from prop
syncFromConfig(props.initialConfig)

// Re-sync when parent updates the prop
watch(
  () => props.initialConfig,
  (cfg) => syncFromConfig(cfg),
  { deep: true },
)

function addCostEntry(): void {
  const name = newModelName.value.trim()
  if (!name) return
  // Prevent duplicates
  if (costEntries.value.some((e) => e.model === name)) {
    toast.add({
      severity: 'warn',
      summary: 'Duplicate Model',
      detail: `"${name}" already exists in the cost map.`,
      life: 5000,
    })
    return
  }
  costEntries.value.push({ model: name, cost: 0 })
  newModelName.value = ''
}

function removeCostEntry(index: number): void {
  costEntries.value.splice(index, 1)
}

function buildPayload(): RoutingConfig {
  const costMap: Record<string, number> = {}
  for (const entry of costEntries.value) {
    if (entry.model.trim()) {
      costMap[entry.model.trim()] = entry.cost
    }
  }
  return {
    enable_model_routing: enabled.value,
    complexity_threshold_fast: thresholdFast.value,
    complexity_threshold_premium: thresholdPremium.value,
    fast_model: fastModel.value.trim(),
    premium_model: premiumModel.value.trim(),
    cost_per_million_tokens: costMap,
    is_override: true,
  }
}

function validate(): string | null {
  if (thresholdFast.value >= thresholdPremium.value) {
    return 'Fast threshold must be less than Premium threshold.'
  }
  for (const entry of costEntries.value) {
    if (entry.cost < 0) {
      return `Cost for "${entry.model}" must be non-negative.`
    }
  }
  return null
}

async function applyConfig(): Promise<void> {
  const error = validate()
  if (error) {
    toast.add({
      severity: 'error',
      summary: 'Validation Error',
      detail: error,
      life: 5000,
    })
    return
  }

  applyLoading.value = true
  try {
    await api<RoutingConfig>('/api/config/routing', {
      method: 'PUT',
      body: buildPayload(),
    })
    toast.add({
      severity: 'success',
      summary: 'Routing Config Updated',
      detail: 'Model routing configuration has been applied.',
      life: 5000,
    })
    emit('updated')
  } catch (err: unknown) {
    const message =
      err instanceof ApiError ? err.message : 'Failed to update routing config'
    toast.add({
      severity: 'error',
      summary: 'Update Failed',
      detail: message,
      life: 5000,
    })
  } finally {
    applyLoading.value = false
  }
}

async function resetConfig(): Promise<void> {
  resetLoading.value = true
  try {
    await api<RoutingConfig>('/api/config/routing', {
      method: 'DELETE',
    })
    toast.add({
      severity: 'success',
      summary: 'Routing Config Reset',
      detail: 'Model routing configuration has been reset to defaults.',
      life: 5000,
    })
    emit('updated')
  } catch (err: unknown) {
    const message =
      err instanceof ApiError ? err.message : 'Failed to reset routing config'
    toast.add({
      severity: 'error',
      summary: 'Reset Failed',
      detail: message,
      life: 5000,
    })
  } finally {
    resetLoading.value = false
  }
}
</script>

<template>
  <Panel
    header="Model Routing"
    :toggleable="true"
    :collapsed="true"
    data-testid="model-routing-panel"
  >
    <div class="routing-form">
      <!-- Enable/Disable Toggle -->
      <div class="form-row toggle-row">
        <label class="form-label" for="routing-toggle">Enable Model Routing</label>
        <ToggleSwitch
          v-model="enabled"
          inputId="routing-toggle"
          data-testid="routing-toggle"
        />
      </div>

      <!-- Threshold Sliders -->
      <div class="form-section">
        <h4 class="section-title">Complexity Thresholds</h4>
        <div class="slider-grid">
          <div class="slider-item">
            <label class="form-label">
              Fast Threshold: <span class="mono threshold-value">{{ thresholdFast.toFixed(2) }}</span>
            </label>
            <Slider
              v-model="thresholdFast"
              :min="0"
              :max="1"
              :step="0.05"
              data-testid="threshold-fast-slider"
            />
            <span class="slider-hint">Below this complexity score, use the fast (cheap) model</span>
          </div>
          <div class="slider-item">
            <label class="form-label">
              Premium Threshold: <span class="mono threshold-value">{{ thresholdPremium.toFixed(2) }}</span>
            </label>
            <Slider
              v-model="thresholdPremium"
              :min="0"
              :max="1"
              :step="0.05"
              data-testid="threshold-premium-slider"
            />
            <span class="slider-hint">Above this complexity score, use the premium model</span>
          </div>
        </div>
      </div>

      <!-- Model Names -->
      <div class="form-section">
        <h4 class="section-title">Model Names</h4>
        <div class="model-grid">
          <div class="form-field">
            <label class="form-label" for="fast-model">Fast Model</label>
            <InputText
              v-model="fastModel"
              inputId="fast-model"
              placeholder="e.g. llama-3.1-8b-instant"
              data-testid="fast-model-input"
              class="model-input"
            />
          </div>
          <div class="form-field">
            <label class="form-label" for="premium-model">Premium Model</label>
            <InputText
              v-model="premiumModel"
              inputId="premium-model"
              placeholder="e.g. llama-3.3-70b-versatile"
              data-testid="premium-model-input"
              class="model-input"
            />
          </div>
        </div>
      </div>

      <!-- Cost Map Editor -->
      <div class="form-section">
        <h4 class="section-title">Cost per Million Tokens</h4>
        <div class="cost-list">
          <div
            v-for="(entry, index) in costEntries"
            :key="entry.model"
            class="cost-entry"
          >
            <span class="cost-model-name mono">{{ entry.model }}</span>
            <InputNumber
              v-model="entry.cost"
              :min="0"
              :maxFractionDigits="4"
              placeholder="USD"
              size="small"
              class="cost-input"
              :data-testid="`cost-input-${index}`"
            />
            <Button
              icon="pi pi-trash"
              severity="danger"
              text
              size="small"
              :data-testid="`cost-remove-${index}`"
              @click="removeCostEntry(index)"
            />
          </div>
          <div v-if="costEntries.length === 0" class="cost-empty">
            No cost entries configured.
          </div>
        </div>
        <div class="cost-add-row">
          <InputText
            v-model="newModelName"
            placeholder="Model name"
            size="small"
            data-testid="cost-new-model-input"
            class="cost-new-input"
            @keyup.enter="addCostEntry()"
          />
          <Button
            label="Add Model"
            icon="pi pi-plus"
            severity="secondary"
            size="small"
            :disabled="!newModelName.trim()"
            data-testid="cost-add-btn"
            @click="addCostEntry()"
          />
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="action-row">
        <Button
          label="Apply"
          icon="pi pi-check"
          severity="success"
          :loading="applyLoading"
          data-testid="routing-apply-btn"
          @click="applyConfig()"
        />
        <Button
          label="Reset to Defaults"
          icon="pi pi-refresh"
          severity="secondary"
          :loading="resetLoading"
          data-testid="routing-reset-btn"
          @click="resetConfig()"
        />
        <span v-if="isOverride" class="override-badge">Custom Override Active</span>
      </div>
    </div>
  </Panel>
</template>

<style scoped>
.routing-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.toggle-row {
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--p-surface-700, #333);
}

.form-label {
  font-size: 0.85rem;
  color: var(--p-surface-300, #aaa);
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.section-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--p-surface-200, #ccc);
  margin: 0;
}

.slider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}

.slider-item {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.slider-hint {
  font-size: 0.7rem;
  color: var(--p-surface-500, #666);
}

.threshold-value {
  color: var(--accent-blue, #3b82f6);
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.model-input {
  width: 100%;
}

.cost-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.cost-entry {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.35rem 0.5rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
}

.cost-model-name {
  min-width: 180px;
  font-size: 0.85rem;
  color: var(--p-surface-200, #ccc);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cost-input {
  width: 120px;
}

.cost-empty {
  font-size: 0.8rem;
  color: var(--p-surface-500, #666);
  padding: 0.5rem 0;
}

.cost-add-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.cost-new-input {
  width: 200px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--p-surface-700, #333);
}

.override-badge {
  font-size: 0.75rem;
  color: var(--accent-yellow, #eab308);
  font-weight: 500;
  margin-left: auto;
}

.mono {
  font-family: var(--font-mono);
}

@media (max-width: 640px) {
  .slider-grid,
  .model-grid {
    grid-template-columns: 1fr;
  }

  .cost-model-name {
    min-width: 120px;
  }

  .cost-new-input {
    width: 140px;
  }
}
</style>
