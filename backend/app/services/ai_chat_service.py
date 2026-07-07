"""
AI Chat 服务（Phase 3.6 C3）

设计要点（plan §7）：
- 同步 Session，与项目其他 service 一致（禁止异步 DB 会话混用）
- 发送消息分 2 段事务（事务 1: 幂等 + 租约 + 建 user/assistant pending；事务外: Dify 调用；事务 2: 收尾）
- Dify inputs 安全：user="dbops:{user_id}" / role 来自 current_user / locale 默认 zh-CN / current_page 白名单 / conversation_id 仅从 session 读
- 幂等：client_request_id 部分唯一索引 UNIQUE(session_id, client_request_id) WHERE role='user' AND client_request_id IS NOT NULL
- 租约：assistant pending 消息设置 processing_expires_at = now() + AI_CHAT_LEASE_SECONDS；过期后下一次 send_message 标记 stale
- 并发保护：DB 层 UNIQUE(session_id) WHERE role='assistant' AND status='pending'
- 错误码：会话正在处理 → 409；功能关闭 → 503；Dify 不可用 → 502；超时 → 504

C16-F2a 扩展（plan §21.2）：
- Session 创建接受 mode ('general'/'instance_sql') + bound_instance_id
- mode='general' → bound_instance_id 必须 NULL
- mode='instance_sql' → bound_instance_id 必须 NOT NULL + 实例存在且 is_active=True
- 已存在同 user+mode+bound_instance_id session 时复用（不重建）
- chat_mode + bound_instance_id 创建后不可变
- 新异常：ChatModeInvalidError / ChatInstanceNotAccessibleError / ChatImmutableViolationError
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.ai import AiChatMessage, AiChatSession
from app.models.dbops_assets import DbInstance
from app.models.user import User
from app.schemas.ai import ALL_CHAT_MODES, AiChatMessageSendRequest, ChatMode
from app.services.dify_service import (
    DifyConfigurationError,
    DifyConnectionError,
    DifyError,
    DifyHttpError,
    DifyResponseFormatError,
    DifyService,
    DifyTimeoutError,
    DifyWorkflowFailedError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Service 层异常
# =============================================================================
class AiChatError(Exception):
    """Chat 服务基类异常。"""


class ChatSessionNotFoundError(AiChatError):
    """会话不存在或属于当前用户（统一返回 404，避免泄露存在性）。"""


class ChatConcurrentPendingError(AiChatError):
    """同 session 已有 assistant pending 在有效期内 → 409 Conflict。"""


class ChatFeatureDisabledError(AiChatError):
    """AI_CHAT_ENABLED=false → 503 Service Unavailable。"""


class ChatDifyUnavailableError(AiChatError):
    """Dify 客户端未初始化或不可用 → 502 Bad Gateway。"""


class ChatDifyTimeoutError(AiChatError):
    """Dify 调用超时 → 504 Gateway Timeout。"""


class ChatModeInvalidError(AiChatError):
    """mode 字段非法或 mode/bound_instance_id 不匹配 → 422。"""


class ChatInstanceNotAccessibleError(AiChatError):
    """bound_instance_id 不存在或 is_active=False → 404。"""


class ChatImmutableViolationError(AiChatError):
    """chat_mode / bound_instance_id 已存在但与请求不一致 → 409 Conflict。"""


# =============================================================================
# Service 返回类型
# =============================================================================
@dataclass
class SendMessageResult:
    """send_message 内部返回（user_message + assistant_message + 幂等命中标记）。"""

    user_message: AiChatMessage
    assistant_message: Optional[AiChatMessage]
    idempotent_replay: bool


@dataclass
class CreateSessionResult:
    """create_session 内部返回（session + 是否复用标记）。"""

    session: AiChatSession
    reused: bool


# =============================================================================
# AiChatService
# =============================================================================
class AiChatService:
    """AI Chat 业务编排。

    所有公开方法均为同步 static / classmethod，签名风格与项目其他 service 一致
    （`Service.method(db, *, kw=...)`）。
    """

    # current_page 白名单（plan §7）
    CURRENT_PAGE_ALLOWLIST = frozenset({
        "ai_chat",
        "inspection_report",
        "instance_report",
        "instance_detail",
    })

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    @staticmethod
    def create_session(
        db: Session,
        *,
        user: User,
        title: Optional[str] = None,
        mode: ChatMode = "general",
        bound_instance_id: Optional[int] = None,
        source_page: Optional[str] = None,
    ) -> CreateSessionResult:
        """创建或复用 Chat session（C16-F2a 扩展）。

        Args:
            db:                SQLAlchemy Session
            user:              当前用户
            title:             会话标题（默认 '新会话'）
            mode:              Chat 模式（'general'/'instance_sql'），默认 'general'
            bound_instance_id: 实例 ID（mode='instance_sql' 时必填；mode='general' 时必须 NULL）
            source_page:       来源页面（仅日志记录，不持久化到 session 层）

        Returns:
            CreateSessionResult(session=<AiChatSession>, reused=<bool>)
            - reused=True:  同 user+mode+bound_instance_id session 已存在，已复用（不重建）
            - reused=False: 新建 session

        Raises:
            ChatModeInvalidError:           mode 非法或与 bound_instance_id 不匹配
            ChatInstanceNotAccessibleError: bound_instance_id 不存在或 is_active=False

        Rules（plan §21.2 P0-2）:
            1. mode='general'       → bound_instance_id 必须 NULL（传了 → 422）
            2. mode='instance_sql'  → bound_instance_id 必须 NOT NULL（缺 → 422）
            3. bound_instance_id 必须存在且 is_active=True（否则 404）
            4. 复用已有同 user+mode+bound_instance_id session（partial unique 兜底）
            5. 创建后 chat_mode + bound_instance_id 不可变（应用层不更新，DB CHECK 兜底）
        """
        # 1. 校验 mode 枚举
        if mode not in ALL_CHAT_MODES:
            raise ChatModeInvalidError(
                f"Invalid chat mode: {mode!r}; must be one of {ALL_CHAT_MODES}"
            )

        # 2. mode 与 bound_instance_id 一致性校验
        if mode == "general" and bound_instance_id is not None:
            raise ChatModeInvalidError(
                "mode='general' must not have bound_instance_id (got "
                f"bound_instance_id={bound_instance_id})"
            )
        if mode == "instance_sql" and bound_instance_id is None:
            raise ChatModeInvalidError(
                "mode='instance_sql' requires bound_instance_id (got None)"
            )

        # 3. bound_instance_id 存在 + is_active 校验
        if bound_instance_id is not None:
            instance = (
                db.query(DbInstance)
                .filter(DbInstance.id == bound_instance_id)
                .first()
            )
            if instance is None:
                raise ChatInstanceNotAccessibleError(
                    f"db_instance id={bound_instance_id} not found"
                )
            if not getattr(instance, "is_active", True):
                raise ChatInstanceNotAccessibleError(
                    f"db_instance id={bound_instance_id} is not active"
                )

        # 4. 复用已有 session（仅 instance_sql 模式；general 模式用户可建多个独立会话）
        #    partial unique uq_ai_chat_session_user_instance_sql 仅约束 instance_sql，
        #    general 模式下 bound_instance_id 始终 NULL，多会话并存为正常预期
        if mode == "instance_sql":
            existing = (
                db.query(AiChatSession)
                .filter(
                    AiChatSession.user_id == user.id,
                    AiChatSession.chat_mode == mode,
                    AiChatSession.bound_instance_id == bound_instance_id,
                )
                .first()
            )
            if existing is not None:
                logger.info(
                    "AiChatService.create_session reused session id=%s mode=%s bound=%s user=%s",
                    existing.id,
                    mode,
                    bound_instance_id,
                    user.id,
                )
                return CreateSessionResult(session=existing, reused=True)

        # 5. 新建 session
        session_obj = AiChatSession(
            session_code=AiChatService._make_session_code(),
            user_id=user.id,
            title=(title or "新会话").strip()[:200] or "新会话",
            message_count=0,
            chat_mode=mode,
            bound_instance_id=bound_instance_id,
        )
        # source_page 仅日志记录（AiChatSession 没有 metadata_json 列，AiChatMessage 才有；
        # 真实 source_page 由前端在使用 session 时附带）
        if source_page:
            logger.debug(
                "AiChatService.create_session source_page=%s (not persisted at session level)",
                source_page,
            )

        db.add(session_obj)
        db.flush()
        return CreateSessionResult(session=session_obj, reused=False)

    @staticmethod
    def list_sessions(db: Session, *, user: User, limit: int = 50) -> tuple[list[AiChatSession], int]:
        """列出当前用户的会话，按 last_message_at DESC NULLS LAST, created_at DESC 排序。"""
        settings = get_settings()
        cap = min(limit, settings.AI_CHAT_MAX_SESSIONS_PER_USER)

        base = db.query(AiChatSession).filter(AiChatSession.user_id == user.id)
        total = base.count()
        items = (
            base.order_by(
                AiChatSession.last_message_at.desc().nullslast(),
                AiChatSession.created_at.desc(),
            )
            .limit(cap)
            .all()
        )
        return items, total

    @staticmethod
    def get_session(db: Session, *, session_id: int, user: User) -> AiChatSession:
        """获取会话（校验 user_id 归属；不属于当前用户 → 404 隔离）。"""
        obj = (
            db.query(AiChatSession)
            .filter(AiChatSession.id == session_id, AiChatSession.user_id == user.id)
            .first()
        )
        if obj is None:
            raise ChatSessionNotFoundError(f"Chat session {session_id} not found or not owned by user")
        return obj

    # ------------------------------------------------------------------
    # Message
    # ------------------------------------------------------------------
    @staticmethod
    def list_messages(
        db: Session,
        *,
        session_id: int,
        user: User,
        limit: int = 100,
    ) -> tuple[list[AiChatMessage], int]:
        """列出会话消息历史（按 created_at ASC）。"""
        AiChatService.get_session(db, session_id=session_id, user=user)
        settings = get_settings()
        cap = min(limit, settings.AI_CHAT_MAX_MESSAGES_PER_SESSION)

        base = db.query(AiChatMessage).filter(AiChatMessage.session_id == session_id)
        total = base.count()
        items = base.order_by(AiChatMessage.created_at.asc()).limit(cap).all()
        return items, total

    @staticmethod
    def send_message(
        db: Session,
        *,
        session_id: int,
        user: User,
        payload: AiChatMessageSendRequest,
    ) -> SendMessageResult:
        """发送消息（核心端点）。

        流程（plan §7）：
          事务 1：
            1. 校验 session 所有权
            2. 幂等检查：SELECT user WHERE client_request_id=? → 命中则返回
            3. pending assistant 检查 → 有效期内 409 / 过期则标记 stale
            4. 建 user message
            5. 建 assistant pending message + lease
            6. COMMIT
          事务外：调 Dify
          事务 2：
            更新 assistant + session.dify_conversation_id + session.last_message_at + message_count

        Raises:
            ChatSessionNotFoundError: session 不存在或不属于当前用户
            ChatFeatureDisabledError: AI_CHAT_ENABLED=false
            ChatDifyUnavailableError: Dify 客户端未配置
            ChatConcurrentPendingError: 同 session 已有有效 pending
            ChatDifyTimeoutError: Dify 超时
            DifyError: 其他 Dify 错误
        """
        settings = get_settings()

        # 0. 功能开关
        if not settings.AI_CHAT_ENABLED:
            raise ChatFeatureDisabledError("AI_CHAT_ENABLED=false")

        # 0.5 Dify 客户端
        if not DifyService.is_configured():
            raise ChatDifyUnavailableError("Dify client not initialized")

        # =========================
        # 事务 1：幂等 + 租约 + 建消息
        # =========================
        try:
            # 1. 校验 session 归属
            session_obj = AiChatService.get_session(db, session_id=session_id, user=user)

            # 2. 幂等检查
            existing_user_msg = (
                db.query(AiChatMessage)
                .filter(
                    AiChatMessage.session_id == session_id,
                    AiChatMessage.role == "user",
                    AiChatMessage.client_request_id == payload.client_request_id,
                )
                .first()
            )
            if existing_user_msg is not None:
                assistant_msg = (
                    db.query(AiChatMessage)
                    .filter(AiChatMessage.parent_message_id == existing_user_msg.id)
                    .first()
                )
                return SendMessageResult(
                    user_message=existing_user_msg,
                    assistant_message=assistant_msg,
                    idempotent_replay=True,
                )

            # 3. pending assistant 检查 + 租约
            now = AiChatService._utcnow()
            lease_expires_at = now + timedelta(seconds=settings.AI_CHAT_LEASE_SECONDS)
            pending = (
                db.query(AiChatMessage)
                .filter(
                    AiChatMessage.session_id == session_id,
                    AiChatMessage.role == "assistant",
                    AiChatMessage.status == "pending",
                )
                .with_for_update()
                .first()
            )
            if pending is not None:
                expires_at_utc = AiChatService._to_utc(pending.processing_expires_at)
                if expires_at_utc > now:
                    raise ChatConcurrentPendingError(
                        f"Chat session {session_id} has an in-flight assistant message (id={pending.id})"
                    )
                # 租约已过期 → 标记 stale
                pending.status = "stale"
                pending.error_code = "PROCESSING_LEASE_EXPIRED"
                db.flush()

            # 4. 建 user message
            user_msg = AiChatMessage(
                session_id=session_id,
                user_id=user.id,
                client_request_id=payload.client_request_id,
                role="user",
                message_type="chat",
                status="completed",
                content=payload.query,
                metadata_json={
                    "current_page": AiChatService._normalize_current_page(payload.current_page),
                },
                attempt_count=0,
            )
            db.add(user_msg)
            db.flush()

            # 5. 建 assistant pending message
            assistant_msg = AiChatMessage(
                session_id=session_id,
                user_id=user.id,
                client_request_id=None,
                role="assistant",
                message_type="chat",
                status="pending",
                content=None,
                parent_message_id=user_msg.id,
                processing_started_at=now,
                processing_expires_at=lease_expires_at,
                attempt_count=1,
            )
            db.add(assistant_msg)
            db.flush()

            db.commit()

        except Exception:
            db.rollback()
            raise

        # =========================
        # 事务外：调 Dify
        # =========================
        dify_response, dify_error, dify_error_code = AiChatService._call_dify(
            query=payload.query,
            conversation_id=session_obj.dify_conversation_id,
            user=user,
            current_page=payload.current_page,
        )

        # =========================
        # 事务 2：收尾
        # =========================
        try:
            assistant_msg = db.query(AiChatMessage).filter(AiChatMessage.id == assistant_msg.id).first()
            if assistant_msg is None:
                logger.error("Assistant message %s disappeared after transaction 1 commit", assistant_msg.id if assistant_msg else None)
                raise AiChatError("Assistant message lost between transactions")

            if dify_error is None:
                answer = (dify_response or {}).get("answer") or ""
                conversation_id = (dify_response or {}).get("conversation_id") or session_obj.dify_conversation_id
                message_id = (dify_response or {}).get("message_id")
                elapsed_ms = (dify_response or {}).get("elapsed_ms") or 0
                total_tokens = (dify_response or {}).get("total_tokens") or 0
                metadata = (dify_response or {}).get("metadata") or {}

                assistant_msg.content = answer
                assistant_msg.status = "completed"
                assistant_msg.dify_task_id = message_id
                assistant_msg.workflow_run_id = (dify_response or {}).get("workflow_run_id")
                assistant_msg.elapsed_ms = int(elapsed_ms) if elapsed_ms else None
                assistant_msg.total_tokens = int(total_tokens) if total_tokens else None
                assistant_msg.processing_started_at = None
                assistant_msg.processing_expires_at = None
                assistant_msg.metadata_json = {
                    **(assistant_msg.metadata_json or {}),
                    "dify_metadata": metadata,
                }

                if conversation_id and conversation_id != session_obj.dify_conversation_id:
                    session_obj.dify_conversation_id = conversation_id
                session_obj.last_message_at = AiChatService._utcnow()
                session_obj.message_count = (session_obj.message_count or 0) + 2
            else:
                assistant_msg.status = "failed"
                assistant_msg.error_code = dify_error_code or "DIFY_ERROR"
                assistant_msg.error_message = str(dify_error)[:1000]
                assistant_msg.processing_started_at = None
                assistant_msg.processing_expires_at = None
                session_obj.last_message_at = AiChatService._utcnow()
                session_obj.message_count = (session_obj.message_count or 0) + 1

            db.commit()
        except Exception:
            db.rollback()
            raise

        if isinstance(dify_error, DifyTimeoutError):
            raise ChatDifyTimeoutError(str(dify_error))

        return SendMessageResult(
            user_message=user_msg,
            assistant_message=assistant_msg,
            idempotent_replay=False,
        )

    # ------------------------------------------------------------------
    # Stale 清理
    # ------------------------------------------------------------------
    @classmethod
    def cleanup_stale_pending(cls, db: Session) -> int:
        """清理所有 assistant pending 且 lease 已过期的消息。

        启动时调用一次（main.py lifespan）。
        同样逻辑适用于 inspection_ai_analysis.pending 和 schema_snapshot.running
        （后续 C22 / C9 各自实现独立清理入口）。

        Returns:
            更新的行数
        """
        now = cls._utcnow()
        result = db.execute(
            update(AiChatMessage)
            .where(
                and_(
                    AiChatMessage.role == "assistant",
                    AiChatMessage.status == "pending",
                    AiChatMessage.processing_expires_at.isnot(None),
                    AiChatMessage.processing_expires_at <= now,
                )
            )
            .values(
                status="stale",
                error_code="PROCESSING_LEASE_EXPIRED",
                processing_started_at=None,
                processing_expires_at=None,
            )
        )
        affected = result.rowcount or 0
        db.commit()
        if affected > 0:
            logger.warning(
                "AiChatService.cleanup_stale_pending: marked %s assistant messages as stale",
                affected,
            )
        return affected

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _make_session_code() -> str:
        """生成 session 唯一 code（前缀 CHAT- + 16 hex）。"""
        return f"CHAT-{secrets.token_hex(8).upper()}"

    @staticmethod
    def _normalize_current_page(value: Optional[str]) -> str:
        """校验 current_page 白名单。非法值降级为 ai_chat（绝不抛出）。"""
        if not value:
            return "ai_chat"
        if value in AiChatService.CURRENT_PAGE_ALLOWLIST:
            return value
        logger.warning("AiChatService rejected unknown current_page=%r; falling back to ai_chat", value)
        return "ai_chat"

    @staticmethod
    def _utcnow() -> datetime:
        """统一返回 aware UTC datetime。"""
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def _to_utc(dt: Optional[datetime]) -> datetime:
        """统一转 aware UTC datetime。None 直接当作 epoch 之前（一定过期）。"""
        if dt is None:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _call_dify(
        *,
        query: str,
        conversation_id: Optional[str],
        user: User,
        current_page: Optional[str],
    ) -> tuple[Optional[dict[str, Any]], Optional[Exception], Optional[str]]:
        """调用 Dify Chat App。捕获所有 DifyError 异常，返回 (response, error, error_code)。"""
        page_normalized = AiChatService._normalize_current_page(current_page)
        role_value = (user.role or "user").strip() or "user"
        locale_value = (getattr(user, "language", None) or "zh-CN").strip() or "zh-CN"
        inputs: dict[str, Any] = {
            "role": role_value,
            "locale": locale_value,
            "current_page": page_normalized,
        }

        dify_user = f"dbops:{user.id}"

        try:
            resp = DifyService.chat_message(
                query=query,
                inputs=inputs,
                user=dify_user,
                conversation_id=conversation_id,
            )
            return resp, None, None
        except DifyTimeoutError as exc:
            return None, exc, "DIFY_TIMEOUT"
        except DifyConnectionError as exc:
            return None, exc, "DIFY_CONNECTION_ERROR"
        except DifyConfigurationError as exc:
            return None, exc, "DIFY_CONFIGURATION_ERROR"
        except DifyHttpError as exc:
            return None, exc, "DIFY_HTTP_ERROR"
        except DifyResponseFormatError as exc:
            return None, exc, "DIFY_RESPONSE_FORMAT_ERROR"
        except DifyWorkflowFailedError as exc:
            return None, exc, "DIFY_WORKFLOW_FAILED"
        except DifyError as exc:
            return None, exc, "DIFY_ERROR"
