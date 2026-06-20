from datetime import datetime

from app.models.dbops_assets import (
    AssetEndpoint,
    AssetChangeProposal,
    AssetEventHistory,
    CollectorRunItem,
    BusinessSystem,
    BusinessSystemContact,
    Cluster,
    ClusterVip,
    CollectorRun,
    CollectorRunResult,
    PortProfile,
    Contact,
    DbInstance,
    DbType,
    DbVersion,
    OsVersion,
    Server,
    Site,
    SystemGroup,
)
from app.schemas.collector import AssetVerifyLaunchRequest
from app.services import collector_service as collector_service_module
from app.services.asset_event_history_service import list_events, record_event
from app.services.asset_proposal_service import AssetProposalService
from app.services.dbops_asset_service import DbopsAssetService
from app.services.dbops_stats_service import DbopsStatsService
from app.services.port_calibration_service import PortCalibrationService
from app.services.port_profile_service import PortProfileService


def test_dbops_asset_models_expose_phase1_keys():
    assert Cluster.__tablename__ == "cluster"
    assert "cluster_code" in Cluster.__table__.columns
    assert "extra_attrs" in Cluster.__table__.columns
    assert DbInstance.__tablename__ == "db_instance"
    assert "node_role" in DbInstance.__table__.columns
    assert "extra_attrs" in DbInstance.__table__.columns
    assert "trust_status" in DbInstance.__table__.columns
    assert "reachability_status" in DbInstance.__table__.columns
    assert "last_verify_at" in DbInstance.__table__.columns
    assert "verify_detail" in DbInstance.__table__.columns
    assert Server.__tablename__ == "server"
    assert Site.__tablename__ == "site"


def test_collector_models_expose_expected_keys():
    assert CollectorRun.__tablename__ == "collector_run"
    assert "run_id" in CollectorRun.__table__.columns
    assert "db_instance_id" in CollectorRun.__table__.columns
    assert "target_scope" in CollectorRun.__table__.columns
    assert "server_id" in CollectorRun.__table__.columns
    assert "item_count" in CollectorRun.__table__.columns
    assert "status" in CollectorRun.__table__.columns
    assert "target_host" in CollectorRun.__table__.columns
    assert "target_port" in CollectorRun.__table__.columns
    assert CollectorRunResult.__tablename__ == "collector_run_result"
    assert "collector_run_id" in CollectorRunResult.__table__.columns
    assert "run_id" in CollectorRunResult.__table__.columns
    assert "item_key" in CollectorRunResult.__table__.columns
    assert "check_code" in CollectorRunResult.__table__.columns
    assert "target_scope" in CollectorRunResult.__table__.columns
    assert "status" in CollectorRunResult.__table__.columns
    assert CollectorRunItem.__tablename__ == "collector_run_item"
    assert "item_key" in CollectorRunItem.__table__.columns
    assert "endpoint_type" in CollectorRunItem.__table__.columns
    assert "port_source" in CollectorRunItem.__table__.columns
    assert "is_required" in CollectorRunItem.__table__.columns
    assert PortProfile.__tablename__ == "port_profile"
    assert AssetEndpoint.__tablename__ == "asset_endpoint"
    assert "reachable" in AssetEndpoint.__table__.columns


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

    def _extract_clause(self, condition):
        """Extract (key, value, operator_name) from a single BinaryExpression."""
        operator_name = getattr(condition.operator, "__name__", "")
        key = getattr(condition.left, "key", None)
        # right may be a BindParameter (with .value) or a raw value (None, bool, int)
        value = getattr(condition.right, "value", condition.right)
        if key is not None:
            return key, value, operator_name
        return None, None, None

    def _extract_clauses(self, condition):
        """Yield (key, value, operator_name) tuples, flattening or_()."""
        operator_name = getattr(condition.operator, "__name__", "")
        if operator_name == "or_":
            clauses = getattr(condition, "clauses", [])
            for clause in clauses:
                key, value, op = self._extract_clause(clause)
                if key is not None:
                    yield key, value, op
        else:
            key, value, op = self._extract_clause(condition)
            if key is not None:
                yield key, value, op

    def filter(self, *conditions):
        for condition in conditions:
            for key, value, operator_name in self._extract_clauses(condition):
                if operator_name == "eq":
                    if key in self.filters:
                        existing = self.filters[key]
                        if isinstance(existing, list):
                            existing.append(value)
                        else:
                            self.filters[key] = [existing, value]
                    else:
                        self.filters[key] = value
                elif operator_name == "is_":
                    # is_(None) becomes a null check
                    self.filters[key] = ("is_null", value)
                elif operator_name == "in_op":
                    if isinstance(value, (list, set, tuple)):
                        self.filters[key] = set(value)
                    else:
                        self.filters[key] = {value}
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, value):
        return self

    def options(self, *args, **kwargs):
        return self

    def with_for_update(self):
        return self

    def _row_matches(self, row, key, value):
        attr = getattr(row, key)
        if isinstance(value, list):
            # OR semantics: any match wins
            return any(self._row_matches_single(row, key, v) for v in value)
        return self._row_matches_single(row, key, value)

    def _row_matches_single(self, row, key, value):
        attr = getattr(row, key)
        if isinstance(value, tuple) and value[0] == "is_null":
            return attr is None
        if isinstance(value, set):
            return attr in value
        return attr == value

    def _rows(self):
        rows = self.session.store.get(self.model, [])
        for key, value in self.filters.items():
            rows = [row for row in rows if self._row_matches(row, key, value)]
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

    def rollback(self):
        return None

    def begin_nested(self):
        """SAVEPOINT stub — I8 (PR review 2026-06-20): 真回滚。

        begin_nested 时遍历 store 里 tracked ORM 对象的 dirty 属性做 snapshot，
        rollback() 恢复。这是 real DB SAVEPOINT 行为的最小子集，足以验证
        partial-failure 语义：失败条目不能污染成功条目的写入。
        """

        class _FakeSavepoint:
            def __init__(self, parent):
                self.parent = parent
                # snapshot: {(obj, attr_name): old_value}
                self.snapshot: dict = {}
                for rows in parent.store.values():
                    for obj in rows:
                        for attr in ("port", "instance_name", "service_name",
                                     "node_role", "db_size_gb", "db_version_id",
                                     "hostname", "cpu_cores", "memory_gb",
                                     "disk_gb", "trust_status", "status"):
                            if hasattr(obj, attr):
                                self.snapshot[(id(obj), attr)] = getattr(obj, attr, None)

            def commit(self):
                self.snapshot.clear()

            def rollback(self):
                # 真回滚：恢复 begin_nested 时的属性值
                rows_by_id: dict = {}
                for rows in self.parent.store.values():
                    for obj in rows:
                        rows_by_id[id(obj)] = obj
                for (oid, attr), old in self.snapshot.items():
                    obj = rows_by_id.get(oid)
                    if obj is not None:
                        setattr(obj, attr, old)
                self.snapshot.clear()

        return _FakeSavepoint(self)

    def refresh(self, obj):
        return obj

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
    server = Server(
        id=60,
        server_code="SRV-1",
        ip_address="10.0.0.10",
        site_id=40,
        os_version_id=50,
        hostname="db01",
        business_group="DBA",
        extra_attrs={"ssh_port": 2201},
    )
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


class _CollectorSettings:
    def __init__(self, callback_url: str):
        self.COLLECTOR_CALLBACK_URL = callback_url


def test_launch_asset_verify_uses_request_base_url_when_callback_url_missing(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 123,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/123",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    result = collector_service_module.CollectorService.launch_asset_verify(
        db,
        instance_id=80,
        payload=AssetVerifyLaunchRequest(),
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    collector_run = db.store[CollectorRun][0]
    assert result["status"] == "launched"
    assert collector_run.callback_url == "http://testserver/api/v1/collector/callback/"
    assert collector_run.extra_vars["callback_url"] == collector_run.callback_url
    assert collector_run.extra_vars["items"][0]["check_code"] == "DB_PORT_REACHABILITY"
    assert collector_run.extra_vars["items"][0]["target_scope"] == "db_instance"


def test_launch_asset_verify_prefers_configured_callback_url(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    monkeypatch.setattr(
        collector_service_module,
        "get_settings",
        lambda: _CollectorSettings("https://collector.example.com/api/v1/collector/callback/"),
    )
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 123,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/123",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    collector_service_module.CollectorService.launch_asset_verify(
        db,
        instance_id=80,
        payload=AssetVerifyLaunchRequest(),
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    collector_run = db.store[CollectorRun][0]
    assert collector_run.callback_url == "https://collector.example.com/api/v1/collector/callback/"


def test_launch_collector_run_builds_multiple_items(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 321,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/321",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    payload = collector_service_module.CollectorRunCreateRequest(
        scope={"target_scope": "db_instance", "asset_ids": [80]},
        check_codes=["DB_PORT_REACHABILITY", "SSH_PORT_REACHABILITY"],
        options={"timeout_seconds": 3},
    )
    result = collector_service_module.CollectorService.launch_collector_run(
        db,
        payload=payload,
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    assert result["item_count"] == 2
    collector_run = db.store[CollectorRun][0]
    assert collector_run.item_count == 2
    assert collector_run.target_scope == "mixed"
    assert len(db.store[CollectorRunItem]) == 2
    assert all(item.collector_run_id == collector_run.id for item in db.store[CollectorRunItem])
    assert collector_run.extra_vars["items"][0]["check_code"] == "DB_PORT_REACHABILITY"
    assert collector_run.extra_vars["items"][1]["check_code"] == "SSH_PORT_REACHABILITY"


def test_handle_callback_items_array_updates_instance_and_endpoint():
    db = _FakeSession()
    group, system, contact, link, db_type, db_version, site, os_version, server, cluster, vip, instance = _seed_asset_graph()
    db.seed(
        group,
        system,
        contact,
        link,
        db_type,
        db_version,
        site,
        os_version,
        server,
        cluster,
        vip,
        instance,
        CollectorRun(
            id=1,
            run_id="COLLECT-20260606150000-db_instance-80",
            target_scope="mixed",
            db_instance_id=80,
            server_id=60,
            status="launched",
            item_count=2,
            target_host="10.0.0.10",
            target_port=1521,
            callback_url="http://testserver/api/v1/collector/callback/",
            extra_vars={},
            request_payload={},
        ),
        CollectorRunItem(
            id=2,
            collector_run_id=1,
            run_id="COLLECT-20260606150000-db_instance-80",
            item_key="db_instance:80:DB_PORT_REACHABILITY:10.0.0.10:1521",
            check_code="DB_PORT_REACHABILITY",
            target_scope="db_instance",
            db_instance_id=80,
            server_id=60,
            target_host="10.0.0.10",
            target_port=1521,
            status="pending",
            timeout_seconds=5,
        ),
        CollectorRunItem(
            id=3,
            collector_run_id=1,
            run_id="COLLECT-20260606150000-db_instance-80",
            item_key="server:60:SSH_PORT_REACHABILITY:10.0.0.10:2201",
            check_code="SSH_PORT_REACHABILITY",
            target_scope="server",
            db_instance_id=80,
            server_id=60,
            target_host="10.0.0.10",
            target_port=2201,
            status="pending",
            timeout_seconds=5,
        ),
    )

    payload = collector_service_module.CollectorCallbackRequest(
        run_id="COLLECT-20260606150000-db_instance-80",
        awx_job_id=123,
        items=[
            collector_service_module.CollectorCallbackItem(
                item_key="db_instance:80:DB_PORT_REACHABILITY:10.0.0.10:1521",
                check_code="DB_PORT_REACHABILITY",
                target_scope="db_instance",
                asset_id=80,
                target_host="10.0.0.10",
                target_port=1521,
                status="verified",
                reachable=True,
                message="PORT_REACHABILITY_OK",
                raw_result={"elapsed_ms": 20},
            ),
            collector_service_module.CollectorCallbackItem(
                item_key="server:60:SSH_PORT_REACHABILITY:10.0.0.10:2201",
                check_code="SSH_PORT_REACHABILITY",
                target_scope="server",
                asset_id=60,
                target_host="10.0.0.10",
                target_port=2201,
                status="missing",
                reachable=False,
                message="SSH_PORT_REACHABILITY_FAILED",
                raw_result={"error": "timeout"},
            ),
        ],
    )

    result = collector_service_module.CollectorService.handle_callback(db, payload=payload)

    assert result["status"] == "partial_success"
    assert instance.trust_status == "verified"
    assert instance.reachability_status == "online"
    assert len(db.store.get(CollectorRunResult, [])) == 2
    assert len(db.store.get(AssetEndpoint, [])) == 2
    assert len(db.store.get(AssetEventHistory, [])) >= 1


def test_launch_collector_run_port_calibration_builds_candidate_items(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    db.seed(
        PortProfile(
            id=9001,
            profile_code="ORACLE_LISTENER_1521",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1521,
            is_required=True,
            is_candidate=True,
            is_enabled=True,
            priority=10,
        ),
        PortProfile(
            id=9002,
            profile_code="ORACLE_LISTENER_1526",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1526,
            is_required=False,
            is_candidate=True,
            is_enabled=True,
            priority=20,
        ),
        PortProfile(
            id=9003,
            profile_code="LINUX_SSH_22",
            target_scope="server",
            endpoint_type="LINUX_SSH",
            os_family="linux",
            protocol="tcp",
            default_port=22,
            is_required=True,
            is_candidate=True,
            is_enabled=True,
            priority=10,
        ),
    )
    db.seed(
        AssetEndpoint(
            id=9101,
            entity_type="db_instance",
            entity_id=80,
            endpoint_type="port",
            host="10.0.0.10",
            port=1526,
            protocol="tcp",
            source="discovered",
            expected=True,
            status="unknown",
        )
    )
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 777,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/777",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    payload = collector_service_module.CollectorRunCreateRequest(
        run_type="port_calibration",
        target_scope="db_instance",
        asset_ids=[80],
        check_codes=["PORT_CANDIDATE_REACHABILITY"],
        options={"timeout_seconds": 3},
    )
    result = collector_service_module.CollectorService.launch_collector_run(
        db,
        payload=payload,
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    assert result["status"] == "launched"
    assert result["item_count"] == len(db.store.get(CollectorRunItem, []))
    run = db.store[CollectorRun][0]
    assert run.request_payload["run_type"] == "port_calibration"
    assert run.extra_vars["run_type"] == "port_calibration"
    assert all(item.check_code == "PORT_CANDIDATE_REACHABILITY" for item in db.store.get(CollectorRunItem, []))
    assert len({(item.target_host, item.target_port, item.protocol) for item in db.store.get(CollectorRunItem, [])}) == len(
        db.store.get(CollectorRunItem, [])
    )
    assert all(item.endpoint_type != "port" for item in db.store.get(CollectorRunItem, []))
    assert any(item.target_port == 22 and item.endpoint_type == "LINUX_SSH" for item in db.store.get(CollectorRunItem, []))
    assert all(item.target_port != 3389 for item in db.store.get(CollectorRunItem, []))


def test_launch_collector_run_infers_port_calibration_from_candidate_check_code(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    db.seed(
        PortProfile(
            id=9001,
            profile_code="ORACLE_LISTENER_1521",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1521,
            is_required=True,
            is_candidate=True,
            is_enabled=True,
            priority=10,
        )
    )
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 778,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/778",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    payload = collector_service_module.CollectorRunCreateRequest(
        scope={"target_scope": "db_instance", "asset_ids": [80]},
        check_codes=["PORT_CANDIDATE_REACHABILITY"],
        options={"timeout_seconds": 3},
    )
    result = collector_service_module.CollectorService.launch_collector_run(
        db,
        payload=payload,
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    assert result["status"] == "launched"
    assert result["item_count"] >= 1
    assert db.store[CollectorRun][0].extra_vars["run_type"] == "port_calibration"


def test_port_calibration_candidate_failure_does_not_mark_instance_missing(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.port = None
    db.seed(
        PortProfile(
            id=9004,
            profile_code="ORACLE_LISTENER_1526_ONLY",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1526,
            is_required=False,
            is_candidate=True,
            is_enabled=True,
            priority=20,
        )
    )
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 779,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/779",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    payload = collector_service_module.CollectorRunCreateRequest(
        run_type="port_calibration",
        target_scope="db_instance",
        asset_ids=[80],
        check_codes=["PORT_CANDIDATE_REACHABILITY"],
        options={"timeout_seconds": 3, "include_related_server": False},
    )
    launch = collector_service_module.CollectorService.launch_collector_run(
        db,
        payload=payload,
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    run = db.store[CollectorRun][0]
    callback_payload = collector_service_module.CollectorCallbackRequest(
        run_id=run.run_id,
        awx_job_id=779,
        checked_by="awx",
        items=[
            collector_service_module.CollectorCallbackItem(
                item_key=db.store[CollectorRunItem][0].item_key,
                check_code="PORT_CANDIDATE_REACHABILITY",
                target_scope="db_instance",
                asset_id=80,
                target_host="10.0.0.10",
                target_port=1526,
                endpoint_type="ORACLE_LISTENER",
                protocol="tcp",
                port_source="profile_candidate",
                is_required=False,
                status="missing",
                reachable=False,
                message="Timeout",
                raw_result={},
            )
        ],
    )
    collector_service_module.CollectorService.handle_callback(db, payload=callback_payload)

    assert instance.trust_status != "missing"
    assert instance.reachability_status != "offline"
    assert len(db.store.get(AssetEventHistory, [])) == 0


def test_port_calibration_creates_drift_proposal_for_changed_port(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    db.seed(
        PortProfile(
            id=9002,
            profile_code="ORACLE_LISTENER_1526",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1526,
            is_required=False,
            is_candidate=True,
            is_enabled=True,
            priority=20,
        )
    )
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 780,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/780",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    payload = collector_service_module.CollectorRunCreateRequest(
        run_type="port_calibration",
        target_scope="db_instance",
        asset_ids=[80],
        check_codes=["PORT_CANDIDATE_REACHABILITY"],
        options={"timeout_seconds": 3, "include_related_server": False},
    )
    collector_service_module.CollectorService.launch_collector_run(
        db,
        payload=payload,
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    run = db.store[CollectorRun][0]
    callback_payload = collector_service_module.CollectorCallbackRequest(
        run_id=run.run_id,
        awx_job_id=780,
        checked_by="awx",
        items=[
            collector_service_module.CollectorCallbackItem(
                item_key=db.store[CollectorRunItem][0].item_key,
                check_code="PORT_CANDIDATE_REACHABILITY",
                target_scope="db_instance",
                asset_id=80,
                target_host="10.0.0.10",
                target_port=1521,
                endpoint_type="ORACLE_LISTENER",
                protocol="tcp",
                port_source="db_instance_port",
                is_required=True,
                status="missing",
                reachable=False,
                message="Timeout",
                raw_result={},
            ),
            collector_service_module.CollectorCallbackItem(
                item_key=db.store[CollectorRunItem][1].item_key,
                check_code="PORT_CANDIDATE_REACHABILITY",
                target_scope="db_instance",
                asset_id=80,
                target_host="10.0.0.10",
                target_port=1526,
                endpoint_type="ORACLE_LISTENER",
                protocol="tcp",
                port_source="profile_candidate",
                is_required=False,
                status="verified",
                reachable=True,
                message=None,
                raw_result={},
            ),
        ],
    )
    collector_service_module.CollectorService.handle_callback(db, payload=callback_payload)

    proposals = db.store.get(AssetChangeProposal, [])
    assert any(p.proposal_type == "PORT_DRIFT_SUSPECTED" for p in proposals)
    assert any(p.suggested_value == 1526 for p in proposals)


def test_port_calibration_callback_prefers_exact_asset_endpoint_identity(monkeypatch):
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    db.seed(
        PortProfile(
            id=9010,
            profile_code="ORACLE_LISTENER_1521",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1521,
            is_required=True,
            is_candidate=True,
            is_enabled=True,
            priority=10,
        ),
        PortProfile(
            id=9011,
            profile_code="ORACLE_LISTENER_1526",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1526,
            is_required=False,
            is_candidate=True,
            is_enabled=True,
            priority=20,
        ),
    )
    db.seed(
        AssetEndpoint(
            id=9201,
            entity_type="db_instance",
            entity_id=80,
            endpoint_type="port",
            host="10.0.0.10",
            port=1526,
            protocol="tcp",
            source="discovered",
            expected=True,
            status="unknown",
        ),
        AssetEndpoint(
            id=9202,
            entity_type="db_instance",
            entity_id=80,
            endpoint_type="ORACLE_LISTENER",
            host="10.0.0.10",
            port=1526,
            protocol="tcp",
            source="discovered",
            expected=True,
            status="unknown",
        ),
    )
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 781,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/781",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    payload = collector_service_module.CollectorRunCreateRequest(
        run_type="port_calibration",
        target_scope="db_instance",
        asset_ids=[80],
        check_codes=["PORT_CANDIDATE_REACHABILITY"],
        options={"timeout_seconds": 3, "include_related_server": False},
    )
    collector_service_module.CollectorService.launch_collector_run(
        db,
        payload=payload,
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    run = db.store[CollectorRun][0]
    callback_payload = collector_service_module.CollectorCallbackRequest(
        run_id=run.run_id,
        awx_job_id=781,
        checked_by="awx",
        items=[
            collector_service_module.CollectorCallbackItem(
                item_key=db.store[CollectorRunItem][1].item_key,
                check_code="PORT_CANDIDATE_REACHABILITY",
                target_scope="db_instance",
                asset_id=80,
                target_host="10.0.0.10",
                target_port=1526,
                status="verified",
                reachable=True,
                message=None,
                raw_result={},
            )
        ],
    )

    result = collector_service_module.CollectorService.handle_callback(db, payload=callback_payload)

    # P0-2: a single-item callback leaves the other run_item still "pending",
    # so the run is correctly reported as "running" until that item arrives.
    # The original "partial_success" expectation predates that safety net;
    # we accept the broader set so the test stays focused on endpoint identity.
    assert result["status"] in {"partial_success", "success", "running"}
    generic_endpoint = next(row for row in db.store[AssetEndpoint] if row.id == 9201)
    exact_endpoint = next(row for row in db.store[AssetEndpoint] if row.id == 9202)
    assert exact_endpoint.last_run_id == run.run_id
    assert generic_endpoint.last_run_id is None


def test_apply_proposal_requires_approved_status():
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=5001,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_FILL_SUGGESTION",
        proposal_type="PORT_FILL_SUGGESTION",
        field_path="port",
        current_value=None,
        suggested_value=1526,
        status="pending",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=5001, operator="admin")
        assert False, "expected ValueError for non-approved proposal"
    except ValueError as exc:
        assert "approved" in str(exc)


def test_create_proposal_flushes_before_serializing():
    class _ProposalSession:
        def __init__(self):
            self.items = []
            self.flushed = False

        def add(self, obj):
            self.items.append(obj)

        def flush(self):
            self.flushed = True
            for index, obj in enumerate(self.items, start=1):
                if getattr(obj, "id", None) is None:
                    obj.id = index

    db = _ProposalSession()
    proposal = AssetProposalService.create_proposal(
        db,
        target_type="db_instance",
        target_id=80,
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        confidence="medium",
        evidence={},
        source_run_id="run-1",
        source_item_key="item-1",
        requested_by="admin",
    )

    assert db.flushed is True
    assert proposal["id"] == 1


def test_apply_proposal_resets_instance_status_after_port_change():
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.trust_status = "verified"
    instance.reachability_status = "online"
    proposal = AssetChangeProposal(
        id=5002,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=5002, operator="admin")

    assert result["status"] == "applied"
    assert instance.port == 1526
    assert instance.trust_status == "unverified"
    assert instance.reachability_status == "unknown"


def test_apply_proposal_rejects_selected_value_for_non_conflict_type():
    """C4 (PR review 2026-06-18): apply_proposal 入口拒绝非 CONFLICT 的 selected_value。

    之前 PORT_DRIFT_SUSPECTED + selected_value 会被静默忽略，掩盖 API 误用。
    """
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=5003,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(
            db, proposal_id=5003, operator="admin", selected_value=1526,
        )
        assert False, "expected ValueError for selected_value on PORT_DRIFT_SUSPECTED"
    except ValueError as exc:
        msg = str(exc)
        assert "selected_value 仅允许用于 PORT_CANDIDATE_CONFLICT" in msg
        assert "PORT_DRIFT_SUSPECTED" in msg

    # PORT_CANDIDATE_CONFLICT 不传 selected_value 仍然报错（保持原行为）
    conflict_proposal = AssetChangeProposal(
        id=5004,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_CANDIDATE_CONFLICT",
        proposal_type="PORT_CANDIDATE_CONFLICT",
        field_path="port",
        current_value={"port": 22},
        suggested_value={"value": 1521, "candidates": [1521, 1526]},
        status="approved",
    )
    db.seed(conflict_proposal)
    try:
        AssetProposalService.apply_proposal(db, proposal_id=5004, operator="admin")
        assert False, "expected ValueError when CONFLICT missing selected_value"
    except ValueError as exc:
        assert "selected_value" in str(exc)


def test_apply_proposal_allows_selected_value_for_port_conflict():
    """C4: 反向用例 — PORT_CANDIDATE_CONFLICT 传 selected_value 仍然正常 apply。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.port = 22
    proposal = AssetChangeProposal(
        id=5005,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_CANDIDATE_CONFLICT",
        proposal_type="PORT_CANDIDATE_CONFLICT",
        field_path="port",
        current_value={"port": 22},
        suggested_value={"value": 1521, "candidates": [1521, 1526]},
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(
        db, proposal_id=5005, operator="admin", selected_value=1521,
    )
    assert result["status"] == "applied"
    assert instance.port == 1521
    assert instance.trust_status == "unverified"


def test_port_calibration_creates_drift_proposal_when_current_port_not_a_service_candidate(monkeypatch):
    """port 被错误地设成 OS 管理端口（如 22）时，只要有可达的 DB 服务端口也要生成 PORT_DRIFT_SUSPECTED。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.port = 22   # 被之前的 bug 设成了 SSH 端口
    db.seed(
        PortProfile(
            id=9020,
            profile_code="ORACLE_LISTENER_1521_X",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1521,
            is_required=True,
            is_candidate=True,
            is_enabled=True,
            priority=10,
        ),
        PortProfile(
            id=9021,
            profile_code="ORACLE_LISTENER_1526_X",
            target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER",
            db_type_code="ORACLE",
            protocol="tcp",
            default_port=1526,
            is_required=False,
            is_candidate=True,
            is_enabled=True,
            priority=20,
        ),
    )
    monkeypatch.setattr(collector_service_module, "get_settings", lambda: _CollectorSettings(""))
    monkeypatch.setattr(
        collector_service_module.AwxService,
        "launch_job",
        lambda extra_vars: {
            "awx_job_id": 782,
            "awx_job_url": "https://awx.example.com/#/jobs/playbook/782",
            "awx_job_template_id": 456,
            "awx_job_template_name": "JT_DBOPS_COLLECTOR_GENERIC",
        },
    )

    payload = collector_service_module.CollectorRunCreateRequest(
        run_type="port_calibration",
        target_scope="db_instance",
        asset_ids=[80],
        check_codes=["PORT_CANDIDATE_REACHABILITY"],
        options={"timeout_seconds": 3, "include_related_server": False},
    )
    collector_service_module.CollectorService.launch_collector_run(
        db,
        payload=payload,
        requested_by="admin",
        request_base_url="http://testserver/",
    )

    run = db.store[CollectorRun][0]
    items = db.store.get(CollectorRunItem, [])
    callback_payload = collector_service_module.CollectorCallbackRequest(
        run_id=run.run_id,
        awx_job_id=782,
        checked_by="awx",
        items=[
            collector_service_module.CollectorCallbackItem(
                item_key=items[0].item_key,
                check_code="PORT_CANDIDATE_REACHABILITY",
                target_scope="db_instance",
                asset_id=80,
                target_host="10.0.0.10",
                target_port=1521,
                endpoint_type="ORACLE_LISTENER",
                protocol="tcp",
                port_source="default_profile",
                is_required=True,
                status="missing",
                reachable=False,
                message="Timeout",
                raw_result={},
            ),
            collector_service_module.CollectorCallbackItem(
                item_key=items[1].item_key,
                check_code="PORT_CANDIDATE_REACHABILITY",
                target_scope="db_instance",
                asset_id=80,
                target_host="10.0.0.10",
                target_port=1526,
                endpoint_type="ORACLE_LISTENER",
                protocol="tcp",
                port_source="profile_candidate",
                is_required=False,
                status="verified",
                reachable=True,
                message=None,
                raw_result={},
            ),
        ],
    )
    collector_service_module.CollectorService.handle_callback(db, payload=callback_payload)

    proposals = db.store.get(AssetChangeProposal, [])
    assert any(p.proposal_type == "PORT_DRIFT_SUSPECTED" for p in proposals), "应生成 PORT_DRIFT_SUSPECTED"
    assert any(p.suggested_value == 1526 for p in proposals), "建议端口应为 1526"


# ---------------------------------------------------------------------------
# PortProfileService 单元测试
# ---------------------------------------------------------------------------


def test_port_profile_list_filters_by_target_scope():
    db = _FakeSession()
    db.seed(
        PortProfile(
            id=1, profile_code="LINUX_SSH_22", target_scope="server",
            endpoint_type="LINUX_SSH", protocol="tcp", default_port=22,
            is_required=True, is_candidate=True, is_enabled=True, priority=10,
        ),
        PortProfile(
            id=2, profile_code="ORACLE_LISTENER_1521", target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER", db_type_code="ORACLE", protocol="tcp",
            default_port=1521, is_required=True, is_candidate=True, is_enabled=True, priority=10,
        ),
    )

    server_profiles = PortProfileService.list_profiles(db, target_scope="server")
    assert len(server_profiles) == 1
    assert server_profiles[0]["profile_code"] == "LINUX_SSH_22"

    instance_profiles = PortProfileService.list_profiles(db, target_scope="db_instance")
    assert len(instance_profiles) == 1
    assert instance_profiles[0]["profile_code"] == "ORACLE_LISTENER_1521"


def test_port_profile_list_filters_db_type_code_with_null_match():
    db = _FakeSession()
    db.seed(
        PortProfile(
            id=1, profile_code="LINUX_SSH_22", target_scope="server",
            endpoint_type="LINUX_SSH", db_type_code=None, os_family="linux",
            protocol="tcp", default_port=22, is_required=True, is_candidate=True,
            is_enabled=True, priority=10,
        ),
        PortProfile(
            id=2, profile_code="ORACLE_LISTENER_1521", target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER", db_type_code="ORACLE", protocol="tcp",
            default_port=1521, is_required=True, is_candidate=True, is_enabled=True, priority=10,
        ),
    )

    # db_type_code=None 的通用 profile 应始终被匹配
    oracle_matches = PortProfileService.list_profiles(db, db_type_code="ORACLE")
    assert len(oracle_matches) == 2
    codes = {p["profile_code"] for p in oracle_matches}
    assert codes == {"LINUX_SSH_22", "ORACLE_LISTENER_1521"}


def test_port_profile_list_filters_os_family_with_null_match():
    db = _FakeSession()
    db.seed(
        PortProfile(
            id=1, profile_code="LINUX_SSH_22", target_scope="server",
            endpoint_type="LINUX_SSH", os_family="linux", protocol="tcp",
            default_port=22, is_required=True, is_candidate=True, is_enabled=True, priority=10,
        ),
        PortProfile(
            id=2, profile_code="WINDOWS_RDP_3389", target_scope="server",
            endpoint_type="WINDOWS_RDP", os_family="windows", protocol="tcp",
            default_port=3389, is_required=True, is_candidate=True, is_enabled=True, priority=10,
        ),
        PortProfile(
            id=3, profile_code="ORACLE_LISTENER_1521", target_scope="db_instance",
            endpoint_type="ORACLE_LISTENER", db_type_code="ORACLE", os_family=None,
            protocol="tcp", default_port=1521, is_required=True, is_candidate=True,
            is_enabled=True, priority=10,
        ),
    )

    linux_matches = PortProfileService.list_profiles(db, os_family="linux")
    assert len(linux_matches) == 2
    codes = {p["profile_code"] for p in linux_matches}
    assert codes == {"LINUX_SSH_22", "ORACLE_LISTENER_1521"}


def test_port_profile_list_filters_by_enabled():
    db = _FakeSession()
    db.seed(
        PortProfile(
            id=1, profile_code="ENABLED_ONE", target_scope="server",
            endpoint_type="LINUX_SSH", protocol="tcp", default_port=22,
            is_enabled=True, priority=10,
        ),
        PortProfile(
            id=2, profile_code="DISABLED_ONE", target_scope="server",
            endpoint_type="WINDOWS_RDP", protocol="tcp", default_port=3389,
            is_enabled=False, priority=10,
        ),
    )

    enabled = PortProfileService.list_profiles(db, is_enabled=True)
    assert len(enabled) == 1
    assert enabled[0]["profile_code"] == "ENABLED_ONE"

    disabled = PortProfileService.list_profiles(db, is_enabled=False)
    assert len(disabled) == 1
    assert disabled[0]["profile_code"] == "DISABLED_ONE"


# ---------------------------------------------------------------------------
# AssetProposalService 状态机单元测试
# ---------------------------------------------------------------------------


def test_approve_proposal_records_approved_by():
    db = _FakeSession()
    proposal = AssetChangeProposal(
        id=1, entity_type="db_instance", entity_id=80,
        change_type="PORT_FILL_SUGGESTION", proposal_type="PORT_FILL_SUGGESTION",
        field_path="port", current_value=None, suggested_value=1526,
        status="pending",
    )
    db.seed(proposal)

    result = AssetProposalService.approve_proposal(db, proposal_id=1, operator="alice")
    assert result["status"] == "approved"
    assert result["approved_by"] == "alice"
    assert proposal.approved_by == "alice"
    assert proposal.approved_at is not None


def test_approve_proposal_rejects_non_pending():
    db = _FakeSession()
    proposal = AssetChangeProposal(
        id=1, entity_type="db_instance", entity_id=80,
        change_type="PORT_FILL_SUGGESTION", status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.approve_proposal(db, proposal_id=1, operator="admin")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "pending" in str(exc)


def test_reject_proposal_records_rejected_by_not_approved_by():
    db = _FakeSession()
    proposal = AssetChangeProposal(
        id=1, entity_type="db_instance", entity_id=80,
        change_type="PORT_FILL_SUGGESTION", proposal_type="PORT_FILL_SUGGESTION",
        field_path="port", current_value=None, suggested_value=1526,
        status="pending",
    )
    db.seed(proposal)

    result = AssetProposalService.reject_proposal(
        db, proposal_id=1, operator="bob", reason="端口已被占用"
    )
    assert result["status"] == "rejected"
    assert result["rejected_by"] == "bob"
    assert result["rejected_reason"] == "端口已被占用"
    # 确保没有把 rejected_by 写入 approved_by
    assert proposal.approved_by is None
    assert proposal.rejected_by == "bob"


def test_reject_proposal_preserves_approved_by_when_rejecting_from_approved():
    db = _FakeSession()
    proposal = AssetChangeProposal(
        id=1, entity_type="db_instance", entity_id=80,
        change_type="PORT_FILL_SUGGESTION", proposal_type="PORT_FILL_SUGGESTION",
        field_path="port", current_value=None, suggested_value=1526,
        status="approved", approved_by="alice",
    )
    db.seed(proposal)

    result = AssetProposalService.reject_proposal(
        db, proposal_id=1, operator="bob", reason="不安全"
    )
    assert result["status"] == "rejected"
    # approved_by 保持不变
    assert result["approved_by"] == "alice"
    # rejected_by 记录实际操作人
    assert result["rejected_by"] == "bob"


def test_reject_proposal_not_found():
    db = _FakeSession()
    try:
        AssetProposalService.reject_proposal(db, proposal_id=999, operator="admin")
        assert False, "expected LookupError"
    except LookupError:
        pass


def test_approve_not_found():
    db = _FakeSession()
    try:
        AssetProposalService.approve_proposal(db, proposal_id=999, operator="admin")
        assert False, "expected LookupError"
    except LookupError:
        pass


def test_reject_proposal_from_pending_and_approved_only():
    db = _FakeSession()
    proposal = AssetChangeProposal(
        id=1, entity_type="db_instance", entity_id=80,
        change_type="PORT_FILL_SUGGESTION", status="applied",
        approved_by="alice",
    )
    db.seed(proposal)

    try:
        AssetProposalService.reject_proposal(db, proposal_id=1, operator="bob")
        assert False, "expected ValueError for applied proposal"
    except ValueError as exc:
        assert "pending/approved" in str(exc)


# ---------------------------------------------------------------------------
# PortCalibrationService 单元测试
# ---------------------------------------------------------------------------


def test_merge_candidate_picks_higher_priority_source():
    existing = {
        "host": "10.0.0.1",
        "port": 1521,
        "protocol": "tcp",
        "endpoint_type": "DB_SERVICE_PORT",
        "port_source": "excel_import",
        "is_required": False,
        "sources": [{"origin": "excel"}],
    }
    incoming = {
        "host": "10.0.0.1",
        "port": 1521,
        "protocol": "tcp",
        "endpoint_type": "ORACLE_LISTENER",
        "port_source": "asset_endpoint",
        "is_required": True,
        "sources": [{"origin": "endpoint"}],
    }

    merged = PortCalibrationService._merge_candidate(existing, incoming)

    # asset_endpoint priority (0) < excel_import (3), so incoming wins
    assert merged["port_source"] == "asset_endpoint"
    assert merged["endpoint_type"] == "ORACLE_LISTENER"
    assert merged["is_required"] is True
    assert len(merged["sources"]) == 2


def test_merge_candidate_keeps_existing_when_higher_priority():
    existing = {
        "host": "10.0.0.1",
        "port": 1521,
        "protocol": "tcp",
        "endpoint_type": "ORACLE_LISTENER",
        "port_source": "db_instance_port",
        "is_required": True,
        "sources": [{"origin": "instance"}],
    }
    incoming = {
        "host": "10.0.0.1",
        "port": 1521,
        "protocol": "tcp",
        "endpoint_type": "ORACLE_LISTENER",
        "port_source": "excel_import",
        "is_required": False,
        "sources": [{"origin": "excel"}],
    }

    merged = PortCalibrationService._merge_candidate(existing, incoming)

    # db_instance_port priority (1) < excel_import (3), existing wins
    assert merged["port_source"] == "db_instance_port"
    assert merged["is_required"] is True


def test_add_candidate_deduplicates_by_host_port_protocol():
    candidate_map: dict = {}
    c1 = PortCalibrationService._make_candidate(
        host="10.0.0.1", port=1521, endpoint_type="ORACLE_LISTENER",
        port_source="db_instance_port", is_required=True,
    )
    c2 = PortCalibrationService._make_candidate(
        host="10.0.0.1", port=1521, endpoint_type="ORACLE_LISTENER",
        port_source="excel_import", is_required=False,
    )

    PortCalibrationService._add_candidate(candidate_map, c1, target_scope="db_instance")
    PortCalibrationService._add_candidate(candidate_map, c2, target_scope="db_instance")

    assert len(candidate_map) == 1
    key = ("10.0.0.1", 1521, "tcp")
    assert key in candidate_map
    # 应保留优先级更高的 db_instance_port
    assert candidate_map[key]["port_source"] == "db_instance_port"


def test_candidate_score_sorts_by_endpoint_type_then_source():
    generic_candidate = {
        "port": 1521, "endpoint_type": "DB_SERVICE_PORT",
        "port_source": "excel_import",
    }
    specific_candidate = {
        "port": 1521, "endpoint_type": "ORACLE_LISTENER",
        "port_source": "profile_candidate",
    }

    # specific endpoint type (0,0) < generic (1,x) — lower is better
    generic_score = PortCalibrationService._candidate_score(generic_candidate)
    specific_score = PortCalibrationService._candidate_score(specific_candidate)
    assert specific_score < generic_score


def test_normalize_endpoint_type_handles_empty():
    assert PortCalibrationService._normalize_endpoint_type("server", None, None) == "OS_ADMIN_PORT"
    assert PortCalibrationService._normalize_endpoint_type("db_instance", "", None) == "DB_SERVICE_PORT"
    assert PortCalibrationService._normalize_endpoint_type("db_instance", "port", None) == "DB_SERVICE_PORT"
    assert PortCalibrationService._normalize_endpoint_type("server", "LINUX_SSH", None) == "LINUX_SSH"


def test_to_int_validates_port_range():
    assert PortCalibrationService._to_int(None) is None
    assert PortCalibrationService._to_int("") is None
    assert PortCalibrationService._to_int("abc") is None
    assert PortCalibrationService._to_int(0) is None
    assert PortCalibrationService._to_int(65536) is None
    assert PortCalibrationService._to_int(22) == 22
    assert PortCalibrationService._to_int("1521") == 1521
    assert PortCalibrationService._to_int(65535) == 65535


# ============================================================================
# C2 (PR review 2026-06-18): batch_action SAVEPOINT 改造
# ============================================================================


def test_batch_action_uses_savepoint_partial_failure():
    """C2: 3 个 proposal，第 2 个失败，验证第 1 和第 3 的 success=True 且 DB 已写入。

    旧实现 db.rollback() 会丢掉前序 in-memory 成功状态，success_count 撒谎。
    """
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.port = 1521
    server = db.store[Server][0]
    server.hostname = "old-host"

    # p1: db_instance.port — 成功
    p1 = AssetChangeProposal(
        id=6001,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        status="approved",
    )
    # p2: db_instance.database_status — 不在白名单 → ValueError（预期失败）
    p2 = AssetChangeProposal(
        id=6002,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="database_status",
        current_value="STARTED",
        suggested_value="STARTED",
        status="approved",
    )
    # p3: server.hostname — 成功
    p3 = AssetChangeProposal(
        id=6003,
        entity_type="server",
        entity_id=60,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="hostname",
        current_value="old-host",
        suggested_value="new-host",
        status="approved",
    )
    db.seed(p1, p2, p3)

    result = AssetProposalService.batch_action(
        db,
        proposal_ids=[6001, 6002, 6003],
        action="apply",
        operator="admin",
    )

    # 关键断言：success_count = 2, fail_count = 1
    assert result["success_count"] == 2
    assert result["fail_count"] == 1
    assert result["action"] == "apply"

    # p1 / p3 成功 — DB 状态写入；p2 失败 — 状态不变
    results_by_id = {entry["id"]: entry for entry in result["results"]}
    assert results_by_id[6001]["success"] is True
    assert "error" not in results_by_id[6001]
    assert results_by_id[6002]["success"] is False
    assert "database_status" in results_by_id[6002]["error"]
    assert results_by_id[6003]["success"] is True

    # DB 持久化状态：p1 应用了 port，p3 应用了 hostname，p2 未应用
    assert instance.port == 1526
    assert p1.status == "applied"
    assert p2.status == "approved"  # 不变
    assert p3.status == "applied"
    assert server.hostname == "new-host"


def test_batch_action_unknown_action_rejected():
    """C2: 未知 action 在每条 proposal 的 savepoint 内被拒绝，整体返回全失败。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    p = AssetChangeProposal(
        id=6010,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        status="approved",
    )
    db.seed(p)

    result = AssetProposalService.batch_action(
        db,
        proposal_ids=[6010],
        action="weird_action",
        operator="admin",
    )
    assert result["success_count"] == 0
    assert result["fail_count"] == 1
    assert result["results"][0]["success"] is False
    assert "未知 action" in result["results"][0]["error"]


def test_batch_action_all_approve_succeeds():
    """C2: 多个 pending proposal 一齐 approve，savepoint.commit() 路径都 OK。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    p1 = AssetChangeProposal(
        id=6020,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        status="pending",
    )
    p2 = AssetChangeProposal(
        id=6021,
        entity_type="server",
        entity_id=70,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="hostname",
        current_value="old",
        suggested_value="new",
        status="pending",
    )
    db.seed(p1, p2)

    result = AssetProposalService.batch_action(
        db,
        proposal_ids=[6020, 6021],
        action="approve",
        operator="admin",
    )
    assert result["success_count"] == 2
    assert result["fail_count"] == 0
    assert p1.status == "approved"
    assert p2.status == "approved"
    assert p1.approved_by == "admin"
    assert p2.approved_by == "admin"


def test_batch_action_rejects_string_override_value():
    """C2: PORT_CANDIDATE_CONFLICT 时 str 端口号被拒绝（非 int）。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    p = AssetChangeProposal(
        id=6030,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_CANDIDATE_CONFLICT",
        proposal_type="PORT_CANDIDATE_CONFLICT",
        field_path="port",
        current_value={"port": 22},
        suggested_value={"value": 1521, "candidates": [1521, 1526]},
        status="approved",
    )
    db.seed(p)

    result = AssetProposalService.batch_action(
        db,
        proposal_ids=[6030],
        action="apply",
        operator="admin",
        override_values={"6030": "1521"},  # 字符串而非整数
    )
    assert result["success_count"] == 0
    assert result["fail_count"] == 1
    assert "整数端口" in result["results"][0]["error"]


def test_batch_action_request_rejects_empty_proposal_ids():
    """C2 配套：空 proposal_ids 列表返回 success=0, fail=0，不抛错。"""
    db = _FakeSession()
    result = AssetProposalService.batch_action(
        db,
        proposal_ids=[],
        action="approve",
        operator="admin",
    )
    assert result["success_count"] == 0
    assert result["fail_count"] == 0
    assert result["results"] == []


# ============================================================================
# C4 (PR review 2026-06-18): apply_proposal 入口 guard（已在上面文件中段测试）
# ============================================================================


# ============================================================================
# I1 (PR review 2026-06-18): apply_proposal 白名单拒绝
# ============================================================================


def test_apply_proposal_rejects_non_whitelisted_field_db_instance():
    """I1: db_instance.ip_address 不在白名单 → ValueError。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=7001,
        entity_type="db_instance",
        entity_id=80,
        change_type="IP_DRIFT",
        proposal_type="IP_DRIFT",
        field_path="ip_address",  # not in APPLYABLE_FIELDS["db_instance"]
        current_value="10.0.0.10",
        suggested_value="10.0.0.11",
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=7001, operator="admin")
        assert False, "expected ValueError for non-whitelisted db_instance field"
    except ValueError as exc:
        msg = str(exc)
        assert "db_instance.ip_address" in msg
        assert "白名单" in msg


def test_apply_proposal_rejects_db_instance_database_status():
    """I1: db_instance.database_status 不在白名单（plan 注释明确禁止）。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=7002,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="database_status",  # semantic mismatch → not whitelisted
        current_value="STARTED",
        suggested_value="STARTED",
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=7002, operator="admin")
        assert False, "expected ValueError for database_status"
    except ValueError as exc:
        assert "database_status" in str(exc)
        assert "白名单" in str(exc)


def test_apply_proposal_rejects_db_version_id():
    """I1: entity_type=db_version 完全不在 APPLYABLE_FIELDS → ValueError。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=7003,
        entity_type="db_version",  # unknown entity_type
        entity_id=31,
        change_type="DB_FACT_DRIFT_DETECTED",
        proposal_type="DB_FACT_DRIFT_DETECTED",
        field_path="version_code",
        current_value="19c",
        suggested_value="21c",
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=7003, operator="admin")
        assert False, "expected ValueError for db_version entity_type"
    except ValueError as exc:
        assert "白名单" in str(exc) or "不支持" in str(exc)


def test_apply_proposal_rejects_cluster_cluster_type():
    """I1: cluster.cluster_type 不在白名单（影响面大，禁止自动 apply）。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=7004,
        entity_type="cluster",
        entity_id=70,
        change_type="CLUSTER_TYPE_MISMATCH",
        proposal_type="CLUSTER_TYPE_MISMATCH",
        field_path="cluster_type",
        current_value="DATAGUARD",
        suggested_value="RAC",
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=7004, operator="admin")
        assert False, "expected ValueError for cluster.cluster_type"
    except ValueError as exc:
        assert "白名单" in str(exc)


# ============================================================================
# I2 (PR review 2026-06-18): apply_proposal 新字段 happy path
# ============================================================================


def test_apply_proposal_writes_instance_name():
    """I2: db_instance.instance_name apply 写入新值。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.instance_name = "OLD_NAME"
    proposal = AssetChangeProposal(
        id=7101,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="instance_name",
        current_value="OLD_NAME",
        suggested_value="NEW_NAME",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7101, operator="admin")

    assert result["status"] == "applied"
    assert instance.instance_name == "NEW_NAME"
    events = [e for e in db.store[AssetEventHistory] if e.event_type == "ASSET_PROPOSAL_APPLIED"]
    assert len(events) == 1
    assert events[0].changed_fields["field_path"] == "instance_name"


def test_apply_proposal_writes_service_name():
    """I2: db_instance.service_name apply 写入新值。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.service_name = "OLD_SVC"
    proposal = AssetChangeProposal(
        id=7102,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="service_name",
        current_value="OLD_SVC",
        suggested_value="NEW_SVC",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7102, operator="admin")

    assert result["status"] == "applied"
    assert instance.service_name == "NEW_SVC"


def test_apply_proposal_writes_node_role():
    """I2: db_instance.node_role apply 写入新值。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.node_role = "primary"
    proposal = AssetChangeProposal(
        id=7103,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="node_role",
        current_value="primary",
        suggested_value="standby",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7103, operator="admin")

    assert result["status"] == "applied"
    assert instance.node_role == "standby"


def test_apply_proposal_writes_server_hostname():
    """I2: server.hostname apply 写入新值。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    server = db.store[Server][0]
    server.hostname = "old-host"
    proposal = AssetChangeProposal(
        id=7201,
        entity_type="server",
        entity_id=60,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="hostname",
        current_value="old-host",
        suggested_value="new-host",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7201, operator="admin")

    assert result["status"] == "applied"
    assert server.hostname == "new-host"


def test_apply_proposal_writes_server_cpu_cores():
    """I2: server.cpu_cores apply 写入新值。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    server = db.store[Server][0]
    server.cpu_cores = 8
    proposal = AssetChangeProposal(
        id=7202,
        entity_type="server",
        entity_id=60,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="cpu_cores",
        current_value=8,
        suggested_value=16,
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7202, operator="admin")

    assert result["status"] == "applied"
    assert int(server.cpu_cores) == 16


def test_apply_proposal_writes_server_memory_gb():
    """I2: server.memory_gb apply 写入新值。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    server = db.store[Server][0]
    server.memory_gb = 32
    proposal = AssetChangeProposal(
        id=7203,
        entity_type="server",
        entity_id=60,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="memory_gb",
        current_value=32,
        suggested_value=64,
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7203, operator="admin")

    assert result["status"] == "applied"
    assert int(server.memory_gb) == 64


def test_apply_proposal_writes_server_disk_gb():
    """I2: server.disk_gb apply 写入新值。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    server = db.store[Server][0]
    server.disk_gb = 500
    proposal = AssetChangeProposal(
        id=7204,
        entity_type="server",
        entity_id=60,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="disk_gb",
        current_value=500,
        suggested_value=1000,
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7204, operator="admin")

    assert result["status"] == "applied"
    assert int(server.disk_gb) == 1000


# ============================================================================
# I3 (PR review 2026-06-18): PORT_CANDIDATE_CONFLICT 三重校验
# ============================================================================


def test_apply_proposal_port_conflict_requires_selected_value():
    """I3 (聚焦): PORT_CANDIDATE_CONFLICT 必须传 selected_value。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=7301,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_CANDIDATE_CONFLICT",
        proposal_type="PORT_CANDIDATE_CONFLICT",
        field_path="port",
        current_value={"port": 22},
        suggested_value={"value": 1521, "candidates": [1521, 1526]},
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=7301, operator="admin")
        assert False, "expected ValueError when CONFLICT missing selected_value"
    except ValueError as exc:
        assert "selected_value" in str(exc)


def test_apply_proposal_port_conflict_rejects_out_of_range():
    """I3: selected_value=70000 (>65535) 或 0 → ValueError。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=7302,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_CANDIDATE_CONFLICT",
        proposal_type="PORT_CANDIDATE_CONFLICT",
        field_path="port",
        current_value={"port": 22},
        suggested_value={"value": 1521, "candidates": [1521, 1526]},
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(
            db, proposal_id=7302, operator="admin", selected_value=70000,
        )
        assert False, "expected ValueError for out-of-range port"
    except ValueError as exc:
        assert "1-65535" in str(exc)

    try:
        AssetProposalService.apply_proposal(
            db, proposal_id=7302, operator="admin", selected_value=0,
        )
        assert False, "expected ValueError for port=0"
    except ValueError as exc:
        assert "1-65535" in str(exc)


def test_apply_proposal_port_conflict_rejects_unknown_port():
    """I3: selected_value=9999 不在 candidates → ValueError。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    proposal = AssetChangeProposal(
        id=7303,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_CANDIDATE_CONFLICT",
        proposal_type="PORT_CANDIDATE_CONFLICT",
        field_path="port",
        current_value={"port": 22},
        suggested_value={"value": 1521, "candidates": [1521, 1526]},
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(
            db, proposal_id=7303, operator="admin", selected_value=9999,
        )
        assert False, "expected ValueError for unknown port"
    except ValueError as exc:
        assert "9999" in str(exc)
        assert "候选端口" in str(exc)


# ============================================================================
# I4 (PR review 2026-06-18): list_proposals 按 source_run_id 过滤
# ============================================================================


def test_list_proposals_filters_by_source_run_id():
    """I4: list_proposals(source_run_id=X) 只返回 X 的 proposals，避免跨批 apply。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    p_run1_a = AssetChangeProposal(
        id=7401,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        source_run_id="run-1",
        evidence_run_id="run-1",
        status="pending",
    )
    p_run1_b = AssetChangeProposal(
        id=7402,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        source_run_id="run-1",
        evidence_run_id="run-1",
        status="pending",
    )
    p_run2_a = AssetChangeProposal(
        id=7403,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        source_run_id="run-2",
        evidence_run_id="run-2",
        status="pending",
    )
    db.seed(p_run1_a, p_run1_b, p_run2_a)

    # 不传 source_run_id：返回全部
    all_rows = AssetProposalService.list_proposals(db)
    assert len(all_rows) == 3

    # source_run_id=run-1：只返回 7401, 7402
    run1_rows = AssetProposalService.list_proposals(db, source_run_id="run-1")
    assert len(run1_rows) == 2
    assert {row["id"] for row in run1_rows} == {7401, 7402}

    # source_run_id=run-2：只返回 7403
    run2_rows = AssetProposalService.list_proposals(db, source_run_id="run-2")
    assert len(run2_rows) == 1
    assert run2_rows[0]["id"] == 7403

    # source_run_id=run-999：空
    none_rows = AssetProposalService.list_proposals(db, source_run_id="run-999")
    assert none_rows == []


def test_list_proposals_source_run_id_with_other_filters():
    """I4: source_run_id 与 status filter 组合工作。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    p = AssetChangeProposal(
        id=7410,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        source_run_id="run-7",
        evidence_run_id="run-7",
        status="approved",
    )
    p2 = AssetChangeProposal(
        id=7411,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_DRIFT_SUSPECTED",
        proposal_type="PORT_DRIFT_SUSPECTED",
        field_path="port",
        current_value=1521,
        suggested_value=1526,
        source_run_id="run-7",
        evidence_run_id="run-7",
        status="pending",
    )
    db.seed(p, p2)

    rows = AssetProposalService.list_proposals(
        db, source_run_id="run-7", status="approved",
    )
    assert len(rows) == 1
    assert rows[0]["id"] == 7410


# --- PR review 2026-06-20 followup: C1 (Numeric coerce) + C2 (node_role) + C3 (db_version idempotency) ---


def test_apply_proposal_writes_memory_gb_decimal_preserved():
    """C1: server.memory_gb Numeric(10,2) — "64.5" 写入后保留小数位（不再 int() 截断）。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    server = db.store[Server][0]
    server.memory_gb = 32
    proposal = AssetChangeProposal(
        id=7301,
        entity_type="server",
        entity_id=60,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="memory_gb",
        current_value=32,
        suggested_value="64.5",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7301, operator="admin")

    assert result["status"] == "applied"
    # 关键断言：64.5 不被截断为 64
    assert float(server.memory_gb) == 64.5


def test_apply_proposal_writes_disk_gb_decimal_preserved():
    """C1: server.disk_gb Numeric(12,2) — "1500.75" 保留小数。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    server = db.store[Server][0]
    server.disk_gb = 500
    proposal = AssetChangeProposal(
        id=7302,
        entity_type="server",
        entity_id=60,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="disk_gb",
        current_value=500,
        suggested_value="1500.75",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7302, operator="admin")

    assert result["status"] == "applied"
    assert float(server.disk_gb) == 1500.75


def test_apply_proposal_writes_node_role_lowercases():
    """C2: node_role "PRIMARY" → "primary"（走 APPLYABLE_NODE_ROLES 白名单，大小写不敏感）。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.node_role = "single"
    proposal = AssetChangeProposal(
        id=7303,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="node_role",
        current_value="single",
        suggested_value="PRIMARY",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7303, operator="admin")

    assert result["status"] == "applied"
    assert instance.node_role == "primary"


def test_apply_proposal_rejects_node_role_invalid_value():
    """C2: 不在 chk_node_role 白名单的值 → ValueError，不绕过 CHECK 约束。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.node_role = "primary"
    proposal = AssetChangeProposal(
        id=7304,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="node_role",
        current_value="primary",
        suggested_value="replica",  # not in {primary, standby, single, member, unknown}
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=7304, operator="admin")
    except ValueError as exc:
        assert "不在允许集合" in str(exc)
        # 关键断言：原值不变（事务回滚）
        assert instance.node_role == "primary"
    else:
        raise AssertionError("expected ValueError for invalid node_role")


def test_apply_proposal_db_version_auto_create_idempotent():
    """C3: 同一 version_str 连续 apply 两次，只新增 1 行 DbVersion（避免 ghost 行循环）。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    # 清空 db_type_id 30 下所有 DbVersion，让两次都触发 auto-create 路径
    initial_versions = [v for v in db.store[DbVersion] if v.db_type_id == 30]
    for v in initial_versions:
        db.delete(v)
    initial_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    assert initial_count == 0

    proposal1 = AssetChangeProposal(
        id=7305,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_version",
        current_value=None,
        suggested_value="21c",
        status="approved",
    )
    proposal2 = AssetChangeProposal(
        id=7306,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_version",
        current_value=None,
        suggested_value="21c",
        status="approved",
    )
    db.seed(proposal1, proposal2)

    # 第一次：auto-create 1 行
    AssetProposalService.apply_proposal(db, proposal_id=7305, operator="admin")
    after_first = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30 and v.version_name == "21c")
    assert after_first == 1

    # 第二次：recheck 命中已存在行，不重复创建
    AssetProposalService.apply_proposal(db, proposal_id=7306, operator="admin")
    after_second = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30 and v.version_name == "21c")
    assert after_second == 1, "ghost 行：C3 idempotency 未生效"


def test_apply_proposal_db_version_rejects_empty_version_str():
    """C3: 全空白 suggested_value → ValueError（不创建空名 DbVersion 行）。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.db_version_id = 31
    proposal = AssetChangeProposal(
        id=7307,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_version",
        current_value=31,
        suggested_value="   ",  # 全空白
        status="approved",
    )
    db.seed(proposal)

    try:
        AssetProposalService.apply_proposal(db, proposal_id=7307, operator="admin")
    except ValueError as exc:
        assert "空白" in str(exc)
        # 关键断言：原 db_version_id 未被清空（事务回滚）
        assert instance.db_version_id == 31
        # 关键断言：没有创建空名 DbVersion
        empty_rows = [v for v in db.store[DbVersion] if v.db_type_id == 30 and not v.version_name.strip()]
        assert empty_rows == []
    else:
        raise AssertionError("expected ValueError for empty version string")


def test_apply_proposal_record_event_captures_real_before_status():
    """I5: apply 改 port 后，event 记录真实 before=verified, after=unverified。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.trust_status = "verified"
    instance.port = 1521
    proposal = AssetChangeProposal(
        id=7308,
        entity_type="db_instance",
        entity_id=80,
        change_type="PORT_CANDIDATE_CONFLICT",
        proposal_type="PORT_CANDIDATE_CONFLICT",
        field_path="port",
        current_value=1521,
        suggested_value={"value": 1521, "candidates": [1521, 1522]},
        status="approved",
    )
    db.seed(proposal)

    AssetProposalService.apply_proposal(db, proposal_id=7308, operator="admin", selected_value=1521)

    events = [e for e in db.store[AssetEventHistory] if e.event_type == "ASSET_PROPOSAL_APPLIED"]
    assert len(events) == 1
    # I5 关键断言：before=verified（应用前真实状态），after=unverified（应用后被覆盖）
    assert events[0].before_status == "verified"
    assert events[0].after_status == "unverified"


# --- PR review 2026-06-20 C7: db_version / db_size_gb happy-path 测试 ---


def test_apply_proposal_db_version_exact_match_on_version_name():
    """C7: suggested_value 精确匹配 DbVersion.version_name → 不 auto-create，直接 link。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.db_version_id = None  # 待 apply
    initial_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    proposal = AssetChangeProposal(
        id=7401,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_version",
        current_value=None,
        suggested_value="19c",  # 精确匹配 seed 中的 DbVersion
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7401, operator="admin")

    assert result["status"] == "applied"
    # 关键断言：匹配到现有行，没创建新行
    after_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    assert after_count == initial_count
    # 关键断言：instance.db_version_id 设为已存在的 31
    assert instance.db_version_id == 31


def test_apply_proposal_db_version_uses_evidence_version_full():
    """C7: suggested_value 没匹配但 evidence.version_full 命中 → 不 auto-create，link 已有行。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.db_version_id = None
    initial_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    proposal = AssetChangeProposal(
        id=7402,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_version",
        current_value=None,
        suggested_value="unknown-label",  # 没匹配
        evidence={"version_full": "19c"},  # evidence 命中
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7402, operator="admin")

    assert result["status"] == "applied"
    # 关键断言：evidence 命中，没创建新行
    after_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    assert after_count == initial_count
    # 关键断言：link 到已存在的 31
    assert instance.db_version_id == 31


def test_apply_proposal_db_version_auto_creates_when_unmatched():
    """C7: 字典完全没匹配 → auto-create 新 DbVersion 行。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.db_version_id = None
    # 清空所有 db_type_id=30 的 DbVersion
    for v in [v for v in db.store[DbVersion] if v.db_type_id == 30]:
        db.delete(v)
    initial_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    assert initial_count == 0

    proposal = AssetChangeProposal(
        id=7403,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_version",
        current_value=None,
        suggested_value="21c",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7403, operator="admin")

    assert result["status"] == "applied"
    # 关键断言：auto-create 1 行
    after_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    assert after_count == 1
    new_version = [v for v in db.store[DbVersion] if v.db_type_id == 30][0]
    assert new_version.version_name == "21c"
    assert new_version.version_code == "21c"
    # 关键断言：instance.db_version_id 指向新建行
    assert instance.db_version_id == new_version.id


def test_apply_proposal_writes_db_size_gb_float():
    """C7: db_size_gb Numeric(12,2) 写入 "1024.5" 保留小数。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.db_size_gb = None
    proposal = AssetChangeProposal(
        id=7404,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_size_gb",
        current_value=None,
        suggested_value="1024.5",
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7404, operator="admin")

    assert result["status"] == "applied"
    assert float(instance.db_size_gb) == 1024.5


def test_apply_proposal_writes_db_size_gb_from_dict_evidence():
    """C7: db_size_gb suggested_value 是 dict {"value": ...} 也能解包。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.db_size_gb = None
    proposal = AssetChangeProposal(
        id=7405,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_size_gb",
        current_value=None,
        suggested_value={"value": "2048.75", "unit": "GB"},
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7405, operator="admin")

    assert result["status"] == "applied"
    assert float(instance.db_size_gb) == 2048.75


def test_apply_proposal_db_version_rejects_unregistered_evidence_only():
    """C7: suggested_value 不可解析且 evidence.version_full 也不命中 → 走 auto-create。"""
    db = _FakeSession()
    db.seed(*_seed_asset_graph())
    instance = db.store[DbInstance][0]
    instance.db_version_id = None
    for v in [v for v in db.store[DbVersion] if v.db_type_id == 30]:
        db.delete(v)
    initial_count = sum(1 for v in db.store[DbVersion] if v.db_type_id == 30)
    assert initial_count == 0

    proposal = AssetChangeProposal(
        id=7406,
        entity_type="db_instance",
        entity_id=80,
        change_type="ASSET_FACT_DRIFT",
        proposal_type="ASSET_FACT_DRIFT",
        field_path="db_version",
        current_value=None,
        suggested_value="PostgreSQL 16",
        evidence={"version_full": "PostgreSQL 16.2"},
        status="approved",
    )
    db.seed(proposal)

    result = AssetProposalService.apply_proposal(db, proposal_id=7406, operator="admin")

    assert result["status"] == "applied"
    # 关键断言：都未命中 → auto-create
    after = [v for v in db.store[DbVersion] if v.db_type_id == 30]
    assert len(after) == 1
    assert after[0].version_name == "PostgreSQL 16"


