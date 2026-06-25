<template>
  <OpsPage>
    <OpsPageHeader title="巡检项" subtitle="管理 inspection run_type 使用的标准巡检项。" icon="rule" />

    <OpsFilterBar
      :keyword="keyword"
      compact
      attached
      @update:keyword="keyword = $event"
      @search="loadItems"
      @reset="keyword = ''; loadItems()"
    >
      <template #actions>
        <button type="button" class="ops-secondary-button" @click="loadItems">
          <span class="material-symbols-outlined text-[18px]">refresh</span>
          刷新
        </button>
        <button type="button" class="ops-primary-button" @click="openCreate">
          <span class="material-symbols-outlined text-[18px]">add</span>
          新增巡检项
        </button>
      </template>
    </OpsFilterBar>

    <OpsModal :open="showEditor" :title="editingId ? '编辑巡检项' : '新增巡检项'" size="xl" @close="cancelEdit">
      <form class="space-y-5" @submit.prevent="submitForm">
        <div v-if="formError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ formError }}
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card">
            <span class="field-label">编码 <span class="text-red-400">*</span></span>
            <input v-model.trim="form.item_code" class="field-input" :disabled="!!editingId" required />
          </label>
          <label class="block field-card">
            <span class="field-label">名称 <span class="text-red-400">*</span></span>
            <input v-model.trim="form.item_name" class="field-input" required />
          </label>
          <label class="block field-card">
            <span class="field-label">check_code <span class="text-red-400">*</span></span>
            <input v-model.trim="form.check_code" class="field-input" required />
          </label>
          <label class="block field-card">
            <span class="field-label">目标范围</span>
            <select v-model="form.target_scope" class="field-input">
              <option value="db_instance">db_instance</option>
              <option value="server">server</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">DB 类型（DB_READONLY_SQL_EXEC 必填）</span>
            <select v-model="form.db_type_code" class="field-input">
              <option value="">（不指定）</option>
              <option value="ORACLE">Oracle</option>
              <option value="POSTGRESQL">PostgreSQL</option>
              <option value="MYSQL">MySQL</option>
              <option value="MSSQL">SQL Server</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">严重级别</span>
            <select v-model="form.severity" class="field-input">
              <option value="info">info</option>
              <option value="warning">warning</option>
              <option value="critical">critical</option>
            </select>
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">描述</span>
            <textarea v-model.trim="form.description" class="field-input min-h-[80px] resize-y" />
          </label>

          <template v-if="form.check_code === 'DB_READONLY_SQL_EXEC'">
            <label class="block field-card sm:col-span-2">
              <span class="field-label">SQL <span class="text-red-400">*</span></span>
              <textarea
                v-model.trim="sqlForm.sql_text"
                class="field-input font-mono text-xs min-h-[240px] resize-y"
                placeholder="SELECT 'RESULT_STATUS', 'MESSAGE' FROM ..."
              />
              <span class="mt-1 text-xs text-on-surface-variant">
                只允许 SELECT / WITH / SHOW，禁止 INSERT/UPDATE/DELETE/DROP/EXEC 等关键字，分号仅可作为末尾终止符。
              </span>
            </label>
            <div class="grid grid-cols-2 gap-4 sm:col-span-2 sm:grid-cols-4">
              <label class="block field-card">
                <span class="field-label">超时 (秒)</span>
                <input v-model.number="sqlForm.timeout_seconds" type="number" min="1" max="120" class="field-input" />
              </label>
              <label class="block field-card">
                <span class="field-label">最大行数</span>
                <input v-model.number="sqlForm.max_rows" type="number" min="1" max="1000" class="field-input" />
              </label>
              <label class="block field-card">
                <span class="field-label">状态列</span>
                <input v-model.trim="sqlForm.result_status_column" class="field-input" placeholder="RESULT_STATUS" />
              </label>
              <label class="block field-card">
                <span class="field-label">消息列</span>
                <input v-model.trim="sqlForm.message_column" class="field-input" placeholder="MESSAGE" />
              </label>
            </div>
            <div class="sm:col-span-2 flex flex-wrap items-center gap-2 text-xs">
              <button type="button" class="ops-secondary-button !py-1" :disabled="validating" @click="onValidateSql">
                <span class="material-symbols-outlined text-[16px]">{{ validating ? 'hourglass_empty' : 'verified' }}</span>
                {{ validating ? '校验中...' : '校验 SQL' }}
              </button>
              <button type="button" class="ops-secondary-button !py-1" @click="openVerifyModal">
                <span class="material-symbols-outlined text-[16px]">play_circle</span>
                验证 SQL
              </button>
              <span v-if="sqlValidationResult" class="text-xs" :class="sqlValidationResult.valid ? 'text-emerald-300' : 'text-red-300'">
                {{ sqlValidationResult.message }}
              </span>
            </div>
          </template>

          <label v-else class="block field-card sm:col-span-2">
            <span class="field-label">规则配置 (JSON)</span>
            <textarea v-model.trim="ruleConfigInput" class="field-input min-h-[120px] resize-y font-mono text-xs" />
          </label>
        </div>

        <label class="inline-flex items-center gap-2 text-sm text-on-surface">
          <input
            v-model="form.enabled"
            type="checkbox"
            class="h-4 w-4"
            :disabled="needsVerificationForEnable"
          />
          <span :class="needsVerificationForEnable ? 'text-on-surface-variant' : ''">启用</span>
          <span v-if="needsVerificationForEnable" class="text-xs text-amber-300">
            （DB_READONLY_SQL_EXEC 项必须先通过验证 SQL）
          </span>
        </label>

        <div class="flex items-center justify-end gap-3 border-t border-outline-variant/40 pt-4">
          <button type="button" class="ops-secondary-button" @click="cancelEdit">取消</button>
          <button type="submit" class="ops-primary-button" :disabled="saving">
            <span class="material-symbols-outlined text-[18px]">{{ saving ? 'hourglass_empty' : 'check' }}</span>
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </form>
    </OpsModal>

    <OpsModal :open="showVerify" title="验证 SQL" size="xl" @close="closeVerifyModal">
      <div class="space-y-4">
        <div v-if="verifyError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ verifyError }}
        </div>
        <label class="block field-card">
          <span class="field-label">目标实例</span>
          <select v-model.number="verifyForm.instance_id" class="field-input" :disabled="verifyRunning">
            <option :value="0">请选择实例</option>
            <option v-for="i in filteredInstances" :key="i.id" :value="i.id">
              {{ i.instance_name }} ({{ i.db_type }} / {{ i.server_ip }}:{{ i.port }})
            </option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">DB 类型</span>
          <select v-model="verifyForm.db_type_code" class="field-input" :disabled="verifyRunning">
            <option value="ORACLE">Oracle</option>
            <option value="POSTGRESQL">PostgreSQL</option>
            <option value="MYSQL">MySQL</option>
            <option value="MSSQL">SQL Server</option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">超时 (秒)</span>
          <input v-model.number="verifyForm.timeout_seconds" type="number" min="1" max="120" class="field-input" :disabled="verifyRunning" />
        </label>
        <label class="block field-card">
          <span class="field-label">最大行数</span>
          <input v-model.number="verifyForm.max_rows" type="number" min="1" max="1000" class="field-input" :disabled="verifyRunning" />
        </label>
        <label class="block field-card">
          <span class="field-label">SQL 预览</span>
          <textarea
            v-model="verifyForm.sql_text"
            class="field-input font-mono text-xs min-h-[200px] resize-y"
            :disabled="verifyRunning"
          />
        </label>

        <div v-if="verifyResult" class="space-y-3 rounded-lg border border-white/10 p-3">
          <div class="flex flex-wrap items-center gap-3 text-xs">
            <span class="text-on-surface-variant">状态: <strong>{{ verifyResult.status }}</strong></span>
            <span v-if="verifyResult.sql_hash" class="text-on-surface-variant">sql_hash: {{ verifyResult.sql_hash.slice(0, 12) }}...</span>
            <span v-if="verifyResult.duration_ms" class="text-on-surface-variant">耗时: {{ verifyResult.duration_ms }} ms</span>
          </div>
          <p v-if="verifyResult.message" class="text-sm">{{ verifyResult.message }}</p>
          <div v-if="verifyResult.columns && verifyResult.columns.length" class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead class="bg-surface-container text-on-surface-variant">
                <tr>
                  <th v-for="(c, idx) in verifyResult.columns" :key="idx" class="whitespace-nowrap px-2 py-1 text-left">
                    {{ c }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, ri) in (verifyResult.rows || []).slice(0, 20)" :key="ri" class="border-t border-white/5">
                  <td v-for="(cell, ci) in r" :key="ci" class="whitespace-nowrap px-2 py-1">
                    {{ formatCell(cell) }}
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="(verifyResult.rows || []).length > 20" class="mt-1 text-xs text-on-surface-variant">
              仅展示前 20 行，共 {{ verifyResult.rows.length }} 行
            </p>
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 border-t border-outline-variant/40 pt-3">
          <button type="button" class="ops-secondary-button" @click="closeVerifyModal">
            关闭
          </button>
          <button
            type="button"
            class="ops-primary-button"
            :disabled="verifyRunning || !verifyForm.instance_id"
            @click="onRunVerify"
          >
            {{ verifyRunning ? '执行中...' : (verifyResult ? '再次执行' : '执行') }}
          </button>
        </div>
      </div>
    </OpsModal>

    <OpsTableShell :loading="loading" :empty="!filteredItems.length && !loading">
      <table class="w-full text-sm">
        <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
          <tr>
            <th class="whitespace-nowrap px-4 py-3">编码</th>
            <th class="whitespace-nowrap px-4 py-3">名称</th>
            <th class="whitespace-nowrap px-4 py-3">check_code</th>
            <th class="whitespace-nowrap px-4 py-3">DB 类型</th>
            <th class="whitespace-nowrap px-4 py-3">范围</th>
            <th class="whitespace-nowrap px-4 py-3">级别</th>
            <th class="whitespace-nowrap px-4 py-3">状态</th>
            <th class="whitespace-nowrap px-4 py-3">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filteredItems" :key="item.id" class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high">
            <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ item.item_code }}</td>
            <td class="whitespace-nowrap px-4 py-3">{{ item.item_name }}</td>
            <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ item.check_code }}</td>
            <td class="whitespace-nowrap px-4 py-3 text-xs">{{ item.db_type_code || '-' }}</td>
            <td class="whitespace-nowrap px-4 py-3">{{ item.target_scope }}</td>
            <td class="whitespace-nowrap px-4 py-3">{{ item.severity }}</td>
            <td class="whitespace-nowrap px-4 py-3">
              <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="item.enabled ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-slate-400/30 bg-slate-400/10 text-slate-300'">
                {{ item.enabled ? '启用' : '禁用' }}
              </span>
            </td>
            <td class="whitespace-nowrap px-4 py-3">
              <button type="button" class="ops-icon-button" title="编辑" @click="openEdit(item)">
                <span class="material-symbols-outlined text-[18px]">edit</span>
              </button>
              <button
                v-if="item.enabled"
                type="button"
                class="ops-icon-button"
                title="禁用"
                @click="onDisable(item)"
              >
                <span class="material-symbols-outlined text-[18px]">toggle_off</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </OpsTableShell>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import OpsFilterBar from '@/components/ops/OpsFilterBar.vue'
import OpsModal from '@/components/ops/OpsModal.vue'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import { assetsApi } from '@/api/assets'
import type {
  InstanceRow,
  InspectionItemCreatePayload,
  InspectionItemRow,
  InspectionItemUpdatePayload,
} from '@/types/api'

const loading = ref(false)
const saving = ref(false)
const validating = ref(false)
const keyword = ref('')
const items = ref<InspectionItemRow[]>([])
const showEditor = ref(false)
const editingId = ref<number | null>(null)
const formError = ref('')
const ruleConfigInput = ref('{}')

const sqlForm = reactive({
  sql_text: '',
  timeout_seconds: 30,
  max_rows: 200,
  result_status_column: 'RESULT_STATUS',
  message_column: 'MESSAGE',
})

const sqlValidationResult = ref<{ valid: boolean; message: string } | null>(null)

const showVerify = ref(false)
const verifyRunning = ref(false)
const verifyError = ref('')
const verifyRunId = ref<number | null>(null)
const verifyResult = ref<{
  status: string
  verified: boolean
  sql_hash: string
  duration_ms: number
  columns: string[]
  rows: unknown[][]
  message: string
} | null>(null)
let verifyPollTimer: ReturnType<typeof setInterval> | null = null

const verifyForm = reactive({
  instance_id: 0,
  db_type_code: 'ORACLE',
  sql_text: '',
  timeout_seconds: 30,
  max_rows: 200,
})

const instances = ref<InstanceRow[]>([])
const filteredInstances = computed(() =>
  instances.value.filter((i) => !verifyForm.db_type_code || i.db_type === verifyForm.db_type_code),
)

interface ItemForm {
  item_code: string
  item_name: string
  check_code: string
  target_scope: 'db_instance' | 'server'
  severity: 'info' | 'warning' | 'critical'
  enabled: boolean
  description: string
  db_type_code: string
}

const form = reactive<ItemForm>({
  item_code: '',
  item_name: '',
  check_code: '',
  target_scope: 'db_instance',
  severity: 'warning',
  enabled: true,
  description: '',
  db_type_code: '',
})

const needsVerificationForEnable = computed(
  () => form.check_code === 'DB_READONLY_SQL_EXEC' && !sqlValidationResult.value?.valid,
)

const filteredItems = computed(() => {
  if (!keyword.value) return items.value
  const kw = keyword.value.toLowerCase()
  return items.value.filter((item) =>
    item.item_code.toLowerCase().includes(kw)
    || item.item_name.toLowerCase().includes(kw)
    || item.check_code.toLowerCase().includes(kw)
  )
})

function resetForm() {
  form.item_code = ''
  form.item_name = ''
  form.check_code = ''
  form.target_scope = 'db_instance'
  form.severity = 'warning'
  form.enabled = true
  form.description = ''
  form.db_type_code = ''
  sqlForm.sql_text = ''
  sqlForm.timeout_seconds = 30
  sqlForm.max_rows = 200
  sqlForm.result_status_column = 'RESULT_STATUS'
  sqlForm.message_column = 'MESSAGE'
  ruleConfigInput.value = '{}'
  sqlValidationResult.value = null
  formError.value = ''
}

async function loadItems() {
  loading.value = true
  try {
    items.value = await assetsApi.listInspectionItems()
  } finally {
    loading.value = false
  }
}

async function loadInstances() {
  try {
    const res = await assetsApi.listInstances({ limit: 500 })
    instances.value = res.items || []
  } catch {
    instances.value = []
  }
}

function openCreate() {
  editingId.value = null
  resetForm()
  showEditor.value = true
}

function openEdit(item: InspectionItemRow) {
  editingId.value = item.id
  form.item_code = item.item_code
  form.item_name = item.item_name
  form.check_code = item.check_code
  form.target_scope = item.target_scope
  form.severity = item.severity
  form.enabled = item.enabled
  form.description = item.description || ''
  form.db_type_code = (item as InspectionItemRow & { db_type_code?: string }).db_type_code || ''
  const rc = (item.rule_config || {}) as Record<string, unknown>
  if (form.check_code === 'DB_READONLY_SQL_EXEC') {
    const rule = rc as Record<string, unknown>
    sqlForm.sql_text = (rule.sql_text as string) || ''
    sqlForm.timeout_seconds = (rule.timeout_seconds as number) || 30
    sqlForm.max_rows = (rule.max_rows as number) || 200
    sqlForm.result_status_column = (rule.result_status_column as string) || 'RESULT_STATUS'
    sqlForm.message_column = (rule.message_column as string) || 'MESSAGE'
    ruleConfigInput.value = JSON.stringify({ executor_type: 'db_sql_readonly', ...rule }, null, 2)
  } else {
    ruleConfigInput.value = JSON.stringify(item.rule_config || {}, null, 2)
  }
  sqlValidationResult.value = null
  formError.value = ''
  showEditor.value = true
}

function cancelEdit() {
  showEditor.value = false
  editingId.value = null
}

function buildRuleConfig(): { value: Record<string, unknown> | null; error: string | null } {
  if (form.check_code !== 'DB_READONLY_SQL_EXEC') {
    const text = (ruleConfigInput.value || '').trim()
    if (!text) return { value: {}, error: null }
    try {
      const parsed = JSON.parse(text)
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return { value: null, error: '规则配置必须为 JSON 对象' }
      }
      return { value: parsed as Record<string, unknown>, error: null }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '格式错误'
      return { value: null, error: `规则配置 JSON 解析失败: ${msg}` }
    }
  }
  if (!sqlForm.sql_text.trim()) {
    return { value: null, error: 'SQL 不能为空' }
  }
  if (!form.db_type_code) {
    return { value: null, error: 'DB_READONLY_SQL_EXEC 必须指定 db_type_code' }
  }
  if (sqlForm.timeout_seconds < 1 || sqlForm.timeout_seconds > 120) {
    return { value: null, error: 'timeout_seconds 必须在 1~120 之间' }
  }
  if (sqlForm.max_rows < 1 || sqlForm.max_rows > 1000) {
    return { value: null, error: 'max_rows 必须在 1~1000 之间' }
  }
  return {
    value: {
      executor_type: 'db_sql_readonly',
      sql_text: sqlForm.sql_text,
      timeout_seconds: sqlForm.timeout_seconds,
      max_rows: sqlForm.max_rows,
      result_status_column: sqlForm.result_status_column || 'RESULT_STATUS',
      message_column: sqlForm.message_column || 'MESSAGE',
    },
    error: null,
  }
}

async function onValidateSql() {
  if (!form.db_type_code) {
    sqlValidationResult.value = { valid: false, message: '请先选择 DB 类型' }
    return
  }
  if (!sqlForm.sql_text.trim()) {
    sqlValidationResult.value = { valid: false, message: 'SQL 不能为空' }
    return
  }
  validating.value = true
  sqlValidationResult.value = null
  try {
    const r = await assetsApi.validateInspectionSql({
      db_type_code: form.db_type_code,
      sql_text: sqlForm.sql_text,
    })
    sqlValidationResult.value = {
      valid: r.valid,
      message: r.valid ? 'SQL 校验通过' : r.errors.join('; ') || 'SQL 校验未通过',
    }
    if (!r.valid && form.enabled) form.enabled = false
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } }
    sqlValidationResult.value = {
      valid: false,
      message: err?.response?.data?.detail || '校验请求失败',
    }
  } finally {
    validating.value = false
  }
}

function openVerifyModal() {
  if (!form.db_type_code) {
    formError.value = '请先选择 DB 类型'
    return
  }
  if (!sqlForm.sql_text.trim()) {
    formError.value = 'SQL 不能为空'
    return
  }
  verifyForm.db_type_code = form.db_type_code
  verifyForm.sql_text = sqlForm.sql_text
  verifyForm.timeout_seconds = sqlForm.timeout_seconds
  verifyForm.max_rows = sqlForm.max_rows
  verifyForm.instance_id = 0
  verifyError.value = ''
  verifyResult.value = null
  verifyRunId.value = null
  showVerify.value = true
  if (!instances.value.length) loadInstances()
}

function closeVerifyModal() {
  showVerify.value = false
  if (verifyPollTimer) {
    clearInterval(verifyPollTimer)
    verifyPollTimer = null
  }
  verifyRunId.value = null
}

async function onRunVerify() {
  if (!verifyForm.instance_id) {
    verifyError.value = '请选择目标实例'
    return
  }
  verifyRunning.value = true
  verifyError.value = ''
  verifyResult.value = null
  try {
    const launch = await assetsApi.verifyInspectionSql({
      instance_id: verifyForm.instance_id,
      db_type_code: verifyForm.db_type_code,
      sql_text: verifyForm.sql_text,
      timeout_seconds: verifyForm.timeout_seconds,
      max_rows: verifyForm.max_rows,
    })
    verifyRunId.value = launch.verify_run_id
    startVerifyPolling(launch.verify_run_id)
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } }
    verifyError.value = err?.response?.data?.detail || '提交验证失败'
    verifyRunning.value = false
  }
}

function startVerifyPolling(runId: number) {
  if (verifyPollTimer) clearInterval(verifyPollTimer)
  const startedAt = Date.now()
  verifyPollTimer = setInterval(async () => {
    if (Date.now() - startedAt > 120_000) {
      if (verifyPollTimer) clearInterval(verifyPollTimer)
      verifyPollTimer = null
      verifyRunning.value = false
      verifyError.value = '轮询超时（>120s），后端 AWX job 仍在执行，可稍后再次点击查询历史结果。'
      return
    }
    try {
      const r = await assetsApi.getVerifySqlResult(runId)
      verifyResult.value = r as typeof verifyResult.value
      if (r.status === 'success' || r.status === 'failed' || r.status === 'rejected') {
        if (verifyPollTimer) clearInterval(verifyPollTimer)
        verifyPollTimer = null
        verifyRunning.value = false
        if (r.status === 'success') {
          form.enabled = true
          sqlValidationResult.value = { valid: true, message: '已验证通过 SQL' }
        } else if (r.status === 'failed' || r.status === 'rejected') {
          form.enabled = false
          sqlValidationResult.value = { valid: false, message: r.message || '验证未通过' }
        }
      }
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      verifyError.value = err?.response?.data?.detail || '轮询失败'
    }
  }, 2500)
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}

async function onDisable(item: InspectionItemRow) {
  if (!confirm(`确认禁用巡检项「${item.item_code}」?`)) return
  try {
    await assetsApi.patchInspectionItem(item.id, { enabled: false } as InspectionItemUpdatePayload)
    await loadItems()
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } }
    alert(err?.response?.data?.detail || '禁用失败')
  }
}

async function submitForm() {
  if (!form.item_code || !form.item_name || !form.check_code) {
    formError.value = '请填写必填字段'
    return
  }

  saving.value = true
  formError.value = ''
  try {
    const parsed = buildRuleConfig()
    if (parsed.error || parsed.value === null) {
      formError.value = parsed.error || '规则配置不合法'
      saving.value = false
      return
    }
    const payload = {
      item_code: form.item_code,
      item_name: form.item_name,
      check_code: form.check_code,
      target_scope: form.target_scope,
      severity: form.severity,
      enabled: form.enabled,
      description: form.description,
      rule_config: parsed.value,
      db_type_code: form.db_type_code || undefined,
    }
    if (editingId.value) {
      await assetsApi.updateInspectionItem(editingId.value, payload as InspectionItemUpdatePayload)
    } else {
      await assetsApi.createInspectionItem(payload)
    }
    showEditor.value = false
    await loadItems()
  } catch (error: unknown) {
    const err = error as { response?: { data?: { detail?: string } } }
    formError.value = err?.response?.data?.detail || (error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadItems)
</script>
