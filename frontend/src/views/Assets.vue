<template>
  <OpsPage>
    <OpsPageHeader title="业务系统" subtitle="按业务系统查看关联的集群、联系人和基础分组信息。" />

    <OpsModal
      :open="showEditor"
      :title="editingSystemId ? '编辑业务系统' : '新增业务系统'"
      :subtitle="editingSystemId ? '修改业务系统基础信息' : '创建一个新的业务系统主数据'"
      :icon="editingSystemId ? 'edit' : 'business'"
      size="lg"
      @close="cancelSystemEditing"
    >
      <form class="space-y-5" @submit.prevent="submitBusinessSystemForm">
        <div v-if="systemFormError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ systemFormError }}
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card sm:col-span-2">
            <span class="field-label">系统名称 <span class="text-red-400">*</span></span>
            <input v-model.trim="systemForm.system_name" class="field-input" type="text" placeholder="请输入系统名称" />
          </label>
          <label class="block field-card">
            <span class="field-label">业务单位</span>
            <input v-model.trim="systemForm.business_unit" class="field-input" type="text" placeholder="可选" />
          </label>
          <label class="block field-card">
            <span class="field-label">部门</span>
            <input v-model.trim="systemForm.department" class="field-input" type="text" placeholder="可选" />
          </label>
          <label class="block field-card">
            <span class="field-label">等级</span>
            <input v-model.trim="systemForm.biz_level" class="field-input" type="text" placeholder="可选" />
          </label>
          <label class="block field-card">
            <span class="field-label">服务范围</span>
            <textarea
              v-model.trim="systemForm.service_scope"
              class="field-input min-h-[80px] resize-y"
              placeholder="可选"
            ></textarea>
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">备注</span>
            <textarea
              v-model.trim="systemForm.remark"
              class="field-input min-h-[80px] resize-y"
              placeholder="可选"
            ></textarea>
          </label>
        </div>

        <div class="flex items-center justify-end gap-3 border-t border-outline-variant/40 pt-4">
          <button
            type="button"
            class="ops-secondary-button"
            @click="cancelSystemEditing"
          >
            取消
          </button>
          <button
            type="submit"
            class="ops-primary-button"
            :disabled="savingSystem"
          >
            <span class="material-symbols-outlined text-[18px]">{{ savingSystem ? 'hourglass_empty' : 'check' }}</span>
            {{ savingSystem ? '保存中...' : (editingSystemId ? '保存修改' : '确认新增') }}
          </button>
        </div>
      </form>
    </OpsModal>

    <OpsStatGrid :items="statItems" />

    <div class="rounded-lg bg-surface-container px-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0 truncate text-sm text-on-surface-variant">
          图形分布 默认收起，点击展开当前业务系统分布图
        </div>
        <button
          class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-on-surface transition-colors hover:bg-white/10"
          type="button"
          @click="systemChartsOpen = !systemChartsOpen"
        >
          {{ systemChartsOpen ? '收起' : '展开' }}
        </button>
      </div>
      <div v-if="systemChartsOpen" class="mt-4">
        <SimpleBarChart :items="businessUnitChart" :as-card="false" />
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
          @click="startCreatingSystem"
        >
          <span class="material-symbols-outlined text-[18px]">add</span>
          新增业务系统
        </button>
        </template>
    </OpsFilterBar>

    <OpsTableShell
      :loading="loading"
      :empty="!filteredSystems.length && !loading"
      :empty-state="error ? 'error' : 'empty'"
      :empty-title="error ? '加载失败' : hasActiveFilters ? '暂无匹配结果' : '暂无业务系统数据'"
      :empty-description="error || (hasActiveFilters ? '当前筛选条件没有匹配的业务系统。' : '当前没有业务系统列表数据。')"
      :total-items="filteredSystems.length"
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
            v-for="system in pagedFilteredSystems"
            :key="system.id"
            class="cursor-pointer border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
            @click="openBusinessDetail(system.id)"
          >
            <td v-for="col in visibleColumns" :key="col.key" class="whitespace-nowrap px-4 py-3">
              <template v-if="col.key === 'system_name'">
                <router-link
                  :to="`/assets/businesses/${system.id}`"
                  class="font-medium text-[#8ec5ff] hover:underline"
                  @click.stop
                >
                  {{ system.system_name }}
                </router-link>
              </template>
              <template v-else-if="col.key === 'business_unit'">{{ system.business_unit || '-' }}</template>
              <template v-else-if="col.key === 'department'">{{ system.department || '-' }}</template>
              <template v-else-if="col.key === 'biz_level'">{{ system.biz_level || '-' }}</template>
              <template v-else-if="col.key === 'status'">
                <span
                  class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium"
                  :class="getStatusBadgeClass(system.status)"
                >
                  {{ formatStatusLabel(system.status) }}
                </span>
              </template>
              <template v-else-if="col.key === 'biz_manager'">{{ getContactNameByRole(system.contacts, 'BUSINESS_MANAGER') }}</template>
              <template v-else-if="col.key === 'dba_owner'">{{ getContactNameByRole(system.contacts, 'DBA_OWNER') }}</template>
              <template v-else-if="col.key === 'clusters'">{{ system.clusters.map(item => item.cluster_code).join(', ') || '-' }}</template>
            </td>
            <td class="whitespace-nowrap px-4 py-3 text-right">
              <button
                class="ops-edit-button"
                type="button"
                @click.stop="startEditingSystem(system)"
              >
                <span class="material-symbols-outlined text-[14px]">edit</span>
                编辑
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </OpsTableShell>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { assetsApi } from '@/api/assets'
import SimpleBarChart from '@/components/SimpleBarChart.vue'
import { OpsColumnPicker, OpsFilterBar, OpsModal, OpsPage, OpsPageHeader, OpsStatGrid, OpsTableShell } from '@/components/ops'
import { assetPageMetric, useAssetPageMetrics } from '@/composables/useAssetPageMetrics'
import { useAssetStatBuckets } from '@/composables/useAssetStatBuckets'
import { useAssetArrayList } from '@/composables/useAssetArrayList'
import { useColumnVisibility } from '@/composables/useColumnVisibility'
import type { BusinessContactRow, BusinessSystemUpsertPayload, SystemRow } from '@/types/api'
import { formatStatusLabel, getStatusBadgeClass } from '@/composables/useStatusFormatters'

const SYSTEM_COLUMNS = [
  { key: 'system_name',    label: '系统' },
  { key: 'business_unit',  label: '业务单位' },
  { key: 'department',     label: '部门' },
  { key: 'biz_level',      label: '等级', defaultVisible: false },
  { key: 'status',         label: '状态' },
  { key: 'biz_manager',    label: '业务主管' },
  { key: 'dba_owner',      label: 'DBA负责人' },
  { key: 'clusters',       label: '集群' },
]
const { orderedColumns, visibleColumns, isVisible: isColVisible, toggleColumn, reorderColumn, resetColumns } = useColumnVisibility('businesses', SYSTEM_COLUMNS)

const { items: systems, loading, error, reload } = useAssetArrayList(() => assetsApi.listBusinessSystems())

const draftKeyword = ref('')
const draftBusinessUnit = ref('all')
const draftBizLevel = ref('all')
const draftStatus = ref('all')
const appliedKeyword = ref('')
const appliedBusinessUnit = ref('all')
const appliedBizLevel = ref('all')
const appliedStatus = ref('all')
const currentPage = ref(1)
const pageSize = ref<number | 'all'>(30)
const systemChartsOpen = ref(false)
const showEditor = ref(false)
const editingSystemId = ref<number | null>(null)
const savingSystem = ref(false)
const systemFormError = ref('')
const systemForm = reactive<BusinessSystemUpsertPayload>({
  system_name: '',
  business_unit: '',
  department: '',
  service_scope: '',
  biz_level: '',
  remark: '',
})
const router = useRouter()

type FilterOption = { label: string; value: string }
type FilterSelect = {
  key: string
  label: string
  value: string
  options: FilterOption[]
}

const statItems = useAssetPageMetrics(systems, () => systems.value.length, [
  assetPageMetric.total('业务总数'),
  assetPageMetric.countMatches('有关联集群', (item) => item.clusters.length > 0),
  assetPageMetric.countEquals('重要', (item) => item.biz_level, '重要'),
  assetPageMetric.countEquals('关键', (item) => item.biz_level, '關鍵'),
])

const businessUnitChart = useAssetStatBuckets(systems, (item) => item.business_unit)

const businessUnitOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(systems.value.map((item) => item.business_unit).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部业务单位', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const bizLevelOptions = computed<FilterOption[]>(() => {
  const values = Array.from(
    new Set(systems.value.map((item) => item.biz_level).filter((value): value is string => Boolean(value)))
  )
  return [
    { label: '全部重要等级', value: 'all' },
    ...values.map((value) => ({ label: value, value })),
  ]
})

const statusOptions = computed<FilterOption[]>(() => {
  return [
    { label: '全部生命周期状态', value: 'all' },
    { label: '建设中', value: 'building' },
    { label: '待上线', value: 'pending' },
    { label: '已上线', value: 'active' },
    { label: '已下线', value: 'retired' },
  ]
})

const filterSelects = computed<FilterSelect[]>(() => [
  {
    key: 'business_unit',
    label: '业务单位',
    value: draftBusinessUnit.value,
    options: businessUnitOptions.value,
  },
  {
    key: 'biz_level',
    label: '重要等级',
    value: draftBizLevel.value,
    options: bizLevelOptions.value,
  },
  {
    key: 'status',
    label: '状态',
    value: draftStatus.value,
    options: statusOptions.value,
  },
])

function handleDraftSelectUpdate(payload: { key: string; value: string }) {
  if (payload.key === 'business_unit') {
    draftBusinessUnit.value = payload.value || 'all'
  }
  if (payload.key === 'biz_level') {
    draftBizLevel.value = payload.value || 'all'
  }
  if (payload.key === 'status') {
    draftStatus.value = payload.value || 'all'
  }
}

function applyFilters() {
  appliedKeyword.value = draftKeyword.value
  appliedBusinessUnit.value = draftBusinessUnit.value
  appliedBizLevel.value = draftBizLevel.value
  appliedStatus.value = draftStatus.value
  currentPage.value = 1
}

function resetFilters() {
  draftKeyword.value = ''
  draftBusinessUnit.value = 'all'
  draftBizLevel.value = 'all'
  draftStatus.value = 'all'
  appliedKeyword.value = ''
  appliedBusinessUnit.value = 'all'
  appliedBizLevel.value = 'all'
  appliedStatus.value = 'all'
  currentPage.value = 1
}

const normalizedAppliedKeyword = computed(() => appliedKeyword.value.trim().toLowerCase())

const filteredSystems = computed(() => {
  const keywordText = normalizedAppliedKeyword.value
  return systems.value.filter((system) => {
    const matchesKeyword =
      !keywordText ||
      [system.system_name, system.business_unit, system.department, system.biz_level]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keywordText))

    const matchesBusinessUnit = appliedBusinessUnit.value === 'all' || system.business_unit === appliedBusinessUnit.value
    const matchesBizLevel = appliedBizLevel.value === 'all' || system.biz_level === appliedBizLevel.value
    const matchesStatus = appliedStatus.value === 'all' || system.status === appliedStatus.value

    return matchesKeyword && matchesBusinessUnit && matchesBizLevel && matchesStatus
  })
})

const pagedFilteredSystems = computed(() => {
  if (pageSize.value === 'all') {
    return filteredSystems.value
  }

  const start = (currentPage.value - 1) * pageSize.value
  return filteredSystems.value.slice(start, start + pageSize.value)
})

const hasActiveFilters = computed(() => {
  return (
    normalizedAppliedKeyword.value.length > 0 ||
    appliedBusinessUnit.value !== 'all' ||
    appliedBizLevel.value !== 'all' ||
    appliedStatus.value !== 'all'
  )
})

function getContactNameByRole(contacts: BusinessContactRow[], roleCode: string) {
  const matched = contacts.find((contact) => contact.contact_type === roleCode && contact.name?.trim())
  return matched?.name || '-'
}

function openBusinessDetail(id: number) {
  router.push(`/assets/businesses/${id}`)
}

function startCreatingSystem() {
  systemFormError.value = ''
  resetSystemForm()
  showEditor.value = true
}

function startEditingSystem(system: SystemRow) {
  systemFormError.value = ''
  editingSystemId.value = system.id
  systemForm.system_name = system.system_name || ''
  systemForm.business_unit = system.business_unit || ''
  systemForm.department = system.department || ''
  systemForm.service_scope = system.service_scope || ''
  systemForm.biz_level = system.biz_level || ''
  systemForm.remark = system.remark || ''
  showEditor.value = true
}

function cancelSystemEditing() {
  systemFormError.value = ''
  resetSystemForm()
}

function resetSystemForm() {
  editingSystemId.value = null
  showEditor.value = false
  systemForm.system_name = ''
  systemForm.business_unit = ''
  systemForm.department = ''
  systemForm.service_scope = ''
  systemForm.biz_level = ''
  systemForm.remark = ''
}

async function submitBusinessSystemForm() {
  savingSystem.value = true
  systemFormError.value = ''
  try {
    if (editingSystemId.value === null) {
      await assetsApi.createBusinessSystem({ ...systemForm })
    } else {
      await assetsApi.updateBusinessSystem(editingSystemId.value, { ...systemForm })
    }
    await reload()
    resetSystemForm()
  } catch (err) {
    systemFormError.value = err instanceof Error ? err.message : '保存业务系统失败'
  } finally {
    savingSystem.value = false
  }
}

function updatePageSize(value: number | 'all') {
  pageSize.value = value === 'all' ? 'all' : Number(value)
  currentPage.value = 1
}

watch(filteredSystems, (items) => {
  const effectivePageSize = pageSize.value === 'all' ? Math.max(1, items.length) : pageSize.value
  const totalPages = Math.max(1, Math.ceil(items.length / effectivePageSize))
  if (currentPage.value > totalPages) {
    currentPage.value = totalPages
  }
}, { immediate: true })

</script>
