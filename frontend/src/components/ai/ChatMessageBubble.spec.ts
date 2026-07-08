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
    // 执行详情按钮始终可见（C16-5：原"查看详情" →"执行详情"以与 plan §21.3 命名统一）
    const buttons = wrapper.findAll('[data-testid="sql-result-actions"] button')
    const viewBtn = buttons.find((b) => b.text().includes('执行详情'))
    expect(viewBtn, '执行详情 button must exist').toBeDefined()
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

  it('执行详情按钮 → 点击 emit view-detail with audit_id', async () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('success', 800),
    })
    const viewBtn = wrapper
      .findAll('[data-testid="sql-result-actions"] button')
      .find((b) => b.text().includes('执行详情'))!
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

/* ------------------------------------------------------------------ *
 * Refactor — hide ``：前端兜底剥离
 *
 * 验证 ChatMessageBubble 的 displayContent computed 对 chat 气泡内容剥离
 *  ``...`` 块（后端 DifyService.chat_message 已做权威剥离，本处为
 * 显示层最后防线）。
 * ------------------------------------------------------------------ */

describe('ChatMessageBubble — hide 块（Refactor 兜底）', () => {
  const T_OPEN = '\<think\>'
  const T_CLOSE = '\</think\>'

  it('chat 气泡：剥离单个 块，仅显示 answer', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: `${T_OPEN}模型推理过程${T_CLOSE}\n\n你好，我可以帮你查 Schema。`,
      },
    })
    const text = wrapper.text()
    expect(text).not.toContain('模型推理过程')
    expect(text).not.toContain(T_OPEN)
    expect(text).not.toContain(T_CLOSE)
    expect(text).toContain('你好')
  })

  it('chat 气泡：无 块时原样显示', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '这是普通回答。',
      },
    })
    expect(wrapper.text()).toContain('这是普通回答')
  })

  it('sql_result 卡片内容分支不受前端剥离影响（保留 JSON 原文渲染）', () => {
    // sql_result 的 content 是 JSON 字符串，渲染走 metadata 解析分支；剥离不应触发
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('success', 1100),
    })
    // sql_result 卡片渲染表格，不应被剥离逻辑误伤
    expect(wrapper.find('table').exists()).toBe(true)
  })
})

/* ------------------------------------------------------------------ *
 * Refactor — render markdown（C15+）：assistant / system 气泡用 v-html
 * 输出 marked 渲染的 HTML，user 气泡保持纯文本。
 * ------------------------------------------------------------------ */

describe('ChatMessageBubble — render markdown（Refactor）', () => {
  it('assistant chat 气泡：H2 渲染为 <h2>', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '## 你好',
      },
    })
    const md = wrapper.find('[data-testid="ai-markdown-body"]')
    expect(md.exists()).toBe(true)
    expect(md.html()).toContain('<h2>')
    expect(md.text()).toContain('你好')
  })

  it('assistant chat 气泡：**加粗** 渲染为 <strong>', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '这是 **重要** 内容',
      },
    })
    const md = wrapper.find('[data-testid="ai-markdown-body"]')
    expect(md.html()).toContain('<strong>')
    expect(md.html()).toContain('重要')
  })

  it('assistant chat 气泡：- 列表 渲染为 <ul><li>', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '- 项目 A\n- 项目 B',
      },
    })
    const md = wrapper.find('[data-testid="ai-markdown-body"]')
    expect(md.find('ul').exists()).toBe(true)
    expect(md.findAll('li').length).toBe(2)
  })

  it('assistant chat 气泡：```围栏代码块``` 渲染为 <pre><code>', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '```sql\nSELECT *\nFROM t;\n```',
      },
    })
    const md = wrapper.find('[data-testid="ai-markdown-body"]')
    expect(md.find('pre').exists()).toBe(true)
    expect(md.find('pre code').exists()).toBe(true)
    expect(md.text()).toContain('SELECT *')
  })

  it('assistant chat 气泡：危险链接 javascript: 降级为纯文本', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '[点我](javascript:alert(1))',
      },
    })
    const md = wrapper.find('[data-testid="ai-markdown-body"]')
    expect(md.find('a').exists()).toBe(false)
    expect(md.text()).toContain('点我')
    expect(md.html()).not.toContain('javascript:')
  })

  it('assistant chat 气泡：合法 http 链接保留 <a href>', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '[官网](https://example.com)',
      },
    })
    const md = wrapper.find('[data-testid="ai-markdown-body"]')
    const a = md.find('a')
    expect(a.exists()).toBe(true)
    expect(a.attributes('href')).toBe('https://example.com')
    expect(a.text()).toBe('官网')
  })

  it('user 气泡：保持纯文本（不渲染 markdown）', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'user',
        status: 'completed',
        messageType: 'chat',
        content: '## 这是用户输入',
      },
    })
    // user 气泡不渲染 v-html → 没有 ai-markdown-body testid
    expect(wrapper.find('[data-testid="ai-markdown-body"]').exists()).toBe(false)
    // 但纯文本内容应该出现
    expect(wrapper.text()).toContain('## 这是用户输入')
  })

  it('sql_result 卡片：不受 markdown 渲染影响（仍走 metadata 解析）', () => {
    // sql_result 走 v-else-if 分支，不会进入 markdown 渲染逻辑
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('success', 1200),
    })
    expect(wrapper.find('[data-testid="ai-markdown-body"]').exists()).toBe(false)
    expect(wrapper.find('table').exists()).toBe(true)
  })

  it('error 文案：assistant 气泡也走 markdown 渲染', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'failed',
        messageType: 'error',
        errorCode: 'TIMEOUT',
        errorMessage: '请求 **超时**，请重试',
        content: '请求 **超时**，请重试',
      },
    })
    const md = wrapper.find('[data-testid="ai-markdown-body"]')
    expect(md.exists()).toBe(true)
    expect(md.html()).toContain('<strong>')
  })
})

/**
 * ChatMessageBubble — sql_preview_link previewLinkMeta 5 分支（C16-F2c + F17 跨入口回归）
 *
 * 背景（F17 — plan §21.3 C16-4 末尾）：
 * - form 模式（SqlPreview.vue 表单提交）写 ai_sql_audit + 双消息（user + preview_message）；
 *   source_page='sql_preview_legacy'，落 message_type='sql_preview_link'
 * - Chat 模式（InstanceDetail 「AI 查询」→ Chat.vue onSend 分流）走同一 F2b 双消息事务，
 *   source_page='instance_detail'
 * - 两条入口的 preview_message 经 listMessages 回到前端，必须被 previewLinkMeta
 *   正确解析为 passed/rejected 卡片（合并 metadata_json 的 audit_id/status +
 *   content JSON 的 SQL 详情 / 拒绝原因）
 *
 * 5 分支必须全覆盖（C16-F2c 已实现 + F17 补回归）：
 *  1. passed + content 含 approved_sql            → 绿框卡 + 「执行 SQL」按钮
 *  2. passed + content 缺 approved_sql（脏数据）   → previewLinkMeta=null，不渲染卡
 *  3. rejected + content.reason                   → 红框 + 「SQL Preview 被拒绝」+ reason
 *  4. rejected + content 缺 reason                → 红框 + 「（拒绝原因未提供）」
 *  5. sql_preview_link + 非 JSON content（历史脏）→ previewLinkMeta=null，不渲染卡
 *  6. messageType='chat' + 任意 metadata/content   → 普通气泡，不渲染预览卡
 */
describe('ChatMessageBubble — sql_preview_link previewLinkMeta（C16-F2c + F17 跨入口一致性回归）', () => {
  /**
   * 构造 sql_preview_link 卡片消息 props；metadataJson/content 字段由测试自定义。
   * preview_safety_status 默认 'passed'，与 F2c metadata_json schema 对齐。
   */
  function makeSqlPreviewLinkMessage(opts: {
    auditId: number
    status: 'passed' | 'rejected'
    contentJson: string | null
    rawContent?: string
    metadataExtras?: Record<string, unknown>
  }) {
    return {
      role: 'assistant' as const,
      status: 'completed' as const,
      messageType: 'sql_preview_link' as const,
      content:
        opts.contentJson !== null ? opts.contentJson : opts.rawContent ?? null,
      metadataJson: {
        audit_id: opts.auditId,
        preview_safety_status: opts.status,
        instance_id: 965,
        ...(opts.metadataExtras ?? {}),
      },
    }
  }

  // 关键字常量（与 .vue 模板第 50 / 83 行一对一）
  const PASSED_TITLE_PREFIX = '已通过的 SQL'
  const REJECTED_TITLE_PREFIX = 'SQL Preview 被拒绝'

  it('case 1 (passed + content 含 approved_sql) → 渲染绿框卡 + 执行按钮 + 透传 audit_id', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeSqlPreviewLinkMessage({
        auditId: 100,
        status: 'passed',
        contentJson: JSON.stringify({
          approved_sql: 'SELECT id, name FROM users WHERE status = $1',
          approved_sql_hash: 'sha256:abc',
          schema_policy_hash: 'sha256:def',
        }),
      }),
    })
    const txt = wrapper.text()
    expect(txt).toContain(PASSED_TITLE_PREFIX)
    expect(txt).toContain('audit #100')
    // 执行 SQL 按钮（按钮文案：执行 SQL；见模板第 64 行）
    expect(txt).toContain('执行 SQL')
    // approved_sql 渲染到 <pre><code>
    expect(wrapper.find('pre code').text()).toBe(
      'SELECT id, name FROM users WHERE status = $1',
    )
    // rejected 分支不应出现
    expect(txt).not.toContain(REJECTED_TITLE_PREFIX)
  })

  it('case 2 (passed + content 缺 approved_sql 脏数据) → previewLinkMeta=null，不渲染预览卡', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeSqlPreviewLinkMessage({
        auditId: 101,
        status: 'passed',
        // 罕见情况：metadata 写 passed 但 content 没有 approved_sql（应为脏数据，
        // previewLinkMeta computed 会因 approved_sql 缺失返回 null）
        contentJson: JSON.stringify({ reason: '前端不应到达该分支' }),
      }),
    })
    const txt = wrapper.text()
    expect(txt).not.toContain(PASSED_TITLE_PREFIX)
    expect(txt).not.toContain(REJECTED_TITLE_PREFIX)
    expect(txt).not.toContain('执行 SQL')
  })

  it('case 3 (rejected + content.reason) → 渲染红框卡 + 「SQL Preview 被拒绝」+ reason + 无执行按钮', () => {
    const reason = '检测到 DELETE，与「只读」安全策略冲突'
    const wrapper = mount(ChatMessageBubble, {
      props: makeSqlPreviewLinkMessage({
        auditId: 200,
        status: 'rejected',
        contentJson: JSON.stringify({
          reason,
          // 兼容：rejected 也可能带 generated_sql，但不应渲染
          approved_sql: 'DELETE FROM users',
        }),
      }),
    })
    const txt = wrapper.text()
    expect(txt).toContain(REJECTED_TITLE_PREFIX)
    expect(txt).toContain('audit #200')
    expect(txt).toContain(reason)
    // 无执行按钮（防止 F2b P1-3 rejected 也写 preview_message 后误触 execute）
    expect(txt).not.toContain('执行 SQL')
    // 没渲染绿框卡
    expect(txt).not.toContain(PASSED_TITLE_PREFIX)
  })

  it('case 4 (rejected + content 缺 reason 兜底) → 红框 + 「（拒绝原因未提供）」', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeSqlPreviewLinkMessage({
        auditId: 201,
        status: 'rejected',
        contentJson: JSON.stringify({}), // 无 reason 字段
      }),
    })
    const txt = wrapper.text()
    expect(txt).toContain(REJECTED_TITLE_PREFIX)
    expect(txt).toContain('audit #201')
    // 兜底文案（previewLinkMeta 计算属性 fallback）
    expect(txt).toContain('（拒绝原因未提供）')
    // 仍然无执行按钮
    expect(txt).not.toContain('执行 SQL')
  })

  it('case 5 (sql_preview_link + 非 JSON content 历史脏数据) → previewLinkMeta=null，不渲染卡', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeSqlPreviewLinkMessage({
        auditId: 300,
        status: 'passed',
        contentJson: null,
        rawContent: '历史脏数据：纯文本 SQL（不是 JSON）',
      }),
    })
    const txt = wrapper.text()
    // 非 JSON content → previewLinkMeta 走空 payload，approved_sql 为空 → 返回 null
    expect(txt).not.toContain(PASSED_TITLE_PREFIX)
    expect(txt).not.toContain(REJECTED_TITLE_PREFIX)
    expect(txt).not.toContain('执行 SQL')
  })

  it('case 6 (messageType=chat) → 普通气泡，不渲染任何 sql_preview_link 卡', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'chat',
        content: '你好，我是一个普通的 chat 回复',
        metadataJson: { foo: 'bar' },
      },
    })
    const txt = wrapper.text()
    expect(txt).toContain('你好，我是一个普通的 chat 回复')
    expect(txt).not.toContain(PASSED_TITLE_PREFIX)
    expect(txt).not.toContain(REJECTED_TITLE_PREFIX)
    expect(txt).not.toContain('执行 SQL')
    // chat 走 markdown 渲染
    expect(wrapper.find('[data-testid="ai-markdown-body"]').exists()).toBe(true)
  })
})

/* ------------------------------------------------------------------ *
 * C16-5 — sql_result 状态配色 + 按钮命名统一 + 幂等渲染兜底
 *
 * 背景：
 * - 配色（C16-5 P0-4）：cancelled 终态独立配 zinc-500/15（与 SqlPreview.vue:913 对齐），
 *   之前 fallback sky-500/15 会让 cancelled 与 pending/running 视觉混淆
 * - 命名（C16-5 P0-4）：sql_result 卡片「查看详情」 →「执行详情」，与 plan §21.3 C16-5 命名统一
 * - 幂等（plan §4 risk #1）：callback 端在 ai_sql_audit 已为 success 时，
 *   不会重复落 sql_result message（后端 partial unique 兜底），但前端必须正确
 *   渲染所有 sql_result message（同 audit_id 出现两次时各渲染一张卡）
 * - Fallback（plan §6.5）：metadata_json 缺 execution_status 时，sqlResultPayload 应
 *   优先从 content JSON 解出 status，再回退到 metadata.execution_status
 * ------------------------------------------------------------------ */
describe('ChatMessageBubble — sql_result 状态配色（C16-5）', () => {
  /** 提取 sql_result 卡片右上角状态徽章（与 ChatStatusBadge 隔离）。 */
  function statusBadge(wrapper: ReturnType<typeof mount>): string {
    // sql_result 卡片的状态徽章 template line 103-105 使用 `text-[10px]`；
    // ChatStatusBadge 用 `text-[11px]`，靠字体大小区分避免误抓
    const card = wrapper.find('[data-testid="sql-result-actions"]')
    if (!card.exists()) return ''
    const scope = card.element.closest('.rounded-lg.border') ?? wrapper.element
    const badges = scope.querySelectorAll('span.rounded-full')
    for (const b of Array.from(badges) as HTMLElement[]) {
      if (b.className.includes('text-[10px]')) return b.className
    }
    return ''
  }

  it('cancelled → zinc-500/15 配色（不再 fallback sky）', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('cancelled', 1100),
    })
    const badge = statusBadge(wrapper)
    expect(badge).toContain('zinc-500/15')
    expect(badge).toContain('text-zinc-300')
    expect(badge).not.toContain('sky-500/15')
    expect(badge).not.toContain('text-sky-300')
  })

  it('success → emerald-500/15 配色', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('success', 1200),
    })
    const badge = statusBadge(wrapper)
    expect(badge).toContain('emerald-500/15')
    expect(badge).toContain('text-emerald-300')
  })

  it('failed → red-500/15 配色', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('failed', 1300),
    })
    const badge = statusBadge(wrapper)
    expect(badge).toContain('red-500/15')
    expect(badge).toContain('text-red-300')
  })

  it('timeout → amber-500/15 配色', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('timeout', 1400),
    })
    const badge = statusBadge(wrapper)
    expect(badge).toContain('amber-500/15')
    expect(badge).toContain('text-amber-300')
  })

  it('按钮命名统一：sql_result 卡片显示「执行详情」（plan §21.3 C16-5）', () => {
    const wrapper = mount(ChatMessageBubble, {
      props: makeResultMessage('success', 1500),
    })
    // 新增 data-testid 用于精准断言
    const viewBtn = wrapper.find('[data-testid="sql-result-view-detail"]')
    expect(viewBtn.exists(), '执行详情按钮必须存在').toBe(true)
    expect(viewBtn.text()).toContain('执行详情')
    expect(viewBtn.text()).not.toContain('查看详情')
  })

  it('callback 幂等兜底：metadata_json 缺 execution_status → 仍从 content JSON 解 status', () => {
    // 极端场景：callback 端序列化时 metadata_json 漏写 execution_status（脏数据），
    // sqlResultPayload 应回退到 content JSON 的 status 字段，保证操作按钮区可见
    const wrapper = mount(ChatMessageBubble, {
      props: {
        role: 'assistant',
        status: 'completed',
        messageType: 'sql_result',
        content: JSON.stringify({
          columns: ['id'],
          rows: [[1]],
          row_count: 1,
          duration_ms: 10,
          status: 'failed',
          error_message: '超时',
        }),
        metadataJson: {
          audit_id: 1600,
          // 故意省略 execution_status — content JSON 兜底
          row_count: 1,
          duration_ms: 10,
        },
      },
    })
    const txt = wrapper.text()
    // 「重新执行」按钮因 status='failed' 应可见（content JSON 解析生效）
    expect(txt).toContain('重新执行')
    // 卡片渲染（columns + rows）
    expect(wrapper.find('table').exists()).toBe(true)
  })
})
