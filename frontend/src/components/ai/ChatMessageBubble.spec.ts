/**
 * ChatMessageBubble — sql_result 卡片操作按钮 C15 单测
 *
 * 覆盖范围：
 *  - sql_result 卡片 metadata_json 提 audit_id
 *  - 重新执行按钮可见性（failed/timeout/cancelled 才显示；success 不显示）
 *  - 重新执行按钮禁用态（pendingAuditIds 命中时）
 *  - 已完成徽章（success 终态时显示）
 *  - 查看详情按钮始终可点
 *
 * 注意：所有断言作用域在 [data-testid="sql-result-actions"] 内，避开
 * ChatStatusBadge 同时渲染"已完成"造成的混淆（消息 lifecycle status vs.
 * audit execution status 是两个独立维度）。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChatMessageBubble from './ChatMessageBubble.vue'

function makeResultMessage(
  status: string,
  auditId: number,
  extras: Record<string, unknown> = {},
) {
  return {
    role: 'assistant' as const,
    status: 'completed' as const,
    messageType: 'sql_result' as const,
    content: JSON.stringify({
      columns: ['id', 'name'],
      rows: [[1, 'alice']],
      row_count: 1,
      duration_ms: 24,
      status,
      error_message: status === 'failed' ? 'syntax error near WHERE' : null,
    }),
    metadataJson: {
      audit_id: auditId,
      execution_status: status,
      row_count: 1,
      duration_ms: 24,
      ...extras,
    },
  }
}

/** 提取 C15 新增的操作按钮区（屏蔽 ChatStatusBadge 的"已完成"干扰）。 */
function actionsText(wrapper: ReturnType<typeof mount>) {
  const row = wrapper.find('[data-testid="sql-result-actions"]')
  return row.exists() ? row.text() : ''
}

describe('ChatMessageBubble — sql_result 操作按钮（C15）', () => {
  it('success 终态 → 「已完成」徽章显示，「重新执行」按钮不显示', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('success', 100),
    })
    const txt = actionsText(wrapper)
    expect(txt).toContain('已完成')
    expect(txt).not.toContain('重新执行')
    // 查看详情按钮始终可见
    const buttons = wrapper.findAll('[data-testid="sql-result-actions"] button')
    const viewBtn = buttons.find((b) => b.text().includes('查看详情'))
    expect(viewBtn, '查看详情 button must exist').toBeDefined()
  })

  it('failed 终态 → 「重新执行」按钮可见，点击 emit re-execute with audit_id', async () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('failed', 200),
    })
    expect(actionsText(wrapper)).toContain('重新执行')

    const reBtn = wrapper
      .findAll('[data-testid="sql-result-actions"] button')
      .find((b) => b.text().includes('重新执行'))!
    await reBtn.trigger('click')

    const events = wrapper.emitted('re-execute')
    expect(events, 're-execute event must fire').toBeDefined()
    expect(events![0]).toEqual([200])
  })

  it('timeout 终态 → 「重新执行」按钮可见', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('timeout', 300),
    })
    expect(actionsText(wrapper)).toContain('重新执行')
  })

  it('cancelled 终态 → 「重新执行」按钮可见', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('cancelled', 400),
    })
    expect(actionsText(wrapper)).toContain('重新执行')
  })

  it('pending/running 非终态 + 不在轮询 → 「重新执行」与「已完成」徽章都不显示', () => {
    const wrapperPending = mount(ChatMessageBubble, {
      props: makeResultMessage('pending', 500),
    })
    const txtPending = actionsText(wrapperPending)
    expect(txtPending).not.toContain('重新执行')
    expect(txtPending).not.toContain('已完成')
    // 没在轮询时也不应显示「执行中…」
    expect(txtPending).not.toContain('执行中')

    const wrapperRunning = mount(ChatMessageBubble, {
      props: makeResultMessage('running', 600),
    })
    const txtRunning = actionsText(wrapperRunning)
    expect(txtRunning).not.toContain('重新执行')
    expect(txtRunning).not.toContain('已完成')
  })

  it('pending 非终态 + 在轮询（pendingAuditIds 命中）→ 「执行中…」徽章显示', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        ...makeResultMessage('pending', 700),
        pendingAuditIds: new Set([700]),
      },
    })
    const txt = actionsText(wrapper)
    expect(txt).toContain('执行中')
    expect(txt).not.toContain('重新执行')
    expect(txt).not.toContain('已完成')
  })

  it('查看详情按钮 → 点击 emit view-detail with audit_id', async () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('success', 800),
    })
    const viewBtn = wrapper
      .findAll('[data-testid="sql-result-actions"] button')
      .find((b) => b.text().includes('查看详情'))!
    await viewBtn.trigger('click')

    const events = wrapper.emitted('view-detail')
    expect(events, 'view-detail event must fire').toBeDefined()
    expect(events![0]).toEqual([800])
  })

  it('failed 时 + pendingAuditIds 命中（自己）→ 「重新执行」按钮 disabled', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        ...makeResultMessage('failed', 900),
        pendingAuditIds: new Set([900]),
      },
    })
    const reBtn = wrapper
      .findAll('[data-testid="sql-result-actions"] button')
      .find((b) => b.text().includes('重新执行'))!
    expect((reBtn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('failed 时 + 其他 audit 在轮询（pendingAuditIds 不命中）→「重新执行」按钮 enabled', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        ...makeResultMessage('failed', 950),
        pendingAuditIds: new Set([999]),
      },
    })
    const reBtn = wrapper
      .findAll('[data-testid="sql-result-actions"] button')
      .find((b) => b.text().includes('重新执行'))!
    expect((reBtn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('没有 audit_id 的 sql_result → 不渲染操作按钮区（testid 不存在）', () => {
    const props = makeResultMessage('failed', 0)
    const wrapper = mount(ChatMessageBubble, {
      props: {
        ...props,
        metadataJson: {
          execution_status: 'failed',
          row_count: 1,
          duration_ms: 24,
        },
      },
    })
    // 没有 audit_id → resultAuditId == null → 整个 actions div 都不渲染
    expect(wrapper.find('[data-testid="sql-result-actions"]').exists()).toBe(false)
  })
})

