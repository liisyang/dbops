/**
 * describePreviewError — C16-F2c1 reason-aware 文案回归
 *
 * 覆盖：plan §11.4 + F2b 5 类新异常 + snapshot_unavailable 4 种 reason
 *
 * 历史回归（C16-F2c1 修复）：
 * - 前 snapshot_unavailable 错误文案硬编码为「请先在实例详情页触发 Schema 采集」，
 *   对 snapshot_expired (TTL 已过) 场景有误导（用户其实已经触发过，
 *   只是 TTL 到了）。改为按 reason 分别给出与根因匹配的处置文案。
 */
import { describe, expect, it } from 'vitest'

import { describePreviewError } from './previewError'

interface FakeAxiosErr {
  response?: {
    status?: number
    data?: { detail?: unknown }
  }
}

function makeErr(status: number, detail: unknown): FakeAxiosErr {
  return { response: { status, data: { detail } } }
}

describe('describePreviewError — C16-F2c1 reason-aware snapshot_unavailable', () => {
  it('snapshot_expired → 明确告知 TTL 默认 24h + 重新触发采集', () => {
    const err = makeErr(409, {
      code: 'snapshot_unavailable',
      reason: 'snapshot_expired',
      message:
        'schema snapshot unavailable for instance 961: reason=snapshot_expired',
    })
    const msg = describePreviewError(err)
    expect(msg).toContain('Schema 快照已过期')
    expect(msg).toContain('snapshot_expired')
    expect(msg).toContain('TTL 默认 24h')
    expect(msg).toContain('重新触发 Schema 采集')
    // 关键回归：旧硬编码文案不应再出现
    expect(msg).not.toBe(
      'Schema 快照不可用（409 snapshot_expired）：请先在实例详情页触发 Schema 采集。',
    )
  })

  it('snapshot_not_current → 等待新采集完成', () => {
    const err = makeErr(409, {
      code: 'snapshot_unavailable',
      reason: 'snapshot_not_current',
      message: '...',
    })
    expect(describePreviewError(err)).toContain('snapshot_not_current')
    expect(describePreviewError(err)).toContain('等待当前采集完成')
  })

  it('snapshot_not_success → 等待 callback 完成', () => {
    const err = makeErr(409, {
      code: 'snapshot_unavailable',
      reason: 'snapshot_not_success',
      message: '...',
    })
    expect(describePreviewError(err)).toContain('snapshot_not_success')
    expect(describePreviewError(err)).toContain('等待最新一次采集回调')
  })

  it('no_snapshot → 提示触发首次采集（旧通用文案兜底）', () => {
    const err = makeErr(409, {
      code: 'snapshot_unavailable',
      reason: 'no_snapshot',
      message: '...',
    })
    expect(describePreviewError(err)).toContain('no_snapshot')
    expect(describePreviewError(err)).toContain('请先在实例详情页触发 Schema 采集')
  })

  it('preview_incomplete_retry_required → 重发即可（user_message_id 注入）', () => {
    const err = makeErr(409, {
      code: 'preview_incomplete_retry_required',
      user_message_id: 12345,
      message: 'interrupted',
    })
    const msg = describePreviewError(err)
    expect(msg).toContain('user_message #12345')
    expect(msg).toContain('重发')
  })

  it('403/404/422/502/503/504 状态码文案未回归', () => {
    expect(describePreviewError(makeErr(403, { message: 'denied' }))).toContain('403')
    expect(describePreviewError(makeErr(404, { message: 'not found' }))).toContain('404')
    expect(describePreviewError(makeErr(422, { message: 'invalid' }))).toContain('422')
    expect(describePreviewError(makeErr(502, { message: 'bad gateway' }))).toContain('502')
    expect(describePreviewError(makeErr(503, ''))).toContain('AI_SQL_PREVIEW_ENABLED')
    expect(describePreviewError(makeErr(504, ''))).toContain('504')
  })
})