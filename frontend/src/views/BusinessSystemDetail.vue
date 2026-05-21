<template>
  <OpsPage>
    <div class="mb-4">
      <router-link
        to="/assets/businesses"
        class="inline-flex items-center gap-2 text-sm text-on-surface-variant transition-colors hover:text-on-surface"
      >
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        返回列表
      </router-link>
    </div>

    <OpsPageHeader
      :title="headerTitle"
      :subtitle="headerSubtitle"
    />

    <OpsSectionCard
      title="基础信息"
      subtitle="展示当前业务系统的基础分组信息。"
      icon="info"
    >
      <OpsEmptyState
        v-if="!loading && !detail"
        :state="error ? 'error' : 'empty'"
        :title="error ? '业务系统加载失败' : '未找到对应业务系统'"
        :description="error || '当前 id 未匹配到可展示的业务系统数据。'"
      />

      <div v-else-if="detail" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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

      <div v-else class="py-8">
        <OpsEmptyState state="loading" title="正在加载业务系统详情" description="正在读取业务系统基础信息和关联关系数据。" />
      </div>
    </OpsSectionCard>

    <OpsSectionCard
      title="联系人"
      subtitle="展示当前业务系统的联系人角色，并允许维护绑定关系。"
      icon="people"
    >
      <OpsEmptyState
        v-if="!loading && detail && !detail.contacts.length"
        state="empty"
        title="暂无联系人"
        description="当前业务系统没有返回联系人信息。"
      />

      <div v-else-if="detail" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="(contact, index) in detail.contacts"
          :key="`${contact.id}-${contact.contact_type}-${index}`"
          class="field-card"
        >
          <div class="field-label">{{ resolveContactLabel(contact.contact_type) }}</div>
          <div class="field-value">{{ contact.name }}</div>
          <div class="mt-2 text-xs text-slate-400">
            {{ contact.phone || '-' }}
          </div>
          <div class="mt-3 flex justify-end">
            <button
              class="rounded-full border border-red-400/25 bg-red-400/10 px-2.5 py-1 text-xs text-red-100 transition-colors hover:bg-red-400/20"
              type="button"
              :disabled="submittingContactBinding"
              @click="removeBusinessContact(contact)"
            >
              解除绑定
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="loading" class="py-8">
        <OpsEmptyState state="loading" title="正在加载联系人" description="正在读取业务系统联系人信息。" />
      </div>

      <div v-if="detail" class="mt-6 space-y-4 border-t border-outline-variant/40 pt-5">
        <div class="text-sm font-medium text-slate-100">新增绑定</div>
        <div v-if="contactBindingError" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {{ contactBindingError }}
        </div>
        <div class="grid gap-3 xl:grid-cols-3">
          <label class="space-y-1.5 text-sm">
            <span class="block text-[11px] uppercase tracking-[0.16em] text-slate-400">联系人</span>
            <select
              v-model.number="contactBindingForm.contact_id"
              class="h-11 w-full rounded-xl border border-outline-variant/60 bg-surface px-4 text-sm text-on-surface outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary/30"
            >
              <option :value="0" disabled>请选择联系人</option>
              <option v-for="contact in contactOptions" :key="contact.value" :value="contact.value">
                {{ contact.label }}
              </option>
            </select>
          </label>
          <label class="space-y-1.5 text-sm">
            <span class="block text-[11px] uppercase tracking-[0.16em] text-slate-400">角色</span>
            <select
              v-model="contactBindingForm.role_code"
              class="h-11 w-full rounded-xl border border-outline-variant/60 bg-surface px-4 text-sm text-on-surface outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary/30"
            >
              <option value="BUSINESS_MANAGER">业务主管</option>
              <option value="DBA_OWNER">DBA负责人</option>
            </select>
          </label>
          <label class="space-y-1.5 text-sm">
            <span class="block text-[11px] uppercase tracking-[0.16em] text-slate-400">备注</span>
            <input
              v-model.trim="contactBindingForm.remark"
              class="h-11 w-full rounded-xl border border-outline-variant/60 bg-surface px-4 text-sm text-on-surface outline-none transition-colors placeholder:text-on-surface-variant/50 focus:border-primary focus:ring-1 focus:ring-primary/30"
              type="text"
              placeholder="可选"
            />
          </label>
        </div>
        <div class="flex items-center justify-end">
          <button
            class="ops-primary-button"
            type="button"
            :disabled="submittingContactBinding || !contactBindingForm.contact_id"
            @click="submitContactBinding"
          >
            <span class="material-symbols-outlined text-[18px]">link</span>
            {{ submittingContactBinding ? '绑定中...' : '绑定联系人' }}
          </button>
        </div>
      </div>
    </OpsSectionCard>

    <OpsSectionCard
      title="关联集群"
      subtitle="展示当前业务系统关联的集群列表。"
      icon="account_tree"
    >
      <OpsEmptyState
        v-if="!loading && detail && !detail.clusters.length"
        state="empty"
        title="暂无关联集群"
        description="当前业务系统没有返回集群关系。"
      />

      <div v-else-if="detail" class="space-y-3">
        <div
          v-for="cluster in detail.clusters"
          :key="cluster.id"
          class="field-card"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="field-label">集群编码</div>
              <div class="field-value font-mono">{{ cluster.cluster_code }}</div>
            </div>
            <span class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">
              {{ cluster.cluster_type }}
            </span>
          </div>
          <div class="mt-3 text-sm text-slate-200">
            {{ cluster.cluster_name || '-' }}
          </div>
        </div>
      </div>

      <div v-else-if="loading" class="py-8">
        <OpsEmptyState state="loading" title="正在加载关联集群" description="正在读取业务系统关联集群数据。" />
      </div>
    </OpsSectionCard>

    <OpsSectionCard
      title="生命周期"
      subtitle="展示当前状态、生命周期操作和历史记录。"
      icon="history"
    >
      <template #actions>
        <div class="flex flex-wrap items-center gap-2">
          <span
            v-if="detail"
            class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium"
            :class="statusBadgeClass(detail.status)"
          >
            {{ formatStatusLabel(detail.status) }}
          </span>
          <button
            class="rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1.5 text-sm text-sky-100 transition-colors hover:bg-sky-400/20"
            type="button"
            :disabled="!detail || loading || submittingLifecycle"
            @click="openLifecycleAction('building')"
          >
            设为建设中
          </button>
          <button
            class="rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1.5 text-sm text-amber-100 transition-colors hover:bg-amber-400/20"
            type="button"
            :disabled="!detail || loading || submittingLifecycle"
            @click="openLifecycleAction('pending')"
          >
            设为待上线
          </button>
          <button
            class="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-sm text-emerald-100 transition-colors hover:bg-emerald-400/20"
            type="button"
            :disabled="!detail || loading || submittingLifecycle"
            @click="openLifecycleAction('active')"
          >
            标记已上线
          </button>
          <button
            class="rounded-full border border-slate-400/20 bg-slate-400/10 px-3 py-1.5 text-sm text-slate-100 transition-colors hover:bg-slate-400/20"
            type="button"
            :disabled="!detail || loading || submittingLifecycle"
            @click="openLifecycleAction('retired')"
          >
            标记已下线
          </button>
          <button
            class="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-on-surface transition-colors hover:bg-white/10"
            type="button"
            :disabled="!detail || loading"
            @click="toggleLifecycleHistory"
          >
            查看历史
          </button>
        </div>
      </template>

      <OpsEmptyState
        v-if="!loading && !detail && !error"
        state="empty"
        title="暂无生命周期信息"
        description="请先加载业务系统详情。"
      />

      <div v-else-if="detail" class="space-y-4">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div class="field-card">
            <div class="field-label">当前状态</div>
            <div class="mt-2 flex items-center gap-2">
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium" :class="statusBadgeClass(detail.status)">
                {{ formatStatusLabel(detail.status) }}
              </span>
            </div>
          </div>
          <div class="field-card sm:col-span-2 xl:col-span-3">
            <div class="field-label">状态说明</div>
            <div class="field-value">
              {{ lifecycleStatusDescription }}
            </div>
          </div>
        </div>

        <div
          v-if="lifecycleAction"
          class="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4"
        >
          <div class="mb-3 flex items-start justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-slate-100">
                {{ lifecycleActionTitle }}
              </div>
              <div class="mt-1 text-xs text-slate-400">
                提交后会刷新详情并拉取最新历史记录。
              </div>
            </div>
            <button
              class="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-on-surface transition-colors hover:bg-white/10"
              type="button"
              @click="closeLifecycleAction"
            >
              取消
            </button>
          </div>

          <div class="grid gap-3">
            <label class="space-y-1.5 text-sm">
              <span class="block text-[11px] uppercase tracking-[0.16em] text-slate-400">操作原因</span>
              <input
                v-model="lifecycleReason"
                class="h-11 w-full rounded-xl border border-outline-variant/60 bg-surface px-4 text-sm text-on-surface outline-none transition-colors placeholder:text-on-surface-variant/50 focus:border-primary focus:ring-1 focus:ring-primary/30"
                type="text"
                placeholder="例如：例行维护 / 业务切换"
              />
            </label>
            <label class="space-y-1.5 text-sm">
              <span class="block text-[11px] uppercase tracking-[0.16em] text-slate-400">补充说明</span>
              <textarea
                v-model="lifecycleRemark"
                class="min-h-[84px] w-full rounded-xl border border-outline-variant/60 bg-surface px-4 py-3 text-sm text-on-surface outline-none transition-colors placeholder:text-on-surface-variant/50 focus:border-primary focus:ring-1 focus:ring-primary/30"
                placeholder="填写本次生命周期变更的简要说明"
              ></textarea>
            </label>
            <label class="space-y-1.5 text-sm">
              <span class="block text-[11px] uppercase tracking-[0.16em] text-slate-400">生命周期上下文</span>
              <textarea
                v-model="lifecycleContextText"
                class="min-h-[84px] w-full rounded-xl border border-outline-variant/60 bg-surface px-4 py-3 text-sm text-on-surface outline-none transition-colors placeholder:text-on-surface-variant/50 focus:border-primary focus:ring-1 focus:ring-primary/30"
                placeholder="例如 IP 组、关联说明或其他上下文"
              ></textarea>
            </label>
          </div>

          <div class="mt-4 flex items-center justify-end gap-3">
            <button
              class="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-on-surface transition-colors hover:bg-white/10"
              type="button"
              @click="closeLifecycleAction"
            >
              取消
            </button>
            <button
              class="rounded-full px-3 py-1.5 text-sm font-medium text-white transition-colors"
              :class="lifecycleAction === 'active' ? 'bg-emerald-500 hover:bg-emerald-400' : lifecycleAction === 'pending' ? 'bg-amber-500 hover:bg-amber-400' : lifecycleAction === 'building' ? 'bg-sky-500 hover:bg-sky-400' : 'bg-slate-500 hover:bg-slate-400'"
              type="button"
              :disabled="submittingLifecycle"
              @click="submitLifecycleAction"
            >
              {{ lifecycleConfirmLabel }}
            </button>
          </div>
        </div>

        <div v-if="showLifecycleHistory" class="space-y-3">
          <OpsEmptyState
            v-if="!lifecycleHistory.length"
            state="empty"
            title="暂无生命周期历史"
            description="当前业务系统还没有生命周期变更记录。"
          />

          <div v-else class="space-y-3">
            <div
              v-for="record in lifecycleHistory"
              :key="record.id"
              class="rounded-xl border border-outline-variant/30 bg-surface-container-low px-3 py-2.5"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-sm font-medium text-slate-100">
                    {{ record.event_type }}
                  </div>
                  <div class="mt-1 text-xs text-slate-400">
                    {{ formatStatusTransition(record.before_status, record.after_status) }}
                  </div>
                </div>
                <span class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                  {{ record.operated_at }}
                </span>
              </div>
              <div class="mt-2 flex flex-wrap gap-3 text-xs text-slate-300">
                <span v-if="record.operator">操作人：{{ record.operator }}</span>
                <span v-if="record.reason">原因：{{ record.reason }}</span>
                <span v-if="record.remark">说明：{{ record.remark }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="loading" class="py-8">
        <OpsEmptyState state="loading" title="正在加载生命周期信息" description="正在读取业务系统生命周期状态和历史记录。" />
      </div>
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { assetsApi } from '@/api/assets'
import { OpsEmptyState, OpsPage, OpsPageHeader, OpsSectionCard } from '@/components/ops'
import type { AssetEventRow, BusinessContactRow, ContactRow, SystemDetail } from '@/types/api'

type SummaryField = {
  label: string
  value: string
  mono?: boolean
}

const route = useRoute()
const loading = ref(false)
const error = ref('')
const detail = ref<SystemDetail | null>(null)
const contactCatalog = ref<ContactRow[]>([])
const showLifecycleHistory = ref(false)
const lifecycleAction = ref<'building' | 'pending' | 'active' | 'retired' | null>(null)
const lifecycleReason = ref('')
const lifecycleRemark = ref('')
const lifecycleContextText = ref('')
const submittingLifecycle = ref(false)
const submittingContactBinding = ref(false)
const contactBindingError = ref('')
const contactBindingForm = reactive({
  contact_id: 0,
  role_code: 'BUSINESS_MANAGER',
  remark: '',
})

const headerTitle = computed(() => detail.value?.system_name || detail.value?.system_code || '业务系统详情')
const headerSubtitle = computed(() => {
  if (!detail.value) return '按业务系统 id 查看基础信息、联系人和关联集群。'
  return [detail.value.system_code, detail.value.business_unit || '无业务单位', detail.value.department || '无部门']
    .join(' / ')
})

const summaryFields = computed<SummaryField[]>(() => {
  if (!detail.value) return []
  return [
    { label: '系统编码', value: detail.value.system_code || '-', mono: true },
    { label: '系统名称', value: detail.value.system_name || '-' },
    { label: '业务单位', value: detail.value.business_unit || '-' },
    { label: '部门', value: detail.value.department || '-' },
    { label: '等级', value: detail.value.biz_level || '-' },
    { label: '联系人数', value: String(detail.value.contacts.length) },
    { label: '集群数', value: String(detail.value.clusters.length) },
  ]
})

const lifecycleHistory = computed<AssetEventRow[]>(() => detail.value?.lifecycle?.history ?? [])
const contactOptions = computed(() => {
  const boundIds = new Set(
    (detail.value?.contacts || []).map((c) => `${c.id}:${c.contact_type}`)
  )
  return contactCatalog.value.map((contact) => {
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

const lifecycleStatusDescription = computed(() => {
  if (!detail.value) return '-'
  if (!detail.value.status) return '当前业务系统尚未设置状态。'
  return `当前业务系统状态为 ${formatStatusLabel(detail.value.status)}。`
})

const lifecycleActionTitle = computed(() => {
  if (lifecycleAction.value === 'building') return '设为建设中'
  if (lifecycleAction.value === 'pending') return '设为待上线'
  if (lifecycleAction.value === 'active') return '标记已上线'
  if (lifecycleAction.value === 'retired') return '标记已下线'
  return ''
})

const lifecycleConfirmLabel = computed(() => {
  if (lifecycleAction.value === 'building') return '确认设为建设中'
  if (lifecycleAction.value === 'pending') return '确认设为待上线'
  if (lifecycleAction.value === 'active') return '确认标记已上线'
  if (lifecycleAction.value === 'retired') return '确认标记已下线'
  return '确认提交'
})

onMounted(() => {
  loadDetail()
})

watch(
  () => route.params.id,
  () => {
    loadDetail()
  }
)

async function loadDetail() {
  const id = String(route.params.id || '').trim()
  loading.value = true
  error.value = ''
  detail.value = null

  if (!id) {
    error.value = '缺少业务系统 id。'
    loading.value = false
    return
  }

  try {
    const [detailResult, historyResult, contactResult] = await Promise.allSettled([
      assetsApi.getBusinessSystem(id),
      assetsApi.listBusinessSystemHistory(id),
      assetsApi.listContacts(),
    ])

    if (detailResult.status === 'rejected') {
      throw detailResult.reason
    }

    detail.value = {
      ...detailResult.value,
      lifecycle: {
        history: historyResult.status === 'fulfilled' ? historyResult.value : [],
      },
    }
    contactCatalog.value = contactResult.status === 'fulfilled' ? contactResult.value : []
    if (!contactBindingForm.contact_id && contactCatalog.value.length) {
      contactBindingForm.contact_id = contactCatalog.value[0].id
    }
  } catch (err) {
    error.value = resolveErrorMessage(err)
  } finally {
    loading.value = false
  }
}

function openLifecycleAction(action: 'building' | 'pending' | 'active' | 'retired') {
  lifecycleAction.value = action
  lifecycleReason.value = ''
  lifecycleRemark.value = ''
  lifecycleContextText.value = ''
}

function closeLifecycleAction() {
  lifecycleAction.value = null
  lifecycleReason.value = ''
  lifecycleRemark.value = ''
  lifecycleContextText.value = ''
}

function resetContactBindingForm() {
  contactBindingError.value = ''
  contactBindingForm.role_code = 'BUSINESS_MANAGER'
  contactBindingForm.remark = ''
  contactBindingForm.contact_id = contactCatalog.value[0]?.id || 0
}

async function submitContactBinding() {
  if (!detail.value || !contactBindingForm.contact_id || submittingContactBinding.value) {
    return
  }

  submittingContactBinding.value = true
  contactBindingError.value = ''
  try {
    await assetsApi.addBusinessSystemContact(detail.value.id, {
      contact_id: contactBindingForm.contact_id,
      role_code: contactBindingForm.role_code,
      remark: trimToNull(contactBindingForm.remark),
    })
    await loadDetail()
    resetContactBindingForm()
  } catch (err) {
    contactBindingError.value = resolveErrorMessage(err)
  } finally {
    submittingContactBinding.value = false
  }
}

async function removeBusinessContact(contact: BusinessContactRow) {
  if (!detail.value || submittingContactBinding.value) return
  const confirmed = window.confirm(`确认解除「${contact.name}」的 ${resolveContactLabel(contact.contact_type)} 绑定吗？`)
  if (!confirmed) return

  submittingContactBinding.value = true
  contactBindingError.value = ''
  try {
    await assetsApi.deleteBusinessSystemContact(detail.value.id, contact.id, contact.contact_type)
    await loadDetail()
    resetContactBindingForm()
  } catch (err) {
    contactBindingError.value = resolveErrorMessage(err)
  } finally {
    submittingContactBinding.value = false
  }
}

function toggleLifecycleHistory() {
  showLifecycleHistory.value = !showLifecycleHistory.value
}

async function submitLifecycleAction() {
  if (!detail.value || !lifecycleAction.value || submittingLifecycle.value) return

  submittingLifecycle.value = true
  try {
    const payload = buildLifecyclePayload(lifecycleAction.value)
    await assetsApi.changeBusinessSystemLifecycle(detail.value.id, payload)

    closeLifecycleAction()
    showLifecycleHistory.value = true
    await loadDetail()
  } catch (err) {
    error.value = resolveErrorMessage(err)
  } finally {
    submittingLifecycle.value = false
  }
}

function buildLifecyclePayload(action: 'building' | 'pending' | 'active' | 'retired') {
  return {
    action,
    reason: trimToNull(lifecycleReason.value),
    remark: trimToNull(lifecycleRemark.value),
    ...(trimToNull(lifecycleContextText.value)
      ? {
          lifecycle_context: {
            context_text: lifecycleContextText.value.trim(),
          },
        }
      : {}),
  }
}

function resolveContactLabel(contactType: BusinessContactRow['contact_type']) {
  if (contactType === 'BUSINESS_MANAGER') return '业务主管'
  if (contactType === 'DBA_OWNER') return 'DBA负责人'
  return contactType || '联系人'
}

function trimToNull(value: string) {
  const trimmed = value.trim()
  return trimmed.length ? trimmed : null
}

function formatStatusLabel(status?: string | null) {
  const normalized = (status || '').trim().toLowerCase()
  if (!normalized) return '-'
  if (['building', 'build', 'draft', 'preparing', '建设中'].includes(normalized)) {
    return '建设中'
  }
  if (['pending', 'ready', '待上线', '上线待定'].includes(normalized)) {
    return '待上线'
  }
  if (['active', 'online', 'up', 'on', 'published', 'enabled', '1', '已上线', '在用'].includes(normalized)) {
    return '已上线'
  }
  if (['retired', 'inactive', 'offline', 'down', 'off', 'disabled', '0', '已下线', '下线', '停用'].includes(normalized)) {
    return '已下线'
  }
  return status || '-'
}

function statusBadgeClass(status?: string | null) {
  const normalized = (status || '').trim().toLowerCase()
  if (['building', 'build', 'draft', 'preparing', '建设中'].includes(normalized)) {
    return 'border-sky-400/30 bg-sky-400/10 text-sky-200'
  }
  if (['pending', 'ready', '待上线', '上线待定'].includes(normalized)) {
    return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  }
  if (['active', 'online', 'up', 'on', 'published', 'enabled', '1', '已上线', '在用'].includes(normalized)) {
    return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  }
  if (['retired', 'inactive', 'offline', 'down', 'off', 'disabled', '0', '已下线', '下线', '停用'].includes(normalized)) {
    return 'border-slate-400/30 bg-slate-400/10 text-slate-200'
  }
  return 'border-white/10 bg-white/5 text-slate-200'
}

function formatStatusTransition(beforeStatus?: string | null, afterStatus?: string | null) {
  const beforeLabel = formatStatusLabel(beforeStatus)
  const afterLabel = formatStatusLabel(afterStatus)
  if (beforeLabel === '-' && afterLabel === '-') return '状态变更信息为空'
  if (beforeLabel === '-') return `状态 -> ${afterLabel}`
  if (afterLabel === '-') return `${beforeLabel} -> 状态`
  return `${beforeLabel} -> ${afterLabel}`
}

function resolveErrorMessage(err: unknown) {
  if (typeof err === 'string') return err
  if (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string') {
    return err.message
  }
  return '请求业务系统详情失败，请稍后重试。'
}
</script>


