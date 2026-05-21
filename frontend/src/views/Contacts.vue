<template>
  <OpsPage>
    <OpsPageHeader title="联系人管理" subtitle="维护联系人主数据，为业务系统提供可复用的联系人底座。" />

    <OpsFilterBar
      :keyword="draftKeyword"
      compact
      attached
      @update:keyword="draftKeyword = $event"
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
          新增联系人
        </button>
        </template>
    </OpsFilterBar>

    <OpsModal
      :open="showEditor"
      :title="editingContactId ? '编辑联系人' : '新增联系人'"
      :subtitle="editingContactId ? '修改联系人主数据' : '新增一个可复用的联系人'"
      :icon="editingContactId ? 'edit' : 'person_add'"
      size="lg"
      @close="cancelEditing"
    >
      <form class="space-y-5" @submit.prevent="submitContactForm">
        <div v-if="formError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ formError }}
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block field-card">
            <span class="field-label">工号</span>
            <input v-model.trim="contactForm.employee_no" class="field-input" type="text" placeholder="可选" />
          </label>
          <label class="block field-card">
            <span class="field-label">姓名 <span class="text-red-400">*</span></span>
            <input v-model.trim="contactForm.contact_name" class="field-input" type="text" placeholder="请输入姓名" />
          </label>
          <label class="block field-card">
            <span class="field-label">电话</span>
            <input v-model.trim="contactForm.phone" class="field-input" type="text" placeholder="可选" />
          </label>
          <label class="block field-card">
            <span class="field-label">邮箱</span>
            <input v-model.trim="contactForm.email" class="field-input" type="email" placeholder="可选" />
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">部门</span>
            <input v-model.trim="contactForm.dept" class="field-input" type="text" placeholder="可选" />
          </label>
          <label class="block field-card sm:col-span-2">
            <span class="field-label">备注</span>
            <textarea
              v-model.trim="contactForm.remark"
              class="field-input min-h-[96px] resize-y"
              placeholder="可选"
            ></textarea>
          </label>
        </div>

        <div class="flex items-center justify-end gap-3 border-t border-outline-variant/40 pt-4">
          <button
            type="button"
            class="ops-secondary-button"
            @click="cancelEditing"
          >
            取消
          </button>
          <button
            type="submit"
            class="ops-primary-button"
            :disabled="saving"
          >
            <span class="material-symbols-outlined text-[18px]">{{ saving ? 'hourglass_empty' : 'check' }}</span>
            {{ saving ? '保存中...' : (editingContactId ? '保存修改' : '确认新增') }}
          </button>
        </div>
      </form>
    </OpsModal>

    <OpsTableShell
      :loading="loading"
      :empty="!pagedContacts.length && !loading"
      :empty-state="error ? 'error' : 'empty'"
      :empty-title="error ? '加载失败' : hasActiveFilters ? '暂无匹配结果' : '暂无联系人数据'"
      :empty-description="error || (hasActiveFilters ? '当前筛选条件没有匹配的联系人。' : '当前没有联系人列表数据。')"
      :total-items="filteredContacts.length"
      :current-page="currentPage"
      :page-size="pageSize"
      @update:current-page="currentPage = $event"
      @update:page-size="pageSize = $event"
    >
      <table class="w-full text-sm">
        <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
          <tr>
            <th v-for="col in visibleColumns" :key="col.key" class="whitespace-nowrap px-4 py-3">{{ col.label }}</th>
            <th class="whitespace-nowrap px-4 py-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="contact in pagedContacts" :key="contact.id" class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high">
            <td v-for="col in visibleColumns" :key="col.key" :class="['whitespace-nowrap px-4 py-3', col.key === 'employee_no' ? 'font-mono' : '']">
              <template v-if="col.key === 'employee_no'">{{ contact.employee_no || '-' }}</template>
              <template v-else-if="col.key === 'contact_name'">{{ contact.contact_name }}</template>
              <template v-else-if="col.key === 'phone'">{{ contact.phone || '-' }}</template>
              <template v-else-if="col.key === 'email'">{{ contact.email || '-' }}</template>
              <template v-else-if="col.key === 'dept'">{{ contact.dept || '-' }}</template>
              <template v-else-if="col.key === 'remark'">{{ contact.remark || '-' }}</template>
            </td>
            <td class="whitespace-nowrap px-4 py-3">
              <div class="flex items-center justify-end gap-2">
                <button
                  class="ops-edit-button"
                  type="button"
                  @click="startEditing(contact)"
                >
                  <span class="material-symbols-outlined text-[14px]">edit</span>
                  编辑
                </button>
                <button
                  class="ops-danger-button"
                  type="button"
                  @click="removeContact(contact)"
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
import { computed, onMounted, reactive, ref } from 'vue'

import { assetsApi } from '@/api/assets'
import type { ContactRow, ContactUpsertPayload } from '@/types/api'
import { OpsColumnPicker, OpsFilterBar, OpsModal, OpsPage, OpsPageHeader, OpsTableShell } from '@/components/ops'
import { useColumnVisibility } from '@/composables/useColumnVisibility'

const CONTACT_COLUMNS = [
  { key: 'employee_no',   label: '工号' },
  { key: 'contact_name',  label: '姓名' },
  { key: 'phone',         label: '电话' },
  { key: 'email',         label: '邮箱' },
  { key: 'dept',          label: '部门' },
  { key: 'remark',        label: '备注', defaultVisible: false },
]
const { orderedColumns, visibleColumns, isVisible: isColVisible, toggleColumn, reorderColumn, resetColumns } = useColumnVisibility('contacts', CONTACT_COLUMNS)

const contacts = ref<ContactRow[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const formError = ref('')
const draftKeyword = ref('')
const appliedKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref<number | 'all'>(30)
const editorVisible = ref(false)
const editingContactId = ref<number | null>(null)
const contactForm = reactive<ContactUpsertPayload>({
  employee_no: '',
  contact_name: '',
  phone: '',
  email: '',
  dept: '',
  remark: '',
})

const normalizedAppliedKeyword = computed(() => appliedKeyword.value.trim().toLowerCase())

const filteredContacts = computed(() => {
  const keyword = normalizedAppliedKeyword.value
  return contacts.value.filter((contact) => {
    if (!keyword) return true
    return [
      contact.employee_no,
      contact.contact_name,
      contact.phone,
      contact.email,
      contact.dept,
      contact.remark,
    ].filter(Boolean).some((field) => String(field).toLowerCase().includes(keyword))
  })
})

const pagedContacts = computed(() => {
  if (pageSize.value === 'all') {
    return filteredContacts.value
  }
  const start = (currentPage.value - 1) * pageSize.value
  return filteredContacts.value.slice(start, start + pageSize.value)
})

const hasActiveFilters = computed(() => normalizedAppliedKeyword.value.length > 0)
const showEditor = computed(() => editorVisible.value)

async function loadContacts() {
  loading.value = true
  error.value = ''
  try {
    contacts.value = await assetsApi.listContacts()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载联系人失败'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingContactId.value = null
  editorVisible.value = false
  contactForm.employee_no = ''
  contactForm.contact_name = ''
  contactForm.phone = ''
  contactForm.email = ''
  contactForm.dept = ''
  contactForm.remark = ''
}

function startCreating() {
  formError.value = ''
  resetForm()
  editorVisible.value = true
}

function startEditing(contact: ContactRow) {
  formError.value = ''
  editorVisible.value = true
  editingContactId.value = contact.id
  contactForm.employee_no = contact.employee_no || ''
  contactForm.contact_name = contact.contact_name || ''
  contactForm.phone = contact.phone || ''
  contactForm.email = contact.email || ''
  contactForm.dept = contact.dept || ''
  contactForm.remark = contact.remark || ''
}

function cancelEditing() {
  formError.value = ''
  resetForm()
}

function applyFilters() {
  appliedKeyword.value = draftKeyword.value
  currentPage.value = 1
}

function resetFilters() {
  draftKeyword.value = ''
  appliedKeyword.value = ''
  currentPage.value = 1
}

async function submitContactForm() {
  saving.value = true
  formError.value = ''
  try {
    if (editingContactId.value === null) {
      await assetsApi.createContact({ ...contactForm })
    } else {
      await assetsApi.updateContact(editingContactId.value, { ...contactForm })
    }
    await loadContacts()
    resetForm()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存联系人失败'
  } finally {
    saving.value = false
  }
}

async function removeContact(contact: ContactRow) {
  const confirmed = window.confirm(`确认删除联系人「${contact.contact_name}」吗？`)
  if (!confirmed) return
  try {
    await assetsApi.deleteContact(contact.id)
    await loadContacts()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除联系人失败'
  }
}

onMounted(() => {
  void loadContacts()
})
</script>
