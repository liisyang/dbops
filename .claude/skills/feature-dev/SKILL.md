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
