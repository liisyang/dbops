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
