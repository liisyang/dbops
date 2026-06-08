<template>
  <OpsPage>
    <div class="mb-4">
      <router-link
        to="/assets/clusters"
        class="inline-flex items-center gap-2 text-sm text-on-surface-variant transition-colors hover:text-on-surface"
      >
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        返回集群列表
      </router-link>
    </div>

    <OpsEntityHeader
      :title="headerTitle"
      :subtitle-parts="headerSubtitleParts"
      icon="schema"
      :chips="headerChips"
    />

    <OpsSectionCard title="基础信息" subtitle="展示当前集群已返回的基础字段，不扩展不存在的后端数据。" icon="info">
      <OpsEmptyState
        v-if="!loading && !detail"
        :state="error ? 'error' : 'empty'"
        :title="error ? '集群详情加载失败' : '未找到对应集群'"
        :description="error || '当前 cluster_code 未匹配到可展示的集群数据。'"
      />

      <div v-else-if="detail" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="field in summaryFields"
          :key="field.label"
          class="field-card"
        >
          <div class="field-label">{{ field.label }}</div>
          <div class="field-value" :class="field.mono ? 'font-mono' : ''">
            {{ field.value }}
          </div>
        </div>
      </div>

      <div v-else class="py-8">
        <OpsEmptyState state="loading" title="正在加载集群详情" description="正在读取集群概要和实例关系数据。" />
      </div>
    </OpsSectionCard>

    <OpsSectionCard title="动态集群架构图" subtitle="基于集群基础信息、VIP 和已有实例列表生成最小拓扑。" icon="schema">
      <div v-if="loading && !detail" class="py-8">
        <OpsEmptyState state="loading" title="正在生成架构图" description="等待集群详情返回后生成节点和连线。" />
      </div>
      <OpsEmptyState
        v-else-if="!detail"
        :state="error ? 'error' : 'empty'"
        :title="error ? '无法生成架构图' : '暂无架构数据'"
        :description="error || '当前集群没有返回可用于生成拓扑的详情数据。'"
      />
      <div v-else class="space-y-4">
        <div v-if="detail.instances.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div
            v-for="instance in detail.instances"
            :key="instance.id"
            class="field-card"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="field-label">实例编码</div>
                <div class="field-value font-mono">{{ instance.instance_code || '-' }}</div>
              </div>
              <span class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                {{ resolveInstanceRoleLabel(instance) }}
              </span>
            </div>
            <div class="mt-2 text-sm text-slate-100">
              {{ instance.instance_name || '-' }}
            </div>
            <div class="mt-3 grid gap-2 text-xs text-slate-400">
              <div>数据库类型：{{ instance.db_type || '-' }}</div>
              <div>服务器 IP：{{ instance.server_ip || '-' }}</div>
              <div>位置：{{ [instance.country, instance.factory_area].filter(Boolean).join(' / ') || '-' }}</div>
            </div>
          </div>
        </div>

        <OpsTopology :nodes="topologyNodes" :edges="topologyEdges" />
      </div>
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { assetsApi } from '@/api/assets'
import OpsTopology from '@/components/ops/OpsTopology.vue'
import { OpsEmptyState, OpsEntityHeader, OpsPage, OpsSectionCard } from '@/components/ops'
import type { ClusterDetail, InstanceRow } from '@/types/api'

type SummaryField = {
  label: string
  value: string
  mono?: boolean
}

type TopologyNode = {
  id: string
  kind: string
  label: string
  subtitle?: string
  x: number
  y: number
  meta: Array<{ label: string; value: string }>
}

type TopologyEdge = {
  id: string
  from: string
  to: string
}

const route = useRoute()

const loading = ref(false)
const error = ref('')
const detail = ref<ClusterDetail | null>(null)

const headerTitle = computed(() => detail.value?.cluster_name || detail.value?.cluster_code || '集群详情')
const headerSubtitleParts = computed(() => {
  if (!detail.value) return ['按 cluster_code 查看集群概要和最小拓扑关系。']
  return [detail.value.cluster_code, detail.value.cluster_type, detail.value.source_cluster_no || '无来源号']
})
const headerChips = computed(() => [
  {
    icon: 'dns',
    label: `实例数 ${detail.value?.instance_count ?? 0}`,
  },
])

const summaryFields = computed<SummaryField[]>(() => {
  if (!detail.value) return []
  return [
    { label: 'Cluster Code', value: detail.value.cluster_code || '-', mono: true },
    { label: '集群名称', value: detail.value.cluster_name || '-' },
    { label: '集群类型', value: detail.value.cluster_type || '-' },
    { label: '来源 CLUSETR_NO', value: detail.value.source_cluster_no || '-' },
    { label: 'VIP', value: detail.value.vip_addresses.join(', ') || '-' },
    { label: '实例数', value: String(detail.value.instance_count ?? 0) },
  ]
})

const topologyNodes = computed<TopologyNode[]>(() => {
  const currentDetail = detail.value
  if (!currentDetail) return []

  const nodes: TopologyNode[] = [
    {
      id: 'cluster',
      kind: 'Cluster',
      label: currentDetail.cluster_name || currentDetail.cluster_code,
      subtitle: currentDetail.cluster_code,
      x: 50,
      y: 38,
      meta: [],
    },
  ]

  if (currentDetail.vip_addresses.length) {
    nodes.push({
      id: 'vip',
      kind: 'VIP',
      label: currentDetail.vip_addresses.length > 1 ? `${currentDetail.vip_addresses.length} 个 VIP` : currentDetail.vip_addresses[0],
      subtitle: currentDetail.vip_addresses.length > 1 ? currentDetail.vip_addresses.join(', ') : '集群虚拟地址',
      x: 50,
      y: 14,
      meta: currentDetail.vip_addresses.map((vip, index) => ({
        label: currentDetail.vip_addresses.length > 1 ? `vip_${index + 1}` : 'vip_addresses',
        value: vip,
      })),
    })
  }

  const primaryInstances = currentDetail.instances.filter((instance) => resolveInstanceRole(instance) === 'primary')
  const standbyInstances = currentDetail.instances.filter((instance) => resolveInstanceRole(instance) === 'standby')
  const unknownInstances = currentDetail.instances.filter((instance) => resolveInstanceRole(instance) === 'unknown')

  nodes.push(...buildInstanceNodes(primaryInstances, 'Primary Instance', 26, 74))
  nodes.push(...buildInstanceNodes(standbyInstances, 'Standby Instance', 74, 74))
  nodes.push(...buildInstanceNodes(unknownInstances, 'Unknown Role Instance', 50, 86))

  return nodes
})

const topologyEdges = computed<TopologyEdge[]>(() => {
  if (!detail.value) return []

  const edges: TopologyEdge[] = []
  const nodeIds = new Set(topologyNodes.value.map((node) => node.id))

  if (nodeIds.has('vip')) {
    edges.push({ id: 'edge-vip-cluster', from: 'vip', to: 'cluster' })
  }

  topologyNodes.value
    .filter((node) => node.id.startsWith('instance-'))
    .forEach((node) => {
      edges.push({ id: `edge-${node.id}`, from: 'cluster', to: node.id })
    })

  return edges
})

watch(
  () => route.params.clusterCode,
  () => {
    loadDetail()
  }
)

onMounted(() => {
  loadDetail()
})

async function loadDetail() {
  const clusterCode = String(route.params.clusterCode || '').trim()
  loading.value = true
  error.value = ''
  detail.value = null

  if (!clusterCode) {
    error.value = '缺少 cluster_code 参数。'
    loading.value = false
    return
  }

  try {
    const clusters = await assetsApi.listClusters()
    const matchedCluster = clusters.find((item) => item.cluster_code === clusterCode)

    if (!matchedCluster) {
      loading.value = false
      return
    }

    detail.value = await assetsApi.getCluster(matchedCluster.id)
  } catch (err) {
    error.value = resolveErrorMessage(err)
  } finally {
    loading.value = false
  }
}

function buildInstanceNodes(instances: InstanceRow[], kind: string, x: number, y: number): TopologyNode[] {
  return instances.map((instance, index) => ({
    id: `instance-${instance.id}`,
    kind,
    label: instance.instance_name || instance.instance_code,
    subtitle: instance.node_role || instance.engine_role || '-',
    x: calculateX(x, index, instances.length),
    y,
    meta: [
      { label: 'instance_name', value: instance.instance_name || '-' },
      { label: 'node_role', value: instance.node_role || '-' },
      { label: 'engine_role', value: instance.engine_role || '-' },
      { label: 'server_ip', value: instance.server_ip || '-' },
      {
        label: '位置',
        value: [instance.country, instance.factory_area].filter(Boolean).join(' / ') || '-',
      },
    ],
  }))
}

function calculateX(center: number, index: number, total: number) {
  if (total <= 1) return center
  const gap = 16
  const offset = index - (total - 1) / 2
  return center + offset * gap
}

function resolveInstanceRole(instance: InstanceRow) {
  const mergedRole = [instance.node_role, instance.engine_role, instance.source_node_role]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  if (/(primary|master|writer|active|主)/.test(mergedRole)) return 'primary'
  if (/(standby|slave|replica|reader|备|secondary)/.test(mergedRole)) return 'standby'
  return 'unknown'
}

function resolveInstanceRoleLabel(instance: InstanceRow) {
  const role = resolveInstanceRole(instance)
  if (role === 'primary') return '主库'
  if (role === 'standby') return '备库'
  return '未知角色'
}

function resolveErrorMessage(err: unknown) {
  if (typeof err === 'string') return err
  if (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string') {
    return err.message
  }
  return '请求集群详情失败，请稍后重试。'
}
</script>

