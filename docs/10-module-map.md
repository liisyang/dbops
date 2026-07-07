# 模块图

> 文档状态：已校准
> 最近校准：2026-06-29
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
| 自动化运维 - 批量校验 | 已实现（Phase 3.2 + Phase 3.3A） | 批量资产校验 + 分网段 AWX 分发调度 + DB/OS 事实采集；支持 asset_ids/filters 选择、check_codes 多选、按 awx_instance_group 分组、dispatch_run 级分发、item 级结果、失败重跑；Phase 3.3A 新增 fact_collection run_type，按 credential_group_hash 聚合 dispatch，callback 写入 fact_snapshot 并生成 drift_event；BatchVerify 页面会展示跳过项计数、单项 facts 与 raw_result 详情 | `backend/app/api/collector.py` + `backend/app/services/batch_collector_service.py` + `backend/app/services/dispatch_planner_service.py` + `backend/app/services/check_item_builder_registry.py` + `backend/app/services/credential_resolver_service.py` + `backend/app/services/fact_snapshot_service.py` + `backend/app/services/drift_detection_service.py` + `frontend/src/views/ops/BatchVerify.vue` |
| 凭证中心 | 已实现（Phase 3.3A） | 凭证档案（Profiles）+ 凭证绑定（Bindings）：管理 DB/OS 凭证与资产的绑定关系，供 AWX 采集任务自动解析注入 | `backend/app/api/collector.py`（凭证相关端点）+ `frontend/src/views/credentials/Profiles.vue` + `frontend/src/views/credentials/Bindings.vue` |
| 备份与恢复 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/backup/*.vue` |
| SQL 分析 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/sql/*.vue` |
| 巡检与健康 | 已实现（Phase 3.4 基础巡检中心） | 已落地巡检项管理、巡检任务创建/列表、巡检报告查询；复用 collector batch + callback 闭环，健康检查页仍为占位 | `backend/app/api/inspection.py` + `backend/app/services/inspection_service.py` + `frontend/src/views/inspection/{Items,Tasks,Reports}.vue` |
| 审计与安全 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/audit/*.vue` |
| 知识库 | 规划中 | 核心资产管理收尾后排期 | `frontend/src/views/knowledge/Index.vue` |
| WebSocket | 已实现 | 任务实时输出推送 | `backend/app/api/websocket.py` |
| AI Copilot - Chat | 已实现（Phase 3.6 C1-C5 + BE-bug1 修复 + Refactor 隐藏推理过程） | Dify chat-message app；user 维度会话/消息 CRUD + 发送（幂等 client_request_id）+ 消息历史；启动 stale cleanup；前端 Chat.vue 完整 UI（会话侧栏 + 消息流 + 输入框 + 错误兜底 409/502/503/504）；DifyService.chat_message 对 answer 字段权威剥离推理块（避免推理模型 DeepSeek R1 / o1 等混入最终答案），前端 ChatMessageBubble.displayContent computed 做显示层兜底剥离 | `backend/app/services/ai_chat_service.py` + `backend/app/services/dify_service.py` + `backend/app/services/ai_text.py`（剥离工具）+ `backend/app/api/ai.py:118-244` + `frontend/src/views/ai/Chat.vue` + `frontend/src/components/ai/ChatMessageBubble.vue` + `frontend/src/utils/aiText.ts`（剥离工具） |
| AI Copilot - Schema Snapshot | 已实现（Phase 3.6B0 C6-C10） | PostgreSQL 元数据采集（AWX 触发）+ callback 落库 + 5 态机（pending/running/success/failed/unavailable）；两阶段发布 is_current；TTL；SHA-256 snapshot_hash；4 API 端点（trigger/status/history/context）；context 含 schema_policy_hash 供 SQL Preview 强绑定 | `backend/app/services/ai/ai_schema_metadata_builder.py` + `backend/app/services/ai/ai_schema_snapshot_service.py` + `backend/app/services/ai/ai_schema_context_service.py` + `backend/app/services/ai/ai_schema_snapshot_callback_service.py` + `backend/app/api/ai.py:250-364` |
| AI Copilot - SQL Preview | 已实现（Phase 3.6B1 C11-C12 + C16-F2b） | sqlglot AST 权威层 + Dify sql-generator workflow 调用；6 层 SQL 安全防御（Layer 3 AST 落地）；双轨 SQL（generated_sql 审计追溯 vs approved_sql 权威）+ 双 SHA-256 + schema_policy_hash 强绑定；7 类异常 → HTTP 404/409/422/502/503/504；ai_sql_audit 表 24 字段/8 FK/6 CHECK/6 索引；**C16-F2b Chat 流内可调用入口**：4 步鉴权链（session ownership + chat_mode='instance_sql' + bound_instance_id 一致 + DbInstance.status='active'）+ client_request_id 幂等（partial unique 天然支持）+ 双消息写入事务（user + preview sql_preview_link + audit 三元组同事务）+ rejected 也写 preview_message 卡片（P1-3）；PreviewResult 扩 4 字段（session_id/user_message_id/preview_message_id/idempotent_replay）；5 类新异常 → HTTP 404/403/422/409 映射 | `backend/app/services/ai/ai_sql_preview_service.py` + `backend/app/services/sql_safety_service.py` + `backend/app/services/ai_chat_service.py:get_session_for_user` + `backend/app/api/ai.py:431-575` + `backend/tests/test_ai_sql_preview_c16_f2b.py` |
| AI Copilot - SQL Execute | 已实现（Phase 3.6B1 C14） | 引用 preview passed 的 audit_id 真正下发到目标 DB；Execute 时 AST 二次校验（防御 preview 后 audit 改写）+ approved_sql_hash 校验 + schema_policy_hash 一致性校验；内联构造 CollectorRun(business_domain='ai_sql', job_type='SQL_VERIFY', check_code='DB_READONLY_SQL_EXEC') + CollectorRunItem(executor_type='db_sql_readonly') + business_context 标准化 JSON；AWX launch 失败时 audit → failed + error_message 落库；Callback 走 collector_service 路由到 AiSqlCallbackService.save_execution_results（条件 UPDATE 终态 + 写 ai_chat_message sql_result，幂等键 `uq_ai_chat_message_sql_result_audit` 部分唯一索引）；6 类异常 → HTTP 404/409（3 子码：audit_not_passed / snapshot_policy_mismatch 结构化 detail / audit_already_running）/422（audit_unsafe_on_execute 结构化 detail）/502/503；前端 SqlPreview.vue 执行按钮 + 5 色状态徽章 + 3s 轮询 + Chat.vue 流式拉取 sql_result | `backend/app/services/ai/ai_sql_execute_service.py` + `backend/app/services/ai/ai_sql_callback_service.py` + `backend/app/api/ai.py:481-584` + `frontend/src/views/ai/SqlPreview.vue` + `frontend/src/components/ai/ChatMessageBubble.vue` |
| AI Copilot - Object Metadata Snapshot | 已实现（Phase 3.6B0 C16-F3） | PostgreSQL 对象 DDL 采集（AWX 触发）+ callback 落库 + 5 态机；1MB DDL 截断（callback service 兜底）+ SHA-256 object_ddl_sha256/snapshot_hash；partial unique 加 schema_name 维度（与 C8 不同）；context 注入 Dify inputs（8000 字符 preview 避免 token 超限）；4 API 端点（collect/status/history/context）；首版 PostgreSQL only（C16-F0 三方言合并）；Ansible role `db_object_metadata_collect` 镜像 `db_schema_metadata_collect` + check_code `DB_OBJECT_METADATA` + business_domain `ai_object_metadata` | `backend/app/services/check_item_builder_registry.py:1119-1273` (`_AiObjectMetadataBuilder`) + `backend/app/services/ai/ai_object_metadata_callback_service.py` (save_snapshots) + `backend/app/services/ai/ai_object_metadata_snapshot_service.py` (trigger/status/history/published/cleanup) + `backend/app/services/ai/ai_schema_context_service.py:350-401` (`_build_object_metadata_field`) + `backend/app/api/ai.py:585-780` (4 端点) + `backend/db/dbops_phase3_6b0_ai_object_metadata.sql` (DDL 21 字段/4 CHECK/5 索引) + `ansible-playbooks/playbooks/roles/db_object_metadata_collect/tasks/main.yml` |
| AI Copilot - Schema/Object Snapshot 三方言合并（C16-F0） | 已实现（Phase 3.6B0 C16-F0） | Schema Snapshot + Object Metadata Snapshot 双链路从 PostgreSQL only 扩展为 **PostgreSQL + Oracle + SQL Server** 三方言支持（MySQL 延后，按 plan §4.8）；后端 Builder 按 `db_type_code` 派发对应方言 SQL 模板（`_load_sql_template` 统一入口，4 个 PG/Oracle/MSSQL SQL 模板文件分目录存放）；Ansible `db_schema_metadata_collect` + `db_object_metadata_collect` role assertion 扩 5 个 dialect 接受值；DDL `CHECK (db_type_code IN ('POSTGRESQL','ORACLE','MSSQL','MYSQL'))` 已就位无需新迁移（db_type_code 规范化为大写）；84 unit tests 覆盖（builder 36+36 + 12 边界/parametrize） | `backend/app/services/ai/sql_templates/oracle/ora_schema_columns.sql` + `ora_object_metadata.sql`（6 列 / 5 列×6 UNION ALL segment）+ `backend/app/services/ai/sql_templates/mssql/mssql_schema_columns.sql` + `mssql_object_metadata.sql`（6 列 / 5 列×9 UNION ALL segment）+ `backend/app/services/check_item_builder_registry.py`（`_AiSchemaMetadataBuilder` + `_AiObjectMetadataBuilder` 重构共用 `_SQL_TEMPLATE_MAP` + `_load_sql_template`）+ `backend/app/services/collector_service.py`（修 C16-F3 漏注册 bug：`DB_OBJECT_METADATA` 加 `_check_definition_defaults` + reachability gating set）+ `ansible-playbooks/playbooks/roles/db_schema_metadata_collect/tasks/main.yml` + `db_object_metadata_collect/tasks/main.yml` |
| AI Copilot - Chat 绑定实例（C16-F2a） | 已实现（Phase 3.6B2 C16-F2a） | Chat session 支持 `chat_mode` (general / instance_sql) + `bound_instance_id` 实例绑定；plan §21.2 P0-1 不可变绑定规则（chat_mode + bound_instance_id 创建后不可修改）；DB 层 2 CHECK + FK + partial unique 兜底；service 层 4 步校验（mode 枚举 → mode/bound 一致 → DbInstance.status='active' → instance_sql 复用）；新 3 异常 + CreateSessionResult dataclass；API 端 422/404/409 异常映射 | `backend/db/dbops_phase3_6b2_c16_f2a_chat_mode.sql` (ADD COLUMN chat_mode + bound_instance_id + 2 CHECK + FK + partial unique + idx) + `backend/app/models/ai.py` (AiChatSession 加 2 字段 + 2 CheckConstraint + 2 Index) + `backend/app/schemas/ai.py` (AiChatSessionCreateRequest mode/bound_instance_id/source_page + AiChatSessionResponse 暴露 chat_mode/bound_instance_id + ChatMode Literal) + `backend/app/services/ai_chat_service.py` (create_session 扩展 + DbInstance.status 校验 + instance_sql 复用 + 3 异常 + CreateSessionResult) + `backend/app/api/ai.py` (POST /chat/sessions 异常映射) |

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
| 巡检中心 | inspection/Items.vue + inspection/Tasks.vue + inspection/Reports.vue | assets.ts → `/v1/inspection/items*` + `/v1/inspection/tasks*` + `/v1/inspection/results` | `api/inspection.py` + `/collector/callback` 扩展 `inspection_results` | InspectionService + BatchCollectorService + CheckItemBuilderRegistry + CollectorService | InspectionItem / InspectionSchedule / InspectionTask / InspectionResult | inspection_item / inspection_schedule / inspection_task / inspection_result（关联 collector_batch_run） | 已实现（Phase 3.4：run_type=inspection 复用 AWX 分发和 callback） |
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
| 健康检查 | 健康检查页仍为占位 | 页面无法展示任何数据 | 后续按排期补全健康专项 API | `frontend/src/views/inspection/Health.vue` |
| 知识库 | 仅前端占位页面 | 页面无内容 | 核心资产管理收尾后排期 | `frontend/src/views/knowledge/Index.vue` |
| 业务评分 | BizScoreRule/Result/Detail 表已定义但无 API | 无法使用 | 核心资产管理收尾后排期 | `backend/app/models/dbops_assets.py:395-416` |

## 6. 需现场确认

- 备份恢复、SQL 分析、巡检健康、审计安全、知识库的具体排期（核心资产管理收尾后）
- Inventory.vue 对应的后端 API 是哪个？是否复用 `/api/v1/servers/servers` 的服务器列表？
