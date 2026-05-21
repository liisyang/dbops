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
