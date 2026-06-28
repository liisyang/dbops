<template>
  <OpsPage>
    <OpsPageHeader
      title="AI Copilot"
      subtitle="基于 Dify 的智能运维对话（C5 落地交互界面）"
    />

    <div class="grid gap-4 lg:grid-cols-[280px_1fr]">
      <!-- 左侧：会话侧栏 -->
      <OpsSectionCard class="lg:min-h-[calc(100vh-220px)]">
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
            <div>
              <h2 class="text-base font-semibold text-on-surface">
                {{ activeSessionTitle }}
              </h2>
              <p class="text-xs text-on-surface-variant">
                <span v-if="activeSessionId">
                  会话 #{{ activeSessionId }} · {{ activeMessages.length }} 条消息
                </span>
                <span v-else>请选择左侧会话，或点击"新建"开始对话</span>
              </p>
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
            title="还没有选中的会话"
            description="在左侧选择一个历史会话，或点击右上角“新建”开始一段新的对话。"
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
            description="在下方的输入框中输入问题，按 Enter 发送。"
          />
        </div>

        <!-- 消息流 -->
        <div v-else class="min-h-[400px] flex-1 space-y-4 overflow-y-auto pr-1">
          <ChatMessageBubble
            v-for="m in activeMessages"
            :key="m.id"
            :role="m.role"
            :status="m.status"
            :content="m.content"
            :created-at="formatTime(m.created_at)"
            :error-code="m.error_code"
            :error-message="m.error_message"
            :elapsed-ms="m.elapsed_ms"
            :total-tokens="m.total_tokens"
          />
        </div>

        <!-- 输入框（P4：发送中禁用 + 错误条） -->
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
            :placeholder="sending ? '正在调用 Dify…请稍候' : '输入消息，Enter 发送，Shift+Enter 换行'"
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
 * AI Copilot — 主入口（Phase 3.6 C5-P4）
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
 * 未做（Phase 3.6B）：FAB 浮窗 + 抽屉（用户已确认双入口策略）
 */
import { ref, computed, onMounted } from 'vue'
import { aiApi } from '@/api/ai'
import type { AiChatMessage, AiChatSession } from '@/types/ai'
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

// ---- derived ----
const activeSessionTitle = computed(() => {
  const s = sessions.value.find((x) => x.id === activeSessionId.value)
  return s?.title ?? 'AI Copilot'
})
const activeMessages = computed<AiChatMessage[]>(() => {
  const id = activeSessionId.value
  if (id == null) return []
  return messagesBySession.value[id] ?? []
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

/** P4 真实发送 */
async function onSend(value: string) {
  const sessionId = activeSessionId.value
  if (sessionId == null || sending.value) return

  const clientRequestId = safeUuid()
  const optimistic = buildOptimisticUser(value, clientRequestId)
  appendToSession(sessionId, optimistic)
  sendError.value = null
  sending.value = true

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
onMounted(() => {
  loadSessions()
})
</script>
