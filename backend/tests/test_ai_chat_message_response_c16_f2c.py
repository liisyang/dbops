"""
C16-F2c 回归测试 — AiChatMessageResponse Pydantic Literal 接受 'sql_preview_link'

F2b 把 'sql_preview_link' 写入 ai_chat_message.message_type（ORM DB CHECK 已加），
但 Pydantic schema `AiChatMessageResponse.message_type` Literal 漏加 → 用户切走再回来
调 listMessages 时会触发 Pydantic 500。F2c commit 1 同步修。

本测试构造 ORM 形态的 dict（SQLAlchemy session 拿不到，只用 dict 走 Pydantic validate），
确认 5 种 message_type 都能通过 validation。
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.ai import AiChatMessageResponse


def _make_payload(message_type: str) -> dict:
    return {
        "id": 1,
        "session_id": 1,
        "user_id": None,
        "client_request_id": None,
        "role": "assistant",
        "message_type": message_type,
        "status": "completed",
        "content": None,
        "parent_message_id": None,
        "metadata_json": {},
        "dify_task_id": None,
        "workflow_run_id": None,
        "elapsed_ms": None,
        "total_tokens": None,
        "error_code": None,
        "error_message": None,
        "processing_started_at": None,
        "processing_expires_at": None,
        "attempt_count": 0,
        "created_at": datetime(2026, 7, 7),
        "updated_at": datetime(2026, 7, 7),
    }


def test_message_type_accepts_sql_preview_link():
    """F2b 落地消息类型 — F2c commit 1 修复后能正常 validate。"""
    payload = _make_payload("sql_preview_link")
    msg = AiChatMessageResponse.model_validate(payload)
    assert msg.message_type == "sql_preview_link"


def test_message_type_accepts_all_known_values():
    """5 种枚举值都能通过（回归保护）。"""
    expected = ["chat", "sql_preview", "sql_preview_link", "sql_result", "error"]
    for mt in expected:
        msg = AiChatMessageResponse.model_validate(_make_payload(mt))
        assert msg.message_type == mt, f"message_type={mt} 应被接受"


def test_message_type_rejects_unknown_value():
    """未知 message_type 应被 Literal 拒绝（Pydantic 422）。"""
    with pytest.raises(ValidationError):
        AiChatMessageResponse.model_validate(_make_payload("unknown_type"))