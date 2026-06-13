# API 契约附录

> 文档状态：已校准
> 最近校准：2026-06-13
> 依据来源：真实代码

## 1. 维护定位

本文件不追求全量接口文档。

只记录：

1. 跨模块核心接口。
2. 近期新增或变更接口。
3. 前后端契约容易不一致的接口。
4. 第三方系统对接接口。
5. 本次任务涉及的接口。

全量接口清单见：

- `docs/contracts/api-inventory.md`

## 2. 核心接口

### 2.1 认证

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 | 认证 |
|---|---|---|---|---|---|
| POST | `/api/auth/login` | `api/auth.py:24` | `auth.ts:11` | Login.vue | 否 |

请求体（基于后端 User model 验证逻辑）：

| 字段 | 类型 | 必填 |
|---|---|---|
| username | string | 是 |
| password | string | 是 |

响应（基于 `api/auth.py:38-58`）：

| 字段 | 类型 |
|---|---|
| access_token | string |
| token_type | string |
| user | object |

### 2.2 资产管理 - 服务器

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| GET | `/api/v1/servers/servers` | `api/servers.py:126` | `assets.ts:27` | Servers.vue |
| POST | `/api/v1/servers/servers` | `api/servers.py:164` | `assets.ts:31` | Servers.vue |
| PUT | `/api/v1/servers/servers/{server_id}` | `api/servers.py:177` | `assets.ts:33` | Servers.vue |
| DELETE | `/api/v1/servers/servers/{server_id}` | `api/servers.py:191` | `assets.ts:35` | Servers.vue |
| POST | `/api/v1/servers/servers/batch-delete` | `api/servers.py:204` | 无前端封装 | - |

> 注：`batch-delete` 后端已实现但前端未使用，Servers.vue 批量删除时逐条调用单删接口。

### 2.3 资产管理 - 数据库实例

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| GET | `/api/v1/servers/instances` | `api/servers.py:78` | `assets.ts:38` | Instances.vue |
| GET | `/api/v1/servers/instances/{instance_id}` | `api/servers.py:111` | `assets.ts:40` | InstanceDetail.vue |
| POST | `/api/v1/servers/dbinstances` | `api/servers.py:575` | `assets.ts:61` | Instances.vue |
| PUT | `/api/v1/servers/dbinstances/{instance_id}` | `api/servers.py:589` | `assets.ts:63` | InstanceDetail.vue |
| DELETE | `/api/v1/servers/dbinstances/{instance_id}` | `api/servers.py:604` | `assets.ts:65` | Instances.vue |

### 2.4 资产管理 - 集群

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| GET | `/api/v1/servers/clusters` | `api/servers.py:490` | `assets.ts:43` | Clusters.vue |
| GET | `/api/v1/servers/clusters/{cluster_id}` | `api/servers.py:499` | `assets.ts:45` | ClusterDetail.vue |
| GET | `/api/v1/servers/clusters/{cluster_id}/instances` | `api/servers.py:480` | `assets.ts:47` | ClusterDetail.vue |
| POST | `/api/v1/servers/clusters` | `api/servers.py:530` | `assets.ts:49` | Clusters.vue |
| PUT | `/api/v1/servers/clusters/{cluster_id}` | `api/servers.py:544` | `assets.ts:51` | Clusters.vue |
| DELETE | `/api/v1/servers/clusters/{cluster_id}` | `api/servers.py:559` | `assets.ts:53` | Clusters.vue |

### 2.5 资产管理 - 联系人

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| GET | `/api/v1/servers/contacts` | `api/servers.py:223` | `assets.ts:68` | Contacts.vue |
| POST | `/api/v1/servers/contacts` | `api/servers.py:232` | `assets.ts:70` | Contacts.vue |
| PUT | `/api/v1/servers/contacts/{contact_id}` | `api/servers.py:243` | `assets.ts:72` | Contacts.vue |
| DELETE | `/api/v1/servers/contacts/{contact_id}` | `api/servers.py:259` | `assets.ts:74` | Contacts.vue |

### 2.6 资产管理 - 业务系统

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| GET | `/api/v1/servers/business-services` | `api/servers.py:272` | `assets.ts:77` | Assets.vue |
| GET | `/api/v1/servers/business-services/{system_id}` | `api/servers.py:308` | `assets.ts:79` | BusinessSystemDetail.vue |
| POST | `/api/v1/servers/business-services` | `api/servers.py:281` | `assets.ts:81` | Assets.vue |
| PUT | `/api/v1/servers/business-services/{system_id}` | `api/servers.py:292` | `assets.ts:83` | Assets.vue |
| POST | `/api/v1/servers/business-services/{system_id}/lifecycle` | `api/servers.py:332` | `assets.ts:91` | BusinessSystemDetail.vue |
| GET | `/api/v1/servers/business-services/{system_id}/lifecycle/history` | `api/servers.py:321` | `assets.ts:89` | BusinessSystemDetail.vue |
| POST | `/api/v1/servers/business-services/{system_id}/contacts` | `api/servers.py:366` | `assets.ts:85` | BusinessSystemDetail.vue |
| DELETE | `/api/v1/servers/business-services/{system_id}/contacts/{contact_id}/{role_code}` | `api/servers.py:384` | `assets.ts:87` | BusinessSystemDetail.vue |

### 2.7 统计

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| GET | `/api/v1/servers/stats/dashboard` | `api/servers.py:406` | `stats.ts:5` | Dashboard.vue |
| GET | `/api/v1/servers/stats/by-country` | `api/servers.py:415` | `stats.ts:7` | Dashboard.vue, Stats.vue |
| GET | `/api/v1/servers/stats/by-factory` | `api/servers.py:424` | `stats.ts:9` | Dashboard.vue, Stats.vue |
| GET | `/api/v1/servers/stats/by-cluster` | `api/servers.py:433` | `stats.ts:11` | Stats.vue |
| GET | `/api/v1/servers/stats/by-deploy-type` | `api/servers.py:442` | `stats.ts:13` | Dashboard.vue, Stats.vue |
| GET | `/api/v1/servers/stats/by-provider` | `api/servers.py:451` | `stats.ts:15` | Dashboard.vue, Stats.vue |
| GET | `/api/v1/servers/stats/summary-by-type` | `api/servers.py:460` | `stats.ts:17` | Dashboard.vue, Stats.vue |
| GET | `/api/v1/servers/stats/by-system-group` | `api/servers.py:469` | `stats.ts:19` | Stats.vue |

### 2.8 导入

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| POST | `/api/v1/servers/imports/preview` | `api/servers.py:619` | `assets.ts:101` | Import.vue |
| POST | `/api/v1/servers/imports/execute` | `api/servers.py:638` | `assets.ts:105` | Import.vue |
| GET | `/api/v1/servers/imports/batches` | `api/servers.py:679` | `assets.ts:109` | Import.vue |

### 2.9 字典/下拉

| 方法 | 路径 | 后端入口 | 前端封装 | 调用页面 |
|---|---|---|---|---|
| GET | `/api/v1/servers/dicts/db-types` | `api/servers.py:512` | `assets.ts:56` | Clusters.vue, Instances.vue |
| GET | `/api/v1/servers/dicts/servers-dropdown` | `api/servers.py:521` | `assets.ts:58` | Instances.vue |

### 2.10 自动化运维 - 账号操作

| 方法 | 路径 | 后端入口 | 前端封装 | 状态 |
|---|---|---|---|---|
| POST | `/api/users/add` | `api/account_ops.py:45` | 无 | 已实现（Celery 暂停） |
| POST | `/api/users/check` | `api/account_ops.py:89` | 无 | 已实现（Celery 暂停） |
| POST | `/api/users/chpasswd` | `api/account_ops.py:134` | 无 | 已实现（Celery 暂停） |
| GET | `/api/tasks/{task_id}` | `api/account_ops.py:186` | 无 | 已实现 |
| GET | `/api/tasks/{task_id}/results` | `api/account_ops.py:199` | 无 | 已实现 |

> 这些接口通过 Celery + Ansible Runner 在目标服务器上执行操作，结果通过 Redis pub/sub 广播到 WebSocket。Celery worker 当前有意暂停（`backend/run.py:63`），前端 Tasks.vue 为占位页面。

### 2.11 WebSocket

| 方法 | 路径 | 后端入口 | 前端封装 | 说明 |
|---|---|---|---|---|
| WS | `/ws/{socket_id}` | `api/websocket.py:62` | 无 | Redis pub/sub 任务输出推送 |

## 3. 前后端契约不一致

| # | 模块 | 不一致点 | 影响 | 代码依据 |
|---|---|---|---|---|
| 1 | Auth | `deps.py:20` tokenUrl 声明为 `/api/rbac/login`，实际登录路由为 `/api/auth/login` | Swagger UI OAuth2 认证流程指向错误 URL | `backend/app/api/deps.py:20` |
| 2 | 日志 | `logs.ts` 路径缺少 `/list` 后缀（`/api/logs` vs `/api/logs/list`），且定义了不存在的 `GET /api/logs/{id}` | 调用 404 | `frontend/src/api/logs.ts:6-7` |
| 3 | 日志 | `logs.ts` 和 `logs.js` 同名导出 `logsApi`，存在覆盖风险 | 实际生效取决于打包器导入顺序 | `frontend/src/api/logs.ts` / `logs.js` |
| 4 | 服务器批量删除 | 前端 Servers.vue 逐条调用 `deleteServer(id)`，后端提供了 `POST batch-delete` 但未使用 | 批量删除需 N 次 HTTP 请求 | `frontend/src/views/Servers.vue` / `api/servers.py:204` |
| 5 | 账号操作 | 5 个后端接口已实现，前端无 API 封装和页面调用 | 功能不可用 | `api/account_ops.py` / `frontend/src/views/ops/Tasks.vue` |

## 4. 近期变更

### 2026-06-04：新增 AWX 资产校验最小闭环接口

新增后端接口：

1. `POST /api/v1/collector/runs`（JWT，主入口）
2. `POST /api/v1/automation/asset-verify/{instance_id}/launch`（JWT，兼容包装）
3. `GET /api/v1/collector/runs/{run_id}`（JWT）
4. `GET /api/v1/collector/instances/{instance_id}/runs`（JWT）
5. `POST /api/v1/collector/callback/`（`X-Collector-Token`，不走 JWT）

对应前端封装：

1. `assetsApi.launchAssetVerify`
2. `assetsApi.getCollectorRun`
3. `assetsApi.listInstanceCollectorRuns`

### 2026-06-06：AWX 资产校验升级为 run/item 底座

新增后端接口：

1. `POST /api/v1/collector/runs`
2. `GET /api/v1/collector/runs/{run_id}/items`
3. `GET /api/v1/collector/servers/{server_id}/runs`
4. `GET /api/v1/collector/endpoints`

callback 协议升级为 `items[]` 数组；旧 `/automation/asset-verify/{instance_id}/launch` 仍保留为兼容包装入口。

### 2026-06-08：Phase 3.1 端口画像与半自动端口校准

新增后端接口：

1. `GET /api/v1/collector/port-profiles`
2. `GET /api/v1/collector/assets/{target_scope}/{asset_id}/endpoints`
3. `GET /api/v1/collector/proposals`
4. `POST /api/v1/collector/proposals/{proposal_id}/approve`
5. `POST /api/v1/collector/proposals/{proposal_id}/reject`
6. `POST /api/v1/collector/proposals/{proposal_id}/apply`

`POST /api/v1/collector/runs` 新增 `run_type=port_calibration`：

- 后端按 `asset_endpoint / db_instance.port / server.extra_attrs / staging_excel_import / port_profile` 优先级自动展开候选端口 items。
- 可选 `options.include_related_server=true` 会把关联服务器管理端口一起纳入候选，并按 `host+port+protocol` 去重。
- callback `items[]` 透传并回写 `endpoint_type / protocol / port_source / is_required`。
- 对于校准候选失败，响应会通过 `candidate_state` 区分 `candidate_unreachable`，不会直接等同于资产 missing。
- 仅生成 proposal，不自动修改 `db_instance.port`；`apply` 且状态为 `approved` 时才更新正式资产字段。

### 2026-06-13：Phase 3.4 基础巡检中心

新增后端接口：

1. `GET /api/v1/inspection/items`
2. `POST /api/v1/inspection/items`
3. `PUT /api/v1/inspection/items/{item_id}`
4. `GET /api/v1/inspection/tasks`
5. `POST /api/v1/inspection/tasks`
6. `GET /api/v1/inspection/tasks/{task_id}`
7. `GET /api/v1/inspection/results`

契约扩展：

1. `POST /api/v1/collector/callback/` 在保留现有 `items[]` 协议基础上，新增可选 `inspection_results[]` 字段。
2. `run_type=inspection` 复用现有 BatchCollector/AWX 分发链路；后端按巡检项映射到已有 check_code 执行，不新增独立 callback URL。

## 5. 第三方对接

已新增 AWX 对接接口（第一阶段）：

1. DBOPS launch API 触发 AWX Job Template 执行
2. AWX 调用 DBOPS callback API 回写校验结果

`account_tasks.py` 中的 Celery + Ansible Runner 仍为内部运维执行通道，非对外接口。

## 6. 需现场确认

- `OAuth2PasswordBearer(tokenUrl="/api/rbac/login")` 是否为历史遗留？需改为 `/api/auth/login`。
- 账号操作（users/add, check, chpasswd）是否需要前端对接并启用 Celery worker？
- WebSocket 连接是否需要前端实现实时推送 UI？
- `logs.ts` vs `logs.js` 哪个是期望的封装？建议删除错误的 `logs.ts` 或修正路径并统一。
- AWX 配置项（`AWX_URL/AWX_USER/AWX_PASSWORD/AWX_VERIFY_JOB_TEMPLATE_ID/COLLECTOR_CALLBACK_*`）在目标环境是否已正确注入（需现场确认）？
