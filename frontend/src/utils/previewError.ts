/**
 * C16-F2c1 reason-aware preview error mapper.
 *
 * 把 aiApi.sqlPreview 的 AxiosError 映射成可读的中文文案。
 *
 * 触发场景:
 * - Chat.vue onSend → /ai/sql/preview (instance_sql 模式)
 *
 * 后端 detail 结构（backend/app/api/ai.py:531-538 + 515-524）:
 *   { code: "snapshot_unavailable", reason: "snapshot_expired", message: "..." }
 *   { code: "preview_incomplete_retry_required", user_message_id: 123, message: "..." }
 *   { code: "chat_instance_not_accessible", message: "..." }
 *
 * 历史变更:
 * - 2026-07-09 (snapshot_expired 修复): reason-aware 区分 4 种 snapshot 状态
 *   → 用户看到与实际根因匹配的处置文案
 */

interface AxiosLikeResponse {
  status?: number
  data?: { detail?: unknown }
}

interface AxiosLikeError {
  response?: AxiosLikeResponse
}

interface PreviewErrorDetailObj {
  code?: string
  message?: string
  reason?: string
  user_message_id?: number
}

function extractDetailString(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { msg?: string; message?: string }) => d?.msg || d?.message || '')
      .filter(Boolean)
      .join('；')
  }
  return null
}

/**
 * 把 sqlPreview 抛出的 AxiosError 翻译成中文文案。
 *
 * 409 snapshot_unavailable reason 分支（plan §11.4 + C16-F2c1 reason-aware）:
 * - snapshot_expired     : 已有 snapshot.success 但 expires_at 已过 (TTL 24h)
 *                          → 用户需在实例详情页重新触发 Schema 采集
 * - snapshot_not_current : 已有新 snapshot.pending/running 抢占 is_current
 *                          → 等待当前采集完成后再试
 * - snapshot_not_success : 当前最新 snapshot 是 pending/running/failed
 *                          → 等待最新一次采集回调完成后再试
 * - no_snapshot          : 该 instance 尚未采集过
 *                          → 用户需在实例详情页触发 Schema 采集
 */
export function describePreviewError(err: unknown): string {
  const ax = err as AxiosLikeError | null
  const status = ax?.response?.status
  const detail = ax?.response?.data?.detail
  const detailStr = extractDetailString(detail)
  const detailObj =
    detail && typeof detail === 'object' && !Array.isArray(detail)
      ? (detail as PreviewErrorDetailObj)
      : null
  const codeMsg = detailObj?.message || null
  const code = detailObj?.code || null

  if (status === 403)
    return `会话无权访问（403）：${codeMsg || detailStr || 'session 不属于当前用户'}`
  if (status === 404)
    return `会话或实例不存在（404）：${codeMsg || detailStr || '检查 session_id / instance_id'}`
  if (status === 409) {
    if (code === 'preview_incomplete_retry_required') {
      // 旧请求事务中断（user_message 落库但 audit 缺失）
      // 前端 onSend 每次用新 UUID，新请求会走完整流程
      const umid = detailObj?.user_message_id
      return umid
        ? `上次请求未完成（user_message #${umid} 已被记录但 audit 未落库）。请直接按 Enter 重发，前端会用新 client_request_id 走完整流程。`
        : '上次请求未完成（事务中断）。请直接按 Enter 重发。'
    }
    if (code === 'snapshot_unavailable') {
      const reason = detailObj?.reason || 'unknown'
      if (reason === 'snapshot_expired') {
        return `Schema 快照已过期（409 snapshot_expired，TTL 默认 24h）：请在实例详情页重新触发 Schema 采集。`
      }
      if (reason === 'snapshot_not_current') {
        return `Schema 快照已被新采集覆盖（409 snapshot_not_current）：请等待当前采集完成后再试。`
      }
      if (reason === 'snapshot_not_success') {
        return `Schema 快照尚未就绪（409 snapshot_not_success）：请等待最新一次采集回调完成后再试。`
      }
      return `Schema 快照不可用（409 ${reason}）：请先在实例详情页触发 Schema 采集。`
    }
    return `请求冲突（409）：${codeMsg || detailStr || '稍后重试'}`
  }
  if (status === 422)
    return `参数校验失败（422）：${codeMsg || detailStr || '检查 mode / bound_instance_id / instance_id 一致性'}`
  if (status === 502)
    return `Dify 服务不可达（502）：${codeMsg || detailStr || '稍后重试'}`
  if (status === 503) return `AI SQL Preview 未启用（AI_SQL_PREVIEW_ENABLED=false）`
  if (status === 504)
    return `Dify 调用超时（504）：${codeMsg || detailStr || '稍后重试或换更短的问题'}`
  return `${codeMsg || detailStr || 'SQL Preview 失败'}`
}