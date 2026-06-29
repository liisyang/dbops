"""
AI 文本处理工具（Phase 3.6 AI Copilot）

集中维护对 Dify / LLM 返回文本的清洗与归一化逻辑，避免业务代码各自重复正则。

设计要点：
- 纯函数，无外部依赖，便于单元测试
- 所有函数接受 ``text: str | None`` 入参，None 时返回空串（前端展示安全）
- 输出与业务语义解耦：剥离噪声但不修改业务内容
"""
from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# 剥离模型推理过程块
# ---------------------------------------------------------------------------
# 推理类模型（DeepSeek R1、o1、o3-mini 等）在 Chat App response_mode=blocking
# 下，可能把推理过程以 ``...`` 的形式混入 ``answer`` 字段。
# 终态用户不需要看到这些，剥离并保留正文。
# - DOTALL：跨越换行
# - 非贪婪：避免跨多个 `` 块合并
_THINK_BLOCK_RE = re.compile(r"\<think\>.*?\</think\>", re.DOTALL)
# 折叠剥离后留下的连续空行（剥离 `` 常在 ``... `` 之间留下一片空行）
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_think_blocks(text: Optional[str]) -> str:
    """剥离文本中的 `` 推理过程块。

    Args:
        text: 原始文本（可能为 None）

    Returns:
        剥离后的纯答案文本（首尾空白已清理，连续空行已折叠为最多 2 个）

    Examples:
        >>> strip_think_blocks("\<think\>我先思考\<\/think\>你好")
        '你好'
        >>> strip_think_blocks(None)
        ''
        >>> strip_think_blocks("\<think\>思考\<\/think\>\\n\\n\\n正式答案")
        '正式答案'
    """
    if not text:
        return ""
    no_think = _THINK_BLOCK_RE.sub("", text)
    collapsed = _BLANK_LINES_RE.sub("\n\n", no_think)
    return collapsed.strip()


def has_think_block(text: Optional[str]) -> bool:
    """判断文本是否包含 `` 块（用于日志 / 监控埋点）。"""
    if not text:
        return False
    return _THINK_BLOCK_RE.search(text) is not None
