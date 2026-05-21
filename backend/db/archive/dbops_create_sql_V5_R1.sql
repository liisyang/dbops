-- DBOPS V5-R1 平台底座建表脚本
-- 目标数据库：PostgreSQL 15+
-- 范围：
--   1. ops schema：平台用户与登录
--   2. dbops schema：业务系统、DB资产、联系人、导入、治理
-- 说明：
--   1. 本脚本适用于全新环境初始化
--   2. 可重复执行

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS dbops;

-- ============================================================
-- ops schema: 平台认证
-- ============================================================

CREATE TABLE IF NOT EXISTS ops.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    department VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'dba',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Shanghai',
    language VARCHAR(10) NOT NULL DEFAULT 'zh',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_ops_users_username ON ops.users(username);

INSERT INTO ops.users (
    username,
    email,
    password_hash,
    full_name,
    department,
    role,
    is_active,
    timezone,
    language
)
VALUES (
    'admin',
    'admin@example.com',
    crypt('Unixadm88', gen_salt('bf', 12)),
    '系统管理员',
    'DBOPS',
    'admin',
    TRUE,
    'Asia/Shanghai',
    'zh'
)
ON CONFLICT (username) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    department = EXCLUDED.department,
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active,
    timezone = EXCLUDED.timezone,
    language = EXCLUDED.language;

-- ============================================================
-- dbops schema: 基础字典与主数据
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.system_group (
    id BIGSERIAL PRIMARY KEY,
    group_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dbops.biz_level (
    id BIGSERIAL PRIMARY KEY,
    level_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(20) NOT NULL UNIQUE,
    level_value INTEGER NOT NULL UNIQUE,
    color VARCHAR(20),
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dbops.env_catalog (
    code VARCHAR(30) PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dbops.db_type_catalog (
    code VARCHAR(30) PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dbops.contact_role_catalog (
    role_code VARCHAR(50) PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        role_code IN (
            'OS_ADMIN',
            'HOST_ADMIN',
            'APP_OWNER',
            'BUSINESS_MANAGER',
            'BUSINESS_BELONG_MANAGER',
            'DBA_OWNER'
        )
    )
);

CREATE TABLE IF NOT EXISTS dbops.import_batches (
    id BIGSERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    uploaded_by VARCHAR(64),
    total_rows INTEGER NOT NULL DEFAULT 0,
    success_rows INTEGER NOT NULL DEFAULT 0,
    fail_rows INTEGER NOT NULL DEFAULT 0,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- dbops schema: 业务与资产主线
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.business_system (
    id BIGSERIAL PRIMARY KEY,
    system_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(300) NOT NULL UNIQUE,
    system_group_id BIGINT NOT NULL REFERENCES dbops.system_group(id),
    business_unit VARCHAR(200),
    department VARCHAR(200),
    service_scope_raw TEXT,
    biz_level_id BIGINT REFERENCES dbops.biz_level(id),
    description TEXT,
    extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_business_system_group_id
    ON dbops.business_system(system_group_id);

CREATE TABLE IF NOT EXISTS dbops.cluster (
    id BIGSERIAL PRIMARY KEY,
    cluster_key VARCHAR(100) NOT NULL UNIQUE,
    business_system_id BIGINT NOT NULL UNIQUE REFERENCES dbops.business_system(id) ON DELETE CASCADE,
    cluster_type VARCHAR(50) NOT NULL,
    name VARCHAR(200),
    ha_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ha_remark TEXT,
    description TEXT,
    extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cluster_cluster_type
    ON dbops.cluster(cluster_type);

CREATE TABLE IF NOT EXISTS dbops.cluster_vip (
    id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES dbops.cluster(id) ON DELETE CASCADE,
    vip_address TEXT NOT NULL,
    vip_type VARCHAR(50),
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, vip_address)
);

CREATE TABLE IF NOT EXISTS dbops.server (
    id BIGSERIAL PRIMARY KEY,
    server_code VARCHAR(50) UNIQUE,
    hostname VARCHAR(200),
    ip_address INET NOT NULL UNIQUE,
    site_name VARCHAR(100),
    room_location TEXT,
    os_name VARCHAR(100),
    os_version VARCHAR(100),
    cpu_cores INTEGER,
    memory_gb NUMERIC(10,2),
    disk_gb NUMERIC(12,2),
    server_type VARCHAR(50),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_server_hostname
    ON dbops.server(hostname);

CREATE TABLE IF NOT EXISTS dbops.db_instance (
    id BIGSERIAL PRIMARY KEY,
    instance_code VARCHAR(50) NOT NULL UNIQUE,
    instance_name VARCHAR(200) NOT NULL,
    db_type_code VARCHAR(30) REFERENCES dbops.db_type_catalog(code),
    db_version VARCHAR(100),
    server_id BIGINT NOT NULL REFERENCES dbops.server(id),
    cluster_id BIGINT NOT NULL REFERENCES dbops.cluster(id) ON DELETE CASCADE,
    env_code VARCHAR(30) REFERENCES dbops.env_catalog(code),
    port INTEGER,
    service_name VARCHAR(200),
    node_role VARCHAR(20) NOT NULL,
    db_size_gb NUMERIC(12,2),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    extra_attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_db_instance_cluster_name UNIQUE(cluster_id, instance_name),
    CONSTRAINT ck_db_instance_node_role CHECK (node_role IN ('Master', 'Slave', 'Single')),
    CONSTRAINT ck_db_instance_port CHECK (port IS NULL OR (port > 0 AND port < 65536))
);

CREATE INDEX IF NOT EXISTS idx_db_instance_server_id
    ON dbops.db_instance(server_id);

CREATE INDEX IF NOT EXISTS idx_db_instance_cluster_id
    ON dbops.db_instance(cluster_id);

CREATE INDEX IF NOT EXISTS idx_db_instance_db_type
    ON dbops.db_instance(db_type_code);

-- ============================================================
-- dbops schema: 联系人与绑定
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.contact (
    id BIGSERIAL PRIMARY KEY,
    employee_no VARCHAR(50),
    contact_code VARCHAR(50) UNIQUE,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(100),
    email VARCHAR(200),
    dept VARCHAR(200),
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contact_name_phone
    ON dbops.contact(name, phone);
CREATE INDEX IF NOT EXISTS idx_contact_employee_no
    ON dbops.contact(employee_no);

COMMENT ON TABLE dbops.contact IS '联系人主数据表';
COMMENT ON COLUMN dbops.contact.employee_no IS '工号/员工编号，允许为空，作为联系人业务标识';
COMMENT ON COLUMN dbops.contact.contact_code IS '联系人稳定技术编码，保留用于主数据引用';
COMMENT ON COLUMN dbops.contact.name IS '联系人姓名';
COMMENT ON COLUMN dbops.contact.phone IS '联系电话';

CREATE TABLE IF NOT EXISTS dbops.business_system_contact (
    id BIGSERIAL PRIMARY KEY,
    business_system_id BIGINT NOT NULL REFERENCES dbops.business_system(id) ON DELETE CASCADE,
    contact_id BIGINT NOT NULL REFERENCES dbops.contact(id),
    role_code VARCHAR(50) NOT NULL REFERENCES dbops.contact_role_catalog(role_code),
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_business_system_contact_role UNIQUE(business_system_id, role_code)
);

COMMENT ON TABLE dbops.business_system_contact IS '业务系统联系人关系表';
COMMENT ON COLUMN dbops.business_system_contact.role_code IS '联系人角色：当前导入阶段优先 BUSINESS_MANAGER/DBA_OWNER，其余角色后续补全';

CREATE INDEX IF NOT EXISTS idx_business_system_contact_contact
    ON dbops.business_system_contact(contact_id);

-- ============================================================
-- dbops schema: 标签与治理
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.tag (
    id BIGSERIAL PRIMARY KEY,
    tag_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    tag_type VARCHAR(30) NOT NULL,
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tag_name_type
    ON dbops.tag(name, tag_type);

CREATE TABLE IF NOT EXISTS dbops.resource_tag (
    id BIGSERIAL PRIMARY KEY,
    resource_type VARCHAR(30) NOT NULL,
    resource_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL REFERENCES dbops.tag(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_resource_tag UNIQUE(resource_type, resource_id, tag_id),
    CONSTRAINT ck_resource_tag_type CHECK (
        resource_type IN ('business_system', 'cluster', 'server', 'db_instance')
    )
);

-- ============================================================
-- dbops schema: 备份
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.backup_policy (
    id BIGSERIAL PRIMARY KEY,
    policy_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    backup_type VARCHAR(50) NOT NULL,
    schedule_cron VARCHAR(100),
    retention_days INTEGER,
    storage_type VARCHAR(50),
    storage_path TEXT,
    is_remote_backup BOOLEAN NOT NULL DEFAULT FALSE,
    remote_backup_location TEXT,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    remark TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dbops.instance_backup_policy (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES dbops.db_instance(id) ON DELETE CASCADE,
    policy_id BIGINT NOT NULL REFERENCES dbops.backup_policy(id) ON DELETE CASCADE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_instance_backup_policy UNIQUE(instance_id, policy_id)
);

-- ============================================================
-- dbops schema: 评分
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.biz_score_rule (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(50) NOT NULL UNIQUE,
    rule_name VARCHAR(200) NOT NULL,
    description TEXT,
    deduct_score NUMERIC(5,2) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dbops.biz_score_result (
    id BIGSERIAL PRIMARY KEY,
    score_batch VARCHAR(100) NOT NULL,
    system_id BIGINT NOT NULL REFERENCES dbops.business_system(id) ON DELETE CASCADE,
    base_score NUMERIC(5,2) NOT NULL DEFAULT 10,
    deduct_score NUMERIC(5,2) NOT NULL DEFAULT 0,
    final_score NUMERIC(5,2) NOT NULL,
    score_level VARCHAR(50),
    scored_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_biz_score_result_batch
    ON dbops.biz_score_result(score_batch, system_id);

CREATE TABLE IF NOT EXISTS dbops.biz_score_result_detail (
    id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL REFERENCES dbops.biz_score_result(id) ON DELETE CASCADE,
    rule_id BIGINT NOT NULL REFERENCES dbops.biz_score_rule(id),
    deduct_score NUMERIC(5,2) NOT NULL,
    reason TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- dbops schema: Excel staging
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.staging_excel_import (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT REFERENCES dbops.import_batches(id) ON DELETE SET NULL,
    source_file_name VARCHAR(255),
    row_no INTEGER,
    cluster_key VARCHAR(100),
    cluster_type VARCHAR(100),
    node_role VARCHAR(100),
    platform_category VARCHAR(50),
    system_name VARCHAR(300),
    service_scope TEXT,
    ip TEXT,
    instance_name VARCHAR(200),
    port INTEGER,
    machine_type VARCHAR(50),
    dns_name VARCHAR(200),
    vip TEXT,
    host_admin VARCHAR(100),
    host_admin_contact VARCHAR(100),
    os_admin VARCHAR(100),
    os_admin_contact VARCHAR(100),
    app_owner VARCHAR(100),
    app_owner_contact VARCHAR(100),
    business_manager VARCHAR(100),
    business_manager_contact VARCHAR(100),
    business_belong_manager VARCHAR(100),
    business_belong_manager_contact VARCHAR(100),
    dba_owner VARCHAR(100),
    dba_owner_contact VARCHAR(100),
    business_unit VARCHAR(200),
    department VARCHAR(200),
    os_name VARCHAR(100),
    os_version VARCHAR(100),
    db_type VARCHAR(100),
    db_version VARCHAR(200),
    patch_version VARCHAR(200),
    db_account VARCHAR(100),
    db_password_raw TEXT,
    os_oracle VARCHAR(100),
    os_oracle_password_raw TEXT,
    os_root VARCHAR(100),
    os_password_raw TEXT,
    hostname VARCHAR(200),
    cpu_cores INTEGER,
    memory_gb NUMERIC(10,2),
    disk_gb NUMERIC(12,2),
    db_size_gb NUMERIC(12,2),
    country VARCHAR(100),
    site_name VARCHAR(100),
    room_location TEXT,
    biz_level_name VARCHAR(50),
    backup_method VARCHAR(100),
    local_backup_policy TEXT,
    remote_backup_policy TEXT,
    remote_backup_location TEXT,
    monitor_tag VARCHAR(50),
    mdr_tag VARCHAR(50),
    db_audit_tag VARCHAR(50),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_staging_excel_import_batch
    ON dbops.staging_excel_import(import_batch_id, row_no);

CREATE OR REPLACE VIEW dbops.v_staging_invalid_platform_category AS
SELECT *
FROM dbops.staging_excel_import s
WHERE s.platform_category IS NOT NULL
  AND s.platform_category NOT IN ('ERP', '人資', '園區', '差旅', '採購', '相信', '關務', '電簽');

CREATE OR REPLACE VIEW dbops.v_staging_system_category_conflict AS
SELECT
    system_name,
    COUNT(DISTINCT platform_category) AS category_count,
    STRING_AGG(DISTINCT platform_category, ',' ORDER BY platform_category) AS categories
FROM dbops.staging_excel_import
WHERE system_name IS NOT NULL
GROUP BY system_name
HAVING COUNT(DISTINCT platform_category) > 1;

CREATE OR REPLACE VIEW dbops.v_staging_system_cluster_conflict AS
SELECT
    system_name,
    COUNT(DISTINCT cluster_key) AS cluster_count,
    STRING_AGG(DISTINCT cluster_key, ',' ORDER BY cluster_key) AS cluster_keys
FROM dbops.staging_excel_import
WHERE system_name IS NOT NULL
  AND cluster_key IS NOT NULL
GROUP BY system_name
HAVING COUNT(DISTINCT cluster_key) > 1;

CREATE OR REPLACE VIEW dbops.v_staging_cluster_system_conflict AS
SELECT
    cluster_key,
    COUNT(DISTINCT system_name) AS system_count,
    STRING_AGG(DISTINCT system_name, ',' ORDER BY system_name) AS system_names
FROM dbops.staging_excel_import
WHERE cluster_key IS NOT NULL
  AND system_name IS NOT NULL
GROUP BY cluster_key
HAVING COUNT(DISTINCT system_name) > 1;

CREATE OR REPLACE VIEW dbops.v_staging_duplicate_instance_name_in_cluster AS
SELECT
    cluster_key,
    instance_name,
    COUNT(*) AS row_count
FROM dbops.staging_excel_import
WHERE cluster_key IS NOT NULL
  AND instance_name IS NOT NULL
GROUP BY cluster_key, instance_name
HAVING COUNT(*) > 1;

-- ============================================================
-- 基础 seed 数据
-- ============================================================

INSERT INTO dbops.system_group (group_code, name, description)
VALUES
    ('GRP-ERP', 'ERP', 'ERP 類系統'),
    ('GRP-HR', '人資', '人資類系統'),
    ('GRP-PARK', '園區', '園區類系統'),
    ('GRP-TRAVEL', '差旅', '差旅類系統'),
    ('GRP-PURCHASE', '採購', '採購類系統'),
    ('GRP-XIANGXIN', '相信', '相信類系統'),
    ('GRP-CUSTOMS', '關務', '關務類系統'),
    ('GRP-ESIGN', '電簽', '電簽類系統')
ON CONFLICT (group_code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO dbops.biz_level (level_code, name, level_value, color, description)
VALUES
    ('BIZ-NORMAL', '一般', 1, '#22c55e', '一般业务'),
    ('BIZ-IMPORTANT', '重要', 2, '#f59e0b', '重要业务'),
    ('BIZ-KEY', '關鍵', 3, '#f97316', '关键业务'),
    ('BIZ-CRITICAL', '極重要', 4, '#ef4444', '极重要业务')
ON CONFLICT (level_code) DO UPDATE SET
    name = EXCLUDED.name,
    level_value = EXCLUDED.level_value,
    color = EXCLUDED.color,
    description = EXCLUDED.description;

INSERT INTO dbops.env_catalog (code, name, description, sort_order)
VALUES
    ('PROD', '生产', '生产环境', 10),
    ('UAT', 'UAT', '用户验收环境', 20),
    ('SIT', 'SIT', '系统集成测试环境', 30),
    ('TEST', '测试', '测试环境', 40),
    ('DEV', '开发', '开发环境', 50),
    ('DR', '灾备', '灾备环境', 60)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    sort_order = EXCLUDED.sort_order;

INSERT INTO dbops.db_type_catalog (code, name, description)
VALUES
    ('ORACLE', 'Oracle', 'Oracle Database'),
    ('MYSQL', 'MySQL', 'MySQL Database'),
    ('MARIADB', 'MariaDB', 'MariaDB Database'),
    ('POSTGRESQL', 'PostgreSQL', 'PostgreSQL Database'),
    ('SQLSERVER', 'SQL Server', 'Microsoft SQL Server'),
    ('MONGODB', 'MongoDB', 'MongoDB Database'),
    ('INFORMIXAP', 'InformixAP', 'IBM Informix Advanced')
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO dbops.contact_role_catalog (role_code, role_name, sort_order)
VALUES
    ('OS_ADMIN', 'OS管理員', 10),
    ('HOST_ADMIN', '主機管理員', 20),
    ('APP_OWNER', '業務負責人', 30),
    ('BUSINESS_MANAGER', '業務主管', 40),
    ('BUSINESS_BELONG_MANAGER', '業務歸屬主管', 50),
    ('DBA_OWNER', 'DBA負責人', 60)
ON CONFLICT (role_code) DO UPDATE SET
    role_name = EXCLUDED.role_name,
    sort_order = EXCLUDED.sort_order;

INSERT INTO dbops.tag (tag_code, name, tag_type, remark)
VALUES
    ('TAG-TYPE-SCOPE', 'scope', 'system', '业务范畴标签类型'),
    ('TAG-TYPE-MONITOR', 'monitor', 'system', '监控标签类型'),
    ('TAG-TYPE-MDR', 'mdr', 'system', 'MDR 标签类型'),
    ('TAG-TYPE-AUDIT', 'audit', 'system', '审计标签类型')
ON CONFLICT (tag_code) DO UPDATE SET
    name = EXCLUDED.name,
    tag_type = EXCLUDED.tag_type,
    remark = EXCLUDED.remark;

INSERT INTO dbops.biz_score_rule (rule_code, rule_name, description, deduct_score, is_enabled, sort_order)
VALUES
    ('NO_HA', '沒有備援', '集群未具备 HA/备援能力', 5, TRUE, 10),
    ('NO_REMOTE_BACKUP', '沒有異地備份', '未配置异地备份', 3, TRUE, 20),
    ('NO_MONITOR', '沒有監控', '未打监控标签', 2, TRUE, 30)
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name = EXCLUDED.rule_name,
    description = EXCLUDED.description,
    deduct_score = EXCLUDED.deduct_score,
    is_enabled = EXCLUDED.is_enabled,
    sort_order = EXCLUDED.sort_order;
