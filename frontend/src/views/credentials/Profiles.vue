<template>
  <OpsPage>
    <OpsPageHeader title="凭证引用管理" subtitle="管理 AWX 凭证引用，不存储密码。凭证实际存储在 AWX 中。" />

    <OpsFilterBar :keyword="keyword" compact attached @update:keyword="keyword = $event" @search="loadProfiles" @reset="keyword = ''; loadProfiles()">
      <template #actions>
        <button type="button" class="ops-primary-button" @click="startCreate">
          <span class="material-symbols-outlined text-[18px]">add</span>
          新增凭证
        </button>
      </template>
    </OpsFilterBar>

    <OpsModal :open="showEditor" :title="editingId ? '编辑凭证' : '新增凭证'" size="lg" @close="cancelEdit">
      <form class="space-y-5" @submit.prevent="submitForm">
        <div v-if="formError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{{ formError }}</div>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card">
            <span class="field-label">编码 <span class="text-red-400">*</span></span>
            <input v-model.trim="form.profile_code" class="field-input" type="text" placeholder="cred-mssql-prod-ro" required :disabled="!!editingId" />
          </label>
          <label class="block field-card">
            <span class="field-label">名称 <span class="text-red-400">*</span></span>
            <input v-model.trim="form.profile_name" class="field-input" type="text" placeholder="SQL Server PROD Readonly" required />
          </label>
          <label class="block field-card">
            <span class="field-label">凭证类型 <span class="text-red-400">*</span></span>
            <select v-model="form.credential_type" class="field-input" required>
              <option value="db_password">DB 密码</option>
              <option value="ssh_key">SSH 密钥</option>
              <option value="ssh_password">SSH 密码</option>
              <option value="winrm_password">WinRM 密码</option>
              <option value="api_token">API Token</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">绑定角色 <span class="text-red-400">*</span></span>
            <select v-model="form.binding_role" class="field-input" required>
              <option value="db_readonly">DB 只读</option>
              <option value="db_monitor">DB 监控</option>
              <option value="db_owner">DB 所有者</option>
              <option value="db_admin">DB 管理员</option>
              <option value="os_readonly">OS 只读</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">AWX 凭证 ID</span>
            <input v-model.number="form.awx_credential_id" class="field-input" type="number" placeholder="5" />
          </label>
          <label class="block field-card">
            <span class="field-label">AWX 凭证名称</span>
            <input v-model.trim="form.awx_credential_name" class="field-input" type="text" placeholder="cred-db-mssql-ro-prod" />
          </label>
          <label class="block field-card">
            <span class="field-label">DB 类型</span>
            <input v-model.trim="form.db_type_code" class="field-input" type="text" placeholder="sqlserver / oracle / postgresql" />
          </label>
          <label class="block field-card">
            <span class="field-label">OS 类型</span>
            <input v-model.trim="form.os_family" class="field-input" type="text" placeholder="linux / windows" />
          </label>
          <label class="block field-card">
            <span class="field-label">使用范围</span>
            <select v-model="form.usage_scope" class="field-input">
              <option value="">不限</option>
              <option value="db_instance">DB 实例</option>
              <option value="server">服务器</option>
            </select>
          </label>
          <label class="block field-card">
            <span class="field-label">网络区域</span>
            <input v-model.trim="form.network_zone" class="field-input" type="text" placeholder="local-lh-test" />
          </label>
          <label class="block field-card">
            <span class="field-label">环境</span>
            <select v-model="form.environment" class="field-input">
              <option value="">不限</option>
              <option value="prod">生产</option>
              <option value="staging">预发布</option>
              <option value="dev">开发</option>
              <option value="test">测试</option>
            </select>
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">备注</span>
            <textarea v-model.trim="form.remark" class="field-input min-h-[80px] resize-y" placeholder="可选"></textarea>
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

    <OpsTableShell :loading="loading" :empty="!filteredProfiles.length && !loading">
      <table>
        <thead>
          <tr>
            <th>编码</th>
            <th>名称</th>
            <th>类型</th>
            <th>角色</th>
            <th>DB 类型</th>
            <th>AWX ID</th>
            <th>区域</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in filteredProfiles" :key="p.id">
            <td class="font-mono text-sm">{{ p.profile_code }}</td>
            <td>{{ p.profile_name }}</td>
            <td><span class="badge">{{ p.credential_type }}</span></td>
            <td><span class="badge">{{ p.binding_role }}</span></td>
            <td>{{ p.db_type_code || '-' }}</td>
            <td class="font-mono text-sm">{{ p.awx_credential_id || '-' }}</td>
            <td>{{ p.network_zone || '-' }}</td>
            <td><span :class="p.is_enabled ? 'badge badge-success' : 'badge badge-error'">{{ p.is_enabled ? '启用' : '禁用' }}</span></td>
            <td>
              <button type="button" class="ops-icon-button" title="编辑" @click="startEdit(p)"><span class="material-symbols-outlined text-[18px]">edit</span></button>
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
import type { CredentialProfileRow, CredentialProfileCreatePayload, CredentialProfileUpdatePayload } from '@/types/api'

const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const profiles = ref<CredentialProfileRow[]>([])
const showEditor = ref(false)
const editingId = ref<number | null>(null)
const formError = ref('')

const emptyForm = (): CredentialProfileCreatePayload => ({
  profile_code: '', profile_name: '', credential_type: 'db_password', binding_role: 'db_readonly',
  awx_credential_id: null, awx_credential_name: '', db_type_code: '', os_family: '',
  usage_scope: '', network_zone: '', environment: '', remark: '',
  is_enabled: true, extra_attrs: {},
})
const form = reactive<CredentialProfileCreatePayload>(emptyForm())

const filteredProfiles = computed(() => {
  if (!keyword.value) return profiles.value
  const kw = keyword.value.toLowerCase()
  return profiles.value.filter(p =>
    p.profile_code.toLowerCase().includes(kw) ||
    p.profile_name.toLowerCase().includes(kw) ||
    (p.db_type_code || '').toLowerCase().includes(kw)
  )
})

async function loadProfiles() {
  loading.value = true
  try { profiles.value = await assetsApi.listCredentialProfiles() } catch (e: any) { /* empty */ }
  finally { loading.value = false }
}

function startCreate() {
  Object.assign(form, emptyForm())
  editingId.value = null
  formError.value = ''
  showEditor.value = true
}

function startEdit(p: CredentialProfileRow) {
  editingId.value = p.id
  formError.value = ''
  form.profile_code = p.profile_code
  form.profile_name = p.profile_name
  form.credential_type = p.credential_type
  form.binding_role = p.binding_role
  form.awx_credential_id = p.awx_credential_id ?? null
  form.awx_credential_name = p.awx_credential_name ?? ''
  form.db_type_code = p.db_type_code ?? ''
  form.os_family = p.os_family ?? ''
  form.usage_scope = p.usage_scope ?? ''
  form.network_zone = p.network_zone ?? ''
  form.environment = p.environment ?? ''
  form.remark = p.remark ?? ''
  form.is_enabled = p.is_enabled
  showEditor.value = true
}

function cancelEdit() { showEditor.value = false; editingId.value = null }

async function submitForm() {
  if (!form.profile_code || !form.profile_name || !form.credential_type || !form.binding_role) {
    formError.value = '请填写必填字段'; return
  }
  saving.value = true; formError.value = ''
  try {
    if (editingId.value) {
      await assetsApi.updateCredentialProfile(editingId.value, form as CredentialProfileUpdatePayload)
    } else {
      await assetsApi.createCredentialProfile(form)
    }
    showEditor.value = false
    await loadProfiles()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || e?.message || '保存失败'
  } finally { saving.value = false }
}

onMounted(loadProfiles)
</script>
