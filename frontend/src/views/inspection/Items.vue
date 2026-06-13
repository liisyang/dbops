<template>
  <OpsPage>
    <OpsPageHeader title="巡检项" subtitle="管理 inspection run_type 使用的标准巡检项。" icon="rule" />

    <OpsFilterBar
      :keyword="keyword"
      compact
      attached
      @update:keyword="keyword = $event"
      @search="loadItems"
      @reset="keyword = ''; loadItems()"
    >
      <template #actions>
        <button type="button" class="ops-secondary-button" @click="loadItems">
          <span class="material-symbols-outlined text-[18px]">refresh</span>
          刷新
        </button>
        <button type="button" class="ops-primary-button" @click="openCreate">
          <span class="material-symbols-outlined text-[18px]">add</span>
          新增巡检项
        </button>
      </template>
    </OpsFilterBar>

    <OpsModal :open="showEditor" :title="editingId ? '编辑巡检项' : '新增巡检项'" size="lg" @close="cancelEdit">
      <form class="space-y-5" @submit.prevent="submitForm">
        <div v-if="formError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ formError }}
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card">
            <span class="field-label">编码 <span class="text-red-400">*</span></span>
            <input v-model.trim="form.item_code" class="field-input" :disabled="!!editingId" required />
          </label>
          <label class="block field-card">
            <span class="field-label">名称 <span class="text-red-400">*</span></span>
            <input v-model.trim="form.item_name" class="field-input" required />
          </label>
          <label class="block field-card">
            <span class="field-label">check_code <span class="text-red-400">*</span></span>
            <input v-model.trim="form.check_code" class="field-input" required />
          </label>
          <label class="block field-card">
            <span class="field-label">目标范围</span>
            <select v-model="form.target_scope" class="field-input">
              <option value="db_instance">db_instance</option>
              <option value="server">server</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">严重级别</span>
            <select v-model="form.severity" class="field-input">
              <option value="info">info</option>
              <option value="warning">warning</option>
              <option value="critical">critical</option>
            </select>
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">描述</span>
            <textarea v-model.trim="form.description" class="field-input min-h-[80px] resize-y" />
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">规则配置 (JSON)</span>
            <textarea v-model.trim="ruleConfigInput" class="field-input min-h-[120px] resize-y font-mono text-xs" />
          </label>
        </div>

        <label class="inline-flex items-center gap-2 text-sm text-on-surface">
          <input v-model="form.enabled" type="checkbox" class="h-4 w-4" />
          启用
        </label>

        <div class="flex items-center justify-end gap-3 border-t border-outline-variant/40 pt-4">
          <button type="button" class="ops-secondary-button" @click="cancelEdit">取消</button>
          <button type="submit" class="ops-primary-button" :disabled="saving">
            <span class="material-symbols-outlined text-[18px]">{{ saving ? 'hourglass_empty' : 'check' }}</span>
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </form>
    </OpsModal>

    <OpsTableShell :loading="loading" :empty="!filteredItems.length && !loading">
      <table class="w-full text-sm">
        <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
          <tr>
            <th class="whitespace-nowrap px-4 py-3">编码</th>
            <th class="whitespace-nowrap px-4 py-3">名称</th>
            <th class="whitespace-nowrap px-4 py-3">check_code</th>
            <th class="whitespace-nowrap px-4 py-3">范围</th>
            <th class="whitespace-nowrap px-4 py-3">级别</th>
            <th class="whitespace-nowrap px-4 py-3">状态</th>
            <th class="whitespace-nowrap px-4 py-3">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filteredItems" :key="item.id" class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high">
            <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ item.item_code }}</td>
            <td class="whitespace-nowrap px-4 py-3">{{ item.item_name }}</td>
            <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ item.check_code }}</td>
            <td class="whitespace-nowrap px-4 py-3">{{ item.target_scope }}</td>
            <td class="whitespace-nowrap px-4 py-3">{{ item.severity }}</td>
            <td class="whitespace-nowrap px-4 py-3">
              <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                    :class="item.enabled ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-slate-400/30 bg-slate-400/10 text-slate-300'">
                {{ item.enabled ? '启用' : '禁用' }}
              </span>
            </td>
            <td class="whitespace-nowrap px-4 py-3">
              <button type="button" class="ops-icon-button" title="编辑" @click="openEdit(item)">
                <span class="material-symbols-outlined text-[18px]">edit</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </OpsTableShell>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import OpsFilterBar from '@/components/ops/OpsFilterBar.vue'
import OpsModal from '@/components/ops/OpsModal.vue'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import { assetsApi } from '@/api/assets'
import type { InspectionItemCreatePayload, InspectionItemRow, InspectionItemUpdatePayload } from '@/types/api'

const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const items = ref<InspectionItemRow[]>([])
const showEditor = ref(false)
const editingId = ref<number | null>(null)
const formError = ref('')
const ruleConfigInput = ref('{}')

const form = reactive<InspectionItemCreatePayload>({
  item_code: '',
  item_name: '',
  check_code: '',
  target_scope: 'db_instance',
  severity: 'warning',
  enabled: true,
  description: '',
  rule_config: {},
})

const filteredItems = computed(() => {
  if (!keyword.value) return items.value
  const kw = keyword.value.toLowerCase()
  return items.value.filter((item) =>
    item.item_code.toLowerCase().includes(kw)
    || item.item_name.toLowerCase().includes(kw)
    || item.check_code.toLowerCase().includes(kw)
  )
})

function resetForm() {
  form.item_code = ''
  form.item_name = ''
  form.check_code = ''
  form.target_scope = 'db_instance'
  form.severity = 'warning'
  form.enabled = true
  form.description = ''
  form.rule_config = {}
  ruleConfigInput.value = '{}'
  formError.value = ''
}

async function loadItems() {
  loading.value = true
  try {
    items.value = await assetsApi.listInspectionItems()
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  resetForm()
  showEditor.value = true
}

function openEdit(item: InspectionItemRow) {
  editingId.value = item.id
  form.item_code = item.item_code
  form.item_name = item.item_name
  form.check_code = item.check_code
  form.target_scope = item.target_scope
  form.severity = item.severity
  form.enabled = item.enabled
  form.description = item.description || ''
  ruleConfigInput.value = JSON.stringify(item.rule_config || {}, null, 2)
  formError.value = ''
  showEditor.value = true
}

function cancelEdit() {
  showEditor.value = false
  editingId.value = null
}

function parseRuleConfig(): { value: Record<string, any> | null; error: string | null } {
  const text = (ruleConfigInput.value || '').trim()
  if (!text) return { value: {}, error: null }
  try {
    const parsed = JSON.parse(text)
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { value: null, error: '规则配置必须为 JSON 对象' }
    }
    return { value: parsed as Record<string, any>, error: null }
  } catch (e: any) {
    return { value: null, error: `规则配置 JSON 解析失败: ${e?.message || '格式错误'}` }
  }
}

async function submitForm() {
  if (!form.item_code || !form.item_name || !form.check_code) {
    formError.value = '请填写必填字段'
    return
  }

  saving.value = true
  formError.value = ''
  try {
    const parsed = parseRuleConfig()
    if (parsed.error || parsed.value === null) {
      formError.value = parsed.error || '规则配置不合法'
      saving.value = false
      return
    }
    const payload = {
      ...form,
      rule_config: parsed.value,
    }
    if (editingId.value) {
      await assetsApi.updateInspectionItem(editingId.value, payload as InspectionItemUpdatePayload)
    } else {
      await assetsApi.createInspectionItem(payload)
    }
    showEditor.value = false
    await loadItems()
  } catch (error: any) {
    formError.value = error?.response?.data?.detail || error?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadItems)
</script>
