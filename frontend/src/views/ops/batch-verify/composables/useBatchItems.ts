/*
 * useBatchItems — 详情页执行项加载 + 筛选 + 选中
 *
 * 关键设计：
 * - 接 Ref<number | null>，组件复用时自动跟随
 * - requestSeq 单调递增 + batchRunId 双保险
 * - 选中主键使用 item_key（语义稳定）
 * - preserveOnError 选项：轮询场景不破坏现有数据
 * - signal 不出现在公开 API：listBatchItems 不支持 abort
 * - 派生 selectedItemForDetail：map 到 VerifyItemDetail 期望 shape
 */

import { computed, reactive, ref, unref, type ComputedRef, type Ref } from 'vue'
import { assetsApi } from '@/api/assets'
import type { BatchRunItemRow } from '@/types/api'

export interface VerifyItemShape {
  item_key: string
  check_code: string
  target_scope: string
  asset_id: number
  target_host: string
  target_port: number
  port_source?: string | null
  status: string
  reachable?: boolean | null
  result_status?: string | null
  result_message?: string | null
  candidate_state?: string | null
  raw_result?: Record<string, unknown> | null
}

export function useBatchItems(batchRunIdRef: Ref<number | null>) {
  const items = ref<BatchRunItemRow[]>([])
  const itemFilters = reactive({ status: '', check_code: '' })
  const selectedItemKey = ref<string | null>(null)
  const loading = ref(false)
  const refreshing = ref(false)
  const error = ref('')

  let requestSeq = 0

  async function loadItems(opts: { preserveOnError?: boolean } = {}) {
    const batchRunId = unref(batchRunIdRef)
    if (!batchRunId) {
      items.value = []
      selectedItemKey.value = null
      return
    }
    const seq = ++requestSeq
    const isPolling = opts.preserveOnError === true
    if (isPolling) {
      refreshing.value = true
    } else {
      loading.value = true
    }
    error.value = ''
    try {
      const params: Record<string, unknown> = {}
      if (itemFilters.status) params.status = itemFilters.status
      if (itemFilters.check_code) params.check_code = itemFilters.check_code
      const result = await assetsApi.listBatchItems(batchRunId, params, { suppressErrorToast: true })
      if (seq !== requestSeq) return
      if (batchRunId !== unref(batchRunIdRef)) return

      const oldKey = selectedItemKey.value
      items.value = result
      if (oldKey && result.some((it) => it.item_key === oldKey)) {
        selectedItemKey.value = oldKey
      } else {
        selectedItemKey.value = result[0]?.item_key ?? null
      }
    } catch (err) {
      if (seq !== requestSeq) return
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (err instanceof Error && err.name === 'CanceledError') return
      if (opts.preserveOnError !== true) {
        items.value = []
        selectedItemKey.value = null
      }
      error.value = err instanceof Error ? err.message : '加载执行项失败'
      console.error('useBatchItems.loadItems failed', err)
    } finally {
      if (seq === requestSeq) {
        loading.value = false
        refreshing.value = false
      }
    }
  }

  function selectItem(item: BatchRunItemRow) {
    selectedItemKey.value = item.item_key
  }

  function reset() {
    requestSeq++
    items.value = []
    selectedItemKey.value = null
    itemFilters.status = ''
    itemFilters.check_code = ''
    error.value = ''
    loading.value = false
    refreshing.value = false
  }

  const selectedItem: ComputedRef<BatchRunItemRow | null> = computed(() => {
    const key = selectedItemKey.value
    if (!key) return null
    return items.value.find((it) => it.item_key === key) ?? null
  })

  const selectedItemForDetail: ComputedRef<VerifyItemShape | null> = computed(() => {
    const it = selectedItem.value
    if (!it) return null
    return {
      item_key: it.item_key,
      check_code: it.check_code,
      target_scope: it.target_scope,
      asset_id: (it as unknown as { asset_id?: number }).asset_id ?? it.db_instance_id ?? it.server_id ?? 0,
      target_host: it.target_host,
      target_port: it.target_port,
      port_source: it.port_source ?? null,
      status: it.status,
      reachable: (it.raw_result as Record<string, unknown> | null | undefined)?.reachable as boolean | null ?? null,
      result_status: it.result_status,
      result_message: it.result_message,
      candidate_state: it.candidate_state,
      raw_result: (it.raw_result as Record<string, unknown> | null | undefined) ?? null,
    }
  })

  return {
    items,
    itemFilters,
    selectedItemKey,
    selectedItem,
    selectedItemForDetail,
    loading,
    refreshing,
    error,
    loadItems,
    selectItem,
    reset,
  }
}