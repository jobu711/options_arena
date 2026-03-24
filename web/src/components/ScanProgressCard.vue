<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import ProgressBar from 'primevue/progressbar'
import DeskCard from '@/components/DeskCard.vue'

interface Props {
  phase: string
  current: number
  total: number
  startedAt: Date
}

const props = defineProps<Props>()

const elapsedSeconds = ref(0)
let intervalId: ReturnType<typeof setInterval> | null = null

function updateElapsed(): void {
  elapsedSeconds.value = Math.floor((Date.now() - props.startedAt.getTime()) / 1000)
}

onMounted(() => {
  updateElapsed()
  intervalId = setInterval(updateElapsed, 1000)
})

onUnmounted(() => {
  if (intervalId !== null) {
    clearInterval(intervalId)
    intervalId = null
  }
})

const progressValue = computed(() => {
  if (props.total <= 0) return 0
  return Math.min(100, Math.round((props.current / props.total) * 100))
})

const elapsedDisplay = computed(() => {
  const secs = elapsedSeconds.value
  const minutes = Math.floor(secs / 60)
  const remainingSeconds = secs % 60
  const paddedSeconds = remainingSeconds.toString().padStart(2, '0')
  if (minutes > 0) {
    return `${minutes}m ${paddedSeconds}s`
  }
  return `${remainingSeconds}s`
})
</script>

<template>
  <DeskCard title="SCAN PROGRESS" data-testid="scan-progress-card">
    <div class="scan-progress">
      <div class="scan-progress__phase">{{ phase }}</div>
      <ProgressBar :value="progressValue" :showValue="true" class="scan-progress__bar" />
      <div class="scan-progress__footer">
        <span class="scan-progress__count">{{ current }} / {{ total }} tickers</span>
        <span class="scan-progress__elapsed">{{ elapsedDisplay }}</span>
      </div>
    </div>
  </DeskCard>
</template>

<style scoped>
.scan-progress {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.scan-progress__phase {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent-blue, #3b82f6);
  text-transform: capitalize;
}

.scan-progress__bar {
  height: 0.5rem;
}

.scan-progress__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.scan-progress__count {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--p-surface-300, #aaa);
}

.scan-progress__elapsed {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}
</style>
