-- ============================================================
-- DBOps 第一阶段可上线标准版 SQL
-- 表数量：25 张
-- 说明：Excel 导入、资产展示、集群关系、备份、巡检、评分
-- 数据库：PostgreSQL
-- ============================================================

CREATE SCHEMA IF NOT EXISTS dbops;

-- 如未启用 gen_random_uuid，需要扩展 pgcrypto
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 0. 公共更新时间函数
-- ============================================================

CREATE OR REPLACE FUNCTION dbops.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 1. 平台用户：dbops.users
-- ============================================================

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

COMMENT ON TABLE dbops.users IS '平台登录用户表';
COMMENT ON COLUMN dbops.users.username IS '登录账号';
COMMENT ON COLUMN dbops.users.password_hash IS '密码哈希，不存明文密码';
COMMENT ON COLUMN dbops.users.role IS '平台角色：admin/operator/viewer';

CREATE INDEX IF NOT EXISTS ix_dbops_users_username ON dbops.users(username);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'ops' AND table_name = 'users'
    ) THEN
        EXECUTE $migrate$
            INSERT INTO dbops.users (
                id,
                username,
                email,
                password_hash,
                full_name,
                department,
                role,
                is_active,
                timezone,
                language,
                created_at,
                updated_at
            )
            SELECT
                id,
                username,
                email,
                password_hash,
                full_name,
                department,
                role,
                is_active,
                timezone,
                language,
                created_at,
                updated_at
            FROM ops.users
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash,
                full_name = EXCLUDED.full_name,
                department = EXCLUDED.department,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                timezone = EXCLUDED.timezone,
                language = EXCLUDED.language,
                updated_at = now()
        $migrate$;
    END IF;
END
$$;

INSERT INTO dbops.users (
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
    'zh-CN'
)
ON CONFLICT (username) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    department = EXCLUDED.department,
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active,
    timezone = EXCLUDED.timezone,
    language = EXCLUDED.language,
    updated_at = now();

DROP TRIGGER IF EXISTS trg_users_updated_at ON dbops.users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON dbops.users
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 2. 业务大类：system_group
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.system_group (
    id BIGSERIAL PRIMARY KEY,
    group_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE dbops.system_group IS '业务大类，固定8类：ERP/人資/園區/差旅/採購/相信/關務/電簽';
COMMENT ON COLUMN dbops.system_group.group_code IS '业务大类编码';
COMMENT ON COLUMN dbops.system_group.name IS '业务大类名称';

DROP TRIGGER IF EXISTS trg_system_group_updated_at ON dbops.system_group;
CREATE TRIGGER trg_system_group_updated_at
BEFORE UPDATE ON dbops.system_group
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

INSERT INTO dbops.system_group (group_code, name, description)
VALUES
('ERP', 'ERP', 'ERP類系統'),
('HR', '人資', '人資類系統'),
('PARK', '園區', '園區類系統'),
('TRAVEL', '差旅', '差旅類系統'),
('PURCHASE', '採購', '採購類系統'),
('XIANGXIN', '相信', '相信類系統'),
('CUSTOMS', '關務', '關務類系統'),
('ESIGN', '電簽', '電簽類系統')
ON CONFLICT (group_code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    updated_at = now();

-- ============================================================
-- 3. 业务系统：business_system
-- ============================================================

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

COMMENT ON TABLE dbops.business_system IS '业务系统表，对应Excel系统名称';
COMMENT ON COLUMN dbops.business_system.system_code IS '业务系统编码，建议系统生成或人工维护';
COMMENT ON COLUMN dbops.business_system.system_name IS '业务系统名称，当前按全局唯一处理';
COMMENT ON COLUMN dbops.business_system.system_group_id IS '业务大类，可先为空后补';
COMMENT ON COLUMN dbops.business_system.service_scope IS '服务范畴，可先存原始文本，后续可拆tag';
COMMENT ON COLUMN dbops.business_system.biz_level IS '业务重要等级：一般/重要/關鍵/極重要';
COMMENT ON COLUMN dbops.business_system.extra_attrs IS '业务系统扩展属性';

CREATE INDEX IF NOT EXISTS idx_business_system_group ON dbops.business_system(system_group_id);
CREATE INDEX IF NOT EXISTS idx_business_system_status ON dbops.business_system(status);

DROP TRIGGER IF EXISTS trg_business_system_updated_at ON dbops.business_system;
CREATE TRIGGER trg_business_system_updated_at
BEFORE UPDATE ON dbops.business_system
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 4. 联系人：contact
-- ============================================================

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

ALTER TABLE dbops.contact
    ADD COLUMN IF NOT EXISTS employee_no VARCHAR(50);

COMMENT ON TABLE dbops.contact IS '联系人主数据表';
COMMENT ON COLUMN dbops.contact.employee_no IS '工号';
COMMENT ON COLUMN dbops.contact.contact_code IS '联系人编码，建议由姓名+电话hash生成';
COMMENT ON COLUMN dbops.contact.contact_name IS '联系人姓名';
COMMENT ON COLUMN dbops.contact.phone IS '联系电话';

CREATE INDEX IF NOT EXISTS idx_contact_employee_no ON dbops.contact(employee_no);
CREATE INDEX IF NOT EXISTS idx_contact_name_phone ON dbops.contact(contact_name, phone);

DROP TRIGGER IF EXISTS trg_contact_updated_at ON dbops.contact;
CREATE TRIGGER trg_contact_updated_at
BEFORE UPDATE ON dbops.contact
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 5. 业务联系人关系：business_system_contact
-- ============================================================

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

COMMENT ON TABLE dbops.business_system_contact IS '业务系统联系人关系表';
COMMENT ON COLUMN dbops.business_system_contact.role_code IS '联系人角色：OS_ADMIN/HOST_ADMIN/APP_OWNER/BUSINESS_MANAGER/BUSINESS_BELONG_MANAGER/DBA_OWNER';

CREATE INDEX IF NOT EXISTS idx_bsc_system ON dbops.business_system_contact(business_system_id);
CREATE INDEX IF NOT EXISTS idx_bsc_contact ON dbops.business_system_contact(contact_id);

-- ============================================================
-- 5.1 通用事件历史：asset_event_history
-- ============================================================

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

COMMENT ON TABLE dbops.asset_event_history IS '资产通用事件历史表';
COMMENT ON COLUMN dbops.asset_event_history.asset_type IS '资产类型';
COMMENT ON COLUMN dbops.asset_event_history.asset_id IS '资产主键';
COMMENT ON COLUMN dbops.asset_event_history.event_type IS '事件类型';
COMMENT ON COLUMN dbops.asset_event_history.before_status IS '变更前状态';
COMMENT ON COLUMN dbops.asset_event_history.after_status IS '变更后状态';
COMMENT ON COLUMN dbops.asset_event_history.changed_fields IS '变更字段快照';
COMMENT ON COLUMN dbops.asset_event_history.reason IS '变更原因';
COMMENT ON COLUMN dbops.asset_event_history.operator IS '操作人';
COMMENT ON COLUMN dbops.asset_event_history.operated_at IS '操作时间';
COMMENT ON COLUMN dbops.asset_event_history.remark IS '备注';
COMMENT ON COLUMN dbops.asset_event_history.created_at IS '创建时间';

CREATE INDEX IF NOT EXISTS idx_asset_event_history_asset
    ON dbops.asset_event_history (asset_type, asset_id, operated_at DESC);
CREATE INDEX IF NOT EXISTS idx_asset_event_history_event
    ON dbops.asset_event_history (event_type, operated_at DESC);

-- ============================================================
-- 6. 站点：site
-- ============================================================

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

COMMENT ON TABLE dbops.site IS '站点/机房表，一条记录代表一个机房级site';
COMMENT ON COLUMN dbops.site.site_code IS '站点编码，建议按国家+厂区+部署类型+provider+机房hash生成';
COMMENT ON COLUMN dbops.site.country IS '国家/地区';
COMMENT ON COLUMN dbops.site.deploy_type IS '部署类型：地端/私有雲/公有雲';
COMMENT ON COLUMN dbops.site.provider IS '资源提供方：地端/GCP/龍華雲/虎躍雲/FII CLOUD等';
COMMENT ON COLUMN dbops.site.factory_area IS '厂区或地区，例如龍華/鄭州/越南/臺北';
COMMENT ON COLUMN dbops.site.room_location IS '机房位置；云资源建议统一 Cloud';

CREATE INDEX IF NOT EXISTS idx_site_country ON dbops.site(country);
CREATE INDEX IF NOT EXISTS idx_site_factory ON dbops.site(factory_area);
CREATE INDEX IF NOT EXISTS idx_site_deploy_provider ON dbops.site(deploy_type, provider);

DROP TRIGGER IF EXISTS trg_site_updated_at ON dbops.site;
CREATE TRIGGER trg_site_updated_at
BEFORE UPDATE ON dbops.site
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 7. OS版本：os_version
-- ============================================================

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

COMMENT ON TABLE dbops.os_version IS 'OS版本字典及生命周期';
COMMENT ON COLUMN dbops.os_version.lifecycle_status IS '生命周期状态：active/maintenance/eos/eol/unknown';
COMMENT ON COLUMN dbops.os_version.risk_level IS '生命周期风险等级：low/medium/high/critical/unknown';

CREATE INDEX IF NOT EXISTS idx_os_version_lifecycle ON dbops.os_version(lifecycle_status);

DROP TRIGGER IF EXISTS trg_os_version_updated_at ON dbops.os_version;
CREATE TRIGGER trg_os_version_updated_at
BEFORE UPDATE ON dbops.os_version
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 8. DB类型：db_type
-- ============================================================

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

ALTER TABLE dbops.db_type
    ADD COLUMN IF NOT EXISTS category VARCHAR(50) NOT NULL DEFAULT 'relational',
    ADD COLUMN IF NOT EXISTS license_type VARCHAR(20) NOT NULL DEFAULT 'commercial',
    ADD COLUMN IF NOT EXISTS vendor VARCHAR(100),
    ADD COLUMN IF NOT EXISTS remark TEXT,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_db_type_category'
          AND connamespace = 'dbops'::regnamespace
    ) THEN
        ALTER TABLE dbops.db_type
            ADD CONSTRAINT ck_db_type_category CHECK (
                category IN ('relational','nosql','cache','search','time_series','other')
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_db_type_license'
          AND connamespace = 'dbops'::regnamespace
    ) THEN
        ALTER TABLE dbops.db_type
            ADD CONSTRAINT ck_db_type_license CHECK (
                license_type IN ('open_source','commercial','hybrid')
            );
    END IF;
END
$$;

COMMENT ON TABLE dbops.db_type IS '数据库类型主数据字典，包含类型、分类、许可证和厂商信息';
COMMENT ON COLUMN dbops.db_type.type_code IS '数据库类型编码，统一使用大写，例如 ORACLE / POSTGRESQL / MYSQL';
COMMENT ON COLUMN dbops.db_type.name IS '展示名称，按行业常用写法，例如 Oracle / PostgreSQL / SQL Server';
COMMENT ON COLUMN dbops.db_type.category IS '数据库分类：relational/nosql/cache/search/time_series/other';
COMMENT ON COLUMN dbops.db_type.license_type IS '许可证类型：open_source/commercial/hybrid';
COMMENT ON COLUMN dbops.db_type.vendor IS '厂商';
COMMENT ON COLUMN dbops.db_type.is_active IS '是否启用';

DROP TRIGGER IF EXISTS trg_db_type_updated_at ON dbops.db_type;
CREATE TRIGGER trg_db_type_updated_at
BEFORE UPDATE ON dbops.db_type
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

INSERT INTO dbops.db_type (type_code, name, category, license_type, vendor, remark)
VALUES
('ORACLE', 'Oracle', 'relational', 'commercial', 'Oracle', 'Oracle Database'),
('SQLSERVER', 'SQL Server', 'relational', 'commercial', 'Microsoft', 'Microsoft SQL Server'),
('INFORMIX', 'Informix', 'relational', 'commercial', 'IBM', 'IBM Informix'),
('INFORMIXAP', 'InformixAP', 'relational', 'commercial', 'IBM', 'IBM Informix Advanced'),
('DB2', 'Db2', 'relational', 'commercial', 'IBM', 'IBM Db2'),
('POSTGRESQL', 'PostgreSQL', 'relational', 'open_source', 'PostgreSQL', 'Advanced open source RDBMS'),
('MARIADB', 'MariaDB', 'relational', 'open_source', 'MariaDB', 'MySQL fork, fully open source'),
('MYSQL', 'MySQL', 'relational', 'hybrid', 'Oracle', 'Community + Enterprise'),
('MONGODB', 'MongoDB', 'nosql', 'hybrid', 'MongoDB', 'Document database (SSPL)'),
('REDIS', 'Redis', 'cache', 'hybrid', 'Redis', 'In-memory data store'),
('ELASTICSEARCH', 'Elasticsearch', 'search', 'hybrid', 'Elastic', 'Search and analytics engine')
ON CONFLICT (type_code) DO UPDATE SET
    name = EXCLUDED.name,
    category = EXCLUDED.category,
    license_type = EXCLUDED.license_type,
    vendor = EXCLUDED.vendor,
    remark = EXCLUDED.remark,
    updated_at = now();

-- ============================================================
-- 9. DB版本：db_version
-- ============================================================

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

ALTER TABLE dbops.db_version
    ADD COLUMN IF NOT EXISTS architecture_bits VARCHAR(20);

COMMENT ON TABLE dbops.db_version IS '数据库版本字典及生命周期';
COMMENT ON COLUMN dbops.db_version.version_code IS '主版本，例如 19.3.0.0.0';
COMMENT ON COLUMN dbops.db_version.patch_version IS '补丁版本，例如 19.25.0.0.0';
COMMENT ON COLUMN dbops.db_version.architecture_bits IS '架构位数，例如 64bit';
COMMENT ON COLUMN dbops.db_version.lifecycle_status IS '生命周期状态：active/maintenance/eos/eol/unknown';

CREATE INDEX IF NOT EXISTS idx_db_version_type ON dbops.db_version(db_type_id);
CREATE INDEX IF NOT EXISTS idx_db_version_lifecycle ON dbops.db_version(lifecycle_status);

DROP TRIGGER IF EXISTS trg_db_version_updated_at ON dbops.db_version;
CREATE TRIGGER trg_db_version_updated_at
BEFORE UPDATE ON dbops.db_version
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 10. 服务器：server
-- ============================================================

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

COMMENT ON TABLE dbops.server IS '服务器/虚拟机资产表';
COMMENT ON COLUMN dbops.server.site_id IS '当前所在site';
COMMENT ON COLUMN dbops.server.os_version_id IS 'OS版本';
COMMENT ON COLUMN dbops.server.business_group IS '资源归属/事业群，例如中央/人資事業群/未知';
COMMENT ON COLUMN dbops.server.extra_attrs IS '服务器扩展属性，例如DNS/VIP原始值等';

CREATE INDEX IF NOT EXISTS idx_server_site ON dbops.server(site_id);
CREATE INDEX IF NOT EXISTS idx_server_os_version ON dbops.server(os_version_id);
CREATE INDEX IF NOT EXISTS idx_server_status ON dbops.server(status);

DROP TRIGGER IF EXISTS trg_server_updated_at ON dbops.server;
CREATE TRIGGER trg_server_updated_at
BEFORE UPDATE ON dbops.server
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 11. 集群：cluster
-- ============================================================

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

COMMENT ON TABLE dbops.cluster IS '数据库集群/主备组/单实例技术组';
COMMENT ON COLUMN dbops.cluster.cluster_code IS '系统生成的集群唯一编码，不依赖Excel cluster_key';
COMMENT ON COLUMN dbops.cluster.cluster_type IS '集群类型字典，详见 docs/cluster_type_dictionary.md';
COMMENT ON COLUMN dbops.cluster.ha_enabled IS '是否具备高可用能力';
COMMENT ON COLUMN dbops.cluster.extra_attrs IS '集群扩展属性';

CREATE INDEX IF NOT EXISTS idx_cluster_system ON dbops.cluster(business_system_id);
CREATE INDEX IF NOT EXISTS idx_cluster_db_type ON dbops.cluster(db_type_id);
CREATE INDEX IF NOT EXISTS idx_cluster_type ON dbops.cluster(cluster_type);

DROP TRIGGER IF EXISTS trg_cluster_updated_at ON dbops.cluster;
CREATE TRIGGER trg_cluster_updated_at
BEFORE UPDATE ON dbops.cluster
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 12. 集群VIP：cluster_vip
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.cluster_vip (
    id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES dbops.cluster(id) ON DELETE CASCADE,
    vip_address TEXT NOT NULL,
    vip_type VARCHAR(50),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_cluster_vip UNIQUE (cluster_id, vip_address)
);

COMMENT ON TABLE dbops.cluster_vip IS '集群VIP表，支持一个集群多个VIP';
COMMENT ON COLUMN dbops.cluster_vip.vip_address IS 'VIP地址，使用TEXT兼容IP、域名、SCAN等';
COMMENT ON COLUMN dbops.cluster_vip.vip_type IS 'VIP类型：service/scan/app/listener等';

-- ============================================================
-- 13. 数据库实例：db_instance
-- ============================================================

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

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_instance_cluster_name_port'
          AND connamespace = 'dbops'::regnamespace
    ) THEN
        ALTER TABLE dbops.db_instance
            DROP CONSTRAINT uq_instance_cluster_name_port;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_instance_cluster_server_name_port'
          AND connamespace = 'dbops'::regnamespace
    ) THEN
        ALTER TABLE dbops.db_instance
            ADD CONSTRAINT uq_instance_cluster_server_name_port
            UNIQUE (cluster_id, server_id, instance_name, port);
    END IF;
END
$$;

COMMENT ON TABLE dbops.db_instance IS '数据库实例表';
COMMENT ON COLUMN dbops.db_instance.instance_code IS '实例唯一编码，建议系统生成';
COMMENT ON COLUMN dbops.db_instance.node_role IS '跨数据库统一基础角色：primary/standby/member/single/unknown';
COMMENT ON COLUMN dbops.db_instance.extra_attrs IS '实例扩展属性，例如 engine_role、source_node_role、原始patch、监听名、DB唯一名等';

CREATE INDEX IF NOT EXISTS idx_instance_server ON dbops.db_instance(server_id);
CREATE INDEX IF NOT EXISTS idx_instance_cluster ON dbops.db_instance(cluster_id);
CREATE INDEX IF NOT EXISTS idx_instance_db_type ON dbops.db_instance(db_type_id);
CREATE INDEX IF NOT EXISTS idx_instance_status ON dbops.db_instance(status);

DROP TRIGGER IF EXISTS trg_db_instance_updated_at ON dbops.db_instance;
CREATE TRIGGER trg_db_instance_updated_at
BEFORE UPDATE ON dbops.db_instance
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 14. 拓扑关系：topology_relation
-- ============================================================

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

COMMENT ON TABLE dbops.topology_relation IS '实例拓扑关系表，统一表达主备、复制、成员关系';
COMMENT ON COLUMN dbops.topology_relation.relation_type IS '关系类型：primary_standby/leader_follower/member/replica/shard_member';
COMMENT ON COLUMN dbops.topology_relation.sync_mode IS '同步模式：sync/async/semisync/unknown';
COMMENT ON COLUMN dbops.topology_relation.lag_seconds IS '复制延迟秒数';

CREATE INDEX IF NOT EXISTS idx_topology_cluster ON dbops.topology_relation(cluster_id);
CREATE INDEX IF NOT EXISTS idx_topology_source ON dbops.topology_relation(source_instance_id);
CREATE INDEX IF NOT EXISTS idx_topology_target ON dbops.topology_relation(target_instance_id);

DROP TRIGGER IF EXISTS trg_topology_updated_at ON dbops.topology_relation;
CREATE TRIGGER trg_topology_updated_at
BEFORE UPDATE ON dbops.topology_relation
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 15. 标签：tag
-- ============================================================

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

COMMENT ON TABLE dbops.tag IS '标签字典表';
COMMENT ON COLUMN dbops.tag.tag_type IS '标签类型：scope/monitor/mdr/audit/custom';
COMMENT ON COLUMN dbops.tag.tag_name IS '标签名称，例如全集團/monitor_enabled/mdr_enabled';

CREATE INDEX IF NOT EXISTS idx_tag_type ON dbops.tag(tag_type);

DROP TRIGGER IF EXISTS trg_tag_updated_at ON dbops.tag;
CREATE TRIGGER trg_tag_updated_at
BEFORE UPDATE ON dbops.tag
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 16. 资源标签关系：resource_tag
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.resource_tag (
    id BIGSERIAL PRIMARY KEY,
    resource_type VARCHAR(50) NOT NULL,
    resource_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL REFERENCES dbops.tag(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_resource_tag UNIQUE (resource_type, resource_id, tag_id),
    CONSTRAINT chk_resource_tag_type CHECK (resource_type IN ('business_system','cluster','server','db_instance'))
);

COMMENT ON TABLE dbops.resource_tag IS '资源标签关系表';
COMMENT ON COLUMN dbops.resource_tag.resource_type IS '资源类型：business_system/cluster/server/db_instance';
COMMENT ON COLUMN dbops.resource_tag.resource_id IS '资源ID，不建外键，由resource_type决定引用表';

CREATE INDEX IF NOT EXISTS idx_resource_tag_resource ON dbops.resource_tag(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_resource_tag_tag ON dbops.resource_tag(tag_id);

-- ============================================================
-- 17. 备份策略：backup_policy
-- ============================================================

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

COMMENT ON TABLE dbops.backup_policy IS '备份策略表';
COMMENT ON COLUMN dbops.backup_policy.backup_type IS '备份类型：RMAN/full/incremental/logical等';
COMMENT ON COLUMN dbops.backup_policy.is_remote_backup IS '是否异地备份';
COMMENT ON COLUMN dbops.backup_policy.remote_backup_location IS '异地备份位置';

DROP TRIGGER IF EXISTS trg_backup_policy_updated_at ON dbops.backup_policy;
CREATE TRIGGER trg_backup_policy_updated_at
BEFORE UPDATE ON dbops.backup_policy
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 18. 实例备份策略关系：instance_backup_policy
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.instance_backup_policy (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES dbops.db_instance(id) ON DELETE CASCADE,
    policy_id BIGINT NOT NULL REFERENCES dbops.backup_policy(id),
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_instance_backup_policy UNIQUE (instance_id, policy_id)
);

COMMENT ON TABLE dbops.instance_backup_policy IS '数据库实例与备份策略关系表';

CREATE INDEX IF NOT EXISTS idx_ibp_instance ON dbops.instance_backup_policy(instance_id);
CREATE INDEX IF NOT EXISTS idx_ibp_policy ON dbops.instance_backup_policy(policy_id);

-- ============================================================
-- 19. 巡检项：inspection_item
-- ============================================================

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

COMMENT ON TABLE dbops.inspection_item IS '巡检项定义表';
COMMENT ON COLUMN dbops.inspection_item.category IS '巡检分类：backup/ha/config/lifecycle/connectivity';
COMMENT ON COLUMN dbops.inspection_item.severity IS '默认严重级别';

DROP TRIGGER IF EXISTS trg_inspection_item_updated_at ON dbops.inspection_item;
CREATE TRIGGER trg_inspection_item_updated_at
BEFORE UPDATE ON dbops.inspection_item
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 20. 巡检任务：inspection_task
-- ============================================================

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

COMMENT ON TABLE dbops.inspection_task IS '巡检任务表';
COMMENT ON COLUMN dbops.inspection_task.scope_type IS '巡检范围类型';
COMMENT ON COLUMN dbops.inspection_task.scope_id IS '巡检范围ID，根据scope_type解释';

CREATE INDEX IF NOT EXISTS idx_inspection_task_status ON dbops.inspection_task(status);

DROP TRIGGER IF EXISTS trg_inspection_task_updated_at ON dbops.inspection_task;
CREATE TRIGGER trg_inspection_task_updated_at
BEFORE UPDATE ON dbops.inspection_task
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

-- ============================================================
-- 21. 巡检结果：inspection_result
-- ============================================================

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

COMMENT ON TABLE dbops.inspection_result IS '巡检结果表';
COMMENT ON COLUMN dbops.inspection_result.extra_attrs IS '巡检结果扩展信息，例如原始SQL、阈值、原始返回值';

CREATE INDEX IF NOT EXISTS idx_ir_task ON dbops.inspection_result(task_id);
CREATE INDEX IF NOT EXISTS idx_ir_target ON dbops.inspection_result(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_ir_status ON dbops.inspection_result(result_status);

-- ============================================================
-- 22. 评分规则：biz_score_rule
-- ============================================================

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

COMMENT ON TABLE dbops.biz_score_rule IS '业务架构评分规则表';
COMMENT ON COLUMN dbops.biz_score_rule.deduct_score IS '扣分值';

DROP TRIGGER IF EXISTS trg_biz_score_rule_updated_at ON dbops.biz_score_rule;
CREATE TRIGGER trg_biz_score_rule_updated_at
BEFORE UPDATE ON dbops.biz_score_rule
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();

INSERT INTO dbops.biz_score_rule
(rule_code, rule_name, description, deduct_score, is_enabled, sort_order)
VALUES
('NO_HA', '没有备援', '业务系统没有主备、集群或高可用能力', 5, true, 10),
('NO_REMOTE_BACKUP', '没有异地备份', '业务系统没有异地备份策略', 3, true, 20),
('DB_EOL', '数据库版本过期', '业务系统存在EOL数据库版本', 2, true, 30),
('OS_EOL', 'OS版本过期', '业务系统存在EOL操作系统版本', 2, true, 40),
('INSPECTION_FAILED', '巡检失败', '业务系统存在失败巡检项', 2, true, 50)
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name = EXCLUDED.rule_name,
    description = EXCLUDED.description,
    deduct_score = EXCLUDED.deduct_score,
    is_enabled = EXCLUDED.is_enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = now();

-- ============================================================
-- 23. 评分结果：biz_score_result
-- ============================================================

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

COMMENT ON TABLE dbops.biz_score_result IS '业务架构评分结果表';
COMMENT ON COLUMN dbops.biz_score_result.score_batch IS '评分批次';

CREATE INDEX IF NOT EXISTS idx_score_result_system_time ON dbops.biz_score_result(business_system_id, scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_score_result_batch ON dbops.biz_score_result(score_batch);

-- ============================================================
-- 24. 评分明细：biz_score_result_detail
-- ============================================================

CREATE TABLE IF NOT EXISTS dbops.biz_score_result_detail (
    id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL REFERENCES dbops.biz_score_result(id) ON DELETE CASCADE,
    rule_id BIGINT NOT NULL REFERENCES dbops.biz_score_rule(id),
    deduct_score NUMERIC(5,2) NOT NULL,
    reason TEXT,
    evidence JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE dbops.biz_score_result_detail IS '业务架构评分扣分明细表';
COMMENT ON COLUMN dbops.biz_score_result_detail.evidence IS '扣分证据JSON，例如实例、版本、备份策略等';

CREATE INDEX IF NOT EXISTS idx_score_detail_result ON dbops.biz_score_result_detail(result_id);
CREATE INDEX IF NOT EXISTS idx_score_detail_rule ON dbops.biz_score_result_detail(rule_id);

-- ============================================================
-- 25. Excel暂存表：staging_excel_import
-- ============================================================

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

ALTER TABLE dbops.staging_excel_import
    ADD COLUMN IF NOT EXISTS source_cluster_no TEXT,
    ADD COLUMN IF NOT EXISTS normalized_node_role TEXT,
    ADD COLUMN IF NOT EXISTS normalized_engine_role TEXT,
    ADD COLUMN IF NOT EXISTS normalized_db_type TEXT;

COMMENT ON TABLE dbops.staging_excel_import IS 'Excel原始导入暂存表。正式表只接清洗后的结构化数据。';
COMMENT ON COLUMN dbops.staging_excel_import.raw_payload IS '原始Excel行JSON，便于追溯';
COMMENT ON COLUMN dbops.staging_excel_import.db_password_raw IS '原始DB密码，只允许暂存，不写正式表';

CREATE INDEX IF NOT EXISTS idx_staging_batch ON dbops.staging_excel_import(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_staging_system ON dbops.staging_excel_import(system_name);
CREATE INDEX IF NOT EXISTS idx_staging_ip ON dbops.staging_excel_import(ip);

-- ============================================================
-- 校验视图：Excel导入质量检查
-- ============================================================

CREATE OR REPLACE VIEW dbops.v_staging_invalid_platform_category AS
SELECT *
FROM dbops.staging_excel_import
WHERE platform_category IS NOT NULL
  AND platform_category NOT IN ('ERP','人資','園區','差旅','採購','相信','關務','電簽');

COMMENT ON VIEW dbops.v_staging_invalid_platform_category IS '平台分类不在固定8类中的记录';

CREATE OR REPLACE VIEW dbops.v_staging_system_category_conflict AS
SELECT
    system_name,
    COUNT(DISTINCT platform_category) AS category_count,
    STRING_AGG(DISTINCT platform_category, ',') AS categories
FROM dbops.staging_excel_import
WHERE system_name IS NOT NULL
GROUP BY system_name
HAVING COUNT(DISTINCT platform_category) > 1;

COMMENT ON VIEW dbops.v_staging_system_category_conflict IS '同一系统名称对应多个平台分类的冲突记录';

CREATE OR REPLACE VIEW dbops.v_staging_invalid_site AS
SELECT *
FROM dbops.staging_excel_import
WHERE deploy_type NOT IN ('地端','私有雲','公有雲')
   OR country IS NULL
   OR provider IS NULL
   OR factory_area IS NULL
   OR room_location IS NULL;

COMMENT ON VIEW dbops.v_staging_invalid_site IS 'site字段不完整或部署类型非法的记录';

-- ============================================================
-- 常用分析视图
-- ============================================================

CREATE OR REPLACE VIEW dbops.v_instance_full AS
SELECT
    bs.system_name,
    sg.name AS system_group,
    c.cluster_code,
    c.cluster_name,
    c.cluster_type,
    c.ha_enabled,
    di.instance_code,
    di.instance_name,
    di.node_role,
    dt.name AS db_type,
    dv.version_name AS db_version,
    dv.patch_version AS db_patch,
    s.hostname,
    s.ip_address,
    site.country,
    site.deploy_type,
    site.provider,
    site.factory_area,
    site.room_location
FROM dbops.db_instance di
JOIN dbops.cluster c ON c.id = di.cluster_id
JOIN dbops.business_system bs ON bs.id = c.business_system_id
LEFT JOIN dbops.system_group sg ON sg.id = bs.system_group_id
JOIN dbops.server s ON s.id = di.server_id
LEFT JOIN dbops.site site ON site.id = s.site_id
JOIN dbops.db_type dt ON dt.id = di.db_type_id
LEFT JOIN dbops.db_version dv ON dv.id = di.db_version_id;

COMMENT ON VIEW dbops.v_instance_full IS '实例全量展示视图，用于资产列表和查询';

-- ============================================================
-- 查询示例
-- ============================================================

-- 1. 某个业务用了哪些数据库
-- SELECT * FROM dbops.v_instance_full WHERE system_name = 'xxx';

-- 2. 按国家/厂区/部署类型/provider统计实例
-- SELECT country, deploy_type, provider, factory_area, COUNT(*) AS instance_count
-- FROM dbops.v_instance_full
-- GROUP BY country, deploy_type, provider, factory_area
-- ORDER BY instance_count DESC;

-- 3. 哪些系统是单实例
-- SELECT bs.system_name, c.cluster_name
-- FROM dbops.cluster c
-- JOIN dbops.business_system bs ON bs.id = c.business_system_id
-- WHERE c.cluster_type = 'SINGLE';

-- 4. 哪些业务没有备份策略
-- SELECT DISTINCT vf.system_name
-- FROM dbops.v_instance_full vf
-- LEFT JOIN dbops.db_instance di ON di.instance_code = vf.instance_code
-- LEFT JOIN dbops.instance_backup_policy ibp ON ibp.instance_id = di.id
-- WHERE ibp.id IS NULL;
