/*
 * useBatchPolling — 详情页 5s 轮询
 *
 * 关键设计：
 * - 递归 setTimeout：tick 完成后再排下一轮，避免并发 tick
 * - AbortController：每次 tick 创建新 controller
 * - 失败时把 err.message 写到 pollError，不停轮询、不清空详情
 * - 终态自停：isTerminalBatchStatus(getStatus()) 时 stopPolling()
 * - startPolling 默认不立即 tick
 * - composable 内部独享 onBeforeUnmount
 * - 返回 isPolling：避免与详情页派生 isRunning 命名冲突
 */

import { onBeforeUnmount, ref, unref, type Ref } from 'vue'
import { isTerminalBatchStatus } from '../utils/batchVerifyFormatters'

export interface UseBatchPollingOptions {
  batchRunIdRef: Ref<number | null>
  getStatus: () => string | null
  onTick: (signal: AbortSignal) => Promise<void>
}

export interface StartPollingOptions {
  immediate?: boolean
}

const POLL_INTERVAL = 5000

export function useBatchPolling(opts: UseBatchPollingOptions) {
  const pollError = ref('')
  const isPolling = ref(false)

  let timer: number | null = null
  let controller: AbortController | null = null
  let stopped = true

  async function tick() {
    if (stopped) return
    controller?.abort()
    const currentController = new AbortController()
    controller = currentController
    try {
      await opts.onTick(currentController.signal)
      pollError.value = ''
      if (isTerminalBatchStatus(opts.getStatus())) {
        stopPolling()
        return
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (err instanceof Error && err.name === 'CanceledError') return
      pollError.value = err instanceof Error ? err.message : '轮询批次状态失败'
      console.error('useBatchPolling.tick failed', err)
    } finally {
      if (controller?.signal === currentController.signal) {
        controller = null
      }
    }
    if (!stopped) {
      timer = window.setTimeout(tick, POLL_INTERVAL)
    }
  }

  function startPolling(options: StartPollingOptions = {}) {
    stopPolling()
    if (!unref(opts.batchRunIdRef)) return
    if (isTerminalBatchStatus(opts.getStatus())) return
    stopped = false
    isPolling.value = true
    if (options.immediate) {
      void tick()
    } else {
      timer = window.setTimeout(tick, POLL_INTERVAL)
    }
  }

  function stopPolling() {
    stopped = true
    isPolling.value = false
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
    controller?.abort()
    controller = null
  }

  onBeforeUnmount(stopPolling)

  return {
    pollError,
    isPolling,
    startPolling,
    stopPolling,
  }
}