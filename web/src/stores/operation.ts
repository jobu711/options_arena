import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type OperationType = 'scan' | 'batch_debate' | null

export const useOperationStore = defineStore('operation', () => {
  const operationType = ref<OperationType>(null)

  const inProgress = computed(() => operationType.value !== null)

  function start(type: 'scan' | 'batch_debate'): void {
    operationType.value = type
  }

  function finish(): void {
    operationType.value = null
  }

  return { operationType, inProgress, start, finish }
})
