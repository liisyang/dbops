"""
AI Copilot API（Phase 3.6）

C1 范围：仅 GET /api/v1/ai/capabilities
后续 commit 追加：
- C3: Chat CRUD/Send/History
- C10: Schema Snapshot collect/status
- C13: SQL Preview
- C19: SQL Execute/Executions
- C24-C25: Inspection AI Analysis
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings


router = APIRouter()


# =============================================================================
# Capabilities 响应模型
# =============================================================================
class CapabilitiesResponse(BaseModel):
    """AI Copilot 能力声明（plan §11）。

    严禁返回 API Key、Dify URL、内部模型配置等敏感信息。
    前端根据能力隐藏/禁用对应 UI 元素。
    """

    chat_enabled: bool
    sql_preview_enabled: bool
    sql_execution_enabled: bool
    report_analysis_enabled: bool
    report_export_ai_enabled: bool
    stream_enabled: bool
    sql_supported_db_types: list[str]


# =============================================================================
# 端点
# =============================================================================
@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_ai_capabilities() -> CapabilitiesResponse:
    """返回 AI Copilot 当前可用能力。

    设计原则（plan §11）：
    - 任何用户（包括未登录）都可以查询 capabilities
    - 仅声明 ON/OFF 与支持的方言，不暴露内部配置
    - 前端启动时拉取一次，灰度菜单按钮
    """
    s = get_settings()
    return CapabilitiesResponse(
        chat_enabled=s.AI_CHAT_ENABLED,
        sql_preview_enabled=s.AI_SQL_PREVIEW_ENABLED,
        sql_execution_enabled=s.AI_SQL_EXECUTION_ENABLED,
        report_analysis_enabled=s.AI_REPORT_ANALYSIS_ENABLED,
        report_export_ai_enabled=s.AI_REPORT_EXPORT_AI_ENABLED,
        stream_enabled=False,  # 首版不实现 SSE/打字流
        sql_supported_db_types=s.sql_supported_db_types,
    )
