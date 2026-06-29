"""
AI 文本处理工具单元测试（Phase 3.6 AI Copilot — refactor: hide ``）

覆盖：
- strip_think_blocks：单块 / 多行块 / 多块 / 空 / None / 前后文 / 折叠空行 / 嵌套代码块 / 大文本
- has_think_block：有 / 无 / None
"""
from __future__ import annotations

from app.services.ai_text import has_think_block, strip_think_blocks


def _t(body: str) -> str:
    """构造含 `` 块的文本 helper（fixture）。"""
    return "<think>" + body + "</think>"


# =============================================================================
# strip_think_blocks
# =============================================================================
def test_strip_simple_keeps_plain_text():
    """最基础的剥离：不含 `` 时原样返回。"""
    text = "用户问：你好\n你好，我是 AI 助手。"
    assert strip_think_blocks(text) == text


def test_strip_single_block_keeps_answer():
    """单个 `` 块剥离，保留 answer。"""
    text = f"{_t('我需要先想想用户的需求')}\n\n正式回答"
    out = strip_think_blocks(text)
    assert out == "正式回答"


def test_strip_multiple_blocks_keeps_answer():
    """多个不连续块剥离（regex 非贪婪）。"""
    text = f"{_t('思考 A')}\n\n答案1\n\n{_t('思考 B')}\n\n答案2"
    out = strip_think_blocks(text)
    assert out == "答案1\n\n答案2"


def test_strip_multiline_thinking():
    """跨多行 `` 内容。"""
    text = _t("第一行思路\n第二行思路\n第三行思路") + "\n\n正式答案第一行\n正式答案第二行"
    out = strip_think_blocks(text)
    assert out == "正式答案第一行\n正式答案第二行"


def test_strip_collapses_trailing_blank_lines():
    """剥离 `` 块后留下的连续空行折叠为最多 2 个。"""
    text = _t("内部思考") + "\n\n\n\n\n正式答案"
    out = strip_think_blocks(text)
    assert out == "正式答案"


def test_strip_block_at_start():
    """`` 块在文本开头。"""
    text = f"{_t('推理内容')}\n\n用户可见内容"
    out = strip_think_blocks(text)
    assert out == "用户可见内容"


def test_strip_block_at_end():
    """`` 块在文本末尾。"""
    text = f"用户可见内容\n\n{_t('推理尾巴')}"
    out = strip_think_blocks(text)
    assert out == "用户可见内容"


def test_strip_only_block_returns_empty():
    """只有 `` 块时返回空串。"""
    assert strip_think_blocks(_t("纯推理内容")) == ""


def test_strip_with_markdown_code_inside():
    """`` 块紧邻 markdown 代码块（markdown 在外），剥离后 markdown 完整保留。"""
    text = _t("这是模型推理") + "\n\n```python\nprint('hello')\n```\n\n下面给 SQL"
    out = strip_think_blocks(text)
    # 块外 markdown 完整保留
    assert "```python" in out
    assert "print('hello')" in out
    assert out.endswith("下面给 SQL")
    # 块内推理已剥离
    assert "这是模型推理" not in out


def test_strip_no_block_unchanged():
    """无 `` 时原样返回（仅 strip 首尾空白）。"""
    text = "  原文本无变化  "
    assert strip_think_blocks(text) == "原文本无变化"


def test_strip_large_block_does_not_crash():
    """大 `` 块剥离不崩溃。"""
    big_thought = "x" * 5000
    text = _t(big_thought) + "\n\n用户答案"
    out = strip_think_blocks(text)
    assert out == "用户答案"
    assert "x" * 100 not in out


def test_strip_chinese_thinking():
    """中文 `` 推理内容正常剥离。"""
    text = _t("我需要先理解 DBA 用户的痛点") + "\n\n可以试试如下 SQL"
    out = strip_think_blocks(text)
    assert out == "可以试试如下 SQL"


def test_strip_english_thinking_with_dots():
    """英文 `` 块带句号 / 标点。"""
    text = (
        f"{_t('The user wants... Let me think. I should provide a SQL example.')}\n\n"
        "Here's the answer: SELECT 1;"
    )
    out = strip_think_blocks(text)
    assert out == "Here's the answer: SELECT 1;"


def test_strip_empty_string():
    """空串返回空串。"""
    assert strip_think_blocks("") == ""


def test_strip_none_returns_empty_string():
    """None 入参返回空串（前端展示安全）。"""
    assert strip_think_blocks(None) == ""


def test_strip_two_blocks_non_greedy():
    """两个相邻块独立剥离（非贪婪避免合并丢失中间 answer）。"""
    text = _t("思考1") + "\n\n答案1\n\n" + _t("思考2") + "\n\n答案2"
    out = strip_think_blocks(text)
    assert out == "答案1\n\n答案2"


def test_strip_preserves_text_with_think_keyword_inside():
    """普通文本含 'think' 单词但不含 `` tag 不被剥离。"""
    text = "I think the answer is 42."
    assert strip_think_blocks(text) == text


def test_strip_handles_only_whitespace():
    """仅有空白（含剥离后）的输入返回空串。"""
    text = _t("思考") + "\n\n  \n\n  "
    assert strip_think_blocks(text) == ""


# =============================================================================
# has_think_block
# =============================================================================
def test_has_block_true():
    """有 `` → True。"""
    assert has_think_block(_t("思考内容")) is True


def test_has_block_false():
    """无 `` → False。"""
    assert has_think_block("普通答案") is False


def test_has_block_none():
    """None → False。"""
    assert has_think_block(None) is False


def test_has_block_empty():
    """空串 → False。"""
    assert has_think_block("") is False
