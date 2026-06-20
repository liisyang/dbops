<!--
  BatchCreateCard — 新建批量任务表单

  错误分工（Round 3 #21）：表单校验 + 接口错误全部在子组件内部展示，
  成功 → emit('created', result: BatchRunCreateResponse) 由父组件跳转。
  props 由父组件通过 useBatchVerifyOptions 注入，避免子组件直接调 API。
-->
<template>
  <OpsSectionCard title="新建批量任务">
    <div class="space-y-4">
      <div class="grid gap-3 sm:grid-cols-2">
        <div class="field-card">
          <div class="field-label">目标范围</div>
          <div class="field-value flex gap-6">
            <label class="flex items-center gap-2 cursor-pointer">
              <input v-model="form.target_scope" type="radio" value="db_instance" class="h-4 w-4" />
              <span class="text-sm">数据库实例</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input v-model="form.target_scope" type="radio" value="server" class="h-4 w-4" />
              <span class="text-sm">服务器</span>
            </label>
          </div>
        </div>

        <div class="field-card">
          <div class="field-label">资产选择</div>
          <div class="field-value flex gap-6">
            <label class="flex items-center gap-2 cursor-pointer">
              <input v-model="selectionMode" type="radio" value="ids" class="h-4 w-4" />
              <span class="text-sm">按资产 ID</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input v-model="selectionMode" type="radio" value="filters" class="h-4 w-4" />
              <span class="text-sm">按条件筛选</span>
            </label>
          </div>
        </div>
      </div>

      <label v-if="selectionMode === 'ids'" class="block field-card">
        <span class="field-label">资产 ID</span>
        <input
          v-model="assetIdsInput"
          class="field-input"
          placeholder="输入资产 ID，逗号分隔（如 1,2,3）"
        />
      </label>

      <div v-if="selectionMode === 'filters'" class="grid gap-3 sm:grid-cols-3">
        <label class="block field-card">
          <span class="field-label">数据库类型</span>
          <select v-model="form.filters.db_type_code" class="field-input">
            <option value="">全部类型</option>
            <option v-for="dt in dbTypes" :key="dt.code" :value="dt.code">{{ dt.name }} ({{ dt.code }})</option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">状态</span>
          <select v-model="form.filters.status" class="field-input">
            <option value="">全部</option>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
          </select>
        </label>
        <label class="block field-card">
          <span class="field-label">站点 ID</span>
          <input v-model.number="form.filters.site_id" type="number" class="field-input" placeholder="站点 ID" />
        </label>
      </div>

      <div class="field-card">
        <div class="field-label">检查项</div>
        <div class="field-value flex flex-wrap gap-3">
          <label
            v-for="check in scopedCheckCodes"
            :key="check.check_code"
            class="flex items-center gap-2 rounded-xl border border-outline-variant/40 bg-surface-container-high px-4 py-3 cursor-pointer hover:bg-surface-container-highest transition-colors"
          >
            <input v-model="form.check_codes" type="checkbox" :value="check.check_code" class="h-4 w-4" />
            <span class="text-sm">{{ check.check_name }}</span>
          </label>
        </div>
      </div>

      <div class="grid gap-3 sm:grid-cols-3">
        <label class="block field-card">
          <span class="field-label">超时（秒）</span>
          <input v-model.number="form.timeout_seconds" type="number" min="1" max="60" class="field-input" />
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

      <button
        class="ops-primary-button"
        :disabled="launchLoading || optionsLoading || form.check_codes.length === 0"
        @click="createBatch"
      >
        <span class="material-symbols-outlined text-[18px]">{{ launchLoading ? 'hourglass_empty' : 'rocket_launch' }}</span>
        {{ launchLoading ? '提交中...' : '启动批量校验' }}
      </button>

      <div v-if="formError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{{ formError }}</div>
    </div>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import { assetsApi } from '@/api/assets'
import type {
  BatchRunCreatePayload,
  BatchRunCreateResponse,
  CollectorCheckDefinitionRow,
} from '@/types/api'

interface DbTypeOption {
  code: string
  name: string
}

const props = defineProps<{
  dbTypes: DbTypeOption[]
  dbInstanceCheckCodes: CollectorCheckDefinitionRow[]
  serverCheckCodes: CollectorCheckDefinitionRow[]
  optionsLoading?: boolean
}>()

const emit = defineEmits<{
  (e: 'created', result: BatchRunCreateResponse): void
}>()

const selectionMode = ref<'ids' | 'filters'>('ids')
const assetIdsInput = ref('')
const launchLoading = ref(false)
const formError = ref('')

const form = reactive({
  target_scope: 'db_instance' as 'db_instance' | 'server',
  check_codes: [] as string[],
  timeout_seconds: 3,
  max_items_per_dispatch: 100,
  include_related_server: true,
  filters: {
    db_type_code: '' as string,
    status: '' as string,
    site_id: null as number | null,
  },
})

const scopedCheckCodes = computed<CollectorCheckDefinitionRow[]>(() => {
  return form.target_scope === 'db_instance'
    ? props.dbInstanceCheckCodes
    : props.serverCheckCodes
})

watch(
  () => form.target_scope,
  () => {
    form.check_codes = []
  },
)

async function createBatch() {
  formError.value = ''

  const payload: BatchRunCreatePayload = {
    target_scope: form.target_scope,
    check_codes: form.check_codes,
    timeout_seconds: form.timeout_seconds,
    max_items_per_dispatch: form.max_items_per_dispatch,
    include_related_server: form.include_related_server,
  }

  if (selectionMode.value === 'ids') {
    const ids = assetIdsInput.value
      .split(',')
      .map((s) => parseInt(s.trim()))
      .filter((n) => !isNaN(n))
    if (ids.length === 0) {
      formError.value = '请输入有效的资产 ID'
      return
    }
    payload.asset_ids = ids
  } else {
    const f: Record<string, unknown> = {}
    if (form.filters.db_type_code) f.db_type_code = form.filters.db_type_code
    if (form.filters.status) f.status = form.filters.status
    if (form.filters.site_id) f.site_id = form.filters.site_id
    payload.filters = f
  }

  launchLoading.value = true
  try {
    const result = await assetsApi.createBatchRun(payload)
    assetIdsInput.value = ''
    form.check_codes = []
    emit('created', result)
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    formError.value = err?.response?.data?.detail || err?.message || String(e)
  } finally {
    launchLoading.value = false
  }
}
</script>