# DBOPS 测试环境架构文档

> 生成日期：2026-06-22 | 所有数据均基于真实环境实时验证
> 标注"需现场确认"的为当前无法自动验证的项目

> ⚠️ **注意：AWX (10.134.185.85:30080) 和 Gitea (10.134.181.168:2222/3000) 为测试与正式环境共用。**
> - 操作 AWX 或 Gitea 时需确认影响范围，避免误停服影响另一套环境
> - Gitea 仓库 `lisiyang/ansible-playbooks` 共用 → AWX 两个 Job Template 指向同一 Project，确保 playbook 变更兼容两侧
> - Gitea 仓库 `lisiyang/dbops` 共用 → 正式环境 A3 通过分支/tag 锁定部署版本，开发机 push 前确认不影响生产

---

## 一、机器清单总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DBOPS 测试环境 (3 台)                             │
│                                                                         │
│  ┌─ 10.134.181.168 ────┐   ┌─ 10.134.185.85 ────┐   ┌─ 10.134.182.173 ┐│
│  │                      │   │                     │   │                 ││
│  │ DBOPS Backend :60801│   │ AWX         :30080 │   │ Receptor :27199 ││
│  │ DBOPS Frontend:61088│   │ PostgreSQL  :5432  │   │ SSH      :22    ││
│  │ Celery Worker       │   │ Redis       :6379  │   │ Zabbix   :10050 ││
│  │ Celery Beat         │   │                     │   │                 ││
│  │ Gitea        :2222  │   │                     │   │                 ││
│  │              :3000  │   │                     │   │                 ││
│  └──────────────────────┘   └─────────────────────┘   └─────────────────┘│
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、逐机器详述

### 2.1 10.134.181.168 — DBOPS 主控节点 + Gitea

| 属性 | 值 |
|------|-----|
| IP | 10.134.181.168/22 (ens192) |

#### 2.1.1 DBOPS Backend (FastAPI)

| 项目 | 值 |
|------|-----|
| 端口 | **60801** |
| 进程 | `python run.py` (PID 2113506) |
| 框架 | FastAPI |
| 启动方式 | 开发模式 `python run.py` |
| Celery Worker | 同机，`--pool=solo` (PID 3243664) |
| Celery Beat | 同机 (PID 3243666) |
| Redis 连接 | → 10.134.185.85:6379/0 |
| PostgreSQL 连接 | → 10.134.185.85:5432 |
| AWX API 连接 | → http://10.134.185.85:30080 |
| 回调地址 | `http://10.134.181.168:60801/api/v1/collector/callback/` |

#### 2.1.2 DBOPS Frontend (Vite)

| 项目 | 值 |
|------|-----|
| 端口 | **61088** |
| 进程 | `vite --host 0.0.0.0 --port 61088 --strictPort` (PID 3243777) |
| 框架 | Vue 3 + TypeScript |
| API 代理 | Vite proxy → `localhost:60801` |
| 访问地址 | `http://10.134.181.168:61088/` |

#### 2.1.3 Gitea (Git 服务)

| 项目 | 值 |
|------|-----|
| SSH Git | **:2222** |
| Web UI | **:3000** |
| 仓库 1 | `lisiyang/ansible-playbooks` — AWX sync 源 |
| 仓库 2 | `lisiyang/dbops` — DBOPS 前后端代码（待建） |
| Clone (playbooks) | `ssh://git@10.134.181.168:2222/lisiyang/ansible-playbooks.git` |
| Clone (dbops) | `ssh://git@10.134.181.168:2222/lisiyang/dbops.git`（待建） |
| 数据库 | SQLite |
| Push 命令 | `export GIT_SSH_COMMAND="sudo ssh -i /root/awx_gitea_key -o IdentitiesOnly=yes -p 2222"` |

#### 2.1.4 Celery 异步任务

| 项目 | 值 |
|------|-----|
| Broker | Redis `redis://10.134.185.85:6379/0` |
| Result Backend | Redis（同上） |
| Worker | solo pool，单进程 |
| Beat | 定时调度器 |
| 注册任务模块 | `app.tasks.account_tasks`, `app.tasks.collector_tasks` |

#### 2.1.5 其他实例（非本环境）

| 项目 | 端口 | 说明 |
|------|------|------|
| feng 的 dbops | 51088 / 50801 | 其他用户环境，不要干预 |

---

### 2.2 10.134.185.85 — AWX + PostgreSQL + Redis

#### 2.2.1 AWX

| 项目 | 值 |
|------|-----|
| 端口 | **30080** |
| URL | `http://10.134.185.85:30080` |
| 用户名 | admin |
| Job Template ID | **10** |
| Job Template 名称 | JT_DBOPS_COLLECTOR_GENERIC_TEST |
| Project ID | **8** |
| Project 名称 | ansible-playbooks |
| SCM URL | `ssh://git@10.134.181.168:2222/lisiyang/ansible-playbooks.git` |
| EE ID | **3** |
| EE 镜像 | awx-ee-dbops:24.6.1 |
| Instance Group | IG_LOCAL_LH_TEST (id=3) |
| Prebound Credential | ID #4（SSH 密钥） |
| AWX 自身数据库 | 需现场确认（内置 PG 还是外部？） |

#### 2.2.2 PostgreSQL

| 项目 | 值 |
|------|-----|
| 端口 | **5432** |
| 版本 | PostgreSQL 17.9 |
| 数据库 | dbops |
| 用户 | dbops |
| Schema | dbops |
| 业务表 | 0（public schema 中无表，需确认 schema 结构） |
| DDL 文件 | `backend/db/dbops_phase3_3a.sql` |

#### 2.2.3 Redis

| 项目 | 值 |
|------|-----|
| 端口 | **6379** |
| 连接状态 | PONG ✅ |
| Key 数量 | 7203 |
| DB 编号 | 0 |
| 用途 | Celery Broker + Result Backend |

---

### 2.3 10.134.182.173 — 远程 Execution Node

| 属性 | 值 |
|------|-----|
| IP | 10.134.182.173 |
| SSH 登录 | `ssh root@10.134.182.173` (免密) |

#### 2.3.1 运行服务

| 端口 | 服务 | 说明 |
|------|------|------|
| **27199** | Receptor | AWX Mesh 任务接收入口，二进制路径 `/usr/local/bin/receptor` |
| **22** | SSH | Ansible 执行 + 管理登录 |
| 10050 | Zabbix Agent | 监控，非 DBOPS |

#### 2.3.2 采集执行过程

AWX 下发 Job 到 Receptor 后，EE 容器内执行 playbook，临时使用 collector_client：

```
collector_client/
├── cli.py                  # 采集 CLI 入口
├── db_connectors/          # MySQL/Oracle/PostgreSQL/Redis/Mongo 连接器
├── os_connectors/          # CPU/Memory/Disk/NIC 采集器
├── result_builder.py       # 采集结果构建与回调
├── env_loader.py           # 环境变量加载
└── schemas.py              # 数据模型
```

Playbook 入口：`playbooks/dbops_collector_generic.yml`
Roles：
- `roles/port_check/tasks/main.yml`
- `roles/db_fact_collect/tasks/main.yml`
- `roles/os_fact_collect/tasks/main.yml`

---

## 三、网络连通性矩阵

| 源 | → | 目标 | 端口 | 用途 | 状态 |
|---|:-:|------|------|------|:--:|
| 10.134.181.168 (Backend) | → | 10.134.185.85 | 5432 | PostgreSQL 读写 | ✅ |
| 10.134.181.168 (Backend) | → | 10.134.185.85 | 6379 | Redis 队列/缓存 | ✅ |
| 10.134.181.168 (Backend) | → | 10.134.185.85 | 30080 | AWX API 调用 | ✅ |
| 10.134.181.168 (用户) | → | 10.134.181.168 | 61088 | DBOPS Frontend | ✅ |
| 10.134.181.168 (用户) | → | 10.134.181.168 | 2222 | Gitea Git | ✅ |
| 10.134.185.85 (AWX) | → | 10.134.181.168 | 2222 | Git Clone playbook | ✅ |
| 10.134.185.85 (AWX) | → | 10.134.182.173 | 27199 | Receptor 任务下发 | ✅ |
| 10.134.185.85 (AWX) | → | 10.134.182.173 | 22 | Ansible SSH 执行 | ✅ |
| 10.134.182.173 (Exec) | → | 10.134.181.168 | 60801 | 采集结果回调 | ✅ |

---

## 四、批量校验数据流

```
 用户操作 (Frontend :61088)
          │ POST /api/v1/verify/batch
          ▼
 DBOPS Backend (:60801) ───── 入队 ────→ Redis (:6379)
                                          │
                                    ┌─────┘
                                    ▼
                             Celery Worker (同机 :168)
                                    │
                                    │ POST /api/v2/job_templates/10/launch/
                                    ▼
                             AWX (:30080)
                                    │
                              ┌─────┴─────┐
                              │ Gitea :2222│ ← sync playbook
                              └───────────┘
                                    │
                                    │ Receptor :27199
                                    ▼
                             Execution Node (:173)
                               └─ Receptor 接收
                               └─ EE 容器启动
                               └─ dbops_collector_generic.yml
                                  ├─ port_check role
                                  ├─ db_fact_collect role
                                  ├─ os_fact_collect role
                                  └─ collector_client result_builder
                                    │
                                    │ HTTP POST callback
                                    ▼
                             DBOPS Backend :60801
                             POST /api/v1/collector/callback/
                                    │
                              ┌─────┴─────┐
                              │ PostgreSQL │ ← 写入结果
                              └───────────┘
                                    │
                              ┌─────┴─────┐
                              │  Redis    │ ← 更新 Celery 任务状态
                              └───────────┘
                                    │
                                    │ WebSocket / Polling
                                    ▼
                             Frontend :61088 展示结果
```

### 关键设计点

| 机制 | 说明 |
|------|------|
| Celery 队列 | Backend → Redis → Worker，解耦下发与执行 |
| 执行节点直连回调 | 采集结果不经过 Redis/AWX，Execution Node 直接 POST 到 Backend :60801 |
| 两阶段门控 | port check reachable → 才进入 db/os fact collect，不通写 skip reason |
| SAVEPOINT 保护 | DB 连接检查不污染业务事务 |
| block/rescue/always | Playbook 异常也确保回调触发 |
| Prebound Credential | SSH 密钥在 AWX Job Template 预绑定，无需每次传递 |

---

## 五、配置文件位置

| 文件 | 路径 |
|------|------|
| Backend .env | `/home/lisiyang/dbops/backend/.env` |
| Frontend .env | `/home/lisiyang/dbops/frontend/.env` |
| 数据库 DDL | `/home/lisiyang/dbops/backend/db/dbops_phase3_3a.sql` |
| Playbook 入口 | `/home/lisiyang/ansible-playbooks/playbooks/dbops_collector_generic.yml` |
| port_check role | `/home/lisiyang/ansible-playbooks/playbooks/roles/port_check/tasks/main.yml` |
| db_fact_collect role | `/home/lisiyang/ansible-playbooks/playbooks/roles/db_fact_collect/tasks/main.yml` |
| os_fact_collect role | `/home/lisiyang/ansible-playbooks/playbooks/roles/os_fact_collect/tasks/main.yml` |
| collector_client (playbook内) | `/home/lisiyang/ansible-playbooks/files/collector_client/` |
| collector_client (源码) | `/home/lisiyang/dbops-collector/collector_client/` |
| EE 镜像 | `/home/lisiyang/awx-ee-dbops-v2.tar` |
| Celery 配置 | `/home/lisiyang/dbops/backend/app/tasks/queue.py` |

---

## 六、关联仓库

| 仓库 | 托管于 | Clone 地址 | 用途 |
|------|--------|------------|------|
| ansible-playbooks | Gitea | `ssh://git@10.134.181.168:2222/lisiyang/ansible-playbooks.git` | AWX Project sync |
| dbops | GitHub → Gitea | `ssh://git@10.134.181.168:2222/lisiyang/dbops.git`（待建） | A3 部署 Clone 源 |

> **dbops 同步链路**：GitHub → 开发机 (10.134.181.168) `git pull` → `git push gitea` → A3 新机器 `git clone` 内网部署
>
> **ansible-playbooks 发布流程**：开发机 `git push gitea`（`sudo ssh -i /root/awx_gitea_key -p 2222`）→ AWX Project #8 sync

---

## 七、正式环境架构（TO-BE）

### 7.1 机器分配

```
╔══════════════════════════════════════════════════════════════════════════╗
║                     网段 A: App/Web Tier (3 台)                          ║
║                                                                          ║
║  ┌─ A1: 10.134.185.85 (复用现有) ────────────────────────────────────┐  ║
║  │  AWX :30080                                                       │  ║
║  │  PostgreSQL 和 Redis 迁出 → 网段 B / A3                           │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                                                                          ║
║  ┌─ A2: 10.134.181.168 (复用现有) ────────────────────────────────────┐  ║
║  │  Gitea :2222/:3000/:80/:443                                       │  ║
║  │  旧 DBOPS 前后端 (开发/过渡使用)                                    │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                                                                          ║
║  ┌─ A3: 新机器 (待分配 IP) ─────────────────────────────────────────┐  ║
║  │  DBOPS Backend     :60801   (FastAPI + Gunicorn + systemd)        │  ║
║  │  DBOPS Frontend    (Nginx 静态托管)                                │  ║
║  │  Celery Worker              (异步任务)                             │  ║
║  │  Celery Beat                (定时调度)                             │  ║
║  │  Redis             :6379    (localhost, Celery Broker + Backend)   │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
                              │                              │
                    A3→B3:5432                A1→B1/B2:27199 + :22
                              │                              │
                              ▼                              ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                     网段 B: Data/Execution Tier (3 台)                    ║
║                                                                          ║
║  ┌─ B1: Execution Node 1 (待分配 IP) ────────────────────────────────┐  ║
║  │  Receptor :27199                                                   │  ║
║  │  SSHD :22                                                          │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                                                                          ║
║  ┌─ B2: Execution Node 2 (待分配 IP) ────────────────────────────────┐  ║
║  │  Receptor :27199                                                   │  ║
║  │  SSHD :22                                                          │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                                                                          ║
║  ┌─ B3: PostgreSQL (待分配 IP) ──────────────────────────────────────┐  ║
║  │  PostgreSQL :5432                                                   │  ║
║  │  DDL + 数据迁移由用户自行完成                                        │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### 7.2 跨网段防火墙白名单

| # | 方向 | 源 | 目标 | 端口 | 用途 |
|---|------|----|------|------|------|
| 1 | A→B | A3 (新 DBOPS) | B3 (PG) | **5432** | 业务数据读写 |
| 2 | A→B | A1 (AWX) | B1 (Exec1) | **27199** | Receptor 任务下发 |
| 3 | A→B | A1 (AWX) | B1 (Exec1) | **22** | Ansible SSH 执行 |
| 4 | A→B | A1 (AWX) | B2 (Exec2) | **27199** | Receptor 任务下发 |
| 5 | A→B | A1 (AWX) | B2 (Exec2) | **22** | Ansible SSH 执行 |
| 6 | B→A | B1/B2 (Exec) | A3 (新 DBOPS) | **60801** | 采集结果回调 |

> Redis 在 A3 本机 localhost，Celery 走本地零延迟，不涉及跨网段。
> Gitea 在 A2，AWX 在 A1，同网段 sync，不涉及跨网段。

### 7.3 .env 配置变更

| 变量 | 测试环境 | 正式环境 (A3) |
|------|---------|--------------|
| POSTGRES_HOST | 10.134.185.85 | **B3 IP** |
| REDIS_URL | 10.134.185.85:6379 | **localhost:6379** |
| AWX_URL | 10.134.185.85:30080 | **10.134.185.85:30080** (A1，同段) |
| COLLECTOR_CALLBACK_URL | 10.134.181.168:60801 | **A3 IP:60801** |

### 7.4 迁移后数据流

> A3 部署源码来源：`git clone ssh://git@10.134.181.168:2222/lisiyang/dbops.git`（Gitea 内网）
> 日常更新：开发机 GitHub → `git push gitea` → A3 `git pull`

```
 用户 → A3 Frontend
           │
           ▼
  A3 Backend (:60801) ──入队──→ A3 Redis (localhost:6379)
           │                        │
           │                   ┌────┘
           │                   ▼
           │            A3 Celery Worker
           │                   │
           │                   │ POST AWX API
           │                   ▼
           │            A1 AWX (:30080)
           │                   │
           │              ┌────┴────┐
           │              │ A2 Gitea│ ← sync playbook + dbops 代码 (同网段)
           │              └─────────┘
           │                   │
           │              Receptor :27199
           │              SSH :22
           │                   │
           │                   ▼
           │            B1/B2 Execution Nodes
           │              └─ EE 容器 + collector_client
           │                   │
           │              HTTP POST callback
           │                   │
           └───────────────────┘
                      ▼
  A3 Backend ← 采集结果直连回调 :60801
           │
           ▼
  B3 PostgreSQL ← 写入结果
```

### 7.5 迁移步骤

| # | 步骤 | 说明 |
|---|------|------|
| 0 | Gitea 建 `lisiyang/dbops` 仓库 + 添加 remote push | 开发机 `git remote add gitea` → push main |
| 1 | B3 部署 PostgreSQL，用户自行迁移 DDL + 数据 | 用户负责 |
| 2 | A3 部署 Redis，配置密码 | 安装 → 改 bind → 改 requirepass |
| 3 | A3 `git clone` Gitea dbops → 部署 Backend (gunicorn + systemd) | `.env` 指向 B3 PG + localhost Redis |
| 4 | A3 部署 Frontend (vite build + Nginx) | 反向代理 → Backend :60801 |
| 5 | A3 启动 Celery Worker + Beat | 连接 localhost Redis |
| 6 | B1/B2 安装 Receptor → 注册到 AWX Instance Group | `install_receptor.yml` |
| 7 | AWX 更新 Project、EE、Instance Group | Project sync 仍走 A2 Gitea |
| 8 | 防火墙放通 6 条规则 | 按 7.2 表 |
| 9 | 端到端验证 — 批量校验流程 | 触发 Job → 采集 → 回调 → 入库 |
