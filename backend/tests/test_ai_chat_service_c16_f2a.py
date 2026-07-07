"""
AiChatService C16-F2a 扩展测试（Phase 3.6B2）

覆盖 plan §21.2 Chat 绑定实例规则：
- mode='general' 不允许传 bound_instance_id
- mode='instance_sql' 必须传 bound_instance_id
- bound_instance_id 必须存在且 status='active'
- mode='instance_sql' 复用已有 session；mode='general' 每次新建
- 不同 user 独立 session

策略：
- 真实 dev DB（dbops.ai_chat_* / dbops.db_instance）
- 每个测试用唯一 session_code 前缀 "C16F2A-..."，teardown 清理
- bound_instance_id 用 dev DB 已注册 instance（PG id=965 from C16-F1 验证）
- inactive 实例：临时 UPDATE status='inactive'，teardown 恢复 'active'
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.ai import AiChatMessage, AiChatSession
from app.models.dbops_assets import DbInstance
from app.models.user import User
from app.services.ai_chat_service import (
    AiChatService,
    ChatInstanceNotAccessibleError,
    ChatModeInvalidError,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _cleanup_leftover_test_data(current_user, request):
    """每个 case 前后清理 C16F2A-* session + 当前测试用户的 instance_sql session。

    关键：服务生成的 session_code 前缀是 'CHAT-'，跨 case 复用 partial unique index
    会导致 test 7/8/11 冲突。每个 case 主动清理当前 user 的 instance_sql session。

    other_user 是 optional：dev DB 可能只有 1 个 active user。
    """
    def _cleanup(db, user_ids):
        # 1. C16F2A-* 前缀
        ids = [
            r[0]
            for r in db.query(AiChatSession.id)
            .filter(AiChatSession.session_code.like("C16F2A-%"))
            .all()
        ]
        # 2. 当前用户 (含 other_user 若存在) 的 instance_sql session
        user_instance_sql_ids = [
            r[0]
            for r in db.query(AiChatSession.id)
            .filter(
                AiChatSession.chat_mode == "instance_sql",
                AiChatSession.bound_instance_id.isnot(None),
                AiChatSession.user_id.in_(user_ids),
            )
            .all()
        ]
        all_ids = list(set(ids + user_instance_sql_ids))
        if all_ids:
            db.query(AiChatMessage).filter(AiChatMessage.session_id.in_(all_ids)).delete(synchronize_session=False)
            db.query(AiChatSession).filter(AiChatSession.id.in_(all_ids)).delete(synchronize_session=False)
            db.commit()

    # 收集所有可能涉及的 user_id（current_user + optional other_user）
    user_ids = [current_user.id]
    try:
        other = request.getfixturevalue("other_user")
        user_ids.append(other.id)
    except pytest.skip.Exception:
        pass

    db = SessionLocal()
    try:
        _cleanup(db, user_ids)
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        _cleanup(db, user_ids)
    finally:
        db.close()


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def current_user(db_session):
    user = db_session.query(User).filter(User.is_active == True).first()  # noqa: E712
    if user is None:
        pytest.skip("No active user in dev DB")
    return user


@pytest.fixture(scope="module")
def other_user(db_session):
    users = (
        db_session.query(User)
        .filter(User.is_active == True)  # noqa: E712
        .order_by(User.created_at)
        .all()
    )
    if len(users) < 2:
        pytest.skip("Need ≥2 active users for isolation test")
    return users[1]


@pytest.fixture(scope="module")
def active_instance(db_session):
    """真实 dev DB 已注册且 status='active' 的 instance（PG id=965 from C16-F1）。"""
    inst = (
        db_session.query(DbInstance)
        .filter(DbInstance.id == 965, DbInstance.status == "active")
        .first()
    )
    if inst is None:
        pytest.skip("Dev DB missing instance id=965 (run C16-F1 first)")
    return inst


@pytest.fixture
def inactive_instance(db_session):
    """临时把另一个 active instance 改为 inactive，case 结束恢复。

    使用 db_session 中第一个 id≠965 的 active instance，避免影响 PG 测试实例。
    """
    candidate = (
        db_session.query(DbInstance)
        .filter(DbInstance.status == "active", DbInstance.id != 965)
        .order_by(DbInstance.id)
        .first()
    )
    if candidate is None:
        pytest.skip("Need an additional active instance for inactive test")
    original_status = candidate.status
    candidate.status = "inactive"
    db_session.commit()
    yield candidate
    # 恢复
    candidate.status = original_status
    db_session.commit()


# -----------------------------------------------------------------------------
# 1. mode='general' 不允许传 bound_instance_id
# -----------------------------------------------------------------------------
def test_general_mode_rejects_bound_instance(db_session, current_user):
    """mode='general' 传 bound_instance_id → ChatModeInvalidError。"""
    with pytest.raises(ChatModeInvalidError) as exc_info:
        AiChatService.create_session(
            db_session,
            user=current_user,
            mode="general",
            bound_instance_id=965,
        )
    assert "general" in str(exc_info.value).lower()
    assert "bound_instance_id" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 2. mode='instance_sql' 必须传 bound_instance_id
# -----------------------------------------------------------------------------
def test_instance_sql_mode_requires_bound_instance(db_session, current_user):
    """mode='instance_sql' 不传 bound_instance_id → ChatModeInvalidError。"""
    with pytest.raises(ChatModeInvalidError) as exc_info:
        AiChatService.create_session(
            db_session,
            user=current_user,
            mode="instance_sql",
            bound_instance_id=None,
        )
    assert "instance_sql" in str(exc_info.value).lower()
    assert "bound_instance_id" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 3. mode 非法字符串 → ChatModeInvalidError
# -----------------------------------------------------------------------------
def test_invalid_mode_string_rejected(db_session, current_user):
    """mode='wrong_mode' → ChatModeInvalidError。"""
    with pytest.raises(ChatModeInvalidError) as exc_info:
        AiChatService.create_session(
            db_session,
            user=current_user,
            mode="wrong_mode",
        )
    assert "invalid" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# 4. bound_instance_id 不存在 → ChatInstanceNotAccessibleError
# -----------------------------------------------------------------------------
def test_bound_instance_not_found(db_session, current_user):
    """bound_instance_id=99999999 不存在 → 404。"""
    with pytest.raises(ChatInstanceNotAccessibleError) as exc_info:
        AiChatService.create_session(
            db_session,
            user=current_user,
            mode="instance_sql",
            bound_instance_id=99999999,
        )
    assert "not found" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# 5. bound_instance_id status='inactive' → ChatInstanceNotAccessibleError
# -----------------------------------------------------------------------------
def test_bound_instance_inactive_rejected(db_session, current_user, inactive_instance):
    """status='inactive' → ChatInstanceNotAccessibleError。"""
    with pytest.raises(ChatInstanceNotAccessibleError) as exc_info:
        AiChatService.create_session(
            db_session,
            user=current_user,
            mode="instance_sql",
            bound_instance_id=inactive_instance.id,
        )
    assert "not accessible" in str(exc_info.value).lower() or "inactive" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# 6. mode='general' + bound=None 默认行为：每次新建
# -----------------------------------------------------------------------------
def test_general_mode_creates_new_session_each_time(db_session, current_user):
    """mode='general' + bound=None：连续两次调用 → 两个独立 session（不复用）。"""
    r1 = AiChatService.create_session(db_session, user=current_user, mode="general")
    db_session.commit()
    r2 = AiChatService.create_session(db_session, user=current_user, mode="general")
    db_session.commit()

    assert r1.reused is False
    assert r2.reused is False
    assert r1.session.id != r2.session.id
    assert r1.session.chat_mode == "general"
    assert r1.session.bound_instance_id is None
    assert r2.session.chat_mode == "general"
    assert r2.session.bound_instance_id is None


# -----------------------------------------------------------------------------
# 7. mode='instance_sql' + bound=A：第一次新建，第二次复用
# -----------------------------------------------------------------------------
def test_instance_sql_mode_reuses_existing_session(db_session, current_user, active_instance):
    """mode='instance_sql' + bound=965：第二次调用复用同一个 session。"""
    r1 = AiChatService.create_session(
        db_session,
        user=current_user,
        mode="instance_sql",
        bound_instance_id=active_instance.id,
    )
    db_session.commit()
    assert r1.reused is False
    assert r1.session.chat_mode == "instance_sql"
    assert r1.session.bound_instance_id == active_instance.id

    r2 = AiChatService.create_session(
        db_session,
        user=current_user,
        mode="instance_sql",
        bound_instance_id=active_instance.id,
    )
    db_session.commit()
    assert r2.reused is True
    assert r2.session.id == r1.session.id


# -----------------------------------------------------------------------------
# 8. 不同 user 的 instance_sql session 互相独立
# -----------------------------------------------------------------------------
def test_instance_sql_session_isolated_per_user(db_session, current_user, other_user, active_instance):
    """不同 user 用同一 instance → 不同 session（不被复用）。"""
    r1 = AiChatService.create_session(
        db_session,
        user=current_user,
        mode="instance_sql",
        bound_instance_id=active_instance.id,
    )
    db_session.commit()
    r2 = AiChatService.create_session(
        db_session,
        user=other_user,
        mode="instance_sql",
        bound_instance_id=active_instance.id,
    )
    db_session.commit()

    assert r1.reused is False
    assert r2.reused is False
    assert r1.session.id != r2.session.id
    assert r1.session.user_id != r2.session.user_id
    assert r1.session.bound_instance_id == r2.session.bound_instance_id == active_instance.id


# -----------------------------------------------------------------------------
# 9. 不可变绑定：service 层不暴露 update 接口
# -----------------------------------------------------------------------------
def test_instance_sql_session_immutable_no_update(db_session, current_user, active_instance):
    """创建 instance_sql session 后，service 层无 update 方法（DB CHECK 兜底）。

    验证：
    1. 创建后 chat_mode + bound_instance_id 在 DB 落库正确
    2. ORM 端没有 update_chat_mode / rebind_instance 等接口（C16-F2a MVP）
    """
    r = AiChatService.create_session(
        db_session,
        user=current_user,
        mode="instance_sql",
        bound_instance_id=active_instance.id,
    )
    db_session.commit()
    obj = r.session
    db_session.refresh(obj)

    assert obj.chat_mode == "instance_sql"
    assert obj.bound_instance_id == active_instance.id

    # service 没有 rebind / change_mode 接口（plan §21.2 P0-1 不可变规则）
    assert not hasattr(AiChatService, "rebind_session")
    assert not hasattr(AiChatService, "change_chat_mode")


# -----------------------------------------------------------------------------
# 10. DB CHECK 约束：mode='general' + bound=NOT NULL → IntegrityError
# -----------------------------------------------------------------------------
def test_db_check_constraint_blocks_invalid_combination(db_session, current_user):
    """DB 层 CHECK 约束兜底：直接 ORM 写非法组合 → IntegrityError。"""
    from sqlalchemy.exc import IntegrityError

    session_obj = AiChatSession(
        session_code=f"C16F2A-{uuid.uuid4().hex[:8].upper()}",
        user_id=current_user.id,
        title="db-check-test",
        message_count=0,
        chat_mode="general",
        bound_instance_id=965,  # 非法组合：general + NOT NULL
    )
    db_session.add(session_obj)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# -----------------------------------------------------------------------------
# 11. partial unique index：同 user + 同 instance 第二次直接 ORM 写冲突
# -----------------------------------------------------------------------------
def test_db_partial_unique_blocks_duplicate_instance_sql(db_session, current_user, active_instance):
    """DB partial unique 兜底：两次 ORM 写同 (user, instance_sql) → IntegrityError。"""
    from sqlalchemy.exc import IntegrityError

    s1 = AiChatSession(
        session_code=f"C16F2A-{uuid.uuid4().hex[:8].upper()}",
        user_id=current_user.id,
        title="unique-1",
        message_count=0,
        chat_mode="instance_sql",
        bound_instance_id=active_instance.id,
    )
    db_session.add(s1)
    db_session.commit()

    s2 = AiChatSession(
        session_code=f"C16F2A-{uuid.uuid4().hex[:8].upper()}",
        user_id=current_user.id,
        title="unique-2",
        message_count=0,
        chat_mode="instance_sql",
        bound_instance_id=active_instance.id,  # 同 (user, bound) → 违反 partial unique
    )
    db_session.add(s2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# -----------------------------------------------------------------------------
# 12. source_page 仅日志记录，不持久化（不抛错即可）
# -----------------------------------------------------------------------------
def test_source_page_logged_not_persisted(db_session, current_user):
    """source_page='instance_detail' 不应抛错，且不影响 session 创建。"""
    r = AiChatService.create_session(
        db_session,
        user=current_user,
        mode="general",
        source_page="instance_detail",
    )
    db_session.commit()
    assert r.reused is False
    assert r.session.id is not None


# -----------------------------------------------------------------------------
# 13. CreateSessionResult dataclass 字段
# -----------------------------------------------------------------------------
def test_create_session_result_dataclass(db_session, current_user):
    """CreateSessionResult(session, reused) 字段类型正确。"""
    from app.services.ai_chat_service import CreateSessionResult

    r = AiChatService.create_session(db_session, user=current_user, mode="general")
    assert isinstance(r, CreateSessionResult)
    assert hasattr(r, "session")
    assert hasattr(r, "reused")
    assert isinstance(r.session, AiChatSession)
    assert isinstance(r.reused, bool)


# -----------------------------------------------------------------------------
# 14. 标题 + mode 同时传入
# -----------------------------------------------------------------------------
def test_create_session_with_title_and_mode(db_session, current_user):
    """title + mode='general' 同时传入 → 落库正确。"""
    r = AiChatService.create_session(
        db_session,
        user=current_user,
        title="我的测试会话",
        mode="general",
    )
    db_session.commit()
    db_session.refresh(r.session)
    assert r.session.title == "我的测试会话"
    assert r.session.chat_mode == "general"
    assert r.session.bound_instance_id is None


# -----------------------------------------------------------------------------
# 15. 异常可被 Pydantic/路由层捕获（继承 AiChatError 基类）
# -----------------------------------------------------------------------------
def test_exceptions_inherit_from_base():
    """C16-F2a 新异常继承 AiChatError 基类（统一捕获语义）。"""
    from app.services.ai_chat_service import AiChatError

    assert issubclass(ChatModeInvalidError, AiChatError)
    assert issubclass(ChatInstanceNotAccessibleError, AiChatError)