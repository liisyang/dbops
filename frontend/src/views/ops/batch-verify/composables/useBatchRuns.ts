/*
 * useBatchRuns — 列表页批次列表加载
 *
 * 封装 assetsApi.listBatchRuns({ limit: 20 })，无轮询。
 * 失败时不静默，写入 error.value 给 BatchRunTable 渲染错误态。
 */

import { ref } from 'vue'
import { assetsApi } from '@/api/assets'
import type { BatchRunRow } from '@/types/api'

export function useBatchRuns() {
  const batches = ref<BatchRunRow[]>([])
  const loading = ref(false)
  const error = ref('')

  async function loadBatches(opts?: { signal?: AbortSignal }) {
    loading.value = true
    error.value = ''
    try {
      batches.value = await assetsApi.listBatchRuns({ limit: 20 }, opts)
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      if (e instanceof Error && e.name === 'CanceledError') return
      error.value = e instanceof Error ? e.message : String(e)
      console.error('useBatchRuns.loadBatches failed', e)
    } finally {
      loading.value = false
    }
  }

  const refresh = loadBatches

  return {
    batches,
    loading,
    error,
    loadBatches,
    refresh,
  }
}