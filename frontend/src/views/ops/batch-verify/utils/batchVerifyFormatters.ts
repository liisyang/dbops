/*
 * batchVerifyFormatters — 批量校验视图专用格式化工具
 *
 * 集中以下职责：
 * 1. 状态徽章 / 文案格式化（批量批次 / dispatch / 执行项）
 * 2. 时间 / 时长格式化（统一走 @/utils/timezone，避免本地实现重复）
 * 3. 终态判断 / 取消谓词（统一收口 NewType brand set 的 `as never` 转换）
 * 4. 执行项派生字段（结果 / 消息 / facts 计数）
 * 5. route.query 取值 helper（统一 `string | string[] | null | undefined` → string）
 *
 * 设计原则：
 * - 纯函数，无副作用，无外部状态
 * - 调用方无需接触 NewType brand set（TERMINAL_BATCH_STATUS_SET 仅在本文件出现）
 * - 与后端 BATCH_TERMINAL_STATUSES + 'canceled' 兼容拼写保持一致
 */

import type { BatchRunItemRow, BatchRunRow } from '@/types/api'
import { TERMINAL_BATCH_STATUS_SET } from '@/types/api'
import { formatDuration as formatDurationTz, formatInTz } from '@/utils/timezone'

// ── 时间 / 时长 ────────────────────────────────────────────────────────

/** 包装 formatInTz，统一空值降级为 '—' */
export function formatTime(val: string | null | undefined): string {
  if (!val) return '—'
  return formatInTz(val)
}

/** 直接复用 timezone.formatDuration（统一 Asia/Shanghai 解析） */
export const formatDuration = formatDurationTz

// ── 状态文案 / 徽章 ─────────────────────────────────────────────────────

/**
 * 9 种 batch / dispatch 状态文案
 * 匹配后端 BATCH_TERMINAL_STATUSES + 运行中状态
 */
export function formatBatchStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return '等待中'
  if (s === 'launched' || s === 'launching') return '启动中'
  if (s === 'running' || s === 'dispatching') return '执行中'
  if (s === 'success') return '已完成'
  if (s === 'partial_success') return '部分成功'
  if (s === 'failed') return '失败'
  if (s === 'cancelled' || s === 'canceled') return '已取消'
  return status || '-'
}

/** 9 种 batch / dispatch 状态徽章 class */
export function getBatchStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'launched' || s === 'launching' || s === 'dispatching') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'running') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'success') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'partial_success') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'failed') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'cancelled' || s === 'canceled') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

/** 5 种 item 状态徽章 class */
export function getItemStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'success') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'failed' || s === 'timeout') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'skipped') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  if (s === 'running') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'pending') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

/** 5 种 item 状态文案 */
export function formatItemStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'success') return '成功'
  if (s === 'failed') return '失败'
  if (s === 'skipped') return '跳过'
  if (s === 'pending') return '等待中'
  if (s === 'running') return '执行中'
  if (s === 'timeout') return '超时'
  return status || '-'
}

/** 显式 'cancelled' / 'canceled' 谓词 — 用于模板判断是否展示 cancelled_at 时间戳 */
export function isCancelled(status: string | null | undefined): boolean {
  const s = (status || '').toLowerCase()
  return s === 'cancelled' || s === 'canceled'
}

// ── 执行项派生字段 ─────────────────────────────────────────────────────

/** 标准化执行项的"结果"列展示值 */
export function formatItemResult(item: BatchRunItemRow): string {
  const raw = (item.raw_result as Record<string, unknown> | null | undefined) || {}
  if ((item.status || '').toLowerCase() === 'skipped') {
    const skipReason = typeof raw.skip_reason === 'string' ? raw.skip_reason : null
    return skipReason || item.result_message || 'skipped'
  }
  return (
    item.result_status ||
    item.candidate_state ||
    (typeof raw.error_code === 'string' ? raw.error_code : null) ||
    item.status
  )
}

/** 标准化执行项的"消息"列展示值 */
export function formatItemMessage(item: BatchRunItemRow): string {
  const raw = (item.raw_result as Record<string, unknown> | null | undefined) || {}
  return (
    item.result_message ||
    (typeof raw.skip_reason === 'string' ? raw.skip_reason : null) ||
    (typeof raw.error_message === 'string' ? raw.error_message : null) ||
    '-'
  )
}

/** 提取执行项的 facts 数（无 facts 返回 0） */
export function getItemFactsCount(item: BatchRunItemRow): number {
  const facts = (item.raw_result as Record<string, unknown> | null | undefined)?.facts
  return Array.isArray(facts) ? facts.length : 0
}

// ── 终态 / 取消谓词 ────────────────────────────────────────────────────

/**
 * 是否终态（success / partial_success / failed / timeout / callback_failed / cancelled）
 *
 * 关键 null-safe：空字符串 / null / undefined 短路返回 `false`（语义：还没拿到状态）
 * NewType brand set 的 `as never` 类型收口集中在这里，调用方拿 `boolean` 不接触类型问题
 */
export function isTerminalBatchStatus(status: string | null | undefined): boolean {
  if (!status) return false
  return TERMINAL_BATCH_STATUS_SET.has(status.toLowerCase() as never)
}

/** 详情页 / BatchItemTable 谓词：当前状态是否允许"取消批次" */
export function canCancelBatch(status: string | null | undefined): boolean {
  if (!status) return false
  const s = status.toLowerCase()
  return s === 'pending' || s === 'dispatching' || s === 'running'
}

// ── 摘要派生 ──────────────────────────────────────────────────────────

/** 成功率（百分比，0-100 整数）；无数据返回 0 */
export function calculateSuccessRate(batch: BatchRunRow | null | undefined): number {
  if (!batch || !batch.total_item_count) return 0
  const s = batch.success_item_count || 0
  return Math.round((s / batch.total_item_count) * 100)
}

/** 成功率 class（>=90 绿 / >=50 琥珀 / 否则 红） */
export function getSuccessRateClass(rate: number): string {
  if (rate >= 90) return 'text-emerald-400'
  if (rate >= 50) return 'text-amber-400'
  return 'text-red-400'
}

// ── route.query 取值 ──────────────────────────────────────────────────

/**
 * 统一收口 `route.query[key]` 的 `string | string[] | null | undefined` 类型
 * 数组取第一个；非数组强转 string；空值返回 ''
 */
export function firstQueryValue(value: unknown): string {
  if (Array.isArray(value)) return String(value[0] ?? '')
  return value == null ? '' : String(value)
}