/**
 * Proposal status 标签与 badge 颜色集中化。
 *
 * I2 (PR review 2026-06-20): 3 个 Vue 组件硬编码重复 status 颜色/文案 →
 * 抽到 constants 模块统一管理。
 *
 * 业务含义（apply_proposal service）：
 * - pending   — 待审（default 状态）
 * - approved  — 已同意
 * - rejected  — 已拒绝
 * - applied   — 已应用
 * - canceled  — 已取消
 */
import type { ProposalStatus } from '@/types/api'

export const PROPOSAL_STATUS_LABEL: Record<ProposalStatus, string> = {
  pending: '待审',
  approved: '已同意',
  rejected: '已拒绝',
  applied: '已应用',
  canceled: '已取消',
}

export const PROPOSAL_STATUS_BADGE: Record<ProposalStatus, string> = {
  pending: 'border-amber-500 text-amber-700',
  approved: 'border-blue-500 text-blue-700',
  rejected: 'border-red-500 text-red-700',
  applied: 'border-emerald-500 text-emerald-700',
  canceled: 'border-outline-variant text-on-surface-variant',
}

const BADGE_BASE = 'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium'

export function proposalStatusLabel(s: string): string {
  return PROPOSAL_STATUS_LABEL[s as ProposalStatus] ?? s
}

export function proposalStatusBadge(s: string): string {
  const color = PROPOSAL_STATUS_BADGE[s as ProposalStatus] ?? 'border-outline-variant text-on-surface-variant'
  return `${BADGE_BASE} ${color}`
}
