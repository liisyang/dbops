<template>
  <OpsPage>
    <OpsPageHeader title="巡检报告" subtitle="查看 inspection 任务生成的标准化巡检结果。" icon="assessment" />

    <OpsSectionCard title="筛选条件" class="mb-6">
      <div class="grid gap-3 sm:grid-cols-4">
        <label class="block field-card">
          <span class="field-label">健康等级</span>
          <select v-model="filters.health_level" class="field-input" @change="loadReports">
            <option value="">全部</option>
            <option value="critical">critical</option>
            <option value="warning">warning</option>
            <option value="healthy">healthy</option>
            <option value="unknown">unknown</option>
            <option value="not_assessed">not_assessed</option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">报告状态</span>
          <select v-model="filters.report_status" class="field-input" @change="loadReports">
            <option value="">全部</option>
            <option value="ready">ready</option>
            <option value="generating">generating</option>
            <option value="partial">partial</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <div class="field-card flex items-end">
          <button type="button" class="ops-secondary-button w-full" @click="loadReports">
            <span class="material-symbols-outlined text-[18px]">refresh</span>
            刷新
          </button>
        </div>
      </div>
    </OpsSectionCard>

    <OpsSectionCard title="报告摘要" class="mb-6">
      <div class="grid gap-3 sm:grid-cols-5">
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold">{{ reports.length }}</div>
          <div class="field-label">报告数</div>
        </div>
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold text-red-400">{{ criticalCount }}</div>
          <div class="field-label">critical</div>
        </div>
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold text-amber-400">{{ warningCount }}</div>
          <div class="field-label">warning</div>
        </div>
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold text-emerald-400">{{ healthyCount }}</div>
          <div class="field-label">healthy</div>
        </div>
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold text-slate-400">{{ unknownCount }}</div>
          <div class="field-label">unknown</div>
        </div>
      </div>
    </OpsSectionCard>

    <OpsSectionCard title="报告列表">
      <OpsTableShell :loading="loading" :empty="!reports.length && !loading">
        <table class="w-full text-sm">
          <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
            <tr>
              <th class="whitespace-nowrap px-4 py-3">报告编码</th>
              <th class="whitespace-nowrap px-4 py-3">任务ID</th>
              <th class="whitespace-nowrap px-4 py-3">健康等级</th>
              <th class="whitespace-nowrap px-4 py-3">健康分数</th>
              <th class="whitespace-nowrap px-4 py-3">实例统计</th>
              <th class="whitespace-nowrap px-4 py-3">状态</th>
              <th class="whitespace-nowrap px-4 py-3">生成时间</th>
              <th class="whitespace-nowrap px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="report in reports"
              :key="report.id"
              class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
            >
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ report.report_code }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ report.task_id }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getHealthClass(report.health_level)">
                  {{ report.health_level || '-' }}
                </span>
              </td>
              <td class="whitespace-nowrap px-4 py-3 font-mono">{{ report.health_score != null ? report.health_score.toFixed(1) : '-' }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs">
                <span class="text-emerald-400">{{ report.healthy_count }}</span>
                / <span class="text-amber-400">{{ report.warning_count }}</span>
                / <span class="text-red-400">{{ report.critical_count }}</span>
                / {{ report.total_target_count }}
              </td>
              <td class="whitespace-nowrap px-4 py-3">
                <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getReportStatusClass(report.report_status)">
                  {{ report.report_status }}
                </span>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">{{ formatTime(report.generated_at) }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs">
                <div class="flex items-center gap-1">
                  <button type="button" class="ops-secondary-button !px-2 !py-1" @click="viewReportDetail(report)">
                    <span class="material-symbols-outlined text-[16px]">visibility</span>
                    详情
                  </button>
                  <button
                    type="button"
                    class="ops-secondary-button !px-2 !py-1"
                    :disabled="exportingId === report.id"
                    @click="handleExport(report)"
                  >
                    <span class="material-symbols-outlined text-[16px]">file_download</span>
                    {{ exportingId === report.id ? '导出中' : '导出' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
    </OpsSectionCard>

  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import { assetsApi } from '@/api/assets'
import type { InspectionReportRow } from '@/types/api'
import { formatInTz } from '@/utils/timezone'

const router = useRouter()

const loading = ref(false)
const reports = ref<InspectionReportRow[]>([])
const exportingId = ref<number | string | null>(null)

const filters = reactive({
  health_level: '',
  report_status: '',
})

const criticalCount = computed(() => reports.value.filter((r) => r.health_level === 'critical').length)
const warningCount = computed(() => reports.value.filter((r) => r.health_level === 'warning').length)
const healthyCount = computed(() => reports.value.filter((r) => r.health_level === 'healthy').length)
const unknownCount = computed(() => reports.value.filter((r) => r.health_level === 'unknown').length)

function getHealthClass(level: string | null): string {
  const l = (level || '').toLowerCase()
  if (l === 'critical') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (l === 'warning') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (l === 'healthy') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (l === 'unknown') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function getReportStatusClass(status: string): string {
  const s = (status || '').toLowerCase()
  if (s === 'ready') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'generating') return 'border-blue-400/30 bg-blue-400/10 text-blue-200'
  if (s === 'failed') return 'border-red-400/30 bg-red-400/10 text-red-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function formatTime(value: string | null | undefined): string {
  return value ? formatInTz(value) : '-'
}

function viewReportDetail(report: InspectionReportRow) {
  router.push(`/inspection/reports/${report.id}`)
}

// Plan v5.1 §8: list-level export entrypoint. Default to non-evidence export
// (operator+admin both allowed); include_evidence is admin-only on the server.
async function handleExport(report: InspectionReportRow) {
  exportingId.value = report.id
  try {
    await assetsApi.exportReport(report.id, { includeEvidence: false })
  } catch (e: any) {
    showError(e?.message || '导出失败')
  } finally {
    exportingId.value = null
  }
}

function showError(message: string) {
  // Tiny inline toast; keeps Reports.vue dependency-free.
  const el = document.createElement('div')
  el.className = 'fixed top-4 right-4 z-50 px-4 py-3 rounded-lg text-white bg-red-600 shadow-lg'
  el.textContent = message
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 3000)
}

async function loadReports() {
  loading.value = true
  try {
    const res = await assetsApi.listInspectionReports({
      health_level: filters.health_level || undefined,
      report_status: filters.report_status || undefined,
    })
    reports.value = res.items || []
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadReports()
})
</script>
