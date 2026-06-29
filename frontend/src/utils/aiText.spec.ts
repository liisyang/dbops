/**
 * AI 文本处理工具 vitest 单测（Phase 3.6 — refactor: hide ``）
 */
import { describe, expect, it } from 'vitest'

import { hasThinkBlock, stripThinkBlocks } from './aiText'

const T_OPEN = '\<think\>'
const T_CLOSE = '\</think\>'
function t(body: string): string {
  return `${T_OPEN}${body}${T_CLOSE}`
}

describe('stripThinkBlocks', () => {
  it('returns plain text unchanged when no block present', () => {
    const text = '用户问：你好\n你好，我是 AI 助手。'
    expect(stripThinkBlocks(text)).toBe(text)
  })

  it('strips a single block, keeps the answer', () => {
    const text = `${t('我需要先想想用户的需求')}\n\n正式回答`
    expect(stripThinkBlocks(text)).toBe('正式回答')
  })

  it('strips multiple blocks independently (non-greedy)', () => {
    const text = `${t('思考 A')}\n\n答案1\n\n${t('思考 B')}\n\n答案2`
    expect(stripThinkBlocks(text)).toBe('答案1\n\n答案2')
  })

  it('handles multi-line content inside the block', () => {
    const text = `${t('第一行\n第二行\n第三行')}\n\n正式答案`
    expect(stripThinkBlocks(text)).toBe('正式答案')
  })

  it('collapses trailing blank lines to at most two', () => {
    const text = `${t('内部思考')}\n\n\n\n\n正式答案`
    expect(stripThinkBlocks(text)).toBe('正式答案')
  })

  it('returns empty string for only-block input', () => {
    expect(stripThinkBlocks(t('纯推理内容'))).toBe('')
  })

  it('strips blocks at start and end positions', () => {
    expect(stripThinkBlocks(`${t('开头')}\n\n中段`)).toBe('中段')
    expect(stripThinkBlocks(`中段\n\n${t('结尾')}`)).toBe('中段')
  })

  it('returns empty string for null/undefined/empty', () => {
    expect(stripThinkBlocks(null)).toBe('')
    expect(stripThinkBlocks(undefined)).toBe('')
    expect(stripThinkBlocks('')).toBe('')
  })

  it('preserves text containing the word "think" without tags', () => {
    expect(stripThinkBlocks('I think the answer is 42.')).toBe(
      'I think the answer is 42.',
    )
  })
})

describe('hasThinkBlock', () => {
  it('returns true when block present', () => {
    expect(hasThinkBlock(t('hello'))).toBe(true)
  })

  it('returns false when no block present', () => {
    expect(hasThinkBlock('plain answer')).toBe(false)
  })

  it('returns false for null/undefined/empty', () => {
    expect(hasThinkBlock(null)).toBe(false)
    expect(hasThinkBlock(undefined)).toBe(false)
    expect(hasThinkBlock('')).toBe(false)
  })
})
