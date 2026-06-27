from __future__ import annotations

import os
from functools import lru_cache
from pydantic_settings import BaseSettings

# 获取 backend 目录路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    SECRET_KEY: str = ""
    POSTGRES_HOST: str = "10.134.185.85"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "dbops"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "dbops"
    SQLALCHEMY_DATABASE_URI: str = ""

    # SSH 凭据
    SSH_USER: str = "dbaacc"
    SSH_PASSWORD: str = ""
    SSH_KEY: str = "~/.ssh/id_ed25519"
    SSH_USER_GROUP: str = "dba"
    SSH_USER_HOME_PREFIX: str = "/home"
    SSH_PROFILE_PATH: str = "/home"
    SSH_TIMEOUT: int = 30
    SSH_PORT: int = 22

    # RQ / Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Ansible 配置
    ANSIBLE_TIMEOUT: int = 10
    ANSIBLE_FORKS: int = 20

    # 主机状态探测
    HOST_CHECK_INTERVAL: int = 600

    # CORS
    CORS_ORIGINS: str = ""

    # Upload
    UPLOAD_FOLDER: str = "uploads"
    ALLOWED_EXTENSIONS: set = {"xlsx", "xls"}

    # AWX / 资产校验
    AWX_URL: str = ""
    AWX_USER: str = ""
    AWX_PASSWORD: str = ""
    AWX_VERIFY_JOB_TEMPLATE_ID: int = 0
    AWX_VERIFY_JOB_TEMPLATE_NAME: str = "JT_ASSET_VERIFY_PORT"
    AWX_COLLECTOR_JOB_TEMPLATE_ID: int = 0
    AWX_COLLECTOR_JOB_TEMPLATE_NAME: str = "JT_DBOPS_COLLECTOR_GENERIC"
    COLLECTOR_CALLBACK_URL: str = ""
    COLLECTOR_CALLBACK_TOKEN: str = ""
    AWX_REQUEST_TIMEOUT: int = 30

    # AWX 批量调度
    AWX_DEFAULT_INSTANCE_GROUP: str = "default"
    # AWX Job Template 已绑定的 credential ID 列表（逗号分隔），launch 时必须保留
    AWX_PREBOUND_CREDENTIAL_IDS: str = ""

    # Collector 调度（Phase 3.4 P0-4/5/6 批量校验底座）
    # 全局并发上限
    COLLECTOR_GLOBAL_MAX_RUNNING_DISPATCHES: int = 20
    # 单 batch_run 并发上限
    COLLECTOR_BATCH_MAX_RUNNING_DISPATCHES: int = 10
    # 单 instance_group 并发上限
    COLLECTOR_IG_MAX_RUNNING_DISPATCHES: int = 5
    # 单 network_zone 并发上限
    COLLECTOR_NETWORK_ZONE_MAX_RUNNING_DISPATCHES: int = 3
    # AWX launch QPS 限速（每秒 launch 次数）
    COLLECTOR_AWX_LAUNCH_QPS: float = 2.0
    # 调度器 beat 间隔（秒）
    COLLECTOR_DISPATCH_SCHEDULER_INTERVAL: int = 15
    # 单 run 超时阈值（分钟），超过后由 timeout_recovery_task 回收
    COLLECTOR_RUN_TIMEOUT_MINUTES: int = 30
    # timeout_recovery beat 间隔（秒）
    COLLECTOR_TIMEOUT_RECOVERY_INTERVAL: int = 60
    # 单用户最大 in-flight batch runs 数量 (I2 rate limit)
    COLLECTOR_MAX_BATCH_RUNS_PER_USER: int = 3

    # =============================================================================
    # AI Copilot 配置（Phase 3.6）
    # =============================================================================
    # 5 个独立功能开关（按 plan §15 环境启用顺序灰度开启）
    AI_CHAT_ENABLED: bool = False
    AI_SQL_PREVIEW_ENABLED: bool = False
    AI_SQL_EXECUTION_ENABLED: bool = False
    AI_REPORT_ANALYSIS_ENABLED: bool = False
    AI_REPORT_EXPORT_AI_ENABLED: bool = False

    # Dify 服务（3 个独立 app + base_url + 4 个独立超时）
    DIFY_BASE_URL: str = ""
    DIFY_CHAT_API_KEY: str = ""
    DIFY_SQL_WORKFLOW_KEY: str = ""
    DIFY_REPORT_WORKFLOW_KEY: str = ""
    DIFY_CONNECT_TIMEOUT_SECONDS: float = 10.0
    DIFY_CHAT_TIMEOUT_SECONDS: float = 60.0
    DIFY_SQL_TIMEOUT_SECONDS: float = 60.0
    DIFY_REPORT_TIMEOUT_SECONDS: float = 120.0

    # Dify Workflow 版本号（用作分析缓存键之一，source_data_hash + workflow_version）
    DIFY_SQL_WORKFLOW_VERSION: str = "2026-06-27-v1"
    DIFY_REPORT_WORKFLOW_VERSION: str = "2026-06-27-v1"

    # Chat 租约（plan §2.1 P0-5）— assistant pending 消息的有效期
    AI_CHAT_LEASE_SECONDS: int = 90
    # Chat 历史分页上限
    AI_CHAT_MAX_MESSAGES_PER_SESSION: int = 500
    # Chat 单页列表分页上限
    AI_CHAT_MAX_SESSIONS_PER_USER: int = 200

    # Schema Snapshot 限制（Phase 3.6B0）
    AI_SCHEMA_SNAPSHOT_TTL_HOURS: int = 24
    AI_SCHEMA_CONTEXT_MAX_CHARS: int = 30000
    AI_SCHEMA_MAX_TABLES: int = 100
    AI_SCHEMA_MAX_COLUMNS_PER_TABLE: int = 100
    AI_SCHEMA_COLLECTION_TIMEOUT_SECONDS: int = 300
    AI_SCHEMA_RESULT_MAX_ROWS: int = 20000
    AI_SCHEMA_RESULT_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB

    # SQL 执行结果限制（Phase 3.6B1/B2）
    AI_SQL_RESULT_MAX_ROWS: int = 200
    AI_SQL_RESULT_MAX_COLUMNS: int = 100
    AI_SQL_RESULT_MAX_CELL_CHARS: int = 4000
    AI_SQL_RESULT_MAX_BYTES: int = 2 * 1024 * 1024  # 2MB

    class Config:
        env_file = os.path.join(BASE_DIR, '.env')
        extra = "allow"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        missing = []
        if not self.SECRET_KEY:
            missing.append("SECRET_KEY")
        if not self.POSTGRES_PASSWORD:
            missing.append("POSTGRES_PASSWORD")
        if missing:
            raise ValueError(
                f"缺少关键配置: {', '.join(missing)}。"
                f"请在 {os.path.join(BASE_DIR, '.env')} 文件中设置这些环境变量。"
            )
        if not self.SQLALCHEMY_DATABASE_URI:
            self.SQLALCHEMY_DATABASE_URI = (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

    def validate_ai_config(self) -> None:
        """特征感知校验 AI Copilot 配置（plan §11 P1 解耦）。

        设计原则：
        - AI_CHAT_ENABLED=false → 不要求 DIFY_BASE_URL/DIFY_CHAT_API_KEY
        - AI_SQL_PREVIEW_ENABLED/AI_SQL_EXECUTION_ENABLED=false → 不要求 DIFY_SQL_WORKFLOW_KEY
        - AI_REPORT_ANALYSIS_ENABLED/AI_REPORT_EXPORT_AI_ENABLED=false → 不要求 DIFY_REPORT_WORKFLOW_KEY
        - 任一功能开启 → 必须有 DIFY_BASE_URL（因为所有 Dify 调用都走它）

        不在 __init__ 中自动调用，main.py lifespan 显式调用一次。
        这样测试可以自由构造 Settings 而不触发校验。
        """
        any_ai_enabled = (
            self.AI_CHAT_ENABLED
            or self.AI_SQL_PREVIEW_ENABLED
            or self.AI_SQL_EXECUTION_ENABLED
            or self.AI_REPORT_ANALYSIS_ENABLED
            or self.AI_REPORT_EXPORT_AI_ENABLED
        )
        if not any_ai_enabled:
            return  # 全部关闭时跳过校验
        missing = []
        if not self.DIFY_BASE_URL:
            missing.append("DIFY_BASE_URL")
        if self.AI_CHAT_ENABLED and not self.DIFY_CHAT_API_KEY:
            missing.append("DIFY_CHAT_API_KEY (AI_CHAT_ENABLED=true)")
        if (self.AI_SQL_PREVIEW_ENABLED or self.AI_SQL_EXECUTION_ENABLED) and not self.DIFY_SQL_WORKFLOW_KEY:
            missing.append("DIFY_SQL_WORKFLOW_KEY (SQL 功能开启)")
        if (self.AI_REPORT_ANALYSIS_ENABLED or self.AI_REPORT_EXPORT_AI_ENABLED) and not self.DIFY_REPORT_WORKFLOW_KEY:
            missing.append("DIFY_REPORT_WORKFLOW_KEY (Report 功能开启)")
        if missing:
            raise ValueError(
                f"AI Copilot 配置缺失: {', '.join(missing)}。"
                f"请在 {os.path.join(BASE_DIR, '.env')} 中设置这些环境变量，"
                f"或关闭对应功能开关。"
            )

    @property
    def dify_configured(self) -> bool:
        """是否有任一 AI 功能启用（用于 capabilities 端点判断）。"""
        return (
            self.AI_CHAT_ENABLED
            or self.AI_SQL_PREVIEW_ENABLED
            or self.AI_SQL_EXECUTION_ENABLED
            or self.AI_REPORT_ANALYSIS_ENABLED
            or self.AI_REPORT_EXPORT_AI_ENABLED
        )

    @property
    def sql_supported_db_types(self) -> list[str]:
        """当前 SQL Preview/Execute 支持的 db_type 列表。

        首版仅 PostgreSQL（plan §4.8）。其他方言 AST 框架保留但测试不要求通过。
        """
        if not (self.AI_SQL_PREVIEW_ENABLED or self.AI_SQL_EXECUTION_ENABLED):
            return []
        return ["POSTGRESQL"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
