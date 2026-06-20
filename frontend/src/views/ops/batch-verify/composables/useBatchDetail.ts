/*
 * useBatchDetail — 详情页单个批次加载 / 取消 / 重跑
 *
 * 关键设计（来自 plan Round 2/3/4 评审修订）：
 * - 接 `Ref<number | null>` 而非 number，组件复用（路由切换）时自动跟随
 * - requestSeq 单调递增 + batchRunId !== unref(batchRunIdRef) 双保险
 * - 同时暴露 `loading`（首次加载 / 主动 refresh）和 `refreshing`（静默 / 轮询）
 * - 失败时不静默：写入 error.value 但保留旧 batchDetail
 * - cancelBatch 沿用 window.confirm 文案（产品决策：本次 0 行为改动）
 */

import { ref, unref, type Ref } from 'vue'
import { assetsApi } from '@/api/assets'
import type { BatchRunRow } from '@/types/api'

export function useBatchDetail(batchRunIdRef: Ref<number | null>) {
  const batchDetail = ref<BatchRunRow | null>(null)
  const loading = ref(false)
  const refreshing = ref(false)
  const error = ref('')
  const retryLoading = ref(false)
  const cancelLoading = ref(false)

  let requestSeq = 0

  async function loadBatchDetail(opts: { silent?: boolean; signal?: AbortSignal } = {}) {
    const batchRunId = unref(batchRunIdRef)
    if (!batchRunId) {
      batchDetail.value = null
      return
    }
    const seq = ++requestSeq
    const silent = opts.silent === true
    if (silent) {
      refreshing.value = true
    } else {
      loading.value = true
    }
    error.value = ''
    try {
      const result = await assetsApi.getBatchRun(batchRunId, { signal: opts.signal })
      if (seq !== requestSeq) return
      if (batchRunId !== unref(batchRunIdRef)) return
      batchDetail.value = result
    } catch (err) {
      if (seq !== requestSeq) return
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (err instanceof Error && err.name === 'CanceledError') return
      error.value = err instanceof Error ? err.message : '加载批次详情失败'
      console.error('useBatchDetail.loadBatchDetail failed', err)
    } finally {
      if (seq === requestSeq) {
        loading.value = false
        refreshing.value = false
      }
    }
  }

  function refreshDetail(opts?: { signal?: AbortSignal }): Promise<void> {
    return loadBatchDetail({ ...(opts || {}), silent: true })
  }

  async function retryFailed(): Promise<void> {
    const batchRunId = unref(batchRunIdRef)
    if (!batchRunId) return
    retryLoading.value = true
    try {
      await assetsApi.retryFailedBatchItems(batchRunId, { scope: 'failed' })
    } catch (err) {
      error.value = err instanceof Error ? err.message : '重跑失败执行项失败'
      throw err
    } finally {
      retryLoading.value = false
    }
  }

  async function cancelBatch(): Promise<void> {
    const batchRunId = unref(batchRunIdRef)
    if (!batchRunId) return
    const ok = typeof window !== 'undefined'
      ? window.confirm('确认取消该批次？已启动的 AWX Job 会被请求 cancel，未启动的 dispatch 不会下发。')
      : true
    if (!ok) return
    cancelLoading.value = true
    try {
      await assetsApi.cancelBatchRun(batchRunId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '取消批次失败'
      throw err
    } finally {
      cancelLoading.value = false
    }
  }

  function reset() {
    requestSeq++
    batchDetail.value = null
    error.value = ''
    loading.value = false
    refreshing.value = false
  }

  return {
    batchDetail,
    loading,
    refreshing,
    error,
    retryLoading,
    cancelLoading,
    loadBatchDetail,
    refreshDetail,
    retryFailed,
    cancelBatch,
    reset,
  }
}