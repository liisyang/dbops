<template>
  <div class="flex h-full flex-col">
    <div class="flex items-center justify-between gap-2 px-1 pb-2">
      <h3 class="text-sm font-semibold text-on-surface">会话</h3>
      <button
        type="button"
        class="ops-secondary-button inline-flex h-7 items-center gap-1 px-2 text-xs"
        :disabled="creating"
        @click="emit('create')"
      >
        <span class="material-symbols-outlined text-[16px]">add</span>
        新建
      </button>
    </div>

    <div class="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
      <div
        v-if="loading"
        class="flex items-center justify-center py-8 text-on-surface-variant"
      >
        <span class="material-symbols-outlined animate-spin text-xl">sync</span>
      </div>

      <div
        v-else-if="!sessions.length"
        class="rounded border border-dashed border-outline-variant/40 bg-surface-container/30 px-3 py-6 text-center text-xs text-on-surface-variant"
      >
        暂无会话<br>
        点击右上角"新建"开始对话
      </div>

      <ChatSessionItem
        v-for="s in sessions"
        :key="s.id"
        :session="s"
        :active="s.id === activeId"
        @select="emit('select', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * AI Copilot — 会话侧栏
 *
 * 列表 + 新建按钮；loading / empty 由父组件传入。
 */
import type { AiChatSession } from '@/types/ai'
import ChatSessionItem from './ChatSessionItem.vue'

defineProps<{
  sessions: AiChatSession[]
  activeId: number | null
  loading: boolean
  creating: boolean
}>()

const emit = defineEmits<{
  (e: 'create'): void
  (e: 'select', sessionId: number): void
}>()
</script>
