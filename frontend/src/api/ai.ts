/**
 * AI Copilot — Phase 3.6
 *
 * 对齐 backend/app/api/ai.py：
 * - GET  /v1/ai/capabilities — 启动时拉取，灰度菜单
 * - POST /v1/ai/chat/sessions — 创建会话
 * - GET  /v1/ai/chat/sessions — 当前用户的会话列表
 * - POST /v1/ai/chat/sessions/{session_id}/messages — 发送消息（核心）
 * - GET  /v1/ai/chat/sessions/{session_id}/messages — 历史
 *
 * C4 范围仅 Chat；后续 commit 追加 SQL Preview / Execute / Inspection AI 等。
 */
import request from './request'
import type {
  AiCapabilities,
  AiChatMessageListResponse,
  AiChatMessageSendRequest,
  AiChatSendResponse,
  AiChatSession,
  AiChatSessionCreateRequest,
  AiChatSessionListResponse,
} from '@/types/ai'

export const aiApi = {
  /** 启动时拉取 capabilities（无需登录），灰度菜单与按钮。 */
  getCapabilities: (): Promise<AiCapabilities> =>
    request.get('/v1/ai/capabilities'),

  /** 创建新会话（用户首次发消息前调用，或前端主动"新建会话"）。 */
  createSession: (data: AiChatSessionCreateRequest = {}): Promise<AiChatSession> =>
    request.post('/v1/ai/chat/sessions', data),

  /**
   * 列出当前用户的会话（最近优先）。
   * suppressErrorToast: Chat.vue 列表挂载失败时静默降级到 []，避免每次进入页面都弹错误。
   */
  listSessions: (
    params?: { limit?: number },
    options?: { suppressErrorToast?: boolean },
  ): Promise<AiChatSessionListResponse> =>
    request.get('/v1/ai/chat/sessions', {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),

  /**
   * 发送消息（核心端点）。
   *
   * 幂等性：相同 `client_request_id` 重复请求会返回首次结果（idempotent_replay=true）。
   * 错误码（plan §11）：
   *   404 ChatSessionNotFoundError
   *   409 ChatConcurrentPendingError
   *   422 参数校验失败
   *   502 Dify 不可用或返回错误
   *   503 AI_CHAT_ENABLED=false
   *   504 Dify 调用超时
   */
  sendMessage: (
    sessionId: number | string,
    data: AiChatMessageSendRequest,
  ): Promise<AiChatSendResponse> =>
    request.post(`/v1/ai/chat/sessions/${sessionId}/messages`, data),

  /**
   * 列出会话消息历史（created_at ASC）。
   * suppressErrorToast: Chat.vue 进入会话时静默拉取，失败由空态兜底。
   */
  listMessages: (
    sessionId: number | string,
    params?: { limit?: number },
    options?: { suppressErrorToast?: boolean },
  ): Promise<AiChatMessageListResponse> =>
    request.get(`/v1/ai/chat/sessions/${sessionId}/messages`, {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
}

// =============================================================================
// 单例 capabilities 缓存（启动时拉一次）
// =============================================================================

let _capabilitiesCache: AiCapabilities | null = null
let _capabilitiesPromise: Promise<AiCapabilities> | null = null

/**
 * 拉取并缓存 capabilities。
 *
 * 设计：
 * - 失败时返回"全 false"占位（不阻塞 UI，让 Layout.vue 直接隐藏 AI 入口）
 * - 并发安全：同一 tick 内多次调用复用同一 in-flight Promise
 * - 测试或热重载可通过 `__resetCapabilitiesCacheForTest` 强制重拉
 */
export async function loadAiCapabilities(force = false): Promise<AiCapabilities> {
  if (force) {
    _capabilitiesCache = null
    _capabilitiesPromise = null
  }
  if (_capabilitiesCache) return _capabilitiesCache
  if (!_capabilitiesPromise) {
    _capabilitiesPromise = aiApi
      .getCapabilities()
      .then((caps) => {
        _capabilitiesCache = caps
        return caps
      })
      .catch(() => {
        // 失败占位：全 false（前端静默隐藏 AI 入口，不弹错误）
        const fallback: AiCapabilities = {
          chat_enabled: false,
          sql_preview_enabled: false,
          sql_execution_enabled: false,
          report_analysis_enabled: false,
          report_export_ai_enabled: false,
          stream_enabled: false,
          sql_supported_db_types: [],
        }
        _capabilitiesCache = fallback
        return fallback
      })
      .finally(() => {
        _capabilitiesPromise = null
      })
  }
  return _capabilitiesPromise
}

/** 测试 / 热重载专用：清空缓存。 */
export function __resetCapabilitiesCacheForTest(): void {
  _capabilitiesCache = null
  _capabilitiesPromise = null
}
