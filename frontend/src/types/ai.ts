/**
 * AI Copilot — Phase 3.6
 *
 * 对齐 backend/app/schemas/ai.py (Chat) + backend/app/api/ai.py CapabilitiesResponse。
 * 当前仅包含 Chat 部分（C4）；后续 commit 追加 SQL Preview / Execute / Inspection AI 等。
 */

// =============================================================================
// Capabilities（GET /api/v1/ai/capabilities）
// =============================================================================

/**
 * AI Copilot 能力声明。启动时拉取一次，前端按能力灰度菜单与按钮。
 *
 * Notes:
 * - 严禁在 capabilities 中暴露 API Key / Dify URL / 内部模型配置（plan §11）
 * - stream_enabled 首版固定 false（SSE / 打字流留待后续）
 */
export interface AiCapabilities {
  chat_enabled: boolean
  sql_preview_enabled: boolean
  sql_execution_enabled: boolean
  report_analysis_enabled: boolean
  report_export_ai_enabled: boolean
  stream_enabled: boolean
  sql_supported_db_types: string[]
}

// =============================================================================
// Chat — Session
// =============================================================================

/** 创建新会话请求（可选 title）。 */
export interface AiChatSessionCreateRequest {
  title?: string | null
}

/** 会话响应。 */
export interface AiChatSession {
  id: number
  session_code: string
  user_id?: string | null
  title: string
  dify_conversation_id?: string | null
  model_provider: string
  message_count: number
  last_message_at?: string | null
  created_at: string
  updated_at: string
}

/** 会话列表响应。 */
export interface AiChatSessionListResponse {
  items: AiChatSession[]
  total: number
}

// =============================================================================
// Chat — Message
// =============================================================================

/**
 * 发送消息请求（前端调用核心）。
 *
 * 关键字段：
 * - client_request_id: 前端生成的 UUID（crypto.randomUUID），用于幂等
 * - current_page: 白名单页面标识（ai_chat / inspection_report / …）
 */
export interface AiChatMessageSendRequest {
  client_request_id: string
  query: string
  current_page?: string | null
}

/** 单条消息响应。 */
export interface AiChatMessage {
  id: number
  session_id: number
  user_id?: string | null
  client_request_id?: string | null
  role: 'user' | 'assistant' | 'system'
  message_type: 'chat' | 'sql_preview' | 'sql_result' | 'error'
  status: 'pending' | 'completed' | 'failed' | 'stale'
  content?: string | null
  parent_message_id?: number | null
  metadata_json?: Record<string, unknown>
  dify_task_id?: string | null
  workflow_run_id?: string | null
  elapsed_ms?: number | null
  total_tokens?: number | null
  error_code?: string | null
  error_message?: string | null
  processing_started_at?: string | null
  processing_expires_at?: string | null
  attempt_count: number
  created_at: string
  updated_at: string
}

/** 消息历史响应。 */
export interface AiChatMessageListResponse {
  items: AiChatMessage[]
  total: number
}

/**
 * 发送消息响应（user + assistant 两条）。
 *
 * assistant_message 可能为 null — 同一 client_request_id 命中历史 user 但
 * assistant 未建时（事务 1 中途异常的边界场景）。前端应做 null 判断。
 */
export interface AiChatSendResponse {
  user_message: AiChatMessage
  assistant_message: AiChatMessage | null
  idempotent_replay: boolean
}
