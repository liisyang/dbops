<template>
  <span :class="classes">
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  tone?: 'neutral' | 'primary' | 'success' | 'warning'
}>(), {
  tone: 'neutral',
})

const classes = computed(() => {
  const base = 'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium'
  const tones: Record<string, string> = {
    neutral: 'border-outline-variant/40 bg-surface-container text-slate-300',
    primary: 'border-primary/25 bg-primary/10 text-cyan-100',
    success: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200',
    warning: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  }
  return `${base} ${tones[props.tone]}`
})
</script>
