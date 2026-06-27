<template>
  <OpsPage>
    <OpsPageHeader
      title="巡检实例详情"
      :subtitle="headerSubtitle"
      icon="fact_check"
    >
      <template #actions>
        <button
          type="button"
          class="ops-secondary-button"
          @click="goBack"
        >
          <span class="material-symbols-outlined text-[18px]">arrow_back</span>
          返回报告
        </button>
        <label
          class="ml-2 flex items-center gap-1.5 text-xs text-on-surface-variant"
          :title="instanceIncludeEvidence ? '需 admin 角色：包含原始 evidence 行' : '仅含 findings/message'"
        >
          <input
            v-model="instanceIncludeEvidence"
            type="checkbox"
            class="h-3.5 w-3.5 rounded border-outline-variant/40 bg-surface-container"
          />
          包含原始 evidence
        </label>
        <button
          type="button"
          class="ops-primary-button ml-2"
          :disabled="instanceExporting"
          @click="handleInstanceExport"
        >
          <span class="material-symbols-outlined text-[18px]">{{ instanceExporting ? 'downloading' : 'file_download' }}</span>
          {{ instanceExporting ? '导出中...' : '导出单实例 DOCX' }}
        </button>
      </template>
    </OpsPageHeader>

    <!-- Loading -->
    <OpsSectionCard v-if="loading" class="mb-6">
      <div class="flex items-center justify-center py-12 text-on-surface-variant">
        <span class="material-symbols-outlined animate-spin text-2xl mr-3">sync</span>
        加载实例详情...
      </div>
    </OpsSectionCard>

    <!-- Error -->
    <OpsSectionCard v-else-if="error" class="mb-6">
      <div class="flex items-center justify-center py-12 text-red-400">
        <span class="material-symbols-outlined text-2xl mr-3">error</span>
        {{ error }}
      </div>
    </OpsSectionCard>

    <template v-else>
      <!-- Instance Summary -->
      <OpsSectionCard title="实例健康摘要" class="mb-6">
        <div v-if="!instanceReport" class="text-sm text-on-surface-variant">
          未找到该实例的 instance_report 记录，可能任务尚未完成或该目标被跳过。
        </div>
        <template v-else>
          <!-- Meta strip: instance IP + DB type + target name (post-verification 2026-06-26) -->
          <div class="mb-4 flex flex-wrap items-center gap-2 text-xs">
            <span v-if="results[0]?.target_name" class="rounded bg-surface-container px-2 py-0.5 font-medium text-on-surface">
              {{ results[0].target_name }}
            </span>
            <span v-if="instanceReport.host_snapshot" class="rounded bg-surface-container px-2 py-0.5 font-mono text-on-surface-variant">
              IP: {{ instanceReport.host_snapshot }}
            </span>
            <span v-if="instanceReport.db_type_code_snapshot" class="inline-flex items-center rounded-full border border-outline-variant/40 bg-surface-container-high px-2 py-0.5 font-mono text-[10px] uppercase text-on-surface-variant">
              {{ instanceReport.db_type_code_snapshot }}
            </span>
            <span v-if="!instanceReport.host_snapshot && !instanceReport.db_type_code_snapshot && !results[0]?.target_name" class="text-on-surface-variant">
              (实例元信息不可用)
            </span>
          </div>
          <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div class="field-card text-center">
            <div class="field-label">健康等级</div>
            <span
              class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
              :class="getHealthClass(instanceReport.health_level)"
            >
              {{ instanceReport.health_level || '-' }}
            </span>
          </div>
          <div class="field-card text-center">
            <div class="field-label">健康分数</div>
            <div class="field-value text-2xl font-bold">
              {{ instanceReport.health_score != null ? instanceReport.health_score.toFixed(1) : '-' }}
            </div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-emerald-400">{{ instanceReport.normal_count }}</div>
            <div class="field-label">normal</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-amber-400">{{ instanceReport.warning_count }}</div>
            <div class="field-label">warning</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-red-400">{{ instanceReport.critical_count }}</div>
            <div class="field-label">critical</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-slate-400">{{ instanceReport.unknown_count }}</div>
            <div class="field-label">unknown</div>
          </div>
          </div>
        </template>
      </OpsSectionCard>

      <!-- Result Detail -->
      <OpsSectionCard title="巡检结果明细" class="mb-6">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
          <span class="text-xs text-on-surface-variant">
            目标 <span class="font-mono">{{ targetType }}:{{ targetId }}</span>
            · 共 {{ results.length }} 条结果
            <span v-if="onlyAbnormal"> · 已过滤为 {{ filteredResults.length }} 条异常</span>
          </span>
          <label class="flex items-center gap-2 text-xs text-on-surface-variant">
            <input
              v-model="onlyAbnormal"
              type="checkbox"
              class="h-3.5 w-3.5 rounded border-outline-variant/40 bg-surface-container"
            />
            只看异常
          </label>
        </div>

        <OpsTableShell
          :loading="resultsLoading"
          :empty="!filteredResults.length && !resultsLoading"
          empty-text="该实例暂无结果数据"
        >
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="w-8 px-2 py-3"></th>
                <th class="whitespace-nowrap px-4 py-3">巡检项</th>
                <th class="whitespace-nowrap px-4 py-3">执行状态</th>
                <th class="whitespace-nowrap px-4 py-3">评估状态</th>
                <th class="whitespace-nowrap px-4 py-3">结果信息</th>
                <th class="whitespace-nowrap px-4 py-3">时间</th>
              </tr>
            </thead>
            <tbody>
              <template
                v-for="group in groupedResults"
                :key="group.category"
              >
                <!-- Category header row (collapsible) -->
                <tr class="bg-surface-container/50 cursor-pointer" @click="toggleCategory(group.category)">
                  <td class="px-2 py-2 align-middle">
                    <span class="material-symbols-outlined text-[16px] text-on-surface-variant">
                      {{ isCategoryOpen(group.category) ? 'expand_more' : 'chevron_right' }}
                    </span>
                  </td>
                  <td colspan="5" class="px-4 py-2 text-xs font-semibold text-on-surface-variant">
                    <span class="font-mono">{{ group.category || '未分类' }}</span>
                    <span class="ml-3 text-on-surface-variant/70">
                      {{ group.items.length }} 项 ·
                      <span class="text-red-300">{{ countByEval(group.items, 'critical') }} critical</span> ·
                      <span class="text-amber-300">{{ countByEval(group.items, 'warning') }} warning</span> ·
                      <span class="text-emerald-300">{{ countByEval(group.items, 'normal') }} normal</span>
                    </span>
                  </td>
                </tr>
                <!-- Result rows under the category -->
                <template v-if="isCategoryOpen(group.category)">
                  <template v-for="r in group.items" :key="r.id">
                    <tr
                      class="border-t border-outline-variant/30 cursor-pointer hover:bg-surface-container-high/40"
                      @click="toggleDetail(r.id)"
                    >
                      <td class="px-2 py-3 align-top">
                        <span class="material-symbols-outlined text-[16px] text-on-surface-variant">
                          {{ isDetailOpen(r.id) ? 'expand_more' : 'chevron_right' }}
                        </span>
                      </td>
                      <td class="whitespace-nowrap px-4 py-3 font-mono text-xs align-top">
                        <div>{{ r.result_code }}</div>
                        <div v-if="r.item_name" class="text-xs text-on-surface-variant">{{ r.item_name }}</div>
                      </td>
                      <td class="whitespace-nowrap px-4 py-3 align-top">
                        <span
                          class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                          :class="getExecutionStatusClass(r.execution_status)"
                        >
                          {{ r.execution_status }}
                        </span>
                      </td>
                      <td class="whitespace-nowrap px-4 py-3 align-top">
                        <span
                          class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                          :class="getEvaluationClass(r.evaluation_status)"
                        >
                          {{ r.evaluation_status }}
                        </span>
                      </td>
                      <td class="px-4 py-3 text-xs max-w-md align-top">
                        <div class="whitespace-pre-wrap break-words">{{ r.message || '-' }}</div>
                      </td>
                      <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant align-top">
                        {{ formatTime(r.detected_at) }}
                      </td>
                    </tr>
                    <!-- Evidence drawer -->
                    <tr v-if="isDetailOpen(r.id)" class="border-t border-outline-variant/30 bg-surface-container/30">
                      <td></td>
                      <td colspan="5" class="px-4 py-4">
                        <ResultEvidencePanel :result="r" />
                      </td>
                    </tr>
                  </template>
                </template>
              </template>
            </tbody>
          </table>
        </OpsTableShell>
      </OpsSectionCard>
    </template>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import ResultEvidencePanel from '@/views/inspection/ResultEvidencePanel.vue'
import { assetsApi } from '@/api/assets'
import type {
  InspectionInstanceReportRow,
  InspectionReportRow,
  InspectionResultRow,
} from '@/types/api'
import { formatInTz } from '@/utils/timezone'

const route = useRoute()
const router = useRouter()

// -- Params --
const reportId = computed(() => String(route.params.id ?? ''))
const targetType = computed(() => String(route.params.targetType ?? ''))
const targetId = computed(() => Number(route.params.targetId ?? 0))

const headerSubtitle = computed(
  () => `报告 #${reportId.value} · 目标 ${targetType.value}:${targetId.value}`,
)

// -- State --
const loading = ref(false)
const error = ref('')
const report = ref<InspectionReportRow | null>(null)
const instanceReport = ref<InspectionInstanceReportRow | null>(null)
const results = ref<InspectionResultRow[]>([])
const resultsLoading = ref(false)

// -- UI state (persisted per session) --
const onlyAbnormal = ref(false)
const openDetails = ref<Set<number>>(new Set())
const openCategories = ref<Set<string>>(new Set())
const instanceExporting = ref(false)
const instanceIncludeEvidence = ref(false)

// -- Helpers (kept consistent with ReportDetail.vue) --
function getHealthClass(level: string | null): string {
  const l = (level || '').toLowerCase()
  if (l === 'critical') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (l === 'warning') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (l === 'healthy') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (l === 'unknown') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function getExecutionStatusClass(status: string): string {
  const s = (status || '').toLowerCase()
  if (s === 'success') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'failed' || s === 'timeout' || s === 'connection_failed' || s === 'permission_denied')
    return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'skipped') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function getEvaluationClass(status: string): string {
  const s = (status || '').toLowerCase()
  if (s === 'normal') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'warning') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'critical') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'not_evaluated') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function formatTime(value: string | null | undefined): string {
  return value ? formatInTz(value) : '-'
}

function isAbnormal(evalStatus: string): boolean {
  const s = (evalStatus || '').toLowerCase()
  return s === 'warning' || s === 'critical' || s === 'unknown'
}

function countByEval(items: InspectionResultRow[], evalStatus: string): number {
  return items.filter((r) => (r.evaluation_status || '').toLowerCase() === evalStatus).length
}

function isDetailOpen(id: number): boolean {
  return openDetails.value.has(id)
}

function toggleDetail(id: number): void {
  const next = new Set(openDetails.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  openDetails.value = next
}

function isCategoryOpen(cat: string): boolean {
  return openCategories.value.has(cat)
}

function toggleCategory(cat: string): void {
  const next = new Set(openCategories.value)
  if (next.has(cat)) next.delete(cat)
  else next.add(cat)
  openCategories.value = next
}

// -- Loaders --
async function loadInstanceReport() {
  const list = await assetsApi.listInstanceReports(reportId.value)
  instanceReport.value = list.find(
    (r) => r.target_type === targetType.value && r.target_id === targetId.value,
  ) ?? null
}

async function loadResults() {
  resultsLoading.value = true
  try {
    results.value = await assetsApi.getInstanceReportResults(
      reportId.value,
      targetType.value,
      targetId.value,
    )
  } finally {
    resultsLoading.value = false
  }
}

async function loadReportMeta() {
  report.value = await assetsApi.getInspectionReport(reportId.value)
}

async function loadAll() {
  if (!reportId.value || !targetType.value || !targetId.value) {
    error.value = '缺少报告ID / 目标类型 / 目标ID'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await loadReportMeta()
    await Promise.all([loadInstanceReport(), loadResults()])
    // Default-open every category encountered on first load.
    openCategories.value = new Set(filteredResults.value.map((r) => r.category || '未分类'))
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载实例详情失败'
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push({ name: 'InspectionReportDetail', params: { id: reportId.value } })
}

// -- Export single instance DOCX (post-verification 2026-06-26) --
async function handleInstanceExport() {
  if (!reportId.value || !targetType.value || !targetId.value) return
  instanceExporting.value = true
  try {
    await assetsApi.exportInstanceReport(
      reportId.value,
      targetType.value,
      targetId.value,
      { includeEvidence: instanceIncludeEvidence.value },
    )
  } catch (e: any) {
    error.value = e?.message || '导出失败'
  } finally {
    instanceExporting.value = false
  }
}

// -- Derived views --
const filteredResults = computed(() => {
  if (!onlyAbnormal.value) return results.value
  return results.value.filter((r) => isAbnormal(r.evaluation_status))
})

interface GroupedResults {
  category: string
  items: InspectionResultRow[]
}

const groupedResults = computed<GroupedResults[]>(() => {
  const groups = new Map<string, InspectionResultRow[]>()
  for (const r of filteredResults.value) {
    const key = r.category || '未分类'
    const list = groups.get(key)
    if (list) list.push(r)
    else groups.set(key, [r])
  }
  return Array.from(groups.entries()).map(([category, items]) => ({ category, items }))
})

onMounted(loadAll)
</script>
