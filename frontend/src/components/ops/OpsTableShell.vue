<template>
  <section class="overflow-hidden rounded-lg bg-surface-container">
    <div v-if="loading">
      <OpsEmptyState
        state="loading"
        :title="loadingTitle"
        :description="loadingDescription"
      />
    </div>

    <template v-else>
      <div v-if="empty">
        <OpsEmptyState
          :state="emptyState"
          :icon="emptyIcon"
          :title="emptyTitle"
          :description="emptyDescription"
        />
      </div>

      <div v-else>
        <div class="overflow-x-auto">
          <slot />
        </div>
      </div>
    </template>

    <div
      v-if="showPagination || showPageSizeSelector || $slots.pagination"
      class="flex flex-col gap-3 border-t border-white/10 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div class="flex flex-wrap items-center gap-3 text-sm text-on-surface-variant">
        <div v-if="showPagination">
          第 {{ currentPage }} / {{ totalPages }} 页，共 {{ totalItems }} 条
        </div>
        <label v-if="showPageSizeSelector" class="flex items-center gap-2">
          <span>每页</span>
          <select
            class="h-9 w-auto rounded-lg border border-outline-variant bg-surface px-3 pr-8 text-sm text-on-surface outline-none transition-colors hover:border-primary focus:border-primary"
            :style="pageSizeSelectStyle"
            :value="normalizedPageSizeValue"
            @change="handlePageSizeChange"
          >
            <option
              v-for="option in normalizedPageSizeOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
      </div>

      <div class="flex items-center justify-end gap-2">
        <slot name="pagination" />

        <template v-if="showPagination">
          <button
            type="button"
            class="h-9 rounded-lg border border-outline-variant px-3 text-sm text-on-surface transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="currentPage <= 1"
            @click="emit('update:currentPage', currentPage - 1)"
          >
            上一页
          </button>
          <button
            type="button"
            class="h-9 rounded-lg border border-outline-variant px-3 text-sm text-on-surface transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="currentPage >= totalPages"
            @click="emit('update:currentPage', currentPage + 1)"
          >
            下一页
          </button>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import OpsEmptyState from './OpsEmptyState.vue'

const props = withDefaults(defineProps<{
  loading?: boolean
  empty?: boolean
  loadingTitle?: string
  loadingDescription?: string
  emptyState?: 'empty' | 'development' | 'error'
  emptyIcon?: string
  emptyTitle?: string
  emptyDescription?: string
  totalItems?: number
  currentPage?: number
  pageSize?: number | 'all'
  pageSizeOptions?: Array<number | string>
}>(), {
  loading: false,
  empty: false,
  loadingTitle: '加载中',
  loadingDescription: '请稍候，页面内容正在加载。',
  emptyState: 'empty',
  emptyTitle: '暂无数据',
  emptyDescription: '当前条件下没有匹配结果。',
  totalItems: 0,
  currentPage: 1,
  pageSize: 30,
  pageSizeOptions: () => [30, 50, 100, 'all'],
})

const emit = defineEmits<{
  (event: 'update:currentPage', value: number): void
  (event: 'update:pageSize', value: number | 'all'): void
}>()

const effectivePageSize = computed(() => {
  return props.pageSize === 'all' ? Math.max(1, props.totalItems) : props.pageSize
})

const normalizedPageSizeValue = computed(() => String(props.pageSize))

const normalizedPageSizeOptions = computed(() => {
  return props.pageSizeOptions.map((option) => {
    if (option === 'all') {
      return { value: 'all', label: '全部' }
    }

    return { value: String(option), label: String(option) }
  })
})

const pageSizeSelectStyle = computed(() => {
  const longestOptionLabelLength = normalizedPageSizeOptions.value.reduce((max, option) => {
    return Math.max(max, option.label.length)
  }, 0)
  const selectedValueLength = normalizedPageSizeValue.value.length
  const widthInCh = Math.max(6, longestOptionLabelLength, selectedValueLength) + 2

  return {
    minWidth: `${widthInCh}ch`,
  }
})

const totalPages = computed(() => {
  return Math.max(1, Math.ceil(props.totalItems / effectivePageSize.value))
})

const showPagination = computed(() => {
  return !props.loading && !props.empty && props.pageSize !== 'all' && props.totalItems > effectivePageSize.value
})

const showPageSizeSelector = computed(() => {
  return !props.loading && !props.empty && props.totalItems > 0
})

function handlePageSizeChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('update:pageSize', value === 'all' ? 'all' : Number(value))
}
</script>
