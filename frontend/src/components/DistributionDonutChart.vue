<template>
  <div class="space-y-5">
    <div class="relative mx-auto flex h-56 w-56 items-center justify-center">
      <svg viewBox="0 0 120 120" class="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r="36" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="18" />
        <circle
          v-for="segment in segments"
          :key="segment.label"
          cx="60"
          cy="60"
          r="36"
          fill="none"
          :stroke="segment.color"
          stroke-width="18"
          :stroke-dasharray="`${segment.length} ${circumference}`"
          :stroke-dashoffset="segment.offset"
          stroke-linecap="round"
        />
      </svg>

      <div class="absolute text-center">
        <div class="text-xs uppercase tracking-[0.18em] text-on-surface-variant">{{ centerLabel }}</div>
        <div class="mt-2 text-3xl font-semibold text-on-surface">{{ total }}</div>
      </div>
    </div>

    <div class="space-y-3">
      <div
        v-for="segment in normalizedItems"
        :key="segment.label"
        class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 text-sm"
      >
        <span class="h-3 w-3 rounded-full" :style="{ backgroundColor: segment.color }" />
        <div class="min-w-0">
          <div class="truncate text-on-surface">{{ segment.label }}</div>
          <div class="text-xs text-on-surface-variant">{{ segment.percentage }}%</div>
        </div>
        <div class="font-medium text-on-surface">{{ segment.value }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  items: Array<{ label: string; value: number }>
  centerLabel?: string
}>(), {
  centerLabel: '总计',
})

const palette = ['#4ade80', '#f87171', '#a78bfa', '#60a5fa', '#fbbf24', '#94a3b8']
const circumference = 2 * Math.PI * 36

const total = computed(() => props.items.reduce((sum, item) => sum + item.value, 0))

const normalizedItems = computed(() => {
  return props.items
    .slice(0, 5)
    .map((item, index) => ({
      ...item,
      color: palette[index % palette.length],
      percentage: total.value ? Math.round((item.value / total.value) * 100) : 0,
    }))
})

const segments = computed(() => {
  let cumulative = 0
  return normalizedItems.value.map((item) => {
    const ratio = total.value ? item.value / total.value : 0
    const length = ratio * circumference
    const offset = -cumulative
    cumulative += length
    return {
      ...item,
      length,
      offset,
    }
  })
})
</script>
