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
