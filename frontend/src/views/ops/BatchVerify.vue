<template>
  <OpsPage>
    <OpsPageHeader
      title="批量校验"
      subtitle="选择资产范围和检查项，统一调度 AWX 批量执行"
      icon="checklist"
    />

    <!-- Create Section -->
    <OpsSectionCard title="新建批量任务" class="mb-6">
      <div class="space-y-4">
        <!-- Target scope & Asset selection mode in one row -->
        <div class="grid gap-3 sm:grid-cols-2">
          <div class="field-card">
            <div class="field-label">目标范围</div>
            <div class="field-value flex gap-6">
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="form.target_scope" type="radio" value="db_instance" class="h-4 w-4" />
                <span class="text-sm">数据库实例</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="form.target_scope" type="radio" value="server" class="h-4 w-4" />
                <span class="text-sm">服务器</span>
              </label>
            </div>
          </div>

          <div class="field-card">
            <div class="field-label">资产选择</div>
            <div class="field-value flex gap-6">
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="selectionMode" type="radio" value="ids" class="h-4 w-4" />
                <span class="text-sm">按资产 ID</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="selectionMode" type="radio" value="filters" class="h-4 w-4" />
                <span class="text-sm">按条件筛选</span>
              </label>
            </div>
          </div>
        </div>

        <!-- ID input -->
        <label v-if="selectionMode === 'ids'" class="block field-card">
          <span class="field-label">资产 ID</span>
          <input
            v-model="assetIdsInput"
            class="field-input"
            placeholder="输入资产 ID，逗号分隔（如 1,2,3）"
          />
        </label>

        <!-- Filters -->
        <div v-if="selectionMode === 'filters'" class="grid gap-3 sm:grid-cols-3">
          <label class="block field-card">
            <span class="field-label">数据库类型</span>
            <select v-model="form.filters.db_type_code" class="field-input">
              <option value="">全部类型</option>
              <option v-for="dt in dbTypes" :key="dt.type_code" :value="dt.type_code">{{ dt.name }} ({{ dt.type_code }})</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">状态</span>
            <select v-model="form.filters.status" class="field-input">
              <option value="">全部</option>
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">站点 ID</span>
            <input v-model.number="form.filters.site_id" type="number" class="field-input" placeholder="站点 ID" />
          </label>
        </div>

        <!-- Check codes -->
        <div class="field-card">
          <div class="field-label">检查项</div>
          <div class="field-value flex flex-wrap gap-3">
            <label
              v-for="check in checkCodeOptions"
              :key="check.value"
              class="flex items-center gap-2 rounded-xl border border-outline-variant/40 bg-surface-container-high px-4 py-3 cursor-pointer hover:bg-surface-container-highest transition-colors"
            >
              <input v-model="form.check_codes" type="checkbox" :value="check.value" class="h-4 w-4" />
              <span class="text-sm">{{ check.label }}</span>
            </label>
          </div>
        </div>

        <!-- Options -->
        <div class="grid gap-3 sm:grid-cols-3">
          <label class="block field-card">
            <span class="field-label">超时（秒）</span>
            <input v-model.number="form.timeout_seconds" type="number" min="1" max="60" class="field-input" />
          </label>
          <label class="block field-card">
            <span class="field-label">每 dispatch 最大 item 数</span>
            <input v-model.number="form.max_items_per_dispatch" type="number" min="1" max="500" class="field-input" />
          </label>
          <div class="field-card flex items-center">
            <label class="flex items-center gap-2 cursor-pointer">
              <input v-model="form.include_related_server" type="checkbox" class="h-4 w-4" />
              <span class="text-sm">包含关联服务器</span>
            </label>
          </div>
        </div>

        <!-- Launch button -->
        <button
          class="ops-primary-button"
          :disabled="launchLoading || form.check_codes.length === 0"
          @click="createBatch"
        >
          <span class="material-symbols-outlined text-[18px]">{{ launchLoading ? 'hourglass_empty' : 'rocket_launch' }}</span>
          {{ launchLoading ? '提交中...' : '启动批量校验' }}
        </button>

        <!-- Messages -->
        <div v-if="launchMessage" class="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{{ launchMessage }}</div>
        <div v-if="launchError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{{ launchError }}</div>
      </div>
    </OpsSectionCard>

    <!-- Batch Runs List -->
    <OpsSectionCard title="批量任务列表">
      <OpsTableShell v-if="batches.length > 0">
        <table class="w-full text-sm">
          <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
            <tr>
              <th class="whitespace-nowrap px-4 py-3">批次编号</th>
              <th class="whitespace-nowrap px-4 py-3">类型</th>
              <th class="whitespace-nowrap px-4 py-3">范围</th>
              <th class="whitespace-nowrap px-4 py-3">状态</th>
              <th class="whitespace-nowrap px-4 py-3">资产数</th>
              <th class="whitespace-nowrap px-4 py-3">总 item</th>
              <th class="whitespace-nowrap px-4 py-3">成功</th>
              <th class="whitespace-nowrap px-4 py-3">失败</th>
              <th class="whitespace-nowrap px-4 py-3">分发数</th>
              <th class="whitespace-nowrap px-4 py-3">创建时间</th>
              <th class="whitespace-nowrap px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="batch in batches"
              :key="batch.id"
              class="cursor-pointer border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
              @click="selectedBatchId = batch.id; loadBatchDetail(batch.id)"
            >
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ batch.batch_code }}</td>
              <td class="whitespace-nowrap px-4 py-3">{{ batch.run_type }}</td>
              <td class="whitespace-nowrap px-4 py-3">{{ batch.target_scope }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                <span
                  class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                  :class="getStatusBadgeClass(batch.status)"
                >{{ formatStatusLabel(batch.status) }}</span>
              </td>
              <td class="whitespace-nowrap px-4 py-3">{{ batch.total_asset_count }}</td>
              <td class="whitespace-nowrap px-4 py-3">{{ batch.total_item_count }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-emerald-400">{{ batch.success_item_count }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-red-400">{{ batch.failed_item_count }}</td>
              <td class="whitespace-nowrap px-4 py-3">{{ batch.dispatch_count }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">{{ formatTime(batch.created_at) }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                <button
                  class="text-xs text-primary transition-colors hover:text-primary/80"
                  @click.stop="selectedBatchId = batch.id; loadBatchDetail(batch.id)"
                >详情</button>
              </td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
      <OpsEmptyState v-else state="empty" title="暂无批量任务" description="请在上方创建" />
    </OpsSectionCard>

    <!-- Batch Detail -->
    <div v-if="batchDetail" class="mt-6 space-y-6">
      <!-- Results Summary -->
      <OpsSectionCard title="结果摘要" icon="analytics">
        <div class="grid gap-3 sm:grid-cols-5">
          <div class="field-card text-center">
            <div class="field-value text-2xl font-bold">{{ batchDetail.total_asset_count }}</div>
            <div class="field-label">总资产数</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-2xl font-bold">{{ batchDetail.total_item_count }}</div>
            <div class="field-label">总检查项</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-2xl font-bold text-emerald-400">{{ batchDetail.success_item_count }}</div>
            <div class="field-label">成功</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-2xl font-bold text-red-400">{{ batchDetail.failed_item_count }}</div>
            <div class="field-label">失败</div>
          </div>
          <div class="field-card text-center">
            <div class="field-value text-2xl font-bold" :class="successRateClass">{{ successRate }}%</div>
            <div class="field-label">成功率</div>
          </div>
        </div>
      </OpsSectionCard>

      <!-- Dispatches -->
      <OpsSectionCard title="分发明细" icon="send">
        <OpsTableShell v-if="(batchDetail.dispatches || []).length > 0">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="whitespace-nowrap px-4 py-3">分发编号</th>
                <th class="whitespace-nowrap px-4 py-3">网段</th>
                <th class="whitespace-nowrap px-4 py-3">实例组</th>
                <th class="whitespace-nowrap px-4 py-3">状态</th>
                <th class="whitespace-nowrap px-4 py-3">Items</th>
                <th class="whitespace-nowrap px-4 py-3">成功</th>
                <th class="whitespace-nowrap px-4 py-3">失败</th>
                <th class="whitespace-nowrap px-4 py-3">AWX Job</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in batchDetail.dispatches || []" :key="d.dispatch_run_id" class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high">
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ d.dispatch_code || '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ d.network_zone || '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ d.awx_instance_group || '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="getStatusBadgeClass(d.status)"
                  >{{ formatStatusLabel(d.status) }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">{{ d.item_count }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-emerald-400">{{ d.success_item_count }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-red-400">{{ d.failed_item_count }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ d.awx_job_id || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </OpsTableShell>
        <OpsEmptyState v-else state="empty" title="暂无分发明细" />
      </OpsSectionCard>

      <!-- Items -->
      <OpsSectionCard title="执行项明细" icon="fact_check">
        <div class="mb-4 flex flex-wrap items-center gap-3">
          <select
            v-model="itemFilters.status"
            class="rounded-lg border border-outline-variant/50 bg-surface-container px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
            @change="loadItems"
          >
            <option value="">全部状态</option>
            <option value="success">success</option>
            <option value="failed">failed</option>
            <option value="pending">pending</option>
            <option value="running">running</option>
          </select>
          <select
            v-model="itemFilters.check_code"
            class="rounded-lg border border-outline-variant/50 bg-surface-container px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
            @change="loadItems"
          >
            <option value="">全部检查项</option>
            <option v-for="c in checkCodeOptions" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
          <button
            class="text-xs text-primary transition-colors hover:text-primary/80"
            :disabled="retryLoading"
            @click="retryFailed"
          >{{ retryLoading ? '重跑中...' : '重跑失败项' }}</button>
        </div>

        <OpsTableShell v-if="items.length > 0">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="whitespace-nowrap px-4 py-3">Item Key</th>
                <th class="whitespace-nowrap px-4 py-3">检查项</th>
                <th class="whitespace-nowrap px-4 py-3">目标</th>
                <th class="whitespace-nowrap px-4 py-3">端口</th>
                <th class="whitespace-nowrap px-4 py-3">状态</th>
                <th class="whitespace-nowrap px-4 py-3">结果</th>
                <th class="whitespace-nowrap px-4 py-3">消息</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.id" class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high">
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs max-w-[200px] truncate" :title="item.item_key">{{ item.item_key }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ item.check_code }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ item.target_host }}:{{ item.target_port }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ item.target_port }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="getItemStatusBadgeClass(item.status)"
                  >{{ item.status }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">{{ item.result_status || item.candidate_state || '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3 max-w-[200px] truncate text-xs" :title="item.result_message || ''">{{ item.result_message || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </OpsTableShell>
        <OpsEmptyState v-else state="empty" title="暂无执行项" description="选择状态或检查项筛选" />
      </OpsSectionCard>

      <!-- Change Proposals -->
      <OpsSectionCard title="变更建议" icon="rule">
        <OpsEmptyState v-if="proposalsLoading" state="loading" title="正在加载变更建议" description="请稍候。" />
        <OpsEmptyState v-else-if="proposalsError" state="error" title="变更建议加载失败" :description="proposalsError" />
        <OpsEmptyState v-else-if="!batchProposals.length" state="empty" title="暂无待处理建议" description="端口校准后若识别到可疑漂移或端口补齐场景，会在此生成建议。" />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="whitespace-nowrap px-4 py-3">对象</th>
                <th class="whitespace-nowrap px-4 py-3">建议类型</th>
                <th class="whitespace-nowrap px-4 py-3">当前值</th>
                <th class="whitespace-nowrap px-4 py-3">建议值</th>
                <th class="whitespace-nowrap px-4 py-3">置信度</th>
                <th class="whitespace-nowrap px-4 py-3">状态</th>
                <th class="whitespace-nowrap px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="proposal in batchProposals"
                :key="proposal.id"
                class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
              >
                <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">{{ proposal.target_type }}#{{ proposal.target_id }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ proposal.proposal_type }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ formatDisplayValue(proposal.current_value) }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ formatDisplayValue(proposal.suggested_value) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ proposal.confidence || '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getProposalStatusBadgeClass(proposal.status)">{{ formatProposalStatusLabel(proposal.status) }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">
                  <div class="flex flex-wrap gap-2">
                    <button class="ops-secondary-button" :disabled="proposal.status !== 'pending'" @click="handleApproveProposal(proposal.id)">同意</button>
                    <button class="ops-secondary-button" :disabled="proposal.status !== 'pending' && proposal.status !== 'approved'" @click="handleRejectProposal(proposal.id)">拒绝</button>
                    <button class="ops-primary-button" :disabled="proposal.status !== 'approved'" @click="handleApplyProposal(proposal.id)">应用</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </OpsSectionCard>
    </div>
  </OpsPage>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import OpsEmptyState from '@/components/ops/OpsEmptyState.vue'
import { assetsApi } from '@/api/assets'
import type { AssetChangeProposalRow, BatchRunRow, BatchRunItemRow, DbTypeRow } from '@/types/api'
import { formatInTz } from '@/utils/timezone'

const selectionMode = ref<'ids' | 'filters'>('ids')
const assetIdsInput = ref('')
const launchLoading = ref(false)
const launchMessage = ref('')
const launchError = ref('')
const batches = ref<BatchRunRow[]>([])
const selectedBatchId = ref<number | null>(null)
const batchDetail = ref<BatchRunRow | null>(null)
const items = ref<BatchRunItemRow[]>([])
const retryLoading = ref(false)
const itemFilters = reactive({ status: '', check_code: '' })
const dbTypes = ref<DbTypeRow[]>([])
const batchProposals = ref<AssetChangeProposalRow[]>([])
const proposalsLoading = ref(false)
const proposalsError = ref('')

const checkCodeOptions = [
  { value: 'DB_PORT_REACHABILITY', label: 'DB 端口连通性' },
  { value: 'SSH_PORT_REACHABILITY', label: 'SSH 端口连通性' },
  { value: 'PORT_CANDIDATE_REACHABILITY', label: '候选端口探测' },
]

const form = reactive({
  target_scope: 'db_instance' as 'db_instance' | 'server',
  check_codes: [] as string[],
  timeout_seconds: 3,
  max_items_per_dispatch: 100,
  include_related_server: true,
  filters: {
    db_type_code: '',
    status: '' as string,
    site_id: null as number | null,
  },
})

const successRate = computed(() => {
  if (!batchDetail.value || !batchDetail.value.total_item_count) return 0
  const s = batchDetail.value.success_item_count || 0
  const t = batchDetail.value.total_item_count
  return Math.round((s / t) * 100)
})

const successRateClass = computed(() => {
  const r = successRate.value
  if (r >= 90) return 'text-emerald-400'
  if (r >= 50) return 'text-amber-400'
  return 'text-red-400'
})

function formatTime(val: any): string {
  return val ? formatInTz(val) : '-'
}

function formatDisplayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

// ── Status badge helpers ────────────────────────────────────────────────

function formatStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return '等待中'
  if (s === 'launched' || s === 'launching') return '启动中'
  if (s === 'running' || s === 'dispatching') return '执行中'
  if (s === 'success') return '已完成'
  if (s === 'partial_success') return '部分成功'
  if (s === 'failed') return '失败'
  if (s === 'cancelled') return '已取消'
  return status || '-'
}

function getStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'launched' || s === 'launching' || s === 'dispatching') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'running') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'success') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'partial_success') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'failed') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'cancelled') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function getItemStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'success') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'failed' || s === 'timeout') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'running') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'pending') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function formatProposalStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return '待审批'
  if (s === 'approved') return '已同意'
  if (s === 'rejected') return '已拒绝'
  if (s === 'applied') return '已应用'
  if (s === 'cancelled') return '已取消'
  return status || '-'
}

function getProposalStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'approved') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'rejected') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  if (s === 'applied') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'cancelled') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

// ── API actions ─────────────────────────────────────────────────────────

async function createBatch() {
  launchLoading.value = true
  launchMessage.value = ''
  launchError.value = ''

  try {
    const payload: any = {
      target_scope: form.target_scope,
      check_codes: form.check_codes,
      timeout_seconds: form.timeout_seconds,
      max_items_per_dispatch: form.max_items_per_dispatch,
      include_related_server: form.include_related_server,
    }

    if (selectionMode.value === 'ids') {
      const ids = assetIdsInput.value
        .split(',')
        .map((s) => parseInt(s.trim()))
        .filter((n) => !isNaN(n))
      if (ids.length === 0) {
        launchError.value = '请输入有效的资产 ID'
        return
      }
      payload.asset_ids = ids
    } else {
      const f: any = {}
      if (form.filters.db_type_code) f.db_type_code = form.filters.db_type_code
      if (form.filters.status) f.status = form.filters.status
      if (form.filters.site_id) f.site_id = form.filters.site_id
      payload.filters = f
    }

    const result = await assetsApi.createBatchRun(payload)
    launchMessage.value = `批量任务已创建：${result.batch_code}，${result.dispatch_count} 个分发`
    assetIdsInput.value = ''
    form.check_codes = []
    await loadBatches()
    selectedBatchId.value = result.batch_run_id
    await loadBatchDetail(result.batch_run_id)
  } catch (e: any) {
    launchError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    launchLoading.value = false
  }
}

async function loadBatches() {
  try {
    batches.value = await assetsApi.listBatchRuns({ limit: 20 })
  } catch {
    // silently fail
  }
}

async function loadBatchDetail(id: number) {
  try {
    batchDetail.value = await assetsApi.getBatchRun(id)
    await loadItems()
    await loadBatchProposals()
  } catch {
    batchDetail.value = null
  }
}

async function loadItems() {
  if (!selectedBatchId.value) return
  try {
    const params: any = {}
    if (itemFilters.status) params.status = itemFilters.status
    if (itemFilters.check_code) params.check_code = itemFilters.check_code
    items.value = await assetsApi.listBatchItems(selectedBatchId.value, params, { suppressErrorToast: true })
  } catch {
    items.value = []
  }
}

async function retryFailed() {
  if (!selectedBatchId.value) return
  retryLoading.value = true
  try {
    await assetsApi.retryFailedBatchItems(selectedBatchId.value, { scope: 'failed' })
    await loadBatchDetail(selectedBatchId.value)
  } catch (e: any) {
    launchError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    retryLoading.value = false
  }
}

async function loadBatchProposals() {
  proposalsLoading.value = true
  proposalsError.value = ''
  try {
    const allItems = await assetsApi.listBatchItems(selectedBatchId.value!, {}, { suppressErrorToast: true })
    if (!allItems.length) {
      batchProposals.value = []
      return
    }
    const targets = new Map<string, { target_type: string; target_id: number }>()
    for (const item of allItems) {
      if (item.db_instance_id) {
        targets.set(`db_instance:${item.db_instance_id}`, { target_type: 'db_instance', target_id: item.db_instance_id })
      }
      if (item.server_id) {
        targets.set(`server:${item.server_id}`, { target_type: 'server', target_id: item.server_id })
      }
    }
    const proposalLists = await Promise.all(
      Array.from(targets.values()).map((t) =>
        assetsApi.listCollectorProposals(
          { target_type: t.target_type, target_id: t.target_id },
          { suppressErrorToast: true }
        ).catch(() => [] as AssetChangeProposalRow[])
      )
    )
    const seen = new Set<number>()
    const merged: AssetChangeProposalRow[] = []
    for (const list of proposalLists) {
      for (const p of list) {
        if (!seen.has(p.id)) {
          seen.add(p.id)
          merged.push(p)
        }
      }
    }
    batchProposals.value = merged
  } catch (err: any) {
    batchProposals.value = []
    proposalsError.value = err?.response?.data?.detail || err?.message || '加载失败'
  } finally {
    proposalsLoading.value = false
  }
}

async function handleApproveProposal(proposalId: number) {
  try {
    await assetsApi.approveCollectorProposal(proposalId)
    await loadBatchProposals()
  } catch (e: any) {
    launchError.value = e?.response?.data?.detail || e?.message || 'approve 失败'
  }
}

async function handleRejectProposal(proposalId: number) {
  try {
    await assetsApi.rejectCollectorProposal(proposalId, {})
    await loadBatchProposals()
  } catch (e: any) {
    launchError.value = e?.response?.data?.detail || e?.message || 'reject 失败'
  }
}

async function handleApplyProposal(proposalId: number) {
  try {
    await assetsApi.applyCollectorProposal(proposalId)
    await loadBatchProposals()
  } catch (e: any) {
    launchError.value = e?.response?.data?.detail || e?.message || 'apply 失败'
  }
}

onMounted(() => {
  loadBatches()
  assetsApi.listDbTypes().then((types) => { dbTypes.value = types }).catch(() => {})
})
</script>
