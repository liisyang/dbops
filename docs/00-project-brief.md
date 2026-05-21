# 项目简报

> 文档状态：已校准
> 最近校准：2026-05-21
> 依据来源：真实代码

## 1. 维护定位

本文件只记录项目级事实。

只维护：

1. 系统定位。
2. 技术栈。
3. 启动方式。
4. 关键边界。
5. 重要风险。
6. 需现场确认事项。

不要在本文件维护完整模块清单，模块事实以 `docs/10-module-map.md` 为准。

## 2. 系统定位

**DBOPS** — 数据库运维管理平台，面向 DBA 团队提供：

- **资产管理**：服务器、数据库实例、集群、业务系统、联系人的统一管理与 Excel 导入
- **自动化运维**：主机清单管理、通过 SSH/Ansible 远程执行账号操作（新增用户、改密、用户检查）
- **资产统计**：按 DB 类型、厂区、国家、部署类型等维度统计
- **备份与恢复、SQL 分析、巡检与健康、审计与安全、凭证中心**：前端路由已注册，后端功能待完善

代码依据：

- 应用标题 `"DBOPS API"` v3.0.0（`backend/app/main.py:49`）
- FastAPI 路由涵盖 servers CRUD、instances、clusters、business services、contacts、stats、imports（`backend/app/api/servers.py`）
- 异步账号操作 API（`backend/app/api/account_ops.py`）
- 前端路由覆盖仪表盘、自动化运维、资产管理、备份恢复、SQL 分析、巡检健康、审计安全、凭证中心、知识库（`frontend/src/router/index.ts`）

## 3. 技术栈

| 层 | 技术 | 代码依据 | 备注 |
|---|---|---|---|
| 后端框架 | FastAPI 0.109.0 | `backend/requirements.txt:13` + `backend/app/main.py:8` | |
| 后端服务器 | Uvicorn 0.27.0 | `backend/requirements.txt:14` + `backend/run.py:78` | 端口 60801 |
| ORM | SQLAlchemy 2.0.25 | `backend/requirements.txt:20` + `backend/app/database.py:4-6` | 原生 SQLAlchemy，无 Flask-SQLAlchemy |
| 数据库 | PostgreSQL | `backend/app/config.py:11-15` + `backend/app/database.py:18` (search_path=dbops,public) | 数据库名 dbops，schema：dbops |
| 前端框架 | Vue 3.4 + TypeScript | `frontend/package.json:16,29` + `frontend/src/main.ts:1` | |
| 前端构建 | Vite 5.x | `frontend/package.json:30` + `frontend/vite.config.ts` | |
| UI 样式 | Tailwind CSS 3.4 + Lucide Icons | `frontend/package.json:27,14` + `frontend/tailwind.config.js` | |
| 状态管理 | Pinia 3.x | `frontend/package.json:15` + `frontend/src/main.ts:2,33` | |
| 路由 | Vue Router 4.x | `frontend/package.json:18` + `frontend/src/router/index.ts` | |
| HTTP 客户端 | Axios 1.6 | `frontend/package.json:12` + `frontend/src/api/request.js:1` | 请求拦截器注入 Bearer token |
| 国际化 | vue-i18n 11.x | `frontend/package.json:17` + `frontend/src/main.ts:3,19-30` | 5 语言：zh-CN, zh-TW, en, ja, pt-BR |
| 异步任务 | Celery 5.5.3 + Redis 5.0 | `backend/requirements.txt:5-6` + `backend/app/tasks/queue.py` | Celery worker 有意暂缓启用，当前阶段不需要（`backend/run.py:63`） |
| SSH/自动化 | Paramiko 3.3.1 + Ansible Runner 2.3.6 | `backend/requirements.txt:3,7` + `backend/app/ansible/inventory.py` | |
| 认证 | JWT (python-jose) + bcrypt | `backend/requirements.txt:15,8` + `backend/app/api/deps.py:11-12,21-22` | token 有效期 480 分钟 |
| 测试 | Pytest 7.4 (后端) + Vitest 3.x (前端) | `backend/requirements.txt:23` + `frontend/package.json:31` | |

## 4. 启动方式

### 4.1 后端

```bash
cd backend
source ../.venv/bin/activate
python run.py
# 启动 FastAPI 在 http://0.0.0.0:60801
# Celery worker 当前不自动启动
```

代码依据：`backend/run.py:60-84`

### 4.2 前端

```bash
cd frontend
npm run dev     # Vite 开发服务器，绑定 0.0.0.0
npm run build   # 生产构建（含 vue-tsc 类型检查）
```

代码依据：`frontend/package.json:6-8`

### 4.3 验证脚本

```bash
bash scripts/ai/verify.sh
# 自动检测并运行 JS lint/typecheck/build、Python pytest、shell 语法检查
```

代码依据：`scripts/ai/verify.sh`

## 5. 关键边界

| 边界 | 当前约定 | 代码依据 | 备注 |
|---|---|---|---|
| 前端请求 | `/api` 走 Axios，token 在 localStorage | `frontend/src/api/request.js:2,48-54` | 401 自动跳转 /login |
| 后端 API | FastAPI router，prefix 为 `/api` 系列 | `backend/app/main.py:68-72` | 5 个 router 注册 |
| 数据库 schema | `dbops` schema，单一模型层 | `backend/app/models/dbops_assets.py:24` | |
| 资产服务 | API 层使用 `DbopsAssetService`、`DbopsContactService`、`DbopsImportService`、`DbopsStatsService` | `backend/app/api/servers.py:12-15` | |
| 认证鉴权 | JWT Bearer token，OAuth2PasswordBearer | `backend/app/api/deps.py:20-23` | tokenUrl=/api/rbac/login，开发密钥硬编码 |
| 配置管理 | pydantic-settings + .env 文件 | `backend/app/config.py:2,46` | 已统一为单套配置 |
| 前端状态 | localStorage token + Pinia store | `frontend/src/stores/user.ts` | |

## 6. 重要风险

| 风险 | 影响 | 建议 | 依据 |
|---|---|---|---|
| SECRET_KEY 硬编码默认值 | JWT 可被伪造，所有接口可越权 | 生产环境部署前必须通过环境变量覆盖 | `backend/app/config.py:10` |
| POSTGRES_PASSWORD 硬编码默认值 | 数据库凭据泄露风险 | 生产环境部署前必须通过环境变量覆盖 | `backend/app/config.py:14` |
| SSH_PASSWORD 未配置 | 无法通过密码方式 SSH 连接 | 确认是否仅使用密钥认证，如需密码认证则配置环境变量 | `.env` 中 SSH_PASSWORD 为空 |
| 审计日志 API 为空实现 | /api/logs/list 永远返回 [] | 实现审计模块或移除空路由 | `backend/app/api/logs.py:15` |
| 前端多数二级页面为占位 | 备份/SQL/巡检/审计/凭证页面功能可能不完整 | 核心资产管理收尾后再排期 | `frontend/src/router/index.ts` 路由已注册 |

## 7. 需现场确认

- 前端备份恢复、SQL 分析、巡检健康、审计安全、凭证中心等模块的具体排期（核心资产管理收尾后）
- 生产环境部署前，SECRET_KEY / POSTGRES_PASSWORD / SSH_PASSWORD 必须在环境变量中配置生产值
- SSH 认证方式：仅密钥（当前 `~/.ssh/id_ed25519`）还是需要密码认证？
