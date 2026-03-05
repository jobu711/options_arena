<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'

interface Props {
  phases: string[]
  currentPhase: string
  current: number
  total: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ cancel: [] }>()

const currentPhaseIndex = computed(() =>
  props.phases.indexOf(props.currentPhase),
)

const phaseProgress = computed(() => {
  if (props.total <= 0) return 0
  return Math.min(100, Math.round((props.current / props.total) * 100))
})

function phaseState(index: number): 'complete' | 'active' | 'pending' {
  if (index < currentPhaseIndex.value) return 'complete'
  if (index === currentPhaseIndex.value) return 'active'
  return 'pending'
}
</script>

<template>
  <div class="progress-tracker" data-testid="progress-tracker">
    <div class="phases">
      <div
        v-for="(phase, index) in phases"
        :key="phase"
        class="phase"
        :class="`phase--${phaseState(index)}`"
      >
        <div class="phase-indicator">
          <span v-if="phaseState(index) === 'complete'" class="pi pi-check" />
          <span v-else class="phase-number">{{ index + 1 }}</span>
        </div>
        <span class="phase-label">{{ phase }}</span>
      </div>
    </div>

    <div class="progress-bar-container">
      <div class="progress-bar" :style="{ width: `${phaseProgress}%` }" />
    </div>

    <div class="progress-info">
      <span class="progress-text mono">
        {{ currentPhase }}: {{ current }} / {{ total }}
      </span>
      <Button
        label="Cancel"
        icon="pi pi-times"
        severity="danger"
        size="small"
        outlined
        data-testid="cancel-scan-btn"
        @click="emit('cancel')"
      />
    </div>
  </div>
</template>

<style scoped>
.progress-tracker {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.phases {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.phase {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  flex: 1;
}

.phase-indicator {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 600;
  border: 2px solid var(--p-surface-500, #555);
  color: var(--p-surface-400, #888);
  background: var(--p-surface-800, #1a1a1a);
}

.phase--complete .phase-indicator {
  background: var(--accent-green);
  border-color: var(--accent-green);
  color: #fff;
}

.phase--active .phase-indicator {
  border-color: var(--accent-blue);
  color: var(--accent-blue);
  animation: pulse 1.5s infinite;
}

.phase-number {
  font-family: var(--font-mono);
}

.phase-label {
  font-size: 0.75rem;
  text-transform: capitalize;
  color: var(--p-surface-400, #888);
}

.phase--active .phase-label {
  color: var(--accent-blue);
  font-weight: 600;
}

.phase--complete .phase-label {
  color: var(--accent-green);
}

.progress-bar-container {
  height: 4px;
  background: var(--p-surface-700, #333);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 0.75rem;
}

.progress-bar {
  height: 100%;
  background: var(--accent-blue);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.progress-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.progress-text {
  font-size: 0.8rem;
  color: var(--p-surface-300, #aaa);
}

.mono {
  font-family: var(--font-mono);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
