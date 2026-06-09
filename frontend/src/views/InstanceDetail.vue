<template>
  <OpsPage>
    <div class="mb-4">
      <router-link
        to="/assets/instances"
        class="inline-flex items-center gap-2 text-sm text-on-surface-variant transition-colors hover:text-on-surface"
      >
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        返回列表
      </router-link>
    </div>

    <OpsEntityHeader
      :title="detail?.instance_name || '实例详情'"
      :subtitle-parts="headerSubtitleParts"
      icon="storage"
      :chips="headerChips"
    />

    <div v-if="detail" class="mb-4 flex flex-wrap items-center gap-3">
      <button class="ops-primary-button" :disabled="launchLoading" @click="openLaunchModal">
        <span class="material-symbols-outlined text-[18px]">play_arrow</span>
        {{ launchLoading ? '提交中...' : '校验资产' }}
      </button>
      <button class="ops-secondary-button" :disabled="calibrationLoading" @click="launchPortCalibration">
        <span class="material-symbols-outlined text-[18px]">tune</span>
        {{ calibrationLoading ? '提交中...' : '端口校准' }}
      </button>
    </div>
    <div v-if="actionMessage" class="mb-4 flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
      <span class="material-symbols-outlined text-[16px]">check_circle</span>
      {{ actionMessage }}
    </div>
    <div v-if="actionError" class="mb-4 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
      <span class="material-symbols-outlined text-[16px]">error</span>
      {{ actionError }}
    </div>

    <OpsModal
      :open="showLaunchModal"
      title="选择校验项"
      subtitle="一个 collector run 会把所选检查项一次性提交给通用 AWX Job Template。"
      icon="play_arrow"
      size="md"
      @close="closeLaunchModal"
    >
      <div class="space-y-3">
        <div v-if="launchModalError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ launchModalError }}
        </div>

        <label
          v-for="check in launchCheckOptions"
          :key="check.value"
          class="flex items-start gap-3 rounded-xl border border-outline-variant/40 bg-surface-container-high px-4 py-3"
        >
          <input
            v-model="selectedCheckCodes"
            class="mt-1 h-4 w-4"
            type="checkbox"
            :value="check.value"
            :disabled="check.disabled"
          />
          <div class="min-w-0">
            <div class="text-sm font-medium text-on-surface">{{ check.label }}</div>
            <div class="mt-1 text-xs text-on-surface-variant">{{ check.description }}</div>
          </div>
        </label>
      </div>

      <template #footer>
        <div class="flex items-center justify-end gap-3">
          <button type="button" class="ops-secondary-button" :disabled="launchLoading" @click="closeLaunchModal">
            取消
          </button>
          <button type="button" class="ops-primary-button" :disabled="launchLoading" @click="submitLaunch">
            <span class="material-symbols-outlined text-[18px]">{{ launchLoading ? 'hourglass_empty' : 'play_arrow' }}</span>
            {{ launchLoading ? '提交中...' : '开始校验' }}
          </button>
        </div>
      </template>
    </OpsModal>

    <OpsSectionCard v-if="loading" title="实例详情" subtitle="正在加载实例信息">
      <OpsEmptyState state="loading" title="正在加载实例详情" description="请稍候。" />
    </OpsSectionCard>

    <OpsSectionCard v-else-if="error" title="实例详情" subtitle="加载失败">
      <OpsEmptyState state="error" title="实例详情加载失败" :description="error" />
    </OpsSectionCard>

    <section v-else-if="detail" class="space-y-4">
      <OpsSectionCard title="基础信息" icon="info">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in baseFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="角色信息" icon="badge">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in roleFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="主机信息" icon="dns">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in hostFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="集群信息" icon="hub">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in clusterFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="资产校验状态" icon="verified_user">
        <template #actions>
          <button class="ops-secondary-button text-xs" :disabled="detailRefreshing" @click="refreshDetail">
            <span class="material-symbols-outlined text-[14px]" :class="detailRefreshing ? 'animate-spin' : ''">refresh</span>
            {{ detailRefreshing ? '刷新中...' : '刷新' }}
          </button>
        </template>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <div class="field-card">
            <div class="field-label">可信状态</div>
            <div class="field-value">
              <span
                class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                :class="getTrustStatusBadgeClass(detail.trust_status)"
              >{{ formatTrustStatusLabel(detail.trust_status) }}</span>
            </div>
          </div>
          <div class="field-card">
            <div class="field-label">连通状态</div>
            <div class="field-value">
              <span
                class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                :class="getReachabilityStatusBadgeClass(detail.reachability_status)"
              >{{ formatReachabilityStatusLabel(detail.reachability_status) }}</span>
            </div>
          </div>
          <div class="field-card">
            <div class="field-label">最近校验时间</div>
            <div class="field-value">{{ detail.last_verify_at ? formatTime(detail.last_verify_at) : '-' }}</div>
          </div>
          <div class="field-card">
            <div class="field-label">最近校验消息</div>
            <div class="field-value">{{ detail.verify_message || '-' }}</div>
          </div>
          <div class="field-card">
            <div class="field-label">最近 AWX Job ID</div>
            <div class="field-value">{{ detail.last_awx_job_id ?? '-' }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="最近执行记录" icon="history">
        <OpsEmptyState
          v-if="runsLoading"
          state="loading"
          title="正在加载执行记录"
          description="请稍候。"
        />
        <OpsEmptyState
          v-else-if="runsError"
          state="error"
          title="执行记录加载失败"
          :description="runsError"
        />
        <OpsEmptyState
          v-else-if="!collectorRuns.length"
          state="empty"
          title="暂无执行记录"
          description="点击“校验资产”后会生成记录。"
        />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="whitespace-nowrap px-4 py-3">Run ID</th>
                <th class="whitespace-nowrap px-4 py-3">类型</th>
                <th class="whitespace-nowrap px-4 py-3">状态</th>
                <th class="whitespace-nowrap px-4 py-3">AWX Job ID</th>
                <th class="whitespace-nowrap px-4 py-3">目标主机</th>
                <th class="whitespace-nowrap px-4 py-3">目标端口</th>
                <th class="whitespace-nowrap px-4 py-3">开始时间</th>
                <th class="whitespace-nowrap px-4 py-3">结束时间</th>
                <th class="whitespace-nowrap px-4 py-3">错误信息</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="run in collectorRuns"
                :key="run.id"
                class="cursor-pointer border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
                @click="selectRun(run.run_id)"
              >
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ formatValue(run.run_id) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(run.run_type) }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="getRunStatusBadgeClass(run.status)"
                  >{{ formatRunStatusLabel(run.status) }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(run.awx_job_id) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(run.target_host) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(run.target_port) }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-xs">{{ run.started_at ? formatTime(run.started_at) : '-' }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-xs">{{ run.finished_at ? formatTime(run.finished_at) : '-' }}</td>
                <td class="max-w-[180px] truncate px-4 py-3 text-xs" :title="run.error_message || undefined">{{ formatValue(run.error_message) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="执行项明细" icon="fact_check">
        <OpsEmptyState
          v-if="selectedRunLoading"
          state="loading"
          title="正在加载执行项"
          description="请稍候。"
        />
        <OpsEmptyState
          v-else-if="selectedRunError"
          state="error"
          title="执行项加载失败"
          :description="selectedRunError"
        />
        <OpsEmptyState
          v-else-if="!selectedRunItems.length"
          state="empty"
          title="暂无执行项"
          description="选择一条执行记录后查看 item 详情。"
        />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="whitespace-nowrap px-4 py-3">检查项键</th>
                <th class="whitespace-nowrap px-4 py-3">检查码</th>
                <th class="whitespace-nowrap px-4 py-3">范围</th>
                <th class="whitespace-nowrap px-4 py-3">目标主机</th>
                <th class="whitespace-nowrap px-4 py-3">目标端口</th>
                <th class="whitespace-nowrap px-4 py-3">校验结果</th>
                <th class="whitespace-nowrap px-4 py-3">候选状态</th>
                <th class="whitespace-nowrap px-4 py-3">结果消息</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in selectedRunItems"
                :key="item.id"
                class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
              >
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ formatValue(item.item_key) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(item.check_code) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(item.target_scope) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(item.target_host) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(item.target_port) }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="item.result_status ? getResultStatusBadgeClass(item.result_status) : getRunStatusBadgeClass(item.status)"
                  >{{ item.result_status ? formatValue(item.result_status) : formatRunStatusLabel(item.status) }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(item.candidate_state) }}</td>
                <td class="max-w-[220px] truncate px-4 py-3 text-xs" :title="item.result_message || undefined">{{ formatValue(item.result_message) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="端点状态" icon="dns">
        <OpsEmptyState
          v-if="endpointsLoading"
          state="loading"
          title="正在加载端点状态"
          description="请稍候。"
        />
        <OpsEmptyState
          v-else-if="endpointsError"
          state="error"
          title="端点状态加载失败"
          :description="endpointsError"
        />
        <OpsEmptyState
          v-else-if="!collectorEndpoints.length"
          state="empty"
          title="暂无端点记录"
          description="校验后会在这里展示 server/db_instance 端点状态。"
        />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
                <th class="whitespace-nowrap px-4 py-3">实体类型</th>
                <th class="whitespace-nowrap px-4 py-3">实体 ID</th>
                <th class="whitespace-nowrap px-4 py-3">端点类型</th>
                <th class="whitespace-nowrap px-4 py-3">主机</th>
                <th class="whitespace-nowrap px-4 py-3">端口</th>
                <th class="whitespace-nowrap px-4 py-3">协议</th>
                <th class="whitespace-nowrap px-4 py-3">可达</th>
                <th class="whitespace-nowrap px-4 py-3">端口来源</th>
                <th class="whitespace-nowrap px-4 py-3">必需</th>
                <th class="whitespace-nowrap px-4 py-3">状态</th>
                <th class="whitespace-nowrap px-4 py-3">最近检查时间</th>
                <th class="whitespace-nowrap px-4 py-3">消息</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="endpoint in collectorEndpoints"
                :key="endpoint.id"
                class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
              >
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(endpoint.entity_type) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(endpoint.entity_id) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(endpoint.endpoint_type) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(endpoint.host) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(endpoint.port) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(endpoint.protocol) }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="endpoint.reachable ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-red-400/30 bg-red-400/10 text-red-200'"
                  >{{ endpoint.reachable ? '可达' : (endpoint.reachable === false ? '不可达' : '-') }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(endpoint.port_source) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ endpoint.is_required ? '是' : (endpoint.is_required === false ? '否' : '-') }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="getEndpointStatusBadgeClass(endpoint.status)"
                  >{{ formatValue(endpoint.status) }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3 text-xs">{{ endpoint.last_checked_at ? formatTime(endpoint.last_checked_at) : '-' }}</td>
                <td class="max-w-[180px] truncate px-4 py-3 text-xs" :title="endpoint.last_message || undefined">{{ formatValue(endpoint.last_message) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="变更建议" icon="rule">
        <OpsEmptyState
          v-if="proposalsLoading"
          state="loading"
          title="正在加载变更建议"
          description="请稍候。"
        />
        <OpsEmptyState
          v-else-if="proposalsError"
          state="error"
          title="变更建议加载失败"
          :description="proposalsError"
        />
        <OpsEmptyState
          v-else-if="!collectorProposals.length"
          state="empty"
          title="暂无待处理建议"
          description="端口校准后若识别到可疑漂移或端口补齐场景，会在此生成建议。"
        />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
              <tr>
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
                v-for="proposal in collectorProposals"
                :key="proposal.id"
                class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
              >
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(proposal.proposal_type) }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ formatValue(displayProposalValue(proposal.current_value)) }}</td>
                <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ formatValue(displayProposalValue(proposal.suggested_value)) }}</td>
                <td class="whitespace-nowrap px-4 py-3">{{ formatValue(proposal.confidence) }}</td>
                <td class="whitespace-nowrap px-4 py-3">
                  <span
                    class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="getProposalStatusBadgeClass(proposal.status)"
                  >{{ formatProposalStatusLabel(proposal.status) }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-3">
                  <div class="flex flex-wrap gap-2">
                    <button
                      class="ops-secondary-button"
                      :disabled="proposal.status !== 'pending'"
                      @click="approveProposal(proposal.id)"
                    >同意</button>
                    <button
                      class="ops-secondary-button"
                      :disabled="proposal.status !== 'pending' && proposal.status !== 'approved'"
                      @click="rejectProposal(proposal.id)"
                    >拒绝</button>
                    <button
                      class="ops-primary-button"
                      :disabled="proposal.status !== 'approved'"
                      @click="applyProposal(proposal.id)"
                    >应用</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </OpsSectionCard>
    </section>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { assetsApi } from '@/api/assets'
import { OpsEmptyState, OpsEntityHeader, OpsModal, OpsPage, OpsSectionCard } from '@/components/ops'
import type { AssetChangeProposalRow, CollectorEndpointRow, CollectorRunItemRow, CollectorRunRow, InstanceDetail } from '@/types/api'
import { formatInTz } from '@/utils/timezone'

type DetailField = {
  label: string
  value: string
}

const route = useRoute()
const detail = ref<InstanceDetail | null>(null)
const loading = ref(false)
const error = ref('')
const detailRefreshing = ref(false)
const launchLoading = ref(false)
const calibrationLoading = ref(false)
const actionMessage = ref('')
const actionError = ref('')
const showLaunchModal = ref(false)
const launchModalError = ref('')
const selectedCheckCodes = ref<string[]>(['DB_PORT_REACHABILITY'])
const runsLoading = ref(false)
const collectorRuns = ref<CollectorRunRow[]>([])
const runsError = ref('')
const selectedRunLoading = ref(false)
const selectedRunItems = ref<CollectorRunItemRow[]>([])
const selectedRunError = ref('')
const collectorEndpoints = ref<CollectorEndpointRow[]>([])
const endpointsLoading = ref(false)
const endpointsError = ref('')
const collectorProposals = ref<AssetChangeProposalRow[]>([])
const proposalsLoading = ref(false)
const proposalsError = ref('')
const launchCheckOptions = computed(() => [
  {
    value: 'DB_PORT_REACHABILITY',
    label: '数据库端口校验',
    description: '校验当前实例对应的 DB 端口是否可达。'
      + (detail.value?.server_id ? '' : ' 当前实例未关联服务器，部分检查不可用。'),
    disabled: false,
  },
  {
    value: 'SSH_PORT_REACHABILITY',
    label: '服务器 SSH 端口校验',
    description: '校验实例所在服务器的管理端口是否可达。',
    disabled: !detail.value?.server_id,
  },
])
const instanceId = computed(() => {
  const rawId = route.params.id
  return Array.isArray(rawId) ? rawId[0] : rawId
})

const headerSubtitleParts = computed(() => {
  if (!detail.value) return ['查看实例、角色、主机与集群信息。']
  return [detail.value.instance_code, detail.value.db_type, detail.value.db_version]
})
const headerChips = computed(() => [
  {
    icon: 'hub',
    label: detail.value?.cluster_code ? `集群 ${detail.value.cluster_code}` : '未关联集群',
  },
  {
    icon: 'dns',
    label: detail.value?.server_ip ? `服务器 ${detail.value.server_ip}` : '未关联服务器',
  },
])

const baseFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: '实例编号', value: formatValue(detail.value.instance_code) },
    { label: '实例名称', value: formatValue(detail.value.instance_name) },
    { label: '数据库类型', value: formatValue(detail.value.db_type) },
    { label: '数据库版本', value: formatValue(detail.value.db_version) },
  ]
})

const roleFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: '基础角色', value: formatValue(detail.value.node_role) },
    { label: '专属角色', value: formatValue(detail.value.engine_role) },
    { label: '来源角色', value: formatValue(detail.value.source_node_role) },
  ]
})

const hostFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: '服务器 IP', value: formatValue(detail.value.server_ip) },
    { label: '主机名', value: formatValue(detail.value.hostname) },
    { label: '站点', value: formatValue([detail.value.country, detail.value.factory_area].filter(Boolean).join(' / ')) },
    { label: '部署类型', value: formatValue(detail.value.deploy_type) },
    { label: 'Provider', value: formatValue(detail.value.provider) },
  ]
})

const clusterFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: 'Cluster', value: formatValue(detail.value.cluster_code) },
    { label: 'Cluster 名称', value: formatValue(detail.value.cluster_name) },
    { label: '集群类型', value: formatValue(detail.value.cluster_type) },
  ]
})

watch(
  () => route.params.id,
  async () => {
    const id = instanceId.value
    if (!id) {
      detail.value = null
      error.value = '缺少实例 ID'
      return
    }

    loading.value = true
    error.value = ''

    try {
      detail.value = await assetsApi.getInstance(id, { suppressErrorToast: true })
      await loadCollectorRuns(id)
      await loadCollectorEndpoints()
      await loadCollectorProposals()
    } catch (err: any) {
      detail.value = null
      error.value = err?.response?.data?.detail || err?.message || '加载失败'
      collectorRuns.value = []
      selectedRunItems.value = []
      collectorEndpoints.value = []
      collectorProposals.value = []
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

async function refreshDetail() {
  const id = instanceId.value
  if (!id) return
  detailRefreshing.value = true
  try {
    detail.value = await assetsApi.getInstance(id, { suppressErrorToast: true })
  } catch {
    // silent
  } finally {
    detailRefreshing.value = false
  }
}

async function loadCollectorRuns(id: string) {
  runsLoading.value = true
  runsError.value = ''
  try {
    if (typeof assetsApi.listInstanceCollectorRuns !== 'function') {
      collectorRuns.value = []
      return
    }

    collectorRuns.value = await assetsApi.listInstanceCollectorRuns(id, { limit: 20 }, { suppressErrorToast: true })
    if (collectorRuns.value.length > 0) {
      await selectRun(collectorRuns.value[0].run_id)
    } else {
      selectedRunItems.value = []
      selectedRunError.value = ''
    }
  } catch (err: any) {
    collectorRuns.value = []
    if (!isCollectorMissingError(err)) {
      runsError.value = err?.response?.data?.detail || err?.message || '加载失败'
    }
  } finally {
    runsLoading.value = false
  }
}

async function loadCollectorEndpoints() {
  const id = instanceId.value
  if (!id || !detail.value) return

  endpointsLoading.value = true
  endpointsError.value = ''
  try {
    if (typeof assetsApi.listCollectorEndpoints !== 'function') {
      collectorEndpoints.value = []
      return
    }

    const [instanceEndpoints, serverEndpoints] = await Promise.all([
      assetsApi.listCollectorEndpoints(
        { entity_type: 'db_instance', entity_id: Number(id) },
        { suppressErrorToast: true }
      ),
      detail.value.server_id
        ? assetsApi.listCollectorEndpoints(
            { entity_type: 'server', entity_id: detail.value.server_id },
            { suppressErrorToast: true }
          )
        : Promise.resolve([]),
    ])
    collectorEndpoints.value = [...instanceEndpoints, ...serverEndpoints]
  } catch (err: any) {
    collectorEndpoints.value = []
    if (!isCollectorMissingError(err)) {
      endpointsError.value = err?.response?.data?.detail || err?.message || '加载失败'
    }
  } finally {
    endpointsLoading.value = false
  }
}

async function loadCollectorProposals() {
  const id = instanceId.value
  if (!id) return
  proposalsLoading.value = true
  proposalsError.value = ''
  try {
    collectorProposals.value = await assetsApi.listCollectorProposals(
      {
        target_type: 'db_instance',
        target_id: Number(id),
      },
      { suppressErrorToast: true }
    )
  } catch (err: any) {
    collectorProposals.value = []
    if (!isCollectorMissingError(err)) {
      proposalsError.value = err?.response?.data?.detail || err?.message || '加载失败'
    }
  } finally {
    proposalsLoading.value = false
  }
}

async function selectRun(runId: string) {
  selectedRunLoading.value = true
  selectedRunError.value = ''
  try {
    if (typeof assetsApi.listCollectorRunItems !== 'function') {
      selectedRunItems.value = []
      return
    }

    selectedRunItems.value = await assetsApi.listCollectorRunItems(runId, { suppressErrorToast: true })
  } catch (err: any) {
    selectedRunItems.value = []
    if (!isCollectorMissingError(err)) {
      selectedRunError.value = err?.response?.data?.detail || err?.message || '加载失败'
    }
  } finally {
    selectedRunLoading.value = false
  }
}

function isCollectorMissingError(err: unknown) {
  const status = typeof err === 'object' && err !== null && 'response' in err
    ? (err as { response?: { status?: number } }).response?.status
    : undefined
  return status === 404
}

function openLaunchModal() {
  actionMessage.value = ''
  actionError.value = ''
  launchModalError.value = ''
  selectedCheckCodes.value = detail.value?.server_id
    ? ['DB_PORT_REACHABILITY', 'SSH_PORT_REACHABILITY']
    : ['DB_PORT_REACHABILITY']
  showLaunchModal.value = true
}

function closeLaunchModal() {
  if (launchLoading.value) return
  showLaunchModal.value = false
  launchModalError.value = ''
}

async function submitLaunch() {
  const id = instanceId.value
  if (!id) return
  if (!selectedCheckCodes.value.length) {
    launchModalError.value = '请至少选择一个校验项'
    return
  }

  launchLoading.value = true
  launchModalError.value = ''
  try {
    const res = await assetsApi.createCollectorRun({
      scope: {
        target_scope: 'db_instance',
        asset_ids: [Number(id)],
      },
      check_codes: [...selectedCheckCodes.value],
      options: {
        timeout_seconds: 5,
      },
    })
    actionMessage.value = `已提交 collector 任务，Job ID: ${res.awx_job_id ?? '-'}，共 ${res.item_count} 项`
    showLaunchModal.value = false
    await loadCollectorRuns(id)
    await loadCollectorEndpoints()
    await loadCollectorProposals()
    await refreshDetail()
  } catch (err: any) {
    actionError.value = err?.response?.data?.detail || err?.message || '提交失败'
  } finally {
    launchLoading.value = false
  }
}

async function launchPortCalibration() {
  const id = instanceId.value
  if (!id) return
  calibrationLoading.value = true
  actionMessage.value = ''
  actionError.value = ''
  try {
    const res = await assetsApi.createCollectorRun({
      run_type: 'port_calibration',
      target_scope: 'db_instance',
      asset_ids: [Number(id)],
      scope: {
        target_scope: 'db_instance',
        asset_ids: [Number(id)],
      },
      check_codes: ['PORT_CANDIDATE_REACHABILITY'],
      options: { timeout_seconds: 3, include_related_server: true },
    })
    actionMessage.value = `已提交端口校准任务，Job ID: ${res.awx_job_id ?? '-'}，共 ${res.item_count} 项`
    await loadCollectorRuns(id)
    await loadCollectorEndpoints()
    await loadCollectorProposals()
    await refreshDetail()
  } catch (err: any) {
    actionError.value = err?.response?.data?.detail || err?.message || '提交失败'
  } finally {
    calibrationLoading.value = false
  }
}

async function approveProposal(proposalId: number) {
  try {
    await assetsApi.approveCollectorProposal(proposalId)
    await loadCollectorProposals()
  } catch (err: any) {
    actionError.value = err?.response?.data?.detail || err?.message || 'approve 失败'
  }
}

async function rejectProposal(proposalId: number) {
  try {
    await assetsApi.rejectCollectorProposal(proposalId, {})
    await loadCollectorProposals()
  } catch (err: any) {
    actionError.value = err?.response?.data?.detail || err?.message || 'reject 失败'
  }
}

async function applyProposal(proposalId: number) {
  try {
    await assetsApi.applyCollectorProposal(proposalId)
    await loadCollectorProposals()
    if (instanceId.value) {
      await loadCollectorRuns(instanceId.value)
    }
  } catch (err: any) {
    actionError.value = err?.response?.data?.detail || err?.message || 'apply 失败'
  }
}

function displayProposalValue(value: unknown) {
  if (value && typeof value === 'object') {
    return JSON.stringify(value)
  }
  return value
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  return String(value)
}

function formatTime(val: string | null | undefined): string {
  return val ? formatInTz(val) : '-'
}

function formatResultStatus(item: CollectorRunItemRow) {
  const status = formatValue(item.result_status)
  if (!item.candidate_state) return status
  return `${status} (${item.candidate_state})`
}

// ── 状态标签 & Badge 工具函数 ──────────────────────────────────────────────

function formatTrustStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'verified') return '已核验'
  if (s === 'unverified') return '待核验'
  if (s === 'missing') return '资产缺失'
  if (s === 'drifted') return '已漂移'
  return status || '-'
}

function getTrustStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'verified') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'missing') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'drifted') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'unverified') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function formatReachabilityStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'online') return '在线'
  if (s === 'offline') return '离线'
  if (s === 'unknown') return '未知'
  return status || '-'
}

function getReachabilityStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'online') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'offline') return 'border-red-400/30 bg-red-400/10 text-red-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function formatRunStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return '等待中'
  if (s === 'launched' || s === 'running') return '执行中'
  if (s === 'finished' || s === 'success' || s === 'completed') return '已完成'
  if (s === 'failed' || s === 'error') return '失败'
  return status || '-'
}

function getRunStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'launched' || s === 'running') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'finished' || s === 'success' || s === 'completed') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (s === 'failed' || s === 'error') return 'border-red-400/30 bg-red-400/10 text-red-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function getResultStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (['success', 'ok', 'pass', 'reachable'].includes(s)) return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (['fail', 'failed', 'error', 'unreachable'].includes(s)) return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (['pending', 'running'].includes(s)) return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function getEndpointStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (['active', 'online', 'ok'].includes(s)) return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (['inactive', 'offline', 'error'].includes(s)) return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (['pending'].includes(s)) return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function formatProposalStatusLabel(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return '待审批'
  if (s === 'approved') return '已同意'
  if (s === 'rejected') return '已拒绝'
  if (s === 'applied') return '已应用'
  return status || '-'
}

function getProposalStatusBadgeClass(status: string | null | undefined): string {
  const s = (status || '').toLowerCase()
  if (s === 'pending') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'approved') return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  if (s === 'rejected') return 'border-slate-400/30 bg-slate-400/10 text-slate-300'
  if (s === 'applied') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}
</script>
