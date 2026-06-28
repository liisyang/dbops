# Phase 3.6 AI Copilot — C6 完成（SQL Schema Snapshot 底座）

**Date**: 2026-06-28
**Branch**: `feature/phase-3.6-ai-copilot`
**Base HEAD**: `72c1fda` (C5+1 BE-bug1)
**New HEAD**: (本 commit)
**Plan**: `.claude/plans/phase-3-6-ai-copilot-full-plan.md` §2.2 + §4
**设计**: `.claude/plans/phase-3-6-progress-2026-06-28-c6-design.md`

---

## ✅ 本轮已完成

C6 = **纯数据库 + ORM 底座**，让后续 C7-C11 能在稳定基础上构建业务逻辑。

### 1. DDL（`backend/db/dbops_phase3_6b0_schema_snapshot.sql`）

- 表 `dbops.ai_sql_schema_snapshot`：21 个字段
- **4 个 CHECK 约束**：
  - `chk_ai_sql_schema_snapshot_db_type` — POSTGRESQL/ORACLE/MSSQL/MYSQL
  - `chk_ai_sql_schema_snapshot_status` — 五态机
  - `chk_ai_sql_schema_snapshot_payload` — 状态机完整性（plan P0-2 修正）
  - `chk_ai_sql_schema_snapshot_hash_len` — SHA-256 长度 64
- **2 个 FK**：instance_id (CASCADE) + collector_run_id (SET NULL)
- **5 个索引**：1 PK + 1 部分唯一 (is_current) + 3 辅助
- **幂等性**：所有 CREATE 用 `IF NOT EXISTS`，约束/索引/触发器用 `DO $$ ... pg_constraint/pg_indexes/pg_trigger` 块保护

### 2. Rollback（`backend/db/rollback_phase3_6b0_schema_snapshot.sql`）

- 单 `DROP TABLE IF EXISTS dbops.ai_sql_schema_snapshot CASCADE`
- 头部明示数据量检查 + 人工确认要求（仿 C2）

### 3. ORM Model（`backend/app/models/ai.py` +158 行）

- `AiSchemaSnapshotStatus` 枚举常量（5 态）
- `AiSchemaSnapshot` Model：21 个 Column + 4 CheckConstraint + 4 Index
- `is_usable()` 方法：判定 snapshot 是否可被 SQL Preview 消费
  - status=success + is_current=true + 未过期
- **不加任何 alias**（BE-bug1 教训）
- `from datetime import timezone` 新增（model 顶部 import）

### 4. Pydantic Schema（`backend/app/schemas/ai.py` +39 行）

- `AiSchemaSnapshotResponse`：21 字段，`from_attributes=True`
- 状态字段用 `Literal["pending", "running", "success", "failed", "unavailable"]`
- `allowed_columns: dict[str, list[str]]` 配 Pydantic 自动转换 JSONB
- **不加 alias**（BE-bug1 教训）

### 5. Config / .env.example

- C5 阶段已加好（`AI_SCHEMA_SNAPSHOT_TTL_HOURS=24` 等 7 个）— 本次无需变更

---

## ✅ 验证

### 5.1 DDL 幂等（dev 库跑 2 次）

```
=== Run 1 === CREATE TABLE / 6 DO 块 / 3 CREATE INDEX / COMMIT ✓
=== Run 2 === 全部 NOTICE: already exists, skipping ✓
```

### 5.2 表结构（`\d dbops.ai_sql_schema_snapshot`）

- 21 字段，类型/默认值/DDL 全部对齐
- 5 索引（含部分唯一 `uq_ai_sql_schema_snapshot_current`）
- 4 CHECK 约束
- 2 FK（CASCADE + SET NULL）

### 5.3 CHECK 约束行为（5 个手工 SQL 测试）

| 场景 | 期望 | 实测 |
|------|------|------|
| 1. success 必填字段齐 | INSERT ✓ | id=1 ✓ |
| 2. success 缺 snapshot_hash | CHECK 拒绝 ✓ | `chk_ai_sql_schema_snapshot_payload` violation ✓ |
| 3. failed + error_message | INSERT ✓ | id=3 ✓ |
| 4. pending + error_message | CHECK 拒绝 ✓ | `chk_ai_sql_schema_snapshot_payload` violation ✓ |
| 5. snapshot_hash 长度 ≠ 64 | CHECK 拒绝 ✓ | `chk_ai_sql_schema_snapshot_hash_len` violation ✓ |

测试数据 `cktest1, cktest3` 已清理（DELETE 2 行）。

### 5.4 模块导入

```python
from app.models.ai import AiSchemaSnapshot, AiSchemaSnapshotStatus  # OK
from app.schemas.ai import AiSchemaSnapshotResponse                  # OK
# tablename: ai_sql_schema_snapshot in schema dbops
# Status ALL: ('pending', 'running', 'success', 'failed', 'unavailable')
```

### 5.5 verify.sh

```
269 passed, 2 skipped, 0 failed in 8.96s
[OK] AI verification finished
```

---

## 📁 文件清单（C6 共 4 文件）

```
backend/db/dbops_phase3_6b0_schema_snapshot.sql          | A +187  (DDL)
backend/db/rollback_phase3_6b0_schema_snapshot.sql        | A +22   (rollback)
backend/app/models/ai.py                                  | M +158  (AiSchemaSnapshot)
backend/app/schemas/ai.py                                 | M +39   (AiSchemaSnapshotResponse)
.claude/plans/phase-3-6-progress-2026-06-28-c6.md         | A +本文件
```

---

## 🚀 下一会话快速恢复（C7 起手）

C7 = **PostgreSQL 固定元数据 SQL 模板**（plan §4.1）

1. 加载本文件
2. 设计 4 个固定 SQL：
   - `pg_schemas.sql` — 查所有 schema
   - `pg_tables.sql` — 查 schema.table
   - `pg_columns.sql` — 查 schema.table.column（带类型/nullable/默认值）
   - `pg_table_counts.sql` — 表 row_count 估计
3. 落到 `backend/app/services/ai/sql_templates/postgresql/`
4. 不实现 Dify 拼接逻辑（C11 才做），只把 SQL 写好 + 单元测试（mock fetch 行为）

---

## 📋 收尾待办（按 plan §14 顺序）

- ✅ ~~C6: SQL Schema Snapshot 底座~~（本 commit）
- C7: PostgreSQL 固定元数据 SQL 模板
- C8: Collector Builder + Role + Playbook 路由
- C9: Callback 落库服务
- C10: API 端点 + AiSchemaContextService
- C11-C26: SQL Preview → SQL Execute → Inspection AI Analysis
- C28: 全量 ~105 测试 + 日志脱敏
- C29: verify.sh 更新 + .env.example + docs/10-module-map.md
- C30: API Key 泄漏 grep 检查
- C31: DDL 幂等验证 + 回滚安全检查（C6 已部分完成）
- C32: 启动时 stale 清理（asyncio.to_thread 兼容性修）
