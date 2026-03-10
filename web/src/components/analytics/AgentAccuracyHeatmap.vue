<script setup lang="ts">
import { computed } from 'vue'
import type { AgentAccuracyReport, AgentCalibrationData } from '@/types'

interface Props {
  accuracy: AgentAccuracyReport[]
  calibration: AgentCalibrationData | null
}

const props = defineProps<Props>()

/** Map agent names to themed colors. */
function agentColor(name: string): string {
  const colorMap: Record<string, string> = {
    bull: 'var(--accent-green)',
    trend: 'var(--accent-green)',
    bear: 'var(--accent-red)',
    risk: 'var(--accent-blue)',
    volatility: 'var(--accent-purple)',
    contrarian: 'var(--accent-yellow)',
    flow: '#06b6d4',
    fundamental: '#f97316',
  }
  return colorMap[name.toLowerCase()] ?? 'var(--p-surface-400, #888)'
}

/** Get a background color based on a 0-1 value (green is good, red is bad). */
function heatColor(value: number, invert = false): string {
  const v = invert ? 1 - value : value
  if (v >= 0.7) return 'rgba(34, 197, 94, 0.25)'
  if (v >= 0.5) return 'rgba(234, 179, 8, 0.2)'
  return 'rgba(239, 68, 68, 0.2)'
}

const sortedAccuracy = computed(() =>
  [...props.accuracy].sort((a, b) => b.direction_hit_rate - a.direction_hit_rate),
)
</script>

<template>
  <div class="heatmap-panel" data-testid="agent-accuracy-heatmap">
    <h3>Agent Accuracy</h3>

    <div v-if="accuracy.length === 0" class="panel-empty">No agent accuracy data available</div>

    <div v-else class="accuracy-grid">
      <!-- Header -->
      <div class="grid-header">Agent</div>
      <div class="grid-header">Hit Rate</div>
      <div class="grid-header">Confidence</div>
      <div class="grid-header">Brier</div>
      <div class="grid-header">Samples</div>

      <!-- Rows -->
      <template v-for="agent in sortedAccuracy" :key="agent.agent_name">
        <div class="grid-agent">
          <span class="agent-dot" :style="{ background: agentColor(agent.agent_name) }" />
          <span class="agent-name">{{ agent.agent_name }}</span>
        </div>
        <div
          class="grid-cell mono"
          :style="{ background: heatColor(agent.direction_hit_rate) }"
        >
          {{ (agent.direction_hit_rate * 100).toFixed(1) }}%
        </div>
        <div class="grid-cell mono">
          {{ (agent.mean_confidence * 100).toFixed(1) }}%
        </div>
        <div
          class="grid-cell mono"
          :style="{ background: heatColor(agent.brier_score, true) }"
        >
          {{ agent.brier_score.toFixed(3) }}
        </div>
        <div class="grid-cell mono">
          {{ agent.sample_size }}
        </div>
      </template>
    </div>

    <!-- Calibration section -->
    <template v-if="calibration && calibration.buckets.length > 0">
      <h4>Confidence Calibration</h4>
      <div class="calibration-grid">
        <div class="grid-header">Bucket</div>
        <div class="grid-header">Mean Conf.</div>
        <div class="grid-header">Actual Hit</div>
        <div class="grid-header">Gap</div>
        <div class="grid-header">Count</div>

        <template v-for="bucket in calibration.buckets" :key="bucket.bucket_label">
          <div class="grid-cell">{{ bucket.bucket_label }}</div>
          <div class="grid-cell mono">{{ (bucket.mean_confidence * 100).toFixed(1) }}%</div>
          <div class="grid-cell mono">{{ (bucket.actual_hit_rate * 100).toFixed(1) }}%</div>
          <div
            class="grid-cell mono"
            :class="Math.abs(bucket.actual_hit_rate - bucket.mean_confidence) > 0.15 ? 'val-red' : 'val-green'"
          >
            {{ ((bucket.actual_hit_rate - bucket.mean_confidence) * 100).toFixed(1) }}pp
          </div>
          <div class="grid-cell mono">{{ bucket.count }}</div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.heatmap-panel {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.heatmap-panel h3 {
  font-size: 0.95rem;
  margin: 0 0 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.heatmap-panel h4 {
  font-size: 0.85rem;
  margin: 1.25rem 0 0.5rem;
  color: var(--p-surface-300, #aaa);
}

.accuracy-grid,
.calibration-grid {
  display: grid;
  grid-template-columns: 1fr repeat(4, auto);
  gap: 1px;
  font-size: 0.85rem;
}

.calibration-grid {
  grid-template-columns: auto repeat(4, auto);
}

.grid-header {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-500, #666);
  padding: 0.25rem 0.75rem;
  border-bottom: 1px solid var(--p-surface-700, #333);
}

.grid-agent {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
}

.agent-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.agent-name {
  text-transform: capitalize;
  color: var(--p-surface-200, #ccc);
}

.grid-cell {
  padding: 0.4rem 0.75rem;
  text-align: right;
  color: var(--p-surface-200, #ccc);
  border-radius: 3px;
}

.mono {
  font-family: var(--font-mono);
}

.val-green {
  color: var(--accent-green);
}

.val-red {
  color: var(--accent-red);
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
