<template>
  <OpsPage>
    <OpsPageHeader title="集群" subtitle="按 `cluster_code` 查看技术集群和来源辅助编号。" />

    <OpsStatGrid :items="statItems" />

    <div class="rounded-lg bg-surface-container px-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0 truncate text-sm text-on-surface-variant">
          图形分布 默认收起，点击展开当前集群分布图
        </div>
        <button
          class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-on-surface transition-colors hover:bg-white/10"
          type="button"
          @click="clusterChartsOpen = !clusterChartsOpen"
        >
          {{ clusterChartsOpen ? '收起' : '展开' }}
        </button>
      </div>
      <div v-if="clusterChartsOpen" class="mt-4">
        <SimpleBarChart :items="clusterTypeChart" :as-card="false" />
      </div>
    </div>

    <OpsFilterBar
      :keyword="draftKeyword"
      :selects="filterSelects"
      @update:keyword="draftKeyword = $event"
      @update:select="handleDraftSelectUpdate"
      @search="applyFilters"
      @reset="resetFilters"
    >
      <template #tools><OpsColumnPicker
          :columns="orderedColumns"
          :is-visible="isColVisible"
          @toggle="toggleColumn"
          @reorder="reorderColumn"
          @reset="resetColumns"
        />
        </template>
        <template #actions>
          <button
          type="button"
          class="ops-primary-button"
          @click="startCreating"
        >
          <span class="material-symbols-outlined text-[18px]">add</span>
          新增集群
        </button>
        </template>
    </OpsFilterBar>

    <OpsModal
      :open="showModal"
      :title="editingCluster ? '编辑集群' : '新增集群'"
      :subtitle="editingCluster ? '修改集群基本信息' : '新增一个技术集群'"
      :icon="editingCluster ? 'edit' : 'hub'"
      size="lg"
      @close="closeModal"
    >
      <form class="space-y-5" @submit.prevent="submitClusterForm">
        <div v-if="modalError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ modalError }}
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card sm:col-span-2">
            <span class="field-label">集群名称 <span class="text-red-400">*</span></span>
            <input v-model.trim="clusterForm.cluster_name" class="field-input" type="text" placeholder="请输入集群名称" />
          </label>
          <label class="block field-card">
            <span class="field-label">业务系统 <span class="text-red-400">*</span></span>
            <select v-model="clusterForm.business_system_id" class="field-input">
              <option :value="0" disabled>请选择业务系统</option>
              <option v-for="sys in businessSystems" :key="sys.id" :value="sys.id">{{ sys.system_name }}</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">数据库类型 <span class="text-red-400">*</span></span>
            <select v-model="clusterForm.db_type_id" class="field-input">
              <option :value="0" disabled>请选择数据库类型</option>
              <option v-for="dbType in dbTypes" :key="dbType.id" :value="dbType.id">{{ dbType.name }}</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">集群类型 <span class="text-red-400">*</span></span>
            <select v-model="clusterForm.cluster_type" class="field-input">
              <option value="" disabled>请选择集群类型</option>
              <option value="SINGLE">SINGLE</option>
              <option value="HA">HA</option>
              <option value="DATAGUARD">DATAGUARD</option>
              <option value="RAC">RAC</option>
              <option value="MHA">MHA</option>
              <option value="MGR">MGR</option>
              <option value="other">other</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">状态</span>
            <select v-model="clusterForm.status" class="field-input">
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">备注</span>
            <textarea
              v-model.trim="clusterForm.remark"
              class="field-input min-h-[80px] resize-y"
              placeholder="可选"
            ></textarea>
          </label>
          <div class="block field-card sm:col-span-2">
            <span class="field-label">VIP 地址</span>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="vip in clusterForm.vip_addresses"
                :key="vip"
                class="inline-flex items-center gap-1 rounded-md bg-primary/15 px-2 py-0.5 text-xs text-primary"
              >
                {{ vip }}
                <button type="button" class="ml-0.5 opacity-60 hover:opacity-100" @click="removeVip(vip)">
                  <span class="material-symbols-outlined text-[14px]">close</span>
                </button>
              </span>
            </div>
            <div class="flex gap-2">
              <input
                v-model.trim="vipInput"
                class="field-input flex-1"
                type="text"
                placeholder="输入 IP，回车或逗号分隔添加多个"
                @keydown.enter.prevent="addVip"
                @keydown.comma.prevent="addVip"
              />
              <button type="button" class="ops-secondary-button shrink-0" @click="addVip">添加</button>
            </div>
          </div>
        </div>
      </form>
      <template #footer>
        <div class="flex items-center justify-end gap-3">
          <button type="button" class="ops-secondary-button" @click="closeModal">取消</button>
          <button type="button" class="ops-primary-button" :disabled="submitting" @click="submitClusterForm">
            <span class="material-symbols-outlined text-[18px]">{{ submitting ? 'hourglass_empty' : 'check' }}</span>
            {{ submitting ? '保存中...' : (editingCluster ? '保存修改' : '确认新增') }}
          </button>
        </div>
      </template>
    </OpsModal>

    <OpsTableShell
      :loading="loading"
      :empty="!filteredClusters.length && !loading"
      :empty-state="error ? 'error' : 'empty'"
      :empty-title="error ? '加载失败' : hasActiveFilters ? '暂无匹配结果' : '暂无集群数据'"
      :empty-description="error || (hasActiveFilters ? '当前筛选条件没有匹配的集群。' : '当前没有集群列表数据。')"
      :total-items="filteredClusters.length"
      :current-page="currentPage"
      :page-size="pageSize"
      @update:current-page="currentPage = $event"
      @update:page-size="updatePageSize"
    >
      <table class="w-full text-sm">
        <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
          <tr>
            <th v-for="col in visibleColumns" :key="col.key" class="whitespace-nowrap px-4 py-3">{{ col.label }}</th>
            <th class="whitespace-nowrap px-4 py-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="cluster in pagedFilteredClusters"
            :key="cluster.id"
            class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
            :class="canViewClusterDetail(cluster) ? 'cursor-pointer' : ''"
            @click="openClusterPage(cluster)"
          >
            <td v-for="col in visibleColumns" :key="col.key" :class="['whitespace-nowrap px-4 py-3', col.key === 'cluster_code' ? 'font-mono' : '']">
              <template v-if="col.key === 'cluster_code'">
                <router-link
                  v-if="canViewClusterDetail(cluster)"
                  :to="`/assets/clusters/${cluster.cluster_code}`"
                  class="text-[#8ec5ff] hover:underline"
                  @click.stop
                >
                  {{ cluster.cluster_code }}
                </router-link>
                <span v-else class="text-on-surface">{{ cluster.cluster_code }}</span>
              </template>
              <template v-else-if="col.key === 'cluster_name'">
                <router-link
                  v-if="canViewClusterDetail(cluster)"
                  :to="`/assets/clusters/${cluster.cluster_code}`"
                  class="text-[#8ec5ff] hover:underline"
                  @click.stop
                >
                  {{ cluster.cluster_name }}
                </router-link>
                <span v-else class="text-on-surface">{{ cluster.cluster_name }}</span>
              </template>
              <template v-else-if="col.key === 'cluster_type'">{{ cluster.cluster_type }}</template>
              <template v-else-if="col.key === 'source_cluster_no'">{{ cluster.source_cluster_no || '-' }}</template>
              <template v-else-if="col.key === 'vip_addresses'">{{ cluster.vip_addresses.join(', ') || '-' }}</template>
              <template v-else-if="col.key === 'instance_count'">{{ cluster.instance_count }}</template>
            </td>
            <td class="whitespace-nowrap px-4 py-3" @click.stop>
              <div class="flex items-center justify-end gap-2">
                <button
                  class="ops-edit-button"
                  type="button"
                  @click="startEditing(cluster)"
                >
                  <span class="material-symbols-outlined text-[14px]">edit</span>
                  编辑
                </button>
                <button
                  class="ops-danger-button"
                  type="button"
                  @click="removeCluster(cluster)"
                >
                  <span class="material-symbols-outlined text-[14px]">delete</span>
                  删除
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </OpsTableShell>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { assetsApi } from '@/api/assets'
import SimpleBarChart from '@/components/SimpleBarChart.vue'
import { OpsColumnPicker, OpsFilterBar, OpsModal, OpsPage, OpsPageHeader, OpsStatGrid, OpsTableShell } from '@/components/ops'
import { assetPageMetric, useAssetPageMetrics } from '@/composables/useAssetPageMetrics'
import { useAssetStatBuckets } from '@/composables/useAssetStatBuckets'
import { useAssetArrayList } from '@/composables/useAssetArrayList'
import { useColumnVisibility } from '@/composables/useColumnVisibility'
import type { ClusterRow, ClusterUpsertPayload, DbTypeRow, SystemRow } from '@/types/api'

const router = useRouter()
const { items: clusters, loading, error, reload } = useAssetArrayList(() => assetsApi.listClusters())

const CLUSTER_COLUMNS = [
  { key: 'cluster_code',     label: 'Cluster Code' },
  { key: 'cluster_name',     label: '名称' },
  { key: 'cluster_type',     label: '类型' },
  { key: 'source_cluster_no', label: '来源 NO', defaultVisible: false },
  { key: 'vip_addresses',    label: 'VIP' },
  { key: 'instance_count',   label: '实例数' },
]
const { orderedColumns, visibleColumns, isVisible: isColVisible, toggleColumn, reorderColumn, resetColumns } = useColumnVisibility('clusters', CLUSTER_COLUMNS)

const draftKeyword = ref('')
const draftClusterType = ref('all')
const appliedKeyword = ref('')
const appliedClusterType = ref('all')
const currentPage = ref(1)
const pageSize = ref<number | 'all'>(30)
const clusterChartsOpen = ref(false)

// CRUD modal state
const showModal = ref(false)
const editingCluster = ref<ClusterRow | null>(null)
const submitting = ref(false)
const modalError = ref('')
const businessSystems = ref<SystemRow[]>([])
const dbTypes = ref<DbTypeRow[]>([])
const vipInput = ref('')

function addVip() {
  const val = vipInput.value.trim()
  if (!val) return
  if (!clusterForm.vip_addresses) clusterForm.vip_addresses = []
  const parts = val.split(/[,\s]+/).map(v => v.trim()).filter(Boolean)
  for (const p of parts) {
    if (!clusterForm.vip_addresses.includes(p)) {
      clusterForm.vip_addresses.push(p)
    }
  }
  vipInput.value = ''
}

function removeVip(vip: string) {
  if (!clusterForm.vip_addresses) return
  clusterForm.vip_addresses = clusterForm.vip_addresses.filter(v => v !== vip)
}

const clusterForm = reactive<ClusterUpsertPayload>({
  cluster_name: '',
  business_system_id: 0,
  db_type_id: 0,
  cluster_type: '',
  status: 'active',
  remark: '',
  vip_addresses: [],
})

async function loadCatalogues() {
  try {
    const [systems, types] = await Promise.all([
      assetsApi.listBusinessSystems(),
      assetsApi.listDbTypes(),
    ])
    businessSystems.value = systems
    dbTypes.value = types
  } catch {
    // non-critical; form dropdowns may be empty
  }
}

function resetForm() {
  clusterForm.cluster_name = ''
  clusterForm.business_system_id = 0
  clusterForm.db_type_id = 0
  clusterForm.cluster_type = ''
  clusterForm.status = 'active'
  clusterForm.remark = ''
  clusterForm.vip_addresses = []
  vipInput.value = ''
}

function startCreating() {
  modalError.value = ''
  editingCluster.value = null
  resetForm()
  showModal.value = true
}

function startEditing(cluster: ClusterRow) {
  modalError.value = ''
  editingCluster.value = cluster
  clusterForm.cluster_name = cluster.cluster_name
  clusterForm.business_system_id = cluster.business_system_id
  clusterForm.db_type_id = (cluster as any).db_type_id || 0
  clusterForm.cluster_type = cluster.cluster_type
  clusterForm.status = (cluster as any).status || 'active'
  clusterForm.remark = (cluster as any).remark || ''
  clusterForm.vip_addresses = [...cluster.vip_addresses]
  vipInput.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingCluster.value = null
  modalError.value = ''
  resetForm()
}

async function submitClusterForm() {
  if (!clusterForm.cluster_name) {
    modalError.value = '集群名称不能为空'
    return
  }
  if (!clusterForm.business_system_id) {
    modalError.value = '请选择业务系统'
    return
  }
  if (!clusterForm.db_type_id) {
    modalError.value = '请选择数据库类型'
    return
  }
  if (!clusterForm.cluster_type) {
    modalError.value = '请选择集群类型'
    return
  }

  submitting.value = true
  modalError.value = ''
  try {
    if (editingCluster.value) {
      await assetsApi.updateCluster(editingCluster.value.id, { ...clusterForm })
    } else {
      await assetsApi.createCluster({ ...clusterForm })
    }
    await reload()
    closeModal()
  } catch (err) {
    modalError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    submitting.value = false
  }
}

async function removeCluster(cluster: ClusterRow) {
  const confirmed = window.confirm(`确认删除集群「${cluster.cluster_name}」吗？`)
  if (!confirmed) return
  try {
    await assetsApi.deleteCluster(cluster.id)
    await reload()
  } catch (err) {
    alert(err instanceof Error ? err.message : '删除失败')
  }
}

type FilterOption = { label: string; value: string }
type FilterSelect = {
  key: string
  label: string
  value: string
  options: FilterOption[]
}

const statItems = useAssetPageMetrics(clusters, () => clusters.value.length, [
  assetPageMetric.total('集群总数'),
  assetPageMetric.countEquals('SINGLE', (item) => item.cluster_type, 'SINGLE'),
  assetPageMetric.countNotEquals('HA 集群', (item) => item.cluster_type, 'SINGLE'),
  assetPageMetric.countEquals('单实例集群', (item) => item.instance_count, 1),
])

const clusterTypeChart = useAssetStatBuckets(clusters, (item) => item.cluster_type)

const clusterTypeOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(clusters.value.map((item) => item.cluster_type).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部集群类型', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const filterSelects = computed<FilterSelect[]>(() => [
  {
    key: 'cluster_type',
    label: '集群类型',
    value: draftClusterType.value,
    options: clusterTypeOptions.value,
  },
])

function handleDraftSelectUpdate(payload: { key: string; value: string }) {
  if (payload.key === 'cluster_type') {
    draftClusterType.value = payload.value || 'all'
  }
}

function applyFilters() {
  appliedKeyword.value = draftKeyword.value
  appliedClusterType.value = draftClusterType.value
  currentPage.value = 1
}

function resetFilters() {
  draftKeyword.value = ''
  draftClusterType.value = 'all'
  appliedKeyword.value = ''
  appliedClusterType.value = 'all'
  currentPage.value = 1
}

const normalizedAppliedKeyword = computed(() => appliedKeyword.value.trim().toLowerCase())

const filteredClusters = computed(() => {
  const keywordText = normalizedAppliedKeyword.value
  return clusters.value.filter((cluster) => {
    const matchesKeyword =
      !keywordText ||
      [cluster.cluster_name, cluster.business_system_name, cluster.cluster_type, cluster.source_cluster_no]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keywordText)) ||
      cluster.vip_addresses.some((vip) => vip.toLowerCase().includes(keywordText))

    const matchesClusterType = appliedClusterType.value === 'all' || cluster.cluster_type === appliedClusterType.value

    return matchesKeyword && matchesClusterType
  })
})

const pagedFilteredClusters = computed(() => {
  if (pageSize.value === 'all') {
    return filteredClusters.value
  }

  const start = (currentPage.value - 1) * pageSize.value
  return filteredClusters.value.slice(start, start + pageSize.value)
})

const hasActiveFilters = computed(() => {
  return normalizedAppliedKeyword.value.length > 0 || appliedClusterType.value !== 'all'
})

function canViewClusterDetail(cluster: ClusterRow) {
  return cluster.cluster_type !== 'SINGLE'
}

function openClusterPage(cluster: ClusterRow) {
  if (!canViewClusterDetail(cluster)) {
    return
  }
  router.push(`/assets/clusters/${cluster.cluster_code}`)
}

function updatePageSize(value: number | 'all') {
  pageSize.value = value === 'all' ? 'all' : Number(value)
  currentPage.value = 1
}

watch(filteredClusters, (items) => {
  const effectivePageSize = pageSize.value === 'all' ? Math.max(1, items.length) : pageSize.value
  const totalPages = Math.max(1, Math.ceil(items.length / effectivePageSize))
  if (currentPage.value > totalPages) {
    currentPage.value = totalPages
  }
}, { immediate: true })

onMounted(() => {
  void loadCatalogues()
})
</script>
