<script setup lang="ts">
import { ref } from 'vue'
import Panel from 'primevue/panel'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'

const toast = useToast()

// Task states
const collectLoading = ref(false)
const collectResult = ref<string | null>(null)

const voteLoading = ref(false)
const voteResult = ref<string | null>(null)

const indicatorLoading = ref(false)
const indicatorResult = ref<string | null>(null)

const regimeLoading = ref(false)
const regimeResult = ref<string | null>(null)

async function collectOutcomes(): Promise<void> {
  collectLoading.value = true
  collectResult.value = null
  try {
    const res = await api<{ outcomes_collected: number }>('/api/analytics/collect-outcomes', {
      method: 'POST',
    })
    collectResult.value = `${res.outcomes_collected} outcome${res.outcomes_collected !== 1 ? 's' : ''} collected`
    toast.add({ severity: 'success', summary: 'Outcomes Collected', detail: collectResult.value, life: 5000 })
  } catch (err: unknown) {
    const msg = err instanceof ApiError ? err.message : 'Failed'
    collectResult.value = msg
    toast.add({ severity: 'error', summary: 'Collection Failed', detail: msg, life: 5000 })
  } finally {
    collectLoading.value = false
  }
}

async function tuneVoteWeights(): Promise<void> {
  voteLoading.value = true
  voteResult.value = null
  try {
    const res = await api<Array<{ agent_name: string; auto_weight: number }>>(
      '/api/analytics/weights/auto-tune',
      { method: 'POST', params: { window: 90 } },
    )
    if (res.length === 0) {
      voteResult.value = 'Not enough data (need 10+ outcomes per agent)'
    } else {
      voteResult.value = `${res.length} agent weights tuned`
    }
    toast.add({ severity: 'success', summary: 'Vote Weights Tuned', detail: voteResult.value, life: 5000 })
  } catch (err: unknown) {
    const msg = err instanceof ApiError ? err.message : 'Failed'
    voteResult.value = msg
    toast.add({ severity: 'error', summary: 'Tune Failed', detail: msg, life: 5000 })
  } finally {
    voteLoading.value = false
  }
}

async function tuneIndicatorWeights(): Promise<void> {
  indicatorLoading.value = true
  indicatorResult.value = null
  try {
    const res = await api<Array<{ indicator_name: string }>>(
      '/api/analytics/indicators/auto-tune',
      { method: 'POST', params: { window: 90 } },
    )
    if (res.length === 0) {
      indicatorResult.value = 'Not enough data (need 50+ signal-P&L pairs)'
    } else {
      indicatorResult.value = `${res.length} indicator weights tuned`
    }
    toast.add({ severity: 'success', summary: 'Indicator Weights Tuned', detail: indicatorResult.value, life: 5000 })
  } catch (err: unknown) {
    const msg = err instanceof ApiError ? err.message : 'Failed'
    indicatorResult.value = msg
    toast.add({ severity: 'error', summary: 'Tune Failed', detail: msg, life: 5000 })
  } finally {
    indicatorLoading.value = false
  }
}

interface RegimeTrainResult {
  status: string
  data_source: string
  sample_count: number
  classes: Record<string, number>
}

async function trainRegime(): Promise<void> {
  regimeLoading.value = true
  regimeResult.value = null
  try {
    const res = await api<RegimeTrainResult>(
      '/api/analytics/regime/train',
      { method: 'POST', timeout: 120_000 },
    )
    regimeResult.value = `${res.sample_count} samples (${res.data_source}), ${Object.keys(res.classes).length} classes`
    toast.add({ severity: 'success', summary: 'Regime Model Trained', detail: regimeResult.value, life: 5000 })
  } catch (err: unknown) {
    const msg = err instanceof ApiError ? err.message : 'Failed'
    regimeResult.value = msg
    toast.add({ severity: 'error', summary: 'Training Failed', detail: msg, life: 5000 })
  } finally {
    regimeLoading.value = false
  }
}

const anyLoading = ref(false)

async function runAll(): Promise<void> {
  anyLoading.value = true
  await collectOutcomes()
  await tuneVoteWeights()
  await tuneIndicatorWeights()
  await trainRegime()
  anyLoading.value = false
}
</script>

<template>
  <Panel
    header="Maintenance"
    :toggleable="true"
    :collapsed="false"
    data-testid="maintenance-panel"
  >
    <div class="maintenance-form">
      <p class="hint">
        Run these periodically to keep analytics accurate. Order matters: collect outcomes
        first, then tune weights.
      </p>

      <!-- Collect Outcomes -->
      <div class="task-row">
        <div class="task-info">
          <span class="task-name">Collect Outcomes</span>
          <span class="task-desc">Check what happened to past recommendations</span>
        </div>
        <div class="task-action">
          <Tag v-if="collectResult" :value="collectResult" :severity="collectResult?.startsWith('Failed') ? 'danger' : 'info'" />
          <Button
            label="Run"
            icon="pi pi-refresh"
            size="small"
            :loading="collectLoading"
            data-testid="btn-collect"
            @click="collectOutcomes"
          />
        </div>
      </div>

      <!-- Tune Vote Weights -->
      <div class="task-row">
        <div class="task-info">
          <span class="task-name">Tune Vote Weights</span>
          <span class="task-desc">Adjust agent influence from prediction accuracy (10+ outcomes/agent)</span>
        </div>
        <div class="task-action">
          <Tag v-if="voteResult" :value="voteResult" :severity="voteResult?.startsWith('Failed') ? 'danger' : 'info'" />
          <Button
            label="Run"
            icon="pi pi-sliders-h"
            size="small"
            :loading="voteLoading"
            data-testid="btn-tune-votes"
            @click="tuneVoteWeights"
          />
        </div>
      </div>

      <!-- Tune Indicator Weights -->
      <div class="task-row">
        <div class="task-info">
          <span class="task-name">Tune Indicator Weights</span>
          <span class="task-desc">Adjust indicator composite from P&L correlation (50+ pairs)</span>
        </div>
        <div class="task-action">
          <Tag v-if="indicatorResult" :value="indicatorResult" :severity="indicatorResult?.startsWith('Failed') ? 'danger' : 'info'" />
          <Button
            label="Run"
            icon="pi pi-chart-line"
            size="small"
            :loading="indicatorLoading"
            data-testid="btn-tune-indicators"
            @click="tuneIndicatorWeights"
          />
        </div>
      </div>

      <!-- Train Regime Classifier -->
      <div class="task-row">
        <div class="task-info">
          <span class="task-name">Train Regime Classifier</span>
          <span class="task-desc">Retrain GBM model from accumulated scan data (200+ scores)</span>
        </div>
        <div class="task-action">
          <Tag v-if="regimeResult" :value="regimeResult" :severity="regimeResult?.startsWith('Failed') ? 'danger' : 'info'" />
          <Button
            label="Run"
            icon="pi pi-cog"
            size="small"
            :loading="regimeLoading"
            data-testid="btn-train-regime"
            @click="trainRegime"
          />
        </div>
      </div>

      <!-- Run All -->
      <div class="run-all-row">
        <Button
          label="Run All"
          icon="pi pi-play"
          severity="info"
          :loading="anyLoading"
          data-testid="btn-run-all"
          @click="runAll"
        />
      </div>
    </div>
  </Panel>
</template>

<style scoped>
.maintenance-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.hint {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
  margin: 0;
}

.task-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.task-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--p-surface-100, #eee);
}

.task-desc {
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
}

.task-action {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.run-all-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.5rem;
  border-top: 1px solid var(--p-surface-700, #333);
}

@media (max-width: 640px) {
  .task-row {
    flex-direction: column;
    gap: 0.5rem;
    align-items: flex-start;
  }

  .task-action {
    align-self: flex-end;
  }
}
</style>
