<template>
  <OpsPage>
    <OpsPageHeader title="巡检任务" subtitle="创建 inspection 批次任务并跟踪执行状态。" icon="playlist_add_check" />

    <OpsSectionCard title="新建巡检任务" class="mb-6">
      <div class="space-y-4">
        <div class="grid gap-3 sm:grid-cols-3">
          <label class="block field-card sm:col-span-2">
            <span class="field-label">任务名称</span>
            <input v-model.trim="form.task_name" class="field-input" placeholder="例如：每日基础巡检-生产区" />
          </label>
          <label class="block field-card">
            <span class="field-label">目标范围</span>
            <select v-model="form.target_scope" class="field-input">
              <option value="db_instance">db_instance</option>
              <option value="server">server</option>
            </select>
          </label>
        </div>

        <OpsInstancePicker v-model="selectedAssetIds" />

        <label v-if="form.target_scope === 'db_instance'" class="block field-card">
          <span class="field-label">DB 类型</span>
          <select v-model="dbTypeFilter" class="field-input">
            <option value="">全部类型</option>
            <option v-for="dt in dbTypes" :key="dt.type_code" :value="dt.type_code">
              {{ dt.name }} ({{ dt.type_code }})
            </option>
          </select>
        </label>

        <div class="field-card">
          <div class="field-label">巡检项</div>
          <div class="space-y-4">
            <div v-for="(group, groupKey) in groupedItems" :key="groupKey" class="border border-outline-variant/30 rounded-xl p-3">
              <label class="flex items-center gap-2 mb-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  :checked="isGroupSelected(groupKey as string)"
                  :indeterminate.prop="isGroupIndeterminate(groupKey as string)"
                  @change="toggleGroup(groupKey as string)"
                  class="h-4 w-4"
                />
                <span class="text-sm font-medium">{{ groupKey }}</span>
                <span class="text-xs text-on-surface-variant">({{ group.items.length }} 项)</span>
              </label>
              <div class="flex flex-wrap gap-2 ml-6">
                <label
                  v-for="item in group.items"
                  :key="item.item_code"
                  class="flex items-center gap-2 rounded-lg border border-outline-variant/30 bg-surface-container-high px-3 py-2 cursor-pointer hover:bg-surface-container-highest transition-colors"
                >
                  <input v-model="form.item_codes" type="checkbox" :value="item.item_code" class="h-3.5 w-3.5" />
                  <span class="text-xs">{{ item.item_name }} ({{ item.item_code }})</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-3">
          <label class="block field-card">
            <span class="field-label">超时（秒）</span>
            <input v-model.number="form.timeout_seconds" type="number" min="1" max="300" class="field-input" />
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

        <button class="ops-primary-button" :disabled="creating" @click="submitTask">
          <span class="material-symbols-outlined text-[18px]">{{ creating ? 'hourglass_empty' : 'rocket_launch' }}</span>
          {{ creating ? '提交中...' : '启动巡检任务' }}
        </button>

        <div v-if="createMessage" class="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{{ createMessage }}</div>
        <div v-if="createError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{{ createError }}</div>
      </div>
    </OpsSectionCard>

    <OpsConfirmDialog
      :open="fleetScanConfirmOpen"
      title="确认全量巡检"
      message="未指定资产 ID 且未指定 DB 类型，本次任务将巡检该范围下的所有资产，可能产生大量 dispatch。是否继续？"
      confirm-label="确认启动"
      @confirm="confirmFleetScan"
      @close="fleetScanConfirmOpen = false"
    />

    <OpsSectionCard title="任务列表">
      <div class="mb-4 flex justify-end">
        <button type="button" class="ops-secondary-button" @click="loadTasks">
          <span class="material-symbols-outlined text-[18px]">refresh</span>
          刷新
        </button>
      </div>
      <OpsTableShell :loading="loading" :empty="!tasks.length && !loading">
        <table class="w-full text-sm">
          <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
            <tr>
              <th class="whitespace-nowrap px-4 py-3">任务编码</th>
              <th class="whitespace-nowrap px-4 py-3">任务名称</th>
              <th class="whitespace-nowrap px-4 py-3">范围</th>
              <th class="whitespace-nowrap px-4 py-3">状态</th>
              <th class="whitespace-nowrap px-4 py-3">报告</th>
              <th class="whitespace-nowrap px-4 py-3">资产数</th>
              <th class="whitespace-nowrap px-4 py-3">检查项</th>
              <th class="whitespace-nowrap px-4 py-3">批次ID</th>
              <th class="whitespace-nowrap px-4 py-3">创建时间</th>
              <th class="whitespace-nowrap px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="task in tasks" :key="task.id" class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high">
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ task.task_code }}</td>
              <td class="whitespace-nowrap px-4 py-3">{{ task.task_name }}</td>
              <td class="whitespace-nowrap px-4 py-3">{{ task.target_scope }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getInspectionStatusClass(task.status)">
                  {{ task.status }}
                </span>
              </td>
              <td class="whitespace-nowrap px-4 py-3">
                <span v-if="task.health_level" class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="getHealthClass(task.health_level)">
                  {{ task.health_level }}
                </span>
                <span v-else-if="task.report_status" class="text-xs text-on-surface-variant">{{ task.report_status }}</span>
                <span v-else class="text-xs text-on-surface-variant">-</span>
              </td>
              <td class="whitespace-nowrap px-4 py-3">{{ getTaskAssetCount(task) }}</td>
              <td class="px-4 py-3 text-xs">{{ (task.item_codes || []).join(', ') || '-' }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ task.batch_run_id || '-' }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">{{ formatTime(task.created_at) }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs">
                <button
                  v-if="task.report_id"
                  type="button"
                  class="ops-secondary-button !px-2 !py-1"
                  @click="$router.push(`/inspection/reports/${task.report_id}`)"
                >
                  <span class="material-symbols-outlined text-[16px]">assessment</span>
                  报告
                </button>
                <span v-else class="text-xs text-on-surface-variant">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </OpsTableShell>
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import OpsConfirmDialog from '@/components/ops/OpsConfirmDialog.vue'
import OpsInstancePicker from '@/components/ops/OpsInstancePicker.vue'
import { assetsApi } from '@/api/assets'
import type { InspectionItemRow, InspectionTaskCreatePayload, InspectionTaskRow, DbTypeRow } from '@/types/api'
import { formatInTz } from '@/utils/timezone'
import { getInspectionStatusClass } from '@/composables/useStatusFormatters'

const loading = ref(false)
const creating = ref(false)
const createMessage = ref('')
const createError = ref('')
const items = ref<InspectionItemRow[]>([])
const tasks = ref<InspectionTaskRow[]>([])
const dbTypes = ref<DbTypeRow[]>([])
const selectedAssetIds = ref<number[]>([])
const dbTypeFilter = ref('')
const fleetScanConfirmOpen = ref(false)

const form = reactive<InspectionTaskCreatePayload>({
  task_name: '',
  target_scope: 'db_instance',
  asset_ids: [],
  item_codes: [],
  include_related_server: true,
  max_items_per_dispatch: 100,
  timeout_seconds: 30,
})

const selectableItems = computed(() =>
  items.value.filter((item) => {
    if (!item.enabled || item.target_scope !== form.target_scope) return false
    if (!dbTypeFilter.value) return true
    const itemDb = (item as any).db_type_code || null
    // show items matching the DB type OR items without a specific DB type (batch verify items)
    if (!itemDb) return true
    return itemDb.toUpperCase() === dbTypeFilter.value.toUpperCase()
  })
)

interface ItemGroup {
  items: InspectionItemRow[]
}

const groupedItems = computed(() => {
  const groups: Record<string, ItemGroup> = {}
  for (const item of selectableItems.value) {
    const key = item.inspection_type || '未分类'
    if (!groups[key]) groups[key] = { items: [] }
    groups[key].items.push(item)
  }
  return groups
})

function isGroupSelected(groupKey: string): boolean {
  const group = groupedItems.value[groupKey]
  if (!group) return false
  return group.items.length > 0 && group.items.every((item) => form.item_codes.includes(item.item_code))
}

function isGroupIndeterminate(groupKey: string): boolean {
  const group = groupedItems.value[groupKey]
  if (!group) return false
  const selected = group.items.filter((item) => form.item_codes.includes(item.item_code))
  return selected.length > 0 && selected.length < group.items.length
}

function toggleGroup(groupKey: string): void {
  const group = groupedItems.value[groupKey]
  if (!group) return
  const allSelected = group.items.every((item) => form.item_codes.includes(item.item_code))
  if (allSelected) {
    form.item_codes = form.item_codes.filter((code) => !group.items.some((item) => item.item_code === code))
  } else {
    for (const item of group.items) {
      if (!form.item_codes.includes(item.item_code)) {
        form.item_codes.push(item.item_code)
      }
    }
  }
}

function getTaskAssetCount(task: InspectionTaskRow): number | string {
  const fromIds = (task.asset_ids || []).length
  if (fromIds > 0) return fromIds
  const batch = (task as any).request_payload?.batch_result
  return batch?.total_asset_count ?? 0
}

function formatTime(value: string | null | undefined): string {
  return value ? formatInTz(value) : '-'
}

function getHealthClass(level: string | null | undefined): string {
  const l = (level || '').toLowerCase()
  if (l === 'critical') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (l === 'warning') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (l === 'healthy') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

// I12: switching target_scope changes the selectable item pool; the user's
// previous selections would all be silently filtered out, so clear them.
watch(
  () => form.target_scope,
  () => {
    form.item_codes = []
  }
)

async function loadItems() {
  items.value = await assetsApi.listInspectionItems({ enabled: true })
}

async function loadTasks() {
  loading.value = true
  try {
    tasks.value = await assetsApi.listInspectionTasks({ limit: 100 })
  } finally {
    loading.value = false
  }
}

async function submitTask() {
  createError.value = ''
  createMessage.value = ''

  if (!form.task_name) {
    createError.value = '任务名称不能为空'
    return
  }
  if (!form.item_codes.length) {
    createError.value = '至少选择一个巡检项'
    return
  }

  const ids = selectedAssetIds.value
  const isFleetScan = ids.length === 0 && !dbTypeFilter.value
  if (isFleetScan) {
    fleetScanConfirmOpen.value = true
    return
  }
  await doCreateTask(ids, false)
}

async function doCreateTask(assetIds: number[], confirmFleetScan: boolean) {
  creating.value = true
  try {
    const payload: InspectionTaskCreatePayload = {
      ...form,
      asset_ids: assetIds.length ? assetIds : undefined,
      db_type_code: !assetIds.length && dbTypeFilter.value ? dbTypeFilter.value : undefined,
      confirm_fleet_scan: confirmFleetScan,
      item_codes: Array.from(new Set(form.item_codes)),
    }
    const result = await assetsApi.createInspectionTask(payload)
    createMessage.value = `任务已创建: ${result.task_code}（batch_run_id=${result.batch_run_id}）`
    form.task_name = ''
    form.item_codes = []
    selectedAssetIds.value = []
    dbTypeFilter.value = ''
    await loadTasks()
  } catch (error: any) {
    createError.value = error?.response?.data?.detail || error?.message || '创建任务失败'
  } finally {
    creating.value = false
  }
}

async function confirmFleetScan() {
  fleetScanConfirmOpen.value = false
  await doCreateTask(selectedAssetIds.value, true)
}

async function loadDbTypes() {
  dbTypes.value = await assetsApi.listDbTypes()
}

onMounted(async () => {
  // I13: each loader has its own try/catch inside; surface failures rather
  // than letting one rejection short-circuit the others.
  const settled = await Promise.allSettled([loadItems(), loadTasks(), loadDbTypes()])
  settled.forEach((result) => {
    if (result.status === 'rejected') {
      console.error('[Tasks] onMounted loader failed:', result.reason)
    }
  })
})
</script>
