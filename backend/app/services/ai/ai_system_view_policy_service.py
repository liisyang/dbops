"""Phase 3.6B2 C16-F2d commit 2 — AiSystemViewPolicyService.

Per-instance 系统视图白名单评估（plan §21.4 / commit handoff 2026-07-09）：

职责
----
本服务为**纯函数 + 静态方法**集合，不引入新异常类型，不维护会话状态。
三个集成点（callback / preview / context）按以下规则统一消费：

  - get_policy(db, instance_id)        → 行级查找；无行/DB 错误 → None
  - is_active(policy)                  → policy.enabled and bool(policy.allowlist)
  - merged_allowlist(policy, base)     → 合并 snapshot.allowed_tables + policy.allowlist
                                          （去重 + 排序；inactive → 仅 base）
  - filter_denied_tables(policy, qns)  → denylist 命中的 qname 集合
                                          （强于 allowlist；inactive → 空集）

命名规范（per dialect, fix 到集成点调用处）
----
- Oracle:  ``DBA_OBJECTS`` / ``V$LOCK`` （无 schema 前缀；SQL 直接 ``FROM V$LOCK``，
  AST 提取的 qname == lower(no-schema) — 与 snapshot 中存什么一致）
- MSSQL:  ``sys.databases`` / ``sys.dm_exec_sessions`` （schema.name）
- PG:     ``pg_catalog.pg_stat_activity`` / ``information_schema.tables``

存储策略
----
policy.allowlist 按 db_type_code 命名规范直接落地；不强制加 schema 前缀。
集成点统一把 entry 追加到 snapshot.allowed_tables，与 AST validator 提取的
``qname = f"{schema or ''}.{table.lower()}"`` 形式对齐（小写、去重、sorted）。

denylist 比较
----
denylist 元素一律 lowercased 后比较（与 AST validator 内部 lowercase set 一致），
调用方传入的 qname 也统一 lowercase 后比对，规避 Oracle ``V$LOCK`` vs
``v$lock`` 等大小写差异。

容错
----
所有 DB 查询包 try/except；policy 查询失败 → 返回 None（fallback 默认安全：
snapshot 白名单不变；preview 行为不变；context 不追加段）。
绝不破坏三个集成点的主流程（C9 callback 已有同款容错策略 — plan §4.4 P1）。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.models.ai import AiSystemViewPolicy
from app.models.dbops_assets import DbInstance, DbType

logger = logging.getLogger(__name__)


# db_type.type_code → ai_system_view_policy CHECK 约束合法值的规范化映射
# （与 ai_sql_preview_service._DB_TYPE_NORMALIZE 对齐）
_DB_TYPE_NORMALIZE: dict[str, str] = {
    "SQLSERVER": "MSSQL",
}


# =============================================================================
# Service 层
# =============================================================================
class AiSystemViewPolicyService:
    """Per-instance 系统视图白名单评估（commit 2 / C16-F2d）。

    三件静态 API：
      - get_policy           ：DB lookup
      - is_active            ：启用 + 允许列表非空
      - merged_allowlist     ：snapshot.allowed_tables ∪ policy.allowlist
      - filter_denied_tables ：policy.denylist ∩ references

    集成点接线：
      - ai_schema_snapshot_callback_service._save_one
      - ai_sql_preview_service.preview
      - ai_schema_context_service.build_schema_context / _render_schema_context
    """

    # ----- DB lookup -----

    @staticmethod
    def _resolve_db_type_code(db: Session, *, instance_id: int) -> Optional[str]:
        """从 DbInstance → DbType 解析规范化的 db_type_code。

        Returns:
            规范化后的 type_code (POSTGRESQL/ORACLE/MSSQL)，或 None
        """
        if not instance_id or instance_id <= 0:
            return None
        try:
            instance = (
                db.query(DbInstance)
                .filter(DbInstance.id == int(instance_id))
                .first()
            )
            if instance is None:
                return None
            db_type_id = getattr(instance, "db_type_id", None)
            if db_type_id is None:
                return None
            db_type = db.query(DbType).filter(DbType.id == db_type_id).first()
            if db_type is None:
                return None
            raw = str(getattr(db_type, "type_code", "") or "").upper()
            return _DB_TYPE_NORMALIZE.get(raw, raw) if raw else None
        except Exception:
            logger.exception(
                "_resolve_db_type_code failed instance_id=%s (non-fatal)",
                instance_id,
            )
            return None

    @staticmethod
    def get_policy(db: Session, *, instance_id: int) -> Optional[AiSystemViewPolicy]:
        """Fetch policy for instance；优先 instance-level，fallback db_type-level。

        C16-F2d v2 (2026-07-09):
          1. 优先查 instance_id 精确匹配
          2. 未命中 → 解析 instance 的 db_type_code → 查 db_type 默认行
             （instance_id IS NULL AND db_type_code = :code）
          3. 全部未命中 → None

        容错（与 C9 callback service 一致）：
            - exception → logger.exception + 返回 None
            - 主流程不被 policy 错误阻塞
        """
        if not instance_id or instance_id <= 0:
            return None
        try:
            # 1. instance-level policy（精确匹配）
            policy = (
                db.query(AiSystemViewPolicy)
                .filter(AiSystemViewPolicy.instance_id == int(instance_id))
                .first()
            )
            if policy is not None:
                return policy

            # 2. fallback to db_type default
            db_type_code = AiSystemViewPolicyService._resolve_db_type_code(
                db, instance_id=instance_id,
            )
            if db_type_code:
                return (
                    db.query(AiSystemViewPolicy)
                    .filter(
                        AiSystemViewPolicy.instance_id.is_(None),
                        AiSystemViewPolicy.db_type_code == db_type_code,
                    )
                    .first()
                )
            return None
        except Exception:
            logger.exception(
                "AiSystemViewPolicyService.get_policy failed instance_id=%s (non-fatal)",
                instance_id,
            )
            return None

    # ----- activation gate -----

    @staticmethod
    def is_active(policy: Optional[AiSystemViewPolicy]) -> bool:
        """policy 是否生效：enabled=True 且 allowlist 非空。"""
        if policy is None:
            return False
        if not getattr(policy, "enabled", False):
            return False
        allowlist = getattr(policy, "allowlist", None) or []
        return any(isinstance(x, str) and x.strip() for x in allowlist)

    # ----- name normalization -----

    @staticmethod
    def normalize(name: Any) -> str:
        """Lowercase + strip — 用作 set 成员比较的规范化形态。

        与 SqlSafetyService.validate_with_ast 内部 lowercase 规范化对齐：
        所有 cross-component 比较必须用此函数。
        """
        if not isinstance(name, str):
            return ""
        return name.strip().lower()

    @staticmethod
    def _lower_set(items: Optional[Iterable[Any]]) -> set[str]:
        """Iterable → lowercased stripped non-empty strings set."""
        if not items:
            return set()
        out: set[str] = set()
        for item in items:
            if isinstance(item, str):
                n = item.strip().lower()
                if n:
                    out.add(n)
        return out

    # ----- merge & filter -----

    @classmethod
    def merged_allowlist(
        cls,
        policy: Optional[AiSystemViewPolicy],
        base_allowed_tables: Optional[Iterable[str]],
    ) -> list[str]:
        """Force-include policy.allowlist into snapshot.allowed_tables。

        行为：
          - policy inactive → 返回 sorted(set(base))
          - policy active  → 返回 sorted(set(base) ∪ {entry for entry in policy.allowlist if non-empty})

        排序 + 去重（与 C7+ _aggregate_whitelist 输出风格一致）。
        """
        merged: set[str] = set()
        for t in base_allowed_tables or []:
            if isinstance(t, str):
                stripped = t.strip()
                if stripped:
                    merged.add(stripped)
        if cls.is_active(policy):
            for entry in getattr(policy, "allowlist", None) or []:
                if isinstance(entry, str):
                    stripped = entry.strip()
                    if stripped:
                        merged.add(stripped)
        return sorted(merged)

    @classmethod
    def filter_denied_tables(
        cls,
        policy: Optional[AiSystemViewPolicy],
        qualified_names: Optional[Iterable[str]],
    ) -> set[str]:
        """返回在 policy.denylist 中命中的 qualified_names 集合（lowercased）。

        - policy inactive → 空集
        - 命中规则：name in {lower(d) for d in policy.denylist}
        - 输入 qnames 通常来自 AST 提取 (schema.table.lower())，
          denylist 元素也 lowercase 后比对（防御大小写差异）
        """
        if not cls.is_active(policy):
            return set()
        denied_lc = cls._lower_set(getattr(policy, "denylist", None))
        if not denied_lc:
            return set()
        out: set[str] = set()
        for qn in qualified_names or []:
            if not isinstance(qn, str):
                continue
            n = qn.strip().lower()
            if n in denied_lc:
                out.add(n)
        return out

    # ----- admin helper -----

    @staticmethod
    def policy_version(policy: Optional[AiSystemViewPolicy]) -> str:
        """Return policy_version string (or '<none>' for tests/log uniform)."""
        if policy is None:
            return "<none>"
        v = getattr(policy, "policy_version", None)
        return str(v) if v else "<none>"

    # ----- column hints (2026-07-09 bug-fix) -----

    @staticmethod
    def get_column_hints(
        policy: Optional[AiSystemViewPolicy],
    ) -> dict[str, list[str]]:
        """返回 policy.column_hints → 规范化 dict[str, list[str]]。

        policy 为 None / inactive → 返回空 dict。
        值必须是 JSONB object（parsed to Python dict），每个 value
        是 list[str]（非 str → 丢弃）。
        与 _normalize_allowed_columns 输出格式对齐，供
        build_schema_context 合并到 allowed_columns。
        """
        if policy is None:
            return {}
        if not AiSystemViewPolicyService.is_active(policy):
            return {}
        raw = getattr(policy, "column_hints", None)
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for k, v in raw.items():
            if not isinstance(k, str) or not k.strip():
                continue
            key = k.strip()
            if isinstance(v, list):
                cols = [str(x).strip() for x in v if x is not None and str(x).strip()]
                if cols:
                    out[key] = cols
            elif isinstance(v, str) and v.strip():
                out[key] = [v.strip()]
        return out
