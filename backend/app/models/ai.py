"""
AI Copilot Models（Phase 3.6）

C2 范围：ai_chat_session + ai_chat_message
C6 范围：ai_sql_schema_snapshot (Phase 3.6B0)
C12 范围：ai_sql_audit (Phase 3.6B1 — SQL Preview/Execute 审计)
后续 commit 追加：
- C22: inspection_ai_analysis (Phase 3.6C1)

设计要点：
- 使用 DbopsAssetBase 复用 dbops schema 的元数据（与 dbops_assets.py 一致）
- `metadata` 列映射为 `metadata_json` Python 属性（SQLAlchemy Base.metadata 是保留属性）
- TIMESTAMPTZ 字段使用 datetime.timezone.utc-aware 类型
- C6 AiSchemaSnapshot 五态机：pending/running/success/failed/unavailable（应用层条件 UPDATE 控制，
  数据库层 CHECK 约束兜底；plan §2.2 P0-2 修正）
- C12 AiSqlAudit 七态机：not_requested/pending/running/success/failed/timeout/cancelled
  （plan §2.3 P0-6 修正 — 应用层条件 UPDATE 控制，DB 仅约束枚举值）
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
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
            # C14: 新增 'sql_preview_link'（Chat 流内 SQL Preview 卡片）；
            # 与 db/dbops_phase3_6b1_ai_sql_execute.sql 保持一致
            "message_type IN ('chat', 'sql_preview', 'sql_preview_link', 'sql_result', 'error')",
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


# =============================================================================
# C6: AI Schema Snapshot（Phase 3.6B0）
# =============================================================================
class AiSchemaSnapshotStatus:
    """Schema Snapshot 状态枚举（plan §2.2 P0-6 修正：应用层常量避免散落字符串）。

    状态机：
    - pending  → 初始，等待 collector 启动
    - running  → collector 执行中
    - success  → 采集完成且数据完整（payload 必填字段齐）
    - failed   → 采集失败（error_message 必填）
    - unavailable → 该 db_type 当前不支持（如 ORACLE/MSSQL/MySQL，capabilities 端点不暴露）
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    ALL = (PENDING, RUNNING, SUCCESS, FAILED, UNAVAILABLE)


class AiSchemaSnapshot(DbopsAssetBase):
    """数据库结构快照（instance + database 维度）。

    设计要点（plan §2.2 + §4.3）：
    - 两阶段发布：success 后才设 is_current=true，旧 snapshot 切 false（应用层 C10 控制）
    - TTL：success 时 expires_at 必须设置（service 端按 AI_SCHEMA_SNAPSHOT_TTL_HOURS 计算）
    - 五态机：CHECK 约束在 DB 层兜底，应用层用 AiSchemaSnapshotStatus 常量
    - SHA-256 64 hex：snapshot_hash 长度 64 由 DB CHECK 约束保证
    """

    __tablename__ = "ai_sql_schema_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    instance_id = Column(
        BigInteger,
        ForeignKey("dbops.db_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    db_type_code = Column(String(50), nullable=False)
    # database_name NOT NULL：无明确 database 时存 '<default>'（plan line 146）
    database_name = Column(String(200), nullable=False)
    schema_name = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, server_default=text("'pending'"))

    # 白名单：采集到的 schema / table / column（C7+ 填充）
    allowed_schemas = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    allowed_tables = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    allowed_columns = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    denied_columns = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    # 两阶段发布标志
    is_current = Column(Boolean, nullable=False, server_default=text("false"))

    # 关联 AWX 采集运行（删除 collector_run 时置 NULL）
    collector_run_id = Column(
        BigInteger,
        ForeignKey("dbops.collector_run.id", ondelete="SET NULL"),
        nullable=True,
    )

    snapshot_hash = Column(String(64), nullable=True)
    total_tables = Column(Integer, nullable=True)
    total_columns = Column(Integer, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    collected_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # CHECK 约束（与 DDL 对齐）
    __table_args__ = (
        CheckConstraint(
            "db_type_code IN ('POSTGRESQL', 'ORACLE', 'MSSQL', 'MYSQL')",
            name="chk_ai_sql_schema_snapshot_db_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed', 'unavailable')",
            name="chk_ai_sql_schema_snapshot_status",
        ),
        # 状态机完整性（plan §2.2 P0-2 修正）— SQLAlchemy 端用 Python
        # 字符串表达（不直接用 Python 字面量拼接，避免 SQL 注入风险）
        CheckConstraint(
            "(status = 'success' AND snapshot_hash IS NOT NULL "
            "AND allowed_schemas IS NOT NULL "
            "AND collected_at IS NOT NULL "
            "AND expires_at IS NOT NULL) "
            "OR "
            "(status IN ('pending', 'running') "
            "AND error_message IS NULL AND error_code IS NULL) "
            "OR "
            "(status IN ('failed', 'unavailable') "
            "AND error_message IS NOT NULL)",
            name="chk_ai_sql_schema_snapshot_payload",
        ),
        CheckConstraint(
            "snapshot_hash IS NULL OR length(snapshot_hash) = 64",
            name="chk_ai_sql_schema_snapshot_hash_len",
        ),
        # 部分唯一索引：同一 (instance_id, database_name) 同时只有一个 is_current=true
        Index(
            "uq_ai_sql_schema_snapshot_current",
            "instance_id",
            "database_name",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
        # 辅助索引（与 DDL 对齐）
        Index(
            "idx_ai_sql_schema_snapshot_instance_status",
            "instance_id",
            "status",
        ),
        Index(
            "idx_ai_sql_schema_snapshot_collector_run",
            "collector_run_id",
            postgresql_where=text("collector_run_id IS NOT NULL"),
        ),
        Index(
            "idx_ai_sql_schema_snapshot_expires_at",
            "expires_at",
            postgresql_where=text("status = 'success'"),
        ),
        {"schema": "dbops"},
    )

    def __repr__(self) -> str:
        return (
            f"<AiSchemaSnapshot id={self.id} instance_id={self.instance_id} "
            f"db_type={self.db_type_code} database={self.database_name} "
            f"status={self.status} is_current={self.is_current}>"
        )

    def is_usable(self) -> bool:
        """判断 snapshot 是否可被 SQL Preview 消费（plan §4.3 验收口径）。

        判定条件（全部满足）：
        1. status == 'success'
        2. is_current == True
        3. expires_at 未过期（无 expires_at 视为永久有效）
        """
        if self.status != AiSchemaSnapshotStatus.SUCCESS:
            return False
        if not self.is_current:
            return False
        if self.expires_at is not None and self.expires_at < datetime.now(timezone.utc):
            return False
        return True


# =============================================================================
# C12: AI SQL Audit（Phase 3.6B1）
# =============================================================================
class AiSqlAuditPreviewSafety:
    """Preview 阶段 SQL 安全校验结果（plan §2.3 line 195）。

    二态机：
    - passed   — AST 校验通过，approved_sql 落库，可供后续 Execute 阶段使用
    - rejected — AST 校验未通过（白名单不符 / 危险语句 / 解析失败等），
                 approved_sql 不落库，preview_safety_reason 记录原因
    """

    PASSED = "passed"
    REJECTED = "rejected"
    ALL = (PASSED, REJECTED)


class AiSqlAuditExecutionSafety:
    """Execute 阶段再次校验 approved_sql_hash 一致性（plan §5 P0-4）。

    NULL = 尚未进入 Execute 阶段（C12 Preview 不填充，留给 C17-C19）。
    """

    PASSED = "passed"
    REJECTED = "rejected"
    ALL = (PASSED, REJECTED)


class AiSqlAuditExecutionStatus:
    """Execute 状态机七态（plan §2.3 line 219-223 + §19 P0-6 修正）。

    状态机：
        not_requested → pending → running → success
                                      ├→ failed
                                      ├→ timeout
                                      └→ cancelled

    数据库 CHECK 仅约束枚举值；状态转换由应用层条件 UPDATE 控制
    （UPDATE ... WHERE execution_status IN (...)）。
    """

    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ALL = (NOT_REQUESTED, PENDING, RUNNING, SUCCESS, FAILED, TIMEOUT, CANCELLED)


class AiSqlAudit(DbopsAssetBase):
    """SQL Preview/Execute 审计（plan §2.3 line 192-197 + §5 P0-4）。

    关键设计：
    - 双轨 SQL：generated_sql（Dify 原始，审计追溯）vs approved_sql（AST 重写，权威）
    - 双 SHA-256 hash：generated_sql_hash + approved_sql_hash；Execute 时再次校验
      `SHA-256(rule_config.sql_text) == approved_sql_hash`
    - Schema 强绑定：schema_snapshot_id + schema_policy_hash；Execute 时校验
      snapshot.is_current + hash 一致，否则 409 要求重新 Preview
    - 七态机 execution_status：状态转换由应用层条件 UPDATE 控制（C17-C19 实现）
    """

    __tablename__ = "ai_sql_audit"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 关联（可空：直接调用 preview 时可不带 chat 上下文）
    session_id = Column(
        BigInteger,
        ForeignKey("dbops.ai_chat_session.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id = Column(
        BigInteger,
        ForeignKey("dbops.ai_chat_message.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_message_id = Column(
        BigInteger,
        ForeignKey("dbops.ai_chat_message.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dbops.users.id", ondelete="SET NULL", use_alter=True, name="fk_ai_sql_audit_user_model"),
        nullable=True,
    )

    # 目标实例（NOT NULL — 删除实例时级联清理 audit）
    instance_id = Column(
        BigInteger,
        ForeignKey("dbops.db_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    db_type_code = Column(String(50), nullable=False)

    # 用户原始问题
    user_question = Column(Text, nullable=False)

    # Dify 生成（原始）— 审计追溯
    generated_sql = Column(Text, nullable=True)
    generated_sql_hash = Column(String(64), nullable=True)

    # AST 重写后（权威）— Execute 时唯一使用
    approved_sql = Column(Text, nullable=True)
    approved_sql_hash = Column(String(64), nullable=True)

    # Preview 安全状态（应用层写入，Dify 响应 + AST 校验后落库）
    preview_safety_status = Column(
        String(20), nullable=False, server_default=text("'rejected'")
    )
    preview_safety_reason = Column(Text, nullable=True)

    # Execute 安全状态（NULL = 尚未 Execute；C17-C19 填充）
    execution_safety_status = Column(String(20), nullable=True)
    execution_safety_reason = Column(Text, nullable=True)

    # 策略版本（与 schema_policy_hash 区分：safety_policy_version 是 SQL 安全规则版本）
    safety_policy_version = Column(String(50), nullable=True)

    # Schema 强绑定
    schema_snapshot_id = Column(
        BigInteger,
        ForeignKey("dbops.ai_sql_schema_snapshot.id", ondelete="SET NULL"),
        nullable=True,
    )
    schema_policy_hash = Column(String(64), nullable=True)

    # Dify 调用追踪
    dify_workflow_run_id = Column(String(100), nullable=True)
    sql_workflow_version = Column(String(50), nullable=True)

    # 时间戳
    previewed_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # 执行状态机
    execution_status = Column(
        String(20), nullable=False, server_default=text("'not_requested'")
    )

    # AWX Collector 关联
    collector_run_id = Column(
        BigInteger,
        ForeignKey("dbops.collector_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    collector_run_item_id = Column(
        BigInteger,
        ForeignKey("dbops.collector_run_item.id", ondelete="SET NULL"),
        nullable=True,
    )
    # C16-F1：Execute launch 成功后回填（plan §7 F1）；幂等 UPDATE WHERE
    # awx_job_id IS NULL；不通过 FK 关联 collector_run（launch_job 后 collector
    # 可能未落 run 行；awx_job_id 是更上游的 AWX 标识，独立保留更可靠）
    awx_job_id = Column(BigInteger, nullable=True)

    # 执行结果统计
    row_count = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # 错误信息
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # CHECK 约束（与 DDL 对齐）
    __table_args__ = (
        CheckConstraint(
            "db_type_code IN ('POSTGRESQL', 'ORACLE', 'MSSQL', 'MYSQL')",
            name="chk_ai_sql_audit_db_type",
        ),
        CheckConstraint(
            "preview_safety_status IN ('passed', 'rejected')",
            name="chk_ai_sql_audit_preview_safety",
        ),
        CheckConstraint(
            "execution_safety_status IS NULL OR "
            "execution_safety_status IN ('passed', 'rejected')",
            name="chk_ai_sql_audit_execution_safety",
        ),
        CheckConstraint(
            "execution_status IN ("
            "'not_requested', 'pending', 'running', 'success', "
            "'failed', 'timeout', 'cancelled')",
            name="chk_ai_sql_audit_execution_status",
        ),
        CheckConstraint(
            "(generated_sql_hash IS NULL OR length(generated_sql_hash) = 64) "
            "AND (approved_sql_hash IS NULL OR length(approved_sql_hash) = 64) "
            "AND (schema_policy_hash IS NULL OR length(schema_policy_hash) = 64)",
            name="chk_ai_sql_audit_hash_len",
        ),
        CheckConstraint(
            "(preview_safety_status = 'passed' "
            "AND user_question IS NOT NULL "
            "AND approved_sql IS NOT NULL "
            "AND approved_sql_hash IS NOT NULL "
            "AND previewed_at IS NOT NULL "
            "AND schema_snapshot_id IS NOT NULL "
            "AND schema_policy_hash IS NOT NULL "
            "AND preview_safety_reason IS NULL) "
            "OR "
            "(preview_safety_status = 'rejected' "
            "AND preview_safety_reason IS NOT NULL)",
            name="chk_ai_sql_audit_payload",
        ),
        # 辅助索引（与 DDL 对齐）
        Index(
            "idx_ai_sql_audit_instance_created",
            "instance_id",
            "created_at",
        ),
        Index(
            "idx_ai_sql_audit_user_created",
            "user_id",
            "created_at",
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "idx_ai_sql_audit_session_created",
            "session_id",
            "created_at",
            postgresql_where=text("session_id IS NOT NULL"),
        ),
        Index(
            "idx_ai_sql_audit_execution_status",
            "execution_status",
            postgresql_where=text("execution_status IN ('pending', 'running')"),
        ),
        Index(
            "idx_ai_sql_audit_collector_run",
            "collector_run_id",
            postgresql_where=text("collector_run_id IS NOT NULL"),
        ),
        Index(
            "idx_ai_sql_audit_schema_snapshot",
            "schema_snapshot_id",
            postgresql_where=text("schema_snapshot_id IS NOT NULL"),
        ),
        {"schema": "dbops"},
    )

    def __repr__(self) -> str:
        return (
            f"<AiSqlAudit id={self.id} instance_id={self.instance_id} "
            f"db_type={self.db_type_code} preview={self.preview_safety_status} "
            f"execution={self.execution_status}>"
        )
