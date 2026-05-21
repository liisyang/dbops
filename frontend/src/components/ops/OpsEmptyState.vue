<template>
  <div class="flex flex-col items-center justify-center px-6 py-10 text-center">
    <span
      class="material-symbols-outlined text-5xl text-on-surface-variant"
      :class="{ 'animate-spin': state === 'loading' }"
    >
      {{ resolvedIcon }}
    </span>
    <h3 class="mt-4 text-base font-semibold text-on-surface">
      {{ title }}
    </h3>
    <p v-if="description" class="mt-2 text-sm text-on-surface-variant">
      {{ description }}
    </p>
    <div v-if="$slots.actions" class="mt-4">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  state?: 'empty' | 'loading' | 'development' | 'error'
  icon?: string
  title: string
  description?: string
}>(), {
  state: 'empty',
})

const resolvedIcon = computed(() => {
  if (props.icon) return props.icon
  switch (props.state) {
    case 'loading':
      return 'progress_activity'
    case 'development':
      return 'construction'
    case 'error':
      return 'error'
    default:
      return 'inbox'
  }
})
</script>
