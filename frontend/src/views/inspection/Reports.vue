<template>
  <OpsPage>
    <OpsPageHeader title="巡检报告" subtitle="查看 inspection 任务生成的标准化巡检结果。" icon="assessment" />

    <OpsSectionCard title="筛选条件" class="mb-6">
      <div class="grid gap-3 sm:grid-cols-4">
        <label class="block field-card">
          <span class="field-label">任务</span>
          <select v-model="filters.task_id" class="field-input" @change="loadResults">
            <option value="">全部</option>
            <option v-for="task in tasks" :key="task.id" :value="String(task.id)">
              {{ task.task_code }} - {{ task.task_name }}
            </option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">结果状态</span>
          <select v-model="filters.result_status" class="field-input" @change="loadResults">
            <option value="">全部</option>
            <option value="abnormal">abnormal</option>
            <option value="warning">warning</option>
            <option value="normal">normal</option>
            <option value="unknown">unknown</option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">目标类型</span>
          <select v-model="filters.target_type" class="field-input" @change="loadResults">
            <option value="">全部</option>
            <option value="db_instance">db_instance</option>
            <option value="server">server</option>
          </select>
        </label>
        <div class="field-card flex items-end">
          <button type="button" class="ops-secondary-button w-full" @click="loadResults">
            <span class="material-symbols-outlined text-[18px]">refresh</span>
            刷新
          </button>
        </div>
      </div>
    </OpsSectionCard>

    <OpsSectionCard title="结果摘要" class="mb-6">
      <div class="grid gap-3 sm:grid-cols-4">
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold">{{ results.length }}</div>
          <div class="field-label">总结果数</div>
        </div>
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold text-red-400">{{ abnormalCount }}</div>
          <div class="field-label">abnormal</div>
        </div>
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold text-amber-400">{{ warningCount }}</div>
          <div class="field-label">warning</div>
        </div>
        <div class="field-card text-center">
          <div class="field-value text-2xl font-bold text-emerald-400">{{ normalCount }}</div>
          <div class="field-label">normal</div>
        </div>
      </div>
    </OpsSectionCard>

    <OpsSectionCard title="结果明细">
      <OpsTableShell :loading="loading" :empty="!results.length && !loading">
        <table class="w-full text-sm">
          <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
            <tr>
              <th class="whitespace-nowrap px-4 py-3">时间</th>
              <th class="whitespace-nowrap px-4 py-3">任务ID</th>
              <th class="whitespace-nowrap px-4 py-3">巡检项</th>
              <th class="whitespace-nowrap px-4 py-3">目标</th>
              <th class="whitespace-nowrap px-4 py-3">状态</th>
              <th class="whitespace-nowrap px-4 py-3">级别</th>
              <th class="whitespace-nowrap px-4 py-3">消息</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in results" :key="row.id" class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high">
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">{{ formatTime(row.detected_at) }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ row.task_id }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                <div class="font-medium">{{ row.item_name || row.item_code || '-' }}</div>
                <div class="font-mono text-xs text-on-surface-variant">{{ row.result_code }}</div>
              </td>
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ row.target_type }}#{{ row.target_id }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getResultClass(row.result_status)">
                  {{ row.result_status }}
                </span>
              </td>
              <td class="whitespace-nowrap px-4 py-3">{{ row.severity }}</td>
              <td class="px-4 py-3 text-xs">{{ row.message || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import { assetsApi } from '@/api/assets'
import type { InspectionResultRow, InspectionTaskRow } from '@/types/api'
import { formatInTz } from '@/utils/timezone'

const loading = ref(false)
const tasks = ref<InspectionTaskRow[]>([])
const results = ref<InspectionResultRow[]>([])

const filters = reactive({
  task_id: '',
  target_type: '',
  result_status: '',
})

const abnormalCount = computed(() => results.value.filter((row) => row.result_status === 'abnormal').length)
const warningCount = computed(() => results.value.filter((row) => row.result_status === 'warning').length)
const normalCount = computed(() => results.value.filter((row) => row.result_status === 'normal').length)

function getResultClass(status: string): string {
  const normalized = (status || '').toLowerCase()
  if (normalized === 'abnormal') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (normalized === 'warning') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (normalized === 'normal') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function formatTime(value: string | null | undefined): string {
  return value ? formatInTz(value) : '-'
}

async function loadTasks() {
  tasks.value = await assetsApi.listInspectionTasks({ limit: 100 })
}

async function loadResults() {
  loading.value = true
  try {
    results.value = await assetsApi.listInspectionResults({
      task_id: filters.task_id ? Number.parseInt(filters.task_id, 10) : undefined,
      target_type: (filters.target_type || undefined) as 'db_instance' | 'server' | undefined,
      result_status: filters.result_status || undefined,
      limit: 500,
    })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadTasks()
  await loadResults()
})
</script>