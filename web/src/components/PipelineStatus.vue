<script setup lang="ts">
import { computed } from 'vue'
import Tag from 'primevue/tag'
import type { PipelineStage } from '@/types/recommendation'

interface Props {
  stage: PipelineStage
}

const props = defineProps<Props>()

interface StageDisplay {
  icon: string
  label: string
  severity: 'secondary' | 'info' | 'warn' | 'success' | 'danger'
  spinning: boolean
}

const stageMap: Record<PipelineStage, StageDisplay> = {
  queued: { icon: 'pi pi-circle-fill', label: 'Queued', severity: 'secondary', spinning: false },
  scored: { icon: 'pi pi-circle-fill', label: 'Scored', severity: 'info', spinning: false },
  analyzing: { icon: 'pi pi-spinner', label: 'Analyzing...', severity: 'warn', spinning: true },
  ready: { icon: 'pi pi-check', label: 'Ready', severity: 'success', spinning: false },
  failed: { icon: 'pi pi-times', label: 'Failed', severity: 'danger', spinning: false },
}

const display = computed(() => stageMap[props.stage])
</script>

<template>
  <Tag
    :severity="display.severity"
    data-testid="pipeline-status"
  >
    <template #default>
      <i
        :class="[display.icon, { 'spin-icon': display.spinning }]"
        style="font-size: 0.65rem; margin-right: 0.35rem;"
      />
      <span class="pipeline-label">{{ display.label }}</span>
    </template>
  </Tag>
</template>

<style scoped>
.pipeline-label {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
