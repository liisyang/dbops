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
      <button class="ops-primary-button" :disabled="launchLoading" @click="handleLaunchVerify">
        <span class="material-symbols-outlined text-[18px]">play_arrow</span>
        {{ launchLoading ? '提交中...' : '校验资产' }}
      </button>
      <span v-if="actionMessage" class="text-sm text-green-300">{{ actionMessage }}</span>
      <span v-if="actionError" class="text-sm text-red-300">{{ actionError }}</span>
    </div>

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
              <tr v-for="run in collectorRuns" :key="run.id">
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
    </section>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { assetsApi } from '@/api/assets'
import { OpsEmptyState, OpsEntityHeader, OpsPage, OpsSectionCard } from '@/components/ops'
import type { CollectorRunRow, InstanceDetail } from '@/types/api'

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
const runsLoading = ref(false)
const collectorRuns = ref<CollectorRunRow[]>([])
const runsError = ref('')
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
      detail.value = await assetsApi.getInstance(id)
      await loadCollectorRuns(id)
    } catch (err: any) {
      detail.value = null
      error.value = err?.response?.data?.detail || err?.message || '加载失败'
      collectorRuns.value = []
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
    collectorRuns.value = await assetsApi.listInstanceCollectorRuns(id, { limit: 20 })
  } catch (err: any) {
    collectorRuns.value = []
    runsError.value = err?.response?.data?.detail || err?.message || '加载失败'
  } finally {
    runsLoading.value = false
  }
}

async function handleLaunchVerify() {
  const id = instanceId.value
  if (!id) return
  launchLoading.value = true
  actionMessage.value = ''
  actionError.value = ''
  try {
    const res = await assetsApi.launchAssetVerify(id, { check_timeout: 5 })
    actionMessage.value = `已提交 AWX 校验任务，Job ID: ${res.awx_job_id ?? '-'}`
    await loadCollectorRuns(id)
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
