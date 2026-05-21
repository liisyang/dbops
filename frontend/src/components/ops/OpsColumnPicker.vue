<template>
  <div class="relative" ref="rootRef">
    <button
      type="button"
      class="flex items-center justify-center rounded-lg bg-surface-container-highest px-4 py-2.5 text-sm text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface focus:outline-none focus:ring-1 focus:ring-primary/40"
      title="欄位顯示設定"
      @click="open = !open"
    >
      <span class="material-symbols-outlined text-[18px] leading-none">settings</span>
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 scale-95 -translate-y-1"
      enter-to-class="opacity-100 scale-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 scale-100 translate-y-0"
      leave-to-class="opacity-0 scale-95 -translate-y-1"
    >
      <div
        v-if="open"
        class="absolute right-0 top-full z-50 mt-1.5 min-w-[200px] rounded-lg bg-surface-container-high py-1.5 shadow-lg ring-1 ring-white/10"
      >
        <div class="px-3 pb-1.5 pt-1 text-[10px] uppercase tracking-widest text-on-surface-variant">
          顯示欄位 · 拖拽排序
        </div>

        <div
          v-for="col in columns"
          :key="col.key"
          draggable="true"
          class="group flex cursor-grab items-center gap-2 px-2 py-1.5 text-sm text-on-surface transition-colors active:cursor-grabbing"
          :class="[
            dragOverKey === col.key ? 'bg-primary/15 ring-1 ring-primary/40' : 'hover:bg-white/5',
            dragKey === col.key ? 'opacity-40' : '',
          ]"
          @dragstart="onDragStart(col.key, $event)"
          @dragover.prevent="onDragOver(col.key)"
          @dragleave="onDragLeave"
          @drop.prevent="onDrop(col.key)"
          @dragend="onDragEnd"
        >
          <!-- drag handle -->
          <span
            class="material-symbols-outlined shrink-0 text-on-surface-variant/50 group-hover:text-on-surface-variant"
            style="font-size:16px"
          >drag_indicator</span>

          <!-- checkbox -->
          <input
            type="checkbox"
            class="h-3.5 w-3.5 shrink-0 cursor-pointer rounded accent-primary"
            :checked="isVisible(col.key)"
            @change="emit('toggle', col.key)"
            @click.stop
          />

          <!-- label -->
          <span class="flex-1 select-none">{{ col.label }}</span>
        </div>

        <div class="mt-1 border-t border-white/8 px-3 pb-1 pt-1.5">
          <button
            type="button"
            class="text-[11px] text-on-surface-variant transition-colors hover:text-on-surface"
            @click="reset"
          >
            重置默認
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { ColumnDef } from '@/composables/useColumnVisibility'

defineProps<{
  columns: ColumnDef[]
  isVisible: (key: string) => boolean
}>()

const emit = defineEmits<{
  toggle: [key: string]
  reorder: [fromKey: string, toKey: string]
  reset: []
}>()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const dragKey = ref<string | null>(null)
const dragOverKey = ref<string | null>(null)

function onDragStart(key: string, e: DragEvent) {
  dragKey.value = key
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', key)
  }
}

function onDragOver(key: string) {
  if (dragKey.value && key !== dragKey.value) {
    dragOverKey.value = key
  }
}

function onDragLeave() {
  dragOverKey.value = null
}

function onDrop(toKey: string) {
  if (dragKey.value && dragKey.value !== toKey) {
    emit('reorder', dragKey.value, toKey)
  }
  dragKey.value = null
  dragOverKey.value = null
}

function onDragEnd() {
  dragKey.value = null
  dragOverKey.value = null
}

function reset() {
  emit('reset')
  open.value = false
}

function onClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))
</script>
