"""DriftDetectionService — compare collected facts against formal asset fields.

Generates asset_drift_record rows for mismatches.
Optionally creates asset_change_proposal (never auto-applies).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any, Callable, Optional

from app.utils.datetime import now_local

from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    AssetChangeProposal,
    AssetDriftRecord,
    AssetFactSnapshot,
    AssetFactValue,
    DbInstance,
    Server,
)


# A3 (PR review 2026-06-20): logger 移到 import 块外，遵守 PEP 8 import 顺序。
logger = logging.getLogger(__name__)


class DriftDetectionService:
    """Compare snapshot facts against formal asset fields and generate drifts."""

    # ------------------------------------------------------------------
    # Field mapping: fact_key → (asset_field, target_type, converter)
    # ------------------------------------------------------------------

    @staticmethod
    def _field_mappings() -> dict[str, dict[str, Any]]:
        """Return the drift detection field mapping.

        Each entry maps a fact_key to:
          asset_field: the formal asset column name
          target_type: 'server' or 'db_instance'
          converter: optional callable to normalize the fact value before comparison
          compare_key: optional alternative fact_key to look up
        """
        return {
            # Server facts → server fields
            "hostname": {
                "asset_field": "hostname",
                "target_type": "server",
            },
            "primary_ip": {
                "asset_field": "ip_address",
                "target_type": "server",
            },
            "cpu_cores": {
                "asset_field": "cpu_cores",
                "target_type": "server",
                "converter": int,
            },
            "memory_mb": {
                "asset_field": "memory_gb",
                "target_type": "server",
                "converter": lambda v: round(float(v) / 1024, 2),  # MB → GB
            },
            # DB instance facts → instance fields
            "instance_name": {
                "asset_field": "instance_name",
                "target_type": "db_instance",
            },
            "service_name": {
                "asset_field": "service_name",
                "target_type": "db_instance",
            },
            "server_port": {
                "asset_field": "port",
                "target_type": "db_instance",
                "converter": int,
            },
            "listener_port": {
                "asset_field": "port",
                "target_type": "db_instance",
                "converter": int,
            },
            "database_role": {
                "asset_field": "node_role",
                "target_type": "db_instance",
                "converter": DriftDetectionService._map_role,
            },
            # Version drift — compare short version_label against db_version.version_name.
            # Both are short labels in the actual data:
            #   version_label: "Microsoft SQL Server 2019" (from collector regex)
            #   version_name:   "Microsoft SQL Server 2019" (from DbVersion table)
            # They share the same format, so exact comparison works.
            "version_label": {
                "asset_field": "db_version_name",  # resolved via _get_formal_value
                "target_type": "db_instance",
                "proposal_field": "db_version",
            },
            # Full version string — info only. Too long/variable for reliable
            # comparison (includes build numbers, compiler versions, etc.).
            # Stored as evidence for apply_proposal fallback lookup.
            "version_full": {
                "asset_field": None,
                "target_type": "db_instance",
                "drift_info": True,
            },
            "version_major": {
                "asset_field": None,
                "target_type": "db_instance",
                "drift_info": True,
            },
            # Database size
            "database_size_gb": {
                "asset_field": "db_size_gb",
                "target_type": "db_instance",
                "converter": float,
                "proposal_field": "db_size_gb",
            },
        }

    # ------------------------------------------------------------------
    # Role mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_role(fact_value: Any) -> Optional[str]:
        """Normalize database role values from various DB types."""
        if fact_value is None:
            return None
        raw = str(fact_value).strip().upper()

        role_map: dict[str, str] = {
            # SQL Server
            "PRIMARY": "primary",
            "SECONDARY": "standby",
            "SINGLE": "single",
            # Oracle
            "PHYSICAL STANDBY": "standby",
            "LOGICAL STANDBY": "standby",
            "SNAPSHOT STANDBY": "standby",
            "FAR SYNC": "standby",
            # PostgreSQL
            "TRUE": "standby",   # pg_is_in_recovery=true
            "FALSE": "primary",  # pg_is_in_recovery=false
            # Generic
            "UNKNOWN": "unknown",
        }
        return role_map.get(raw, raw.lower())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def detect_for_snapshot(
        cls,
        db: Session,
        snapshot: AssetFactSnapshot,
    ) -> list[AssetDriftRecord]:
        """Run drift detection for all fact values in a snapshot.

        Args:
            db: Database session.
            snapshot: The AssetFactSnapshot to check.

        Returns:
            List of created AssetDriftRecord rows.
        """
        values = (
            db.query(AssetFactValue)
            .filter(AssetFactValue.snapshot_id == snapshot.id)
            .all()
        )
        if not values:
            return []

        # Build fact lookup
        facts: dict[str, Any] = {}
        for v in values:
            facts[v.fact_key] = v.fact_value

        drifts: list[AssetDriftRecord] = []

        for fact_key, mapping in cls._field_mappings().items():
            fact_value = facts.get(fact_key)
            if fact_value is None:
                continue  # this fact was not collected

            asset_field = mapping.get("asset_field")
            target_type = mapping["target_type"]
            drift_info_only = mapping.get("drift_info", False)

            # Skip if this fact doesn't apply to the snapshot's target type
            if target_type != snapshot.target_type:
                continue

            # Get current formal value
            current_value = cls._get_formal_value(
                db, target_type, snapshot.target_id, asset_field
            )

            # Apply converter
            converter = mapping.get("converter")
            normalized = fact_value
            if converter and callable(converter):
                try:
                    normalized = converter(fact_value)
                except (ValueError, TypeError):
                    continue

            # Determine drift
            is_drift = False
            # I11 (PR review 2026-06-20): 正式字段为 None → 字典未登记，视为信息缺失
            # 不是 actionable drift；仍记 info-only record，但不创建 proposal。
            record_info_only = False
            if asset_field is None:
                # Informational only: always record
                pass
            elif current_value is None:
                # 字典未登记视为信息缺失
                is_drift = False
                record_info_only = True
            else:
                # Compare normalized values
                is_drift = not cls._values_equal(normalized, current_value)

            # database_role on standalone instance (node_role=single) is not a
            # drift.  Oracle v$database.database_role = 'PRIMARY' is normal for
            # any non-standby database, regardless of clustering.
            if is_drift and fact_key == "database_role" and str(current_value).strip().lower() == "single":
                is_drift = False

            if is_drift or asset_field is None or record_info_only:
                drift = cls._create_drift_record(
                    db,
                    snapshot=snapshot,
                    fact_key=fact_key,
                    expected_value=current_value,
                    actual_value=normalized if is_drift else fact_value,
                    drift_type="mismatch" if is_drift else "extra",
                    severity="warning" if is_drift else "info",
                )
                db.add(drift)
                drifts.append(drift)

                # Create change proposal for actionable drifts only
                # I11: None formal value → 不创建 proposal（信息缺失非漂移）
                if is_drift and asset_field is not None:
                    proposal = cls._create_change_proposal(
                        db,
                        snapshot=snapshot,
                        fact_key=fact_key,
                        proposal_field=mapping.get("proposal_field", asset_field),
                        current_value=current_value,
                        suggested_value=normalized,
                        target_type=target_type,
                        target_id=snapshot.target_id,
                    )
                    if proposal:
                        drift.proposal_id = int(proposal.id)

        return drifts

    # ------------------------------------------------------------------
    # Value comparison
    # ------------------------------------------------------------------

    @staticmethod
    def _values_equal(a: Any, b: Any) -> bool:
        """Compare two values for equality, handling type coercion."""
        if a == b:
            return True
        # String comparison
        sa, sb = str(a).strip(), str(b).strip()
        if sa == sb:
            return True
        # Try numeric comparison
        try:
            if float(sa) == float(sb):
                return True
        except (ValueError, TypeError):
            pass
        return False

    # ------------------------------------------------------------------
    # Formal value lookup
    # ------------------------------------------------------------------

    @staticmethod
    def _get_formal_value(
        db: Session,
        target_type: str,
        target_id: int,
        asset_field: Optional[str],
    ) -> Any:
        """Read the current formal asset field value from the database."""
        if asset_field is None:
            return None

        if target_type == "server":
            row = db.query(Server).filter(Server.id == target_id).first()
        elif target_type == "db_instance":
            row = db.query(DbInstance).filter(DbInstance.id == target_id).first()
        else:
            return None

        if row is None:
            return None

        # Special fields resolved via relationships
        if asset_field == "db_version_name":
            db_version = getattr(row, "db_version", None)
            return getattr(db_version, "version_name", None) if db_version else None

        value = getattr(row, asset_field, None)

        # Handle IP address type (INET → string)
        if value is not None and hasattr(value, "__str__"):
            s = str(value)
            if "/" in s:
                s = s.split("/")[0]
            return s

        # Handle Numeric → float
        from decimal import Decimal
        if isinstance(value, Decimal):
            return float(value)

        return value

    # ------------------------------------------------------------------
    # Drift record creation
    # ------------------------------------------------------------------

    @staticmethod
    def _create_drift_record(
        db: Session,
        *,
        snapshot: AssetFactSnapshot,
        fact_key: str,
        expected_value: Any,
        actual_value: Any,
        drift_type: str = "mismatch",
        severity: str = "warning",
    ) -> AssetDriftRecord:
        """Create an AssetDriftRecord row."""
        now = now_local()
        drift_code = DriftDetectionService._generate_drift_code(fact_key)

        return AssetDriftRecord(
            drift_code=drift_code,
            snapshot_id=int(snapshot.id),
            target_type=snapshot.target_type,
            target_id=snapshot.target_id,
            fact_key=fact_key,
            expected_value=expected_value,
            actual_value=actual_value,
            drift_type=drift_type,
            severity=severity,
            is_resolved=False,
            created_at=now,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # Change proposal creation
    # ------------------------------------------------------------------

    @staticmethod
    def _create_change_proposal(
        db: Session,
        *,
        snapshot: AssetFactSnapshot,
        fact_key: str,
        proposal_field: str | None = None,
        current_value: Any,
        suggested_value: Any,
        target_type: str,
        target_id: int,
    ) -> AssetChangeProposal | None:
        """Create an AssetChangeProposal for an actionable drift.

        NEVER auto-applies — requires manual approve+apply.
        """
        from app.services.asset_proposal_service import AssetProposalService

        try:
            proposal_dict = AssetProposalService.create_proposal(
                db,
                target_type=target_type,
                target_id=target_id,
                proposal_type="ASSET_FACT_DRIFT",
                field_path=proposal_field or fact_key,
                current_value=current_value,
                suggested_value=suggested_value,
                confidence="medium",
                evidence={
                    "snapshot_id": snapshot.snapshot_id,
                    "source_run_id": snapshot.source_run_id,
                    "source_item_key": snapshot.source_item_key,
                    "fact_key": fact_key,
                    "collected_at": snapshot.collected_at.isoformat() if snapshot.collected_at else None,
                },
                source_run_id=snapshot.source_run_id,
                source_item_key=snapshot.source_item_key,
                requested_by=None,
            )
            return (
                db.query(AssetChangeProposal)
                .filter(AssetChangeProposal.id == proposal_dict["id"])
                .first()
            )
        except IntegrityError as exc:
            # C5 (PR review 2026-06-20): 重复 (snapshot, fact_key) 视为正常的并发副作用，
            # 不阻断 callback 事务的提交。
            logger.info(
                "Duplicate change proposal for snapshot_id=%s fact_key=%s: %s",
                snapshot.snapshot_id, fact_key, exc.orig,
            )
            return None
        except (OperationalError, DBAPIError):
            # 瞬时 DB 错误（连接断 / 超时）：让 callback 事务感知并回滚，
            # 而不是把半成功的 state 一起 commit。
            logger.exception(
                "DB error creating change proposal for snapshot_id=%s fact_key=%s",
                snapshot.snapshot_id, fact_key,
            )
            raise
        except SQLAlchemyError:
            # schema / 编程错误：日志 + 抛出，让上层决定如何处理。
            logger.exception(
                "ORM error creating change proposal for snapshot_id=%s fact_key=%s",
                snapshot.snapshot_id, fact_key,
            )
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_drift_code(fact_key: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(3).upper()
        safe_key = fact_key.replace(" ", "_").replace("-", "_")[:30]
        return f"DRIFT-{timestamp}-{safe_key}-{suffix}"

    # ------------------------------------------------------------------
    # 资产校验功能优化 v2 / 2026-06-17:
    # build_cluster_type_hint — 单实例 cluster_type 提示
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_cluster_type_from_facts(facts: dict[str, Any]) -> str | None:
        """从单实例采集事实推断集群类型。"""
        role = str(facts.get("database_role") or facts.get("instance_role") or "").upper()
        is_recovery = facts.get("is_in_recovery")
        has_slave = facts.get("has_slave")

        if role in ("PRIMARY",) and has_slave:
            return "master-slave"
        if role in ("PHYSICAL STANDBY", "LOGICAL STANDBY", "SNAPSHOT STANDBY"):
            return "primary-standby"
        if is_recovery is True:
            return "primary-standby"
        # PRIMARY without slave / is_in_recovery=false → ambiguous, don't infer
        return None

    @staticmethod
    def build_cluster_type_hint(
        db: Session,
        instance: Any,
        facts: dict[str, Any],
    ) -> dict[str, Any] | None:
        """从单实例采集事实推断 cluster_type 提示。

        本次仅作为 AssetVerifyReport 的信息提示，不生成 AssetChangeProposal。
        下轮跨实例聚合后再考虑自动 proposal。
        """
        inferred = DriftDetectionService._infer_cluster_type_from_facts(facts)
        if not inferred:
            return None

        cluster = getattr(instance, "cluster", None)
        if not cluster or not getattr(cluster, "cluster_type", None):
            return None

        current = (cluster.cluster_type or "").lower()
        if current == inferred.lower():
            return None  # 一致，无需提示

        return {
            "item_code": "CLUSTER_TYPE_MISMATCH",
            "severity": "warning",
            "target_scope": "db_instance",
            "target_id": int(instance.id),
            "derived_target_type": "cluster",
            "derived_target_id": int(instance.cluster_id) if instance.cluster_id else None,
            "current_cluster_type": cluster.cluster_type,
            "inferred_cluster_type": inferred,
            "auto_proposal": False,
            "message": (
                f"采集事实推断的集群类型({inferred})与CMDB记录({cluster.cluster_type})"
                "不一致，请人工确认。"
            ),
        }
