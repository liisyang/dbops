<template>
  <OpsPage>
    <OpsPageHeader title="UI 预览 · 服务器详情" subtitle="模拟 /assets/servers/481，仅用于开发预览（Mock 数据）。" />

    <section class="mb-5 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <span class="inline-flex items-center gap-2 text-sm text-on-surface-variant">
          <span class="material-symbols-outlined text-[18px]">preview</span>
          详情页交互预览
        </span>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="ops-edit-button">
            <span class="material-symbols-outlined text-[14px]">edit</span>
            编辑
          </button>
          <button type="button" class="ops-secondary-button">
            <span class="material-symbols-outlined text-[18px]">history</span>
            审计日志
          </button>
          <button type="button" class="ops-secondary-button" @click="previewMode = 'loading'">
            <span class="material-symbols-outlined text-[18px]">hourglass_empty</span>
            加载态
          </button>
          <button type="button" class="ops-secondary-button" @click="previewMode = 'empty'">
            <span class="material-symbols-outlined text-[18px]">inbox</span>
            空态
          </button>
          <button type="button" class="ops-primary-button" @click="previewMode = 'data'">
            <span class="material-symbols-outlined text-[18px]">refresh</span>
            数据态
          </button>
        </div>
      </div>

      <OpsEntityHeader
        :title="mockServer.ip_address"
        :subtitle-parts="[mockServer.hostname, mockServer.server_code]"
        icon="dns"
        :status="mockServer.status"
        :chips="serverHeaderChips"
      />
    </section>

    <OpsStatGrid :items="statItems" />

    <OpsSectionCard title="基础信息" subtitle="服务器详情基础字段（Mock）" icon="info">
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div v-for="field in summaryFields" :key="field.label" class="field-card">
          <div class="field-label">{{ field.label }}</div>
          <div class="field-value">{{ field.value }}</div>
        </div>
      </div>
    </OpsSectionCard>

    <OpsSectionCard title="关联实例" subtitle="支持筛选、列控制、状态展示和操作按钮。" icon="hub">
      <OpsFilterBar
        :keyword="draftKeyword"
        :selects="filterSelects"
        @update:keyword="draftKeyword = $event"
        @update:select="handleDraftSelectUpdate"
        @search="applyFilters"
        @reset="resetFilters"
      >
        <template #tools>
          <OpsColumnPicker
            :columns="orderedColumns"
            :is-visible="isColVisible"
            @toggle="toggleColumn"
            @reorder="reorderColumn"
            @reset="resetColumns"
          />
        </template>
      </OpsFilterBar>

      <OpsTableShell
        :loading="previewMode === 'loading'"
        :empty="previewMode === 'empty' || !pagedRows.length"
        :empty-state="'empty'"
        :empty-title="previewMode === 'empty' ? '当前为预览空态' : '暂无匹配结果'"
        :empty-description="previewMode === 'empty' ? '点击“数据态”可恢复实例表格。' : '当前筛选条件没有匹配实例。'"
        :total-items="effectiveRows.length"
        :current-page="currentPage"
        :page-size="pageSize"
        @update:current-page="currentPage = $event"
        @update:page-size="updatePageSize"
      >
        <table class="w-full text-sm">
          <thead class="bg-surface-container text-left text-[11px] uppercase text-on-surface-variant">
            <tr>
              <th v-for="col in visibleColumns" :key="col.key" class="whitespace-nowrap px-4 py-2.5">{{ col.label }}</th>
              <th class="whitespace-nowrap px-4 py-2.5 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in pagedRows"
              :key="row.id"
              class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
            >
              <td v-for="col in visibleColumns" :key="col.key" class="whitespace-nowrap px-4 py-3">
                <template v-if="col.key === 'instance_code'">
                  <span class="font-mono">{{ row.instance_code }}</span>
                </template>
                <template v-else-if="col.key === 'instance_name'">{{ row.instance_name || '-' }}</template>
                <template v-else-if="col.key === 'db_type'">{{ row.db_type || '-' }}</template>
                <template v-else-if="col.key === 'engine_role'">{{ row.engine_role || '-' }}</template>
                <template v-else-if="col.key === 'status'">
                  <span
                    class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium"
                    :class="getStatusBadgeClass(row.status)"
                  >
                    {{ formatStatusLabel(row.status) }}
                  </span>
                </template>
                <template v-else-if="col.key === 'cluster_code'">{{ row.cluster_code || '-' }}</template>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-right">
                <div class="inline-flex items-center gap-2">
                  <button type="button" class="ops-edit-button">
                    <span class="material-symbols-outlined text-[14px]">open_in_new</span>
                    查看
                  </button>
                  <button type="button" class="ops-danger-button">
                    <span class="material-symbols-outlined text-[14px]">delete</span>
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  OpsColumnPicker,
  OpsEntityHeader,
  OpsFilterBar,
  OpsPage,
  OpsPageHeader,
  OpsSectionCard,
  OpsStatGrid,
  OpsTableShell,
} from '@/components/ops'
import { useColumnVisibility } from '@/composables/useColumnVisibility'
import { formatStatusLabel, getStatusBadgeClass } from '@/composables/useStatusFormatters'

type PreviewInstance = {
  id: number
  instance_code: string
  instance_name: string
  db_type: string
  engine_role: string
  status: string
  cluster_code: string
}

const mockServer = {
  ip_address: '10.134.181.168',
  hostname: 'dbops-app-481',
  server_code: 'SRV-00481',
  server_type: 'VM',
  deploy_type: 'KVM',
  provider: 'IDC',
  status: 'active',
  instance_count: 4,
  os: 'CentOS 7.9',
  cpu_cores: 16,
  memory_gb: 64,
  disk_gb: 500,
  factory_area: 'CN-SH',
}

const MOCK_INSTANCES: PreviewInstance[] = [
  { id: 1, instance_code: 'INS-481-01', instance_name: 'order-main', db_type: 'MySQL', engine_role: 'primary', status: 'active', cluster_code: 'CLU-481' },
  { id: 2, instance_code: 'INS-481-02', instance_name: 'order-standby', db_type: 'MySQL', engine_role: 'standby', status: 'pending', cluster_code: 'CLU-481' },
  { id: 3, instance_code: 'INS-481-03', instance_name: 'audit-main', db_type: 'PostgreSQL', engine_role: 'primary', status: 'active', cluster_code: 'CLU-713' },
  { id: 4, instance_code: 'INS-481-04', instance_name: 'legacy-report', db_type: 'Oracle', engine_role: 'standby', status: 'retired', cluster_code: 'CLU-081' },
]

const PREVIEW_COLUMNS = [
  { key: 'instance_code', label: '实例编号' },
  { key: 'instance_name', label: '实例名称' },
  { key: 'db_type', label: '数据库类型' },
  { key: 'engine_role', label: '角色' },
  { key: 'status', label: '状态' },
  { key: 'cluster_code', label: '集群' },
]

const {
  orderedColumns,
  visibleColumns,
  isVisible: isColVisible,
  toggleColumn,
  reorderColumn,
  resetColumns,
} = useColumnVisibility('ui-preview-server-detail', PREVIEW_COLUMNS)

const previewMode = ref<'data' | 'empty' | 'loading'>('data')
const currentPage = ref(1)
const pageSize = ref<number | 'all'>(30)

const draftKeyword = ref('')
const draftStatus = ref('all')
const draftDbType = ref('all')
const appliedKeyword = ref('')
const appliedStatus = ref('all')
const appliedDbType = ref('all')

const statusOptions = computed(() => {
  const values = Array.from(new Set(MOCK_INSTANCES.map((item) => item.status)))
  return [{ label: '全部状态', value: 'all' }, ...values.map((value) => ({ label: formatStatusLabel(value), value }))]
})

const dbTypeOptions = computed(() => {
  const values = Array.from(new Set(MOCK_INSTANCES.map((item) => item.db_type)))
  return [{ label: '全部数据库', value: 'all' }, ...values.map((value) => ({ label: value, value }))]
})

const filterSelects = computed(() => [
  { key: 'status', label: '状态', value: draftStatus.value, options: statusOptions.value },
  { key: 'db_type', label: '数据库', value: draftDbType.value, options: dbTypeOptions.value },
])

const filteredRows = computed(() => {
  const keyword = appliedKeyword.value.trim().toLowerCase()
  return MOCK_INSTANCES.filter((item) => {
    const matchesKeyword =
      !keyword ||
      [item.instance_code, item.instance_name, item.db_type, item.cluster_code]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keyword))
    const matchesStatus = appliedStatus.value === 'all' || item.status === appliedStatus.value
    const matchesDbType = appliedDbType.value === 'all' || item.db_type === appliedDbType.value
    return matchesKeyword && matchesStatus && matchesDbType
  })
})

const effectiveRows = computed(() => (previewMode.value === 'empty' ? [] : filteredRows.value))
const pagedRows = computed(() => {
  if (pageSize.value === 'all') return effectiveRows.value
  const start = (currentPage.value - 1) * pageSize.value
  return effectiveRows.value.slice(start, start + pageSize.value)
})

const statItems = computed(() => [
  { label: '关联实例', value: MOCK_INSTANCES.length, hint: 'Mock 关联总量', icon: 'hub', tone: 'primary' as const },
  { label: '运行中', value: MOCK_INSTANCES.filter((item) => formatStatusLabel(item.status) === '已上线').length, hint: '状态为已上线', icon: 'check_circle', tone: 'success' as const },
  { label: '待上线', value: MOCK_INSTANCES.filter((item) => formatStatusLabel(item.status) === '待上线').length, hint: '状态为待上线', icon: 'rocket_launch', tone: 'warning' as const },
  { label: '已下线', value: MOCK_INSTANCES.filter((item) => formatStatusLabel(item.status) === '已下线').length, hint: '状态为已下线', icon: 'power_settings_new', tone: 'muted' as const },
])

const summaryFields = computed(() => [
  { label: 'IP 地址', value: mockServer.ip_address },
  { label: '主机名', value: mockServer.hostname },
  { label: '操作系统', value: mockServer.os },
  { label: 'CPU', value: `${mockServer.cpu_cores} Core` },
  { label: '内存', value: `${mockServer.memory_gb} GB` },
  { label: '磁盘', value: `${mockServer.disk_gb} GB` },
  { label: '厂区', value: mockServer.factory_area },
  { label: '实例数', value: String(mockServer.instance_count) },
])

const serverHeaderChips = computed(() => [
  { icon: 'computer', label: mockServer.server_type },
  { icon: 'view_in_ar', label: mockServer.deploy_type },
  { icon: 'cloud', label: mockServer.provider },
  { icon: 'hub', label: `${mockServer.instance_count} 台实例` },
])

watch(effectiveRows, (rows) => {
  const effectivePageSize = pageSize.value === 'all' ? Math.max(1, rows.length) : pageSize.value
  const totalPages = Math.max(1, Math.ceil(rows.length / effectivePageSize))
  if (currentPage.value > totalPages) currentPage.value = totalPages
}, { immediate: true })

function handleDraftSelectUpdate(payload: { key: string; value: string }) {
  if (payload.key === 'status') draftStatus.value = payload.value || 'all'
  if (payload.key === 'db_type') draftDbType.value = payload.value || 'all'
}

function applyFilters() {
  appliedKeyword.value = draftKeyword.value
  appliedStatus.value = draftStatus.value
  appliedDbType.value = draftDbType.value
  currentPage.value = 1
}

function resetFilters() {
  draftKeyword.value = ''
  draftStatus.value = 'all'
  draftDbType.value = 'all'
  appliedKeyword.value = ''
  appliedStatus.value = 'all'
  appliedDbType.value = 'all'
  currentPage.value = 1
}

function updatePageSize(value: number | 'all') {
  pageSize.value = value === 'all' ? 'all' : Number(value)
  currentPage.value = 1
}
</script>
