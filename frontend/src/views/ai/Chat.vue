<template>
  <OpsPage>
    <OpsPageHeader
      :title="pageTitle"
      :subtitle="boundInstanceId
        ? '基于 Dify 的智能 SQL Copilot（C16-F2c 实例绑定模式）'
        : '基于 Dify 的智能运维对话（C5 落地交互界面）'"
    />

    <div :class="boundInstanceId ? '' : 'grid gap-4 lg:grid-cols-[280px_1fr]'">
      <!-- 左侧：会话侧栏 — 仅 general 模式展示 -->
      <OpsSectionCard
        v-if="!boundInstanceId"
        class="lg:min-h-[calc(100vh-220px)]"
      >
        <ChatSessionList
          :sessions="sessions"
          :active-id="activeSessionId"
          :loading="loadingSessions"
          :creating="creating"
          @create="handleCreateSession"
          @select="handleSelectSession"
        />
      </OpsSectionCard>

      <!-- 右侧：主区（消息流 + 输入框） -->
      <OpsSectionCard class="flex flex-col">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <h2 class="text-base font-semibold text-on-surface">
                {{ activeSessionTitle }}
              </h2>
              <p class="truncate text-xs text-on-surface-variant">
                <span v-if="activeSessionId">
                  会话 #{{ activeSessionId }} · {{ activeMessages.length }} 条消息
                </span>
                <span v-else-if="boundInstanceId">创建/复用绑定会话中…</span>
                <span v-else>请选择左侧会话，或点击"新建"开始对话</span>
              </p>
            </div>
            <!-- C16-F2c NEW — instance_sql 模式：实例上下文 + 退出按钮 -->
            <div v-if="boundInstanceId" class="flex shrink-0 items-center gap-2">
              <span
                v-if="boundInstanceContext"
                class="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300"
                :title="`${boundInstanceContext.instance_name} (${boundInstanceContext.db_type_code || '?'} / ${boundInstanceContext.server_ip || 'no-ip'}:${boundInstanceContext.port || '-'})`"
              >
                <span class="material-symbols-outlined text-[12px]">database</span>
                {{ boundInstanceContext.instance_name }}
                <span class="text-on-surface-variant/80">
                  · {{ boundInstanceContext.db_type_code || '?' }}
                  · {{ boundInstanceContext.server_ip || 'no-ip' }}:{{ boundInstanceContext.port || '-' }}
                </span>
              </span>
              <span
                v-else-if="boundInstanceLoading"
                class="inline-flex items-center gap-1 text-[11px] text-on-surface-variant"
              >
                <span class="material-symbols-outlined animate-spin text-[12px]">sync</span>
                加载实例上下文…
              </span>
              <span
                v-else-if="boundInstanceError"
                class="text-[11px] text-red-300"
                :title="boundInstanceError"
              >
                实例上下文加载失败
              </span>
              <button
                type="button"
                class="ops-secondary-button inline-flex items-center gap-1 px-2 py-0.5 text-[11px]"
                @click="exitBoundMode"
              >
                <span class="material-symbols-outlined text-[12px]">arrow_back</span>
                返回通用 Chat
              </button>
            </div>
          </div>
        </template>

        <!-- 加载中 -->
        <div
          v-if="loadingMessages"
          class="flex min-h-[400px] flex-1 items-center justify-center text-on-surface-variant"
        >
          <span class="material-symbols-outlined animate-spin text-2xl">sync</span>
          <span class="ml-2 text-sm">加载消息历史…</span>
        </div>

        <!-- 错误态 -->
        <div
          v-else-if="loadError"
          class="flex min-h-[400px] flex-1 flex-col items-center justify-center px-6 text-center"
        >
          <span class="material-symbols-outlined text-3xl text-red-400">error</span>
          <p class="mt-3 text-sm text-red-200">{{ loadError }}</p>
          <button
            type="button"
            class="ops-secondary-button mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs"
            @click="retryLoadMessages"
          >
            <span class="material-symbols-outlined text-[16px]">refresh</span>
            重试
          </button>
        </div>

        <!-- 空态：未选会话 -->
        <div
          v-else-if="!activeSessionId"
          class="flex min-h-[400px] flex-1 items-center justify-center"
        >
          <OpsEmptyState
            state="empty"
            icon="forum"
            :title="boundInstanceId ? '正在创建绑定会话…' : '还没有选中的会话'"
            :description="boundInstanceId ? '首次进入实例绑定模式时会自动创建或复用 instance_sql 会话。' : '在左侧选择一个历史会话，或点击右上角“新建”开始一段新的对话。'"
          />
        </div>

        <!-- 空态：会话无消息 -->
        <div
          v-else-if="!activeMessages.length"
          class="flex min-h-[400px] flex-1 items-center justify-center"
        >
          <OpsEmptyState
            state="empty"
            icon="chat_bubble"
            title="这条会话还没有消息"
            :description="boundInstanceId
              ? '在下方的输入框输入自然语言问题，例如「查询最近 10 条订单」，按 Enter 发送。'
              : '在下方的输入框中输入问题，按 Enter 发送。'"
          />
        </div>

        <!-- 消息流 -->
        <div v-else class="min-h-[400px] flex-1 space-y-4 overflow-y-auto pr-1">
          <ChatMessageBubble
            v-for="m in activeMessages"
            :key="m.id"
            :role="m.role"
            :status="m.status"
            :message-type="m.message_type"
            :content="m.content"
            :created-at="formatTime(m.created_at)"
            :error-code="m.error_code"
            :error-message="m.error_message"
            :elapsed-ms="m.elapsed_ms"
            :total-tokens="m.total_tokens"
            :metadata-json="m.metadata_json"
            :executing="pendingAuditIds.has(getAuditId(m))"
            :pending-audit-ids="pendingAuditIds"
            @execute="onExecuteFromBubble"
            @re-execute="onReExecuteFromResult"
            @view-detail="onViewDetailFromResult"
          />
          <!-- C14 NEW — execute 错误条（局部，不污染 sendError） -->
          <div
            v-if="executeError"
            class="flex items-start gap-2 rounded border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-200"
          >
            <span class="material-symbols-outlined text-[16px]">error</span>
            <span class="flex-1">{{ executeError }}</span>
            <button
              type="button"
              class="text-on-surface-variant/70 hover:text-on-surface"
              title="清空"
              @click="executeError = null"
            >
              <span class="material-symbols-outlined text-[14px]">close</span>
            </button>
          </div>
        </div>

        <!-- 输入框（P4：发送中禁用 + 错误条；C16-F2c 改：placeholder 按模式切换） -->
        <div v-if="activeSessionId" class="mt-4 space-y-2 border-t border-outline-variant/30 pt-4">
          <div
            v-if="sendError"
            class="flex items-start gap-2 rounded border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-200"
          >
            <span class="material-symbols-outlined text-[16px]">error</span>
            <span class="flex-1">{{ sendError }}</span>
            <button
              type="button"
              class="text-on-surface-variant/70 hover:text-on-surface"
              title="清空"
              @click="sendError = null"
            >
              <span class="material-symbols-outlined text-[14px]">close</span>
            </button>
          </div>
          <ChatInputBox
            :model-value="draft"
            :disabled="sending"
            :placeholder="inputPlaceholder"
            @update:model-value="draft = $event"
            @send="onSend"
          />
        </div>
      </OpsSectionCard>
    </div>
  </OpsPage>
</template>

<script setup lang="ts">
/**
 * AI Copilot — 主入口（Phase 3.6 C5-P4 + C16-F2c boundInstanceId 模式分流）
 *
 * P4 进度：接 sendMessage + safeUuid（兼容非 secure context）+ 错误码 409/502/503/504/null 兜底。
 * - 乐观更新：先 append 本地 user 消息（status=pending），响应回来再替换
 * - 错误状态码特定文案（plan §11）：
 *     409 ChatConcurrentPendingError — 已有 pending 消息
 *     502 Dify 不可用
 *     503 AI_CHAT_ENABLED=false
 *     504 Dify 超时
 * - assistant_message=null 兜底：UI 提示"助手消息未生成"，不弹错
 * - Pydantic 422 detail 数组 → 提取 .msg 拼成可读字符串
 *
 * C16-F2c NEW（plan §21.3 C16-4 — 实例绑定 Chat SQL Copilot）：
 * - 读取 route.query.boundInstanceId：有值 → 进入 instance_sql 模式
 * - instance_sql 模式：创建/复用绑定 session（F2a partial unique 天然复用）
 * - onSend 分流：instance_sql → POST /api/v1/ai/sql/preview；
 *                general     → POST /api/v1/ai/chat/sessions/{id}/messages
 * - 顶部显示实例上下文（name / db_type / host:port）
 * - 输入框 placeholder 切换为 SQL 提示
 *
 * 未做（Phase 3.6B）：FAB 浮窗 + 抽屉（用户已确认双入口策略）
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { aiApi } from '@/api/ai'
import { assetsApi } from '@/api/assets'
import type {
  AiChatMessage,
  AiChatSession,
  AiSqlPreviewLinkMetadata,
} from '@/types/ai'
import type { InstanceDetail } from '@/types/api'
import { safeUuid } from '@/utils/uuid'
import {
  ChatMessageBubble,
  ChatInputBox,
  ChatSessionList,
} from '@/components/ai'
import {
  OpsPage,
  OpsPageHeader,
  OpsSectionCard,
  OpsEmptyState,
} from '@/components/ops'

// ---- state ----
const sessions = ref<AiChatSession[]>([])
const messagesBySession = ref<Record<number, AiChatMessage[]>>({})
const activeSessionId = ref<number | null>(null)
const loadingSessions = ref(false)
const loadingMessages = ref(false)
const creating = ref(false)
const sessionsError = ref<string | null>(null)
const loadError = ref<string | null>(null)
const sendError = ref<string | null>(null)
const sending = ref(false)
const draft = ref('')

// ---- C14 NEW — SQL 执行状态 ----
const executeError = ref<string | null>(null)
// 当前正在轮询的 audit_id 集合（sql_preview_link 卡片触发 execute 后 + 历史
// pending audit 自动加载时填充；终态时移除）
const pendingAuditIds = ref<Set<number>>(new Set())
const pendingPollingEnabled = ref(false)
let pendingPollTimer: ReturnType<typeof setInterval> | null = null

// C15 NEW — 路由（C15-B 「查看详情」跳转 /ai/sql/preview?audit_id= 用）
const router = useRouter()

// C16-F2c NEW — boundInstanceId 模式分流（plan §21.3 C16-4）
const route = useRoute()
// 来自 route.query.boundInstanceId；有值 → instance_sql 模式
const boundInstanceId = ref<number | null>(null)
// 绑定的实例上下文（仅展示用，无关键行为依赖）
const boundInstanceContext = ref<InstanceDetail | null>(null)
const boundInstanceLoading = ref(false)
const boundInstanceError = ref<string | null>(null)

// 解析 route.query.boundInstanceId 为正整数；非法 → null
function parseBoundInstanceId(): number | null {
  const raw = route.query.boundInstanceId
  if (raw == null) return null
  const s = Array.isArray(raw) ? String(raw[0] ?? '') : String(raw)
  const n = Number(s)
  return Number.isFinite(n) && n > 0 ? n : null
}

function getAuditId(msg: AiChatMessage): number {
  const md = msg.metadata_json as { audit_id?: number } | null | undefined
  return typeof md?.audit_id === 'number' ? md.audit_id : -1
}

// ---- derived ----
const activeSessionTitle = computed(() => {
  const s = sessions.value.find((x) => x.id === activeSessionId.value)
  return s?.title ?? 'AI Copilot'
})

// C16-F2c1 NEW — 页面标题 + 浏览器标签标题（instance_sql 模式下展示
// "AI Copilot · 业务系统名 · 10.134.181.168:1521 (oracle)" 模式，
// 便于 DBA 区分多实例窗口 + 一眼看到业务归属）
const DEFAULT_PAGE_TITLE = 'AI Copilot'
const pageTitle = computed(() => {
  if (boundInstanceId.value == null) return DEFAULT_PAGE_TITLE
  const ctx = boundInstanceContext.value
  if (!ctx) {
    return `${DEFAULT_PAGE_TITLE} · 实例 #${boundInstanceId.value} (加载中…)`
  }
  const dbType = (ctx.db_type_code || '?').toLowerCase()
  const ip = ctx.server_ip || 'no-ip'
  const port = ctx.port ?? '-'
  const biz = ctx.system_name || ''
  // 业务系统名 → IP:端口 (db_type)；无业务系统名时回退到原版
  return biz
    ? `${DEFAULT_PAGE_TITLE} · ${biz} · ${ip}:${port} (${dbType})`
    : `${DEFAULT_PAGE_TITLE} · ${ip}:${port} (${dbType})`
})

// 同步 document.title — 多 Tab 切换时浏览器标签可一眼区分
// 进入实例绑定模式时：标签显示 "AI Copilot · 10.134.181.168:1521 (oracle)"
// 离开时：还原为 "AI Copilot"
const ORIGINAL_DOC_TITLE = typeof document !== 'undefined' ? document.title : DEFAULT_PAGE_TITLE
watch(
  pageTitle,
  (t) => {
    if (typeof document !== 'undefined') document.title = t
  },
  { immediate: true },
)
const activeMessages = computed<AiChatMessage[]>(() => {
  const id = activeSessionId.value
  if (id == null) return []
  return messagesBySession.value[id] ?? []
})
// C16-F2c NEW — 当前激活 session 是否为 instance_sql 模式（决定 onSend 走 sqlPreview 还是 sendMessage）
const activeSessionIsInstanceSql = computed<boolean>(() => {
  if (boundInstanceId.value == null) return false
  const s = sessions.value.find((x) => x.id === activeSessionId.value)
  return s?.chat_mode === 'instance_sql' && s?.bound_instance_id === boundInstanceId.value
})
// C16-F2c NEW — 输入框 placeholder（按模式切换）
const inputPlaceholder = computed(() => {
  if (sending.value) return '正在调用 Dify…请稍候'
  if (activeSessionIsInstanceSql.value) {
    return '请输入要查询的数据，例如：查询最近 10 条订单（Enter 发送，Shift+Enter 换行）'
  }
  return '输入消息，Enter 发送，Shift+Enter 换行'
})

// ---- helpers ----
function formatTime(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toTimeString().slice(0, 5)
}

interface AxiosLikeError {
  response?: {
    status?: number
    data?: { message?: string; detail?: string | Array<{ msg?: string; message?: string }> }
  }
}

/** 通用：从 axios 错误里抽 detail 字符串（兼容字符串 / 数组两种形态） */
function extractDetail(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const ax = err as AxiosLikeError
    const data = ax.response?.data
    if (data?.message) return data.message
    if (typeof data?.detail === 'string' && data.detail) return data.detail
    if (Array.isArray(data?.detail) && data.detail.length) {
      return data.detail
        .map((d) => d?.msg || d?.message || JSON.stringify(d))
        .join('；')
    }
    if (ax.response?.status) return `HTTP ${ax.response.status}`
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}

/** sendMessage 专用：按状态码给特定中文提示（plan §11 错误码文档） */
function describeSendError(err: unknown): string {
  const status = (err as AxiosLikeError | null)?.response?.status
  if (status === 409) return '该会话已有消息正在处理，请稍候再发'
  if (status === 502) return 'AI 服务暂时不可达（Dify 错误），请稍后重试'
  if (status === 503) return 'AI 功能未启用（AI_CHAT_ENABLED=false），请联系管理员'
  if (status === 504) return 'AI 调用超时（30s），请稍后重试或换更短的问题'
  return extractDetail(err, '发送失败')
}

function nowIso(): string {
  return new Date().toISOString()
}

/** 构造一条占位 user 消息（optimistic） */
function buildOptimisticUser(content: string, clientRequestId: string): AiChatMessage {
  return {
    id: -Date.now(), // 负数 id 便于后续 findAndRemove
    session_id: activeSessionId.value ?? 0,
    user_id: null,
    client_request_id: clientRequestId,
    role: 'user',
    message_type: 'chat',
    status: 'pending',
    content,
    parent_message_id: null,
    metadata_json: undefined,
    dify_task_id: null,
    workflow_run_id: null,
    elapsed_ms: null,
    total_tokens: null,
    error_code: null,
    error_message: null,
    processing_started_at: null,
    processing_expires_at: null,
    attempt_count: 1,
    created_at: nowIso(),
    updated_at: nowIso(),
  }
}

/** 用 clientRequestId 找到并替换占位消息 */
function replaceOptimistic(
  sessionId: number,
  clientRequestId: string,
  next: AiChatMessage,
) {
  const arr = messagesBySession.value[sessionId] ?? []
  const idx = arr.findIndex((m) => m.client_request_id === clientRequestId)
  if (idx >= 0) {
    const copy = arr.slice()
    copy[idx] = next
    messagesBySession.value[sessionId] = copy
  } else {
    messagesBySession.value[sessionId] = [...arr, next]
  }
}

function appendToSession(sessionId: number, msg: AiChatMessage) {
  const arr = messagesBySession.value[sessionId] ?? []
  messagesBySession.value[sessionId] = [...arr, msg]
}

// ---- loaders ----
async function loadSessions() {
  loadingSessions.value = true
  sessionsError.value = null
  try {
    const resp = await aiApi.listSessions(
      { limit: 50 },
      { suppressErrorToast: true },
    )
    sessions.value = resp.items
    if (!activeSessionId.value && resp.items.length) {
      await handleSelectSession(resp.items[0].id)
    }
  } catch (err) {
    sessionsError.value = extractDetail(err, '加载会话列表失败')
    // eslint-disable-next-line no-console
    console.error('[Chat] loadSessions failed:', err)
  } finally {
    loadingSessions.value = false
  }
}

async function loadMessages(sessionId: number) {
  loadingMessages.value = true
  loadError.value = null
  try {
    const resp = await aiApi.listMessages(
      sessionId,
      { limit: 200 },
      { suppressErrorToast: true },
    )
    messagesBySession.value[sessionId] = resp.items
  } catch (err) {
    loadError.value = extractDetail(err, '加载消息历史失败')
    // eslint-disable-next-line no-console
    console.error('[Chat] loadMessages failed:', err)
  } finally {
    loadingMessages.value = false
  }
}

// ---- handlers ----
async function handleSelectSession(sessionId: number) {
  activeSessionId.value = sessionId
  sendError.value = null
  if (!messagesBySession.value[sessionId]) {
    await loadMessages(sessionId)
  }
}

async function handleCreateSession() {
  creating.value = true
  try {
    const created = await aiApi.createSession({})
    sessions.value = [created, ...sessions.value]
    activeSessionId.value = created.id
    messagesBySession.value[created.id] = []
    sendError.value = null
  } catch (err) {
    sessionsError.value = extractDetail(err, '新建会话失败')
    // eslint-disable-next-line no-console
    console.error('[Chat] createSession failed:', err)
  } finally {
    creating.value = false
  }
}

async function retryLoadMessages() {
  if (activeSessionId.value != null) {
    await loadMessages(activeSessionId.value)
  }
}

// =============================================================================
// C16-F2c NEW — boundInstanceId 模式分流（plan §21.3 C16-4）
// =============================================================================

/** 拉取绑定实例上下文（仅展示用）。失败不阻塞主流程。 */
async function loadBoundInstanceContext(instanceId: number) {
  boundInstanceLoading.value = true
  boundInstanceError.value = null
  try {
    boundInstanceContext.value = await assetsApi.getInstance(instanceId, {
      suppressErrorToast: true,
    })
  } catch (err) {
    boundInstanceError.value = extractDetail(err, '加载实例上下文失败')
    // eslint-disable-next-line no-console
    console.error('[Chat] loadBoundInstanceContext failed:', err)
  } finally {
    boundInstanceLoading.value = false
  }
}

/** 创建/复用 instance_sql 绑定 session（F2a partial unique 天然复用）。 */
async function createBoundSession(instanceId: number) {
  creating.value = true
  try {
    const sess = await aiApi.createSession({
      mode: 'instance_sql',
      bound_instance_id: instanceId,
      source_page: 'instance_detail',
    })
    sessions.value = [sess, ...sessions.value]
    activeSessionId.value = sess.id
    messagesBySession.value[sess.id] = []
    sendError.value = null
    sessionsError.value = null
  } catch (err) {
    sessionsError.value = extractDetail(err, '创建/复用绑定会话失败')
    // eslint-disable-next-line no-console
    console.error('[Chat] createBoundSession failed:', err)
  } finally {
    creating.value = false
  }
}

/** 退出实例绑定模式（去掉 query.boundInstanceId，回到 general 模式）。 */
function exitBoundMode() {
  boundInstanceId.value = null
  boundInstanceContext.value = null
  activeSessionId.value = null
  // 用 router.replace 清 query，不留历史
  router.replace({ name: 'AiChat', query: {} })
}

/** sqlPreview 错误映射（plan §11 + F2b 5 类新异常 + C16-F2c1 解析 detail.code）。 */
function describePreviewError(err: unknown): string {
  const ax = err as AxiosLikeError | null
  const status = ax?.response?.status
  const detail = ax?.response?.data?.detail
  const detailStr =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail) && detail.length
        ? detail.map((d: { msg?: string; message?: string }) => d?.msg || d?.message || '').join('；')
        : null
  // C16-F2c1 NEW: 后端 detail 可能是对象 {code, message, ...}，提取更具体的提示
  const detailObj = (detail && typeof detail === 'object' && !Array.isArray(detail)
    ? (detail as { code?: string; message?: string; reason?: string; user_message_id?: number })
    : null)
  const codeMsg = detailObj?.message || null
  const code = detailObj?.code || null
  if (status === 403) return `会话无权访问（403）：${codeMsg || detailStr || 'session 不属于当前用户'}`
  if (status === 404) return `会话或实例不存在（404）：${codeMsg || detailStr || '检查 session_id / instance_id'}`
  if (status === 409) {
    if (code === 'preview_incomplete_retry_required') {
      // 旧请求事务中断 (user_message 落库但 audit 缺失)；前端 onSend
      // 每次用新 UUID，新请求会走完整流程。所以这里直接告诉用户「重发即可」
      const umid = detailObj?.user_message_id
      return umid
        ? `上次请求未完成（user_message #${umid} 已被记录但 audit 未落库）。请直接按 Enter 重发，前端会用新 client_request_id 走完整流程。`
        : '上次请求未完成（事务中断）。请直接按 Enter 重发。'
    }
    if (code === 'snapshot_unavailable') {
      return `Schema 快照不可用（409 ${detailObj?.reason || 'unknown'}）：请先在实例详情页触发 Schema 采集。`
    }
    return `请求冲突（409）：${codeMsg || detailStr || '稍后重试'}`
  }
  if (status === 422) return `参数校验失败（422）：${codeMsg || detailStr || '检查 mode / bound_instance_id / instance_id 一致性'}`
  if (status === 502) return `Dify 服务不可达（502）：${codeMsg || detailStr || '稍后重试'}`
  if (status === 503) return `AI SQL Preview 未启用（AI_SQL_PREVIEW_ENABLED=false）`
  if (status === 504) return `Dify 调用超时（504）：${codeMsg || detailStr || '稍后重试或换更短的问题'}`
  return extractDetail(err, 'SQL Preview 失败')
}

/** P4 真实发送（C16-F2c 改：instance_sql 分流到 sqlPreview） */
async function onSend(value: string) {
  const sessionId = activeSessionId.value
  if (sessionId == null || sending.value) return

  const clientRequestId = safeUuid()
  const optimistic = buildOptimisticUser(value, clientRequestId)
  appendToSession(sessionId, optimistic)
  sendError.value = null
  sending.value = true

  // C16-F2c NEW — instance_sql 模式走 /ai/sql/preview
  if (activeSessionIsInstanceSql.value && boundInstanceId.value != null) {
    try {
      const r = await aiApi.sqlPreview({
        session_id: sessionId,
        client_request_id: clientRequestId,
        instance_id: boundInstanceId.value,
        user_question: value,
        current_page: 'instance_detail',
      })
      // 把占位 user 消息标记为 completed（id 由后端定；后续拉消息以服务端为准）
      const completed: AiChatMessage = {
        ...optimistic,
        status: 'completed',
        updated_at: nowIso(),
      }
      replaceOptimistic(sessionId, clientRequestId, completed)
      // 重新拉消息：F2b 双消息事务写入了 user + preview message，
      // 前端用 listMessages 拿到完整 message row（含真实 id + metadata_json）。
      await loadMessages(sessionId)
      // idempotent_replay 提示用户
      if (r.idempotent_replay) {
        sendError.value = '（使用缓存结果，未重复调用 Dify）'
      }
    } catch (err) {
      const failed: AiChatMessage = {
        ...optimistic,
        status: 'failed',
        error_code: 'SqlPreviewError',
        error_message: describePreviewError(err),
        updated_at: nowIso(),
      }
      replaceOptimistic(sessionId, clientRequestId, failed)
      sendError.value = describePreviewError(err)
      // eslint-disable-next-line no-console
      console.error('[Chat] sqlPreview failed:', err)
    } finally {
      sending.value = false
    }
    return
  }

  // general 模式 — 维持 C3 sendMessage 行为
  try {
    const resp = await aiApi.sendMessage(sessionId, {
      client_request_id: clientRequestId,
      query: value,
      current_page: 'ai_chat',
    })
    // 用服务端 user_message 替换占位（保留真实 id + 时间戳）
    replaceOptimistic(sessionId, clientRequestId, resp.user_message)

    // assistant_message 可能为 null（事务 1 中断的边界场景，plan §11）
    if (resp.assistant_message) {
      appendToSession(sessionId, resp.assistant_message)
    } else {
      sendError.value = '助手消息未生成（事务中断），可重新发送同一问题'
    }
  } catch (err) {
    // 把乐观 user 标记为 failed
    const failed: AiChatMessage = {
      ...optimistic,
      status: 'failed',
      error_code: 'SendError',
      error_message: describeSendError(err),
      updated_at: nowIso(),
    }
    replaceOptimistic(sessionId, clientRequestId, failed)
    sendError.value = describeSendError(err)
    // eslint-disable-next-line no-console
    console.error('[Chat] sendMessage failed:', err)
  } finally {
    sending.value = false
  }
}

// ---- lifecycle ----
onMounted(async () => {
  const bid = parseBoundInstanceId()
  if (bid != null) {
    // C16-F2c NEW — instance_sql 模式入口
    boundInstanceId.value = bid
    // 并行：拉实例上下文 + 创建/复用 session（后者依赖 F2a partial unique 自动复用）
    await Promise.all([
      loadBoundInstanceContext(bid),
      createBoundSession(bid),
    ])
    // session 建好后拉历史（普通情况无历史；已复用 session 才有历史）
    if (activeSessionId.value != null) {
      await loadMessages(activeSessionId.value)
    }
  } else {
    // general 模式 — 维持 C5 行为
    await loadSessions()
  }
  loadPendingExecutions()
})

onBeforeUnmount(() => {
  stopPendingPolling()
  // C16-F2c1 NEW: 离开页面还原 document.title（避免 SPA 路由切换后残留旧 title）
  if (typeof document !== 'undefined') {
    document.title = ORIGINAL_DOC_TITLE
  }
})

// =============================================================================
// C14 NEW — SQL Execute 集成（plan §6.1 + §8）
// =============================================================================

/** execute 专用：按状态码给特定中文提示（plan §11 错误码文档） */
function describeExecuteError(err: unknown): string {
  const ax = err as AxiosLikeError | null
  const status = ax?.response?.status
  const detail = ax?.response?.data?.detail
  const detailStr =
    typeof detail === 'string' ? detail
    : detail && typeof detail === 'object' && 'message' in detail
      ? String((detail as { message?: string }).message)
      : null
  if (status === 409) return `SQL 执行冲突（409）：${detailStr || '请检查 audit 状态或 schema policy'}`
  if (status === 422) return `SQL 在 Execute 时被安全层拒绝（422）：${detailStr || '重新 Preview 后再试'}`
  if (status === 502) return `AWX 调度失败（502）：${detailStr || '检查 AWX 凭证 / Job Template'}`
  if (status === 503) return `SQL 执行功能未启用（AI_SQL_EXECUTION_ENABLED=false）`
  return extractDetail(err, 'SQL 执行失败')
}

/** sql_preview_link 卡片点击「执行 SQL」 → aiApi.executeSql + 启动轮询 */
async function onExecuteFromBubble(meta: AiSqlPreviewLinkMetadata) {
  if (typeof meta?.audit_id !== 'number') {
    executeError.value = '卡片 metadata 缺失 audit_id'
    return
  }
  await triggerExecute(meta.audit_id, /* force */ false)
}

/**
 * 触发 SQL 执行：async 包装 executeSql + pendingAuditIds 集合 + 错误兜底。
 * 复用给 sql_preview_link 卡片（force=false）和 sql_result 卡片重新执行（force=true）。
 */
async function triggerExecute(auditId: number, force: boolean) {
  if (!Number.isFinite(auditId) || auditId <= 0) {
    executeError.value = 'audit_id 无效'
    return
  }
  if (pendingAuditIds.value.has(auditId)) return
  pendingAuditIds.value.add(auditId)
  executeError.value = null
  try {
    await aiApi.executeSql({ audit_id: auditId, force })
    startPendingPolling()
  } catch (err) {
    pendingAuditIds.value.delete(auditId)
    executeError.value = describeExecuteError(err)
    // eslint-disable-next-line no-console
    console.error('[Chat] executeSql failed:', err)
  }
}

/**
 * C15 NEW — sql_result 卡片点击「重新执行」：走 executeSql force=true（终态覆盖）。
 * 失败/超时/取消三种终态下可点击；success 终态在气泡里禁用按钮。
 */
async function onReExecuteFromResult(auditId: number) {
  await triggerExecute(auditId, /* force */ true)
}

/**
 * C15 NEW — sql_result 卡片点击「查看详情」：路由到 SqlPreview.vue 接
 * ?audit_id= query（SqlPreview.onMounted 检测并自动加载 execution status）。
 */
function onViewDetailFromResult(auditId: number) {
  if (!Number.isFinite(auditId) || auditId <= 0) {
    executeError.value = 'audit_id 无效，无法跳转详情'
    return
  }
  router.push({ path: '/ai/sql/preview', query: { audit_id: String(auditId) } })
}

/**
 * 进入会话时扫描 activeMessages，找出 sql_preview_link 卡片 metadata 里的
 * audit_id，对每个 audit_id 调 getExecutionStatus 检查是否仍在 pending/
 * running 中，是的话加入 pendingAuditIds 集合 + 启动轮询。
 *
 * 设计：去重 + 最多 5 个并发（防止历史消息过多时同时发起多个轮询）。
 */
async function loadPendingExecutions() {
  if (!activeMessages.value.length) return
  const auditIds = new Set<number>()
  for (const m of activeMessages.value) {
    if (m.message_type !== 'sql_preview_link') continue
    const id = getAuditId(m)
    if (id > 0) auditIds.add(id)
  }
  if (!auditIds.size) return
  // 限制最多 5 个并发
  const slice = Array.from(auditIds).slice(0, 5)
  await Promise.all(
    slice.map(async (aid) => {
      try {
        const r = await aiApi.getExecutionStatus(aid)
        if (r.execution_status === 'pending' || r.execution_status === 'running') {
          pendingAuditIds.value.add(aid)
        }
      } catch {
        // 单个失败不影响整体
      }
    }),
  )
  if (pendingAuditIds.value.size > 0) {
    startPendingPolling()
  }
}

function startPendingPolling() {
  if (pendingPollingEnabled.value) return
  pendingPollingEnabled.value = true
  pendingPollTimer = setInterval(async () => {
    if (pendingAuditIds.value.size === 0) {
      stopPendingPolling()
      return
    }
    const ids = Array.from(pendingAuditIds.value)
    for (const aid of ids) {
      try {
        const r = await aiApi.getExecutionStatus(aid)
        const s = r.execution_status
        if (s === 'success' || s === 'failed' || s === 'timeout' || s === 'cancelled') {
          pendingAuditIds.value.delete(aid)
          // 重新拉一次消息，让 sql_result 卡片渲染
          if (activeSessionId.value != null) {
            loadMessages(activeSessionId.value).catch(() => {
              /* 静默 */
            })
          }
        }
      } catch {
        // 单次轮询失败不打断
      }
    }
  }, 3000)
}

function stopPendingPolling() {
  pendingPollingEnabled.value = false
  if (pendingPollTimer != null) {
    clearInterval(pendingPollTimer)
    pendingPollTimer = null
  }
}
</script>
