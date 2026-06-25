# Plan: Phase 3.5 — DB 只读 SQL 通用执行器 + 动态巡检 + 备份状态采集

**Source**: User PRD `# 1 DBOPS Phase 3.4 / 3.5 P0 实施任务`
**Scope**: P0-1, P0-2, P0-3 only (不含 Dify/MCP/AI Agent/大屏/恢复流程)
**Complexity**: Large
**Date**: 2026-06-24 (plan)；2026-06-25 (last progress sync)
**Status**: ✅ Phase 3.5 P0 全部 5 个 commit 完成、pushed to origin/main；dbops HEAD `a1e8760` + ansible-playbooks `b6221b7`；vue-tsc 0 错、verify.sh 223 passed、22/22 SQL safety 用例 pass

## 当前进度（2026-06-25 续会话完成态）

| Commit | 范围 | 状态 | 说明 |
|---|---|---|---|
| 1 | `roles/db_sql_readonly_collect` + playbook 路由 | ✅ 已 commit `be84847` push | ansible-playbooks repo |
| 2 | collector-client `db_sql_readonly` executor | ✅ 已 commit `b6221b7` push | ansible-playbooks repo（dbops-collector 同步留底） |
| 3 | backend SQL safety + inspection dispatch | ✅ 已 commit `1d5ec9b` | dbops repo |
| 4 | backend P0-3 backup | ✅ 已 commit `3e10b22` | DDL 已应用测试库，4 endpoint smoke test 通过 |
| 5 | frontend P0 | ✅ 已 commit `a1e8760` | 4.1/4.2/4.3/4.4 全部完成；vue-tsc 0 错，verify.sh 223 passed |

**Commit 4 已完成文件**（5 新增，3 修改）：
- 新增：`backend/db/dbops_phase3_5_backup_status.sql`、`backend/db/rollback_phase3_5_backup_status.sql`、`backend/app/schemas/backup.py`、`backend/app/services/backup_service.py`、`backend/app/api/backup.py`
- 修改：`backend/app/main.py`、`backend/app/models/dbops_assets.py`（加 `BackupStatusSnapshot` ORM）、`backend/app/services/collector_service.py`（加 backup_status callback 分流）

**Commit 5 已完成文件**（3 新增，6 修改）：
- 新增：`frontend/src/api/backup.ts`、`frontend/src/components/ops/OpsDrawer.vue`（共享 slide-in drawer 组件，Teleport + Transition + width sm/md/lg/xl/full）
- 修改：`frontend/src/api/assets.ts`（+4 methods）、`frontend/src/composables/useStatusFormatters.ts`（+`getBackupStatusClass`）、`frontend/src/views/inspection/Items.vue`（SQL editor + verify modal + needsVerificationForEnable gate）、`frontend/src/views/inspection/Reports.vue`（+OpsDrawer evidence columns/rows/duration/sql_hash/connector/stderr + raw JSON toggle）、`frontend/src/views/backup/Jobs.vue`（filter bar + status badge via getBackupStatusClass + 历史/采集 modals）、`frontend/src/components/ops/index.ts`（export OpsDrawer）、`frontend/src/types/api.ts`（InspectionItem* 加 db_type_code，InstanceRow 加 port）

**dbops repo 剩余工作**：
- 端到端冒烟（手工插 inspection_item → 后端 → AWX → callback → Reports 看到 evidence → Jobs 看到 backup 状态）— 需 AWX 可达 + 至少一个目标 DB 可连通

## 环境确认

- **当前环境即为测试环境**，DDL 变更直接在测试库执行，生成 SQL 文件便于追溯和回滚
- **Oracle 权限需现场确认**：`dba_data_files`、`dba_free_space`、`v$rman_backup_job_details` 查询权限未在目标 Oracle 实例上验证，开发完成后需在对应对实例上执行示例 SQL 确认。collector_client 需对权限不足的情况做明确的 error_code（`PERMISSION_DENIED`）而非笼统失败
- 所有 DDL 变更文件放在 `backend/db/` 下，同步生成对应的 `rollback_*.sql`

## Summary

新增通用 DB 只读 SQL 执行器（`DB_READONLY_SQL_EXEC`），使巡检项和备份采集不再需要固化 check_code/yml，只需在 DBOPS 配置 SQL。闭环：DBOPS 配置 SQL → 后端 SQL 安全校验 → 构建 collector_item → AWX `dbops_collector_generic.yml` → `db_sql_readonly_collect` role → `collector_client.cli` 执行只读 SQL → callback 返回结果 → 按 `business_domain` 分别写入 `inspection_result` / `backup_status_snapshot`。

**callback 分流规则（按 business_domain）**：

| business_domain | 落库目标 | 说明 |
|---|---|---|
| `inspection` | `inspection_result` | 巡检报告 |
| `backup_status` | `backup_status_snapshot` | 备份状态快照 |
| `inspection_verify` | **不写业务表** | 只更新 `collector_run_result`，供前端轮询 verify 结果 |

`inspection_verify` 不写 `inspection_result`，不写 `backup_status_snapshot`。

**最小验证路径**：手工插入 `inspection_item` → 后端创建任务 → AWX 执行 `DB_READONLY_SQL_EXEC` → callback 写 `inspection_result`。前端在后端+AWX 闭环跑通后再接。

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Ansible role | `roles/db_fact_collect/tasks/main.yml` | assert→set_fact→command→parse→build→append |
| Playbook routing | `dbops_collector_generic.yml:48-185` | `include_role` + `loop` + `when` with gate |
| collector_client dispatch | `cli.py:258-268` | dispatch by executor_type, not target_scope |
| collector_client output | `result_builder.py:49-58` | `write_result()` → `model_dump(mode="json")` |
| Backend service | `inspection_service.py` | static methods, `_now()`, dict serialization |
| Backend API | `api/inspection.py:24-30` | `APIRouter` + `Depends(get_current_user)` + `Depends(get_db)` |
| Backend schema | `schemas/inspection.py` | Pydantic v2, `BaseModel`, `Field`, `Literal` |
| Builder registry | `check_item_builder_registry.py:45-140` | register check_code→builder, `_checkcode_to_inspection_items` |
| Callback handling | `collector_service.py:1338-1344` | detect `run_type=="inspection"` → `InspectionService.save_callback_results()` |
| Frontend page | `views/inspection/Items.vue` | `OpsPage` → `OpsPageHeader` → `OpsFilterBar` → `OpsTableShell` → `OpsModal` |
| Frontend API | `api/assets.ts` | export plain object, use `request` from `request.js` |
| DB migration | `db/dbops_phase3_4.sql` | `CREATE TABLE IF NOT EXISTS` + indexes + views |

## Files to Change

| File | Action | Why |
|---|---|---|
| `roles/db_sql_readonly_collect/tasks/main.yml` | **CREATE** | New Ansible role for DB readonly SQL execution |
| `playbooks/dbops_collector_generic.yml` | UPDATE | Add `db_sql_readonly_collect` routing after `reachable_db_asset_ids` |
| `collector_client/cli.py` | UPDATE | Add `executor_type` dispatch → `collect_db_readonly_sql()` |
| `collector_client/schemas.py` | UPDATE | Add `executor_type`, `business_domain`, `rule_config` fields to `CollectorItemInput`; add new `DbReadonlySqlOutput` |
| `collector_client/result_builder.py` | UPDATE | Add `build_sql_output()` for the new JSON output shape |
| `backend/app/services/sql_safety_service.py` | **CREATE** | SQL readonly validation, keyword blocking, masking, multi-statement detection |
| `backend/app/services/inspection_service.py` | UPDATE | Add `DB_READONLY_SQL_EXEC` result merging in `_merge_derived_results`; add `validate_sql()` / `verify_sql()` |
| `backend/app/services/check_item_builder_registry.py` | UPDATE | Register `DB_READONLY_SQL_EXEC` builder; add `_checkcode_to_inspection_items` mapping |
| `backend/app/schemas/inspection.py` | UPDATE | Add `ValidateSqlRequest/Response`, `VerifySqlRequest/Response` |
| `backend/app/api/inspection.py` | UPDATE | Add `validate-sql`, `verify-sql`, `PATCH /items/{id}` (disable) endpoints |
| `backend/app/services/collector_service.py` | UPDATE | Add `business_domain=="backup_status"` → `BackupService.save_snapshot()` |
| `backend/app/services/backup_service.py` | **CREATE** | Backup status snapshot save + latest/history API |
| `backend/app/api/backup.py` | **CREATE** | `GET /backup/status/latest`, `GET /backup/status/history` |
| `backend/db/dbops_phase3_5_backup_status.sql` | **CREATE** | DDL for `backup_status_snapshot` table + `v_backup_status_latest` view |
| `backend/app/models/dbops_assets.py` | UPDATE | Add `BackupStatusSnapshot` ORM model |
| `frontend/src/api/inspection.ts` | **CREATE** | Inspection API functions (items CRUD + validate-sql + verify-sql) |
| `frontend/src/api/backup.ts` | **CREATE** | Backup API functions (latest + history) |
| `frontend/src/views/inspection/Items.vue` | UPDATE | Add SQL editor textarea, verify-sql modal, DB type selector, enabled gate |
| `frontend/src/views/inspection/Tasks.vue` | UPDATE | Ensure DB SQL inspection tasks work |
| `frontend/src/views/inspection/Reports.vue` | UPDATE | Evidence drawer with columns/rows/duration/sql_hash |
| `frontend/src/composables/useStatusFormatters.ts` | UPDATE | Add `getBackupStatusClass()` for backup status badge colors |
| `frontend/src/views/backup/Jobs.vue` | UPDATE | Latest backup status table with Ops components |

## Tasks

### Phase 1: AWX + collector_client 闭环 (P0-1)

#### Task 1.1: Create Ansible role `db_sql_readonly_collect`
- **Action**: Create `roles/db_sql_readonly_collect/tasks/main.yml` mirroring `db_fact_collect/tasks/main.yml` pattern with:
  - Field validation (item_key, check_code==DB_READONLY_SQL_EXEC, executor_type==db_sql_readonly, **business_domain in ['inspection', 'inspection_verify', 'backup_status']**, rule_config.sql_text)
  - Serialize item to JSON, call `collector_client.cli --item-json`
  - Parse output with block/rescue fallback (empty stdout → default failed result, parse error → PARSE_ERROR)
  - Build `collector_item_result` with `raw_result` containing columns/rows/result_status/severity/error_code/connector/duration_ms/sql_hash/rc/stderr
  - Append to `collector_results` and log
  - `changed_when: false`, `failed_when: false` — single item never fails the job

**`collector_item_result` 必须透传业务字段到顶层**（不解析 item_key，不放 raw_result 深处）：

```yaml
- name: Build item result
  ansible.builtin.set_fact:
    collector_item_result:
      item_key: "{{ _parsed.item_key }}"
      check_code: "{{ _parsed.check_code }}"
      target_scope: "{{ _parsed.target_scope }}"
      asset_id: "{{ _parsed.asset_id | int }}"
      target_host: "{{ _parsed.target_host }}"
      target_port: "{{ _parsed.target_port | int }}"
      status: "{{ _parsed.status }}"
      reachable: "{{ _parsed.reachable | default(false) | bool }}"
      message: "{{ _parsed.message | default('') }}"
      # --- 业务字段透传（callback 落库直接读顶层）---
      business_domain: "{{ collector_item.business_domain | default('inspection') }}"
      task_id: "{{ collector_item.task_id | default(omit) }}"
      inspection_item_id: "{{ collector_item.inspection_item_id | default(omit) }}"
      item_code: "{{ collector_item.item_code | default(omit) }}"
      policy_id: "{{ collector_item.policy_id | default(omit) }}"
      backup_type: "{{ collector_item.backup_type | default(omit) }}"
      # --- raw_result ---
      raw_result:
        columns: "{{ _parsed.columns | default([]) }}"
        rows: "{{ _parsed.rows | default([]) }}"
        result_status: "{{ _parsed.result_status | default('unknown') }}"
        severity: "{{ _parsed.severity | default(collector_item.severity | default('warning')) }}"
        error_code: "{{ _parsed.error_code | default('') }}"
        connector: "{{ _parsed.connector | default('') }}"
        duration_ms: "{{ _parsed.duration_ms | default(0) }}"
        sql_hash: "{{ _parsed.sql_hash | default('') }}"
        rc: "{{ _db_sql_result.rc | default(-1) }}"
        stderr: "{{ (_db_sql_result.stderr | default(''))[:4000] }}"
```

这些字段不能只放在 item_key 中，也不能只放 raw_result 深处。callback 业务落库必须直接读取顶层字段。

- **Mirror**: `roles/db_fact_collect/tasks/main.yml` (same parse→build→append pattern)
- **Validate**: `ansible-playbook --syntax-check dbops_collector_generic.yml` (after Task 1.2)

#### Task 1.2: Expand pre-copy scope + Add routing in `dbops_collector_generic.yml`

**Step A — 扩展 pre-copy 判断，纳入 DB_READONLY_SQL_EXEC**

`db_sql_readonly_collect` role 依赖 `/tmp/collector_client`，但原来只有 DB fact items 存在时才复制。如果本批次只有 `DB_READONLY_SQL_EXEC` 而没有 DB fact item，复制不会触发，role 会失败。

修改现有 `db_fact_check_codes` 变量（line 109-113），**保留原变量不变**，新增扩展变量：

```yaml
# 保留原变量（db_fact_collect 路由继续使用）
- name: Define DB fact check codes
  ansible.builtin.set_fact:
    db_fact_check_codes:
      - DB_BASIC_FACT_COLLECTION
      - DB_VERSION_FACT_COLLECTION
      - DB_ROLE_FACT_COLLECTION

# 新增扩展变量（仅用于 pre-copy 判断）
- name: Define DB python collector check codes
  ansible.builtin.set_fact:
    db_python_collect_check_codes: "{{ db_fact_check_codes + ['DB_READONLY_SQL_EXEC'] }}"
```

然后将 `has_db_fact_items` 变量改名为 `has_db_python_collect_items`，判断条件从 `db_fact_check_codes` 改为 `db_python_collect_check_codes`。

**关键约束**：
- `db_fact_check_codes` 原变量不动，`Route db_fact_collect items` 继续用它（`collector_item.check_code in db_fact_check_codes`）
- `db_python_collect_check_codes` 只用于 pre-copy 的三个任务：Remove stale / Pre-copy / Verify import
- 后续 pre-copy 和 import verify 的 `when` 条件改为 `has_db_python_collect_items | bool`

**Step B — 新增路由（放在 pre-copy + import verify 之后）**

在 `Verify collector_client can be imported` 任务（line 142-153）之后，`Route db_fact_collect items`（line 155）之前，新增：

```yaml
- name: Route db_sql_readonly_collect items
  ansible.builtin.include_role:
    name: db_sql_readonly_collect
  loop: "{{ items }}"
  loop_control:
    loop_var: collector_item
    label: "{{ collector_item.item_key }}"
  when:
    - collector_item.executor_type | default('') == 'db_sql_readonly'
    - collector_item.check_code | default('') == 'DB_READONLY_SQL_EXEC'
    - collector_item.business_domain | default('') in ['inspection', 'inspection_verify', 'backup_status']
    - >-
      (collector_results | selectattr('check_code', 'equalto', 'DB_PORT_REACHABILITY') | list | length == 0)
      or (collector_item.asset_id | int in (reachable_db_asset_ids | default([])))
```

**为什么需要 `inspection_verify`**：verify-sql 设计使用 `business_domain="inspection_verify"`，如果路由不包含它，verify-sql AWX job 启动了但 item 被跳过，永远不会执行。

**关键约束**：

- 路由必须在 pre-copy 和 import verify 成功之后，确保 `/tmp/collector_client` 已就绪
- `has_db_fact_items` 改名为 `has_db_python_collect_items`，同时覆盖 DB fact 和 DB readonly SQL
- 原 port_check / db_fact_collect / os_fact_collect 逻辑不变

#### Task 1.3: Add `executor_type` dispatch in collector_client CLI
- **Action**: In `cli.py:main()`, before the target_scope dispatch (line 259), check `item.executor_type`:
  - If `executor_type == "db_sql_readonly"` → call `collect_db_readonly_sql(item)`
  - Else → existing `collect_db_facts`/`collect_os_facts` dispatch
- **Action**: Add `collect_db_readonly_sql(item)` function:
  - Parse `rule_config` from item (needs new field in `CollectorItemInput`)
  - Do client-side SQL safety validation (兜底校验): allow only SELECT/WITH/SHOW, block INSERT/UPDATE/DELETE/DROP etc., block multi-statement (`;`)
  - Get DB connector (reuse `_get_db_connector`), execute `rule_config.sql_text` with **真实驱动层超时**：
    - Oracle：使用 driver call timeout / statement timeout，按当前 connector 实现确认
    - PostgreSQL：优先 `SET LOCAL statement_timeout` 或连接参数 `options='-c statement_timeout=...'`
    - MySQL：使用 `read_timeout` / `SET SESSION max_execution_time`
    - SQL Server：使用 ODBC `query_timeout` / `cursor.timeout`
    - **如果某个 connector 暂时无法设置硬超时，必须在返回 JSON 中标记 `timeout_enforced: false` 并在 message 中说明**
  - Mask sensitive columns (password/passwd/pwd/token/secret/key/hash/credential → `***MASKED***`)
  - Truncate rows at `rule_config.max_rows`
  - On success: stdout JSON with `status="success"`, `columns`, `rows`, `result_status`, `severity`, `duration_ms`, `connector`, `sql_hash`
  - On failure: stdout JSON with `status="failed"`, `error_code`, `message`
  - NEVER print traceback to stdout — only to stderr
- **Mirror**: `collect_db_facts()` pattern (connector factory + try/except + build_output)
- **Validate**: `cd /home/lisiyang/dbops-collector && python -m compileall collector_client/`

#### Task 1.4: Update collector_client schemas
- **Action**: Add to `CollectorItemInput`: `executor_type`, `business_domain`, `rule_config` (dict with sql_text, timeout_seconds, max_rows, result_mapping)
- **Action**: Add `DbReadonlySqlOutput` schema for the new JSON output shape (columns, rows, result_status, severity, sql_hash, duration_ms, connector, error_code)
- **Mirror**: Existing Pydantic v2 pattern in `schemas.py`
- **Validate**: `python -c "from collector_client.schemas import CollectorItemInput; print('ok')"`

### Phase 2: Backend SQL Safety + Inspection Dispatch (P0-2 core)

#### Task 2.0: Verify collector_run constraints + add verify-sql run_type support (实施前必做)

**现状确认（已查 DB 验证）**：
- `CollectorRun` 模型列是 `job_type`（line 341），**无 CHECK 约束**（DB 只有 status/target_scope/target_port/item_count 的 CHECK）
- `run_type` 存储在 `request_payload` JSONB 中（line 404 via extra_vars）
- callback 分流逻辑（line 1338）通过 `request_payload.run_type` 判断
- **结论：新增 `SQL_VERIFY` / `BACKUP_STATUS` 作为 `job_type` 值无需 DDL，不会触发约束错误**

**需要做的**：
1. verify-sql 创建 run 时设置 `job_type="SQL_VERIFY"`，`request_payload.run_type="sql_verify"`
2. backup collect 创建 run 时设置 `job_type="BACKUP_STATUS"`，`request_payload.run_type="backup_status"`
3. callback 分流新增 `run_type == "sql_verify"` 分支：只更新 `collector_run_result`，不写业务表
4. callback 分流新增 `run_type == "backup_status"` 分支：写入 `backup_status_snapshot`

#### Task 2.1: Create SQL safety service
- **Action**: Create `backend/app/services/sql_safety_service.py`:
  - `validate_sql_readonly(sql_text: str, db_type_code: str) -> dict` — returns `{valid: bool, sql_hash: str, errors: list[str]}`

**关键字检测规则（token 级，禁止简单字符串包含）**：

```python
import re

# 危险关键字列表（不使用简单字符串包含，使用 token 级 \b 匹配）
DANGEROUS_KEYWORDS = [
    # 写操作
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "GRANT", "REVOKE",
    # 执行/调用
    "EXEC", "EXECUTE", "CALL", "BEGIN", "DECLARE",
    # 维护/管理
    "ANALYZE", "VACUUM", "REINDEX", "COPY",
    # 锁/事务陷阱
    "LOCK",           # LOCK TABLE
    "WAITFOR",        # SQL Server 延迟
    # Oracle 高风险包
    "DBMS_LOCK", "DBMS_SCHEDULER", "DBMS_PIPE",
    "UTL_HTTP", "UTL_FILE", "UTL_SMTP", "UTL_TCP",
    # PostgreSQL 高风险函数
    "PG_SLEEP", "PG_READ_FILE", "PG_WRITE_FILE",
    # MySQL 高风险
    "SLEEP", "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
]

# 注意：INTO 不列入全局关键词（会误杀正常 SQL 中的字段别名/函数名）。
# 改为模式级禁止：SELECT ... INTO / INTO OUTFILE / INTO DUMPFILE

# 关键字按长度倒序 + re.escape，避免特殊字符问题
escaped_keywords = sorted(
    [re.escape(k) for k in DANGEROUS_KEYWORDS],
    key=len, reverse=True
)
DANGEROUS_PATTERN = re.compile(
    r'\b(' + '|'.join(escaped_keywords) + r')\b',
    re.IGNORECASE
)
```

**字符串字面量屏蔽（关键！必须在关键词匹配前做）**：

```python
def _mask_string_literals(sql: str) -> str:
    """Replace single-quoted strings with placeholders so keyword
    matching won't false-positive on string content like
    SELECT 'DROP TABLE test' AS message FROM dual."""
    # Replace '' (escaped quote) → placeholder, then '...' → placeholder
    result = re.sub(r"''", "__ESC_QUOTE__", sql)
    result = re.sub(r"'[^']*'", "__STR_LIT__", result)
    result = re.sub(r"__ESC_QUOTE__", "''", result)
    return result
```

**检测流程**：
1. 去注释（`--` 行注释、`/* */` 块注释）
2. `_mask_string_literals()` 屏蔽单引号字符串
3. （可选）屏蔽双引号标识符
4. `DANGEROUS_PATTERN.search()` 做 token 级关键词匹配
5. 额外检查 `SELECT ... INTO` 模式：`re.search(r'\bSELECT\b.*\bINTO\b', sql, re.IGNORECASE | re.DOTALL)`
6. 分号检测（屏蔽字符串后）

**实现步骤**：
1. 去掉 SQL 注释（`--` 行注释、`/* */` 块注释）
2. 找到第一个有效关键字（跳过空白和注释）
3. 第一个关键字必须在允许列表中
4. 危险关键字用 `\bKEYWORD\b` 单词边界匹配（避免 `created_at` 包含 `CREATE` 被误杀）
5. **分号规则（调整后）**：先 strip 末尾空白。如果末尾有单个 `;`，自动 strip 掉。如果中间出现 `;`（排除字符串字面量内的），禁止。如果 strip 末尾分号后仍有分号，禁止。禁止分号后还有非空内容
6. `WITH` 后必须最终是 SELECT 查询
7. 额外禁止：`FOR UPDATE`（会加锁）、`SELECT ... INTO`（可能写表）

**允许的 SQL 按 DB 类型限制**：

| DB 类型 | 允许的首关键字 |
|---------|---------------|
| Oracle | SELECT, WITH |
| PostgreSQL | SELECT, WITH, SHOW |
| MySQL | SELECT, WITH, SHOW |
| SQL Server | SELECT, WITH |

- **Masking**：`SENSITIVE_COLUMNS = {"password","passwd","pwd","token","secret","key","hash","credential"}` — 返回列名匹配时值替换为 `***MASKED***`（仅 collector_client 端兜底，主校验在后端）
- **Limits**：`DEFAULT_TIMEOUT = 30`, `MAX_TIMEOUT = 120`, `DEFAULT_MAX_ROWS = 200`, `MAX_MAX_ROWS = 1000`
- **Mirror**: Static method pattern from `InspectionService`

**SQL 安全校验必须通过的测试清单**（集成到 `verify.sh` 或单独测试脚本）：

必须允许（`valid=True`）：
```sql
SELECT 1;
SELECT 1 FROM dual;
SELECT 'DROP TABLE test' AS msg FROM dual;
SELECT 'abc''DROP TABLE t' FROM dual;       -- Oracle 转义引号
SELECT $$DROP TABLE t$$ FROM t;             -- PostgreSQL dollar-quoting
SELECT created_at FROM dbops.collector_run; -- 不误杀 create
-- 这是注释，其中包含 DROP TABLE
SELECT 1;
WITH x AS (SELECT 1 AS id) SELECT * FROM x;
SHOW search_path;  -- PostgreSQL/MySQL only
```

必须拒绝（`valid=False`）：
```sql
SELECT 1; DELETE FROM dbops.db_instance;
SELECT * FROM v$session FOR UPDATE;
UPDATE dbops.db_instance SET status = 'inactive';
DROP TABLE dbops.db_instance;
SELECT pg_sleep(10);
SELECT utl_http.request('http://example.com') FROM dual;
SELECT * INTO new_table FROM old_table;
SELECT * INTO OUTFILE '/tmp/x' FROM t;
```

**P0 采用规则校验，不等同完整 SQL parser。已知不会覆盖的边界**：
- Oracle `q'[...]'` 替代引号语法（P0 暂不处理，后续可加）
- 极端嵌套的注释/字符串混合场景

- **Validate**: `python -m compileall app/services/sql_safety_service.py` + 运行测试用例

#### Task 2.2: Add `validate-sql` and `verify-sql` endpoints

**`POST /inspection/items/validate-sql`**（纯安全校验，不连目标库）

请求：`{db_type_code, sql_text}` → 响应：`{valid, sql_hash, message, errors}`

**`POST /inspection/items/verify-sql`**（AWX 异步验证，复用 Collector EE 驱动）

后端不做 DB 直连。verify-sql 走 AWX one-shot：

1. 后端构建单个 `DB_READONLY_SQL_EXEC` collector_item（含 sql_text、timeout_seconds、max_rows）
2. 后端调用 AWX `JT_DBOPS_COLLECTOR_GENERIC` 模板发起单 item job
3. 返回 `{verify_run_id: collector_run.id, status: "launched", awx_job_id}`
4. 前端轮询 `GET /inspection/items/verify-sql/{collector_run_id}`
5. 后端轮询接口实现（明确从表读取）：
   - 查询 `CollectorRun` WHERE `id = collector_run_id` AND `request_payload->>'run_type' = 'sql_verify'`
   - 查询该 run 下最新 `CollectorRunItem` / `CollectorRunResult`
   - 读取 `raw_result.columns` / `raw_result.rows` / `raw_result.duration_ms` / `raw_result.sql_hash`
   - 状态映射：`pending/launched/running` → `running`，`success` → `success`+结果，`failed` → `failed`+message
6. callback 到达时更新 `collector_run_result`，前端轮询获取最新结果

**设计理由**：
- 复用 Collector EE 里已有的 Oracle/PostgreSQL/MySQL/SQLServer 驱动和凭证注入
- 避免在后端临时复制一套不完整的 DB 连接逻辑
- 与生产巡检走完全相同的执行路径，验证结果更有参考价值

**`DELETE /inspection/items/{id}`** → P0 不做硬删除。改为 `PATCH /inspection/items/{id}` 设 `enabled=false` 作为软禁用。

硬删除仅在以下条件同时满足时允许：
- 无历史 `inspection_result` 引用（`SELECT COUNT(*) FROM inspection_result WHERE item_id = :id`）
- 无历史 `inspection_task` 的 `item_codes` 包含该 item_code
- 返回 409 Conflict 提示"请先禁用"

**原因**：巡检项被 `inspection_task` / `inspection_result` / `inspection_schedule` 引用，即使 `inspection_result.item_id` 可空，硬删除也会破坏历史追溯。
- **Mirror**: `api/inspection.py` existing endpoint pattern (try/except → HTTPException)
- **Validate**: `curl -X POST http://localhost:60801/api/v1/inspection/items/validate-sql ...`

#### Task 2.3: Update InspectionItem schemas
- **Action**: Add to `schemas/inspection.py`:
  - `ValidateSqlRequest(db_type_code, sql_text)`
  - `ValidateSqlResponse(valid, sql_hash, message, errors)`
  - `VerifySqlRequest(instance_id, db_type_code, sql_text, timeout_seconds, max_rows)` — 发起异步验证
  - `VerifySqlResponse(verify_run_id, status, awx_job_id)` — 返回异步 run ID
  - `VerifySqlResultResponse(success, verified, sql_hash, duration_ms, columns, rows, message)` — 轮询结果
- **Mirror**: Existing Pydantic v2 `BaseModel` + `Field` pattern

#### Task 2.4: Update InspectionService for SQL validation

**`verify_sql()` 状态存储 — 复用现有 `collector_run`（方案 A，优先）**：

verify-sql 不新增表。直接复用现有 `collector_run` / `collector_run_item` / `collector_run_result`：

```text
run_type = "sql_verify"
business_domain = "inspection_verify"
check_code = "DB_READONLY_SQL_EXEC"
```

流程：
1. 调用 `SqlSafetyService.validate_sql_readonly()` 做安全校验
2. 构建单个 `DB_READONLY_SQL_EXEC` collector_item
3. 创建 `CollectorRun`（run_type="sql_verify"，关联 inspection_item_id）
4. 调用 `AwxService.launch_job()` 发起 AWX one-shot
5. 返回 `{verify_run_id: collector_run.id, collector_run_id, status: "launched", awx_job_id}`
6. callback 到达时，`CollectorService.process_callback()` 更新 `collector_run_result`
7. 前端轮询 `GET /inspection/items/verify-sql/{collector_run_id}` 从 `collector_run_result` 取结果

**如果现有 collector 表无法稳定支撑轮询**（例如 run 级别的 status 更新时序与 item 级别不一致），再启用方案 B：新增 `inspection_sql_verify_run` 轻量表。不要在代码中只写 verify_run 概念而没有明确的落库来源。

**`create_item()` / `update_item()` SQL 校验**：
- Validate `rule_config.executor_type == "db_sql_readonly"`
- Validate `rule_config.sql_text` passes readonly check
- Validate `rule_config.timeout_seconds` in 1~120
- Validate `rule_config.max_rows` in 1~1000
- If `enabled=True`, require `rule_config.verified=True`

#### Task 2.5: Register `DB_READONLY_SQL_EXEC` in CheckItemBuilderRegistry
- **Action**: Add builder class `_DbReadonlySqlExecBuilder` that generates `DB_READONLY_SQL_EXEC` items:
  - For each `db_instance` asset, resolve host/port/credential same as `_DbFactCollectionBuilderBase`
  - Build item_key = `{business_domain}:{task_id}:{item_code}:{instance_id}` (用于日志和幂等定位)
  - **显式携带业务字段**（不依赖解析 item_key）:
    ```json
    {
      "item_key": "inspection:123:ORACLE_TABLESPACE_USAGE:1001",
      "check_code": "DB_READONLY_SQL_EXEC",
      "executor_type": "db_sql_readonly",
      "business_domain": "inspection",
      "target_scope": "db_instance",
      "asset_id": 1001,
      "task_id": 123,
      "inspection_item_id": 456,
      "item_code": "ORACLE_TABLESPACE_USAGE",
      "target_host": "10.1.1.10",
      "target_port": 1521,
      "db_type_code": "ORACLE",
      "rule_config": { ... }
    }
    ```
  - 备份状态采集同理显式携带 `business_domain: "backup_status"`、`policy_id`、`backup_type`
- **Action**: Register with `CheckItemBuilderRegistry.register("DB_READONLY_SQL_EXEC", _DbReadonlySqlExecBuilder())`
- **Action**: Add `"DB_READONLY_SQL_EXEC"` to `_checkcode_to_inspection_items` mapping (maps to itself for passthrough)
- **Mirror**: `_DbFactCollectionBuilderBase` pattern (credential resolution, skip-on-missing)
- **Validate**: `cd backend && python -m compileall app/services/check_item_builder_registry.py`

#### Task 2.6: Add DB_READONLY_SQL_EXEC callback result merging
- **Action**: In `InspectionService._merge_derived_results()`, add handling for `check_code == "DB_READONLY_SQL_EXEC"`:
  - **直接从 callback_item 读取显式字段**：`task_id`、`inspection_item_id`、`item_code`、`business_domain`。不解析 `item_key`
  - `item_key` 仅用于日志和 `collector_item_key` 关联，不做业务字段来源

**多行 result_status 聚合规则（优先级聚合，不只读第一行）**：

优先级：`abnormal > warning > unknown > normal`

```python
def _aggregate_result_status(rows: list[dict], status_column: str = "RESULT_STATUS") -> str:
    if not rows:
        return "normal"
    statuses = [str(row.get(status_column, "")).lower() for row in rows]
    for priority in ("abnormal", "warning", "unknown"):
        if priority in statuses:
            return priority
    return "normal"
```

**message 聚合规则**：
- 取最严重行的 MESSAGE；如果有多行同级别，拼接前 3 条
- 如果 SQL 成功但 rows 为空 → `result_status=normal, message="no abnormal rows"`
- 如果 SQL 失败 → `result_status=unknown, severity=warning, message=collector_item_result.message`

- Set `evidence = {collector_item_key, raw_result}` with columns, rows, duration_ms, sql_hash, stderr
- **Mirror**: Existing `build_inspection_results_from_callback()` for `DB_VERSION_COLLECTED` etc.
- **Validate**: `python -m compileall app/services/inspection_service.py`

### Phase 3: Backup Status Snapshot (P0-3)

**架构约束**：
- `backup_status_snapshot` **不强依赖 inspection_task**
- `backup_status` 可以作为独立 `business_domain` 发起 collector run
- `backup_status` callback 写 `backup_status_snapshot`，不与 `inspection_result` 耦合
- `inspection_result` 是巡检报告，`backup_status_snapshot` 是备份业务状态 — 结果落库必须分开
- 后续"备份中心"不会被"巡检中心"拖住

#### Task 3.1: Create DDL for backup_status_snapshot
- **Action**: Create `backend/db/dbops_phase3_5_backup_status.sql`:
  - `CREATE TABLE IF NOT EXISTS dbops.backup_status_snapshot`，字段固定如下（不允许自由发挥）：
    ```sql
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES dbops.db_instance(id) ON DELETE CASCADE,
    policy_id BIGINT NULL REFERENCES dbops.backup_policy(id),
    collector_run_id BIGINT NULL,
    collector_run_item_id BIGINT NULL,
    backup_type VARCHAR(50) NULL,
    source_type VARCHAR(50) NOT NULL DEFAULT 'db_sql',
    last_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    last_success_at TIMESTAMP NULL,
    last_failure_at TIMESTAMP NULL,
    recovery_point_at TIMESTAMP NULL,
    age_minutes INTEGER NULL,
    duration_seconds INTEGER NULL,
    backup_size_mb NUMERIC(18,2) NULL,
    message TEXT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    collected_at TIMESTAMP NOT NULL DEFAULT now(),
    created_at TIMESTAMP NOT NULL DEFAULT now()
    ```
  - `CREATE OR REPLACE VIEW dbops.v_backup_status_latest` (DISTINCT ON instance_id, backup_type)
  - Indexes: `(instance_id, collected_at DESC)`, `(last_status)`, `(policy_id)`
  - CHECK: `last_status IN ('success','failed','warning','unknown')`, `source_type IN ('db_sql','agent','manual','external')`
- **Action**: Create `backend/db/rollback_phase3_5_backup_status.sql`:
  - `DROP VIEW IF EXISTS dbops.v_backup_status_latest`
  - `DROP TABLE IF EXISTS dbops.backup_status_snapshot`
- **Action**: Execute DDL against test DB (10.134.185.85:5432, user=dbops, db=dbops)
- **Validate**: `SELECT to_regclass('dbops.backup_status_snapshot')`, `SELECT to_regclass('dbops.v_backup_status_latest')`

#### Task 3.2: Add BackupStatusSnapshot model
- **Action**: Add `BackupStatusSnapshot` ORM model to `models/dbops_assets.py`
- **Mirror**: `InspectionResult` model pattern

#### Task 3.3: Create BackupService
- **Action**: Create `backend/app/services/backup_service.py`:
  - `launch_collect(db, payload)` — 构建 backup_status collector items，发起 AWX collector run
  - `save_snapshot(db, run, callback_items)` — iterate callback items where `business_domain=="backup_status"`, parse `raw_result.rows[0]`, write to `backup_status_snapshot`
  - `list_latest(db, filters)` — query `v_backup_status_latest`，**join `db_instance`/`db_type`/`server` 返回前端可直接展示的数据**（见 Task 3.5 补充）
  - `list_history(db, filters)` — query `backup_status_snapshot`
  - Field mapping: case-insensitive column name matching (BACKUP_TYPE/backup_type etc.)
  - If rows empty → `last_status="unknown"`
  - If SQL failed → `last_status="unknown"`
- **Mirror**: `InspectionService.create_task()` + `save_callback_results()` 模式

#### Task 3.4: Add backup_status callback handling in CollectorService
- **Action**: In `collector_service.py:process_callback()`, after the inspection callback block (line 1344), add:
  - Detect items with `business_domain == "backup_status"` in callback_items
  - Call `BackupService.save_snapshot(db, run, callback_items)`
  - Wrap in try/except so backup save failure doesn't break inspection callback

#### Task 3.5: Create backup API endpoints
- **Action**: Create `backend/app/api/backup.py`:
  - `GET /backup/status/latest?db_type_code=&last_status=&backup_type=&keyword=` → 后端 join `db_instance`/`db_type`/`server`，返回前端可直接展示的数据。**不能只返回 `instance_id` 让前端二次查资产**
  - `GET /backup/status/history?instance_id=&limit=`
  - **`POST /backup/status/collect`** → 手动发起一次备份状态采集（见 Task 3.6）
- **Action**: Register router in `main.py`

**`GET /backup/status/latest` 响应格式（至少包含）**：

```json
{
  "instance_id": 1001,
  "instance_name": "ORCL",
  "db_type_code": "ORACLE",
  "host": "10.1.1.10",
  "port": 1521,
  "backup_type": "RMAN",
  "last_status": "success",
  "last_success_at": "2026-06-24T01:00:00Z",
  "last_failure_at": null,
  "recovery_point_at": "2026-06-24T01:00:00Z",
  "age_minutes": 300,
  "duration_seconds": null,
  "backup_size_mb": null,
  "collected_at": "2026-06-24T08:00:00Z",
  "message": "last backup end_time=2026-06-24 01:00:00",
  "collector_run_id": 123,
  "collector_run_item_id": 456
}
```

- **Mirror**: `api/inspection.py` pattern

#### Task 3.6: Create backup status collect entry point
- **Action**: 在 `BackupService` 中新增 `launch_collect()` 方法：
  - 输入：`{instance_ids, db_type_code, backup_type, sql_text, timeout_seconds, max_rows}`
  - **必须先调用 `SqlSafetyService.validate_sql_readonly(sql_text, db_type_code)` 做安全校验**，校验不通过直接拒绝
  - `business_domain` 固定为 `backup_status`，前端不能传入覆盖
  - `check_code` 固定为 `DB_READONLY_SQL_EXEC`，前端不能传入覆盖
  - `timeout_seconds` 限制 1~120，`max_rows` 限制 1~1000
  - `db_type_code` 与 `instance_ids` 对应的实例类型做一致性校验
  - 为每个 instance 构建 `business_domain="backup_status"` 的 `DB_READONLY_SQL_EXEC` collector_item：
    ```json
    {
      "item_key": "backup_status:{run_id}:{backup_type}:{instance_id}",
      "check_code": "DB_READONLY_SQL_EXEC",
      "executor_type": "db_sql_readonly",
      "business_domain": "backup_status",
      "target_scope": "db_instance",
      "asset_id": 1001,
      "policy_id": null,
      "backup_type": "RMAN",
      "rule_config": { "sql_text": "...", "timeout_seconds": 30, "max_rows": 200 }
    }
    ```
  - 通过 `BatchCollectorService` 发起 collector run
  - 返回 `{collector_run_id, status, awx_job_id}`
- **P0 不做**：复杂调度、cron 定时、恢复流程、备份策略复杂 UI。只做手动采集一次
- **Mirror**: `InspectionService.create_task()` → `BatchCollectorService.create_batch_run()` 模式

### Phase 4: Frontend (P0-2 + P0-3 frontend) — 最小可用闭环

**P0 范围内只做**：

1. `Items.vue`：SQL 编辑、validate-sql、verify-sql（异步轮询）、未验证不允许启用
2. `Reports.vue`：展示 evidence.columns / evidence.rows / raw_result
3. `backup/Jobs.vue`：展示 latest backup status

**P0 不做**：复杂图表、复杂矩阵、复杂任务编排、备份恢复流程、备份策略编辑

**前端强制约束**：
- 所有 API 请求走 `@/api/request`（禁止直接 import axios）
- 页面使用 `OpsPage` / `OpsPageHeader` / `OpsFilterBar` / `OpsTableShell` / `OpsModal` / `OpsDrawer` / `OpsEmptyState`
- 表格用原生 `<table>`，不引入第三方表格组件
- 状态 class 使用 `useStatusFormatters().getInspectionStatusClass()`（禁止硬编码颜色）
- 按钮用 `ops-primary-button` / `ops-secondary-button` / `ops-danger-button`
- 不写大段 inline style
- 空值显示 `-`

#### Task 4.1: Create frontend API modules
- **Action**: Create `frontend/src/api/inspection.ts`:
  - `listItems`, `createItem`, `updateItem`, `disableItem(id)` — `disableItem` 内部 PATCH `{enabled: false}`，P0 不提供 deleteItem
  - `validateSql(payload)`, `verifySql(payload)`, `getVerifySqlResult(verifyRunId)` — 轮询接口独立，不混在 verifySql 里
- **Action**: Create `frontend/src/api/backup.ts`:
  - `listBackupStatusLatest(params)`, `listBackupStatusHistory(params)`
- **Mirror**: `api/assets.ts` (uses `request` from `request.js`, exports plain object)

#### Task 4.2: Enhance inspection Items.vue
- **Action**: Expand the create/edit modal (`OpsModal size="xl"`):
  - Add `db_type_code` selector (ORACLE/POSTGRESQL/MYSQL/SQLSERVER)
  - Replace raw rule_config JSON textarea with structured form fields:
    - `sql_text` textarea (font-mono, min-h-[240px])
    - `timeout_seconds` (1-120, default 30)
    - `max_rows` (1-1000, default 200)
    - `status_column` input (default "RESULT_STATUS")
    - `message_column` input (default "MESSAGE")
  - Show SQL safety hints (只允许 SELECT/WITH/SHOW)
  - Show verified status badge + verified instance + verified time
- **Action**: Add "验证 SQL" button that opens verify-sql modal:
  - Instance selector dropdown (filter by db_type_code)
  - SQL summary preview
  - Execute button → 调用 `POST /inspection/items/verify-sql` 获取 `verify_run_id`
  - 轮询 `GET /inspection/items/verify-sql/{verify_run_id}` 每 2~3 秒一次
  - 轮询超过 120 秒自动停止，显示 timeout
  - 关闭 verify modal 时停止前端轮询，但不取消后端 AWX job
  - 再次打开时可按 verify_run_id 查询历史结果
  - Result table (max 20 rows)
  - On success: set `verified=true, verified_instance_id, verified_at`, allow `enabled=true`
  - On failure: set `verified=false`, force `enabled=false`, show error in red alert

**verify-sql 状态机**：

```text
pending → launched → running → success
                             → failed
                             → timeout
                             → rejected (SQL 安全校验不通过)
```
- **Action**: Frontend guards:
  - `sql_text` empty → disable submit
  - `db_type_code` empty → disable submit
  - `!verified` → disable `enabled=true`
  - SQL modified → auto-set `verified=false`
- **Mirror**: Existing `Items.vue` template structure

#### Task 4.3: Enhance inspection Reports.vue
- **Action**: In the detail drawer (`OpsDrawer`), add evidence display:
  - `evidence.columns` → table headers
  - `evidence.rows` → table body (first 20 rows)
  - `evidence.duration_ms`, `evidence.sql_hash`, `evidence.connector`
  - `evidence.stderr` (truncated)
  - Raw JSON toggle
- **Mirror**: Existing `Reports.vue` pattern

#### Task 4.4: Enhance backup Jobs.vue
- **Action**: Minimal usable backup status list:
  - Fetch from `GET /backup/status/latest`
  - Table: instance_name, db_type, backup_type, last_status, last_success_at, last_failure_at, recovery_point_at, age_minutes, collected_at, message
  - Filter: db_type, last_status, backup_type, keyword
  - Detail drawer: evidence, collector_run_id, collector_run_item_id, duration_ms, message
  - Status colors from `useStatusFormatters().getBackupStatusClass()`（**必须新增此方法**，不能用 `getInspectionStatusClass()`，因为备份状态枚举不同：`success/failed/warning/unknown` vs 巡检的 `normal/abnormal/warning/unknown`）
- **Mirror**: `Reports.vue` pattern

**新增 `getBackupStatusClass()` 到 `frontend/src/composables/useStatusFormatters.ts`**：

```typescript
export function getBackupStatusClass(status: Status): string {
  const normalized = (status || '').trim().toLowerCase()
  if (normalized === 'success') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  if (normalized === 'warning') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (normalized === 'failed') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (normalized === 'unknown') return 'border-slate-400/30 bg-slate-400/10 text-slate-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}
```

禁止在 `Jobs.vue` 硬编码 status badge 颜色。

#### Task 4.5: Ensure inspection Tasks.vue works with DB_READONLY_SQL_EXEC items
- **Action**: 确保任务创建流程兼容 DB SQL 巡检项：
  - 巡检项选择器中列出 `check_code == "DB_READONLY_SQL_EXEC"` 的项
  - 任务列表中的 status 使用 `useStatusFormatters().getInspectionStatusClass()`
- **P0 不做**：复杂任务编排界面、调度配置 UI
- **Mirror**: Existing `Tasks.vue` structure

### Phase 5: Integration Testing & Verification

#### Task 5.1: End-to-end manual test (最小验证路径)
- **Action**: 手工插入 `inspection_item` → 后端创建任务 → AWX 执行 `DB_READONLY_SQL_EXEC` → callback 写 `inspection_result`
- **Action**: 前端验证：Items.vue SQL 编辑 → validate-sql → verify-sql → 启用 → 创建任务 → Reports.vue 查看 evidence
- **Action**: 备份：`backup_status_snapshot` DDL 执行 → callback 写备份状态 → Jobs.vue 查看

## Validation

```bash
# AWX playbook syntax
cd /home/lisiyang/ansible-playbooks && ansible-playbook --syntax-check playbooks/dbops_collector_generic.yml

# collector_client compilation
cd /home/lisiyang/dbops-collector && python -m compileall collector_client/

# Backend compilation
cd /home/lisiyang/dbops/backend && source ../.venv/bin/activate && python -m compileall app/

# Frontend type check
cd /home/lisiyang/dbops/frontend && npx vue-tsc --noEmit

# Full verify
bash /home/lisiyang/dbops/scripts/ai/verify.sh
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| DB_READONLY_SQL_EXEC 放在 pre-copy 之前导致 /tmp/collector_client 不存在 | **Critical** | 已将 `DB_READONLY_SQL_EXEC` 纳入 `db_python_collect_check_codes`，pre-copy 条件覆盖 |
| verify-sql 后端直连 DB 导致两套连接逻辑 | **High** | 采用 AWX 异步方案（方案 B），复用 Collector EE 驱动和凭证注入 |
| SQL 安全校验用简单字符串包含导致误杀（如 `created_at`） | **High** | 强制使用 `\bKEYWORD\b` token 级单词边界匹配，先去掉注释 |
| callback 解析 item_key 反推业务字段不可靠 | **High** | collector_item 显式携带 `task_id`/`inspection_item_id`/`item_code`/`business_domain` |
| backup_status_snapshot 强绑 inspection_task 导致后续耦合 | Medium | backup_status 作为独立 business_domain 写入，不与 inspection_result 耦合 |
| Oracle 权限不足导致运行时失败 | Medium | 权限标注"需现场确认"，collector 返回 `PERMISSION_DENIED` 而非笼统失败 |
| Frontend P0 超范围做复杂大屏拖延交付 | Medium | 明确 P0 只做 Items SQL 编辑+验证 / Reports evidence / Jobs status list |

## Acceptance

- [ ] `dbops_collector_generic.yml` syntax check passes
- [ ] New `db_sql_readonly_collect` role routes and executes (after pre-copy)
- [ ] Existing port_check / db_fact_collect / os_fact_collect unaffected
- [ ] `collector_client` outputs valid JSON for both success and failure
- [ ] Single item failure does not fail entire AWX job
- [ ] `collector_run.job_type` CHECK 约束已确认/更新支持 `SQL_VERIFY`
- [ ] Ansible 路由条件包含 `inspection_verify`（verify-sql item 不被跳过）
- [ ] callback 按 `business_domain` 正确分流（inspection→inspection_result, backup_status→snapshot, inspection_verify→只更新 result）
- [ ] SQL safety 先屏蔽字符串字面量再做关键词匹配（`SELECT 'DROP TABLE' AS msg` 不误杀）
- [ ] SQL safety 关键词使用 `re.escape` + 长度倒序
- [ ] `INTO` 不在全局关键词列表，改用 `SELECT ... INTO` 模式级检测
- [ ] SQL safety blocks `FOR UPDATE`/`DBMS_LOCK`/`UTL_HTTP`/`PG_SLEEP` etc.
- [ ] 末尾单个分号被自动 strip，中间分号被拒绝
- [ ] `validate-sql` and `verify-sql` API endpoints work
- [ ] verify-sql 使用 AWX 异步方案，复用 collector_run 存状态
- [ ] Inspection task with `DB_READONLY_SQL_EXEC` items dispatches to AWX
- [ ] callback_item 顶层透传 `business_domain`/`task_id`/`inspection_item_id`/`item_code`
- [ ] Callback writes `inspection_result` with mult-row status priority aggregation
- [ ] `backup_status_snapshot` table + view exist (with rollback SQL)
- [ ] `POST /backup/status/collect` 手动采集入口可用
- [ ] Callback writes `backup_status_snapshot` for `business_domain=backup_status`
- [ ] `GET /backup/status/latest` 返回 join 后的前端可用数据（含 instance_name/db_type_code/host/port）
- [ ] Frontend Items.vue supports SQL editor + verify-sql modal with 2-3s polling + 120s timeout
- [ ] Frontend Reports.vue shows evidence (columns + rows)
- [ ] `getBackupStatusClass()` 已添加到 `useStatusFormatters.ts`（备份 success/failed/warning/unknown）
- [ ] Frontend Jobs.vue shows latest backup status（使用 `getBackupStatusClass`，无硬编码颜色）
- [ ] `verify.sh` passes all tests

## Commit Plan

1. `feat(collector): add db readonly sql collect role` — role + playbook route
2. `feat(collector-client): support db_sql_readonly executor` — CLI dispatch + SQL executor + JSON output
3. `feat(backend): add readonly sql safety and inspection sql dispatch` — SqlSafetyService + validate-sql/verify-sql APIs + DB_READONLY_SQL_EXEC builder + callback merge
4. `feat(backup): add backup status snapshot collection` — DDL + BackupService + callback + API
5. `feat(frontend): support dynamic sql inspection and backup status list` — Items.vue enhancement + Reports.vue evidence + Jobs.vue backup status

## 需用户配合事项

- **Oracle 权限需现场确认**：`dba_data_files`、`dba_free_space`、`v$rman_backup_job_details` 查询权限未在所有目标 Oracle 实例上验证。开发完成后需在对应对 Oracle DB 上执行示例 SQL 确认权限。collector_client 会对权限不足返回明确的 `PERMISSION_DENIED` error_code
- **DDL 回滚**：所有 DDL 变更均配套生成 `rollback_*.sql`，当前环境为测试环境，可直接执行，便于追溯和回滚
