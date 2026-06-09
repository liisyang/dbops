# 交付看板

> 文档状态：已校准
> 最近校准：2026-05-21
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
6. **扩展模块待排期**：备份恢复、SQL 分析、巡检健康、审计安全、凭证中心、知识库共 16 个前端页面，在核心资产管理收尾后统一排期。

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
| 3 | Phase 3.2: 批量资产校验中心 + 分网段 AWX 分发调度 | 已实现（后端 + 前端已完成，需 AWX 联调验收） | `POST /api/v1/collector/batch-runs` + BatchVerify.vue |
| 4 | Phase 3.3: 只读资产事实采集 | 批量底座就绪后接入采集能力 | 通过 BatchCollectorService 下发 |
| 5 | AWX 多网段联调验收 | 验证 IG_NET_A/B/C 分发正确性 | 需现场确认 |

## 6. Phase 3.2 交付物

- ✅ `collector_batch_run` / `collector_dispatch_run` 表（可重复执行 DDL）
- ✅ `BatchCollectorService` — 批量编排（禁止 check_code 分支，走 Registry）
- ✅ `DispatchPlannerService` — 按 awx_instance_group 分组（不依赖 site.extra_attrs）
- ✅ `CheckItemBuilderRegistry` — check_code → builder 注册表
- ✅ `CollectorService.handle_callback()` — 统一事务边界，刷新 batch/dispatch 统计
- ✅ 6 个 batch API 端点（create/list/get/dispatches/items/retry-failed）
- ✅ `BatchVerify.vue` — 前端批量校验页面（`/ops/batch-verify`）
- ✅ 18 个后端测试全部通过，62 个总测试（含回归）全部通过

## 7. 需现场确认

- AWX playbook `port_check` role metadata 透传修复（endpoint_type/protocol/port_source/is_required）
- AWX 多 Instance Group 联调（IG_NET_A/B/C）
- SSH 认证方式确认：仅密钥 or 需要密码认证？
- 生产环境 Redis 地址（当前默认 localhost:6379）？
- AWX Pod 到回调地址的网络连通性与回调 token 一致性（需现场确认）？
