<template>
  <span
    class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium"
    :class="resolvedClass"
    :title="resolvedTitle"
  >
    <span class="material-symbols-outlined text-[12px] leading-none">{{ resolvedIcon }}</span>
    {{ labelText }}
  </span>
</template>

<script setup lang="ts">
/**
 * AI Copilot — Chat 消息状态徽章
 *
 * 状态机（对齐 backend app/models/ai.py ChatMessage.status）：
 *   pending  - Dify 调用中
 *   completed - 成功
 *   failed   - 失败（error_code / error_message 有值）
 *   stale    - 处理超时（processing_expires_at 已过），需刷新或重新发送
 */
import { computed } from 'vue'

type Status = 'pending' | 'completed' | 'failed' | 'stale'

const props = withDefaults(defineProps<{
  status: Status
  /** 自定义文案（可选；缺省用 status 自身） */
  label?: string
}>(), { label: '' })

interface Resolved {
  cls: string
  icon: string
  text: string
  title: string
}

const RESOLVED: Record<Status, Resolved> = {
  pending: {
    cls: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
    icon: 'hourglass_top',
    text: '处理中',
    title: 'Dify 调用进行中',
  },
  completed: {
    cls: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
    icon: 'check_circle',
    text: '已完成',
    title: '消息已成功完成',
  },
  failed: {
    cls: 'border-red-400/30 bg-red-400/10 text-red-200',
    icon: 'error',
    text: '失败',
    title: '消息处理失败',
  },
  stale: {
    cls: 'border-slate-400/30 bg-slate-400/10 text-slate-300',
    icon: 'history',
    text: '已过期',
    title: '处理超时（stale），建议刷新或重新发送',
  },
}

const resolvedClass = computed(() => RESOLVED[props.status]?.cls ?? 'border-slate-400/30 bg-slate-400/10 text-slate-300')
const resolvedIcon = computed(() => RESOLVED[props.status]?.icon ?? 'help')
const resolvedTitle = computed(() => RESOLVED[props.status]?.title ?? props.status)
const labelText = computed(() => props.label || RESOLVED[props.status]?.text || props.status)
</script>
