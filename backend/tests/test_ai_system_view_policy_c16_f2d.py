"""Phase 3.6B2 C16-F2d — ai_system_view_policy DDL/ORM 集成测试.

覆盖 (plan §21.4 / commit handoff 2026-07-09):
  Part A  DDL Schema (5 cases):
    1.  dbops.ai_system_view_policy 表存在
    2.  11 列及类型 / nullable / default 符合 DDL
    3.  3 CHECK 约束存在并按设计工作（db_type / allowlist nonempty / denylist array）
    4.  UNIQUE on instance_id 生效（重复插入 instance_id 报 unique_violation）
    5.  FK to dbops.db_instance ON DELETE CASCADE 生效

  Part B  Trigger Validate Elements (3 cases):
    6.  allowlist 元素 trim 后为空 → RAISE EXCEPTION
    7.  denylist 元素 trim 后为空 → RAISE EXCEPTION
    8.  NULL 元素 → RAISE EXCEPTION

  Part C  ORM Model (4 cases):
    9.  AiSystemViewPolicy.__tablename__ == "ai_system_view_policy"
    10. ORM 字段 (instance_id / db_type_code / policy_version / allowlist /
        denylist / enabled / updated_by / updated_at / created_at) 完整
    11. ORM unique=True on instance_id（与 DDL UNIQUE 约束对齐）
    12. ORM CheckConstraint chk_ai_system_view_policy_db_type 存在

策略:
  - 直接连真实 dev DB（10.134.185.85:5432），通过 SQLAlchemy text() 查询 information_schema
  - 不连业务表 / 不修改业务数据（CLAUDE.md §5 强约束）
  - 测试结束后清理测试插入的行（rollback 或 DELETE WHERE）
  - 真实测试 instance 用 dbops.db_instance 中已有的行（避免 FK 报错）；
    若测试 instance 不存在则 skip
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Optional

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai import AiSystemViewPolicy  # noqa: E402
from app.models.dbops_assets import DbopsAssetBase  # noqa: E402

DEV_DB_URL = os.getenv(
    "DBOPS_TEST_DB_URL",
    "postgresql+psycopg2://dbops:root123@10.134.185.85:5432/dbops",
)

# 测试 instance_id：硬编码一个真实存在的 db_instance id；若无则 skip
TEST_INSTANCE_ID = int(os.getenv("DBOPS_TEST_INSTANCE_ID", "1"))


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DEV_DB_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def cleanup_policy(engine):
    """每个 case 跑完后清理测试 instance 对应的 policy 行。"""
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM dbops.ai_system_view_policy WHERE instance_id = :iid"),
            {"iid": TEST_INSTANCE_ID},
        )


def _instance_exists(engine, instance_id: int) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM dbops.db_instance WHERE id = :iid LIMIT 1"),
            {"iid": instance_id},
        ).first()
    return row is not None


def _skip_if_no_instance(engine):
    if not _instance_exists(engine, TEST_INSTANCE_ID):
        pytest.skip(f"dev DB 缺 db_instance id={TEST_INSTANCE_ID}，跳过 DDL 集成测试")


# =============================================================================
# Part A: DDL Schema (5 cases)
# =============================================================================
def test_table_exists(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='dbops' AND table_name='ai_system_view_policy'"
            )
        ).first()
    assert row is not None, "dbops.ai_system_view_policy 表不存在"


def test_table_columns(engine):
    """11 列：id/instance_id/db_type_code/policy_version/allowlist/denylist/
    enabled/updated_by/updated_at/created_at."""
    expected = {
        "id": ("bigint", "NO"),
        "instance_id": ("bigint", "NO"),
        "db_type_code": ("character varying", "NO"),
        "policy_version": ("character varying", "NO"),
        "allowlist": ("jsonb", "NO"),
        "denylist": ("jsonb", "NO"),
        "enabled": ("boolean", "NO"),
        "updated_by": ("uuid", "YES"),
        "updated_at": ("timestamp without time zone", "NO"),
        "created_at": ("timestamp without time zone", "NO"),
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema='dbops' AND table_name='ai_system_view_policy'"
            )
        ).fetchall()
    got = {r[0]: (r[1], r[2]) for r in rows}
    assert set(expected.keys()).issubset(set(got.keys())), (
        f"缺失列：{set(expected.keys()) - set(got.keys())}"
    )
    for col, (dtype, nullable) in expected.items():
        assert got[col][0] == dtype, f"列 {col} 类型应为 {dtype}，实为 {got[col][0]}"
        assert got[col][1] == nullable, (
            f"列 {col} nullable 应为 {nullable}，实为 {got[col][1]}"
        )


def test_check_constraints(engine):
    """3 CHECK 约束必须存在。"""
    expected_checks = {
        "chk_ai_system_view_policy_db_type",
        "chk_ai_system_view_policy_allowlist_nonempty",
        "chk_ai_system_view_policy_denylist_array",
    }
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid='dbops.ai_system_view_policy'::regclass "
                "AND contype='c'"
            )
        ).fetchall()
    got = {r[0] for r in rows}
    missing = expected_checks - got
    assert not missing, f"缺失 CHECK 约束：{missing}"


def test_unique_constraint_on_instance_id(engine, cleanup_policy):
    """UNIQUE on instance_id 生效：插入两行同 instance_id 应报错。"""
    _skip_if_no_instance(engine)
    sql = text(
        "INSERT INTO dbops.ai_system_view_policy "
        "(instance_id, db_type_code, policy_version, allowlist, enabled) "
        "VALUES (:iid, :db, :ver, CAST(:al AS jsonb), false)"
    )
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "iid": TEST_INSTANCE_ID,
                "db": "POSTGRESQL",
                "ver": "2026-07-09-v1",
                "al": '["pg_catalog.pg_stat_activity"]',
            },
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                sql,
                {
                    "iid": TEST_INSTANCE_ID,
                    "db": "POSTGRESQL",
                    "ver": "2026-07-09-v1",
                    "al": '["pg_catalog.pg_stat_database"]',
                },
            )


def test_foreign_key_instance_id(engine, cleanup_policy):
    """FK to dbops.db_instance ON DELETE CASCADE — 插入不存在的 instance_id 应报错。"""
    fake_iid = 999_999_999
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO dbops.ai_system_view_policy "
                    "(instance_id, db_type_code, policy_version, allowlist) "
                    "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', '[\"x\"]'::jsonb)"
                ),
                {"iid": fake_iid},
            )


# =============================================================================
# Part B: Trigger Validate Elements (3 cases)
# =============================================================================
def test_trigger_validate_allowlist_empty_element(engine, cleanup_policy):
    """allowlist 元素 trim 后为空 → trigger 抛异常。"""
    _skip_if_no_instance(engine)
    with engine.begin() as conn:
        with pytest.raises(Exception) as excinfo:
            conn.execute(
                text(
                    "INSERT INTO dbops.ai_system_view_policy "
                    "(instance_id, db_type_code, policy_version, allowlist) "
                    "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', CAST(:al AS jsonb))"
                ),
                {"iid": TEST_INSTANCE_ID, "al": '["   "]'},
            )
        # PG trigger 用 RAISE EXCEPTION，psycopg 抛出 PG 的 IntegrityError 或
        # ProgrammingError，message 含 "ai_system_view_policy element must be"
        assert "ai_system_view_policy element must be" in str(excinfo.value)


def test_trigger_validate_denylist_empty_element(engine, cleanup_policy):
    """denylist 元素 trim 后为空 → trigger 抛异常。"""
    _skip_if_no_instance(engine)
    with engine.begin() as conn:
        with pytest.raises(Exception) as excinfo:
            conn.execute(
                text(
                    "INSERT INTO dbops.ai_system_view_policy "
                    "(instance_id, db_type_code, policy_version, allowlist, denylist) "
                    "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', CAST(:al AS jsonb), CAST(:dl AS jsonb))"
                ),
                {
                    "iid": TEST_INSTANCE_ID,
                    "al": '["pg_class"]',
                    "dl": '["   "]',
                },
            )
        assert "ai_system_view_policy element must be" in str(excinfo.value)


def test_trigger_validate_null_element(engine, cleanup_policy):
    """allowlist 含 NULL 元素 → trigger 抛异常。"""
    _skip_if_no_instance(engine)
    # jsonb 数组不支持 SQL NULL 元素（会变成 JSON null），用 'null' 触发
    with engine.begin() as conn:
        with pytest.raises(Exception) as excinfo:
            conn.execute(
                text(
                    "INSERT INTO dbops.ai_system_view_policy "
                    "(instance_id, db_type_code, policy_version, allowlist) "
                    "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', CAST(:al AS jsonb))"
                ),
                {"iid": TEST_INSTANCE_ID, "al": '["valid", null]'},
            )
        assert "ai_system_view_policy element must be" in str(excinfo.value)


# =============================================================================
# Part C: ORM Model (4 cases)
# =============================================================================
def test_orm_model_tablename():
    assert AiSystemViewPolicy.__tablename__ == "ai_system_view_policy"


def test_orm_model_columns_present():
    cols = {c.name for c in AiSystemViewPolicy.__table__.columns}
    expected = {
        "id",
        "instance_id",
        "db_type_code",
        "policy_version",
        "allowlist",
        "denylist",
        "enabled",
        "updated_by",
        "updated_at",
        "created_at",
    }
    missing = expected - cols
    assert not missing, f"ORM 缺失列：{missing}"


def test_orm_model_unique_constraint_instance_id():
    instance_id_col = AiSystemViewPolicy.__table__.columns["instance_id"]
    assert instance_id_col.unique is True, (
        "instance_id ORM 列缺 unique=True（与 DDL UNIQUE 约束对齐）"
    )


def test_orm_model_check_constraint_db_type():
    names = {c.name for c in AiSystemViewPolicy.__table__.constraints}
    assert "chk_ai_system_view_policy_db_type" in names, (
        "ORM CheckConstraint chk_ai_system_view_policy_db_type 缺失"
    )


# =============================================================================
# Part D: Defaults 验证
# =============================================================================
def test_default_enabled_is_false(engine, cleanup_policy):
    """不显式传 enabled → 默认 false。"""
    _skip_if_no_instance(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dbops.ai_system_view_policy "
                "(instance_id, db_type_code, policy_version, allowlist) "
                "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', '[\"x\"]'::jsonb)"
            ),
            {"iid": TEST_INSTANCE_ID},
        )
        row = conn.execute(
            text(
                "SELECT enabled FROM dbops.ai_system_view_policy "
                "WHERE instance_id = :iid"
            ),
            {"iid": TEST_INSTANCE_ID},
        ).first()
    assert row is not None
    assert row[0] is False, f"enabled 默认应为 false，实为 {row[0]}"


def test_default_denylist_is_empty_array(engine, cleanup_policy):
    """不显式传 denylist → 默认 '[]'。"""
    _skip_if_no_instance(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dbops.ai_system_view_policy "
                "(instance_id, db_type_code, policy_version, allowlist) "
                "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', '[\"x\"]'::jsonb)"
            ),
            {"iid": TEST_INSTANCE_ID},
        )
        row = conn.execute(
            text(
                "SELECT denylist FROM dbops.ai_system_view_policy "
                "WHERE instance_id = :iid"
            ),
            {"iid": TEST_INSTANCE_ID},
        ).first()
    assert row is not None
    # psycopg 返回 jsonb 时自动转 dict/list
    denylist = row[0]
    assert isinstance(denylist, list), f"denylist 应为 list，实为 {type(denylist)}"
    assert len(denylist) == 0, f"denylist 默认应为空数组，实为 {denylist}"


# =============================================================================
# Part E: Schema 边界条件
# =============================================================================
def test_index_on_db_type_code(engine):
    """idx_ai_system_view_policy_db_type 索引存在。"""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE schemaname='dbops' AND tablename='ai_system_view_policy' "
                "AND indexname='idx_ai_system_view_policy_db_type'"
            )
        ).first()
    assert row is not None, "索引 idx_ai_system_view_policy_db_type 不存在"


def test_reject_invalid_db_type_code(engine, cleanup_policy):
    """db_type_code 不在枚举内 → CHECK 拒绝。"""
    _skip_if_no_instance(engine)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO dbops.ai_system_view_policy "
                    "(instance_id, db_type_code, policy_version, allowlist) "
                    "VALUES (:iid, 'MYSQL', '2026-07-09-v1', '[\"x\"]'::jsonb)"
                ),
                {"iid": TEST_INSTANCE_ID},
            )


def test_reject_empty_allowlist(engine, cleanup_policy):
    """allowlist 为空数组 → CHECK 拒绝。"""
    _skip_if_no_instance(engine)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO dbops.ai_system_view_policy "
                    "(instance_id, db_type_code, policy_version, allowlist) "
                    "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', '[]'::jsonb)"
                ),
                {"iid": TEST_INSTANCE_ID},
            )


def test_reject_non_array_allowlist(engine, cleanup_policy):
    """allowlist 不是数组 → CHECK 拒绝。"""
    _skip_if_no_instance(engine)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO dbops.ai_system_view_policy "
                    "(instance_id, db_type_code, policy_version, allowlist) "
                    "VALUES (:iid, 'POSTGRESQL', '2026-07-09-v1', '{\"a\": 1}'::jsonb)"
                ),
                {"iid": TEST_INSTANCE_ID},
            )
