<!--
  BatchRunTable — 批次列表表格 + 行点击

  接收 rows / loading / error props，由父组件通过 useBatchRuns 注入。
  不在子组件内部调 API（保持单一职责）。
-->
<template>
  <OpsTableShell v-if="rows.length > 0">
    <table class="w-full text-sm">
      <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
        <tr>
          <th class="whitespace-nowrap px-4 py-3">批次编号</th>
          <th class="whitespace-nowrap px-4 py-3">类型</th>
          <th class="whitespace-nowrap px-4 py-3">范围</th>
          <th class="whitespace-nowrap px-4 py-3">状态</th>
          <th class="whitespace-nowrap px-4 py-3">资产数</th>
          <th class="whitespace-nowrap px-4 py-3">总 item</th>
          <th class="whitespace-nowrap px-4 py-3">成功</th>
          <th class="whitespace-nowrap px-4 py-3">失败</th>
          <th class="whitespace-nowrap px-4 py-3">分发数</th>
          <th class="whitespace-nowrap px-4 py-3">创建时间</th>
          <th class="whitespace-nowrap px-4 py-3">耗时</th>
          <th class="whitespace-nowrap px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="batch in rows"
          :key="batch.id"
          class="cursor-pointer border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
          @click="emit('detail', batch.id)"
        >
          <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ batch.batch_code }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ batch.run_type }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ batch.target_scope }}</td>
          <td class="whitespace-nowrap px-4 py-3">
            <span
              class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
              :class="getBatchStatusBadgeClass(batch.status)"
            >{{ formatBatchStatusLabel(batch.status) }}</span>
          </td>
          <td class="whitespace-nowrap px-4 py-3">{{ batch.total_asset_count }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ batch.total_item_count }}</td>
          <td class="whitespace-nowrap px-4 py-3 text-emerald-400">{{ batch.success_item_count }}</td>
          <td class="whitespace-nowrap px-4 py-3 text-red-400">{{ batch.failed_item_count }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ batch.dispatch_count }}</td>
          <td class="whitespace-nowrap px-4 py-3 text-xs text-on-surface-variant">{{ formatTime(batch.created_at) }}</td>
          <td class="whitespace-nowrap px-4 py-3 font-mono text-xs text-on-surface-variant">
            {{ formatDuration(batch.started_at, batch.finished_at) }}
          </td>
          <td class="whitespace-nowrap px-4 py-3">
            <button
              class="text-xs text-primary transition-colors hover:text-primary/80"
              @click.stop="emit('detail', batch.id)"
            >详情</button>
          </td>
        </tr>
      </tbody>
    </table>
  </OpsTableShell>
  <OpsEmptyState
    v-else-if="error"
    state="error"
    title="批量任务列表加载失败"
    :description="error"
  />
  <OpsEmptyState v-else state="empty" title="暂无批量任务" description="请在上方创建" />
</template>

<script setup lang="ts">
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import OpsEmptyState from '@/components/ops/OpsEmptyState.vue'
import type { BatchRunRow } from '@/types/api'
import {
  formatBatchStatusLabel,
  formatDuration,
  formatTime,
  getBatchStatusBadgeClass,
} from '../utils/batchVerifyFormatters'

defineProps<{
  rows: BatchRunRow[]
  loading: boolean
  error?: string
}>()

const emit = defineEmits<{
  (e: 'detail', batchRunId: number): void
}>()
</script>