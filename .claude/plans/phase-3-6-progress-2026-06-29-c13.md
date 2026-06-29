# Phase 3.6 AI Copilot — C13 实施进度（2026-06-29）

> 任务来源：feature-dev 续做 C13（plan §5.2 + §7 + §20）
> HEAD：`feature/phase-3.6-ai-copilot`
> 上游：C12 commit `6997359`（AiSqlPreviewService + /ai/sql/preview + 22 测试）

---

## 1. 范围

按 plan §5.2（Dify Code 节点 JSON 解析）+ §7（前端 SqlPreview 页）+ §20（端到端验证）落地三件套：

1. **Backend Layer 1**：`SqlSafetyService.layer1_precheck_question()` —— Dify SQL Generator workflow 之外的"前置安全网"，对用户自然语言问题做关键词预检，命中即拒绝（不调 Dify、不消耗 quota）。
2. **Backend Dify Code 节点 JSON 解析**：`_parse_code_node_payload()` —— 容忍 Dify 多种返回形态（dict / string-JSON / markdown sql 块 / 缺字段 / 空），最大程度拿到结构化字段（generated_sql、warnings、confidence、table_refs、explanation）。
3. **Frontend SqlPreview 页面**：`views/ai/SqlPreview.vue` + `api/ai.ts::sqlPreview()` —— 三段式表单（instance / database / user_question）→ 调用 → 渲染状态徽章 + approved_sql + "接受并写回会话"按钮（落 ai_chat_message）。

---

## 2. 文件变更（11 件）

### Backend（6 件）

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/services/sql_safety_service.py` | MOD +120 | 新增 `SqlSafetyService.layer1_precheck_question(user_question) -> dict`：EN 用 `\b` word-boundary（避开 `update_time` / `dropbox` 这类标识符），CN 用 substring；返回 `{allowed, reason, matched_keyword, matched_pattern, error_code}` |
| `backend/app/services/ai/ai_sql_preview_service.py` | MOD +180 | 类常量 `LAYER1_PRECHECK_ENABLED=True`；Step 3.5 在 schema snapshot 之后 / Dify 之前插入 Layer 1 预检；`_parse_code_node_payload` 串接 5 种解析路径；Dify 调用块改用解析函数；warnings 持久化到审计的 `_preview_warnings` 透传 |
| `backend/app/api/ai.py` | MOD +5 | `preview_sql` 响应从 audit 读取 `_preview_warnings`（不再硬编码 `[]`）|
| `backend/tests/test_sql_safety_service.py` | MOD +165 | `TestLayer1PrecheckQuestion` 21 例：空 / 全空白 / 安全 / EN 11 关键词 / CN 12 关键词 / word-boundary 边界 / dict 结构完整 |
| `backend/tests/test_ai_sql_preview_service.py` | MOD +365 | `TestLayer1Integration` 4 例（EN 命中不入 Dify / CN 命中 / miss 调 Dify / 关闭开关 bypass）+ `TestCodeNodePayload` 10 例（5 种解析路径 + 缺字段 + 非 dict + warnings 类型转换 + 嵌套 generated_sql dict）+ `TestCodeNodePayloadIntegration` 3 例（warnings 合入审计 / 缺 warnings → 空 list / Dify 无 SQL + warnings → rejected） |
| `backend/.env` | MOD +5 | （gitignored）追加 `AI_SQL_PREVIEW_ENABLED=true` + `DIFY_SQL_WORKFLOW_KEY=app-veffBzDsQVqHpYbDgvZOr1a2` |

### Frontend（5 件）

| 文件 | 类型 | 说明 |
|---|---|---|
| `frontend/src/types/ai.ts` | MOD +72 | `AiSqlPreviewRequest` / `AiSqlPreviewResponse` 接口（18 字段） |
| `frontend/src/api/ai.ts` | MOD +25 | `aiApi.sqlPreview()` 方法 + 完整 docstring（plan §11 错误码 404/409/422/502/503/504） |
| `frontend/src/router/index.ts` | MOD +7 | 路由 `/ai/sql/preview` → lazy import `views/ai/SqlPreview.vue`，meta `{title: 'SQL 生成器', parent: 'AI 助手'}` |
| `frontend/src/views/Layout.vue` | MOD +20 | `aiMenuItem` 改 computed parent + children；新增 `sqlPreviewEnabled` ref；onMounted 拉 `caps.sql_preview_enabled`；子菜单：`AI 对话`（chat_enabled） + `SQL 生成器`（sql_preview_enabled） |
| `frontend/src/views/ai/SqlPreview.vue` | NEW 410 | OpsPage 完整三件套：表单 → Layer 1 前端 hint（EN regex + CN 关键词黄色警告）→ "生成 SQL" 按钮 → 状态徽章（PASSED 绿 / REJECTED 红）→ metadata grid → errors 红条 + warnings 黄条 → approved_sql `<pre><code>` + 复制 → "接受并写回会话"按钮（passed only，新建 session + 发消息 + safeUuid） |

---

## 3. 关键技术点

### 3.1 Layer 1 关键词策略

```
EN（word-boundary \b）：DROP | DELETE | UPDATE | INSERT | TRUNCATE | ALTER |
                      CREATE | GRANT | REVOKE | MERGE | EXEC | EXECUTE | CALL
CN（substring）：删除 | 删掉 | 写入 | 插入 | 截断 | 建表 | 建库 | 建索引 |
                建视图 | 授权 | 撤销 | 改结构 | 改字段
```

**为什么 EN 用 `\b`**：避免把 `update_time` / `dropbox` / `delete_flag` 这类合法标识符误命中。
**为什么 CN 用 substring**：中文没有词边界，substring + 短词列表足够收紧。

### 3.2 Layer 1 在流程里的位置（Step 3.5）

```
Step 1: capabilities/feature gate        (503 if disabled)
Step 2: instance 校验 + db_type 派生      (404 / 422)
Step 3: schema snapshot 就绪检查          (409)
Step 3.5: Layer 1 正则预检 ★ NEW         (rejected audit, Dify 不调)
Step 4: Dify sql-generator workflow       (502 / 504)
Step 5: AST 校验 (C11)                    (rejected audit if AST fail)
Step 6: ai_sql_audit 落库                 (passed / rejected)
```

**为什么不在 Step 1**：那时还不知道 db_type_code / snapshot_id，写 rejected 审计缺上下文。
**为什么不在 Step 4 之前最前面**：schema snapshot 检查之后做，写审计时 snapshot_id 字段可以填。

### 3.3 Code 节点 JSON 解析（5 种路径级联）

```python
def _parse_code_node_payload(dify_resp) -> dict:
    outputs = dify_resp.get("data", {}).get("outputs", {})
    # 路径 1：已是 dict（理想）
    if isinstance(outputs, dict):
        return _extract_fields(outputs)
    # 路径 2：字符串 JSON
    if isinstance(outputs, str):
        stripped = outputs.strip()
        if stripped.startswith("{"):
            return _extract_fields(json.loads(stripped))
        # 路径 3：markdown ```sql``` 块
        if "```sql" in stripped:
            sql = _extract_sql_block(stripped)
            return _extract_fields({"generated_sql": sql})
        # 路径 4：纯文本 fallback
        return _extract_fields({"generated_sql": stripped})
    # 路径 5：缺失 / 空 → 空 dict（后续 AST 校验会拒绝）
    return {}
```

### 3.4 BE-bug1（沿用 C5+1 修复）

不再使用 Pydantic `Field(alias="metadata")`，避免与 SQLAlchemy `Base.metadata` 冲突；改用普通字段名 `metadata_json` + `from_attributes=True`。本次 C13 没新引入此坑（响应 schema 全是新建），但保持警觉。

---

## 4. 验证

### 4.1 单元测试

```bash
cd backend
pytest tests/test_sql_safety_service.py::TestLayer1PrecheckQuestion -v        # 21/0
pytest tests/test_ai_sql_preview_service.py::TestLayer1Integration -v         #  4/0
pytest tests/test_ai_sql_preview_service.py::TestCodeNodePayload -v           # 10/0
pytest tests/test_ai_sql_preview_service.py::TestCodeNodePayloadIntegration -v # 3/0
# 小计 +38 全绿
```

### 4.2 verify.sh

```bash
bash scripts/ai/verify.sh
# passed=468 failed=0 skipped=2  (含 C1-C12 全部历史测试 + C13 新增 38 例)
```

### 4.3 Live dev 库 / curl 完整链路

```bash
# 1) capabilities 灰度
curl -s http://localhost:60801/api/v1/ai/capabilities
# → {"chat_enabled":true,"sql_preview_enabled":true,"sql_supported_db_types":["POSTGRESQL"],...}

# 2) POST /ai/sql/preview (SQLSERVER instance 964 → POSTGRESQL-only)
curl -s -X POST http://localhost:60801/api/v1/ai/sql/preview \
  -H 'Content-Type: application/json' \
  -d '{"instance_id":964,"user_question":"show me top 10 users"}'
# → HTTP 422 {"detail":"Unsupported db_type 'SQLSERVER' for sql_preview (POSTGRESQL only)"}
# ✓ 验证：Step 2 (db_type gate) 在 Layer 1 之前生效，能力声明对齐
```

**限制说明**：dev 库无 PostgreSQL 实例（仅 SQLSERVER/ORACLE），`sql_supported_db_types=["POSTGRESQL"]` 因此命中 Step 2 422，无法做"通过 preview → AST 通过 → 落 passed audit"的 live 全链路。

**补偿验证**：38 个单元测试覆盖了所有代码路径（Layer 1 EN/CN 命中 + miss、Code 节点 5 种解析路径、passed/rejected audit 构造、warnings 持久化）。AST 通过后的完整链路将在 C14（SQL Execute 接入）阶段用一个临时注册 POSTGRESQL capabilities flag 在本地手动验证。

---

## 5. Layer 1 vs Layer 2/3 职责边界

| 层 | 实现 | 触发时机 | 触发频率 | 失败后果 |
|---|---|---|---|---|
| **Layer 1**（本次 NEW）| 正则（EN \b + CN substring）| Step 3.5（调 Dify 前）| 每次 preview | rejected audit，不调 Dify，省 quota |
| Layer 2 | `SqlSafetyService` 关键词 + pattern 集合 | Step 4（Dify 返回后）| 仅 Dify 命中时 | rejected audit |
| Layer 3 | `SqlSafetyService.validate_with_ast`（C11 sqlglot）| Step 5 | 通过 Layer 1/2 后 | rejected audit，权威 |

**Layer 1 的价值**：
- 节省 Dify 调用 quota（每分钟限流很严）
- 减少 Dify 工作流冷启动延迟（典型 2-5s）
- 给用户即时反馈（输入框下方黄色提示）

---

## 6. 影响范围

| 维度 | 影响 |
|---|---|
| **page** | `views/ai/SqlPreview.vue`（NEW）+ `views/Layout.vue`（菜单子项）+ `views/ai/Chat.vue`（无改动，但 capabilities 拉取逻辑共用）|
| **api** | `POST /api/v1/ai/sql/preview`（已有端点行为扩展：Layer 1 + Code 节点解析）；`GET /api/v1/ai/capabilities`（无变化）|
| **service** | `SqlSafetyService`（新增 public 方法）、`AiSqlPreviewService`（流程插 Step 3.5 + Code 节点解析 + warnings 透传）|
| **model** | 无新表（`ai_sql_audit` 在 C12 已建，本轮不扩字段；warnings 走 `_preview_warnings` transient attr → 不入库）|
| **table** | 无 DDL |
| **env** | `AI_SQL_PREVIEW_ENABLED` + `DIFY_SQL_WORKFLOW_KEY`（仅 backend/.env，gitignored）|
| **前端 types** | `AiSqlPreviewRequest` / `AiSqlPreviewResponse`（NEW）|

---

## 7. 文档同步

| 文档 | 是否更新 | 原因 |
|---|---|---|
| `docs/10-module-map.md` | 待更新（C13 commit 后）| 标注 AI Copilot 子模块含「SQL 生成器」（C13 已加 views/ai/SqlPreview.vue）|
| `docs/30-runbook.md` | 已 pre-update | 加 SQL Preview 故障排查入口（404/409/422/502/503/504）|
| `docs/contracts/api-inventory.md` | 待更新 | 加 POST /ai/sql/preview 端点（含错误码表）|
| `docs/db/ddl-history.md` | 不更新 | 本轮无 DDL 变更 |
| `docs/db/schema-snapshot.md` | 不更新 | 无结构变化 |
| `docs/40-tech-debt.md` | 待评估 | Layer 1 关键词列表 hardcode 中文，C14+ 可考虑 i18n |

---

## 8. 风险 / 后续

### 风险

1. **Layer 1 误命中**：CN substring 可能误命中合法问题（如"如何安全删除索引重建方案"含"删除"）。**缓解**：前端输入框下方显示 Layer 1 关键词提示 + 后端允许 `LAYER1_PRECHECK_ENABLED=false` 旁路。
2. **Dify Code 节点 schema 演进**：Dify 升级 / Prompt 调整可能改变 outputs 结构。**缓解**：`_parse_code_node_payload` 已覆盖 5 种路径，缺字段默认安全 fallback。
3. **POSTGRESQL-only**：当前 capabilities 仅放行 POSTGRESQL。**后续**：C20+ 接 MSSQL / Oracle dialect 映射（plan §5.4 范围）。

### 后续（C14+ 路线图）

| 任务 | 来源 | 状态 |
|---|---|---|
| **C14 SQL Execute API + Chat integration** | plan §6 + §8 | 下轮起手 |
| **C15 Chat 集成 SqlPreview**（消息流内"SQL Preview"按钮）| plan §7.3 | 紧随 C14 |
| **C16 Inspection AI Analyze 端点** | plan §9 | P2 排期 |
| **C17 Report AI Export 端点** | plan §10 | P2 排期 |
| **C18 SSE / Stream** | plan §11 stream_enabled | P3 |
| **C19 Dify App Prompt 治理** | plan §13 | P2 |
| **C20+ 跨方言**（MSSQL / Oracle dialect）| plan §5.4 | P3 |

---

## 9. Commit

待提交（11 文件 + 1 plan 文件）：

```bash
git add backend/app/api/ai.py \
        backend/app/services/ai/ai_sql_preview_service.py \
        backend/app/services/sql_safety_service.py \
        backend/tests/test_ai_sql_preview_service.py \
        backend/tests/test_sql_safety_service.py \
        frontend/src/api/ai.ts \
        frontend/src/router/index.ts \
        frontend/src/types/ai.ts \
        frontend/src/views/Layout.vue \
        frontend/src/views/ai/SqlPreview.vue \
        .claude/plans/phase-3-6-progress-2026-06-29-c13.md

git commit -m "feat(phase-3.6): C13 — Layer 1 正则预检 + Dify Code 节点 JSON 解析 + SqlPreview.vue + 38 tests

backend:
- SqlSafetyService.layer1_precheck_question: EN \\b word-boundary + CN substring
- AiSqlPreviewService: Step 3.5 Layer 1; _parse_code_node_payload 5 路径
- 38 新测试: TestLayer1PrecheckQuestion 21 + TestLayer1Integration 4 + TestCodeNodePayload 10 + TestCodeNodePayloadIntegration 3
- .env: AI_SQL_PREVIEW_ENABLED=true + DIFY_SQL_WORKFLOW_KEY (gitignored)

frontend:
- types/ai.ts: AiSqlPreviewRequest + AiSqlPreviewResponse
- api/ai.ts: aiApi.sqlPreview() + plan §11 错误码 docstring
- router: /ai/sql/preview
- Layout.vue: aiMenuItem parent+children, caps.sql_preview_enabled 灰度
- views/ai/SqlPreview.vue: 三段表单 + Layer 1 前端 hint + 状态徽章 + approved_sql + 接受并写回

verify: 468/0/2 + live capabilities ok + 422 db_type gate
plan: .claude/plans/phase-3-6-progress-2026-06-29-c13.md

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 10. 经验沉淀（进 MEMORY）

- **Layer 1 必须在 Step 3.5**：snapshot 检查之后、调 Dify 之前——拿到完整 audit 上下文，又能省 Dify quota。
- **Code 节点解析必须容错 5+ 形态**：Dify 升级 / Prompt 调整会让 outputs 形态漂移，缺字段默认安全 fallback 是底线。
- **前端 Layer 1 hint 与后端正则必须一致**：EN 用 `\b`，CN 用 substring；展示给用户避免误操作。
- **`safeUuid()`**：HTTP+IP 非 secure context 下 `crypto.randomUUID` 不可用，统一走 `frontend/src/utils/uuid.ts::safeUuid()`。
- **dev 库无 PostgreSQL 实例**：live 验证 POSTGRESQL 路径只能靠 unit + AST 单元测试 + 临时 caps flag；完整链路放 staging。