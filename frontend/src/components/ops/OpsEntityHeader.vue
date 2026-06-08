<template>
  <header class="rounded-2xl border border-outline-variant/40 bg-surface-container/80 p-5 backdrop-blur-sm">
    <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div class="flex items-start gap-4">
        <div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/30 bg-primary/15">
          <span class="material-symbols-outlined text-[28px] text-primary">{{ icon || 'deployed_code' }}</span>
        </div>
        <div class="min-w-0 space-y-2">
          <h1 class="text-xl font-semibold text-on-surface lg:text-2xl">
            {{ title }}
          </h1>

          <div v-if="resolvedSubtitle" class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-on-surface-variant lg:text-sm">
            <span v-for="(part, index) in resolvedSubtitleParts" :key="`${part}-${index}`" :class="index === 0 ? 'font-mono' : ''">
              <span v-if="index > 0" class="mr-2 text-outline-variant">·</span>
              {{ part }}
            </span>
          </div>

          <div v-if="status || chips.length" class="flex flex-wrap items-center gap-2 pt-1">
            <span
              v-if="status"
              class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
              :class="statusClass"
            >
              <span class="size-1.5 rounded-full bg-current" />
              {{ statusLabel }}
            </span>
            <span
              v-for="chip in chips"
              :key="`${chip.icon || 'none'}-${chip.label}`"
              class="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-on-surface-variant"
            >
              <span v-if="chip.icon" class="material-symbols-outlined text-[14px] leading-none">{{ chip.icon }}</span>
              {{ chip.label }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { formatStatusLabel, getStatusBadgeClass } from '@/composables/useStatusFormatters'

type HeaderChip = {
  label: string
  icon?: string
}

const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string | null
    subtitleParts?: Array<string | null | undefined>
    icon?: string
    status?: string | null
    chips?: HeaderChip[]
  }>(),
  {
    subtitle: '',
    subtitleParts: () => [],
    icon: 'deployed_code',
    status: '',
    chips: () => [],
  },
)

const resolvedSubtitleParts = computed(() => {
  if (props.subtitleParts.length) {
    return props.subtitleParts
      .map((part) => (part || '').trim())
      .filter((part) => part.length > 0)
  }
  const fallback = (props.subtitle || '').trim()
  return fallback ? [fallback] : []
})

const resolvedSubtitle = computed(() => resolvedSubtitleParts.value.join(' · '))
const statusLabel = computed(() => formatStatusLabel(props.status))
const statusClass = computed(() => getStatusBadgeClass(props.status))
</script>
