# DB 附录

> 文档状态：AI 自动维护
> 最近校准：2026-05-22
> 依据来源：真实代码 / DDL baseline / ORM Model / Service 查询 / 实时数据库元数据扫描（PostgreSQL 17.9）

## 1. 维护定位

本文件只记录数据库核心摘要，不记录全量字段。

全量 DDL baseline 和接入后的 DDL 变更见：

- `docs/db/ddl-history.md`

当前测试库 / 开发库结构快照见：

- `docs/db/schema-snapshot.md`

## 2. 数据库类型

| 项目 | 内容 |
|---|---|
| 数据库类型 | PostgreSQL 17.9 |
| 当前连接环境 | 测试库 / 开发库（已连接扫描，结构已与 DDL 文件校准） |
| 权限边界 | 由数据库账号控制 |
| 结构来源 | `backend/db/dbops_phase1_25_tables.sql` + `backend/db/dbops_awx_collector_phase2_refactor.sql` + ORM 模型 + Service 查询 + 实时元数据扫描 |
| 文档维护方式 | AI 自动维护 |

## 3. DB 连接安全边界

1. AI 不保存连接串。
2. AI 不输出连接串。
3. AI 不把连接信息写入 docs。
4. AI 不把连接信息写入 Git。
5. DB 连接信息只允许来自本地环境变量、CI Secret 或人工临时输入。
6. 生产库连接必须人工明确确认。
7. 测试库 / 开发库账号必须由数据库权限控制只读范围。

## 4. 核心 Schema

| Schema | 用途 | 依据 | 备注 |
|---|---|---|---|
| dbops | DBOps 平台主 schema，当前 baseline 为 26 张业务表；2026-06-04 增量新增 collector_run / collector_run_result（执行后共 28 表）；2026-06-06 phase2 refactor 已在开发库落库（32 表）；2026-06-08 Phase 3.1 新增 port_profile 并增强 endpoint/proposal 字段（33 表）；2026-06-08 端口校准 refactor 仅调整候选去重与语义，不新增表结构 | `backend/db/dbops_phase1_25_tables.sql:8` + `backend/db/dbops_awx_collector_phase1.sql` + `backend/db/dbops_awx_collector_phase2_refactor.sql` + `backend/db/dbops_port_profile_phase3_1.sql` + `backend/app/database.py:18` | search_path=dbops,public；pgcrypto 扩展安装在 dbops schema |
| public | PostgreSQL 默认 schema | — | plpgsql 扩展所在 |

## 5. 核心表摘要

| 模块 | Table | 用途 | 关键字段 | 依据 |
|---|---|---|---|---|
| 认证 | users | 平台登录用户 | username, password_hash, role | `backend/app/models/user.py:13` |
| 业务 | system_group | 业务大类（8 类固定） | group_code, name | `backend/app/services/dbops_stats_service.py:82-88` |
| 业务 | business_system | 业务系统主数据 | system_name, status, biz_level | `backend/app/services/dbops_asset_service.py:80-129` |
| 联系人 | contact | 联系人主数据 | employee_no, contact_name, email | `backend/app/services/dbops_contact_service.py:18-35` |
| 联系人 | business_system_contact | 业务-联系人角色关系 | role_code (6 种角色) | `backend/app/services/dbops_asset_service.py:176-201` |
| 资产 | site | 站点/机房 | country, deploy_type, provider, factory_area | `backend/app/services/dbops_import_service.py:744-765` |
| 资产 | server | 服务器/虚拟机 | ip_address (INET), site_id, status | `backend/app/services/dbops_asset_service.py:390-503` |
| 资产 | cluster | 数据库集群 | cluster_code, cluster_type, ha_enabled | `backend/app/services/dbops_asset_service.py:295-325` |
| 资产 | cluster_vip | 集群 VIP | vip_address, vip_type | `backend/app/services/dbops_asset_service.py:302-303` |
| 资产 | db_instance | 数据库实例 | instance_name, node_role, cluster_id | `backend/app/services/dbops_asset_service.py:341-380` |
| 自动化校验 | collector_run | AWX 校验任务主记录 | run_id, target_scope, db_instance_id, server_id, status | `backend/app/models/dbops_assets.py` |
| 自动化校验 | collector_run / collector_run_item / collector_run_result / asset_endpoint | AWX 校验任务、item 明细、结果明细、端点状态（Phase 3.1 增加 endpoint metadata） | run_id, item_key, check_code, endpoint_type, protocol, port_source, is_required, reachable | `backend/app/models/dbops_assets.py` + `backend/db/dbops_awx_collector_phase2_refactor.sql` + `backend/db/dbops_port_profile_phase3_1.sql` |
| 自动化校验 | port_profile | 端口画像与候选端口配置 | profile_code, target_scope, endpoint_type, default_port, is_required, priority | `backend/app/models/dbops_assets.py` + `backend/db/dbops_port_profile_phase3_1.sql` |
| 资产 | topology_relation | 实例拓扑关系 | relation_type, sync_mode | `backend/app/services/dbops_import_service.py:1030-1062` |
| 资产 | asset_event_history | 资产事件历史 | asset_type, event_type, changed_fields | `backend/app/services/asset_event_history_service.py` |
| 字典 | os_version | OS 版本字典+生命周期 | os_name, version_name, lifecycle_status | ORM 模型 |
| 字典 | db_type | DB 类型字典 | type_code, category, license_type | `backend/app/services/dbops_asset_service.py:506-508` |
| 字典 | db_version | DB 版本字典+生命周期 | version_code, patch_version | ORM 模型 |
| 标签 | tag | 标签字典 | tag_type, tag_name | ORM 模型 |
| 标签 | resource_tag | 资源标签关系（多态） | resource_type, resource_id, tag_id | ORM 模型 |
| 备份 | backup_policy | 备份策略 | policy_code, backup_type, retention_days | ORM 模型 |
| 备份 | instance_backup_policy | 实例-策略关系 | instance_id, policy_id | ORM 模型 |
| 巡检 | inspection_item | 巡检项定义 | item_code, category, severity | ORM 模型 |
| 巡检 | inspection_task | 巡检任务 | task_code, scope_type, status | ORM 模型 |
| 巡检 | inspection_result | 巡检结果 | target_type, result_status | ORM 模型 |
| 评分 | biz_score_rule | 评分规则 | rule_code, deduct_score | ORM 模型 |
| 评分 | biz_score_result | 评分结果 | final_score, score_batch | ORM 模型 |
| 评分 | biz_score_result_detail | 评分明细 | evidence (JSONB) | ORM 模型 |
| 导入 | staging_excel_import | Excel 导入暂存 | import_batch_id, raw_payload | `backend/app/services/dbops_import_service.py:1065-1101` |

## 6. 关键索引摘要

| Table | Index | 用途 | 依据 |
|---|---|---|---|
| users | ix_dbops_users_username | 用户名登录查询 | phase1 L49 |
| business_system | idx_business_system_status | 按状态筛选 | phase1 L206 |
| contact | idx_contact_name_phone | 姓名+电话联合查重 | phase1 L240 |
| server | idx_server_site / idx_server_status | 按站点/状态筛选 | phase1 L537-539 |
| cluster | idx_cluster_system / idx_cluster_db_type / idx_cluster_type | 集群多维查询 | phase1 L572-574 |
| db_instance | idx_instance_cluster / idx_instance_server / idx_instance_status | 实例核心查询 | phase1 L659-662 |
| db_instance | idx_db_instance_trust_status / idx_db_instance_reachability_status / idx_db_instance_last_verify_at | 资产校验状态查询 | `backend/db/dbops_awx_collector_phase1.sql` |
| collector_run | idx_collector_run_instance_time / idx_collector_run_status / idx_collector_run_awx_job | 按实例、状态、AWX job 查询校验任务 | `backend/db/dbops_awx_collector_phase1.sql` |
| collector_run_result | idx_collector_run_result_instance_time / idx_collector_run_result_server_time | 按实例/服务器回看历史校验结果 | `backend/db/dbops_awx_collector_phase2_refactor.sql` |
| port_profile | idx_port_profile_scope / idx_port_profile_db_type / idx_port_profile_os_family / idx_port_profile_enabled / idx_port_profile_endpoint_type | 按 scope、DB 类型、OS 家族检索候选端口 | `backend/db/dbops_port_profile_phase3_1.sql` |
| staging_excel_import | idx_staging_batch | 按批次查询导入记录 | phase1 L1054 |
| biz_score_result | idx_score_result_system_time | 业务评分历史趋势 | phase1 L939 |
| asset_event_history | idx_asset_event_history_asset | 资产事件时间线 | phase1 L302-303 |

## 7. DDL 与测试库差异摘要

| 类型 | 对象 | 差异 | 影响 | 建议 |
|---|---|---|---|---|
| pgcrypto 安装位置 | pgcrypto 扩展 | DDL 未指定 schema，实际安装在 dbops schema | 无功能影响 | 不影响 pgcrypto 函数调用 |
| 一致 | 26 表 + 4 视图 + 98 索引 + 约束 + 序列 + 触发器 | DDL 文件与实际数据库结构完全一致 | — | 无需变更 |

## 8. 结构风险

| 风险 | 影响范围 | 验证方式 | 建议 |
|---|---|---|---|
| staging_excel_import 存明文密码 | db_password_raw / os_password_raw 字段 | `SELECT count(*) FROM dbops.staging_excel_import WHERE db_password_raw IS NOT NULL;` | 定期清理暂存表或脱敏处理 |
| resource_tag 无外键约束 | resource_id 可能指向不存在的资源 | 应用层校验 | 后续可加触发器或定期清理孤记录 |
| backup_policy / inspection_item 等表无 API | 表结构已存在但无后端 API | 确认前端模块排期 | 10-module-map 已标注为"规划中" |
| AWX callback 依赖网络可达性与 token 一致性 | 回调失败会导致状态无法回写 | 使用 curl 从 AWX 网络侧校验 callback URL 与 token | `backend/app/api/collector.py` |

## 9. 需现场确认

- 历史迁移脚本（migrate_v4_4_cmdb_lite / migrate_asset_fields / migrate_drop_cluster_id）原始 .py 源码位置（仅在 `__pycache__` 中存在 .pyc 缓存）
- backup_policy / inspection / biz_score 等表的 API 开发排期
- 2026-06-04 增量 DDL 在目标开发库是否已执行并完成元数据复扫（需现场确认）

> 2026-05-22：已连接测试库完成实时元数据扫描，DDL 文件与实际库结构一致。
