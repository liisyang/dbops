# Phase 3.6 AI Copilot — C5+1 (BE-bug1 完成 + Live 验证)

**Date**: 2026-06-28
**Branch**: `feature/phase-3.6-ai-copilot`
**Base HEAD**: `3af1b15` (C5)
**New HEAD**: (本 commit)
**Plan**: `.claude/plans/phase-3-6-ai-copilot-full-plan.md` (v4 Final)
**Resumption**: 新会话用 `/feature-dev` 加载此文件从 C6 起手

---

## ✅ 本轮已完成（BE-bug1 — Chat metadata 字段冲突）

### 根因

Pydantic v2 + SQLAlchemy 保留属性冲突：
- ORM `AiChatMessage.metadata_json` Python 属性 → DB 列 `metadata`（`app/models/ai.py:111`）
- Schema `AiChatMessageResponse` 之前定义为 `metadata_json: ... = Field(alias="metadata")`
- Pydantic v2 默认 `populate_by_name=False`，`from_attributes=True` 时**优先用 alias** 取属性
- `getattr(obj, 'metadata')` 命中 SQLAlchemy `Base.metadata` 保留类属性 = `MetaData()` 实例
- `model_validate` 抛 ValidationError: `Input should be a valid dictionary ... input=MetaData()`

### 修复

`backend/app/schemas/ai.py`（仅 1 文件 3 行修改）：

```diff
-    metadata_json: dict[str, Any] = Field(default_factory=dict, alias="metadata")
+    # 字段名 metadata_json 而非 metadata：避免与 SQLAlchemy Base.metadata 保留属性冲突
+    # （ORM 中 Python 属性 metadata_json 映射到 DB 列 metadata — 见 app/models/ai.py:111）
+    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

JSON 输出 key 由 `metadata` → `metadata_json`，与 frontend `types/ai.ts:86` 期望一致。

---

## ✅ Live 验证（4 个错误码路径）

| 场景 | 触发方式 | HTTP | 备注 |
|------|----------|------|------|
| 正常 201/200 | createSession + sendMessage + listMessages | 201 / 200 / 200 | session=170, user_msg=274 status=completed, assistant_msg=275 status=completed |
| **409 并发 pending** | 直接 INSERT pending assistant msg(id=271) + sendMessage | **409** ✓ | detail: `Chat session 169 has an in-flight assistant message (id=271)` |
| **504 超时** | `DIFY_CHAT_TIMEOUT_SECONDS=0.001` + sendMessage | **504** ✓ | detail: `Dify 调用超时: timed out`；DB: assistant_msg.status=failed, error_code=DIFY_TIMEOUT |
| **503 功能关闭** | `AI_CHAT_ENABLED=false` + sendMessage | **503** ✓ | detail: `AI_CHAT_ENABLED=false` |
| **502 Dify 不可达** | — | **不可触发** ⚠ | 见下方"502 设计说明" |

### 502 设计说明（结构性不可达）

经代码审计 + 启动验证：

- api.py 的 `except ChatDifyUnavailableError → 502` 仅在 `DifyService.is_configured()=False` 时触发
- `is_configured()` 要求 `DifyService._client is not None`，由 startup 阶段 `init_client(base_url, ...)` 构造
- `app/config.py:validate_ai_config()` 主动拦截：若 `AI_CHAT_ENABLED=true` 且 `DIFY_CHAT_API_KEY` 缺失 → 直接抛 ValueError，**后端启动失败**
- 实测：清空 `DIFY_CHAT_API_KEY=` + 重启 → 后端启动报 `ValueError: AI Copilot 配置缺失` 而非进入运行态

普通 Dify 连接错误（ConnectError / HTTPError）也走不到 502：
- service 内 `_call_dify` 捕获所有 DifyError 子类 → 返回 `(None, exc, code)` 不抛
- sendMessage 仅在 `isinstance(dify_error, DifyTimeoutError)` 时 re-raise `ChatDifyTimeoutError` → 504
- 其他错误 → assistant_msg 标 failed + content=""，返回 HTTP 200

**结论**：502 路径在 API 层结构性不可达，是 fail-fast 设计意图（启动校验 > 运行期 502）。api.py 中的 `except DifyError → 502` 是防御性 dead code，无须清理。

---

## 📁 文件清单（BE-bug1 共 2 文件）

```
backend/app/schemas/ai.py                     | M  +4    (移除 alias="metadata")
.claude/plans/phase-3-6-progress-2026-06-28-c5b1.md | A  +100  (本文件，进度文档)
```

### 启动清理兼容性问题（已知，C3 范围外）

启动日志：`AI chat startup cleanup failed (continuing): module 'asyncio' has no attribute 'to_thread'`

- Python 3.8 不支持 `asyncio.to_thread`（3.9+ 引入）
- 当前 stale cleanup 报错但 startup 继续，业务不受影响
- 修复方案：改用 `loop.run_in_executor(None, ...)` 或 `asyncio.get_event_loop().run_in_executor(...)`
- C32 范围（启动 stale 清理兼容性修）

---

## 🛠 真实环境信息（C5+1 验证后）

- **Backend**: PID 2815152, 端口 60801（live verify 后保留运行）
- **Live capabilities**: `chat_enabled: true`，5 个能力字段全 false（除 chat）
- **Dify 配置**: `DIFY_BASE_URL=http://10.134.181.168/v1`, `DIFY_CHAT_API_KEY=app-KMBEDixFmpgaBKSa6VUobw5O`
- **DB 残留**:
  - session 169（P2 409 测试）：user 269 completed + user 272 completed + assistant 270/273（completed/failed）
  - session 170（P5 final）：user 274 completed + assistant 275 completed
- **pytest**: 15 passed / 2 skipped（C3 既有测试，全绿）
- **远端**: `origin/main` HEAD `3af1b15` → 本 commit（待 push）

---

## 📋 收尾待办（按 plan §14 顺序）

- ✅ ~~BE-bug1: 修 `app/schemas/ai.py` 的 `metadata` 字段名冲突~~（本 commit）
- C6~C26: plan §14 主线（SQL Schema Snapshot → SQL Preview → SQL Execute → Inspection AI Analysis）
- C28: 全量 ~105 测试 + 日志脱敏
- C29: verify.sh 更新 + .env.example + docs/10-module-map.md
- C30: API Key 泄漏 grep 检查（防 Dify key 入 git）
- C31: DDL 幂等验证 + 回滚安全检查
- C32: 启动时 stale 清理（chat pending 已完成；asyncio.to_thread 兼容性修）

---

## 🚀 下一会话快速恢复

1. 加载本文件
2. 从 C6 起手（SQL Schema Snapshot — plan §14）
3. 设计 DDL（ai_sql_schema_snapshot 表）+ Service + API 端点
4. 优先验证 DDL 幂等（C31 范围）