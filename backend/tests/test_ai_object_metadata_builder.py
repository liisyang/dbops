"""
Phase 3.6B0 C16-F3 + C16-F0 — _AiObjectMetadataBuilder 单元测试

覆盖 (plan §13 Object Metadata Snapshot 矩阵的 builder 部分):

  PG (C16-F3 原版):
   1. Builder 已注册到 CheckItemBuilderRegistry (DB_OBJECT_METADATA)
   2. Class attrs: check_code / supported db types / max limits
   3. SQL 模板 inline 到 rule_config.sql_text (5 段 UNION ALL, 5 列)
   4. build() 空 assets / 非 db_instance scope / instance 不存在 → 空列表
   5. build() 不支持 db_type (mysql) → UNSUPPORTED_DB_TYPE skipped
   6. build() 缺凭证 → CREDENTIAL_MISSING skipped
   7. build() postgresql + 凭证齐全 → 正常 item
      - item_key 格式正确
      - check_code / executor_type=db_sql_readonly / business_domain=ai_object_metadata
      - db_instance_id / server_id / target_host / target_port
      - database_name='postgres'
      - rule_config.sql_text 含 pg_object_metadata UNION ALL 段
      - rule_config.max_rows=20000, max_bytes=1MB
      - rule_config.source / phase='3.6B0.F3' 标识
      - 5 个 credential_* 字段

  Oracle / SQL Server (C16-F0 三方言合并新增):
   8.  Oracle 正常 item（rule_config.sql_text 含 all_tab_columns / source=oracle/...）
   9.  Oracle 无 service_name → database_name=""
  10.  Oracle 6 UNION ALL 段（table/view/materialized_view/index/function+proc/constraint）
  11.  SQL Server 正常 item（rule_config.sql_text 含 sys.columns / source=mssql/...）
  12.  SQL Server sqlserver alias 同义
  13.  SQL Server 8 UNION ALL 段（table/view/index/function/procedure/4×constraint）
  14.  三方言 _load_sql_template(db_type_code) 均返回非空只读 SELECT
  15.  _SQL_TEMPLATE_MAP 含 5 个 key（postgres + oracle + mssql + sqlserver alias）
  16.  _load_sql_template 未知 db_type 抛 ValueError

  通用:
  17. 多实例混合: 1 pg + 1 oracle + 1 mssql + 1 no-cred → 3 normal + 1 skipped
  18. inline SQL 与磁盘模板字节级一致（3 方言）
  19. _default_database 边界（5 个 db_type + 空 + 未知）

策略:
- 纯 mock Session + CredentialResolverService (不连 DB)
- 与 test_ai_schema_metadata_builder.py 同一 fixture 风格
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
    _AiObjectMetadataBuilder,
)


# ---------------------------------------------------------------------------
# Helpers (镜像 C8 builder 测试)
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
    assert "DB_OBJECT_METADATA" in codes, (
        "Builder must be registered before C16-F3 callback can resolve it"
    )


def test_builder_class_attrs():
    b = _AiObjectMetadataBuilder()
    assert b._check_code == "DB_OBJECT_METADATA"
    # C16-F0 三方言: postgresql/postgres + oracle + mssql/sqlserver
    assert b._SUPPORTED_DB_TYPES == frozenset({
        "postgresql", "postgres", "oracle", "mssql", "sqlserver",
    })
    # Commit 8: _MAX_ROWS lowered 20000 → 1000 (EE pydantic
    # DbReadonlySqlRuleConfig le=1000 hard cap; 20000 caused EE to reject
    # rule_config with 422).
    assert b._MAX_ROWS == 1000
    # F3 独立 1MB cap（与 C8 10MB 不同）
    assert b._MAX_BYTES == 1048576
    assert issubclass(_AiObjectMetadataBuilder, BaseCheckItemBuilder)


def test_sql_template_map_has_all_dialects():
    """C16-F0 三方言映射: 5 个 key"""
    m = _AiObjectMetadataBuilder._SQL_TEMPLATE_MAP
    assert set(m.keys()) == {"postgresql", "postgres", "oracle", "mssql", "sqlserver"}
    assert m["postgresql"] == ("postgresql", "pg_object_metadata.sql")
    assert m["postgres"]   == ("postgresql", "pg_object_metadata.sql")
    assert m["oracle"]     == ("oracle",     "ora_object_metadata.sql")
    assert m["mssql"]      == ("mssql",      "mssql_object_metadata.sql")
    assert m["sqlserver"]  == ("mssql",      "mssql_object_metadata.sql")


# ---------------------------------------------------------------------------
# 2. _load_sql_template() dispatch (C16-F0 三方言核心)
# ---------------------------------------------------------------------------

def test_load_sql_template_postgresql():
    sql, source = _AiObjectMetadataBuilder._load_sql_template("postgresql")
    assert sql
    assert source == "dbops.ai.sql_templates.postgresql.pg_object_metadata"
    assert sql.count("UNION ALL") >= 4  # 5 段 → 至少 4 个 UNION ALL
    assert "pg_catalog" in sql
    assert "object_type" in sql
    assert "schema_name" in sql
    assert "object_name" in sql
    assert "ddl_text" in sql
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT")


def test_load_sql_template_oracle():
    sql, source = _AiObjectMetadataBuilder._load_sql_template("oracle")
    assert sql
    assert source == "dbops.ai.sql_templates.oracle.ora_object_metadata"
    # Oracle 6 段 UNION ALL (table/view/materialized_view/index/function+procedure/constraint)
    assert sql.count("UNION ALL") >= 5
    assert "all_tab_columns" in sql.lower()
    assert "all_views" in sql.lower()
    assert "all_constraints" in sql.lower()
    assert "object_type" in sql
    assert "schema_name" in sql
    assert "ddl_text" in sql
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT")


def test_load_sql_template_mssql():
    sql, source = _AiObjectMetadataBuilder._load_sql_template("mssql")
    assert sql
    assert source == "dbops.ai.sql_templates.mssql.mssql_object_metadata"
    # SQL Server 9 段 UNION ALL (table/view/index/function/procedure/4×constraint)
    assert sql.count("UNION ALL") >= 8
    assert "sys.columns" in sql.lower()
    assert "sys.views" in sql.lower()
    assert "object_definition" in sql.lower()
    assert "sys.check_constraints" in sql.lower()
    assert "object_type" in sql
    assert "schema_name" in sql
    assert "ddl_text" in sql
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT")


def test_load_sql_template_unknown_raises():
    with pytest.raises(ValueError, match="unsupported db_type_code"):
        _AiObjectMetadataBuilder._load_sql_template("unknown_db")


def test_load_sql_template_postgres_alias_same_as_postgresql():
    sql_pg, src_pg = _AiObjectMetadataBuilder._load_sql_template("postgresql")
    sql_alias, src_alias = _AiObjectMetadataBuilder._load_sql_template("postgres")
    assert sql_pg == sql_alias
    assert src_pg == src_alias


def test_load_sql_template_sqlserver_alias_same_as_mssql():
    sql_ms, src_ms = _AiObjectMetadataBuilder._load_sql_template("mssql")
    sql_alias, src_alias = _AiObjectMetadataBuilder._load_sql_template("sqlserver")
    assert sql_ms == sql_alias
    assert src_ms == src_alias


def test_load_sql_template_three_dialects_distinct():
    """3 方言 SQL 模板互不相同（不串模板）"""
    sql_pg, _ = _AiObjectMetadataBuilder._load_sql_template("postgresql")
    sql_ora, _ = _AiObjectMetadataBuilder._load_sql_template("oracle")
    sql_ms, _ = _AiObjectMetadataBuilder._load_sql_template("mssql")
    assert sql_pg != sql_ora != sql_ms
    assert sql_pg != sql_ms


# ---------------------------------------------------------------------------
# 3. build() input filtering (no DB hit / wrong scope / missing instance)
# ---------------------------------------------------------------------------

def test_build_empty_assets_returns_empty():
    b = _AiObjectMetadataBuilder()
    session = MagicMock()
    assert b.build(session, assets=[], options={}) == []
    session.query.assert_not_called()


def test_build_wrong_scope_skipped():
    b = _AiObjectMetadataBuilder()
    session = MagicMock()
    assets = [{"id": 1, "target_scope": "server"}]
    assert b.build(session, assets=assets, options={}) == []
    session.query.assert_not_called()


def test_build_instance_not_found_returns_empty():
    b = _AiObjectMetadataBuilder()
    session = MagicMock()
    session.query.side_effect = lambda m: _query_for(None)
    assert b.build(session, assets=[_asset(999)], options={}) == []


# ---------------------------------------------------------------------------
# 4. UNSUPPORTED_DB_TYPE skipped path (C16-F0: 仅 mysql + unknown)
# ---------------------------------------------------------------------------

def test_build_mysql_returns_unsupported_skipped():
    """C16-F0: mysql 不在 _SUPPORTED_DB_TYPES → skipped (PG/Oracle/MSSQL 均支持)"""
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=200, port=3306, instance_name="mysql-prod")
    srv = _make_server(server_id=2, ip="10.0.0.20")
    dbtype = _make_dbtype(type_code="mysql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    items = b.build(session, assets=[_asset(200)], options={})
    assert len(items) == 1
    it = items[0]
    assert it["check_code"] == "DB_OBJECT_METADATA"
    assert it["executor_type"] == "db_sql_readonly"
    # F3 关键：business_domain 独立于 ai_schema
    assert it["business_domain"] == "ai_object_metadata"
    assert it["status"] == "skipped"
    assert it["result_message"] == "UNSUPPORTED_DB_TYPE"
    assert it["raw_result"]["skip_reason"] == "UNSUPPORTED_DB_TYPE"
    assert it["raw_result"]["skip_code"] == "UNSUPPORTED_DB_TYPE"
    assert it["db_type_code"] == "mysql"


def test_build_unknown_dbtype_returns_unsupported_skipped():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=203, port=1234)
    srv = _make_server(server_id=23, ip="10.0.0.23")
    dbtype = _make_dbtype(type_code="sqlite")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    items = b.build(session, assets=[_asset(203)], options={})
    assert items[0]["result_message"] == "UNSUPPORTED_DB_TYPE"


def test_build_postgres_alias_supported():
    """db_type.type_code='postgres' (alias) is also accepted."""
    b = _AiObjectMetadataBuilder()
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
# 5. CREDENTIAL_MISSING skipped path
# ---------------------------------------------------------------------------

def test_build_postgresql_no_credential_returns_skipped():
    b = _AiObjectMetadataBuilder()
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


def test_build_oracle_no_credential_returns_skipped():
    """Oracle 没有凭证 → CREDENTIAL_MISSING（不再是 UNSUPPORTED_DB_TYPE）"""
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=301, port=1521, service_name="ORCL")
    srv = _make_server(server_id=51, ip="10.0.0.51")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=None,
    ):
        items = b.build(session, assets=[_asset(301)], options={})
    assert items[0]["result_message"] == "CREDENTIAL_MISSING"


def test_build_mssql_no_credential_returns_skipped():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=302, port=1433)
    srv = _make_server(server_id=52, ip="10.0.0.52")
    dbtype = _make_dbtype(type_code="mssql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=None,
    ):
        items = b.build(session, assets=[_asset(302)], options={})
    assert items[0]["result_message"] == "CREDENTIAL_MISSING"


# ---------------------------------------------------------------------------
# 6. Happy path: postgresql + credential resolved
# ---------------------------------------------------------------------------

def test_build_postgresql_with_credential_returns_normal_item():
    b = _AiObjectMetadataBuilder()
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

    assert it["item_key"] == "db_instance:400:DB_OBJECT_METADATA:10.0.0.40:5432"
    assert it["check_code"] == "DB_OBJECT_METADATA"
    assert it["executor_type"] == "db_sql_readonly"
    assert it["business_domain"] == "ai_object_metadata"
    assert it["target_scope"] == "db_instance"
    assert it["db_instance_id"] == 400
    assert it["server_id"] == 6
    assert it["asset_id"] == 400
    assert it["target_host"] == "10.0.0.40"
    assert it["target_port"] == 5432
    assert it["protocol"] == "tcp"
    assert it["endpoint_type"] == "DB_SERVICE_PORT"
    assert it["port_source"] == "db_instance_port"
    assert it["is_required"] is True
    assert it["db_type_code"] == "postgresql"
    assert it["database_name"] == "postgres"
    assert it["asset_name"] == "pg-prod-02"
    assert it["service_name"] == ""
    assert it["timeout_seconds"] == 45

    rc = it["rule_config"]
    assert "sql_text" in rc and rc["sql_text"]
    assert rc["sql_text"].count("UNION ALL") >= 4
    # Commit 8: builder.default max_rows=1000 (see _MAX_ROWS rationale above).
    assert rc["max_rows"] == 1000
    assert rc["max_bytes"] == 1048576
    assert rc["timeout_seconds"] == 45
    assert rc["source"] == "dbops.ai.sql_templates.postgresql.pg_object_metadata"
    assert rc["phase"] == "3.6B0.F3"

    assert it["credential_profile_id"] == 7
    assert it["credential_code"] == "cred-db-pg-ro-prod"
    assert it["awx_credential_id"] == 12
    assert it["credential_role"] == "db_readonly"
    assert it["credential_type"] == "db"

    assert "status" not in it
    assert "result_message" not in it


def test_build_postgresql_default_timeout_30s():
    b = _AiObjectMetadataBuilder()
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
# 7. Happy path: Oracle (C16-F0 三方言合并新增)
# ---------------------------------------------------------------------------

def test_build_oracle_with_credential_returns_normal_item():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=600, port=1521, instance_name="ora-prod",
                          service_name="ORCL")
    srv = _make_server(server_id=60, ip="10.0.0.60")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(
            session,
            assets=[_asset(600)],
            options={"timeout_seconds": 45},
        )
    assert len(items) == 1
    it = items[0]

    assert it["item_key"] == "db_instance:600:DB_OBJECT_METADATA:10.0.0.60:1521"
    assert it["check_code"] == "DB_OBJECT_METADATA"
    assert it["business_domain"] == "ai_object_metadata"
    assert it["db_type_code"] == "oracle"
    assert it["database_name"] == "ORCL"
    assert it["service_name"] == "ORCL"
    assert it["target_port"] == 1521

    rc = it["rule_config"]
    assert rc["source"] == "dbops.ai.sql_templates.oracle.ora_object_metadata"
    assert rc["phase"] == "3.6B0.F3"
    assert rc["timeout_seconds"] == 45
    assert "all_tab_columns" in rc["sql_text"].lower()
    assert rc["max_bytes"] == 1048576  # F3 1MB cap 不变

    assert "status" not in it
    assert "result_message" not in it


def test_build_oracle_no_service_name_uses_empty_db():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=601, port=1521, service_name="")
    srv = _make_server(server_id=61, ip="10.0.0.61")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(601)], options={})
    assert items[0]["database_name"] == ""


def test_build_oracle_rule_config_contains_union_all():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=602, port=1521, service_name="ORCL2")
    srv = _make_server(server_id=62, ip="10.0.0.62")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(602)], options={})
    rc = items[0]["rule_config"]
    # Oracle 6 段 UNION ALL
    assert rc["sql_text"].count("UNION ALL") >= 5


def test_build_oracle_credential_fields_complete():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=603, port=1521, service_name="ORCL3")
    srv = _make_server(server_id=63, ip="10.0.0.63")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(603)], options={})
    it = items[0]
    assert it["credential_profile_id"] == 7
    assert it["credential_code"] == "cred-db-pg-ro-prod"
    assert it["awx_credential_id"] == 12
    assert it["credential_role"] == "db_readonly"
    assert it["credential_type"] == "db"


# ---------------------------------------------------------------------------
# 8. Happy path: SQL Server (C16-F0 三方言合并新增)
# ---------------------------------------------------------------------------

def test_build_mssql_with_credential_returns_normal_item():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=700, port=1433, instance_name="mssql-prod")
    srv = _make_server(server_id=70, ip="10.0.0.70")
    dbtype = _make_dbtype(type_code="mssql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(
            session,
            assets=[_asset(700)],
            options={"timeout_seconds": 50},
        )
    assert len(items) == 1
    it = items[0]

    assert it["item_key"] == "db_instance:700:DB_OBJECT_METADATA:10.0.0.70:1433"
    assert it["check_code"] == "DB_OBJECT_METADATA"
    assert it["business_domain"] == "ai_object_metadata"
    assert it["db_type_code"] == "mssql"
    assert it["database_name"] == "master"
    assert it["target_port"] == 1433

    rc = it["rule_config"]
    assert rc["source"] == "dbops.ai.sql_templates.mssql.mssql_object_metadata"
    assert rc["phase"] == "3.6B0.F3"
    assert rc["timeout_seconds"] == 50
    assert "sys.columns" in rc["sql_text"].lower()
    assert rc["max_bytes"] == 1048576

    assert "status" not in it
    assert "result_message" not in it


def test_build_mssql_sqlserver_alias_supported():
    """'sqlserver' 是 mssql 的别名字面"""
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=701, port=1433)
    srv = _make_server(server_id=71, ip="10.0.0.71")
    dbtype = _make_dbtype(type_code="sqlserver")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(701)], options={})
    it = items[0]
    assert it["db_type_code"] == "sqlserver"
    assert it["database_name"] == "master"
    assert it["rule_config"]["source"] == "dbops.ai.sql_templates.mssql.mssql_object_metadata"


def test_build_mssql_rule_config_contains_union_all():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=702, port=1433)
    srv = _make_server(server_id=72, ip="10.0.0.72")
    dbtype = _make_dbtype(type_code="mssql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(702)], options={})
    rc = items[0]["rule_config"]
    # SQL Server 9 段 UNION ALL (含 4 子类约束)
    assert rc["sql_text"].count("UNION ALL") >= 8


def test_build_mssql_credential_fields_complete():
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=703, port=1433)
    srv = _make_server(server_id=73, ip="10.0.0.73")
    dbtype = _make_dbtype(type_code="mssql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(703)], options={})
    it = items[0]
    assert it["credential_profile_id"] == 7
    assert it["credential_code"] == "cred-db-pg-ro-prod"
    assert it["awx_credential_id"] == 12
    assert it["credential_role"] == "db_readonly"
    assert it["credential_type"] == "db"


# ---------------------------------------------------------------------------
# 9. SQL 模板只读 + 字段名（防御性回归）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_type_code, expected_source_substr", [
    ("postgresql", "dbops.ai.sql_templates.postgresql.pg_object_metadata"),
    ("postgres",   "dbops.ai.sql_templates.postgresql.pg_object_metadata"),
    ("oracle",     "dbops.ai.sql_templates.oracle.ora_object_metadata"),
    ("mssql",      "dbops.ai.sql_templates.mssql.mssql_object_metadata"),
    ("sqlserver",  "dbops.ai.sql_templates.mssql.mssql_object_metadata"),
])
def test_load_sql_template_all_dialects_parametrized(db_type_code, expected_source_substr):
    sql, source = _AiObjectMetadataBuilder._load_sql_template(db_type_code)
    assert sql
    assert source == expected_source_substr
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT")


@pytest.mark.parametrize("db_type_code, expected_marker", [
    ("postgresql", "pg_catalog"),
    ("oracle",     "all_tab_columns"),
    ("mssql",      "sys.columns"),
])
def test_load_sql_template_contains_dialect_marker(db_type_code, expected_marker):
    sql, _ = _AiObjectMetadataBuilder._load_sql_template(db_type_code)
    assert expected_marker in sql.lower(), (
        f"{db_type_code} SQL must contain '{expected_marker}'"
    )


# ---------------------------------------------------------------------------
# 10. Mixed batch: PG + Oracle + MSSQL + no-cred → 3 normal + 1 skipped (C16-F0)
# ---------------------------------------------------------------------------

def test_build_mixed_assets_returns_mixed_items():
    """C16-F0: 1 pg + 1 oracle + 1 mssql + 1 no-cred → 3 normal + 1 skipped"""
    b = _AiObjectMetadataBuilder()

    pg_inst = _make_instance(instance_id=500, port=5432, instance_name="pg-prod-03")
    pg_srv = _make_server(server_id=10, ip="10.0.0.50")
    pg_dbt = _make_dbtype(type_code="postgresql")

    ora_inst = _make_instance(instance_id=501, port=1521, instance_name="ora-prod-03",
                              service_name="ORCL")
    ora_srv = _make_server(server_id=11, ip="10.0.0.51")
    ora_dbt = _make_dbtype(type_code="oracle")

    ms_inst = _make_instance(instance_id=503, port=1433, instance_name="mssql-prod-03")
    ms_srv = _make_server(server_id=13, ip="10.0.0.53")
    ms_dbt = _make_dbtype(type_code="mssql")

    nopg_inst = _make_instance(instance_id=502, port=5432, instance_name="pg-no-cred")
    nopg_srv = _make_server(server_id=12, ip="10.0.0.52")
    nopg_dbt = _make_dbtype(type_code="postgresql")

    pool = [
        (pg_inst, pg_srv, pg_dbt),        # asset 500 - PG ok
        (ora_inst, ora_srv, ora_dbt),     # asset 501 - Oracle ok
        (nopg_inst, nopg_srv, nopg_dbt),  # asset 502 - PG no cred
        (ms_inst, ms_srv, ms_dbt),        # asset 503 - MSSQL ok
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
        if cred_calls["n"] in (1, 2, 4):  # PG, Oracle, MSSQL have cred
            return _make_credential()
        return None  # PG no-cred (3rd call)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        side_effect=cred_resolver,
    ):
        items = b.build(
            session,
            assets=[_asset(500), _asset(501), _asset(502), _asset(503)],
            options={},
        )

    assert len(items) == 4
    by_id = {it["db_instance_id"]: it for it in items}

    it500 = by_id[500]
    assert "rule_config" in it500
    assert it500["db_type_code"] == "postgresql"
    assert it500["rule_config"]["source"].endswith("pg_object_metadata")
    assert it500["rule_config"]["phase"] == "3.6B0.F3"

    it501 = by_id[501]
    assert "rule_config" in it501
    assert it501["db_type_code"] == "oracle"
    assert it501["rule_config"]["source"].endswith("ora_object_metadata")

    it502 = by_id[502]
    assert it502["status"] == "skipped"
    assert it502["result_message"] == "CREDENTIAL_MISSING"
    assert "rule_config" not in it502

    it503 = by_id[503]
    assert "rule_config" in it503
    assert it503["db_type_code"] == "mssql"
    assert it503["rule_config"]["source"].endswith("mssql_object_metadata")


# ---------------------------------------------------------------------------
# 11. inline SQL 与磁盘模板字节级一致 (3 方言)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_type_code", ["postgresql", "oracle", "mssql"])
def test_inline_sql_matches_disk_template(db_type_code):
    b = _AiObjectMetadataBuilder()
    inst = _make_instance(instance_id=800, port=5432)
    srv = _make_server(server_id=80, ip="10.0.0.80")
    dbtype = _make_dbtype(type_code=db_type_code)
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(800)], options={})

    disk_sql, _ = _AiObjectMetadataBuilder._load_sql_template(db_type_code)
    assert items[0]["rule_config"]["sql_text"] == disk_sql


# ---------------------------------------------------------------------------
# 12. _default_database helper
# ---------------------------------------------------------------------------

def test_default_database_helper():
    assert _AiObjectMetadataBuilder._default_database("postgresql") == "postgres"
    assert _AiObjectMetadataBuilder._default_database("postgres") == "postgres"
    assert _AiObjectMetadataBuilder._default_database("mssql") == "master"
    assert _AiObjectMetadataBuilder._default_database("sqlserver") == "master"
    assert _AiObjectMetadataBuilder._default_database("oracle", "ORCL") == "ORCL"
    assert _AiObjectMetadataBuilder._default_database("mysql") == "mysql"
    assert _AiObjectMetadataBuilder._default_database("") == "master"
    assert _AiObjectMetadataBuilder._default_database("unknown") == "master"


def test_default_database_oracle_without_service_name_returns_empty():
    assert _AiObjectMetadataBuilder._default_database("oracle", "") == ""
    assert _AiObjectMetadataBuilder._default_database("oracle") == ""