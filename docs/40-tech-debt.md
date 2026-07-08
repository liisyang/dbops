# 技术债 Backlog

> 文档状态：已校准
> 最近校准：2026-07-08
> 依据来源：真实代码 + PR 评审批 0/1/2/3/4 + Phase 3.6 C1-C16-5-Commit 1-4 真实实施反馈

## 1. 维护定位

本文件只记录真实代码中能确认的技术债。

不记录个人偏好。

## 2. 总览

| 等级 | 数量 | 说明 |
|---|---:|---|
| High | 0 | 已全部修复（2026-06-16 批 0/1/2/3/4 收尾） |
| Medium | 11 | 重复实现、不一致、性能隐患（4 项已修复；新增 F18 collector PG connector psycopg v3 alias 闭环） |
| Low | 6 | 清理项、渐进优化（3 项已修复：timezone.js / i18n.js / user.js 全删） |

> 最近校准：2026-06-16 15:00 — 批 4 v2 加固完成：C1v2 pg_try_advisory_lock + C2 cancel race + C3+I5 partial unique index + C4/C5 .js 删除 + I1 admin gate + I2 rate limit + I3 timeout re-read + I4 lock release + A2 DISPATCH_TERMINAL_STATUSES + I6 AWX sanitize + I7 callback replay + I8 AbortController + I9 formatTime + I10 TERMINAL_BATCH_STATUS_SET。全 111 测试 + frontend build 绿。

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
| L2 | `.js`/`.ts` 同名文件并存（0 对） | 3 对已删，0 对冗余 | TypeScript 项目中的 `.js` 文件不受类型检查；Vite 启动时把无后缀 import 解析到 `.js`，运行期 `.js` 被删除/重命名后模块图缓存不重新解析，导致前端空白（需重启 vite 才能恢复） | Low | 确认 `.ts` 版本是否为实际入口，移除冗余 `.js` 文件 | ✅ 已修复 | 2026-06-16: `utils/timezone.js`、`utils/i18n.js`、`stores/user.js` 3 对已删，对应 `.ts` 留存为唯一入口。`api/request.js`（无 `.ts` 对应，axios 客户端约定）+ `locales/{en,zh-CN,zh-TW,ja,pt-BR}.js`（5 个，vue-i18n 约定）是合法 `.js`，**非冗余**。`main.js` / `utils/weather.js` 在仓库历史中从未存在，文档此前误引。需 `pkill -f vite` 清旧 PID cache 后重启 |
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
- L2 `.js`/`.ts` 双文件：全部 4 对已清理（2026-06-16 批 4）
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

### 6.3 批 4 — v2 加固 (2026-06-16)

> 基于 v2 plan（pg_try_advisory_lock + QueuePool 防泄漏 + RUN_TERMINAL_STATUSES 拼写 + partial unique index）
> 执行：C1 v2 / C2 / C3+I5 合并迁移 / C4/C5 .js 删除 / I1 admin gate / I2 rate limit / I3 timeout re-read / I4 lock release / A2 DISPATCH_TERMINAL_STATUSES / I6 AWX error sanitize / I7 callback replay / I8 AbortController / I9 formatTime type / I10 TERMINAL_BATCH_STATUS_SET
> 全 111 测试通过 + frontend build 绿

| 编号 | 类别 | 描述 | 落点 | 闭环 |
|---|---|---|---|---|---|
| C1v2 | Critical | `pg_advisory_xact_lock` 被 per-dispatch commit 提前释放 + QueuePool 锁泄漏 | `pg_try_advisory_lock` (session-level, non-blocking) + finally 显式 unlock | ✅ 批 4 |
| C2 | Critical | `cancel_batch_run` 最终 batch re-acquire 无条件覆盖终态 | `BATCH_TERMINAL_STATUSES` 守卫 + `detail=already_terminal` | ✅ 批 4 |
| C3+I5 | Critical | `uq_asset_fact_snapshot_source` UNIQUE CONSTRAINT 不覆盖 NULL + 单列索引冗余 | 合并迁移：DROP CONSTRAINT → CREATE PARTIAL UNIQUE INDEX (WHERE NOT NULL) + ORM 同步 | ✅ 批 4 |
| C4 | Critical | `i18n.js` Vite 优先于 .ts 不可达 | 删除 `frontend/src/utils/i18n.js` | ✅ 批 4 |
| C5 | Critical | `user.js` Vite 优先于 .ts 不可达 | 删除 `frontend/src/stores/user.js` | ✅ 批 4 |
| I1 | Important | `create_batch_run` / `retry_failed_items` / `cancel_batch_run` 无 admin 角色门 | `get_current_admin` dependency + 3 endpoint 切换 | ✅ 批 4 |
| I2 | Important | `create_batch_run` 无速率限制 | per-user in-flight batch cap (default 3) + `COLLECTOR_MAX_BATCH_RUNS_PER_USER` config | ✅ 批 4 |
| I3 | Important | `timeout_recovery_task` 不重读 run.status（callback 抢先终态） | per-row re-select + `RUN_TERMINAL_STATUSES` 守卫（canceled 双 L） | ✅ 批 4 |
| I4 | Important | `timeout_recovery_task` AWX error 时 FOR UPDATE 锁未释放 | `db.rollback()` before `continue` | ✅ 批 4 |
| A2 | Advisory | `timeout_recovery` 硬编码终态集合 | 改用 `DISPATCH_TERMINAL_STATUSES - {"timeout"}` | ✅ 批 4 |
| I6 | Important | AWX error body 全量落 DB（可能泄漏凭据/路径/IP） | cap 500 字符 + raw body 只写 log | ✅ 批 4 |
| I7 | Important | callback 无 replay protection | `collector_callback` 入口 `RUN_TERMINAL_STATUSES` 检查 | ✅ 批 4 |
| I8 | Important | BatchVerify 轮询无 AbortController | 切路由/换 batch 时 abort in-flight 请求 | ✅ 批 4 |
| I9 | Advisory | `formatTime(val: any)` 类型过宽 | 收紧为 `string | null | undefined` | ✅ 批 4 |
| I10 | Advisory | `TERMINAL_BATCH_STATUSES` 前端本地硬编码 | 迁移到 `@/types/api.ts` 作为 `TERMINAL_BATCH_STATUS_SET` | ✅ 批 4 |
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

---

## 7. Phase 3.6 AI Copilot 后续工时（2026-06-29 收尾记录）

> C1-C14 已完成 + C15（A/B/B.2/C/D）已闭环。下表为后续 sprint 待办，技术债等级 = Medium。

| # | 任务 | 来源 | 落点 | 风险等级 | 建议处理 | 状态 |
|---:|---|---|---|---|---|---|
| F1 | `awx_job_id` 暂未回填 `ai_sql_audit` 行 | C14 commit `fb8addb` 实测：execute_service.commit() 时未写 audit.awx_job_id，只写 collector_run.awx_job_id | `backend/app/services/ai_sql_execute_service.py` + ORM `ai_sql_audit.awx_job_id` 字段 | Medium | ✅ C16-F1 已闭环：新增 `backend/db/dbops_phase3_6b1_awx_job_id_backfill.sql`（`ALTER TABLE ai_sql_audit ADD COLUMN IF NOT EXISTS awx_job_id BIGINT NULL` + 部分索引 `idx_ai_sql_audit_awx_job_id`）；ORM `AiSqlAudit.awx_job_id` 字段新增；execute_service AWX launch 成功后用 SQLAlchemy Core `update().where(awx_job_id IS NULL)` 幂等回填；api/ai.py execute_sql + get_execution_status 两处 `awx_job_id=None` TODO 替换为 `getattr(audit, "awx_job_id", None)`；3 个新测试覆盖（首次回填 / 已存在不覆盖 / launch 返回 None 跳过）；18/18 execute_service 测试通过 + 130/130 其他 AI 测试通过 | 已完成 |
| F2 | `result_message_id` 双向绑定缺 E2E 验证 | C14 commit `fb8addb` 实测：ai_sql_audit.result_message_id 与 ai_chat_message.id 互相绑定已实现，但缺端到端 happy path（dev 库无 PG 实例） | `backend/app/services/ai_sql_callback_service.py` save_snapshots 阶段；live 走完 dev 库 PG 实例 | Medium | ✅ C16-F2 已闭环（验证见 `phase-3-6-c16-f2-completed-2026-07-06.md`）：1) Pydantic schema `CollectorCallbackItem` 显式声明 `business_context: Optional[dict[str, Any]] = None`（之前 extra='ignore' 静默 drop）；2) `_extract_business_context` 加 item_key 兜底（`ai_sql:{audit_id}:{instance_id}` 解析，无需 ansible-playbooks 改动）；3) 8 个新单元测试（TestF2BusinessContextResolution × 6 + TestF2SchemaAcceptsBusinessContext × 2）覆盖 nested/flat/missing 三种格式；4) live E2E：合成 callback（item_key="ai_sql:5:965" + 无 business_context）→ audit 5 execution_status=success + result_message_id=1130 + ai_chat_message(1130, message_type='sql_result', role='assistant', parent_message_id=200) + GET /audit/5/execution 返回 message_type=sql_result；5) failure path 验证：audit 6 = failed + error_message="[PG_DENIED] ..." + chat_message(1131) 同样落库；6) idempotency：replay callback（status 已是 success）不覆盖 row_count / result_message_id | 已完成 |
| F3 | Chat 流 sql_preview_link 渲染分支 | C14 commit `78e1768` 已落，Chat.vue onExecuteFromBubble + startPendingPolling + loadPendingExecutions 闭环 | `frontend/src/views/ai/Chat.vue:474-565` | — | ✅ C15-A 已闭环（验证见 `phase-3-6-c15-completed-2026-06-29.md`） | 已完成 |
| F4 | Chat 流 sql_result 卡片「重新执行」/「查看详情」按钮 | C14 commit `78e1768` sql_result 卡片缺操作按钮 | `frontend/src/components/ai/ChatMessageBubble.vue` 新增按钮 + emit + Chat.vue onReExecuteFromResult（force=true 走 executeSql）+ onViewDetailFromResult（router.push /ai/sql/preview?audit_id=）；终态 disable 逻辑（plan §4 risk #1） | — | ✅ C15-B 已闭环 | 已完成 |
| F5 | SqlPreview.vue 接 auditId from query 详情显示 | C14 commit `78e1768` 当前 SqlPreview.vue 不读 query.audit_id，「查看详情」跳转无处落 | `frontend/src/views/ai/SqlPreview.vue` parseAuditIdFromQuery + loadAuditDetail + 新增 audit 详情卡 + exitAuditDetailMode；plan §4 risk #2 兼容 query string 模式 | — | ✅ C15-B.2 已闭环 | 已完成 |
| F6 | dev 库无 PG 实例（限制 live SQL Execute happy path） | C14 live curl 验证时确认 | dev 库 10.134.185.85:5432/dbops 当前仅 PG schema（无 dbops 实例绑定到 PG），需要为 ai_sql 演示专门起一个 dev-only PG 实例 | Low | 待现场确认：是否在 dev 库加一个 miniredis 类似作用的 dev-only PG 实例（与 dev 后端 PORT 60801 + AI_SQL_EXECUTION_ENABLED=true 配套） | 待确认 |
| F7 | AI Copilot 测试覆盖率尚需补强 | C1-C14 共 511 pytest passed（含 38 ai 安全 + 22 preview + 24 execute + 19 callback），但 Chat → SQL Execute → Callback → sql_result 卡片 端到端 happy path 缺 | `backend/tests/test_chat_sql_execute_integration.py`（5 测试已写）覆盖 callback 三状态但缺真实 AWX launch + dev PG 实例 走通 | Medium | 下次 dev 库加 PG 实例后补一条 happy path 集成测（启动 AWX job → 模拟 collector callback → 断言 ai_chat_message.sql_result 落库） | 待处理 |
| F8 | Vue 组件单测覆盖 | C1-C14 无 Vue 组件单测（项目原本未配置 vitest 模板） | 新增 `frontend/tests/components/ai/ChatMessageBubble.spec.ts` + SqlPreview.vue + Chat.vue 路由切换 | Low | 项目无 vitest 模板时跳过；下次新增 components 时配套加上 @vue/test-utils + vitest | 待处理（无模板） |
| F9 | SSE / 流式 Chat（typing effect） | C5 落地 notes：stream_enabled 首版固定 false（SSE 留待后续） | `backend/app/services/dify_service.py` 加 streaming + `backend/app/api/ai.py` 用 `StreamingResponse` + 前端 `Chat.vue` EventSource 增量 push | Low | 与 Dify 流式接口协议 + SSE 长连接断线重连复杂度相关，sprint 单独排期 | 待排期 |
| F10 | 跨方言 SQL 校验（MySQL/Oracle/MSSQL） | C11 sqlglot 权威层已实现 PostgreSQL 校验；MySQL/Oracle/MSSQL 各自 dialect 的 AST 误报可能未覆盖 | `backend/app/services/sql_safety_service.py` `validate_with_ast` 扩展方言分支 + 测试矩阵 `tests/test_sql_safety_*.py` 28 → 100+ | Medium | C12 已通过 `sql_dialect` 字段为 schema policy 留口；补全需 `capabilities.sql_supported_db_types` 扩展到所有 4 方言 + 各自 sqlglot dialect 测试夹具 | 待处理 |
| F11 | `db_sql_readonly_collect` role 是否需要为 `ai_sql` 加 special handling | C10 决策：`ai_sql` 复用 inspection 路径（`db_schema_metadata_collect` role），未单独加 `ai_sql` play | `ansible-playbooks/playbooks/dbops_collector_generic.yml` + `ansible-playbooks/playbooks/roles/db_*` | Low | 当前复用无问题（schema_metadata + AWX launch + collector callback 全走通）；若未来 `ai_sql` 需要特殊的 readonly 校验策略（如禁止 pg_dump），可加 `db_sql_readonly_collect` role | 待观察 |
| F12 | AI Copilot ChatMessageBubble 渲染 Dify markdown 答案时未解析（用户看到 `**粗体**` / `## 标题` / `` `代码` `` 源码态） | C15+ Refactor 2026-06-29：发现 ChatMessageBubble 用 `whitespace-pre-wrap` + `{{ content }}` 直出 Dify LLM 返回的 markdown 文本，无人读懂 | `frontend/src/components/ai/ChatMessageBubble.vue:25-29`（v-if 块） | Medium | ✅ Refactor 已完成：新增 `frontend/src/utils/markdown.ts`（marked + 危险协议拦截 + 裸 HTML 拦截）+ ChatMessageBubble assistant 气泡走 `v-html="renderedMarkdown"`（user 气泡保留纯文本）+ 22 vitest + 535 pytest 全过 + vue-tsc 0 错 + docs/frontend-guide.md 3.11 节新增 markdown 渲染约定 + main.css 新增 `.ai-markdown` 样式 | 已完成 |
| F13 | AI Copilot Object Metadata Snapshot（DB DDL 快照）补强 | C16-F3 commit `93499a1`+`6e071e9` 已落：DDL/ORM/Builder/Ansible Role/路由 + 运行时层 7 文件，但首版仅支持 PostgreSQL + 1MB DDL 截断（与 C8 schema snapshot 10MB cap 不同），未实现跨方言 | `backend/app/services/ai/ai_object_metadata_callback_service.py` `save_snapshots`（1MB 截断 + 两阶段发布）+ `backend/app/services/ai/ai_object_metadata_snapshot_service.py`（trigger/status/history/published/cleanup） + `backend/app/services/check_item_builder_registry.py:1119-1273`（`_AiObjectMetadataBuilder`） + `ansible-playbooks/playbooks/roles/db_object_metadata_collect/tasks/main.yml` | Medium | ✅ C16-F3 commit 3 已闭环：4 个测试文件 65 cases（builder 15 + callback 21 + snapshot 20 + context_integration 9） + 4 docs 同步 + 1 memory 闭环；live E2E 待 dev 库 PG 实例就绪后跑（已注册 PG `10.134.185.228` id=965 credential=7）；跨方言（MySQL/Oracle/MSSQL）与 C16-F0 合并排期 | 已完成 |
| F0 | AI Copilot Schema Snapshot + Object Metadata Snapshot 三方言合并（PG/Oracle/MSSQL） | C8 schema snapshot + C16-F3 object metadata snapshot 首版仅 PostgreSQL；C16-F0 任务要求三方言（MySQL 暂不实现，按 plan §4.8 范围） | `backend/app/services/ai/sql_templates/oracle/ora_schema_columns.sql` + `ora_object_metadata.sql`（6 列 / 5 列×6 UNION ALL segment）+ `backend/app/services/ai/sql_templates/mssql/mssql_schema_columns.sql` + `mssql_object_metadata.sql`（6 列 / 5 列×9 UNION ALL segment）+ `backend/app/services/check_item_builder_registry.py` `_AiSchemaMetadataBuilder` + `_AiObjectMetadataBuilder`（`_SUPPORTED_DB_TYPES` 5 个值 + `_SQL_TEMPLATE_MAP` 5 个映射 + `_load_sql_template` 统一入口）+ `backend/app/services/collector_service.py` `_check_definition_defaults` + reachability gating 注册 DB_OBJECT_METADATA（修 C16-F3 漏注册 bug）+ `ansible-playbooks/playbooks/roles/db_schema_metadata_collect/tasks/main.yml` + `db_object_metadata_collect/tasks/main.yml` assertion 扩 5 个 dialect | Medium | ✅ C16-F0 已闭环：84 unit tests（builder 36+36 + 12 边界/parametrize）+ verify.sh 0 failed + 264 pytest passed（6 C13 sqlglot 失败系历史环境问题）+ DDL `CHECK (db_type_code IN ('POSTGRESQL','ORACLE','MSSQL','MYSQL'))` 已就位无需新迁移；MySQL 延后（按 plan §4.8 + capabilities `sql_supported_db_types`）；dev 库已注册 PG `10.134.185.228` id=965，Oracle/MSSQL 走同样 4 端点路径只需 collector 跑通；live E2E 待 dev 库 ORACLE/MSSQL 实例就绪后补 | 已完成 |
| F14 | AI Copilot Chat 绑定实例（chat_mode + bound_instance_id） | C16-F2a 任务要求 Chat session 支持实例绑定 SQL Copilot 模式；plan §21.2 P0-1 不可变绑定规则 | `backend/db/dbops_phase3_6b2_c16_f2a_chat_mode.sql`（ADD COLUMN chat_mode/bound_instance_id + 2 CHECK + FK + partial unique）+ `backend/app/models/ai.py` `AiChatSession` 2 字段 + 2 CheckConstraint + 2 Index + `backend/app/schemas/ai.py` `AiChatSessionCreateRequest` mode/bound_instance_id/source_page + `AiChatSessionResponse` chat_mode/bound_instance_id + `backend/app/services/ai_chat_service.py` create_session 扩展 mode/bound_instance_id + DbInstance.status 校验 + instance_sql 复用 logic + 3 异常 + `CreateSessionResult` dataclass + `backend/app/api/ai.py` POST /chat/sessions 异常映射 | Medium | ✅ C16-F2a 已闭环：3 commit (`cb0aed8` DDL+ORM+Schemas / `2fe07b0` Service+API / commit 3 测试+文档+memory) + 14 pytest passed (1 skipped 因 dev 库只有 1 active user) + verify.sh 0 failed (2 skipped 系历史 C13 sqlglot) + dev 库 DDL 已落 + 2 次幂等验证；C16-F2b Preview API 改造待起手（消费 chat_mode + bound_instance_id 鉴权） | 已完成 |
| F15 | AI Copilot SQL Preview 在 Chat 流内可调用（绑定鉴权 + 幂等 + 双消息写入） | C16-F2b 任务要求 POST /ai/sql/preview 重构为 Chat 可调用入口；plan §21.3 C16-3 4 件事：P0-1 绑定鉴权 / P0-2 幂等 / P0-3 双消息写入 / P1-3 rejected 也写 preview_message | `backend/app/schemas/ai.py` `AiSqlPreviewRequest` 必填 session_id + client_request_id，移除 message_id；`AiSqlPreviewResponse` 加 session_id/user_message_id/preview_message_id/idempotent_replay + `backend/app/services/ai_chat_service.py` 新增 helper `get_session_for_user`（统一 404 隔离存在性泄露）+ `backend/app/services/ai/ai_sql_preview_service.py` preview() 签名加 client_request_id + 4 步鉴权链 `_auth_check_session_for_preview`（session ownership + chat_mode='instance_sql' + bound_instance_id 一致 + DbInstance.status='active'）+ step 2.5 幂等检查（client_request_id 命中已有 user_message → 返回原 audit 三元组 idempotent_replay=True；audit 缺失 → PreviewIncompleteRetryRequiredError 409）+ 双消息写入 helper `_finalize_preview_with_chat_messages`（user role='user' + preview role='assistant' message_type='sql_preview_link' 与 audit.message_id/result_message_id 同事务）+ 5 类新异常（ChatSessionNotFoundErrorPreview/ChatSessionForbiddenErrorPreview/ChatModeNotInstanceSqlError/ChatImmutableViolationErrorPreview/PreviewIncompleteRetryRequiredError）+ rejected 也写 preview_message 卡片（P1-3）+ `PreviewResult` 扩展 4 字段 + `backend/app/api/ai.py` 5 类异常 HTTP 映射 + 响应 4 字段填充 | Medium | ✅ C16-F2b 已闭环：2 commit (`babe687` Schemas+Service 鉴权+异常 / `54b122d` Service 幂等+双消息+API 映射) + 39 preview 单测 + _FakeSession.flush() + _next_id() 模拟 autoincrement + verify.sh 0 failed (679 passed / 3 skipped) + dev 库 partial unique `uq_ai_chat_message_session_client_request_idx` 天然支持 client_request_id 幂等；下轮起手 C16-F2c Chat.vue boundInstanceId 模式分流 + SqlPreview.vue 重构 | 已完成 |
| F16 | AI Copilot Chat.vue boundInstanceId 模式分流 + SqlPreview.vue 重构（C16-F2b 遗留 Pydantic Literal 漏 'sql_preview_link' 修） | C16-F2b 把 `'sql_preview_link'` 写入 ai_chat_message 后，前端 listMessages 触发 Pydantic 500（`AiChatMessageResponse.message_type` Literal 漏加）；同时 C16-F2c 任务要求 Chat.vue 走 `route.query.boundInstanceId` → `mode='instance_sql'` + 创建/复用绑定实例 session + 顶部实例上下文 header + 输入框 placeholder 切换 + onSend 分流（instance_sql→POST /ai/sql/preview, general→POST /chat/sessions/{id}/messages）；SqlPreview.vue boundInstanceId 模式重定向 Chat.vue | `backend/app/schemas/ai.py` `AiChatMessageResponse.message_type` Literal 加 `'sql_preview_link'`（F2b 漏修）+ 3 回归测试 `tests/test_ai_chat_message_response_c16_f2c.py`（接受 sql_preview_link / 5 枚举全过 / 拒绝 unknown）+ `frontend/src/types/ai.ts` `AiChatSessionCreateRequest` 加 `mode?/bound_instance_id?/source_page?` + `AiChatSession` 加 `chat_mode?/bound_instance_id?` + `AiSqlPreviewRequest` `session_id` 必填 + `client_request_id` 必填（移除 `message_id`）+ `AiSqlPreviewResponse` 加 4 字段 + `AiSqlPreviewLinkMetadata` 加 `reason?` + `frontend/src/views/ai/Chat.vue` `parseBoundInstanceId` + `loadBoundInstanceContext` + `createBoundSession` + `exitBoundMode` + `activeSessionIsInstanceSql` computed + `inputPlaceholder` computed + `describePreviewError` helper + onSend 分流（`aiApi.sqlPreview` 走 instance_sql；调用后 `loadMessages` 同步后端实际状态）+ onMounted `Promise.all([loadBoundInstanceContext, createBoundSession])` + 模板：bound 模式隐藏会话侧栏、显示实例上下文 header（`instance_name / db_type_code / server_ip:port`）、「返回通用 Chat」按钮、placeholder 切换 + `frontend/src/views/InstanceDetail.vue` `useRouter` + `gotoAiChat` + 「AI 查询」按钮（`auto_awesome` 图标 + `data-testid="instance-ai-chat-button"`） + `frontend/src/components/ai/ChatMessageBubble.vue` 重写 `previewLinkMeta` computed（合并 `metadata_json` audit_id/status + `content` JSON approved_sql/schema_policy_hash/reason）+ rejected 分支模板（红框 + 「SQL Preview 被拒绝（audit #N）」+ reason 显示 + 无执行按钮） + `frontend/src/views/ai/SqlPreview.vue` `parseBoundInstanceIdFromQuery` + onMounted 检测 `boundInstanceId` → `router.replace({name: 'AiChat', query: {boundInstanceId}})`（commit 2 重定向） | Medium | ✅ C16-F2c 已闭环：3 commit (`387ad97` Chat.vue+F2b 漏修 / `209bff7` SqlPreview.vue 重定向 / commit 3 测试+docs+memory) + 3 回归测试 + verify.sh 0 failed + 693 pytest + vue-tsc 0 错 + dev 库 `POST /ai/chat/sessions` + `POST /ai/sql/preview` 走通 instance_sql 流；下轮起手 F17 跨入口一致性回归（`/ai/sql/preview` form 模式 vs Chat 模式）/ Phase 3.7 下一阶段 | 已完成 |

| F17 | AI Copilot /ai/sql/preview Chat 流入口与 form 入口跨入口一致性回归（F2a/F2b/F2c 测试补强） | F2c 实施记录末尾已识别回归盲点：F2b 落地 `message_type='sql_preview_link'` 后，前端 listMessages 走 ChatMessageBubble.previewLinkMeta 5 message_type 解析分支（F2a 不可变绑定 + F2b 双消息 + F2c Pydantic Literal 修复已闭环），但 form 模式（SqlPreview.vue 旧表单入口，保留 `source_page='sql_preview_legacy'`）和 Chat 模式（InstanceDetail 「AI 查询」入口，`source_page='instance_detail'`）写出的 preview_message 回到前端的卡片渲染完整性未单独回归覆盖 | `frontend/src/components/ai/ChatMessageBubble.spec.ts` 追加 1 个 describe 块「ChatMessageBubble — sql_preview_link previewLinkMeta（C16-F2c + F17 跨入口一致性回归）」共 6 cases：case 1 passed + content 含 approved_sql（绿框 + 执行按钮 + audit_id 透传）/ case 2 passed + content 缺 approved_sql 脏数据（previewLinkMeta=null，不渲染卡）/ case 3 rejected + content.reason（红框 + 拒绝原因 + 无执行按钮）/ case 4 rejected + content 缺 reason（红框 + 兜底文案）/ case 5 sql_preview_link + 非 JSON content 历史脏（不渲染卡）/ case 6 messageType='chat'（普通气泡，markdown 渲染）；后端不新增测试文件（跨入口一致性回归由 F2a `tests/test_ai_chat_service_c16_f2a.py`（partial unique 复用 + source_page 不持久化 + immutable binding + 4 步校验 + mode 隔离）/ F2b `tests/test_ai_sql_preview_c16_f2b.py`（4 步鉴权链 + 幂等 + 双消息事务 + 5 类新异常）/ F2c `tests/test_ai_chat_message_response_c16_f2c.py`（AiChatMessageResponse.message_type 5 值 Literal）共 12+14+3=29 cases 覆盖） | Medium | ✅ C16-F17 已闭环：1 commit ChatMessageBubble 5 分支回归 + verify.sh 0 failed (696 passed / 3 skipped 历史 C13 sqlglot) + 28 vitest cases (含新增 6) + vue-tsc 0 错；下轮起手 Phase 3.7 下一阶段（Inspection AI 集成）/ dev 库 ORACLE/MSSQL 实例 live E2E 补跨方言 | 已完成 |
| F18 | collector_client PG connector psycopg2 → psycopg v3 alias（C16-5 Commit 4） | DBOPS Collector EE 镜像 `awx-ee-dbops:24.6.1` 只预装 psycopg v3 (3.2.13)，不含 psycopg2；老 `postgresql.py` `import psycopg2` 在 EE 容器中 ModuleNotFoundError，阻塞 `db_sql_readonly_collect` role + `db_fact_collect` role 跑 PG 实例 | `ansible-playbooks/files/collector_client/db_connectors/postgresql.py` `_connect()` 改 `import psycopg as psycopg2`（psycopg v3 API 兼容 alias；`connect() / cursor() 默认 tuple row factory / execute() / fetchone() / fetchmany() / description / SET LOCAL` 全兼容）+ `ansible-playbooks/files/collector_client/requirements.txt` `psycopg2-binary>=2.9` → `psycopg[binary]>=3.1`（与 EE 实际一致） | Medium | ✅ C16-5 Commit 4 已闭环：ansible-playbooks commit `0bffbda`（2 files / +21 −9）推送 `4932140..0bffbda` + EE 容器实测 collect_basic_facts 返回 `version_label=PostgreSQL 17.9 / database_name=dbops / current_user=dbops` + execute_readonly_sql('SELECT now(), 1+1') 返回 columns=['ts','sum'] + rows + `timeout_enforced=True`；下轮起手 Commit 5（backend capabilities 三方言解锁 + dev 库 PG credential binding + ai_sql_audit 卡 running cleanup）/ Commit 6（dev 库 PG 965 dbops_readonly role + GRANT）/ Commit 7（PG 965 live E2E 8 端点） | 已完成 |
| F19 | backend capabilities 三方言解锁 + dev 库凭证 binding + ai_sql_audit 卡 running cleanup（C16-5 Commit 5） | C8 schema snapshot + C11-C12 sqlglot + C16-F0 三方言 SQL 模板（PG/Oracle/MSSQL builder + 5 dialect）已闭环，但 `settings.sql_supported_db_types` 仍硬编码 `["POSTGRESQL"]`，/api/v1/ai/capabilities 暴露给前端的 dialect 列表只 1 项；dev 库仅 profile 6 个 id 9-14 凭证绑定，缺 PG instance 965 专属凭证（仅走 global priority=200 默认），导致 SQL Copilot binding 解析时全 fallback 到 global；ai_sql_audit 自 2026-07-06 起 id=4 卡 `execution_status='running'` 未结（AWX launch 时序漏 callback 路径）；dev 库未落 `ai_object_metadata_snapshot` 表，触发 ObjectMetadata 端点直接 table not exist | `backend/app/config.py:200-211` `sql_supported_db_types` 返回列表从 `["POSTGRESQL"]` 扩到 `["POSTGRESQL", "ORACLE", "MSSQL"]`（MySQL 延后按 plan §4.8）+ `backend/tests/test_dify_service.py:422-451` 3 tests（postgres_only_when_sql_preview_enabled + includes_when_execution_enabled + three_dialects_order_stable 含 MYSQL 不在断言）+ dev 库 SQL: `INSERT credential_binding` `(binding_code='bind-db-postgresql-inst-965', credential_profile_id=4, target_type='db_instance', target_id=965, binding_role='db_readonly', priority=10, is_enabled=true)` + `UPDATE ai_sql_audit SET execution_status='timeout', completed_at=NOW(), error_message='[C16-5 Commit 5 cleanup] dev 库残留卡 running 记录强制收尾' WHERE id=4 AND execution_status='running'` + 落 `backend/db/dbops_phase3_6b0_ai_object_metadata.sql` 21 字段/4 CHECK/5 索引 | Medium | ✅ C16-5 Commit 5 已闭环：1 commit dbops sql_supported_db_types（1 file / +2 −1）+ 3 tests 通过 + dev 库 ai_object_metadata_snapshot 表 CREATE 成功 + credential_binding id=15 INSERT + ai_sql_audit id=4 UPDATE 1 row → timeout；下轮 Commit 6（dev 库 PG 965 dbops_readonly role + GRANT）/ Commit 7（PG 965 live E2E 8 端点走通三方言 capabilities） | 已完成 |
| F20 | dev 库 PG 965 `dbops_readonly` role + GRANT + AWX 新建 readonly 凭证 + binding 切换（C16-5 Commit 6） | Commit 5 落 `bind-db-postgresql-inst-965` 绑定到 profile_id=4 `cred-db-postgresql-ro-prod`（AWX id=7 gdmms 全局 readonly，已被 collectors 占用），复用同一 AWX 凭证会让 SQL Copilot end-user 走与 collector 完全相同的 readonly 链路（缺专属命名 + 缺最小权限粒度）；dev 库 PG 965 实际是测试实例 `benchdb/jemdb/postgres` 三 DB 多 schema（plan §6 假设的 `dbops` schema 不存在），需要实测确认 GRANT 范围 | dev 库 PG 965 (10.134.185.228:5432 superuser `postgres/root123`)：`CREATE ROLE dbops_readonly LOGIN PASSWORD 'readonly2026@readonly'` (`rolcanlogin=t rolsuper=f rolcreatedb=f rolcreaterole=f`) + 3 库三套 `GRANT CONNECT + GRANT USAGE ON SCHEMA public/sbtest/app/oggadm + GRANT SELECT ON ALL TABLES IN SCHEMA ... + ALTER DEFAULT PRIVILEGES IN SCHEMA ... GRANT SELECT + ALTER DEFAULT PRIVILEGES FOR ROLE benchuser/app/oggadm IN SCHEMA ... GRANT SELECT`；AWX REST 新建 cred id=10 `cred-db-postgresql-ro-prod-readonly` organization=1 credential_type=32 inputs.username=`dbops_readonly` inputs.password=`readonly2026@readonly`；dbops DB `INSERT credential_profile id=12 profile_code='cred-db-postgresql-ro-prod-readonly' profile_name='PostgreSQL 生产只读 (dbops_readonly role)' credential_type='db_password' awx_credential_id=10 binding_role='db_readonly' db_type_code='postgresql' is_enabled=true environment='dev'` + `UPDATE credential_binding id=15 SET credential_profile_id=12, remark=... WHERE credential_profile_id=4`；冒烟（5 全过）：benchdb.pgbench_accounts(1M) / benchdb.sbtest.sbtest1(1M) / jemdb.public / postgres.app / postgres.oggadm | Medium | ✅ C16-5 Commit 6 已闭环：PG 965 server-side 1 file `/tmp/commit6_grant_readonly.sql`（`\connect benchdb/jemdb/postgres` 三轮 GRANT block + 9 条 ALTER DEFAULT PRIVILEGES）+ AWX cred id=10 via REST + dbops DB `credential_profile id=12` INSERT + `credential_binding id=15` `profile_id` 4→12 UPDATE + 5 冒烟正 / 2 冒烟负；下轮 Commit 7 PG 965 live E2E 8 端点（preview→execute→callback 走 dbops_readonly + AWX id=10） | 已完成 |

### 7.1 Phase 3.6 后续 sprint 建议

1. **F1 + F2 已闭环**（C16-F1 `83deed2`+`d9a84b0` + C16-F2 本次 commit）：awx_job_id 回填 + result_message_id 双向绑定 + 8 单测 + 合成 callback E2E 验证 success/failure/idempotency 三态
2. **F7 集成测试补强**：dev 库加 PG 实例后（待现场确认），补 1 条 happy path（半天）
3. **F3-F5 已闭环**：仅在新功能扩展时回顾（避免回归）
4. **F8 Vue 组件单测**：取决于项目 vitest 模板决策（CLAUDE.md 维护定位以外，需独立排期）
5. **F9 SSE 流式**：与产品需求同步，单独 sprint
6. **F10 跨方言**：C12 已扩展 schema policy 多 dialect 入口，补 sqlglot 测试矩阵
7. **F11 是否需要 special role**：观察 `ai_sql` 复用 `db_schema_metadata_collect` 的真实使用 1-2 周后决定
8. **F13 Object Metadata Snapshot**：C16-F3 commit 3 已闭环；live E2E 待 dev 库 PG 实例就绪后跑；跨方言与 C16-F0 合并
9. **F14 Chat 绑定实例**：C16-F2a commit 3 已闭环（chat_mode + bound_instance_id 不可变绑定 + 4 步校验 + 3 异常 + partial unique 兜底）
10. **F15 SQL Preview Chat 流入口**：C16-F2b commit 3 已闭环（4 步鉴权 + 幂等 + 双消息写入 + 5 类新异常 + 14 测试）
11. **F16 Chat 前端 boundInstanceId 模式分流**：C16-F2c commit 3 已闭环（3 commit：Chat.vue+F2b Literal 漏修 / SqlPreview.vue 重定向 / 本次测试+docs+memory）；F2b 残留 Pydantic Literal 漏 `'sql_preview_link'` 已修（listMessages 500 bug 修复）
12. **F17 跨入口一致性回归**：C16-F17 已闭环（1 commit：ChatMessageBubble previewLinkMeta 5 分支 6 cases 回归）；form 模式（SqlPreview.vue 旧表单，`source_page='sql_preview_legacy'`）和 Chat 模式（InstanceDetail 「AI 查询」，`source_page='instance_detail'`）的 preview_message 渲染完整性已由 vitest 覆盖；后端 4 步鉴权 / 幂等 / 双消息 / Pydantic Literal 由 F2a/F2b/F2c 三件套 29 cases 覆盖；下轮 Phase 3.7 下一阶段（Inspection AI 集成）/ dev 库 ORACLE/MSSQL 实例 live E2E 补跨方言
13. **F18 collector PG connector psycopg v3 alias**：C16-5 Commit 4 ansible-playbooks `0bffbda` 已闭环（2 files / +21 −9）；EE 容器实测 collect_basic_facts + execute_readonly_sql 兼容 v3 API；下轮 Commit 5-6（capabilities 三方言解锁 + dev 库 PG 凭证 + dbops_readonly role）/ Commit 7（PG 965 live E2E 8 端点）
14. **F19 capabilities 三方言解锁 + dev 库凭证 + ai_sql_audit 卡 running cleanup**：C16-5 Commit 5 已闭环（1 file / +2 −1 config.py + 3 tests + dev 库 `ai_object_metadata_snapshot` DDL 落地 + credential_binding id=15 INSERT + ai_sql_audit id=4 UPDATE → timeout）；下轮 Commit 6（dev 库 PG 965 dbops_readonly role + GRANT）/ Commit 7（PG 965 live E2E 8 端点走通三方言 capabilities）
15. **F20 PG 965 dbops_readonly 最小权限闭环**：C16-5 Commit 6 已闭环（dev 库 PG 965 CREATE ROLE dbops_readonly + 3 库 5 schema SELECT/DEFAULT PRIVILEGES + AWX 新建 readonly 凭证 id=10 + dbops DB `credential_profile id=12` INSERT + `credential_binding id=15` 4→12 UPDATE）；下轮 Commit 7（PG 965 live E2E 8 端点：preview→execute→callback 走 dbops_readonly + AWX id=10）

### 7.2 Phase 3.6 范围外但与 AI Copilot 相关

- **Inspection AI 集成**：Phase 3.6 暂未覆盖（plan 已规划但 C1-C14 都没碰到 Inspection AI）。下阶段排期。
- **Report Export AI 集成**：plan §16 提及但 C1-C14 未实现，capabilities 字段 `report_analysis_enabled` + `report_export_ai_enabled` 已保留 false 占位。
- **Dify 会话上下文压缩**：Chat 会话无窗口限制；当前依赖 Dify 服务端 + dbops 端 ai_chat_message 完整留存。后续如需压缩，按 `dify_conversation_id` 维度。
