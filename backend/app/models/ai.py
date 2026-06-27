"""
AI Copilot Models（Phase 3.6）

C2 范围：ai_chat_session + ai_chat_message
后续 commit 追加：
- C6: ai_sql_schema_snapshot (Phase 3.6B0)
- C12: ai_sql_audit (Phase 3.6B1)
- C22: inspection_ai_analysis (Phase 3.6C1)

设计要点：
- 使用 DbopsAssetBase 复用 dbops schema 的元数据（与 dbops_assets.py 一致）
- `metadata` 列映射为 `metadata_json` Python 属性（SQLAlchemy Base.metadata 是保留属性）
- TIMESTAMPTZ 字段使用 datetime.timezone.utc-aware 类型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.dbops_assets import DbopsAssetBase


# -----------------------------------------------------------------------------
# 1. AiChatSession — 聊天会话
# -----------------------------------------------------------------------------
class AiChatSession(DbopsAssetBase):
    """聊天会话（user 维度）。"""

    __tablename__ = "ai_chat_session"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_code = Column(String(100), nullable=False, unique=True, index=True)
    # 注：FK 直接引用 User.__table__ 而非字符串 "dbops.users.id" —
    # 避免 User（独立 declarative_base）与 DbopsAssetBase 跨 MetaData 解析失败
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dbops.users.id", ondelete="SET NULL", use_alter=True, name="fk_ai_chat_session_user"),
        nullable=True,
    )
    title = Column(String(200), nullable=False, server_default=text("'新会话'"))
    dify_conversation_id = Column(String(200), nullable=True)
    model_provider = Column(String(50), nullable=False, server_default=text("'dify'"))
    message_count = Column(Integer, nullable=False, server_default=text("0"))
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    messages = relationship(
        "AiChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# -----------------------------------------------------------------------------
# 2. AiChatMessage — 聊天消息
# -----------------------------------------------------------------------------
class AiChatMessage(DbopsAssetBase):
    """聊天消息（user / assistant / system）。

    重要：Python 属性 `metadata_json` 映射到列名 `metadata`（避免与 Base.metadata 保留属性冲突）。
    """

    __tablename__ = "ai_chat_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(
        BigInteger,
        ForeignKey("dbops.ai_chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dbops.users.id", ondelete="SET NULL", use_alter=True, name="fk_ai_chat_message_user"),
        nullable=True,
    )
    client_request_id = Column(UUID(as_uuid=True), nullable=True)
    role = Column(String(20), nullable=False)
    message_type = Column(String(30), nullable=False, server_default=text("'chat'"))
    status = Column(String(20), nullable=False, server_default=text("'pending'"))
    content = Column(Text, nullable=True)
    parent_message_id = Column(
        BigInteger,
        ForeignKey("dbops.ai_chat_message.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 关键：Python 属性 metadata_json 映射到列名 metadata
    metadata_json = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Dify 响应元数据
    dify_task_id = Column(String(100), nullable=True)
    workflow_run_id = Column(String(100), nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    # 错误与状态
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)

    # 租约机制（plan §2.1 P0-5）
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_expires_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, server_default=text("0"))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # CHECK 约束（与 DDL 对齐）
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="chk_ai_chat_message_role",
        ),
        CheckConstraint(
            "message_type IN ('chat', 'sql_preview', 'sql_result', 'error')",
            name="chk_ai_chat_message_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'stale')",
            name="chk_ai_chat_message_status",
        ),
        # 部分唯一索引由 DDL 创建（plan §2.1 P0-5）：
        #   - UNIQUE(session_id, client_request_id) WHERE role='user' AND client_request_id IS NOT NULL
        #   - UNIQUE(session_id) WHERE role='assistant' AND status='pending'
        # 在 SQLAlchemy 端用 Index(... postgresql_where=...) 表达，便于 ORM 识别
        Index(
            "uq_ai_chat_message_session_client_request_idx",
            "session_id",
            "client_request_id",
            unique=True,
            postgresql_where=text("role = 'user' AND client_request_id IS NOT NULL"),
        ),
        Index(
            "uq_ai_chat_message_assistant_pending_idx",
            "session_id",
            unique=True,
            postgresql_where=text("role = 'assistant' AND status = 'pending'"),
        ),
        Index(
            "idx_ai_chat_message_session_created",
            "session_id",
            "created_at",
        ),
        Index(
            "idx_ai_chat_message_status_pending",
            "status",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "idx_ai_chat_message_processing_expires",
            "processing_expires_at",
            postgresql_where=text("status = 'pending' AND role = 'assistant'"),
        ),
        Index(
            "idx_ai_chat_message_parent",
            "parent_message_id",
            postgresql_where=text("parent_message_id IS NOT NULL"),
        ),
        {"schema": "dbops"},
    )

    # Relationships
    session = relationship("AiChatSession", back_populates="messages")
    parent = relationship("AiChatMessage", remote_side="AiChatMessage.id", backref="replies")

    def __repr__(self) -> str:
        return (
            f"<AiChatMessage id={self.id} session_id={self.session_id} "
            f"role={self.role} status={self.status} type={self.message_type}>"
        )
