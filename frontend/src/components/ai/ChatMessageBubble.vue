<template>
  <div :class="['flex', isUser ? 'justify-end' : 'justify-start']">
    <div :class="['max-w-[78%] space-y-1', isUser ? 'items-end' : 'items-start']">
      <!-- 头部：角色 + 状态徽章 + 时间 -->
      <div :class="['flex items-center gap-2 text-[11px] text-on-surface-variant', isUser ? 'justify-end' : 'justify-start']">
        <span class="material-symbols-outlined text-[14px]">
          {{ isUser ? 'person' : 'auto_awesome' }}
        </span>
        <span class="font-medium">{{ roleLabel }}</span>
        <ChatStatusBadge v-if="!isUser" :status="status" />
        <span v-if="createdAt" class="font-mono text-[10px] text-on-surface-variant/70">
          {{ createdAt }}
        </span>
      </div>

      <!-- 内容气泡 -->
      <div
        :class="[
          'rounded-lg px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words',
          isUser
            ? 'bg-sky-500/20 text-on-surface'
            : 'bg-surface-container-high text-on-surface',
        ]"
      >
        <slot>
          {{ content || '(空)' }}
        </slot>
      </div>

      <!-- 错误信息（仅 failed） -->
      <div
        v-if="status === 'failed' && (errorCode || errorMessage)"
        class="rounded border border-red-400/30 bg-red-400/5 px-3 py-2 text-[11px] text-red-200"
      >
        <div v-if="errorCode" class="font-mono">[{{ errorCode }}]</div>
        <div v-if="errorMessage">{{ errorMessage }}</div>
      </div>

      <!-- 性能元数据（仅 completed） -->
      <div
        v-if="status === 'completed' && (elapsedMs != null || totalTokens != null)"
        class="text-[10px] text-on-surface-variant/70"
      >
        <span v-if="elapsedMs != null">{{ elapsedMs }} ms</span>
        <span v-if="elapsedMs != null && totalTokens != null"> · </span>
        <span v-if="totalTokens != null">{{ totalTokens }} tokens</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * AI Copilot — 单条消息气泡（user / assistant / system）
 *
 * Props 与 AiChatMessage 字段对齐；status 非 user 时显示徽章。
 * 错误详情仅在 failed 时显示，避免误以为是用户输入错误。
 */
import { computed } from 'vue'
import ChatStatusBadge from './ChatStatusBadge.vue'

const props = defineProps<{
  role: 'user' | 'assistant' | 'system'
  status: 'pending' | 'completed' | 'failed' | 'stale'
  content?: string | null
  createdAt?: string | null
  errorCode?: string | null
  errorMessage?: string | null
  elapsedMs?: number | null
  totalTokens?: number | null
}>()

const isUser = computed(() => props.role === 'user')
const roleLabel = computed(() => {
  if (props.role === 'user') return '你'
  if (props.role === 'assistant') return 'AI 助手'
  return '系统'
})
</script>
