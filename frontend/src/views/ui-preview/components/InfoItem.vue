<template>
  <div class="preview-info-item">
    <dl class="flex items-start justify-between gap-3">
      <dt class="min-w-0 text-xs font-medium tracking-wide text-slate-400">
        {{ label }}
      </dt>
      <dd
        class="min-w-0 text-right text-sm text-slate-100"
        :class="emphasis ? 'text-base font-semibold text-cyan-100' : 'font-medium'"
      >
        {{ displayValue }}
      </dd>
    </dl>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  value: string | number | null | undefined
  emphasis?: boolean
  emptyText?: string
}>(), {
  emphasis: false,
  emptyText: '未配置',
})

const displayValue = computed(() => {
  const value = props.value
  if (value === null || value === undefined || value === '') return props.emptyText
  return String(value)
})
</script>
