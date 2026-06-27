<template>
  <button
    type="button"
    :class="[
      'flex w-full flex-col gap-1 rounded-md border px-3 py-2 text-left transition',
      active
        ? 'border-sky-400/60 bg-sky-500/15 text-on-surface'
        : 'border-outline-variant/30 bg-surface-container/40 text-on-surface hover:bg-surface-container-high',
    ]"
    @click="emit('select', session.id)"
  >
    <div class="flex items-center justify-between gap-2">
      <span class="truncate text-sm font-medium">
        {{ session.title || '新会话' }}
      </span>
      <span class="shrink-0 text-[10px] font-mono text-on-surface-variant/70">
        #{{ session.id }}
      </span>
    </div>
    <div class="flex items-center justify-between gap-2 text-[11px] text-on-surface-variant">
      <span class="font-mono">{{ messageCountText }}</span>
      <span v-if="session.last_message_at" class="font-mono text-[10px]">
        {{ formatRelative(session.last_message_at) }}
      </span>
    </div>
  </button>
</template>

<script setup lang="ts">
/**
 * AI Copilot — 会话项（侧栏单条）
 *
 * 显示标题、消息数、最后活跃时间；active 高亮由父组件控制。
 */
import type { AiChatSession } from '@/types/ai'
import { computed } from 'vue'

const props = defineProps<{
  session: AiChatSession
  active: boolean
}>()

const emit = defineEmits<{
  (e: 'select', sessionId: number): void
}>()

const messageCountText = computed(() => {
  const n = props.session.message_count
  if (n === 0) return '暂无消息'
  if (n === 1) return '1 条消息'
  return `${n} 条消息`
})

/**
 * 相对时间（极简）：> 1d 显示日期，< 1d 显示 HH:mm。
 * 避免引入 dayjs；如需精度后续替换。
 */
function formatRelative(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const now = Date.now()
  const diffMs = now - date.getTime()
  const oneDay = 86_400_000
  if (diffMs < oneDay) {
    return date.toTimeString().slice(0, 5)
  }
  if (diffMs < 7 * oneDay) {
    return `${Math.floor(diffMs / oneDay)}天前`
  }
  return date.toISOString().slice(0, 10)
}
</script>
