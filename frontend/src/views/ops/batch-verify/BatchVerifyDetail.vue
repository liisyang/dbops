<!--
  BatchVerifyDetail — 批量校验详情页

  编排 6 个 Section：
  - BatchPollingAlert（轮询错误）
  - BatchSummaryCard（结果摘要）
  - AssetVerifyReport（资产维度报告，:key 触发重 mount）
  - BatchDispatchTable（分发明细）
  - BatchItemTable + VerifyItemDetail（执行项）
  - ProposalPanel（变更建议，:key 触发重 mount）

  轮询启动单 owner：mount / watch(batchRunId) / handleManualRefresh /
  handleRetryFailed / handleCancelBatch 五处统一走 syncPollingAfterLoad()。
  终态自停由 useBatchPolling 内部负责。
-->
<template>
  <OpsPage>
    <OpsPageHeader
      :title="batchDetail?.batch_code || '批量校验详情'"
      :subtitle="subtitle"
      icon="analytics"
    >
      <template #actions>
        <button
          class="ops-secondary-button text-xs"
          :disabled="manualRefreshing || detailLoading"
          @click="handleManualRefresh"
        >
          <span class="material-symbols-outlined text-[16px]">refresh</span>
          刷新
        </button>
        <button class="ops-secondary-button text-xs" @click="router.push({ name: 'BatchVerify' })">
          返回列表
        </button>
      </template>
    </OpsPageHeader>

    <div
      v-if="showCreatedBanner"
      class="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200 flex items-center justify-between"
    >
      <span>{{ createdMessage }}</span>
      <button class="underline text-xs" @click="dismissCreatedBanner">关闭</button>
    </div>

    <OpsEmptyState v-if="invalidId" state="error" title="无效的批次 ID" />
    <OpsEmptyState
      v-else-if="detailLoading && !batchDetail"
      state="loading"
      title="正在加载批次详情"
    />
    <OpsEmptyState
      v-else-if="detailError && !batchDetail"
      state="error"
      title="加载失败"
      :description="detailError"
    />
    <template v-else-if="batchDetail">
      <BatchPollingAlert v-if="pollError" :message="pollError" @dismiss="pollError = ''" />
      <BatchSummaryCard :batch="batchDetail" />

      <AssetVerifyReport
        :key="`asset-report-${batchRunIdRef}-${assetReportRefreshKey}`"
        :batch-run-id="batchDetail.id"
      />

      <OpsSectionCard title="分发明细" icon="send">
        <BatchDispatchTable :rows="batchDetail.dispatches || []" />
      </OpsSectionCard>

      <OpsSectionCard title="执行项明细" icon="fact_check">
        <BatchItemTable
          v-model:status="itemFilters.status"
          v-model:check-code="itemFilters.check_code"
          :rows="items"
          :loading="itemsLoading"
          :refreshing="itemsRefreshing"
          :selected-item-key="selectedItem?.item_key ?? null"
          :can-cancel="canCancelBatch(batchDetail.status)"
          :retry-loading="retryLoading"
          :cancel-loading="cancelLoading"
          :check-code-options="itemCheckCodeOptions"
          @select="selectItem"
          @reload="loadItems"
          @retry="handleRetryFailed"
          @cancel="handleCancelBatch"
        />
      </OpsSectionCard>

      <VerifyItemDetail :item="selectedItemForDetail" />
      <ProposalPanel
        :key="`proposal-${batchRunIdRef}-${proposalRefreshKey}`"
        :batch-run-id="batchDetail.id"
      />
    </template>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsEmptyState from '@/components/ops/OpsEmptyState.vue'
import AssetVerifyReport from '@/components/ops/AssetVerifyReport.vue'
import ProposalPanel from '@/components/ops/ProposalPanel.vue'
import VerifyItemDetail from '@/components/ops/VerifyItemDetail.vue'
import BatchSummaryCard from './components/BatchSummaryCard.vue'
import BatchDispatchTable from './components/BatchDispatchTable.vue'
import BatchItemTable from './components/BatchItemTable.vue'
import BatchPollingAlert from './components/BatchPollingAlert.vue'
import { useBatchDetail } from './composables/useBatchDetail'
import { useBatchItems } from './composables/useBatchItems'
import { useBatchPolling } from './composables/useBatchPolling'
import { useBatchVerifyOptions } from './composables/useBatchVerifyOptions'
import {
  canCancelBatch,
  firstQueryValue,
  isTerminalBatchStatus,
} from './utils/batchVerifyFormatters'

const props = defineProps<{ batchRunId: number }>()
const route = useRoute()
const router = useRouter()

const batchRunIdRef = computed(() =>
  Number.isFinite(props.batchRunId) && props.batchRunId > 0 ? props.batchRunId : null,
)
const invalidId = computed(() => batchRunIdRef.value === null)

const {
  batchDetail,
  loading: detailLoading,
  refreshing: detailRefreshing,
  error: detailError,
  loadBatchDetail,
  refreshDetail,
  retryFailed,
  cancelBatch,
  reset: resetDetail,
  retryLoading,
  cancelLoading,
} = useBatchDetail(batchRunIdRef)

const {
  items,
  itemFilters,
  selectedItem,
  selectedItemForDetail,
  loading: itemsLoading,
  refreshing: itemsRefreshing,
  loadItems,
  selectItem,
  reset: resetItems,
} = useBatchItems(batchRunIdRef)

const { checkCodes: checkCodeOptions, loadOptions: loadVerifyOptions } = useBatchVerifyOptions()

const { pollError, startPolling, stopPolling } = useBatchPolling({
  batchRunIdRef,
  getStatus: () => batchDetail.value?.status ?? null,
  onTick: async (signal) => {
    await Promise.all([
      loadBatchDetail({ silent: true, signal }),
      loadItems({ preserveOnError: true }),
    ])
  },
})

const subtitle = computed(() =>
  batchDetail.value ? `批次编号：${batchDetail.value.batch_code}` : '批次详情',
)

const isRunning = computed(() => {
  const status = batchDetail.value?.status
  return !!status && !isTerminalBatchStatus(status)
})

const itemCheckCodeOptions = computed(() => {
  const exists = new Set(
    items.value.map(item => item.check_code).filter((code): code is string => Boolean(code)),
  )
  return checkCodeOptions.value.filter(item => exists.has(item.check_code))
})

const showCreatedBanner = computed(() => firstQueryValue(route.query.created) === '1')
const createdMessage = computed(() => {
  if (!showCreatedBanner.value) return ''
  const code = firstQueryValue(route.query.code) || batchDetail.value?.batch_code || ''
  const dispatches =
    firstQueryValue(route.query.dispatches) ||
    String(batchDetail.value?.dispatch_count ?? 0)
  return `批量任务已创建：${code}，${dispatches} 个分发`
})
function dismissCreatedBanner() {
  const nextQuery = { ...route.query }
  delete nextQuery.created
  delete nextQuery.code
  delete nextQuery.dispatches
  router.replace({
    name: 'BatchVerifyDetail',
    params: { batchRunId: props.batchRunId },
    query: nextQuery,
  })
}

const assetReportRefreshKey = ref(0)
const proposalRefreshKey = ref(0)
const manualRefreshing = ref(false)
async function handleManualRefresh() {
  manualRefreshing.value = true
  try {
    assetReportRefreshKey.value += 1
    proposalRefreshKey.value += 1
    await Promise.allSettled([
      refreshDetail(),
      loadItems({ preserveOnError: true }),
    ])
    syncPollingAfterLoad()
  } finally {
    manualRefreshing.value = false
  }
}

async function reloadDetailPage(opts: { preserveItemsOnError?: boolean } = {}) {
  await Promise.all([
    refreshDetail(),
    loadItems({ preserveOnError: opts.preserveItemsOnError === true }),
  ])
}

function syncPollingAfterLoad() {
  if (isRunning.value) {
    startPolling({ immediate: false })
  } else {
    stopPolling()
  }
}

async function handleRetryFailed() {
  await retryFailed()
  await Promise.allSettled([
    refreshDetail(),
    loadItems({ preserveOnError: true }),
  ])
  proposalRefreshKey.value += 1
  syncPollingAfterLoad()
}

async function handleCancelBatch() {
  await cancelBatch()
  await Promise.allSettled([
    refreshDetail(),
    loadItems({ preserveOnError: true }),
  ])
  syncPollingAfterLoad()
}

onMounted(async () => {
  if (invalidId.value) return
  void loadVerifyOptions()
  await reloadDetailPage({ preserveItemsOnError: false })
  syncPollingAfterLoad()
})

watch(
  () => props.batchRunId,
  async () => {
    stopPolling()
    pollError.value = ''
    resetDetail()
    resetItems()
    if (invalidId.value) return
    await reloadDetailPage({ preserveItemsOnError: false })
    syncPollingAfterLoad()
  },
)
</script>