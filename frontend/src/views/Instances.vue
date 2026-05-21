<template>
  <OpsPage>
    <OpsPageHeader title="数据库实例" subtitle="按实例查看集群、服务器、站点和标准化角色。" />

    <OpsStatGrid :items="statItems" />

    <div class="rounded-lg bg-surface-container px-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0 truncate text-sm text-on-surface-variant">
          图形分布 默认收起，点击展开当前实例分布图
        </div>
        <button
          class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-on-surface transition-colors hover:bg-white/10"
          type="button"
          @click="instanceChartsOpen = !instanceChartsOpen"
        >
          {{ instanceChartsOpen ? '收起' : '展开' }}
        </button>
      </div>
      <div v-if="instanceChartsOpen" class="mt-4">
        <SimpleBarChart :items="dbTypeChart" :as-card="false" />
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
          新增实例
        </button>
        </template>
    </OpsFilterBar>

    <OpsModal
      :open="showModal"
      :title="editingInstance ? '编辑实例' : '新增实例'"
      :subtitle="editingInstance ? '修改实例基本信息' : '新增一个数据库实例'"
      :icon="editingInstance ? 'edit' : 'storage'"
      size="lg"
      @close="closeModal"
    >
      <form class="space-y-5" @submit.prevent="submitInstanceForm">
        <div v-if="modalError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ modalError }}
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card sm:col-span-2">
            <span class="field-label">实例名称 <span class="text-red-400">*</span></span>
            <input v-model.trim="instanceForm.instance_name" class="field-input" type="text" placeholder="请输入实例名称" />
          </label>
          <label class="block field-card">
            <span class="field-label">所属集群 <span class="text-red-400">*</span></span>
            <select v-model="instanceForm.cluster_id" class="field-input">
              <option :value="0" disabled>请选择集群</option>
              <option v-for="c in clustersList" :key="c.id" :value="c.id">{{ c.cluster_name }}</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">数据库类型 <span class="text-red-400">*</span></span>
            <select v-model="instanceForm.db_type_id" class="field-input">
              <option :value="0" disabled>请选择数据库类型</option>
              <option v-for="dbType in dbTypes" :key="dbType.id" :value="dbType.id">{{ dbType.name }}</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">所在服务器 <span class="text-red-400">*</span></span>
            <select v-model="instanceForm.server_id" class="field-input">
              <option :value="0" disabled>请选择服务器</option>
              <option v-for="srv in serversDropdown" :key="srv.id" :value="srv.id">{{ srv.hostname }}</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">节点角色 <span class="text-red-400">*</span></span>
            <select v-model="instanceForm.node_role" class="field-input">
              <option value="" disabled>请选择节点角色</option>
              <option value="primary">primary</option>
              <option value="standby">standby</option>
              <option value="single">single</option>
              <option value="member">member</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">服务名称</span>
            <input v-model.trim="instanceForm.service_name" class="field-input" type="text" placeholder="可选" />
          </label>
          <label class="block field-card">
            <span class="field-label">状态</span>
            <select v-model="instanceForm.status" class="field-input">
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">备注</span>
            <textarea
              v-model.trim="instanceForm.remark"
              class="field-input min-h-[80px] resize-y"
              placeholder="可选"
            ></textarea>
          </label>
        </div>
      </form>
      <template #footer>
        <div class="flex items-center justify-end gap-3">
          <button type="button" class="ops-secondary-button" @click="closeModal">取消</button>
          <button type="button" class="ops-primary-button" :disabled="submitting" @click="submitInstanceForm">
            <span class="material-symbols-outlined text-[18px]">{{ submitting ? 'hourglass_empty' : 'check' }}</span>
            {{ submitting ? '保存中...' : (editingInstance ? '保存修改' : '确认新增') }}
          </button>
        </div>
      </template>
    </OpsModal>

    <OpsTableShell
      :loading="loading"
      :empty="!filteredItems.length && !loading"
      :empty-state="error ? 'error' : 'empty'"
      :empty-title="error ? '加载失败' : hasActiveFilters ? '暂无匹配结果' : '暂无实例数据'"
      :empty-description="error || (hasActiveFilters ? '当前筛选条件没有匹配的数据库实例。' : '当前没有数据库实例列表数据。')"
      :total-items="filteredItems.length"
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
            v-for="instance in pagedFilteredItems"
            :key="instance.id"
            class="cursor-pointer border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
            @click="openInstancePage(instance)"
          >
            <td v-for="col in visibleColumns" :key="col.key" :class="['whitespace-nowrap px-4 py-3', col.key === 'instance_name' ? 'font-medium' : col.key === 'cluster_code' ? 'font-mono' : '']">
              <template v-if="col.key === 'instance_name'">{{ instance.instance_name }}</template>
              <template v-else-if="col.key === 'db_type'">
                <div class="flex items-center gap-1.5">
                  <DbTypeIcon v-if="instance.db_type" :db-type="instance.db_type" size="sm" />
                  <span>{{ instance.db_type || '-' }}</span>
                </div>
              </template>
              <template v-else-if="col.key === 'db_version'">{{ instance.db_version || '-' }}</template>
              <template v-else-if="col.key === 'node_role'">{{ instance.node_role }}</template>
              <template v-else-if="col.key === 'engine_role'">{{ instance.engine_role || '-' }}</template>
              <template v-else-if="col.key === 'cluster_code'">{{ instance.cluster_code || '-' }}</template>
              <template v-else-if="col.key === 'server_ip'">{{ instance.server_ip || '-' }}</template>
              <template v-else-if="col.key === 'system_name'">{{ instance.system_name || '-' }}</template>
              <template v-else-if="col.key === 'country'">{{ instance.country || '-' }}</template>
              <template v-else-if="col.key === 'provider'">{{ instance.provider || '-' }}</template>
              <template v-else-if="col.key === 'deploy_type'">{{ instance.deploy_type || '-' }}</template>
              <template v-else-if="col.key === 'factory_area'">{{ instance.factory_area || '-' }}</template>
              <template v-else-if="col.key === 'room_location'">{{ instance.room_location || '-' }}</template>
            </td>
            <td class="whitespace-nowrap px-4 py-3" @click.stop>
              <div class="flex items-center justify-end gap-2">
                <button
                  class="ops-edit-button"
                  type="button"
                  @click="startEditing(instance)"
                >
                  <span class="material-symbols-outlined text-[14px]">edit</span>
                  编辑
                </button>
                <button
                  class="ops-danger-button"
                  type="button"
                  @click="removeInstance(instance)"
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
import DbTypeIcon from '@/components/DbTypeIcon.vue'
import SimpleBarChart from '@/components/SimpleBarChart.vue'
import { OpsColumnPicker, OpsFilterBar, OpsModal, OpsPage, OpsPageHeader, OpsStatGrid, OpsTableShell } from '@/components/ops'
import { assetPageMetric, useAssetPageMetrics } from '@/composables/useAssetPageMetrics'
import { useAssetStatBuckets } from '@/composables/useAssetStatBuckets'
import { useColumnVisibility } from '@/composables/useColumnVisibility'
import { usePagedAssetList } from '@/composables/usePagedAssetList'
import type { ClusterRow, DbInstanceUpsertPayload, DbTypeRow, InstanceRow, ServerDropdownRow } from '@/types/api'

const router = useRouter()
const { items, total, loading, error, reload } = usePagedAssetList((params) => assetsApi.listInstances(params))

const INSTANCE_COLUMNS = [
  { key: 'instance_name', label: '实例' },
  { key: 'db_type',       label: '数据库类型' },
  { key: 'db_version',    label: '版本' },
  { key: 'node_role',     label: '基础角色' },
  { key: 'engine_role',   label: '专属角色' },
  { key: 'cluster_code',  label: 'Cluster' },
  { key: 'server_ip',     label: '服务器' },
  { key: 'system_name',   label: '业务系统', defaultVisible: false },
  { key: 'country',       label: '国家', defaultVisible: false },
  { key: 'provider',      label: 'Provider', defaultVisible: false },
  { key: 'deploy_type',   label: '部署类型', defaultVisible: false },
  { key: 'factory_area',  label: '厂区', defaultVisible: false },
  { key: 'room_location', label: '机房位置', defaultVisible: false },
]
const { orderedColumns, visibleColumns, isVisible: isColVisible, toggleColumn, reorderColumn, resetColumns } = useColumnVisibility('instances', INSTANCE_COLUMNS)

const draftKeyword = ref('')
const draftFactoryArea = ref('all')
const draftDbType = ref('all')
const draftNodeRole = ref('all')
const appliedKeyword = ref('')
const appliedFactoryArea = ref('all')
const appliedDbType = ref('all')
const appliedNodeRole = ref('all')
const currentPage = ref(1)
const pageSize = ref<number | 'all'>(30)
const instanceChartsOpen = ref(false)

// CRUD modal state
const showModal = ref(false)
const editingInstance = ref<InstanceRow | null>(null)
const submitting = ref(false)
const modalError = ref('')
const dbTypes = ref<DbTypeRow[]>([])
const serversDropdown = ref<ServerDropdownRow[]>([])
const clustersList = ref<ClusterRow[]>([])

const instanceForm = reactive<DbInstanceUpsertPayload>({
  instance_name: '',
  cluster_id: 0,
  db_type_id: 0,
  server_id: 0,
  db_version_id: null,
  node_role: '',
  service_name: '',
  status: 'active',
  remark: '',
})

async function loadCatalogues() {
  try {
    const [types, servers, clusters] = await Promise.all([
      assetsApi.listDbTypes(),
      assetsApi.listServersDropdown(),
      assetsApi.listClusters(),
    ])
    dbTypes.value = types
    serversDropdown.value = servers
    clustersList.value = clusters
  } catch {
    // non-critical
  }
}

function resetForm() {
  instanceForm.instance_name = ''
  instanceForm.cluster_id = 0
  instanceForm.db_type_id = 0
  instanceForm.server_id = 0
  instanceForm.db_version_id = null
  instanceForm.node_role = ''
  instanceForm.service_name = ''
  instanceForm.status = 'active'
  instanceForm.remark = ''
}

function startCreating() {
  modalError.value = ''
  editingInstance.value = null
  resetForm()
  showModal.value = true
}

function startEditing(instance: InstanceRow) {
  modalError.value = ''
  editingInstance.value = instance
  instanceForm.instance_name = instance.instance_name
  instanceForm.cluster_id = instance.cluster_id
  instanceForm.db_type_id = 0  // db_type_id not in InstanceRow, will be 0
  instanceForm.server_id = instance.server_id
  instanceForm.db_version_id = null
  instanceForm.node_role = instance.node_role
  instanceForm.service_name = ''
  instanceForm.status = 'active'
  instanceForm.remark = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingInstance.value = null
  modalError.value = ''
  resetForm()
}

async function submitInstanceForm() {
  if (!instanceForm.instance_name) {
    modalError.value = '实例名称不能为空'
    return
  }
  if (!instanceForm.cluster_id) {
    modalError.value = '请选择所属集群'
    return
  }
  if (!instanceForm.db_type_id) {
    modalError.value = '请选择数据库类型'
    return
  }
  if (!instanceForm.server_id) {
    modalError.value = '请选择所在服务器'
    return
  }
  if (!instanceForm.node_role) {
    modalError.value = '请选择节点角色'
    return
  }

  submitting.value = true
  modalError.value = ''
  try {
    if (editingInstance.value) {
      await assetsApi.updateDbInstance(editingInstance.value.id, { ...instanceForm })
    } else {
      await assetsApi.createDbInstance({ ...instanceForm })
    }
    await reload()
    closeModal()
  } catch (err) {
    modalError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    submitting.value = false
  }
}

async function removeInstance(instance: InstanceRow) {
  const confirmed = window.confirm(`确认删除实例「${instance.instance_name}」吗？`)
  if (!confirmed) return
  try {
    await assetsApi.deleteDbInstance(instance.id)
    await reload()
  } catch (err) {
    alert(err instanceof Error ? err.message : '删除失败')
  }
}

const statItems = useAssetPageMetrics(items, total, [
  assetPageMetric.total('实例总数'),
  assetPageMetric.countEquals('Oracle', (item) => item.db_type, 'Oracle'),
  assetPageMetric.countEquals('PostgreSQL', (item) => item.db_type, 'PostgreSQL'),
  assetPageMetric.countEquals('SQL Server', (item) => item.db_type, 'SQL Server'),
])

const dbTypeChart = useAssetStatBuckets(items, (item) => item.db_type)

type FilterOption = { label: string; value: string }
type FilterSelect = {
  key: string
  label: string
  value: string
  options: FilterOption[]
}

const factoryAreaOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(items.value.map((item) => item.factory_area).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部厂区', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const dbTypeOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(items.value.map((item) => item.db_type).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部数据库类型', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const nodeRoleOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(items.value.map((item) => item.node_role).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部实例角色', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const filterSelects = computed<FilterSelect[]>(() => [
  {
    key: 'factory_area',
    label: '厂区',
    value: draftFactoryArea.value,
    options: factoryAreaOptions.value,
  },
  {
    key: 'db_type',
    label: '数据库类型',
    value: draftDbType.value,
    options: dbTypeOptions.value,
  },
  {
    key: 'node_role',
    label: '实例角色',
    value: draftNodeRole.value,
    options: nodeRoleOptions.value,
  },
])

function handleDraftSelectUpdate(payload: { key: string; value: string }) {
  if (payload.key === 'factory_area') {
    draftFactoryArea.value = payload.value || 'all'
  }
  if (payload.key === 'db_type') {
    draftDbType.value = payload.value || 'all'
  }
  if (payload.key === 'node_role') {
    draftNodeRole.value = payload.value || 'all'
  }
}

function applyFilters() {
  appliedKeyword.value = draftKeyword.value
  appliedFactoryArea.value = draftFactoryArea.value
  appliedDbType.value = draftDbType.value
  appliedNodeRole.value = draftNodeRole.value
  currentPage.value = 1
}

function resetFilters() {
  draftKeyword.value = ''
  draftFactoryArea.value = 'all'
  draftDbType.value = 'all'
  draftNodeRole.value = 'all'
  appliedKeyword.value = ''
  appliedFactoryArea.value = 'all'
  appliedDbType.value = 'all'
  appliedNodeRole.value = 'all'
  currentPage.value = 1
}

const normalizedAppliedKeyword = computed(() => appliedKeyword.value.trim().toLowerCase())

const filteredItems = computed(() => {
  const keywordText = normalizedAppliedKeyword.value
  return items.value.filter((instance) => {
    const matchesKeyword =
      !keywordText ||
      [
        instance.instance_name,
        instance.server_ip,
        instance.cluster_name,
        instance.db_type,
        instance.node_role,
        instance.engine_role,
      ]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keywordText))

    const matchesFactoryArea = appliedFactoryArea.value === 'all' || instance.factory_area === appliedFactoryArea.value
    const matchesDbType = appliedDbType.value === 'all' || instance.db_type === appliedDbType.value
    const matchesNodeRole = appliedNodeRole.value === 'all' || instance.node_role === appliedNodeRole.value

    return matchesKeyword && matchesFactoryArea && matchesDbType && matchesNodeRole
  })
})

const pagedFilteredItems = computed(() => {
  if (pageSize.value === 'all') {
    return filteredItems.value
  }

  const start = (currentPage.value - 1) * pageSize.value
  return filteredItems.value.slice(start, start + pageSize.value)
})

const hasActiveFilters = computed(() => {
  return (
    normalizedAppliedKeyword.value.length > 0 ||
    appliedFactoryArea.value !== 'all' ||
    appliedDbType.value !== 'all' ||
    appliedNodeRole.value !== 'all'
  )
})

function openInstancePage(instance: InstanceRow) {
  router.push(`/assets/instances/${instance.id}`)
}

function updatePageSize(value: number | 'all') {
  pageSize.value = value === 'all' ? 'all' : Number(value)
  currentPage.value = 1
}

watch(filteredItems, (items) => {
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
