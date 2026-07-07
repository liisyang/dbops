/**
 * markdown 渲染工具单测
 *
 * 覆盖：
 *  - 空值兜底（null / undefined / '' / 纯空白）
 *  - 标题 / 加粗 / 列表 / 行内代码 / 围栏代码块（gfm 能力）
 *  - 单换行 → <br>（breaks:true 行为）
 *  - HTML 注入过滤：<script>/onerror= → 被剥除
 *  - 危险链接：javascript: / data: → 被剥除
 *  - renderMarkdownBlock 包一层 <div class="ai-markdown">
 */
import { describe, expect, it } from 'vitest'

import { renderMarkdown, renderMarkdownBlock } from './markdown'

describe('renderMarkdown — 空值兜底', () => {
  it('null → 空串', () => {
    expect(renderMarkdown(null)).toBe('')
  })
  it('undefined → 空串', () => {
    expect(renderMarkdown(undefined)).toBe('')
  })
  it('空串 → 空串', () => {
    expect(renderMarkdown('')).toBe('')
  })
})

describe('renderMarkdown — 基础 markdown', () => {
  it('H2 标题', () => {
    const out = renderMarkdown('## 你好')
    expect(out).toContain('<h2')
    expect(out).toContain('你好')
  })

  it('加粗 + 斜体', () => {
    const out = renderMarkdown('**bold** and *em*')
    expect(out).toContain('<strong>bold</strong>')
    expect(out).toContain('<em>em</em>')
  })

  it('无序列表', () => {
    const out = renderMarkdown('- 项目 A\n- 项目 B')
    expect(out).toContain('<ul>')
    expect(out).toContain('<li>项目 A</li>')
    expect(out).toContain('<li>项目 B</li>')
  })

  it('行内代码', () => {
    const out = renderMarkdown('使用 `SELECT *` 查询')
    expect(out).toContain('<code>SELECT *</code>')
  })

  it('围栏代码块（保留多行）', () => {
    const out = renderMarkdown('```sql\nSELECT *\nFROM t;\n```')
    expect(out).toContain('<pre>')
    expect(out).toContain('<code')
    expect(out).toContain('SELECT *')
    expect(out).toContain('FROM t;')
  })

  it('单换行 → <br>（breaks:true）', () => {
    const out = renderMarkdown('第一行\n第二行')
    expect(out).toContain('<br')
  })

  it('链接允许 http/https', () => {
    const out = renderMarkdown('[官网](https://example.com)')
    expect(out).toContain('href="https://example.com"')
  })
})

describe('renderMarkdown — XSS 过滤（marked + 危险协议拦截）', () => {
  it('剥除 <script> 标签（html 渲染器返回空）', () => {
    const out = renderMarkdown('hello <script>alert(1)</script> world')
    // <script> 标签本身被剥除；内联文本按 marked 默认行为保留（视为文本节点）
    expect(out).not.toContain('<script>')
    expect(out).toContain('hello')
    expect(out).toContain('world')
  })

  it('合法 markdown 仍然渲染', () => {
    const out = renderMarkdown('**safe**')
    expect(out).toContain('<strong>safe</strong>')
  })

  it('javascript: 链接降级为纯文本（不渲染 <a> 标签）', () => {
    const out = renderMarkdown('[bad](javascript:alert(1))')
    expect(out).not.toContain('href=')
    expect(out).not.toContain('javascript:')
    expect(out).toContain('bad')
  })

  it('data: URL 链接降级为纯文本', () => {
    const out = renderMarkdown('[bad](data:text/html,<x>)')
    expect(out).not.toContain('href=')
    expect(out).not.toContain('data:')
    expect(out).toContain('bad')
  })

  it('vbscript: 链接降级为纯文本', () => {
    const out = renderMarkdown('[bad](vbscript:msgbox(1))')
    expect(out).not.toContain('href=')
    expect(out).not.toContain('vbscript:')
  })

  it('合法 http/https 链接保留 <a href>', () => {
    const out = renderMarkdown('[官网](https://example.com)')
    expect(out).toContain('href="https://example.com"')
    expect(out).toContain('官网')
  })

  it('合法 mailto 链接保留', () => {
    const out = renderMarkdown('[联系](mailto:a@b.com)')
    expect(out).toContain('href="mailto:a@b.com"')
  })

  it('相对路径链接保留', () => {
    const out = renderMarkdown('[docs](/docs/intro)')
    expect(out).toContain('href="/docs/intro"')
  })

  it('锚点链接保留', () => {
    const out = renderMarkdown('[section](#section)')
    expect(out).toContain('href="#section"')
  })
})

describe('renderMarkdownBlock — 外层包裹', () => {
  it('外层包 <div class="ai-markdown">', () => {
    const out = renderMarkdownBlock('**bold**')
    expect(out).toMatch(/^<div class="ai-markdown">/)
    expect(out).toMatch(/<\/div>$/)
    expect(out).toContain('<strong>bold</strong>')
  })

  it('空输入 → 空串（不返回空 div）', () => {
    expect(renderMarkdownBlock('')).toBe('')
    expect(renderMarkdownBlock(null)).toBe('')
  })
})
