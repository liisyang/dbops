# 排障手册

> 文档状态：已校准
> 最近校准：2026-05-22
> 依据来源：真实代码

## 1. 维护定位

本文件是故障入口表。

只记录：

1. 常见现象。
2. 优先检查位置。
3. 常见根因。
4. 修复入口。
5. 标准排查命令。
6. 已确认问题。

不要编造历史故障。

## 2. 快速入口

| 现象 | 优先检查 | 常见根因 | 修复入口 | 代码依据 |
|---|---|---|---|---|
| 前端 401 | localStorage token 是否存在；后端 `SECRET_KEY` 是否一致 | token 过期（480min）/ token 被清除 / 后端重启后 SECRET_KEY 变化 | 重新登录；检查 `backend/app/api/deps.py:56` SECRET_KEY 来源 | `frontend/src/api/request.js:114-126` + `backend/app/api/deps.py:55-56` |
| 前端 403 | 用户 `role` 字段是否为 admin/operator | 后端路由未做角色校验（当前所有认证路由只校验登录态，不区分角色） | 检查 `get_current_user` 调用链，确认是否需要增加角色校验 | `backend/app/api/deps.py:69-102` |
| 后端 500 | 后端控制台日志；数据库连接是否正常 | DB 连接池耗尽 / 唯一约束冲突 / JSONB 字段格式错误 / Celery Redis 连接失败 | 查看后端 stderr 输出；检查 PostgreSQL 连接 `SELECT 1` | `backend/app/database.py:12-19` |
| 数据库连接失败 | `SQLALCHEMY_DATABASE_URI` 拼装是否正确；PG 端口 5432 是否可达 | PG 不可达 / 账号密码错误 / search_path 中 schema 不存在 | `psql -h <host> -U dbops -d dbops -c "SELECT 1"` | `backend/app/config.py:51-55` + `backend/app/database.py:18` |
| 表不存在 / schema 错误 | `search_path=dbops,public` 是否生效；表是否建在 dbops schema | 部署时未执行 DDL / ORM `__table_args__` 未指定 schema | `SELECT tablename FROM pg_tables WHERE schemaname='dbops'` | `backend/app/database.py:18` + `backend/db/dbops_phase1_25_tables.sql` |
| 登录接口无响应 | 后端进程是否在 60801 端口监听 | 后端未启动 / uvicorn 进程崩溃 / 端口冲突 | `ss -lntp \| grep 60801` | `backend/run.py:78` |
| 前端页面空白 / 路由不跳转 | `window.__VITE_ROUTER__` 是否已挂载；`router.beforeEach` 守卫逻辑 | router 实例未挂载到 window / token 缺失导致守卫重定向到 /login | 检查浏览器 console；确认 localStorage 中 token 存在 | `frontend/src/router/index.ts:228-240` |
| Vite 代理 502/504 | 后端 60801 端口是否存活 | 后端未启动 / 后端启动失败 | `curl -i http://127.0.0.1:60801/api/auth/login` | `frontend/vite.config.ts:17-20` |
| Swagger UI 认证失败 | OAuth2 弹窗跳转到 `/api/rbac/login`（已修复为 `/api/auth/login`） | `deps.py:20` tokenUrl 已修正 | 使用 Swagger UI Authorize 按钮或直接 POST `/api/auth/login` | `backend/app/api/deps.py:20` |
| 异步任务入队但不执行 | Celery worker 未启动 | `run.py:63` worker 启动代码被注释 | 当前阶段不需要，后续恢复时取消 `run.py:63-68` 注释 | `backend/run.py:63-68` |
| 操作日志页面无数据 | `/api/logs/list` 返回 `[]` | `logs.py:15` 硬编码返回空数组，审计模块未实现 | 当前阶段无数据，需实现审计模块 | `backend/app/api/logs.py:11-15` |
| WebSocket 连接无推送 | Redis pub/sub 订阅者未启动 | `main.py:26` Redis 订阅者启动代码被注释 | 当前阶段不需要，后续恢复时取消注释 | `backend/app/main.py:26` + `backend/app/api/websocket.py:78-110` |

## 3. 标准排查命令

### 3.1 后端健康检查

```bash
# FastAPI 服务端口检查
ss -lntp | grep 60801

# 直接请求后端（绕过 Vite 代理）
curl -i http://127.0.0.1:60801/api/auth/login -d '{"username":"admin","password":"test"}'

# 检查后端进程
ps aux | grep uvicorn
```

**代码依据：** `backend/run.py:78` — uvicorn 监听 `0.0.0.0:60801`

### 3.2 数据库连通性检查

```bash
# 从后端机器测试 PG 连接（连接信息来自 config.py 默认值或 .env）
psql -h 10.134.185.85 -U dbops -d dbops -c "SELECT current_database(), current_schema(), version();"

# 检查 search_path 是否生效
psql -h 10.134.185.85 -U dbops -d dbops -c "SHOW search_path;"

# 检查核心表是否存在
psql -h 10.134.185.85 -U dbops -d dbops -c "SELECT tablename FROM pg_tables WHERE schemaname='dbops' ORDER BY tablename;"
```

**代码依据：** `backend/app/config.py:11-16` + `backend/app/database.py:18` — `connect_args={"options": "-c search_path=dbops,public"}`

### 3.3 认证链排查

```bash
# 1. 获取 token
TOKEN=$(curl -s http://127.0.0.1:60801/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<password>"}' | jq -r '.access_token')

# 2. 用 token 访问需要认证的接口
curl -i http://127.0.0.1:60801/api/v1/servers/instances \
  -H "Authorization: Bearer $TOKEN"

# 3. 解码 JWT 查看 payload（不验证签名）
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq .

# 4. 检查前端 localStorage
# 在浏览器 console 中执行：localStorage.getItem('token')
```

**代码依据：** `backend/app/api/deps.py:50-56` — HS256 + SECRET_KEY + 480min expiry；`frontend/src/api/request.js:49-52` — 请求拦截器注入 Bearer token

### 3.4 端口检查

```bash
# 检查后端端口
ss -lntp | grep 60801

# 检查 Vite 前端端口
ss -lntp | grep 61088

# 注意：端口 51088/50801 是其他用户(feng)的实例，不要干预
```

### 3.5 前端构建检查

```bash
cd frontend && npm run build
```

### 3.6 Shell 脚本语法检查

```bash
find scripts -type f -name "*.sh" -print0 | xargs -0 -I{} bash -n {}
```

### 3.7 统一验证入口

```bash
bash scripts/ai/verify.sh
```

覆盖：JS lint/typecheck/build、Python pytest、Shell 语法检查、git status。

**代码依据：** `scripts/ai/verify.sh`

## 4. 关键配置检查点

| 配置项 | 默认值 / 来源 | 影响 | 代码依据 |
|---|---|---|---|
| SECRET_KEY | `"dev-secret-key-change-in-production"` | JWT 签名，变更会导致所有 token 失效 | `backend/app/config.py:10` |
| POSTGRES_HOST | `10.134.185.85` | 数据库连接 | `backend/app/config.py:11` |
| POSTGRES_PORT | `5432` | 数据库连接 | `backend/app/config.py:12` |
| REDIS_URL | `redis://localhost:6379/0` | Celery broker/backend + 任务状态存储 | `backend/app/config.py:29` |
| ACCESS_TOKEN_EXPIRE_MINUTES | `480`（8小时） | token 有效期 | `backend/app/api/deps.py:22` |
| ALGORITHM | `HS256` | JWT 签名算法 | `backend/app/api/deps.py:21` |
| DB search_path | `dbops,public` | 所有 ORM 查询的表定位 | `backend/app/database.py:18` |
| DB pool_recycle | `300`（5分钟） | 连接池回收周期 | `backend/app/database.py:16` |
| Vite proxy target | `http://127.0.0.1:60801` | 前端 `/api` 请求代理到后端 | `frontend/vite.config.ts:17-20` |
| Vite dev port | `61088` | 前端开发服务器端口 | `frontend/vite.config.ts:15` |

## 5. 已确认问题

| 问题现象 | 根因 | 修复建议 | 状态 | 代码依据 |
|---|---|---|---|---|
| OAuth2 tokenUrl 指向错误路由 | `deps.py:20` 声明 `tokenUrl="/api/rbac/login"`，实际登录路由是 `/api/auth/login` | 将 tokenUrl 改为 `/api/auth/login` | ✅ 已修复 | `backend/app/api/deps.py:20` |
| 操作日志 API 返回空数组 | `logs.py:15` 硬编码 `return []`，审计模块未实现 | 实现审计模块后替换硬编码 | 已知限制 | `backend/app/api/logs.py:11-15` |
| Celery worker 未启用 | `run.py:63` worker 启动代码被注释 | 当前阶段不需要，后续恢复时取消注释 | 有意暂缓 | `backend/run.py:63-68` |
| Redis pub/sub 订阅者未启动 | `main.py:26` 订阅者启动代码被注释 | 当前阶段不需要，后续恢复时取消注释 | 有意暂缓 | `backend/app/main.py:26` |
| 前端 `logs.ts` 调用不存在的路由 | `GET /api/logs` 和 `GET /api/logs/{id}` 后端均不存在 | 改为 `/api/logs/list` 或删除 `logs.ts` | 待修复 | `frontend/src/api/logs.ts:6-7` |
| 前端批量删除逐条调用单删接口 | `Servers.vue` 循环调用 `deleteServer(id)`，后端有 `batch-delete` 但前端未使用 | 前端改用批量删除接口 | 待优化 | `backend/app/api/servers.py:204-218` |
| Excel 导入预览/校验报"网络错误" | `_existing_record_messages` 逐行查询（每行最多 6 次 DB 查询），大文件超时；前端显式设置 `Content-Type: multipart/form-data` 阻止浏览器自动添加 boundary | 批量预查现有记录（`_load_existing_lookups`），移除前端显式 Content-Type，修复 `file.filename` None 防护 | ✅ 已修复 | `backend/app/services/dbops_import_service.py:655-725` + `frontend/src/api/assets.ts:101-104` |
| SQL Server 导入时 AG/MIRROR cluster type 不支持 | `CLUSTER_TYPE_CATALOG` 和 `CLUSTER_TYPE_ALIASES` 缺少 AG (Always On) 和 MIRROR (Database Mirroring) 定义 | 补全 AG 和 MIRROR 的 catalog 和 alias 定义 | ✅ 已修复 | `backend/app/services/dbops_import_service.py:246-256` |
| Excel 导入 COLUMN_MAP 列名不匹配 | Excel 模板列名为 `業務主管`/`DBA負責人`，COLUMN_MAP 期期待 `業務主管(必填)`/`DBA負責人(必填)`，导致 business_manager/dba_owner 字段未填充 | COLUMN_MAP 增加无 `(必填)` 后缀的列名映射，保持向后兼容 | ✅ 已修复 | `backend/app/services/dbops_import_service.py:451-457` |
| 导入执行时 deploy_type `云` 违反 CHECK 约束 | site 表 CHECK 约束只允许 `地端`/`私有雲`/`公有雲`，Excel 中使用 `云` | 添加 DEPLOY_TYPE_ALIASES 映射（`云`→`公有雲`），upsert_site 使用 normalize 后的值 | ✅ 已修复 | `backend/app/services/dbops_import_service.py:288-299,848-851` |
| list_instances API 未返回 port 字段 | `list_instances` 方法构建返回字典时遗漏 `instance.port` | 在返回字典中增加 `"port": instance.port` | ✅ 已修复 | `backend/app/services/dbops_asset_service.py:378` |

## 6. 需现场确认

- `deps.py:20` 中 `tokenUrl="/api/rbac/login"` 是历史遗留还是有意指向（Swagger UI OAuth2 流程暂未使用，影响仅限于 Swagger 文档页的 Authorize 按钮）
- Redis 服务是否在本机 `localhost:6379` 运行且可用（Celery/任务状态依赖 Redis）
- PostgreSQL 连接信息（`10.134.185.85:5432`）是否为当前测试库
- 生产环境 `SECRET_KEY` 是否已从默认值 `dev-secret-key-change-in-production` 变更
- 端口 61088/50801 是其他用户(feng)的实例，排查时注意区分
