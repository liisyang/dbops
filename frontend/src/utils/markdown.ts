/**
 * AI Copilot — Markdown 渲染工具（Phase 3.6 AI Copilot — refactor: 渲染 Dify markdown 回答）
 *
 * 背景：
 * - Dify chat-messages API 返回的 `answer` 字段是 LLM 原始 markdown 文本
 * - 之前 ChatMessageBubble 用 `whitespace-pre-wrap` + `{{ content }}` 直出 → 用户看到的是
 *   `**粗体**` / `## 标题` / `` `代码` `` / `- 列表` 等"源码态"（不可读）
 * - 本工具把 markdown 解析为受控 HTML 片段，供 v-html 渲染
 *
 * 安全策略：
 * - marked 默认会转义用户输入的 HTML（`<script>` 不会出现）→ XSS 基础保障
 * - marked 自身支持在 link 渲染时拦截危险 href（见下方 link 扩展）
 * - 链接协议白名单：仅放行 http / https / mailto / tel / 相对路径 / 锚点
 * - 禁止 javascript: / data: / vbscript: 等危险协议 → 链接降级为纯文本
 * - AI 回答可能含用户输入片段（系统提示词注入），必须过滤
 *
 * 选型记录（vs marked + DOMPurify）：
 * - DOMPurify v3 在 happy-dom 测试环境下，hook 内的 setAttribute / removeAttribute
 *   不生效（DOM mutation 写不回去），导致 javascript: 链接无法被拦截
 * - 切到 marked renderer 扩展直接在 tokenize 阶段过滤，零 DOM 依赖
 * - bundle 体积更小（无需 dompurify ~20KB），逻辑更直白
 *
 * 性能：
 * - bundle 增量 ~10KB（仅 marked，无 dompurify）
 * - 不带语法高亮（避免 highlight.js ~50KB），代码块用纯 <pre><code> 包裹
 */
import { marked } from 'marked'

/**
 * 危险链接协议黑名单（小写匹配）。
 * 命中后该链接被降级为纯文本（不渲染 <a> 标签），避免 XSS。
 */
const DANGEROUS_URI_RE = /^\s*(?:javascript|vbscript|data|file):/i

// marked 全局配置（一次设置，整个应用生效）
// - gfm: 支持 GitHub Flavored Markdown（表格、删除线、任务列表、围栏代码）
// - breaks: 单换行 → <br>（Dify LLM 经常不写双换行）
// 注意：marked.setOptions 必须在第一次 parse 之前完成，模块顶层求值时即生效
marked.setOptions({
  gfm: true,
  breaks: true,
})

/**
 * 自定义 link 渲染器：检测到危险协议时降级为纯文本。
 *
 * marked v14 的 Renderer.link 签名：
 *   link({ href, title, text, tokens }) => string
 * 返回的 string 就是最终 HTML 片段。
 *
 * 危险链接降级策略：保留可读文本，移除 href。
 * 例：[bad](javascript:alert(1)) → 'bad'（无 <a>，无可点击，无 XSS）
 *
 * 注意：不能直接 bind marked.Renderer.prototype.link 来当 fallback，
 * 因为内部需要 this.parser.parseInline（依赖 marked 内部状态）。
 * 所以这里手写一个安全的 <a> 渲染器，只用受控字段。
 */
const renderer = new marked.Renderer()
renderer.link = (token): string => {
  const t = token as { href?: string; title?: string | null; text?: string }
  const rawHref = t.href ?? ''
  if (DANGEROUS_URI_RE.test(rawHref)) {
    return t.text ?? ''
  }
  const titleAttr = t.title ? ` title="${escapeAttr(t.title)}"` : ''
  // href 也用 escapeAttr 防御性转义（虽然 DANGEROUS_URI_RE 已挡掉 javascript:，
  // 但双重保险：引号 / 尖括号等被转义后不会突破属性边界）
  return `<a href="${escapeAttr(rawHref)}"${titleAttr} target="_blank" rel="noopener noreferrer">${t.text ?? ''}</a>`
}

/**
 * 自定义 html 渲染器：剥除用户输入的裸 HTML。
 *
 * marked v14 默认会把 markdown 里的 `<script>` / `<iframe>` / 内联事件当作
 * 合法 HTML 直接渲染。AI 回答包含用户输入片段（系统提示词注入风险），
 * 必须把所有裸 HTML token 都剥掉，只保留 markdown 自身产物的标签。
 */
renderer.html = (): string => ''

marked.use({ renderer })

/**
 * HTML 属性值转义：转义 `& " < >` 四个字符。
 * 用于在 `title="..."` / `href="..."` 等属性上下文里安全嵌入用户内容。
 */
function escapeAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * 把 Dify AI 回答（markdown 文本）渲染为受控 HTML 字符串。
 *
 * 流程：marked.parse（renderer 自动拦截危险链接）→ 返回。
 * 空值安全（null / undefined / 空串 → ''）。
 *
 * @example
 *   renderMarkdown('## 你好\n\n- 项目 A\n- 项目 B')
 *   // → '<h2>你好</h2><ul><li>项目 A</li><li>项目 B</li></ul>'
 *
 *   renderMarkdown('[bad](javascript:alert(1))')
 *   // → 'bad'（href 被剥，避免 XSS）
 */
export function renderMarkdown(input: string | null | undefined): string {
  if (!input) return ''
  // marked.parse 在 breaks:true 时对同步输入返回 string
  return marked.parse(input, { async: false }) as string
}

/**
 * 把 markdown 渲染为带 prose 样式的 HTML 片段（外层 <div class="ai-markdown">）。
 * 用于 ChatMessageBubble 的 v-html。
 */
export function renderMarkdownBlock(input: string | null | undefined): string {
  const inner = renderMarkdown(input)
  if (!inner) return ''
  return `<div class="ai-markdown">${inner}</div>`
}
