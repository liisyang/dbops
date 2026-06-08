<template>
  <section :class="['preview-metric-card', muted ? 'preview-muted-card' : '']">
    <div class="flex items-start gap-3">
      <span class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10">
        <span class="material-symbols-outlined text-[20px] text-primary">{{ icon }}</span>
      </span>
      <div class="min-w-0 flex-1">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-sm font-medium text-slate-100">{{ title }}</div>
            <div class="mt-1 text-xs text-slate-400">{{ hint }}</div>
          </div>
          <div class="shrink-0 text-lg font-semibold text-cyan-100">{{ value }}</div>
        </div>

        <div v-if="typeof percent === 'number'" class="mt-3">
          <div class="h-2 rounded-full bg-surface-container-low">
            <div
              class="h-2 rounded-full"
              :class="barClass"
              :style="{ width: `${percent}%` }"
            />
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  hint: string
  value: string
  icon: string
  percent?: number
  muted?: boolean
  barClass?: string
}>(), {
  muted: false,
  barClass: 'bg-gradient-to-r from-[#4d96ff] to-[#67c3ff]',
})
</script>
