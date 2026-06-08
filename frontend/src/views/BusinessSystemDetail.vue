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

    <OpsConfirmDialog
      :open="showConfirmRemoveContact"
      :message="`确认解除「${confirmingContact?.name}」的 ${formatContactTypeLabel(confirmingContact?.contact_type || '')} 绑定吗？`"
      confirm-label="解除绑定"
      :is-loading="submittingContactBinding"
      @close="onCancelRemoveContact"
      @confirm="confirmRemoveContact"
    />

    <div class="space-y-5 lg:space-y-6">
      <OpsEntityHeader
        :title="detail?.system_name || '业务系统详情'"
        :subtitle-parts="[detail?.system_code, detail?.business_unit, detail?.department]"
        :status="detail?.status"
        :chips="headerChips"
      />

      <div class="grid gap-5 lg:grid-cols-2 lg:gap-6">
        <BusinessBasicInfoCard
          :detail="detail"
          :contact-catalog="contactCatalog"
          :loading="loading"
          :error="error"
          :submitting="submittingContactBinding"
          :binding-error="contactBindingError"
          @submit="onSubmitContactBinding"
          @remove="onRequestRemoveContact"
          @reset-binding-error="contactBindingError = ''"
        />

        <BusinessTopologyCard
          :system-name="detail?.system_name"
          :clusters="detail?.clusters ?? []"
        />
      </div>

      <BusinessLifecycleCard
        :detail="detail"
        :loading="loading"
        :error="error"
        :history="lifecycleHistory"
        :show-history="showLifecycleHistory"
        :action="lifecycleAction"
        :reason="lifecycleReason"
        :remark="lifecycleRemark"
        :context="lifecycleContextText"
        :submitting="submittingLifecycle"
        :active-stage="activeStage"
        @toggle-history="toggleLifecycleHistory"
        @select-stage="setActiveStage"
        @open-action="openLifecycleAction"
        @close-action="closeLifecycleAction"
        @submit-action="submitLifecycleAction"
        @update:reason="lifecycleReason = $event"
        @update:remark="lifecycleRemark = $event"
        @update:context="lifecycleContextText = $event"
      />
    </div>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { assetsApi } from '@/api/assets'
import {
  BusinessBasicInfoCard,
  BusinessLifecycleCard,
  BusinessTopologyCard,
  type LifecycleStageId,
} from '@/components/business'
import { OpsConfirmDialog, OpsEntityHeader, OpsPage } from '@/components/ops'
import { formatContactTypeLabel } from '@/composables/useStatusFormatters'
import type { AssetEventRow, BusinessContactRow, ContactRow, SystemDetail } from '@/types/api'

type BindingPayload = {
  contact_id: number
  role_code: string
  remark: string | null
}

const route = useRoute()
const loading = ref(false)
const error = ref('')
const detail = ref<SystemDetail | null>(null)
const contactCatalog = ref<ContactRow[]>([])

const showLifecycleHistory = ref(false)
const lifecycleAction = ref<LifecycleStageId | null>(null)
const lifecycleReason = ref('')
const lifecycleRemark = ref('')
const lifecycleContextText = ref('')
const submittingLifecycle = ref(false)
const activeStage = ref<LifecycleStageId>('active')

const submittingContactBinding = ref(false)
const contactBindingError = ref('')
const showConfirmRemoveContact = ref(false)
const confirmingContact = ref<BusinessContactRow | null>(null)

const lifecycleHistory = computed<AssetEventRow[]>(() => detail.value?.lifecycle?.history ?? [])
const headerChips = computed(() => {
  const chips = [
    {
      icon: 'hub',
      label: `${detail.value?.clusters.length ?? 0} 个集群`,
    },
    {
      icon: 'group',
      label: `${detail.value?.contacts.length ?? 0} 位联系人`,
    },
  ]
  if (detail.value?.biz_level) {
    chips.push({
      icon: 'workspace_premium',
      label: detail.value.biz_level,
    })
  }
  return chips
})

const stageFromStatus: Record<string, LifecycleStageId> = {
  building: 'building',
  build: 'building',
  draft: 'building',
  preparing: 'building',
  '建设中': 'building',
  pending: 'pending',
  ready: 'pending',
  '待上线': 'pending',
  '上线待定': 'pending',
  active: 'active',
  online: 'active',
  up: 'active',
  on: 'active',
  enabled: 'active',
  published: 'active',
  '1': 'active',
  '已上线': 'active',
  '在用': 'active',
  retired: 'retired',
  inactive: 'retired',
  offline: 'retired',
  down: 'retired',
  off: 'retired',
  disabled: 'retired',
  '0': 'retired',
  '已下线': 'retired',
  '下线': 'retired',
  '停用': 'retired',
}

watch(
  () => detail.value?.status,
  (status) => {
    const key = (status || '').trim().toLowerCase()
    activeStage.value = stageFromStatus[key] || 'active'
  },
  { immediate: true }
)

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
  } catch (err) {
    error.value = resolveErrorMessage(err)
  } finally {
    loading.value = false
  }
}

function setActiveStage(stage: LifecycleStageId) {
  activeStage.value = stage
}

function openLifecycleAction(action: LifecycleStageId) {
  lifecycleAction.value = action
  lifecycleReason.value = ''
  lifecycleRemark.value = ''
  lifecycleContextText.value = ''
  activeStage.value = action
}

function closeLifecycleAction() {
  lifecycleAction.value = null
  lifecycleReason.value = ''
  lifecycleRemark.value = ''
  lifecycleContextText.value = ''
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

function buildLifecyclePayload(action: LifecycleStageId) {
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

async function onSubmitContactBinding(payload: BindingPayload) {
  if (!detail.value || submittingContactBinding.value) return
  submittingContactBinding.value = true
  contactBindingError.value = ''
  try {
    await assetsApi.addBusinessSystemContact(detail.value.id, payload)
    await loadDetail()
  } catch (err) {
    contactBindingError.value = resolveErrorMessage(err)
  } finally {
    submittingContactBinding.value = false
  }
}

function onRequestRemoveContact(contact: BusinessContactRow) {
  if (!detail.value || submittingContactBinding.value) return
  confirmingContact.value = contact
  showConfirmRemoveContact.value = true
}

function onCancelRemoveContact() {
  if (submittingContactBinding.value) return
  showConfirmRemoveContact.value = false
  confirmingContact.value = null
}

async function confirmRemoveContact() {
  if (!detail.value || !confirmingContact.value || submittingContactBinding.value) return

  const contact = confirmingContact.value
  submittingContactBinding.value = true
  contactBindingError.value = ''
  try {
    await assetsApi.deleteBusinessSystemContact(detail.value.id, contact.id, contact.contact_type)
    await loadDetail()
  } catch (err) {
    contactBindingError.value = resolveErrorMessage(err)
  } finally {
    submittingContactBinding.value = false
    showConfirmRemoveContact.value = false
    confirmingContact.value = null
  }
}

function trimToNull(value: string) {
  const trimmed = value.trim()
  return trimmed.length ? trimmed : null
}

function resolveErrorMessage(err: unknown) {
  if (typeof err === 'string') return err
  if (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string') {
    return err.message
  }
  return '请求业务系统详情失败，请稍后重试。'
}

</script>
