<template>
  <OpsPage>
    <OpsPageHeader title="凭证绑定管理" subtitle="将凭证引用绑定到资产，支持优先级解析（数值越小优先级越高）。" />

    <OpsFilterBar :keyword="keyword" compact attached @update:keyword="keyword = $event" @search="loadData" @reset="keyword = ''; loadData()">
      <template #actions>
        <button type="button" class="ops-primary-button" @click="startCreate">
          <span class="material-symbols-outlined text-[18px]">add</span>
          新增绑定
        </button>
      </template>
    </OpsFilterBar>

    <OpsModal :open="showEditor" :title="editingId ? '编辑绑定' : '新增绑定'" size="lg" @close="cancelEdit">
      <form class="space-y-5" @submit.prevent="submitForm">
        <div v-if="formError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{{ formError }}</div>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card">
            <span class="field-label">绑定编码 <span class="text-red-400">*</span></span>
            <input v-model.trim="form.binding_code" class="field-input" type="text" placeholder="bind-mssql-instance-963" required />
          </label>
          <label class="block field-card">
            <span class="field-label">凭证 ID <span class="text-red-400">*</span></span>
            <select v-model.number="form.credential_profile_id" class="field-input" required>
              <option :value="0" disabled>请选择凭证</option>
              <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.profile_code }} ({{ p.credential_type }})</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">目标类型 <span class="text-red-400">*</span></span>
            <select v-model="form.target_type" class="field-input" required>
              <option value="db_instance">DB 实例</option>
              <option value="server">服务器</option>
              <option value="cluster">集群</option>
              <option value="business_system">业务系统</option>
              <option value="network_zone">网络区域</option>
              <option value="global">全局</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">目标 ID</span>
            <input v-model.number="form.target_id" class="field-input" type="number" placeholder="留空=按区域/全局" />
          </label>
          <label class="block field-card">
            <span class="field-label">网络区域</span>
            <input v-model.trim="form.network_zone" class="field-input" type="text" placeholder="target_type=network_zone 时填写" />
          </label>
          <label class="block field-card">
            <span class="field-label">绑定角色</span>
            <select v-model="form.binding_role" class="field-input">
              <option value="">继承 Profile 角色</option>
              <option value="db_readonly">DB 只读</option>
              <option value="db_monitor">DB 监控</option>
              <option value="db_owner">DB 所有者</option>
              <option value="db_admin">DB 管理员</option>
              <option value="os_readonly">OS 只读</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">优先级 <span class="text-red-400">*</span></span>
            <input v-model.number="form.priority" class="field-input" type="number" min="1" max="1000" required />
            <span class="text-xs text-on-surface-variant">越小越优先 (1-1000)</span>
          </label>
        </div>
        <div class="flex items-center justify-end gap-3 border-t border-outline-variant/40 pt-4">
          <button type="button" class="ops-secondary-button" @click="cancelEdit">取消</button>
          <button type="submit" class="ops-primary-button" :disabled="saving">
            <span class="material-symbols-outlined text-[18px]">{{ saving ? 'hourglass_empty' : 'check' }}</span>
            {{ saving ? '保存中...' : (editingId ? '保存修改' : '确认新增') }}
          </button>
        </div>
      </form>
    </OpsModal>

    <OpsTableShell :loading="loading" :empty="!filteredBindings.length && !loading">
      <table>
        <thead>
          <tr>
            <th>绑定编码</th>
            <th>凭证</th>
            <th>目标类型</th>
            <th>目标 ID</th>
            <th>区域</th>
            <th>角色</th>
            <th>优先级</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in filteredBindings" :key="b.id">
            <td class="font-mono text-sm">{{ b.binding_code }}</td>
            <td>{{ b.profile?.profile_code || `#${b.credential_profile_id}` }}</td>
            <td><span class="badge">{{ b.target_type }}</span></td>
            <td class="font-mono text-sm">{{ b.target_id || '-' }}</td>
            <td>{{ b.network_zone || '-' }}</td>
            <td><span class="badge">{{ b.binding_role || b.profile?.binding_role || '-' }}</span></td>
            <td class="font-mono">{{ b.priority }}</td>
            <td><span :class="b.is_enabled ? 'badge badge-success' : 'badge badge-error'">{{ b.is_enabled ? '启用' : '禁用' }}</span></td>
            <td class="flex gap-1">
              <button type="button" class="ops-icon-button" title="编辑" @click="startEdit(b)"><span class="material-symbols-outlined text-[18px]">edit</span></button>
              <button type="button" class="ops-icon-button text-red-400" title="删除" @click="confirmDelete(b)"><span class="material-symbols-outlined text-[18px]">delete</span></button>
            </td>
          </tr>
        </tbody>
      </table>
    </OpsTableShell>
  </OpsPage>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { assetsApi } from '@/api/assets'
import type { CredentialProfileRow, CredentialBindingRow, CredentialBindingCreatePayload } from '@/types/api'

const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const bindings = ref<CredentialBindingRow[]>([])
const profiles = ref<CredentialProfileRow[]>([])
const showEditor = ref(false)
const editingId = ref<number | null>(null)
const formError = ref('')

const emptyForm = (): CredentialBindingCreatePayload => ({
  binding_code: '', credential_profile_id: 0, target_type: 'db_instance',
  target_id: null, network_zone: '', binding_role: '', priority: 100,
  is_enabled: true, extra_attrs: {}, remark: '',
})
const form = reactive<CredentialBindingCreatePayload>(emptyForm())

const filteredBindings = computed(() => {
  if (!keyword.value) return bindings.value
  const kw = keyword.value.toLowerCase()
  return bindings.value.filter(b =>
    b.binding_code.toLowerCase().includes(kw) ||
    (b.profile?.profile_code || '').toLowerCase().includes(kw) ||
    b.target_type.toLowerCase().includes(kw)
  )
})

async function loadData() {
  loading.value = true
  try {
    const [b, p] = await Promise.all([assetsApi.listCredentialBindings(), assetsApi.listCredentialProfiles()])
    bindings.value = b; profiles.value = p
  } catch (e: any) { /* empty */ }
  finally { loading.value = false }
}

function startCreate() {
  Object.assign(form, emptyForm())
  editingId.value = null
  formError.value = ''
  showEditor.value = true
}

function startEdit(b: CredentialBindingRow) {
  editingId.value = b.id
  formError.value = ''
  form.binding_code = b.binding_code
  form.credential_profile_id = b.credential_profile_id
  form.target_type = b.target_type
  form.target_id = b.target_id ?? null
  form.network_zone = b.network_zone ?? ''
  form.binding_role = b.binding_role ?? ''
  form.priority = b.priority
  form.is_enabled = b.is_enabled
  showEditor.value = true
}

function cancelEdit() { showEditor.value = false; editingId.value = null }

async function submitForm() {
  if (!form.binding_code || !form.credential_profile_id || !form.target_type || !form.priority) {
    formError.value = '请填写必填字段'; return
  }
  saving.value = true; formError.value = ''
  try {
    if (editingId.value) {
      await assetsApi.updateCredentialBinding(editingId.value, form as any)
    } else {
      await assetsApi.createCredentialBinding(form)
    }
    showEditor.value = false
    await loadData()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || e?.message || '保存失败'
  } finally { saving.value = false }
}

async function confirmDelete(b: CredentialBindingRow) {
  if (!confirm(`确定删除绑定 "${b.binding_code}" 吗？此操作不可撤销。`)) return
  try {
    await assetsApi.deleteCredentialBinding(b.id)
    await loadData()
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

onMounted(loadData)
</script>
