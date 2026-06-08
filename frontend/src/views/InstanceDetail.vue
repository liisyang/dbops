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
      <span v-if="actionMessage" class="text-sm text-green-300">{{ actionMessage }}</span>
      <span v-if="actionError" class="text-sm text-red-300">{{ actionError }}</span>
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
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <div v-for="field in verifyFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
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
          <table class="ops-table min-w-full">
            <thead>
              <tr>
                <th>run_id</th>
                <th>status</th>
                <th>awx_job_id</th>
                <th>target_host</th>
                <th>target_port</th>
                <th>started_at</th>
                <th>finished_at</th>
                <th>error_message</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in collectorRuns" :key="run.id" class="cursor-pointer" @click="selectRun(run.run_id)">
                <td>{{ formatValue(run.run_id) }}</td>
                <td>{{ formatValue(run.status) }}</td>
                <td>{{ formatValue(run.awx_job_id) }}</td>
                <td>{{ formatValue(run.target_host) }}</td>
                <td>{{ formatValue(run.target_port) }}</td>
                <td>{{ formatValue(run.started_at) }}</td>
                <td>{{ formatValue(run.finished_at) }}</td>
                <td>{{ formatValue(run.error_message) }}</td>
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
          <table class="ops-table min-w-full">
            <thead>
              <tr>
                <th>item_key</th>
                <th>check_code</th>
                <th>target_scope</th>
                <th>target_host</th>
                <th>target_port</th>
                <th>status</th>
                <th>result_status</th>
                <th>result_message</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in selectedRunItems" :key="item.id">
                <td>{{ formatValue(item.item_key) }}</td>
                <td>{{ formatValue(item.check_code) }}</td>
                <td>{{ formatValue(item.target_scope) }}</td>
                <td>{{ formatValue(item.target_host) }}</td>
                <td>{{ formatValue(item.target_port) }}</td>
                <td>{{ formatValue(item.status) }}</td>
                <td>{{ formatValue(item.result_status) }}</td>
                <td>{{ formatValue(item.result_message) }}</td>
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
          <table class="ops-table min-w-full">
            <thead>
              <tr>
                <th>entity_type</th>
                <th>entity_id</th>
                <th>host</th>
                <th>port</th>
                <th>source</th>
                <th>status</th>
                <th>last_verify_at</th>
                <th>last_message</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="endpoint in collectorEndpoints" :key="endpoint.id">
                <td>{{ formatValue(endpoint.entity_type) }}</td>
                <td>{{ formatValue(endpoint.entity_id) }}</td>
                <td>{{ formatValue(endpoint.host) }}</td>
                <td>{{ formatValue(endpoint.port) }}</td>
                <td>{{ formatValue(endpoint.source) }}</td>
                <td>{{ formatValue(endpoint.status) }}</td>
                <td>{{ formatValue(endpoint.last_verify_at) }}</td>
                <td>{{ formatValue(endpoint.last_message) }}</td>
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
import type { CollectorEndpointRow, CollectorRunItemRow, CollectorRunRow, InstanceDetail } from '@/types/api'

type DetailField = {
  label: string
  value: string
}

const route = useRoute()
const detail = ref<InstanceDetail | null>(null)
const loading = ref(false)
const error = ref('')
const launchLoading = ref(false)
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
    description: '校验实例所在服务器的 22 端口是否可达。',
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

const verifyFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: '可信状态', value: formatValue(detail.value.trust_status) },
    { label: '连通状态', value: formatValue(detail.value.reachability_status) },
    { label: '最近校验时间', value: formatValue(detail.value.last_verify_at) },
    { label: '最近校验消息', value: formatValue(detail.value.verify_message) },
    { label: '最近 AWX Job ID', value: formatValue(detail.value.last_awx_job_id) },
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
    } catch (err: any) {
      detail.value = null
      error.value = err?.response?.data?.detail || err?.message || '加载失败'
      collectorRuns.value = []
      selectedRunItems.value = []
      collectorEndpoints.value = []
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

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
  } catch (err: any) {
    actionError.value = err?.response?.data?.detail || err?.message || '提交失败'
  } finally {
    launchLoading.value = false
  }
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  return String(value)
}
</script>
