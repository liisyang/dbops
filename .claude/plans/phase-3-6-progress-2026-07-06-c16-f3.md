# C16-F3 工作进度 — 2026-07-06

> **状态**: ✅ 已完成（Commit 1 ✅ + Commit 2 ✅ + Commit 3 ✅ 全部闭环并推送）
> **起点**: `.claude/plans/phase-3-6-progress-2026-07-06-c16-f2.md` §2
> **上游 commit**: `e965ae6` (C16-F2 result_message_id E2E)
> **完整设计**: `.claude/plans/abundant-beaming-hamster.md`
> **分支**: `feature/phase-3.6-ai-copilot`
> **当前 HEAD (dbops)**: `<commit-3-sha>` (commit 3 — 测试+文档+记忆+验证)
> **当前 HEAD (ansible-playbooks)**: `000854e` (commit 1)
> **跨会话记忆**: `~/.claude/projects/-home-lisiyang-dbops/memory/phase-3-6-c16-f3-completed-2026-07-06.md`

---

## 0. 跨会话说明

新会话从本 plan 文件继续执行 Commit 3。
Commit 1 (DDL/Builder/Ansible) + Commit 2 (运行时层) 已推送并验证可导入可路由可回归 159 测试。
剩余 Commit 3 全为测试 + 文档 + 记忆 + 验证 纯增量工作。

Commit 3 已完成（2026-07-07）：

- 4 个测试文件 65 cases 全过（builder 15 + callback 21 + snapshot 20 + context 9）
- 5 个 docs 更新（tech-debt F13 + module-map + api-inventory 4 端点 + runbook §8.5 + plan §4A）
- 1 个 memory file + MEMORY.md 索引行
- verify.sh 0 失败 + vue-tsc 0 错 + C8/C10/C14 回归 159 全过

---

## 1. 已完成 ✅

### Commit 1 (2026-07-06 推送)

| # | 文件 | 状态 | 备注 |
|---|------|------|------|
| 1 | `backend/app/services/ai/sql_templates/postgresql/pg_object_metadata.sql` | ✅ dbops `93499a1` | 5 段 UNION ALL：table/view/index/function/constraint |
| 2 | `backend/db/dbops_phase3_6b0_ai_object_metadata.sql` | ✅ dbops `93499a1` | 21 字段 / 2 FK / 4 CHECK / 5 索引 / partial unique / 幂等 |
| 3 | `backend/db/rollback_phase3_6b0_ai_object_metadata.sql` | ✅ dbops `93499a1` | DROP TABLE IF EXISTS CASCADE |
| 4 | `backend/app/models/ai.py` | ✅ dbops `93499a1` (+173) | `AiObjectMetadataSnapshotStatus` + `AiObjectMetadataSnapshot(DbopsAssetBase)` 类 |
| 5 | `backend/app/services/check_item_builder_registry.py` | ✅ dbops `93499a1` (+157) | `_AiObjectMetadataBuilder` + `register("DB_OBJECT_METADATA", ...)` |
| 6 | `ansible-playbooks/playbooks/roles/db_object_metadata_collect/tasks/main.yml` | ✅ ansible-playbooks `000854e` (NEW 188 行) | 镜像 `db_schema_metadata_collect`；hardcode `check_code='DB_OBJECT_METADATA'` + `business_domain='ai_object_metadata'` + `max_bytes=1048576` + `phase='3.6B0.F3'` + `source='dbops.ai.sql_templates.postgresql.pg_object_metadata'` |
| 7 | `ansible-playbooks/playbooks/dbops_collector_generic.yml` | ✅ ansible-playbooks `000854e` (+30) | line 124-126 `db_python_collect_check_codes` 列表追加 `'DB_OBJECT_METADATA'`；line 215 后追加新路由块 `Route db_object_metadata_collect items` (7 条件 + 两阶段 gate) |

### Commit 2 (2026-07-06 推送)

| # | 文件 | 状态 | 行数 | 备注 |
|---|------|------|------|------|
| 8 | `backend/app/schemas/ai.py` | ✅ dbops `6e071e9` | +115 | 5 个 Pydantic 模型 (collect request/response, snapshot item, list, context) |
| 9 | `backend/app/services/ai/ai_object_metadata_callback_service.py` | ✅ dbops `6e071e9` | +499 (NEW) | `save_snapshots` 镜像 C9 schema callback;两阶段发布 + 1MB 截断 + SHA-256 + 5 类对象计数 |
| 10 | `backend/app/services/ai/ai_object_metadata_snapshot_service.py` | ✅ dbops `6e071e9` | +423 (NEW) | trigger + status + history + get_published_object_metadata + cleanup_running_timeouts + 5 异常类 |
| 11 | `backend/app/services/collector_service.py` | ✅ dbops `6e071e9` | +29 | handle_callback 加 `ai_object_metadata` 分发 (与 ai_schema/ai_sql 同款 try/except) |
| 12 | `backend/app/main.py` | ✅ dbops `6e071e9` | +31 | startup lifespan 加 object metadata cleanup hook (复用 AI_SQL_PREVIEW_ENABLED gate) |
| 13 | `backend/app/api/ai.py` | ✅ dbops `6e071e9` | +197 | 4 端点 (collect/status/history/context) + 异常别名 import (4 个 `ObjectMetadata*Error` 别名避免与 C10 冲突) |
| 14 | `backend/app/services/ai/ai_schema_context_service.py` | ✅ dbops `6e071e9` | +65 | build_schema_context 返回 dict 加 `object_metadata` 字段 (lazy import, 8000 字符 preview, try/except 兜底) |

**Commit 2 验证证据**：
- 159 既有 C8/C10/C14 测试无回归（`pytest tests/test_ai_schema_metadata_builder.py tests/test_ai_schema_snapshot_callback_service.py tests/test_ai_schema_snapshot_service.py tests/test_ai_schema_context_service.py tests/test_ai_sql_*.py -q`）
- 4 个新 object-metadata 路由注册成功（`router.routes` 计数 16，包含 4 个新路由）
- 5 个 service exception 全部 importable（`AiObjectMetadataSnapshotError` 基类 + 4 子类）
- AST parse 9/9 files OK

---

## 2. 剩余工作 ❌

### 2.1 Commit 1（DDL + ORM + SQL + Builder + Ansible）

**全部完成并推送** — 跨 dbops `93499a1` + ansible-playbooks `000854e`。

### 2.2 Commit 2（运行时层 ~1200 行）

**全部完成并推送** — dbops `6e071e9`（7 files / +1359 lines，超 plan 估算的 +1200 因为 callback/service 实测更完整）。

### 2.3 Commit 3（测试 + 文档 + 记忆 + 验证）— 新会话从这开始

| # | 文件 | 操作 | 行数 | 备注 |
|---|------|------|------|------|
| 17 | `backend/tests/test_ai_object_metadata_builder.py` | NEW | ~250 (10 cases) | 复用 C8 test_ai_schema_metadata_builder.py fixture 风格 (5 fixture: `_make_credential/_make_instance/_make_server/_make_dbtype/_session_with_single_asset` + MagicMock) |
| 18 | `backend/tests/test_ai_object_metadata_callback_service.py` | NEW | ~350 (12 cases) | 缺 run_id / 未知 run_id / 空 rows / 5 类对象各 1 case / DDL 拼接 / 1MB 截断 / SHA-256 正确 / staging 翻 false / 幂等 upsert / status 完整性 |
| 19 | `backend/tests/test_ai_object_metadata_snapshot_service.py` | NEW | ~250 (10 cases) | trigger 创建 staging / 已 running 拒绝 / dispatch 正确 / status 字典 / status not found / history 过滤 / history 分页 / published latest / published 不存在 / cleanup_running_timeouts |
| 20 | `backend/tests/test_ai_object_metadata_context_integration.py` | NEW | ~150 (8 cases) | 缺 snapshot 时不出现 / 有 snapshot 时注入 / dict 必备键 / sha256 匹配 / counts 匹配 / published_at isoformat / dify payload 包含 / 现有 schema_context 键未变 |
| 21 | `docs/40-tech-debt.md` | UPDATE | +10 | §7 F-list 追加 F13 行（不复用 F3 编号） |
| 22 | `docs/10-module-map.md` | UPDATE | +5 | §2 章节 44 追加 C16-F3 描述 |
| 23 | `docs/contracts/api-inventory.md` | UPDATE | +30 | 4 个新端点 (POST/GET status/GET history/GET context) |
| 24 | `docs/30-runbook.md` | UPDATE | +40 | §7 增加新排障入口 (object metadata 采集 stuck / TRUNCATED / 1MB cap) |
| 25 | `.claude/plans/phase-3-6-ai-copilot-full-plan.md` | UPDATE | +30 | §4 追加 F3 段落 |
| 26 | `.claude/plans/phase-3-6-progress-2026-07-06-c16-f3.md` (本文件) | UPDATE | — | 标记 commit 3 完成 + 终态 |
| 27 | `~/.claude/projects/-home-lisiyang-dbops/memory/phase-3-6-c16-f3-completed-2026-07-06.md` | NEW | +30 | 跨会话记忆 (3 commit SHAs + 4 routes + 4 tests 文件 + 5 docs) |
| 28 | `~/.claude/projects/-home-lisiyang-dbops/memory/MEMORY.md` | UPDATE | +1 | 索引行 |
| 29 | 1 个 git commit + push | — | dbops 端 | Commit 3 单包提交（测试+docs+memory 一起） |

**新会话起手指令** (给新会话的 Claude):
```
/feature-dev  读 .claude/plans/phase-3-6-progress-2026-07-06-c16-f3.md §2.3
→ 写 4 个 test 文件 → pytest 40/40 + 既有 C8/C10/C14 回归
→ 改 5 个 docs → 写 memory + MEMORY.md
→ verify.sh 0 失败 + vue-tsc 0 错
→ commit 3 单包 (dbops) → push
```

---

## 3. 验证清单（端到端）

新会话执行 Commit 3 完成后，必须跑：

```bash
cd /home/lisiyang/dbops
bash scripts/ai/verify.sh                                     # 0 失败
cd backend && pytest tests/test_ai_object_metadata_*.py -v   # 40/40 通过
cd backend && pytest tests/test_ai_schema_*.py -v             # C8 回归全过
cd backend && pytest tests/test_ai_sql_*.py -v                # C14 回归全过
cd frontend && npx vue-tsc --noEmit                          # 0 错
psql -h 10.134.185.85 -U dbops -d dbops -f backend/db/dbops_phase3_6b0_ai_object_metadata.sql  # 成功（幂等）
psql -c "\d+ dbops.ai_object_metadata_snapshot"              # 看到 5 索引 + 2 FK + 4 CHECK
```

---

## 4. live E2E 验证（dev 库 PG 实例就绪后做）

PG 实例 `10.134.185.228` (id=965, credential=7) 已注册（C16-F1 阶段）：

```bash
# 触发采集
curl -X POST -H "Authorization: Bearer <token>" \
  http://10.134.185.85:51088/api/v1/ai/sql/object-metadata/965/collect \
  -d '{"schema_name":"public"}'
# 期望 202 + collector_run_id

# 5 分钟内 callback 落库
psql -c "SELECT id, status, is_current, length(object_ddl_text), table_count, view_count, index_count, function_count, total_object_count FROM dbops.ai_object_metadata_snapshot WHERE instance_id=965 ORDER BY id DESC LIMIT 3"
# 期望看到 status=success, is_current=true, total_object_count > 0

# context 端点验证
curl -H "Authorization: Bearer <token>" \
  "http://10.134.185.85:51088/api/v1/ai/sql/object-metadata/965/context?schema_name=public"
# 期望非空 object_ddl_text

# schema context 集成验证
curl -H "Authorization: Bearer <token>" \
  "http://10.134.185.85:51088/api/v1/ai/sql/schema-snapshots/965/context"
# 期望 JSON 含 object_metadata 字段
```

---

## 5. 关键设计决策（F3 全程遵守）

| 决策 | 选择 | 理由 |
|------|------|------|
| DB 方言 | PostgreSQL only | 与 C8 一致，三方言合并 C16-F0 |
| 落表 | 独立 `ai_object_metadata_snapshot` | 概念独立（DDL vs column rows） |
| 路由 | `business_domain='ai_object_metadata'` | 独立 callback 路径 |
| run_type | `ai_object_metadata` | 与 `ai_schema` 并列 |
| SQL 范围 | table + view + materialized_view + index + function/procedure + constraint | AI SQL 生成必需 |
| Capabilities | 不增加 capability flag | 复用 `AI_SQL_PREVIEW_ENABLED` gate |
| 编号冲突 | docs §7 F-list 追加 F13 | F3 已被 "前端 sql_preview_link" 占用 |
| 提交方式 | 拆 3 个 commit | ~3000 行单一 commit 风险高 |
| Partial unique | 加 schema_name 维度 | DDL 概念上需 schema 粒度（与 C8 不同） |
| 1MB 截断 | callback service 兜底 | 避免 DDL 文本超 TOAST |
| TTL | 24h（`AI_OBJECT_METADATA_TTL_HOURS`） | 与 C8 一致 |

---

## 6. 风险 + Rollback

| 风险 | 缓解 |
|------|------|
| DDL 行超 TOAST | callback 1MB 截断 + `error_message='TRUNCATED'` |
| Dify 上下文超 token | `object_ddl_text_preview` 限 8000 字符注入 |
| Builder 误注册到非 PG | `_SUPPORTED_DB_TYPES` frozenset 守卫 + skipped item |
| staging 永久卡住 | `cleanup_running_timeouts` startup hook 兜底（10 min） |
| 同 (instance, schema) 并发 trigger | `AiObjectMetadataAlreadyRunning` 异常 409 |
| collector_service handle_callback 影响 C8 路径 | 新 ai_object_metadata 走独立 dispatcher；现有分支不变 |

**Rollback 步骤**（按 commit 倒序）：

```bash
# commit 3 失败（仅 docs + tests）
git revert <commit-3-sha> --no-edit && git push

# commit 2 失败（业务逻辑）
git revert <commit-2-sha> --no-edit && git push
psql -h 10.134.185.85 -U dbops -d dbops -c \
  "UPDATE dbops.ai_object_metadata_snapshot SET status='failed' WHERE status IN ('pending','running');"

# commit 1 失败（DDL + Builder + Ansible）
git revert <commit-1-sha> --no-edit && git push
psql -h 10.134.185.85 -U dbops -d dbops -f \
  /home/lisiyang/dbops/backend/db/rollback_phase3_6b0_ai_object_metadata.sql
```

---

## 7. 关键文件位置速查

- 完整设计: `.claude/plans/abundant-beaming-hamster.md` (~1000 行)
- 上游 commit: `e965ae6` (C16-F2)
- 起点 plan: `.claude/plans/phase-3-6-progress-2026-07-06-c16-f2.md`
- 父 handoff: `.claude/plans/phase-3-6-progress-2026-07-06-c16-handoff.md`
- C8 实现参考: `backend/app/services/check_item_builder_registry.py:964-1116`
- C9 callback 参考: `backend/app/services/ai/ai_schema_snapshot_callback_service.py`
- C10 service 参考: `backend/app/services/ai/ai_schema_snapshot_service.py`
- C10 API 参考: `backend/app/api/ai.py:264-378`
- C8 DDL 参考: `backend/db/dbops_phase3_6b0_schema_snapshot.sql`
- C8 ansible role: `ansible-playbooks/playbooks/roles/db_schema_metadata_collect/tasks/main.yml`
- C16-F1 验证 plan: `.claude/plans/phase-3-6-progress-2026-07-06-c16-f1-handoff.md`
- C16-F2 验证 plan: `.claude/plans/phase-3-6-progress-2026-07-06-c16-f2.md`
- F3 跨会话 memory（Commit 3 完成后写）: `~/.claude/projects/-home-lisiyang-dbops/memory/phase-3-6-c16-f3-completed-2026-07-06.md`


---

## 4. live E2E 验证（dev 库 PG 实例就绪后做）

PG 实例 `10.134.185.228` (id=965, credential=7) 已注册（C16-F1 阶段）：

```bash
# 触发采集
curl -X POST -H "Authorization: Bearer <token>" \
  http://10.134.185.85:51088/api/v1/ai/sql/object-metadata/965/collect \
  -d '{"schema_name":"public"}'
# 期望 202 + collector_run_id

# 5 分钟内 callback 落库
psql -c "SELECT id, status, is_current, length(object_ddl_text), table_count, view_count, index_count, function_count, total_object_count FROM dbops.ai_object_metadata_snapshot WHERE instance_id=965 ORDER BY id DESC LIMIT 3"
# 期望看到 status=success, is_current=true, total_object_count > 0

# context 端点验证
curl -H "Authorization: Bearer <token>" \
  "http://10.134.185.85:51088/api/v1/ai/sql/object-metadata/965/context?schema_name=public"
# 期望非空 object_ddl_text

# schema context 集成验证
curl -H "Authorization: Bearer <token>" \
  "http://10.134.185.85:51088/api/v1/ai/sql/schema-snapshots/965/context"
# 期望 JSON 含 object_metadata 字段
```

---

## 5. 关键设计决策（F3 全程遵守）

| 决策 | 选择 | 理由 |
|------|------|------|
| DB 方言 | PostgreSQL only | 与 C8 一致，三方言合并 C16-F0 |
| 落表 | 独立 `ai_object_metadata_snapshot` | 概念独立（DDL vs column rows） |
| 路由 | `business_domain='ai_object_metadata'` | 独立 callback 路径 |
| run_type | `ai_object_metadata` | 与 `ai_schema` 并列 |
| SQL 范围 | table + view + materialized_view + index + function/procedure + constraint | AI SQL 生成必需 |
| Capabilities | 不增加 capability flag | 复用 `AI_SQL_PREVIEW_ENABLED` gate |
| 编号冲突 | docs §7 F-list 追加 F13 | F3 已被 "前端 sql_preview_link" 占用 |
| 提交方式 | 拆 3 个 commit | ~3000 行单一 commit 风险高 |
| Partial unique | 加 schema_name 维度 | DDL 概念上需 schema 粒度（与 C8 不同） |
| 1MB 截断 | callback service 兜底 | 避免 DDL 文本超 TOAST |
| TTL | 24h（`AI_OBJECT_METADATA_TTL_HOURS`） | 与 C8 一致 |

---

## 6. 风险 + Rollback

| 风险 | 缓解 |
|------|------|
| DDL 行超 TOAST | callback 1MB 截断 + `error_message='TRUNCATED'` |
| Dify 上下文超 token | `object_ddl_text_preview` 限 8000 字符注入 |
| Builder 误注册到非 PG | `_SUPPORTED_DB_TYPES` frozenset 守卫 + skipped item |
| staging 永久卡住 | `cleanup_running_timeouts` startup hook 兜底（10 min） |
| 同 (instance, schema) 并发 trigger | `AiObjectMetadataAlreadyRunning` 异常 409 |
| collector_service handle_callback 影响 C8 路径 | 新 ai_object_metadata 走独立 dispatcher；现有分支不变 |

**Rollback 步骤**（按 commit 倒序）：

```bash
# commit 3 失败（仅 docs + tests）
git revert <commit-3-sha> --no-edit && git push

# commit 2 失败（业务逻辑）
git revert <commit-2-sha> --no-edit && git push
psql -h 10.134.185.85 -U dbops -d dbops -c \
  "UPDATE dbops.ai_object_metadata_snapshot SET status='failed' WHERE status IN ('pending','running');"

# commit 1 失败（DDL + Builder + Ansible）
git revert <commit-1-sha> --no-edit && git push
psql -h 10.134.185.85 -U dbops -d dbops -f \
  /home/lisiyang/dbops/backend/db/rollback_phase3_6b0_ai_object_metadata.sql
```

---

## 7. 关键文件位置速查

- 完整设计: `.claude/plans/abundant-beaming-hamster.md` (~1000 行)
- 上游 commit: `e965ae6` (C16-F2)
- 起点 plan: `.claude/plans/phase-3-6-progress-2026-07-06-c16-f2.md`
- 父 handoff: `.claude/plans/phase-3-6-progress-2026-07-06-c16-handoff.md`
- C8 实现参考: `backend/app/services/check_item_builder_registry.py:964-1116`
- C9 callback 参考: `backend/app/services/ai/ai_schema_snapshot_callback_service.py`
- C10 service 参考: `backend/app/services/ai/ai_schema_snapshot_service.py`
- C10 API 参考: `backend/app/api/ai.py:264-378`
- C8 DDL 参考: `backend/db/dbops_phase3_6b0_schema_snapshot.sql`
- C8 ansible role: `ansible-playbooks/playbooks/roles/db_schema_metadata_collect/tasks/main.yml`
- C16-F1 验证 plan: `.claude/plans/phase-3-6-progress-2026-07-06-c16-f1-handoff.md`
- C16-F2 验证 plan: `.claude/plans/phase-3-6-progress-2026-07-06-c16-f2.md`