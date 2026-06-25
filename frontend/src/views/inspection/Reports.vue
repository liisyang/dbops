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
              <th class="whitespace-nowrap px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in results"
              :key="row.id"
              class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
            >
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
              <td class="whitespace-nowrap px-4 py-3 text-xs">
                <button type="button" class="ops-secondary-button !px-2 !py-1" @click="openEvidence(row)">
                  <span class="material-symbols-outlined text-[16px]">description</span>
                  证据
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
    </OpsSectionCard>

    <OpsDrawer
      :open="!!selectedResult"
      :title="drawerTitle"
      :subtitle="drawerSubtitle"
      icon="description"
      width="xl"
      @close="closeEvidence"
    >
      <div v-if="selectedResult" class="space-y-5">
        <!-- Summary block -->
        <section class="rounded-lg border border-outline-variant/40 bg-surface-container-high/40 p-4">
          <h3 class="mb-3 text-sm font-semibold text-on-surface">结果概要</h3>
          <dl class="grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt class="text-on-surface-variant">检测时间</dt>
              <dd class="mt-0.5 font-mono">{{ formatTime(selectedResult.detected_at) }}</dd>
            </div>
            <div>
              <dt class="text-on-surface-variant">任务ID</dt>
              <dd class="mt-0.5 font-mono">{{ selectedResult.task_id }}</dd>
            </div>
            <div>
              <dt class="text-on-surface-variant">巡检项</dt>
              <dd class="mt-0.5">
                <div class="font-medium">{{ selectedResult.item_name || selectedResult.item_code || '-' }}</div>
                <div class="font-mono text-on-surface-variant">{{ selectedResult.result_code }}</div>
              </dd>
            </div>
            <div>
              <dt class="text-on-surface-variant">目标</dt>
              <dd class="mt-0.5 font-mono">{{ selectedResult.target_type }}#{{ selectedResult.target_id }}</dd>
            </div>
            <div>
              <dt class="text-on-surface-variant">结果状态</dt>
              <dd class="mt-1">
                <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getResultClass(selectedResult.result_status)">
                  {{ selectedResult.result_status }}
                </span>
              </dd>
            </div>
            <div>
              <dt class="text-on-surface-variant">级别</dt>
              <dd class="mt-0.5">{{ selectedResult.severity }}</dd>
            </div>
            <div class="col-span-2">
              <dt class="text-on-surface-variant">消息</dt>
              <dd class="mt-0.5 whitespace-pre-wrap break-words">{{ selectedResult.message || '-' }}</dd>
            </div>
          </dl>
        </section>

        <!-- Evidence table -->
        <section>
          <h3 class="mb-3 text-sm font-semibold text-on-surface">SQL 执行证据</h3>

          <!-- Meta line -->
          <div v-if="hasEvidenceMeta" class="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-on-surface-variant">
            <span v-if="evidenceSqlHash">
              sql_hash: <span class="font-mono text-on-surface">{{ evidenceSqlHash }}</span>
            </span>
            <span v-if="evidenceDurationMs !== null">
              duration: <span class="font-mono text-on-surface">{{ evidenceDurationMs }} ms</span>
            </span>
            <span v-if="evidenceConnector">
              connector: <span class="font-mono text-on-surface">{{ evidenceConnector }}</span>
            </span>
            <span v-if="evidenceRowCount !== null">
              rows: <span class="font-mono text-on-surface">{{ evidenceRowCount }}</span>
            </span>
          </div>

          <!-- Rows table -->
          <div v-if="hasEvidenceRows" class="overflow-x-auto rounded-lg border border-outline-variant/40">
            <table class="w-full text-xs">
              <thead class="bg-surface-container text-left text-[11px] uppercase text-on-surface-variant">
                <tr>
                  <th class="whitespace-nowrap px-3 py-2 font-mono">#</th>
                  <th
                    v-for="(col, idx) in evidenceColumns"
                    :key="`${col}-${idx}`"
                    class="whitespace-nowrap px-3 py-2 font-mono"
                  >
                    {{ col }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, rIdx) in evidenceRowsLimited"
                  :key="rIdx"
                  class="border-t border-outline-variant/30"
                >
                  <td class="whitespace-nowrap px-3 py-1.5 font-mono text-on-surface-variant">{{ rIdx + 1 }}</td>
                  <td
                    v-for="(col, cIdx) in evidenceColumns"
                    :key="`${rIdx}-${col}-${cIdx}`"
                    class="whitespace-nowrap px-3 py-1.5 font-mono"
                  >
                    {{ formatCell(row[col]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            v-else
            class="rounded-lg border border-dashed border-outline-variant/40 px-4 py-6 text-center text-xs text-on-surface-variant"
          >
            {{ evidenceEmptyMessage }}
          </div>
          <p v-if="hasEvidenceRowsOverflow" class="mt-2 text-xs text-on-surface-variant">
            仅展示前 {{ MAX_EVIDENCE_ROWS }} 行，共 {{ evidenceRowCount }} 行。
          </p>
        </section>

        <!-- Stderr -->
        <section v-if="evidenceStderr">
          <h3 class="mb-2 text-sm font-semibold text-on-surface">stderr</h3>
          <pre class="max-h-40 overflow-auto rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs font-mono text-red-200 whitespace-pre-wrap break-words">{{ evidenceStderr }}</pre>
        </section>

        <!-- Raw JSON toggle -->
        <section>
          <button
            type="button"
            class="ops-secondary-button"
            @click="showRawJson = !showRawJson"
          >
            <span class="material-symbols-outlined text-[16px]">{{ showRawJson ? 'expand_less' : 'expand_more' }}</span>
            {{ showRawJson ? '收起原始 JSON' : '查看原始 JSON' }}
          </button>
          <pre
            v-if="showRawJson"
            class="mt-3 max-h-80 overflow-auto rounded-lg border border-outline-variant/40 bg-surface-container-high/40 px-3 py-2 text-xs font-mono whitespace-pre-wrap break-words"
          >{{ rawJsonText }}</pre>
        </section>
      </div>
    </OpsDrawer>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import OpsDrawer from '@/components/ops/OpsDrawer.vue'
import { assetsApi } from '@/api/assets'
import type { InspectionResultRow, InspectionTaskRow } from '@/types/api'
import { formatInTz } from '@/utils/timezone'

const MAX_EVIDENCE_ROWS = 20
const MAX_STDERR_LENGTH = 2000

const loading = ref(false)
const tasks = ref<InspectionTaskRow[]>([])
const results = ref<InspectionResultRow[]>([])

const filters = reactive({
  task_id: '',
  target_type: '',
  result_status: '',
})

const selectedResult = ref<InspectionResultRow | null>(null)
const showRawJson = ref(false)

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

const drawerTitle = computed(() => {
  const r = selectedResult.value
  if (!r) return '巡检证据'
  const name = r.item_name || r.item_code || r.result_code
  return `${name} #${r.id}`
})

const drawerSubtitle = computed(() => {
  const r = selectedResult.value
  if (!r) return ''
  return `${r.target_type}#${r.target_id} · ${formatTime(r.detected_at)}`
})

// Evidence field accessors — defensive against missing fields and wrong casing.
const evidenceColumns = computed<string[]>(() => {
  const ev = selectedResult.value?.evidence
  if (!ev) return []
  const cols = ev.columns
  return Array.isArray(cols) ? cols.map((c) => String(c)) : []
})

const evidenceRowsAll = computed<Record<string, unknown>[]>(() => {
  const ev = selectedResult.value?.evidence
  if (!ev) return []
  const rows = ev.rows
  return Array.isArray(rows) ? (rows as Record<string, unknown>[]) : []
})

const evidenceRowsLimited = computed<Record<string, unknown>[]>(() =>
  evidenceRowsAll.value.slice(0, MAX_EVIDENCE_ROWS),
)

const evidenceRowCount = computed<number | null>(() => {
  const ev = selectedResult.value?.evidence
  if (!ev || !Array.isArray(ev.rows)) return null
  return ev.rows.length
})

const hasEvidenceRows = computed(() => evidenceRowsAll.value.length > 0)
const hasEvidenceRowsOverflow = computed(() => evidenceRowsAll.value.length > MAX_EVIDENCE_ROWS)

const evidenceSqlHash = computed<string | null>(() => {
  const ev = selectedResult.value?.evidence
  if (!ev) return null
  const v = ev.sql_hash
  return typeof v === 'string' && v ? v : null
})

const evidenceDurationMs = computed<number | null>(() => {
  const ev = selectedResult.value?.evidence
  if (!ev) return null
  const v = ev.duration_ms
  if (typeof v === 'number' && Number.isFinite(v)) return v
  return null
})

const evidenceConnector = computed<string | null>(() => {
  const ev = selectedResult.value?.evidence
  if (!ev) return null
  const v = ev.connector
  return typeof v === 'string' && v ? v : null
})

const evidenceStderr = computed<string | null>(() => {
  const ev = selectedResult.value?.evidence
  if (!ev) return null
  const v = ev.stderr
  if (typeof v !== 'string' || !v) return null
  return v.length > MAX_STDERR_LENGTH ? `${v.slice(0, MAX_STDERR_LENGTH)}…(truncated)` : v
})

const hasEvidenceMeta = computed(() =>
  !!evidenceSqlHash.value
  || evidenceDurationMs.value !== null
  || !!evidenceConnector.value
  || evidenceRowCount.value !== null,
)

const evidenceEmptyMessage = computed(() => {
  if (!selectedResult.value?.evidence) return '无证据数据'
  if (evidenceRowCount.value === 0) return 'SQL 成功执行，无返回行'
  return 'evidence 中不包含 rows / columns'
})

const rawJsonText = computed(() => {
  const ev = selectedResult.value?.evidence
  if (!ev) return ''
  try {
    return JSON.stringify(ev, null, 2)
  } catch {
    return String(ev)
  }
})

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function openEvidence(row: InspectionResultRow) {
  selectedResult.value = row
  showRawJson.value = false
}

function closeEvidence() {
  selectedResult.value = null
  showRawJson.value = false
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
