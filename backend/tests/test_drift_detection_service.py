"""Tests for DriftDetectionService.

C6 (PR review 2026-06-20): 文件整体不存在（grep 只找到陈旧 .pyc），新建。
覆盖：
- 5 个 detect_for_snapshot 行为 case
- 2 个 _create_change_proposal 异常分流 case (C5)
- 1 个 I11 (current_value None → info-only drift) case
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.dbops_assets import (
    AssetChangeProposal,
    AssetDriftRecord,
    AssetFactSnapshot,
    AssetFactValue,
    DbInstance,
    DbVersion,
    Server,
)
from app.services.drift_detection_service import DriftDetectionService


# ----------------------------------------------------------------------------
# Lightweight in-memory session
# ----------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        rows = self.session.store.get(self.model, [])
        for row in rows:
            if True:
                return row
        return None

    def all(self):
        return list(self.session.store.get(self.model, []))


class _FakeSession:
    def __init__(self):
        self.store: dict = {}
        self._next_ids: dict = {}

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            model = type(obj)
            obj.id = self._next_ids.get(model, 1)
            self._next_ids[model] = obj.id + 1
        self.store.setdefault(type(obj), []).append(obj)

    def seed(self, *objects):
        for obj in objects:
            self.add(obj)

    def query(self, model):
        return _FakeQuery(self, model)

    def flush(self):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


def _make_server(id: int = 60, **kwargs) -> Server:
    defaults = dict(
        id=id,
        server_code=f"SRV-{id}",
        ip_address=f"10.0.0.{id}",
        hostname="db01",
        business_group="DBA",
    )
    defaults.update(kwargs)
    return Server(**defaults)


def _make_db_instance(id: int = 80, **kwargs) -> DbInstance:
    defaults = dict(
        id=id,
        instance_code=f"INS-{id}",
        instance_name="ORCL1",
        port=1521,
        node_role="primary",
    )
    defaults.update(kwargs)
    return DbInstance(**defaults)


def _make_db_version(id: int = 31, **kwargs) -> DbVersion:
    defaults = dict(
        id=id,
        db_type_id=30,
        version_code="19c",
        version_name="19c",
    )
    defaults.update(kwargs)
    return DbVersion(**defaults)


def _make_snapshot(
    snapshot_id: str = "SNAP-1",
    target_type: str = "db_instance",
    target_id: int = 80,
) -> AssetFactSnapshot:
    return AssetFactSnapshot(
        id=1,
        snapshot_id=snapshot_id,
        target_type=target_type,
        target_id=target_id,
        collected_at=datetime(2026, 6, 20, 10, 0, 0),
    )


def _add_fact(snapshot, key: str, value):
    return AssetFactValue(
        snapshot_id=snapshot.id,
        fact_key=key,
        fact_value=value,
        fact_type="string",
    )


# ----------------------------------------------------------------------------
# C6: detect_for_snapshot 行为
# ----------------------------------------------------------------------------


def test_detect_for_snapshot_database_role_single_is_not_drift():
    """node_role=single + fact=PRIMARY → 不是 actionable drift（standalone 不报 role drift）。"""
    db = _FakeSession()
    instance = _make_db_instance(id=80, node_role="single")
    db.seed(instance)
    snapshot = _make_snapshot(target_id=80)
    db.seed(snapshot, _add_fact(snapshot, "database_role", "PRIMARY"))

    drifts = DriftDetectionService.detect_for_snapshot(db, snapshot=snapshot)

    role_drifts = [d for d in drifts if d.fact_key == "database_role"]
    # standalone single 模式不下发 actionable drift
    assert all(d.drift_type != "mismatch" for d in role_drifts)


def test_detect_for_snapshot_database_role_primary_when_standby_is_drift():
    """node_role=standby + fact=PRIMARY → 是 drift。"""
    db = _FakeSession()
    instance = _make_db_instance(id=80, node_role="standby")
    db.seed(instance)
    snapshot = _make_snapshot(target_id=80)
    db.seed(snapshot, _add_fact(snapshot, "database_role", "PRIMARY"))

    drifts = DriftDetectionService.detect_for_snapshot(db, snapshot=snapshot)

    role_drifts = [d for d in drifts if d.fact_key == "database_role"]
    # 应至少有一条 mismatch drift
    assert any(d.drift_type == "mismatch" for d in role_drifts)


def test_detect_for_snapshot_null_formal_value_no_actionable_drift():
    """I11: 正式字段 None → 视为信息缺失，标记为 extra / info，不下发 actionable drift。"""
    db = _FakeSession()
    server = _make_server(id=60)
    server.memory_gb = None
    db.seed(server)
    snapshot = _make_snapshot(
        target_type="server", target_id=60, snapshot_id="SNAP-MEM",
    )
    db.seed(snapshot, _add_fact(snapshot, "memory_mb", 65536))  # 64 GB

    drifts = DriftDetectionService.detect_for_snapshot(db, snapshot=snapshot)

    mem_drifts = [d for d in drifts if d.fact_key == "memory_mb"]
    # I11: 至少没有 mismatch
    mismatch = [d for d in mem_drifts if d.drift_type == "mismatch"]
    assert mismatch == [], "I11: None formal value 不应触发 actionable drift"


def test_detect_for_snapshot_version_label_match_no_drift():
    """version_label 与 db_version.version_name 完全一致 → 没有 actionable drift。"""
    db = _FakeSession()
    version = _make_db_version(id=31, version_name="19c")
    instance = _make_db_instance(id=80, db_version_id=31, db_version=version)
    db.seed(version, instance)
    snapshot = _make_snapshot(target_id=80)
    db.seed(snapshot, _add_fact(snapshot, "version_label", "19c"))

    drifts = DriftDetectionService.detect_for_snapshot(db, snapshot=snapshot)

    version_drifts = [d for d in drifts if d.fact_key == "version_label"]
    actionable = [d for d in version_drifts if d.drift_type == "mismatch"]
    assert actionable == []


def test_detect_for_snapshot_extra_field_marked_info_only():
    """version_full / version_major 没在 asset_field 映射里 → 标记为 extra/info，不下发 proposal。"""
    db = _FakeSession()
    instance = _make_db_instance(id=80)
    db.seed(instance)
    snapshot = _make_snapshot(target_id=80)
    db.seed(snapshot, _add_fact(snapshot, "version_full", "19.0.0.0.0 Patch 360"))
    db.seed(_add_fact(snapshot, "version_major", 19))

    drifts = DriftDetectionService.detect_for_snapshot(db, snapshot=snapshot)

    info_drifts = [d for d in drifts if d.severity == "info"]
    info_keys = {d.fact_key for d in info_drifts}
    assert "version_full" in info_keys
    assert "version_major" in info_keys


# ----------------------------------------------------------------------------
# C5: _create_change_proposal 异常分流
# ----------------------------------------------------------------------------


def test_create_change_proposal_returns_none_on_integrity_error_duplicate(monkeypatch):
    """C5: duplicate → 返回 None，不阻断 callback 事务。"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=99)

    def _raise_integrity(*args, **kwargs):
        raise IntegrityError("INSERT", "params", Exception("dup key"))

    monkeypatch.setattr(
        "app.services.asset_proposal_service.AssetProposalService.create_proposal",
        staticmethod(_raise_integrity),
    )

    snapshot = SimpleNamespace(
        snapshot_id="SNAP-DUP", source_run_id="run-1", source_item_key="item-1",
        collected_at=None, target_id=80,
    )

    result = DriftDetectionService._create_change_proposal(
        db,
        snapshot=snapshot,
        fact_key="version_label",
        current_value="old",
        suggested_value="new",
        target_type="db_instance",
        target_id=80,
    )

    assert result is None


def test_create_change_proposal_reraises_on_operational_error(monkeypatch):
    """C5: OperationalError（瞬时 DB 错误）→ 抛出，让 callback 事务回滚。"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=99)

    def _raise_operational(*args, **kwargs):
        raise OperationalError("SELECT", "params", Exception("connection lost"))

    monkeypatch.setattr(
        "app.services.asset_proposal_service.AssetProposalService.create_proposal",
        staticmethod(_raise_operational),
    )

    snapshot = SimpleNamespace(
        snapshot_id="SNAP-OP", source_run_id="run-1", source_item_key="item-1",
        collected_at=None, target_id=80,
    )

    with pytest.raises(OperationalError):
        DriftDetectionService._create_change_proposal(
            db,
            snapshot=snapshot,
            fact_key="version_label",
            current_value="old",
            suggested_value="new",
            target_type="db_instance",
            target_id=80,
        )
