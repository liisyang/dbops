<template>
  <OpsPage>
    <OpsPageHeader title="备份状态" subtitle="按实例 + 备份类型展示最新一次 SQL 采集结果。" icon="backup" />

    <OpsFilterBar
      :keyword="filters.keyword"
      compact
      attached
      @update:keyword="filters.keyword = $event"
      @search="loadLatest"
      @reset="resetFilters"
    >
      <template #actions>
        <button type="button" class="ops-secondary-button" @click="loadLatest">
          <span class="material-symbols-outlined text-[18px]">refresh</span>
          刷新
        </button>
        <button
          type="button"
          class="ops-secondary-button"
          :disabled="loading"
          @click="openCollectModal"
        >
          <span class="material-symbols-outlined text-[18px]">play_arrow</span>
          采集一次
        </button>
      </template>

      <template #filters>
        <select v-model="filters.db_type_code" class="field-input">
          <option value="">全部 DB 类型</option>
          <option value="ORACLE">Oracle</option>
          <option value="POSTGRESQL">PostgreSQL</option>
          <option value="MYSQL">MySQL</option>
          <option value="MSSQL">SQL Server</option>
        </select>
        <select v-model="filters.last_status" class="field-input">
          <option value="">全部状态</option>
          <option value="success">success</option>
          <option value="warning">warning</option>
          <option value="failed">failed</option>
          <option value="unknown">unknown</option>
        </select>
        <input
          v-model.trim="filters.backup_type"
          class="field-input"
          placeholder="备份类型 (RMAN / pg_basebackup ...)"
        />
      </template>
    </OpsFilterBar>

    <OpsSectionCard title="最新备份状态">
      <OpsTableShell :loading="loading" :empty="!rows.length && !loading">
        <table class="w-full text-sm">
          <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
            <tr>
              <th class="whitespace-nowrap px-4 py-3">实例</th>
              <th class="whitespace-nowrap px-4 py-3">DB 类型</th>
              <th class="whitespace-nowrap px-4 py-3">备份类型</th>
              <th class="whitespace-nowrap px-4 py-3">状态</th>
              <th class="whitespace-nowrap px-4 py-3">最近成功</th>
              <th class="whitespace-nowrap px-4 py-3">RPO 时间</th>
              <th class="whitespace-nowrap px-4 py-3">距今</th>
              <th class="whitespace-nowrap px-4 py-3">采集时间</th>
              <th class="whitespace-nowrap px-4 py-3">消息</th>
              <th class="whitespace-nowrap px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.id"
              class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
            >
              <td class="whitespace-nowrap px-4 py-3">
                <div class="flex flex-col">
                  <span class="text-on-surface font-medium">{{ row.instance_name || '-' }}</span>
                  <span class="text-xs text-on-surface-variant">{{ row.host }}:{{ row.port }}</span>
                </div>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">
                {{ row.db_type_code || '-' }}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs">{{ row.backup_type || '-' }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs">
                <span
                  class="inline-flex items-center px-2 py-0.5 rounded-full border"
                  :class="getBackupStatusClass(row.last_status)"
                >
                  {{ row.last_status || '-' }}
                </span>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">
                {{ formatTime(row.last_success_at) }}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">
                {{ formatTime(row.recovery_point_at) }}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">
                {{ formatAge(row.age_minutes) }}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">
                {{ formatTime(row.collected_at) }}
              </td>
              <td class="px-4 py-3 text-xs text-on-surface-variant max-w-[260px] truncate" :title="row.message || ''">
                {{ row.message || '-' }}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs">
                <button type="button" class="ops-secondary-button !px-2 !py-1" @click="viewHistory(row)">
                  <span class="material-symbols-outlined text-[16px]">history</span>
                  历史
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
    </OpsSectionCard>

    <OpsModal
      :open="showHistory"
      :title="historyTitle"
      size="xl"
      @close="showHistory = false"
    >
      <div class="space-y-3">
        <p v-if="!historyLoading && history.length === 0" class="text-sm text-on-surface-variant">
          暂无历史记录
        </p>
        <table v-else class="w-full text-sm">
          <thead class="text-xs text-on-surface-variant">
            <tr class="border-b border-white/10">
              <th class="text-left py-2 pr-3">采集时间</th>
              <th class="text-left py-2 pr-3">状态</th>
              <th class="text-left py-2 pr-3">最近成功</th>
              <th class="text-left py-2 pr-3">耗时(s)</th>
              <th class="text-left py-2 pr-3">消息</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in history" :key="h.id" class="border-b border-white/5">
              <td class="py-1.5 pr-3 text-xs">{{ formatTime(h.collected_at) }}</td>
              <td class="py-1.5 pr-3 text-xs">
                <span
                  class="inline-flex items-center px-2 py-0.5 rounded-full border"
                  :class="getBackupStatusClass(h.last_status)"
                >
                  {{ h.last_status }}
                </span>
              </td>
              <td class="py-1.5 pr-3 text-xs">{{ formatTime(h.last_success_at) }}</td>
              <td class="py-1.5 pr-3 text-xs">{{ h.duration_seconds ?? '-' }}</td>
              <td class="py-1.5 pr-3 text-xs text-on-surface-variant">{{ h.message || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </OpsModal>

    <OpsModal
      :open="showCollect"
      title="采集一次备份状态"
      size="lg"
      @close="showCollect = false"
    >
      <form class="space-y-4" @submit.prevent="submitCollect">
        <div v-if="collectError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ collectError }}
        </div>
        <label class="block field-card">
          <span class="field-label">DB 类型</span>
          <select v-model="collectForm.db_type_code" class="field-input" required>
            <option value="ORACLE">Oracle</option>
            <option value="POSTGRESQL">PostgreSQL</option>
            <option value="MYSQL">MySQL</option>
            <option value="MSSQL">SQL Server</option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">实例 ID 列表（逗号分隔）</span>
          <input v-model.trim="collectForm.instance_ids_text" class="field-input" placeholder="例如 1001, 1002" required />
        </label>
        <label class="block field-card">
          <span class="field-label">备份类型 (可选)</span>
          <input v-model.trim="collectForm.backup_type" class="field-input" placeholder="RMAN / pg_basebackup" />
        </label>
        <label class="block field-card">
          <span class="field-label">SQL <span class="text-red-400">*</span></span>
          <textarea
            v-model.trim="collectForm.sql_text"
            class="field-input font-mono text-xs"
            rows="6"
            placeholder="SELECT 'last_success_at', 'last_status' FROM ..."
            required
          />
        </label>
        <div class="grid grid-cols-2 gap-4">
          <label class="block field-card">
            <span class="field-label">超时 (秒)</span>
            <input v-model.number="collectForm.timeout_seconds" type="number" min="1" max="120" class="field-input" />
          </label>
          <label class="block field-card">
            <span class="field-label">最大行数</span>
            <input v-model.number="collectForm.max_rows" type="number" min="1" max="1000" class="field-input" />
          </label>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button type="button" class="ops-secondary-button" @click="showCollect = false">取消</button>
          <button type="submit" class="ops-primary-button" :disabled="collectSubmitting">
            提交
          </button>
        </div>
      </form>
    </OpsModal>
  </OpsPage>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { backupApi, type BackupStatusHistory, type BackupStatusLatest } from '@/api/backup'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsFilterBar from '@/components/ops/OpsFilterBar.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import OpsModal from '@/components/ops/OpsModal.vue'
import { getBackupStatusClass } from '@/composables/useStatusFormatters'

const filters = ref({
  db_type_code: '',
  last_status: '',
  backup_type: '',
  keyword: '',
})

const rows = ref<BackupStatusLatest[]>([])
const loading = ref(false)

async function loadLatest() {
  loading.value = true
  try {
    const params: Record<string, string | number> = { limit: 200 }
    if (filters.value.db_type_code) params.db_type_code = filters.value.db_type_code
    if (filters.value.last_status) params.last_status = filters.value.last_status
    if (filters.value.backup_type) params.backup_type = filters.value.backup_type
    if (filters.value.keyword) params.keyword = filters.value.keyword
    rows.value = await backupApi.listLatest(params)
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.value = { db_type_code: '', last_status: '', backup_type: '', keyword: '' }
  loadLatest()
}

function formatTime(s: string | null | undefined): string {
  if (!s) return '-'
  try {
    const d = new Date(s)
    if (isNaN(d.getTime())) return s
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return s
  }
}

function formatAge(min: number | null | undefined): string {
  if (min === null || min === undefined) return '-'
  if (min < 60) return `${min}m`
  if (min < 60 * 24) return `${Math.round(min / 60)}h`
  return `${Math.round(min / 60 / 24)}d`
}

const showHistory = ref(false)
const history = ref<BackupStatusHistory[]>([])
const historyLoading = ref(false)
const historyTitle = ref('历史')
async function viewHistory(row: BackupStatusLatest) {
  showHistory.value = true
  historyTitle.value = `${row.instance_name} / ${row.backup_type || 'default'} 历史`
  historyLoading.value = true
  try {
    history.value = await backupApi.listHistory({ instance_id: row.instance_id, limit: 50 })
  } finally {
    historyLoading.value = false
  }
}

const showCollect = ref(false)
const collectSubmitting = ref(false)
const collectError = ref('')
const collectForm = ref({
  db_type_code: 'ORACLE',
  instance_ids_text: '',
  backup_type: '',
  sql_text: '',
  timeout_seconds: 30,
  max_rows: 200,
})

function openCollectModal() {
  collectError.value = ''
  showCollect.value = true
}

async function submitCollect() {
  collectError.value = ''
  collectSubmitting.value = true
  try {
    const instance_ids = collectForm.value.instance_ids_text
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n) && n > 0)
    if (instance_ids.length === 0) {
      collectError.value = '请填写至少一个有效的 instance_id'
      return
    }
    await backupApi.collect({
      instance_ids,
      db_type_code: collectForm.value.db_type_code,
      backup_type: collectForm.value.backup_type || null,
      sql_text: collectForm.value.sql_text,
      timeout_seconds: collectForm.value.timeout_seconds,
      max_rows: collectForm.value.max_rows,
    })
    showCollect.value = false
    await loadLatest()
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    collectError.value = e?.response?.data?.detail || '提交失败'
  } finally {
    collectSubmitting.value = false
  }
}

onMounted(loadLatest)
</script>
