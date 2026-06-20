<!--
  VerifyItemDetail — 单个 item 执行详情组件
  资产校验功能优化 v2 / 2026-06-17
  - 显示 check_code / status / reachable / message
  - 标准化 raw_result（duration_ms、rc、stdout、stderr、error_code、facts）
  - PORT_CANDIDATE_CONFLICT 提示
-->
<template>
  <OpsSectionCard
    v-if="item"
    title="执行项详情"
    :description="item.item_key"
  >
    <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      <dt class="text-on-surface-variant">check_code</dt>
      <dd class="font-mono text-xs">{{ item.check_code }}</dd>

      <dt class="text-on-surface-variant">target_scope</dt>
      <dd class="font-mono text-xs">{{ item.target_scope }}</dd>

      <dt class="text-on-surface-variant">target</dt>
      <dd class="font-mono text-xs">{{ item.target_host }}:{{ item.target_port }}</dd>

      <dt class="text-on-surface-variant">asset_id</dt>
      <dd class="font-mono text-xs">{{ item.asset_id }}</dd>

      <dt class="text-on-surface-variant">is_formal_port</dt>
      <dd>
        <!-- I11 (PR review 2026-06-18): 顶层字段是 dead wire，改为读 raw_result -->
        <span :class="item.raw_result?.is_formal_port ? 'text-emerald-700' : 'text-on-surface-variant'">
          {{ item.raw_result?.is_formal_port ? '是' : '否' }}
        </span>
      </dd>

      <dt class="text-on-surface-variant">port_source</dt>
      <dd class="font-mono text-xs">{{ item.port_source || '-' }}</dd>

      <dt class="text-on-surface-variant">status</dt>
      <dd>
        <span :class="statusBadgeClass(item.status)">{{ item.status }}</span>
      </dd>

      <dt class="text-on-surface-variant">reachable</dt>
      <dd>
        <span :class="item.reachable ? 'text-emerald-700' : 'text-red-700'">
          {{ item.reachable ? 'yes' : 'no' }}
        </span>
      </dd>

      <dt class="text-on-surface-variant">result_status</dt>
      <dd class="font-mono text-xs">{{ item.result_status || '-' }}</dd>

      <dt class="text-on-surface-variant">message</dt>
      <dd class="font-mono text-xs break-all">{{ item.result_message || '-' }}</dd>

      <template v-if="skipReason">
        <dt class="text-on-surface-variant">skip reason</dt>
        <dd class="text-amber-700 text-xs">{{ skipReason }}</dd>
      </template>
    </dl>

    <details v-if="rawResult" class="mt-4">
      <summary class="cursor-pointer text-sm text-on-surface-variant">
        raw_result ({{ factsCount }} facts, {{ durationMs }}ms)
      </summary>
      <pre class="mt-2 text-xs bg-surface-container p-3 rounded overflow-x-auto">{{ JSON.stringify(rawResult, null, 2) }}</pre>
    </details>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OpsSectionCard from './OpsSectionCard.vue'
import { verifyItemStatusBadge } from '@/constants/verifyItemStatus'
import type { CollectorRunItemRow } from '@/types/api'

// I13 (PR review 2026-06-20): 用 shared CollectorRunItemRow 替代 local VerifyItem。
// asset_id 来自 server_id 或 db_instance_id（按 target_scope 路由）。
// raw_result 用 Record<string, any> | null | undefined 以兼容外部 VerifyItemShape。
type VerifyItem = Omit<
  Pick<
    CollectorRunItemRow,
    | 'item_key' | 'check_code' | 'target_scope' | 'target_host' | 'target_port'
    | 'port_source' | 'status' | 'result_status' | 'result_message'
    | 'candidate_state'
  >,
  never
> & {
  asset_id: number
  reachable?: boolean | null
  raw_result?: Record<string, any> | null
}

const props = defineProps<{ item: VerifyItem | null }>()

const rawResult = computed(() => props.item?.raw_result || null)

const factsCount = computed(() => {
  const facts = (rawResult.value?.facts as unknown[]) || []
  return Array.isArray(facts) ? facts.length : 0
})

const durationMs = computed(() => {
  const r = rawResult.value
  if (!r) return 0
  const v = r.duration_ms ?? r.elapsed_ms
  return typeof v === 'number' ? v : 0
})

const skipReason = computed(() => {
  if (props.item?.status !== 'skipped') return null
  // 标准化 skip reason 推断
  const ev = rawResult.value
  if (ev && typeof ev === 'object' && 'skip_reason' in ev) {
    return String((ev as Record<string, unknown>).skip_reason)
  }
  return 'CALLBACK_RESULT_MISSING'
})

const statusBadgeClass = (s: string): string => verifyItemStatusBadge(s)
</script>
