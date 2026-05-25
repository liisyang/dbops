#!/usr/bin/env bash
set -euo pipefail

# Purpose:
#   Initialize AI Coding Governance v1.1 files for a repository.
#
# Usage:
#   bash scripts/bootstrap/init-ai-governance-v1.1.sh
#   bash scripts/bootstrap/init-ai-governance-v1.1.sh --help

show_usage() {
  cat <<'USAGE'
Usage:
  bash scripts/bootstrap/init-ai-governance-v1.1.sh

This script creates:
  - CLAUDE.md
  - AGENTS.md
  - .github/copilot-instructions.md
  - .github/agents/*
  - .claude/settings.json
  - .claude/skills/*
  - .claude/agents/*
  - docs/*
  - scripts/ai/guard.sh
  - scripts/ai/verify.sh
  - .github/pull_request_template.md
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  show_usage
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "[ERROR] Unknown argument: $*" >&2
  show_usage >&2
  exit 1
fi

echo "[INFO] Create AI Coding Governance v1.1"

write_file() {
  local file="$1"
  mkdir -p "$(dirname "$file")"
  cat > "$file"
  echo "[OK] wrote $file"
}

write_exec_file() {
  local file="$1"
  write_file "$file"
  chmod +x "$file"
  echo "[OK] chmod +x $file"
}

backup_file() {
  local file="$1"
  if [ -f "$file" ] && [ ! -f "$file.v1.1.backup" ]; then
    cp "$file" "$file.v1.1.backup"
    echo "[OK] backup $file to $file.v1.1.backup"
  fi
}

backup_file CLAUDE.md
backup_file AGENTS.md

mkdir -p .claude/skills/{docs-bootstrap,docs-sync,bug-fix,feature-dev,refactor,frontend-optimize}
mkdir -p .claude/agents
mkdir -p .github/agents
mkdir -p docs/{contracts,db,_archive}
mkdir -p scripts/ai
mkdir -p .github

write_file CLAUDE.md <<'EOT'
# CLAUDE.md

本仓库使用 Claude Code 辅助开发。本文件只放长期强约束，不放一次性任务。

## 1. AI Coding v1.1 总原则

1. 真实代码优先，文档只做辅助。
2. 新项目只初始化治理框架，不强行补齐不存在的基线。
3. 开发中项目首次接入时补齐一次 baseline。
4. 日常开发只描述任务目标。
5. AI 自动判断是否更新、追加或删除 docs 内容。
6. 默认只读 2 个核心文档。
7. 按任务类型增量读取相关文档。
8. 文档职责单一，避免重复维护。
9. DB 文档由 AI 自动维护，但只允许查询结构元数据。
10. AI 不查询业务表数据。
11. AI 不记录账号、密码、连接串、Token。
12. Hook 只做 P0 极高危兜底。
13. verify.sh 是统一基础验证入口。
14. 所有不确定内容必须标注“需现场确认”。

## 2. 长期开发规则

1. 以真实代码为准，不根据旧文档或历史记忆直接修改。
2. 修改前必须确认影响范围：page / api / service / model / table。
3. 优先复用现有实现，不新增重复页面、重复接口、重复 service、重复组件。
4. 前端请求统一走 `src/api/*` 或当前项目已确认的统一请求封装。
5. 后端 API 层不堆业务逻辑，业务逻辑放 service。
6. 文档与代码不一致时，以代码为准。
7. 不做无意义扩大修改范围。
8. 不通过绕过问题的方式修 Bug。
9. 涉及删除、批量更新、迁移、权限、密钥、生产配置时，必须先说明风险。
10. P0 极高危操作不得自动执行。
11. 修改完成后优先执行 `bash scripts/ai/verify.sh`。
12. 文档更新必须有代码依据。
13. 前端不硬编码状态颜色、状态文案、枚举值。
14. 不写大段内联样式。
15. 重复结构优先抽公共组件。
16. Bug 修复必须先定位根因。
17. 重构不能改变业务行为。
18. 完成后必须说明改动、文件、原因、影响范围、验证方式和风险。

## 3. 默认文档读取规则

普通任务默认只读：

- docs/00-project-brief.md
- docs/10-module-map.md

新功能开发额外读：

- docs/20-delivery-board.md

Bug / 排障任务额外读：

- docs/30-runbook.md
- docs/40-tech-debt.md

重构任务额外读：

- docs/40-tech-debt.md

前端任务额外读：

- docs/frontend-guide.md

涉及接口变化才读：

- docs/contracts/README.md
- docs/contracts/api-inventory.md

涉及数据库变化才读：

- docs/db/README.md
- docs/db/ddl-history.md
- docs/db/schema-snapshot.md

归档文档默认不读：

- docs/_archive/*

## 4. 文档自动维护规则

日常开发中，用户不需要手动要求更新 docs。

AI 在每次 feature-dev / bug-fix / refactor / frontend-optimize 完成后，必须自动判断是否需要更新、追加或删除相关文档内容。

规则：

1. 只基于真实代码更新文档。
2. 不把计划写成已完成。
3. 不确定内容标注“需现场确认”。
4. 不涉及的文档不得强行更新。
5. 删除文档内容必须确认该内容已不再被真实代码支持。
6. API 文档只记录真实存在的接口和调用，不凭猜测补全。
7. Runbook 只记录真实可验证的排障入口，不编造历史故障。
8. Tech Debt 只记录真实代码中可确认的问题，不记录个人偏好。
9. DB 文档只能记录结构元数据，不记录业务数据、账号、密码、连接串、Token。
10. DB 文档由 AI 自动维护，人工不手动维护。

## 5. DB 自动维护规则

AI 可以连接指定测试库 / 开发库，自行生成只读元数据 SQL 查询数据库结构。

允许查询：

1. schema
2. table
3. column
4. index
5. constraint
6. view
7. sequence
8. database version
9. current schema / current database

禁止查询：

1. 业务表数据。
2. 任意 `SELECT * FROM 业务表`。
3. INSERT / UPDATE / DELETE / MERGE。
4. DROP / TRUNCATE。
5. 未经确认的 ALTER / CREATE。
6. 生产库连接信息。
7. 账号、密码、连接串、Token。

## 6. 推荐入口

新项目：

- `/init`
- `/docs-bootstrap`

开发中项目首次接入：

- `/init`
- `/docs-bootstrap all`
- `/docs-sync docs/contracts/api-inventory.md`
- `/docs-sync docs/contracts/README.md`
- `/docs-sync docs/db/ddl-history.md`
- `/docs-sync docs/db/schema-snapshot.md`
- `/docs-sync docs/db/README.md`
- `/docs-sync docs/frontend-guide.md`
- `/docs-sync docs/40-tech-debt.md`
- `/docs-sync docs/30-runbook.md`

日常开发：

- `/feature-dev`
- `/bug-fix`
- `/refactor`
- `/frontend-optimize`
EOT

write_file AGENTS.md <<'EOT'
# AGENTS.md

本文件适用于 Claude Code、Codex、Cursor、Copilot Agent、Windsurf 等 AI Coding Agent。

## 1. 基本原则

1. 真实代码优先，文档仅作辅助。
2. 修改前确认 page / api / service / model / table。
3. 优先复用已有实现。
4. 不新增重复实现。
5. 不随意扩大修改范围。
6. 不绕过问题做临时补丁。
7. 高风险操作必须说明风险。
8. 文档必须基于真实代码。
9. 不确定内容必须标注“需现场确认”。

## 2. v1.1 工作模式

### 2.1 新项目

只初始化治理框架和最小事实。

不得强行生成不存在的 API / DB / 前端 / 排障 / 技术债基线。

### 2.2 开发中项目首次接入

首次接入时允许集中补齐一次基线。

baseline 提交后，后续进入日常开发自动维护模式。

### 2.3 日常开发

用户只描述任务目标。

AI 必须在任务完成后自动判断是否更新、追加或删除相关 docs 内容。

## 3. 必读文档

默认任务只读：

- docs/00-project-brief.md
- docs/10-module-map.md

新功能开发额外读：

- docs/20-delivery-board.md

Bug / 排障任务额外读：

- docs/30-runbook.md
- docs/40-tech-debt.md

重构任务额外读：

- docs/40-tech-debt.md

前端任务额外读：

- docs/frontend-guide.md

涉及接口变化才读：

- docs/contracts/README.md
- docs/contracts/api-inventory.md

涉及表、字段、索引、约束、Model、Repository、Mapper、SQL 查询变化才读：

- docs/db/README.md
- docs/db/ddl-history.md
- docs/db/schema-snapshot.md

归档文档默认不读：

- docs/_archive/*

## 4. 文档自动维护规则

开发任务完成后，AI 必须判断是否需要更新相关 docs。

1. 系统定位、技术栈、启动方式、关键边界变化：更新 `docs/00-project-brief.md`。
2. page / api / service / model / table 关系变化：更新 `docs/10-module-map.md`。
3. 功能交付状态、阻塞项、下个迭代建议变化：更新 `docs/20-delivery-board.md`。
4. Bug 排查路径、故障入口、已确认问题变化：更新 `docs/30-runbook.md`。
5. 重复实现、旧架构残留、不一致实现、潜在风险变化：更新 `docs/40-tech-debt.md`。
6. 前端页面结构、组件复用、表格、表单、状态展示、样式规则变化：更新 `docs/frontend-guide.md`。
7. 接口路径、请求参数、响应结构、错误码、前后端契约变化：更新 `docs/contracts/README.md` 和 `docs/contracts/api-inventory.md`。
8. 表、字段、索引、约束变化：更新 `docs/db/ddl-history.md`、`docs/db/schema-snapshot.md`、`docs/db/README.md`。
9. `docs/_archive/*` 默认不维护。

## 5. 交付输出

每次完成任务后输出：

1. 改了什么
2. 修改了哪些文件
3. 为什么这样改
4. 影响了哪些模块
5. 更新了哪些文档
6. 哪些文档未更新及原因
7. 如何验证
8. 是否还有风险或后续建议

涉及 DB 时额外输出：

1. 涉及哪些表
2. 是否需要 DDL
3. 生成或追加了哪些 DDL
4. 是否更新 `docs/db/ddl-history.md`
5. 是否更新 `docs/db/schema-snapshot.md`
6. 是否更新 `docs/db/README.md`
7. 实际执行的只读元数据 SQL
8. 风险和需现场确认事项

## 6. P0 极高危操作

以下操作不得由 AI 自动执行：

- `rm -rf /`
- `rm -rf /*`
- `mkfs`
- `dd` 写磁盘
- `DROP DATABASE`
- `DROP SCHEMA`
- `DROP TABLE`
- `TRUNCATE`
- `git push --force`
- `git reset --hard`
- `kubectl delete`
- `docker rm -f`
EOT

write_file .github/copilot-instructions.md <<'EOT'
# Copilot Instructions

This repository uses `AGENTS.md` and `CLAUDE.md` as the canonical shared instructions.

- Follow `AGENTS.md` first for repository-wide rules.
- Follow `CLAUDE.md` for Claude-specific governance details that also apply here.
- Do not duplicate or fork repo rules in additional instruction files unless the tool requires it.
EOT

write_file docs/00-project-brief.md <<'EOT'
# 项目简报

> 文档状态：初始模板  
> 最近校准：待校准  
> 依据来源：待确认

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

需基于真实代码确认。

## 3. 技术栈

| 层 | 技术 | 代码依据 | 备注 |
|---|---|---|---|
| 后端 | 待确认 | 待确认 |  |
| 前端 | 待确认 | 待确认 |  |
| 数据库 | 待确认 | 待确认 |  |
| 异步任务 | 待确认 | 待确认 |  |
| 自动化 / 运维 | 待确认 | 待确认 |  |
| 构建 / 包管理 | 待确认 | 待确认 |  |

## 4. 启动方式

### 4.1 后端

```bash
待基于真实代码确认
```

### 4.2 前端

```bash
待基于真实代码确认
```

### 4.3 其他服务

```bash
待基于真实代码确认
```

## 5. 关键边界

| 边界 | 当前约定 | 代码依据 | 备注 |
|---|---|---|---|
| 前端请求 | 待确认 | 待确认 |  |
| 后端 API | 待确认 | 待确认 |  |
| 业务 service | 待确认 | 待确认 |  |
| 数据库 schema | 待确认 | 待确认 |  |
| 认证鉴权 | 待确认 | 待确认 |  |
| 配置管理 | 待确认 | 待确认 |  |

## 6. 重要风险

| 风险 | 影响 | 建议 | 依据 |
|---|---|---|---|

## 7. 需现场确认

-
EOT

write_file docs/10-module-map.md <<'EOT'
# 模块图

> 文档状态：初始模板  
> 最近校准：待校准  
> 依据来源：待确认

## 1. 维护定位

本文件是模块事实源。

只维护：

1. 模块总览。
2. page / api / service / model / table 对应关系。
3. 主要调用链。
4. 缺失链路。
5. 需现场确认事项。

## 2. 模块总览

| 模块 | 当前状态 | 说明 | 代码依据 |
|---|---|---|---|

## 3. page / api / service / model / table 对应关系

| 模块 | Page | Frontend API | Backend API | Service | Model | Table | 状态 | 代码依据 |
|---|---|---|---|---|---|---|---|---|

## 4. 主要调用链

```text
Page
→ Frontend API
→ Backend API
→ Service
→ Model
→ Table
```

## 5. 缺失链路

| 模块 | 缺失环节 | 影响 | 建议 | 依据 |
|---|---|---|---|---|

## 6. 需现场确认

-
EOT

write_file docs/20-delivery-board.md <<'EOT'
# 交付看板

> 文档状态：初始模板  
> 最近校准：待校准  
> 依据来源：待确认

## 1. 维护定位

本文件只记录当前交付判断和下一步行动。

已完成模块以 `docs/10-module-map.md` 为准。

## 2. 当前结论

需基于真实代码确认。

1.
2.
3.

## 3. 当前阻塞项

| 优先级 | 问题 | 影响 | 处理建议 | 依据 |
|---|---|---|---|---|
| P0 |  |  |  |  |
| P1 |  |  |  |  |
| P2 |  |  |  |  |

## 4. 部分完成事项

| 功能 | 已有代码 | 缺口 | 建议下一步 | 依据 |
|---|---|---|---|---|

## 5. 下个迭代建议

| 顺序 | 任务 | 原因 | 验证方式 |
|---|---|---|---|

## 6. 需现场确认

-
EOT

write_file docs/30-runbook.md <<'EOT'
# 排障手册

> 文档状态：初始模板  
> 最近校准：待校准  
> 依据来源：待确认

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

| 现象 | 优先检查 | 常见根因 | 修复入口 |
|---|---|---|---|
| 前端 401 | 待确认 | 待确认 | 待确认 |
| 前端 403 | 待确认 | 待确认 | 待确认 |
| 后端 500 | 待确认 | 待确认 | 待确认 |
| 数据库连接失败 | 待确认 | 待确认 | 待确认 |
| 表不存在 / schema 错误 | 待确认 | 待确认 | 待确认 |

## 3. 标准排查命令

### 3.1 后端健康检查

```bash
curl -i http://127.0.0.1:<port>/api/health || true
```

### 3.2 端口检查

```bash
ss -lntp | grep <port> || true
```

### 3.3 前端构建检查

```bash
npm run build
```

### 3.4 Shell 脚本语法检查

```bash
find scripts -type f -name "*.sh" -print0 | xargs -0 -I{} bash -n {}
```

## 4. 已确认问题

| 问题现象 | 根因 | 修复建议 | 状态 | 代码依据 |
|---|---|---|---|---|

## 5. 需现场确认

-
EOT

write_file docs/40-tech-debt.md <<'EOT'
# 技术债 Backlog

> 文档状态：初始模板  
> 最近校准：待校准  
> 依据来源：待确认

## 1. 维护定位

本文件只记录真实代码中能确认的技术债。

不记录个人偏好。

## 2. 总览

| 等级 | 数量 | 说明 |
|---|---:|---|
| High | 0 | 待确认 |
| Medium | 0 | 待确认 |
| Low | 0 | 待确认 |

## 3. 技术债清单

| 等级 | 问题 | 位置 | 影响范围 | 建议处理 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|

## 4. 暂不处理项

| 问题 | 暂不处理原因 | 重新评估条件 |
|---|---|---|

## 5. 需现场确认

-
EOT

write_file docs/frontend-guide.md <<'EOT'
# 前端开发约定

> 文档状态：初始模板  
> 最近校准：待校准  
> 依据来源：待确认

## 1. 维护定位

本文件只记录当前项目真实前端约定。

不要写成前端教程。

当前事实和建议必须分开。

## 2. 必须遵守

1. 页面请求必须走统一 API 封装。
2. 列表页优先复用现有页面容器、筛选区、表格壳组件。
3. 表单优先复用现有弹窗、抽屉或表单模式。
4. 空值展示必须统一。
5. 操作按钮必须避免触发行点击副作用。
6. 不直接硬编码业务枚举。
7. 不写大段内联 style。
8. 不新增重复 API 封装。

## 3. 推荐复用

| 场景 | 优先复用 | 代码依据 |
|---|---|---|
| 页面容器 | 待确认 | 待确认 |
| 筛选区 | 待确认 | 待确认 |
| 表格 | 待确认 | 待确认 |
| 表单 | 待确认 | 待确认 |
| 弹窗 | 待确认 | 待确认 |
| 抽屉 | 待确认 | 待确认 |
| 空态 | 待确认 | 待确认 |
| 状态展示 | 待确认 | 待确认 |

## 4. 当前不一致点

| 问题 | 位置 | 影响 | 建议 | 代码依据 |
|---|---|---|---|---|

## 5. 需现场确认

-
EOT

write_file docs/contracts/README.md <<'EOT'
# API 契约附录

> 文档状态：按需维护  
> 最近校准：待校准  
> 依据来源：待确认

## 1. 维护定位

本文件不追求全量接口文档。

只记录：

1. 跨模块核心接口。
2. 近期新增或变更接口。
3. 前后端契约容易不一致的接口。
4. 第三方系统对接接口。
5. 本次任务涉及的接口。

全量或阶段性接口盘点见：

- `docs/contracts/api-inventory.md`

## 2. 核心接口摘要

| 模块 | 方法 | 路径 | 调用页面 | 前端封装 | 后端入口 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|---|

## 3. 高风险契约

| 模块 | 契约风险 | 影响 | 建议 | 依据 |
|---|---|---|---|---|

## 4. 需现场确认

-
EOT

write_file docs/contracts/api-inventory.md <<'EOT'
# API Inventory

> 文档状态：初始模板  
> 最近校准：待校准  
> 依据来源：待确认

## 1. 维护定位

本文件记录当前代码中可确认的 API 清单。

本文件用于首次接入和阶段性盘点。

日常接口变化时，由 AI 自动追加、修改或删除相关条目。

## 2. 后端 API 清单

| 模块 | 方法 | 路径 | 后端入口 | Service | 认证要求 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|---|

## 3. 前端 API 封装清单

| 模块 | 前端封装 | 方法 | 路径 | 调用页面 | 状态 | 代码依据 |
|---|---|---|---|---|---|---|

## 4. 前后端契约不一致

| 模块 | 前端调用 | 后端接口 | 不一致点 | 影响 | 建议 |
|---|---|---|---|---|---|

## 5. 后端存在但前端未发现调用

| 模块 | 方法 | 路径 | 后端入口 | 可能用途 | 依据 |
|---|---|---|---|---|---|

## 6. 前端调用但后端未发现接口

| 模块 | 前端调用 | 调用页面 | 影响 | 建议 | 依据 |
|---|---|---|---|---|---|

## 7. 需现场确认

-
EOT

write_file docs/db/README.md <<'EOT'
# DB 附录

> 文档状态：AI 自动维护  
> 最近校准：待校准  
> 依据来源：真实代码 / DDL baseline / 测试库元数据 SQL

## 1. 维护定位

本文件只记录数据库核心摘要，不记录全量字段。

全量 DDL baseline 和接入后的 DDL 变更见：

- `docs/db/ddl-history.md`

当前测试库 / 开发库结构快照见：

- `docs/db/schema-snapshot.md`

## 2. 数据库类型

| 项目 | 内容 |
|---|---|
| 数据库类型 | 需现场确认 |
| 当前连接环境 | 测试库 / 开发库，需现场确认 |
| 权限边界 | 由数据库账号控制 |
| 结构来源 | AI 生成只读元数据 SQL 查询 |
| 文档维护方式 | AI 自动维护 |

## 3. DB 连接安全边界

1. AI 不保存连接串。
2. AI 不输出连接串。
3. AI 不把连接信息写入 docs。
4. AI 不把连接信息写入 Git。
5. DB 连接信息只允许来自本地环境变量、CI Secret 或人工临时输入。
6. 生产库连接必须人工明确确认。
7. 测试库 / 开发库账号必须由数据库权限控制只读范围。

## 4. 核心 Schema

| Schema | 用途 | 依据 | 备注 |
|---|---|---|---|

## 5. 核心表摘要

| 模块 | Table | 用途 | 关键字段 | 依据 |
|---|---|---|---|---|

## 6. 关键索引摘要

| Table | Index | 用途 | 风险 | 依据 |
|---|---|---|---|---|

## 7. DDL 与测试库差异摘要

| 类型 | 对象 | 差异 | 影响 | 建议 |
|---|---|---|---|---|

## 8. 结构风险

| 风险 | 影响范围 | 验证方式 | 建议 |
|---|---|---|---|

## 9. 需现场确认

-
EOT

write_file docs/db/ddl-history.md <<'EOT'
# DB DDL History / Baseline

> 文档状态：AI 自动维护  
> 最近更新：待更新  
> 依据来源：真实代码 / Migration / SQL 文件 / 测试库元数据 SQL / 本次 DB 变更  
> 注意：本文件只记录 DDL 和结构 baseline，不记录业务数据。

## 1. 维护规则

1. 本文件由 AI 自动维护。
2. 人工不手动维护本文件。
3. 首次接入时，本文件记录当前可确认的 DDL baseline。
4. baseline 来源包括现有 SQL、Migration、ORM Model、Repository / Mapper、测试库 / 开发库元数据。
5. 首次接入前的真实历史 DDL 不保证完整还原。
6. 首次接入后的 DDL 变更必须按时间追加。
7. 涉及表结构变化时，AI 必须追加 DDL。
8. 不记录数据库账号、密码、连接串、Token。
9. 不记录业务数据。
10. 回滚 SQL 只记录，不由 AI 自动执行。
11. 实际执行 DDL 前必须确认环境和风险。

## 2. DDL Baseline

### 2.1 初始化 baseline

变更目的：

```text
需基于真实代码、Migration、SQL 文件或测试库结构补充。
```

影响对象：

```text
需现场确认
```

DDL：

```sql
-- 待 AI 基于真实 DB 变更自动补充
```

验证 SQL：

```sql
-- 待 AI 基于数据库类型自动生成只读元数据 SQL
```

回滚建议：

```sql
-- 待 AI 生成，仅作为人工评估参考，不自动执行
```

## 3. 接入后的 DDL 变更记录

-
EOT

write_file docs/db/schema-snapshot.md <<'EOT'
# DB Schema Snapshot

> 文档状态：AI 自动生成  
> 最近扫描：待扫描  
> 依据来源：AI 生成的只读元数据 SQL  
> 注意：本文件只记录数据库结构元数据，不记录业务数据。

## 1. 数据库类型

需现场确认。

## 2. 当前连接环境

测试库 / 开发库，需现场确认。

## 3. 规模控制规则

1. 小库可以记录完整业务 schema。
2. 大库只记录当前业务 schema 或本次任务相关 schema。
3. 超过 100 张表时，建议按 schema / module 拆分。
4. 不记录系统 schema。
5. 不记录业务数据。
6. 不记录账号、密码、连接串、Token。
7. 字段注释如可能包含敏感信息，默认不记录。

## 4. 本次执行的只读元数据 SQL

```sql
待 AI 自动填写
```

## 5. Schema 清单

| Schema | 说明 |
|---|---|

## 6. 表清单

| Schema | Table | Type | 备注 |
|---|---|---|---|

## 7. 字段清单

| Schema | Table | Column | Type | Nullable | Default |
|---|---|---|---|---|---|

## 8. 索引清单

| Schema | Table | Index | Definition |
|---|---|---|---|

## 9. 约束清单

| Schema | Table | Constraint | Type | Columns |
|---|---|---|---|---|

## 10. 视图清单

| Schema | View | 备注 |
|---|---|---|

## 11. 需现场确认

-
EOT

write_file docs/_archive/README.md <<'EOT'
# 归档文档说明

## 1. 说明

本目录用于存放旧文档、历史规则或临时资料。

默认情况下，AI 不读取本目录内容。

## 2. 使用规则

1. 只有人工明确要求时，AI 才读取本目录。
2. 本目录内容不作为当前事实源。
3. 当前事实以真实代码和 docs 核心文档为准。
EOT

write_file .claude/skills/docs-bootstrap/SKILL.md <<'EOT'
---
name: docs-bootstrap
description: 初始化或大校准核心 docs。新项目只初始化最小事实，开发中项目首次接入可执行 all 补齐核心三件套。
---

# docs-bootstrap

## 1. 目标

基于真实代码初始化或大校准核心文档：

1. docs/00-project-brief.md
2. docs/10-module-map.md
3. docs/20-delivery-board.md

## 2. 使用方式

新项目：

```text
/docs-bootstrap

项目类型：新项目
```

开发中项目首次接入：

```text
/docs-bootstrap all

项目类型：开发中项目首次接入
```

## 3. 执行规则

1. 只处理目标文档。
2. 新项目只写已有真实代码事实，不强行补齐不存在内容。
3. 开发中项目首次接入时，`all` 模式按 00、10、20 分轮处理。
4. 不修改业务代码。
5. 不确定内容标注“需现场确认”。
6. 每个关键结论必须有代码依据。
7. 不读取 docs/_archive/*，除非用户明确要求。

## 4. 输出格式

1. 当前代码摘要
2. 项目类型判断
3. 文档-代码差异
4. 实际修改文件
5. 代码依据
6. 反向校验结果
7. 需现场确认事项
EOT

write_file .claude/skills/docs-sync/SKILL.md <<'EOT'
---
name: docs-sync
description: 基于真实代码同步指定 docs 文档。v1.1 中只用于开发中项目首次基线、人工指定校准、文档异常修复，日常开发不要求手动执行。
---

# docs-sync

## 1. 适用场景

1. 开发中项目首次接入补齐基线。
2. 人工指定重新校准某个文档。
3. 文档严重过期。
4. 大版本重构后重新盘点。
5. 上线前 schema drift 检查。
6. check-only 检查文档是否过期。

## 2. 使用方式

```text
/docs-sync docs/10-module-map.md
```

```text
/docs-sync

目标文档：docs/frontend-guide.md
模式：update
```

```text
/docs-sync

目标文档：docs/10-module-map.md
模式：check-only
```

## 3. 执行规则

1. 只处理用户指定的目标文档。
2. 未指定目标文档时先询问。
3. 默认模式为 update。
4. check-only 只输出差异，不修改文件。
5. 必须基于真实代码。
6. 不确定内容标注“需现场确认”。
7. 不读取 docs/_archive/*，除非用户明确要求。
8. 日常开发任务中，不要求用户手动执行 `/docs-sync`。
9. 涉及 DB 时，只查询结构元数据，不查询业务数据，不记录连接串和密钥。

## 4. 输出格式

1. 当前代码现状摘要
2. 文档-代码差异清单
3. 实际修改文件
4. 代码依据
5. 反向校验结果
6. 需现场确认事项
EOT

write_file .claude/skills/bug-fix/SKILL.md <<'EOT'
---
name: bug-fix
description: 基于真实代码定位并修复 bug。用于 /bug-fix。
---

# bug-fix

## 1. 必读

- docs/00-project-brief.md
- docs/10-module-map.md
- docs/30-runbook.md
- 涉及历史问题、重复实现、旧架构残留再读 docs/40-tech-debt.md

## 2. 执行规则

1. 先定位根因，再做最小正确修复。
2. 不允许只改前端掩盖后端问题。
3. 不允许吞异常。
4. 不允许绕过鉴权、权限或核心校验。
5. 不允许扩大成无关重构。
6. 涉及 DB 时不查询业务表数据，不记录连接串、账号、密码、Token。
7. 修复后自动判断是否更新 runbook、tech-debt、contracts、db docs。
8. 执行 `bash scripts/ai/verify.sh`。

## 3. 输出格式

1. 根因
2. 修改文件
3. 修复说明
4. 影响范围
5. 更新了哪些文档
6. 哪些文档未更新及原因
7. 验证命令
8. 风险 / 需现场确认
EOT

write_file .claude/skills/feature-dev/SKILL.md <<'EOT'
---
name: feature-dev
description: 基于真实代码开发新功能。用于 /feature-dev。
---

# feature-dev

## 1. 必读

- docs/00-project-brief.md
- docs/10-module-map.md
- docs/20-delivery-board.md
- 涉及前端再读 docs/frontend-guide.md

## 2. 执行规则

1. 基于现有代码实现最小功能闭环。
2. 修改前输出影响范围：page / api / service / model / table。
3. 优先复用现有实现。
4. 不新增重复 API、service、组件、页面模式。
5. 不把计划写成完成。
6. 涉及 DB 时自动更新 ddl-history、schema-snapshot、db README。
7. 自动判断是否更新 module-map、delivery-board、frontend-guide、contracts。
8. 执行 `bash scripts/ai/verify.sh`。

## 3. 输出格式

1. 功能实现方案
2. 实际修改文件
3. 影响范围
4. 更新了哪些文档
5. 哪些文档未更新及原因
6. 验证方式
7. 风险 / 后续建议
EOT

write_file .claude/skills/refactor/SKILL.md <<'EOT'
---
name: refactor
description: 基于真实代码进行小步重构。用于 /refactor。
---

# refactor

## 1. 必读

- docs/00-project-brief.md
- docs/10-module-map.md
- docs/20-delivery-board.md
- docs/40-tech-debt.md
- 涉及前端再读 docs/frontend-guide.md

## 2. 执行规则

1. 小步重构，不改变业务行为。
2. 不顺手改无关功能。
3. 不大范围重命名。
4. 不把重构变成重写。
5. 不跳过验证。
6. 自动判断是否更新 module-map、tech-debt、frontend-guide、contracts、db README。
7. 执行 `bash scripts/ai/verify.sh`。

## 3. 输出格式

1. 重构前问题
2. 重构方案
3. 实际修改文件
4. 影响范围
5. 更新了哪些文档
6. 哪些文档未更新及原因
7. 风险点
8. 验证方式
EOT

write_file .claude/skills/frontend-optimize/SKILL.md <<'EOT'
---
name: frontend-optimize
description: 基于现有前端风格优化页面、组件、表格、表单、状态展示和交互一致性。
---

# frontend-optimize

## 1. 必读

- docs/00-project-brief.md
- docs/10-module-map.md
- docs/frontend-guide.md
- docs/20-delivery-board.md

## 2. 执行规则

1. 不为了美化破坏原交互。
2. 不硬编码状态颜色、状态文案、枚举值。
3. 不写大段内联样式。
4. 不绕过统一 API 封装直接请求后端。
5. 不新增重复组件模式。
6. 自动判断是否更新 frontend-guide、module-map、contracts、delivery-board。
7. 执行 `bash scripts/ai/verify.sh`。

## 3. 输出格式

1. 当前问题
2. 优化方案
3. 实际修改文件
4. 抽离了哪些公共能力
5. 影响范围
6. 更新了哪些文档
7. 哪些文档未更新及原因
8. 验证方式
EOT

write_file .claude/agents/code-reader.md <<'EOT'
name: code-reader
description: 只读分析代码结构、调用链、影响范围，不允许写文件。
tools: Read, Grep, Glob, Bash
permissionMode: plan
---

你是只读代码分析 Agent。

任务：

1. 读取真实代码。
2. 梳理调用链。
3. 输出 page / api / service / model / table 对应关系。
4. 标注无法确认内容为“需现场确认”。

禁止：

1. 不允许修改文件。
2. 不允许生成补丁。
3. 不允许根据旧文档猜测。
4. 不允许执行破坏性命令。
5. 不允许查询业务表数据。

输出：

1. 调用链
2. 影响范围
3. 关键代码依据
4. 需现场确认
EOT

write_file .claude/agents/docs-reviewer.md <<'EOT'
name: docs-reviewer
description: 只读审查 docs 是否与真实代码一致，适用于文档更新后的反向校验。
tools: Read, Grep, Glob, Bash
permissionMode: plan
---

你是文档一致性审查 Agent。

任务：

1. 读取目标文档。
2. 读取相关真实代码。
3. 校验文档中的架构、模块、调用链、进度是否有代码依据。
4. 找出过时、不准确、缺失、无法确认内容。

输出：

1. 通过项
2. 不一致项
3. 缺失项
4. 需现场确认项
5. 是否建议合并

禁止：

1. 不允许修改文件。
2. 不允许根据旧文档推断。
3. 不允许执行破坏性命令。
EOT

write_file .claude/agents/security-reviewer.md <<'EOT'
name: security-reviewer
description: 只读审查鉴权、RBAC、SSH、Ansible、导入导出、密钥、批量操作、数据库操作等高风险改动。
tools: Read, Grep, Glob, Bash
permissionMode: plan
---

你是安全审查 Agent。

重点审查：

1. 鉴权绕过。
2. RBAC 权限缺失。
3. 硬编码密码、token、密钥。
4. SSH / Ansible 命令注入。
5. 文件上传下载路径穿越。
6. 批量 UPDATE / DELETE 风险。
7. 导入导出敏感数据泄露。
8. 日志打印敏感信息。
9. 生产配置误改风险。
10. DB 查询是否只查询结构元数据。
11. 是否查询了业务表数据。
12. 是否记录了数据库账号、密码、连接串、Token。

输出：

1. 风险等级：High / Medium / Low
2. 问题文件
3. 问题原因
4. 修复建议
5. 是否阻断合并

禁止：

1. 不允许修改文件。
2. 不允许执行破坏性命令。
EOT

write_file .github/agents/code-reader.agent.md <<'EOT'
---
name: code-reader
description: 只读分析代码结构、调用链、影响范围，不允许写文件。
tools: ["read", "search", "glob", "bash"]
---

你是只读代码分析 Agent。

任务：

1. 读取真实代码。
2. 梳理调用链。
3. 输出 page / api / service / model / table 对应关系。
4. 标注无法确认内容为“需现场确认”。

禁止：

1. 不允许修改文件。
2. 不允许生成补丁。
3. 不允许根据旧文档猜测。
4. 不允许执行破坏性命令。
5. 不允许查询业务表数据。

输出：

1. 调用链
2. 影响范围
3. 关键代码依据
4. 需现场确认
EOT

write_file .github/agents/docs-reviewer.agent.md <<'EOT'
---
name: docs-reviewer
description: 只读审查 docs 是否与真实代码一致，适用于文档更新后的反向校验。
tools: ["read", "search", "glob", "bash"]
---

你是文档一致性审查 Agent。

任务：

1. 读取目标文档。
2. 读取相关真实代码。
3. 校验文档中的架构、模块、调用链、进度是否有代码依据。
4. 找出过时、不准确、缺失、无法确认内容。

输出：

1. 通过项
2. 不一致项
3. 缺失项
4. 需现场确认项
5. 是否建议合并

禁止：

1. 不允许修改文件。
2. 不允许根据旧文档推断。
3. 不允许执行破坏性命令。
EOT

write_file .github/agents/security-reviewer.agent.md <<'EOT'
---
name: security-reviewer
description: 只读审查鉴权、RBAC、SSH、Ansible、导入导出、密钥、批量操作、数据库操作等高风险改动。
tools: ["read", "search", "glob", "bash"]
---

你是安全审查 Agent。

重点审查：

1. 鉴权绕过。
2. RBAC 权限缺失。
3. 硬编码密码、token、密钥。
4. SSH / Ansible 命令注入。
5. 文件上传下载路径穿越。
6. 批量 UPDATE / DELETE 风险。
7. 导入导出敏感数据泄露。
8. 日志打印敏感信息。
9. 生产配置误改风险。
10. DB 查询是否只查询结构元数据。
11. 是否查询了业务表数据。
12. 是否记录了数据库账号、密码、连接串、Token。

输出：

1. 风险等级：High / Medium / Low
2. 问题文件
3. 问题原因
4. 修复建议
5. 是否阻断合并

禁止：

1. 不允许修改文件。
2. 不允许执行破坏性命令。
EOT

write_exec_file scripts/ai/guard.sh <<'EOT'
#!/usr/bin/env bash
set -euo pipefail

# Purpose:
#   Block P0 dangerous commands before Claude Code runs Bash tools.
#
# Usage:
#   printf '%s\n' '{"tool_input":{"command":"echo hello"}}' | bash scripts/ai/guard.sh

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'USAGE'
Usage:
  printf '%s\n' '{"tool_input":{"command":"echo hello"}}' | bash scripts/ai/guard.sh

This script reads Claude Code hook JSON from stdin and blocks P0 dangerous commands.
USAGE
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "[ERROR] Unknown argument: $*" >&2
  exit 1
fi

json_input="$(cat)"

command_text="$(
JSON_INPUT="$json_input" python3 - <<'PY'
import json
import os

try:
    data = json.loads(os.environ.get("JSON_INPUT", "{}"))
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
PY
)"

if [ -z "$command_text" ]; then
  exit 0
fi

normalized_command="$(printf '%s' "$command_text" | tr '\n' ' ')"

blocked_patterns=(
  '(^|[;&|[:space:]])rm[[:space:]]+-rf[[:space:]]+/([[:space:]]|$)'
  '(^|[;&|[:space:]])rm[[:space:]]+-rf[[:space:]]+/\*([[:space:]]|$)'
  '(^|[;&|[:space:]])mkfs([.[:alnum:]_-]*|[[:space:]])'
  '(^|[;&|[:space:]])dd[[:space:]].*of=/dev/'
  '(^|[;&|[:space:]])git[[:space:]]+push[[:space:]].*--force'
  '(^|[;&|[:space:]])git[[:space:]]+reset[[:space:]]+--hard'
  '(^|[;&|[:space:]])kubectl[[:space:]]+delete[[:space:]]'
  '(^|[;&|[:space:]])docker[[:space:]]+rm[[:space:]].*-f'
  '(^|[^A-Za-z0-9_])DROP[[:space:]]+(DATABASE|SCHEMA|TABLE|USER|ROLE|OWNED)([^A-Za-z0-9_]|$)'
  '(^|[^A-Za-z0-9_])TRUNCATE([[:space:]]+TABLE)?[[:space:]]+'
  '(^|[^A-Za-z0-9_])ALTER[[:space:]]+SYSTEM([^A-Za-z0-9_]|$)'
  '(^|[^A-Za-z0-9_])SHUTDOWN([^A-Za-z0-9_]|$)'
)

for pattern in "${blocked_patterns[@]}"; do
  if printf '%s' "$normalized_command" | grep -Eiq "$pattern"; then
    echo "Blocked by scripts/ai/guard.sh"
    echo "P0 dangerous command detected:"
    echo "$command_text"
    echo "Run manually only after human confirmation."
    exit 2
  fi
done

exit 0
EOT

write_exec_file scripts/ai/verify.sh <<'EOT'
#!/usr/bin/env bash
set -u

# Purpose:
#   Run available baseline checks for AI Coding tasks.
#
# Usage:
#   bash scripts/ai/verify.sh
#
# Notes:
#   This script does not use set -e because it collects multiple check results.

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'USAGE'
Usage:
  bash scripts/ai/verify.sh

Runs available checks:
  - JS lint/typecheck/build if package scripts exist
  - Python pytest if pytest is available
  - Bash syntax check for scripts/*.sh
USAGE
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "[ERROR] Unknown argument: $*" >&2
  exit 1
fi

echo "[INFO] AI verification started"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root" || exit 1

fail_count=0
skip_count=0

run_step() {
  local name="$1"
  shift

  echo "[INFO] Run: $name"

  if "$@"; then
    echo "[OK] $name"
  else
    echo "[FAIL] $name"
    fail_count=$((fail_count + 1))
  fi
}

skip_step() {
  local reason="$1"
  echo "[WARN] Skip: $reason"
  skip_count=$((skip_count + 1))
}

has_package_script() {
  local dir="$1"
  local script_name="$2"

  if [ ! -f "$dir/package.json" ]; then
    return 1
  fi

  if ! command -v node >/dev/null 2>&1; then
    return 1
  fi

  node -e "
const fs = require('fs');
const p = '$dir/package.json';
const pkg = JSON.parse(fs.readFileSync(p, 'utf8'));
process.exit(pkg.scripts && pkg.scripts['$script_name'] ? 0 : 1);
" >/dev/null 2>&1
}

run_js_script() {
  local dir="$1"
  local script_name="$2"
  local status=0

  if [ ! -f "$dir/package.json" ]; then
    return 0
  fi

  if ! has_package_script "$dir" "$script_name"; then
    skip_step "$dir package.json has no script: $script_name"
    return 0
  fi

  cd "$repo_root/$dir" || return 1

  if [ -f "pnpm-lock.yaml" ] && command -v pnpm >/dev/null 2>&1; then
    pnpm "$script_name" || status=$?
  elif [ -f "yarn.lock" ] && command -v yarn >/dev/null 2>&1; then
    yarn "$script_name" || status=$?
  elif command -v npm >/dev/null 2>&1; then
    npm run "$script_name" || status=$?
  else
    cd "$repo_root" || return 1
    skip_step "$dir no available package manager for $script_name"
    return 0
  fi

  cd "$repo_root" || return 1
  return "$status"
}

check_js_project() {
  local dir="$1"

  if [ ! -f "$dir/package.json" ]; then
    return 0
  fi

  echo "[INFO] Check JS project: $dir"

  if [ ! -d "$dir/node_modules" ]; then
    skip_step "$dir/node_modules not found"
    return 0
  fi

  run_step "$dir lint" run_js_script "$dir" "lint"
  run_step "$dir typecheck" run_js_script "$dir" "typecheck"
  run_step "$dir build" run_js_script "$dir" "build"
}

run_pytest_dir() {
  local dir="$1"
  local status=0

  cd "$repo_root/$dir" || return 1

  if [ -f "$repo_root/venv/bin/activate" ]; then
    . "$repo_root/venv/bin/activate"
  elif [ -f "$repo_root/.venv/bin/activate" ]; then
    . "$repo_root/.venv/bin/activate"
  fi

  pytest -v || status=$?

  cd "$repo_root" || return 1
  return "$status"
}

check_python_project() {
  local dir="$1"

  if [ ! -d "$dir" ]; then
    return 0
  fi

  if [ ! -d "$dir/tests" ] && [ ! -f "$dir/pytest.ini" ] && [ ! -f "$dir/pyproject.toml" ]; then
    return 0
  fi

  if ! command -v pytest >/dev/null 2>&1; then
    skip_step "pytest not found for $dir"
    return 0
  fi

  run_step "$dir pytest" run_pytest_dir "$dir"
}

check_shell_scripts() {
  if [ ! -d "scripts" ]; then
    return 0
  fi

  while IFS= read -r script_file; do
    run_step "bash -n $script_file" bash -n "$script_file"
  done < <(find scripts -type f -name "*.sh" | sort)
}

echo "[INFO] Detect and run available checks"

check_js_project "."
check_js_project "frontend"
check_js_project "web"

check_python_project "."
check_python_project "backend"
check_python_project "server"

check_shell_scripts

echo "[INFO] Git status"
git status --short

echo "[INFO] Verification summary"
echo "[INFO] failed: $fail_count"
echo "[INFO] skipped: $skip_count"

if [ "$fail_count" -gt 0 ]; then
  echo "[FAIL] AI verification finished with errors"
  exit 1
fi

echo "[OK] AI verification finished"
exit 0
EOT

write_file .claude/settings.json <<'EOT'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash scripts/ai/guard.sh"
          }
        ]
      }
    ]
  }
}
EOT

write_file .github/pull_request_template.md <<'EOT'
# PR 说明

## 1. 改了什么

-

## 2. 修改了哪些文件

-

## 3. 为什么这样改

-

## 4. 影响范围

- [ ] frontend page
- [ ] frontend api
- [ ] backend api
- [ ] backend service
- [ ] model
- [ ] table
- [ ] docs
- [ ] scripts
- [ ] config
- [ ] db ddl
- [ ] db schema snapshot
- [ ] db data

## 5. 文档更新

- [ ] docs/00-project-brief.md
- [ ] docs/10-module-map.md
- [ ] docs/20-delivery-board.md
- [ ] docs/30-runbook.md
- [ ] docs/40-tech-debt.md
- [ ] docs/frontend-guide.md
- [ ] docs/contracts/README.md
- [ ] docs/contracts/api-inventory.md
- [ ] docs/db/README.md
- [ ] docs/db/ddl-history.md
- [ ] docs/db/schema-snapshot.md
- [ ] 不需要更新文档，原因：

## 6. 验证方式

执行命令：

```bash
bash scripts/ai/verify.sh
```

结果：

```text
```

## 7. 数据库说明

- [ ] 不涉及数据库
- [ ] 仅涉及 DB 文档
- [ ] 涉及 Model / Migration / Mapper / Repository
- [ ] 涉及 DDL 生成
- [ ] 涉及测试库结构快照
- [ ] 涉及数据修复
- [ ] 涉及批量 UPDATE / DELETE

说明：

-

## 8. DB 安全确认

- [ ] 未查询业务数据
- [ ] 未记录数据库账号、密码、连接串、Token
- [ ] 仅查询结构元数据
- [ ] 不涉及生产库
- [ ] 涉及生产库，已人工明确确认

## 9. 风险说明

- [ ] 无明显风险
- [ ] 有风险，说明如下：

## 10. 是否涉及 P0 极高危操作

- [ ] 否
- [ ] 是，已人工确认

## 11. 后续建议

-
EOT

echo "[OK] AI Coding Governance v1.1 created"
