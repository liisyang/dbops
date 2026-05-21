<template>
  <OpsPage>
    <OpsPageHeader v-if="isListView || isCreateView" :title="headerTitle" :subtitle="headerSubtitle" />

    <template v-else-if="detail">
      <section class="mb-6 border-b border-outline-variant/40 pb-5">
        <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div class="space-y-4">
            <router-link
              to="/assets/servers"
              class="inline-flex items-center gap-2 text-sm text-on-surface-variant transition-colors hover:text-on-surface"
            >
              <span class="material-symbols-outlined text-[18px]">arrow_back</span>
              返回列表
            </router-link>

            <div class="flex flex-wrap gap-2">
              <span class="rounded-md border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-on-surface">
                {{ detail.server_type || '主机' }}
              </span>
              <span class="rounded-md border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-on-surface">
                {{ detail.deploy_type || '部署类型' }}
              </span>
              <span class="rounded-md border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-on-surface">
                {{ detail.provider || 'Provider' }}
              </span>
            </div>

            <div>
              <div class="flex flex-wrap items-center gap-3">
                <h1 class="text-4xl font-semibold tracking-tight text-on-surface">{{ detail.ip_address }}</h1>
                <span class="rounded-md border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-200">
                  {{ detail.instance_count }} 台实例
                </span>
              </div>
              <div class="mt-2 text-sm text-on-surface-variant">
                {{ detail.hostname || '-' }} / {{ detail.server_code || '-' }}
              </div>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2 xl:pt-10">
            <button
              v-if="!editing"
              class="ops-primary-button"
              type="button"
              @click="startEditing"
            >
              <span class="material-symbols-outlined text-[18px]">edit</span>
              编辑
            </button>
            <button
              v-else
              class="ops-secondary-button"
              type="button"
              @click="cancelEditing"
            >
              <span class="material-symbols-outlined text-[18px]">close</span>
              取消编辑
            </button>
            <button
              class="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/8 px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-white/12"
              type="button"
              @click="router.push('/audit/operations')"
            >
              <span class="material-symbols-outlined text-[18px]">history</span>
              审计日志
            </button>
          </div>
        </div>

        <div class="mt-6 flex items-center gap-8 border-t border-white/8 pt-4 text-sm font-medium">
          <span class="border-b-2 border-sky-400 pb-4 text-on-surface">概览</span>
        </div>
      </section>
    </template>

    <template v-if="isListView">
      <OpsStatGrid :items="heroStats" />

      <div class="rounded-lg bg-surface-container px-3 py-2.5">
        <div class="flex items-center justify-between gap-2">
          <div class="min-w-0 truncate text-xs text-on-surface-variant">
            图形分布 默认收起，点击展开当前服务器分布图
          </div>
          <button
            class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-on-surface transition-colors hover:bg-white/10"
            type="button"
            @click="serverChartsOpen = !serverChartsOpen"
          >
            {{ serverChartsOpen ? '收起' : '展开' }}
          </button>
        </div>
        <div v-if="serverChartsOpen" class="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.9fr)_minmax(320px,0.9fr)]">
          <div class="rounded-lg bg-surface-container-high p-3">
            <div class="text-xs uppercase tracking-wide text-on-surface-variant">按厂区分布 (Top 8)</div>
            <SimpleBarChart class="mt-2" :items="factoryChart" :as-card="false" />
          </div>
          <div class="rounded-lg bg-surface-container-high p-3">
            <div class="text-xs uppercase tracking-wide text-on-surface-variant">操作系统分布</div>
            <DistributionDonutChart class="mt-2" :items="osChart" center-label="OS" />
          </div>
        </div>
      </div>

      <OpsFilterBar
        :keyword="draftKeyword"
        :selects="filterSelects"
        compact
        attached
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
            class="ops-primary-button"
            type="button"
            @click="openCreateServerPage"
          >
            <span class="material-symbols-outlined text-[18px]">add</span>
            新增服务器
          </button>
        </template>
      </OpsFilterBar>

      <OpsTableShell
        :loading="loading"
        :empty="!filteredItems.length && !loading"
        :empty-state="error ? 'error' : 'empty'"
        :empty-title="error ? '加载失败' : hasActiveFilters ? '暂无匹配结果' : '暂无服务器数据'"
        :empty-description="error || (hasActiveFilters ? '当前筛选条件没有匹配的服务器。' : '当前没有服务器列表数据。')"
        :total-items="filteredItems.length"
        :current-page="currentPage"
        :page-size="pageSize"
        @update:current-page="currentPage = $event"
        @update:page-size="updatePageSize"
      >
        <table class="w-full text-sm">
          <thead class="bg-surface-container text-left text-[11px] uppercase text-on-surface-variant">
            <tr>
              <th v-for="col in visibleColumns" :key="col.key" class="whitespace-nowrap px-4 py-1.5">{{ col.label }}</th>
              <th class="whitespace-nowrap px-4 py-1.5 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="server in pagedFilteredItems"
              :key="server.id"
              class="cursor-pointer border-t border-outline-variant/40 transition-colors hover:bg-surface-container-high"
              @click="openServerPage(server)"
            >
              <td v-for="col in visibleColumns" :key="col.key" :class="col.key === 'ip_address' ? 'whitespace-nowrap px-4 py-2 font-mono' : 'whitespace-nowrap px-4 py-2'">
                <template v-if="col.key === 'ip_address'">{{ server.ip_address }}</template>
                <template v-else-if="col.key === 'hostname'">{{ server.hostname || '-' }}</template>
                <template v-else-if="col.key === 'os'">
                  <div class="flex items-center gap-1.5">
                    <span v-if="server.os_name" class="material-symbols-outlined shrink-0 text-on-surface-variant" style="font-size:16px">dns</span>
                    <span>{{ [server.os_name, server.os_version].filter(Boolean).join(' ') || '-' }}</span>
                  </div>
                </template>
                <template v-else-if="col.key === 'deploy_type'">{{ server.deploy_type || '-' }}</template>
                <template v-else-if="col.key === 'cpu_cores'">{{ server.cpu_cores ?? '-' }}</template>
                <template v-else-if="col.key === 'memory_gb'">{{ server.memory_gb ?? '-' }}</template>
                <template v-else-if="col.key === 'disk_gb'">{{ server.disk_gb ?? '-' }}</template>
                <template v-else-if="col.key === 'provider'">{{ server.provider || '-' }}</template>
                <template v-else-if="col.key === 'country'">{{ server.country || '-' }}</template>
                <template v-else-if="col.key === 'factory_area'">{{ server.factory_area || '-' }}</template>
                <template v-else-if="col.key === 'room_location'">{{ server.room_location || '-' }}</template>
              </td>
              <td class="whitespace-nowrap px-4 py-2 text-right">
                <button
                  class="ops-edit-button"
                  type="button"
                  @click.stop="openServerPage(server, true)"
                >
                  <span class="material-symbols-outlined text-[14px]">edit</span>
                  编辑
                </button>
                <button
                  class="ops-danger-button"
                  type="button"
                  @click.stop="handleDeleteServer(server)"
                >
                  <span class="material-symbols-outlined text-[14px]">delete</span>
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
    </template>

    <template v-else>
      <OpsSectionCard v-if="detailLoading" title="服务器详情" subtitle="正在加载服务器信息">
        <OpsEmptyState state="loading" title="正在加载服务器详情" description="请稍候。" />
      </OpsSectionCard>

      <OpsSectionCard v-else-if="detailError" title="服务器详情" subtitle="加载失败">
        <OpsEmptyState state="error" title="服务器详情加载失败" :description="detailError" />
      </OpsSectionCard>

      <template v-else-if="detail">
        <section class="space-y-4">
          <OpsSectionCard id="server-summary" title="基礎信息" icon="info">
            <div v-if="!editing" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div
                v-for="field in serverDisplayFields"
                :key="field.label"
                class="field-card"
              >
                <div class="field-label">{{ field.label }}</div>
                <div class="field-value">{{ field.value }}</div>
              </div>
            </div>

            <form v-else class="space-y-4" @submit.prevent="submitServerForm">
              <div v-if="serverFormError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {{ serverFormError }}
              </div>
              <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <label
                  v-for="field in serverFormFields"
                  :key="String(field.key)"
                  class="block field-card"
                >
                  <span class="field-label">{{ field.label }}</span>
                  <input
                    v-model.trim="serverForm[field.key]"
                    class="field-input"
                    :type="field.inputType"
                  />
                </label>
              </div>
              <div class="flex items-center justify-end gap-3 pt-2">
                <button class="ops-secondary-button" type="button" @click="cancelEditing">
                  取消
                </button>
                <button class="ops-primary-button" type="submit" :disabled="serverFormSaving">
                  {{ serverFormSaving ? '保存中...' : '保存' }}
                </button>
              </div>
            </form>
          </OpsSectionCard>

          <OpsSectionCard title="当前关联实例" subtitle="展示当前服务器挂载的实例列表。" icon="hub">
            <div v-if="detail.instances.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div
                v-for="instance in detail.instances"
                :key="instance.id"
                class="field-card"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="field-label">实例编号</div>
                    <div class="field-value font-mono">{{ instance.instance_code || '-' }}</div>
                  </div>
                  <span class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                    {{ instance.node_role || instance.engine_role || '-' }}
                  </span>
                </div>
                <div class="mt-2 text-sm text-slate-100">
                  {{ instance.instance_name || '-' }}
                </div>
                <div class="mt-3 grid gap-2 text-xs text-slate-400">
                  <div>数据库类型：{{ instance.db_type || '-' }}</div>
                  <div>Cluster：{{ instance.cluster_code || '-' }}</div>
                  <div>服务器 IP：{{ instance.server_ip || '-' }}</div>
                </div>
              </div>
            </div>

            <OpsEmptyState
              v-else
              state="empty"
              title="暂无关联实例"
              description="当前服务器没有返回实例关系。"
            />
          </OpsSectionCard>
        </section>
      </template>
      <template v-else-if="isCreateView">
      <OpsSectionCard title="新增服务器" subtitle="填写基础信息后保存" icon="add_circle">
          <form class="space-y-4" @submit.prevent="submitServerForm">
            <div v-if="serverFormError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {{ serverFormError }}
            </div>
            <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <label
                v-for="field in serverFormFields"
                :key="String(field.key)"
                class="block field-card"
              >
                <span class="field-label">{{ field.label }}</span>
                <input
                  v-model.trim="serverForm[field.key]"
                  class="field-input"
                  :type="field.inputType"
                />
              </label>
            </div>
            <div class="flex items-center justify-end gap-3 pt-2">
              <button class="ops-secondary-button" type="button" @click="router.push('/assets/servers')">
                取消
              </button>
              <button class="ops-primary-button" type="submit" :disabled="serverFormSaving">
                <span class="material-symbols-outlined text-[18px]">{{ serverFormSaving ? 'hourglass_empty' : 'check' }}</span>
                {{ serverFormSaving ? '保存中...' : '确认新增' }}
              </button>
            </div>
          </form>
        </OpsSectionCard>
      </template>
    </template>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { assetsApi } from '@/api/assets'
import DistributionDonutChart from '@/components/DistributionDonutChart.vue'
import SimpleBarChart from '@/components/SimpleBarChart.vue'
import { OpsColumnPicker, OpsEmptyState, OpsFilterBar, OpsPage, OpsPageHeader, OpsSectionCard, OpsStatGrid, OpsTableShell } from '@/components/ops'
import { assetPageMetric, useAssetPageMetrics } from '@/composables/useAssetPageMetrics'
import { useAssetStatBuckets } from '@/composables/useAssetStatBuckets'
import { useColumnVisibility } from '@/composables/useColumnVisibility'
import { usePagedAssetList } from '@/composables/usePagedAssetList'
import type { ServerDetail, ServerRow, ServerUpsertPayload } from '@/types/api'

const route = useRoute()
const router = useRouter()
const { items, total, loading, error, reload } = usePagedAssetList((params) => assetsApi.listServers(params))

const SERVER_COLUMNS = [
  { key: 'ip_address',    label: 'IP' },
  { key: 'hostname',      label: '主机名' },
  { key: 'os',            label: 'OS' },
  { key: 'cpu_cores',     label: 'CPU', defaultVisible: false },
  { key: 'memory_gb',     label: 'MEM(GB)', defaultVisible: false },
  { key: 'disk_gb',       label: 'DISK(GB)', defaultVisible: false },
  { key: 'deploy_type',   label: '部署类型' },
  { key: 'provider',      label: 'Provider' },
  { key: 'country',       label: '国家', defaultVisible: false },
  { key: 'factory_area',  label: '厂区' },
  { key: 'room_location', label: '机房位置', defaultVisible: false },
]
const { orderedColumns, visibleColumns, isVisible: isColVisible, toggleColumn, reorderColumn, resetColumns } = useColumnVisibility('servers', SERVER_COLUMNS)

const draftKeyword = ref('')
const draftFactoryArea = ref('all')
const draftServerType = ref('all')
const appliedKeyword = ref('')
const appliedFactoryArea = ref('all')
const appliedServerType = ref('all')
const currentPage = ref(1)
const pageSize = ref<number | 'all'>(30)
const serverChartsOpen = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detail = ref<ServerDetail | null>(null)
const editing = ref(false)
const serverFormSaving = ref(false)
const serverFormError = ref('')
const serverId = computed(() => String(route.params.id || '').trim())
const isCreateView = computed(() => route.name === 'AssetServerCreate')
const isListView = computed(() => route.name === 'AssetServers')
const serverForm = ref<ServerUpsertPayload>(createEmptyServerForm())

type FilterOption = { label: string; value: string }
type FilterSelect = {
  key: string
  label: string
  value: string
  options: FilterOption[]
}

const statItems = useAssetPageMetrics(items, total, [
  assetPageMetric.total('总服务器', '资产全量'),
  assetPageMetric.countEquals('VM', (item) => item.server_type, 'VM', '虚拟化主机'),
  assetPageMetric.countEquals('物理机', (item) => item.server_type, '物理', '独立宿主机'),
  assetPageMetric.countEquals('空载服务器', (item) => item.instance_count, 0, '当前无挂载实例'),
])

const headerTitle = computed(() => {
  if (isListView.value) return '服务器'
  if (isCreateView.value) return '新增服务器'
  if (detail.value) return editing.value ? '编辑服务器' : detail.value.ip_address
  return '服务器详情'
})

const headerSubtitle = computed(() => {
  if (isListView.value) return '查看主机、站点和基础资源信息。'
  if (isCreateView.value) return '填写基础服务器信息后保存。'
  if (detail.value) return [detail.value.hostname || '-', detail.value.server_code || '-'].join(' / ')
  return '查看和编辑单台服务器信息。'
})

const heroStats = computed(() => [
  { ...statItems.value[0], icon: 'dns', tone: 'primary' as const },
  { ...statItems.value[1], icon: 'cloud', tone: 'success' as const },
  { ...statItems.value[2], icon: 'computer', tone: 'primary' as const },
  { ...statItems.value[3], icon: 'bedtime', tone: 'muted' as const },
])

const factoryOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(items.value.map((item) => item.factory_area).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部厂区', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const serverTypeOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(items.value.map((item) => item.server_type).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部主机属性', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const filterSelects = computed<FilterSelect[]>(() => [
  {
    key: 'factory_area',
    label: '厂区',
    value: draftFactoryArea.value,
    options: factoryOptions.value,
  },
  {
    key: 'server_type',
    label: '主机属性',
    value: draftServerType.value,
    options: serverTypeOptions.value,
  },
])

function handleDraftSelectUpdate(payload: { key: string; value: string }) {
  if (payload.key === 'factory_area') {
    draftFactoryArea.value = payload.value || 'all'
  }
  if (payload.key === 'server_type') {
    draftServerType.value = payload.value || 'all'
  }
}

function applyFilters() {
  appliedKeyword.value = draftKeyword.value
  appliedFactoryArea.value = draftFactoryArea.value
  appliedServerType.value = draftServerType.value
  currentPage.value = 1
}

function resetFilters() {
  draftKeyword.value = ''
  draftFactoryArea.value = 'all'
  draftServerType.value = 'all'
  appliedKeyword.value = ''
  appliedFactoryArea.value = 'all'
  appliedServerType.value = 'all'
  currentPage.value = 1
}

const normalizedAppliedKeyword = computed(() => appliedKeyword.value.trim().toLowerCase())

const filteredItems = computed(() => {
  const keywordText = normalizedAppliedKeyword.value
  return items.value.filter((server) => {
    const matchesKeyword =
      !keywordText ||
      [
        server.ip_address,
        server.hostname,
        server.os_name,
        server.os_version,
        server.deploy_type,
        server.provider,
        server.factory_area,
        server.server_type,
      ]
        .filter(Boolean)
      .some((field) => String(field).toLowerCase().includes(keywordText))

    const matchesFactoryArea = appliedFactoryArea.value === 'all' || server.factory_area === appliedFactoryArea.value
    const matchesServerType = appliedServerType.value === 'all' || server.server_type === appliedServerType.value

    return matchesKeyword && matchesFactoryArea && matchesServerType
  })
})

const pagedFilteredItems = computed(() => {
  if (pageSize.value === 'all') {
    return filteredItems.value
  }

  const start = (currentPage.value - 1) * pageSize.value
  return filteredItems.value.slice(start, start + pageSize.value)
})

const factoryChart = useAssetStatBuckets(items, (item) => item.factory_area)
const osChart = useAssetStatBuckets(items, (item) => item.os_name, { emptyLabel: 'Other' })

const hasActiveFilters = computed(() => {
  return (
    normalizedAppliedKeyword.value.length > 0 ||
    appliedFactoryArea.value !== 'all' ||
    appliedServerType.value !== 'all'
  )
})

function formatServerValue(value: unknown) {
  return value === null || value === undefined || value === '' ? '-' : String(value)
}

type DetailField = {
  label: string
  value: string
}

type FormField = {
  label: string
  key: keyof ServerUpsertPayload
  inputType: 'text' | 'number'
}

const serverFormFields: FormField[] = [
  { label: 'IP', key: 'ip', inputType: 'text' },
  { label: '主机名', key: 'hostname', inputType: 'text' },
  { label: 'DNS 名称', key: 'dns_name', inputType: 'text' },
  { label: '主机属性', key: 'host_type', inputType: 'text' },
  { label: 'CPU 核数', key: 'cpu_cores', inputType: 'number' },
  { label: '业务组', key: 'business_group', inputType: 'text' },
  { label: '内存 GB', key: 'memory_gb', inputType: 'number' },
  { label: '磁盘 GB', key: 'disk_gb', inputType: 'number' },
  { label: '厂区', key: 'factory', inputType: 'text' },
  { label: '机房位置', key: 'room_location', inputType: 'text' },
  { label: 'OS 类型', key: 'os_type', inputType: 'text' },
  { label: 'OS 版本', key: 'os_version', inputType: 'text' },
]

const baseInfoFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return serverFormFields.map((field) => ({
    label: field.label,
    value: getServerDetailFieldValue(field.key),
  }))
})

const serverDisplayFields = computed<DetailField[]>(() => baseInfoFields.value)

function getServerDetailFieldValue(key: keyof ServerUpsertPayload) {
  if (!detail.value) return '-'

  switch (key) {
    case 'ip':
      return detail.value.ip_address || '-'
    case 'hostname':
      return detail.value.hostname || '-'
    case 'dns_name':
      return '-'
    case 'host_type':
      return detail.value.server_type || '-'
    case 'cpu_cores':
      return formatServerValue(detail.value.cpu_cores)
    case 'business_group':
      return formatServerValue(detail.value.business_group)
    case 'memory_gb':
      return formatServerValue(detail.value.memory_gb)
    case 'disk_gb':
      return formatServerValue(detail.value.disk_gb)
    case 'factory':
      return [detail.value.country, detail.value.factory_area].filter(Boolean).join(' / ') || '-'
    case 'machine_room':
    case 'room_location':
      return formatServerValue(detail.value.room_location)
    case 'os_type':
      return detail.value.os_name || '-'
    case 'os_version':
      return detail.value.os_version || '-'
    case 'status':
      return 'active'
    default:
      return '-'
  }
}

function createEmptyServerForm(): ServerUpsertPayload {
  return {
    ip: '',
    hostname: '',
    dns_name: '',
    host_type: '',
    cpu_cores: null,
    business_group: '',
    memory_gb: null,
    disk_gb: null,
    factory: '',
    machine_room: '',
    room_location: '',
    os_type: '',
    os_version: '',
    status: 'active',
  }
}

function trimToNull(value: unknown) {
  if (value === null || value === undefined) return null
  const normalized = String(value).trim()
  return normalized.length ? normalized : null
}

function numberOrNull(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function openCreateServerPage() {
  router.push({ name: 'AssetServerCreate' })
}

function openServerPage(server: ServerRow, edit = false) {
  if (edit) {
    router.push(`/assets/servers/${server.id}?mode=edit`)
    return
  }
  router.push(`/assets/servers/${server.id}`)
}

function normalizeServerPayload(): ServerUpsertPayload {
  return {
    ip: serverForm.value.ip.trim(),
    hostname: trimToNull(serverForm.value.hostname),
    dns_name: trimToNull(serverForm.value.dns_name),
    host_type: trimToNull(serverForm.value.host_type),
    cpu_cores: numberOrNull(serverForm.value.cpu_cores),
    business_group: trimToNull(serverForm.value.business_group),
    memory_gb: numberOrNull(serverForm.value.memory_gb),
    disk_gb: numberOrNull(serverForm.value.disk_gb),
    factory: trimToNull(serverForm.value.factory),
    machine_room: trimToNull(serverForm.value.room_location),
    room_location: trimToNull(serverForm.value.room_location),
    os_type: trimToNull(serverForm.value.os_type),
    os_version: trimToNull(serverForm.value.os_version),
    status: trimToNull(serverForm.value.status),
  }
}

async function refreshServers() {
  if (isListView.value) {
    await reload()
    return
  }
  await loadDetail()
}

async function submitServerForm() {
  serverFormError.value = ''
  const payload = normalizeServerPayload()
  if (!payload.ip) {
    serverFormError.value = 'IP地址不能为空'
    return
  }

  serverFormSaving.value = true
  try {
    if (isCreateView.value) {
      await assetsApi.createServer(payload)
      await router.push('/assets/servers')
    } else if (detail.value) {
      await assetsApi.updateServer(detail.value.id, payload)
      editing.value = false
    }
    await refreshServers()
  } catch (error: any) {
    serverFormError.value = error?.response?.data?.detail || error?.response?.data?.message || error?.message || '保存失败'
  } finally {
    serverFormSaving.value = false
  }
}

async function handleDeleteServer(server: ServerRow) {
  if (!window.confirm(`确认删除服务器 ${server.ip_address} 吗？`)) {
    return
  }

  await assetsApi.deleteServer(server.id)
  await refreshServers()
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

watch(serverId, () => {
  if (isListView.value) {
    editing.value = false
    detail.value = null
    detailError.value = ''
    return
  }
  if (isCreateView.value) {
    editing.value = true
    detail.value = null
    detailError.value = ''
    serverForm.value = createEmptyServerForm()
    return
  }
  loadDetail()
}, { immediate: true })

function startEditing() {
  if (!detail.value) return
  editing.value = true
  serverFormError.value = ''
  serverForm.value = {
    ip: detail.value.ip_address || '',
    hostname: detail.value.hostname || '',
    dns_name: '',
    host_type: detail.value.server_type || '',
    cpu_cores: detail.value.cpu_cores ?? null,
    business_group: detail.value.business_group || '',
    memory_gb: detail.value.memory_gb ?? null,
    disk_gb: detail.value.disk_gb ?? null,
    factory: detail.value.factory_area || '',
    machine_room: detail.value.room_location || '',
    room_location: detail.value.room_location || '',
    os_type: detail.value.os_name || '',
    os_version: detail.value.os_version || '',
    status: 'active',
  }
}

function cancelEditing() {
  editing.value = false
  serverFormError.value = ''
}

async function loadDetail() {
  const id = Number(serverId.value)
  detailLoading.value = true
  detailError.value = ''
  detail.value = null

  if (!Number.isFinite(id)) {
    detailError.value = '缺少服务器 ID。'
    detailLoading.value = false
    return
  }

  try {
    detail.value = await assetsApi.getServer(id)
    if (route.query.mode === 'edit') {
      startEditing()
    }
  } catch (err: any) {
    detailError.value = err?.response?.data?.detail || err?.message || '加载失败'
  } finally {
    detailLoading.value = false
  }
}
</script>


