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
 * - client_request_id: 前端生成的 UUID（utils/uuid.safeUuid），用于幂等
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
  message_type: 'chat' | 'sql_preview' | 'sql_preview_link' | 'sql_result' | 'error'
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

// =============================================================================
// SQL Preview（C13）
// =============================================================================

/**
 * POST /api/v1/ai/sql/preview 请求（plan §5.2 + §5.3）。
 *
 * 关键字段：
 * - instance_id: 目标实例；后端派生 db_type_code，前端不直接传
 * - database_name: 可选；留空时 service fallback 到 '<default>'
 * - user_question: 用户原始问题，传给 Dify sql-generator workflow
 * - session_id / message_id: 可选；用于关联 ai_chat_session/message
 * - current_page: 白名单页面标识（ai_chat / instance_detail 等）
 */
export interface AiSqlPreviewRequest {
  instance_id: number
  database_name?: string | null
  user_question: string
  session_id?: number | null
  message_id?: number | null
  current_page?: string | null
}

/**
 * POST /api/v1/ai/sql/preview 响应（plan §5.2 + §5.3 + §19 状态机）。
 *
 * preview_safety_status='passed' 时：
 *   - approved_sql + approved_sql_hash 必填（落 ai_sql_audit）
 *   - schema_snapshot_id + schema_policy_hash 必填（Execute 校验）
 *   - audit_id 返回供 Execute 阶段引用
 * preview_safety_status='rejected' 时：
 *   - preview_safety_reason 必填
 *   - errors 列表（Layer 1 / AST 校验错误）
 *   - audit_id 仍可能返回（rejected 也落库用于审计）
 */
export interface AiSqlPreviewResponse {
  audit_id: number
  preview_safety_status: 'passed' | 'rejected'

  // 双轨 SQL
  generated_sql?: string | null
  generated_sql_hash?: string | null
  approved_sql?: string | null
  approved_sql_hash?: string | null

  // 错误信息
  preview_safety_reason?: string | null
  errors: string[]
  warnings: string[]

  // Schema 强绑定
  schema_snapshot_id?: number | null
  schema_policy_hash?: string | null

  // 元数据
  db_type_code: string
  sql_dialect?: string | null
  sql_workflow_version?: string | null
  safety_policy_version?: string | null
  dify_workflow_run_id?: string | null

  // 时间戳
  previewed_at?: string | null
}

// =============================================================================
// SQL Execute（C14）
// =============================================================================

/**
 * POST /api/v1/ai/sql/execute 请求（plan §6.1）。
 *
 * - audit_id: 来自 Preview 阶段已 passed 的 ai_sql_audit.id
 * - force: 强制重跑（仅当 audit.execution_status IN ('pending','running') 时生效）
 */
export interface AiSqlExecuteRequest {
  audit_id: number
  force?: boolean
}

/**
 * POST /api/v1/ai/sql/execute 响应（plan §6.1）。
 *
 * execution_status='running' 表示 AWX 已接单；'failed' 表示 launch 失败
 * （error_message 含 AWX 错误详情）。
 */
export interface AiSqlExecuteResponse {
  audit_id: number
  execution_status:
    | 'not_requested'
    | 'pending'
    | 'running'
    | 'success'
    | 'failed'
    | 'timeout'
    | 'cancelled'
  awx_job_id?: number | null
  awx_job_url?: string | null
  collector_run_id?: number | null
  collector_run_item_id?: number | null
  executed_at?: string | null
  error_message?: string | null
}

/**
 * GET /api/v1/ai/sql/audit/{audit_id}/execution 响应（plan §6.1，前端轮询）。
 *
 * callback 写库后 result_message_id + message_type='sql_result' 才有值。
 */
export interface AiSqlExecutionStatusResponse {
  audit_id: number
  execution_status:
    | 'not_requested'
    | 'pending'
    | 'running'
    | 'success'
    | 'failed'
    | 'timeout'
    | 'cancelled'
  row_count?: number | null
  duration_ms?: number | null
  completed_at?: string | null
  error_message?: string | null
  collector_run_id?: number | null
  awx_job_id?: number | null
  executed_at?: string | null
  // chat message 关联（callback 写库后才有）
  result_message_id?: number | null
  message_type?: 'sql_result' | null
  created_at: string
}

// =============================================================================
// SQL Result 渲染（C14 Chat 集成）
// =============================================================================

/**
 * sql_result chat message 的 metadata_json 内容（plan §6.5）。
 *
 * 列与行直接来自 collector_client 的 raw_result（dbops 端透传，不做改写）。
 */
export interface AiSqlResultMetadata {
  audit_id: number
  execution_status:
    | 'not_requested'
    | 'pending'
    | 'running'
    | 'success'
    | 'failed'
    | 'timeout'
    | 'cancelled'
  row_count: number
  duration_ms: number
}

/**
 * sql_result chat message 的 content JSON（callback 落库时序列化）。
 */
export interface AiSqlResultPayload {
  columns: string[]
  rows: Array<Array<string | number | boolean | null>>
  row_count: number
  duration_ms: number
  status: string
  error_message?: string | null
  executed_at?: string | null
}

/**
 * sql_preview_link chat message 的 metadata_json（preview 阶段写入，
 * Chat 集成时把 approved_sql 卡片挂到 assistant message 上 + 提供执行入口）。
 */
export interface AiSqlPreviewLinkMetadata {
  audit_id: number
  instance_id: number
  database_name?: string | null
  approved_sql: string
  approved_sql_hash?: string | null
  schema_policy_hash?: string | null
  preview_safety_status: 'passed' | 'rejected'
}
