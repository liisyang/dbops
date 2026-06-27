# 排障手册

> 文档状态：已校准
> 最近校准：2026-06-16
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
| AWX EE 容器内 collector `--item-json` 返回 `COLLECTOR_ERROR_IMPORTERROR: libodbc.so.2: cannot open shared object file` | Ansible `command` 任务不继承容器启动时的环境变量，`dlopen()` 找不到 ODBC 库 | `import pyodbc` 成功但 `pyodbc.connect()` 触发 unixODBC 动态加载驱动时失败 | `db_fact_collect/tasks/main.yml` 的 environment 块加入 `LD_LIBRARY_PATH: /usr/lib64:/opt/microsoft/msodbcsql18/lib64` | `ansible-playbooks/playbooks/roles/db_fact_collect/tasks/main.yml` |
| AWX EE 容器内 collector 返回 `COLLECTOR_ERROR_OPERATIONALERROR: SSL Provider: certificate verify failed: self-signed certificate` | ODBC Driver 18 默认强制 SSL 加密并验证证书；内网 SQL Server 使用自签名证书 | Driver 17 默认 Encrypt=no，Driver 18 改为 Encrypt=yes + 强制校验 | `mssql.py` 连接串加 `TrustServerCertificate=yes;` | `ansible-playbooks/files/collector_client/db_connectors/mssql.py` |
| AWX collector 任务 `--item-json` 参数含特殊字符时命令解析失败 | `cmd:` 格式用单引号包裹 JSON，若 JSON 中含单引号则破坏 bash 参数 | Ansible `command` 的 `cmd:` 按 shell 规则分词 | 改为 `argv:` 列表格式，JSON 作为独立参数直接传递，无 shell 解析 | `ansible-playbooks/playbooks/roles/db_fact_collect/tasks/main.yml` |
| fact_collection 里 Oracle item 不执行或显示缺失 | 凭证绑定链未命中（db_instance/cluster/business_system/network_zone/global） | item 在构建阶段被标记 `CREDENTIAL_MISSING` 并进入 skipped | 先在凭证中心补齐 Oracle binding，再重跑 batch 看 item 是否进入 AWX dispatch | `backend/app/services/credential_resolver_service.py` + `backend/app/services/check_item_builder_registry.py` |
| Oracle 三类事实项都失败并报 `ORA-01017` | AWX 凭证内容错误（用户名/密码或 service_name） | 调度与回写链路正常，但 connector 登录被拒绝 | 修正 AWX 凭证 `cred-db-oracle-ro-prod(id=6)` 后重跑 batch（现象已在 batch_run 91 / AWX job 259 复现） | `ansible-playbooks/files/collector_client/db_connectors/oracle.py` + batch_run `91` |
| 全资产事实采集”都成功但感觉很慢” | `db_fact_collect` 每个 item 都执行多条 Debug 命令并重复 copy collector_client，且 loop 串行 | 单 job 耗时被 debug 与串行执行放大 | ✅ 已修复（2026-06-16 refactor）：主 playbook 预拷贝 collector_client 一次（`has_db_fact_items` 守卫）+ role 删除 Copy/Debug 共 7 个 task；验证 batch 136（3 items SQL Server）40s 较 batch 91 baseline 63s 提速 36%；AWX Job stdout 中 `Pre-copy collector_client` 仅出现 1 次 | `ansible-playbooks/playbooks/dbops_collector_generic.yml` + `ansible-playbooks/playbooks/roles/db_fact_collect/tasks/main.yml` |
| 实例详情"校验资产"提交失败，提示回调地址未配置 | `COLLECTOR_CALLBACK_URL` 是否显式配置；当前请求的 `base_url` 是否可用 | 直接调用内部服务时未传请求基址，或反向代理/Host 头异常导致无法自动回退 | 优先配置 `COLLECTOR_CALLBACK_URL`；若走前端入口，检查代理后重试 | `backend/app/services/collector_service.py:40-50,68-86` |
| 端口校准按钮提示 `不支持的 check_code: PORT_CANDIDATE_REACHABILITY` | 当前后端是否已加载最新 `port_calibration` 分流代码；前端是否仍在发旧 payload | 命中旧后端进程，或旧客户端只传了 `PORT_CANDIDATE_REACHABILITY` 而未被新分流识别 | 重启后端到最新代码；确认前端已加载最新 `InstanceDetail.vue`，并检查 `POST /api/v1/collector/runs` payload 是否含 `run_type=port_calibration` | `backend/app/services/collector_service.py:312-346` + `frontend/src/views/InstanceDetail.vue:681-698` |
| 端口校准里某个候选端口失败后实例状态仍保持未验证 | 该项是否属于候选端口而非已登记/必选端口 | 校准流程只把候选失败记为 `candidate_state=candidate_unreachable`，不会直接把实例改成 missing/offline | 只检查 `candidate_state`、`result_status` 和 `asset_endpoint`；若是已登记/必选端口失败才需要继续排查资产异常 | `backend/app/services/collector_service.py:869-1042` |
| 端口从 1521 切到 1526 后没有生成变更建议 | proposal 是否按单个端口分组了 | 旧逻辑按 `host+port+protocol` 分组，导致同一资产的“当前端口 + 备选端口”没有被放到同一比较集合里 | 现已改为按 `asset_id+host+protocol` 聚合；若再次出现，先看回调是否包含当前端口和备选端口的同一次校准结果 | `backend/app/services/port_calibration_service.py:498-596` |
| Linux 资产的端口校准里出现 3389 候选 | 相关服务器的 OS 族是否能解析出来 | 旧逻辑在 OS 族未知时也会回退到 server 画像，误带入 Windows RDP | 现已改为仅在 OS 族可解析时加入 profile 候选；若仍出现，检查 server 的 `os_version` / `extra_attrs.os_family` | `backend/app/services/port_calibration_service.py:277-309` |
| AWX 回调步骤返回 500 | `asset_change_proposal` 创建后是否已 `flush`，proposal id 是否为空 | 旧实现直接序列化未 flush 的 proposal，`id=None` 导致回调链 500 | 已在 `AssetProposalService.create_proposal()` 里先 `flush()`；若再次出现，先看后端 traceback 是否仍在 proposal 序列化处 | `backend/app/services/asset_proposal_service.py:42-77` |
| batch 仅含 DB_BASIC_FACT_COLLECTION 无 DB_PORT_REACHABILITY 时，AWX Job 成功但 batch 永远 dispatching/launched | Playbook 连通性门控无端口检测项 → `reachable_db_asset_ids=[]` → 所有 DB fact item 被过滤 → callback `items=[]` → 后端 `_callback_items()` 将 `[]` (falsy) 误判为 None 走旧协议 → ValueError → HTTP 400 | `collector_service.py:_callback_items` 用 `if payload.items is not None` 代替 `if payload.items`；`handle_callback` 空列表时把 pending item 标记为 skipped | ✅ 已修复（2026-06-17+2026-06-20）：playbook 门控在无端口检测项时不生效；后端空 items 时写 skipped + 4 个具体 skip_reason code：<br/>• `PORT_CANDIDATE_CONFLICT` — 端口候选冲突无法决定<br/>• `PORT_DRIFT_SUSPECTED` — 端口漂移可疑<br/>• `OS_FACT_UNSUPPORTED_WINDOWS` — Windows OS 跳过 fact<br/>• `CALLBACK_RESULT_MISSING` — callback 缺结果<br/>`CONNECTIVITY_GATE_FAILED` 作为 backward-compat alias 保留 | `ansible-playbooks/playbooks/dbops_collector_generic.yml:155-170` + `backend/app/services/collector_service.py:730-737,937-986` + `backend/app/constants.py` |
| apply 后实例端口改了但校验状态没变 | `apply_proposal()` 是否同时重置 `trust_status/reachability_status` | 旧实现只改 `db_instance.port`，没有把校验状态打回未验证 | 已在 apply 后重置为 `unverified/unknown` 并写入 `verify_detail`；若要最终 verified，需要重新跑校验 | `backend/app/services/asset_proposal_service.py:128-169` |
| asset_verify + DB_BASIC_FACT_COLLECTION 成功但不生成变更建议 | 检查 `asset_fact_snapshot` 是否有对应的 `asset_drift_record`；检查 session 是否 `autoflush=False` | `FactSnapshotService.create_from_collector_result` 只 `db.add` fact values 未 `db.flush()`，而 `DriftDetectionService.detect_for_snapshot` 在同一 session 内用 `db.query` 查 fact values，`autoflush=False` 时返回空 → drift 检测跳过 → 无 proposal | ✅ 已修复：`create_from_collector_result` 末尾增加 `db.flush()` 确保 fact values 写入 DB 后再被 drift detection 查询 | `backend/app/services/fact_snapshot_service.py:86-104` + `backend/app/database.py:21` (autoflush=False) |
| AWX 回调步骤返回 500 且报 `uq_asset_endpoint_identity` | `asset_endpoint` upsert 是否先命中完整 identity，再回退 generic 行 | 旧实现只按 host+port 取第一行，更新 endpoint_type/source 时可能撞上已存在的精确记录 | 已改成先按完整 identity 查找，避免把 generic 记录更新成重复键；若再出现先看 traceback 是否仍在 `collector_service._upsert_endpoint()` | `backend/app/services/collector_service.py:729-796` |
| 实例详情“最近执行记录”显示 Not Found | 先看 `collector` 路由是否存在；再看后端是否为当前代码版本进程 | 后端未重启到包含 `collector` 路由的版本，或命中到其他用户旧进程 | 先验证 `/api/v1/collector/*` 路由是否返回 401（未鉴权）而非 404；必要时只重启当前用户进程 | `backend/app/main.py` + `backend/app/api/collector.py` |
| 前端页面无法访问 `:61088` | Vite 进程是否存活、端口是否监听 | 前端 dev 进程退出或未成功启动 | 重启 `frontend` dev 进程并检查 `ss -lntp | grep 61088` 和 `curl http://127.0.0.1:61088/` | `frontend/vite.config.ts:15-23` |
| AWX EE collector 调用 `--item-json` 报 `libodbc.so.2: cannot open shared object file` | Ansible command 任务缺少 `LD_LIBRARY_PATH` | pyodbc.connect() 触发 unixODBC 动态加载 libmsodbcsql18.so 时找不到 libodbc.so.2 | playbook task environment 块加 `LD_LIBRARY_PATH: /usr/lib64:/opt/microsoft/msodbcsql18/lib64` | `ansible-playbooks/playbooks/roles/db_fact_collect/tasks/main.yml` |
| MSSQL collector 报 `SSL Provider: certificate verify failed: self-signed certificate` | ODBC Driver 18 默认 Encrypt=yes + 强制证书验证 | 内网 SQL Server 使用自签名证书，Driver 18 拒绝连接 | 连接串加 `TrustServerCertificate=yes;` | `ansible-playbooks/files/collector_client/db_connectors/mssql.py` |
| AWX 回调步骤返回 500 且日志显示 `NotNullViolation: null value in column "status" of relation "collector_run_result"` | `backend/app/services/collector_service.py:995-1007` 新建 `CollectorRunResult` 时未设置 `status` 字段 | DB column `status` 有 NOT NULL 约束，但 ORM 构造器未赋值 → `db.flush()` 抛 `IntegrityError` → `except` 块 `db.rollback()` 后查询不到该行 → `raise` 重新抛出 | 在构造器内提前计算并设置 `status`；已修复为 `status=("failed" if candidate_state else (run_item.result_status or callback_item.status))` | `backend/app/services/collector_service.py` + `backend/app/api/collector.py:267` |
| batch/dispatch 的 `created_at` 显示 UTC (07:xx) 而非 CST (15:xx)，与 `updated_at` 不一致 | ORM model `default=datetime.utcnow` 写入 UTC，但 DB trigger `set_updated_at()` 使用 PostgreSQL `now()`（CST） | Python 侧写入 UTC naive 值，PostgreSQL 侧写入 CST naive 值 → 同一行的 `created_at`/`updated_at` 时区不同 | 已修复：模型 defaults 全部改为 `default=datetime.now`（67 处），`_now()` 改为 `datetime.now()`，`collector_tasks.py` 所有显式 `datetime.utcnow()` 改为 `datetime.now()` | `backend/app/models/dbops_assets.py` + `backend/app/services/collector_service.py:_now()` + `backend/app/tasks/collector_tasks.py` |
| timeout_recovery 将刚启动的 job 立即标记为 timeout（< 2 分钟） | `collector_tasks.py` 查询用 `func.now() - interval`（CST）比较 `started_at`（UTC naive） | M14 v1 修复只改了查询端用 CST，但写入端仍用 UTC → CST 15:14 - 30min = 14:44 vs UTC naive 07:12 → `07:12 < 14:44` 恒为 TRUE → 所有新 job 秒级 timeout | 已修复（M14 v2）：写入端全部改为 `datetime.now()`（CST），查询端 `func.now() - interval`（CST），双端对齐 | `backend/app/tasks/collector_tasks.py` + `backend/app/models/dbops_assets.py` |
| 前端 61088 返回 HTML 但 `<div id="app">` 始终空白（Pre-transform error） | curl `/src/main.ts` 看编译后 import 路径是否仍引用已删除/重命名的 `.js` 文件；看 `frontend-dev.log` 是否有 `Pre-transform error: Failed to load url /src/...` | Vite dev server 启动时把 `@/utils/foo`（无后缀）解析到 `foo.js`，运行期 `foo.js` 被删除/重命名后，Vite 模块图缓存不重新解析 → 编译后 main.ts 仍 emit `/src/utils/foo.js` → 浏览器请求 `.js` 拿到 index.html（HTML 200）→ JS 解析失败 → app 永不 mount | 1) `curl -sS http://127.0.0.1:61088/src/main.ts \| grep foo` 找 stale 引用；2) `pkill -f "vite.*61088"`；3) `cd frontend && nohup npx vite --host 0.0.0.0 --port 61088 --strictPort > frontend-dev.log 2>&1 &`；4) 复查 `curl http://127.0.0.1:61088/src/main.ts` import 路径都指向磁盘上存在的文件；5) 浏览器 hard refresh | `frontend/vite.config.ts:15-23` + `frontend/src/main.ts:5` |
| 多 Celery worker 同时 dispatch 导致 per-dispatch commit 提前释放 xact lock | 检查 `pg_locks` 是否有 0x434F4C4C 的 advisory lock 堆积；看 worker 日志是否每 15s 只有一个 `dispatch_scheduler_tick` | v1 使用 `pg_advisory_xact_lock`（xact 级），per-dispatch `db.commit()` 提前释放 → 后续 loop 无保护。v2 改用 `pg_try_advisory_lock`（session 级非阻塞）+ finally 显式 unlock。QueuePool 场景下 `Session.close()` 还连接回池不断 PG 连接，不显式 unlock 会锁泄漏到下个 worker | 查看 `pg_locks WHERE locktype='advisory' AND objid=1129279564` 持续只有 0 或 1 个；若持续 > 1 需重启 worker | `backend/app/tasks/collector_tasks.py:dispatch_scheduler_task` (C1 v2, 批 4) |
| cancel_batch_run 后 batch.status 被 callback 覆盖为 success | 检查 cancel 请求的时间线 vs callback 时间线 | per-row commit 释放初始 FOR UPDATE 锁后，callback 可抢先 finalize batch → cancel 最终无条件写 "cancelled" 覆盖 "success" | v2 在最终 batch re-acquire 后检查 `BATCH_TERMINAL_STATUSES`，若已终态则返回 `detail=already_terminal` 保留原状态 | `backend/app/services/batch_collector_service.py:cancel_batch_run` (C2, 批 4) |
| timeout_recovery 覆盖 callback 已终态的 run | 检查 run.status 是否在 timeout 后又被改回 "timeout" | 旧代码在一次 SELECT FOR UPDATE 中拿候选行后不再重读 status，callback 在 AWX HTTP 调用期间抢先终态 | v2 改 per-row re-select + `RUN_TERMINAL_STATUSES`（canceled 双 L）守卫，AWX error 时 `db.rollback()` 释放锁 | `backend/app/tasks/collector_tasks.py:timeout_recovery_task` (I3+I4, 批 4) |
| asset_fact_snapshot 双写 TOCTOU | 查询是否有同 `(source_run_id, source_item_key)` 的重复行 | PG 默认 NULLS DISTINCT → UNIQUE 约束不覆盖 NULL 列，两条 NULL 行可同时通过 pre-check → double INSERT | v2 合并迁移：DROP full UNIQUE → CREATE PARTIAL UNIQUE INDEX (`WHERE source_run_id IS NOT NULL AND source_item_key IS NOT NULL`) | `backend/db/dbops_phase3_4_batch_verify_p0_4_5_6_v2_partial_unique.sql` (C3+I5, 批 4) |

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

### 3.8 AWX collector 路由自检（防止 Not Found 复发）

```bash
# 1) 未带 JWT 访问 collector 路由
curl -i http://127.0.0.1:60801/api/v1/collector/instances/961/runs

# 预期：
# - 401 = 路由已注册（只是没登录）
# - 404 = 当前后端实例未加载 collector 路由（版本/进程问题）

# 2) 检查 OpenAPI 是否包含 collector 路径
curl -s http://127.0.0.1:60801/openapi.json \
  | grep -E '"/api/v1/collector/instances/\{instance_id\}/runs"|"/api/v1/collector/runs/\{run_id\}"'

# 如果 `/api/v1/collector/runs` 或 `/api/v1/collector/runs/{run_id}/items` 不在 OpenAPI 里，
# 说明 60801 还在跑旧进程，需要用当前代码重启后端再测。

# 如果 AWX job 失败并提示 `role 'port_check' was not found`，
# 检查 `ansible-playbooks/playbooks/roles/port_check/tasks/main.yml` 是否存在，
# 因为 AWX 项目的 playbook 目录只会自动搜索 `playbooks/roles`。
```

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
| 实例详情页显示 `Not Found` 且整页加载失败 | `InstanceDetail.vue` 把“最近执行记录”接口失败（如 `/api/v1/collector/instances/{id}/runs` 返回 404）当成主详情失败处理，导致详情数据被清空 | 将执行记录加载错误与主详情加载解耦：执行记录失败仅显示记录区错误，不影响基础详情展示 | ✅ 已修复 | `frontend/src/views/InstanceDetail.vue` |
| 实例详情“最近执行记录”持续 Not Found | 本机 60801 命中旧后端进程，未加载 collector 路由 | 先做 collector 路由 401/404 判定，再仅重启当前用户后端进程并复查 openapi | ✅ 已处理 | `backend/app/main.py` + `backend/app/api/collector.py` |
| 前端 `http://<host>:61088` 无法访问 | Vite dev 进程退出导致端口无监听 | 启动 `cd frontend && npm run dev -- --host 0.0.0.0 --port 61088`，再用 `curl http://127.0.0.1:61088/` 验证 | ✅ 已处理 | `frontend/vite.config.ts:15-23` |
| `cancel_batch_run` 把已 success 的 dispatch.finished_at 覆盖为 NULL 时间 | 旧实现无差别写 `finished_at`，且终态集合漏 `callback_failed`，导致 cancel 行为破坏 callback 写入的 `finished_at` | 加 `cancelled_at TIMESTAMP` 列（DB 迁移 `dbops_phase3_4_batch_verify_p0_4_5_6_fixups.sql`），cancel 路径只写 `cancelled_at` 不动 `finished_at`；终态集合抽常量 `BATCH_TERMINAL_STATUSES` 统一 | ✅ 已修复 | `batch_collector_service.py:1242,1268` + `dbops_assets.py:1042` + DB schema `cancelled_at` 列 + 索引 `idx_collector_dispatch_run_cancelled_at` |
| 多 Celery worker 并发 tick 突破 `COLLECTOR_GLOBAL_MAX_RUNNING_DISPATCHES` cap | 旧 `dispatch_scheduler_task` 多个 worker 各自读 `precompute_running_counts` + `with_for_update`，无跨 worker 串行化 → 竞态导致超额 launch | tick 入口加 `pg_advisory_xact_lock(0x434F4C4C)`（'COLL'），PG 内置、跨 worker 安全、单 worker 行为不变 | ✅ 已修复 | `backend/app/tasks/collector_tasks.py:230-232` |
| `cancel_batch_run` 把整批 dispatch 一次性 `with_for_update().all()` 锁住，AWX HTTP I/O 全部在长事务里 | callback writer / 其他 worker 在 1000 实例 batch cancel 期间被锁阻塞 | 改为枚举候选 ID（无锁）+ per-row `with_for_update(skip_locked=True).first()` + per-row `db.commit()` 立刻释放 | ✅ 已修复 | `backend/app/services/batch_collector_service.py:1215-1285` |
| `handle_callback` 双 callback TOCTOU 重复插入 `asset_fact_snapshot` | callback 高并发场景下 `existing_snapshot` 预检与 INSERT 之间存在竞态 | 加 DB 级别 `UNIQUE(source_run_id, source_item_key)` 约束 + ORM `UniqueConstraint` 镜像 | ✅ 已修复 | `backend/app/models/dbops_assets.py:1171-1174` + DB 约束 `uq_asset_fact_snapshot_source` |
| db_fact_collect role 每个 item 重复 copy collector_client + 6 段 debug，导致 6 items Job 浪费 72% wall time | 主 playbook `include_role` loop N 次 → role 内 `Copy collector_client from project files` 执行 N 次（11-14s/次），加 6 段 debug 也按 N 倍放大 | 主 playbook 抽 `db_fact_check_codes` + `has_db_fact_items`，预拷贝一次（`/tmp/collector_client`）并 `Verify import`；role 删除 Copy + 6 段 Debug 共 7 task | ✅ 已修复 | `ansible-playbooks/playbooks/dbops_collector_generic.yml`（pre-copy block）+ `playbooks/roles/db_fact_collect/tasks/main.yml`（精简 148→102 行）；BATCH-20260616115042-871686 (id 136) 3 items SQL Server batch_total 40s（AWX Job 32s + 启动 8s），较 batch 91 baseline 63s 提速 36%；AWX Job 333 stdout 确认 `Pre-copy collector_client` 出现 1 次、`Route db_fact_collect items` 仍执行 3 次（DB_BASIC 14 facts + DB_VERSION 8 facts + DB_ROLE 4 facts）、callback status=200 attempts=1、3 fact_snapshot + 26 fact_value 写入 |

## 6. 需现场确认

- `deps.py:20` 中 `tokenUrl="/api/rbac/login"` 是历史遗留还是有意指向（Swagger UI OAuth2 流程暂未使用，影响仅限于 Swagger 文档页的 Authorize 按钮）
- Redis 服务是否在本机 `localhost:6379` 运行且可用（Celery/任务状态依赖 Redis）
- PostgreSQL 连接信息（`10.134.185.85:5432`）是否为当前测试库
- 生产环境 `SECRET_KEY` 是否已从默认值 `dev-secret-key-change-in-production` 变更
- 端口 61088/50801 是其他用户(feng)的实例，排查时注意区分

## 7. Phase 3.5 巡检中心 排障入口

### 7.1 动态 SQL 调度

| 现象 | 优先检查 | 常见根因 | 修复入口 | 代码依据 |
|---|---|---|---|---|
| `POST /api/v1/inspection/items/validate-sql` 返回 400 拒绝 | SQL 是否含写操作关键字 | `readonly_sql_safety` 模块检测到 `INSERT/UPDATE/DELETE/MERGE/DROP/TRUNCATE/CREATE/ALTER/GRANT/REVOKE` | 改写为只读查询；多语句需在 `;` 后换行且每条都需为 SELECT | `backend/app/services/inspection_service.py` (validate_sql) |
| `POST /api/v1/inspection/items/verify-sql` 返回 verify_run 持续 pending | AWX Job 是否调度成功 / collector callback 是否到达 | 任务未真正派发到 AWX / callback URL 配置错 / network 不通 | 检查 `dispatch_status` 状态机；`collector/callback/` 日志 | `backend/app/api/inspection.py:131` + `backend/app/services/inspection_evaluator_service.py` |
| 巡检任务 dispatch 后 batch_run 长期 running 但 callback 不来 | AWX Job 模板 `INSPECTION_SQL_RUN` 是否被覆盖；EE 容器 `LD_LIBRARY_PATH` | 同 §2 collector 排障入口 | 同 §2 | `ansible-playbooks/playbooks/roles/db_fact_collect/tasks/main.yml` |

### 7.2 报告 / 导出

| 现象 | 优先检查 | 常见根因 | 修复入口 | 代码依据 |
|---|---|---|---|---|
| `GET /api/v1/inspection/reports/{id}/instances/{type}/{id}/results` 返回空 | `task_item.db_type` 与 `task_target.db_type` 是否一致；bug5 隔离是否生效 | Oracle/MSSQL 任务目标混排时，过滤后无匹配 | 确认 `inspection_service.get_instance_report_results` 按 db_type 双重过滤；待 v5.1/v5.2 治理稳态后回归 | `backend/app/services/inspection_service.py` (get_instance_report_results) |
| `POST /api/v1/inspection/reports/{id}/export` 报 500 / DOCX 损坏 | 评估引擎是否抛异常；evidence jsonb 是否含 `columns/rows` 键 | `InspectionEvaluatorService` 注入 summary 失败 / 模板渲染异常 | 检查 `report_export_service.build_report_docx`；evidence 缺列时回退到空表 | `backend/app/services/report_export_service.py:build_report_docx` |
| DOCX 导出漏掉实例行 | `inspection_instance_report` 是否都已生成 | 评估未跑 / `regenerate` 端点未调用 | 调用 `POST /api/v1/inspection/reports/{id}/regenerate` 重新生成实例报告 | `backend/app/api/inspection.py:302` |
| 单实例 DOCX 导出按钮点击无反应 | 前端 `InstanceReport.vue` 是否传 `targetType/targetId` | 路由参数缺失 | 检查 `frontend/src/router/index.ts` 路由 `/inspection/reports/:reportId/instances/:targetType/:targetId` | `frontend/src/views/inspection/InstanceReport.vue` + `frontend/src/router/index.ts` |

### 7.3 评估引擎

| 现象 | 优先检查 | 常见根因 | 修复入口 | 代码依据 |
|---|---|---|---|---|
| `inspection_result.result_summary` 为 null | 评估器是否对该 `item_kind` / `evaluator_type` 实现 | 巡检项是 dynamic / custom 但 evaluator 走 baseline 分支 | 检查 `InspectionEvaluatorService` 的 evaluator_type 路由表 | `backend/app/services/inspection_evaluator_service.py` |
| `dispatch_status` 一直 `pending` 不变 | callback 是否真的到达；`pending → running → success` 状态机 | callback 处理事务未提交 | 检查 `inspection_service.handle_callback` 是否抛异常；事务是否 rollback | `backend/app/services/inspection_service.py` (handle_callback) |

### 7.4 DDL 治理

| 现象 | 优先检查 | 常见根因 | 修复入口 | 代码依据 |
|---|---|---|---|---|
| v5.1 重建后历史 inspection 数据丢失 | 备份是否完整；migration 顺序 | v5.1 脚本内含 DROP TABLE（无 CASCADE） | 回滚路径：恢复备份后回退到 3.4 schema；prod 应用前需 DBA 现场评估 | `backend/db/dbops_inspection_v5_1.sql:25-32` |
| v5.2 `inspection_type` 索引失败 | `inspection_item` 表是否已建 | v5.1 未先跑 / v5.2 在 v5.1 之前应用 | 先跑 v5.1 → 再跑 v5.2 | `backend/db/dbops_inspection_v5_2_inspection_type.sql` |
| v5.2 回滚 | `idx_inspection_item_inspection_type` 索引是否存在 | IF EXISTS 防护 | 直接执行 `backend/db/rollback_inspection_v5_2_inspection_type.sql` | `backend/db/rollback_inspection_v5_2_inspection_type.sql` |
