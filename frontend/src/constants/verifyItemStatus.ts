/**
 * Verify item / port reachability status 标签与 badge 颜色集中化。
 *
 * I2 (PR review 2026-06-20): 3 个 Vue 组件硬编码重复 status 颜色/文案 →
 * 抽到 constants 模块统一管理。
 *
 * Verify item 的 status 集合与 proposal 不同，复用 proposalStatus 会语义错位。
 *
 * 业务含义（collector_service + drift_detection）：
 * - verified/collected/success/reachable — 已通过
 * - missing/failed/unreachable           — 失败
 * - skipped                              — 跳过（含 4 个 SKIP_REASON_* code）
 */

const BADGE_BASE = 'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium'

const SUCCESS_BADGE = `${BADGE_BASE} border-emerald-500 text-emerald-700`
const FAIL_BADGE = `${BADGE_BASE} border-red-500 text-red-700`
const SKIPPED_BADGE = `${BADGE_BASE} border-amber-500 text-amber-700`
const DEFAULT_BADGE = `${BADGE_BASE} border-outline-variant text-on-surface-variant`

export function verifyItemStatusBadge(s: string | null | undefined): string {
  if (!s) return DEFAULT_BADGE
  if (s === 'verified' || s === 'collected' || s === 'success' || s === 'reachable') {
    return SUCCESS_BADGE
  }
  if (s === 'missing' || s === 'failed' || s === 'unreachable') {
    return FAIL_BADGE
  }
  if (s === 'skipped') return SKIPPED_BADGE
  return DEFAULT_BADGE
}
