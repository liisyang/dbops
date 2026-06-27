"""
DifyService + AI 配置单元测试（Phase 3.6 C1）

覆盖：
- DifyService 生命周期：init_client/close_client/is_configured
- _post 异常映射：成功 / Timeout / ConnectError / HTTP 5xx / HTTP 4xx / 非 JSON
- 三个公开方法：chat_message / run_sql_workflow / run_report_workflow（含 config 缺失）
- Settings.validate_ai_config 特征感知校验（plan §11 P1 解耦）
- Settings.dify_configured / sql_supported_db_types
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.services.dify_service import (
    DifyConfigurationError,
    DifyConnectionError,
    DifyHttpError,
    DifyResponseFormatError,
    DifyService,
    DifyTimeoutError,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _make_settings(**overrides) -> Settings:
    """构造一个不读 .env 的 Settings 实例，仅用于 AI 相关字段测试。"""
    base = {
        "SECRET_KEY": "test-secret",
        "POSTGRES_PASSWORD": "test-pwd",
        "POSTGRES_HOST": "127.0.0.1",
    }
    base.update(overrides)
    s = Settings(_env_file=None, **base)
    return s


@pytest.fixture(autouse=True)
def _reset_dify_state():
    """每个 case 前重置 DifyService 类变量，避免测试间相互污染。"""
    DifyService._client = None
    DifyService._base_url = ""
    DifyService._connect_timeout = 10.0
    DifyService._default_timeout = 60.0
    yield
    DifyService._client = None


# -----------------------------------------------------------------------------
# 1. DifyService 生命周期
# -----------------------------------------------------------------------------
def test_init_client_requires_base_url():
    with pytest.raises(DifyConfigurationError, match="base_url"):
        DifyService.init_client(base_url="")


def test_init_client_strips_trailing_slash():
    DifyService.init_client(base_url="http://example.com/v1/")
    assert DifyService._base_url == "http://example.com/v1"
    assert DifyService.is_configured() is True
    DifyService.close_client()
    assert DifyService.is_configured() is False


def test_init_client_uses_provided_timeouts():
    DifyService.init_client(
        base_url="http://example.com",
        timeout=42.0,
        connect_timeout=3.5,
    )
    assert DifyService._default_timeout == 42.0
    assert DifyService._connect_timeout == 3.5
    DifyService.close_client()


def test_close_client_safe_when_uninitialized():
    # 不应抛异常
    DifyService.close_client()
    assert DifyService.is_configured() is False


# -----------------------------------------------------------------------------
# 2. _post 异常映射
# -----------------------------------------------------------------------------
def _mock_response(status_code: int, body) -> httpx.Response:
    if isinstance(body, dict):
        text = json.dumps(body)
    else:
        text = body
    return httpx.Response(status_code=status_code, text=text)


@patch("app.services.dify_service.httpx.Client")
def test_post_success_returns_json_dict(mock_client_cls):
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(200, {"ok": True, "answer": "hi"})
    DifyService._client = mock_client

    result = DifyService._post(
        "/chat-messages",
        headers={"Authorization": "Bearer x"},
        json_body={"q": 1},
    )
    assert result == {"ok": True, "answer": "hi"}


@patch("app.services.dify_service.httpx.Client")
def test_post_timeout_raises_dify_timeout(mock_client_cls):
    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.TimeoutException("read timeout")
    DifyService._client = mock_client

    with pytest.raises(DifyTimeoutError, match="超时"):
        DifyService._post("/x", headers={}, json_body={})


@patch("app.services.dify_service.httpx.Client")
def test_post_connect_error_raises_dify_connection(mock_client_cls):
    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.ConnectError("dns fail")
    DifyService._client = mock_client

    with pytest.raises(DifyConnectionError, match="连接失败"):
        DifyService._post("/x", headers={}, json_body={})


@patch("app.services.dify_service.httpx.Client")
def test_post_5xx_raises_dify_http(mock_client_cls):
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(500, "internal error")
    DifyService._client = mock_client

    with pytest.raises(DifyHttpError) as ei:
        DifyService._post("/x", headers={}, json_body={})
    assert ei.value.status_code == 500


@patch("app.services.dify_service.httpx.Client")
def test_post_4xx_raises_dify_http(mock_client_cls):
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(401, "unauthorized")
    DifyService._client = mock_client

    with pytest.raises(DifyHttpError) as ei:
        DifyService._post("/x", headers={}, json_body={})
    assert ei.value.status_code == 401


@patch("app.services.dify_service.httpx.Client")
def test_post_non_json_raises_dify_response_format(mock_client_cls):
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(200, "<html>oops</html>")
    DifyService._client = mock_client

    with pytest.raises(DifyResponseFormatError, match="非 JSON"):
        DifyService._post("/x", headers={}, json_body={})


def test_post_without_client_raises_configuration_error():
    DifyService._client = None
    with pytest.raises(DifyConfigurationError, match="未初始化"):
        DifyService._post("/x", headers={}, json_body={})


# -----------------------------------------------------------------------------
# 3. 三个公开方法
# -----------------------------------------------------------------------------
@patch("app.services.dify_service.httpx.Client")
@patch("app.services.dify_service.get_settings")
def test_chat_message_sends_blocking_body(mock_settings, mock_client_cls):
    mock_settings.return_value = MagicMock(
        DIFY_CHAT_API_KEY="chat-key",
        DIFY_CHAT_TIMEOUT_SECONDS=30.0,
    )
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(200, {"answer": "hello"})
    DifyService._client = mock_client

    DifyService.chat_message(
        query="hi",
        inputs={"role": "admin"},
        user="dbops:1",
        conversation_id="conv-1",
    )
    args, kwargs = mock_client.post.call_args
    assert args[0] == "/chat-messages"
    assert kwargs["headers"] == {"Authorization": "Bearer chat-key"}
    assert kwargs["json"]["query"] == "hi"
    assert kwargs["json"]["user"] == "dbops:1"
    assert kwargs["json"]["conversation_id"] == "conv-1"
    assert kwargs["json"]["response_mode"] == "blocking"
    assert kwargs["timeout"] == 30.0


@patch("app.services.dify_service.get_settings")
def test_chat_message_missing_key_raises(mock_settings):
    mock_settings.return_value = MagicMock(DIFY_CHAT_API_KEY="")
    with pytest.raises(DifyConfigurationError, match="DIFY_CHAT_API_KEY"):
        DifyService.chat_message(query="x", inputs={}, user="dbops:1")


@patch("app.services.dify_service.httpx.Client")
@patch("app.services.dify_service.get_settings")
def test_run_sql_workflow_uses_sql_key_and_path(mock_settings, mock_client_cls):
    mock_settings.return_value = MagicMock(
        DIFY_SQL_WORKFLOW_KEY="sql-key",
        DIFY_SQL_TIMEOUT_SECONDS=45.0,
    )
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(200, {"workflow_run_id": "wf-1"})
    DifyService._client = mock_client

    DifyService.run_sql_workflow(inputs={"sql": "SELECT 1"}, user="dbops:1")
    args, kwargs = mock_client.post.call_args
    assert args[0] == "/workflows/run"
    assert kwargs["headers"] == {"Authorization": "Bearer sql-key"}
    assert kwargs["json"]["inputs"]["sql"] == "SELECT 1"
    assert kwargs["timeout"] == 45.0


@patch("app.services.dify_service.get_settings")
def test_run_sql_workflow_missing_key_raises(mock_settings):
    mock_settings.return_value = MagicMock(DIFY_SQL_WORKFLOW_KEY="")
    with pytest.raises(DifyConfigurationError, match="DIFY_SQL_WORKFLOW_KEY"):
        DifyService.run_sql_workflow(inputs={}, user="dbops:1")


@patch("app.services.dify_service.httpx.Client")
@patch("app.services.dify_service.get_settings")
def test_run_report_workflow_uses_report_key(mock_settings, mock_client_cls):
    mock_settings.return_value = MagicMock(
        DIFY_REPORT_WORKFLOW_KEY="report-key",
        DIFY_REPORT_TIMEOUT_SECONDS=90.0,
    )
    mock_client = MagicMock()
    mock_client.post.return_value = _mock_response(200, {"workflow_run_id": "wf-2"})
    DifyService._client = mock_client

    DifyService.run_report_workflow(inputs={"report_id": 99}, user="dbops:1")
    args, kwargs = mock_client.post.call_args
    assert args[0] == "/workflows/run"
    assert kwargs["headers"] == {"Authorization": "Bearer report-key"}
    assert kwargs["timeout"] == 90.0


# -----------------------------------------------------------------------------
# 4. Settings 特征感知校验（plan §11 P1 解耦）
# -----------------------------------------------------------------------------
def test_validate_ai_config_passes_when_all_disabled():
    s = _make_settings(AI_CHAT_ENABLED=False, DIFY_BASE_URL="")
    # 不应抛异常
    s.validate_ai_config()


def test_validate_ai_config_requires_base_url_when_chat_enabled():
    s = _make_settings(
        AI_CHAT_ENABLED=True,
        DIFY_BASE_URL="",
        DIFY_CHAT_API_KEY="key",
    )
    with pytest.raises(ValueError, match="DIFY_BASE_URL"):
        s.validate_ai_config()


def test_validate_ai_config_requires_chat_key_when_chat_enabled():
    s = _make_settings(
        AI_CHAT_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_CHAT_API_KEY="",
    )
    with pytest.raises(ValueError, match="DIFY_CHAT_API_KEY"):
        s.validate_ai_config()


def test_validate_ai_config_chat_enabled_alone_does_not_require_sql_or_report_key():
    """关键解耦：仅 chat 开启时不应要求 SQL/Report key。"""
    s = _make_settings(
        AI_CHAT_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_CHAT_API_KEY="ck",
        DIFY_SQL_WORKFLOW_KEY="",
        DIFY_REPORT_WORKFLOW_KEY="",
    )
    # 不应抛异常
    s.validate_ai_config()


def test_validate_ai_config_requires_sql_key_when_sql_preview_enabled():
    s = _make_settings(
        AI_CHAT_ENABLED=False,
        AI_SQL_PREVIEW_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_SQL_WORKFLOW_KEY="",
    )
    with pytest.raises(ValueError, match="DIFY_SQL_WORKFLOW_KEY"):
        s.validate_ai_config()


def test_validate_ai_config_requires_sql_key_when_sql_execution_enabled():
    s = _make_settings(
        AI_SQL_EXECUTION_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_SQL_WORKFLOW_KEY="",
    )
    with pytest.raises(ValueError, match="DIFY_SQL_WORKFLOW_KEY"):
        s.validate_ai_config()


def test_validate_ai_config_requires_report_key_when_report_analysis_enabled():
    s = _make_settings(
        AI_REPORT_ANALYSIS_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_REPORT_WORKFLOW_KEY="",
    )
    with pytest.raises(ValueError, match="DIFY_REPORT_WORKFLOW_KEY"):
        s.validate_ai_config()


def test_validate_ai_config_requires_report_key_when_report_export_enabled():
    s = _make_settings(
        AI_REPORT_EXPORT_AI_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_REPORT_WORKFLOW_KEY="",
    )
    with pytest.raises(ValueError, match="DIFY_REPORT_WORKFLOW_KEY"):
        s.validate_ai_config()


def test_validate_ai_config_full_ai_stack_passes():
    s = _make_settings(
        AI_CHAT_ENABLED=True,
        AI_SQL_PREVIEW_ENABLED=True,
        AI_SQL_EXECUTION_ENABLED=True,
        AI_REPORT_ANALYSIS_ENABLED=True,
        AI_REPORT_EXPORT_AI_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_CHAT_API_KEY="ck",
        DIFY_SQL_WORKFLOW_KEY="sk",
        DIFY_REPORT_WORKFLOW_KEY="rk",
    )
    s.validate_ai_config()


# -----------------------------------------------------------------------------
# 5. dify_configured / sql_supported_db_types 属性
# -----------------------------------------------------------------------------
def test_dify_configured_default_false():
    s = _make_settings()
    assert s.dify_configured is False


def test_dify_configured_true_when_chat_enabled():
    s = _make_settings(AI_CHAT_ENABLED=True, DIFY_BASE_URL="http://d", DIFY_CHAT_API_KEY="k")
    assert s.dify_configured is True


def test_sql_supported_db_types_default_empty():
    s = _make_settings()
    assert s.sql_supported_db_types == []


def test_sql_supported_db_types_postgres_only_when_sql_preview_enabled():
    s = _make_settings(
        AI_SQL_PREVIEW_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_SQL_WORKFLOW_KEY="sk",
    )
    assert s.sql_supported_db_types == ["POSTGRESQL"]


def test_sql_supported_db_types_includes_when_execution_enabled():
    s = _make_settings(
        AI_SQL_EXECUTION_ENABLED=True,
        DIFY_BASE_URL="http://d",
        DIFY_SQL_WORKFLOW_KEY="sk",
    )
    assert s.sql_supported_db_types == ["POSTGRESQL"]
