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
| High | 0 | 已全部修复 |
| Medium | 9 | 重复实现、不一致、性能隐患（1 项已修复） |
| Low | 5 | 清理项、渐进优化 |

## 3. 技术债清单

### 3.1 High

| # | 问题 | 位置 | 影响范围 | 风险等级 | 建议处理 | 状态 | 代码依据 |
|---:|---|---|---|---|---|---|---|
| H1 | `batch_delete_servers` 调用不存在的 `ServerService` | `backend/app/api/servers.py:214` | 批量删除服务器功能 | High | 将 `ServerService.delete_server(db=db, server_id=sid)` 改为 `DbopsAssetService.delete_server(db=db, server_id=int(sid))` | ✅ 已修复 | `grep -rn "ServerService" backend/` 仅匹配 `servers.py:214`，无定义/导入；实际服务类是 `DbopsAssetService`（`servers.py:12`） |
| H2 | `OAuth2PasswordBearer` tokenUrl 指向错误路径 | `backend/app/api/deps.py:20` | Swagger UI OAuth2 认证流程 | High | 将 `tokenUrl="/api/rbac/login"` 改为 `tokenUrl="/api/auth/login"` | ✅ 已修复 | `deps.py:20`: `OAuth2PasswordBearer(tokenUrl="/api/rbac/login")`；实际登录路由在 `auth.py:24`: `POST /api/auth/login` |
| H3 | `staging_excel_import` 存储明文密码 | `backend/app/models/dbops_assets.py:478-482` / `backend/app/services/dbops_import_service.py:451,591` | 所有导入操作的 Excel 原始数据 | High | 导入执行时在写入暂存表前清除 `db_password_raw`/`os_password_raw`/`os_oracle_password_raw` 字段 | ✅ 已修复 | `dbops_assets.py:478`: `db_password_raw = Column(Text)`；import_service 将 Excel 密码列直接写入暂存表 |
| H4 | 配置文件中硬编码默认数据库凭证 | `backend/app/config.py:10-15` | 若 .env 缺失则暴露开发环境凭证 | High | SECRET_KEY/POSTGRES_PASSWORD 默认值改为空字符串，启动时检查必需配置 | ✅ 已修复 | `config.py:10`: `SECRET_KEY: str = "dev-secret-key-change-in-production"`；`config.py:14`: `POSTGRES_PASSWORD: str = "root123"` |

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

### 3.3 Low

| # | 问题 | 位置 | 影响范围 | 风险等级 | 建议处理 | 状态 | 代码依据 |
|---:|---|---|---|---|---|---|---|
| L1 | `lucide-vue-next` 已安装但未使用 | `frontend/package.json:14` | 增加包体积 | Low | 确认是否需要，不需要则 `npm uninstall lucide-vue-next` | 待处理 | 全局搜索源码无 `lucide` 引用 |
| L2 | `.js`/`.ts` 同名文件并存（5 对） | `main.js/ts`, `stores/user.js/ts`, `utils/i18n.js/ts`, `utils/timezone.js/ts`, `utils/weather.js/ts` | TypeScript 项目中的 `.js` 文件不受类型检查 | Low | 确认 `.ts` 版本是否为实际入口，移除冗余 `.js` 文件 | 待处理 | 5 组同名文件同时存在 |
| L3 | CRUD 交互模式不一致 | `Servers.vue`（路由切换） vs `Instances.vue`/`Assets.vue`（OpsModal 弹窗） | 用户心智模型不一致 | Low | 统一为一种模式 | 待确认 | `Servers.vue`: 路由 `/assets/servers/create` 和 `/assets/servers/:id`；`Instances.vue:53-133`: OpsModal |
| L4 | WebSocket 端点无认证 | `backend/app/api/websocket.py:62-75` | 任何知道 socket_id 的人可连接 WebSocket | Low | 添加 token 验证（查询参数或首条消息） | 待处理 | `websocket.py:62`: `@router.websocket("/{socket_id}")` 无 `Depends(get_current_user)` |
| L5 | 国际化覆盖率低 | 各视图模板 | 切换语言后大量中文硬编码不变 | Low | 逐步迁移硬编码文案到 i18n | 待处理 | 各 `.vue` 文件中的中文按钮、标签、提示文案 |

## 4. 暂不处理项

| # | 问题 | 暂不处理原因 | 重新评估条件 |
|---:|---|---|---|
| D1 | Celery worker 未启用（`backend/run.py:63`） | 有意暂缓，当前阶段不需要异步任务执行 | 账号操作模块正式启用时恢复 |
| D2 | 审计/备份/SQL/巡检/凭证/知识库模块无后端 API | 当前阶段聚焦核心资产管理，规划中模块排期在后 | 核心资产管理收尾后 |
| D3 | 前端仅有暗色模式（`tailwind.config.js` 只定义一套颜色 Token） | 亮色模式非当前阶段需求 | 用户明确要求亮色模式时 |
| D4 | 历史迁移脚本源码缺失（`backend/db/__pycache__/*.pyc` 存在但 `.py` 已删除） | 历史迁移已生效，回溯源码意义有限 | 需要重跑历史迁移或审计迁移历史时 |

## 5. 需现场确认

- H4 硬编码凭证：当前 `.env` 文件是否存在并覆盖了默认值？
- L2 `.js`/`.ts` 双文件：TypeScript 版本是否为实际入口？`.js` 文件是否可以安全删除？
- L3 CRUD 交互模式：倾向于统一为弹窗模式还是路由模式？
- L1 `lucide-vue-next`：是否有计划使用？还是可以直接移除？
- M9 `resource_tag`：多态关联是否需要应用层定期校验/清理？
