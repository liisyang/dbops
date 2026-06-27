<template>
  <OpsPage>
    <OpsPageHeader title="巡检报告详情" subtitle="查看巡检报告的详细结果与实例健康状态。" icon="assessment">
      <template #actions>
        <button type="button" class="ops-secondary-button" @click="$router.back()">
          <span class="material-symbols-outlined text-[18px]">arrow_back</span>
          返回
        </button>
        <button
          type="button"
          class="ops-secondary-button ml-2"
          :disabled="regenerating"
          @click="handleRegenerate"
        >
          <span class="material-symbols-outlined text-[18px]">{{ regenerating ? 'sync' : 'refresh' }}</span>
          {{ regenerating ? '重新生成中...' : '重新生成' }}
        </button>
      </template>
    </OpsPageHeader>

    <!-- Loading -->
    <OpsSectionCard v-if="loading" class="mb-6">
      <div class="flex items-center justify-center py-12 text-on-surface-variant">
        <span class="material-symbols-outlined animate-spin text-2xl mr-3">sync</span>
        加载报告...
      </div>
    </OpsSectionCard>

    <!-- Error -->
    <OpsSectionCard v-else-if="error" class="mb-6">
      <div class="flex items-center justify-center py-12 text-red-400">
        <span class="material-symbols-outlined text-2xl mr-3">error</span>
        {{ error }}
      </div>
    </OpsSectionCard>

    <template v-else-if="report">
      <!-- Report Summary -->
      <OpsSectionCard title="报告摘要" class="mb-6">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div class="field-card text-center">
            <div class="field-label">报告编号</div>
            <div class="field-value font-mono text-sm">{{ report.report_code }}</div>
          </div>
          <div class="field-card text-center">
            <div class="field-label">健康等级</div>
            <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getHealthClass(report.health_level)">
              {{ report.health_level || '-' }}
            </span>
          </div>
          <div class="field-card text-center">
            <div class="field-label">健康分数</div>
            <div class="field-value text-2xl font-bold">{{ report.health_score != null ? report.health_score.toFixed(1) : '-' }}</div>
          </div>
          <div class="field-card text-center">
            <div class="field-label">报告状态</div>
            <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getReportStatusClass(report.report_status)">
              {{ report.report_status }}
            </span>
          </div>
          <div class="field-card text-center">
            <div class="field-label">生成时间</div>
            <div class="field-value text-xs">{{ formatTime(report.generated_at) }}</div>
          </div>
        </div>

        <!-- Instance counts -->
        <div class="mt-4 grid gap-3 sm:grid-cols-6">
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold">{{ report.total_target_count }}</div>
            <div class="field-label">目标总数</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-emerald-400">{{ report.healthy_count }}</div>
            <div class="field-label">healthy</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-amber-400">{{ report.warning_count }}</div>
            <div class="field-label">warning</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-red-400">{{ report.critical_count }}</div>
            <div class="field-label">critical</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-slate-400">{{ report.unknown_count }}</div>
            <div class="field-label">unknown</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-xl font-bold text-slate-400">{{ report.missing_result_count }}</div>
            <div class="field-label">缺失结果</div>
          </div>
        </div>
      </OpsSectionCard>

      <!-- Instance Reports -->
      <OpsSectionCard title="实例健康详情" class="mb-6">
        <div class="mb-3 flex items-center justify-between">
          <span class="text-xs text-on-surface-variant">共 {{ instanceReports.length }} 个实例</span>
          <select v-model="instanceFilter" class="field-input w-40 text-xs" @change="loadInstanceReports">
            <option value="">全部健康等级</option>
            <option value="critical">critical</option>
            <option value="warning">warning</option>
            <option value="healthy">healthy</option>
            <option value="unknown">unknown</option>
            <option value="not_assessed">not_assessed</option>
          </select>
        </div>

        <OpsTableShell :loading="instancesLoading" :empty="!instanceReports.length && !instancesLoading">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="whitespace-nowrap px-4 py-3">目标类型</th>
                <th class="whitespace-nowrap px-4 py-3">目标ID</th>
                <th class="whitespace-nowrap px-4 py-3">实例IP</th>
                <th class="whitespace-nowrap px-4 py-3">DB类型</th>
                <th class="whitespace-nowrap px-4 py-3">健康等级</th>
                <th class="whitespace-nowrap px-4 py-3">健康分数</th>
                <th class="whitespace-nowrap px-4 py-3">结果分布</th>
                <th class="whitespace-nowrap px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="irep in instanceReports"
                :key="irep.id"
                class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
              >
                <td class="whitespace-nowrap px-4 py-3">{{ irep.target_type }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ irep.target_id }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ irep.host_snapshot || '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span v-if="irep.db_type_code_snapshot" class="inline-flex items-center rounded-full border border-outline-variant/40 bg-surface-container-high px-2 py-0.5 text-[10px] font-medium font-mono uppercase text-on-surface-variant">
                    {{ irep.db_type_code_snapshot }}
                  </span>
                  <span v-else>-</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getHealthClass(irep.health_level)">
                    {{ irep.health_level || '-' }}
                  </span>
                </td>
                <td class="whitespace-nowrap px-4 py-3 font-mono">{{ irep.health_score != null ? irep.health_score.toFixed(1) : '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-xs">
                  <span class="text-emerald-400">{{ irep.normal_count }}</span>
                  / <span class="text-amber-400">{{ irep.warning_count }}</span>
                  / <span class="text-red-400">{{ irep.critical_count }}</span>
                  / <span class="text-slate-400">{{ irep.unknown_count }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">
                  <div class="flex items-center gap-2">
                    <router-link
                      :to="{
                        name: 'InspectionInstanceReport',
                        params: {
                          id: String(report.id),
                          targetType: irep.target_type,
                          targetId: irep.target_id,
                        },
                      }"
                      class="ops-secondary-button !px-2 !py-1"
                    >
                      <span class="material-symbols-outlined text-[16px]">open_in_new</span>
                      详情
                    </router-link>
                    <!-- Per-instance DOCX export (bug4 fix 2026-06-26).
                         Sits next to the "详情" link so operators don't have
                         to enter the instance detail page just to download
                         a single instance's slice of the report. -->
                    <button
                      type="button"
                      class="ops-secondary-button !px-2 !py-1"
                      :disabled="rowExporting.has(irep.id)"
                      :title="`导出 ${irep.target_type}:${irep.target_id} 的单实例 DOCX`"
                      @click="handleRowExport(irep)"
                    >
                      <span class="material-symbols-outlined text-[16px]">
                        {{ rowExporting.has(irep.id) ? 'downloading' : 'file_download' }}
                      </span>
                      {{ rowExporting.has(irep.id) ? '导出中' : '导出' }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </OpsTableShell>
      </OpsSectionCard>
    </template>
  </OpsPage>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import { assetsApi } from '@/api/assets'
import type { InspectionReportRow, InspectionInstanceReportRow } from '@/types/api'
import { formatInTz } from '@/utils/timezone'

const route = useRoute()

const loading = ref(false)
const error = ref('')
const report = ref<InspectionReportRow | null>(null)
const instanceReports = ref<InspectionInstanceReportRow[]>([])
const instancesLoading = ref(false)
const instanceFilter = ref('')
const regenerating = ref(false)
// Tracks which instance row is currently exporting DOCX (bug4 fix 2026-06-26).
// Each row is independently clickable, so a Set keyed by instance_report.id
// lets us show per-row "导出中" state instead of disabling the whole table.
const rowExporting = ref<Set<number>>(new Set())

// -- Health class helpers --
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

// -- Load report --
async function loadReport() {
  const id = route.params.id as string
  if (!id) {
    error.value = '缺少报告ID'
    return
  }

  loading.value = true
  error.value = ''
  try {
    report.value = await assetsApi.getInspectionReport(id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载报告失败'
  } finally {
    loading.value = false
  }
}

async function loadInstanceReports() {
  if (!report.value) return
  instancesLoading.value = true
  try {
    const params = instanceFilter.value ? { health_level: instanceFilter.value } : undefined
    instanceReports.value = await assetsApi.listInstanceReports(report.value.id, params)
  } finally {
    instancesLoading.value = false
  }
}

// -- Regenerate --
async function handleRegenerate() {
  if (!report.value) return
  regenerating.value = true
  try {
    report.value = await assetsApi.regenerateReport(report.value.id)
    await loadInstanceReports()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '重新生成失败'
  } finally {
    regenerating.value = false
  }
}

// -- Per-instance DOCX export (bug4 fix 2026-06-26) --
// Calls the existing single-instance endpoint
//   POST /v1/inspection/reports/{report_id}/instances/{target_type}/{target_id}/export
// which builds a DOCX scoped to that (target_type, target_id) only.
// Each row has its own button so operators don't have to drill into the
// instance detail page just to download that instance's report.
async function handleRowExport(irep: InspectionInstanceReportRow) {
  if (!report.value || rowExporting.value.has(irep.id)) return
  const next = new Set(rowExporting.value)
  next.add(irep.id)
  rowExporting.value = next
  try {
    await assetsApi.exportInstanceReport(
      report.value.id,
      irep.target_type,
      irep.target_id,
    )
  } catch (e: any) {
    error.value = e?.message || `实例 ${irep.target_type}:${irep.target_id} 导出失败`
  } finally {
    const done = new Set(rowExporting.value)
    done.delete(irep.id)
    rowExporting.value = done
  }
}

onMounted(async () => {
  await loadReport()
  if (report.value) {
    await loadInstanceReports()
  }
})
</script>
