"""
Phase 3.6B0 C8 + C16-F0 — _AiSchemaMetadataBuilder 单元测试

覆盖 (plan §13 Schema Snapshot 矩阵的 builder 部分):

  PG (C8 原版):
   1. Builder 已注册到 CheckItemBuilderRegistry
   2. Class attrs: check_code / supported db types / max limits
   3. SQL 模板 inline 到 rule_config.sql_text (C7 单源)
   4. build() 空 assets / 非 db_instance scope / instance 不存在 → 空列表
   5. build() 不支持 db_type (mysql) → UNSUPPORTED_DB_TYPE skipped
   6. build() 缺凭证 → CREDENTIAL_MISSING skipped
   7. build() postgresql + 凭证齐全 → 正常 item
      - item_key 格式正确
      - check_code / executor_type=db_sql_readonly / business_domain=ai_schema
      - db_instance_id / server_id / target_host / target_port
      - database_name='postgres'
      - rule_config.sql_text 含 information_schema.columns
      - rule_config.max_rows=20000, max_bytes=10MB
      - rule_config.source / phase 标识
      - 5 个 credential_* 字段

  Oracle / SQL Server (C16-F0 三方言合并):
   8.  Oracle 正常 item（rule_config.sql_text 含 ALL_TAB_COLUMNS / source=oracle/...）
   9.  Oracle sqlserver alias 同义
  10.  Oracle UNSUPPORTED 不再触发（service_name → ORCL）
  11.  SQL Server 正常 item（rule_config.sql_text 含 sys.columns / source=mssql/...）
  12.  SQL Server sqlserver alias 同义
  13.  SQL Server UNSUPPORTED 不再触发（database_name → master）
  14.  三方言 _load_sql_template(db_type_code) 均返回非空只读 SELECT
  15.  _SQL_TEMPLATE_MAP 含 5 个 key（postgres + oracle + mssql + sqlserver alias）
  16.  _load_sql_template 未知 db_type 抛 ValueError

  通用:
  17. 多实例混合: 1 pg + 1 oracle + 1 mssql + 1 no-cred → 3 normal + 1 skipped
  18. inline SQL 与磁盘模板字节级一致（3 方言）
  19. _default_database 边界（5 个 db_type + 空 + 未知）

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
    # C16-F0 三方言: postgresql/postgres + oracle + mssql/sqlserver
    assert b._SUPPORTED_DB_TYPES == frozenset({
        "postgresql", "postgres", "oracle", "mssql", "sqlserver",
    })
    # Commit 8: _MAX_ROWS lowered 20000 → 1000 (EE pydantic DbReadonlySqlRuleConfig
    # le=1000 hard cap; 20000 caused EE to reject rule_config with 422).
    assert b._MAX_ROWS == 1000
    assert b._MAX_BYTES == 10485760
    assert issubclass(_AiSchemaMetadataBuilder, BaseCheckItemBuilder)


def test_sql_template_map_has_all_dialects():
    """C16-F0 三方言映射: 5 个 key（postgres 是 postgresql 别名）"""
    m = _AiSchemaMetadataBuilder._SQL_TEMPLATE_MAP
    assert set(m.keys()) == {"postgresql", "postgres", "oracle", "mssql", "sqlserver"}
    # PG / Oracle / MSSQL 各指向自己的 SQL 文件
    assert m["postgresql"] == ("postgresql", "pg_schema_columns.sql")
    assert m["postgres"]   == ("postgresql", "pg_schema_columns.sql")
    assert m["oracle"]     == ("oracle",     "ora_schema_columns.sql")
    assert m["mssql"]      == ("mssql",      "mssql_schema_columns.sql")
    assert m["sqlserver"]  == ("mssql",      "mssql_schema_columns.sql")


# ---------------------------------------------------------------------------
# 2. _load_sql_template() dispatch (C16-F0 三方言核心)
# ---------------------------------------------------------------------------

def test_load_sql_template_postgresql():
    sql, source = _AiSchemaMetadataBuilder._load_sql_template("postgresql")
    assert sql, "SQL template must not be empty"
    assert source == "dbops.ai.sql_templates.postgresql.pg_schema_columns"
    assert "information_schema.columns" in sql
    assert "ordinal_position" in sql
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT"), (
        f"PG SQL body must start with SELECT, got: {body[:80]!r}"
    )


def test_load_sql_template_oracle():
    sql, source = _AiSchemaMetadataBuilder._load_sql_template("oracle")
    assert sql
    assert source == "dbops.ai.sql_templates.oracle.ora_schema_columns"
    assert "all_tab_columns" in sql.lower()
    assert "ordinal_position" in sql  # column_name alias
    assert "table_schema" in sql
    assert "is_nullable" in sql
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT")


def test_load_sql_template_mssql():
    sql, source = _AiSchemaMetadataBuilder._load_sql_template("mssql")
    assert sql
    assert source == "dbops.ai.sql_templates.mssql.mssql_schema_columns"
    assert "sys.columns" in sql.lower()
    assert "ordinal_position" in sql
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT")


def test_load_sql_template_unknown_raises():
    with pytest.raises(ValueError, match="unsupported db_type_code"):
        _AiSchemaMetadataBuilder._load_sql_template("unknown_db")


def test_load_sql_template_postgres_alias_same_as_postgresql():
    sql_pg, src_pg = _AiSchemaMetadataBuilder._load_sql_template("postgresql")
    sql_alias, src_alias = _AiSchemaMetadataBuilder._load_sql_template("postgres")
    assert sql_pg == sql_alias
    assert src_pg == src_alias


def test_load_sql_template_sqlserver_alias_same_as_mssql():
    sql_ms, src_ms = _AiSchemaMetadataBuilder._load_sql_template("mssql")
    sql_alias, src_alias = _AiSchemaMetadataBuilder._load_sql_template("sqlserver")
    assert sql_ms == sql_alias
    assert src_ms == src_alias


def test_load_sql_template_three_dialects_distinct():
    """3 方言 SQL 模板互不相同（不串模板）"""
    sql_pg, _ = _AiSchemaMetadataBuilder._load_sql_template("postgresql")
    sql_ora, _ = _AiSchemaMetadataBuilder._load_sql_template("oracle")
    sql_ms, _ = _AiSchemaMetadataBuilder._load_sql_template("mssql")
    assert sql_pg != sql_ora != sql_ms
    assert sql_pg != sql_ms


# ---------------------------------------------------------------------------
# 3. build() input filtering (no DB hit / wrong scope / missing instance)
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
    session.query.side_effect = lambda m: _query_for(None)
    assert b.build(session, assets=[_asset(999)], options={}) == []


# ---------------------------------------------------------------------------
# 4. UNSUPPORTED_DB_TYPE skipped path (C16-F0: 仅 mysql + unknown)
# ---------------------------------------------------------------------------

def test_build_mysql_returns_unsupported_skipped():
    """C16-F0: mysql 不在 _SUPPORTED_DB_TYPES → skipped (PG/Oracle/MSSQL 均支持)"""
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=200, port=3306, instance_name="mysql-prod")
    srv = _make_server(server_id=2, ip="10.0.0.20")
    dbtype = _make_dbtype(type_code="mysql")
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
    assert it["db_type_code"] == "mysql"


def test_build_unknown_dbtype_returns_unsupported_skipped():
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=203, port=1234)
    srv = _make_server(server_id=23, ip="10.0.0.23")
    dbtype = _make_dbtype(type_code="sqlite")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    items = b.build(session, assets=[_asset(203)], options={})
    assert items[0]["result_message"] == "UNSUPPORTED_DB_TYPE"


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
# 5. CREDENTIAL_MISSING skipped path
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


def test_build_oracle_no_credential_returns_skipped():
    """Oracle 没有凭证 → CREDENTIAL_MISSING（不再是 UNSUPPORTED_DB_TYPE）"""
    b = _AiSchemaMetadataBuilder()
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
    b = _AiSchemaMetadataBuilder()
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
# 6. Happy path: postgresql + credential resolved (C8 保留)
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

    assert it["item_key"] == "db_instance:400:DB_SCHEMA_METADATA_COLLECTION:10.0.0.40:5432"
    assert it["check_code"] == "DB_SCHEMA_METADATA_COLLECTION"
    assert it["executor_type"] == "db_sql_readonly"
    assert it["business_domain"] == "ai_schema"
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
    assert "information_schema.columns" in rc["sql_text"]
    assert rc["max_rows"] == 1000
    assert rc["max_bytes"] == 10485760
    assert rc["timeout_seconds"] == 45
    assert rc["source"] == "dbops.ai.sql_templates.postgresql.pg_schema_columns"
    assert rc["phase"] == "3.6B0"

    assert it["credential_profile_id"] == 7
    assert it["credential_code"] == "cred-db-pg-ro-prod"
    assert it["awx_credential_id"] == 12
    assert it["credential_role"] == "db_readonly"
    assert it["credential_type"] == "db"

    assert "status" not in it
    assert "result_message" not in it


def test_build_postgresql_default_timeout_30s():
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
# 7. Happy path: Oracle (C16-F0 三方言合并新增)
# ---------------------------------------------------------------------------

def test_build_oracle_with_credential_returns_normal_item():
    b = _AiSchemaMetadataBuilder()
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

    assert it["item_key"] == "db_instance:600:DB_SCHEMA_METADATA_COLLECTION:10.0.0.60:1521"
    assert it["check_code"] == "DB_SCHEMA_METADATA_COLLECTION"
    assert it["db_type_code"] == "oracle"
    assert it["database_name"] == "ORCL"  # service_name 决定
    assert it["service_name"] == "ORCL"
    assert it["target_port"] == 1521

    rc = it["rule_config"]
    assert rc["source"] == "dbops.ai.sql_templates.oracle.ora_schema_columns"
    assert rc["phase"] == "3.6B0"
    assert rc["timeout_seconds"] == 45
    assert "all_tab_columns" in rc["sql_text"].lower()
    assert "ordinal_position" in rc["sql_text"]

    assert "status" not in it
    assert "result_message" not in it


def test_build_oracle_no_service_name_uses_empty_db():
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=601, port=1521, service_name="")
    srv = _make_server(server_id=61, ip="10.0.0.61")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(601)], options={})
    # service_name 空时 _default_database 返回 ""
    assert items[0]["database_name"] == ""


def test_build_oracle_sqlserver_alias_works():
    """'sqlserver' alias 不适用于 oracle, 但 'oracle' 字面 → 同 'oracle' 模板"""
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=602, port=1521, service_name="ORCL2")
    srv = _make_server(server_id=62, ip="10.0.0.62")
    dbtype = _make_dbtype(type_code="oracle")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(602)], options={})
    assert items[0]["db_type_code"] == "oracle"
    assert "all_tab_columns" in items[0]["rule_config"]["sql_text"].lower()


# ---------------------------------------------------------------------------
# 8. Happy path: SQL Server (C16-F0 三方言合并新增)
# ---------------------------------------------------------------------------

def test_build_mssql_with_credential_returns_normal_item():
    b = _AiSchemaMetadataBuilder()
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

    assert it["item_key"] == "db_instance:700:DB_SCHEMA_METADATA_COLLECTION:10.0.0.70:1433"
    assert it["check_code"] == "DB_SCHEMA_METADATA_COLLECTION"
    assert it["db_type_code"] == "mssql"
    assert it["database_name"] == "master"  # _default_database default for mssql
    assert it["target_port"] == 1433

    rc = it["rule_config"]
    assert rc["source"] == "dbops.ai.sql_templates.mssql.mssql_schema_columns"
    assert rc["phase"] == "3.6B0"
    assert rc["timeout_seconds"] == 50
    assert "sys.columns" in rc["sql_text"].lower()
    assert "ordinal_position" in rc["sql_text"]

    assert "status" not in it
    assert "result_message" not in it


def test_build_mssql_sqlserver_alias_supported():
    """'sqlserver' 是 mssql 的别名字面（同 _SQL_TEMPLATE_MAP）"""
    b = _AiSchemaMetadataBuilder()
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
    # rule_config.source 仍指向 mssql 子目录（与 _SQL_TEMPLATE_MAP 一致）
    assert it["rule_config"]["source"] == "dbops.ai.sql_templates.mssql.mssql_schema_columns"


def test_build_mssql_database_name_overrides_default():
    """database_name 不允许 None；mssql 默认 master 来自 _default_database"""
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=702, port=1433)
    srv = _make_server(server_id=72, ip="10.0.0.72")
    dbtype = _make_dbtype(type_code="mssql")
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(702)], options={})
    assert items[0]["database_name"] == "master"


# ---------------------------------------------------------------------------
# 9. SQL 模板只读 + 字段名（防御性回归）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_type_code, expected_source_substr", [
    ("postgresql", "dbops.ai.sql_templates.postgresql.pg_schema_columns"),
    ("postgres",   "dbops.ai.sql_templates.postgresql.pg_schema_columns"),
    ("oracle",     "dbops.ai.sql_templates.oracle.ora_schema_columns"),
    ("mssql",      "dbops.ai.sql_templates.mssql.mssql_schema_columns"),
    ("sqlserver",  "dbops.ai.sql_templates.mssql.mssql_schema_columns"),
])
def test_load_sql_template_all_dialects_parametrized(db_type_code, expected_source_substr):
    """5 个 db_type_code 都返回合法 (sql, source) 元组, source 包含正确子目录"""
    sql, source = _AiSchemaMetadataBuilder._load_sql_template(db_type_code)
    assert sql
    assert source == expected_source_substr
    body = "\n".join(ln for ln in sql.splitlines()
                     if ln.strip() and not ln.strip().startswith("--"))
    assert body.lstrip().upper().startswith("SELECT"), (
        f"{db_type_code} SQL body must start with SELECT, got: {body[:80]!r}"
    )


@pytest.mark.parametrize("db_type_code, expected_marker", [
    ("postgresql", "information_schema.columns"),
    ("oracle",     "all_tab_columns"),
    ("mssql",      "sys.columns"),
])
def test_load_sql_template_contains_dialect_marker(db_type_code, expected_marker):
    """每个方言 SQL 模板含该方言特征表名"""
    sql, _ = _AiSchemaMetadataBuilder._load_sql_template(db_type_code)
    assert expected_marker in sql.lower(), (
        f"{db_type_code} SQL must contain '{expected_marker}'"
    )


# ---------------------------------------------------------------------------
# 10. Mixed batch: PG + Oracle + MSSQL + no-cred → 3 normal + 1 skipped (C16-F0)
# ---------------------------------------------------------------------------

def test_build_mixed_assets_returns_mixed_items():
    """C16-F0: 1 pg + 1 oracle + 1 mssql + 1 no-cred → 3 normal + 1 skipped"""
    b = _AiSchemaMetadataBuilder()

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
        (pg_inst, pg_srv, pg_dbt),    # asset 500 - PG ok
        (ora_inst, ora_srv, ora_dbt), # asset 501 - Oracle ok
        (nopg_inst, nopg_srv, nopg_dbt), # asset 502 - PG no cred
        (ms_inst, ms_srv, ms_dbt),    # asset 503 - MSSQL ok
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
    assert it500["rule_config"]["source"].endswith("pg_schema_columns")

    it501 = by_id[501]
    assert "rule_config" in it501
    assert it501["db_type_code"] == "oracle"
    assert it501["rule_config"]["source"].endswith("ora_schema_columns")

    it502 = by_id[502]
    assert it502["status"] == "skipped"
    assert it502["result_message"] == "CREDENTIAL_MISSING"
    assert "rule_config" not in it502

    it503 = by_id[503]
    assert "rule_config" in it503
    assert it503["db_type_code"] == "mssql"
    assert it503["rule_config"]["source"].endswith("mssql_schema_columns")


# ---------------------------------------------------------------------------
# 11. inline SQL 与磁盘模板字节级一致 (3 方言)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("db_type_code", ["postgresql", "oracle", "mssql"])
def test_inline_sql_matches_disk_template(db_type_code):
    b = _AiSchemaMetadataBuilder()
    inst = _make_instance(instance_id=800, port=5432)
    srv = _make_server(server_id=80, ip="10.0.0.80")
    dbtype = _make_dbtype(type_code=db_type_code)
    session = _session_with_single_asset(instance=inst, server=srv, dbtype=dbtype)

    with patch(
        "app.services.credential_resolver_service.CredentialResolverService.resolve_for_item",
        return_value=_make_credential(),
    ):
        items = b.build(session, assets=[_asset(800)], options={})

    disk_sql, _ = _AiSchemaMetadataBuilder._load_sql_template(db_type_code)
    assert items[0]["rule_config"]["sql_text"] == disk_sql


# ---------------------------------------------------------------------------
# 12. _default_database helper
# ---------------------------------------------------------------------------

def test_default_database_helper():
    assert _AiSchemaMetadataBuilder._default_database("postgresql") == "postgres"
    assert _AiSchemaMetadataBuilder._default_database("postgres") == "postgres"
    assert _AiSchemaMetadataBuilder._default_database("mssql") == "master"
    assert _AiSchemaMetadataBuilder._default_database("sqlserver") == "master"
    assert _AiSchemaMetadataBuilder._default_database("oracle", "ORCL") == "ORCL"
    assert _AiSchemaMetadataBuilder._default_database("mysql") == "mysql"
    assert _AiSchemaMetadataBuilder._default_database("") == "master"
    assert _AiSchemaMetadataBuilder._default_database("unknown") == "master"


def test_default_database_oracle_without_service_name_returns_empty():
    """Oracle 无 service_name 时 _default_database 返回空字符串（oracle 默认 db = service_name）"""
    assert _AiSchemaMetadataBuilder._default_database("oracle", "") == ""
    assert _AiSchemaMetadataBuilder._default_database("oracle") == ""