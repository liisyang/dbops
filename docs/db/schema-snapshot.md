# DB Schema Snapshot

> 文档状态：AI 自动生成（基于实时数据库元数据查询）
> 最近扫描：2026-06-06
> 依据来源：PostgreSQL 17.9 @ 10.134.185.85:5432/dbops — 只读元数据 SQL 查询
> 注意：本文件只记录数据库结构元数据，不记录业务数据。

## 1. 数据库类型

PostgreSQL 17.9 on x86_64-pc-linux-gnu, compiled by gcc (GCC) 11.5.0 20240719 (Red Hat 11.5.0-11), 64-bit。

## 2. 当前连接环境

测试库 / 开发库，已连接扫描。

## 3. 规模控制规则

1. 小库可以记录完整业务 schema。
2. 大库只记录当前业务 schema 或本次任务相关 schema。
3. 超过 100 张表时，建议按 schema / module 拆分。
4. 不记录系统 schema。
5. 不记录业务数据。
6. 不记录账号、密码、连接串、Token。
7. 字段注释如可能包含敏感信息，默认不记录。

## 4. 本次执行的只读元数据 SQL

```sql
-- 1. 数据库版本
SELECT current_database(), current_schema(), version();

-- 2. 扩展
SELECT extname, extversion, extnamespace::regnamespace AS schema FROM pg_extension;

-- 3. Schema 清单
SELECT schema_name FROM information_schema.schemata
WHERE schema_name NOT IN ('information_schema','pg_catalog','pg_toast') ORDER BY schema_name;

-- 4. 表和视图清单
SELECT table_schema, table_name, table_type,
       obj_description((table_schema||'.'||table_name)::regclass, 'pg_class') AS comment
FROM information_schema.tables WHERE table_schema = 'dbops'
ORDER BY table_type, table_name;

-- 5. 字段清单（含注释）
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, c.udt_name, c.character_maximum_length,
       c.numeric_precision, c.numeric_scale, c.is_nullable, c.column_default,
       pgd.description AS column_comment
FROM information_schema.columns c
LEFT JOIN pg_catalog.pg_description pgd
    ON pgd.objoid = (c.table_schema||'.'||c.table_name)::regclass
    AND pgd.objsubid = c.ordinal_position
WHERE c.table_schema = 'dbops' ORDER BY c.table_name, c.ordinal_position;

-- 6. 索引清单
SELECT schemaname AS table_schema, tablename AS table_name,
       indexname AS index_name, indexdef AS index_definition
FROM pg_indexes WHERE schemaname = 'dbops'
ORDER BY tablename, indexname;

-- 7. 约束清单
SELECT tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns,
       cc.check_clause
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.check_constraints cc
    ON tc.constraint_name = cc.constraint_name AND tc.constraint_schema = cc.constraint_schema
WHERE tc.table_schema = 'dbops'
GROUP BY tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type, cc.check_clause
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;

-- 8. 序列清单
SELECT sequence_schema, sequence_name, data_type, start_value, minimum_value, maximum_value, increment
FROM information_schema.sequences WHERE sequence_schema = 'dbops' ORDER BY sequence_name;

-- 9. 视图定义
SELECT schemaname AS table_schema, viewname AS view_name, definition
FROM pg_views WHERE schemaname = 'dbops' ORDER BY viewname;

-- 10. 自定义函数（仅 dbops schema 下的 plpgsql 函数）
SELECT n.nspname AS schema, p.proname AS function_name, pg_get_functiondef(p.oid) AS function_definition
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'dbops' AND p.prokind = 'f' AND p.prolang != 'c'::regproc
ORDER BY p.proname;

-- 11. 触发器
SELECT trigger_schema, trigger_name, event_object_table AS table_name, event_manipulation, action_timing
FROM information_schema.triggers WHERE trigger_schema = 'dbops'
ORDER BY event_object_table, trigger_name;
```

## 5. Schema 清单

| Schema | 说明 |
|---|---|
| dbops | DBOps 主业务 schema（32 表 + 4 视图 + 1 自定义函数 + 18 触发器 + 31 序列） |
| public | PostgreSQL 默认 schema |

## 6. 表清单

| Schema | Table | Type | 备注 |
|---|---|---|---|
| dbops | users | BASE TABLE | 平台登录用户表 |
| dbops | system_group | BASE TABLE | 业务大类，固定8类：ERP/人資/園區/差旅/採購/相信/關務/電簽 |
| dbops | business_system | BASE TABLE | 业务系统表，对应Excel系统名称 |
| dbops | contact | BASE TABLE | 联系人主数据表 |
| dbops | business_system_contact | BASE TABLE | 业务系统联系人关系表 |
| dbops | asset_event_history | BASE TABLE | 资产通用事件历史表 |
| dbops | site | BASE TABLE | 站点/机房表，一条记录代表一个机房级site |
| dbops | os_version | BASE TABLE | OS版本字典及生命周期 |
| dbops | db_type | BASE TABLE | 数据库类型主数据字典，包含类型、分类、许可证和厂商信息 |
| dbops | db_version | BASE TABLE | 数据库版本字典及生命周期 |
| dbops | server | BASE TABLE | 服务器/虚拟机资产表 |
| dbops | cluster | BASE TABLE | 数据库集群/主备组/单实例技术组 |
| dbops | cluster_vip | BASE TABLE | 集群VIP表，支持一个集群多个VIP |
| dbops | db_instance | BASE TABLE | 数据库实例表 |
| dbops | topology_relation | BASE TABLE | 实例拓扑关系表，统一表达主备、复制、成员关系 |
| dbops | tag | BASE TABLE | 标签字典表 |
| dbops | resource_tag | BASE TABLE | 资源标签关系表 |
| dbops | backup_policy | BASE TABLE | 备份策略表 |
| dbops | instance_backup_policy | BASE TABLE | 数据库实例与备份策略关系表 |
| dbops | inspection_item | BASE TABLE | 巡检项定义表 |
| dbops | inspection_task | BASE TABLE | 巡检任务表 |
| dbops | inspection_result | BASE TABLE | 巡检结果表 |
| dbops | biz_score_rule | BASE TABLE | 业务架构评分规则表 |
| dbops | biz_score_result | BASE TABLE | 业务架构评分结果表 |
| dbops | biz_score_result_detail | BASE TABLE | 业务架构评分扣分明细表 |
| dbops | staging_excel_import | BASE TABLE | Excel原始导入暂存表。正式表只接清洗后的结构化数据。 |
| dbops | collector_run | BASE TABLE | AWX校验任务主记录 |
| dbops | collector_run_item | BASE TABLE | AWX校验任务项明细 |
| dbops | collector_run_result | BASE TABLE | AWX校验结果明细 |
| dbops | collector_check_definition | BASE TABLE | 检查项定义表 |
| dbops | asset_endpoint | BASE TABLE | 端点状态表 |
| dbops | asset_change_proposal | BASE TABLE | 资产变更提案表 |
| dbops | v_instance_full | VIEW | 实例全量展示视图，用于资产列表和查询 |
| dbops | v_staging_invalid_platform_category | VIEW | 平台分类不在固定8类中的记录 |
| dbops | v_staging_invalid_site | VIEW | site字段不完整或部署类型非法的记录 |
| dbops | v_staging_system_category_conflict | VIEW | 同一系统名称对应多个平台分类的冲突记录 |

## 7. 字段清单

### 7.1 users

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | |
| username | varchar(100) | NO | | 登录账号 |
| email | varchar(200) | NO | | |
| password_hash | text | NO | | 密码哈希，不存明文密码 |
| full_name | varchar(100) | YES | | |
| department | varchar(200) | YES | | |
| role | varchar(50) | YES | 'admin' | 平台角色：admin/operator/viewer |
| is_active | boolean | YES | true | |
| timezone | varchar(50) | YES | 'Asia/Shanghai' | |
| language | varchar(20) | YES | 'zh-CN' | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.2 system_group

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| group_code | varchar(50) | NO | | 业务大类编码 |
| name | varchar(50) | NO | | 业务大类名称 |
| description | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.3 business_system

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| system_code | varchar(100) | NO | | 业务系统编码，建议系统生成或人工维护 |
| system_name | varchar(300) | NO | | 业务系统名称，当前按全局唯一处理 |
| system_group_id | bigint | YES | | 业务大类，可先为空后补 |
| business_unit | varchar(200) | YES | | |
| department | varchar(200) | YES | | |
| service_scope | text | YES | | 服务范畴，可先存原始文本，后续可拆tag |
| biz_level | varchar(50) | YES | | 业务重要等级：一般/重要/關鍵/極重要 |
| status | varchar(20) | YES | 'building' | |
| remark | text | YES | | |
| extra_attrs | jsonb | YES | '{}'::jsonb | 业务系统扩展属性 |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.4 contact

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| employee_no | varchar(50) | YES | | 工号 |
| contact_code | varchar(100) | NO | | 联系人编码，建议由姓名+电话hash生成 |
| contact_name | varchar(100) | NO | | 联系人姓名 |
| phone | varchar(100) | YES | | 联系电话 |
| email | varchar(200) | YES | | |
| dept | varchar(200) | YES | | |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.5 business_system_contact

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| business_system_id | bigint | NO | | |
| contact_id | bigint | NO | | |
| role_code | varchar(50) | NO | | 联系人角色：6种角色 |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |

### 7.6 asset_event_history

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| asset_type | varchar(50) | NO | | 资产类型 |
| asset_id | bigint | NO | | 资产主键 |
| event_type | varchar(50) | NO | | 事件类型 |
| before_status | varchar(20) | YES | | 变更前状态 |
| after_status | varchar(20) | YES | | 变更后状态 |
| changed_fields | jsonb | NO | '{}'::jsonb | 变更字段快照 |
| reason | text | YES | | 变更原因 |
| operator | varchar(100) | YES | | 操作人 |
| operated_at | timestamp | NO | now() | 操作时间 |
| remark | text | YES | | 备注 |
| created_at | timestamp | YES | now() | 创建时间 |

### 7.7 site

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| site_code | varchar(100) | NO | | 站点编码 |
| country | varchar(50) | NO | | 国家/地区 |
| deploy_type | varchar(50) | NO | | 部署类型：地端/私有雲/公有雲 |
| provider | varchar(100) | NO | | 资源提供方 |
| factory_area | varchar(100) | NO | | 厂区或地区 |
| room_location | varchar(200) | NO | | 机房位置 |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.8 os_version

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| os_code | varchar(100) | NO | | |
| os_name | varchar(100) | NO | | |
| version_name | varchar(200) | NO | | |
| release_date | date | YES | | |
| eos_date | date | YES | | |
| eol_date | date | YES | | |
| lifecycle_status | varchar(50) | YES | 'unknown' | 生命周期状态：active/maintenance/eos/eol/unknown |
| risk_level | varchar(50) | YES | 'unknown' | 生命周期风险等级：low/medium/high/critical/unknown |
| is_supported | boolean | YES | true | |
| is_recommended | boolean | YES | false | |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.9 db_type

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| type_code | varchar(50) | NO | | 数据库类型编码，统一使用大写 |
| name | varchar(100) | NO | | 展示名称，按行业常用写法 |
| category | varchar(50) | NO | 'relational' | 数据库分类：relational/nosql/cache/search/time_series/other |
| license_type | varchar(20) | NO | 'commercial' | 许可证类型：open_source/commercial/hybrid |
| vendor | varchar(100) | YES | | 厂商 |
| remark | text | YES | | |
| is_active | boolean | NO | true | 是否启用 |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.10 db_version

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| db_type_id | bigint | NO | | |
| version_code | varchar(100) | NO | | 主版本 |
| version_name | varchar(200) | NO | | |
| patch_version | varchar(200) | YES | | 补丁版本 |
| architecture_bits | varchar(20) | YES | | 架构位数，例如 64bit |
| release_date | date | YES | | |
| eos_date | date | YES | | |
| eol_date | date | YES | | |
| lifecycle_status | varchar(50) | YES | 'unknown' | 生命周期状态：active/maintenance/eos/eol/unknown |
| risk_level | varchar(50) | YES | 'unknown' | |
| is_supported | boolean | YES | true | |
| is_recommended | boolean | YES | false | |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.11 server

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| server_code | varchar(100) | NO | | |
| hostname | varchar(200) | YES | | |
| ip_address | inet | NO | | |
| site_id | bigint | YES | | 当前所在site |
| os_version_id | bigint | YES | | OS版本 |
| cpu_cores | integer | YES | | |
| memory_gb | numeric(10,2) | YES | | |
| disk_gb | numeric(12,2) | YES | | |
| server_type | varchar(50) | YES | | |
| business_group | varchar(100) | YES | | 资源归属/事业群 |
| status | varchar(20) | YES | 'active' | |
| remark | text | YES | | |
| extra_attrs | jsonb | YES | '{}'::jsonb | 服务器扩展属性，例如DNS/VIP原始值等 |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.12 cluster

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| cluster_code | varchar(100) | NO | | 系统生成的集群唯一编码 |
| cluster_name | varchar(200) | NO | | |
| business_system_id | bigint | NO | | |
| db_type_id | bigint | NO | | |
| cluster_type | varchar(50) | NO | | 集群类型字典 |
| ha_enabled | boolean | YES | false | 是否具备高可用能力 |
| status | varchar(20) | YES | 'active' | |
| remark | text | YES | | |
| extra_attrs | jsonb | YES | '{}'::jsonb | 集群扩展属性 |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.13 cluster_vip

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| cluster_id | bigint | NO | | |
| vip_address | text | NO | | VIP地址，使用TEXT兼容IP、域名、SCAN等 |
| vip_type | varchar(50) | YES | | VIP类型：service/scan/app/listener等 |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |

### 7.14 db_instance

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| instance_code | varchar(100) | NO | | 实例唯一编码，建议系统生成 |
| instance_name | varchar(200) | NO | | |
| db_type_id | bigint | NO | | |
| db_version_id | bigint | YES | | |
| server_id | bigint | NO | | |
| cluster_id | bigint | NO | | |
| port | integer | YES | | |
| service_name | varchar(200) | YES | | |
| node_role | varchar(50) | YES | 'unknown' | 跨数据库统一基础角色：primary/standby/member/single/unknown |
| db_size_gb | numeric(12,2) | YES | | |
| status | varchar(20) | YES | 'active' | |
| remark | text | YES | | |
| extra_attrs | jsonb | YES | '{}'::jsonb | 实例扩展属性 |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.15 topology_relation

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| cluster_id | bigint | NO | | |
| source_instance_id | bigint | YES | | |
| target_instance_id | bigint | YES | | |
| relation_type | varchar(50) | NO | | 关系类型：primary_standby/leader_follower/member/replica/shard_member |
| sync_mode | varchar(50) | YES | | 同步模式：sync/async/semisync/unknown |
| status | varchar(50) | YES | | |
| lag_seconds | integer | YES | | 复制延迟秒数 |
| remark | text | YES | | |
| extra_attrs | jsonb | YES | '{}'::jsonb | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.16 tag

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| tag_code | varchar(100) | NO | | |
| tag_name | varchar(100) | NO | | 标签名称 |
| tag_type | varchar(50) | YES | | 标签类型：scope/monitor/mdr/audit/custom |
| color | varchar(30) | YES | | |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.17 resource_tag

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| resource_type | varchar(50) | NO | | 资源类型：business_system/cluster/server/db_instance |
| resource_id | bigint | NO | | 资源ID，不建外键，由resource_type决定引用表 |
| tag_id | bigint | NO | | |
| created_at | timestamp | YES | now() | |

### 7.18 backup_policy

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| policy_code | varchar(100) | NO | | |
| policy_name | varchar(200) | NO | | |
| backup_type | varchar(50) | YES | | 备份类型：RMAN/full/incremental/logical等 |
| schedule_cron | varchar(100) | YES | | |
| retention_days | integer | YES | | |
| storage_type | varchar(50) | YES | | |
| storage_path | text | YES | | |
| is_remote_backup | boolean | YES | false | 是否异地备份 |
| remote_backup_location | text | YES | | 异地备份位置 |
| is_enabled | boolean | YES | true | |
| remark | text | YES | | |
| extra_attrs | jsonb | YES | '{}'::jsonb | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.19 instance_backup_policy

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| instance_id | bigint | NO | | |
| policy_id | bigint | NO | | |
| is_enabled | boolean | YES | true | |
| created_at | timestamp | YES | now() | |

### 7.20 inspection_item

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| item_code | varchar(100) | NO | | |
| item_name | varchar(200) | NO | | |
| category | varchar(50) | YES | | 巡检分类：backup/ha/config/lifecycle/connectivity |
| severity | varchar(20) | YES | 'info' | 默认严重级别 |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.21 inspection_task

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| task_code | varchar(100) | NO | | |
| task_name | varchar(200) | NO | | |
| scope_type | varchar(50) | YES | | 巡检范围类型 |
| scope_id | bigint | YES | | 巡检范围ID，根据scope_type解释 |
| status | varchar(20) | YES | 'pending' | |
| started_at | timestamp | YES | | |
| finished_at | timestamp | YES | | |
| remark | text | YES | | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.22 inspection_result

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| task_id | bigint | NO | | |
| item_id | bigint | NO | | |
| target_type | varchar(50) | NO | | |
| target_id | bigint | NO | | |
| result_status | varchar(20) | NO | | |
| result_value | text | YES | | |
| extra_attrs | jsonb | YES | '{}'::jsonb | 巡检结果扩展信息 |
| created_at | timestamp | YES | now() | |

### 7.23 biz_score_rule

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| rule_code | varchar(100) | NO | | |
| rule_name | varchar(200) | NO | | |
| description | text | YES | | |
| deduct_score | numeric(5,2) | NO | | 扣分值 |
| is_enabled | boolean | YES | true | |
| sort_order | integer | YES | 0 | |
| created_at | timestamp | YES | now() | |
| updated_at | timestamp | YES | now() | |

### 7.24 biz_score_result

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| business_system_id | bigint | NO | | |
| base_score | numeric(5,2) | YES | 10 | |
| deduct_score | numeric(5,2) | YES | 0 | |
| final_score | numeric(5,2) | NO | | |
| score_level | varchar(20) | YES | | |
| score_batch | varchar(100) | YES | | 评分批次 |
| scored_at | timestamp | YES | now() | |

### 7.25 biz_score_result_detail

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| result_id | bigint | NO | | |
| rule_id | bigint | NO | | |
| deduct_score | numeric(5,2) | NO | | |
| reason | text | YES | | |
| evidence | jsonb | YES | '{}'::jsonb | 扣分证据JSON |
| created_at | timestamp | YES | now() | |

### 7.26 staging_excel_import

| Column | Type | Nullable | Default | Comment |
|---|---|---|---|---|
| id | bigint (BIGSERIAL) | NO | nextval | |
| import_batch_id | varchar(100) | YES | | |
| source_file_name | varchar(300) | YES | | |
| row_no | integer | YES | | |
| system_name | text | YES | | |
| platform_category | text | YES | | |
| ... | _(60+ 个 TEXT 字段对应 Excel 列)_ | | | |
| raw_payload | jsonb | YES | '{}'::jsonb | 原始Excel行JSON，便于追溯 |
| imported_at | timestamp | YES | now() | |

> 完整 64 列清单见 `docs/db/ddl-history.md` 3.4.26 节或数据库实时查询 `information_schema.columns WHERE table_name = 'staging_excel_import'`。

## 8. 索引清单

共 98 个索引。以下按表分组（含 PK/UNIQUE 索引和业务索引）：

| Table | Index | Type | Definition |
|---|---|---|---|
| **users** (5) | users_pkey | PK UNIQUE | (id) |
| | users_username_key | UNIQUE | (username) |
| | users_email_key | UNIQUE | (email) |
| | ix_dbops_users_username | INDEX | (username) |
| **system_group** (3) | system_group_pkey | PK UNIQUE | (id) |
| | system_group_group_code_key | UNIQUE | (group_code) |
| | system_group_name_key | UNIQUE | (name) |
| **business_system** (5) | business_system_pkey | PK UNIQUE | (id) |
| | business_system_system_code_key | UNIQUE | (system_code) |
| | business_system_system_name_key | UNIQUE | (system_name) |
| | idx_business_system_group | INDEX | (system_group_id) |
| | idx_business_system_status | INDEX | (status) |
| **contact** (4) | contact_pkey | PK UNIQUE | (id) |
| | contact_contact_code_key | UNIQUE | (contact_code) |
| | idx_contact_employee_no | INDEX | (employee_no) |
| | idx_contact_name_phone | INDEX | (contact_name, phone) |
| **business_system_contact** (4) | business_system_contact_pkey | PK UNIQUE | (id) |
| | uq_business_system_contact | UNIQUE | (business_system_id, contact_id, role_code) |
| | idx_bsc_system | INDEX | (business_system_id) |
| | idx_bsc_contact | INDEX | (contact_id) |
| **asset_event_history** (4) | asset_event_history_pkey | PK UNIQUE | (id) |
| | idx_asset_event_history_asset | INDEX | (asset_type, asset_id, operated_at DESC) |
| | idx_asset_event_history_event | INDEX | (event_type, operated_at DESC) |
| **site** (5) | site_pkey | PK UNIQUE | (id) |
| | site_site_code_key | UNIQUE | (site_code) |
| | idx_site_country | INDEX | (country) |
| | idx_site_factory | INDEX | (factory_area) |
| | idx_site_deploy_provider | INDEX | (deploy_type, provider) |
| **os_version** (4) | os_version_pkey | PK UNIQUE | (id) |
| | os_version_os_code_key | UNIQUE | (os_code) |
| | uq_os_name_version | UNIQUE | (os_name, version_name) |
| | idx_os_version_lifecycle | INDEX | (lifecycle_status) |
| **db_type** (4) | db_type_pkey | PK UNIQUE | (id) |
| | db_type_type_code_key | UNIQUE | (type_code) |
| | db_type_name_key | UNIQUE | (name) |
| **db_version** (4) | db_version_pkey | PK UNIQUE | (id) |
| | uq_db_version | UNIQUE | (db_type_id, version_code, patch_version) |
| | idx_db_version_type | INDEX | (db_type_id) |
| | idx_db_version_lifecycle | INDEX | (lifecycle_status) |
| **server** (5) | server_pkey | PK UNIQUE | (id) |
| | server_server_code_key | UNIQUE | (server_code) |
| | server_ip_address_key | UNIQUE | (ip_address) |
| | idx_server_site | INDEX | (site_id) |
| | idx_server_os_version | INDEX | (os_version_id) |
| | idx_server_status | INDEX | (status) |
| **cluster** (5) | cluster_pkey | PK UNIQUE | (id) |
| | cluster_cluster_code_key | UNIQUE | (cluster_code) |
| | idx_cluster_system | INDEX | (business_system_id) |
| | idx_cluster_db_type | INDEX | (db_type_id) |
| | idx_cluster_type | INDEX | (cluster_type) |
| **cluster_vip** (3) | cluster_vip_pkey | PK UNIQUE | (id) |
| | uq_cluster_vip | UNIQUE | (cluster_id, vip_address) |
| **db_instance** (6) | db_instance_pkey | PK UNIQUE | (id) |
| | db_instance_instance_code_key | UNIQUE | (instance_code) |
| | uq_instance_cluster_server_name_port | UNIQUE | (cluster_id, server_id, instance_name, port) |
| | idx_instance_server | INDEX | (server_id) |
| | idx_instance_cluster | INDEX | (cluster_id) |
| | idx_instance_db_type | INDEX | (db_type_id) |
| | idx_instance_status | INDEX | (status) |
| **topology_relation** (5) | topology_relation_pkey | PK UNIQUE | (id) |
| | uq_topology_relation | UNIQUE | (cluster_id, source_instance_id, target_instance_id, relation_type) |
| | idx_topology_cluster | INDEX | (cluster_id) |
| | idx_topology_source | INDEX | (source_instance_id) |
| | idx_topology_target | INDEX | (target_instance_id) |
| **tag** (3) | tag_pkey | PK UNIQUE | (id) |
| | tag_tag_code_key | UNIQUE | (tag_code) |
| | idx_tag_type | INDEX | (tag_type) |
| **resource_tag** (4) | resource_tag_pkey | PK UNIQUE | (id) |
| | uq_resource_tag | UNIQUE | (resource_type, resource_id, tag_id) |
| | idx_resource_tag_resource | INDEX | (resource_type, resource_id) |
| | idx_resource_tag_tag | INDEX | (tag_id) |
| **backup_policy** (2) | backup_policy_pkey | PK UNIQUE | (id) |
| | backup_policy_policy_code_key | UNIQUE | (policy_code) |
| **instance_backup_policy** (4) | instance_backup_policy_pkey | PK UNIQUE | (id) |
| | uq_instance_backup_policy | UNIQUE | (instance_id, policy_id) |
| | idx_ibp_instance | INDEX | (instance_id) |
| | idx_ibp_policy | INDEX | (policy_id) |
| **inspection_item** (2) | inspection_item_pkey | PK UNIQUE | (id) |
| | inspection_item_item_code_key | UNIQUE | (item_code) |
| **inspection_task** (3) | inspection_task_pkey | PK UNIQUE | (id) |
| | inspection_task_task_code_key | UNIQUE | (task_code) |
| | idx_inspection_task_status | INDEX | (status) |
| **inspection_result** (4) | inspection_result_pkey | PK UNIQUE | (id) |
| | idx_ir_task | INDEX | (task_id) |
| | idx_ir_target | INDEX | (target_type, target_id) |
| | idx_ir_status | INDEX | (result_status) |
| **biz_score_rule** (2) | biz_score_rule_pkey | PK UNIQUE | (id) |
| | biz_score_rule_rule_code_key | UNIQUE | (rule_code) |
| **biz_score_result** (3) | biz_score_result_pkey | PK UNIQUE | (id) |
| | idx_score_result_system_time | INDEX | (business_system_id, scored_at DESC) |
| | idx_score_result_batch | INDEX | (score_batch) |
| **biz_score_result_detail** (3) | biz_score_result_detail_pkey | PK UNIQUE | (id) |
| | idx_score_detail_result | INDEX | (result_id) |
| | idx_score_detail_rule | INDEX | (rule_id) |
| **staging_excel_import** (4) | staging_excel_import_pkey | PK UNIQUE | (id) |
| | idx_staging_batch | INDEX | (import_batch_id) |
| | idx_staging_system | INDEX | (system_name) |
| | idx_staging_ip | INDEX | (ip) |

## 9. 约束清单

### 9.1 CHECK 约束（业务级）

| Table | Constraint | Definition |
|---|---|---|
| business_system | chk_business_system_status | status IN ('building','pending','active','retired') |
| business_system_contact | chk_business_contact_role | role_code IN (6 roles) |
| site | chk_site_deploy_type | deploy_type IN ('地端','私有雲','公有雲') |
| db_type | ck_db_type_category | category IN (6 categories) |
| db_type | ck_db_type_license | license_type IN ('open_source','commercial','hybrid') |
| server | chk_server_status | status IN ('active','inactive','retired') |
| cluster | chk_cluster_status | status IN ('active','inactive','retired') |
| db_instance | chk_instance_status | status IN ('active','inactive','retired') |
| db_instance | chk_node_role | node_role IN ('primary','standby','member','single','unknown') |
| resource_tag | chk_resource_tag_type | resource_type IN (4 types) |
| inspection_item | chk_inspection_item_severity | severity IN ('info','warning','critical') |
| inspection_task | chk_inspection_task_status | status IN ('pending','running','success','failed','cancelled') |
| inspection_task | chk_inspection_task_scope | scope_type IN (4 types) OR NULL |
| inspection_result | chk_inspection_result_target | target_type IN (4 types) |
| inspection_result | chk_inspection_result_status | result_status IN ('ok','warning','failed','unknown') |

> PostgreSQL 17 自动为 NOT NULL 列生成 `<oid>_<ord>_not_null` CHECK 约束（如上查询结果中 18667_* 系列），此处省略。完整的 195 条约束（含 NOT NULL、PK、FK、UNIQUE、CHECK）已从数据库实时查询获取。

### 9.2 FOREIGN KEY 约束

| Table | Constraint | Columns | References |
|---|---|---|---|
| business_system | business_system_system_group_id_fkey | system_group_id | system_group(id) |
| business_system_contact | *business_system_id_fkey | business_system_id | business_system(id) ON DELETE CASCADE |
| business_system_contact | *contact_id_fkey | contact_id | contact(id) |
| cluster | cluster_business_system_id_fkey | business_system_id | business_system(id) |
| cluster | cluster_db_type_id_fkey | db_type_id | db_type(id) |
| cluster_vip | cluster_vip_cluster_id_fkey | cluster_id | cluster(id) ON DELETE CASCADE |
| db_instance | db_instance_db_type_id_fkey | db_type_id | db_type(id) |
| db_instance | db_instance_db_version_id_fkey | db_version_id | db_version(id) |
| db_instance | db_instance_server_id_fkey | server_id | server(id) |
| db_instance | db_instance_cluster_id_fkey | cluster_id | cluster(id) |
| db_version | db_version_db_type_id_fkey | db_type_id | db_type(id) |
| server | server_site_id_fkey | site_id | site(id) |
| server | server_os_version_id_fkey | os_version_id | os_version(id) |
| topology_relation | topology_relation_cluster_id_fkey | cluster_id | cluster(id) ON DELETE CASCADE |
| topology_relation | *source_instance_id_fkey | source_instance_id | db_instance(id) |
| topology_relation | *target_instance_id_fkey | target_instance_id | db_instance(id) |
| resource_tag | resource_tag_tag_id_fkey | tag_id | tag(id) ON DELETE CASCADE |
| instance_backup_policy | *instance_id_fkey | instance_id | db_instance(id) ON DELETE CASCADE |
| instance_backup_policy | *policy_id_fkey | policy_id | backup_policy(id) |
| inspection_result | inspection_result_task_id_fkey | task_id | inspection_task(id) ON DELETE CASCADE |
| inspection_result | inspection_result_item_id_fkey | item_id | inspection_item(id) |
| biz_score_result | biz_score_result_business_system_id_fkey | business_system_id | business_system(id) ON DELETE CASCADE |
| biz_score_result_detail | *result_id_fkey | result_id | biz_score_result(id) ON DELETE CASCADE |
| biz_score_result_detail | *rule_id_fkey | rule_id | biz_score_rule(id) |

### 9.3 UNIQUE 约束

| Table | Constraint | Columns |
|---|---|---|
| users | users_username_key | (username) |
| users | users_email_key | (email) |
| system_group | system_group_group_code_key | (group_code) |
| system_group | system_group_name_key | (name) |
| business_system | business_system_system_code_key | (system_code) |
| business_system | business_system_system_name_key | (system_name) |
| business_system_contact | uq_business_system_contact | (business_system_id, contact_id, role_code) |
| contact | contact_contact_code_key | (contact_code) |
| site | site_site_code_key | (site_code) |
| os_version | os_version_os_code_key | (os_code) |
| os_version | uq_os_name_version | (os_name, version_name) |
| db_type | db_type_type_code_key | (type_code) |
| db_type | db_type_name_key | (name) |
| db_version | uq_db_version | (db_type_id, version_code, patch_version) |
| server | server_server_code_key | (server_code) |
| server | server_ip_address_key | (ip_address) |
| cluster | cluster_cluster_code_key | (cluster_code) |
| cluster_vip | uq_cluster_vip | (cluster_id, vip_address) |
| db_instance | db_instance_instance_code_key | (instance_code) |
| db_instance | uq_instance_cluster_server_name_port | (cluster_id, server_id, instance_name, port) |
| topology_relation | uq_topology_relation | (cluster_id, source_instance_id, target_instance_id, relation_type) |
| tag | tag_tag_code_key | (tag_code) |
| resource_tag | uq_resource_tag | (resource_type, resource_id, tag_id) |
| backup_policy | backup_policy_policy_code_key | (policy_code) |
| instance_backup_policy | uq_instance_backup_policy | (instance_id, policy_id) |
| inspection_item | inspection_item_item_code_key | (item_code) |
| inspection_task | inspection_task_task_code_key | (task_code) |
| biz_score_rule | biz_score_rule_rule_code_key | (rule_code) |

## 10. 视图清单

| Schema | View | 用途 | 行数 |
|---|---|---|---|
| dbops | v_instance_full | 实例全量展示（9 表 JOIN：db_instance → cluster → business_system → system_group + server → site + db_type + db_version） | — |
| dbops | v_staging_invalid_platform_category | 平台分类不在固定8类中的记录 | — |
| dbops | v_staging_system_category_conflict | 同一系统名称对应多个平台分类的冲突记录 | — |
| dbops | v_staging_invalid_site | site字段不完整或部署类型非法的记录 | — |

## 11. 序列清单

25 个 BIGSERIAL 序列（BIGINT 类型，start=1, max=9223372036854775807, increment=1）：

`asset_event_history_id_seq`, `backup_policy_id_seq`, `biz_score_result_detail_id_seq`, `biz_score_result_id_seq`, `biz_score_rule_id_seq`, `business_system_contact_id_seq`, `business_system_id_seq`, `cluster_id_seq`, `cluster_vip_id_seq`, `contact_id_seq`, `db_instance_id_seq`, `db_type_id_seq`, `db_version_id_seq`, `inspection_item_id_seq`, `inspection_result_id_seq`, `inspection_task_id_seq`, `instance_backup_policy_id_seq`, `os_version_id_seq`, `resource_tag_id_seq`, `server_id_seq`, `site_id_seq`, `staging_excel_import_id_seq`, `system_group_id_seq`, `tag_id_seq`, `topology_relation_id_seq`

> users 表使用 UUID 主键（gen_random_uuid()），无序列。

## 12. 函数清单

| Schema | Function | 类型 | 说明 |
|---|---|---|---|
| dbops | set_updated_at() | plpgsql TRIGGER | 通用 updated_at 自动更新触发器函数 |
| dbops | gen_random_uuid() | C (pgcrypto) | UUID 生成 |
| dbops | gen_salt(text), gen_salt(text, integer) | C (pgcrypto) | salt 生成 |
| dbops | crypt(text, text) | C (pgcrypto) | 密码哈希 |
| dbops | digest(text,text), digest(bytea,text) | C (pgcrypto) | 摘要 |
| dbops | hmac(text,text,text), hmac(bytea,bytea,text) | C (pgcrypto) | HMAC |
| dbops | encrypt/decrypt 系列 | C (pgcrypto) | 对称加密 |
| dbops | pgp_sym_encrypt/decrypt 系列 | C (pgcrypto) | PGP 对称加密 |
| dbops | pgp_pub_encrypt/decrypt 系列 | C (pgcrypto) | PGP 公钥加密 |
| dbops | armor/dearmor | C (pgcrypto) | Base64 包装 |
| dbops | gen_random_bytes | C (pgcrypto) | 随机字节 |
| dbops | pgp_key_id, pgp_armor_headers | C (pgcrypto) | PGP 工具 |

> 共 37 个函数在 dbops namespace 下注册（pgcrypto 扩展安装在 dbops schema，故所有 pgcrypto C 函数均出现在 dbops schema）。

## 13. 触发器清单

17 个 BEFORE UPDATE 触发器，均调用 `dbops.set_updated_at()`：

| Trigger | Table |
|---|---|
| trg_users_updated_at | users |
| trg_system_group_updated_at | system_group |
| trg_business_system_updated_at | business_system |
| trg_contact_updated_at | contact |
| trg_site_updated_at | site |
| trg_os_version_updated_at | os_version |
| trg_db_type_updated_at | db_type |
| trg_db_version_updated_at | db_version |
| trg_server_updated_at | server |
| trg_cluster_updated_at | cluster |
| trg_db_instance_updated_at | db_instance |
| trg_topology_updated_at | topology_relation |
| trg_tag_updated_at | tag |
| trg_backup_policy_updated_at | backup_policy |
| trg_inspection_item_updated_at | inspection_item |
| trg_inspection_task_updated_at | inspection_task |
| trg_biz_score_rule_updated_at | biz_score_rule |

## 14. 扩展清单

| Extension | Version | Schema |
|---|---|---|
| plpgsql | 1.0 | pg_catalog |
| pgcrypto | 1.3 | dbops |

## 15. DDL 文件 vs 实际数据库差异

| 差异项 | DDL 文件描述 | 实际数据库 | 影响 |
|---|---|---|---|
| 一致 | — | 32 表 + 4 视图完全匹配 | DDL 文件与实际库一致 |
| 一致 | — | 126 个索引与 DDL 预期匹配 | |
| pgcrypto 安装位置 | 预期在 public | 实际在 dbops schema | pgcrypto 函数注册在 dbops namespace 下，不影响使用 |

## 16. 需现场确认

- 无重大差异。DDL 文件与数据库实际结构一致。
- 2026-06-04 新增 AWX 资产校验 DDL（`backend/db/dbops_awx_collector_phase1.sql`）已在开发库落库，并在后续元数据复扫中确认：
  - `db_instance` 新增校验字段与约束
  - 新增 `collector_run` / `collector_run_result`
  - 新增 collector 相关索引与触发器
- 2026-06-06 已在开发库执行 AWX 资产校验第二阶段 DDL（`backend/db/dbops_awx_collector_phase2_refactor.sql`），新增 `collector_run_item` / `asset_endpoint` / `asset_change_proposal` / `collector_check_definition`；本快照已按当前数据库状态刷新。
