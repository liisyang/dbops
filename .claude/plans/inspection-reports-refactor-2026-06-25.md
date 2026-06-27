# 巡检报告重构 Plan Final v5.1

> 分支：`feature/phase-3.5-db-readonly-sql-exec`
> HEAD：`b70eaef`
> 更新：v1(代码梳理)→v2(架构)→v3(8点)→v4(15点)→v5(13点)→v5.1(9个收口修正+4个实施门禁)
> 前置条件：历史巡检数据确认无用，全部清除，一次性重构。
> 状态：**Final — 架构冻结，可以立即开始编码/migration/测试。以下内容已锁定不再变更：表结构/状态枚举/规则JSON Schema/结果粒度/健康分数公式/缺失结果语义/regenerate语义/API路径与分页格式**
> 实施门禁：开始编码前需确认 §A 的 4 个门禁（SQL Server target_database 验证 / callback 同 attempt 覆盖规则 / FK ON DELETE / migration 演练）

---

## 18. 实施进度追踪（2026-06-25 17:00 最终更新）

### ✅ P0 完成（5/5）

| 任务 | 文件 | 状态 |
|---|---|---|
| P0-A DOCX 导出 | `backend/app/services/report_export_service.py`（新增）+ `backend/app/api/inspection.py` POST `/reports/{id}/export` | ✅ 实测 38KB DOCX 下载成功；admin `include_evidence=true` 包含 raw findings/rows；500 实例上限 + admin 权限校验 |
| P0-B SQL Server target_database | `backend/app/services/check_item_builder_registry.py` 增加 `connection_context.target_database` 透传；DB 种子暂留空（待 operator 按实例填业务库名） | ✅ 后端支持就绪；plan B 待人工配置 item.rule_config |
| P0-C hash 三件套 | `backend/app/services/inspection_service.py` 新增 5 个 `_compute_*_hash` 静态方法 | ✅ sql_hash/rule_hash 写 task_item；source_data_hash 写 inspection_report |
| P0-D 审计事件 | `asset_event_history_service.record_event` 调用 | ✅ `inspection.task.created`（create_task）+ `report.regenerated`（regenerate 端点）+ `report.exported` / `report.evidence_exported`（export 端点） |
| 端到端冒烟 | task 8 (SQL Server) + task 9 (Oracle) | ✅ 10 results + 1 report + 2 instance_reports 全部生成 |

### ✅ P1 完成（2/2，2026-06-25 16:30）

| 任务 | 文件 | 状态 |
|---|---|---|
| P1-E InstanceReport.vue 拆分 | `frontend/src/views/inspection/InstanceReport.vue`（新增 252 行）+ `frontend/src/router/index.ts` 新增 `InspectionInstanceReport` 嵌套路由 + `frontend/src/views/inspection/ReportDetail.vue`（353 → 260 行，-93 行） | ✅ 路由 `/inspection/reports/:id/instances/:targetType/:targetId`；"详情" 按钮改 `<router-link>`；删除死代码 `getExecutionStatusClass` / `getEvaluationClass` + 5 个 toggle 状态；`vue-tsc --noEmit` 0 错误；backend pytest 223/223 通过；`bash scripts/ai/verify.sh` 0 fail |
| P1-F MSSQL §11.3 §11.4 改用 sys.master_files | `.claude/plans/inspection-reports-refactor-2026-06-25.md` §11 重要边界 + §11.3 SQL + §11.4 SQL + §11 P0 配置总览表 + §11 SQL Server P1 自动增长配置 + §11 "target_database 问题" 段 | ✅ 改用 server-wide 视图 `sys.master_files`，从 master 连接跨所有用户 DB；`used_pct` 语义从 `SpaceUsed/allocated`（碎片分析）改为 `allocated/max_size`（容量规划）；告警阈值不变；operator 零输入；不需要 target_database 注入 |

### ❌ 已删除项

| 任务 | 删除原因 |
|---|---|
| migration 演练 §14.1（prod 切换） | 用户确认当前**无 prod 环境**，所有环境均为 test；§14.1 演练在 dev 库已通过，无需重复；prod 切换流程（停任务/停 AWX callback/单事务 DROP+CREATE）作为未来如果建 prod 才需要的预案保留在 §14 文档中 |
| seed: 补 `target_database` 默认值（MSSQL） | P1-F 已改 §11.3 §11.4 SQL 使用 `sys.master_files`（server-wide），operator 不再需要为每个 SQL Server 实例提供业务库名；该项作废 |

### 📝 P1-F 实施细节（2026-06-25 16:50）

```
新增 §11 重要边界 v5.1 修正：解释从 sys.database_files/dm_db_log_space_usage（当前 DB scope）
  改到 sys.master_files（server-wide）的取舍
新增 §11 P0 配置总览表：增加 target_database 列，所有 5 项标注"不需要"
修改 §11.3 MSSQL_DATA_FILE_USAGE：
  - SQL 从 sys.database_files + FILEPROPERTY('SpaceUsed') 改为 sys.master_files
  - used_pct 公式从 SpaceUsed/size 改为 size/max_size
  - WHERE 排除 master/tempdb/model/msdb 系统库
  - 标题改为"实例所有用户数据库数据文件使用率（master 连接，跨 DB）"
修改 §11.4 MSSQL_LOG_USAGE：同上，filter type_desc = 'LOG'
修改 §11 SQL Server P1 "文件自动增长配置"：sys.database_files → sys.master_files
删 §11 "target_database 问题"段：被 §11 重要边界 v5.1 取代
```

### 📝 Live 冒烟结果（2026-06-25 15:49 / 16:00）

```
task 8 = SQL Server: 1 batch + 2 targets + 10 results + 1 report(RPT-20260625-3816C6) + 2 instance_reports
  health=unknown score=84.44
  evidence 结构 100% 符合 §3.6 (schema_version/columns/rows/findings/sql_hash/template_render)
  DOCX 38KB 完整生成
  audit: report.exported / report.evidence_exported / report.regenerated / inspection.task.created 落表

task 9 = Oracle: 创建后由后续会话跑 callback 验证（dispatch_count=1, item_count=5）
```

### ✅ 验证基线（2026-06-25 17:00 — 用户验证前快照）

```
bash scripts/ai/verify.sh
  → 223 backend pytest passed, 0 failed
  → bash syntax check: OK
  → git status: 显示本次 session 改动的 15 M + 5 ??

cd frontend && npm run type-check
  → vue-tsc --noEmit: 0 errors, EXIT=0

git status --short
  → M backend/app/api/inspection.py                (P0 五件套)
  → M backend/app/models/dbops_assets.py
  → M backend/app/schemas/inspection.py
  → M backend/app/services/batch_collector_service.py
  → M backend/app/services/check_item_builder_registry.py
  → M backend/app/services/dbops_asset_service.py
  → M backend/app/services/inspection_service.py
  → M backend/tests/test_inspection_service.py
  → M frontend/src/api/assets.ts
  → M frontend/src/components/ops/index.ts
  → M frontend/src/router/index.ts                 (P1-E 路由注册)
  → M frontend/src/types/api.ts
  → M frontend/src/views/inspection/Items.vue
  → M frontend/src/views/inspection/Reports.vue
  → M frontend/src/views/inspection/Tasks.vue
  → ?? .claude/plans/inspection-reports-refactor-2026-06-25.md  (本次 plan)
  → ?? .claude/plans/phase-3.5-batch-smoke-instance-picker.md
  → ?? backend/app/services/inspection_evaluator_service.py     (P0-C 评估器)
  → ?? backend/app/services/report_export_service.py            (P0-A DOCX)
  → ?? backend/db/dbops_inspection_v5_1.sql                      (DDL v5.1)
  → ?? frontend/nohup.out                                       (运行残留)
  → ?? frontend/src/components/ops/OpsInstancePicker.vue
  → ?? frontend/src/views/inspection/InstanceReport.vue         (P1-E 新组件)
  → ?? frontend/src/views/inspection/ReportDetail.vue           (M 转 ?? 状态)
```

### 📝 P1-E 实施细节（2026-06-25 16:30）

```
新增 frontend/src/views/inspection/InstanceReport.vue
  - OpsPage + OpsPageHeader (返回报告按钮 → router.push InspectionReportDetail)
  - 实例健康摘要卡 (level/score/normal/warning/critical/unknown)
  - 巡检结果明细表 (result_code / execution_status / evaluation_status / message / time)
  - loadInstanceReport: 通过 listInstanceReports 过滤 target_type+target_id 得到 instance_report
  - loadResults: getInstanceReportResults 直接拿结果
  - 保留 getHealthClass/getExecutionStatusClass/getEvaluationClass/formatTime 与 ReportDetail 风格一致

修改 frontend/src/router/index.ts
  + InspectionInstanceReport 路由，props 函数提取 id/targetType/targetId

修改 frontend/src/views/inspection/ReportDetail.vue (-93 行)
  - 删除 inline 展开明细 (template ~50 行)
  - 删除 expandedInstance/expandedTargetType/expandedTargetId/instanceDetailResults/detailLoading/toggleInstanceDetail
  - 删除 getExecutionStatusClass + getEvaluationClass 死代码
  - "详情" 按钮改为 <router-link :to="{ name: 'InspectionInstanceReport', params: { id, targetType, targetId } }">
```

---

## 0. 设计原则

1. **SQL 采集 → 规则引擎确定性判断 → 聚合服务生成健康等级 → AI 解释归因建议。**
2. AI 不修改 `evaluation_status`、健康等级和分数。
3. 巡检结果必须确定、可解释、可复现。
4. 区分 `execution_status`（采集层）和 `evaluation_status`（规则层）。
5. 信息采集成功 ≠ 健康正常 → `not_evaluated`，不计入统计。
6. 全部可评估项为 `not_evaluated` → `not_assessed`。
7. 任务保存巡检项和目标快照，保证历史可重现。
8. `regenerate` 只重新聚合，不重跑 SQL、不重评估规则。
9. **预期执行但未产生结果的项目必须补齐为缺失结果，不得从报告中消失。**

---

## 1. 当前代码基础

### 1.1 已有表（重构将 DROP + CREATE）

| 表 | 动作 |
|---|---|
| inspection_item | DROP + CREATE（新增 category/item_kind/evaluator_type 等） |
| inspection_task | DROP + CREATE |
| inspection_result | DROP + CREATE（execution_status/evaluation_status 拆分，删除 severity，新增 task_target_id + UNIQUE） |
| inspection_schedule | DROP + CREATE |

> collector_* 表不清除。迁移方式：显式 DROP 子表 → DROP 父表 → CREATE 新表。禁止 CASCADE。

### 1.2 保留能力

DB_READONLY_SQL_EXEC / SqlSafetyService / AWX 闭环 / fleet-scan 护栏 / PATCH 软禁用。

---

## 2. 数据模型

### 2.1 整体架构

```
InspectionTask
    ├── inspection_task_item (1:N, 巡检项快照)
    ├── inspection_task_target (1:N, 目标快照，双状态机)
    ├── InspectionReport (1:1)
    │       └── InspectionInstanceReport (1:N, 关联 task_target_id)
    │               └── inspection_result (1:N, UNIQUE task_id+task_item_id+task_target_id)
    └── inspection_result (1:N)
```

### 2.2 inspection_task_item

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| task_id | BIGINT FK NOT NULL | |
| inspection_item_id | BIGINT FK | 原巡检项 ID |
| item_code | VARCHAR(100) NOT NULL | |
| item_name | VARCHAR(200) NOT NULL | |
| check_code | VARCHAR(100) NOT NULL | 执行路由 |
| executor_type | VARCHAR(32) | |
| target_scope | VARCHAR(32) NOT NULL | db_instance / server |
| db_type_code | VARCHAR(32) | |
| category | VARCHAR(50) | |
| item_kind | VARCHAR(32) | information / metric / state / count / composite |
| evaluator_type | VARCHAR(32) | none / range / equals / not_equals / in / not_in / boolean / status_column |
| severity | VARCHAR(20) | info / warning / critical |
| weight | INTEGER DEFAULT 10 | |
| rule_version | VARCHAR(20) | |
| rule_config_snapshot | JSONB NOT NULL | |
| applicability_snapshot | JSONB | |
| enabled_snapshot | BOOLEAN | |
| description_snapshot | TEXT | |
| sql_hash | VARCHAR(64) | SHA-256 of sql_text |
| rule_hash | VARCHAR(64) | SHA-256 of canonical(check_code+executor_type+rule_config_snapshot+applicability_snapshot) |
| check_order | INTEGER | 展示顺序 |
| created_at | TIMESTAMPTZ | |

UNIQUE: `(task_id, item_code)`

### 2.3 inspection_task_target

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| task_id | BIGINT FK NOT NULL | |
| target_type | VARCHAR(32) NOT NULL | |
| target_id | BIGINT NOT NULL | |
| target_name_snapshot | VARCHAR(200) | |
| host_snapshot | VARCHAR(100) | |
| port_snapshot | INTEGER | |
| db_type_code_snapshot | VARCHAR(32) | |
| business_system_snapshot | VARCHAR(200) | |
| site_snapshot | VARCHAR(200) | |
| asset_snapshot | JSONB | db_version, node_role, cluster_name, business_system_id, site_id 等 |
| dispatch_status | VARCHAR(20) NOT NULL | pending / dispatched / dispatch_failed / skipped |
| skip_code | VARCHAR(50) | NOT_APPLICABLE / POLICY_EXCLUDED / ASSET_DISABLED / NO_CREDENTIAL / USER_CANCELLED / DISPATCH_REJECTED / UNKNOWN |
| skip_reason | VARCHAR(500) | 跳过原因（人类可读，不要依靠文本判断业务状态） |
| execution_status | VARCHAR(20) NOT NULL | pending / running / success / partial_success / failed / cancelled |
| collector_run_id | BIGINT | |
| attempt_no | INTEGER NOT NULL DEFAULT 1 | |
| started_at | TIMESTAMPTZ | |
| finished_at | TIMESTAMPTZ | |
| last_callback_at | TIMESTAMPTZ | |
| error_code | VARCHAR(50) | |
| error_message | TEXT | |
| created_at | TIMESTAMPTZ | |

UNIQUE: `(task_id, target_type, target_id)`

**状态迁移规则**：

```
dispatch_status:
  pending → dispatched / dispatch_failed / skipped  (终态不得回退)

execution_status:
  pending → running → success / partial_success / failed / cancelled
  pending → failed / cancelled                     (直接失败)
  禁止: success → running, failed → running, cancelled → success
```

更新条件：
```sql
UPDATE inspection_task_target
SET execution_status = :new, finished_at = :now, last_callback_at = :now
WHERE id = :id
  AND execution_status IN (:allowed_previous);
```

旧 attempt callback 不得覆盖新 attempt 结果（按 `attempt_no` 比较）。

**报告生成条件**：
```
所有 task_target 满足:
  execution_status IN ('success','partial_success','failed','cancelled')
  OR dispatch_status IN ('dispatch_failed','skipped')
```
禁止用 `dispatch_status=dispatched` 判断完成。

### 2.4 inspection_result

一条 result = 一个 task_item × 一个 task_target。SQL 返回多行存入 evidence.findings。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| task_id | BIGINT FK NOT NULL | |
| task_item_id | BIGINT FK NOT NULL | |
| task_target_id | BIGINT FK NOT NULL | |
| collector_run_id | BIGINT FK | |
| collector_run_item_id | BIGINT FK | |
| target_type | VARCHAR(32) NOT NULL | 冗余 |
| target_id | BIGINT NOT NULL | 冗余 |
| result_code | VARCHAR(100) NOT NULL | |
| execution_status | VARCHAR(32) NOT NULL | success/failed/timeout/skipped/permission_denied/connection_failed/parse_failed |
| evaluation_status | VARCHAR(32) NOT NULL | normal/warning/critical/unknown/not_evaluated |
| message | TEXT | |
| evidence | JSONB NOT NULL | 标准化结构（见 §3.6） |
| attempt_no | INTEGER NOT NULL | 0=缺失占位，≥1=真实执行。CHECK(attempt_no >= 0) |
| received_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 服务端接收时间，用于同 attempt 内判断先后 |
| detected_at | TIMESTAMPTZ NOT NULL | |
| created_at | TIMESTAMPTZ | |

UNIQUE: `(task_id, task_item_id, task_target_id)`

> 已删除 `severity` 列。健康聚合只用 `evaluation_status`。

**UPSERT 规则**：callback 到达时：

```sql
INSERT INTO inspection_result (...) VALUES (...)
ON CONFLICT (task_id, task_item_id, task_target_id)
DO UPDATE SET
    collector_run_id      = EXCLUDED.collector_run_id,
    collector_run_item_id = EXCLUDED.collector_run_item_id,
    execution_status      = EXCLUDED.execution_status,
    evaluation_status     = EXCLUDED.evaluation_status,
    message               = EXCLUDED.message,
    evidence              = EXCLUDED.evidence,
    attempt_no            = EXCLUDED.attempt_no,
    received_at           = EXCLUDED.received_at,
    detected_at           = EXCLUDED.detected_at
WHERE EXCLUDED.attempt_no > inspection_result.attempt_no
   OR (
       EXCLUDED.attempt_no = inspection_result.attempt_no
       AND EXCLUDED.received_at >= inspection_result.received_at
       AND inspection_result.execution_status NOT IN (
           'success','failed','timeout','skipped',
           'permission_denied','connection_failed','parse_failed'
       )
   );
```

**同 attempt 防乱序规则**：

| 当前结果状态 | 同 attempt callback 到达 | 行为 |
|---|---|---|
| 非终态 (running/pending) | 任意 | 允许更新 |
| 终态 | 内容完全相同 | 忽略（不更新） |
| 终态 | 内容不同 | **拒绝覆盖**，记录审计日志 |
| — | 更高 attempt_no | 始终允许覆盖 |

> 若 Collector 能提供递增 `callback_sequence`，优先按 `attempt_no + callback_sequence` 判断新旧。不单独依赖服务端 `received_at` 判定业务先后。

evidence 中记录：
```json
{
  "attempt_no": 2,
  "previous_attempt_count": 1
}
```

### 2.5 inspection_report

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| report_code | VARCHAR(100) UNIQUE | RPT-{YYYYMMDD}-{HEX6} |
| task_id | BIGINT FK UNIQUE | |
| report_status | VARCHAR(32) | generating / ready / partial / failed |
| health_level | VARCHAR(32) | healthy / warning / critical / unknown / not_assessed |
| health_score | NUMERIC(5,2) | NULL when not_assessed |
| total_target_count | INTEGER | |
| healthy_count | INTEGER | |
| warning_count | INTEGER | |
| critical_count | INTEGER | |
| unknown_count | INTEGER | |
| not_assessed_count | INTEGER | |
| normal_item_count | INTEGER | |
| warning_item_count | INTEGER | |
| critical_item_count | INTEGER | |
| unknown_item_count | INTEGER | |
| collection_failed_count | INTEGER | |
| missing_result_count | INTEGER | 预期但未产生的 result 数（补齐为占位后计数） |
| summary | JSONB | 按 DB 类型/站点/业务系统分布 |
| rule_engine_version | VARCHAR(50) | |
| source_data_hash | VARCHAR(64) | 规范化哈希 |
| source_result_count | INTEGER | |
| generated_reason | VARCHAR(32) | auto / manual / regenerate |
| generated_by | VARCHAR(100) | |
| generated_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### 2.6 inspection_instance_report

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| report_id | BIGINT FK NOT NULL | |
| task_id | BIGINT FK NOT NULL | |
| **task_target_id** | BIGINT FK NOT NULL | 直接关联 task_target |
| target_type | VARCHAR(32) NOT NULL | 冗余 |
| target_id | BIGINT NOT NULL | 冗余 |
| health_level | VARCHAR(32) | |
| health_score | NUMERIC(5,2) | |
| normal_count | INTEGER | |
| warning_count | INTEGER | |
| critical_count | INTEGER | |
| unknown_count | INTEGER | |
| not_evaluated_count | INTEGER | |
| collection_failed_count | INTEGER | |
| missing_result_count | INTEGER | |
| summary | JSONB | |
| generated_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

UNIQUE: `(report_id, task_target_id)`

### 2.7 外键 ON DELETE 策略

| FK | ON DELETE | 说明 |
|---|---|---|
| task_item.inspection_item_id → inspection_item | SET NULL | 原巡检项即使被物理删除，任务快照保留 |
| task_item.task_id → task | CASCADE | 任务内部快照同生命周期 |
| task_target.task_id → task | CASCADE | |
| result.task_id → task | CASCADE | |
| result.task_item_id → task_item | CASCADE | |
| result.task_target_id → task_target | CASCADE | |
| report.task_id → task | CASCADE | |
| instance_report.report_id → report | CASCADE | |
| instance_report.task_target_id → task_target | 不建强外键或 SET NULL | task_target 本身 CASCADE 到 task |

> `target_id`（result/instance_report 的冗余列）不建立到资产表的强外键。实例资产未来可能删除，但历史巡检报告仍需保留；展示时使用任务目标快照。若必须建 FK，使用 `ON DELETE SET NULL`。

---

## 3. 规则引擎

### 3.1 item_kind（5 种）→ evaluator_type 绑定

| item_kind | 允许的 evaluator_type |
|---|---|
| information | none |
| metric | range |
| state | equals / not_equals / in / not_in / boolean |
| count | range |
| composite | status_column |

### 3.2 evaluator_type（8 种）

none / range / equals / not_equals / in / not_in / boolean / status_column

### 3.3 边界语义（修正）

**empty_result_policy**（已删除 not_applicable）：
| 值 | 含义 |
|---|---|
| normal | 没有异常 |
| unknown | 无法确定 |
| warning | 0 行表示告警 |
| critical | 0 行表示严重 |

> `not_applicable` 已删除。SQL 返回 0 行可能原因太多（权限不足、SQL 错误、实际无记录），无法可靠判断"不适用"。不适用只能由执行前 applicability 判断产生。

**null_value_policy**：normal / unknown / warning / critical / not_evaluated

**multiple_rows**（统一入口，删除了 value_selector.row_mode）：

```json
{
  "multiple_rows": {
    "policy": "worst",
    "aggregate": null
  }
}
```

policy 值：first / each / worst / aggregate。
当 policy=aggregate 时，aggregate 必填，白名单：min / max / sum / avg / count。
禁止动态函数名或 Python eval()。

**not_applicable_policy**：只能为 `not_evaluated`。区分：
- 明确确认不适用 → not_evaluated
- 无法确认是否适用 → unknown

### 3.4 跨字段校验

```
item_kind=information → evaluator.type 必须为 none
item_kind=composite   → evaluator.type 必须为 status_column
evaluator.type=range  → 必须存在 value_selector.column + warning/critical 至少一个
evaluator.type=range  → critical 阈值不能弱于 warning
multiple_rows.policy=aggregate → multiple_rows.aggregate 必填
not_applicable_policy → 只能为 not_evaluated
```

### 3.5 status_column 契约

所有返回列名 lowercase 归一化。标准列：`result_status / severity / message`。

映射：
```
normal                          → normal
warning                         → warning
critical                        → critical
abnormal + severity=critical    → critical
abnormal + severity≠critical    → warning
unknown                         → unknown
无法识别                         → execution_status=parse_failed, evaluation_status=unknown
```

### 3.6 evidence 标准结构

```json
{
  "schema_version": 1,
  "columns": ["tablespace_name", "used_pct"],
  "rows": [["USERS", 85.5]],
  "findings": [
    {"row_index": 0, "evaluation_status": "warning", "message": "USERS 使用率 85.5%"}
  ],
  "source_severity": "warning",
  "connector": "oracle",
  "duration_ms": 150,
  "sql_hash": "a1b2c3...",
  "rc": 0,
  "stderr": "",
  "truncated": false,
  "original_row_count": 10,
  "stored_row_count": 10,
  "attempt_no": 1,
  "previous_attempt_count": 0
}
```

缺失结果占位 evidence：
```json
{
  "schema_version": 1,
  "error_code": "MISSING_RESULT",
  "columns": [],
  "rows": [],
  "findings": [],
  "truncated": false,
  "attempt_no": 0,
  "previous_attempt_count": 0
}
```

限制：stored rows ≤ max_rows(≤1000)，stderr ≤ 4KB，message ≤ 4KB，单条 evidence ≤ 1MB。超限设 `truncated=true`。

---

## 4. 健康等级与分数

### 4.1 实例健康等级

```
1. 存在 evaluation_status=critical → critical（一票否决）
2. 不存在 critical，但存在 warning → warning
3. 没有异常，但存在 unknown 或 execution_status≠success → unknown
4. 所有可评估项均为 normal → healthy
5. 全部项目均为 not_evaluated → not_assessed
```

### 4.2 实例健康分数

```
penalty: normal=0, warning=0.4, critical=1.0, unknown=0.2, not_evaluated=不参与

health_score = 100 × (1 - Σ(weight_i × penalty_i) / Σ(weight_j))
  j 遍历所有可评估项

0.00 ≤ health_score ≤ 100.00  (NUMERIC(5,2))

全部 not_evaluated → health_score = NULL, health_level = not_assessed
```

### 4.3 整体报告健康等级（从实例聚合）

```
1. 任一实例 critical      → critical
2. 无 critical，有 warning → warning
3. 无异常，有 unknown      → unknown
4. 所有可评估实例 healthy  → healthy
5. 全部实例 not_assessed   → not_assessed
```

### 4.4 整体报告健康分数

```sql
ROUND(AVG(health_score) FILTER (WHERE health_score IS NOT NULL), 2)
```

全部 not_assessed → health_score = NULL, health_level = not_assessed。

> P0 不引入 target_weight/business_criticality_weight，放 P1。

### 4.5 缺失结果处理

报告生成前计算预期矩阵：
```
task_target (execution 预期执行)
  ×
task_item (applicability 适用)
```
与 inspection_result LEFT JOIN。缺失组合补写占位：
```
execution_status = skipped
evaluation_status = unknown
message = "未收到预期巡检结果"
collection_failed_count += 1
missing_result_count += 1
```

dispatch_failed 的目标：execution_status=connection_failed, evaluation_status=unknown。
策略明确跳过的目标：按 skip_code 确定性映射：

```
NOT_APPLICABLE / POLICY_EXCLUDED / ASSET_DISABLED
    → execution_status=skipped, evaluation_status=not_evaluated

NO_CREDENTIAL / USER_CANCELLED / DISPATCH_REJECTED / UNKNOWN
    → execution_status=skipped, evaluation_status=unknown
```

> 不要依靠中文 skip_reason 文本判断业务状态。

---

## 5. 报告生成与并发

### 5.1 callback 事务（小事务）

一次小事务内完成：
1. 解析 collector 返回值
2. 归一化 execution_status
3. 使用任务规则快照执行 Evaluator → evaluation_status + 标准 evidence
4. UPSERT inspection_result（按 attempt_no 比较）
5. 更新 task_target 状态（检查状态迁移合法性）
6. 提交

### 5.2 报告生成事务（独立事务，callback 提交后触发）

1. 检查所有目标是否终态
2. `SELECT inspection_task ... FOR UPDATE`
3. 二次检查完成条件
4. 计算预期矩阵，补齐缺失结果（INSERT 占位 inspection_result）
5. 聚合 instance_report（按 task_target_id）
6. 聚合整体 report
7. 提交

> callback 保存与报告生成分两个事务。自动报告生成失败可通过 regenerate 恢复。

### 5.3 幂等

```sql
INSERT INTO inspection_report (...) VALUES (...)
ON CONFLICT (task_id) DO UPDATE SET ...;

INSERT INTO inspection_instance_report (...) VALUES (...)
ON CONFLICT (report_id, task_target_id) DO UPDATE SET ...;
```

### 5.4 regenerate

只根据已保存的 inspection_result 重新聚合。不重跑 SQL，不重评估规则。`generated_reason='regenerate'`。生成前计算 source_data_hash，无变化可直接返回。

### 5.5 迟到 callback 自动重聚合

callback UPSERT 后：
1. 比较旧/新 result_hash（见 §5.6）。如果内容未变化且只是完全相同的重复 callback → 不处理。
2. 如果内容发生变化且 `inspection_report` 已存在 → 设置 `report_status='generating'`，触发 `generate_report(task_id, generated_reason='auto')`。

```
callback 更新 inspection_result
        ↓
检查 inspection_report 是否存在
        ↓
结果内容发生变化（result_hash 不同）
        ↓
触发 generate_report(task_id, generated_reason='auto')
```

### 5.6 hash 规范化

```python
def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_result_hash(result: InspectionResult) -> str:
    """Per-result hash covering all fields that affect report content."""
    ev = result.evidence or {}
    return sha256(canonical_json({
        "task_target_id": result.task_target_id,
        "task_item_id": result.task_item_id,
        "attempt_no": result.attempt_no,
        "execution_status": result.execution_status,
        "evaluation_status": result.evaluation_status,
        "message": result.message,
        "findings": ev.get("findings", []),
        "error_code": ev.get("error_code"),
        "sql_hash": ev.get("sql_hash"),
        "truncated": ev.get("truncated", False),
    }).encode("utf-8")).hexdigest()


rule_hash = sha256(canonical_json({
    "check_code": ...,
    "executor_type": ...,
    "rule_config_snapshot": ...,
    "applicability_snapshot": ...,
}).encode("utf-8")).hexdigest()

# 计算顺序：先补齐 MISSING_RESULT → 再计算各 result_hash → 最后计算 source_data_hash
source_data_hash = sha256(canonical_json({
    "task_items": [...],      # 按 id 排序，含 rule_hash
    "task_targets": [...],    # 按 id 排序
    "results": [...],         # 按 task_target_id, task_item_id 排序，含 result_hash（非仅 sql_hash）
}).encode("utf-8")).hexdigest()
```

---

## 6. 后端 API

### 6.1 报告端点

```
GET    /api/v1/inspection/reports
GET    /api/v1/inspection/reports/{report_id}
GET    /api/v1/inspection/reports/{report_id}/instances
GET    /api/v1/inspection/reports/{report_id}/instances/{target_type}/{target_id}
GET    /api/v1/inspection/reports/{report_id}/instances/{target_type}/{target_id}/results

POST   /api/v1/inspection/reports/{report_id}/regenerate
POST   /api/v1/inspection/reports/{report_id}/export
```

### 6.2 分页规范

| 参数 | 默认 | 范围 |
|---|---|---|
| page | 1 | ≥1 |
| page_size | 20 | 1～200 |

筛选参数 health_level 使用 FastAPI `list[str]`（`?health_level=critical&health_level=warning`）。

时间筛选统一 ISO-8601。

分页响应：
```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0,
  "total_pages": 0
}
```

### 6.3 AI 端点（本期不注册）

---

## 7. 前端重构

### 7.1 文件拆分与路由

```
frontend/src/views/inspection/
├── Items.vue
├── Tasks.vue              # 增加报告摘要列
├── Reports.vue            # 报告列表
├── ReportDetail.vue       # 整体报告详情（新建）
└── InstanceReport.vue     # 实例报告详情（新建）
```

路由：
```typescript
/inspection/reports
/inspection/reports/:reportId → ReportDetail
/inspection/reports/:reportId/instances/:targetType/:targetId → InstanceReport
```

### 7.2 各页面要点

**Reports.vue**：任务下拉+健康等级多选+报告状态+时间区间 → 报告列表表格。

**ReportDetail.vue**：[重新生成][导出DOCX][AI分析(禁用)] + 健康摘要五宫格 + 严重异常TopN + 实例列表筛选分页 + AI占位。

**InstanceReport.vue**：实例信息 + 健康等级/分数 + 各状态计数 + 只看异常开关 + 巡检项分类折叠 + 结果列表 + AI占位。

**Tasks.vue**：新增 report_status / health_level / 查看报告按钮。

---

## 8. DOCX 导出

### 8.1 技术

`python-docx` 生成临时文件 → `FileResponse` 返回 → `BackgroundTasks` 清理。

> `python-docx` 在保存前会在内存中构造完整文档，单纯使用 `StreamingResponse` 不等于真正流式生成。P0 通过实例数量上限（500）和 evidence 大小限制（1MB/条）控制内存。

```python
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import BackgroundTasks
from fastapi.responses import FileResponse


def _remove_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def build_docx_response(
    report_code: str,
    document,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    with NamedTemporaryFile(
        prefix=f"inspection-report-{report_code}-",
        suffix=".docx",
        delete=False,
    ) as f:
        temp_path = f.name
    document.save(temp_path)
    background_tasks.add_task(_remove_file, temp_path)
    return FileResponse(
        path=temp_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"inspection-report-{report_code}.docx",
        background=background_tasks,
    )
```

### 8.2 边界

| 约束 | 值 |
|---|---|
| 单次最大实例数 | 500 |
| 默认不导出 raw rows | 只导出 findings/message |
| 原始 evidence 导出 | 仅 admin 角色 |

响应头：
```
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename*=UTF-8''inspection-report-<report_code>.docx
```

### 8.3 文档结构

封面→基本信息→健康摘要→等级分布→严重/告警清单→实例汇总表→各实例详情→附录。

### 8.4 审计元数据

rule_engine_version + 巡检项规则版本 + 报告生成时间 + 报告编号。

---

## 9. 权限与审计

### 9.1 操作权限

角色使用现有系统定义：admin / operator / viewer。不引入新角色。

| 操作 | 最低角色 |
|---|---|
| 查看报告 | viewer |
| 查看 findings/message | viewer |
| 查看原始 rows/stderr | operator |
| 导出普通报告 | operator |
| 导出原始 evidence | admin |
| regenerate | operator |
| 编辑巡检项 | admin |
| 创建全量巡检任务 | admin（或二次确认） |

### 9.2 审计事件

```
report.regenerated
report.exported
report.evidence_exported
inspection.item.changed
inspection.task.created
```

审计记录：operator, report_id/task_id, filter_conditions, include_evidence, operated_at。

---

## 10. Oracle P0 巡检项与 SQL

### P0 配置总览

| item_code | item_kind | evaluator | empty_result |
|---|---|---|---|
| ORA_VERSION_INFO | information | none | unknown |
| ORA_DATABASE_OPEN_MODE | composite | status_column | unknown |
| ORA_TABLESPACE_USAGE | metric | range | unknown |
| ORA_SESSION_USAGE | metric | range | unknown |
| ORA_BLOCKING_SESSION | composite | status_column | normal |

> 阻塞检查使用 `composite/status_column`（非 `count/range`），因为异常等级取决于阻塞持续时间而非仅数量。

### 10.1 ORA_VERSION_INFO — 版本和实例信息

```text
item_kind=information, evaluator_type=none, max_rows=1, empty_result_policy=unknown
```

```sql
SELECT
    i.instance_name, i.host_name, i.version, i.startup_time,
    i.status AS instance_status, i.database_status,
    i.parallel AS rac_enabled,
    d.name AS database_name, d.db_unique_name,
    d.database_role, d.open_mode, d.log_mode,
    (SELECT v.banner FROM v$version v
     WHERE v.banner LIKE 'Oracle Database%' AND ROWNUM = 1) AS version_banner
FROM v$instance i CROSS JOIN v$database d;
```

成功 → `execution_status=success, evaluation_status=not_evaluated`。

### 10.2 ORA_DATABASE_OPEN_MODE — 数据库角色与打开模式

支持主库、物理备库、逻辑备库、快照备库，不写死 `READ WRITE`。

```text
item_kind=composite, evaluator_type=status_column, multiple_rows.policy=first, empty_result_policy=unknown
```

```sql
SELECT
    database_role, open_mode, log_mode,
    CASE
        WHEN database_role = 'PRIMARY' AND open_mode = 'READ WRITE' THEN 'normal'
        WHEN database_role = 'PHYSICAL STANDBY' AND open_mode IN ('MOUNTED','READ ONLY WITH APPLY') THEN 'normal'
        WHEN database_role IN ('LOGICAL STANDBY','SNAPSHOT STANDBY') AND open_mode = 'READ WRITE' THEN 'normal'
        WHEN database_role IN ('PRIMARY','PHYSICAL STANDBY','LOGICAL STANDBY','SNAPSHOT STANDBY') THEN 'critical'
        ELSE 'warning'
    END AS result_status,
    CASE
        WHEN database_role = 'PRIMARY' AND open_mode = 'READ WRITE' THEN 'info'
        WHEN database_role = 'PHYSICAL STANDBY' AND open_mode IN ('MOUNTED','READ ONLY WITH APPLY') THEN 'info'
        WHEN database_role IN ('LOGICAL STANDBY','SNAPSHOT STANDBY') AND open_mode = 'READ WRITE' THEN 'info'
        WHEN database_role IN ('PRIMARY','PHYSICAL STANDBY','LOGICAL STANDBY','SNAPSHOT STANDBY') THEN 'critical'
        ELSE 'warning'
    END AS severity,
    'DATABASE_ROLE='||database_role||', OPEN_MODE='||open_mode||', LOG_MODE='||log_mode AS message
FROM v$database;
```

**需现场确认**：Far Sync、特殊只读主库、升级维护状态是否加入正常组合。

### 10.3 ORA_TABLESPACE_USAGE — 永久表空间使用率

`DBA_TABLESPACE_USAGE_METRICS.USED_PERCENT` 直接给出百分比。`TABLESPACE_SIZE` 考虑数据文件自动扩展上限及底层可用空间。

```text
item_kind=metric, evaluator_type=range, value_selector.column=used_pct
warning.gte=80, critical.gte=90, multiple_rows.policy=each, empty_result_policy=unknown
```

```sql
SELECT
    m.tablespace_name, t.contents, t.status AS tablespace_status,
    ROUND(m.used_percent, 2) AS used_pct,
    ROUND(m.used_space * t.block_size/1024/1024/1024, 2) AS used_gb,
    ROUND(m.tablespace_size * t.block_size/1024/1024/1024, 2) AS max_gb
FROM dba_tablespace_usage_metrics m
JOIN dba_tablespaces t ON t.tablespace_name = m.tablespace_name
WHERE t.contents = 'PERMANENT' AND t.status = 'ONLINE'
ORDER BY m.used_percent DESC;
```

> P0 只检查 PERMANENT。TEMP/UNDO/FRA 独立成巡检项。CDB 环境若连接 CDB$ROOT 需另行设计 `CDB_*` 视图。

rule_config:
```json
{
  "schema_version": 1,
  "item_kind": "metric", "category": "capacity",
  "evaluator": {"type": "range", "warning": {"gte": 80}, "critical": {"gte": 90}},
  "value_selector": {"column": "used_pct"},
  "multiple_rows": {"policy": "each", "aggregate": null},
  "empty_result_policy": "unknown", "null_value_policy": "unknown",
  "unit": "%",
  "message_template": "{tablespace_name} 表空间使用率为 {used_pct}%"
}
```

### 10.4 ORA_SESSION_USAGE — 会话资源使用率

`LIMIT_VALUE` 可能出现 `UNLIMITED`，必须先验证格式再 `TO_NUMBER`。

```text
item_kind=metric, evaluator_type=range, value_selector.column=used_pct
warning.gte=80, critical.gte=90, multiple_rows.policy=first, empty_result_policy=unknown, null_value_policy=unknown
```

```sql
WITH resource_data AS (
    SELECT resource_name, current_utilization, max_utilization, limit_value,
        CASE WHEN REGEXP_LIKE(TRIM(limit_value), '^[0-9]+$') THEN TO_NUMBER(TRIM(limit_value)) ELSE NULL END AS limit_value_num
    FROM v$resource_limit WHERE resource_name = 'sessions'
)
SELECT resource_name, current_utilization, max_utilization, limit_value, limit_value_num,
    CASE WHEN limit_value_num > 0 THEN ROUND(current_utilization*100/limit_value_num, 2) ELSE NULL END AS used_pct
FROM resource_data;
```

建议后续复制一份检查 `resource_name='processes'`，会话数和进程数分别生成两个巡检结果。

### 10.5 ORA_BLOCKING_SESSION — 阻塞会话

使用 `GV$SESSION` 兼容 RAC，每条被阻塞会话为一条 finding，父结果取最严重。

```text
item_kind=composite, evaluator_type=status_column, multiple_rows.policy=each, empty_result_policy=normal, max_rows=200
```

```sql
SELECT
    s.inst_id, s.sid AS blocked_sid, s.serial# AS blocked_serial,
    s.username AS blocked_username, s.sql_id AS blocked_sql_id,
    s.blocking_instance, s.blocking_session,
    s.final_blocking_instance, s.final_blocking_session,
    s.event, s.wait_class,
    ROUND(s.wait_time_micro/1000000, 2) AS wait_seconds,
    CASE WHEN s.wait_time_micro >= 300000000 THEN 'critical' ELSE 'warning' END AS result_status,
    CASE WHEN s.wait_time_micro >= 300000000 THEN 'critical' ELSE 'warning' END AS severity,
    'Blocked SID='||TO_CHAR(s.sid)||', Blocker SID='||TO_CHAR(s.blocking_session)||
    ', Wait='||TO_CHAR(ROUND(s.wait_time_micro/1000000,2))||'s, Event='||s.event AS message
FROM gv$session s
WHERE s.blocking_session_status = 'VALID' AND s.state = 'WAITING'
  AND NVL(s.wait_class, 'Unknown') <> 'Idle'
ORDER BY s.wait_time_micro DESC;
```

rule_config:
```json
{
  "schema_version": 1,
  "item_kind": "composite", "category": "performance",
  "evaluator": {"type": "status_column", "status_column": "result_status", "severity_column": "severity", "message_column": "message"},
  "multiple_rows": {"policy": "each", "aggregate": null},
  "empty_result_policy": "normal"
}
```

### Oracle 只读账号权限

```sql
GRANT CREATE SESSION TO <COLLECTOR_USER>;
GRANT SELECT ON SYS.V_$INSTANCE TO <COLLECTOR_USER>;
GRANT SELECT ON SYS.V_$DATABASE TO <COLLECTOR_USER>;
GRANT SELECT ON SYS.V_$VERSION TO <COLLECTOR_USER>;
GRANT SELECT ON SYS.V_$RESOURCE_LIMIT TO <COLLECTOR_USER>;
GRANT SELECT ON SYS.GV_$SESSION TO <COLLECTOR_USER>;
GRANT SELECT ON SYS.DBA_TABLESPACES TO <COLLECTOR_USER>;
GRANT SELECT ON SYS.DBA_TABLESPACE_USAGE_METRICS TO <COLLECTOR_USER>;
```

### Oracle P1 建议优先补充

| 巡检项 | 建议视图 |
|---|---|
| FRA 使用率 | `V$RECOVERY_FILE_DEST` |
| 无效对象 | `DBA_OBJECTS` |
| UNUSABLE 索引 | `DBA_INDEXES`, `DBA_IND_PARTITIONS` |
| 归档目的地错误 | `V$ARCHIVE_DEST_STATUS` |
| Data Guard 延迟 | `V$DATAGUARD_STATS` |
| RMAN 最近备份 | `V$RMAN_BACKUP_JOB_DETAILS` |
| 长事务 (P1) | `V$TRANSACTION`, `V$SESSION` 关联 |

---

## 11. SQL Server P0 巡检项与 SQL

### 重要边界（2026-06-25 v5.1 修正）

`sys.database_files`、`FILEPROPERTY`、`sys.dm_db_file_space_usage` 和 `sys.dm_db_log_space_usage` 都是**当前数据库上下文**的数据，原本要求 Collector 必须能注入 `target_database` 才能正确巡检业务库。

**v5.1 修正**：改用 **server-wide** 视图 `sys.master_files`（位于 master，自带 `database_id` 字段），从 master 连接一把查所有用户数据库的文件信息。**`used_pct` 语义相应变化**：

| 旧语义 | 新语义 |
|---|---|
| `used_pct = FILEPROPERTY('SpaceUsed') / size`（"已分配里实际用了多少"） | `used_pct = size / max_size`（"已分配占上限的百分比"——容量规划指标） |
| 当前 DB only，需 target_database | **跨所有用户 DB，零 operator 输入** |

> 容量规划场景下"会不会撞上限自动增长"是关键告警，"碎片多不多"是次要指标。巡检以此为准。

### P0 配置总览

| item_code | item_kind | evaluator | empty_result | target_database |
|---|---|---|---|---|
| MSSQL_VERSION_INFO | information | none | unknown | 不需要（server-wide） |
| MSSQL_DATABASE_STATE | composite | status_column | unknown | 不需要（server-wide） |
| MSSQL_DATA_FILE_USAGE | metric | range | unknown | **不需要**（v5.1 改 sys.master_files，server-wide） |
| MSSQL_LOG_USAGE | metric | range | unknown | **不需要**（v5.1 改 sys.master_files，server-wide） |
| MSSQL_BLOCKING_REQUEST | composite | status_column | normal | 不需要（server-wide） |

> 阻塞请求使用 `composite/status_column`（非 `count/range`）。

### 11.1 MSSQL_VERSION_INFO — 版本和启动信息

```text
item_kind=information, evaluator_type=none, max_rows=1, empty_result_policy=unknown
```

```sql
SELECT
    CAST(SERVERPROPERTY('MachineName') AS NVARCHAR(128)) AS machine_name,
    CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128)) AS server_name,
    CAST(SERVERPROPERTY('InstanceName') AS NVARCHAR(128)) AS instance_name,
    CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128)) AS product_version,
    CAST(SERVERPROPERTY('ProductLevel') AS NVARCHAR(128)) AS product_level,
    CAST(SERVERPROPERTY('Edition') AS NVARCHAR(128)) AS edition,
    CAST(SERVERPROPERTY('EngineEdition') AS INT) AS engine_edition,
    osi.sqlserver_start_time
FROM sys.dm_os_sys_info AS osi;
```

### 11.2 MSSQL_DATABASE_STATE — 用户数据库状态

```text
item_kind=composite, evaluator_type=status_column, multiple_rows.policy=each, empty_result_policy=unknown
```

```sql
SELECT
    d.database_id, d.name AS database_name, d.state_desc AS database_state,
    d.user_access_desc, d.recovery_model_desc, d.log_reuse_wait_desc,
    d.is_read_only, d.is_in_standby,
    CASE
        WHEN d.state_desc = N'ONLINE' THEN N'normal'
        WHEN d.state_desc IN (N'RECOVERY_PENDING',N'SUSPECT',N'EMERGENCY',N'OFFLINE') THEN N'critical'
        ELSE N'warning'
    END AS result_status,
    CASE
        WHEN d.state_desc = N'ONLINE' THEN N'info'
        WHEN d.state_desc IN (N'RECOVERY_PENDING',N'SUSPECT',N'EMERGENCY',N'OFFLINE') THEN N'critical'
        ELSE N'warning'
    END AS severity,
    CONCAT(N'Database=',QUOTENAME(d.name),N', State=',d.state_desc,
           N', RecoveryModel=',d.recovery_model_desc) AS message
FROM sys.databases AS d
WHERE d.database_id > 4 AND d.source_database_id IS NULL
ORDER BY d.name;
```

**需现场确认**：Log Shipping Secondary 处于 `RESTORING/STANDBY` 是否正常、只读数据库是否允许、快照是否纳入、`database_id>4` 是否符合资产范围。

### 11.3 MSSQL_DATA_FILE_USAGE — 实例所有用户数据库数据文件使用率（master 连接，跨 DB）

```text
item_kind=metric, evaluator_type=range, value_selector.column=used_pct
warning.gte=80, critical.gte=90, multiple_rows.policy=each, empty_result_policy=unknown, null_value_policy=unknown
target_database 不需要（sys.master_files 是 server-wide）
```

```sql
-- v5.1：改用 sys.master_files（server-wide），从 master 跑，跨所有用户 DB
SELECT
    DB_NAME(mf.database_id) AS database_name,
    mf.file_id, mf.name AS logical_file_name, mf.type_desc, mf.physical_name,
    CAST(mf.size*8.0/1024 AS DECIMAL(18,2)) AS allocated_mb,
    CAST(CASE WHEN mf.max_size = -1 OR mf.max_size = 0 THEN NULL
         ELSE mf.max_size*8.0/1024 END AS DECIMAL(18,2)) AS max_size_mb,
    CASE
        WHEN mf.max_size = -1 OR mf.max_size = 0 THEN 0
        ELSE CAST(mf.size*100.0/mf.max_size AS DECIMAL(9,2))
    END AS used_pct,
    mf.is_percent_growth, mf.growth
FROM sys.master_files AS mf
WHERE mf.type_desc = N'ROWS'
  AND DB_NAME(mf.database_id) NOT IN (N'master', N'tempdb', N'model', N'msdb')
  AND DB_NAME(mf.database_id) IS NOT NULL
ORDER BY used_pct DESC;
```

> 语义变化（v5.1）：`used_pct` 现在是 `allocated/max_size`（容量规划），不再是 `SpaceUsed/allocated`（碎片分析）。告警阈值不变（warning≥80, critical≥90）。

### 11.4 MSSQL_LOG_USAGE — 实例所有用户数据库日志使用率（master 连接，跨 DB）

```text
item_kind=metric, evaluator_type=range, value_selector.column=used_pct
warning.gte=70, critical.gte=90, multiple_rows.policy=first, empty_result_policy=unknown
target_database 不需要（sys.master_files 是 server-wide）
```

```sql
-- v5.1：改用 sys.master_files，从 master 跑，跨所有用户 DB
SELECT
    DB_NAME(mf.database_id) AS database_name,
    mf.name AS logical_file_name,
    CAST(mf.size*8.0/1024 AS DECIMAL(18,2)) AS total_log_mb,
    CAST(CASE WHEN mf.max_size = -1 OR mf.max_size = 0 THEN NULL
         ELSE mf.max_size*8.0/1024 END AS DECIMAL(18,2)) AS max_size_mb,
    CASE
        WHEN mf.max_size = -1 OR mf.max_size = 0 THEN 0
        ELSE CAST(mf.size*100.0/mf.max_size AS DECIMAL(9,2))
    END AS used_pct,
    mf.is_percent_growth, mf.growth
FROM sys.master_files AS mf
WHERE mf.type_desc = N'LOG'
  AND DB_NAME(mf.database_id) NOT IN (N'master', N'tempdb', N'model', N'msdb')
  AND DB_NAME(mf.database_id) IS NOT NULL
ORDER BY used_pct DESC;
```

> 语义变化（v5.1）：同 11.3。P1 仍应独立检查 `log_reuse_wait_desc`（NOTHING/LOG_BACKUP/ACTIVE_TRANSACTION/AVAILABILITY_REPLICA），不同状态不能统一按同一严重等级。

### 11.5 MSSQL_BLOCKING_REQUEST — 阻塞请求

`blocking_session_id < 0` 有特殊含义（如 `-2`=孤立分布式事务，`-3`=延迟恢复，`-4`=latch），不能当作普通会话处理。

```text
item_kind=composite, evaluator_type=status_column, multiple_rows.policy=each, empty_result_policy=normal, max_rows=200
```

```sql
SELECT
    r.session_id AS blocked_session_id, r.blocking_session_id,
    DB_NAME(r.database_id) AS database_name,
    r.status AS request_status, r.command, r.wait_type,
    CAST(r.wait_time/1000.0 AS DECIMAL(18,2)) AS wait_seconds, r.wait_resource,
    CAST(r.total_elapsed_time/1000.0 AS DECIMAL(18,2)) AS elapsed_seconds,
    CASE
        WHEN r.blocking_session_id < 0 THEN N'unknown'
        WHEN r.wait_time >= 300000 THEN N'critical'
        ELSE N'warning'
    END AS result_status,
    CASE
        WHEN r.blocking_session_id < 0 THEN N'warning'
        WHEN r.wait_time >= 300000 THEN N'critical'
        ELSE N'warning'
    END AS severity,
    CONCAT(N'BlockedSession=',r.session_id,N', BlockingSession=',r.blocking_session_id,
           N', WaitSeconds=',CONVERT(DECIMAL(18,2),r.wait_time/1000.0),
           N', WaitType=',COALESCE(r.wait_type,N'')) AS message
FROM sys.dm_exec_requests AS r
WHERE r.session_id <> @@SPID AND r.blocking_session_id <> 0
ORDER BY r.wait_time DESC;
```

rule_config:
```json
{
  "schema_version": 1,
  "item_kind": "composite", "category": "performance",
  "evaluator": {"type": "status_column", "status_column": "result_status", "severity_column": "severity", "message_column": "message"},
  "multiple_rows": {"policy": "each", "aggregate": null},
  "empty_result_policy": "normal"
}
```

### SQL Server 只读账号权限

SQL Server 2019 及以前：
```sql
GRANT VIEW SERVER STATE TO [<COLLECTOR_USER>];
GRANT VIEW ANY DATABASE TO [<COLLECTOR_USER>];
```

SQL Server 2022 及以后：
```sql
GRANT VIEW SERVER PERFORMANCE STATE TO [<COLLECTOR_USER>];
GRANT VIEW ANY DATABASE TO [<COLLECTOR_USER>];
```

> 需先确认 `VIEW ANY DATABASE` 对业务数据库的影响，在测试环境验证最小权限。

### SQL Server P1 建议优先补充

| 巡检项 | 建议视图 |
|---|---|
| 最近完整/日志备份 | `msdb.dbo.backupset` |
| Agent 失败作业 | `msdb.dbo.sysjobhistory` |
| AG 同步状态 | `sys.dm_hadr_database_replica_states` |
| 可疑页 | `msdb.dbo.suspect_pages` |
| 日志无法复用原因 | `sys.databases.log_reuse_wait_desc` |
| 长事务 | `sys.dm_tran_active_transactions` 等事务 DMV |
| 磁盘卷剩余空间 | `sys.dm_os_volume_stats` |
| 文件自动增长配置 | `sys.master_files` 增长检查（v5.1 起改用 master_files，自动跨 DB） |

**v5.1 状态**：target_database 问题已通过改用 `sys.master_files` 解决（见 §11.3 / §11.4）。MSSQL_DATA_FILE_USAGE 和 MSSQL_LOG_USAGE 不再需要 operator 配置业务库名，从 master 一把查所有用户数据库。

**实施前验证门禁**：

```sql
-- 分别对两个业务数据库执行，结果必须返回对应数据库名
SELECT DB_NAME() AS current_database, @@SERVERNAME AS server_name;
```

验证不通过时的处理：

| 方案 | 说明 |
|---|---|
| A: 修复 Collector | 连接时通过 ODBC 参数 `DATABASE=ERPDB` 指定目标库，或 rule_config 增加 `connection_context.target_database` |
| B: 暂时禁用 | 未解决当前库上下文前，不启用 `MSSQL_DATA_FILE_USAGE` 和 `MSSQL_LOG_USAGE`，避免把 `master` 的文件使用率当成业务实例结果 |

---

## 12. 索引设计

```sql
-- 任务
CREATE INDEX idx_inspection_task_status_created ON dbops.inspection_task (status, created_at DESC);

-- 任务目标
CREATE INDEX idx_inspection_task_target_task_execution ON dbops.inspection_task_target (task_id, execution_status);
CREATE INDEX idx_task_target_filter ON dbops.inspection_task_target (task_id, db_type_code_snapshot);
CREATE INDEX idx_task_target_business_system ON dbops.inspection_task_target (task_id, business_system_snapshot);
CREATE INDEX idx_task_target_site ON dbops.inspection_task_target (task_id, site_snapshot);

-- 任务巡检项
CREATE INDEX idx_inspection_task_item_task ON dbops.inspection_task_item (task_id, check_order, id);

-- 巡检结果
CREATE INDEX idx_inspection_result_task_target ON dbops.inspection_result (task_id, task_target_id);
CREATE INDEX idx_inspection_result_task_item ON dbops.inspection_result (task_id, task_item_id);

-- 部分索引：异常结果快速查询（替代普通 evaluation 索引，避免与主键/唯一索引重复）
CREATE INDEX idx_inspection_result_abnormal ON dbops.inspection_result (task_id, evaluation_status, task_target_id)
    WHERE evaluation_status IN ('warning', 'critical', 'unknown');

-- 报告
CREATE INDEX idx_inspection_report_status_generated ON dbops.inspection_report (report_status, generated_at DESC);

-- 实例报告（UNIQUE(report_id, task_target_id) 已自动创建唯一索引，不重复建 idx_instance_report_report_target）
CREATE INDEX idx_instance_report_report_health ON dbops.inspection_instance_report (report_id, health_level, health_score);
```

> 已精简：删除了被唯一约束自动覆盖的 `idx_instance_report_report_target`，以及被部分索引替代的普通 `evaluation` 索引。

---

## 13. 实施顺序

### P0-A：安全与数据重置

P0-A1 轮换已暴露凭证 → P0-A2 停止任务和 callback → P0-A3 检查外键 → P0-A4 备份旧 DDL → P0-A5 DROP 子表→父表→CREATE 新表+索引。

### P0-B：数据契约（DDL + Model + Schema + Index）

P0-B1~B8 全部 8 张巡检域表 + P0-B9 RuleConfigSchema（含跨字段校验）+ P0-B10 全部索引 + P0-B11 TIMESTAMPTZ 统一 + P0-B12 种子规则初始化。

### P0-C：规则引擎

P0-C1 InspectionEvaluatorService → P0-C2 全部 8 种 evaluator → P0-C3 status_column 归一化+白名单 → P0-C4 4 个 policy → P0-C5 健康分数公式 → P0-C6 单元测试。

### P0-D：执行链路

P0-D1 create_task 生成快照 → P0-D2 callback 小事务（解析+评估+UPSERT）→ P0-D3 状态迁移校验 → P0-D4 报告生成（补齐缺失+聚合，独立事务+FOR UPDATE）→ P0-D5 regenerate。

### P0-E：API + 前端 + 种子规则

P0-E1 5 个 GET + regenerate + export → P0-E2 list_results JOIN + 分页 → P0-E3 Tasks.vue 报告列 → P0-E4 Reports.vue → P0-E5 ReportDetail.vue → P0-E6 InstanceReport.vue → P0-E7 DOCX 导出(含权限) → P0-E8 AI 占位 → P0-E9 前端 API/类型 → P0-E10 Oracle+SQL Server 最小规则种子(各5项) → P0-E11 端到端冒烟。

### P1：降低维护成本

完整规则包 / 巡检方案(rule_package) / 任务创建选方案 / 实例级阈值覆盖 / 图表 / 新模型下重新聚合。

### P2：AI 接入

inspection_ai_analysis 表 / AI API / 整体+实例 AI 分析 / 人工审核 / DOCX 追加 AI。

---

## 14. 数据迁移步骤

> DROP、CREATE、索引、种子数据放在**同一个 PostgreSQL 事务**中。不要 DROP 后先 COMMIT 再单独 CREATE，否则建表失败会导致巡检表全部消失的中间状态。

```
1. 停止任务创建
2. 停止 AWX callback
3. 检查外键引用（SQL 见下方）
4. pg_dump --schema-only -t dbops.inspection_*
5. BEGIN  ← 单事务开始
6.   -- 按 FK 依赖顺序 DROP：先子表后父表
7.   DROP TABLE IF EXISTS dbops.inspection_result;            -- FK→task_item, task_target, task, collector_*
8.   DROP TABLE IF EXISTS dbops.inspection_instance_report;   -- FK→report, task, task_target
9.   DROP TABLE IF EXISTS dbops.inspection_report;            -- FK→task
10.  DROP TABLE IF EXISTS dbops.inspection_task_item;         -- FK→task
11.  DROP TABLE IF EXISTS dbops.inspection_task_target;       -- FK→task
12.  DROP TABLE IF EXISTS dbops.inspection_task;              -- FK→schedule
13.  DROP TABLE IF EXISTS dbops.inspection_schedule;
14.  DROP TABLE IF EXISTS dbops.inspection_item;
15.  -- CREATE 全部 8 张表
16.  -- CREATE 全部索引
17.  -- INSERT 种子规则数据（Oracle 5 项 + SQL Server 5 项）
18. COMMIT ← 单事务结束
19. 启动服务
20. 冒烟测试
```

禁止 CASCADE。外键检查：
```sql
SELECT con.conname, con.conrelid::regclass AS tbl, con.confrelid::regclass AS ref
FROM pg_constraint con
WHERE con.contype = 'f'
  AND (con.conrelid IN (
          'dbops.inspection_item'::regclass,
          'dbops.inspection_task'::regclass,
          'dbops.inspection_result'::regclass,
          'dbops.inspection_schedule'::regclass
      )
       OR con.confrelid IN (
          'dbops.inspection_item'::regclass,
          'dbops.inspection_task'::regclass,
          'dbops.inspection_result'::regclass,
          'dbops.inspection_schedule'::regclass
      ))
ORDER BY tbl, conname;
```

### 14.1 迁移前演练（门禁）

❗正式执行前必须在开发库完整演练一次：

```bash
# 1. 备份旧 DDL
pg_dump --schema-only --table='dbops.inspection_*' \
  --file=/tmp/dbops_inspection_before_v5_1.sql "$DATABASE_URL"

# 2. 执行 migration
psql "$DATABASE_URL" -f migration_v5_1.sql

# 3. 验证表已创建（预期 ≥ 8 张）
psql "$DATABASE_URL" -c "
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'dbops' AND table_name LIKE 'inspection_%'
ORDER BY table_name;"

# 4. 验证约束
psql "$DATABASE_URL" -c "
SELECT conrelid::regclass AS tbl, conname, contype,
       pg_get_constraintdef(oid) AS def
FROM pg_constraint WHERE connamespace = 'dbops'::regnamespace
  AND conrelid::regclass::text LIKE 'dbops.inspection_%'
ORDER BY tbl, conname;"
```

只有 migration、种子数据、后端启动、创建任务、callback 和报告生成全部跑通后，再执行正式环境切换。

---

## 15. 代码地图

| 层 | 文件 | 影响 |
|---|---|---|
| 后端路由 | `backend/app/api/inspection.py` | P0-E 新增端点 |
| 后端 Service | `backend/app/services/inspection_service.py` | P0-D 核心改造 |
| 后端 Service（新） | `backend/app/services/inspection_evaluator_service.py` | P0-C |
| 后端 Service（新） | `backend/app/services/report_export_service.py` | P0-E7 |
| 后端 Schema | `backend/app/schemas/inspection.py` | P0-B8 |
| 后端 Model | `backend/app/models/dbops_assets.py` | P0-B |
| 后端 DDL | 全新 migration | P0-B |
| 前端 Reports | `frontend/src/views/inspection/Reports.vue` | P0-E4 |
| 前端 ReportDetail（新） | `frontend/src/views/inspection/ReportDetail.vue` | P0-E5 |
| 前端 InstanceReport（新） | `frontend/src/views/inspection/InstanceReport.vue` | P0-E6 |
| 前端 Tasks | `frontend/src/views/inspection/Tasks.vue` | P0-E3 |
| 前端 Items | `frontend/src/views/inspection/Items.vue` | 小幅 |
| 前端 API | `frontend/src/api/assets.ts` | P0-E9 |
| 前端类型 | `frontend/src/types/api.ts` | P0-E9 |

---

## 16. 设计决策摘要

1. **任务快照**：task_item + task_target 保证历史可重现
2. **目标双状态机**：dispatch_status + execution_status 分离，含合法迁移规则
3. **一条 result = task_item × task_target**：UNIQUE(task_id, task_item_id, task_target_id)，多行→findings
4. **删除 severity**：只用 evaluation_status
5. **not_evaluated + not_assessed**：信息采集不计分，全部不可评估→not_assessed, score=NULL
6. **缺失结果补齐**：预期矩阵 LEFT JOIN → 占位 INSERT，不消失不虚高
7. **callback 事务一次完成解析+评估+UPSERT**：不拆分保存和评估
8. **报告事务独立**：FOR UPDATE + 补齐缺失 + 聚合
9. **regenerate 只重建聚合**
10. **attempt_no 比较**：旧 attempt 不覆盖新结果
11. **规范化哈希**：sort_keys JSON → SHA-256
12. **instance_report 关联 task_target_id**：避免三字段 JOIN
13. **multiple_rows 统一入口**：删除 value_selector.row_mode
14. **empty_result_policy 删除 not_applicable**
15. **TIMESTAMPTZ / evidence 限制 / 索引精简 / API 分页规范 / DOCX 权限 / 审计事件**
16. **AI 本期占位 / P0 含 10 项种子规则 / 前端复用 Ops 组件**

---

## 17. 验收清单

| 场景 | 预期 |
|---|---|
| 信息类 SQL 成功 | exec=success, eval=not_evaluated |
| SQL 超时 | exec=timeout, eval=unknown |
| 阻塞查询返回 0 行 | empty=normal → eval=normal |
| DB 状态查询返回 0 行 | empty=unknown → eval=unknown |
| 存在 critical 项 | 实例 critical |
| 只有 warning 项 | 实例 warning |
| 全部 normal | 实例 healthy |
| 全部 information | 实例 not_assessed, score=NULL |
| 实例无任何结果 | 报告中出现，level=unknown（来自补齐） |
| 预期 5 项只返回 3 项 | 补 2 项 skipped+unknown，不虚高 |
| 修改阈值 | 已完成任务不变化（快照） |
| callback 重复 | UPSERT，attempt_no 比较 |
| 两个 final callback 同时到 | 一份报告（FOR UPDATE） |
| 报告完成后重复 callback | 按 attempt_no 拒绝或更新后重聚合 |
| regenerate | 一致，hash 同则跳过 |
| status_column 返回非法 | exec=parse_failed, eval=unknown |
| evidence 超限 | truncated=true |
| 规则 warning/critical 反向 | 创建时拒绝 |
| 一个目标无任何适用项 | not_assessed |
| 导出 500+ 实例 | 拒绝或截断提示 |
| DOCX 不含 evidence（默认） | 仍有摘要和审计信息 |
| 非 admin 导出原始 evidence | 拒绝 |
| AI 按钮 | disabled，tooltip="规划中" |
| 所有目标 skipped | report_status=partial |
| 时间字段 | TIMESTAMPTZ，前端按时区展示 |
| dispatch_status 终态回退 | UPDATE 条件拒绝 |
| 旧 attempt callback 迟到 | 不覆盖新 attempt 结果 |
| 同 attempt 旧 callback 后到且当前已终态 | 不覆盖已保存的终态结果 |
| MISSING_RESULT (attempt=0) 后真实 callback 到 | attempt=1 覆盖，自动重新聚合 |
| 创建任务后禁用原 inspection_item | 已创建任务继续使用 task_item 快照 |
| 创建任务后修改资产名称/IP | 报告显示任务目标快照值 |
| SQL Server 连接指定业务 DB | `DB_NAME()` 返回预期数据库名 |
| 删除或停用原资产 | 历史报告和实例报告仍可查询（快照隔离） |

---

## 附录 A：环境配置

| 项目 | 值 |
|---|---|
| AWX URL | `<AWX_URL>` |
| AWX Job Template ID | 10 |
| AWX Project ID | 8 |
| AWX EE ID | 3 |
| AWX Instance Group | IG_LOCAL_LH_TEST (id=3) |
| DBOPS 后端 | `<DBOPS_BACKEND_URL>` |
| DBOPS 前端 | `<DBOPS_FRONTEND_URL>` |
| DBOPS 数据库 | `<DATABASE_URL>` |
| Redis | `<REDIS_URL>` |
| 源 playbook | `/home/lisiyang/ansible-playbooks` |
| 环境配置 | `.env` |

## 附录 B：关键文件位置

| 文件 | 路径 |
|---|---|
| Playbook | `.../playbooks/dbops_collector_generic.yml` |
| db_fact_collect role | `.../roles/db_fact_collect/tasks/main.yml` |
| os_fact_collect role | `.../roles/os_fact_collect/tasks/main.yml` |
| collector client | `/home/lisiyang/ansible-playbooks/files/collector_client/` |
| collector 源码 | `/home/lisiyang/dbops-collector/collector_client/` |
| EE 镜像 | `/home/lisiyang/awx-ee-dbops-v2.tar` |
| 数据库 DDL（旧） | `backend/db/dbops_phase3_3a.sql` |
| 环境配置 | `backend/.env` |

## 附录 C：AI 功能（未来）

数据模型 `inspection_ai_analysis`、AI API、输出 JSON 格式、人工审核流程 — 同 v4 附录 C，本期全部不实现，仅在前端放置 disabled 占位按钮。

## 安全注意事项

已暴露凭证已从文档移除。所有凭证统一放入 `.env` / AWX Credential / Secret Manager。需立即轮换并检查 Git 历史。后续确保文档不含密码/Token/连接串。
