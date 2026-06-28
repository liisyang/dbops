/**
 * utils/uuid.ts — 跨环境安全的 UUID v4 生成
 *
 * 背景：crypto.randomUUID() 是 Web Crypto API，在 **非 secure context**
 * （HTTP + 非 localhost，例如 http://10.134.181.168:61088）下不可用 —
 * Chrome 直接抛 TypeError。Phase 3.6A Chat 上线时该 API 在 secure
 * context 下稳定，但运维内网常用 IP+HTTP 访问，导致 C5 上线后
 * "按发送按钮无反应 + Vue warn Unhandled error during execution of
 * component event handler" 的现场 bug。
 *
 * 策略：
 * 1. 主路径：crypto.randomUUID() — secure context 下原生 API（性能最好）
 * 2. Fallback：基于 Math.random 的 RFC4122 v4 拼装，保证后端
 *    AiChatService 按 UUID 解析 client_request_id 时不报错
 *
 * 未来 Phase 3.6B（SQL Preview / Execute）也要用 client_request_id 做
 * 幂等，直接复用本函数即可。
 */

function fallbackUuidV4(): string {
  // RFC4122 v4: version 4 (random), variant 1 (RFC4122)
  const rnd = (): number => Math.floor(Math.random() * 0x100)
  const bytes: number[] = Array.from({ length: 16 }, rnd)
  bytes[6] = (bytes[6] & 0x0f) | 0x40 // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // variant 10
  const hex = bytes.map((b) => b.toString(16).padStart(2, '0')).join('')
  return (
    hex.slice(0, 8) +
    '-' +
    hex.slice(8, 12) +
    '-' +
    hex.slice(12, 16) +
    '-' +
    hex.slice(16, 20) +
    '-' +
    hex.slice(20, 32)
  )
}

/** 跨环境 UUID v4 生成（secure context 主路径 + 非 secure context fallback）。 */
export function safeUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID()
    } catch {
      // 部分浏览器版本下 API 存在但调用仍抛（如 cross-origin isolated 未就绪）
      // → 静默走 fallback
    }
  }
  return fallbackUuidV4()
}
