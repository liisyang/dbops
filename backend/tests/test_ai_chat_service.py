"""
AiChatService + Chat API 单元测试（Phase 3.6 C3 / C4）

覆盖 plan §13 Chat 矩阵的 12+ 用例：
1.  create_session
2.  send_message（mock Dify 成功）— assistant status=completed + dify_conversation_id 写入
3.  send_message conversation_id 复用 — 第二次 send 复用第一次的 dify_conversation_id
4.  用户隔离 — 其他 user 不能访问本 user 的 session
5.  list_messages — 按 created_at ASC 排序
6.  empty query 被 Pydantic 拒绝
7.  user 消息幂等 — 相同 client_request_id 返回 idempotent_replay=true
8.  同 session 并发第二个 send → 409 ChatConcurrentPendingError
9.  pending 超时 → stale → 允许新 send（lease 过期场景）
10. cleanup_stale_pending — UPDATE 把 lease 过期的 assistant pending 标 stale
11. 前端 role/locale/conversation_id 被忽略 — Dify inputs 来自 current_user
12. AI_CHAT_ENABLED=false → ChatFeatureDisabledError
13. Dify 未初始化 → ChatDifyUnavailableError
14. Dify 超时 → ChatDifyTimeoutError
15. Dify HTTP 错误 → assistant status=failed + error_code 写入

策略：
- 真实 dev DB（dbops.ai_chat_*）— 通过 SQLAlchemy SessionLocal
- 每个测试用唯一 session_code 前缀 "CHAT-TEST-..."，最后 teardown 清理
- DifyService.chat_message 用 unittest.mock.patch 拦截
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.ai import AiChatMessage, AiChatSession
from app.models.user import User
from app.schemas.ai import AiChatMessageSendRequest
from app.services.ai_chat_service import (
    AiChatService,
    ChatConcurrentPendingError,
    ChatDifyTimeoutError,
    ChatDifyUnavailableError,
    ChatFeatureDisabledError,
    ChatSessionNotFoundError,
)
from app.services.dify_service import DifyService


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _cleanup_leftover_test_data():
    """每次测试前清理残留 CHAT-TEST-* session 与 pending 消息。

    关键：上次测试失败/中断可能留下 assistant pending 消息，撞
    uq_ai_chat_message_assistant_pending 部分唯一索引导致后续测试无法创建 pending。
    """
    db = SessionLocal()
    try:
        test_session_ids = (
            db.query(AiChatSession.id)
            .filter(AiChatSession.session_code.like("CHAT-TEST-%"))
            .all()
        )
        ids = [r[0] for r in test_session_ids]
        if ids:
            db.query(AiChatMessage).filter(AiChatMessage.session_id.in_(ids)).delete(synchronize_session=False)
            db.query(AiChatSession).filter(AiChatSession.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()
    yield
    # 测试后再次清理（确保下个测试前干净）
    db = SessionLocal()
    try:
        ids = [
            r[0]
            for r in db.query(AiChatSession.id)
            .filter(AiChatSession.session_code.like("CHAT-TEST-%"))
            .all()
        ]
        if ids:
            db.query(AiChatMessage).filter(AiChatMessage.session_id.in_(ids)).delete(synchronize_session=False)
            db.query(AiChatSession).filter(AiChatSession.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def db_session():
    """整个测试模块共享一个 DB session。"""
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def current_user(db_session):
    """使用 dev DB 中第一个 active user（admin / zh-CN）。"""
    user = db_session.query(User).filter(User.is_active == True).first()  # noqa: E712
    if user is None:
        pytest.skip("No active user in dev DB")
    return user


@pytest.fixture(scope="module")
def other_user(db_session):
    """第二个 active user（用于用户隔离测试）。"""
    users = (
        db_session.query(User)
        .filter(User.is_active == True)  # noqa: E712
        .order_by(User.created_at)
        .all()
    )
    if len(users) < 2:
        pytest.skip("Need ≥2 active users for isolation test")
    return users[1]


@pytest.fixture(autouse=True)
def _reset_dify_class():
    """每个 case 前重置 DifyService 类变量。"""
    import sys as _sys
    print(f"\n[DEBUG _reset setup] _client={DifyService._client}", file=_sys.stderr)
    DifyService._client = None
    DifyService._base_url = ""
    DifyService._connect_timeout = 10.0
    DifyService._default_timeout = 60.0
    yield
    print(f"\n[DEBUG _reset teardown] _client={DifyService._client}", file=_sys.stderr)
    DifyService._client = None


@pytest.fixture(autouse=True)
def _enable_chat_and_dify():
    """默认开启 chat + 注入测试用 Dify 配置 + 初始化 DifyService 客户端。

    关键：pytest 同 scope autouse fixtures 按字母顺序运行。
    本 fixture 名字以 _e 开头，在 _reset_dify_class（_r）之前执行 ——
    所以 init_client 的结果不会被 _reset 覆盖。
    DifyService.close_client() 在 teardown 把 _client 置 None，下个 case 重新 init。
    """
    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    object.__setattr__(s, "AI_CHAT_ENABLED", True)
    object.__setattr__(s, "DIFY_BASE_URL", "http://dify.test/v1")
    object.__setattr__(s, "DIFY_CHAT_API_KEY", "test-chat-key")
    object.__setattr__(s, "AI_CHAT_LEASE_SECONDS", 90)

    DifyService.init_client(base_url="http://dify.test/v1", timeout=60.0, connect_timeout=5.0)

    yield
    DifyService.close_client()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_dify_class():
    """兜底：万一 _enable 因异常未 init，把 _client 显式置 None。

    pytest 字母顺序：_enable (e) < _reset (r)，所以 _enable 先 init，_reset 再 reset。
    这意味着 _reset 总是会把 _client 置 None ——
    因此仅在 _enable 出错时（未 init）才生效，正常情况由 _enable teardown 处理。
    """
    yield
    DifyService._client = None


@pytest.fixture
def test_session(db_session, current_user):
    """为每个 case 创建一个会话（teardown 时按 id 删除，cascade 删 messages）。"""
    code = f"CHAT-TEST-{uuid.uuid4().hex[:12].upper()}"
    obj = AiChatSession(
        session_code=code,
        user_id=current_user.id,
        title="测试会话",
        message_count=0,
    )
    db_session.add(obj)
    db_session.commit()
    db_session.refresh(obj)
    yield obj
    db_session.query(AiChatSession).filter(AiChatSession.id == obj.id).delete()
    db_session.commit()


# -----------------------------------------------------------------------------
# 1. create_session
# -----------------------------------------------------------------------------
def test_create_session_returns_valid_session(db_session, current_user):
    """创建会话：返回 CreateSessionResult(session, reused) 且 session_code 唯一。

    C16-F2a 升级：create_session 改为返回 CreateSessionResult 包装对象，
    兼容旧的 kwargs（mode/bound_instance_id 默认 'general'/None 即老行为）。
    """
    result = AiChatService.create_session(db_session, user=current_user, title="新测试")
    db_session.commit()
    obj = result.session
    db_session.refresh(obj)

    assert obj.id is not None
    assert obj.session_code.startswith("CHAT-")
    assert obj.user_id == current_user.id
    assert obj.title == "新测试"
    assert obj.message_count == 0
    # C16-F2a 默认 mode='general' + bound_instance_id=None
    assert obj.chat_mode == "general"
    assert obj.bound_instance_id is None
    # 首次创建：reused=False
    assert result.reused is False

    # Teardown
    db_session.query(AiChatSession).filter(AiChatSession.id == obj.id).delete()
    db_session.commit()


# -----------------------------------------------------------------------------
# 2. send_message — 成功 + assistant completed + dify_conversation_id 写入
# -----------------------------------------------------------------------------
def test_send_message_with_mock_dify_success(db_session, current_user, test_session):
    """send_message：mock Dify 返回 answer + conversation_id。"""
    fake_response = {
        "answer": "你好，这是 mock 回复。",
        "conversation_id": "dify-conv-001",
        "message_id": "dify-msg-001",
        "elapsed_ms": 123,
        "total_tokens": 42,
        "metadata": {"retriever_resources": []},
    }

    with patch.object(DifyService, "chat_message", return_value=fake_response) as mock_chat:
        result = AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="你好",
                current_page="ai_chat",
            ),
        )

    assert result.idempotent_replay is False
    assert result.user_message.role == "user"
    assert result.user_message.content == "你好"
    assert result.user_message.status == "completed"
    assert result.assistant_message is not None
    assert result.assistant_message.role == "assistant"
    assert result.assistant_message.status == "completed"
    assert result.assistant_message.content == "你好，这是 mock 回复。"
    assert result.assistant_message.dify_task_id == "dify-msg-001"

    db_session.refresh(test_session)
    assert test_session.dify_conversation_id == "dify-conv-001"
    assert test_session.last_message_at is not None
    assert test_session.message_count == 2  # user + assistant

    # Dify 调用参数验证（plan §7 安全）
    call_kwargs = mock_chat.call_args.kwargs
    assert call_kwargs["query"] == "你好"
    assert call_kwargs["user"] == f"dbops:{current_user.id}"
    assert call_kwargs["conversation_id"] is None
    assert call_kwargs["inputs"]["current_page"] == "ai_chat"
    assert call_kwargs["inputs"]["locale"] == "zh-CN"


# -----------------------------------------------------------------------------
# 3. send_message conversation_id 复用
# -----------------------------------------------------------------------------
def test_send_message_reuses_dify_conversation_id(db_session, current_user, test_session):
    """第二次 send 时 conversation_id 传 session 已有的值。"""
    test_session.dify_conversation_id = "dify-existing-conv"
    db_session.commit()

    fake_response = {"answer": "x", "conversation_id": "dify-existing-conv", "message_id": "m1"}
    with patch.object(DifyService, "chat_message", return_value=fake_response) as mock_chat:
        AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="follow-up",
                current_page="ai_chat",
            ),
        )

    call_kwargs = mock_chat.call_args.kwargs
    assert call_kwargs["conversation_id"] == "dify-existing-conv"


# -----------------------------------------------------------------------------
# 4. 用户隔离
# -----------------------------------------------------------------------------
def test_get_session_user_isolation(db_session, current_user, other_user, test_session):
    """其他用户不能访问本用户的 session → ChatSessionNotFoundError。"""
    with pytest.raises(ChatSessionNotFoundError):
        AiChatService.get_session(db_session, session_id=test_session.id, user=other_user)


def test_send_message_user_isolation(db_session, current_user, other_user, test_session):
    """其他用户 send → ChatSessionNotFoundError。"""
    with patch.object(DifyService, "chat_message", return_value={"answer": "x"}):
        with pytest.raises(ChatSessionNotFoundError):
            AiChatService.send_message(
                db_session,
                session_id=test_session.id,
                user=other_user,
                payload=AiChatMessageSendRequest(
                    client_request_id=uuid.uuid4(),
                    query="hi",
                ),
            )


# -----------------------------------------------------------------------------
# 5. list_messages 顺序
# -----------------------------------------------------------------------------
def test_list_messages_returns_chronological(db_session, current_user, test_session):
    """list_messages 按 created_at ASC 返回。"""
    crids = [uuid.uuid4() for _ in range(3)]
    with patch.object(DifyService, "chat_message", return_value={"answer": "x", "conversation_id": "c"}):
        for i, crid in enumerate(crids):
            AiChatService.send_message(
                db_session,
                session_id=test_session.id,
                user=current_user,
                payload=AiChatMessageSendRequest(
                    client_request_id=crid,
                    query=f"q{i}",
                ),
            )

    items, total = AiChatService.list_messages(db_session, session_id=test_session.id, user=current_user)
    assert total == 6
    assert len(items) == 6
    # 顺序：user, assistant, user, assistant, user, assistant
    assert items[0].role == "user" and items[0].content == "q0"
    assert items[1].role == "assistant"
    assert items[2].role == "user" and items[2].content == "q1"
    assert items[3].role == "assistant"
    assert items[4].role == "user" and items[4].content == "q2"
    assert items[5].role == "assistant"


# -----------------------------------------------------------------------------
# 6. 空 query 拒绝（Pydantic 层）
# -----------------------------------------------------------------------------
def test_empty_query_rejected_by_pydantic():
    """空字符串 query 被 Pydantic Field(min_length=1) 拒绝。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AiChatMessageSendRequest(client_request_id=uuid.uuid4(), query="")


# -----------------------------------------------------------------------------
# 7. user 消息幂等
# -----------------------------------------------------------------------------
def test_send_message_idempotent_replay(db_session, current_user, test_session):
    """相同 client_request_id 第二次调用 → idempotent_replay=True 且不调 Dify。"""
    crid = uuid.uuid4()
    payload = AiChatMessageSendRequest(client_request_id=crid, query="同一请求")

    fake_response = {"answer": "first reply", "conversation_id": "c-first"}
    with patch.object(DifyService, "chat_message", return_value=fake_response) as mock_chat:
        first = AiChatService.send_message(
            db_session, session_id=test_session.id, user=current_user, payload=payload,
        )
        assert first.idempotent_replay is False
        assert mock_chat.call_count == 1

        second = AiChatService.send_message(
            db_session, session_id=test_session.id, user=current_user, payload=payload,
        )
        assert second.idempotent_replay is True
        assert mock_chat.call_count == 1
        assert first.user_message.id == second.user_message.id


# -----------------------------------------------------------------------------
# 8. 同 session 并发第二个 send → 409
# -----------------------------------------------------------------------------
def test_concurrent_pending_returns_409(db_session, current_user, test_session):
    """同一 session 有 pending assistant 时，第二个 send → ChatConcurrentPendingError。"""
    now = datetime.now(tz=timezone.utc)
    expires = now + timedelta(seconds=90)
    pending_msg = AiChatMessage(
        session_id=test_session.id,
        user_id=current_user.id,
        role="assistant",
        message_type="chat",
        status="pending",
        processing_started_at=now,
        processing_expires_at=expires,
        attempt_count=1,
    )
    db_session.add(pending_msg)
    db_session.commit()

    with pytest.raises(ChatConcurrentPendingError):
        AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="并发请求",
            ),
        )


# -----------------------------------------------------------------------------
# 9. pending 超时 → stale → 允许新 send
# -----------------------------------------------------------------------------
def test_expired_lease_allows_new_send(db_session, current_user, test_session):
    """pending assistant lease 已过期 → send 自动标记 stale 并允许新请求。"""
    now = datetime.now(tz=timezone.utc)
    expired = now - timedelta(seconds=120)
    pending_msg = AiChatMessage(
        session_id=test_session.id,
        user_id=current_user.id,
        role="assistant",
        message_type="chat",
        status="pending",
        processing_started_at=expired,
        processing_expires_at=expired,
        attempt_count=1,
    )
    db_session.add(pending_msg)
    db_session.commit()

    fake_response = {"answer": "ok", "conversation_id": "c2"}
    with patch.object(DifyService, "chat_message", return_value=fake_response):
        result = AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="lease 过期后",
            ),
        )

    db_session.refresh(pending_msg)
    assert pending_msg.status == "stale"
    assert pending_msg.error_code == "PROCESSING_LEASE_EXPIRED"

    assert result.idempotent_replay is False
    assert result.assistant_message.status == "completed"


# -----------------------------------------------------------------------------
# 10. cleanup_stale_pending
# -----------------------------------------------------------------------------
def test_cleanup_stale_pending_updates_db(db_session, current_user):
    """cleanup_stale_pending 把 lease 过期的 pending assistant 标记 stale。

    注：DB 部分唯一索引 UNIQUE(session_id) WHERE role='assistant' AND status='pending'
    限制每个 session 至多一个 pending assistant。本测试使用 2 个 session：
    - session A：expired pending（应被标 stale）
    - session B：fresh pending（应保持 pending）
    """
    now = datetime.now(tz=timezone.utc)
    expired = now - timedelta(seconds=10)
    fresh = now + timedelta(seconds=90)

    # 2 个独立 session（避免同一 session 双 pending 触发 partial unique index）
    code_a = f"CHAT-TEST-{uuid.uuid4().hex[:12].upper()}"
    code_b = f"CHAT-TEST-{uuid.uuid4().hex[:12].upper()}"
    sess_a = AiChatSession(session_code=code_a, user_id=current_user.id, title="A", message_count=0)
    sess_b = AiChatSession(session_code=code_b, user_id=current_user.id, title="B", message_count=0)
    db_session.add_all([sess_a, sess_b])
    db_session.commit()
    db_session.refresh(sess_a)
    db_session.refresh(sess_b)

    stale_msg = AiChatMessage(
        session_id=sess_a.id, user_id=current_user.id,
        role="assistant", message_type="chat", status="pending",
        processing_started_at=expired, processing_expires_at=expired,
        attempt_count=1,
    )
    fresh_msg = AiChatMessage(
        session_id=sess_b.id, user_id=current_user.id,
        role="assistant", message_type="chat", status="pending",
        processing_started_at=now, processing_expires_at=fresh,
        attempt_count=1,
    )
    db_session.add_all([stale_msg, fresh_msg])
    db_session.commit()

    affected = AiChatService.cleanup_stale_pending(db_session)
    assert affected >= 1

    db_session.refresh(stale_msg)
    db_session.refresh(fresh_msg)
    assert stale_msg.status == "stale"
    assert stale_msg.error_code == "PROCESSING_LEASE_EXPIRED"
    assert fresh_msg.status == "pending"

    # Teardown
    db_session.query(AiChatSession).filter(AiChatSession.id.in_([sess_a.id, sess_b.id])).delete(synchronize_session=False)
    db_session.query(AiChatMessage).filter(AiChatMessage.session_id.in_([sess_a.id, sess_b.id])).delete(synchronize_session=False)
    db_session.commit()


# -----------------------------------------------------------------------------
# 11. Dify inputs 安全：role/locale/conversation_id 来自后端
# -----------------------------------------------------------------------------
def test_dify_inputs_ignore_frontend_role_locale(db_session, current_user, test_session):
    """Dify inputs 来自 current_user（role / locale），不接受前端伪造。"""
    fake_response = {"answer": "ok", "conversation_id": "c"}
    with patch.object(DifyService, "chat_message", return_value=fake_response) as mock_chat:
        AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="test",
                current_page="inspection_report",
            ),
        )

    inputs = mock_chat.call_args.kwargs["inputs"]
    assert inputs["role"] == current_user.role
    assert inputs["locale"] == (current_user.language or "zh-CN")
    assert inputs["current_page"] == "inspection_report"
    assert mock_chat.call_args.kwargs["user"] == f"dbops:{current_user.id}"


def test_dify_inputs_reject_unknown_current_page(db_session, current_user, test_session):
    """current_page 不在白名单时降级为 ai_chat（绝不阻塞）。"""
    fake_response = {"answer": "ok", "conversation_id": "c"}
    with patch.object(DifyService, "chat_message", return_value=fake_response) as mock_chat:
        AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="test",
                current_page="<script>alert(1)</script>",
            ),
        )
    inputs = mock_chat.call_args.kwargs["inputs"]
    assert inputs["current_page"] == "ai_chat"


# -----------------------------------------------------------------------------
# 12. AI_CHAT_ENABLED=false → 503
# -----------------------------------------------------------------------------
def test_chat_disabled_returns_503(db_session, current_user, test_session):
    """AI_CHAT_ENABLED=false → ChatFeatureDisabledError。"""
    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    object.__setattr__(s, "AI_CHAT_ENABLED", False)

    with pytest.raises(ChatFeatureDisabledError):
        AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="hi",
            ),
        )

    object.__setattr__(s, "AI_CHAT_ENABLED", True)
    get_settings.cache_clear()


# -----------------------------------------------------------------------------
# 13. Dify 未初始化 → ChatDifyUnavailableError
# -----------------------------------------------------------------------------
def test_dify_not_initialized_returns_502(db_session, current_user, test_session):
    """DifyService.is_configured() == False → ChatDifyUnavailableError。"""
    # 显式重置（覆盖 _enable_chat_and_dify 自动 init）
    DifyService.close_client()
    DifyService._client = None

    with pytest.raises(ChatDifyUnavailableError):
        AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="hi",
            ),
        )


# -----------------------------------------------------------------------------
# 14. Dify 超时 → ChatDifyTimeoutError + assistant failed
# -----------------------------------------------------------------------------
def test_dify_timeout_propagates(db_session, current_user, test_session):
    """Dify chat_message 抛 DifyTimeoutError → send_message 抛 ChatDifyTimeoutError。"""
    from app.services.dify_service import DifyTimeoutError

    with patch.object(DifyService, "chat_message", side_effect=DifyTimeoutError("read timeout")):
        with pytest.raises(ChatDifyTimeoutError):
            AiChatService.send_message(
                db_session,
                session_id=test_session.id,
                user=current_user,
                payload=AiChatMessageSendRequest(
                    client_request_id=uuid.uuid4(),
                    query="hi",
                ),
            )

    msgs = (
        db_session.query(AiChatMessage)
        .filter(AiChatMessage.session_id == test_session.id)
        .all()
    )
    assistant_failed = [m for m in msgs if m.role == "assistant" and m.status == "failed"]
    assert len(assistant_failed) >= 1
    assert assistant_failed[-1].error_code == "DIFY_TIMEOUT"


# -----------------------------------------------------------------------------
# 15. Dify HTTP 错误 → assistant status=failed + error_code 写入
# -----------------------------------------------------------------------------
def test_dify_http_error_marks_failed(db_session, current_user, test_session):
    """Dify chat_message 抛 DifyHttpError → assistant failed + error_code 写入。

    设计：HTTP 错误（非超时）落库为 failed message 返回 200，
    与 Dify Timeout（超时 → 504）不同 ——
    超时客户端可能重试，HTTP 错误则确定性失败。
    """
    from app.services.dify_service import DifyHttpError

    with patch.object(DifyService, "chat_message", side_effect=DifyHttpError("500", status_code=500)):
        result = AiChatService.send_message(
            db_session,
            session_id=test_session.id,
            user=current_user,
            payload=AiChatMessageSendRequest(
                client_request_id=uuid.uuid4(),
                query="hi",
            ),
        )

    # 不抛异常，返回的 assistant_message 应为 failed
    assert result.idempotent_replay is False
    assert result.assistant_message is not None
    assert result.assistant_message.status == "failed"
    assert result.assistant_message.error_code == "DIFY_HTTP_ERROR"
    assert result.assistant_message.error_message is not None

    # DB 验证
    db_session.refresh(result.assistant_message)
    assert result.assistant_message.status == "failed"
    assert result.assistant_message.error_code == "DIFY_HTTP_ERROR"
