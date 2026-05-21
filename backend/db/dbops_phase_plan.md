# DBOps 分阶段建设设计

## 1. 总体策略

DBOps 平台不建议一次性把所有能力做满。建议分两阶段：

```text
第一阶段：可上线标准版
目标：Excel 可导入、资产可展示、集群关系可看、备份/巡检/评分可跑
规模：26 张表

第二阶段：企业级完整版
目标：告警、凭据、审计、自动化、历史趋势、治理闭环
规模：建议扩展到 40~46 张表
```

当前推荐先做第一阶段。第一阶段不是“简化版台账”，而是一个能上线、能运行、能产生治理价值的标准版本。

---

# 2. 第一阶段：可上线标准版

## 2.1 目标

第一阶段目标：

```text
先把 Excel 导入、资产展示、集群关系、备份、巡检、评分跑起来；
后面再逐步加告警、凭据、审计和自动化。
```

当前已经落地的 CRUD 顺序建议固定为：

```text
1. 联系人主数据 CRUD
2. 业务系统新增 / 编辑 / 状态变更
3. 业务系统 - 联系人关系绑定 / 解绑
4. 服务器 / 实例的有限字段编辑
5. 集群保持只读，后续再评估受控编辑
```

## 2.2 表数量

第一阶段设计 **26 张表**。

## 2.3 第一阶段表清单

### A. 平台认证层

| 序号 | 表名 | 用途 |
|---:|---|---|
| 1 | dbops.users | 平台登录用户 |

### B. 业务与联系人

| 序号 | 表名 | 用途 |
|---:|---|---|
| 2 | dbops.system_group | 业务大类，固定 8 类 |
| 3 | dbops.business_system | 业务系统（生命周期状态：建设中 / 待上线 / 已上线 / 已下线；Excel 导入默认已上线，手工新建默认建设中） |
| 4 | dbops.contact | 联系人主数据（先人工清洗再导入） |
| 5 | dbops.business_system_contact | 业务系统与联系人角色关系 |

### C. 站点与主机

| 序号 | 表名 | 用途 |
|---:|---|---|
| 6 | dbops.asset_event_history | 资产通用事件历史表（业务生命周期、OS/DB/服务器等变更统一底座） |
| 7 | dbops.site | 国家、厂区、部署类型、资源提供方、机房位置 |
| 8 | dbops.server | 服务器/虚拟机资产 |

### D. OS / DB 版本

| 序号 | 表名 | 用途 |
|---:|---|---|
| 9 | dbops.os_version | OS 版本字典和生命周期 |
| 10 | dbops.db_type | 数据库类型主数据字典（类型/分类/许可证/厂商） |
| 11 | dbops.db_version | 数据库版本和生命周期 |

### E. 集群与实例

| 序号 | 表名 | 用途 |
|---:|---|---|
| 12 | dbops.cluster | 数据库集群/主备组 |
| 13 | dbops.cluster_vip | 集群 VIP |
| 14 | dbops.db_instance | 数据库实例 |
| 15 | dbops.topology_relation | 实例拓扑关系 |

### F. 标签

| 序号 | 表名 | 用途 |
|---:|---|---|
| 16 | dbops.tag | 标签字典 |
| 17 | dbops.resource_tag | 资源标签关系 |

### G. 备份

| 序号 | 表名 | 用途 |
|---:|---|---|
| 18 | dbops.backup_policy | 备份策略 |
| 19 | dbops.instance_backup_policy | 实例与备份策略关系 |

### H. 巡检

| 序号 | 表名 | 用途 |
|---:|---|---|
| 20 | dbops.inspection_item | 巡检项定义 |
| 21 | dbops.inspection_task | 巡检任务 |
| 22 | dbops.inspection_result | 巡检结果 |

### I. 业务架构评分

| 序号 | 表名 | 用途 |
|---:|---|---|
| 23 | dbops.biz_score_rule | 评分规则 |
| 24 | dbops.biz_score_result | 评分结果 |
| 25 | dbops.biz_score_result_detail | 评分明细 |

### J. Excel 导入

| 序号 | 表名 | 用途 |
|---:|---|---|
| 26 | dbops.staging_excel_import | Excel 原始导入暂存表 |

---

## 2.4 第一阶段能回答的问题

第一阶段完成后，可以回答：

```text
某个业务用了哪些数据库
某个实例在哪台主机、哪个机房
哪些系统是单实例
哪些系统有主备
哪些业务没有备份
哪些实例版本过旧
哪些巡检失败
哪些业务架构分低
按国家/厂区/云/地端/provider 统计实例
按业务大类统计风险
```

---

# 3. 第一阶段核心关系

## 3.1 业务主线

```text
system_group
  ↓
business_system
  ↓
cluster
  ↓
db_instance
```

## 3.2 资产主线

```text
site
  ↓
server
  ↓
db_instance
```

## 3.3 版本主线

```text
os_version → server
db_type → db_version → db_instance
```

## 3.4 拓扑主线

```text
cluster
  ↓
db_instance
  ↓
topology_relation
```

## 3.5 治理主线

```text
backup_policy / inspection_result / tag / version lifecycle
  ↓
biz_score_result
```

---

# 4. 第一阶段关键设计说明

## 4.1 site 为什么一张表

当前 Excel 已经结构化出：

```text
国家
部署类型
资源提供方
厂区
机房位置
```

这些都是固定字段，不需要 site_category / mapping。第一阶段用一张 `site` 表最简单、最稳定。

## 4.2 cluster_code 不依赖 Excel 的 CLUSTER_KEY

`cluster_code` 由系统生成：

```text
CLU-{DB_TYPE}-{CLUSTER_TYPE}-{HASH}
```

HASH 推荐来源：

```text
业务系统名称 + DB类型 + 实例名称 + 端口 + 集群类型
```

这样即使 Excel 没有 cluster_key，也可以稳定生成技术集群。

`cluster_type` 的完整字典定义见 [docs/cluster_type_dictionary.md](/home/feng/dbops/docs/cluster_type_dictionary.md)。

## 4.3 单实例也建 cluster

单实例同样建 `cluster`，`cluster_type = SINGLE`。

好处：

```text
SQL 统一
页面统一
后续单实例升级主备更容易
```

## 4.4 tag 的边界

`tag` 用于补充属性，不替代核心字段。

适合 tag：

```text
监控开启
MDR开启
DB审计开启
服务范畴
临时标记
```

不适合 tag：

```text
db_type
deploy_type
provider
cluster_type
node_role
```

---

# 5. 第二阶段：企业级完整版

## 5.1 表数量

第二阶段建议扩展到 **40~46 张表**。

不是一次性推倒第一阶段，而是在 26 张表基础上渐进增强。

## 5.2 第二阶段目标

第二阶段目标：

```text
从“资产可见、风险可算”
升级到
“运维可控、过程可审计、动作可自动化、风险可闭环”
```

## 5.3 第二阶段新增能力

### A. 告警中心

新增表：

```text
alert_rule
alert_event
alert_notify_channel
alert_rule_channel
```

能力：

```text
按 BIZ 等级控制告警优先级
按实例、集群、业务产生告警
支持通知渠道
支持告警事件历史
```

解决问题：

```text
哪些关键业务正在异常
哪些告警需要优先处理
同一类告警是否频繁发生
```

### B. 凭据中心

新增表：

```text
credential
credential_binding
credential_access_log
```

能力：

```text
账号密码集中管理
凭据绑定到实例/服务器
记录谁访问过凭据
支持后续密码轮换
```

解决问题：

```text
Excel 明文密码风险
账号散落无人管
凭据访问无法审计
```

### C. 审计与变更

新增表：

```text
change_record
audit_log
maintenance_record
```

能力：

```text
记录业务下线、实例迁移、机房变动
记录用户操作
记录运维维护历史
```

解决问题：

```text
谁改了数据
什么时候下线
为什么变更
能否追溯
```

### D. 备份执行记录

新增表：

```text
backup_job
```

能力：

```text
记录每次备份执行结果
统计备份成功率
检查最近一次备份
```

解决问题：

```text
有策略但不知道是否真的成功
无法证明备份有效性
```

### E. 自动化任务

新增表：

```text
automation_job
automation_run
automation_run_log
```

能力：

```text
执行巡检脚本
执行备份检查
执行批量SQL
执行主机探测
保留执行日志
```

解决问题：

```text
人工操作多
过程不可复现
失败无法追踪
```

### F. 监控与容量趋势

新增表：

```text
metric_snapshot
capacity_history
```

能力：

```text
保存实例容量趋势
保存连接数、空间、延迟等指标
```

解决问题：

```text
容量何时耗尽
哪个系统增长最快
巡检只能看当前，不能看趋势
```

### G. 更细业务治理

可新增：

```text
business_domain
business_system_domain
service_sla
```

能力：

```text
支持更细的业务范畴
支持 SLA/RTO/RPO
支持多维归属
```

---

# 6. 第二阶段能解决的问题

第二阶段可以进一步回答：

```text
哪些关键业务正在告警
哪些告警重复发生
哪些业务备份失败
哪些账号长期未轮换
谁查看过生产密码
哪个系统最近发生过变更
哪些实例容量增长异常
哪些任务自动化执行失败
哪些业务存在未闭环风险
```

---

# 7. 推荐建设节奏

## 第一阶段：4~6 周

```text
1. 建 26 张表
2. Excel 导入 staging
3. 清洗并写入 site/server/cluster/instance/system/contact，其中 contact 先作为主数据单独导入，业务联系人关系后续仅挂业务主管与 DBA，再逐步补全其他角色
4. 展示资产、业务、集群
5. 跑备份策略检查
6. 跑巡检结果
7. 跑业务评分
```

## 第二阶段：6~12 周

```text
1. 加告警中心
2. 加凭据中心
3. 加审计/变更
4. 加备份执行记录
5. 加自动化任务
6. 加容量趋势
7. 做治理闭环仪表盘
```

---

# 8. 结论

```text
第一阶段 26 张表：可上线标准版
第二阶段 40~46 张表：企业级完整版
```

第一阶段重点是“跑起来”，第二阶段重点是“管起来”。
