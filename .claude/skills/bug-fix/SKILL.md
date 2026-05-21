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
