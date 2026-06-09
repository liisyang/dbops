# 模块图

> 文档状态：已校准
> 最近校准：2026-05-21
> 依据来源：真实代码

## 1. 维护定位

本文件是模块事实源。

只维护：

1. 模块总览。
2. page / api / service / model / table 对应关系。
3. 主要调用链。
4. 缺失链路。
5. 需现场确认事项。

## 2. 模块总览

| 模块 | 当前状态 | 说明 | 代码依据 |
|---|---|---|---|
| Auth | 已实现 | JWT 登录，后端 `/api/auth/login`，前端 Login.vue | `backend/app/api/auth.py` + `frontend/src/views/Login.vue` |
| Dashboard | 已实现 | 仪表盘统计卡片和图表 | `frontend/src/views/Dashboard.vue` + stats API |
| 资产管理 - 服务器 | 已实现 | CRUD + 列表 + 详情 | `backend/app/api/servers.py:202-294` + `frontend/src/views/Servers.vue` |
| 资产管理 - 实例 | 已实现 | CRUD + 列表 + 详情 | `backend/app/api/servers.py:85-198` + `frontend/src/views/Instances.vue` |
| 资产管理 - AWX 资产校验 | 已实现（Phase 3.1 端口画像 + 端点治理 + 半自动校准） | 实例详情可发起端口校验与端口校准；校准 run 会按 `port_profile + endpoint + 资产字段` 自动展开候选端口，并按 `host+port+protocol` 去重；`include_related_server=true` 时会把关联服务器管理端口一起纳入候选，提案需人工 approve+apply 才更新正式端口字段 | `backend/app/api/collector.py` + `backend/app/services/collector_service.py` + `backend/app/services/port_calibration_service.py` + `frontend/src/views/InstanceDetail.vue` |
| 资产管理 - 集群 | 已实现 | CRUD + 列表 + 详情 + 实例关联 | `backend/app/api/servers.py:564-658` + `frontend/src/views/Clusters.vue` |
| 资产管理 - 业务系统 | 已实现 | CRUD + 详情 + 生命周期管理 + 联系人关联 | `backend/app/api/servers.py:348-477` + `frontend/src/views/Assets.vue` |
| 资产管理 - 联系人 | 已实现 | CRUD | `backend/app/api/servers.py:299-343` + `frontend/src/views/Contacts.vue` |
| 资产管理 - 导入 | 已实现 | Excel 预览 + 执行 + 批次记录 | `backend/app/api/servers.py:704-774` + `frontend/src/views/Import.vue` |
| 资产管理 - 统计 | 已实现 | 多维度分组统计 | `backend/app/api/servers.py:489-561` + `frontend/src/views/Stats.vue` |
| 自动化运维 - 主机清单 | 已实现 | Ansible 主机清单管理 | `backend/app/ansible/inventory.py` + `frontend/src/views/Inventory.vue` |
| 自动化运维 - 作业执行 | 部分实现 | 账号操作 API 已就绪，Celery worker 有意暂缓启用 | `backend/app/api/account_ops.py` + `frontend/src/views/ops/Tasks.vue` |
| 自动化运维 - 批量校验 | 已实现（Phase 3.2） | 批量资产校验 + 分网段 AWX 分发调度；支持 asset_ids/filters 选择、check_codes 多选、按 awx_instance_group 分组、dispatch_run 级分发、item 级结果、失败重跑 | `backend/app/api/collector.py` + `backend/app/services/batch_collector_service.py` + `backend/app/services/dispatch_planner_service.py` + `backend/app/services/check_item_builder_registry.py` + `frontend/src/views/ops/BatchVerify.vue` |
| 备份与恢复 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/backup/*.vue` |
| SQL 分析 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/sql/*.vue` |
| 巡检与健康 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/inspection/*.vue` |
| 审计与安全 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/audit/*.vue` |
| 凭证中心 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/credentials/*.vue` |
| 知识库 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/knowledge/Index.vue` |
| WebSocket | 已实现 | 任务实时输出推送 | `backend/app/api/websocket.py` |

## 3. page / api / service / model / table 对应关系

### 3.1 已实现链路

| 模块 | Page | Frontend API | Backend API | Service | Model | Table (dbops) | 状态 |
|---|---|---|---|---|---|---|---|
| 登录 | Login.vue | auth.ts → `/auth/login` | `api/auth.py` → `POST /api/auth/login` | - | User (dbops.users) | users | 已实现 |
| 仪表盘 | Dashboard.vue | stats.ts → `/v1/servers/stats/dashboard` | `api/servers.py:491-498` | DbopsStatsService | - | db_instance, server, cluster, business_system | 已实现 |
| 服务器 | Servers.vue | assets.ts → `/v1/servers/servers` | `api/servers.py:202-294` | DbopsAssetService | Server (dbops) | server | 已实现 |
| 实例 | Instances.vue + InstanceDetail.vue | assets.ts → `/v1/servers/instances` | `api/servers.py:85-198` | DbopsAssetService | DbInstance | db_instance | 已实现 |
| 集群 | Clusters.vue + ClusterDetail.vue | assets.ts → `/v1/servers/clusters` | `api/servers.py:564-658` | DbopsAssetService | Cluster (dbops) | cluster | 已实现 |
| 业务系统 | Assets.vue + BusinessSystemDetail.vue | assets.ts → `/v1/servers/business-services` | `api/servers.py:348-477` | DbopsAssetService | BusinessSystem | business_system | 已实现 |
| 联系人 | Contacts.vue | assets.ts → `/v1/servers/contacts` | `api/servers.py:299-343` | DbopsContactService | Contact (dbops) | contact | 已实现 |
| 导入 | Import.vue | assets.ts → `/v1/servers/imports/*` | `api/servers.py:704-774` | DbopsImportService | StagingExcelImport | staging_excel_import | 已实现 |
| AWX 资产校验 | InstanceDetail.vue | assets.ts → `/v1/collector/runs`（主入口）+ `/v1/automation/asset-verify/{id}/launch`（兼容包装）+ `/v1/collector/proposals*` | `api/collector.py` | CollectorService + PortProfileService + PortCalibrationService + AssetProposalService + AwxService（callback URL 优先配置值，未配置时回退请求基址） | CollectorRun / CollectorRunItem / CollectorRunResult / CollectorCheckDefinition / PortProfile / AssetEndpoint / AssetChangeProposal / DbInstance / Server | collector_run / collector_run_item / collector_run_result / collector_check_definition / port_profile / asset_endpoint / asset_change_proposal / db_instance / asset_event_history | 已实现（Phase 3.1：支持 run_type=port_calibration 与提案审批/应用） |
| 统计 | Stats.vue | stats.ts → `/v1/servers/stats/*` | `api/servers.py:489-561` | DbopsStatsService | - | (聚合查询) | 已实现 |
| 账号操作 | Tasks.vue | `/users/add\|check\|chpasswd` | `api/account_ops.py` | account_tasks (Celery) | TaskState (Redis) | (Redis) | 部分实现 |
| 主机清单 | Inventory.vue | 需现场确认 | 需现场确认 | Ansible inventory | - | (Ansible) | 部分实现 |

### 3.2 前端占位模块（后端 API 未确认）

| 模块 | Page | 前端路由路径 | 后端现状 |
|---|---|---|---|
| 备份策略 | backup/Policies.vue | /backup/policies | dbops schema 有 backup_policy 表定义，无 API |
| 备份作业 | backup/Jobs.vue | /backup/jobs | 无后端 |
| 恢复中心 | backup/Restore.vue | /backup/restore | 无后端 |
| SQL 审计 | sql/Audit.vue | /sql/audit | 无后端 |
| 慢查询 | sql/SlowQuery.vue | /sql/slow | 无后端 |
| TOP SQL | sql/TopSql.vue | /sql/top | 无后端 |
| 巡检报告 | inspection/Reports.vue | /inspection/reports | dbops schema 有 inspection 表定义，无 API |
| 健康检查 | inspection/Health.vue | /inspection/health | 无后端 |
| 操作日志 | audit/Operations.vue | /audit/operations | `/api/logs/list` 返回 [] |
| 登录日志 | audit/LoginLogs.vue | /audit/login | 无后端 |
| 敏感操作 | audit/Sensitive.vue | /audit/sensitive | 无后端 |
| SSH 凭证 | credentials/Ssh.vue | /credentials/ssh | ops schema 有 host_credentials 表，无 API |
| DB 凭证 | credentials/Db.vue | /credentials/db | ops schema 有 db_credentials 表，无 API |
| 知识库 | knowledge/Index.vue | /knowledge | 无后端 |
| UI 预览-服务器详情 | ui-preview/servers.vue | /ui-preview/servers.vue | Mock-only，仅用于开发预览，不调用真实 API |
| UI 预览-实例详情 | ui-preview/instances.vue | /ui-preview/instances.vue | Mock-only，仅用于开发预览，不调用真实 API |

## 4. 主要调用链

### 4.1 资产管理 CRUD（典型链路）

```text
Page (Servers.vue)
  → assetsApi.listServers()                   # frontend/src/api/assets.ts:27
  → GET /api/v1/servers/servers               # Axios baseURL=/api
  → servers.router (prefix=/api/v1/servers)   # backend/app/api/servers.py:26
  → DbopsAssetService.list_servers(db)        # backend/app/services/dbops_asset_service.py
  → Server (dbops.server)                      # backend/app/models/dbops_assets.py:213
  → PostgreSQL dbops.server
```

### 4.2 认证链路

```text
Page (Login.vue)
  → POST /api/auth/login                      # frontend/src/api/auth.ts
  → auth.router (prefix=/api/auth)            # backend/app/api/auth.py:10
  → User.query + verify_password()            # backend/app/models/user.py:31
  → create_access_token()                      # backend/app/api/deps.py:50
  → JWT → localStorage('token')
  → 后续请求 Axios 拦截器注入 Authorization: Bearer <token>
```

### 4.3 异步账号操作链路

```text
Page (Tasks.vue)
  → POST /api/users/add (WebSocket socket_id)
  → account_ops.router                        # backend/app/api/account_ops.py:16
  → add_user_task.delay(...)                  # Celery task 入队
  → Redis queue → Celery worker (当前未启用)
  → Paramiko/Ansible 远程执行
  → Redis pub/sub channel "task_output"
  → WebSocket → 前端实时更新
```

### 4.4 导入链路

```text
Page (Import.vue)
  → POST /api/v1/servers/imports/preview      # 预览
  → POST /api/v1/servers/imports/execute      # 执行
  → DbopsImportService.preview_import / execute_import
  → StagingExcelImport (临时表)               # backend/app/models/dbops_assets.py:418
  → BusinessSystem / Server / Cluster / DbInstance / Contact (正式表)
  → ImportBatch (批次追踪)
```

### 4.5 AWX 资产校验闭环链路（Phase 3.1）

```text
Page (InstanceDetail.vue)
  → POST /api/v1/collector/runs (run_type=asset_verify | port_calibration)
  → collector.router
  → CollectorService.launch_collector_run()
  → PortCalibrationService.build_port_calibration_items()  # run_type=port_calibration，候选按 host+port+protocol 去重
  → CollectorRun(pending) + CollectorRunItem[] + extra_vars.items
  → AwxService.launch_job()
  → CollectorRun(launched)
  → AWX Job 执行后回调 POST /api/v1/collector/callback/
  → CollectorService.handle_callback()
  → CollectorRunItem / CollectorRunResult(upsert, 含 endpoint metadata)
  → AssetEndpoint upsert（reachable/status/port_source/is_required）
  → PortCalibrationService.create_port_change_proposals()
  → AssetProposalService approve/reject/apply
  → apply 后才更新 DbInstance.port，并写入 AssetEventHistory
  → AssetEventHistory 记录事件
```

## 5. 缺失链路

| 模块 | 缺失环节 | 影响 | 建议 | 依据 |
|---|---|---|---|---|
| 账号操作 | Celery worker 有意暂缓 | 异步任务入队后不会执行 | 当前阶段不需要，后续需要时恢复启动代码 | `backend/run.py:63` |
| 审计日志 | `/api/logs/list` 硬编码返回 [] | 操作日志/登录日志/敏感操作三个页面无数据 | 核心资产管理收尾后实现 | `backend/app/api/logs.py:15` |
| 备份恢复 | 前端有 3 个页面，后端无 API | 页面无法展示任何数据 | 核心资产管理收尾后排期 | `frontend/src/views/backup/*.vue` |
| SQL 分析 | 前端有 3 个页面，后端无 API | 页面无法展示任何数据 | 核心资产管理收尾后排期 | `frontend/src/views/sql/*.vue` |
| 巡检健康 | 模型表已定义但无 API | 页面无法展示任何数据 | 核心资产管理收尾后排期 | `backend/app/models/dbops_assets.py:371-393` |
| 凭证中心 | 前端占位 | 页面无法展示任何数据 | 核心资产管理收尾后排期 | `frontend/src/views/credentials/*.vue` |
| 知识库 | 仅前端占位页面 | 页面无内容 | 核心资产管理收尾后排期 | `frontend/src/views/knowledge/Index.vue` |
| 业务评分 | BizScoreRule/Result/Detail 表已定义但无 API | 无法使用 | 核心资产管理收尾后排期 | `backend/app/models/dbops_assets.py:395-416` |

## 6. 需现场确认

- 备份恢复、SQL 分析、巡检健康、审计安全、凭证中心、知识库的具体排期（核心资产管理收尾后）
- Inventory.vue 对应的后端 API 是哪个？是否复用 `/api/v1/servers/servers` 的服务器列表？
