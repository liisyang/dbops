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
