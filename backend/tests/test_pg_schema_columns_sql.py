"""
Phase 3.6B0 C7 — PostgreSQL Schema Metadata SQL 模板测试

覆盖:
1. SQL 文件存在且可读
2. SQL 是单条 SELECT（只读），无 DDL/DML
3. SELECT 列表为 6 列（与 plan §4.4 line 437 一致）
4. WHERE 排除 pg_catalog / information_schema
5. ORDER BY 稳定（按 schema/table/ordinal_position）

不在 C7 测试范围:
- live DB 实跑（手动 C7-3 验证，test 中不依赖 dev DB 状态）
- 完整性校验（truncated/total_rows/returned_rows 是 C9 callback 范围）
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SQL_PATH = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "services"
    / "ai"
    / "sql_templates"
    / "postgresql"
    / "pg_schema_columns.sql"
)


@pytest.fixture(scope="module")
def sql_text() -> str:
    """读取 SQL 模板文件内容。"""
    return SQL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_first_statement(sql_text: str) -> str:
    """提取第一条 SQL 语句（去掉注释）。"""
    # 移除 -- 行注释
    lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        lines.append(line)
    return "\n".join(lines).strip().rstrip(";").strip()


# -----------------------------------------------------------------------------
# 1. 文件存在性 + 基本可读性
# -----------------------------------------------------------------------------
def test_sql_file_exists():
    assert SQL_PATH.exists(), f"SQL template not found: {SQL_PATH}"


def test_sql_file_is_readable():
    content = SQL_PATH.read_text(encoding="utf-8")
    assert len(content) > 0, "SQL template is empty"


def test_sql_file_mentions_phase36():
    """Header 注释应包含 Phase 3.6 标识，便于人工审计。"""
    content = SQL_PATH.read_text(encoding="utf-8")
    assert "Phase 3.6" in content


# -----------------------------------------------------------------------------
# 2. SQL 只读性（无 DDL/DML 关键字）
# -----------------------------------------------------------------------------
FORBIDDEN_KEYWORDS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bVACUUM\b",
    r"\bCOPY\b",  # COPY 可写
]


@pytest.mark.parametrize("pattern", FORBIDDEN_KEYWORDS)
def test_sql_has_no_dml_ddl(sql_first_statement: str, pattern: str):
    """验证 SQL 不包含写操作关键字（计划 §4.4 P0 — 只读约束）。"""
    assert not re.search(pattern, sql_first_statement, re.IGNORECASE), (
        f"SQL contains forbidden keyword pattern: {pattern}"
    )


def test_sql_is_select(sql_first_statement: str):
    """SQL 必须是单条 SELECT。"""
    assert re.match(r"^\s*SELECT\b", sql_first_statement, re.IGNORECASE), (
        "SQL must start with SELECT"
    )


def test_sql_single_statement(sql_text: str):
    """SQL 只能有一条语句（无分号分隔的多语句，避免 statement injection）。"""
    # 去掉注释后计数
    stripped = []
    for line in sql_text.splitlines():
        if line.strip().startswith("--") or not line.strip():
            continue
        stripped.append(line)
    body = "\n".join(stripped)
    # 语句分隔符是分号；末尾分号允许，文件中只能有一个
    semicolons = body.count(";")
    assert semicolons <= 1, f"SQL has {semicolons} statements; expected at most 1"


# -----------------------------------------------------------------------------
# 3. SELECT 列集合（6 列）
# -----------------------------------------------------------------------------
EXPECTED_COLUMNS = [
    "table_schema",
    "table_name",
    "column_name",
    "data_type",
    "is_nullable",
    "ordinal_position",
]


@pytest.mark.parametrize("column", EXPECTED_COLUMNS)
def test_sql_selects_expected_column(sql_first_statement: str, column: str):
    """SELECT 列表必须包含 6 列（与 plan §4.4 line 437 + C8 Builder 期望一致）。"""
    pattern = rf"\b{re.escape(column)}\b"
    assert re.search(pattern, sql_first_statement, re.IGNORECASE), (
        f"SQL must select column: {column}"
    )


def test_sql_select_count(sql_first_statement: str):
    """SELECT 列表恰好 6 列（避免额外列污染 snapshot 数据）。"""
    # 匹配 SELECT ... FROM 之间的内容
    match = re.search(
        r"SELECT\s+(.+?)\s+FROM",
        sql_first_statement,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, "SQL must have SELECT ... FROM structure"
    select_body = match.group(1)
    # 按逗号分割（顶层逗号，不在括号内）
    cols = [c.strip() for c in select_body.split(",") if c.strip()]
    assert len(cols) == 6, f"SQL must select exactly 6 columns, got {len(cols)}: {cols}"


# -----------------------------------------------------------------------------
# 4. WHERE 过滤系统 schema
# -----------------------------------------------------------------------------
def test_sql_excludes_pg_catalog(sql_first_statement: str):
    assert "pg_catalog" in sql_first_statement, (
        "SQL must exclude pg_catalog in WHERE"
    )


def test_sql_excludes_information_schema(sql_first_statement: str):
    assert "information_schema" in sql_first_statement, (
        "SQL must exclude information_schema in WHERE"
    )


def test_sql_uses_information_schema_view(sql_first_statement: str):
    """必须查询 information_schema.columns（只读视图，不直接读 pg_catalog）。"""
    assert re.search(
        r"FROM\s+information_schema\.columns",
        sql_first_statement,
        re.IGNORECASE,
    ), "SQL must query information_schema.columns"


# -----------------------------------------------------------------------------
# 5. ORDER BY 稳定排序
# -----------------------------------------------------------------------------
def test_sql_has_order_by(sql_first_statement: str):
    """ORDER BY 保证 (schema, table, ordinal) 稳定 → 幂等 hash 一致。"""
    assert re.search(r"ORDER\s+BY\b", sql_first_statement, re.IGNORECASE), (
        "SQL must have ORDER BY for stable hashing"
    )


def test_sql_order_by_keys(sql_first_statement: str):
    """ORDER BY 必须是 (table_schema, table_name, ordinal_position) — 与 SELECT 列表前缀一致。"""
    match = re.search(
        r"ORDER\s+BY\s+(.+?)$",
        sql_first_statement,
        re.IGNORECASE | re.DOTALL,
    )
    assert match
    keys = [k.strip() for k in match.group(1).split(",")]
    expected = ["table_schema", "table_name", "ordinal_position"]
    assert keys == expected, f"ORDER BY must be {expected}, got {keys}"


# -----------------------------------------------------------------------------
# 6. SQL 模板元信息（header 注释完整性）
# -----------------------------------------------------------------------------
def test_sql_header_documents_purpose(sql_text: str):
    """Header 注释应说明用途 + plan 参考。"""
    assert "用途" in sql_text or "Purpose" in sql_text.lower()
    assert "plan" in sql_text.lower() or "§4.4" in sql_text


def test_sql_header_documents_readonly(sql_text: str):
    """Header 应明示只读性。"""
    assert "只读" in sql_text or "read-only" in sql_text.lower() or "readonly" in sql_text.lower()
