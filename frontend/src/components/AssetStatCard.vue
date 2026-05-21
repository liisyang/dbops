<template>
  <article
    class="relative overflow-hidden rounded-lg border p-2.5"
    :class="toneClasses.card"
  >
    <div class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
    <div class="flex items-start justify-between gap-3">
      <div class="space-y-1">
        <p class="text-[11px] uppercase tracking-[0.18em] text-on-surface-variant">{{ label }}</p>
        <div class="text-[1.35rem] font-semibold leading-none tracking-tight text-on-surface">{{ value }}</div>
      </div>
      <div
        class="flex h-7 w-7 items-center justify-center rounded-lg text-[16px]"
        :class="toneClasses.iconWrap"
      >
        <span class="material-symbols-outlined">{{ icon }}</span>
      </div>
    </div>

    <div class="mt-2.5 border-t border-white/8 pt-2">
      <span
        v-if="hint"
        class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
        :class="toneClasses.hint"
      >
        {{ hint }}
      </span>
      <p v-else class="text-xs text-on-surface-variant">实时汇总当前全量服务器资产。</p>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  value: number | string
  hint?: string
  icon?: string
  tone?: 'primary' | 'success' | 'warning' | 'muted'
}>(), {
  icon: 'database',
  tone: 'primary',
})

const toneClasses = computed(() => {
  switch (props.tone) {
    case 'success':
      return {
        card: 'border-emerald-400/20 bg-surface-container',
        iconWrap: 'bg-emerald-400/10 text-emerald-200',
        hint: 'bg-emerald-400/12 text-emerald-200',
      }
    case 'warning':
      return {
        card: 'border-amber-300/20 bg-surface-container',
        iconWrap: 'bg-amber-300/10 text-amber-100',
        hint: 'bg-amber-300/12 text-amber-100',
      }
    case 'muted':
      return {
        card: 'border-slate-200/10 bg-surface-container',
        iconWrap: 'bg-white/5 text-slate-200',
        hint: 'bg-white/8 text-slate-200',
      }
    default:
      return {
        card: 'border-primary/20 bg-surface-container',
        iconWrap: 'bg-primary/10 text-[#d8e4ec]',
        hint: 'bg-primary/12 text-[#d8e4ec]',
      }
  }
})
</script>
