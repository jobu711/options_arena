<script setup lang="ts">
import { computed } from 'vue'
import type { DeskAssessment } from '@/types/recommendation'
import DeskCard from '@/components/DeskCard.vue'
import DirectionBadge from '@/components/DirectionBadge.vue'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'

interface Props {
  assessment: DeskAssessment
}

const props = defineProps<Props>()

/** Desk name in uppercase for the card title. */
const deskTitle = computed(() => props.assessment.desk.toUpperCase())

/** Map desk names to accent color CSS variables. */
const DESK_COLORS: Record<string, string> = {
  trend: '#3b82f6',
  volatility: '#a855f7',
  flow: '#06b6d4',
  fundamental: '#f59e0b',
  risk: '#ef4444',
  contrarian: '#10b981',
}

/** Accent color for the left border based on desk name. */
const accentColor = computed(() => {
  const desk = props.assessment.desk.toLowerCase()
  return DESK_COLORS[desk] ?? '#6b7280'
})
</script>

<template>
  <DeskCard :title="deskTitle" data-testid="desk-assessment-card">
    <template #status>
      <DirectionBadge :direction="assessment.direction" />
      <ConfidenceBadge :value="assessment.confidence" />
    </template>

    <div class="desk-assessment" :style="{ '--desk-accent': accentColor }">
      <p class="desk-assessment__summary">{{ assessment.summary }}</p>

      <ul
        v-if="assessment.key_findings.length > 0"
        class="desk-assessment__findings"
      >
        <li
          v-for="(finding, idx) in assessment.key_findings"
          :key="`${assessment.desk}-finding-${idx}`"
          class="desk-assessment__finding"
        >
          {{ finding }}
        </li>
      </ul>
    </div>
  </DeskCard>
</template>

<style scoped>
.desk-assessment {
  border-left: 3px solid var(--desk-accent, #6b7280);
  padding-left: 0.75rem;
}

.desk-assessment__summary {
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--p-surface-200, #ccc);
  margin: 0 0 0.5rem 0;
}

.desk-assessment__findings {
  margin: 0;
  padding: 0 0 0 1.25rem;
  list-style: disc;
}

.desk-assessment__finding {
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--p-surface-300, #aaa);
  margin-bottom: 0.25rem;
}

.desk-assessment__finding:last-child {
  margin-bottom: 0;
}
</style>
