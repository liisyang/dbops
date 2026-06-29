/**
 * AI 文本处理工具（Phase 3.6 AI Copilot — refactor: hide ``）
 *
 * 与后端 `backend/app/services/ai_text.py` 行为一致：
 * - 推理模型（DeepSeek R1 / o1 / o3-mini 等）可能把 ``...`` 混入可见 answer
 * - 兜底剥离，避免历史脏数据 / 其它端点漏剥离时泄露给用户
 *
 * 设计要点：
 * - 纯函数，零依赖
 * - 空值安全（Null / Undefined → ''）
 * - 与 backend strip_think_blocks 行为完全对齐（DOTALL + 非贪婪 + 折叠空行）
 */

const THINK_BLOCK_RE = /\<think\>[\s\S]*?\<\/think\>/g
const BLANK_LINES_RE = /\n{3,}/g

/**
 * 剥离 AI 文本中的 `` 推理过程块。
 *
 * @example
 *   stripThinkBlocks('\<think\>我先思考\<\/think\>你好') // → '你好'
 *   stripThinkBlocks(null)                              // → ''
 */
export function stripThinkBlocks(text: string | null | undefined): string {
  if (!text) return ''
  const noThink = text.replace(THINK_BLOCK_RE, '')
  const collapsed = noThink.replace(BLANK_LINES_RE, '\n\n')
  return collapsed.trim()
}

/** 判断文本是否包含 `` 块（用于埋点 / 调试）。 */
export function hasThinkBlock(text: string | null | undefined): boolean {
  if (!text) return false
  return THINK_BLOCK_RE.test(text)
}
