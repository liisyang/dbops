<template>
  <div
    class="flex flex-wrap gap-2"
    :class="props.compact ? 'items-center' : 'items-end'"
  >
      <!-- Search input with icon -->
      <div class="relative w-[260px] shrink-0">
        <span class="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-on-surface-variant/60">
          search
        </span>
        <input
          class="w-full rounded-lg border-0 bg-surface-container-low py-2.5 pl-9 pr-4 text-sm text-on-surface placeholder:text-on-surface-variant/50 outline-none transition-all focus:ring-1 focus:ring-primary/40"
          type="search"
          :value="props.keyword"
          placeholder="搜索"
          @input="emitKeyword"
          @keydown.enter="emit('search')"
        />
      </div>

      <!-- Select filters -->
      <select
        v-for="select in props.selects"
        :key="select.key"
        class="rounded-lg border-0 bg-surface-container-low py-2.5 pl-3 pr-8 text-sm text-on-surface outline-none appearance-none cursor-pointer transition-all focus:ring-1 focus:ring-primary/40 xl:w-[180px] xl:shrink-0"
        :value="select.value"
        @change="emitSelect(select.key, $event)"
      >
        <option
          v-for="option in select.options"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </option>
      </select>

      <!-- Actions slot + buttons -->
      <div class="flex items-center gap-2 ml-auto">
        <slot name="tools" />
        <button
          type="button"
          class="rounded-lg bg-surface-container-highest px-4 py-2.5 text-sm text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface focus:outline-none focus:ring-1 focus:ring-primary/40"
          @click="emit('search')"
        >
          查询
        </button>
        <button
          type="button"
          class="rounded-lg bg-surface-container-highest px-4 py-2.5 text-sm text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface focus:outline-none focus:ring-1 focus:ring-primary/40"
          @click="emit('reset')"
        >
          重置
        </button>
        <slot name="actions" />
      </div>
    </div>
</template>

<script setup lang="ts">
export interface OpsFilterSelectOption {
  label: string
  value: string
}

export interface OpsFilterSelect {
  key: string
  label: string
  value: string
  options: OpsFilterSelectOption[]
}

const props = withDefaults(defineProps<{
  keyword: string
  selects?: OpsFilterSelect[]
  compact?: boolean
  attached?: boolean
}>(), {
  selects: () => [],
  compact: false,
  attached: false,
})

const emit = defineEmits<{
  (event: 'update:keyword', value: string): void
  (event: 'update:select', payload: { key: string; value: string }): void
  (event: 'search'): void
  (event: 'reset'): void
}>()

function emitKeyword(event: Event) {
  emit('update:keyword', (event.target as HTMLInputElement).value)
}

function emitSelect(key: string, event: Event) {
  emit('update:select', { key, value: (event.target as HTMLSelectElement).value })
}
</script>
