from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import AssetChangeProposal, DbInstance, Server
from app.services.asset_event_history_service import record_event


logger = logging.getLogger(__name__)


# 资产校验功能优化 v2 / 2026-06-17:
# 字段更新白名单。apply 必须在白名单内才允许写入正式资产表。
# 原因：某些字段语义不一致（database_status vs db_instance.status）或影响面大
# （server.ip_address 网络拓扑），不应自动 apply。
APPLYABLE_FIELDS: dict[str, set[str]] = {
    "db_instance": {"port", "instance_name", "service_name", "node_role", "db_size_gb", "db_version"},
    "server": {"hostname", "cpu_cores", "memory_gb", "disk_gb"},
}

# C2 (PR review 2026-06-20): node_role apply 必须走 chk_node_role CHECK 约束白名单
# 避免绕过约束导致事务回滚连带其他 proposal 失败。
APPLYABLE_NODE_ROLES = {"primary", "standby", "single", "member", "unknown"}


def _coerce_field(value: Any, target_type: str, *, allowed_values: set[str] | None = None) -> Any:
    """C1 (PR review 2026-06-20): 统一 int / float / str coerce + 白名单校验。

    Numeric(10,2)/(12,2) 列（memory_gb / disk_gb / db_size_gb）走 float，
    避免 `int("64.5") == 64` 截断。
    """
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return None
    if target_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"无法转换为整数：{value!r}")
    if target_type == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"无法转换为浮点数：{value!r}")
    if target_type == "str":
        coerced = str(value)
        if allowed_values is not None:
            allowed_lower = {v.lower() for v in allowed_values}
            if coerced.lower() not in allowed_lower:
                raise ValueError(
                    f"值 {coerced!r} 不在允许集合 {sorted(allowed_values)} 内"
                )
            # 命中白名单 → 规范化返回小写形式
            # (chk_node_role 等 CHECK 约束存的是 'primary' 小写规范值)
            coerced = coerced.lower()
        return coerced
    raise ValueError(f"未支持的 target_type: {target_type}")


# ============================================================================
# I10 (PR review 2026-06-20): field applier 注册表 — 每个 apply 字段一个函数，
# 消除 apply_proposal 内 200 行 if/elif 阶梯。新增字段 = 加一行注册表。
# ============================================================================


def _apply_db_instance_port(
    db: Session,
    instance: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    """Apply port change to a DbInstance, including trust/reachability reset."""
    before = instance.port
    if proposal_type == "PORT_CANDIDATE_CONFLICT":
        new_port = int(selected_value)
    else:
        new_port = _coerce_field(proposal.suggested_value, "int")
    instance.port = new_port
    instance.trust_status = "unverified"
    instance.reachability_status = "unknown"
    instance.verify_message = "PORT_CHANGED_PENDING_REVERIFY"
    instance.verify_detail = {
        "proposal_id": int(proposal.id),
        "proposal_type": proposal_type,
        "field_path": "port",
        "before_port": before,
        "after_port": instance.port,
    }
    return before, instance.port


def _apply_db_instance_str_field(
    db: Session,
    instance: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    """Generic str-type field setter for DbInstance."""
    field = (proposal.field_path or "").strip()
    before = getattr(instance, field)
    setattr(instance, field, _coerce_field(proposal.suggested_value, "str"))
    return before, getattr(instance, field)


def _apply_db_instance_node_role(
    db: Session,
    instance: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    """Apply node_role with CHECK constraint whitelist validation."""
    before = instance.node_role
    instance.node_role = _coerce_field(
        proposal.suggested_value, "str", allowed_values=APPLYABLE_NODE_ROLES
    )
    return before, instance.node_role


def _apply_db_instance_float_field(
    db: Session,
    instance: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    """Generic float-type field setter for DbInstance (Numeric columns)."""
    field = (proposal.field_path or "").strip()
    before = getattr(instance, field)
    setattr(instance, field, _coerce_field(proposal.suggested_value, "float"))
    return before, getattr(instance, field)


def _apply_db_instance_version(
    db: Session,
    instance: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    """Apply db_version with multi-step lookup + idempotent auto-create."""
    from app.models.dbops_assets import DbVersion

    before = instance.db_version_id
    version_val = _coerce_field(proposal.suggested_value, "str")
    if version_val:
        version_str = version_val.strip()
        if not version_str:
            raise ValueError("db_version 字符串为空或全空白")

        db_type_id = instance.db_type_id
        base_q = db.query(DbVersion).filter(DbVersion.db_type_id == db_type_id)

        matched = None
        # 1) Exact match on version_name
        matched = base_q.filter(DbVersion.version_name == version_str).first()
        # 2) Exact match on version_code
        if matched is None:
            matched = base_q.filter(DbVersion.version_code == version_str).first()
        # 3) version_name contains version_str (short inside long)
        if matched is None:
            matched = base_q.filter(
                DbVersion.version_name.like(f"%{version_str}%")
            ).first()
        # 4) version_str contains version_name (reverse of step 3)
        if matched is None:
            for c in base_q.all():
                if c.version_name and c.version_name in version_str:
                    matched = c
                    break
        # 5) Evidence fallback: version_full from proposal evidence
        if matched is None:
            evidence = proposal.evidence or {}
            ev_version_full = evidence.get("version_full")
            if ev_version_full:
                ev_str = str(ev_version_full).strip()
                matched = base_q.filter(DbVersion.version_name == ev_str).first()
                if matched is None:
                    matched = base_q.filter(DbVersion.version_code == ev_str).first()
        # 6) Idempotent recheck + auto-create
        if matched is None:
            recheck = base_q.filter(DbVersion.version_name == version_str).first()
            if recheck is None:
                recheck = base_q.filter(DbVersion.version_code == version_str).first()
            matched = recheck
        if matched is None:
            now = AssetProposalService._now()
            matched = DbVersion(
                db_type_id=int(db_type_id),
                version_code=version_str,
                version_name=version_str,
                lifecycle_status="unknown",
                risk_level="unknown",
                is_supported=True,
                is_recommended=False,
                created_at=now,
                updated_at=now,
            )
            db.add(matched)
            db.flush()
            logger.info(
                "apply_proposal(db_version): auto-created DbVersion "
                "id=%s version_name=%s for db_type_id=%s",
                matched.id, version_str, db_type_id,
            )

        instance.db_version_id = int(matched.id)
    else:
        instance.db_version_id = None
    return before, instance.db_version_id


def _apply_server_str_field(
    db: Session,
    server: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    field = (proposal.field_path or "").strip()
    before = getattr(server, field)
    setattr(server, field, _coerce_field(proposal.suggested_value, "str"))
    return before, getattr(server, field)


def _apply_server_int_field(
    db: Session,
    server: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    field = (proposal.field_path or "").strip()
    before = getattr(server, field)
    setattr(server, field, _coerce_field(proposal.suggested_value, "int"))
    return before, getattr(server, field)


def _apply_server_float_field(
    db: Session,
    server: Any,
    proposal: Any,
    proposal_type: str,
    selected_value: int | None,
) -> tuple[Any, Any]:
    field = (proposal.field_path or "").strip()
    before = getattr(server, field)
    setattr(server, field, _coerce_field(proposal.suggested_value, "float"))
    return before, getattr(server, field)


DB_INSTANCE_APPLIERS: dict[str, Any] = {
    "port": _apply_db_instance_port,
    "instance_name": _apply_db_instance_str_field,
    "service_name": _apply_db_instance_str_field,
    "node_role": _apply_db_instance_node_role,
    "db_size_gb": _apply_db_instance_float_field,
    "db_version": _apply_db_instance_version,
}

SERVER_APPLIERS: dict[str, Any] = {
    "hostname": _apply_server_str_field,
    "cpu_cores": _apply_server_int_field,
    "memory_gb": _apply_server_float_field,
    "disk_gb": _apply_server_float_field,
}


class AssetProposalService:
    @staticmethod
    def _now() -> datetime:
        # M14 v3: use local time to match PostgreSQL's naive `now()` and
        # the rest of the codebase. Single source of truth: now_local().
        from app.utils.datetime import now_local
        return now_local()

    @staticmethod
    def _to_dict(row: AssetChangeProposal) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "target_type": row.entity_type,
            "target_id": int(row.entity_id),
            "proposal_type": row.proposal_type or row.change_type,
            "field_path": row.field_path,
            "current_value": row.current_value if row.current_value is not None else row.old_value,
            "suggested_value": row.suggested_value if row.suggested_value is not None else row.new_value,
            "confidence": row.confidence,
            "evidence": row.evidence or {},
            "source_run_id": row.source_run_id or row.evidence_run_id,
            "source_item_key": row.source_item_key,
            "status": row.status,
            "requested_by": row.requested_by,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at,
            "applied_at": row.applied_at,
            "rejected_by": row.rejected_by,
            "rejected_reason": row.rejected_reason,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def create_proposal(
        db: Session,
        *,
        target_type: str,
        target_id: int,
        proposal_type: str,
        field_path: str,
        current_value: Any,
        suggested_value: Any,
        confidence: str,
        evidence: dict[str, Any],
        source_run_id: str | None,
        source_item_key: str | None,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        proposal = AssetChangeProposal(
            entity_type=target_type,
            entity_id=target_id,
            change_type=proposal_type,
            proposal_type=proposal_type,
            field_path=field_path,
            old_value=current_value if isinstance(current_value, dict) else {"value": current_value},
            new_value=suggested_value if isinstance(suggested_value, dict) else {"value": suggested_value},
            current_value=current_value,
            suggested_value=suggested_value,
            confidence=confidence,
            evidence_run_id=source_run_id,
            source_run_id=source_run_id,
            source_item_key=source_item_key,
            evidence=evidence or {},
            status="pending",
            requested_by=requested_by,
        )
        db.add(proposal)
        db.flush()
        return AssetProposalService._to_dict(proposal)

    @staticmethod
    def list_proposals(
        db: Session,
        *,
        target_type: str | None = None,
        target_id: int | None = None,
        proposal_type: str | None = None,
        status: str | None = None,
        source_run_id: str | int | None = None,
        batch_run_id: int | None = None,
    ) -> list[dict[str, Any]]:
        query = db.query(AssetChangeProposal)
        if target_type:
            query = query.filter(AssetChangeProposal.entity_type == target_type)
        if target_id is not None:
            query = query.filter(AssetChangeProposal.entity_id == target_id)
        if status:
            query = query.filter(AssetChangeProposal.status == status)
        if batch_run_id is not None:
            # Resolve batch → collector_run.run_id values → filter by source_run_id
            from app.models.dbops_assets import CollectorRun as _CR
            run_id_rows = (
                db.query(_CR.run_id)
                .filter(_CR.batch_run_id == batch_run_id)
                .distinct()
                .all()
            )
            source_run_ids = [row[0] for row in run_id_rows if row[0]]
            if source_run_ids:
                query = query.filter(AssetChangeProposal.source_run_id.in_(source_run_ids))
            else:
                return []
        elif source_run_id is not None:
            # I4 (PR review 2026-06-18): 按 batch 隔离 proposals，避免跨批 apply。
            query = query.filter(AssetChangeProposal.source_run_id == source_run_id)
        rows = query.order_by(AssetChangeProposal.created_at.desc()).all()
        if proposal_type:
            rows = [row for row in rows if (row.proposal_type or row.change_type) == proposal_type]
        return [AssetProposalService._to_dict(row) for row in rows]

    @staticmethod
    def approve_proposal(db: Session, *, proposal_id: int, operator: str) -> dict[str, Any]:
        proposal = db.query(AssetChangeProposal).filter(AssetChangeProposal.id == proposal_id).with_for_update().first()
        if proposal is None:
            raise LookupError("proposal 不存在")
        if proposal.status != "pending":
            raise ValueError("仅 pending 状态可 approve")

        proposal.status = "approved"
        proposal.approved_by = operator
        proposal.approved_at = AssetProposalService._now()
        return AssetProposalService._to_dict(proposal)

    @staticmethod
    def reject_proposal(db: Session, *, proposal_id: int, operator: str, reason: str | None = None) -> dict[str, Any]:
        proposal = db.query(AssetChangeProposal).filter(AssetChangeProposal.id == proposal_id).with_for_update().first()
        if proposal is None:
            raise LookupError("proposal 不存在")
        if proposal.status not in {"pending", "approved"}:
            raise ValueError("仅 pending/approved 状态可 reject")

        proposal.status = "rejected"
        proposal.rejected_by = operator
        proposal.rejected_reason = reason
        proposal.updated_at = AssetProposalService._now()
        return AssetProposalService._to_dict(proposal)

    @staticmethod
    def apply_proposal(
        db: Session,
        *,
        proposal_id: int,
        operator: str,
        selected_value: int | None = None,
    ) -> dict[str, Any]:
        """Apply an approved proposal to the target asset.

        I10 (PR review 2026-06-20): dispatch through DB_INSTANCE_APPLIERS /
        SERVER_APPLIERS registry instead of 200‑line if/elif ladder.
        New fields only need a registry entry + (if needed) an applier function.
        """
        proposal = db.query(AssetChangeProposal).filter(AssetChangeProposal.id == proposal_id).with_for_update().first()
        if proposal is None:
            raise LookupError("proposal 不存在")
        if proposal.status != "approved":
            raise ValueError("apply 仅允许 approved 状态")

        field_path = (proposal.field_path or "").strip()
        entity_type = (proposal.entity_type or "").strip()

        # 字段更新白名单校验
        allowed = APPLYABLE_FIELDS.get(entity_type, set())
        if field_path not in allowed:
            raise ValueError(
                f"字段 {entity_type}.{field_path} 不在更新白名单内，不允许 apply"
            )

        proposal_type = proposal.proposal_type or proposal.change_type

        # C4 (PR review 2026-06-18): selected_value 仅对 PORT_CANDIDATE_CONFLICT 有意义
        if selected_value is not None and proposal_type != "PORT_CANDIDATE_CONFLICT":
            raise ValueError(
                f"selected_value 仅允许用于 PORT_CANDIDATE_CONFLICT；"
                f"当前 proposal_type={proposal_type}"
            )

        if proposal_type == "PORT_CANDIDATE_CONFLICT":
            if selected_value is None or not isinstance(selected_value, int):
                raise ValueError(
                    "PORT_CANDIDATE_CONFLICT 必须传入 selected_value（单个整数端口）"
                )
            if selected_value < 1 or selected_value > 65535:
                raise ValueError("selected_value 必须是 1-65535 的整数端口")
            candidates = (proposal.suggested_value or {}).get("candidates", [])
            if selected_value not in candidates:
                raise ValueError(
                    f"selected_value={selected_value} 不在候选端口列表 {candidates} 内"
                )

        # db_instance 系列字段 — dispatch through registry
        if entity_type == "db_instance":
            instance = db.query(DbInstance).filter(DbInstance.id == proposal.entity_id).with_for_update().first()
            if instance is None:
                raise LookupError("proposal 目标实例不存在")

            # I5 (PR review 2026-06-20): 写前快照 trust_status
            before_trust_status = getattr(instance, "trust_status", None)

            applier = DB_INSTANCE_APPLIERS.get(field_path)
            if applier is None:
                raise ValueError(f"db_instance.{field_path} 未实现 apply 逻辑")
            before_value, after_value = applier(
                db, instance, proposal, proposal_type, selected_value,
            )

            proposal.status = "applied"
            proposal.applied_at = AssetProposalService._now()

            after_trust_status = getattr(instance, "trust_status", None)
            record_event(
                db,
                asset_type="db_instance",
                asset_id=int(instance.id),
                event_type="ASSET_PROPOSAL_APPLIED",
                before_status=before_trust_status,
                after_status=after_trust_status,
                changed_fields={
                    "field_path": field_path,
                    "before": before_value,
                    "after": after_value,
                    "proposal_id": int(proposal.id),
                    "proposal_type": proposal_type,
                },
                reason="apply proposal",
                operator=operator,
            )
            return AssetProposalService._to_dict(proposal)

        # server 系列字段 — dispatch through registry
        if entity_type == "server":
            server = db.query(Server).filter(Server.id == proposal.entity_id).with_for_update().first()
            if server is None:
                raise LookupError("proposal 目标服务器不存在")

            applier = SERVER_APPLIERS.get(field_path)
            if applier is None:
                raise ValueError(f"server.{field_path} 未实现 apply 逻辑")
            before_value, after_value = applier(
                db, server, proposal, proposal_type, selected_value,
            )

            proposal.status = "applied"
            proposal.applied_at = AssetProposalService._now()

            record_event(
                db,
                asset_type="server",
                asset_id=int(server.id),
                event_type="ASSET_PROPOSAL_APPLIED",
                before_status=None,
                after_status=None,
                changed_fields={
                    "field_path": field_path,
                    "before": before_value,
                    "after": after_value,
                    "proposal_id": int(proposal.id),
                    "proposal_type": proposal_type,
                },
                reason="apply proposal",
                operator=operator,
            )
            return AssetProposalService._to_dict(proposal)

        raise ValueError(f"暂不支持对 {entity_type}.{field_path} 执行 apply")

    @staticmethod
    def batch_action(
        db: Session,
        *,
        proposal_ids: list[int],
        action: str,
        operator: str,
        comment: str | None = None,
        override_values: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """批量 approve / reject / apply 多条 proposal。

        override_values 用于 PORT_CANDIDATE_CONFLICT 场景：键为 proposal_id（字符串），
        值为用户选定的单个整数端口。

        C2 (PR review 2026-06-18): 每条 proposal 用 SAVEPOINT（db.begin_nested）隔离，
        单条失败时只回滚自己的 savepoint，前序成功的 proposal 保留；最后一次性 db.commit
        原子化所有成功的 savepoint。这避免旧实现 db.rollback() 把前序 in-memory 成功状态
        一起抹掉、谎报 success_count 的问题。

        返回：{action, results: [{id, success, error?}], success_count, fail_count}
        """
        override_values = override_values or {}
        results: list[dict[str, Any]] = []
        success_count = 0
        fail_count = 0

        for pid in proposal_ids:
            entry: dict[str, Any] = {"id": int(pid), "success": False}
            savepoint = db.begin_nested()
            try:
                if action == "approve":
                    AssetProposalService.approve_proposal(
                        db, proposal_id=int(pid), operator=operator
                    )
                elif action == "reject":
                    AssetProposalService.reject_proposal(
                        db,
                        proposal_id=int(pid),
                        operator=operator,
                        reason=comment,
                    )
                elif action == "apply":
                    selected = override_values.get(str(int(pid)))
                    if selected is not None and not isinstance(selected, int):
                        # 强类型校验：str 端口号不接受（必须 int）
                        raise ValueError(
                            f"override_values[{pid}] 必须是整数端口"
                        )
                    AssetProposalService.apply_proposal(
                        db,
                        proposal_id=int(pid),
                        operator=operator,
                        selected_value=int(selected) if selected is not None else None,
                    )
                else:
                    raise ValueError(f"未知 action: {action}")

                savepoint.commit()  # release this savepoint
                entry["success"] = True
                success_count += 1
            except Exception as exc:  # 单条失败不影响其他条目
                savepoint.rollback()  # unwind only this iteration
                entry["error"] = str(exc)
                logger.warning(
                    "batch_action failed: action=%s proposal_id=%s error=%s",
                    action, pid, exc, exc_info=True,
                )
                fail_count += 1
            finally:
                results.append(entry)

        db.commit()  # commit all successful savepoints atomically
        return {
            "action": action,
            "results": results,
            "success_count": success_count,
            "fail_count": fail_count,
        }
