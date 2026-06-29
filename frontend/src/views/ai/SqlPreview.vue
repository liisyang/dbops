<!--
  AI Copilot SQL 生成器（Phase 3.6 C13 — plan §5.2 + §5.3 + §20；
                              C14 — plan §6.1 + §8 SQL Execute）

  功能：
    - 选 instance（database_name 留空由后端 fallback）
    - 输入自然语言问题（user_question）
    - 点「生成 SQL」调 aiApi.sqlPreview
    - 展示 preview_safety_status（passed/rejected 徽章）+
      approved_sql（语法高亮用 <pre><code> 简化处理）+ errors/warnings
    - 「接受并写回会话」按钮（accepted）：调 sendMessage 把
      approved_sql + audit_id 写回 ai_chat_message
      （message_type='sql_preview' + metadata_json.preview_audit_id）
    - 「执行 SQL」按钮（C14 NEW）：passed 后调 aiApi.executeSql →
      AWX 异步执行 → 3s 轮询 getExecutionStatus → success/failed/
      timeout 终态。Callback 写 ai_chat_message(sql_result)，由 Chat
      流轮询读取渲染（见 ChatMessageBubble.vue）。

  错误码（plan §11）：
    404 InstanceNotFoundError → 实例不存在
    409 SnapshotUnavailableError → schema snapshot 未就绪（详细 reason）
    422 UnsupportedDbTypeError → db_type 不在 capabilities 支持范围
    502 Dify 不可用 / Workflow 失败
    503 FeatureDisabledError → AI_SQL_PREVIEW_ENABLED=false
    504 Dify 调用超时

  C14 SQL Execute 错误码：
    404 AuditNotFoundError — audit_id 不存在
    409 AuditNotPassedError / SnapshotPolicyMismatchError /
       AuditAlreadyRunningError
    422 AuditUnsafeOnExecuteError — Execute 时 AST 二次校验失败
    502 AwxLaunchError — AWX launch 失败
    503 FeatureDisabledError — AI_SQL_EXECUTION_ENABLED=false

  注意：
    - 200 响应里 preview_safety_status='rejected' 不是错误，要展示给用户看
    - 不复用 Chat 的 client_request_id 幂等（plan §14 C13 注释：SQL Preview
      无状态，前端自行防抖；见 AiSqlPreviewService docstring）
-->
<template>
  <OpsPage>
    <OpsPageHeader
      title="SQL 生成器"
      subtitle="基于 Dify sql-generator 的自然语言 → 只读 SQL（plan §5.2 + §5.3）"
    />

    <div class="grid gap-4 lg:grid-cols-1">
      <!-- 顶部：输入区 -->
      <OpsSectionCard>
        <template #header>
          <h2 class="text-base font-semibold text-on-surface">生成 SQL</h2>
        </template>

        <!-- 实例 + 数据库 -->
        <div class="grid gap-4 md:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-on-surface-variant">
              数据库实例 <span class="text-red-400">*</span>
            </label>
            <select
              v-model.number="form.instanceId"
              class="ops-input w-full"
              :disabled="loadingInstances || generating"
              @change="onInstanceChange"
            >
              <option :value="null" disabled>-- 请选择实例 --</option>
              <option
                v-for="inst in instanceOptions"
                :key="inst.id"
                :value="inst.id"
              >
                {{ inst.instance_name }}
                <template v-if="inst.db_type_code">
                  （{{ inst.db_type_code }} / {{ inst.server_ip || 'no-ip' }}:{{ inst.port || '-' }}）
                </template>
              </option>
            </select>
            <p
              v-if="instancesError"
              class="mt-1 text-xs text-red-400"
            >
              {{ instancesError }}
            </p>
            <p
              v-else-if="form.instanceId && selectedInstance && !supportedByPreview(selectedInstance.db_type_code)"
              class="mt-1 text-xs text-amber-400"
            >
              当前 db_type <code>{{ selectedInstance.db_type_code }}</code> 不在 capabilities 支持范围（{{ capabilities.sql_supported_db_types.join(', ') || '无' }}）
            </p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-on-surface-variant">
              数据库名（可选，留空由后端 fallback）
            </label>
            <input
              v-model="form.databaseName"
              type="text"
              maxlength="200"
              class="ops-input w-full"
              :disabled="generating"
              placeholder="<default>"
            />
          </div>
        </div>

        <!-- 用户问题 -->
        <div class="mt-4">
          <label class="mb-1 block text-xs font-medium text-on-surface-variant">
            问题描述 <span class="text-red-400">*</span>
          </label>
          <textarea
            v-model="form.userQuestion"
            rows="3"
            maxlength="8000"
            class="ops-input w-full resize-y"
            :disabled="generating"
            placeholder="例：查询最近一周下单的用户名和邮箱（不要含 DELETE/DROP/INSERT 等非只读关键词）"
          />
          <div class="mt-1 flex items-center justify-between text-xs text-on-surface-variant">
            <span>{{ form.userQuestion.length }} / 8000</span>
            <span v-if="form.userQuestion && layer1Hint" class="text-amber-400">
              ⚠ {{ layer1Hint }}
            </span>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="mt-4 flex items-center gap-2">
          <button
            type="button"
            class="ops-primary-button inline-flex items-center gap-1.5 px-4 py-2 text-sm"
            :disabled="!canSubmit"
            @click="onGenerate"
          >
            <span
              v-if="generating"
              class="material-symbols-outlined animate-spin text-[16px]"
            >sync</span>
            <span v-else class="material-symbols-outlined text-[16px]">
              auto_awesome
            </span>
            {{ generating ? '生成中…' : '生成 SQL' }}
          </button>
          <button
            v-if="result || formError"
            type="button"
            class="ops-secondary-button inline-flex items-center gap-1.5 px-4 py-2 text-sm"
            @click="onReset"
          >
            <span class="material-symbols-outlined text-[16px]">refresh</span>
            重置
          </button>
        </div>

        <!-- 表单级错误（如 HTTP 5xx） -->
        <div
          v-if="formError"
          class="mt-3 flex items-start gap-2 rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"
        >
          <span class="material-symbols-outlined mt-0.5 text-[18px]">error</span>
          <div class="flex-1">
            <p class="font-medium">{{ formError.title }}</p>
            <p v-if="formError.detail" class="mt-1 text-xs text-red-300/80">
              {{ formError.detail }}
            </p>
            <p v-if="formError.hint" class="mt-1 text-xs text-amber-300/80">
              {{ formError.hint }}
            </p>
          </div>
        </div>
      </OpsSectionCard>

      <!-- 底部：结果区 -->
      <OpsSectionCard v-if="result">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <h2 class="text-base font-semibold text-on-surface">预览结果</h2>
            <!-- 状态徽章 -->
            <span
              v-if="result.preview_safety_status === 'passed'"
              class="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300"
            >
              <span class="material-symbols-outlined text-[14px]">check_circle</span>
              PASSED
            </span>
            <span
              v-else
              class="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-xs text-red-300"
            >
              <span class="material-symbols-outlined text-[14px]">cancel</span>
              REJECTED
            </span>
          </div>
        </template>

        <!-- 元信息 -->
        <div class="grid gap-3 text-xs text-on-surface-variant md:grid-cols-2 lg:grid-cols-3">
          <div>
            <span class="text-on-surface-variant/70">audit_id:</span>
            <code class="ml-1 text-on-surface">{{ result.audit_id }}</code>
          </div>
          <div>
            <span class="text-on-surface-variant/70">db_type:</span>
            <code class="ml-1 text-on-surface">{{ result.db_type_code }}</code>
          </div>
          <div v-if="result.sql_dialect">
            <span class="text-on-surface-variant/70">sql_dialect:</span>
            <code class="ml-1 text-on-surface">{{ result.sql_dialect }}</code>
          </div>
          <div v-if="result.schema_snapshot_id">
            <span class="text-on-surface-variant/70">snapshot_id:</span>
            <code class="ml-1 text-on-surface">{{ result.schema_snapshot_id }}</code>
          </div>
          <div v-if="result.schema_policy_hash" class="truncate">
            <span class="text-on-surface-variant/70">policy_hash:</span>
            <code class="ml-1 text-on-surface">{{ result.schema_policy_hash.slice(0, 16) }}…</code>
          </div>
          <div v-if="result.dify_workflow_run_id">
            <span class="text-on-surface-variant/70">dify_run:</span>
            <code class="ml-1 text-on-surface">{{ result.dify_workflow_run_id }}</code>
          </div>
        </div>

        <!-- errors（红条） -->
        <div
          v-if="result.errors && result.errors.length"
          class="mt-4 rounded border border-red-500/30 bg-red-500/10 p-3 text-sm"
        >
          <div class="flex items-center gap-1.5 text-red-200">
            <span class="material-symbols-outlined text-[16px]">error</span>
            <span class="font-medium">拒绝原因（{{ result.errors.length }} 条）</span>
          </div>
          <ul class="mt-2 list-disc space-y-1 pl-6 text-xs text-red-200/90">
            <li v-for="(e, i) in result.errors" :key="i">
              <code>{{ e }}</code>
            </li>
          </ul>
          <p
            v-if="result.preview_safety_reason"
            class="mt-2 text-xs text-red-300/70"
          >
            {{ result.preview_safety_reason }}
          </p>
        </div>

        <!-- warnings（黄条） -->
        <div
          v-if="result.warnings && result.warnings.length"
          class="mt-3 rounded border border-amber-500/30 bg-amber-500/10 p-3 text-sm"
        >
          <div class="flex items-center gap-1.5 text-amber-200">
            <span class="material-symbols-outlined text-[16px]">warning</span>
            <span class="font-medium">提示（{{ result.warnings.length }} 条）</span>
          </div>
          <ul class="mt-2 list-disc space-y-1 pl-6 text-xs text-amber-200/90">
            <li v-for="(w, i) in result.warnings" :key="i">
              {{ w }}
            </li>
          </ul>
        </div>

        <!-- approved_sql（passed 时显示） -->
        <div v-if="result.preview_safety_status === 'passed' && result.approved_sql" class="mt-4">
          <div class="mb-1 flex items-center justify-between text-xs text-on-surface-variant">
            <span>approved_sql（Execute 阶段权威）</span>
            <button
              type="button"
              class="ops-secondary-button inline-flex items-center gap-1 px-2 py-0.5 text-[11px]"
              @click="onCopySql"
            >
              <span class="material-symbols-outlined text-[12px]">content_copy</span>
              {{ copied ? '已复制' : '复制' }}
            </button>
          </div>
          <pre class="overflow-x-auto rounded bg-surface-variant/40 p-3 text-xs leading-relaxed text-on-surface"><code>{{ result.approved_sql }}</code></pre>
          <div
            v-if="result.generated_sql && result.generated_sql !== result.approved_sql"
            class="mt-3"
          >
            <div class="mb-1 text-xs text-on-surface-variant">
              generated_sql（Dify 原始，审计追溯）
            </div>
            <pre class="overflow-x-auto rounded bg-surface-variant/20 p-3 text-xs leading-relaxed text-on-surface/80"><code>{{ result.generated_sql }}</code></pre>
          </div>
        </div>

        <!-- generated_sql（仅 rejected 时显示） -->
        <div v-else-if="result.generated_sql" class="mt-4">
          <div class="mb-1 text-xs text-on-surface-variant">
            generated_sql（Dify 原始 — 未通过 AST 校验）
          </div>
          <pre class="overflow-x-auto rounded bg-surface-variant/20 p-3 text-xs leading-relaxed text-on-surface/80"><code>{{ result.generated_sql }}</code></pre>
        </div>

        <!-- 接受按钮：passed 时显示 -->
        <div
          v-if="result.preview_safety_status === 'passed' && result.approved_sql"
          class="mt-4 flex flex-wrap items-center gap-2 border-t border-surface-variant/30 pt-4"
        >
          <button
            type="button"
            class="ops-primary-button inline-flex items-center gap-1.5 px-4 py-2 text-sm"
            :disabled="accepting || !canAccept"
            @click="onAccept"
          >
            <span
              v-if="accepting"
              class="material-symbols-outlined animate-spin text-[16px]"
            >sync</span>
            <span v-else class="material-symbols-outlined text-[16px]">task_alt</span>
            {{ accepting ? '写回中…' : '接受并写回会话' }}
          </button>
          <!-- C14 NEW — 执行 SQL 按钮（capabilities.sql_execution_enabled 才显示） -->
          <button
            v-if="capabilities.sql_execution_enabled"
            type="button"
            class="ops-secondary-button inline-flex items-center gap-1.5 px-4 py-2 text-sm"
            :disabled="!canExecute || executing"
            @click="onExecuteSql"
          >
            <span
              v-if="executing"
              class="material-symbols-outlined animate-spin text-[16px]"
            >sync</span>
            <span v-else class="material-symbols-outlined text-[16px]">play_arrow</span>
            {{ executing ? '执行中…' : '执行 SQL' }}
          </button>
          <span v-if="!capabilities.sql_execution_enabled" class="text-xs text-on-surface-variant">
            （AI_SQL_EXECUTION_ENABLED=false，按钮禁用）
          </span>
          <span v-else class="text-xs text-on-surface-variant">
            （写入 Chat 会话并把 approved_sql 作为 assistant 消息存入 / 执行 SQL 通过 AWX 异步调度）
          </span>
        </div>

        <!-- 接受结果反馈 -->
        <div
          v-if="acceptResult"
          class="mt-3 rounded border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200"
        >
          <div class="flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[16px]">check_circle</span>
            <span>{{ acceptResult }}</span>
          </div>
        </div>
        <div
          v-if="acceptError"
          class="mt-3 rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"
        >
          <div class="flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[16px]">error</span>
            <span>{{ acceptError }}</span>
          </div>
        </div>

        <!-- C14 NEW — SQL 执行状态面板 -->
        <div
          v-if="execution || executionError"
          class="mt-4 rounded border border-surface-variant/30 bg-surface-variant/10 p-3 text-sm"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-on-surface-variant">SQL 执行状态</span>
              <span v-if="execution" :class="executionBadgeClass">
                <span class="material-symbols-outlined text-[14px]">{{ executionBadgeIcon }}</span>
                {{ execution.execution_status.toUpperCase() }}
              </span>
            </div>
            <button
              v-if="polling"
              type="button"
              class="ops-secondary-button inline-flex items-center gap-1 px-2 py-0.5 text-[11px]"
              @click="stopPolling"
            >
              <span class="material-symbols-outlined text-[12px]">close</span>
              停止轮询
            </button>
          </div>

          <div v-if="execution" class="mt-2 grid gap-2 text-xs text-on-surface-variant md:grid-cols-2 lg:grid-cols-3">
            <div v-if="execution.row_count != null">
              <span class="text-on-surface-variant/70">rows:</span>
              <code class="ml-1 text-on-surface">{{ execution.row_count }}</code>
            </div>
            <div v-if="execution.duration_ms != null">
              <span class="text-on-surface-variant/70">duration:</span>
              <code class="ml-1 text-on-surface">{{ execution.duration_ms }} ms</code>
            </div>
            <div v-if="execution.completed_at">
              <span class="text-on-surface-variant/70">completed_at:</span>
              <code class="ml-1 text-on-surface">{{ execution.completed_at }}</code>
            </div>
            <div v-if="execution.collector_run_id">
              <span class="text-on-surface-variant/70">collector_run_id:</span>
              <code class="ml-1 text-on-surface">#{{ execution.collector_run_id }}</code>
            </div>
            <div v-if="execution.executed_at">
              <span class="text-on-surface-variant/70">executed_at:</span>
              <code class="ml-1 text-on-surface">{{ execution.executed_at }}</code>
            </div>
            <div v-if="execution.result_message_id">
              <span class="text-on-surface-variant/70">chat_msg:</span>
              <code class="ml-1 text-on-surface">#{{ execution.result_message_id }}</code>
            </div>
          </div>

          <p
            v-if="execution?.error_message"
            class="mt-2 text-xs text-red-300/90"
          >
            {{ execution.error_message }}
          </p>

          <div
            v-if="executionError"
            class="mt-2 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-200"
          >
            <div class="flex items-center gap-1.5">
              <span class="material-symbols-outlined text-[14px]">error</span>
              <span>{{ executionError }}</span>
            </div>
          </div>
        </div>
      </OpsSectionCard>
    </div>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { assetsApi } from '@/api/assets'
import { aiApi, loadAiCapabilities } from '@/api/ai'
import type { InstanceRow } from '@/types/api'
import type {
  AiCapabilities,
  AiChatSessionCreateRequest,
  AiSqlExecutionStatusResponse,
  AiSqlExecuteRequest,
  AiSqlPreviewRequest,
  AiSqlPreviewResponse,
} from '@/types/ai'
import { safeUuid } from '@/utils/uuid'

// =============================================================================
// 表单状态
// =============================================================================
const form = reactive<{
  instanceId: number | null
  databaseName: string
  userQuestion: string
}>({
  instanceId: null,
  databaseName: '',
  userQuestion: '',
})

const generating = ref(false)
const accepting = ref(false)
const formError = ref<{ title: string; detail?: string; hint?: string } | null>(null)

const result = ref<AiSqlPreviewResponse | null>(null)
const copied = ref(false)
const acceptResult = ref('')
const acceptError = ref('')

// =============================================================================
// 实例列表 + capabilities
// =============================================================================
const loadingInstances = ref(false)
const instancesError = ref('')
const instanceOptions = ref<InstanceRow[]>([])
const capabilities = ref<AiCapabilities>({
  chat_enabled: false,
  sql_preview_enabled: false,
  sql_execution_enabled: false,
  report_analysis_enabled: false,
  report_export_ai_enabled: false,
  stream_enabled: false,
  sql_supported_db_types: [],
})

const selectedInstance = computed<InstanceRow | null>(() => {
  if (form.instanceId == null) return null
  return instanceOptions.value.find((i) => i.id === form.instanceId) || null
})

function supportedByPreview(dbTypeCode: string | null | undefined): boolean {
  if (!dbTypeCode) return false
  const allowed = capabilities.value.sql_supported_db_types.map((s) => s.toUpperCase())
  return allowed.includes(dbTypeCode.toUpperCase())
}

// 简易 Layer 1 预检提示（前端兜底 — 真正拦截在后端）
const layer1Hint = computed(() => {
  const q = form.userQuestion
  if (!q) return ''
  const en = /\b(DROP|DELETE|UPDATE|INSERT|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|MERGE)\b/i
  if (en.test(q)) return '问题包含非只读关键词，可能被后端 Layer 1 拒绝'
  const cnKw = ['删除', '删掉', '写入', '插入', '截断', '建表', '建库', '建索引', '授权']
  for (const k of cnKw) {
    if (q.includes(k)) return `问题包含非只读关键词「${k}」，可能被后端 Layer 1 拒绝`
  }
  return ''
})

// =============================================================================
// 校验
// =============================================================================
const canSubmit = computed(
  () =>
    !generating.value &&
    form.instanceId != null &&
    form.userQuestion.trim().length > 0,
)

const canAccept = computed(
  () =>
    !!result.value &&
    result.value.preview_safety_status === 'passed' &&
    !!result.value.approved_sql,
)

// =============================================================================
// 生命周期
// =============================================================================
onMounted(async () => {
  await loadCapabilities()
  await loadInstances()
})

async function loadCapabilities() {
  try {
    capabilities.value = await loadAiCapabilities(true)
  } catch {
    // loadAiCapabilities 内部已兜底全 false — 这里忽略
  }
}

async function loadInstances() {
  loadingInstances.value = true
  instancesError.value = ''
  try {
    const resp = await assetsApi.listInstances({ page_size: 200, page: 1 })
    instanceOptions.value = resp.items || []
    if (!instanceOptions.value.length) {
      instancesError.value = '当前无可用数据库实例'
    }
  } catch (err: any) {
    instancesError.value = err?.message || '实例列表加载失败'
  } finally {
    loadingInstances.value = false
  }
}

function onInstanceChange() {
  // 重置结果（避免跨实例残留的 approved_sql）
  result.value = null
  formError.value = null
  acceptResult.value = ''
  acceptError.value = ''
}

// =============================================================================
// 操作
// =============================================================================
function onReset() {
  result.value = null
  formError.value = null
  acceptResult.value = ''
  acceptError.value = ''
  form.userQuestion = ''
  form.databaseName = ''
  copied.value = false
}

async function onGenerate() {
  if (!canSubmit.value) return
  generating.value = true
  formError.value = null
  result.value = null
  acceptResult.value = ''
  acceptError.value = ''
  copied.value = false

  const payload: AiSqlPreviewRequest = {
    instance_id: form.instanceId!,
    database_name: form.databaseName.trim() || null,
    user_question: form.userQuestion.trim(),
    current_page: 'instance_detail',
  }

  try {
    const r = await aiApi.sqlPreview(payload)
    result.value = r
    if (r.preview_safety_status === 'rejected' && r.errors?.length) {
      // 200 但 rejected — 给个轻提示（非阻塞错误）
      formError.value = {
        title: 'SQL Preview 被安全层拒绝',
        detail: r.errors.join('；'),
        hint: '调整问题描述或检查 Schema Policy。rejected 也已落 ai_sql_audit。',
      }
    }
  } catch (err: any) {
    // HTTP 4xx/5xx — request.js 通常会把错误转为 reject
    const status = err?.response?.status
    const detail = err?.response?.data?.detail || err?.message || '未知错误'
    let hint = ''
    if (status === 409) hint = '请先到「资产 → 数据库实例」触发 schema 采集并等待 success'
    else if (status === 503) hint = '检查 backend/.env 的 AI_SQL_PREVIEW_ENABLED 是否为 true'
    else if (status === 502 || status === 504) hint = '检查 Dify 服务可达性与 API Key'
    formError.value = {
      title: `请求失败（HTTP ${status || '网络错误'}）`,
      detail: typeof detail === 'string' ? detail : JSON.stringify(detail),
      hint,
    }
  } finally {
    generating.value = false
  }
}

async function onCopySql() {
  if (!result.value?.approved_sql) return
  try {
    await navigator.clipboard.writeText(result.value.approved_sql)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    copied.value = false
  }
}

// =============================================================================
// 接受并写回会话（C13 — plan §8 Chat 集成入口）
// =============================================================================
// 流程：
//   1) POST /chat/sessions （创建新会话）
//   2) POST /chat/sessions/{id}/messages （client_request_id=UUID, query=
//      "AI Copilot 已生成 SQL（audit_id={N}）", message_type='sql_preview'
//      通过 metadata_json 携带 audit_id / approved_sql_hash）
//
// 简化策略（首版）：
//   - 用一个"AI Copilot 已生成 SQL"的简短 query + 把 approved_sql 摘要
//     作为 query 内容；assistant 消息由 Dify 返回（首版简化）
async function onAccept() {
  if (!canAccept.value || !result.value) return
  accepting.value = true
  acceptResult.value = ''
  acceptError.value = ''
  try {
    // 1) 创建会话
    const sessionPayload: AiChatSessionCreateRequest = {
      title: `SQL Preview · ${result.value.db_type_code} · audit ${result.value.audit_id}`,
    }
    const session = await aiApi.createSession(sessionPayload)
    // 2) 发送消息：query 用 audit 引用 + approved_sql 摘要
    const approvedSql = result.value.approved_sql || ''
    const truncated = approvedSql.length > 200 ? approvedSql.slice(0, 200) + '…' : approvedSql
    const query = `AI Copilot 已生成 SQL（audit_id=${result.value.audit_id}）\n\n${truncated}\n\n（详情见 metadata_json.preview_audit_id）`
    await aiApi.sendMessage(session.id, {
      client_request_id: safeUuid(),
      query,
      current_page: 'ai_chat',
    })
    acceptResult.value = `已写回会话 #${session.id}（${session.session_code || session.id}）`
  } catch (err: any) {
    const detail = err?.response?.data?.detail || err?.message || '未知错误'
    acceptError.value = `写回失败：${typeof detail === 'string' ? detail : JSON.stringify(detail)}`
  } finally {
    accepting.value = false
  }
}

// =============================================================================
// SQL Execute（C14 NEW — plan §6.1 + §8 Chat 集成入口）
// =============================================================================
const executing = ref(false)
const execution = ref<AiSqlExecutionStatusResponse | null>(null)
const executionError = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null
const polling = ref(false)

// 是否启用执行按钮：passed + capabilities + 不在终态
const canExecute = computed(
  () =>
    !!result.value &&
    result.value.preview_safety_status === 'passed' &&
    !!result.value.approved_sql &&
    capabilities.value.sql_execution_enabled,
)

const EXEC_TERMINAL_STATUSES = new Set(['success', 'failed', 'timeout', 'cancelled'])

const executionBadgeClass = computed(() => {
  const s = execution.value?.execution_status
  if (s === 'success') return 'inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300'
  if (s === 'failed') return 'inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-xs text-red-300'
  if (s === 'timeout') return 'inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300'
  if (s === 'cancelled') return 'inline-flex items-center gap-1 rounded-full bg-zinc-500/15 px-2 py-0.5 text-xs text-zinc-300'
  // running / pending / not_requested
  return 'inline-flex items-center gap-1 rounded-full bg-sky-500/15 px-2 py-0.5 text-xs text-sky-300'
})

const executionBadgeIcon = computed(() => {
  const s = execution.value?.execution_status
  if (s === 'success') return 'check_circle'
  if (s === 'failed') return 'cancel'
  if (s === 'timeout') return 'timer_off'
  if (s === 'cancelled') return 'block'
  return 'autorenew'  // running / pending
})

async function onExecuteSql() {
  if (!canExecute.value || !result.value) return
  executing.value = true
  executionError.value = ''
  execution.value = null
  try {
    const payload: AiSqlExecuteRequest = {
      audit_id: result.value.audit_id,
      force: false,
    }
    const r = await aiApi.executeSql(payload)
    execution.value = {
      audit_id: r.audit_id,
      execution_status: r.execution_status,
      executed_at: r.executed_at,
      collector_run_id: r.collector_run_id,
      // 其他字段（row_count / duration_ms / completed_at / result_message_id）由轮询补齐
      row_count: null,
      duration_ms: null,
      completed_at: null,
      error_message: r.error_message,
      awx_job_id: r.awx_job_id,
      result_message_id: null,
      message_type: null,
      created_at: new Date().toISOString(),
    }
    if (!EXEC_TERMINAL_STATUSES.has(r.execution_status)) {
      startPolling(r.audit_id)
    }
  } catch (err: any) {
    const status = err?.response?.status
    const detail = err?.response?.data?.detail || err?.message || '未知错误'
    let hint = ''
    if (status === 409) hint = '请检查 audit 状态（pending/running 需 force=true）/ schema policy'
    else if (status === 422) hint = 'Execute 时 AST 二次校验失败；请重新 Preview'
    else if (status === 503) hint = '检查 backend/.env 的 AI_SQL_EXECUTION_ENABLED'
    else if (status === 502) hint = 'AWX 调度失败；检查 AWX 凭证与 Job Template'
    executionError.value = `执行请求失败（HTTP ${status || '网络错误'}）：${
      typeof detail === 'string' ? detail : JSON.stringify(detail)
    }${hint ? ' — ' + hint : ''}`
  } finally {
    executing.value = false
  }
}

function startPolling(auditId: number) {
  stopPolling()
  polling.value = true
  pollTimer = setInterval(async () => {
    try {
      const r = await aiApi.getExecutionStatus(auditId)
      execution.value = r
      if (EXEC_TERMINAL_STATUSES.has(r.execution_status)) {
        stopPolling()
      }
    } catch (err: any) {
      // 单次轮询失败 → log + continue（不打断流程）
      console.warn('execute status poll failed:', err)
    }
  }, 3000)
}

function stopPolling() {
  polling.value = false
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onBeforeUnmount(() => {
  stopPolling()
})
</script>