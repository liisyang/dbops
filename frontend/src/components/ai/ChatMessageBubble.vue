<template>
  <div :class="['flex', isUser ? 'justify-end' : 'justify-start']">
    <div :class="['max-w-[78%] space-y-1', isUser ? 'items-end' : 'items-start']">
      <!-- 头部：角色 + 状态徽章 + 时间 -->
      <div :class="['flex items-center gap-2 text-[11px] text-on-surface-variant', isUser ? 'justify-end' : 'justify-start']">
        <span class="material-symbols-outlined text-[14px]">
          {{ isUser ? 'person' : headerIcon }}
        </span>
        <span class="font-medium">{{ roleLabel }}</span>
        <ChatStatusBadge v-if="!isUser" :status="status" />
        <span v-if="createdAt" class="font-mono text-[10px] text-on-surface-variant/70">
          {{ createdAt }}
        </span>
      </div>

      <!-- 内容气泡 — 普通 chat / error 文案 -->
      <div
        v-if="messageType === 'chat' || messageType === 'sql_preview' || messageType === 'error' || !messageType"
        :class="[
          'rounded-lg px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words',
          isUser
            ? 'bg-sky-500/20 text-on-surface'
            : 'bg-surface-container-high text-on-surface',
        ]"
      >
        <slot>
          {{ displayContent || '(空)' }}
        </slot>
      </div>

      <!-- C14 NEW — sql_preview_link 卡片：SQL 摘要 + 执行入口 -->
      <div
        v-else-if="messageType === 'sql_preview_link' && previewLinkMeta"
        class="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-sm"
      >
        <div class="mb-2 flex items-center gap-2 text-xs font-medium text-emerald-300">
          <span class="material-symbols-outlined text-[14px]">data_object</span>
          <span>已通过的 SQL（audit #{{ previewLinkMeta.audit_id }}）</span>
        </div>
        <pre class="overflow-x-auto rounded bg-surface-variant/40 p-2 text-[11px] leading-relaxed text-on-surface"><code>{{ previewLinkMeta.approved_sql }}</code></pre>
        <div class="mt-2 flex items-center justify-between text-[10px] text-on-surface-variant">
          <span v-if="previewLinkMeta.schema_policy_hash">
            policy_hash: {{ previewLinkMeta.schema_policy_hash.slice(0, 12) }}…
          </span>
          <button
            v-if="!executing"
            type="button"
            class="ops-secondary-button inline-flex items-center gap-1 px-2 py-0.5 text-[11px]"
            @click="$emit('execute', previewLinkMeta)"
          >
            <span class="material-symbols-outlined text-[12px]">play_arrow</span>
            执行 SQL
          </button>
          <span
            v-else
            class="inline-flex items-center gap-1 rounded bg-sky-500/15 px-2 py-0.5 text-[11px] text-sky-300"
          >
            <span class="material-symbols-outlined animate-spin text-[12px]">sync</span>
            执行中…
          </span>
        </div>
      </div>

      <!-- C14 NEW — sql_result 表格（callback 落库后） -->
      <div
        v-else-if="messageType === 'sql_result' && sqlResultPayload"
        class="rounded-lg border border-sky-500/30 bg-sky-500/5 px-4 py-3 text-sm"
      >
        <div class="mb-2 flex items-center justify-between gap-2 text-xs">
          <div class="flex items-center gap-2 font-medium text-sky-300">
            <span class="material-symbols-outlined text-[14px]">table_chart</span>
            <span>执行结果（{{ sqlResultPayload.row_count }} 行 · {{ sqlResultPayload.duration_ms }} ms）</span>
          </div>
          <span :class="resultStatusClass">
            {{ sqlResultPayload.status.toUpperCase() }}
          </span>
        </div>
        <!-- 表格（行 > 0 时） -->
        <div
          v-if="sqlResultPayload.columns.length && sqlResultPayload.rows.length"
          class="overflow-x-auto rounded bg-surface-variant/30"
        >
          <table class="w-full text-[11px]">
            <thead class="bg-surface-variant/50 text-on-surface-variant">
              <tr>
                <th
                  v-for="col in sqlResultPayload.columns"
                  :key="col"
                  class="border-b border-surface-variant/30 px-2 py-1 text-left font-medium"
                >
                  {{ col }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, ri) in sqlResultPayload.rows"
                :key="ri"
                class="odd:bg-surface-variant/10"
              >
                <td
                  v-for="(cell, ci) in row"
                  :key="ci"
                  class="border-b border-surface-variant/20 px-2 py-1 font-mono text-on-surface/90"
                >
                  {{ cell === null || cell === undefined ? '∅' : String(cell) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="text-xs text-on-surface-variant">（无返回行）</p>
        <p
          v-if="sqlResultPayload.error_message"
          class="mt-2 text-[11px] text-red-300/90"
        >
          {{ sqlResultPayload.error_message }}
        </p>

        <!-- C15 NEW — 操作按钮区：「重新执行」/「查看详情」/「已完成」徽章 -->
        <div
          v-if="resultAuditId != null"
          data-testid="sql-result-actions"
          class="mt-3 flex flex-wrap items-center gap-2 border-t border-surface-variant/30 pt-2 text-[11px]"
        >
          <!-- 「重新执行」：仅 failed/timeout/cancelled 时可点击（plan §4 risk #1） -->
          <button
            v-if="resultCanReExecute"
            type="button"
            class="ops-secondary-button inline-flex items-center gap-1 px-2 py-0.5 text-[11px]"
            :disabled="pendingAuditIdSet.has(resultAuditId)"
            @click="$emit('re-execute', resultAuditId)"
          >
            <span class="material-symbols-outlined text-[12px]">refresh</span>
            重新执行
          </button>
          <!-- 「执行中…」徽章：pending/running 时占位 -->
          <span
            v-else-if="resultIsNonTerminal && pendingAuditIdSet.has(resultAuditId)"
            class="inline-flex items-center gap-1 rounded bg-sky-500/15 px-2 py-0.5 text-[11px] text-sky-300"
          >
            <span class="material-symbols-outlined animate-spin text-[12px]">sync</span>
            执行中…
          </span>
          <!-- 「已完成」徽章：success 终态，禁用重新执行（避免重复触发；plan §4 risk #1） -->
          <span
            v-else-if="resultIsTerminalSuccess"
            class="inline-flex items-center gap-1 rounded bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300"
            title="该 SQL 已成功执行完成（再次执行可能产生不同结果）"
          >
            <span class="material-symbols-outlined text-[12px]">check_circle</span>
            已完成
          </span>

          <!-- 「查看详情」：始终可点，路由到 /ai/sql/preview?audit_id= -->
          <button
            type="button"
            class="ops-secondary-button inline-flex items-center gap-1 px-2 py-0.5 text-[11px]"
            @click="$emit('view-detail', resultAuditId)"
          >
            <span class="material-symbols-outlined text-[12px]">open_in_new</span>
            查看详情
          </button>
        </div>
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
 *
 * C14 NEW — sql_preview_link / sql_result 两种 message_type 分支：
 *  - sql_preview_link：渲染 approved_sql 卡片 + 执行按钮（emit 'execute'）
 *  - sql_result：渲染 columns/rows 表格 + row_count + duration_ms
 *
 * C15 NEW — sql_result 卡片底部加操作按钮区：
 *  - 「重新执行」仅 failed/timeout/cancelled 时显示，调 emit('re-execute', auditId)
 *  - 「查看详情」始终显示，emit('view-detail', auditId)，路由到 /ai/sql/preview?audit_id=
 *  - 「已完成」徽章：success 终态时占位（避免重复触发，plan §4 risk #1）
 *  - 「执行中…」徽章：pending/running 且在 Chat.vue pendingAuditIds 集合内时占位
 *
 * Refactor — hide ``：
 *  - 在 chat 气泡显示前对 content 做兜底剥离（避免历史脏数据 / 其它端点漏剥离时泄露）
 *  - 只影响 chat / sql_preview / error 普通文本气泡，不影响 sql_preview_link / sql_result 卡片
 *  - 后端 DifyService.chat_message 已对 answer 做权威剥离，本处为显示层最后防线
 */
import { computed } from 'vue'
import ChatStatusBadge from './ChatStatusBadge.vue'
import type {
  AiSqlPreviewLinkMetadata,
  AiSqlResultMetadata,
  AiSqlResultPayload,
} from '@/types/ai'
import { stripThinkBlocks } from '@/utils/aiText'

const props = defineProps<{
  role: 'user' | 'assistant' | 'system'
  status: 'pending' | 'completed' | 'failed' | 'stale'
  messageType?: 'chat' | 'sql_preview' | 'sql_preview_link' | 'sql_result' | 'error' | null
  content?: string | null
  createdAt?: string | null
  errorCode?: string | null
  errorMessage?: string | null
  elapsedMs?: number | null
  totalTokens?: number | null
  metadataJson?: Record<string, unknown> | null
  /** C14 NEW — sql_preview_link 卡片正在触发 execute 时禁用按钮。 */
  executing?: boolean
  /** C15 NEW — 当前在轮询的 audit_id 集合（用于 sql_result 卡片按钮 disable + 「执行中…」徽章）。 */
  pendingAuditIds?: Set<number>
}>()

defineEmits<{
  (e: 'execute', meta: AiSqlPreviewLinkMetadata): void
  // C15 NEW — sql_result 卡片「重新执行」（force=true 走 executeSql）
  (e: 're-execute', auditId: number): void
  // C15 NEW — sql_result 卡片「查看详情」（路由到 /ai/sql/preview?audit_id=）
  (e: 'view-detail', auditId: number): void
}>()

const isUser = computed(() => props.role === 'user')

// C15 NEW — 空 Set fallback，避免 vue-tsc 在 props.pendingAuditIds?.has() 时
// 持续报 TS18048（template 里 .has() 仍需非 undefined 接收方）。
const EMPTY_SET: ReadonlySet<number> = new Set<number>()
const roleLabel = computed(() => {
  if (props.role === 'user') return '你'
  if (props.role === 'assistant') return 'AI 助手'
  return '系统'
})

const headerIcon = computed(() => {
  if (props.messageType === 'sql_preview_link') return 'data_object'
  if (props.messageType === 'sql_result') return 'table_chart'
  return 'auto_awesome'
})

const previewLinkMeta = computed<AiSqlPreviewLinkMetadata | null>(() => {
  if (props.messageType !== 'sql_preview_link' || !props.metadataJson) return null
  const m = props.metadataJson as Partial<AiSqlPreviewLinkMetadata>
  if (typeof m.audit_id !== 'number' || typeof m.approved_sql !== 'string') return null
  return {
    audit_id: m.audit_id,
    instance_id: typeof m.instance_id === 'number' ? m.instance_id : 0,
    database_name: m.database_name ?? null,
    approved_sql: m.approved_sql,
    approved_sql_hash: m.approved_sql_hash ?? null,
    schema_policy_hash: m.schema_policy_hash ?? null,
    preview_safety_status: m.preview_safety_status === 'rejected' ? 'rejected' : 'passed',
  }
})

const sqlResultPayload = computed<AiSqlResultPayload | null>(() => {
  if (props.messageType !== 'sql_result') return null
  const md = props.metadataJson as Partial<AiSqlResultMetadata> | undefined
  // content 是 JSON 字符串（callback 序列化），做兜底解析
  if (props.content && typeof props.content === 'string') {
    try {
      const parsed = JSON.parse(props.content) as AiSqlResultPayload
      if (Array.isArray(parsed.columns) && Array.isArray(parsed.rows)) {
        return parsed
      }
    } catch {
      // 不是 JSON 时 fallback 到 metadata
    }
  }
  if (md && Array.isArray((md as any).columns) && Array.isArray((md as any).rows)) {
    return md as unknown as AiSqlResultPayload
  }
  return null
})

// C15 NEW — 从 metadata_json 提 audit_id（sql_result 卡片操作按钮依赖）
const resultAuditId = computed<number | null>(() => {
  if (props.messageType !== 'sql_result') return null
  const md = props.metadataJson as { audit_id?: number } | null | undefined
  const id = md?.audit_id
  return typeof id === 'number' && id > 0 ? id : null
})

// C15 NEW — 重新执行按钮可见性：仅 failed/timeout/cancelled 终态可重跑（plan §4 risk #1）
const resultCanReExecute = computed<boolean>(() => {
  const s = sqlResultPayload.value?.status
  return s === 'failed' || s === 'timeout' || s === 'cancelled'
})

// C15 NEW — pending/running 非终态（用于「执行中…」徽章占位）
const resultIsNonTerminal = computed<boolean>(() => {
  const s = sqlResultPayload.value?.status
  return s === 'pending' || s === 'running'
})

// C15 NEW — success 终态：禁用重新执行（避免重复触发）
const resultIsTerminalSuccess = computed<boolean>(() => {
  const s = sqlResultPayload.value?.status
  return s === 'success'
})

// C15 NEW — 给模板一个非 undefined 的 Set 视图（避免 TS18048 + 简化模板）
const pendingAuditIdSet = computed<Set<number>>(
  () => props.pendingAuditIds ?? (EMPTY_SET as Set<number>),
)

const resultStatusClass = computed(() => {
  const status = sqlResultPayload.value?.status
  if (status === 'success') return 'inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300'
  if (status === 'failed') return 'inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] text-red-300'
  if (status === 'timeout') return 'inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-300'
  return 'inline-flex items-center gap-1 rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] text-sky-300'
})

/**
 * Refactor — hide ``：
 * 普通 chat 气泡显示前剥离 content 中的 `` 推理过程块。
 * 仅影响 messageType ∈ {chat, sql_preview, error, undefined} 分支；
 * sql_preview_link / sql_result 两种卡片分支走 metadata 渲染，不经此处（无泄露风险）。
 */
const displayContent = computed<string>(() => {
  if (
    props.messageType === 'sql_preview_link' ||
    props.messageType === 'sql_result'
  ) {
    return props.content ?? ''
  }
  return stripThinkBlocks(props.content)
})
</script>
