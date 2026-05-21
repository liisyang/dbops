
-- ============================================================
-- DBOps 数据底座完整建表脚本
-- PostgreSQL
-- 版本：site/site_category/site_category_mapping 替代原 idc
-- 表数量：42 张
-- ============================================================

CREATE SCHEMA IF NOT EXISTS dbops;
SET search_path TO dbops;

-- ============================================================
-- 0. 公共函数
-- ============================================================

CREATE OR REPLACE FUNCTION dbops.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION dbops.set_updated_at() IS '通用更新时间触发器函数';

-- ============================================================
-- 1. 基础维表 / 站点分类层
-- ============================================================

CREATE TABLE site (
    id BIGSERIAL PRIMARY KEY,
    site_code VARCHAR(50) NOT NULL UNIQUE,
    site_name VARCHAR(100) NOT NULL,
    site_address TEXT,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE site IS '厂区/站点表，替代原 idc。存实际站点，如龍華、龍華雲、美國GCP、印度雲';
COMMENT ON COLUMN site.site_code IS '站点编码，例如 SITE-LH、SITE-GCP-US';
COMMENT ON COLUMN site.site_name IS '站点名称，例如 龍華、昆山、龍華雲、美國GCP';
COMMENT ON COLUMN site.site_address IS '主要机房地址或默认地址；当前阶段不拆机房明细，先存这里';
COMMENT ON COLUMN site.remark IS '备注，可保存原始机房描述差异';

CREATE UNIQUE INDEX idx_site_name_unique ON site(site_name);
CREATE TRIGGER trg_site_updated_at BEFORE UPDATE ON site FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE site_category (
    id BIGSERIAL PRIMARY KEY,
    category_type VARCHAR(50) NOT NULL,
    category_code VARCHAR(50) NOT NULL UNIQUE,
    category_name VARCHAR(100) NOT NULL,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE site_category IS '站点分类表。支持云地分类、国家地区、云平台等统计口径';
COMMENT ON COLUMN site_category.category_type IS '分类类型：cloud_area / country_region / cloud_provider / factory_area';
COMMENT ON COLUMN site_category.category_code IS '分类编码，例如 CA-GCP、REGION-CN、CLOUD-GCP';
COMMENT ON COLUMN site_category.category_name IS '分类名称，例如 GCP、中國大陸、龍華地端';

CREATE INDEX idx_site_category_type ON site_category(category_type);


CREATE TABLE site_category_mapping (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL REFERENCES site_category(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(site_id, category_id)
);

COMMENT ON TABLE site_category_mapping IS '站点与分类关系表。一个站点可同时属于多个分类，如美國GCP属于GCP、美国、云平台GCP';
COMMENT ON COLUMN site_category_mapping.site_id IS '站点ID';
COMMENT ON COLUMN site_category_mapping.category_id IS '分类ID';

CREATE INDEX idx_site_category_mapping_site ON site_category_mapping(site_id);
CREATE INDEX idx_site_category_mapping_category ON site_category_mapping(category_id);


CREATE TABLE os_version (
    id BIGSERIAL PRIMARY KEY,
    os_code VARCHAR(50) NOT NULL UNIQUE,
    os_name VARCHAR(100) NOT NULL,
    os_version VARCHAR(100),
    kernel_version VARCHAR(100),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE os_version IS '操作系统版本字典表';
COMMENT ON COLUMN os_version.os_code IS 'OS编码，例如 OS-RHEL-8.8';
COMMENT ON COLUMN os_version.os_name IS 'OS名称';
COMMENT ON COLUMN os_version.os_version IS 'OS版本';
COMMENT ON COLUMN os_version.kernel_version IS '内核版本';

CREATE TRIGGER trg_os_version_updated_at BEFORE UPDATE ON os_version FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE db_type (
    id BIGSERIAL PRIMARY KEY,
    type_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE db_type IS '数据库类型字典表';
COMMENT ON COLUMN db_type.type_code IS '数据库类型编码：ORACLE / POSTGRESQL / MYSQL / SQLSERVER';
COMMENT ON COLUMN db_type.name IS '数据库类型名称';


CREATE TABLE db_version (
    id BIGSERIAL PRIMARY KEY,
    db_type_id BIGINT NOT NULL REFERENCES db_type(id),
    version_code VARCHAR(100) NOT NULL,
    version_name VARCHAR(100),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE(db_type_id, version_code)
);

COMMENT ON TABLE db_version IS '数据库版本字典表';
COMMENT ON COLUMN db_version.db_type_id IS '数据库类型ID';
COMMENT ON COLUMN db_version.version_code IS '版本编码，例如 11.2.0.4、19c、17.5、8.0';
COMMENT ON COLUMN db_version.version_name IS '版本显示名称';

CREATE INDEX idx_db_version_db_type ON db_version(db_type_id);
CREATE TRIGGER trg_db_version_updated_at BEFORE UPDATE ON db_version FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE env (
    id BIGSERIAL PRIMARY KEY,
    env_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE env IS '环境字典表';
COMMENT ON COLUMN env.env_code IS '环境编码，例如 PROD、TEST、DEV、DR';
COMMENT ON COLUMN env.name IS '环境名称';


-- ============================================================
-- 2. 资源资产层
-- ============================================================

CREATE TABLE platform (
    id BIGSERIAL PRIMARY KEY,
    platform_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE platform IS '平台/业务平台表，偏资源平台概念';
COMMENT ON COLUMN platform.platform_code IS '平台业务编码，例如 PLAT-ECARD';
COMMENT ON COLUMN platform.name IS '平台名称';
COMMENT ON COLUMN platform.extra_attrs IS '个性化扩展字段';

CREATE INDEX idx_platform_name ON platform(name);
CREATE TRIGGER trg_platform_updated_at BEFORE UPDATE ON platform FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE cluster (
    id BIGSERIAL PRIMARY KEY,
    cluster_code VARCHAR(50) NOT NULL UNIQUE,
    platform_id BIGINT REFERENCES platform(id),
    name VARCHAR(200) NOT NULL,
    cluster_type VARCHAR(50),
    description TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE cluster IS '集群/主备组/逻辑组表，属于技术分组';
COMMENT ON COLUMN cluster.cluster_code IS '集群编码';
COMMENT ON COLUMN cluster.platform_id IS '所属平台';
COMMENT ON COLUMN cluster.cluster_type IS '集群类型：single / primary_standby / rac / mgr / patroni';

CREATE INDEX idx_cluster_platform ON cluster(platform_id);
CREATE TRIGGER trg_cluster_updated_at BEFORE UPDATE ON cluster FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE server (
    id BIGSERIAL PRIMARY KEY,
    server_code VARCHAR(50) UNIQUE,
    hostname VARCHAR(200),
    ip_address INET NOT NULL UNIQUE,
    site_id BIGINT REFERENCES site(id),
    os_version_id BIGINT REFERENCES os_version(id),
    cpu_cores INTEGER,
    memory_gb NUMERIC(10,2),
    disk_gb NUMERIC(12,2),
    server_type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'active',
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE server IS '服务器资产表。server.site_id 关联 site，不再关联原 idc';
COMMENT ON COLUMN server.site_id IS '所属站点/厂区/云区域';
COMMENT ON COLUMN server.server_type IS '服务器类型：VM / physical / container / cloud_vm';
COMMENT ON COLUMN server.status IS '服务器资产状态：active / offline / retired';
COMMENT ON COLUMN server.extra_attrs IS '服务器扩展属性，例如 {"zabbix":"Y","mdr":"Y"}';

CREATE INDEX idx_server_site ON server(site_id);
CREATE INDEX idx_server_os ON server(os_version_id);
CREATE INDEX idx_server_hostname ON server(hostname);
CREATE TRIGGER trg_server_updated_at BEFORE UPDATE ON server FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE db_instance (
    id BIGSERIAL PRIMARY KEY,
    instance_code VARCHAR(50) NOT NULL UNIQUE,
    instance_name VARCHAR(200) NOT NULL,
    db_type_id BIGINT REFERENCES db_type(id),
    db_version_id BIGINT REFERENCES db_version(id),
    server_id BIGINT REFERENCES server(id),
    cluster_id BIGINT REFERENCES cluster(id),
    env_id BIGINT REFERENCES env(id),
    port INTEGER,
    service_name VARCHAR(200),
    configured_role VARCHAR(50),
    status VARCHAR(50) DEFAULT 'active',
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE db_instance IS '数据库实例表，DBOps 核心资产';
COMMENT ON COLUMN db_instance.configured_role IS '人工/Excel配置角色：primary / standby / single / unknown';
COMMENT ON COLUMN db_instance.status IS '资产状态：active / offline / retired';
COMMENT ON COLUMN db_instance.extra_attrs IS '个性化扩展属性';

CREATE INDEX idx_db_instance_server ON db_instance(server_id);
CREATE INDEX idx_db_instance_cluster ON db_instance(cluster_id);
CREATE INDEX idx_db_instance_db_type ON db_instance(db_type_id);
CREATE INDEX idx_db_instance_env ON db_instance(env_id);
CREATE TRIGGER trg_db_instance_updated_at BEFORE UPDATE ON db_instance FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


-- ============================================================
-- 3. 业务层
-- ============================================================

CREATE TABLE system_group (
    id BIGSERIAL PRIMARY KEY,
    group_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE system_group IS '业务分组表，例如 制造、财务、电商';
CREATE TRIGGER trg_system_group_updated_at BEFORE UPDATE ON system_group FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE business_system (
    id BIGSERIAL PRIMARY KEY,
    system_code VARCHAR(50) NOT NULL UNIQUE,
    system_group_id BIGINT REFERENCES system_group(id),
    name VARCHAR(200) NOT NULL,
    owner_dept VARCHAR(200),
    description TEXT,
    extra_attrs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE business_system IS '业务系统表，例如 TIPTOP、MES、一卡通';
CREATE INDEX idx_business_system_group ON business_system(system_group_id);
CREATE TRIGGER trg_business_system_updated_at BEFORE UPDATE ON business_system FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE instance_system (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES db_instance(id) ON DELETE CASCADE,
    system_id BIGINT NOT NULL REFERENCES business_system(id) ON DELETE CASCADE,
    usage_role VARCHAR(100),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(instance_id, system_id)
);

COMMENT ON TABLE instance_system IS '实例与业务系统关系表，支持一个实例服务多个业务';
COMMENT ON COLUMN instance_system.usage_role IS '实例在业务中的用途：主库 / 备库 / 报表库 / 共享库';


-- ============================================================
-- 4. 联系人与账号层
-- ============================================================

CREATE TABLE contact (
    id BIGSERIAL PRIMARY KEY,
    contact_code VARCHAR(50) UNIQUE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    phone VARCHAR(50),
    dept VARCHAR(200),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE contact IS '联系人表';
CREATE INDEX idx_contact_name ON contact(name);
CREATE TRIGGER trg_contact_updated_at BEFORE UPDATE ON contact FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE instance_contact (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES db_instance(id) ON DELETE CASCADE,
    contact_id BIGINT NOT NULL REFERENCES contact(id) ON DELETE CASCADE,
    contact_role VARCHAR(50),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(instance_id, contact_id, contact_role)
);

COMMENT ON TABLE instance_contact IS '实例联系人关系表。角色如 DBA、应用负责人、值班人';


CREATE TABLE account (
    id BIGSERIAL PRIMARY KEY,
    account_code VARCHAR(50) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL,
    account_type VARCHAR(50),
    description TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE account IS '数据库账号元数据表，不存密码';
COMMENT ON COLUMN account.account_type IS '账号类型：DBA / APP / READONLY / MONITOR';
CREATE INDEX idx_account_username ON account(username);
CREATE TRIGGER trg_account_updated_at BEFORE UPDATE ON account FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE instance_account (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES db_instance(id) ON DELETE CASCADE,
    account_id BIGINT NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    privilege_level VARCHAR(50),
    is_enabled BOOLEAN DEFAULT true,
    expire_at TIMESTAMP,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE(instance_id, account_id)
);

COMMENT ON TABLE instance_account IS '实例账号关系表';
COMMENT ON COLUMN instance_account.privilege_level IS '权限级别：admin / read / write / monitor';
CREATE TRIGGER trg_instance_account_updated_at BEFORE UPDATE ON instance_account FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


-- ============================================================
-- 5. 状态与拓扑层
-- ============================================================

CREATE TABLE instance_status (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL UNIQUE REFERENCES db_instance(id) ON DELETE CASCADE,
    actual_role VARCHAR(50),
    db_status VARCHAR(50),
    replication_status VARCHAR(50),
    replication_lag_seconds INTEGER,
    last_check_time TIMESTAMP,
    check_message TEXT,
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE instance_status IS '实例当前状态表，每个实例一条，由自动采集更新';
COMMENT ON COLUMN instance_status.actual_role IS 'SQL采集到的实际角色：primary / standby / single / unknown';
COMMENT ON COLUMN instance_status.db_status IS '数据库状态：up / down / unknown';
COMMENT ON COLUMN instance_status.replication_status IS '复制状态：normal / lagging / broken / unknown';


CREATE TABLE instance_status_history (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES db_instance(id) ON DELETE CASCADE,
    actual_role VARCHAR(50),
    db_status VARCHAR(50),
    replication_status VARCHAR(50),
    replication_lag_seconds INTEGER,
    check_message TEXT,
    checked_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE instance_status_history IS '实例状态历史表，建议按月分区';
CREATE INDEX idx_status_history_instance_time ON instance_status_history(instance_id, checked_at DESC);


CREATE TABLE replication_topology (
    id BIGSERIAL PRIMARY KEY,
    primary_instance_id BIGINT NOT NULL REFERENCES db_instance(id),
    standby_instance_id BIGINT NOT NULL REFERENCES db_instance(id),
    replication_type VARCHAR(50),
    sync_mode VARCHAR(50),
    status VARCHAR(50),
    lag_seconds INTEGER,
    last_check_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE(primary_instance_id, standby_instance_id)
);

COMMENT ON TABLE replication_topology IS '主备/复制拓扑关系表，由自动识别或人工维护';
CREATE TRIGGER trg_replication_topology_updated_at BEFORE UPDATE ON replication_topology FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE topology_relation (
    id BIGSERIAL PRIMARY KEY,
    src_instance_id BIGINT NOT NULL REFERENCES db_instance(id),
    dst_instance_id BIGINT NOT NULL REFERENCES db_instance(id),
    relation_type VARCHAR(50),
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE(src_instance_id, dst_instance_id, relation_type)
);

COMMENT ON TABLE topology_relation IS '通用依赖拓扑关系：replication / etl / sync / api / report';
CREATE TRIGGER trg_topology_relation_updated_at BEFORE UPDATE ON topology_relation FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


-- ============================================================
-- 6. 运维治理层
-- ============================================================

CREATE TABLE maintenance_record (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT REFERENCES db_instance(id),
    maintenance_type VARCHAR(100),
    title VARCHAR(200),
    content TEXT,
    operator VARCHAR(100),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE maintenance_record IS '维护记录表，人工录入或自动任务生成';


CREATE TABLE change_record (
    id BIGSERIAL PRIMARY KEY,
    resource_type VARCHAR(50),
    resource_id BIGINT,
    change_type VARCHAR(100),
    before_data JSONB,
    after_data JSONB,
    operator VARCHAR(100),
    changed_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE change_record IS '变更记录表，记录资源变更前后JSON';


CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_name VARCHAR(100),
    action VARCHAR(100),
    resource_type VARCHAR(50),
    resource_id BIGINT,
    request_data JSONB,
    ip_address INET,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE audit_log IS '操作审计日志表';


CREATE TABLE tag (
    id BIGSERIAL PRIMARY KEY,
    tag_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    color VARCHAR(50),
    remark TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE tag IS '标签定义表，如核心系统、高风险、无备份';


CREATE TABLE resource_tag (
    id BIGSERIAL PRIMARY KEY,
    resource_type VARCHAR(50) NOT NULL,
    resource_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL REFERENCES tag(id),
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(resource_type, resource_id, tag_id)
);

COMMENT ON TABLE resource_tag IS '资源标签关系表。resource_type 支持 platform/cluster/server/instance/site';


-- ============================================================
-- 7. 备份模块
-- ============================================================

CREATE TABLE backup_policy (
    id BIGSERIAL PRIMARY KEY,
    policy_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    backup_type VARCHAR(50) NOT NULL,
    schedule_cron VARCHAR(100),
    retention_days INTEGER,
    storage_type VARCHAR(50),
    storage_path TEXT,
    is_enabled BOOLEAN DEFAULT true,
    remark TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE backup_policy IS '备份策略表，人工维护';
COMMENT ON COLUMN backup_policy.backup_type IS '备份类型：full / incr / archivelog / logical';
CREATE TRIGGER trg_backup_policy_updated_at BEFORE UPDATE ON backup_policy FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE instance_backup_policy (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES db_instance(id) ON DELETE CASCADE,
    policy_id BIGINT NOT NULL REFERENCES backup_policy(id),
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(instance_id, policy_id)
);

COMMENT ON TABLE instance_backup_policy IS '实例与备份策略绑定表，人工维护';


CREATE TABLE backup_job (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL REFERENCES db_instance(id),
    policy_id BIGINT REFERENCES backup_policy(id),
    job_type VARCHAR(50),
    status VARCHAR(50),
    backup_size_gb NUMERIC(12,2),
    backup_path TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE backup_job IS '备份任务执行记录表，由备份系统/脚本动态写入';
CREATE INDEX idx_backup_job_instance_time ON backup_job(instance_id, started_at DESC);


-- ============================================================
-- 8. 巡检模块
-- ============================================================

CREATE TABLE inspection_template (
    id BIGSERIAL PRIMARY KEY,
    template_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    db_type_id BIGINT REFERENCES db_type(id),
    description TEXT,
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE inspection_template IS '巡检模板表，人工维护';
CREATE TRIGGER trg_inspection_template_updated_at BEFORE UPDATE ON inspection_template FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE inspection_item (
    id BIGSERIAL PRIMARY KEY,
    template_id BIGINT NOT NULL REFERENCES inspection_template(id) ON DELETE CASCADE,
    item_code VARCHAR(100) NOT NULL,
    item_name VARCHAR(200) NOT NULL,
    check_type VARCHAR(50),
    check_sql TEXT,
    threshold_rule JSONB,
    severity VARCHAR(50),
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE(template_id, item_code)
);

COMMENT ON TABLE inspection_item IS '巡检项表，人工维护';
COMMENT ON COLUMN inspection_item.check_type IS '检查类型：sql / ssh / api';
COMMENT ON COLUMN inspection_item.threshold_rule IS '阈值规则JSON';
CREATE TRIGGER trg_inspection_item_updated_at BEFORE UPDATE ON inspection_item FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE inspection_task (
    id BIGSERIAL PRIMARY KEY,
    task_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    template_id BIGINT REFERENCES inspection_template(id),
    schedule_cron VARCHAR(100),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE inspection_task IS '巡检任务表，人工维护调度策略';
CREATE TRIGGER trg_inspection_task_updated_at BEFORE UPDATE ON inspection_task FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE inspection_task_instance (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES inspection_task(id) ON DELETE CASCADE,
    instance_id BIGINT NOT NULL REFERENCES db_instance(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(task_id, instance_id)
);

COMMENT ON TABLE inspection_task_instance IS '巡检任务实例绑定表，人工维护';


CREATE TABLE inspection_result (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT REFERENCES inspection_task(id),
    instance_id BIGINT REFERENCES db_instance(id),
    item_id BIGINT REFERENCES inspection_item(id),
    status VARCHAR(50),
    result_value TEXT,
    result_detail JSONB,
    checked_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE inspection_result IS '巡检结果表，由巡检任务动态写入';
CREATE INDEX idx_inspection_result_instance_time ON inspection_result(instance_id, checked_at DESC);


-- ============================================================
-- 9. 告警模块
-- ============================================================

CREATE TABLE alert_rule (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    resource_type VARCHAR(50),
    metric_code VARCHAR(100),
    condition_operator VARCHAR(20),
    threshold_value VARCHAR(100),
    severity VARCHAR(50),
    duration_seconds INTEGER DEFAULT 0,
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE alert_rule IS '告警规则表，人工维护';
CREATE TRIGGER trg_alert_rule_updated_at BEFORE UPDATE ON alert_rule FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE alert_event (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES alert_rule(id),
    resource_type VARCHAR(50),
    resource_id BIGINT,
    severity VARCHAR(50),
    title VARCHAR(200),
    content TEXT,
    status VARCHAR(50) DEFAULT 'open',
    first_triggered_at TIMESTAMP DEFAULT now(),
    last_triggered_at TIMESTAMP DEFAULT now(),
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE alert_event IS '告警事件表，由状态采集/备份/巡检动态触发';
CREATE INDEX idx_alert_event_resource ON alert_event(resource_type, resource_id);
CREATE TRIGGER trg_alert_event_updated_at BEFORE UPDATE ON alert_event FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE alert_notify_channel (
    id BIGSERIAL PRIMARY KEY,
    channel_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100),
    channel_type VARCHAR(50),
    config JSONB,
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE alert_notify_channel IS '告警通知渠道表，人工维护';
CREATE TRIGGER trg_alert_notify_channel_updated_at BEFORE UPDATE ON alert_notify_channel FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE alert_rule_channel (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL REFERENCES alert_rule(id) ON DELETE CASCADE,
    channel_id BIGINT NOT NULL REFERENCES alert_notify_channel(id),
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(rule_id, channel_id)
);

COMMENT ON TABLE alert_rule_channel IS '告警规则与通知渠道关系表';


-- ============================================================
-- 10. 凭据中心
-- ============================================================

CREATE TABLE credential (
    id BIGSERIAL PRIMARY KEY,
    credential_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    credential_type VARCHAR(50),
    username VARCHAR(100),
    encrypted_secret TEXT NOT NULL,
    encryption_key_id VARCHAR(100),
    expire_at TIMESTAMP,
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE credential IS '凭据表，用于存储加密后的数据库密码、SSH Key、API Token';
COMMENT ON COLUMN credential.encrypted_secret IS '加密后的密文，禁止明文存储';
CREATE TRIGGER trg_credential_updated_at BEFORE UPDATE ON credential FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


CREATE TABLE credential_binding (
    id BIGSERIAL PRIMARY KEY,
    credential_id BIGINT NOT NULL REFERENCES credential(id) ON DELETE CASCADE,
    resource_type VARCHAR(50) NOT NULL,
    resource_id BIGINT NOT NULL,
    purpose VARCHAR(50),
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(credential_id, resource_type, resource_id, purpose)
);

COMMENT ON TABLE credential_binding IS '凭据与资源绑定表。resource_type 支持 instance/server';


CREATE TABLE credential_access_log (
    id BIGSERIAL PRIMARY KEY,
    credential_id BIGINT REFERENCES credential(id),
    user_name VARCHAR(100),
    action VARCHAR(100),
    resource_type VARCHAR(50),
    resource_id BIGINT,
    ip_address INET,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE credential_access_log IS '凭据访问审计日志，由系统动态写入';

-- ============================================================
-- 11. 一级示例数据：手动维护类
-- ============================================================

-- 站点：依据当前 Excel 的厂区/云区域清洗后的一级站点
INSERT INTO site (site_code, site_name, site_address, remark) VALUES
('SITE-LH', '龍華', '龍華 D13 / B3 / C8 等机房', 'Excel中有 D13、B3-2F、龍華區D13A-2F 等多种机房写法'),
('SITE-LH-FII', '龍華Fii', 'FII雲服務器', NULL),
('SITE-LH-CLOUD', '龍華雲', '龍華雲', NULL),
('SITE-HY', '虎躍', '虎躍廠區2樓層機房', NULL),
('SITE-HY-CLOUD', '虎躍雲', '臺北虎耀二樓機房', NULL),
('SITE-KS', '昆山', '昆山', NULL),
('SITE-KS-WSJ', '昆山(吳淞江)', 'A1', NULL),
('SITE-HZ', '惠州', '惠州廠區B區21棟3樓層 富鴻網機房', NULL),
('SITE-ZZ', '鄭州', '鄭州廠區E區12棟2樓層 富鴻網機房', NULL),
('SITE-CD', '成都', '成都廠區C區07棟2樓層富鴻網機房', NULL),
('SITE-FS', '佛山', '佛山普力華廠區普力華三期 一棟3樓服務器機房', NULL),
('SITE-NN', '南寧', '南寧機房', NULL),
('SITE-SH', '上海', '上海廠區', NULL),
('SITE-TPE', '臺北', '臺北虎耀二樓機房', NULL),
('SITE-VN', '越南', '越南廠區桂武區B11棟1樓B11資訊機房', NULL),
('SITE-IN-CLOUD', '印度雲', '印度雲/印度本地機房', NULL),
('SITE-GCP-US', '美國GCP', '美國Google Cloud', NULL),
('SITE-GCP-MX', '墨西哥GCP', '墨西哥Google Cloud', NULL),
('SITE-GCP-EU', '歐洲GCP', '歐洲Google Cloud', NULL),
('SITE-GCP-BR', '巴西GCP', '巴西Google Cloud', NULL),
('SITE-GCP-IN', '印度GCP', '印度Google Cloud', NULL),
('SITE-GCP-SG', 'GCP', '新加坡GCP / 新加坡GCVE', '原始厂区列为 GCP，机房出现新加坡GCP、新加坡GCVE'),
('SITE-GCVE', 'GCVE', 'GCVE', NULL),
('SITE-NA', '北美', '北美', NULL),
('SITE-GZ', '贛州', '贛州', NULL),
('SITE-HH', '鴻華', '鴻華機房', NULL)
ON CONFLICT (site_code) DO NOTHING;

-- 分类：云地、国家地区、云平台
INSERT INTO site_category (category_type, category_code, category_name) VALUES
('cloud_area', 'CA-LH-LOCAL', '龍華地端'),
('cloud_area', 'CA-TW-LOCAL', '台灣地端'),
('cloud_area', 'CA-CN-OTHER-LOCAL', '大陸其他地端'),
('cloud_area', 'CA-OVERSEA-LOCAL', '海外地端'),
('cloud_area', 'CA-HY-CLOUD', '虎躍雲'),
('cloud_area', 'CA-LH-CLOUD', '龍華雲'),
('cloud_area', 'CA-IN-CLOUD', '印度雲'),
('cloud_area', 'CA-GCP', 'GCP'),
('cloud_area', 'CA-GCVE', 'GCVE'),
('country_region', 'REGION-CN', '中國大陸'),
('country_region', 'REGION-TW', '台灣'),
('country_region', 'REGION-IN', '印度'),
('country_region', 'REGION-VN', '越南'),
('country_region', 'REGION-US', '美國'),
('country_region', 'REGION-MX', '墨西哥'),
('country_region', 'REGION-EU', '歐洲'),
('country_region', 'REGION-BR', '巴西'),
('country_region', 'REGION-SG', '新加坡'),
('country_region', 'REGION-NA', '北美'),
('cloud_provider', 'CLOUD-GCP', 'GCP'),
('cloud_provider', 'CLOUD-GCVE', 'GCVE'),
('cloud_provider', 'CLOUD-PRIVATE', '私有雲')
ON CONFLICT (category_code) DO NOTHING;

-- 映射：示例覆盖主要站点
INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-LH-LOCAL','REGION-CN')
WHERE s.site_code = 'SITE-LH'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-LH-CLOUD','REGION-CN','CLOUD-PRIVATE')
WHERE s.site_code = 'SITE-LH-CLOUD'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-HY-CLOUD','REGION-TW','CLOUD-PRIVATE')
WHERE s.site_code = 'SITE-HY-CLOUD'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-IN-CLOUD','REGION-IN','CLOUD-PRIVATE')
WHERE s.site_code = 'SITE-IN-CLOUD'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-GCP','REGION-US','CLOUD-GCP')
WHERE s.site_code = 'SITE-GCP-US'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-GCP','REGION-MX','CLOUD-GCP')
WHERE s.site_code = 'SITE-GCP-MX'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-GCP','REGION-EU','CLOUD-GCP')
WHERE s.site_code = 'SITE-GCP-EU'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-GCP','REGION-BR','CLOUD-GCP')
WHERE s.site_code = 'SITE-GCP-BR'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-GCP','REGION-IN','CLOUD-GCP')
WHERE s.site_code = 'SITE-GCP-IN'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-GCP','REGION-SG','CLOUD-GCP')
WHERE s.site_code = 'SITE-GCP-SG'
ON CONFLICT DO NOTHING;

INSERT INTO site_category_mapping (site_id, category_id)
SELECT s.id, c.id FROM site s JOIN site_category c ON c.category_code IN ('CA-GCVE','CLOUD-GCVE')
WHERE s.site_code = 'SITE-GCVE'
ON CONFLICT DO NOTHING;

-- 常用基础字典
INSERT INTO db_type (type_code, name) VALUES
('ORACLE', 'Oracle Database'),
('POSTGRESQL', 'PostgreSQL'),
('MYSQL', 'MySQL'),
('SQLSERVER', 'SQL Server')
ON CONFLICT (type_code) DO NOTHING;

INSERT INTO env (env_code, name) VALUES
('PROD', '生产'),
('TEST', '测试'),
('DEV', '开发'),
('DR', '灾备')
ON CONFLICT (env_code) DO NOTHING;

INSERT INTO os_version (os_code, os_name, os_version) VALUES
('OS-RHEL-8', 'Red Hat Enterprise Linux', '8'),
('OS-OL-7', 'Oracle Linux', '7'),
('OS-DEBIAN-13', 'Debian', '13')
ON CONFLICT (os_code) DO NOTHING;

-- 一级资源示例
INSERT INTO platform (platform_code, name, description) VALUES
('PLAT-ECARD', '一卡通平台', '员工卡消费、门禁、餐饮相关平台')
ON CONFLICT (platform_code) DO NOTHING;

INSERT INTO cluster (cluster_code, platform_id, name, cluster_type)
SELECT 'CLU-ECARD-ORA-DG-01', id, '一卡通Oracle主备组', 'primary_standby'
FROM platform WHERE platform_code='PLAT-ECARD'
ON CONFLICT (cluster_code) DO NOTHING;

INSERT INTO server (server_code, hostname, ip_address, site_id, os_version_id, cpu_cores, memory_gb, disk_gb, server_type)
SELECT 'SRV-ECARD-01', 'ecarddb01', '10.10.1.11',
       (SELECT id FROM site WHERE site_code='SITE-LH'),
       (SELECT id FROM os_version WHERE os_code='OS-OL-7'),
       32, 128, 2048, 'physical'
ON CONFLICT (ip_address) DO NOTHING;

INSERT INTO db_version (db_type_id, version_code, version_name)
SELECT id, '19c', 'Oracle 19c' FROM db_type WHERE type_code='ORACLE'
ON CONFLICT (db_type_id, version_code) DO NOTHING;

INSERT INTO db_instance (instance_code, instance_name, db_type_id, db_version_id, server_id, cluster_id, env_id, port, service_name, configured_role)
SELECT 'DB-ECARD-ORA-01', 'ECARDDB1',
       (SELECT id FROM db_type WHERE type_code='ORACLE'),
       (SELECT dv.id FROM db_version dv JOIN db_type dt ON dt.id=dv.db_type_id WHERE dt.type_code='ORACLE' AND dv.version_code='19c'),
       (SELECT id FROM server WHERE server_code='SRV-ECARD-01'),
       (SELECT id FROM cluster WHERE cluster_code='CLU-ECARD-ORA-DG-01'),
       (SELECT id FROM env WHERE env_code='PROD'),
       1521, 'ECARDDB', 'primary'
ON CONFLICT (instance_code) DO NOTHING;

-- ============================================================
-- 12. 动态采集写入示例
-- ============================================================

-- 实例状态采集：每次采集后 upsert 当前状态，并写历史
INSERT INTO instance_status (instance_id, actual_role, db_status, replication_status, replication_lag_seconds, last_check_time, check_message)
SELECT id, 'primary', 'up', 'normal', 0, now(), 'SQL采集正常'
FROM db_instance WHERE instance_code='DB-ECARD-ORA-01'
ON CONFLICT (instance_id) DO UPDATE SET
    actual_role = EXCLUDED.actual_role,
    db_status = EXCLUDED.db_status,
    replication_status = EXCLUDED.replication_status,
    replication_lag_seconds = EXCLUDED.replication_lag_seconds,
    last_check_time = EXCLUDED.last_check_time,
    check_message = EXCLUDED.check_message,
    updated_at = now();

INSERT INTO instance_status_history (instance_id, actual_role, db_status, replication_status, replication_lag_seconds, check_message)
SELECT id, 'primary', 'up', 'normal', 0, 'SQL采集正常'
FROM db_instance WHERE instance_code='DB-ECARD-ORA-01';

-- 备份任务动态写入
INSERT INTO backup_policy (policy_code, name, backup_type, schedule_cron, retention_days, storage_type, storage_path)
VALUES ('BKP-ORA-FULL-DAILY', 'Oracle每日全备', 'full', '0 2 * * *', 30, 'nfs', '/backup/oracle/full')
ON CONFLICT (policy_code) DO NOTHING;

INSERT INTO backup_job (instance_id, policy_id, job_type, status, backup_size_gb, backup_path, started_at, ended_at)
SELECT di.id, bp.id, 'full', 'success', 850.50, '/backup/oracle/full/ECARDDB1_20260425.bkp', now() - interval '2 hour', now() - interval '1 hour'
FROM db_instance di, backup_policy bp
WHERE di.instance_code='DB-ECARD-ORA-01' AND bp.policy_code='BKP-ORA-FULL-DAILY';

-- 告警事件动态写入
INSERT INTO alert_rule (rule_code, name, resource_type, metric_code, condition_operator, threshold_value, severity, duration_seconds)
VALUES ('ALERT-DB-DOWN', '数据库不可连接', 'instance', 'db_status', '=', 'down', 'critical', 60)
ON CONFLICT (rule_code) DO NOTHING;

INSERT INTO alert_event (rule_id, resource_type, resource_id, severity, title, content, status)
SELECT r.id, 'instance', di.id, 'critical', '数据库不可连接', 'ECARDDB1连接失败', 'open'
FROM alert_rule r, db_instance di
WHERE r.rule_code='ALERT-DB-DOWN' AND di.instance_code='DB-ECARD-ORA-01';

-- ============================================================
-- 13. 常用查询
-- ============================================================

-- 按站点统计实例数量
-- SELECT st.site_name, COUNT(di.id) AS instance_count
-- FROM site st
-- JOIN server s ON s.site_id = st.id
-- JOIN db_instance di ON di.server_id = s.id
-- GROUP BY st.site_name
-- ORDER BY instance_count DESC;

-- 按云地分类统计实例数量
-- SELECT c.category_name, COUNT(di.id) AS instance_count
-- FROM site_category c
-- JOIN site_category_mapping m ON m.category_id = c.id
-- JOIN site st ON st.id = m.site_id
-- JOIN server s ON s.site_id = st.id
-- JOIN db_instance di ON di.server_id = s.id
-- WHERE c.category_type = 'cloud_area'
-- GROUP BY c.category_name
-- ORDER BY instance_count DESC;

-- 按国家/地区统计实例数量
-- SELECT c.category_name, COUNT(di.id) AS instance_count
-- FROM site_category c
-- JOIN site_category_mapping m ON m.category_id = c.id
-- JOIN site st ON st.id = m.site_id
-- JOIN server s ON s.site_id = st.id
-- JOIN db_instance di ON di.server_id = s.id
-- WHERE c.category_type = 'country_region'
-- GROUP BY c.category_name
-- ORDER BY instance_count DESC;


-- ================= 增强部分 =================


-- ============================================================
-- DBOps 增强设计：OS/DB 生命周期管理 + BIZ 等级联动
-- 适用对象：dbops_schema_42_site_version.sql 之后执行
-- PostgreSQL
-- ============================================================

SET search_path TO dbops;

-- ============================================================
-- 1. OS 生命周期字段
-- ============================================================

ALTER TABLE os_version
ADD COLUMN IF NOT EXISTS release_date DATE,
ADD COLUMN IF NOT EXISTS eos_date DATE,
ADD COLUMN IF NOT EXISTS eol_date DATE,
ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(50) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS risk_level VARCHAR(50) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS is_supported BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS is_recommended BOOLEAN DEFAULT false;

COMMENT ON COLUMN os_version.release_date IS 'OS版本发布日期';
COMMENT ON COLUMN os_version.eos_date IS '停止标准支持日期，End of Support';
COMMENT ON COLUMN os_version.eol_date IS '完全停止支持日期，End of Life';
COMMENT ON COLUMN os_version.lifecycle_status IS '生命周期状态：active / maintenance / eos / eol / unknown';
COMMENT ON COLUMN os_version.risk_level IS '生命周期风险等级：low / medium / high / critical / unknown';
COMMENT ON COLUMN os_version.is_supported IS '当前是否仍受支持';
COMMENT ON COLUMN os_version.is_recommended IS '是否推荐新系统使用';

CREATE INDEX IF NOT EXISTS idx_os_version_lifecycle_status ON os_version(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_os_version_eol_date ON os_version(eol_date);


-- ============================================================
-- 2. DB 生命周期字段
-- ============================================================

ALTER TABLE db_version
ADD COLUMN IF NOT EXISTS release_date DATE,
ADD COLUMN IF NOT EXISTS eos_date DATE,
ADD COLUMN IF NOT EXISTS eol_date DATE,
ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(50) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS risk_level VARCHAR(50) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS is_supported BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS is_recommended BOOLEAN DEFAULT false;

COMMENT ON COLUMN db_version.release_date IS '数据库版本发布日期';
COMMENT ON COLUMN db_version.eos_date IS '停止标准支持日期，End of Support';
COMMENT ON COLUMN db_version.eol_date IS '完全停止支持日期，End of Life';
COMMENT ON COLUMN db_version.lifecycle_status IS '生命周期状态：active / maintenance / eos / eol / unknown';
COMMENT ON COLUMN db_version.risk_level IS '生命周期风险等级：low / medium / high / critical / unknown';
COMMENT ON COLUMN db_version.is_supported IS '当前是否仍受支持';
COMMENT ON COLUMN db_version.is_recommended IS '是否推荐新系统使用';

CREATE INDEX IF NOT EXISTS idx_db_version_lifecycle_status ON db_version(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_db_version_eol_date ON db_version(eol_date);


-- ============================================================
-- 3. BIZ 等级表
-- ============================================================

CREATE TABLE IF NOT EXISTS biz_level (
    id BIGSERIAL PRIMARY KEY,
    level_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(20) NOT NULL UNIQUE,
    level_value INTEGER NOT NULL UNIQUE,
    color VARCHAR(20),
    description TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE biz_level IS '业务重要等级/BIA等级表，属于业务层，但会影响告警、备份、巡检、变更等运维策略';
COMMENT ON COLUMN biz_level.level_code IS '等级编码，例如 BIZ-NORMAL、BIZ-IMPORTANT、BIZ-KEY、BIZ-CRITICAL';
COMMENT ON COLUMN biz_level.name IS '等级名称：一般、重要、關鍵、極重要';
COMMENT ON COLUMN biz_level.level_value IS '等级数值，越大越重要';
COMMENT ON COLUMN biz_level.color IS '前端显示颜色';
COMMENT ON COLUMN biz_level.description IS '等级说明';

DROP TRIGGER IF EXISTS trg_biz_level_updated_at ON biz_level;
CREATE TRIGGER trg_biz_level_updated_at
BEFORE UPDATE ON biz_level
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


-- ============================================================
-- 4. 业务系统和实例增加 BIZ 等级
-- ============================================================

ALTER TABLE business_system
ADD COLUMN IF NOT EXISTS biz_level_id BIGINT REFERENCES biz_level(id);

COMMENT ON COLUMN business_system.biz_level_id IS '业务系统默认BIZ等级，实例未设置时可继承';

ALTER TABLE db_instance
ADD COLUMN IF NOT EXISTS biz_level_id BIGINT REFERENCES biz_level(id);

COMMENT ON COLUMN db_instance.biz_level_id IS '实例级BIZ等级，优先级高于业务系统默认等级';

CREATE INDEX IF NOT EXISTS idx_business_system_biz_level ON business_system(biz_level_id);
CREATE INDEX IF NOT EXISTS idx_db_instance_biz_level ON db_instance(biz_level_id);


-- ============================================================
-- 5. BIZ 等级与告警联动
-- ============================================================

ALTER TABLE alert_rule
ADD COLUMN IF NOT EXISTS min_biz_level_value INTEGER,
ADD COLUMN IF NOT EXISTS notify_level_policy JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN alert_rule.min_biz_level_value IS '规则生效的最低BIZ等级数值，例如 3 表示仅關鍵及以上触发';
COMMENT ON COLUMN alert_rule.notify_level_policy IS '不同BIZ等级的通知策略JSON，例如 {"4":["phone","wecom"],"3":["wecom"]}';


-- ============================================================
-- 6. BIZ 等级与备份策略联动
-- ============================================================

ALTER TABLE backup_policy
ADD COLUMN IF NOT EXISTS min_biz_level_value INTEGER,
ADD COLUMN IF NOT EXISTS rpo_minutes INTEGER,
ADD COLUMN IF NOT EXISTS rto_minutes INTEGER;

COMMENT ON COLUMN backup_policy.min_biz_level_value IS '策略建议适用的最低BIZ等级';
COMMENT ON COLUMN backup_policy.rpo_minutes IS '建议RPO，单位分钟';
COMMENT ON COLUMN backup_policy.rto_minutes IS '建议RTO，单位分钟';


-- ============================================================
-- 7. BIZ 等级与巡检任务联动
-- ============================================================

ALTER TABLE inspection_task
ADD COLUMN IF NOT EXISTS min_biz_level_value INTEGER,
ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 100;

COMMENT ON COLUMN inspection_task.min_biz_level_value IS '任务适用最低BIZ等级';
COMMENT ON COLUMN inspection_task.priority IS '巡检任务优先级，数值越小越优先';


-- ============================================================
-- 8. 变更记录增加 BIZ 影响字段
-- ============================================================

ALTER TABLE change_record
ADD COLUMN IF NOT EXISTS biz_impact_level_id BIGINT REFERENCES biz_level(id),
ADD COLUMN IF NOT EXISTS approval_required BOOLEAN DEFAULT false;

COMMENT ON COLUMN change_record.biz_impact_level_id IS '本次变更影响的BIZ等级';
COMMENT ON COLUMN change_record.approval_required IS '是否需要审批，通常極重要/關鍵需要审批';


-- ============================================================
-- 9. 示例数据：BIZ 等级
-- ============================================================

INSERT INTO biz_level (level_code, name, level_value, color, description)
VALUES
('BIZ-NORMAL', '一般', 1, 'gray', '普通业务，故障影响范围较小'),
('BIZ-IMPORTANT', '重要', 2, 'blue', '重要业务，故障会影响部分业务'),
('BIZ-KEY', '關鍵', 3, 'orange', '关键业务，故障会影响核心流程'),
('BIZ-CRITICAL', '極重要', 4, 'red', '极重要业务，故障会造成重大业务影响')
ON CONFLICT (level_code) DO UPDATE SET
    name = EXCLUDED.name,
    level_value = EXCLUDED.level_value,
    color = EXCLUDED.color,
    description = EXCLUDED.description,
    updated_at = now();


-- ============================================================
-- 10. 示例数据：生命周期维护示例
-- 注意：以下日期仅为示例，请以官方生命周期政策或企业内部标准为准
-- ============================================================

UPDATE os_version
SET lifecycle_status = 'active',
    risk_level = 'low',
    is_supported = true,
    is_recommended = true
WHERE os_code IN ('OS-RHEL-8', 'OS-DEBIAN-13');

UPDATE os_version
SET lifecycle_status = 'maintenance',
    risk_level = 'medium',
    is_supported = true,
    is_recommended = false
WHERE os_code IN ('OS-OL-7');

UPDATE db_version dv
SET lifecycle_status = 'maintenance',
    risk_level = 'medium',
    is_supported = true,
    is_recommended = false
FROM db_type dt
WHERE dv.db_type_id = dt.id
  AND dt.type_code = 'ORACLE'
  AND dv.version_code = '19c';

-- 示例：给业务系统默认等级
UPDATE business_system
SET biz_level_id = (SELECT id FROM biz_level WHERE level_code = 'BIZ-CRITICAL')
WHERE system_code IN ('SYS-ECARD');

-- 示例：给实例单独设置等级，覆盖业务系统默认值
UPDATE db_instance
SET biz_level_id = (SELECT id FROM biz_level WHERE level_code = 'BIZ-CRITICAL')
WHERE instance_code IN ('DB-ECARD-ORA-01');


-- ============================================================
-- 11. 视图：实例最终 BIZ 等级
-- 规则：实例级 > 业务系统级 > NULL
-- ============================================================

CREATE OR REPLACE VIEW v_instance_biz_level AS
SELECT
    di.id AS instance_id,
    di.instance_code,
    di.instance_name,
    COALESCE(ibl.id, sbl.id) AS final_biz_level_id,
    COALESCE(ibl.level_code, sbl.level_code) AS final_biz_level_code,
    COALESCE(ibl.name, sbl.name) AS final_biz_level_name,
    COALESCE(ibl.level_value, sbl.level_value) AS final_biz_level_value,
    COALESCE(ibl.color, sbl.color) AS final_biz_level_color,
    CASE
        WHEN ibl.id IS NOT NULL THEN 'instance'
        WHEN sbl.id IS NOT NULL THEN 'business_system'
        ELSE 'none'
    END AS source_type
FROM db_instance di
LEFT JOIN biz_level ibl ON di.biz_level_id = ibl.id
LEFT JOIN instance_system isys ON isys.instance_id = di.id
LEFT JOIN business_system bs ON bs.id = isys.system_id
LEFT JOIN biz_level sbl ON bs.biz_level_id = sbl.id;

COMMENT ON VIEW v_instance_biz_level IS '实例最终BIZ等级视图。实例级优先，否则继承业务系统等级';


-- ============================================================
-- 12. 视图：OS/DB 生命周期风险实例
-- ============================================================

CREATE OR REPLACE VIEW v_instance_lifecycle_risk AS
SELECT
    di.id AS instance_id,
    di.instance_code,
    di.instance_name,
    s.hostname,
    s.ip_address,
    os.os_name,
    os.os_version,
    os.lifecycle_status AS os_lifecycle_status,
    os.eol_date AS os_eol_date,
    os.risk_level AS os_risk_level,
    dt.name AS db_type,
    dv.version_code AS db_version,
    dv.lifecycle_status AS db_lifecycle_status,
    dv.eol_date AS db_eol_date,
    dv.risk_level AS db_risk_level,
    CASE
        WHEN os.lifecycle_status IN ('eol') OR dv.lifecycle_status IN ('eol') THEN 'critical'
        WHEN os.lifecycle_status IN ('eos') OR dv.lifecycle_status IN ('eos') THEN 'high'
        WHEN os.eol_date <= CURRENT_DATE + INTERVAL '180 days'
          OR dv.eol_date <= CURRENT_DATE + INTERVAL '180 days' THEN 'medium'
        ELSE 'low'
    END AS overall_lifecycle_risk
FROM db_instance di
LEFT JOIN server s ON di.server_id = s.id
LEFT JOIN os_version os ON s.os_version_id = os.id
LEFT JOIN db_type dt ON di.db_type_id = dt.id
LEFT JOIN db_version dv ON di.db_version_id = dv.id;

COMMENT ON VIEW v_instance_lifecycle_risk IS '实例OS/DB生命周期风险视图';


-- ============================================================
-- 13. 告警规则示例：只对關鍵及以上实例触发
-- ============================================================

INSERT INTO alert_rule (
    rule_code, name, resource_type, metric_code, condition_operator,
    threshold_value, severity, duration_seconds, min_biz_level_value, notify_level_policy
)
VALUES (
    'ALERT-DB-DOWN-KEY-UP',
    '關鍵及以上数据库不可连接',
    'instance',
    'db_status',
    '=',
    'down',
    'critical',
    60,
    3,
    '{"4":["phone","wecom","email"],"3":["wecom","email"],"2":["email"],"1":[]}'::jsonb
)
ON CONFLICT (rule_code) DO UPDATE SET
    min_biz_level_value = EXCLUDED.min_biz_level_value,
    notify_level_policy = EXCLUDED.notify_level_policy,
    updated_at = now();


-- ============================================================
-- 14. 备份策略示例：按 BIZ 等级推荐
-- ============================================================

INSERT INTO backup_policy (
    policy_code, name, backup_type, schedule_cron, retention_days,
    storage_type, storage_path, min_biz_level_value, rpo_minutes, rto_minutes
)
VALUES
('BKP-CRITICAL-FULL-DAILY', '極重要每日全备', 'full', '0 2 * * *', 30, 'nfs', '/backup/critical/full', 4, 60, 120),
('BKP-KEY-FULL-DAILY', '關鍵每日全备', 'full', '0 3 * * *', 30, 'nfs', '/backup/key/full', 3, 240, 240),
('BKP-IMPORTANT-WEEKLY', '重要每周全备', 'full', '0 3 * * 0', 14, 'nfs', '/backup/important/full', 2, 1440, 480)
ON CONFLICT (policy_code) DO UPDATE SET
    min_biz_level_value = EXCLUDED.min_biz_level_value,
    rpo_minutes = EXCLUDED.rpo_minutes,
    rto_minutes = EXCLUDED.rto_minutes,
    updated_at = now();


-- ============================================================
-- 15. 巡检任务示例：按 BIZ 等级
-- ============================================================

UPDATE inspection_task
SET min_biz_level_value = 3,
    priority = 10
WHERE task_code LIKE '%DAILY%';


-- ============================================================
-- 16. 常用查询
-- ============================================================

-- 查询極重要实例
-- SELECT * FROM v_instance_biz_level WHERE final_biz_level_value = 4;

-- 查询OS/DB生命周期高风险实例
-- SELECT * FROM v_instance_lifecycle_risk
-- WHERE overall_lifecycle_risk IN ('critical','high','medium')
-- ORDER BY overall_lifecycle_risk, db_eol_date, os_eol_date;

-- 查询需要优先巡检的实例
-- SELECT di.instance_code, di.instance_name, v.final_biz_level_name, v.final_biz_level_value
-- FROM db_instance di
-- JOIN v_instance_biz_level v ON v.instance_id = di.id
-- WHERE v.final_biz_level_value >= 3
-- ORDER BY v.final_biz_level_value DESC;

-- 查询某告警规则是否适用于某实例
-- SELECT
--     ar.rule_code,
--     di.instance_code,
--     v.final_biz_level_name,
--     v.final_biz_level_value,
--     ar.min_biz_level_value,
--     CASE
--       WHEN v.final_biz_level_value >= COALESCE(ar.min_biz_level_value, 0) THEN true
--       ELSE false
--     END AS rule_applicable
-- FROM alert_rule ar
-- CROSS JOIN db_instance di
-- JOIN v_instance_biz_level v ON v.instance_id = di.id
-- WHERE ar.rule_code = 'ALERT-DB-DOWN-KEY-UP';


-- ============================================================
-- 业务架构评分模块
-- ============================================================


-- ============================================================
-- DBOps 业务架构评分模块
-- 适用对象：
--   已执行 dbops_full_design.sql 或 dbops_schema_42_site_version.sql
--   已存在 business_system / instance_system / db_instance / cluster /
--   replication_topology / backup_policy / instance_backup_policy /
--   db_version / os_version / instance_status / biz_level 等表
--
-- 目标：
--   按业务系统进行架构评分，例如总分10分：
--     没有备援       -5分
--     没有异地备份   -3分
--     DB版本EOL      -2分
--     OS版本EOL      -2分
--     没有监控       -2分
--
-- 说明：
--   评分模块不改核心资产主线，只新增评分表，少量增强已有表。
-- ============================================================

SET search_path TO dbops;

-- ============================================================
-- 1. 增强已有表
-- ============================================================

-- 1.1 backup_policy 增加是否异地备份标识
ALTER TABLE backup_policy
ADD COLUMN IF NOT EXISTS is_remote_backup BOOLEAN DEFAULT false;

COMMENT ON COLUMN backup_policy.is_remote_backup IS
'是否异地备份策略。true=该备份策略满足异地备份要求，用于业务架构评分中的“是否有异地备份”。';

-- 1.2 cluster 增加是否具备HA能力标识
-- 说明：
--   自动拓扑成熟后，优先使用 replication_topology 判断主备。
--   但很多系统初期未自动采集主备拓扑，因此保留 ha_enabled 作为人工标识。
ALTER TABLE cluster
ADD COLUMN IF NOT EXISTS ha_enabled BOOLEAN DEFAULT false;

COMMENT ON COLUMN cluster.ha_enabled IS
'是否具备高可用/备援能力。用于主备拓扑未自动采集前的人工标识。';

-- 1.3 可选：cluster 增加HA说明
ALTER TABLE cluster
ADD COLUMN IF NOT EXISTS ha_remark TEXT;

COMMENT ON COLUMN cluster.ha_remark IS
'高可用说明，例如 Data Guard、RAC、MGR、Patroni、应用级备援等。';


-- ============================================================
-- 2. 新增业务评分规则表
-- ============================================================

CREATE TABLE IF NOT EXISTS biz_score_rule (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(50) NOT NULL UNIQUE,
    rule_name VARCHAR(200) NOT NULL,
    description TEXT,
    deduct_score NUMERIC(5,2) NOT NULL,
    is_enabled BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE biz_score_rule IS
'业务架构评分规则表。定义扣分规则，例如无备援、无异地备份、版本EOL、无监控。';

COMMENT ON COLUMN biz_score_rule.rule_code IS
'规则编码，例如 NO_HA、NO_REMOTE_BACKUP、DB_EOL、OS_EOL、NO_MONITOR。';

COMMENT ON COLUMN biz_score_rule.rule_name IS
'规则名称，例如 没有备援、没有异地备份。';

COMMENT ON COLUMN biz_score_rule.description IS
'规则说明。';

COMMENT ON COLUMN biz_score_rule.deduct_score IS
'扣分值。';

COMMENT ON COLUMN biz_score_rule.is_enabled IS
'是否启用该评分规则。';

COMMENT ON COLUMN biz_score_rule.sort_order IS
'排序字段，用于页面展示。';

DROP TRIGGER IF EXISTS trg_biz_score_rule_updated_at ON biz_score_rule;
CREATE TRIGGER trg_biz_score_rule_updated_at
BEFORE UPDATE ON biz_score_rule
FOR EACH ROW EXECUTE FUNCTION dbops.set_updated_at();


-- ============================================================
-- 3. 新增业务评分结果表
-- ============================================================

CREATE TABLE IF NOT EXISTS biz_score_result (
    id BIGSERIAL PRIMARY KEY,
    system_id BIGINT NOT NULL REFERENCES business_system(id) ON DELETE CASCADE,
    base_score NUMERIC(5,2) DEFAULT 10,
    deduct_score NUMERIC(5,2) DEFAULT 0,
    final_score NUMERIC(5,2) NOT NULL,
    score_level VARCHAR(50),
    score_batch VARCHAR(50),
    scored_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE biz_score_result IS
'业务系统架构评分结果表。用于保存某次评分快照。';

COMMENT ON COLUMN biz_score_result.system_id IS
'业务系统ID，关联 business_system。';

COMMENT ON COLUMN biz_score_result.base_score IS
'基础分，默认10分。';

COMMENT ON COLUMN biz_score_result.deduct_score IS
'总扣分。';

COMMENT ON COLUMN biz_score_result.final_score IS
'最终得分，通常为 base_score - deduct_score，最低为0。';

COMMENT ON COLUMN biz_score_result.score_level IS
'评分等级，例如 A/B/C/D。';

COMMENT ON COLUMN biz_score_result.score_batch IS
'评分批次，例如 20260425 或 daily-20260425。';

COMMENT ON COLUMN biz_score_result.scored_at IS
'评分时间。';

CREATE INDEX IF NOT EXISTS idx_biz_score_result_system_time
ON biz_score_result(system_id, scored_at DESC);

CREATE INDEX IF NOT EXISTS idx_biz_score_result_batch
ON biz_score_result(score_batch);


-- ============================================================
-- 4. 新增业务评分扣分明细表
-- ============================================================

CREATE TABLE IF NOT EXISTS biz_score_result_detail (
    id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL REFERENCES biz_score_result(id) ON DELETE CASCADE,
    rule_id BIGINT NOT NULL REFERENCES biz_score_rule(id),
    deduct_score NUMERIC(5,2) NOT NULL,
    reason TEXT,
    evidence JSONB,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE biz_score_result_detail IS
'业务系统架构评分扣分明细表。保存每条扣分原因及证据。';

COMMENT ON COLUMN biz_score_result_detail.result_id IS
'评分结果ID，关联 biz_score_result。';

COMMENT ON COLUMN biz_score_result_detail.rule_id IS
'触发的评分规则ID，关联 biz_score_rule。';

COMMENT ON COLUMN biz_score_result_detail.deduct_score IS
'本项扣分值。';

COMMENT ON COLUMN biz_score_result_detail.reason IS
'扣分原因说明。';

COMMENT ON COLUMN biz_score_result_detail.evidence IS
'扣分证据JSON，例如涉及实例、版本、拓扑、备份策略等。';

CREATE INDEX IF NOT EXISTS idx_biz_score_detail_result
ON biz_score_result_detail(result_id);

CREATE INDEX IF NOT EXISTS idx_biz_score_detail_rule
ON biz_score_result_detail(rule_id);


-- ============================================================
-- 5. 初始化评分规则
-- ============================================================

INSERT INTO biz_score_rule
(rule_code, rule_name, description, deduct_score, is_enabled, sort_order)
VALUES
('NO_HA', '没有备援', '业务系统没有主备、集群、复制拓扑或人工HA标识', 5, true, 10),
('NO_REMOTE_BACKUP', '没有异地备份', '业务系统没有绑定任何异地备份策略', 3, true, 20),
('DB_EOL', '数据库版本过期', '业务系统存在 lifecycle_status = eol 的数据库版本', 2, true, 30),
('OS_EOL', 'OS版本过期', '业务系统存在 lifecycle_status = eol 的操作系统版本', 2, true, 40),
('NO_MONITOR', '没有监控', '业务系统实例没有 instance_status 当前状态记录', 2, true, 50)
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name = EXCLUDED.rule_name,
    description = EXCLUDED.description,
    deduct_score = EXCLUDED.deduct_score,
    is_enabled = EXCLUDED.is_enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = now();


-- ============================================================
-- 6. 业务系统实例基础视图
-- ============================================================

CREATE OR REPLACE VIEW v_biz_score_base_instances AS
SELECT
    bs.id AS system_id,
    bs.system_code,
    bs.name AS system_name,
    bs.biz_level_id AS system_biz_level_id,
    bl.name AS system_biz_level_name,
    bl.level_value AS system_biz_level_value,
    di.id AS instance_id,
    di.instance_code,
    di.instance_name,
    di.cluster_id,
    di.db_version_id,
    s.id AS server_id,
    s.server_code,
    s.hostname,
    s.ip_address,
    s.os_version_id
FROM business_system bs
JOIN instance_system isys ON isys.system_id = bs.id
JOIN db_instance di ON di.id = isys.instance_id
LEFT JOIN server s ON s.id = di.server_id
LEFT JOIN biz_level bl ON bl.id = bs.biz_level_id;

COMMENT ON VIEW v_biz_score_base_instances IS
'业务评分基础实例视图。把 business_system → instance_system → db_instance → server 拉平成评分输入。';


-- ============================================================
-- 7. 实时评分视图
-- ============================================================

CREATE OR REPLACE VIEW v_biz_arch_score AS
WITH biz AS (
    SELECT DISTINCT
        system_id,
        system_code,
        system_name,
        system_biz_level_name AS biz_level_name,
        system_biz_level_value AS biz_level_value
    FROM v_biz_score_base_instances
),
rule_score AS (
    SELECT
        rule_code,
        deduct_score,
        is_enabled
    FROM biz_score_rule
),
ha AS (
    SELECT
        bi.system_id,
        CASE
            WHEN COUNT(rt.id) > 0
              OR COUNT(c.id) FILTER (WHERE c.ha_enabled = true) > 0
            THEN 0
            ELSE COALESCE((SELECT deduct_score FROM rule_score WHERE rule_code = 'NO_HA' AND is_enabled = true), 0)
        END AS deduct_score
    FROM v_biz_score_base_instances bi
    LEFT JOIN replication_topology rt
        ON rt.primary_instance_id = bi.instance_id
        OR rt.standby_instance_id = bi.instance_id
    LEFT JOIN cluster c ON c.id = bi.cluster_id
    GROUP BY bi.system_id
),
remote_backup AS (
    SELECT
        bi.system_id,
        CASE
            WHEN COUNT(bp.id) FILTER (WHERE bp.is_remote_backup = true) > 0
            THEN 0
            ELSE COALESCE((SELECT deduct_score FROM rule_score WHERE rule_code = 'NO_REMOTE_BACKUP' AND is_enabled = true), 0)
        END AS deduct_score
    FROM v_biz_score_base_instances bi
    LEFT JOIN instance_backup_policy ibp ON ibp.instance_id = bi.instance_id
    LEFT JOIN backup_policy bp ON bp.id = ibp.policy_id
    GROUP BY bi.system_id
),
db_eol AS (
    SELECT
        bi.system_id,
        CASE
            WHEN COUNT(dv.id) FILTER (WHERE dv.lifecycle_status = 'eol') > 0
            THEN COALESCE((SELECT deduct_score FROM rule_score WHERE rule_code = 'DB_EOL' AND is_enabled = true), 0)
            ELSE 0
        END AS deduct_score
    FROM v_biz_score_base_instances bi
    LEFT JOIN db_version dv ON dv.id = bi.db_version_id
    GROUP BY bi.system_id
),
os_eol AS (
    SELECT
        bi.system_id,
        CASE
            WHEN COUNT(os.id) FILTER (WHERE os.lifecycle_status = 'eol') > 0
            THEN COALESCE((SELECT deduct_score FROM rule_score WHERE rule_code = 'OS_EOL' AND is_enabled = true), 0)
            ELSE 0
        END AS deduct_score
    FROM v_biz_score_base_instances bi
    LEFT JOIN os_version os ON os.id = bi.os_version_id
    GROUP BY bi.system_id
),
monitor AS (
    SELECT
        bi.system_id,
        CASE
            WHEN COUNT(ist.id) > 0
            THEN 0
            ELSE COALESCE((SELECT deduct_score FROM rule_score WHERE rule_code = 'NO_MONITOR' AND is_enabled = true), 0)
        END AS deduct_score
    FROM v_biz_score_base_instances bi
    LEFT JOIN instance_status ist ON ist.instance_id = bi.instance_id
    GROUP BY bi.system_id
),
score AS (
    SELECT
        b.system_id,
        b.system_code,
        b.system_name,
        b.biz_level_name,
        b.biz_level_value,
        10::NUMERIC AS base_score,
        COALESCE(ha.deduct_score, 0)
        + COALESCE(rb.deduct_score, 0)
        + COALESCE(de.deduct_score, 0)
        + COALESCE(oe.deduct_score, 0)
        + COALESCE(mo.deduct_score, 0) AS deduct_score,
        COALESCE(ha.deduct_score, 0) AS no_ha_deduct,
        COALESCE(rb.deduct_score, 0) AS no_remote_backup_deduct,
        COALESCE(de.deduct_score, 0) AS db_eol_deduct,
        COALESCE(oe.deduct_score, 0) AS os_eol_deduct,
        COALESCE(mo.deduct_score, 0) AS no_monitor_deduct
    FROM biz b
    LEFT JOIN ha ON ha.system_id = b.system_id
    LEFT JOIN remote_backup rb ON rb.system_id = b.system_id
    LEFT JOIN db_eol de ON de.system_id = b.system_id
    LEFT JOIN os_eol oe ON oe.system_id = b.system_id
    LEFT JOIN monitor mo ON mo.system_id = b.system_id
)
SELECT
    *,
    GREATEST(0, base_score - deduct_score) AS final_score,
    CASE
        WHEN GREATEST(0, base_score - deduct_score) >= 9 THEN 'A'
        WHEN GREATEST(0, base_score - deduct_score) >= 7 THEN 'B'
        WHEN GREATEST(0, base_score - deduct_score) >= 5 THEN 'C'
        ELSE 'D'
    END AS score_level
FROM score;

COMMENT ON VIEW v_biz_arch_score IS
'业务架构实时评分视图。默认基础分10分，根据备援、异地备份、生命周期、监控进行扣分。';


-- ============================================================
-- 8. 扣分明细视图
-- ============================================================

CREATE OR REPLACE VIEW v_biz_arch_score_detail AS
WITH bi AS (
    SELECT * FROM v_biz_score_base_instances
),
rule_enabled AS (
    SELECT rule_code, rule_name, deduct_score
    FROM biz_score_rule
    WHERE is_enabled = true
),
no_ha AS (
    SELECT
        bi.system_id,
        'NO_HA'::VARCHAR AS rule_code,
        (SELECT rule_name FROM rule_enabled WHERE rule_code = 'NO_HA') AS rule_name,
        (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'NO_HA') AS deduct_score,
        '业务系统没有主备/集群/复制拓扑或人工HA标识' AS reason,
        jsonb_build_object(
            'instances', jsonb_agg(DISTINCT bi.instance_code),
            'clusters', jsonb_agg(DISTINCT bi.cluster_id)
        ) AS evidence
    FROM bi
    LEFT JOIN replication_topology rt
        ON rt.primary_instance_id = bi.instance_id
        OR rt.standby_instance_id = bi.instance_id
    LEFT JOIN cluster c ON c.id = bi.cluster_id
    GROUP BY bi.system_id
    HAVING COUNT(rt.id) = 0
       AND COUNT(c.id) FILTER (WHERE c.ha_enabled = true) = 0
       AND (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'NO_HA') IS NOT NULL
),
no_remote_backup AS (
    SELECT
        bi.system_id,
        'NO_REMOTE_BACKUP'::VARCHAR AS rule_code,
        (SELECT rule_name FROM rule_enabled WHERE rule_code = 'NO_REMOTE_BACKUP') AS rule_name,
        (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'NO_REMOTE_BACKUP') AS deduct_score,
        '业务系统没有任何异地备份策略' AS reason,
        jsonb_build_object(
            'instances', jsonb_agg(DISTINCT bi.instance_code)
        ) AS evidence
    FROM bi
    LEFT JOIN instance_backup_policy ibp ON ibp.instance_id = bi.instance_id
    LEFT JOIN backup_policy bp ON bp.id = ibp.policy_id
    GROUP BY bi.system_id
    HAVING COUNT(bp.id) FILTER (WHERE bp.is_remote_backup = true) = 0
       AND (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'NO_REMOTE_BACKUP') IS NOT NULL
),
db_eol AS (
    SELECT
        bi.system_id,
        'DB_EOL'::VARCHAR AS rule_code,
        (SELECT rule_name FROM rule_enabled WHERE rule_code = 'DB_EOL') AS rule_name,
        (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'DB_EOL') AS deduct_score,
        '业务系统存在EOL数据库版本' AS reason,
        jsonb_build_object(
            'instances', jsonb_agg(DISTINCT bi.instance_code),
            'db_versions', jsonb_agg(DISTINCT dv.version_code)
        ) AS evidence
    FROM bi
    JOIN db_version dv ON dv.id = bi.db_version_id
    WHERE dv.lifecycle_status = 'eol'
      AND (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'DB_EOL') IS NOT NULL
    GROUP BY bi.system_id
),
os_eol AS (
    SELECT
        bi.system_id,
        'OS_EOL'::VARCHAR AS rule_code,
        (SELECT rule_name FROM rule_enabled WHERE rule_code = 'OS_EOL') AS rule_name,
        (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'OS_EOL') AS deduct_score,
        '业务系统存在EOL操作系统版本' AS reason,
        jsonb_build_object(
            'instances', jsonb_agg(DISTINCT bi.instance_code),
            'os_versions', jsonb_agg(DISTINCT os.os_name || ' ' || COALESCE(os.os_version, ''))
        ) AS evidence
    FROM bi
    JOIN os_version os ON os.id = bi.os_version_id
    WHERE os.lifecycle_status = 'eol'
      AND (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'OS_EOL') IS NOT NULL
    GROUP BY bi.system_id
),
no_monitor AS (
    SELECT
        bi.system_id,
        'NO_MONITOR'::VARCHAR AS rule_code,
        (SELECT rule_name FROM rule_enabled WHERE rule_code = 'NO_MONITOR') AS rule_name,
        (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'NO_MONITOR') AS deduct_score,
        '业务系统实例没有当前监控状态记录' AS reason,
        jsonb_build_object(
            'instances', jsonb_agg(DISTINCT bi.instance_code)
        ) AS evidence
    FROM bi
    LEFT JOIN instance_status ist ON ist.instance_id = bi.instance_id
    GROUP BY bi.system_id
    HAVING COUNT(ist.id) = 0
       AND (SELECT deduct_score FROM rule_enabled WHERE rule_code = 'NO_MONITOR') IS NOT NULL
)
SELECT * FROM no_ha
UNION ALL
SELECT * FROM no_remote_backup
UNION ALL
SELECT * FROM db_eol
UNION ALL
SELECT * FROM os_eol
UNION ALL
SELECT * FROM no_monitor;

COMMENT ON VIEW v_biz_arch_score_detail IS
'业务架构评分扣分明细实时视图。展示每个业务系统触发了哪些扣分规则及证据。';


-- ============================================================
-- 9. 保存评分快照的函数
-- ============================================================

CREATE OR REPLACE FUNCTION save_biz_arch_score_snapshot(p_score_batch VARCHAR DEFAULT to_char(now(), 'YYYYMMDDHH24MISS'))
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    INSERT INTO biz_score_result (
        system_id,
        base_score,
        deduct_score,
        final_score,
        score_level,
        score_batch,
        scored_at
    )
    SELECT
        system_id,
        base_score,
        deduct_score,
        final_score,
        score_level,
        p_score_batch,
        now()
    FROM v_biz_arch_score;

    GET DIAGNOSTICS v_count = ROW_COUNT;

    INSERT INTO biz_score_result_detail (
        result_id,
        rule_id,
        deduct_score,
        reason,
        evidence
    )
    SELECT
        r.id,
        rule.id,
        d.deduct_score,
        d.reason,
        d.evidence
    FROM biz_score_result r
    JOIN v_biz_arch_score_detail d
        ON d.system_id = r.system_id
    JOIN biz_score_rule rule
        ON rule.rule_code = d.rule_code
    WHERE r.score_batch = p_score_batch;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION save_biz_arch_score_snapshot(VARCHAR) IS
'保存业务架构评分快照。将实时评分视图结果写入 biz_score_result 和 biz_score_result_detail。';


-- ============================================================
-- 10. 示例：设置HA和异地备份
-- ============================================================

-- 示例：把某个集群标记为具备高可用
-- UPDATE cluster
-- SET ha_enabled = true,
--     ha_remark = 'Oracle Data Guard'
-- WHERE cluster_code = 'CLU-ECARD-ORA-DG-01';

-- 示例：把某备份策略标记为异地备份
-- UPDATE backup_policy
-- SET is_remote_backup = true
-- WHERE policy_code = 'BKP-ORA-REMOTE-DAILY';


-- ============================================================
-- 11. 查询示例
-- ============================================================

-- 11.1 查询所有业务系统实时评分
-- SELECT * FROM v_biz_arch_score ORDER BY final_score ASC;

-- 11.2 查询某个业务系统扣分明细
-- SELECT d.*
-- FROM v_biz_arch_score_detail d
-- JOIN business_system bs ON bs.id = d.system_id
-- WHERE bs.system_code = 'SYS-ECARD';

-- 11.3 保存一次评分快照
-- SELECT save_biz_arch_score_snapshot('daily-20260425');

-- 11.4 查询最近一次评分结果
-- SELECT
--     bs.system_code,
--     bs.name AS system_name,
--     r.base_score,
--     r.deduct_score,
--     r.final_score,
--     r.score_level,
--     r.scored_at
-- FROM biz_score_result r
-- JOIN business_system bs ON bs.id = r.system_id
-- WHERE r.score_batch = 'daily-20260425'
-- ORDER BY r.final_score ASC;

-- 11.5 查询评分明细
-- SELECT
--     bs.system_code,
--     bs.name AS system_name,
--     rule.rule_code,
--     rule.rule_name,
--     d.deduct_score,
--     d.reason,
--     d.evidence
-- FROM biz_score_result_detail d
-- JOIN biz_score_result r ON r.id = d.result_id
-- JOIN business_system bs ON bs.id = r.system_id
-- JOIN biz_score_rule rule ON rule.id = d.rule_id
-- WHERE r.score_batch = 'daily-20260425'
-- ORDER BY bs.system_code, rule.sort_order;


-- ============================================================
-- 固定8大类与Excel导入校验补丁
-- ============================================================


-- ============================================================
-- FINAL PATCH: 固定 8 大系统分类 + Excel 导入校验
-- ============================================================

SET search_path TO dbops;

INSERT INTO system_group (group_code, name, description)
VALUES
('GRP-ERP', 'ERP', 'ERP類系統'),
('GRP-HR', '人資', '人資類系統'),
('GRP-PARK', '園區', '園區類系統'),
('GRP-TRAVEL', '差旅', '差旅類系統'),
('GRP-PURCHASE', '採購', '採購類系統'),
('GRP-XIANGXIN', '相信', '相信類系統'),
('GRP-CUSTOMS', '關務', '關務類系統'),
('GRP-ESIGN', '電簽', '電簽類系統')
ON CONFLICT (group_code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    updated_at = now();

CREATE TABLE IF NOT EXISTS staging_excel_import (
    id BIGSERIAL PRIMARY KEY,
    cluster_key VARCHAR(100),
    cluster_type VARCHAR(100),
    node_role VARCHAR(100),
    service_scope TEXT,
    platform_category VARCHAR(50),
    system_name VARCHAR(300),
    ip INET,
    instance_name VARCHAR(200),
    port INTEGER,
    machine_type VARCHAR(50),
    dns_name VARCHAR(200),
    vip INET,
    host_admin VARCHAR(100),
    host_admin_contact VARCHAR(100),
    os_admin VARCHAR(100),
    os_admin_contact VARCHAR(100),
    app_owner VARCHAR(100),
    app_owner_contact VARCHAR(100),
    business_manager VARCHAR(100),
    business_manager_contact VARCHAR(100),
    business_belong_manager VARCHAR(100),
    dba_owner VARCHAR(100),
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
    imported_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE staging_excel_import IS 'Excel原始导入暂存表。先导入这里，再清洗到正式表。';
COMMENT ON COLUMN staging_excel_import.platform_category IS '平台分类，固定8类：ERP/人資/園區/差旅/採購/相信/關務/電簽，对应 system_group。';
COMMENT ON COLUMN staging_excel_import.service_scope IS '应用业务范畴，建议逗号分隔，例如：全集團,一卡通服務；导入为 tag/resource_tag。';

CREATE OR REPLACE VIEW v_staging_invalid_platform_category AS
SELECT *
FROM staging_excel_import s
WHERE s.platform_category IS NOT NULL
  AND s.platform_category NOT IN ('ERP','人資','園區','差旅','採購','相信','關務','電簽');

COMMENT ON VIEW v_staging_invalid_platform_category IS 'Excel导入校验：平台分类不在固定8类中的记录。';

CREATE OR REPLACE VIEW v_staging_system_category_conflict AS
SELECT
    system_name,
    COUNT(DISTINCT platform_category) AS category_count,
    STRING_AGG(DISTINCT platform_category, ',') AS categories
FROM staging_excel_import
WHERE system_name IS NOT NULL
GROUP BY system_name
HAVING COUNT(DISTINCT platform_category) > 1;

COMMENT ON VIEW v_staging_system_category_conflict IS 'Excel导入校验：同一系统名称对应多个平台分类，需要人工修正。';

ALTER TABLE tag ADD COLUMN IF NOT EXISTS tag_type VARCHAR(50);
COMMENT ON COLUMN tag.tag_type IS '标签类型：scope / monitor / mdr / audit / custom';

INSERT INTO tag (tag_code, name, tag_type, remark)
SELECT DISTINCT
    'TAG-SCOPE-' || upper(substr(md5(trim(scope_value)), 1, 10)) AS tag_code,
    trim(scope_value) AS name,
    'scope' AS tag_type,
    '从Excel 应用业务范畴 导入'
FROM staging_excel_import s
CROSS JOIN LATERAL regexp_split_to_table(COALESCE(s.service_scope, ''), '[,，;；]') AS scope_value
WHERE trim(scope_value) <> ''
ON CONFLICT (tag_code) DO UPDATE SET
    name = EXCLUDED.name,
    tag_type = EXCLUDED.tag_type,
    remark = EXCLUDED.remark;

INSERT INTO business_system (
    system_code,
    system_group_id,
    name,
    owner_dept,
    biz_level_id
)
SELECT DISTINCT
    'SYS-' || upper(substr(md5(COALESCE(s.system_name,'') || '|' || COALESCE(s.department,'')), 1, 10)) AS system_code,
    sg.id AS system_group_id,
    s.system_name AS name,
    s.department AS owner_dept,
    bl.id AS biz_level_id
FROM staging_excel_import s
JOIN system_group sg ON sg.name = s.platform_category
LEFT JOIN biz_level bl ON bl.name = s.biz_level_name
WHERE s.system_name IS NOT NULL
  AND s.platform_category IN ('ERP','人資','園區','差旅','採購','相信','關務','電簽')
ON CONFLICT (system_code) DO UPDATE SET
    system_group_id = EXCLUDED.system_group_id,
    name = EXCLUDED.name,
    owner_dept = EXCLUDED.owner_dept,
    biz_level_id = EXCLUDED.biz_level_id,
    updated_at = now();
