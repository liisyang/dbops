# API Inventory

> 文档状态：已校准
> 最近校准：2026-05-21
> 依据来源：真实代码

## 1. 维护定位

本文件记录当前代码中可确认的 API 清单。

本文件用于首次接入和阶段性盘点。

日常接口变化时，由 AI 自动追加、修改或删除相关条目。

## 2. 后端 API 清单

### 2.1 Auth（prefix: `/api/auth`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| POST | `/api/auth/login` | `api/auth.py:24` | - (直接查 User model) | 否 | 已实现 | `backend/app/api/auth.py:24-58` |

### 2.2 资产管理 - 实例（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/v1/servers/instances` | `api/servers.py:78` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:78-108` |
| GET | `/api/v1/servers/instances/{instance_id}` | `api/servers.py:111` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:111-121` |
| POST | `/api/v1/servers/dbinstances` | `api/servers.py:575` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:575-586` |
| PUT | `/api/v1/servers/dbinstances/{instance_id}` | `api/servers.py:589` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:589-601` |
| DELETE | `/api/v1/servers/dbinstances/{instance_id}` | `api/servers.py:604` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:604-614` |

### 2.3 资产管理 - 服务器（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/v1/servers/servers` | `api/servers.py:126` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:126-148` |
| GET | `/api/v1/servers/servers/{server_id}` | `api/servers.py:151` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:151-161` |
| POST | `/api/v1/servers/servers` | `api/servers.py:164` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:164-174` |
| PUT | `/api/v1/servers/servers/{server_id}` | `api/servers.py:177` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:177-188` |
| DELETE | `/api/v1/servers/servers/{server_id}` | `api/servers.py:191` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:191-201` |
| POST | `/api/v1/servers/servers/batch-delete` | `api/servers.py:204` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:204-218` |

### 2.4 资产管理 - 联系人（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/v1/servers/contacts` | `api/servers.py:223` | DbopsContactService | JWT | 已实现 | `backend/app/api/servers.py:223-229` |
| POST | `/api/v1/servers/contacts` | `api/servers.py:232` | DbopsContactService | JWT | 已实现 | `backend/app/api/servers.py:232-240` |
| PUT | `/api/v1/servers/contacts/{contact_id}` | `api/servers.py:243` | DbopsContactService | JWT | 已实现 | `backend/app/api/servers.py:243-256` |
| DELETE | `/api/v1/servers/contacts/{contact_id}` | `api/servers.py:259` | DbopsContactService | JWT | 已实现 | `backend/app/api/servers.py:259-267` |

### 2.5 资产管理 - 业务系统（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/v1/servers/business-services` | `api/servers.py:272` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:272-278` |
| POST | `/api/v1/servers/business-services` | `api/servers.py:281` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:281-289` |
| PUT | `/api/v1/servers/business-services/{system_id}` | `api/servers.py:292` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:292-305` |
| GET | `/api/v1/servers/business-services/{system_id}` | `api/servers.py:308` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:308-318` |
| GET | `/api/v1/servers/business-services/{system_id}/lifecycle/history` | `api/servers.py:321` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:321-329` |
| POST | `/api/v1/servers/business-services/{system_id}/lifecycle` | `api/servers.py:332` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:332-363` |
| POST | `/api/v1/servers/business-services/{system_id}/contacts` | `api/servers.py:366` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:366-381` |
| DELETE | `/api/v1/servers/business-services/{system_id}/contacts/{contact_id}/{role_code}` | `api/servers.py:384` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:384-401` |

### 2.6 资产管理 - 统计（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/v1/servers/stats/dashboard` | `api/servers.py:406` | DbopsStatsService | JWT | 已实现 | `backend/app/api/servers.py:406-412` |
| GET | `/api/v1/servers/stats/by-country` | `api/servers.py:415` | DbopsStatsService | JWT | 已实现 | `backend/app/api/servers.py:415-421` |
| GET | `/api/v1/servers/stats/by-factory` | `api/servers.py:424` | DbopsStatsService | JWT | 已实现 | `backend/app/api/servers.py:424-429` |
| GET | `/api/v1/servers/stats/by-cluster` | `api/servers.py:433` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:433-439` |
| GET | `/api/v1/servers/stats/by-deploy-type` | `api/servers.py:442` | DbopsStatsService | JWT | 已实现 | `backend/app/api/servers.py:442-448` |
| GET | `/api/v1/servers/stats/by-provider` | `api/servers.py:451` | DbopsStatsService | JWT | 已实现 | `backend/app/api/servers.py:451-457` |
| GET | `/api/v1/servers/stats/summary-by-type` | `api/servers.py:460` | DbopsStatsService | JWT | 已实现 | `backend/app/api/servers.py:460-466` |
| GET | `/api/v1/servers/stats/by-system-group` | `api/servers.py:469` | DbopsStatsService | JWT | 已实现 | `backend/app/api/servers.py:469-475` |

### 2.7 资产管理 - 集群（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/v1/servers/clusters` | `api/servers.py:490` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:490-496` |
| GET | `/api/v1/servers/clusters/{cluster_id}` | `api/servers.py:499` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:499-509` |
| GET | `/api/v1/servers/clusters/{cluster_id}/instances` | `api/servers.py:480` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:480-487` |
| POST | `/api/v1/servers/clusters` | `api/servers.py:530` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:530-541` |
| PUT | `/api/v1/servers/clusters/{cluster_id}` | `api/servers.py:544` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:544-556` |
| DELETE | `/api/v1/servers/clusters/{cluster_id}` | `api/servers.py:559` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:559-572` |

### 2.8 资产管理 - 字典/下拉（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/v1/servers/dicts/db-types` | `api/servers.py:512` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:512-518` |
| GET | `/api/v1/servers/dicts/servers-dropdown` | `api/servers.py:521` | DbopsAssetService | JWT | 已实现 | `backend/app/api/servers.py:521-527` |

### 2.9 资产管理 - 导入（prefix: `/api/v1/servers`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| POST | `/api/v1/servers/imports/preview` | `api/servers.py:619` | DbopsImportService | JWT | 已实现 | `backend/app/api/servers.py:619-635` |
| POST | `/api/v1/servers/imports/execute` | `api/servers.py:638` | DbopsImportService | JWT | 已实现 | `backend/app/api/servers.py:638-676` |
| GET | `/api/v1/servers/imports/batches` | `api/servers.py:679` | DbopsImportService | JWT | 已实现 | `backend/app/api/servers.py:679-690` |

### 2.10 自动化运维 - 账号操作（prefix: `/api`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| POST | `/api/users/add` | `api/account_ops.py:45` | account_tasks (Celery) | JWT | 部分实现 | `backend/app/api/account_ops.py:45-78` |
| POST | `/api/users/check` | `api/account_ops.py:89` | account_tasks (Celery) | JWT | 部分实现 | `backend/app/api/account_ops.py:89-123` |
| POST | `/api/users/chpasswd` | `api/account_ops.py:134` | account_tasks (Celery) | JWT | 部分实现 | `backend/app/api/account_ops.py:134-175` |
| GET | `/api/tasks/{task_id}` | `api/account_ops.py:186` | Redis TaskState | JWT | 部分实现 | `backend/app/api/account_ops.py:186-196` |
| GET | `/api/tasks/{task_id}/results` | `api/account_ops.py:199` | Redis TaskState | JWT | 部分实现 | `backend/app/api/account_ops.py:199-216` |

> 说明：Celery worker 有意暂缓启用（`backend/run.py:63`），因此任务入队后不会实际执行。前端 Tasks.vue 为占位页面。

### 2.11 日志（prefix: `/api/logs`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| GET | `/api/logs/list` | `api/logs.py:11` | - | JWT | 空实现 | `backend/app/api/logs.py:11-15` |

> 说明：`return []` 硬编码空数组，TODO 注释说明"审计模块实现后从此模块获取"。

### 2.12 WebSocket（prefix: `/ws`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| WS | `/ws/{socket_id}` | `api/websocket.py:62` | ConnectionManager | 否 | 已实现 | `backend/app/api/websocket.py:62-75` |

> 说明：通过 Redis pub/sub channel `task_output` 接收 Celery 任务输出并推送到对应房间。Redis 订阅者在 main.py lifespan 中启动。

### 2.13 AWX 资产校验（prefix: `/api/v1`）

| 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|
| POST | `/api/v1/collector/runs` | `api/collector.py:42` | CollectorService + AwxService | JWT | 已实现（主入口） | `backend/app/api/collector.py`, `backend/app/services/collector_service.py` |
| POST | `/api/v1/automation/asset-verify/{instance_id}/launch` | `api/collector.py:22` | CollectorService + AwxService | JWT | 已实现（兼容包装） | `backend/app/api/collector.py`, `backend/app/services/collector_service.py` |
| GET | `/api/v1/collector/runs/{run_id}` | `api/collector.py:43` | CollectorService | JWT | 已实现 | `backend/app/api/collector.py` |
| GET | `/api/v1/collector/runs/{run_id}/items` | `api/collector.py:61` | CollectorService | JWT | 已实现 | `backend/app/api/collector.py` |
| GET | `/api/v1/collector/instances/{instance_id}/runs` | `api/collector.py:54` | CollectorService | JWT | 已实现 | `backend/app/api/collector.py` |
| GET | `/api/v1/collector/servers/{server_id}/runs` | `api/collector.py:71` | CollectorService | JWT | 已实现 | `backend/app/api/collector.py` |
| GET | `/api/v1/collector/endpoints` | `api/collector.py:81` | CollectorService | JWT | 已实现 | `backend/app/api/collector.py` |
| POST | `/api/v1/collector/callback/` | `api/collector.py:66` | CollectorService | `X-Collector-Token`（不走 JWT） | 已实现 | `backend/app/api/collector.py` |

## 3. 前端 API 封装清单

### 3.1 assets.ts（baseURL: `/api`，封装 `/v1/servers/*`）

| 前端封装 | 方法 | 路径 | 调用页面 | 状态 | 代码依据 |
|---|---|---|---|---|---|
| assetsApi.listServers | GET | `/api/v1/servers/servers` | Servers.vue | 已实现 | `frontend/src/api/assets.ts:27-28` |
| assetsApi.getServer | GET | `/api/v1/servers/servers/{id}` | Servers.vue | 已实现 | `frontend/src/api/assets.ts:29-30` |
| assetsApi.createServer | POST | `/api/v1/servers/servers` | Servers.vue | 已实现 | `frontend/src/api/assets.ts:31-32` |
| assetsApi.updateServer | PUT | `/api/v1/servers/servers/{id}` | Servers.vue | 已实现 | `frontend/src/api/assets.ts:33-34` |
| assetsApi.deleteServer | DELETE | `/api/v1/servers/servers/{id}` | Servers.vue | 已实现 | `frontend/src/api/assets.ts:35-36` |
| assetsApi.listInstances | GET | `/api/v1/servers/instances` | Instances.vue | 已实现 | `frontend/src/api/assets.ts:38-39` |
| assetsApi.getInstance | GET | `/api/v1/servers/instances/{id}` | InstanceDetail.vue | 已实现 | `frontend/src/api/assets.ts:40-41` |
| assetsApi.createCollectorRun | POST | `/api/v1/collector/runs` | InstanceDetail.vue | 已实现（主入口） | `frontend/src/api/assets.ts` |
| assetsApi.launchAssetVerify | POST | `/api/v1/automation/asset-verify/{id}/launch` | InstanceDetail.vue（兼容） | 已实现 | `frontend/src/api/assets.ts` |
| assetsApi.getCollectorRun | GET | `/api/v1/collector/runs/{run_id}` | InstanceDetail.vue（可扩展） | 已实现 | `frontend/src/api/assets.ts` |
| assetsApi.listCollectorRunItems | GET | `/api/v1/collector/runs/{run_id}/items` | InstanceDetail.vue | 已实现 | `frontend/src/api/assets.ts` |
| assetsApi.listInstanceCollectorRuns | GET | `/api/v1/collector/instances/{id}/runs` | InstanceDetail.vue | 已实现 | `frontend/src/api/assets.ts` |
| assetsApi.listServerCollectorRuns | GET | `/api/v1/collector/servers/{id}/runs` | InstanceDetail.vue（可扩展） | 已实现 | `frontend/src/api/assets.ts` |
| assetsApi.listCollectorEndpoints | GET | `/api/v1/collector/endpoints` | InstanceDetail.vue | 已实现 | `frontend/src/api/assets.ts` |
| assetsApi.listClusters | GET | `/api/v1/servers/clusters` | Clusters.vue, ClusterDetail.vue | 已实现 | `frontend/src/api/assets.ts:43-44` |
| assetsApi.getCluster | GET | `/api/v1/servers/clusters/{id}` | ClusterDetail.vue | 已实现 | `frontend/src/api/assets.ts:45-46` |
| assetsApi.getClusterInstances | GET | `/api/v1/servers/clusters/{id}/instances` | ClusterDetail.vue | 已实现 | `frontend/src/api/assets.ts:47-48` |
| assetsApi.createCluster | POST | `/api/v1/servers/clusters` | Clusters.vue | 已实现 | `frontend/src/api/assets.ts:49-50` |
| assetsApi.updateCluster | PUT | `/api/v1/servers/clusters/{id}` | Clusters.vue | 已实现 | `frontend/src/api/assets.ts:51-52` |
| assetsApi.deleteCluster | DELETE | `/api/v1/servers/clusters/{id}` | Clusters.vue | 已实现 | `frontend/src/api/assets.ts:53-54` |
| assetsApi.listDbTypes | GET | `/api/v1/servers/dicts/db-types` | Clusters.vue, Instances.vue | 已实现 | `frontend/src/api/assets.ts:56-57` |
| assetsApi.listServersDropdown | GET | `/api/v1/servers/dicts/servers-dropdown` | Instances.vue | 已实现 | `frontend/src/api/assets.ts:58-59` |
| assetsApi.createDbInstance | POST | `/api/v1/servers/dbinstances` | Instances.vue | 已实现 | `frontend/src/api/assets.ts:61-62` |
| assetsApi.updateDbInstance | PUT | `/api/v1/servers/dbinstances/{id}` | InstanceDetail.vue | 已实现 | `frontend/src/api/assets.ts:63-64` |
| assetsApi.deleteDbInstance | DELETE | `/api/v1/servers/dbinstances/{id}` | Instances.vue | 已实现 | `frontend/src/api/assets.ts:65-66` |
| assetsApi.listContacts | GET | `/api/v1/servers/contacts` | Contacts.vue, BusinessSystemDetail.vue | 已实现 | `frontend/src/api/assets.ts:68-69` |
| assetsApi.createContact | POST | `/api/v1/servers/contacts` | Contacts.vue | 已实现 | `frontend/src/api/assets.ts:70-71` |
| assetsApi.updateContact | PUT | `/api/v1/servers/contacts/{id}` | Contacts.vue | 已实现 | `frontend/src/api/assets.ts:72-73` |
| assetsApi.deleteContact | DELETE | `/api/v1/servers/contacts/{id}` | Contacts.vue | 已实现 | `frontend/src/api/assets.ts:74-75` |
| assetsApi.listBusinessSystems | GET | `/api/v1/servers/business-services` | Assets.vue | 已实现 | `frontend/src/api/assets.ts:77-78` |
| assetsApi.getBusinessSystem | GET | `/api/v1/servers/business-services/{id}` | BusinessSystemDetail.vue | 已实现 | `frontend/src/api/assets.ts:79-80` |
| assetsApi.createBusinessSystem | POST | `/api/v1/servers/business-services` | Assets.vue | 已实现 | `frontend/src/api/assets.ts:81-82` |
| assetsApi.updateBusinessSystem | PUT | `/api/v1/servers/business-services/{id}` | Assets.vue | 已实现 | `frontend/src/api/assets.ts:83-84` |
| assetsApi.addBusinessSystemContact | POST | `/api/v1/servers/business-services/{id}/contacts` | BusinessSystemDetail.vue | 已实现 | `frontend/src/api/assets.ts:85-86` |
| assetsApi.deleteBusinessSystemContact | DELETE | `/api/v1/servers/business-services/{sid}/contacts/{cid}/{role}` | BusinessSystemDetail.vue | 已实现 | `frontend/src/api/assets.ts:87-88` |
| assetsApi.listBusinessSystemHistory | GET | `/api/v1/servers/business-services/{id}/lifecycle/history` | BusinessSystemDetail.vue | 已实现 | `frontend/src/api/assets.ts:89-90` |
| assetsApi.changeBusinessSystemLifecycle | POST | `/api/v1/servers/business-services/{id}/lifecycle` | BusinessSystemDetail.vue | 已实现 | `frontend/src/api/assets.ts:91-99` |
| assetsApi.previewImport | POST | `/api/v1/servers/imports/preview` | Import.vue | 已实现 | `frontend/src/api/assets.ts:101-104` |
| assetsApi.executeImport | POST | `/api/v1/servers/imports/execute` | Import.vue | 已实现 | `frontend/src/api/assets.ts:105-108` |
| assetsApi.getImportBatches | GET | `/api/v1/servers/imports/batches` | Import.vue | 已实现 | `frontend/src/api/assets.ts:109-110` |

### 3.2 auth.ts（baseURL: `/api`，封装 `/auth/*`）

| 前端封装 | 方法 | 路径 | 调用页面 | 状态 | 代码依据 |
|---|---|---|---|---|---|
| authApi.login | POST | `/api/auth/login` | Login.vue | 已实现 | `frontend/src/api/auth.ts:11-12` |

### 3.3 stats.ts（baseURL: `/api`，封装 `/v1/servers/stats/*`）

| 前端封装 | 方法 | 路径 | 调用页面 | 状态 | 代码依据 |
|---|---|---|---|---|---|
| statsApi.getDashboard | GET | `/api/v1/servers/stats/dashboard` | Dashboard.vue | 已实现 | `frontend/src/api/stats.ts:5-6` |
| statsApi.getByCountry | GET | `/api/v1/servers/stats/by-country` | Dashboard.vue, Stats.vue | 已实现 | `frontend/src/api/stats.ts:7-8` |
| statsApi.getByFactory | GET | `/api/v1/servers/stats/by-factory` | Dashboard.vue, Stats.vue | 已实现 | `frontend/src/api/stats.ts:9-10` |
| statsApi.getByCluster | GET | `/api/v1/servers/stats/by-cluster` | Stats.vue | 已实现 | `frontend/src/api/stats.ts:11-12` |
| statsApi.getByDeployType | GET | `/api/v1/servers/stats/by-deploy-type` | Dashboard.vue, Stats.vue | 已实现 | `frontend/src/api/stats.ts:13-14` |
| statsApi.getByProvider | GET | `/api/v1/servers/stats/by-provider` | Dashboard.vue, Stats.vue | 已实现 | `frontend/src/api/stats.ts:15-16` |
| statsApi.getSummaryByType | GET | `/api/v1/servers/stats/summary-by-type` | Dashboard.vue, Stats.vue | 已实现 | `frontend/src/api/stats.ts:17-18` |
| statsApi.getBySystemGroup | GET | `/api/v1/servers/stats/by-system-group` | Stats.vue | 已实现 | `frontend/src/api/stats.ts:19-20` |

### 3.4 logs.ts / logs.js（baseURL: `/api`，封装 `/logs/*`）

| 前端封装 | 方法 | 路径 | 调用页面 | 状态 | 代码依据 |
|---|---|---|---|---|---|
| logsApi.list (logs.ts) | GET | `/api/logs` | 无页面调用 | 路径错误 | `frontend/src/api/logs.ts:6` |
| logsApi.get (logs.ts) | GET | `/api/logs/{id}` | 无页面调用 | 路径错误 | `frontend/src/api/logs.ts:7` |
| logsApi.list (logs.js) | GET | `/api/logs/list` | 无页面调用 | 正确路径 | `frontend/src/api/logs.js:4` |

> 说明：两个文件同名导出 `logsApi`，存在覆盖风险。`logs.ts` 路径错误（`/logs` 和 `/logs/{id}` 后端不存在），`logs.js` 路径正确（`/logs/list`）。但 Logs.vue 当前未导入任何 `logsApi`——页面是占位状态。

### 3.5 账号操作 / WebSocket（无前端封装）

| 功能 | 当前状态 | 代码依据 |
|---|---|---|
| POST `/api/users/add` | 无前端 API 封装，Tasks.vue 为占位页面 | `frontend/src/views/ops/Tasks.vue` |
| POST `/api/users/check` | 无前端 API 封装 | 同上 |
| POST `/api/users/chpasswd` | 无前端 API 封装 | 同上 |
| GET `/api/tasks/{task_id}` | 无前端 API 封装 | 同上 |
| GET `/api/tasks/{task_id}/results` | 无前端 API 封装 | 同上 |
| WS `/ws/{socket_id}` | 无前端 WebSocket 封装 | 同上 |

## 4. 前后端契约不一致

| 模块 | 前端调用 | 后端接口 | 不一致点 | 影响 | 建议 |
|---|---|---|---|---|---|
| 日志 | `logs.ts`: `GET /api/logs` | `logs.py`: `GET /api/logs/list` | 前端 `logs.ts` 路径缺少 `/list` 后缀，且还有个不存在的 `GET /api/logs/{id}` | 调用 404 | `logs.ts` 改为 `/logs/list`，删除不存在的 `get(id)` 方法，或统一使用 `logs.js` 的封装 |
| 日志 | `logs.ts` / `logs.js` 同名导出 | - | 两个文件都 export `logsApi`，存在覆盖风险 | 实际生效取决于打包器/导入顺序 | 删除冗余文件，只保留一个封装 |
| Auth OAuth2 | - | `deps.py:20` tokenUrl=`/api/rbac/login` | 依赖注入声明 tokenUrl 为 `/api/rbac/login`，实际登录路由为 `/api/auth/login` | Swagger UI 认证流程可能指向错误 URL | 将 tokenUrl 改为 `/api/auth/login` |
| 服务器批量删除 | `Servers.vue` 循环调用 `deleteServer(id)` | `POST /api/v1/servers/servers/batch-delete` | 前端逐个调用单删接口，后端提供了批量删除接口但前端未使用 | 批量删除性能差，需 N 次 HTTP 请求 | 前端改用 `batchDeleteServers` 调用批量删除接口 |
| 账号操作 | 无前端封装 | 5 个后端接口已实现 | 后端 API 已就绪，前端无对应的 API 封装层和页面调用 | 功能不可用 | 需现场确认是否需要前端对接 |

## 5. 后端存在但前端未发现调用

| 模块 | 方法 | 路径 | 后端入口 | 可能用途 | 依据 |
|---|---|---|---|---|---|
| 服务器 | POST | `/api/v1/servers/servers/batch-delete` | `api/servers.py:204` | 批量删除服务器 | 前端 Servers.vue 批量删除时逐条调用 `deleteServer` |
| 账号操作 | POST | `/api/users/add` | `api/account_ops.py:45` | 异步新增数据库用户 | Tasks.vue 为占位页面，Celery worker 暂停 |
| 账号操作 | POST | `/api/users/check` | `api/account_ops.py:89` | 检查数据库用户是否存在 | 同上 |
| 账号操作 | POST | `/api/users/chpasswd` | `api/account_ops.py:134` | 异步修改数据库用户密码 | 同上 |
| 任务 | GET | `/api/tasks/{task_id}` | `api/account_ops.py:186` | 查询异步任务状态 | 同上 |
| 任务 | GET | `/api/tasks/{task_id}/results` | `api/account_ops.py:199` | 查询异步任务结果 | 同上 |
| WebSocket | WS | `/ws/{socket_id}` | `api/websocket.py:62` | 任务实时输出推送 | 前端无 WebSocket 连接逻辑 |

## 6. 前端调用但后端未发现接口

| 模块 | 前端调用 | 调用页面 | 影响 | 建议 | 依据 |
|---|---|---|---|---|---|
| 日志 | `logs.ts`: `GET /api/logs` | 无页面实际调用 | 即使调用也会 404 | 修复路径为 `/api/logs/list` 或删除 | `frontend/src/api/logs.ts:6` |
| 日志 | `logs.ts`: `GET /api/logs/{id}` | 无页面实际调用 | 后端无此路由 | 删除此方法 | `frontend/src/api/logs.ts:7` |

## 7. 需现场确认

- 账号操作（users/add, check, chpasswd, tasks）是否需要前端对接并启用 Celery worker？
- WebSocket 连接是否需要前端实现实时推送 UI？
- `logs.ts` vs `logs.js` 哪个是期望的封装？建议删除 `logs.ts`（路径错误）或修正并统一。
- `OAuth2PasswordBearer(tokenUrl="/api/rbac/login")` 是否故意指向 `/api/rbac/login` 还是历史遗留？
