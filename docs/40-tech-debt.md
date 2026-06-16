# 技术债 Backlog

> 文档状态：已校准
> 最近校准：2026-05-22
> 依据来源：真实代码

## 1. 维护定位

本文件只记录真实代码中能确认的技术债。

不记录个人偏好。

## 2. 总览

| 等级 | 数量 | 说明 |
|---|---:|---|
| High | 0 | 已全部修复（2026-06-16 批 0/1/2 收尾） |
| Medium | 10 | 重复实现、不一致、性能隐患（4 项已修复） |
| Low | 6 | 清理项、渐进优化（2 项已修复：timezone.js 删、L6） |

> 最近校准：2026-06-16 10:30 — PR 评审 19 项修复（批 0/1/2/3）全部完成：advisory lock (C1) + cancel_batch_run 终态集合补 callback_failed (C2) + 锁粒度 (C3) + BATCH_TERMINAL_STATUSES 常量 (C4) + now_local() 时区一致性 (C5) + cancelled_at 取消信号 (C6) + 前端 dayjs.tz (C8) + N1/N2/N3 业务正确性 + I1 LaunchOutcome 桶分 + I3 AssetFactSnapshot UNIQUE + 测试 mock 修复（_FakeCancelDB）；后端重启 PID 3809407 + celery beat/worker 新进程 + batch 133/134 验证 dispatch.finished_at 不被 cancel 覆盖、cancelled_at 正确设置、awx_cancel_failed=0

## 3. 技术债清单

### 3.1 High

| # | 问题 | 位置 | 影响范围 | 风险等级 | 建议处理 | 状态 | 代码依据 |
|---:|---|---|---|---|---|---|---|
| H1 | `batch_delete_servers` 调用不存在的 `ServerService` | `backend/app/api/servers.py:214` | 批量删除服务器功能 | High | 将 `ServerService.delete_server(db=db, server_id=sid)` 改为 `DbopsAssetService.delete_server(db=db, server_id=int(sid))` | ✅ 已修复 | `grep -rn "ServerService" backend/` 仅匹配 `servers.py:214`，无定义/导入；实际服务类是 `DbopsAssetService`（`servers.py:12`） |
| H2 | `OAuth2PasswordBearer` tokenUrl 指向错误路径 | `backend/app/api/deps.py:20` | Swagger UI OAuth2 认证流程 | High | 将 `tokenUrl="/api/rbac/login"` 改为 `tokenUrl="/api/auth/login"` | ✅ 已修复 | `deps.py:20`: `OAuth2PasswordBearer(tokenUrl="/api/rbac/login")`；实际登录路由在 `auth.py:24`: `POST /api/auth/login` |
| H3 | `staging_excel_import` 存储明文密码 | `backend/app/models/dbops_assets.py:478-482` / `backend/app/services/dbops_import_service.py:451,591` | 所有导入操作的 Excel 原始数据 | High | 导入执行时在写入暂存表前清除 `db_password_raw`/`os_password_raw`/`os_oracle_password_raw` 字段 | ✅ 已修复 | `dbops_assets.py:478`: `db_password_raw = Column(Text)`；import_service 将 Excel 密码列直接写入暂存表 |
| H4 | 配置文件中硬编码默认数据库凭证 | `backend/app/config.py:10-15` | 若 .env 缺失则暴露开发环境凭证 | High | SECRET_KEY/POSTGRES_PASSWORD 默认值改为空字符串，启动时检查必需配置 | ✅ 已修复 | `config.py:10`: `SECRET_KEY: str = "dev-secret-key-change-in-production"`；`config.py:14`: `POSTGRES_PASSWORD: str = "root123"` |
| H5 | `collector_dispatch_run`/`collector_batch_run` status check constraint 缺 `timeout`/`callback_failed` | DB DDL: `chk_collector_dispatch_run_status` / `chk_collector_batch_run_status` | timeout_recovery_task 每分钟被 `IntegrityError` 阻断，孤儿 dispatch/run 永久卡 `launched`，batch 永远无法收敛 | High | ALTER TABLE 同时补齐 `timeout` + `callback_failed`；同步修复 `refresh_batch_status` 终态集合 | ✅ 已修复 | `collector_tasks.py:319` 写 `dispatch.status = "timeout"`；worker 日志持续 `IntegrityError('chk_collector_dispatch_run_status')` 155 次；`batch_collector_service.py:624-632` 终态判断缺 `timeout` 导致 batch 永远 `running` |
| H6 | 全 skipped batch 被标 `failed` | `backend/app/services/batch_collector_service.py:282` | 创建 batch 时若所有 item 都是 skipped（无凭证），batch 进 `failed` 而非 `partial_success`，导致误报失败 | High | 当 `not dispatchable_items` 且 `credential_skipped_items` 非空时改为 `partial_success` | ✅ 已修复 | `batch_collector_service.py:282`: `batch_run.status = "failed"`；对比 `collector_service.py:1285` 的 `_summarize_run_status` 已正确处理 all-skipped → partial_success |

### 3.2 Medium

| # | 问题 | 位置 | 影响范围 | 风险等级 | 建议处理 | 状态 | 代码依据 |
|---:|---|---|---|---|---|---|---|
| M1 | `get_db()` 函数重复定义 | `backend/app/database.py:26-31` / `backend/app/api/deps.py:25-31` | 维护混淆，两个函数实现完全一致 | Medium | 删除 `database.py` 中的 `get_db()`，统一使用 `deps.py` 的版本 | 待处理 | 两个文件各有完全相同的 `get_db()` 实现 |
| M2 | `auth.py` 绕过依赖注入直接创建 SessionLocal | `backend/app/api/auth.py:27` | 与其他所有 API handler 的 `db: Session = Depends(get_db)` 模式不一致 | Medium | 改为 `db: Session = Depends(get_db)` | 待处理 | `auth.py:27`: `db = SessionLocal()`；对比 `servers.py:88`: `db: Session = Depends(get_db)` |
| M3 | `create_server`/`update_server` 接受裸 `dict` 而非 Pydantic 模型 | `backend/app/api/servers.py:166-188` | 绕过 FastAPI 自动验证和 OpenAPI schema 生成 | Medium | 定义 `ServerUpsertRequest(BaseModel)` 替代 `data: dict`，与其他端点保持一致 | 待处理 | `servers.py:166`: `data: dict`；对比 `servers.py:54-63`: `ClusterUpsertRequest(BaseModel)` |
| M4 | 前端 `logs.ts` 路径错误 + 与 `logs.js` 同名导出冲突 | `frontend/src/api/logs.ts:6-7` / `frontend/src/api/logs.js:4` | `GET /api/logs` 和 `GET /api/logs/{id}` 后端不存在（正确路径为 `/api/logs/list`） | Medium | 删除 `logs.ts`（路径错误且无页面调用），保留 `logs.js` | 待处理 | `logs.ts:6`: `request.get('/logs')`；后端 `logs.py:11`: `@router.get("/list")` → `GET /api/logs/list` |
| M5 | 前端分页为全量加载后内存切片 | `frontend/src/composables/usePagedAssetList.ts:17-23` | 数据量增长后每次页面加载需 N 次 HTTP 请求 | Medium | 后端列表接口增加服务端分页支持（当前已返回 total/page/page_size），前端改为按需加载当前页 | 待处理 | `usePagedAssetList.ts:17-23`: 循环 `for (let page = 2; page <= totalPages; page++)` 拉取所有页 |
| M6 | 状态展示函数重复实现 | `frontend/src/views/Assets.vue:444-477` / `frontend/src/views/BusinessSystemDetail.vue:635-672` | `formatStatusLabel()` 和 `statusBadgeClass()` 在两个视图各自实现 | Medium | 抽取到 `src/composables/useStatusBadge.ts` 或公共组件，同时与 i18n 集成 | 待处理 | 两处有几乎相同的 status→label 映射和 status→css class 映射 |
| M7 | 删除确认使用原生 `window.confirm` | 5 个视图（Servers/Clusters/BusinessSystemDetail/Instances/Contacts） | 体验不一致，无法定制样式 | Medium | 统一为 OpsModal 确认弹窗 | 待处理 | `Servers.vue:698`, `Clusters.vue:393`, `BusinessSystemDetail.vue:571`, `Instances.vue:371`, `Contacts.vue:295` |
| M8 | `/api/logs/list` 硬编码返回空数组 | `backend/app/api/logs.py:14-15` | 操作日志页面永远无数据 | Medium | 核心资产管理收尾后实现审计日志模块 | 待实现 | `logs.py:15`: `return []`；TODO 注释确认后续实现 |
| M9 | `resource_tag.resource_id` 无外键约束 | DDL: `dbops_phase1_25_tables.sql` / ORM: `dbops_assets.py:341-355` | `resource_id` 可能指向不存在的资源（多态关联设计） | Medium | 后续可加应用层校验或定期清理孤儿记录 | 待处理 | DDL 未对 `resource_id` 建 FK，由 `resource_type` 决定引用目标表 |
| M10 | `list_servers` 引用不存在的 `server.dns_name` | `backend/app/services/dbops_asset_service.py:409` | 服务器列表接口运行时 `AttributeError` | Medium | 从 `list_servers` 返回 dict 中移除 `dns_name` 字段 | ✅ 已修复 | `dbops_asset_service.py:409`: `"dns_name": server.dns_name`；`Server` 模型 (`dbops_assets.py:213-236`) 无 `dns_name` 列；测试 `test_list_servers_returns_business_group_and_room_location` 因此失败 |
| M11 | 缺少“端口+路由”一键自检，易在共享环境误判服务状态 | 运维流程（非单文件） | 进程存在但路由未加载、或端口被旧实例占用时，前端出现 Not Found/不可访问 | Medium | 增加自检脚本：检查 60801/61088 监听、`/openapi.json` 包含 collector 路径、collector 路由未鉴权返回 401 | 待处理 | 本次故障：collector 接口 404 + 前端端口无监听，需手工多步排查 |
| M12 | 共享后端进程可能滞后于仓库源码，导致 collector 新路由不可用 | 运维流程（非单文件） | 60801 上的后端仍是旧进程时，`POST /api/v1/collector/runs` 会直接 404 | Medium | 启动前先用 `/openapi.json` 核对 collector 路由；必要时重启后端到当前代码 | 已记录 | 本次 961 资产测试：旧 60801 进程缺少新 collector 主入口，重启后才恢复 |
| M13 | AWX 项目 role 目录必须放在 playbooks/roles 下，否则 `include_role` 找不到 role | AWX 内容仓库布局 | `playbooks/dbops_collector_generic.yml` 执行时找不到 `port_check` role | Medium | 将执行 role 放到 `playbooks/roles/<role>/tasks/main.yml`，或改成显式 tasks include | 已记录 | 本次 AWX job 31 失败原因：role 放在仓库根 `roles/` 下，AWX 实际搜索路径未包含它 |
| H7 | Callback 创建 `CollectorRunResult` 时未设置 `status` 字段导致 `NotNullViolation` | `backend/app/services/collector_service.py:995-1007` | AWX playbook 回调 DBOPS 返回 500，`no_log:true` 掩盖错误；最终 dispatch/run 被 timeout_recovery 标记为 timeout（但实际 AWX 执行成功） | High | 在 `CollectorRunResult` 构造器中提前设置 `status` 字段，避免 `db.flush()` 时触发 NOT NULL 约束 | ✅ 已修复 | 2026-06-15 Job 301 回调 4 次全部 500；日志 `NotNullViolation: null value in column "status" of relation "collector_run_result"`；修复后新 batch 回调正常 |
| H8 | `refresh_batch_status()` 进入终态时未回写 `finished_at` | `backend/app/services/batch_collector_service.py:604-671` | 批次已收敛到 `success`/`partial_success`/`failed` 等终态，但 `finished_at` 仍为 NULL；前端无法展示真实耗时（仅显示 `created_at`）；统计/对账/巡检等下游也无法按完成时间查询 | High | 在 `refresh_batch_status()` 中先保存 `old_status`，仅当 `old_status not in terminal_statuses and batch_run.finished_at is None` 时回写 `_now()`；避免后续 refresh 覆盖真实结束时间 | ✅ 已修复 | `batch_collector_service.py:604-671`：原实现仅设置 `status`，未写 `finished_at`；典型样本：BATCH-20260615163427-55EB9D（3 个实例）已完成但 `finished_at=NULL`；历史孤儿 batch ID 126 `status=running` + `finished_at=15:43:02` 已通过 P0 SQL 修正为 `partial_success` |
| M14 | `collector_run.started_at` 与 `datetime.utcnow()` 比较时区不一致（三轮修复） | `backend/app/tasks/collector_tasks.py:269-284` / `backend/app/models/dbops_assets.py` 全部 `default=datetime.utcnow` / `backend/app/services/collector_service.py:_now()` | **原问题**: ORM `default=datetime.utcnow` 写入 UTC，但 timeout_recovery 用 Python `datetime.utcnow()` 比较（也是 UTC），而 DB 写入的是 CST wall clock → offset 8h → `considered:0`。**M14 v1 修复** (2026-06-15 15:10): 查询改 `func.now() - interval`（CST），但写入仍是 UTC → 8h offset 反向 → 所有 run 在 1min 内被 timeout。**M14 v2 完整修复** (2026-06-15 15:42): 写入端全部改为 `datetime.now()`（CST）→ 模型 `default=datetime.now`（67 处）+ `_now()` 改为 `datetime.now()` + `collector_tasks.py` 所有 `datetime.utcnow()`→`datetime.now()`；查询端用 `func.now() - interval`（CST）；双端对齐后 timeout_recovery 正确。**M14 v3 修复** (2026-06-16 08:39): M14 v2 漏改了 `BatchCollectorService._now()`（HEAD 17b2694 `:34-35` 仍是 `datetime.utcnow()`），导致 `batch_run.started_at` / `dispatch_run.finished_at` 通过该函数被错写为 UTC（`launched_at` 走 `datetime.now()` 所以正常 → `finished_at - launched_at` 算出负数）；本轮已改 `_now()` 返回 `datetime.now()`，重启后端（PID 3519591 启动于 08:39:06 CST），BATCH-20260616084009-346144 (id 131) 验证：`started_at=08:40:09` + `finished_at=08:40:37` 全 CST，dur=28.2s 正常 | High→✅ 已修复 | v1 验证: CST 时刻 `started_at` 命中 `considered:1,recovered:1`（正则验通过）；v1 回归: Job 301 `started_at` UTC 07:12 vs `func.now()` CST 15:14 → `07:12<14:44` → 1.5min 内触发 timeout（确认 v1 有缺陷）；v2 验证: Batch 126 `created_at=15:42:36 CST` 与 `updated_at=15:42:36 CST` 一致（✅）；v3 验证: Batch 131 `started_at=08:40:09 CST` + `finished_at=08:40:37 CST` + dur=28.2s（✅），历史 batch 130 (`started_at=00:30:01` UTC 错 → 回填为 `08:30:01 CST`) + batch 128/129 `finished_at=NULL` 已通过 SQL 回填 |

### 3.3 Low

| # | 问题 | 位置 | 影响范围 | 风险等级 | 建议处理 | 状态 | 代码依据 |
|---:|---|---|---|---|---|---|---|
| L1 | `lucide-vue-next` 已安装但未使用 | `frontend/package.json:14` | 增加包体积 | Low | 确认是否需要，不需要则 `npm uninstall lucide-vue-next` | 待处理 | 全局搜索源码无 `lucide` 引用 |
| L2 | `.js`/`.ts` 同名文件并存（4 对） | `main.js/ts`, `stores/user.js/ts`, `utils/i18n.js/ts`, `utils/weather.js/ts` | TypeScript 项目中的 `.js` 文件不受类型检查 | Low | 确认 `.ts` 版本是否为实际入口，移除冗余 `.js` 文件 | 部分修复 | 已删 `utils/timezone.js`（与 `.ts` 冲突导致 build 失败，批 1 A1）；其余 4 对待处理 |
| L3 | CRUD 交互模式不一致 | `Servers.vue`（路由切换） vs `Instances.vue`/`Assets.vue`（OpsModal 弹窗） | 用户心智模型不一致 | Low | 统一为一种模式 | 待确认 | `Servers.vue`: 路由 `/assets/servers/create` 和 `/assets/servers/:id`；`Instances.vue:53-133`: OpsModal |
| L4 | WebSocket 端点无认证 | `backend/app/api/websocket.py:62-75` | 任何知道 socket_id 的人可连接 WebSocket | Low | 添加 token 验证（查询参数或首条消息） | 待处理 | `websocket.py:62`: `@router.websocket("/{socket_id}")` 无 `Depends(get_current_user)` |
| L5 | 国际化覆盖率低 | 各视图模板 | 切换语言后大量中文硬编码不变 | Low | 逐步迁移硬编码文案到 i18n | 待处理 | 各 `.vue` 文件中的中文按钮、标签、提示文案 |
| L6 | AWX Job Template `allow_simultaneous=False` 阻塞批量分发并发 | AWX Job Template `JT_DBOPS_COLLECTOR_GENERIC_TEST` (id=10) | 同一 Job Template 下的 AWX Job 串行执行；批量任务 N 个 dispatch 必须等前一个 Job 完成才能启动后续 Job，1000+ 实例场景排队严重 | Low | 通过 AWX API PATCH `allow_simultaneous=true`；DBOPS 侧 `COLLECTOR_IG_MAX_RUNNING_DISPATCHES` 与 IG `max_concurrent_jobs` 兜底限流 | ✅ 已修复 | 样本：BATCH-20260615163427-55EB9D（2 个 dispatch）总耗时 160s 串行 vs ~102s 并行；2026-06-16 已 PATCH `allow_simultaneous=true`（AWX Instance Group `max_concurrent_jobs=0`/`max_forks=0` 表示无限制） |

## 4. 暂不处理项

| # | 问题 | 暂不处理原因 | 重新评估条件 |
|---:|---|---|---|
| ~~D1~~ | ~~Celery worker 未启用（`backend/run.py:63`）~~ | ~~有意暂缓，当前阶段不需要异步任务执行~~ | ✅ 已解决：P0-0 阶段以 systemd 部署 `dbops-celery-worker.service` + `dbops-celery-beat.service`，连独立 Redis `10.134.185.85:6379`；P0-4/P0-5 注册 `dispatch-scheduler` (15s) + `timeout-recovery` (60s) 两个 beat 任务；详见 `/etc/systemd/system/dbops-celery-{worker,beat}.service` |
| D2 | 审计/备份/SQL/巡检/凭证/知识库模块无后端 API | 当前阶段聚焦核心资产管理，规划中模块排期在后 | 核心资产管理收尾后 |
| D3 | 前端仅有暗色模式（`tailwind.config.js` 只定义一套颜色 Token） | 亮色模式非当前阶段需求 | 用户明确要求亮色模式时 |
| D4 | 历史迁移脚本源码缺失（`backend/db/__pycache__/*.pyc` 存在但 `.py` 已删除） | 历史迁移已生效，回溯源码意义有限 | 需要重跑历史迁移或审计迁移历史时 |

## 5. 需现场确认

- H4 硬编码凭证：当前 `.env` 文件是否存在并覆盖了默认值？
- L2 `.js`/`.ts` 双文件：4 对待处理（已删 timezone.js → 2026-06-16 批 1 A1）
- L3 CRUD 交互模式：倾向于统一为弹窗模式还是路由模式？
- L1 `lucide-vue-next`：是否有计划使用？还是可以直接移除？
- M9 `resource_tag`：多态关联是否需要应用层定期校验/清理？

---

## 6. PR 评审 backlog（batch 校验 1000+ 性能优化 diff）

> 评审日期：2026-06-16
> 评审范围：working tree 17 文件 / 754+/-124 diff（6 阶段 refactor + M14 v3 + AWX 并发）
> 评审视角：code-reviewer / silent-failure-hunter / typescript-reviewer / simplify
> 发现：**8 Critical + 10 Important + 9 Advisory**
> 落地：批 0/1/2/3 全部完成（19/19 闭环）— 详见 `/home/lisiyang/.claude/plans/critical-fixes-pr-review-2026-06-16.md`

### 6.1 已闭环（按编号归档，便于追溯）

| 编号 | 类别 | 描述 | 落点 | 闭环 |
|---|---|---|---|---|
| C1 | Critical | 多 Celery worker 配额原子性 | `collector_tasks.py:230-232` advisory lock key=0x434F4C4C | ✅ 批 2 |
| C2 | Critical | `cancel_batch_run` 终态集合缺 `callback_failed` | `BATCH_TERMINAL_STATUSES` 常量（`backend/app/constants.py`） | ✅ 批 1 |
| C3 | Critical | `cancel_batch_run` 锁粒度 + AWX HTTP 在事务里 | per-row `with_for_update(skip_locked=True)` + per-row commit | ✅ 批 2 |
| C4 | Critical | 终态集合三处分裂 | `app/constants.py` 抽 `BATCH_TERMINAL_STATUSES` / `RUN_TERMINAL_STATUSES` / `RUNNING_DISPATCH_STATUSES` / `AWX_TERMINAL_STATUSES` | ✅ 批 1 |
| C5 | Critical | `inspection_service._now()` 仍用 `datetime.utcnow()` | `app/utils/datetime.py` 抽 `now_local()` + 7 处 service 切换 | ✅ 批 1 |
| C6 | Critical | cancel 覆盖 `dispatch.finished_at` | DB 加 `cancelled_at` 列 + cancel 路径用 `cancelled_at` 而非 `finished_at` | ✅ 批 2 |
| C7 | Critical | 时区/TZ 三层不一致 | **推迟**（单区域跑无问题，跨区域部署时再开 sprint） | ⏸ 暂缓 |
| C8 | Critical | 前端 `formatDuration` 不走 dayjs.tz | `utils/timezone.ts` 暴露 `formatDuration()`，BatchVerify.vue 删本地 80 行实现 | ✅ 批 1 |
| N1 | Critical | `_summarize_run_status` 在部分 item 终态就聚合 | 全 item 终态才聚合 | ✅ 批 1 |
| N2 | Critical | timeout_recovery 覆盖已终态 dispatch | 检查 `status` 不在 `BATCH_TERMINAL_STATUSES` 才更新 | ✅ 批 0 |
| N3 | Critical | skipped item 仍写 result 行 | skipped 路径直接 `continue` | ✅ 批 0 |
| I1 | Important | scheduler summary 桶分不清 | `LaunchOutcome` enum（LAUNCHED / DATA_ERROR / AWX_ERROR / UNKNOWN_ERROR）+ summary 输出 `launched` / `skipped_data_error` / `skipped_awx_error` | ✅ 批 2 |
| I3 | Important | `AssetFactSnapshot` 缺 UNIQUE（callback 双写 TOCTOU） | `UniqueConstraint("source_run_id", "source_item_key")` + DB 迁移镜像 | ✅ 批 2 |
| I5 | Important | `error_message` 拼接两遍 | `_append_error` helper 抽 | ✅ 批 2 |
| I6 | Important | run/dispatch 同改 `finished_at` 模板 4 处 | `cancelled_at` 替代（已包含在 C6 修复） | ✅ 批 2 |
| I7 | Important | `refresh_batch_status` 内 set 展开字面量 | 改 `BATCH_TERMINAL_STATUSES`（已包含在 C4 修复） | ✅ 批 1 |
| A1 | Advisory | 删 `frontend/src/utils/timezone.js`（与 .ts 冲突导致 build 失败） | `rm` 完成 | ✅ 批 1 |

### 6.2 后续 sprint 处理（pending）

| 编号 | 类别 | 描述 | 建议处理 | 建议时机 |
|---|---|---|---|---|
| I2 | Important | 轮询 tick 触发 N+1 proposal 请求 | 加 `fromPoll=true` 标志位，tick 路径跳过 proposal 列表 | 性能优化 sprint |
| I3' | Important | 切换批次 items 闪烁 | `loadBatchDetail` 入口清空 items（避免前次渲染残留） | UX polish |
| I4 | Important | `create_batch_run` 不主动触发 beat | beat 容器化部署后由 cron/容器自动恢复；当前 15s tick 延迟可接受 | 鲁棒性 sprint（容器化） |
| I8 | Important | `launching` 状态被 worker crash 卡住 | timeout_recovery 任务范围扩展（把 `launching` 也纳入超时恢复） | 性能优化 sprint |
| I9 | Important | 切 tab 后轮询风暴 | `visibilitychange` 事件 + 切回才恢复轮询 | 前端 UX polish |
| I10 | Important | 拼写 `canceled`/`cancelled` 不规则 | `docs/30-runbook.md` 明确化（统一为 `cancelled`） | 文档 polish |
| A2 | Advisory | `BatchVerify.vue` 内联 `dayjs` 调用可抽 composable | 抽 `useBatchVerifyTimer()` 或类似 | 下个 refactor |
| A3 | Advisory | `formatDuration` 在 `timezone.ts` 但仍可挪到 `composables/useDuration.ts` | 视 A2 走向 | 下个 refactor |
| A4 | Advisory | `refresh_batch_status` 与 `cancel_batch_run` 重复写 finished_at/cancelled_at 模板 | 抽 `_write_terminal_state(batch_run, status, *, error_message=None)` | 下个 refactor |
| A5 | Advisory | `summarize_run_status` 字符串拼接可改 dict-based | 抽 `_RUN_STATUS_PRIORITY` 常量 | 下个 refactor |
| A6 | Advisory | `cancel_batch_run` 多处 `db.commit()`，可在异常路径加 `db.rollback()` 保险 | 用 context manager 统一事务 | 下个 refactor |
| A7 | Advisory | `BatchCollectorService` 越来越大（>700 行） | 按职责拆 `BatchRunService` / `DispatchService` / `RunSummaryService` | 下个 refactor |
| A8 | Advisory | `tests/test_collector_tasks_p0_4_5_6.py` mock 重写后可参数化 | 抽 `pytest.mark.parametrize` 模板 | 测试清理 |
| A9 | Advisory | `cancelled_at` 列名在 schema-snapshot 也需补 | `docs/db/schema-snapshot.md` 更新 | 文档同步 sprint |

### 6.3 PR 评审闭环验证

| 类别 | 验证方式 | 实际结果 |
|---|---|---|
| 全套 | `bash scripts/ai/verify.sh` | 111 passed, 0 failed ✅ |
| 前端 | `npm run build` | BatchVerify 27.64 kB / 7.56 kB gzip ✅ |
| DB 迁移 | 测试库 `10.134.185.85:5432/dbops` | `cancelled_at` 列 + `uq_asset_fact_snapshot_source` 已存在 ✅ |
| C6 修复 | 直接查 `collector_dispatch_run`（id 138/139/140） | `finished_at=NULL, cancelled_at=SET`（cancel 不覆盖）✅ |
| C1 修复 | celery beat 日志 `dispatch_scheduler_tick` | `{'considered': 2, 'launched': 2, 'skipped_cap': 0, 'skipped_error': 0}` ✅ |
| 批 3 后端 | PID 3809407 + 3809406 + 3809405 | batch 133/134 happy path + cancel 全通过 ✅ |
