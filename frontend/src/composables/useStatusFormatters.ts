/**
 * Business status formatting utilities for lifecycle management.
 * Centralizes status label, badge styling, and status transition formatting.
 * Used by Assets.vue, BusinessSystemDetail.vue, and other asset detail views.
 */

type Status = string | null | undefined

/**
 * Normalize status value to standard format and get display label.
 * Supports multiple status value representations (EN, CN, numeric).
 */
export function formatStatusLabel(status: Status): string {
  const normalized = (status || '').trim().toLowerCase()
  if (!normalized) return '-'

  // Building state
  if (['building', 'build', 'draft', 'preparing', '建设中'].includes(normalized)) {
    return '建设中'
  }

  // Pending state
  if (['pending', 'ready', '待上线', '上线待定'].includes(normalized)) {
    return '待上线'
  }

  // Active state
  if (['active', 'online', 'up', 'on', 'published', 'enabled', '1', '已上线', '在用'].includes(normalized)) {
    return '已上线'
  }

  // Retired state
  if (['retired', 'inactive', 'offline', 'down', 'off', 'disabled', '0', '已下线', '下线', '停用'].includes(normalized)) {
    return '已下线'
  }

  return status || '-'
}

/**
 * Get Tailwind CSS classes for status badge styling.
 * Colors follow MD3 design tokens: sky (building), amber (pending), emerald (active), slate (retired).
 */
export function getStatusBadgeClass(status: Status): string {
  const normalized = (status || '').trim().toLowerCase()

  // Building state - sky blue
  if (['building', 'build', 'draft', 'preparing', '建设中'].includes(normalized)) {
    return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  }

  // Pending state - amber/orange
  if (['pending', 'ready', '待上线', '上线待定'].includes(normalized)) {
    return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  }

  // Active state - emerald/green
  if (['active', 'online', 'up', 'on', 'published', 'enabled', '1', '已上线', '在用'].includes(normalized)) {
    return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  }

  // Retired state - slate/gray
  if (['retired', 'inactive', 'offline', 'down', 'off', 'disabled', '0', '已下线', '下线', '停用'].includes(normalized)) {
    return 'border-slate-400/30 bg-slate-400/10 text-slate-200'
  }

  // Default state
  return 'border-white/10 bg-white/5 text-slate-200'
}

/**
 * Format a status transition for display (e.g., "building -> pending").
 */
export function formatStatusTransition(beforeStatus: Status, afterStatus: Status): string {
  const beforeLabel = formatStatusLabel(beforeStatus)
  const afterLabel = formatStatusLabel(afterStatus)

  if (beforeLabel === '-' && afterLabel === '-') return '状态变更信息为空'
  if (beforeLabel === '-') return `状态 -> ${afterLabel}`
  if (afterLabel === '-') return `${beforeLabel} -> 状态`
  return `${beforeLabel} -> ${afterLabel}`
}

/**
 * Format contact type to display label.
 */
export function formatContactTypeLabel(contactType: string): string {
  if (contactType === 'BUSINESS_MANAGER') return '业务主管'
  if (contactType === 'DBA_OWNER') return 'DBA负责人'
  return contactType || '联系人'
}

/**
 * Inspection task/result status badge classes.
 * Centralizes the palette so phase-3.4 inspection views stay consistent.
 */
export function getInspectionStatusClass(status: Status): string {
  const normalized = (status || '').trim().toLowerCase()
  if (normalized === 'success') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (normalized === 'partial_success') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (normalized === 'failed' || normalized === 'callback_failed' || normalized === 'timeout') {
    return 'border-red-400/30 bg-red-400/10 text-red-200'
  }
  if (normalized === 'running' || normalized === 'launched' || normalized === 'pending') {
    return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  }
  if (normalized === 'cancelled' || normalized === 'canceled') {
    return 'border-slate-400/30 bg-slate-400/10 text-slate-200'
  }
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}
