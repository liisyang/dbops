<template>
  <OpsSectionCard title="基础信息" subtitle="基础分组信息与联系人维护。" icon="info">
    <div v-if="!detail && !loading">
      <OpsEmptyState
        :state="error ? 'error' : 'empty'"
        :title="error ? '业务系统加载失败' : '未找到对应业务系统'"
        :description="error || '当前 id 未匹配到可展示的业务系统数据。'"
      />
    </div>

    <div v-else-if="loading && !detail" class="py-8">
      <OpsEmptyState state="loading" title="正在加载业务系统详情" description="正在读取业务系统基础信息和关联关系数据。" />
    </div>

    <div v-else-if="detail" class="space-y-6">
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="field in summaryFields"
          :key="field.label"
          class="field-card"
        >
          <div class="field-label">{{ field.label }}</div>
          <div class="field-value" :class="field.mono ? 'font-mono' : ''">
            {{ field.value }}
          </div>
        </div>
      </div>

      <div class="space-y-3">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="inline-flex h-6 w-6 items-center justify-center rounded-md bg-primary/15">
              <span class="material-symbols-outlined text-[14px] text-primary">group</span>
            </span>
            <h3 class="text-sm font-medium text-on-surface">联系人</h3>
            <span class="text-xs text-on-surface-variant">共 {{ detail.contacts.length }} 位</span>
          </div>
          <button
            type="button"
            class="ops-edit-button"
            :disabled="submitting"
            @click="openAddModal"
          >
            <span class="material-symbols-outlined text-[16px] leading-none">add</span>
            新增绑定
          </button>
        </div>

        <div v-if="!detail.contacts.length" class="rounded-xl border border-dashed border-outline-variant/50 bg-surface-container-low px-4 py-6 text-center text-sm text-on-surface-variant">
          暂无联系人，点击右上角"新增绑定"添加。
        </div>

        <div v-else class="overflow-hidden rounded-xl border border-outline-variant/40">
          <table class="w-full">
            <thead>
              <tr class="bg-surface-container-low text-left text-xs font-medium text-on-surface-variant">
                <th class="px-4 py-2.5">角色</th>
                <th class="px-4 py-2.5">联系人</th>
                <th class="px-4 py-2.5">联系方式</th>
                <th class="px-4 py-2.5 text-right">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-variant/30">
              <tr
                v-for="(contact, index) in detail.contacts"
                :key="`${contact.id}-${contact.contact_type}-${index}`"
                class="text-sm text-on-surface transition-colors hover:bg-surface-container-low"
              >
                <td class="px-4 py-2.5">{{ formatContactTypeLabel(contact.contact_type) }}</td>
                <td class="px-4 py-2.5">
                  <div class="flex items-center gap-2">
                    <span class="flex h-7 w-7 items-center justify-center rounded-full bg-white/5 text-on-surface-variant">
                      <span class="material-symbols-outlined text-[16px] leading-none">person</span>
                    </span>
                    <span>{{ contact.name }}</span>
                  </div>
                </td>
                <td class="px-4 py-2.5 text-on-surface-variant">{{ contact.phone || '-' }}</td>
                <td class="px-4 py-2.5 text-right">
                  <button
                    type="button"
                    class="ops-danger-button"
                    :disabled="submitting"
                    @click="$emit('remove', contact)"
                  >
                    <span class="material-symbols-outlined text-[14px] leading-none">link_off</span>
                    解除绑定
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <OpsModal
      :open="addModalOpen"
      title="新增联系人"
      subtitle="选择联系人与角色并填写备注后，绑定到当前业务系统。"
      icon="person_add"
      size="md"
      @close="closeAddModal"
    >
      <div v-if="bindingError" class="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {{ bindingError }}
      </div>
      <div class="grid gap-4 md:grid-cols-2">
        <label class="space-y-1.5 text-sm">
          <span class="field-label">联系人</span>
          <select
            v-model.number="form.contact_id"
            class="field-input"
          >
            <option :value="0" disabled>请选择联系人</option>
            <option v-for="option in contactOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="field-label">角色</span>
          <select
            v-model="form.role_code"
            class="field-input"
          >
            <option value="BUSINESS_MANAGER">业务主管</option>
            <option value="DBA_OWNER">DBA负责人</option>
          </select>
        </label>
        <label class="space-y-1.5 text-sm md:col-span-2">
          <span class="field-label">备注</span>
          <input
            v-model.trim="form.remark"
            type="text"
            class="field-input"
            placeholder="可选"
          />
        </label>
      </div>
      <template #footer>
        <div class="flex items-center justify-end gap-3">
          <button type="button" class="ops-secondary-button" :disabled="submitting" @click="closeAddModal">
            取消
          </button>
          <button
            type="button"
            class="ops-primary-button"
            :disabled="submitting || !form.contact_id"
            @click="submit"
          >
            <span class="material-symbols-outlined text-[18px]">link</span>
            {{ submitting ? '绑定中...' : '绑定联系人' }}
          </button>
        </div>
      </template>
    </OpsModal>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { OpsEmptyState, OpsModal, OpsSectionCard } from '@/components/ops'
import { formatContactTypeLabel } from '@/composables/useStatusFormatters'
import type { BusinessContactRow, ContactRow, SystemDetail } from '@/types/api'

type SummaryField = { label: string; value: string; mono?: boolean }

type BindingPayload = {
  contact_id: number
  role_code: string
  remark: string | null
}

const props = defineProps<{
  detail: SystemDetail | null
  contactCatalog: ContactRow[]
  loading: boolean
  error: string
  submitting: boolean
  bindingError: string
}>()

const emit = defineEmits<{
  (event: 'submit', payload: BindingPayload): void
  (event: 'remove', contact: BusinessContactRow): void
  (event: 'reset-binding-error'): void
}>()

const addModalOpen = ref(false)
const form = reactive({
  contact_id: 0,
  role_code: 'BUSINESS_MANAGER',
  remark: '',
})

const summaryFields = computed<SummaryField[]>(() => {
  if (!props.detail) return []
  return [
    { label: '系统编码', value: props.detail.system_code || '-', mono: true },
    { label: '系统名称', value: props.detail.system_name || '-' },
    { label: '业务单位', value: props.detail.business_unit || '-' },
    { label: '部门', value: props.detail.department || '-' },
    { label: '等级', value: props.detail.biz_level || '-' },
    { label: '联系人数', value: String(props.detail.contacts.length) },
    { label: '集群数', value: String(props.detail.clusters.length) },
  ]
})

const contactOptions = computed(() => {
  const boundIds = new Set(
    (props.detail?.contacts || []).map((c) => `${c.id}:${c.contact_type}`)
  )
  return props.contactCatalog.map((contact) => {
    const isBoundAsManager = boundIds.has(`${contact.id}:BUSINESS_MANAGER`)
    const isBoundAsDBA = boundIds.has(`${contact.id}:DBA_OWNER`)
    const suffix = isBoundAsManager && isBoundAsDBA
      ? ' [已绑定: 业务主管+DBA]'
      : isBoundAsManager
        ? ' [已绑定: 业务主管]'
        : isBoundAsDBA
          ? ' [已绑定: DBA]'
          : ''
    return {
      value: contact.id,
      label: [
        contact.contact_name,
        contact.employee_no ? `(${contact.employee_no})` : '',
        contact.dept ? `- ${contact.dept}` : '',
      ].filter(Boolean).join(' ') + suffix,
    }
  })
})

watch(
  () => props.contactCatalog,
  (catalog) => {
    if (!form.contact_id && catalog.length) {
      form.contact_id = catalog[0].id
    }
  },
  { immediate: true }
)

watch(
  () => props.submitting,
  (next, prev) => {
    if (prev && !next && !props.bindingError) {
      addModalOpen.value = false
      resetForm()
    }
  }
)

function openAddModal() {
  emit('reset-binding-error')
  if (!form.contact_id && props.contactCatalog.length) {
    form.contact_id = props.contactCatalog[0].id
  }
  addModalOpen.value = true
}

function closeAddModal() {
  if (props.submitting) return
  addModalOpen.value = false
  emit('reset-binding-error')
}

function resetForm() {
  form.role_code = 'BUSINESS_MANAGER'
  form.remark = ''
  form.contact_id = props.contactCatalog[0]?.id || 0
}

function submit() {
  if (!form.contact_id || props.submitting) return
  const trimmedRemark = form.remark.trim()
  emit('submit', {
    contact_id: form.contact_id,
    role_code: form.role_code,
    remark: trimmedRemark.length ? trimmedRemark : null,
  })
}
</script>
