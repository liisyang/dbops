<template>
  <component
    :is="asCard ? 'section' : 'div'"
    :class="asCard ? 'rounded-lg bg-surface-container p-5' : ''"
  >
    <div v-if="title || subtitle" class="flex items-center justify-between gap-3">
      <div>
        <h2 v-if="title" class="text-sm font-medium text-on-surface">{{ title }}</h2>
        <p v-if="subtitle" class="mt-1 text-xs text-on-surface-variant">{{ subtitle }}</p>
      </div>
    </div>

    <div :class="title || subtitle ? 'mt-5 space-y-3' : 'space-y-3'">
      <div
        v-for="item in displayItems"
        :key="item.label"
        class="grid grid-cols-[minmax(0,160px)_1fr_auto] items-center gap-3"
      >
        <span class="truncate text-sm text-on-surface" :title="item.label">{{ item.label }}</span>
        <div class="h-2.5 overflow-hidden rounded-full bg-[#162127]">
          <div
            class="h-full rounded-full bg-[#9ecaff]"
            :style="{ width: `${maxValue ? (item.value / maxValue) * 100 : 0}%` }"
          />
        </div>
        <span class="min-w-[2rem] text-right text-sm font-medium text-on-surface">{{ item.value }}</span>
      </div>

      <p v-if="!displayItems.length" class="py-6 text-center text-sm text-on-surface-variant">暂无统计数据</p>
    </div>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  items: Array<{ label: string; value: number }>
  limit?: number
  asCard?: boolean
}>(), {
  asCard: true,
})

const displayItems = computed(() => {
  const limit = props.limit ?? 8
  return props.items.slice(0, limit)
})

const maxValue = computed(() => {
  return displayItems.value.reduce((current, item) => Math.max(current, item.value), 0)
})
</script>
