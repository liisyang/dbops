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
