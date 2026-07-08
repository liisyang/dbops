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

/**
 * 创建新会话请求。
 *
 * C16-F2a 扩展（plan §21.2 P0-1 不可变绑定）：
 * - mode:              'general'（普通多轮） / 'instance_sql'（实例绑定 SQL Copilot）
 * - bound_instance_id: 当 mode='instance_sql' 时必填
 *                      当 mode='general' 时必须不传（传了 422）
 * - source_page:       来源页面（落 metadata_json；不影响行为）
 */
export interface AiChatSessionCreateRequest {
  title?: string | null
  mode?: 'general' | 'instance_sql'
  bound_instance_id?: number | null
  source_page?: string | null
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
  // C16-F2a：chat_mode + bound_instance_id 让前端可路由入口（plan §21.2）
  chat_mode?: 'general' | 'instance_sql'
  bound_instance_id?: number | null
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
 * POST /api/v1/ai/sql/preview 请求（plan §5.2 + §5.3 + C16-F2b）。
 *
 * C16-F2b 字段收紧（plan §21.3 C16-3 — Chat 流强制）：
 * - session_id:        必填；消费 chat session.id，鉴权 session.user_id + chat_mode='instance_sql'
 * - client_request_id: 必填；UUID 幂等键（同 session+UUID 重复请求返回原 audit）
 * - message_id:        移除；由 service 内部生成 user_message 后回填 audit.message_id
 * - instance_id:       目标实例；后端派生 db_type_code，前端不直接传
 * - database_name:     可选；留空时 service fallback 到 '<default>'
 * - user_question:     用户原始问题，传给 Dify sql-generator workflow
 * - current_page:      白名单页面标识（ai_chat / instance_detail 等）
 */
export interface AiSqlPreviewRequest {
  // === C16-F2b 必填 ===
  session_id: number
  client_request_id: string
  // === C12 既有 ===
  instance_id: number
  database_name?: string | null
  user_question: string
  current_page?: string | null
}

/**
 * POST /api/v1/ai/sql/preview 响应（plan §5.2 + §5.3 + §19 状态机 + C16-F2b）。
 *
 * C16-F2b 新增字段（plan §21.3 C16-3 — Chat 流耦合）：
 * - session_id:          chat session.id（与 request 一致）
 * - user_message_id:     ai_chat_message.id（role='user'，content=user_question）
 * - preview_message_id:  ai_chat_message.id（role='assistant'，message_type='sql_preview_link'）
 * - idempotent_replay:   client_request_id 命中已有 user message → 返回原三元组
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
  // === C16-F2b 新增 ===
  session_id: number
  user_message_id: number
  preview_message_id: number
  idempotent_replay: boolean

  // 核心结果
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
// SQL Result 独立 API（C16-5 P0-3 — plan §21.3）
// =============================================================================

/**
 * GET /api/v1/ai/sql/executions/{audit_id}/result 响应（plan §21.3 C16-5）。
 *
 * 与 /audit/{id}/execution 的区别：
 *   - /execution 返回状态机 + 元数据（轻量，前端轮询用）
 *   - /result 返回完整 columns + rows（重量，可能 1MB+）
 *
 * 数据源（service 层 fallback 链）：
 *   1. ai_chat_message.content (message_type='sql_result') — callback 规范化
 *   2. CollectorRunItem.raw_result — callback 失败/未落 message 的极端 fallback
 *
 * 关键字段：
 *   - columns:        字符串列表（敏感列保留原名 + masked_columns 标记）
 *   - rows:           list[list[Any]]；敏感列 cell 已替换为 "***"
 *   - returned_rows:  实际返回行数（受 limit/offset 影响）
 *   - row_count:      audit.row_count（callback 报告的总行数）
 *   - truncated:      true 表示还有更多行未返回（受 limit 限制）
 *   - masked_columns: 被掩码的列名列表
 */
export interface AiSqlExecutionResultResponse {
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
  executed_at?: string | null
  error_message?: string | null
  collector_run_id?: number | null
  awx_job_id?: number | null

  // P0-3 核心：实际数据
  columns: string[]
  rows: Array<Array<string | number | boolean | null>>
  returned_rows: number
  truncated: boolean
  masked_columns: string[]
}

/**
 * GET /api/v1/ai/sql/executions/{audit_id}/result 查询参数。
 *
 * - limit:  最大返回行数（后端 ge=1, le=200；默认 100）
 * - offset: 分页偏移（后端 ge=0；默认 0）
 *
 * 注：前端仅透传给 query string；后端做边界校验，越界返 422。
 */
export interface AiSqlExecutionResultParams {
  limit?: number
  offset?: number
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
 * sql_preview_link chat message 解析后的展示数据。
 *
 * C16-F2c 调整：F2b 把 preview_payload 写到 content JSON（passed 包含 approved_sql 等；
 * rejected 包含 reason）。前端从 content + metadata_json 合并解析。
 *
 * ChatMessageBubble.vue previewLinkMeta 消费此 interface。
 */
export interface AiSqlPreviewLinkMetadata {
  audit_id: number
  instance_id: number
  database_name?: string | null
  approved_sql: string
  approved_sql_hash?: string | null
  schema_policy_hash?: string | null
  preview_safety_status: 'passed' | 'rejected'
  /** rejected 时显示的拒绝原因（F2b 落地在 content JSON 的 reason 字段） */
  reason?: string | null
}
