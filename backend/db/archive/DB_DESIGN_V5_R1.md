# DBOPS V5-R1 平台底座设计

## 1. 设计目标

`V5-R1` 是 DBOPS 平台底座设计，不只覆盖资产管理，还包含：

- 平台认证与管理员初始化
- 业务系统与数据库资产管理
- 联系人复用与角色绑定
- Excel staging 导入
- 标签、生命周期、备份、评分等治理能力

本版针对当前尚未上线的阶段，直接重整 `V5` 设计，不做兼容迁移。

## 2. 总体边界

平台底座统一使用单一 schema：

- `dbops`
  - 平台用户与登录认证
  - 业务系统、DB 资产、联系人、导入、治理

## 3. 已确认业务规则

- `平台分类` 是业务大类，固定 8 类
- `系统名稱` 视为业务系统主标识，按全局唯一处理
- `CLUSETR_KEY` 是技术集群外部编号，表示同一组主机 / 同一套 DB 组
- `CLUSTER_TYPE` 表示技术集群类型
- `CLUSTER_TYPE` 的完整字典见 [docs/cluster_type_dictionary.md](/home/feng/dbops/docs/cluster_type_dictionary.md)
- `NODE_ROLE` 表示实例在组内角色
- 一个 `business_system` 当前只对应一个 `cluster`
- 一个 `cluster` 当前只对应一个 `business_system`
- 同一台主机允许承载多个实例
- `instance_name` 必填
- 同一 `cluster` 内，实例唯一性按 `server_id + instance_name + port` 判定
- 一个集群允许有多个 VIP
- 备份策略当前按 `db_instance` 管理
- 联系人固定 6 类角色

## 4. 平台级主线

### 4.1 认证主线

`dbops.users`

平台登录用户表。当前后端登录最小依赖就是这张表，因此必须纳入初始化 SQL。

关键字段：

- `id UUID PK`
- `username UNIQUE NOT NULL`
- `email UNIQUE NOT NULL`
- `password_hash NOT NULL`
- `full_name`
- `department`
- `role`
- `is_active`
- `timezone`
- `language`
- `created_at`
- `updated_at`

初始化要求：

- 默认账号：`admin`
- 默认密码：`Unixadm88`
- SQL 可重复执行

### 4.2 业务与资产主线

平台资产主线收敛为：

`system_group -> business_system -> cluster -> db_instance -> server`

这是当前 Excel 与运营规则下最稳定的结构，不预先做多对多泛化。

## 5. 核心表设计

### 5.1 业务分组：`dbops.system_group`

固定 8 类业务大类。

字段：

- `id`
- `group_code`
- `name`
- `description`
- `created_at`
- `updated_at`

约束：

- `group_code UNIQUE`
- `name UNIQUE`

初始化数据：

- `ERP`
- `人資`
- `園區`
- `差旅`
- `採購`
- `相信`
- `關務`
- `電簽`

### 5.2 业务系统：`dbops.business_system`

承载 Excel 中的 `系统名稱`。

字段：

- `id`
- `system_code`
- `name`
- `system_group_id`
- `business_unit`
- `department`
- `service_scope_raw`
- `biz_level`
- `description`
- `extra_attrs`
- `created_at`
- `updated_at`

约束：

- `system_code UNIQUE`
- `name UNIQUE`
- `system_group_id NOT NULL`

规则：

- 一个系统名称只能属于一个平台分类
- 一个系统名称当前只允许绑定一个集群

### 5.3 集群：`dbops.cluster`

承载 `CLUSETR_KEY` 和技术分组语义。

字段：

- `id`
- `cluster_key`
- `business_system_id`
- `cluster_type`
- `name`
- `ha_enabled`
- `ha_remark`
- `description`
- `extra_attrs`
- `created_at`
- `updated_at`

约束：

- `cluster_key UNIQUE`
- `business_system_id UNIQUE`
- `business_system_id NOT NULL`

规则：

- 一个 `cluster_key` 只对应一个业务系统
- 一个业务系统当前只允许一个集群

### 5.4 集群 VIP：`dbops.cluster_vip`

字段：

- `id`
- `cluster_id`
- `vip_address`
- `vip_type`
- `remark`
- `created_at`

约束：

- `cluster_id NOT NULL`
- `UNIQUE(cluster_id, vip_address)`

说明：

- `vip_address` 使用 `TEXT`
- 不使用单一 `INET`

### 5.5 主机：`dbops.server`

字段：

- `id`
- `server_code`
- `hostname`
- `ip_address`
- `site_name`
- `room_location`
- `os_name`
- `os_version`
- `cpu_cores`
- `memory_gb`
- `disk_gb`
- `server_type`
- `status`
- `extra_attrs`
- `remark`
- `created_at`
- `updated_at`

约束：

- `ip_address UNIQUE`

说明：

- 当前先保留 Excel 导入和资产管理必要字段
- 以后如果 OS 维表成熟，再逐步过渡到 `os_version_id`

### 5.6 数据库实例：`dbops.db_instance`

字段：

- `id`
- `instance_code`
- `instance_name`
- `db_type`
- `db_version`
- `server_id`
- `cluster_id`
- `env_code`
- `port`
- `service_name`
- `node_role`
- `db_size_gb`
- `status`
- `extra_attrs`
- `remark`
- `created_at`
- `updated_at`

约束：

- `instance_code UNIQUE`
- `cluster_id NOT NULL`
- `server_id NOT NULL`
- `instance_name NOT NULL`
- `UNIQUE(cluster_id, server_id, instance_name, port)`

规则：

- `NODE_ROLE` 直接写入 `node_role`
- 当前不允许空实例名

## 6. 联系人设计

### 6.1 联系人主数据：`dbops.contact`

字段：

- `id`
- `employee_no`
- `contact_code`
- `name`
- `phone`
- `email`
- `dept`
- `remark`
- `created_at`
- `updated_at`

约束：

- `contact_code UNIQUE`

建议：

- `employee_no` 优先作为人工主数据标识，允许为空
- `contact_code` 作为稳定技术编码保留，不再由姓名和电话派生
- 导入时优先按 `employee_no`、`email`、标准化 `phone` 匹配复用

### 6.2 业务联系人关系：`dbops.business_system_contact`

字段：

- `id`
- `business_system_id`
- `contact_id`
- `role_code`
- `remark`
- `created_at`

约束：

- `business_system_id NOT NULL`
- `contact_id NOT NULL`
- `UNIQUE(business_system_id, role_code)`
- `role_code` 固定 6 类

固定角色：

- `OS_ADMIN`
- `HOST_ADMIN`
- `APP_OWNER`
- `BUSINESS_MANAGER`
- `BUSINESS_BELONG_MANAGER`
- `DBA_OWNER`

说明：

- 同一个业务系统，每个角色最多 1 个联系人
- 联系人主数据可以跨业务系统复用
- 当前导入阶段先绑定 `BUSINESS_MANAGER` 和 `DBA_OWNER`，其余角色保留在 Excel 中，后续再逐步补全

## 7. 标签与治理

### 7.1 标签：`dbops.tag` / `dbops.resource_tag`

用途：

- 业务范畴
- 监控开启
- MDR 开启
- DB 审计开启

`resource_tag.resource_type` 受限为：

- `business_system`
- `cluster`
- `server`
- `db_instance`

### 7.2 生命周期

当前版本先保留轻量能力：

- `os_name/os_version`
- `db_type/db_version`

后续如需要，可追加标准化维表：

- `os_version_catalog`
- `db_version_catalog`

### 7.3 评分

本版保留最小评分基础：

- `biz_level`
- `biz_score_rule`
- `biz_score_result`
- `biz_score_result_detail`

评分依赖：

- 是否有 HA
- 是否有备份
- 是否异地备份
- 监控/审计/MDR 标签

## 8. 备份模型

### 8.1 `dbops.backup_policy`

字段：

- `id`
- `policy_code`
- `name`
- `backup_type`
- `schedule_cron`
- `retention_days`
- `storage_type`
- `storage_path`
- `is_remote_backup`
- `remote_backup_location`
- `is_enabled`
- `remark`
- `created_at`
- `updated_at`

### 8.2 `dbops.instance_backup_policy`

字段：

- `id`
- `instance_id`
- `policy_id`
- `is_enabled`
- `created_at`

约束：

- `UNIQUE(instance_id, policy_id)`

## 9. Excel staging 导入

### 9.1 staging 原则

- 原始 Excel 字段完整保留
- 原始值优先按文本保存
- 冲突在 staging 层检查
- 正式表只接结构化结果

### 9.2 staging 表：`dbops.staging_excel_import`

除原始 Excel 列外，额外增加：

- `import_batch_id`
- `source_file_name`
- `row_no`
- `raw_payload`
- `imported_at`

关键要求：

- `VIP` 使用 `TEXT`
- 联系人姓名与联系方式原样入 staging
- 原始密码只允许落 staging

## 10. 关键导入规则

### 10.1 业务系统

- `系统名稱` 不能为空
- 同一 `系统名稱` 只能对应一个 `平台分类`
- 同一 `系统名稱` 当前只能对应一个 `cluster_key`

### 10.2 集群

- `CLUSETR_KEY` 不能为空
- 同一 `cluster_key` 只能对应一个 `系统名稱`
- `CLUSTER_TYPE` 必须可识别

### 10.3 实例

- `instance_name` 不能为空
- 同一 `cluster_key` 下 `instance_name` 唯一
- `NODE_ROLE` 必须可识别

### 10.4 联系人

- 联系人先作为独立主数据维护，再由业务系统引用
- 当前导入阶段先处理业务主管和 DBA，其他角色后续再补
- 同一人优先复用联系人主数据

### 10.5 VIP

- 允许为空
- 允许单格多值
- 导入时拆分后写入 `cluster_vip`

## 11. 最小基础数据

建表 SQL 必须包含：

1. `dbops.users` 初始化管理员
2. `dbops.system_group` 固定 8 类
3. 常用 `env_code`
4. 常用 `db_type`
5. 联系人角色固定枚举
6. 基础 `biz_level`

## 12. 推荐落地顺序

1. 建立 `ops` 与 `dbops` schema
2. 初始化认证与管理员
3. 建立业务、资产、联系人、备份、标签、评分表
4. 建立 staging 和校验视图
5. 初始化基础数据
6. 实现导入脚本 / 服务

## 13. 结论

`V5-R1` 不是把 V5 推倒，而是把它整理成可启动、可导入、可扩展的平台级底座。

核心关系固定为：

`system_group -> business_system -> cluster -> db_instance -> server`

并以联系人复用、集群多 VIP、实例级备份、平台级认证为补充能力。
