<!--
  AssetVerifyReport — 资产维度校验报告
  资产校验功能优化 v2 / 2026-06-17
-->
<template>
  <OpsSectionCard
    title="资产维度报告"
    :description="`按资产聚合 batch ${batchRunId ?? '-'} 的所有 item 状态`"
  >
    <template #actions>
      <button
        v-if="report"
        class="ops-secondary-button"
        :disabled="loading"
        @click="load"
      >
        刷新
      </button>
    </template>

    <OpsEmptyState
      v-if="loading"
      state="loading"
      title="正在加载资产报告"
    />
    <OpsEmptyState
      v-else-if="error"
      state="error"
      title="资产报告加载失败"
      :description="error"
    />
    <OpsEmptyState
      v-else-if="!report || report.assets.length === 0"
      state="empty"
      title="暂无资产数据"
      description="该 batch 暂无 item。"
    />
    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-outline-variant text-sm">
        <thead class="bg-surface-container text-on-surface-variant">
          <tr>
            <th class="px-4 py-2 text-left">实体</th>
            <th class="px-4 py-2 text-left">IP</th>
            <th class="px-4 py-2 text-left">DB 端口</th>
            <th class="px-4 py-2 text-left">OS 端口</th>
            <th class="px-4 py-2 text-left">事实采集</th>
            <th class="px-4 py-2 text-right">Facts</th>
            <th class="px-4 py-2 text-left">错误</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-variant">
          <tr v-for="asset in report.assets" :key="`${asset.entity_type}-${asset.entity_id}`">
            <td class="px-4 py-2 font-mono text-xs">
              {{ asset.entity_type }}#{{ asset.entity_id }}<br />
              <span class="text-on-surface-variant">{{ asset.entity_name || '-' }}</span>
            </td>
            <td class="px-4 py-2 font-mono text-xs">{{ asset.ip_address || '-' }}</td>
            <td class="px-4 py-2">
              <span :class="badgeClass(asset.db_port_status)">
                {{ formatStatus(asset.db_port_status) }}
              </span>
            </td>
            <td class="px-4 py-2">
              <span :class="badgeClass(asset.os_port_status)">
                {{ formatStatus(asset.os_port_status) }}
              </span>
            </td>
            <td class="px-4 py-2">
              <span :class="badgeClass(asset.fact_status)">
                {{ formatStatus(asset.fact_status) }}
              </span>
            </td>
            <td class="px-4 py-2 text-right font-mono text-xs">{{ asset.fact_count }}</td>
            <td class="px-4 py-2 text-xs text-error">
              <span v-if="asset.error_messages.length === 0">-</span>
              <ul v-else class="space-y-0.5">
                <li v-for="(msg, idx) in asset.error_messages" :key="idx">
                  {{ msg }}
                </li>
              </ul>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import OpsSectionCard from './OpsSectionCard.vue'
import OpsEmptyState from './OpsEmptyState.vue'
import { assetsApi } from '@/api/assets'
import { verifyItemStatusBadge } from '@/constants/verifyItemStatus'
import type { AssetReport } from '@/types/api'

// I12 (PR review 2026-06-20): 删除 inline interface，import from @/types/api
// (AssetReport / AssetReportAsset 已在 script setup 顶部 import)

const props = defineProps<{ batchRunId: number | null }>()

const report = ref<AssetReport | null>(null)
const loading = ref(false)
const error = ref('')

const load = async () => {
  if (!props.batchRunId) {
    report.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    report.value = await assetsApi.getAssetReport(props.batchRunId, {
      suppressErrorToast: true,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    report.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.batchRunId, () => {
  void load()
})

onMounted(() => {
  void load()
})

// A5 (PR review 2026-06-20): 删除 formatPortStatus / formatFactStatus no-op 包装
// (if (!s) return 'n/a'; return s)，模板里直接显示 s 即可。
const formatStatus = (s: string | null | undefined): string => s || 'n/a'

const badgeClass = (s: string | null | undefined): string => verifyItemStatusBadge(s)
</script>
