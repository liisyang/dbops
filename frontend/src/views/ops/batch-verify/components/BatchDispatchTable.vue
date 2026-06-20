<!--
  BatchDispatchTable — 分发明细表格

  纯展示组件，props.rows: DispatchRunSummary[]。
  cancelled_at 时间戳：仅在 I-8 operator 取消场景下显示。
-->
<template>
  <OpsTableShell v-if="rows.length > 0">
    <table class="w-full text-sm">
      <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
        <tr>
          <th class="whitespace-nowrap px-4 py-3">分发编号</th>
          <th class="whitespace-nowrap px-4 py-3">网段</th>
          <th class="whitespace-nowrap px-4 py-3">实例组</th>
          <th class="whitespace-nowrap px-4 py-3">状态</th>
          <th class="whitespace-nowrap px-4 py-3">Items</th>
          <th class="whitespace-nowrap px-4 py-3">成功</th>
          <th class="whitespace-nowrap px-4 py-3">失败</th>
          <th class="whitespace-nowrap px-4 py-3">AWX Job</th>
          <th class="whitespace-nowrap px-4 py-3">耗时</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="d in rows"
          :key="d.dispatch_run_id"
          class="border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
        >
          <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ d.dispatch_code || '-' }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ d.network_zone || '-' }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ d.awx_instance_group || '-' }}</td>
          <td class="whitespace-nowrap px-4 py-3">
            <span
              class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
              :class="getBatchStatusBadgeClass(d.status)"
            >{{ formatBatchStatusLabel(d.status) }}</span>
            <span
              v-if="isCancelled(d.status) && d.cancelled_at"
              class="ml-1.5 font-mono text-[10px] text-slate-400"
              :title="`cancelled at ${d.cancelled_at}`"
            >{{ formatTime(d.cancelled_at) }}</span>
          </td>
          <td class="whitespace-nowrap px-4 py-3">{{ d.item_count }}</td>
          <td class="whitespace-nowrap px-4 py-3 text-emerald-400">{{ d.success_item_count }}</td>
          <td class="whitespace-nowrap px-4 py-3 text-red-400">{{ d.failed_item_count }}</td>
          <td class="whitespace-nowrap px-4 py-3 font-mono text-xs">{{ d.awx_job_id || '-' }}</td>
          <td class="whitespace-nowrap px-4 py-3 font-mono text-xs text-on-surface-variant">
            {{ formatDuration(d.launched_at, d.finished_at) }}
          </td>
        </tr>
      </tbody>
    </table>
  </OpsTableShell>
  <OpsEmptyState v-else state="empty" title="暂无分发明细" />
</template>

<script setup lang="ts">
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import OpsEmptyState from '@/components/ops/OpsEmptyState.vue'
import type { DispatchRunSummary } from '@/types/api'
import {
  formatBatchStatusLabel,
  formatDuration,
  formatTime,
  getBatchStatusBadgeClass,
  isCancelled,
} from '../utils/batchVerifyFormatters'

defineProps<{ rows: DispatchRunSummary[] }>()
</script>