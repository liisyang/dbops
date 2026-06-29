"""
Dify AI 服务客户端（Phase 3.6 AI Copilot）

设计要点（plan §3）：
- 同步 httpx.Client 池（与 SQLAlchemy 同步 Session 一致；禁止混用异步 DB 会话）
- lifespan 启动时 init_client 一次，关闭时 close_client
- base_url 自动 rstrip('/')，避免拼接时出现 //
- Chat/Workflow POST 默认不自动重试（网络超时 ≠ Dify 未执行，盲目重试可能产生重复 Workflow Run）
- 自定义异常体系便于上层 service 分类处理
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.services.ai_text import strip_think_blocks

logger = logging.getLogger(__name__)


# =============================================================================
# 异常体系
# =============================================================================
class DifyError(Exception):
    """Dify 调用基类异常。"""

    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class DifyConfigurationError(DifyError):
    """Dify 配置缺失或非法（base_url 未设置等）。"""


class DifyTimeoutError(DifyError):
    """Dify 调用超时（connect/read/timeout）。"""


class DifyConnectionError(DifyError):
    """Dify 网络连接失败（DNS/拒绝/重置等）。"""


class DifyHttpError(DifyError):
    """Dify 返回非 2xx 状态码。"""


class DifyResponseFormatError(DifyError):
    """Dify 返回内容无法解析为预期 JSON 结构。"""


class DifyWorkflowFailedError(DifyError):
    """Dify Workflow 自身执行失败（workflow_run.status='failed'）。"""


# =============================================================================
# DifyService
# =============================================================================
class DifyService:
    """Dify AI 服务的同步客户端封装。

    使用方式：
    - app lifespan 启动时调用 DifyService.init_client(base_url, timeout)
    - 业务代码通过类方法调用 chat_message / run_sql_workflow / run_report_workflow
    - app lifespan 关闭时调用 DifyService.close_client()
    """

    _client: Optional[httpx.Client] = None
    _base_url: str = ""
    _connect_timeout: float = 10.0
    _default_timeout: float = 60.0

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @classmethod
    def init_client(
        cls,
        base_url: str,
        timeout: float = 60.0,
        connect_timeout: float = 10.0,
    ) -> None:
        """在 app lifespan 中调用一次。

        Args:
            base_url: Dify 服务 base URL（如 http://10.134.181.168/v1）
            timeout: 默认读超时（秒）
            connect_timeout: 连接超时（秒）
        """
        if not base_url:
            raise DifyConfigurationError("DifyService.init_client 缺少 base_url")
        cls._base_url = base_url.rstrip("/")
        cls._connect_timeout = connect_timeout
        cls._default_timeout = timeout
        cls._client = httpx.Client(
            base_url=cls._base_url,
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        logger.info(
            "DifyService 客户端初始化完成 base_url=%s connect_timeout=%.1fs timeout=%.1fs",
            cls._base_url,
            connect_timeout,
            timeout,
        )

    @classmethod
    def close_client(cls) -> None:
        """在 app lifespan 关闭时调用一次。"""
        if cls._client is not None:
            try:
                cls._client.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("DifyService 关闭客户端异常: %s", exc)
            cls._client = None
            logger.info("DifyService 客户端已关闭")

    @classmethod
    def is_configured(cls) -> bool:
        """Dify 客户端是否已初始化。"""
        return cls._client is not None

    # ------------------------------------------------------------------
    # 内部请求
    # ------------------------------------------------------------------
    @classmethod
    def _ensure_client(cls) -> httpx.Client:
        if cls._client is None:
            raise DifyConfigurationError("DifyService 客户端未初始化（请先调用 init_client）")
        return cls._client

    @classmethod
    def _post(
        cls,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any],
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """统一 POST 入口，封装异常映射。"""
        client = cls._ensure_client()
        try:
            resp = client.post(
                path,
                headers=headers,
                json=json_body,
                timeout=timeout if timeout is not None else cls._default_timeout,
            )
        except httpx.TimeoutException as exc:
            raise DifyTimeoutError(f"Dify 调用超时: {exc}", payload={"path": path}) from exc
        except httpx.ConnectError as exc:
            raise DifyConnectionError(f"Dify 连接失败: {exc}", payload={"path": path}) from exc
        except httpx.HTTPError as exc:
            raise DifyConnectionError(f"Dify 网络错误: {exc}", payload={"path": path}) from exc

        if resp.status_code >= 500:
            raise DifyHttpError(
                f"Dify 服务器错误 {resp.status_code}",
                status_code=resp.status_code,
                payload={"path": path, "body": resp.text[:500]},
            )
        if resp.status_code >= 400:
            raise DifyHttpError(
                f"Dify 客户端错误 {resp.status_code}",
                status_code=resp.status_code,
                payload={"path": path, "body": resp.text[:500]},
            )

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise DifyResponseFormatError(
                f"Dify 响应非 JSON: {exc}",
                status_code=resp.status_code,
                payload={"path": path, "body": resp.text[:500]},
            ) from exc
        return data

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    @classmethod
    def chat_message(
        cls,
        *,
        query: str,
        inputs: dict[str, Any],
        user: str,
        conversation_id: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """POST /chat-messages（Dify Chat App，blocking 模式）。

        Args:
            query: 用户消息文本
            inputs: 附加变量（role/locale/current_page 等）
            user: Dify 端用户标识（统一为 dbops:{user_id}，由 service 层构造）
            conversation_id: 已有会话 id（首次发送可为空）
            api_key: Dify Chat App API Key（默认从 settings 取）
            timeout: 本次调用的读超时（默认 settings.DIFY_CHAT_TIMEOUT_SECONDS）

        Returns:
            Dify 原始响应 dict（含 answer / conversation_id / message_id 等）。
            注意：answer 字段已剥离模型推理过程 ``...``，避免 Chat UI 显示中间思考链。
        """
        settings = get_settings()
        key = api_key or settings.DIFY_CHAT_API_KEY
        if not key:
            raise DifyConfigurationError("DIFY_CHAT_API_KEY 未配置")
        body: dict[str, Any] = {
            "query": query,
            "inputs": inputs or {},
            "user": user,
            "response_mode": "blocking",
        }
        if conversation_id:
            body["conversation_id"] = conversation_id
        resp = cls._post(
            "/chat-messages",
            headers={"Authorization": f"Bearer {key}"},
            json_body=body,
            timeout=timeout if timeout is not None else settings.DIFY_CHAT_TIMEOUT_SECONDS,
        )
        # 剥离推理模型（如 DeepSeek R1 / o1）在 answer 中混入的 `` 块，
        # 单点 sink：所有 chat_message 调用者拿到的都是干净 answer。
        if isinstance(resp, dict) and isinstance(resp.get("answer"), str):
            resp["answer"] = strip_think_blocks(resp["answer"])
        return resp

    @classmethod
    def run_sql_workflow(
        cls,
        *,
        inputs: dict[str, Any],
        user: str,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """POST /workflows/run（Dify SQL Workflow App，blocking 模式）。

        Args:
            inputs: SQL 预览输入（user_question / db_type_code / schema_context / allowed_* 等）
            user: Dify 端用户标识
            api_key: Dify SQL Workflow API Key（默认从 settings 取）
            timeout: 本次调用的读超时

        Returns:
            Dify Workflow Run 原始响应 dict
        """
        settings = get_settings()
        key = api_key or settings.DIFY_SQL_WORKFLOW_KEY
        if not key:
            raise DifyConfigurationError("DIFY_SQL_WORKFLOW_KEY 未配置")
        body = {
            "inputs": inputs or {},
            "user": user,
            "response_mode": "blocking",
        }
        return cls._post(
            "/workflows/run",
            headers={"Authorization": f"Bearer {key}"},
            json_body=body,
            timeout=timeout if timeout is not None else settings.DIFY_SQL_TIMEOUT_SECONDS,
        )

    @classmethod
    def run_report_workflow(
        cls,
        *,
        inputs: dict[str, Any],
        user: str,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """POST /workflows/run（Dify Report Workflow App，blocking 模式）。

        Args:
            inputs: 巡检分析输入（report_id / source_data / source_data_hash 等）
            user: Dify 端用户标识
            api_key: Dify Report Workflow API Key
            timeout: 本次调用的读超时

        Returns:
            Dify Workflow Run 原始响应 dict
        """
        settings = get_settings()
        key = api_key or settings.DIFY_REPORT_WORKFLOW_KEY
        if not key:
            raise DifyConfigurationError("DIFY_REPORT_WORKFLOW_KEY 未配置")
        body = {
            "inputs": inputs or {},
            "user": user,
            "response_mode": "blocking",
        }
        return cls._post(
            "/workflows/run",
            headers={"Authorization": f"Bearer {key}"},
            json_body=body,
            timeout=timeout if timeout is not None else settings.DIFY_REPORT_TIMEOUT_SECONDS,
        )
