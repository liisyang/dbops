<!--
  BatchItemTable — 执行项表格 + 筛选 + 选中

  props 契约：
  - rows / loading / refreshing: 数据状态
  - selectedItemKey: 用 item_key 作选中主键（Round 3 #20）
  - canCancel: 是否允许取消批次
  - checkCodeOptions: 详情页 useBatchVerifyOptions 注入

  选中态：v-model:status / v-model:checkCode + @select(item) + @reload + @retry + @cancel
-->
<template>
  <div class="mb-4 flex flex-wrap items-center gap-3">
    <select
      v-model="status"
      class="rounded-lg border border-outline-variant/50 bg-surface-container px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
      @change="emit('reload')"
    >
      <option value="">全部状态</option>
      <option value="success">success</option>
      <option value="failed">failed</option>
      <option value="pending">pending</option>
      <option value="running">running</option>
    </select>
    <select
      v-model="checkCode"
      class="rounded-lg border border-outline-variant/50 bg-surface-container px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
      @change="emit('reload')"
    >
      <option value="">全部检查项</option>
      <option v-for="c in checkCodeOptions" :key="c.check_code" :value="c.check_code">
        {{ c.check_name }}
      </option>
    </select>
    <button
      class="text-xs text-primary transition-colors hover:text-primary/80"
      :disabled="retryLoading"
      @click="emit('retry')"
    >{{ retryLoading ? '重跑中...' : '重跑失败项' }}</button>
    <button
      v-if="canCancel"
      class="text-xs text-red-300 transition-colors hover:text-red-200 disabled:opacity-50"
      :disabled="cancelLoading"
      @click="emit('cancel')"
    >{{ cancelLoading ? '取消中...' : '取消批次' }}</button>
  </div>

  <OpsTableShell v-if="rows.length > 0">
    <table class="w-full text-sm">
      <thead class="bg-surface-container text-left text-xs uppercase text-on-surface-variant">
        <tr>
          <th class="whitespace-nowrap px-4 py-3">Item Key</th>
          <th class="whitespace-nowrap px-4 py-3">检查项</th>
          <th class="whitespace-nowrap px-4 py-3">目标</th>
          <th class="whitespace-nowrap px-4 py-3">状态</th>
          <th class="whitespace-nowrap px-4 py-3">结果</th>
          <th class="whitespace-nowrap px-4 py-3">事实数</th>
          <th class="whitespace-nowrap px-4 py-3">消息</th>
          <th class="whitespace-nowrap px-4 py-3">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in rows"
          :key="item.item_key"
          class="cursor-pointer border-t border-outline-variant/30 transition-colors hover:bg-surface-container-high"
          :class="selectedItemKey === item.item_key ? 'bg-surface-container-high' : ''"
          @click="emit('select', item)"
        >
          <td class="whitespace-nowrap px-4 py-3 font-mono text-xs max-w-[200px] truncate" :title="item.item_key">{{ item.item_key }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ item.check_code }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ item.target_host }}:{{ item.target_port }}</td>
          <td class="whitespace-nowrap px-4 py-3">
            <span
              class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
              :class="getItemStatusBadgeClass(item.status)"
            >{{ formatItemStatusLabel(item.status) }}</span>
          </td>
          <td class="whitespace-nowrap px-4 py-3">{{ formatItemResult(item) }}</td>
          <td class="whitespace-nowrap px-4 py-3">{{ getItemFactsCount(item) }}</td>
          <td class="max-w-[200px] truncate px-4 py-3 text-xs" :title="formatItemMessage(item)">{{ formatItemMessage(item) }}</td>
          <td class="whitespace-nowrap px-4 py-3">
            <button class="text-xs text-primary transition-colors hover:text-primary/80" @click.stop="emit('select', item)">详情</button>
          </td>
        </tr>
      </tbody>
    </table>
  </OpsTableShell>
  <OpsEmptyState v-else state="empty" title="暂无执行项" description="选择状态或检查项筛选" />
</template>

<script setup lang="ts">
import OpsTableShell from '@/components/ops/OpsTableShell.vue'
import OpsEmptyState from '@/components/ops/OpsEmptyState.vue'
import type { BatchRunItemRow, CollectorCheckDefinitionRow } from '@/types/api'
import {
  formatItemMessage,
  formatItemResult,
  formatItemStatusLabel,
  getItemFactsCount,
  getItemStatusBadgeClass,
} from '../utils/batchVerifyFormatters'

const status = defineModel<string>('status', { required: true })
const checkCode = defineModel<string>('checkCode', { required: true })

defineProps<{
  rows: BatchRunItemRow[]
  loading: boolean
  refreshing?: boolean
  selectedItemKey: string | null
  canCancel: boolean
  retryLoading?: boolean
  cancelLoading?: boolean
  checkCodeOptions: CollectorCheckDefinitionRow[]
}>()

const emit = defineEmits<{
  (e: 'select', item: BatchRunItemRow): void
  (e: 'reload'): void
  (e: 'retry'): void
  (e: 'cancel'): void
}>()
</script>