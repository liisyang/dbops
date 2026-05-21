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
