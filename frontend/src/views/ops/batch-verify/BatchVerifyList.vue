<!--
  BatchVerifyList — 批量校验列表页

  编排创建表单 + 批次列表。点击行 / 「详情」按钮跳转到 BatchVerifyDetail。
  创建成功 → router.push 跳详情页（附 query.created=1&code=&dispatches=），
  详情页顶部展示成功条。
-->
<template>
  <OpsPage>
    <OpsPageHeader
      title="批量校验"
      subtitle="选择资产范围和检查项，统一调度 AWX 批量执行"
      icon="checklist"
    />

    <BatchCreateCard
      class="mb-6"
      :db-types="dbTypes"
      :db-instance-check-codes="dbInstanceCheckCodes"
      :server-check-codes="serverCheckCodes"
      :options-loading="optionsLoading"
      @created="handleCreated"
    />

    <OpsSectionCard title="批量任务列表">
      <template #actions>
        <button class="ops-secondary-button text-xs" :disabled="loading" @click="() => loadBatches()">
          <span class="material-symbols-outlined text-[16px]">refresh</span>
          刷新
        </button>
      </template>

      <BatchRunTable
        :rows="batches"
        :loading="loading"
        :error="error"
        @detail="goDetail"
      />
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import BatchCreateCard from './components/BatchCreateCard.vue'
import BatchRunTable from './components/BatchRunTable.vue'
import { useBatchRuns } from './composables/useBatchRuns'
import { useBatchVerifyOptions } from './composables/useBatchVerifyOptions'
import type { BatchRunCreateResponse } from '@/types/api'

const router = useRouter()

const { batches, loading, error, loadBatches } = useBatchRuns()

const {
  dbTypes,
  dbInstanceCheckCodes,
  serverCheckCodes,
  loading: optionsLoading,
  loadOptions,
} = useBatchVerifyOptions()

onMounted(() => {
  void loadBatches()
  void loadOptions()
})

function goDetail(id: number) {
  router.push({ name: 'BatchVerifyDetail', params: { batchRunId: id } })
}

async function handleCreated(result: BatchRunCreateResponse) {
  await loadBatches()
  router.push({
    name: 'BatchVerifyDetail',
    params: { batchRunId: result.batch_run_id },
    query: {
      created: '1',
      code: result.batch_code,
      dispatches: String(result.dispatch_count),
    },
  })
}
</script>