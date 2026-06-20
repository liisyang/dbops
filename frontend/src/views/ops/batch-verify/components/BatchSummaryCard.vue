<!--
  BatchSummaryCard — 7 格栅格摘要 + skipped 提示条

  纯展示组件，props.batch: BatchRunRow。
-->
<template>
  <OpsSectionCard title="结果摘要" icon="analytics">
    <div class="grid gap-3 sm:grid-cols-7">
      <div class="field-card text-center">
        <div class="field-value text-2xl font-bold">{{ batch.total_asset_count }}</div>
        <div class="field-label">总资产数</div>
      </div>
      <div class="field-card text-center">
        <div class="field-value text-2xl font-bold">{{ batch.total_item_count }}</div>
        <div class="field-label">总检查项</div>
      </div>
      <div class="field-card text-center">
        <div class="field-value text-2xl font-bold text-emerald-400">{{ batch.success_item_count }}</div>
        <div class="field-label">成功</div>
      </div>
      <div class="field-card text-center">
        <div class="field-value text-2xl font-bold text-red-400">{{ batch.failed_item_count }}</div>
        <div class="field-label">失败</div>
      </div>
      <div class="field-card text-center">
        <div class="field-value text-2xl font-bold" :class="successRateClass">{{ successRate }}%</div>
        <div class="field-label">成功率</div>
      </div>
      <div v-if="(batch.skipped_item_count || 0) > 0" class="field-card text-center">
        <div class="field-value text-2xl font-bold text-slate-300">{{ batch.skipped_item_count }}</div>
        <div class="field-label">跳过</div>
      </div>
      <div class="field-card text-center">
        <div class="field-value text-2xl font-bold font-mono">
          {{ formatDuration(batch.started_at, batch.finished_at) }}
        </div>
        <div class="field-label">总耗时</div>
      </div>
    </div>
    <div
      v-if="(batch.skipped_item_count || 0) > 0"
      class="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100"
    >
      本批次有 {{ batch.skipped_item_count }} 项被跳过，常见原因是目标类型未绑定可用凭证，或该项不适用当前批次。
    </div>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import type { BatchRunRow } from '@/types/api'
import {
  calculateSuccessRate,
  formatDuration,
  getSuccessRateClass,
} from '../utils/batchVerifyFormatters'

const props = defineProps<{ batch: BatchRunRow }>()

const successRate = computed(() => calculateSuccessRate(props.batch))
const successRateClass = computed(() => getSuccessRateClass(successRate.value))
</script>