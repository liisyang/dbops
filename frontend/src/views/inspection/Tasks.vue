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

        <label class="block field-card">
          <span class="field-label">资产 ID（可选，留空默认巡检全部）</span>
          <input v-model.trim="assetIdsInput" class="field-input" placeholder="1,2,3" />
        </label>

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
          <div class="field-value flex flex-wrap gap-3">
            <label
              v-for="item in selectableItems"
              :key="item.item_code"
              class="flex items-center gap-2 rounded-xl border border-outline-variant/40 bg-surface-container-high px-4 py-3 cursor-pointer hover:bg-surface-container-highest transition-colors"
            >
              <input v-model="form.item_codes" type="checkbox" :value="item.item_code" class="h-4 w-4" />
              <span class="text-sm">{{ item.item_name }} ({{ item.item_code }})</span>
            </label>
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
              <th class="whitespace-nowrap px-4 py-3">资产数</th>
              <th class="whitespace-nowrap px-4 py-3">检查项</th>
              <th class="whitespace-nowrap px-4 py-3">批次ID</th>
              <th class="whitespace-nowrap px-4 py-3">创建时间</th>
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
              <td class="whitespace-nowrap px-4 py-3">{{ (task.asset_ids || []).length }}</td>
              <td class="px-4 py-3 text-xs">{{ (task.item_codes || []).join(', ') || '-' }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ task.batch_run_id || '-' }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">{{ formatTime(task.created_at) }}</td>
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
const assetIdsInput = ref('')
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
  items.value.filter((item) => item.enabled && item.target_scope === form.target_scope)
)

function formatTime(value: string | null | undefined): string {
  return value ? formatInTz(value) : '-'
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

function parseAssetIds(): { ids: number[]; invalidTokens: string[] } {
  const invalidTokens: string[] = []
  const ids = assetIdsInput.value
    .split(',')
    .map((value) => value.trim())
    .filter((value) => value.length > 0)
    .map((value) => {
      const parsed = Number.parseInt(value, 10)
      if (!Number.isFinite(parsed) || parsed <= 0) {
        invalidTokens.push(value)
        return NaN
      }
      return parsed
    })
    .filter((value) => Number.isFinite(value))
  return { ids, invalidTokens }
}

async function submitTask() {
  createError.value = ''
  createMessage.value = ''

  const parsed = parseAssetIds()
  if (!form.task_name) {
    createError.value = '任务名称不能为空'
    return
  }
  if (parsed.invalidTokens.length) {
    // I11: surface the bad tokens instead of silently dropping them
    createError.value = `资产 ID 输入非法: ${parsed.invalidTokens.join(', ')}（需为正整数）`
    return
  }
  if (!form.item_codes.length) {
    createError.value = '至少选择一个巡检项'
    return
  }

  // I9: fleet-scan footgun guard — when neither asset_ids nor db_type_code
  // is set, the backend would scan every asset in scope. Ask the user to
  // confirm before submitting.
  const isFleetScan = parsed.ids.length === 0 && !dbTypeFilter.value
  if (isFleetScan) {
    fleetScanConfirmOpen.value = true
    return
  }
  await doCreateTask(parsed.ids, false)
}

async function doCreateTask(parsedAssetIds: number[], confirmFleetScan: boolean) {
  creating.value = true
  try {
    const payload: InspectionTaskCreatePayload = {
      ...form,
      asset_ids: parsedAssetIds.length ? parsedAssetIds : undefined,
      db_type_code: !parsedAssetIds.length && dbTypeFilter.value ? dbTypeFilter.value : undefined,
      confirm_fleet_scan: confirmFleetScan,
      item_codes: Array.from(new Set(form.item_codes)),
    }
    const result = await assetsApi.createInspectionTask(payload)
    createMessage.value = `任务已创建: ${result.task_code}（batch_run_id=${result.batch_run_id}）`
    form.task_name = ''
    form.item_codes = []
    assetIdsInput.value = ''
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
  // re-parse at submit time so the latest input is honored
  const parsed = parseAssetIds()
  await doCreateTask(parsed.ids, true)
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
