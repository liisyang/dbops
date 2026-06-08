<template>
  <OpsSectionCard title="生命周期" subtitle="展示当前状态、阶段流程和历史记录。" icon="timeline">
    <template #actions>
      <div class="flex items-center gap-2">
        <span
          v-if="detail"
          class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium"
          :class="getStatusBadgeClass(detail.status)"
        >
          {{ formatStatusLabel(detail.status) }}
        </span>
        <button
          type="button"
          class="ops-edit-button"
          :disabled="!detail || loading"
          @click="$emit('toggle-history')"
        >
          <span class="material-symbols-outlined text-[14px] leading-none">history</span>
          查看历史{{ history.length ? ` (${history.length})` : '' }}
        </button>
      </div>
    </template>

    <OpsEmptyState
      v-if="!loading && !detail && !error"
      state="empty"
      title="暂无生命周期信息"
      description="请先加载业务系统详情。"
    />

    <div v-else-if="loading && !detail" class="py-6">
      <OpsEmptyState state="loading" title="正在加载生命周期信息" description="正在读取业务系统生命周期状态和历史记录。" />
    </div>

    <div v-else-if="detail" class="space-y-5">
      <!-- Horizontal lifecycle flow with circular stage nodes -->
      <div class="relative overflow-hidden rounded-2xl border border-outline-variant/40 bg-gradient-to-br from-surface-container-low/80 via-surface-container-low/40 to-surface-container-low/80 p-4 md:p-4">
        <div class="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(125,211,252,0.06),transparent_70%)]" />

        <div class="relative flex flex-col gap-4 md:flex-row md:items-start md:justify-between md:gap-2">
          <!-- Connector line (md+ only) -->
          <div class="absolute left-[2.75rem] right-[2.75rem] top-[1.5rem] hidden h-[2px] -translate-y-1/2 rounded-full bg-outline-variant/30 md:block">
            <div
              class="h-full rounded-full bg-gradient-to-r from-sky-400 via-amber-400 to-emerald-400 shadow-[0_0_8px_rgba(56,189,248,0.45)] transition-all duration-700 ease-out"
              :style="{ width: `${activeIndex <= 0 ? 0 : (activeIndex / (stages.length - 1)) * 100}%` }"
            />
          </div>

          <button
            v-for="(stage, idx) in stages"
            :key="stage.id"
            type="button"
            class="group relative z-10 flex flex-1 items-start gap-3 md:flex-col md:items-center md:gap-2 md:text-center"
            @click="$emit('select-stage', stage.id)"
          >
            <div
              class="relative flex h-11 w-11 items-center justify-center rounded-full border-2 transition-all duration-300 group-hover:scale-105"
              :class="circleClass(idx)"
            >
              <span class="material-symbols-outlined text-[18px] leading-none">
                {{ idx < activeIndex ? 'check' : stage.icon }}
              </span>

              <!-- Pulsing ring for current active stage -->
              <span v-if="idx === activeIndex && stage.id === 'active'" class="pointer-events-none absolute inset-0 -m-1 rounded-full">
                <span class="absolute inset-0 animate-ping rounded-full bg-emerald-400/35" />
              </span>

              <!-- Step number badge -->
              <span class="absolute -bottom-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-outline-variant/60 bg-surface-container font-mono text-[8px] text-on-surface-variant">
                {{ idx + 1 }}
              </span>
            </div>

            <div class="flex min-w-0 flex-col text-left md:text-center">
              <span class="text-xs font-medium md:mt-0.5" :class="textClass(idx)">{{ stage.label }}</span>
              <span class="text-[9px] uppercase tracking-[0.14em] text-on-surface-variant">{{ stage.subtitle }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- Selected stage detail + actions -->
      <div class="flex flex-col gap-4 rounded-2xl border border-outline-variant/40 bg-surface-container-low p-4 sm:flex-row sm:items-center sm:justify-between">
        <div class="space-y-1">
          <div class="flex items-center gap-2">
            <span class="size-2 rounded-full" :class="dotClass(activeStage)" />
            <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-on-surface-variant">
              所选节点详情 ({{ activeStageLabel }})
            </p>
          </div>
          <p class="text-xs text-on-surface">{{ activeStageDescription }}</p>
        </div>
        <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:justify-end">
          <button
            v-for="action in stages"
            :key="action.id"
            type="button"
            class="inline-flex h-8 items-center justify-center whitespace-nowrap rounded-full border px-3.5 text-xs font-medium transition-all disabled:cursor-not-allowed disabled:opacity-60"
            :class="actionButtonClass(action.id)"
            :disabled="!detail || loading || submitting"
            @click="$emit('open-action', action.id)"
          >
            {{ action.actionLabel }}
          </button>
        </div>
      </div>

      <!-- Inline action form -->
      <div
        v-if="action"
        class="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4"
      >
        <div class="mb-3 flex items-start justify-between gap-3">
          <div>
            <div class="text-sm font-semibold text-on-surface">{{ actionTitle }}</div>
            <div class="mt-1 text-xs text-on-surface-variant">
              提交后会刷新详情并拉取最新历史记录。
            </div>
          </div>
          <button
            type="button"
            class="ops-secondary-button !h-8 !px-3 !text-xs"
            @click="$emit('close-action')"
          >
            取消
          </button>
        </div>

        <div class="grid gap-3">
          <label class="space-y-1.5 text-sm">
            <span class="field-label">操作原因</span>
            <input
              :value="reason"
              type="text"
              class="field-input"
              placeholder="例如：例行维护 / 业务切换"
              @input="$emit('update:reason', ($event.target as HTMLInputElement).value)"
            />
          </label>
          <label class="space-y-1.5 text-sm">
            <span class="field-label">补充说明</span>
            <textarea
              :value="remark"
              class="field-input min-h-[80px]"
              placeholder="填写本次生命周期变更的简要说明"
              @input="$emit('update:remark', ($event.target as HTMLTextAreaElement).value)"
            ></textarea>
          </label>
          <label class="space-y-1.5 text-sm">
            <span class="field-label">生命周期上下文</span>
            <textarea
              :value="context"
              class="field-input min-h-[80px]"
              placeholder="例如 IP 组、关联说明或其他上下文"
              @input="$emit('update:context', ($event.target as HTMLTextAreaElement).value)"
            ></textarea>
          </label>
        </div>

        <div class="mt-4 flex items-center justify-end gap-3">
          <button type="button" class="ops-secondary-button" @click="$emit('close-action')">
            取消
          </button>
          <button
            type="button"
            class="ops-primary-button"
            :disabled="submitting"
            @click="$emit('submit-action')"
          >
            <span class="material-symbols-outlined text-[18px]">check</span>
            {{ confirmLabel }}
          </button>
        </div>
      </div>

      <!-- History list -->
      <div v-if="showHistory" class="space-y-2">
        <OpsEmptyState
          v-if="!history.length"
          state="empty"
          title="暂无生命周期历史"
          description="当前业务系统还没有生命周期变更记录。"
        />
        <div
          v-for="record in history"
          :key="record.id"
          class="rounded-xl border border-outline-variant/30 bg-surface-container-low px-3 py-2.5"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="text-sm font-medium text-on-surface">{{ record.event_type }}</div>
              <div class="mt-1 text-xs text-on-surface-variant">
                {{ formatStatusTransition(record.before_status, record.after_status) }}
              </div>
            </div>
            <span class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-on-surface-variant">
              {{ record.operated_at }}
            </span>
          </div>
          <div class="mt-2 flex flex-wrap gap-3 text-xs text-on-surface-variant">
            <span v-if="record.operator">操作人：{{ record.operator }}</span>
            <span v-if="record.reason">原因：{{ record.reason }}</span>
            <span v-if="record.remark">说明：{{ record.remark }}</span>
          </div>
        </div>
      </div>
    </div>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { OpsEmptyState, OpsSectionCard } from '@/components/ops'
import { formatStatusLabel, formatStatusTransition, getStatusBadgeClass } from '@/composables/useStatusFormatters'
import type { AssetEventRow, SystemDetail } from '@/types/api'

export type LifecycleStageId = 'building' | 'pending' | 'active' | 'retired'

type StageConfig = {
  id: LifecycleStageId
  label: string
  subtitle: string
  icon: string
  description: string
  actionLabel: string
  activeClass: string
}

const props = defineProps<{
  detail: SystemDetail | null
  loading: boolean
  error: string
  history: AssetEventRow[]
  showHistory: boolean
  action: LifecycleStageId | null
  reason: string
  remark: string
  context: string
  submitting: boolean
  activeStage: LifecycleStageId
}>()

defineEmits<{
  (event: 'toggle-history'): void
  (event: 'select-stage', stage: LifecycleStageId): void
  (event: 'open-action', stage: LifecycleStageId): void
  (event: 'close-action'): void
  (event: 'submit-action'): void
  (event: 'update:reason', value: string): void
  (event: 'update:remark', value: string): void
  (event: 'update:context', value: string): void
}>()

const stages: StageConfig[] = [
  {
    id: 'building',
    label: '建设中',
    subtitle: 'Construction',
    icon: 'construction',
    description: '系统基础环境配置和代码构建阶段。',
    actionLabel: '设为建设中',
    activeClass: '!bg-sky-500/20 !border-sky-400/50 !text-sky-100',
  },
  {
    id: 'pending',
    label: '待上线',
    subtitle: 'Pending',
    icon: 'rocket_launch',
    description: '通过预发测试，准备部署上线。',
    actionLabel: '设为待上线',
    activeClass: '!bg-amber-500/20 !border-amber-400/50 !text-amber-100',
  },
  {
    id: 'active',
    label: '已上线',
    subtitle: 'Online',
    icon: 'check_circle',
    description: '系统正在生产环境提供高可用服务。',
    actionLabel: '标记已上线',
    activeClass: '!bg-emerald-500/20 !border-emerald-400/50 !text-emerald-100',
  },
  {
    id: 'retired',
    label: '已下线',
    subtitle: 'Offline',
    icon: 'power_settings_new',
    description: '业务迁移完成，已安全回收资源并归档。',
    actionLabel: '标记已下线',
    activeClass: '!bg-slate-500/20 !border-slate-400/50 !text-slate-100',
  },
]

const activeIndex = computed(() => stages.findIndex((s) => s.id === props.activeStage))

const activeStageLabel = computed(() => stages.find((s) => s.id === props.activeStage)?.label ?? '-')
const activeStageDescription = computed(() => {
  const stage = stages.find((s) => s.id === props.activeStage)
  if (!stage) return '当前业务系统尚未设置状态。'
  if (!props.detail?.status) return '当前业务系统尚未设置状态。'
  return `${stage.description} 当前业务系统状态为 ${formatStatusLabel(props.detail.status)}。`
})

const actionTitle = computed(() => stages.find((s) => s.id === props.action)?.actionLabel ?? '')
const confirmLabel = computed(() => {
  const label = stages.find((s) => s.id === props.action)?.actionLabel
  return label ? `确认${label}` : '确认提交'
})

type StageColor = {
  ringActive: string
  bgActive: string
  borderActive: string
  textActive: string
  glow: string
  buttonSolid: string
  buttonOutline: string
}

const stageColors: Record<LifecycleStageId, StageColor> = {
  building: {
    ringActive: 'ring-sky-400/40',
    bgActive: 'bg-sky-500/15',
    borderActive: 'border-sky-400/70',
    textActive: 'text-sky-200',
    glow: '',
    buttonSolid: 'border-sky-400/60 bg-sky-500/20 text-sky-100 hover:bg-sky-500/30',
    buttonOutline: 'border-outline-variant/40 bg-transparent text-on-surface-variant hover:border-sky-400/40 hover:text-sky-200',
  },
  pending: {
    ringActive: 'ring-amber-400/40',
    bgActive: 'bg-amber-500/15',
    borderActive: 'border-amber-400/70',
    textActive: 'text-amber-200',
    glow: '',
    buttonSolid: 'border-amber-400/60 bg-amber-500/20 text-amber-100 hover:bg-amber-500/30',
    buttonOutline: 'border-outline-variant/40 bg-transparent text-on-surface-variant hover:border-amber-400/40 hover:text-amber-200',
  },
  active: {
    ringActive: 'ring-emerald-400/50',
    bgActive: 'bg-emerald-500/15',
    borderActive: 'border-emerald-400/80',
    textActive: 'text-emerald-200',
    glow: 'shadow-[0_0_18px_rgba(16,185,129,0.35)]',
    buttonSolid: 'border-emerald-400/60 bg-emerald-500/20 text-emerald-100 hover:bg-emerald-500/30',
    buttonOutline: 'border-outline-variant/40 bg-transparent text-on-surface-variant hover:border-emerald-400/40 hover:text-emerald-200',
  },
  retired: {
    ringActive: 'ring-slate-400/40',
    bgActive: 'bg-slate-500/15',
    borderActive: 'border-slate-400/70',
    textActive: 'text-slate-200',
    glow: '',
    buttonSolid: 'border-slate-400/60 bg-slate-500/20 text-slate-100 hover:bg-slate-500/30',
    buttonOutline: 'border-outline-variant/40 bg-transparent text-on-surface-variant hover:border-slate-400/40 hover:text-slate-200',
  },
}

function circleClass(idx: number) {
  const stage = stages[idx]
  if (idx < activeIndex.value) {
    return 'border-primary/60 bg-primary/15 text-primary'
  }
  if (idx === activeIndex.value) {
    const c = stageColors[stage.id]
    return `${c.bgActive} ${c.borderActive} ${c.textActive} ${c.glow} ring-4 ring-offset-2 ring-offset-surface-container-low ${c.ringActive}`
  }
  return 'border-outline-variant/50 bg-surface-container text-on-surface-variant'
}

function textClass(idx: number) {
  const stage = stages[idx]
  if (idx === activeIndex.value) return `font-semibold ${stageColors[stage.id].textActive}`
  if (idx < activeIndex.value) return 'font-medium text-on-surface'
  return 'text-on-surface-variant'
}

function actionButtonClass(stageId: LifecycleStageId) {
  const c = stageColors[stageId]
  return props.activeStage === stageId ? c.buttonSolid : c.buttonOutline
}

function dotClass(stage: LifecycleStageId) {
  if (stage === 'building') return 'bg-sky-400'
  if (stage === 'pending') return 'bg-amber-400'
  if (stage === 'active') return 'bg-emerald-400 animate-pulse'
  return 'bg-slate-400'
}
</script>
