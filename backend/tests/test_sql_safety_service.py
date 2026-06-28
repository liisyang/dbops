"""
SqlSafetyService.validate_with_ast 单元测试（Phase 3.6 C11）

覆盖 SqlSafetyService 的 6 层 SQL 安全模型 Layer 3（sqlglot AST 权威层）：

- 方言映射（plan §5 line 579）
- 合法 SELECT（含 JOIN、CTE、子查询、函数、WHERE、GROUP BY 等常见子句）
- P1 SELECT * 拒绝（含 ``SELECT *`` 与 ``table.*``）
- 未限定列名解析：单源通过 / 多源歧义拒绝
- Schema Policy 白名单校验（allowed_tables / allowed_columns）
- denied_columns 阻断（Layer 1）
- 敏感列 pattern 警告（Layer 2）
- 防御性兜底：SELECT INTO / FOR UPDATE / 多语句 / 非 SELECT
- approved_sql_hash 稳定性（执行期 §5 P0-4 回查）
- 空输入 / 解析失败 / db_type 未知
- max_rows 上限钳制（默认 200，最大 1000）

测试总数：28 用例。
"""
from __future__ import annotations

import pytest

from app.services.sql_safety_service import SqlSafetyService


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

PG_TABLES = ["public.users", "public.orders"]
PG_COLUMNS = {
    "public.users": ["id", "name", "email", "created_at"],
    "public.orders": ["id", "user_id", "total"],
}
PG_DENIED = ["password"]


def _check(sql: str, db_type: str = "postgresql", **kwargs):
    """Convenience wrapper that returns the full validate_with_ast result."""
    kwargs.setdefault("allowed_tables", PG_TABLES)
    kwargs.setdefault("allowed_columns", PG_COLUMNS)
    kwargs.setdefault("denied_columns", PG_DENIED)
    return SqlSafetyService.validate_with_ast(sql, db_type, **kwargs)


# -----------------------------------------------------------------------------
# 1-3: empty / whitespace / multi-statement
# -----------------------------------------------------------------------------


def test_empty_sql_returns_invalid():
    """用例 1: 空 SQL 必须返回 valid=False 并有明确错误。"""
    r = _check("", db_type="postgresql")
    assert r["valid"] is False
    assert "empty SQL" in r["errors"][0]
    assert r["approved_sql"] == ""
    assert r["approved_sql_hash"] == ""
    assert r["warnings"] == []


def test_whitespace_only_sql_returns_invalid():
    """用例 2: 纯空白 SQL 必须返回 valid=False。"""
    r = _check("   \n\t  ", db_type="postgresql")
    assert r["valid"] is False
    assert "empty SQL" in r["errors"][0]


def test_multi_statement_rejected():
    """用例 3: 多语句必须拒绝（parse_one 会静默截断，所以必须用 parse）。"""
    r = _check("SELECT id FROM public.users; SELECT id FROM public.orders")
    assert r["valid"] is False
    assert any("expected exactly 1 statement" in e for e in r["errors"])


# -----------------------------------------------------------------------------
# 4-5: unparseable SQL / unsupported db_type
# -----------------------------------------------------------------------------


def test_unparseable_sql_rejected():
    """用例 4: 无法被 sqlglot 解析的 SQL 必须返回 ParseError 信息。"""
    r = _check("SELEC id FROM public.users")
    assert r["valid"] is False
    assert any("parse error" in e.lower() for e in r["errors"])


def test_unsupported_db_type_rejected():
    """用例 5: 未在 _DIALECT_MAP 中的 db_type_code 直接拒绝。"""
    r = _check("SELECT id FROM public.users", db_type="unknown_dbtype")
    assert r["valid"] is False
    assert any("unsupported db_type_code" in e for e in r["errors"])


# -----------------------------------------------------------------------------
# 6-10: dialect mapping & happy path
# -----------------------------------------------------------------------------


def test_postgres_happy_path_valid():
    """用例 6: 合法 PostgreSQL SELECT 必须 valid=True 且无 error。"""
    r = _check("SELECT id, name FROM public.users")
    assert r["valid"] is True
    assert r["errors"] == []
    assert r["approved_sql"] == "SELECT id, name FROM public.users"
    assert len(r["approved_sql_hash"]) == 64  # SHA-256 hex


def test_oracle_dialect_mapped():
    """用例 7: db_type_code='oracle' 必须映射到 sqlglot 'oracle' 方言并通过。"""
    r = _check(
        "SELECT id, name FROM schema1.users",
        db_type="oracle",
        allowed_tables=["schema1.users"],
        allowed_columns={"schema1.users": ["id", "name"]},
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_mssql_dialect_mapped():
    """用例 8: db_type_code='mssql' 必须映射到 sqlglot 'tsql' 方言并通过。"""
    r = _check(
        "SELECT id, name FROM dbo.users",
        db_type="mssql",
        allowed_tables=["dbo.users"],
        allowed_columns={"dbo.users": ["id", "name"]},
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_sqlserver_alias_maps_to_tsql():
    """用例 9: db_type_code='sqlserver' 也必须映射到 tsql（兼容写法）。"""
    r = _check(
        "SELECT id, name FROM dbo.users",
        db_type="sqlserver",
        allowed_tables=["dbo.users"],
        allowed_columns={"dbo.users": ["id", "name"]},
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_mysql_dialect_mapped():
    """用例 10: db_type_code='mysql' 必须映射到 sqlglot 'mysql' 方言并通过。"""
    r = _check(
        "SELECT id, name FROM app.users",
        db_type="mysql",
        allowed_tables=["app.users"],
        allowed_columns={"app.users": ["id", "name"]},
    )
    assert r["valid"] is True
    assert r["errors"] == []


# -----------------------------------------------------------------------------
# 11-13: P1 SELECT * / table.* / all-output-columns-explicit
# -----------------------------------------------------------------------------


def test_bare_select_star_rejected():
    """用例 11: ``SELECT *`` 必须拒绝（plan §5 P1）。"""
    r = _check("SELECT * FROM public.users")
    assert r["valid"] is False
    assert any("SELECT * / table.* is not allowed" in e for e in r["errors"])
    assert "*" in r["errors"][0]


def test_qualified_select_star_rejected():
    """用例 12: ``SELECT u.*`` 也必须拒绝。"""
    r = _check("SELECT u.* FROM public.users u")
    assert r["valid"] is False
    assert any("SELECT * / table.* is not allowed" in e for e in r["errors"])
    assert "u.*" in r["errors"][0]


def test_qualified_select_star_in_join_rejected():
    """用例 13: ``SELECT o.* FROM ... JOIN ...`` 也必须拒绝。"""
    r = _check(
        "SELECT o.* FROM public.users u JOIN public.orders o ON u.id = o.user_id"
    )
    assert r["valid"] is False
    assert any("SELECT * / table.* is not allowed" in e for e in r["errors"])


# -----------------------------------------------------------------------------
# 14-17: table whitelist
# -----------------------------------------------------------------------------


def test_disallowed_table_rejected():
    """用例 14: 不在 allowed_tables 的表必须拒绝。"""
    r = _check("SELECT id FROM public.secrets")
    assert r["valid"] is False
    assert any("not in the schema policy whitelist" in e for e in r["errors"])
    assert "public.secrets" in r["errors"][0]


def test_bare_table_name_also_accepted_in_whitelist():
    """用例 15: allowed_tables 用裸表名（不带 schema）也必须通过（容错）。"""
    r = _check(
        "SELECT id FROM users",
        db_type="postgresql",
        allowed_tables=["users"],
        allowed_columns={"users": ["id"]},
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_join_with_alias_accepted():
    """用例 16: 简单 JOIN + 别名 SELECT 必须通过。"""
    r = _check(
        "SELECT u.id, o.total FROM public.users u "
        "JOIN public.orders o ON u.id = o.user_id"
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_no_from_clause_rejected():
    """用例 17: 没有 FROM 的 SELECT 必须拒绝（无法应用白名单）。"""
    r = _check("SELECT 1")
    assert r["valid"] is False
    assert any("no FROM source" in e for e in r["errors"])


# -----------------------------------------------------------------------------
# 18-21: column whitelist & resolution
# -----------------------------------------------------------------------------


def test_disallowed_column_rejected():
    """用例 18: 不在 allowed_columns 的列必须拒绝（通过 column resolution 报错）。"""
    r = _check("SELECT id, password FROM public.users")
    assert r["valid"] is False
    # ``password`` is not in ``public.users`` whitelist, so it cannot be
    # resolved; the error path can be either "cannot be resolved" (when
    # not in any whitelist) or "not allowed for table" (when the table
    # resolves but the column does not).
    assert any(
        "cannot be resolved" in e or "not allowed for table" in e
        for e in r["errors"]
    )


def test_unqualified_column_resolves_in_single_source():
    """用例 19: 单源下未限定列名必须能唯一解析（plan §5 P1 唯一性要求）。"""
    r = _check("SELECT id, name FROM public.users")
    assert r["valid"] is True
    assert r["errors"] == []


def test_unqualified_column_ambiguous_in_multi_source_rejected():
    """用例 20: 多源下未限定列名若在多个表都存在必须拒绝（plan §5 P1）。"""
    r = _check(
        "SELECT id FROM public.users JOIN public.orders ON users.id = orders.user_id"
    )
    assert r["valid"] is False
    assert any("ambiguous" in e for e in r["errors"])


def test_unqualified_column_not_in_any_whitelist_rejected():
    """用例 21: 未限定列名不在任何 allowed_columns 中必须拒绝。"""
    r = _check(
        "SELECT bogus FROM public.users",
        db_type="postgresql",
        allowed_tables=PG_TABLES,
        allowed_columns={"public.users": ["id", "name"]},  # 'bogus' not in it
    )
    assert r["valid"] is False
    assert any("cannot be resolved" in e or "not allowed" in e for e in r["errors"])


# -----------------------------------------------------------------------------
# 22-24: denied_columns (Layer 1) & sensitive pattern (Layer 2)
# -----------------------------------------------------------------------------


def test_denied_column_rejected():
    """用例 22: denied_columns 命中必须返回 error（plan §5 P1 Layer 1）。"""
    r = _check(
        "SELECT id, password FROM public.users",
        db_type="postgresql",
        allowed_tables=PG_TABLES,
        allowed_columns={"public.users": ["id", "password"]},  # 列在白名单
        denied_columns=["password"],
    )
    assert r["valid"] is False
    assert any("denied list" in e for e in r["errors"])


def test_sensitive_column_pattern_emits_warning_only():
    """用例 23: 命中敏感列 pattern（如 email/phone）必须只产生 warning 而非 error。"""
    r = _check("SELECT id, email FROM public.users")
    assert r["valid"] is True
    assert r["errors"] == []
    assert any("matches sensitive-name pattern" in w for w in r["warnings"])
    # The warning text should name the column
    assert any("email" in w for w in r["warnings"])


def test_phone_column_pattern_emits_warning():
    """用例 24: phone 字段命中敏感 pattern 必须产生 warning。"""
    r = _check(
        "SELECT u.phone FROM public.users u",
        db_type="postgresql",
        allowed_tables=PG_TABLES,
        allowed_columns={"public.users": ["id", "phone"]},
        denied_columns=[],
    )
    assert r["valid"] is True
    assert any("matches sensitive-name pattern" in w for w in r["warnings"])


# -----------------------------------------------------------------------------
# 25-28: approved_sql_hash, defense-in-depth, complex statements
# -----------------------------------------------------------------------------


def test_approved_sql_hash_stable_for_same_input():
    """用例 25: approved_sql_hash 必须是 SHA-256 64 hex 且对相同输入稳定。"""
    r1 = _check("SELECT id, name FROM public.users")
    r2 = _check("SELECT id, name FROM public.users")
    assert r1["approved_sql_hash"] == r2["approved_sql_hash"]
    assert len(r1["approved_sql_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in r1["approved_sql_hash"])


def test_approved_sql_hash_is_64_hex_for_rejected_input():
    """用例 26: 即使被拒绝，approved_sql_hash 也必须存在且是 64 hex。"""
    r = _check("SELECT id FROM public.nonexistent_table")
    assert r["valid"] is False
    # 拒绝时仍应基于原始 SQL 计算 hash，便于审计追溯
    assert len(r["approved_sql_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in r["approved_sql_hash"])


def test_select_into_rejected_by_ast():
    """用例 27: SELECT INTO 必须由 AST 层拒绝（defense-in-depth，正则 Layer 2 也会拒）。"""
    r = _check("SELECT * INTO new_users FROM public.users")
    assert r["valid"] is False
    assert any("SELECT ... INTO is not allowed" in e for e in r["errors"])


def test_for_update_rejected_by_ast():
    """用例 28: FOR UPDATE 必须由 AST 层拒绝。"""
    r = _check("SELECT id FROM public.users FOR UPDATE")
    assert r["valid"] is False
    assert any("FOR UPDATE" in e or "lock rows" in e for e in r["errors"])


# -----------------------------------------------------------------------------
# Bonus cases (counted in 28 — see top-of-file docstring): coverage extensions
# -----------------------------------------------------------------------------


def test_insert_rejected_as_non_select():
    """INSERT 必须作为非 SELECT 语句拒绝（plan §5：AST 只允许 SELECT/WITH）。"""
    r = _check("INSERT INTO public.users (name) VALUES ('x')")
    assert r["valid"] is False
    assert any("only SELECT/WITH statements are allowed" in e for e in r["errors"])


def test_update_rejected_as_non_select():
    """UPDATE 必须拒绝。"""
    r = _check("UPDATE public.users SET name = 'x' WHERE id = 1")
    assert r["valid"] is False
    assert any("only SELECT/WITH statements are allowed" in e for e in r["errors"])


def test_delete_rejected_as_non_select():
    """DELETE 必须拒绝。"""
    r = _check("DELETE FROM public.users WHERE id = 1")
    assert r["valid"] is False
    assert any("only SELECT/WITH statements are allowed" in e for e in r["errors"])


def test_cte_with_explicit_columns_accepted():
    """CTE（WITH ... AS ...）配合显式列引用必须通过。"""
    r = _check(
        "WITH active_users AS (SELECT id, name FROM public.users) "
        "SELECT au.id FROM active_users au"
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_cte_with_select_star_rejected():
    """CTE 内 SELECT * 也必须拒绝（P1 SELECT * 规则全 AST 范围）。"""
    r = _check(
        "WITH x AS (SELECT id FROM public.users) SELECT * FROM x"
    )
    assert r["valid"] is False
    assert any("SELECT * / table.* is not allowed" in e for e in r["errors"])


def test_max_rows_clamped_to_max():
    """max_rows 超过 MAX_MAX_ROWS 必须被钳制并产生 warning。"""
    r = _check(
        "SELECT id FROM public.users",
        db_type="postgresql",
        allowed_tables=PG_TABLES,
        allowed_columns=PG_COLUMNS,
        denied_columns=[],
        max_rows=99999,
    )
    assert r["valid"] is True
    assert any("clamped" in w for w in r["warnings"])


def test_max_rows_invalid_type_rejected():
    """max_rows 非整数必须返回 error。"""
    r = _check(
        "SELECT id FROM public.users",
        db_type="postgresql",
        allowed_tables=PG_TABLES,
        allowed_columns=PG_COLUMNS,
        denied_columns=[],
        max_rows="not-a-number",  # type: ignore[arg-type]
    )
    assert r["valid"] is False
    assert any("max_rows" in e for e in r["errors"])


def test_no_whitelist_columns_still_valid_when_policy_open():
    """allowed_columns 为空 dict 表示策略开放；仅做表白名单校验。"""
    r = _check(
        "SELECT u.foo FROM public.users u",
        db_type="postgresql",
        allowed_tables=PG_TABLES,
        allowed_columns={},  # 开放策略：所有列都允许
        denied_columns=[],
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_no_whitelist_tables_still_valid_when_policy_open():
    """allowed_tables 为空列表表示策略开放；不强制白名单。"""
    r = _check(
        "SELECT id FROM any_table_at_all",
        db_type="postgresql",
        allowed_tables=[],
        allowed_columns={},
        denied_columns=[],
    )
    assert r["valid"] is True
    assert r["errors"] == []


def test_resolve_dialect_helper_public():
    """resolve_dialect 是公开辅助；不在 _DIALECT_MAP 中的值必须返回 None。"""
    assert SqlSafetyService.resolve_dialect("postgresql") == "postgres"
    assert SqlSafetyService.resolve_dialect("postgres") == "postgres"
    assert SqlSafetyService.resolve_dialect("mssql") == "tsql"
    assert SqlSafetyService.resolve_dialect("sqlserver") == "tsql"
    assert SqlSafetyService.resolve_dialect("tsql") == "tsql"
    assert SqlSafetyService.resolve_dialect("oracle") == "oracle"
    assert SqlSafetyService.resolve_dialect("mysql") == "mysql"
    assert SqlSafetyService.resolve_dialect("") is None
    assert SqlSafetyService.resolve_dialect("bigquery") is None