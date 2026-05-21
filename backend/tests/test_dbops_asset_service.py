from datetime import datetime

from app.models.dbops_assets import (
    AssetEventHistory,
    BusinessSystem,
    BusinessSystemContact,
    Cluster,
    ClusterVip,
    Contact,
    DbInstance,
    DbType,
    DbVersion,
    OsVersion,
    Server,
    Site,
    SystemGroup,
)
from app.services.asset_event_history_service import list_events, record_event
from app.services.dbops_asset_service import DbopsAssetService
from app.services.dbops_stats_service import DbopsStatsService


def test_dbops_asset_models_expose_phase1_keys():
    assert Cluster.__tablename__ == "cluster"
    assert "cluster_code" in Cluster.__table__.columns
    assert "extra_attrs" in Cluster.__table__.columns
    assert DbInstance.__tablename__ == "db_instance"
    assert "node_role" in DbInstance.__table__.columns
    assert "extra_attrs" in DbInstance.__table__.columns
    assert Server.__tablename__ == "server"
    assert Site.__tablename__ == "site"


def test_db_type_model_exposes_dictionary_fields():
    assert DbType.__tablename__ == "db_type"
    assert "type_code" in DbType.__table__.columns
    assert "name" in DbType.__table__.columns
    assert "category" in DbType.__table__.columns
    assert "license_type" in DbType.__table__.columns
    assert "vendor" in DbType.__table__.columns
    assert "is_active" in DbType.__table__.columns
    constraint_names = {constraint.name for constraint in DbType.__table__.constraints if constraint.name}
    assert "ck_db_type_category" in constraint_names
    assert "ck_db_type_license" in constraint_names


def test_asset_event_history_model_exposes_append_only_columns():
    assert AssetEventHistory.__tablename__ == "asset_event_history"
    assert "asset_type" in AssetEventHistory.__table__.columns
    assert "asset_id" in AssetEventHistory.__table__.columns
    assert "event_type" in AssetEventHistory.__table__.columns
    assert "changed_fields" in AssetEventHistory.__table__.columns
    assert "operated_at" in AssetEventHistory.__table__.columns


class _FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def filter(self, *conditions):
        for condition in conditions:
            if hasattr(condition, "left") and hasattr(condition, "right") and getattr(condition.operator, "__name__", "") == "eq":
                key = getattr(condition.left, "key", None)
                value = getattr(condition.right, "value", None)
                if key is not None:
                    self.filters[key] = value
        return self

    def _rows(self):
        rows = self.session.store.get(self.model, [])
        for key, value in self.filters.items():
            rows = [row for row in rows if getattr(row, key) == value]
        return rows

    def first(self):
        rows = self._rows()
        return rows[0] if rows else None

    def all(self):
        return list(self._rows())

    def count(self):
        return len(self._rows())


class _FakeSession:
    def __init__(self):
        self.store = {}
        self._next_ids = {}

    def seed(self, *objects):
        for obj in objects:
            self._ensure_identity(obj)
            self.store.setdefault(type(obj), []).append(obj)

    def query(self, model):
        return _FakeQuery(self, model)

    def add(self, obj):
        self._ensure_identity(obj)
        self.store.setdefault(type(obj), []).append(obj)

    def flush(self):
        return None

    def commit(self):
        return None

    def delete(self, obj):
        rows = self.store.get(type(obj), [])
        if obj in rows:
            rows.remove(obj)

    def _ensure_identity(self, obj):
        if getattr(obj, "id", None) is None:
            model = type(obj)
            next_id = self._next_ids.get(model, 1)
            obj.id = next_id
            self._next_ids[model] = next_id + 1


def _seed_asset_graph():
    group = SystemGroup(id=1, group_code="ERP", name="ERP")
    system = BusinessSystem(id=10, system_code="SYS-1", system_name="ERP 系统", system_group_id=1)
    contact = Contact(id=20, contact_code="CT-1", contact_name="张三", phone="10086")
    link = BusinessSystemContact(id=21, business_system_id=10, contact_id=20, role_code="DBA_OWNER")
    db_type = DbType(
        id=30,
        type_code="ORACLE",
        name="Oracle",
        category="relational",
        license_type="commercial",
        vendor="Oracle",
        is_active=True,
    )
    db_version = DbVersion(id=31, db_type_id=30, version_code="19c", version_name="19c", patch_version=None)
    site = Site(id=40, site_code="SITE-1", country="中國", deploy_type="地端", provider="地端", factory_area="深圳", room_location="A1")
    os_version = OsVersion(id=50, os_code="OS-1", os_name="Linux", version_name="RHEL 8")
    server = Server(id=60, server_code="SRV-1", ip_address="10.0.0.10", site_id=40, os_version_id=50, hostname="db01", business_group="DBA")
    cluster = Cluster(
        id=70,
        cluster_code="CLU-ORACLE-DATAGUARD-AAAA",
        cluster_name="ERP 系统",
        business_system_id=10,
        db_type_id=30,
        cluster_type="DATAGUARD",
        extra_attrs={"source_cluster_no": "1"},
    )
    vip = ClusterVip(id=71, cluster_id=70, vip_address="10.0.0.100")
    instance = DbInstance(
        id=80,
        instance_code="INS-1",
        instance_name="ORCL1",
        db_type_id=30,
        db_version_id=31,
        server_id=60,
        cluster_id=70,
        port=1521,
        node_role="primary",
        extra_attrs={"engine_role": "primary", "source_node_role": "Master"},
    )
    instance.db_type = db_type
    return [group, system, contact, link, db_type, db_version, site, os_version, server, cluster, vip, instance]


def test_list_servers_returns_business_group_and_room_location():
    db = _FakeSession()
    db.seed(*_seed_asset_graph())

    rows = DbopsAssetService.list_servers(db)

    assert len(rows) == 1
    assert rows[0]["business_group"] == "DBA"
    assert rows[0]["room_location"] == "A1"


def test_create_and_update_server_keep_business_group_and_room_location():
    db = _FakeSession()

    server_id = DbopsAssetService.create_server(
        db,
        {
            "ip": "10.0.0.20",
            "hostname": "db02",
            "business_group": "Finance",
            "factory": "深圳",
            "room_location": "B12",
            "provider": "地端",
            "deploy_type": "地端",
        },
    )

    assert server_id == 1
    created_server = db.store[Server][0]
    created_site = db.store[Site][0]
    assert created_server.business_group == "Finance"
    assert created_site.room_location == "B12"

    updated = DbopsAssetService.update_server(
        db,
        server_id,
        {
            "business_group": "IT",
            "room_location": "C08",
        },
    )

    assert updated is True
    assert created_server.business_group == "IT"
    assert created_site.room_location == "C08"


def test_record_event_appends_history_row_with_expected_fields():
    db = _FakeSession()

    operated_at = datetime(2026, 5, 18, 10, 30, 0)
    event = record_event(
        db,
        asset_type="business_system",
        asset_id=10,
        event_type="business.up",
        before_status="inactive",
        after_status="active",
        changed_fields={
            "action": "up",
            "context": {"ticket": "INC-1"},
        },
        reason="上线",
        operator="admin",
        remark="手工上线",
        operated_at=operated_at,
    )

    assert event.asset_type == "business_system"
    assert event.asset_id == 10
    assert event.event_type == "business.up"
    assert event.before_status == "inactive"
    assert event.after_status == "active"
    assert event.changed_fields["context"]["ticket"] == "INC-1"
    assert event.reason == "上线"
    assert event.operator == "admin"
    assert event.remark == "手工上线"
    assert event.operated_at == operated_at
    assert db.store[AssetEventHistory][0] is event


def test_list_events_returns_newest_first():
    db = _FakeSession()

    record_event(
        db,
        asset_type="business_system",
        asset_id=10,
        event_type="business.down",
        before_status="active",
        after_status="inactive",
        changed_fields={"action": "down"},
        operated_at=datetime(2026, 5, 18, 9, 0, 0),
    )
    record_event(
        db,
        asset_type="business_system",
        asset_id=10,
        event_type="business.up",
        before_status="inactive",
        after_status="active",
        changed_fields={"action": "up"},
        operated_at=datetime(2026, 5, 18, 11, 0, 0),
    )

    rows = list_events(db, asset_type="business_system", asset_id=10)

    assert [row.event_type for row in rows] == ["business.up", "business.down"]


def test_change_business_status_updates_status_and_writes_history():
    db = _FakeSession()
    system = BusinessSystem(
        id=10,
        system_code="SYS-1",
        system_name="ERP 系统",
        status="building",
        extra_attrs={"existing": "value"},
    )
    db.seed(system)

    result = DbopsAssetService.change_business_status(
        db,
        system_id=10,
        action="retired",
        reason="业务下线",
        remark="计划停用",
        operator="admin",
        lifecycle_context={"ticket": "INC-2"},
    )

    assert result is not None
    assert system.status == "retired"
    assert system.extra_attrs["existing"] == "value"
    assert system.extra_attrs["lifecycle_context"]["action"] == "retired"
    assert system.extra_attrs["lifecycle_context"]["before_status"] == "building"
    assert system.extra_attrs["lifecycle_context"]["after_status"] == "retired"
    assert system.extra_attrs["lifecycle_context"]["context"]["ticket"] == "INC-2"

    history = db.store[AssetEventHistory][0]
    assert history.event_type == "business.retired"
    assert history.before_status == "building"
    assert history.after_status == "retired"
    assert history.reason == "业务下线"
    assert history.operator == "admin"
    assert history.remark == "计划停用"


def test_change_business_status_history_list_uses_newest_first():
    db = _FakeSession()
    system = BusinessSystem(
        id=10,
        system_code="SYS-1",
        system_name="ERP 系统",
        status="building",
        extra_attrs={},
    )
    db.seed(system)

    DbopsAssetService.change_business_status(
        db,
        system_id=10,
        action="retired",
        operator="admin",
        lifecycle_context={"ticket": "INC-3"},
    )
    DbopsAssetService.change_business_status(
        db,
        system_id=10,
        action="active",
        operator="admin",
        lifecycle_context={"ticket": "INC-4"},
    )

    rows = DbopsAssetService.list_business_lifecycle_history(db, 10)

    assert [row.event_type for row in rows] == ["business.active", "business.retired"]


def test_list_clusters_returns_cluster_code_and_source_cluster_no():
    db = _FakeSession()
    db.seed(*_seed_asset_graph())

    rows = DbopsAssetService.list_clusters(db)

    assert len(rows) == 1
    assert rows[0]["cluster_code"] == "CLU-ORACLE-DATAGUARD-AAAA"
    assert rows[0]["source_cluster_no"] == "1"
    assert rows[0]["vip_addresses"] == ["10.0.0.100"]


def test_list_business_systems_returns_contacts_and_clusters():
    db = _FakeSession()
    db.seed(*_seed_asset_graph())

    rows = DbopsAssetService.list_business_systems(db)

    assert len(rows) == 1
    assert rows[0]["system_name"] == "ERP 系统"
    assert rows[0]["contacts"][0]["contact_type"] == "DBA_OWNER"
    assert rows[0]["clusters"][0]["cluster_code"] == "CLU-ORACLE-DATAGUARD-AAAA"


def test_business_system_upsert_and_contact_binding_work():
    db = _FakeSession()
    db.seed(
        Contact(
            id=20,
            contact_code="CT-1",
            contact_name="张三",
            phone="13800000000",
            email="zhangsan@example.com",
            dept="DBA",
        )
    )

    system = DbopsAssetService.upsert_business_system(
        db,
        {
            "system_name": "ERP 系统",
            "business_unit": "应用一处",
            "department": "平台部",
            "biz_level": "重要",
            "remark": "初始创建",
        },
    )

    assert system.system_code.startswith("SYS-")
    assert system.status == "building"
    assert system.business_unit == "应用一处"

    updated = DbopsAssetService.upsert_business_system(
        db,
        {
            "system_name": "ERP 系统",
            "business_unit": "应用二处",
            "department": "平台部",
            "biz_level": "关键",
            "remark": "更新",
        },
        system_id=system.id,
    )

    assert updated.id == system.id
    assert updated.business_unit == "应用二处"
    assert updated.remark == "更新"

    link = DbopsAssetService.upsert_business_contact_link(
        db,
        business_system_id=system.id,
        contact_id=20,
        role_code="DBA_OWNER",
        remark="核心负责人",
    )

    assert link.business_system_id == system.id
    assert link.contact_id == 20
    assert link.role_code == "DBA_OWNER"
    assert link.remark == "核心负责人"

    deleted = DbopsAssetService.delete_business_contact_link(
        db,
        business_system_id=system.id,
        contact_id=20,
        role_code="DBA_OWNER",
    )

    assert deleted is True
    assert db.store.get(BusinessSystemContact, []) == []


def test_stats_group_by_provider_returns_counts():
    db = _FakeSession()
    db.seed(*_seed_asset_graph())

    result = DbopsStatsService.by_provider(db)

    assert result["groups"][0]["provider"] == "地端"
    assert result["groups"][0]["count"] == 1
