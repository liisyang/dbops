# DBOps 最终完整设计文档（46张表 + 固定8大类）

## 一、版本说明

本版本是最终整合版，基于制造业数据库运维场景设计。

总表数：

```text
42 张核心表（site 架构版）
+ 1 张 BIZ等级表：biz_level
+ 3 张业务架构评分表：biz_score_rule / biz_score_result / biz_score_result_detail
= 46 张表
```

同时包含：

```text
OS / DB 生命周期管理
BIZ 等级管理
业务架构评分
固定 8 大系统分类
Excel 导入暂存与校验逻辑
```

---

## 二、固定 8 大系统分类

你的“平台分类”是业务系统大类，固定为 8 类：

```text
ERP
人資
園區
差旅
採購
相信
關務
電簽
```

数据库中对应：

```text
system_group
```

Excel 中对应字段：

```text
平台分类
```

导入规则：

```text
平台分类 → system_group.name
系统名称 → business_system.name
实例 → instance_system → business_system
```

强制规则：

```text
同一个系统名称，只能对应一个平台分类。
```

---

## 三、应用业务范畴设计

Excel 字段：

```text
應用業務範疇(使用tag)
```

建议支持多值：

```text
全集團,一卡通服務
```

数据库中对应：

```text
tag
resource_tag
```

推荐标签类型：

```text
scope   -- 业务范畴，例如 全集团、事业群、一卡通服務、TIPTOP
monitor -- 监控开启
mdr     -- MDR开启
audit   -- DB审计开启
custom  -- 其他
```

绑定建议：

```text
服务范畴 tag → 挂 business_system
监控/MDR/DB审计 tag → 挂 db_instance 或 server
```

---

## 四、最终分层表清单

### 1. 站点层（3）

```text
1. site
2. site_category
3. site_category_mapping
```

### 2. 基础维表（4）

```text
4. os_version              -- 含生命周期字段
5. db_type
6. db_version              -- 含生命周期字段
7. env
```

### 3. 资源层（4）

```text
8. platform
9. cluster                 -- 含 ha_enabled / ha_remark
10. server                 -- 关联 site
11. db_instance            -- 含 biz_level_id
```

### 4. 业务层（4）

```text
12. system_group           -- 固定8大类
13. business_system        -- 业务系统/系统名称
14. instance_system        -- 实例与业务系统关系
15. biz_level              -- 一般/重要/關鍵/極重要
```

### 5. 联系人与账号层（4）

```text
16. contact
17. instance_contact
18. account
19. instance_account
```

### 6. 状态与拓扑层（4）

```text
20. instance_status
21. instance_status_history
22. replication_topology
23. topology_relation
```

### 7. 运维治理层（5）

```text
24. maintenance_record
25. change_record
26. audit_log
27. tag
28. resource_tag
```

### 8. 备份模块（3）

```text
29. backup_policy          -- 含 is_remote_backup
30. instance_backup_policy
31. backup_job
```

### 9. 巡检模块（5）

```text
32. inspection_template
33. inspection_item
34. inspection_task
35. inspection_task_instance
36. inspection_result
```

### 10. 告警模块（4）

```text
37. alert_rule             -- 支持BIZ等级联动
38. alert_event
39. alert_notify_channel
40. alert_rule_channel
```

### 11. 凭据中心（3）

```text
41. credential
42. credential_binding
43. credential_access_log
```

### 12. 业务架构评分模块（3）

```text
44. biz_score_rule
45. biz_score_result
46. biz_score_result_detail
```

---

## 五、核心关系

### 1. 资产主线

```text
site → server → db_instance
platform → cluster → db_instance
db_type → db_version → db_instance
env → db_instance
```

### 2. 业务主线

```text
system_group（8大类）
    ↓
business_system（系统名称）
    ↓
instance_system
    ↓
db_instance
```

### 3. 标签主线

```text
tag
  ↓
resource_tag
  ↓
business_system / db_instance / server / site
```

### 4. 主备拓扑

```text
cluster
  ↓
db_instance(primary)
  ↓
replication_topology
  ↓
db_instance(standby)
```

### 5. 业务架构评分

```text
business_system
  ↓
instance_system
  ↓
db_instance
  ├─ cluster / replication_topology        判断是否有备援
  ├─ backup_policy.is_remote_backup       判断是否有异地备份
  ├─ db_version.lifecycle_status          判断DB生命周期
  ├─ server → os_version.lifecycle_status 判断OS生命周期
  └─ instance_status                      判断是否有监控
```

---

## 六、Excel 字段映射

| Excel字段 | 目标表/字段 | 说明 |
|---|---|---|
| CLUSETR_KEY | cluster.cluster_code | 建议转为 CLU-{key} |
| CLUSTER_TYPE | cluster.cluster_type | DATAGUARD/SINGLE |
| NODE_ROLE | db_instance.configured_role | Master/Slave/SINGLE |
| 平台分类 | system_group.name | 固定8类 |
| 應用業務範疇(使用tag) | tag/resource_tag | 可多值，逗号分隔 |
| 系统名称 | business_system.name | 业务系统名称 |
| IP | server.ip_address | 服务器主IP |
| 實例名稱 | db_instance.instance_name | 数据库实例名 |
| PORT | db_instance.port | 监听端口 |
| Hostname | server.hostname | 主机名 |
| CPU(Cores) | server.cpu_cores | CPU核数 |
| 記憶體(G) | server.memory_gb | 内存 |
| 磁碟空間(G) | server.disk_gb | 磁盘 |
| 數據庫空間(G) | db_instance.extra_attrs | 放 JSONB |
| 國家/廠區/機房位置 | site/site_category | 站点与分类 |
| 重要等級 | biz_level.name | 一般/重要/關鍵/極重要 |
| 備份方式 | backup_policy.backup_type/remark | RMAN等 |
| 異地備份位置 | backup_policy.is_remote_backup | 非空则 true |
| 监控开启 | tag/resource_tag 或 instance_status | 建议tag记录开关 |
| MDR开启 | tag/resource_tag | 挂 server 或 instance |
| DB审计开启 | tag/resource_tag | 挂 instance |

---

## 七、导入校验规则

### 1. 平台分类只允许8类

```sql
SELECT *
FROM dbops.v_staging_invalid_platform_category;
```

### 2. 同一系统名称不能对应多个平台分类

```sql
SELECT *
FROM dbops.v_staging_system_category_conflict;
```

### 3. 密码不要明文入正式表

Excel 里的：

```text
db_password
os_oracle_password
os_password
```

只能进入 staging，不应直接进入正式业务表。正式密码进入：

```text
credential.encrypted_secret
```

---

## 八、评分逻辑

默认基础分：

```text
10分
```

扣分项：

```text
没有备援       -5
没有异地备份   -3
DB版本EOL      -2
OS版本EOL      -2
没有监控       -2
```

实时查询：

```sql
SELECT *
FROM dbops.v_biz_arch_score
ORDER BY final_score ASC;
```

保存快照：

```sql
SELECT dbops.save_biz_arch_score_snapshot('daily-20260425');
```

---

## 九、推荐落地顺序

```text
1. 执行最终SQL
2. Excel 导入 staging_excel_import
3. 先查平台分类异常
4. 修正同一系统多分类问题
5. 清洗写入正式表
6. 生成 replication_topology
7. 生成 tag/resource_tag
8. 执行业务架构评分
```

---

## 十、结论

这版模型不是普通 CMDB，而是：

```text
DBOps 数据底座 + 业务优先级 + 生命周期治理 + 架构评分
```

关键落地点：

```text
平台分类固定8类 → system_group
服务范畴多值 → tag
业务系统 → business_system
数据库实例 → db_instance
架构评分 → biz_score_*
```
