<template>
  <OpsModal
    :open="open"
    title="确认操作"
    :subtitle="subtitle"
    icon="warning"
    size="sm"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <p class="text-sm text-on-surface-variant">
        {{ message }}
      </p>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-3">
        <button
          type="button"
          class="ops-secondary-button"
          @click="$emit('close')"
        >
          取消
        </button>
        <button
          type="button"
          class="ops-danger-button"
          :disabled="isLoading"
          @click="$emit('confirm')"
        >
          <span class="material-symbols-outlined text-[18px]">{{ isLoading ? 'hourglass_empty' : 'check' }}</span>
          {{ confirmLabel || '确认' }}
        </button>
      </div>
    </template>
  </OpsModal>
</template>

<script setup lang="ts">
import { OpsModal } from '@/components/ops'

defineProps<{
  open: boolean
  subtitle?: string
  message: string
  confirmLabel?: string
  isLoading?: boolean
}>()

defineEmits<{
  close: []
  confirm: []
}>()
</script>
