# Plan: Phase 3.5 — 批量冒烟测试 + 实例选择器增强

**Date**: 2026-06-25
**Branch**: feature/phase-3.5-db-readonly-sql-exec
**Source**: `/refactor` 验证计划完成度 + 修复 UX 缺陷

## Context

Phase 3.5 全部 9 个 commit 已完成推送，27/27 验收通过。但存在 3 个缺陷：

1. **Verify-SQL 实例选择器信息不足**：只显示 `instance_name (db_type / ip:port)`，缺少 cluster_type、node_role、db_version
2. **任务创建只能手动输入 ID**：asset_ids 是 `<input placeholder="1,2,3">`，无批量交互选择
3. **缺少 Oracle 冒烟巡检项**：只有 `SMOKE_DB_READONLY_001` (SQL Server)，3 个实例 (961 ORA + 963/964 MSSQL) 需全跑

## Part A: 批量冒烟测试

### A1. 创建 Oracle 巡检项
通过 API 创建 `SMOKE_DB_READONLY_002`：
- check_code: `DB_READONLY_SQL_EXEC`, db_type_code: `ORACLE`, severity: info, enabled: true
- sql_text: `SELECT name, open_mode, database_role, log_mode FROM v$database`
- timeout_seconds: 30, max_rows: 200

### A2. 发起批量巡检
对 961 (Oracle) + 963, 964 (SQL Server) 分别发起 task → 验证 callback → 检查 inspection_result

## Part B: Verify-SQL 实例选择器增强

### B1. 后端 — `dbops_asset_service.py`
`list_instances()` 返回值加 `cluster_type` 字段（当前缺失，但 InstanceRow 类型已定义）

### B2. 前端 — `Items.vue`
- Fix `loadInstances()` 参数：`{ limit: 500 }` → `{ page_size: 500 }`
- Fix `filteredInstances` 过滤逻辑：`i.db_type` (display name) 与 `verifyForm.db_type_code` (code) 不匹配
- 下拉选项增强：`{{ i.instance_name }} | {{ i.server_ip }}:{{ i.port }} | {{ i.cluster_type || '-' }} | {{ i.node_role }} | {{ i.db_version || '-' }}`
- 将单 select 改为 checkbox 列表，支持多选 + 全选/取消 + 已选计数

### B3. 后端 — verify-sql 支持批量
- `VerifySqlRequest.instance_id: int` → `instance_ids: list[int]`
- `verify_sql()` 为每个 instance 创建独立 collector_run，返回 `verify_run_ids: list[int]`

## Part C: 任务创建批量资产选择器

### C1. 新增 `OpsInstancePicker.vue` 组件
- 搜索 + DB 类型筛选 + checkbox 列表（instance_name / IP / cluster_type / node_role / db_version）
- 全选/取消全选
- 已选标签列表（可逐个移除）
- Props: `modelValue: number[]`, Emits: `update:modelValue`

### C2. 改造 `Tasks.vue`
- `<input placeholder="1,2,3">` → `<OpsInstancePicker v-model="selectedAssetIds">`
- 保留留空=全部行为

## 关键文件

| File | Action | Reason |
|---|---|---|
| `backend/app/services/dbops_asset_service.py` | UPDATE | `list_instances()` 加 `cluster_type` |
| `backend/app/schemas/inspection.py` | UPDATE | `VerifySqlRequest` 支持 `instance_ids` 批量 |
| `backend/app/services/inspection_service.py` | UPDATE | `verify_sql()` 支持多 instance |
| `frontend/src/views/inspection/Items.vue` | UPDATE | Fix bugs + 增强选择器 + 多选 |
| `frontend/src/views/inspection/Tasks.vue` | UPDATE | 替换文本输入为 `OpsInstancePicker` |
| `frontend/src/components/ops/OpsInstancePicker.vue` | **CREATE** | 新批量选择器组件 |
| `frontend/src/components/ops/index.ts` | UPDATE | 导出新组件 |

## 验证

1. 冒烟：3 实例 (961, 963, 964) 全部返回 evidence 落库
2. Verify-SQL：打开 modal 看到 IP/cluster_type/node_role/db_version → 可多选批量验证
3. Tasks.vue：checkbox 列表多选资产 → 创建任务调度成功
4. `verify.sh` 223 passed + `vue-tsc --noEmit` 0 errors
