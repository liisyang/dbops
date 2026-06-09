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

    assert result["status"] in {"partial_success", "success"}
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
