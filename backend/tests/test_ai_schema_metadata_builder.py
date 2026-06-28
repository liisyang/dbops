"""
Phase 3.6B0 C8 — _AiSchemaMetadataBuilder 单元测试

覆盖 (plan §13 Schema Snapshot 矩阵的 builder 部分):

  1.  Builder 已注册到 CheckItemBuilderRegistry
  2.  Class attrs: check_code / supported db types / max limits
  3.  SQL 模板 inline 到 rule_config.sql_text (C7 单源)
  4.  build() 空 assets / 非 db_instance scope / instance 不存在 → 空列表
  5.  build() 非 postgresql 实例 → UNSUPPORTED_DB_TYPE skipped
  6.  build() 缺凭证 → CREDENTIAL_MISSING skipped
  7.  build() postgresql + 凭证齐全 → 正常 item
      - item_key 格式正确
      - check_code / executor_type=db_sql_readonly / business_domain=ai_schema
      - db_instance_id / server_id / target_host / target_port
      - database_name='postgres'
      - rule_config.sql_text 含 information_schema.columns
      - rule_config.max_rows=20000, max_bytes=10MB
      - rule_config.source / phase 标识
      - 5 个 credential_* 字段
  8.  多实例混合: 1 pg + 1 oracle → 1 normal + 1 skipped

策略:
- 纯 mock Session + CredentialResolverService (不连 DB)
- 与 test_collector_check_codes_endpoint.py / test_pg_schema_columns_sql.py 同一策略
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.check_item_builder_registry import (
    BaseCheckItemBuilder,
    CheckItemBuilderRegistry,
    _AiSchemaMetadataBuilder,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_credential():
    return {
        "credential_profile_id": 7,
        "profile_code": "cred-db-pg-ro-prod",
        "awx_credential_id": 12,
        "awx_credential_name": "cred-db-pg-ro-prod",
        "credential_type": "db",
        "binding_role": "db_readonly",
    }


def _make_instance(*, instance_id: int = 100, server_id: int = 1, port: int = 5432,
                   instance_name: str = "pg-prod-01", service_name: str = ""):
    inst = MagicMock()
    inst.id = instance_id
    inst.server_id = server_id
    inst.port = port
    inst.instance_name = instance_name
    inst.service_name = service_name
    return inst


def _make_server(*, server_id: int = 1, ip: str = "10.0.0.10"):
    srv = MagicMock()
    srv.id = server_id
    srv.ip_address = ip
    return srv


def _make_dbtype(*, type_code: str = "postgresql"):
    dt = MagicMock()
    dt.type_code = type_code
    return dt


def _query_for(obj):
    q = MagicMock()
    q.filter.return_value.first.return_value = obj
    return q


def _session_with_single_asset(*, instance=None, server=None, dbtype=None):
    """Return a MagicMock Session whose .query() chain yields instance,
    server, dbtype in order on successive calls."""
    session = MagicMock()

    def qside(model):
        name = model.__name__
        if name == "DbInstance":
            return _query_for(instance)
        if name == "Server":
            return _query_for(server)
        if name == "DbType":
            return _query_for(dbtype)
        return _query_for(None)

    session.query.side_effect = qside
    return session


def _asset(instance_id: int = 100):
    return {"id": instance_id, "target_scope": "db_instance"}


# ---------------------------------------------------------------------------
# 1. Registration + class attrs
# ---------------------------------------------------------------------------

def test_builder_registered_in_registry():
    codes = CheckItemBuilderRegistry.supported_codes()
    assert "DB_SCHEMA_METADATA_COLLECTION" in codes, (
        "Builder must be registered before C8 callback can resolve it"
    )


def test_builder_class_attrs():
    b = _AiSchemaMetadataBuilder()
    assert b._check_code == "DB_SCHEMA_METADATA_COLLECTION"
    assert b._SUPPORTED_DB_TYPES == frozenset({"postgresql", "postgres"})
    assert b._MAX_ROWS == 20000
    assert b._MAX_BYTES == 10485760
    assert issubclass(_AiSchemaMetadataBuilder, BaseCheckItemBuilder)


def test_sql_template_loadable_and_readonly():
    """SQL template loads; body is read-only SELECT (full read-only test
    lives in C7's test_pg_schema_columns_sql.py — we only smoke-check here)."""
    sql = _AiSchemaMetadataBuilder._load_sql_template()
    assert sql, "SQL template must not be empty"
    assert "information_schema.columns" in sql
    assert "ordinal_position" in sql
    # First non-comment line must be SELECT (C7 invariant — body starts here)
    body = "\n".join(
        ln for ln in sql.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    )
    assert body.lstrip().upper().startswith("SELECT"), (
        f"SQL body must start with SELECT, got: {body[:80]!r}"
    )


# ---------------------------------------------------------------------------
# 2. build() input filtering (no DB hit / wrong scope / missing instance)
# ---------------------------------------------------------------------------

def test_build_empty_assets_returns_empty():
    b = _AiSchemaMetadataBuilder()
    session = MagicMock()
    assert b.build(session, assets=[], options={}) == []
    session.query.assert_not_called()


def test_build_wrong_scope_skipped():
    b = _AiSchemaMetadataBuilder()
    session = MagicMock()
    assets = [{"id": 1, "target_scope": "server"}]
    assert b.build(session, assets=assets, options={}) == []
    session.query.assert_not_called()


def test_build_instance_not_found_returns_empty():
    b = _AiSchemaMetadataBuilder()
    session = MagicMock()
    # DbInstance query returns None → skip
    session.query.side_effect = lambda m: _query_for(None)
    assert b.build(session, assets=[_asset(999)], options={}) == []


# ---------------------------------------------------------------------------
# 3. UNSUPPORTED_DB_TYPE skipped path
# ---------------------------------------------------------------------------

def test_build_oracle_returns_unsupported_skipped():
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=200, port=1521, instance_name="ora-prod")
    srv = _make_server(server_id=2, ip="10.0.0.20")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    items = b.build(session, assets=[_asset(200)], options={})
    assert len(items) == 1
    it = items[0]
    assert it["check_code"] == "DB_SCHEMA_METADATA_COLLECTION"
    assert it["executor_type"] == "db_sql_readonly"
    assert it["business_domain"] == "ai_schema"
    assert it["status"] == "skipped"
    assert it["result_message"] == "UNSUPPORTED_DB_TYPE"
    assert it["raw_result"]["skip_reason"] == "UNSUPPORTED_DB_TYPE"
    assert it["raw_result"]["skip_code"] == "UNSUPPORTED_DB_TYPE"
    assert it["db_type_code"] == "oracle"


def test_build_mssql_returns_unsupported_skipped():
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=201, port=1433, instance_name="mssql-prod")
    srv = _make_server(server_id=3, ip="10.0.0.21")
    dbtype = _make_dbtype(type_code="mssql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    items = b.build(session, assets=[_asset(201)], options={})
    assert len(items) == 1
    assert items[0]["result_message"] == "UNSUPPORTED_DB_TYPE"
    assert items[0]["db_type_code"] == "mssql"


def test_build_postgres_alias_supported():
    """db_type.type_code='postgres' (alias) is also accepted (plan §4.4 wording)."""
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=202, port=5432)
    srv = _make_server(server_id=4, ip="10.0.0.22")
    dbtype = _make_dbtype(type_code="postgres")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(202)], options={})
    assert len(items) == 1
    assert "rule_config" in items[0]
    assert items[0]["db_type_code"] == "postgres"


# ---------------------------------------------------------------------------
# 4. CREDENTIAL_MISSING skipped path
# ---------------------------------------------------------------------------

def test_build_postgresql_no_credential_returns_skipped():
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=300)
    srv = _make_server(server_id=5, ip="10.0.0.30")
    dbtype = _make_dbtype(type_code="postgresql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=None,
    ):
        items = b.build(session, assets=[_asset(300)], options={})
    assert len(items) == 1
    it = items[0]
    assert it["status"] == "skipped"
    assert it["result_message"] == "CREDENTIAL_MISSING"
    assert it["raw_result"]["skip_code"] == "CREDENTIAL_MISSING"
    assert "rule_config" not in it


# ---------------------------------------------------------------------------
# 5. Happy path: postgresql + credential resolved
# ---------------------------------------------------------------------------

def test_build_postgresql_with_credential_returns_normal_item():
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=400, port=5432, instance_name="pg-prod-02")
    srv = _make_server(server_id=6, ip="10.0.0.40")
    dbtype = _make_dbtype(type_code="postgresql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(
            session,
            assets=[_asset(400)],
            options={"timeout_seconds": 45},
        )
    assert len(items) == 1
    it = items[0]

    # item_key format
    assert it["item_key"] == "db_instance:400:DB_SCHEMA_METADATA_COLLECTION:10.0.0.40:5432"

    # core routing fields
    assert it["check_code"] == "DB_SCHEMA_METADATA_COLLECTION"
    assert it["executor_type"] == "db_sql_readonly"
    assert it["business_domain"] == "ai_schema"
    assert it["target_scope"] == "db_instance"

    # ids
    assert it["db_instance_id"] == 400
    assert it["server_id"] == 6
    assert it["asset_id"] == 400

    # network
    assert it["target_host"] == "10.0.0.40"
    assert it["target_port"] == 5432
    assert it["protocol"] == "tcp"
    assert it["endpoint_type"] == "DB_SERVICE_PORT"
    assert it["port_source"] == "db_instance_port"
    assert it["is_required"] is True

    # db-specific
    assert it["db_type_code"] == "postgresql"
    assert it["database_name"] == "postgres"  # default for postgresql
    assert it["asset_name"] == "pg-prod-02"
    assert it["service_name"] == ""
    assert it["timeout_seconds"] == 45  # from options

    # rule_config — SQL template inline + 完整性限制
    rc = it["rule_config"]
    assert "sql_text" in rc and rc["sql_text"], "SQL text must be inlined"
    assert "information_schema.columns" in rc["sql_text"]
    assert rc["max_rows"] == 20000
    assert rc["max_bytes"] == 10485760
    assert rc["timeout_seconds"] == 45
    assert rc["source"] == "dbops.ai.sql_templates.postgresql.pg_schema_columns"
    assert rc["phase"] == "3.6B0"

    # credential fields (5 fields)
    assert it["credential_profile_id"] == 7
    assert it["credential_code"] == "cred-db-pg-ro-prod"
    assert it["awx_credential_id"] == 12
    assert it["credential_role"] == "db_readonly"
    assert it["credential_type"] == "db"

    # Must NOT carry skipped markers
    assert "status" not in it
    assert "result_message" not in it


def test_build_postgresql_default_timeout_30s():
    """When options does not specify timeout_seconds, default = 30."""
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=401, port=5432)
    srv = _make_server(server_id=7, ip="10.0.0.41")
    dbtype = _make_dbtype(type_code="postgresql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(401)], options={})
    assert items[0]["timeout_seconds"] == 30
    assert items[0]["rule_config"]["timeout_seconds"] == 30


# ---------------------------------------------------------------------------
# 6. Mixed batch: 1 pg + 1 oracle + 1 no-credential → 1 normal + 2 skipped
# ---------------------------------------------------------------------------

def test_build_mixed_assets_returns_mixed_items():
    """Each asset is processed independently; mixed outcomes are allowed."""
    b = _AiSchemaMetadataBuilder()

    pg_inst = _make_instance(instance_id=500, port=5432, instance_name="pg-prod-03")
    pg_srv = _make_server(server_id=10, ip="10.0.0.50")
    pg_dbt = _make_dbtype(type_code="postgresql")

    ora_inst = _make_instance(instance_id=501, port=1521, instance_name="ora-prod-03")
    ora_srv = _make_server(server_id=11, ip="10.0.0.51")
    ora_dbt = _make_dbtype(type_code="oracle")

    nopg_inst = _make_instance(instance_id=502, port=5432, instance_name="pg-no-cred")
    nopg_srv = _make_server(server_id=12, ip="10.0.0.52")
    nopg_dbt = _make_dbtype(type_code="postgresql")

    pool = [
        (pg_inst, pg_srv, pg_dbt),  # asset 500
        (ora_inst, ora_srv, ora_dbt),  # asset 501
        (nopg_inst, nopg_srv, nopg_dbt),  # asset 502
    ]
    call_index = {"i": 0}

    def query_side(model):
        idx = call_index["i"]
        call_index["i"] = idx + 1
        trio = pool[idx // 3]
        local = idx % 3
        return _query_for(trio[local])

    session = MagicMock()
    session.query.side_effect = query_side

    cred_calls = {"n": 0}

    def cred_resolver(db, **kwargs):
        cred_calls["n"] += 1
        if cred_calls["n"] == 1:  # only asset 500 has credential
            return _make_credential()
        return None

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        side_effect=cred_resolver,
    ):
        items = b.build(
            session,
            assets=[_asset(500), _asset(501), _asset(502)],
            options={},
        )

    assert len(items) == 3
    by_id = {it["db_instance_id"]: it for it in items}

    it500 = by_id[500]
    assert "rule_config" in it500
    assert it500["check_code"] == "DB_SCHEMA_METADATA_COLLECTION"
    assert it500["business_domain"] == "ai_schema"

    it501 = by_id[501]
    assert it501["status"] == "skipped"
    assert it501["result_message"] == "UNSUPPORTED_DB_TYPE"

    it502 = by_id[502]
    assert it502["status"] == "skipped"
    assert it502["result_message"] == "CREDENTIAL_MISSING"
    assert "rule_config" not in it502


# ---------------------------------------------------------------------------
# 7. SQL template inline idempotency (C7 invariant)
# ---------------------------------------------------------------------------

def test_inline_sql_matches_disk_template():
    """rule_config.sql_text must equal the on-disk template (byte-for-byte after strip)."""
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=600, port=5432)
    srv = _make_server(server_id=20, ip="10.0.0.60")
    dbtype = _make_dbtype(type_code="postgresql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(600)], options={})

    disk_sql = _AiSchemaMetadataBuilder._load_sql_template()
    assert items[0]["rule_config"]["sql_text"] == disk_sql


# ---------------------------------------------------------------------------
# 8. _default_database helper
# ---------------------------------------------------------------------------

def test_default_database_helper():
    assert _AiSchemaMetadataBuilder._default_database("postgresql") == "postgres"
    assert _AiSchemaMetadataBuilder._default_database("postgres") == "postgres"
    assert _AiSchemaMetadataBuilder._default_database("mssql") == "master"
    assert _AiSchemaMetadataBuilder._default_database("oracle", "ORCL") == "ORCL"
    assert _AiSchemaMetadataBuilder._default_database("mysql") == "mysql"
    assert _AiSchemaMetadataBuilder._default_database("") == "master"
    assert _AiSchemaMetadataBuilder._default_database("unknown") == "master"