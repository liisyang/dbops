# DB DDL History / Baseline

> 文档状态：AI 自动维护
> 最近更新：2026-06-13
> 依据来源：真实代码 / SQL 文件 / ORM Model / Service 查询
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

## 2. 环境信息

| 项目 | 内容 |
|---|---|
| 数据库类型 | PostgreSQL |
| Schema | dbops |
| 扩展依赖 | pgcrypto（gen_random_uuid / crypt / gen_salt） |
| ORM | SQLAlchemy 2.0.25（原生，非 Flask-SQLAlchemy） |
| search_path | dbops, public（`backend/app/database.py:18`） |
| DDL 来源 | `backend/db/dbops_phase1_25_tables.sql` |

## 3. DDL Baseline

### 3.1 Baseline 概述

- **变更日期**：2026-05（首次接入 baseline）
- **变更目的**：建立 DBOps 第一阶段可上线标准版数据库底座，覆盖平台认证、业务系统、联系人、站点/服务器、OS/DB 版本字典、集群/实例、拓扑、标签、备份策略、巡检、业务评分、Excel 导入暂存。
- **影响范围**：dbops schema 下 25 张业务表 + 1 张用户表 + 4 个视图 + 1 个函数 + 多个触发器 + 种子数据
- **DDL 来源**：`backend/db/dbops_phase1_25_tables.sql`（权威 SQL）、`backend/app/models/dbops_assets.py`（ORM 模型）、`backend/app/models/user.py`（用户模型）
- **历史归档参考**：`backend/db/archive/dbops_create_sql_V5.sql`（42 表旧版）、`backend/db/archive/dbops_create_sql_V5_R1.sql`（V5-R1 版，含 ops 双 schema）

### 3.2 公共函数

```sql
CREATE SCHEMA IF NOT EXISTS dbops;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION dbops.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

- **变更目的**：提供通用 `updated_at` 自动更新时间触发器函数
- **验证 SQL**：`SELECT proname FROM pg_proc WHERE pronamespace = 'dbops'::regnamespace AND proname = 'set_updated_at';`
- **回滚建议**：`DROP FUNCTION IF EXISTS dbops.set_updated_at() CASCADE;`（注意 CASCADE 会删除依赖触发器）

### 3.3 表清单（26 张）

| # | Table | 用途 | 主键类型 | ORM Model | 代码依据 |
|---:|---|---|---|---|---|
| 1 | users | 平台登录用户 | UUID | User (`backend/app/models/user.py:13`) | phase1 L29-42 |
| 2 | system_group | 业务大类（固定8类） | BIGSERIAL | SystemGroup (`dbops_assets.py:27`) | phase1 L143-150 |
| 3 | business_system | 业务系统 | BIGSERIAL | BusinessSystem (`dbops_assets.py:38`) | phase1 L180-195 |
| 4 | contact | 联系人主数据 | BIGSERIAL | Contact (`dbops_assets.py:60`) | phase1 L217-228 |
| 5 | business_system_contact | 业务系统-联系人关系 | BIGSERIAL | BusinessSystemContact (`dbops_assets.py:77`) | phase1 L251-262 |
| 6 | asset_event_history | 资产通用事件历史 | BIGSERIAL | AssetEventHistory (`dbops_assets.py:95`) | phase1 L274-287 |
| 7 | site | 站点/机房 | BIGSERIAL | Site (`dbops_assets.py:117`) | phase1 L311-323 |
| 8 | os_version | OS 版本字典 | BIGSERIAL | OsVersion (`dbops_assets.py:134`) | phase1 L346-362 |
| 9 | db_type | 数据库类型字典 | BIGSERIAL | DbType (`dbops_assets.py:155`) | phase1 L379-396 |
| 10 | db_version | 数据库版本字典 | BIGSERIAL | DbVersion (`dbops_assets.py:185`) | phase1 L470-488 |
| 11 | server | 服务器/虚拟机 | BIGSERIAL | Server (`dbops_assets.py:213`) | phase1 L511-529 |
| 12 | cluster | 数据库集群 | BIGSERIAL | Cluster (`dbops_assets.py:238`) | phase1 L550-564 |
| 13 | cluster_vip | 集群 VIP | BIGSERIAL | ClusterVip (`dbops_assets.py:260`) | phase1 L585-593 |
| 14 | db_instance | 数据库实例 | BIGSERIAL | DbInstance (`dbops_assets.py:277`) | phase1 L603-623 |
| 15 | topology_relation | 实例拓扑关系 | BIGSERIAL | TopologyRelation (`dbops_assets.py:311`) | phase1 L673-687 |
| 16 | tag | 标签字典 | BIGSERIAL | Tag (`dbops_assets.py:328`) | phase1 L707-716 |
| 17 | resource_tag | 资源标签关系 | BIGSERIAL | ResourceTag (`dbops_assets.py:341`) | phase1 L733-741 |
| 18 | backup_policy | 备份策略 | BIGSERIAL | BackupPolicy (`dbops_assets.py:355`) | phase1 L754-770 |
| 19 | instance_backup_policy | 实例-备份策略关系 | BIGSERIAL | InstanceBackupPolicy (`dbops_assets.py:363`) | phase1 L786-793 |
| 20 | inspection_item | 巡检项定义 | BIGSERIAL | InspectionItem (`dbops_assets.py:371`) | phase1 L804-814 |
| 21 | inspection_task | 巡检任务 | BIGSERIAL | InspectionTask (`dbops_assets.py:379`) | phase1 L829-843 |
| 22 | inspection_result | 巡检结果 | BIGSERIAL | InspectionResult (`dbops_assets.py:387`) | phase1 L860-873 |
| 23 | biz_score_rule | 业务评分规则 | BIGSERIAL | BizScoreRule (`dbops_assets.py:395`) | phase1 L885-895 |
| 24 | biz_score_result | 业务评分结果 | BIGSERIAL | BizScoreResult (`dbops_assets.py:403`) | phase1 L925-934 |
| 25 | biz_score_result_detail | 评分扣分明细 | BIGSERIAL | BizScoreResultDetail (`dbops_assets.py:410`) | phase1 L946-954 |
| 26 | staging_excel_import | Excel 导入暂存 | BIGSERIAL | StagingExcelImport (`dbops_assets.py:418`) | phase1 L966-1042 |

### 3.4 核心 CREATE TABLE DDL

#### 3.4.1 users — 平台登录用户

```sql
CREATE TABLE IF NOT EXISTS dbops.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(200) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(100),
    department VARCHAR(200),
    role VARCHAR(50) DEFAULT 'admin',
    is_active BOOLEAN DEFAULT true,
    timezone VARCHAR(50) DEFAULT 'Asia/Shanghai',
    language VARCHAR(20) DEFAULT 'zh-CN',
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- **索引**：`ix_dbops_users_username` ON (username)
- **触发器**：`trg_users_updated_at` BEFORE UPDATE → `dbops.set_updated_at()`
- **种子数据**：admin 用户（password_hash 使用 pgcrypto crypt/bf）
- **验证 SQL**：`SELECT count(*) FROM dbops.users;`
- **回滚建议**：`DROP TABLE IF EXISTS dbops.users CASCADE;`

#### 3.4.2 system_group — 业务大类

```sql
CREATE TABLE IF NOT EXISTS dbops.system_group (
    id BIGSERIAL PRIMARY KEY,
    group_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- **触发器**：`trg_system_group_updated_at`
- **种子数据**：ERP / 人資 / 園區 / 差旅 / 採購 / 相信 / 關務 / 電簽（8 类固定分类）
- **验证 SQL**：`SELECT * FROM dbops.system_group ORDER BY id;`

#### 3.4.3 business_system — 业务系统

```sql
CREATE TABLE IF NOT EXISTS dbops.business_system (
    id BIGSERIAL PRIMARY KEY,
    system_code VARCHAR(100) NOT NULL UNIQUE,
    system_name VARCHAR(300) NOT NULL UNIQUE,
    system_group_id BIGINT REFERENCES dbops.system_group(id),
    business_unit VARCHAR(200),
    department VARCHAR(200),
    service_scope TEXT,
    biz_level VARCHAR(50),
    status VARCHAR(20) DEFAULT 'building',
    remark TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_business_system_status CHECK (status IN ('building','pending','active','retired'))
);
```

- **索引**：`idx_business_system_group` ON (system_group_id)、`idx_business_system_status` ON (status)
- **CHECK**：status ∈ {building, pending, active, retired}
- **触发器**：`trg_business_system_updated_at`
- **Service 查询**：`DbopsAssetService.list_business_systems()` (`backend/app/services/dbops_asset_service.py:80`)
- **验证 SQL**：`SELECT status, count(*) FROM dbops.business_system GROUP BY status;`

#### 3.4.4 contact — 联系人主数据

```sql
CREATE TABLE IF NOT EXISTS dbops.contact (
    id BIGSERIAL PRIMARY KEY,
    employee_no VARCHAR(50),
    contact_code VARCHAR(100) NOT NULL UNIQUE,
    contact_name VARCHAR(100) NOT NULL,
    phone VARCHAR(100),
    email VARCHAR(200),
    dept VARCHAR(200),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- **后续 ALTER**：`ALTER TABLE dbops.contact ADD COLUMN IF NOT EXISTS employee_no VARCHAR(50);`（工号字段补充）
- **索引**：`idx_contact_employee_no` ON (employee_no)、`idx_contact_name_phone` ON (contact_name, phone)
- **触发器**：`trg_contact_updated_at`
- **种子数据**：`backend/db/contact_seed_contact_catalog_2026-05-15.sql`（175 条联系人记录）
- **Service 查询**：`DbopsContactService.list_contacts()` (`backend/app/services/dbops_contact_service.py:18`)

#### 3.4.5 business_system_contact — 业务联系人关系

```sql
CREATE TABLE IF NOT EXISTS dbops.business_system_contact (
    id BIGSERIAL PRIMARY KEY,
    business_system_id BIGINT NOT NULL REFERENCES dbops.business_system(id) ON DELETE CASCADE,
    contact_id BIGINT NOT NULL REFERENCES dbops.contact(id),
    role_code VARCHAR(50) NOT NULL,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_business_system_contact UNIQUE (business_system_id, contact_id, role_code),
    CONSTRAINT chk_business_contact_role CHECK (
        role_code IN ('OS_ADMIN','HOST_ADMIN','APP_OWNER','BUSINESS_MANAGER','BUSINESS_BELONG_MANAGER','DBA_OWNER')
    )
);
```

- **索引**：`idx_bsc_system` ON (business_system_id)、`idx_bsc_contact` ON (contact_id)
- **CHECK**：role_code ∈ {OS_ADMIN, HOST_ADMIN, APP_OWNER, BUSINESS_MANAGER, BUSINESS_BELONG_MANAGER, DBA_OWNER}
- **UNIQUE**：(business_system_id, contact_id, role_code)
- **Service 查询**：`DbopsAssetService` 中通过 `BusinessSystemContact` 模型查询联系人关联

#### 3.4.6 asset_event_history — 资产事件历史

```sql
CREATE TABLE IF NOT EXISTS dbops.asset_event_history (
    id BIGSERIAL PRIMARY KEY,
    asset_type VARCHAR(50) NOT NULL,
    asset_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    before_status VARCHAR(20),
    after_status VARCHAR(20),
    changed_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    operator VARCHAR(100),
    operated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    remark TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
```

- **索引**：`idx_asset_event_history_asset` ON (asset_type, asset_id, operated_at DESC)、`idx_asset_event_history_event` ON (event_type, operated_at DESC)
- **用途**：记录业务系统生命周期变更、资产状态变更等事件
- **Service 使用**：`backend/app/services/asset_event_history_service.py`

#### 3.4.7 site — 站点/机房

```sql
CREATE TABLE IF NOT EXISTS dbops.site (
    id BIGSERIAL PRIMARY KEY,
    site_code VARCHAR(100) NOT NULL UNIQUE,
    country VARCHAR(50) NOT NULL,
    deploy_type VARCHAR(50) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    factory_area VARCHAR(100) NOT NULL,
    room_location VARCHAR(200) NOT NULL,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_site_deploy_type CHECK (deploy_type IN ('地端','私有雲','公有雲'))
);
```

- **索引**：`idx_site_country` ON (country)、`idx_site_factory` ON (factory_area)、`idx_site_deploy_provider` ON (deploy_type, provider)
- **CHECK**：deploy_type ∈ {地端, 私有雲, 公有雲}
- **触发器**：`trg_site_updated_at`
- **设计说明**：第一阶段用单表 site 承载国家/厂区/部署类型/资源提供方/机房位置，不再拆 site_category / site_category_mapping（与旧版 V5 42 表设计不同）

#### 3.4.8 os_version — OS 版本字典

```sql
CREATE TABLE IF NOT EXISTS dbops.os_version (
    id BIGSERIAL PRIMARY KEY,
    os_code VARCHAR(100) NOT NULL UNIQUE,
    os_name VARCHAR(100) NOT NULL,
    version_name VARCHAR(200) NOT NULL,
    release_date DATE,
    eos_date DATE,
    eol_date DATE,
    lifecycle_status VARCHAR(50) DEFAULT 'unknown',
    risk_level VARCHAR(50) DEFAULT 'unknown',
    is_supported BOOLEAN DEFAULT true,
    is_recommended BOOLEAN DEFAULT false,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_os_name_version UNIQUE (os_name, version_name)
);
```

- **索引**：`idx_os_version_lifecycle` ON (lifecycle_status)
- **UNIQUE**：(os_name, version_name)
- **触发器**：`trg_os_version_updated_at`

#### 3.4.9 db_type — 数据库类型字典

```sql
CREATE TABLE IF NOT EXISTS dbops.db_type (
    id BIGSERIAL PRIMARY KEY,
    type_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL DEFAULT 'relational',
    license_type VARCHAR(20) NOT NULL DEFAULT 'commercial',
    vendor VARCHAR(100),
    remark TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT ck_db_type_category CHECK (
        category IN ('relational','nosql','cache','search','time_series','other')
    ),
    CONSTRAINT ck_db_type_license CHECK (
        license_type IN ('open_source','commercial','hybrid')
    )
);
```

- **后续 ALTER**：`ADD COLUMN IF NOT EXISTS category, license_type, vendor, remark, is_active`（增量添加字段，含条件 CHECK 约束添加）
- **CHECK**：category ∈ {relational, nosql, cache, search, time_series, other}、license_type ∈ {open_source, commercial, hybrid}
- **种子数据**：Oracle / SQL Server / Informix / InformixAP / Db2 / PostgreSQL / MariaDB / MySQL / MongoDB / Redis / Elasticsearch（11 种）
- **Service 查询**：`DbopsAssetService.list_db_types()` → 仅返回 `is_active = true` 的类型

#### 3.4.10 db_version — 数据库版本字典

```sql
CREATE TABLE IF NOT EXISTS dbops.db_version (
    id BIGSERIAL PRIMARY KEY,
    db_type_id BIGINT NOT NULL REFERENCES dbops.db_type(id),
    version_code VARCHAR(100) NOT NULL,
    version_name VARCHAR(200) NOT NULL,
    patch_version VARCHAR(200),
    architecture_bits VARCHAR(20),
    release_date DATE,
    eos_date DATE,
    eol_date DATE,
    lifecycle_status VARCHAR(50) DEFAULT 'unknown',
    risk_level VARCHAR(50) DEFAULT 'unknown',
    is_supported BOOLEAN DEFAULT true,
    is_recommended BOOLEAN DEFAULT false,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_db_version UNIQUE (db_type_id, version_code, patch_version)
);
```

- **后续 ALTER**：`ADD COLUMN IF NOT EXISTS architecture_bits VARCHAR(20);`
- **索引**：`idx_db_version_type` ON (db_type_id)、`idx_db_version_lifecycle` ON (lifecycle_status)
- **UNIQUE**：(db_type_id, version_code, patch_version)

#### 3.4.11 server — 服务器/虚拟机

```sql
CREATE TABLE IF NOT EXISTS dbops.server (
    id BIGSERIAL PRIMARY KEY,
    server_code VARCHAR(100) NOT NULL UNIQUE,
    hostname VARCHAR(200),
    ip_address INET NOT NULL UNIQUE,
    site_id BIGINT REFERENCES dbops.site(id),
    os_version_id BIGINT REFERENCES dbops.os_version(id),
    cpu_cores INTEGER,
    memory_gb NUMERIC(10,2),
    disk_gb NUMERIC(12,2),
    server_type VARCHAR(50),
    business_group VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    remark TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_server_status CHECK (status IN ('active','inactive','retired'))
);
```

- **索引**：`idx_server_site` ON (site_id)、`idx_server_os_version` ON (os_version_id)、`idx_server_status` ON (status)
- **CHECK**：status ∈ {active, inactive, retired}
- **ip_address 类型**：PostgreSQL INET（ORM 使用 `sqlalchemy.dialects.postgresql.INET`）
- **Service CRUD**：`DbopsAssetService.list_servers()` / `create_server()` / `update_server()` / `delete_server()`

#### 3.4.12 cluster — 数据库集群

```sql
CREATE TABLE IF NOT EXISTS dbops.cluster (
    id BIGSERIAL PRIMARY KEY,
    cluster_code VARCHAR(100) NOT NULL UNIQUE,
    cluster_name VARCHAR(200) NOT NULL,
    business_system_id BIGINT NOT NULL REFERENCES dbops.business_system(id),
    db_type_id BIGINT NOT NULL REFERENCES dbops.db_type(id),
    cluster_type VARCHAR(50) NOT NULL,
    ha_enabled BOOLEAN DEFAULT false,
    status VARCHAR(20) DEFAULT 'active',
    remark TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_cluster_status CHECK (status IN ('active','inactive','retired'))
);
```

- **索引**：`idx_cluster_system` ON (business_system_id)、`idx_cluster_db_type` ON (db_type_id)、`idx_cluster_type` ON (cluster_type)
- **CHECK**：status ∈ {active, inactive, retired}
- **cluster_code 生成规则**：`CLU-{DB_TYPE}-{CLUSTER_TYPE}-{HASH}`（系统生成，不依赖 Excel cluster_key）
- **cluster_type 支持值**：SINGLE / DATAGUARD / RAC / HDR / PATRONI / STREAMING_REPL / REPMGR / MGR / REDIS_SENTINEL / REDIS_CLUSTER / MONGODB_RS / MONGODB_SHARD（定义于 `backend/app/services/dbops_import_service.py:188-249`）
- **设计说明**：单实例也建 cluster（cluster_type = SINGLE），统一 SQL 和页面

#### 3.4.13 cluster_vip — 集群 VIP

```sql
CREATE TABLE IF NOT EXISTS dbops.cluster_vip (
    id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES dbops.cluster(id) ON DELETE CASCADE,
    vip_address TEXT NOT NULL,
    vip_type VARCHAR(50),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_cluster_vip UNIQUE (cluster_id, vip_address)
);
```

- **UNIQUE**：(cluster_id, vip_address)
- **vip_address 类型**：TEXT（兼容 IP、域名、SCAN 等格式）

#### 3.4.14 db_instance — 数据库实例

```sql
CREATE TABLE IF NOT EXISTS dbops.db_instance (
    id BIGSERIAL PRIMARY KEY,
    instance_code VARCHAR(100) NOT NULL UNIQUE,
    instance_name VARCHAR(200) NOT NULL,
    db_type_id BIGINT NOT NULL REFERENCES dbops.db_type(id),
    db_version_id BIGINT REFERENCES dbops.db_version(id),
    server_id BIGINT NOT NULL REFERENCES dbops.server(id),
    cluster_id BIGINT NOT NULL REFERENCES dbops.cluster(id),
    port INTEGER,
    service_name VARCHAR(200),
    node_role VARCHAR(50) DEFAULT 'unknown',
    db_size_gb NUMERIC(12,2),
    status VARCHAR(20) DEFAULT 'active',
    remark TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_instance_cluster_server_name_port UNIQUE (cluster_id, server_id, instance_name, port),
    CONSTRAINT chk_instance_status CHECK (status IN ('active','inactive','retired')),
    CONSTRAINT chk_node_role CHECK (node_role IN ('primary','standby','member','single','unknown'))
);
```

- **UNIQUE 变更记录**：旧约束 `uq_instance_cluster_name_port` → 新约束 `uq_instance_cluster_server_name_port`（`cluster_id, server_id, instance_name, port`），通过 DO 块条件 DROP + ADD 实现
- **索引**：`idx_instance_server` ON (server_id)、`idx_instance_cluster` ON (cluster_id)、`idx_instance_db_type` ON (db_type_id)、`idx_instance_status` ON (status)
- **CHECK**：status ∈ {active, inactive, retired}、node_role ∈ {primary, standby, member, single, unknown}
- **extra_attrs 常用字段**：engine_role, source_node_role, db_patch, instance_desc

#### 3.4.15 topology_relation — 实例拓扑关系

```sql
CREATE TABLE IF NOT EXISTS dbops.topology_relation (
    id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES dbops.cluster(id) ON DELETE CASCADE,
    source_instance_id BIGINT REFERENCES dbops.db_instance(id),
    target_instance_id BIGINT REFERENCES dbops.db_instance(id),
    relation_type VARCHAR(50) NOT NULL,
    sync_mode VARCHAR(50),
    status VARCHAR(50),
    lag_seconds INTEGER,
    remark TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_topology_relation UNIQUE (cluster_id, source_instance_id, target_instance_id, relation_type)
);
```

- **UNIQUE**：(cluster_id, source_instance_id, target_instance_id, relation_type)
- **索引**：`idx_topology_cluster` ON (cluster_id)、`idx_topology_source` ON (source_instance_id)、`idx_topology_target` ON (target_instance_id)
- **relation_type 语义**：primary_standby / leader_follower / member / replica / shard_member

#### 3.4.16 tag — 标签字典

```sql
CREATE TABLE IF NOT EXISTS dbops.tag (
    id BIGSERIAL PRIMARY KEY,
    tag_code VARCHAR(100) NOT NULL UNIQUE,
    tag_name VARCHAR(100) NOT NULL,
    tag_type VARCHAR(50),
    color VARCHAR(30),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- **索引**：`idx_tag_type` ON (tag_type)
- **tag_type**：scope / monitor / mdr / audit / custom

#### 3.4.17 resource_tag — 资源标签关系

```sql
CREATE TABLE IF NOT EXISTS dbops.resource_tag (
    id BIGSERIAL PRIMARY KEY,
    resource_type VARCHAR(50) NOT NULL,
    resource_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL REFERENCES dbops.tag(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_resource_tag UNIQUE (resource_type, resource_id, tag_id),
    CONSTRAINT chk_resource_tag_type CHECK (resource_type IN ('business_system','cluster','server','db_instance'))
);
```

- **索引**：`idx_resource_tag_resource` ON (resource_type, resource_id)、`idx_resource_tag_tag` ON (tag_id)
- **resource_id 不建外键**：由 resource_type 决定引用目标表（多态关联）

#### 3.4.18 backup_policy — 备份策略

```sql
CREATE TABLE IF NOT EXISTS dbops.backup_policy (
    id BIGSERIAL PRIMARY KEY,
    policy_code VARCHAR(100) NOT NULL UNIQUE,
    policy_name VARCHAR(200) NOT NULL,
    backup_type VARCHAR(50),
    schedule_cron VARCHAR(100),
    retention_days INTEGER,
    storage_type VARCHAR(50),
    storage_path TEXT,
    is_remote_backup BOOLEAN DEFAULT false,
    remote_backup_location TEXT,
    is_enabled BOOLEAN DEFAULT true,
    remark TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- **触发器**：`trg_backup_policy_updated_at`
- **注意**：ORM 模型仅定义了 id/policy_code/policy_name 三个字段（精简版），SQL DDL 是完整版

#### 3.4.19 instance_backup_policy — 实例备份策略关系

```sql
CREATE TABLE IF NOT EXISTS dbops.instance_backup_policy (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES dbops.db_instance(id) ON DELETE CASCADE,
    policy_id BIGINT NOT NULL REFERENCES dbops.backup_policy(id),
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_instance_backup_policy UNIQUE (instance_id, policy_id)
);
```

- **索引**：`idx_ibp_instance` ON (instance_id)、`idx_ibp_policy` ON (policy_id)

#### 3.4.20 inspection_item — 巡检项定义

```sql
CREATE TABLE IF NOT EXISTS dbops.inspection_item (
    id BIGSERIAL PRIMARY KEY,
    item_code VARCHAR(100) NOT NULL UNIQUE,
    item_name VARCHAR(200) NOT NULL,
    category VARCHAR(50),
    severity VARCHAR(20) DEFAULT 'info',
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_inspection_item_severity CHECK (severity IN ('info','warning','critical'))
);
```

- **CHECK**：severity ∈ {info, warning, critical}
- **触发器**：`trg_inspection_item_updated_at`

#### 3.4.21 inspection_task — 巡检任务

```sql
CREATE TABLE IF NOT EXISTS dbops.inspection_task (
    id BIGSERIAL PRIMARY KEY,
    task_code VARCHAR(100) NOT NULL UNIQUE,
    task_name VARCHAR(200) NOT NULL,
    scope_type VARCHAR(50),
    scope_id BIGINT,
    status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_inspection_task_status CHECK (status IN ('pending','running','success','failed','cancelled')),
    CONSTRAINT chk_inspection_task_scope CHECK (scope_type IN ('all','business_system','cluster','db_instance') OR scope_type IS NULL)
);
```

- **索引**：`idx_inspection_task_status` ON (status)
- **触发器**：`trg_inspection_task_updated_at`

#### 3.4.22 inspection_result — 巡检结果

```sql
CREATE TABLE IF NOT EXISTS dbops.inspection_result (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES dbops.inspection_task(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL REFERENCES dbops.inspection_item(id),
    target_type VARCHAR(50) NOT NULL,
    target_id BIGINT NOT NULL,
    result_status VARCHAR(20) NOT NULL,
    result_value TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_inspection_result_target CHECK (target_type IN ('business_system','cluster','db_instance','server')),
    CONSTRAINT chk_inspection_result_status CHECK (result_status IN ('ok','warning','failed','unknown'))
);
```

- **索引**：`idx_ir_task` ON (task_id)、`idx_ir_target` ON (target_type, target_id)、`idx_ir_status` ON (result_status)

#### 3.4.23 biz_score_rule — 业务评分规则

```sql
CREATE TABLE IF NOT EXISTS dbops.biz_score_rule (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(100) NOT NULL UNIQUE,
    rule_name VARCHAR(200) NOT NULL,
    description TEXT,
    deduct_score NUMERIC(5,2) NOT NULL,
    is_enabled BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- **种子数据**：NO_HA (扣5分) / NO_REMOTE_BACKUP (扣3分) / DB_EOL (扣2分) / OS_EOL (扣2分) / INSPECTION_FAILED (扣2分)

#### 3.4.24 biz_score_result — 业务评分结果

```sql
CREATE TABLE IF NOT EXISTS dbops.biz_score_result (
    id BIGSERIAL PRIMARY KEY,
    business_system_id BIGINT NOT NULL REFERENCES dbops.business_system(id) ON DELETE CASCADE,
    base_score NUMERIC(5,2) DEFAULT 10,
    deduct_score NUMERIC(5,2) DEFAULT 0,
    final_score NUMERIC(5,2) NOT NULL,
    score_level VARCHAR(20),
    score_batch VARCHAR(100),
    scored_at TIMESTAMP DEFAULT now()
);
```

- **索引**：`idx_score_result_system_time` ON (business_system_id, scored_at DESC)、`idx_score_result_batch` ON (score_batch)

#### 3.4.25 biz_score_result_detail — 评分扣分明细

```sql
CREATE TABLE IF NOT EXISTS dbops.biz_score_result_detail (
    id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL REFERENCES dbops.biz_score_result(id) ON DELETE CASCADE,
    rule_id BIGINT NOT NULL REFERENCES dbops.biz_score_rule(id),
    deduct_score NUMERIC(5,2) NOT NULL,
    reason TEXT,
    evidence JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now()
);
```

- **索引**：`idx_score_detail_result` ON (result_id)、`idx_score_detail_rule` ON (rule_id)

#### 3.4.26 staging_excel_import — Excel 导入暂存

```sql
CREATE TABLE IF NOT EXISTS dbops.staging_excel_import (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id VARCHAR(100),
    source_file_name VARCHAR(300),
    row_no INTEGER,
    system_name TEXT,
    platform_category TEXT,
    service_scope TEXT,
    biz_level TEXT,
    business_unit TEXT,
    department TEXT,
    source_cluster_no TEXT,
    cluster_type TEXT,
    node_role TEXT,
    normalized_node_role TEXT,
    normalized_engine_role TEXT,
    instance_name TEXT,
    port TEXT,
    service_name TEXT,
    db_size_gb TEXT,
    db_type TEXT,
    normalized_db_type TEXT,
    db_version TEXT,
    db_patch TEXT,
    os_name TEXT,
    os_version TEXT,
    ip TEXT,
    hostname TEXT,
    server_type TEXT,
    cpu_cores TEXT,
    memory_gb TEXT,
    disk_gb TEXT,
    business_group TEXT,
    country TEXT,
    deploy_type TEXT,
    provider TEXT,
    factory_area TEXT,
    room_location TEXT,
    dns_name TEXT,
    vip TEXT,
    host_admin TEXT,
    host_admin_contact TEXT,
    os_admin TEXT,
    os_admin_contact TEXT,
    app_owner TEXT,
    app_owner_contact TEXT,
    business_manager TEXT,
    business_manager_contact TEXT,
    business_belong_manager TEXT,
    dba_owner TEXT,
    backup_type TEXT,
    local_backup_policy TEXT,
    backup_manage_policy TEXT,
    remote_backup_location TEXT,
    monitor_tag TEXT,
    mdr_tag TEXT,
    audit_tag TEXT,
    db_account TEXT,
    db_password_raw TEXT,
    os_oracle TEXT,
    os_oracle_password_raw TEXT,
    os_root TEXT,
    os_password_raw TEXT,
    raw_payload JSONB DEFAULT '{}'::jsonb,
    imported_at TIMESTAMP DEFAULT now()
);
```

- **后续 ALTER**：`ADD COLUMN IF NOT EXISTS source_cluster_no, normalized_node_role, normalized_engine_role, normalized_db_type`
- **索引**：`idx_staging_batch` ON (import_batch_id)、`idx_staging_system` ON (system_name)、`idx_staging_ip` ON (ip)
- **安全注意**：`db_password_raw` 字段存储原始 Excel 密码，仅供暂存，正式表不存储明文密码

### 3.5 视图（4 个）

#### v_instance_full — 实例全量展示视图

```sql
CREATE OR REPLACE VIEW dbops.v_instance_full AS
SELECT
    bs.system_name,
    sg.name AS system_group,
    c.cluster_code, c.cluster_name, c.cluster_type, c.ha_enabled,
    di.instance_code, di.instance_name, di.node_role,
    dt.name AS db_type,
    dv.version_name AS db_version, dv.patch_version AS db_patch,
    s.hostname, s.ip_address,
    site.country, site.deploy_type, site.provider, site.factory_area, site.room_location
FROM dbops.db_instance di
JOIN dbops.cluster c ON c.id = di.cluster_id
JOIN dbops.business_system bs ON bs.id = c.business_system_id
LEFT JOIN dbops.system_group sg ON sg.id = bs.system_group_id
JOIN dbops.server s ON s.id = di.server_id
LEFT JOIN dbops.site site ON site.id = s.site_id
JOIN dbops.db_type dt ON dt.id = di.db_type_id
LEFT JOIN dbops.db_version dv ON dv.id = di.db_version_id;
```

#### v_staging_invalid_platform_category — 平台分类校验

```sql
CREATE OR REPLACE VIEW dbops.v_staging_invalid_platform_category AS
SELECT * FROM dbops.staging_excel_import
WHERE platform_category IS NOT NULL
  AND platform_category NOT IN ('ERP','人資','園區','差旅','採購','相信','關務','電簽');
```

#### v_staging_system_category_conflict — 系统分类冲突

```sql
CREATE OR REPLACE VIEW dbops.v_staging_system_category_conflict AS
SELECT system_name, COUNT(DISTINCT platform_category) AS category_count,
       STRING_AGG(DISTINCT platform_category, ',') AS categories
FROM dbops.staging_excel_import
WHERE system_name IS NOT NULL
GROUP BY system_name
HAVING COUNT(DISTINCT platform_category) > 1;
```

#### v_staging_invalid_site — Site 字段校验

```sql
CREATE OR REPLACE VIEW dbops.v_staging_invalid_site AS
SELECT * FROM dbops.staging_excel_import
WHERE deploy_type NOT IN ('地端','私有雲','公有雲')
   OR country IS NULL OR provider IS NULL OR factory_area IS NULL OR room_location IS NULL;
```

### 3.6 种子数据摘要

| 目标表 | 内容 | 记录数 | 来源 |
|---|---|---|---|
| users | admin 管理员用户 | 1 | `dbops_phase1_25_tables.sql:102-132` |
| system_group | 8 类业务大类 | 8 | `dbops_phase1_25_tables.sql:161-174` |
| db_type | 11 种数据库类型 | 11 | `dbops_phase1_25_tables.sql:445-464` |
| biz_score_rule | 5 条评分规则 | 5 | `dbops_phase1_25_tables.sql:905-919` |
| contact | 联系人目录 | 175 | `contact_seed_contact_catalog_2026-05-15.sql` |

### 3.7 核心关系链

```
system_group → business_system → cluster → db_instance
                                        → cluster_vip
                                        → topology_relation
site → server → db_instance
os_version → server
db_type → db_version → db_instance
db_type → cluster
contact → business_system_contact ← business_system
tag → resource_tag ← (business_system | cluster | server | db_instance)
backup_policy → instance_backup_policy ← db_instance
inspection_item → inspection_result ← inspection_task
biz_score_rule → biz_score_result_detail ← biz_score_result ← business_system
staging_excel_import (独立暂存表)
asset_event_history (独立事件表)
```

### 3.8 触发器清单

所有含 `updated_at` 字段的业务表均配置 BEFORE UPDATE 触发器自动更新：

| Table | Trigger | 函数 |
|---|---|---|
| users | trg_users_updated_at | dbops.set_updated_at() |
| system_group | trg_system_group_updated_at | dbops.set_updated_at() |
| business_system | trg_business_system_updated_at | dbops.set_updated_at() |
| contact | trg_contact_updated_at | dbops.set_updated_at() |
| site | trg_site_updated_at | dbops.set_updated_at() |
| os_version | trg_os_version_updated_at | dbops.set_updated_at() |
| db_type | trg_db_type_updated_at | dbops.set_updated_at() |
| db_version | trg_db_version_updated_at | dbops.set_updated_at() |
| server | trg_server_updated_at | dbops.set_updated_at() |
| cluster | trg_cluster_updated_at | dbops.set_updated_at() |
| db_instance | trg_db_instance_updated_at | dbops.set_updated_at() |
| topology_relation | trg_topology_updated_at | dbops.set_updated_at() |
| tag | trg_tag_updated_at | dbops.set_updated_at() |
| backup_policy | trg_backup_policy_updated_at | dbops.set_updated_at() |
| inspection_item | trg_inspection_item_updated_at | dbops.set_updated_at() |
| inspection_task | trg_inspection_task_updated_at | dbops.set_updated_at() |
| biz_score_rule | trg_biz_score_rule_updated_at | dbops.set_updated_at() |

### 3.9 确认的 ALTER TABLE 变更

DDL 中使用 `ADD COLUMN IF NOT EXISTS` 和条件 DO 块实现了向后兼容的增量变更：

1. **dbops.contact** — `ADD COLUMN IF NOT EXISTS employee_no VARCHAR(50)`
2. **dbops.db_type** — `ADD COLUMN IF NOT EXISTS category / license_type / vendor / remark / is_active`
3. **dbops.db_type** — 条件添加 `ck_db_type_category` / `ck_db_type_license` CHECK 约束
4. **dbops.db_version** — `ADD COLUMN IF NOT EXISTS architecture_bits VARCHAR(20)`
5. **dbops.staging_excel_import** — `ADD COLUMN IF NOT EXISTS source_cluster_no / normalized_node_role / normalized_engine_role / normalized_db_type`
6. **dbops.db_instance** — UNIQUE 约束从 `uq_instance_cluster_name_port` 迁移到 `uq_instance_cluster_server_name_port`（条件 DROP + ADD）
7. **dbops.users** — 从 `ops.users` 迁移数据（DO 块条件 INSERT ON CONFLICT UPDATE）

### 3.10 已知历史迁移（来源：.pyc 缓存文件）

以下迁移文件仅存在于 `backend/db/__pycache__/`（源代码 .py 已删除），具体 DDL 内容无法完整还原：

| 迁移文件 | 推测内容 |
|---|---|
| `migrate_v4_4_cmdb_lite.py` | 从更早版本迁移到 CMDB Lite 结构 |
| `migrate_asset_fields.py` | 资产字段扩展/调整 |
| `migrate_drop_cluster_id.py` | 删除某表的 cluster_id 列（可能是 db_instance 重构） |

> 需现场确认：原始 .py 迁移脚本是否存在于其他位置或 Git 历史中。

## 4. 接入后的 DDL 变更记录

### 4.1 2026-06-04 — AWX 资产校验第一阶段最小闭环

- **变更类型**：增量 DDL（新增表 + 扩展已有表）
- **DDL 文件**：`backend/db/dbops_awx_collector_phase1.sql`
- **变更摘要**：
  1. `dbops.db_instance` 新增校验字段：`trust_status`、`reachability_status`、`last_seen_at`、`last_verify_at`、`verify_message`、`last_verify_run_id`、`last_awx_job_id`、`verify_detail`
  2. `dbops.db_instance` 新增约束：`chk_db_instance_trust_status`、`chk_db_instance_reachability_status`
  3. 新增 `dbops.collector_run`
  4. 新增 `dbops.collector_run_result`
  5. 新增相关索引与 `trg_collector_run_updated_at`

- **回滚建议（需人工确认后执行）**：

```sql
BEGIN;
SET search_path TO dbops, public;
DROP TABLE IF EXISTS dbops.collector_run_result;
DROP TABLE IF EXISTS dbops.collector_run;
ALTER TABLE dbops.db_instance
    DROP CONSTRAINT IF EXISTS chk_db_instance_trust_status,
    DROP CONSTRAINT IF EXISTS chk_db_instance_reachability_status,
    DROP COLUMN IF EXISTS trust_status,
    DROP COLUMN IF EXISTS reachability_status,
    DROP COLUMN IF EXISTS last_seen_at,
    DROP COLUMN IF EXISTS last_verify_at,
    DROP COLUMN IF EXISTS verify_message,
    DROP COLUMN IF EXISTS last_verify_run_id,
    DROP COLUMN IF EXISTS last_awx_job_id,
    DROP COLUMN IF EXISTS verify_detail;
COMMIT;
```

- **2026-06-08 端口校准 refactor 说明**：候选合并、`include_related_server` 与 `candidate_state` 仅影响后端逻辑和前端展示，不引入新的 DDL。

- **状态**：已在开发库执行并在后续元数据复扫中确认。

### 4.2 2026-06-06 — AWX 资产校验第二阶段通用 item 底座（代码内 DDL）

- **变更类型**：增量 DDL（已在开发库执行）
- **DDL 文件**：`backend/db/dbops_awx_collector_phase2_refactor.sql`
- **变更摘要**：
  1. `collector_run` 增加 `target_scope`、`server_id`、`item_count`，并放宽 `db_instance_id` / `target_host` / `target_port`
  2. 新增 `collector_check_definition`
  3. 新增 `collector_run_item`
  4. 新增 `asset_endpoint`
  5. 新增 `asset_change_proposal`
  6. `collector_run_result` 增加 `item_key`、`check_code`、`target_scope`、`server_id`、`collector_run_item_id`、`result_message`、`updated_at`
  7. `collector_run_result` 唯一键从 run 级调整为 item 级

- **回滚建议（需人工确认后执行）**：

```sql
BEGIN;
SET search_path TO dbops, public;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP CONSTRAINT IF EXISTS uq_collector_run_result_item_id;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP CONSTRAINT IF EXISTS uq_collector_run_result_item;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP COLUMN IF EXISTS collector_run_item_id;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP COLUMN IF EXISTS item_key;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP COLUMN IF EXISTS check_code;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP COLUMN IF EXISTS target_scope;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP COLUMN IF EXISTS server_id;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP COLUMN IF EXISTS result_message;
ALTER TABLE IF EXISTS dbops.collector_run_result DROP COLUMN IF EXISTS updated_at;
DROP TABLE IF EXISTS dbops.asset_change_proposal;
DROP TABLE IF EXISTS dbops.asset_endpoint;
DROP TABLE IF EXISTS dbops.collector_run_item;
DROP TABLE IF EXISTS dbops.collector_check_definition;
ALTER TABLE IF EXISTS dbops.collector_run DROP COLUMN IF EXISTS target_scope;
ALTER TABLE IF EXISTS dbops.collector_run DROP COLUMN IF EXISTS server_id;
ALTER TABLE IF EXISTS dbops.collector_run DROP COLUMN IF EXISTS item_count;
COMMIT;
```

- **状态**：已在开发库执行，`docs/db/schema-snapshot.md` 已按当前元数据刷新。

### 4.3 2026-06-08 — Phase 3.1 端口画像 + 端点治理 + 半自动端口校准

- **变更类型**：增量 DDL（兼容已有结构，优先补字段）
- **DDL 文件**：`backend/db/dbops_port_profile_phase3_1.sql`
- **变更摘要**：
  1. 新增 `dbops.port_profile`
  2. 初始化 Linux/Windows/Oracle/SQLServer 默认与候选端口画像（幂等 upsert）
  3. `collector_run_item` 增加 `endpoint_type`、`port_source`、`is_required`
  4. `collector_run_result` 增加 `endpoint_type`、`protocol`、`port_source`、`is_required`
  5. `asset_endpoint` 增加 `last_checked_at`、`last_item_key`、`reachable`、`port_source`、`is_required`
  6. `asset_change_proposal` 兼容增强：增加 `proposal_type`、`field_path`、`current_value`、`suggested_value`、`confidence`、`source_run_id`、`source_item_key`

- **回滚建议（需人工确认后执行）**：

```sql
BEGIN;
SET search_path TO dbops, public;
ALTER TABLE IF EXISTS dbops.asset_change_proposal
    DROP COLUMN IF EXISTS proposal_type,
    DROP COLUMN IF EXISTS field_path,
    DROP COLUMN IF EXISTS current_value,
    DROP COLUMN IF EXISTS suggested_value,
    DROP COLUMN IF EXISTS confidence,
    DROP COLUMN IF EXISTS source_run_id,
    DROP COLUMN IF EXISTS source_item_key;
ALTER TABLE IF EXISTS dbops.asset_endpoint
    DROP COLUMN IF EXISTS last_checked_at,
    DROP COLUMN IF EXISTS last_item_key,
    DROP COLUMN IF EXISTS reachable,
    DROP COLUMN IF EXISTS port_source,
    DROP COLUMN IF EXISTS is_required;
ALTER TABLE IF EXISTS dbops.collector_run_result
    DROP COLUMN IF EXISTS endpoint_type,
    DROP COLUMN IF EXISTS protocol,
    DROP COLUMN IF EXISTS port_source,
    DROP COLUMN IF EXISTS is_required;
ALTER TABLE IF EXISTS dbops.collector_run_item
    DROP COLUMN IF EXISTS endpoint_type,
    DROP COLUMN IF EXISTS port_source,
    DROP COLUMN IF EXISTS is_required;
DROP TABLE IF EXISTS dbops.port_profile;
COMMIT;
```

### 4.4 2026-06-13 — Phase 3.4 基础巡检中心

- **变更类型**：增量 DDL（可重复执行，`IF NOT EXISTS`）
- **DDL 文件**：`backend/db/dbops_phase3_4.sql`
- **变更摘要**：
  1. 新增 `inspection_schedule`（周期计划）
  2. 扩展 `inspection_item`：`check_code/target_scope/severity/enabled/rule_config` 等字段
  3. 扩展 `inspection_task`：`batch_run_id/schedule_id/run_type/check_codes/item_codes/asset_ids` 等字段（status CHECK 同步增加 `partial_success`）
  4. 扩展 `inspection_result`：`result_code/result_status/severity/evidence/collector_run*` 等字段
  5. 初始化首批 8 个基础巡检项（CONNECTIVITY_PORT_REACHABLE 等）
  6. **收尾**：`DROP CONSTRAINT chk_inspection_result_target`（旧约束 target_type 集合含 `business_system`/`cluster`/`db_instance`/`server`，与 Phase 3.4 收窄后的 `chk_inspection_result_target_type` 共存冗余；DROP 不影响历史数据，应用层自 Phase 3.4 起只写 `server`/`db_instance`）

- **回滚建议（需人工确认后执行）**：

```sql
BEGIN;
SET search_path TO dbops, public;
ALTER TABLE IF EXISTS dbops.inspection_result
    DROP COLUMN IF EXISTS batch_run_id,
    DROP COLUMN IF EXISTS collector_run_id,
    DROP COLUMN IF EXISTS collector_run_item_id,
    DROP COLUMN IF EXISTS result_code,
    DROP COLUMN IF EXISTS message,
    DROP COLUMN IF EXISTS evidence,
    DROP COLUMN IF EXISTS detected_at;
ALTER TABLE IF EXISTS dbops.inspection_task
    DROP COLUMN IF EXISTS schedule_id,
    DROP COLUMN IF EXISTS batch_run_id,
    DROP COLUMN IF EXISTS run_type,
    DROP COLUMN IF EXISTS check_codes,
    DROP COLUMN IF EXISTS item_codes,
    DROP COLUMN IF EXISTS asset_ids,
    DROP COLUMN IF EXISTS request_payload;
ALTER TABLE IF EXISTS dbops.inspection_item
    DROP COLUMN IF EXISTS check_code,
    DROP COLUMN IF EXISTS target_scope,
    DROP COLUMN IF EXISTS enabled,
    DROP COLUMN IF EXISTS rule_config;
DROP TABLE IF EXISTS dbops.inspection_schedule;
COMMIT;
```

- **状态**：DDL 脚本已入库；目标环境是否已执行需现场确认。

### 4.4.1 2026-06-13 — Phase 3.4 重名 FK 收尾

- **变更类型**：约束命名修正（删除冗余短名 FK，DDL 同步改用 PG 默认名）
- **DDL 文件**：`backend/db/dbops_phase3_4.sql`（3 处 DO 块：`fk_inspection_task_batch_run` / `fk_inspection_result_batch_run` / `fk_inspection_result_collector_run_item` → `<table>_<col>_fkey`）
- **变更摘要**：
  1. `dbops.inspection_result.batch_run_id`：DROP `fk_inspection_result_batch_run`，保留 `inspection_result_batch_run_id_fkey`
  2. `dbops.inspection_result.collector_run_item_id`：DROP `fk_inspection_result_collector_run_item`，保留 `inspection_result_collector_run_item_id_fkey`
  3. `dbops.inspection_task.batch_run_id`：DROP `fk_inspection_task_batch_run`，保留 `inspection_task_batch_run_id_fkey`
  4. 改 DDL：3 处 DO 块的条件查询与 `ADD CONSTRAINT` 都改用 PG 默认名，避免下次重跑脚本时再次产生重名
- **风险面**：DROP 前已 grep 应用层代码无任何短名 FK 引用；真表上默认名 FK 已存在，DROP 短名不影响引用完整性；完全可逆（重跑改后的 DDL 幂等 no-op）
- **回滚建议（需人工确认后执行）**：

```sql
BEGIN;
SET search_path TO dbops, public;
-- 重新 ADD 短名 FK（与默认名共存，回到重名状态，仅用于应急回退）
ALTER TABLE dbops.inspection_result
    ADD CONSTRAINT fk_inspection_result_batch_run
    FOREIGN KEY (batch_run_id) REFERENCES dbops.collector_batch_run(id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_inspection_result_collector_run_item
    FOREIGN KEY (collector_run_item_id) REFERENCES dbops.collector_run_item(id) ON DELETE SET NULL;
ALTER TABLE dbops.inspection_task
    ADD CONSTRAINT fk_inspection_task_batch_run
    FOREIGN KEY (batch_run_id) REFERENCES dbops.collector_batch_run(id) ON DELETE SET NULL;
COMMIT;
```

- **状态**：已在 10.134.185.85:5432/dbops 执行；DDL 改后重跑验证为 idempotent（全部 `NOTICE: already exists, skipping`，无 ERROR）；`docs/db/schema-snapshot.md` 9 节"需现场确认"中"inspection_result 重名 FK"项可移除（已解决）。

## 5. Phase1→3.4 漏记字段排查

> 2026-06-13 第三轮收尾：通过 `information_schema.columns` 对比仓库 DDL 文件，发现 `inspection_item` 与 `inspection_result` 真表上存在 9 个**仓库无 DDL 来源**的字段（git 全历史 `git log --all -p -- 'backend/db/*.sql'` 无任何 ALTER ADD COLUMN 痕迹）。AI 不擅自 DROP/ALTER，仅记录现状 + 治理建议，待人工确认后由后续 phase 处理。

### 5.1 漏记字段清单

| 表 | 字段 | 类型 | Nullable | Default | 疑似来源 | 与之重叠的有效字段 |
|---|---|---|---|---|---|---|
| `inspection_item` | `target_type` | varchar(50) | YES | | V5/phase1 早期设计遗留 | `target_scope` (phase3_4) |
| `inspection_item` | `threshold_config` | jsonb | NO | `'{}'` | V5 archive `threshold_rule` 概念演化版 | `rule_config` (phase3_4) |
| `inspection_item` | `status` | varchar(20) | NO | `'enabled'` | V5/phase1 早期设计遗留 | `enabled` (phase3_4) |
| `inspection_result` | `dispatch_run_id` | bigint | YES | | 疑似 Phase 3.2 batch verify 风格补字段（未沉淀） | — |
| `inspection_result` | `server_id` | bigint | YES | | 疑似 Phase 3.2 风格补字段，与 `collector_run.server_id` 对齐（未沉淀） | — |
| `inspection_result` | `db_instance_id` | bigint | YES | | 疑似 Phase 3.2 风格补字段（未沉淀） | — |
| `inspection_result` | `status` | varchar(30) | YES | | V5 archive `status` 概念遗留 | `result_status` (phase3_4) |
| `inspection_result` | `actual_value` | jsonb | YES | | V5 archive `result_value` 的 jsonb 版本（疑似） | `result_value` (phase1, text) |
| `inspection_result` | `details` | text | YES | | V5/phase1 早期设计遗留 | `message` (phase3_4) |

### 5.2 排查依据

```bash
# 1) 拉真表全字段
psql -h 10.134.185.85 -p 5432 -U dbops -d dbops -c "
  SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
  WHERE table_schema='dbops' AND table_name IN ('inspection_item','inspection_result')
  ORDER BY table_name, ordinal_position;"

# 2) 仓库 DDL 文件检索
grep -n "threshold_config\|actual_value\|dispatch_run_id" backend/db/*.sql backend/db/archive/*.sql
# threshold_config / actual_value / status('enabled') / details / target_type / dispatch_run_id：
#   无任何 ADD COLUMN 命中（dispatch_run_id 仅在 collector_run / collector_run_item 出现）

# 3) git 全历史检索
git log --all -p -- 'backend/db/*.sql' | grep -B 2 -A 1 "ADD COLUMN.*\(threshold_config\|actual_value\|details\)"
# 全部为空
```

### 5.3 治理建议（未来 phase 决策）

按 CLAUDE.md「真实代码优先 + 不确定标注需现场确认」，AI 不自动处理，列出 3 条候选路径供人工选择：

**路径 A：DROP 漏记字段（推荐）** — 如果业务代码确认无引用：

```sql
-- 需先验证 0 行非默认值数据，再人工执行
BEGIN;
SET search_path TO dbops, public;

ALTER TABLE dbops.inspection_item
    DROP COLUMN IF EXISTS target_type,
    DROP COLUMN IF EXISTS threshold_config,
    DROP COLUMN IF EXISTS status;

ALTER TABLE dbops.inspection_result
    DROP COLUMN IF EXISTS dispatch_run_id,
    DROP COLUMN IF EXISTS server_id,
    DROP COLUMN IF EXISTS db_instance_id,
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS actual_value,
    DROP COLUMN IF EXISTS details;

COMMIT;
```

**路径 B：保留并补 DDL** — 如果业务代码确认有引用（需 grep 验证）：在 `backend/db/dbops_phase1_25_tables.sql` 末尾追加 idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`，把这 9 个字段补到 DDL 文件；并在 schema-snapshot.md 7.20 / 7.22 移除"漏记字段"标注。

**路径 C：保留并 deprecate** — 折中方案：保留字段 + 在 ORM model 上加注释 `# DEPRECATED: use rule_config` 等；DDL 文件不补；后续业务慢慢迁移至新字段。

### 5.4 验证 grep 命令（执行前 DBA 务必跑）

```bash
# 任何漏记字段被 ORM/Service/Schema/前端引用 → 走路径 B 或 C，不能 A
grep -rE "(threshold_config|actual_value|dispatch_run_id|details|target_type)" \
  backend/app/ frontend/src/ 2>/dev/null | grep -v "node_modules\|__pycache__\|target_type_id"
# 当前（2026-06-13）：threshold_config / actual_value / details 均无 ORM 字段；
# target_type 在 inspection_result 应用代码有用（但那是 phase3_4 有效字段，不是漏记的 inspection_item.target_type）。
# 待 DBA 复核后再决定路径。
```

- **状态**：记录中，未执行任何 DDL 变更；DROP 决策需 DBA + 业务方共同确认；后续 phase 3.5 起新任务"漏记字段治理"统一处理。

