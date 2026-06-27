<template>
  <OpsPage>
    <OpsPageHeader title="巡检项" subtitle="管理 inspection run_type 使用的标准巡检项。" icon="rule" />

    <OpsFilterBar
      :keyword="keyword"
      compact
      attached
      @update:keyword="keyword = $event"
      @search="loadItems"
      @reset="keyword = ''; dbTypeFilter = ''; sourceFilter = ''; inspectionTypeFilter = ''; loadItems()"
    >
      <template #tools>
        <select v-model="sourceFilter" class="field-input w-36 text-xs" @change="loadItems">
          <option value="">全部来源</option>
          <option value="custom">自定义 SQL</option>
          <option value="batch_verify">批量校验</option>
        </select>
        <select v-model="dbTypeFilter" class="field-input w-36 text-xs" @change="loadItems">
          <option value="">全部 DB 类型</option>
          <option value="ORACLE">Oracle</option>
          <option value="SQLSERVER">SQL Server</option>
          <option value="MYSQL">MySQL</option>
          <option value="POSTGRESQL">PostgreSQL</option>
        </select>
        <select v-model="inspectionTypeFilter" class="field-input w-40 text-xs" @change="loadItems">
          <option value="">全部巡检类型</option>
          <option v-for="t in inspectionTypes" :key="t" :value="t">{{ t }}</option>
        </select>
      </template>
      <template #actions>
        <button
          v-if="selectedIds.length"
          type="button"
          class="ops-danger-button"
          @click="batchDisable"
        >
          批量禁用 ({{ selectedIds.length }})
        </button>
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
            <select v-model="form.check_code" class="field-input" :disabled="isCheckCodeLocked">
              <option value="DB_READONLY_SQL_EXEC">DB_READONLY_SQL_EXEC</option>
            </select>
            <span v-if="isCheckCodeLocked" class="mt-1 text-xs text-on-surface-variant">
              系统默认项不可修改 check_code
            </span>
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
              <option value="SQLSERVER">SQL Server</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">巡检类型</span>
            <div class="flex items-center gap-2">
              <select v-model="form.inspection_type" class="field-input flex-1">
                <option value="">（不指定）</option>
                <option v-for="t in inspectionTypes" :key="t" :value="t">{{ t }}</option>
              </select>
              <button
                v-if="!showNewTypeInput"
                type="button"
                class="ops-secondary-button"
                title="新增巡检类型"
                @click="showNewTypeInput = true"
              >
                <span class="material-symbols-outlined text-[16px]">add</span>
              </button>
              <template v-else>
                <input
                  v-model.trim="newTypeDraft"
                  class="field-input flex-1"
                  maxlength="64"
                  placeholder="输入新类型回车确认"
                  @keydown.enter.prevent="confirmNewType"
                  @keydown.esc.prevent="cancelNewType"
                />
                <button
                  type="button"
                  class="ops-primary-button"
                  title="确认"
                  :disabled="!newTypeDraft"
                  @click="confirmNewType"
                >
                  <span class="material-symbols-outlined text-[16px]">check</span>
                </button>
                <button
                  type="button"
                  class="ops-secondary-button"
                  title="取消"
                  @click="cancelNewType"
                >
                  <span class="material-symbols-outlined text-[16px]">close</span>
                </button>
              </template>
            </div>
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
        <div class="field-card">
          <div class="flex items-center justify-between mb-2">
            <span class="field-label mb-0">
              目标实例
              <span class="text-xs text-on-surface-variant ml-1">({{ verifyForm.db_type_code }} — 已选 {{ verifyForm.selectedInstanceIds.length }})</span>
            </span>
            <button type="button" class="text-xs text-primary hover:underline" @click="toggleSelectAllInstances">
              {{ verifyForm.selectedInstanceIds.length === filteredInstances.length ? '取消全选' : '全选' }}
            </button>
          </div>
          <input
            v-model="verifyInstanceSearch"
            type="text"
            class="field-input mb-2 text-xs"
            placeholder="搜索实例名称或 IP..."
            :disabled="verifyRunning"
          />
          <div class="max-h-[220px] overflow-y-auto space-y-1 rounded border border-outline-variant/40 p-2">
            <label
              v-for="i in filteredInstances"
              :key="i.id"
              class="flex items-center gap-2 rounded px-2 py-1.5 text-xs cursor-pointer hover:bg-surface-container-high transition-colors"
              :class="verifyForm.selectedInstanceIds.includes(i.id) ? 'bg-primary/10' : ''"
            >
              <input
                type="checkbox"
                :value="i.id"
                :checked="verifyForm.selectedInstanceIds.includes(i.id)"
                @change="toggleInstanceSelection(i.id)"
                :disabled="verifyRunning"
                class="rounded"
              />
              <span class="font-mono text-on-surface">{{ i.instance_name }}</span>
              <span class="text-on-surface-variant">{{ i.server_ip }}:{{ i.port }}</span>
              <span class="text-on-surface-variant/60 text-[10px]">{{ i.cluster_type || '-' }}</span>
              <span class="text-on-surface-variant/60 text-[10px]">{{ i.node_role }}</span>
              <span class="text-on-surface-variant/60 text-[10px]">{{ i.db_version || '-' }}</span>
            </label>
            <p v-if="!filteredInstances.length" class="text-xs text-on-surface-variant px-2 py-2">无匹配实例</p>
          </div>
        </div>
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
            :disabled="verifyRunning || !verifyForm.selectedInstanceIds.length"
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
            <th class="whitespace-nowrap px-4 py-3 w-10">
              <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" class="rounded" />
            </th>
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
            <td class="whitespace-nowrap px-4 py-3">
              <input type="checkbox" :checked="selectedIds.includes(item.id)" @change="toggleItemSelection(item.id)" class="rounded" />
            </td>
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
const dbTypeFilter = ref('')
const sourceFilter = ref('')
const inspectionTypeFilter = ref('')
const inspectionTypes = ref<string[]>([])
const showNewTypeInput = ref(false)
const newTypeDraft = ref('')

function confirmNewType() {
  const value = newTypeDraft.value.trim()
  if (!value) return
  if (!inspectionTypes.value.includes(value)) {
    inspectionTypes.value = [...inspectionTypes.value, value].sort()
  }
  form.inspection_type = value
  newTypeDraft.value = ''
  showNewTypeInput.value = false
}

function cancelNewType() {
  newTypeDraft.value = ''
  showNewTypeInput.value = false
}
const selectedIds = ref<number[]>([])
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
  selectedInstanceIds: [] as number[],
  db_type_code: '',
  sql_text: '',
  timeout_seconds: 30,
  max_rows: 200,
})

const verifyInstanceSearch = ref('')
const instances = ref<InstanceRow[]>([])
const filteredInstances = computed(() => {
  let list = instances.value
  if (verifyForm.db_type_code) {
    list = list.filter((i) => (i.db_type_code || '').toUpperCase() === verifyForm.db_type_code.toUpperCase())
  }
  const kw = verifyInstanceSearch.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((i) =>
      (i.instance_name || '').toLowerCase().includes(kw)
      || (i.server_ip || '').toLowerCase().includes(kw)
      || (i.instance_code || '').toLowerCase().includes(kw)
    )
  }
  return list
})

interface ItemForm {
  item_code: string
  item_name: string
  check_code: string
  target_scope: 'db_instance' | 'server'
  severity: 'info' | 'warning' | 'critical'
  enabled: boolean
  description: string
  db_type_code: string
  inspection_type: string
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
  inspection_type: '',
})

const needsVerificationForEnable = computed(
  () => form.check_code === 'DB_READONLY_SQL_EXEC' && !sqlValidationResult.value?.valid,
)

// Plan 2026-06-26: 编辑系统默认项时锁定 check_code 字段（不允许改）
const isCheckCodeLocked = computed(
  () => !!editingId.value && form.check_code !== 'DB_READONLY_SQL_EXEC',
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
  // Plan 2026-06-26: 默认 DB_READONLY_SQL_EXEC，点新增直接进 SQL 模式
  form.check_code = 'DB_READONLY_SQL_EXEC'
  form.target_scope = 'db_instance'
  form.severity = 'warning'
  form.enabled = true
  form.description = ''
  form.db_type_code = ''
  form.inspection_type = ''
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
    const params: { enabled?: boolean; db_type_code?: string; source?: string; inspection_type?: string } = {}
    if (dbTypeFilter.value) params.db_type_code = dbTypeFilter.value
    if (sourceFilter.value) params.source = sourceFilter.value
    if (inspectionTypeFilter.value) params.inspection_type = inspectionTypeFilter.value
    items.value = await assetsApi.listInspectionItems(params)
  } finally {
    loading.value = false
  }
}

async function loadInstances() {
  try {
    const res = await assetsApi.listInstances({ page_size: 500 })
    instances.value = res.items || []
  } catch {
    instances.value = []
  }
}

async function loadInspectionTypes() {
  try {
    inspectionTypes.value = await assetsApi.listInspectionTypes()
  } catch {
    inspectionTypes.value = []
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
  verifyForm.selectedInstanceIds = []
  verifyInstanceSearch.value = ''
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
  if (!verifyForm.selectedInstanceIds.length) {
    verifyError.value = '请选择至少一个目标实例'
    return
  }
  verifyRunning.value = true
  verifyError.value = ''
  verifyResult.value = null
  try {
    const launch = await assetsApi.verifyInspectionSql({
      instance_ids: verifyForm.selectedInstanceIds,
      db_type_code: verifyForm.db_type_code,
      sql_text: verifyForm.sql_text,
      timeout_seconds: verifyForm.timeout_seconds,
      max_rows: verifyForm.max_rows,
    })
    // Poll the first verify run; the result shows per-instance status
    verifyRunId.value = launch.verify_run_ids[0]
    if (verifyRunId.value) startVerifyPolling(verifyRunId.value)
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

function toggleInstanceSelection(id: number) {
  const idx = verifyForm.selectedInstanceIds.indexOf(id)
  if (idx >= 0) {
    verifyForm.selectedInstanceIds.splice(idx, 1)
  } else {
    verifyForm.selectedInstanceIds.push(id)
  }
}

function toggleSelectAllInstances() {
  if (verifyForm.selectedInstanceIds.length === filteredInstances.value.length) {
    verifyForm.selectedInstanceIds = []
  } else {
    verifyForm.selectedInstanceIds = filteredInstances.value.map((i) => i.id)
  }
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

const allSelected = computed(() =>
  filteredItems.value.length > 0 && filteredItems.value.every((i) => selectedIds.value.includes(i.id))
)

function toggleItemSelection(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

function toggleSelectAll() {
  if (allSelected.value) {
    const visible = new Set(filteredItems.value.map((i) => i.id))
    selectedIds.value = selectedIds.value.filter((id) => !visible.has(id))
  } else {
    const existing = new Set(selectedIds.value)
    for (const i of filteredItems.value) existing.add(i.id)
    selectedIds.value = Array.from(existing)
  }
}

async function batchDisable() {
  if (!selectedIds.value.length) return
  if (!confirm(`确认禁用 ${selectedIds.value.length} 个巡检项？`)) return
  try {
    const result = await assetsApi.batchDisableInspectionItems(selectedIds.value)
    alert(`已禁用 ${result.disabled.length} 个${result.skipped.length ? `，${result.skipped.length} 个已是禁用状态` : ''}`)
    selectedIds.value = []
    await loadItems()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '批量禁用失败')
  }
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

onMounted(() => {
  loadItems()
  loadInspectionTypes()
})
</script>
