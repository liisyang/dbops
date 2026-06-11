# 交付看板

> 文档状态：已校准
> 最近校准：2026-06-11
> 依据来源：真实代码

## 1. 维护定位

本文件只记录当前交付判断和下一步行动。

已完成模块以 `docs/10-module-map.md` 为准。

## 2. 当前结论

基于真实代码分析，当前项目状态：

1. **核心资产管理层已完整实现**：服务器、实例、集群、业务系统、联系人、导入、统计的 CRUD 和前后端链路均已打通。
2. **认证体系已就绪**：JWT 登录 + 路由守卫 + 请求拦截器 + 401 处理完整闭环。
3. **旧 ops schema 代码已清理**：模型层统一为 dbops schema，配置统一为 pydantic-settings。
4. **异步运维框架已就绪但暂缓启用**：Celery + Redis + WebSocket 架构完整，当前阶段有意不启动 worker。
5. **AWX 资产校验已进入 Phase 3.1**：在原 run/item/callback 底座上新增 `port_profile`、`run_type=port_calibration`、端点候选探测、`asset_change_proposal` 审批/应用流程（仅人工 apply 后更新正式端口字段）；后续 refactor 已将候选收敛到 `host+port+protocol`，并支持 `include_related_server`。
6. **Phase 3.3A — DB 事实采集已完整交付并验证通过**：凭证中心（Profiles + Bindings）、CredentialResolverService、CheckItemBuilder、credential_group_hash 分发、AwxService 凭证注入、EE Collector Client、AWX Playbook 角色路由、Callback Fact Snapshots + Drift Detection、前端批量校验扩展均已实现。2 台 SQL Server 各采集 14 个 facts，端到端通过。
7. **扩展模块待排期**：备份恢复、SQL 分析、巡检健康、审计安全、知识库共多个前端页面，在 Phase 3.3A 收尾后统一排期。

## 3. 当前阻塞项

| 优先级 | 问题 | 影响 | 处理建议 | 依据 |
|---|---|---|---|---|
| P0 | SECRET_KEY 和数据库密码在代码中有硬编码默认值 | 部署到生产时存在安全风险 | 生产部署前通过环境变量覆盖 | `backend/app/config.py:10,14` |
| P0 | SSH_PASSWORD 未配置 | 无法通过密码方式 SSH 连接 | 确认是否仅使用密钥认证 | `.env` 中 SSH_PASSWORD 为空 |
| P1 | 16 个前端页面无后端支撑 | 用户点击后看到空页面 | 核心资产管理收尾后排期 | `frontend/src/router/index.ts` |

## 4. 部分完成事项

| 功能 | 已有代码 | 缺口 | 建议下一步 | 依据 |
|---|---|---|---|---|
| 异步账号操作 | API 层完整 + Celery task 定义 + WebSocket 推送 + TaskState Redis 存储 | Celery worker 有意暂缓启用 | 后续需要时恢复 `backend/run.py` 中 worker 启动代码 | `backend/run.py:63` |
| 审计日志 | 前端 3 个页面已就绪 | 后端返回空数组，无数据源 | 核心资产管理收尾后实现 | `backend/app/api/logs.py:15` |
| AWX 资产校验闭环 | `collector/runs` 主入口 + AWX service + collector service + 实例详情“校验资产/端口校准”入口已完成；callback URL 未显式配置时自动回退到当前请求基址 | Phase 3.1 已支持端口画像驱动候选探测、endpoint 元数据回写、proposal approve/reject/apply；候选失败会通过 `candidate_state` 区分，不会直接当成资产 missing；禁止自动修改正式资产字段 | 在开发库执行 `backend/db/dbops_port_profile_phase3_1.sql` 并联调 AWX callback | `backend/app/api/collector.py`, `backend/app/services/collector_service.py`, `backend/app/services/port_calibration_service.py`, `backend/app/services/asset_proposal_service.py`, `frontend/src/views/InstanceDetail.vue` |
| 巡检模块 | InspectionItem/Task/Result 表已定义 | 无 API，前端占位 | 核心资产管理收尾后排期 | `backend/app/models/dbops_assets.py:371-393` |
| 业务评分 | BizScoreRule/Result/Detail 表已定义 | 无 API，无前端页面 | 核心资产管理收尾后排期 | `backend/app/models/dbops_assets.py:395-416` |
| 凭证管理 | 前端占位页面 | 无 API，无模型 | 核心资产管理收尾后排期 | `frontend/src/views/credentials/*.vue` |

## 5. 下个迭代建议

| 顺序 | 任务 | 原因 | 验证方式 |
|---|---|---|---|
| ~~1~~ | ~~核心资产管理收尾~~ | ~~Phase 3.1 已完成~~ | ✅ |
| ~~2~~ | ~~AWX 闭环联调~~ | ~~callback 链路已就绪~~ | ✅ |
| ~~3~~ | ~~Phase 3.2: 批量资产校验中心 + 分网段 AWX 分发调度~~ | ~~已实现（后端 + 前端已完成）~~ | ✅ |
| ~~4~~ | ~~Phase 3.3A: DB 事实采集~~ | ~~全部 9 个 Phase + Batch 4 联调验证通过~~ | ✅ 2026-06-11 |
| 5 | Phase 10: 单元测试补全 | Phase 3.3A 测试未做，需补 CredentialResolverService、CheckItemBuilder、AwxService 凭证注入、Callback Fact Snapshot、Drift Detection 的 pytest | `cd backend && pytest tests/` |
| 6 | AWX 多网段执行节点扩展 | 当前只有 IG_LOCAL_LH_TEST 一个 instance group，生产需按网段分组分发 | 需现场确认各网段执行节点 IP 和 SSH 免密配置 |
| 7 | Phase 3.3B: Oracle / PostgreSQL / MySQL 事实采集联调 | MSSQL 已通；其他 connector 已实现但未联调 | 对各 DB 类型触发 batch run 并验证 14+ facts |

## 6. Phase 3.2 交付物

- ✅ `collector_batch_run` / `collector_dispatch_run` 表（可重复执行 DDL）
- ✅ `BatchCollectorService` — 批量编排（禁止 check_code 分支，走 Registry）
- ✅ `DispatchPlannerService` — 按 awx_instance_group 分组（不依赖 site.extra_attrs）
- ✅ `CheckItemBuilderRegistry` — check_code → builder 注册表
- ✅ `CollectorService.handle_callback()` — 统一事务边界，刷新 batch/dispatch 统计
- ✅ 6 个 batch API 端点（create/list/get/dispatches/items/retry-failed）
- ✅ `BatchVerify.vue` — 前端批量校验页面（`/ops/batch-verify`）
- ✅ 18 个后端测试全部通过，62 个总测试（含回归）全部通过

## 7. Phase 3.3A 交付物（2026-06-11 验证通过）

- ✅ `collector_credential_profile` / `collector_credential_binding` 表（凭证中心 DB 模型）
- ✅ `CredentialResolverService` — 按 asset_id + check_code 解析凭证，构建 AWX extra_vars 注入
- ✅ `CheckItemBuilderRegistry` 4 个 fact builder — DB_BASIC_FACT_COLLECTION / DB_VERSION_FACT_COLLECTION / DB_ROLE_FACT_COLLECTION / OS_BASIC_FACT_COLLECTION
- ✅ `DispatchPlannerService` credential_group_hash 分组 — 同凭证的 item 聚合到同一 dispatch，减少 AWX job 数
- ✅ `AwxService.launch_job_with_credentials()` — 凭证作为 extra_vars 注入 AWX job，不写入 AWX credential 对象
- ✅ `ExecutionNodeCollectorClient` — 执行节点 collector_client CLI 封装
- ✅ AWX Playbook 角色路由 (`dbops_collector_generic.yml`) — 按 `check_code` 前缀路由到 `db_fact_collect` / `os_fact_collect` role，`port_check` 跳过
- ✅ `FactSnapshotService` + `DriftDetectionService` — callback 写入 fact_snapshot，与上次快照比对生成 drift_event
- ✅ 前端扩展：`credentials/Profiles.vue` + `credentials/Bindings.vue` + `BatchVerify.vue` 支持 fact_collection run_type
- ✅ `backend/db/dbops_phase3_3a.sql` — Phase 3.3A DDL（fact_snapshot、drift_event、credential 相关表）
- ✅ Batch 4 端到端验证：2 台 SQLSERVER 各采集 14 个 facts，AWX Job 245 successful，batch_run 80 status=success

**关键修复（Batch 4 联调中发现）：**
- `LD_LIBRARY_PATH: /usr/lib64:/opt/microsoft/msodbcsql18/lib64` — Ansible command 任务不继承容器环境，需显式传入 ODBC 库路径（`ansible-playbooks/playbooks/roles/db_fact_collect/tasks/main.yml`）
- `TrustServerCertificate=yes` — ODBC Driver 18 默认强制 SSL 验证，内网自签名证书需跳过（`files/collector_client/db_connectors/mssql.py`）
- `argv:` 替代 `cmd:` — 避免 JSON 中特殊字符破坏 shell 参数解析
- `AWX_PREBOUND_CREDENTIAL_IDS` 会与事实采集凭证合并，即使某个 dispatch 没有事实凭证也会保留预绑定 credential IDs，避免 AWX launch 校验失败

## 8. 需现场确认

- AWX 多网段执行节点扩展：各网段节点 IP + SSH 免密 + AWX Instance Group 配置（当前仅 IG_LOCAL_LH_TEST）
- Phase 3.3B：Oracle / PostgreSQL / MySQL 采集联调，需对应 DB 实例访问凭证
- Phase 10 测试优先级：是否在开发下个功能前补全 Phase 3.3A 测试
- 生产环境部署前 SECRET_KEY / POSTGRES_PASSWORD 须通过环境变量覆盖
