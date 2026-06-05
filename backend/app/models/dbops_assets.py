from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import declarative_base, relationship


DbopsAssetBase = declarative_base()
DbopsAssetBase.metadata.schema = "dbops"


class SystemGroup(DbopsAssetBase):
    __tablename__ = "system_group"

    id = Column(BigInteger, primary_key=True)
    group_code = Column(String(50), nullable=False, unique=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class BusinessSystem(DbopsAssetBase):
    __tablename__ = "business_system"

    id = Column(BigInteger, primary_key=True)
    system_code = Column(String(100), nullable=False, unique=True)
    system_name = Column(String(300), nullable=False, unique=True)
    system_group_id = Column(BigInteger, ForeignKey("system_group.id"))
    business_unit = Column(String(200))
    department = Column(String(200))
    service_scope = Column(Text)
    biz_level = Column(String(50))
    status = Column(String(20), nullable=False, server_default=text("'building'"))
    remark = Column(Text)
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    system_group = relationship("SystemGroup")
    contacts = relationship("BusinessSystemContact", back_populates="business_system")
    clusters = relationship("Cluster", back_populates="business_system")


class Contact(DbopsAssetBase):
    __tablename__ = "contact"

    id = Column(BigInteger, primary_key=True)
    employee_no = Column(String(50))
    contact_code = Column(String(100), nullable=False, unique=True)
    contact_name = Column(String(100), nullable=False)
    phone = Column(String(100))
    email = Column(String(200))
    dept = Column(String(200))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    business_links = relationship("BusinessSystemContact", back_populates="contact")


class BusinessSystemContact(DbopsAssetBase):
    __tablename__ = "business_system_contact"

    id = Column(BigInteger, primary_key=True)
    business_system_id = Column(BigInteger, ForeignKey("business_system.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(BigInteger, ForeignKey("contact.id"), nullable=False)
    role_code = Column(String(50), nullable=False)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    business_system = relationship("BusinessSystem", back_populates="contacts")
    contact = relationship("Contact", back_populates="business_links")

    __table_args__ = (
        UniqueConstraint("business_system_id", "contact_id", "role_code", name="uq_business_system_contact"),
    )


class AssetEventHistory(DbopsAssetBase):
    __tablename__ = "asset_event_history"

    id = Column(BigInteger, primary_key=True)
    asset_type = Column(String(50), nullable=False)
    asset_id = Column(BigInteger, nullable=False)
    event_type = Column(String(50), nullable=False)
    before_status = Column(String(20))
    after_status = Column(String(20))
    changed_fields = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    reason = Column(Text)
    operator = Column(String(100))
    operated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_asset_event_history_asset", "asset_type", "asset_id", operated_at.desc()),
        Index("idx_asset_event_history_event", "event_type", operated_at.desc()),
    )


class Site(DbopsAssetBase):
    __tablename__ = "site"

    id = Column(BigInteger, primary_key=True)
    site_code = Column(String(100), nullable=False, unique=True)
    country = Column(String(50), nullable=False)
    deploy_type = Column(String(50), nullable=False)
    provider = Column(String(100), nullable=False)
    factory_area = Column(String(100), nullable=False)
    room_location = Column(String(200), nullable=False)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    servers = relationship("Server", back_populates="site")


class OsVersion(DbopsAssetBase):
    __tablename__ = "os_version"

    id = Column(BigInteger, primary_key=True)
    os_code = Column(String(100), nullable=False, unique=True)
    os_name = Column(String(100), nullable=False)
    version_name = Column(String(200), nullable=False)
    release_date = Column(Date)
    eos_date = Column(Date)
    eol_date = Column(Date)
    lifecycle_status = Column(String(50), nullable=False, server_default=text("'unknown'"))
    risk_level = Column(String(50), nullable=False, server_default=text("'unknown'"))
    is_supported = Column(Boolean, nullable=False, server_default=text("true"))
    is_recommended = Column(Boolean, nullable=False, server_default=text("false"))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    servers = relationship("Server", back_populates="os_version")


class DbType(DbopsAssetBase):
    __tablename__ = "db_type"

    id = Column(BigInteger, primary_key=True)
    type_code = Column(String(50), nullable=False, unique=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(String(50), nullable=False, default="relational", server_default=text("'relational'"))
    license_type = Column(String(20), nullable=False, default="commercial", server_default=text("'commercial'"))
    vendor = Column(String(100))
    remark = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "category IN ('relational','nosql','cache','search','time_series','other')",
            name="ck_db_type_category",
        ),
        CheckConstraint(
            "license_type IN ('open_source','commercial','hybrid')",
            name="ck_db_type_license",
        ),
    )

    versions = relationship("DbVersion", back_populates="db_type")
    clusters = relationship("Cluster", back_populates="db_type")
    instances = relationship("DbInstance", back_populates="db_type")


class DbVersion(DbopsAssetBase):
    __tablename__ = "db_version"

    id = Column(BigInteger, primary_key=True)
    db_type_id = Column(BigInteger, ForeignKey("db_type.id"), nullable=False)
    version_code = Column(String(100), nullable=False)
    version_name = Column(String(200), nullable=False)
    patch_version = Column(String(200))
    architecture_bits = Column(String(20))
    release_date = Column(Date)
    eos_date = Column(Date)
    eol_date = Column(Date)
    lifecycle_status = Column(String(50), nullable=False, server_default=text("'unknown'"))
    risk_level = Column(String(50), nullable=False, server_default=text("'unknown'"))
    is_supported = Column(Boolean, nullable=False, server_default=text("true"))
    is_recommended = Column(Boolean, nullable=False, server_default=text("false"))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    db_type = relationship("DbType", back_populates="versions")
    instances = relationship("DbInstance", back_populates="db_version")

    __table_args__ = (
        UniqueConstraint("db_type_id", "version_code", "patch_version", name="uq_db_version"),
    )


class Server(DbopsAssetBase):
    __tablename__ = "server"

    id = Column(BigInteger, primary_key=True)
    server_code = Column(String(100), nullable=False, unique=True)
    hostname = Column(String(200))
    ip_address = Column(INET, nullable=False, unique=True)
    site_id = Column(BigInteger, ForeignKey("site.id"))
    os_version_id = Column(BigInteger, ForeignKey("os_version.id"))
    cpu_cores = Column(Integer)
    memory_gb = Column(Numeric(10, 2))
    disk_gb = Column(Numeric(12, 2))
    server_type = Column(String(50))
    business_group = Column(String(100))
    status = Column(String(20), nullable=False, server_default=text("'active'"))
    remark = Column(Text)
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    site = relationship("Site", back_populates="servers")
    os_version = relationship("OsVersion", back_populates="servers")
    instances = relationship("DbInstance", back_populates="server")


class Cluster(DbopsAssetBase):
    __tablename__ = "cluster"

    id = Column(BigInteger, primary_key=True)
    cluster_code = Column(String(100), nullable=False, unique=True)
    cluster_name = Column(String(200), nullable=False)
    business_system_id = Column(BigInteger, ForeignKey("business_system.id"), nullable=False)
    db_type_id = Column(BigInteger, ForeignKey("db_type.id"), nullable=False)
    cluster_type = Column(String(50), nullable=False)
    ha_enabled = Column(Boolean, nullable=False, server_default=text("false"))
    status = Column(String(20), nullable=False, server_default=text("'active'"))
    remark = Column(Text)
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    business_system = relationship("BusinessSystem", back_populates="clusters")
    db_type = relationship("DbType", back_populates="clusters")
    vips = relationship("ClusterVip", back_populates="cluster")
    instances = relationship("DbInstance", back_populates="cluster")


class ClusterVip(DbopsAssetBase):
    __tablename__ = "cluster_vip"

    id = Column(BigInteger, primary_key=True)
    cluster_id = Column(BigInteger, ForeignKey("cluster.id", ondelete="CASCADE"), nullable=False)
    vip_address = Column(Text, nullable=False)
    vip_type = Column(String(50))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    cluster = relationship("Cluster", back_populates="vips")

    __table_args__ = (
        UniqueConstraint("cluster_id", "vip_address", name="uq_cluster_vip"),
    )


class DbInstance(DbopsAssetBase):
    __tablename__ = "db_instance"

    id = Column(BigInteger, primary_key=True)
    instance_code = Column(String(100), nullable=False, unique=True)
    instance_name = Column(String(200), nullable=False)
    db_type_id = Column(BigInteger, ForeignKey("db_type.id"), nullable=False)
    db_version_id = Column(BigInteger, ForeignKey("db_version.id"))
    server_id = Column(BigInteger, ForeignKey("server.id"), nullable=False)
    cluster_id = Column(BigInteger, ForeignKey("cluster.id"), nullable=False)
    port = Column(Integer)
    service_name = Column(String(200))
    node_role = Column(String(50), nullable=False, server_default=text("'unknown'"))
    db_size_gb = Column(Numeric(12, 2))
    status = Column(String(20), nullable=False, server_default=text("'active'"))
    trust_status = Column(String(32), nullable=False, server_default=text("'unverified'"))
    reachability_status = Column(String(32), nullable=False, server_default=text("'unknown'"))
    last_seen_at = Column(DateTime)
    last_verify_at = Column(DateTime)
    verify_message = Column(Text)
    last_verify_run_id = Column(String(64))
    last_awx_job_id = Column(BigInteger)
    verify_detail = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    remark = Column(Text)
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    db_type = relationship("DbType", back_populates="instances")
    db_version = relationship("DbVersion", back_populates="instances")
    server = relationship("Server", back_populates="instances")
    cluster = relationship("Cluster", back_populates="instances")
    collector_runs = relationship("CollectorRun", back_populates="db_instance")
    collector_results = relationship("CollectorRunResult", back_populates="db_instance")

    __table_args__ = (
        UniqueConstraint("cluster_id", "server_id", "instance_name", "port", name="uq_instance_cluster_server_name_port"),
        CheckConstraint(
            "node_role IN ('primary','standby','single','member','unknown')",
            name="chk_node_role",
        ),
        CheckConstraint(
            "trust_status IN ('unverified', 'verified', 'missing', 'drifted')",
            name="chk_db_instance_trust_status",
        ),
        CheckConstraint(
            "reachability_status IN ('unknown', 'online', 'offline')",
            name="chk_db_instance_reachability_status",
        ),
        Index("idx_db_instance_trust_status", "trust_status"),
        Index("idx_db_instance_reachability_status", "reachability_status"),
        Index("idx_db_instance_last_verify_at", last_verify_at.desc()),
    )


class CollectorRun(DbopsAssetBase):
    __tablename__ = "collector_run"

    id = Column(BigInteger, primary_key=True)
    run_id = Column(String(64), nullable=False, unique=True)
    db_instance_id = Column(BigInteger, ForeignKey("db_instance.id"), nullable=False)
    job_type = Column(String(64), nullable=False, server_default=text("'ASSET_VERIFY_PORT'"))
    status = Column(String(32), nullable=False, server_default=text("'pending'"))
    awx_job_id = Column(BigInteger)
    awx_job_url = Column(Text)
    awx_job_template_id = Column(BigInteger)
    awx_job_template_name = Column(String(200))
    target_host = Column(String(255), nullable=False)
    target_port = Column(Integer, nullable=False)
    callback_url = Column(Text)
    requested_by = Column(String(100))
    request_payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    extra_vars = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    db_instance = relationship("DbInstance", back_populates="collector_runs")
    results = relationship("CollectorRunResult", back_populates="collector_run")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'launched', 'success', 'failed', 'callback_failed')",
            name="chk_collector_run_status",
        ),
        CheckConstraint(
            "target_port BETWEEN 1 AND 65535",
            name="chk_collector_run_target_port",
        ),
        Index("idx_collector_run_instance_time", "db_instance_id", created_at.desc()),
        Index("idx_collector_run_awx_job", "awx_job_id"),
        Index("idx_collector_run_status", "status"),
    )


class CollectorRunResult(DbopsAssetBase):
    __tablename__ = "collector_run_result"

    id = Column(BigInteger, primary_key=True)
    collector_run_id = Column(BigInteger, ForeignKey("collector_run.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String(64), nullable=False)
    db_instance_id = Column(BigInteger, ForeignKey("db_instance.id"), nullable=False)
    check_type = Column(String(64), nullable=False, server_default=text("'PORT_REACHABILITY'"))
    status = Column(String(32), nullable=False)
    port_reachable = Column(Boolean)
    target_host = Column(String(255), nullable=False)
    target_port = Column(Integer, nullable=False)
    error_message = Column(Text)
    awx_job_id = Column(BigInteger)
    checked_by = Column(String(50))
    checked_at = Column(DateTime)
    raw_result = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)

    collector_run = relationship("CollectorRun", back_populates="results")
    db_instance = relationship("DbInstance", back_populates="collector_results")

    __table_args__ = (
        UniqueConstraint("run_id", "check_type", name="uq_collector_run_result_run_check"),
        CheckConstraint(
            "status IN ('verified', 'missing', 'drifted')",
            name="chk_collector_run_result_status",
        ),
        CheckConstraint(
            "target_port BETWEEN 1 AND 65535",
            name="chk_collector_run_result_target_port",
        ),
        Index("idx_collector_run_result_instance_time", "db_instance_id", created_at.desc()),
    )


class TopologyRelation(DbopsAssetBase):
    __tablename__ = "topology_relation"

    id = Column(BigInteger, primary_key=True)
    cluster_id = Column(BigInteger, ForeignKey("cluster.id", ondelete="CASCADE"), nullable=False)
    source_instance_id = Column(BigInteger, ForeignKey("db_instance.id"))
    target_instance_id = Column(BigInteger, ForeignKey("db_instance.id"))
    relation_type = Column(String(50), nullable=False)
    sync_mode = Column(String(50))
    status = Column(String(50))
    lag_seconds = Column(Integer)
    remark = Column(Text)
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Tag(DbopsAssetBase):
    __tablename__ = "tag"

    id = Column(BigInteger, primary_key=True)
    tag_code = Column(String(100), nullable=False, unique=True)
    tag_name = Column(String(100), nullable=False)
    tag_type = Column(String(50))
    color = Column(String(30))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ResourceTag(DbopsAssetBase):
    __tablename__ = "resource_tag"

    id = Column(BigInteger, primary_key=True)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(BigInteger, nullable=False)
    tag_id = Column(BigInteger, ForeignKey("tag.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "tag_id", name="uq_resource_tag"),
    )


class BackupPolicy(DbopsAssetBase):
    __tablename__ = "backup_policy"

    id = Column(BigInteger, primary_key=True)
    policy_code = Column(String(100), nullable=False, unique=True)
    policy_name = Column(String(200), nullable=False)


class InstanceBackupPolicy(DbopsAssetBase):
    __tablename__ = "instance_backup_policy"

    id = Column(BigInteger, primary_key=True)
    instance_id = Column(BigInteger, ForeignKey("db_instance.id", ondelete="CASCADE"), nullable=False)
    policy_id = Column(BigInteger, ForeignKey("backup_policy.id"), nullable=False)


class InspectionItem(DbopsAssetBase):
    __tablename__ = "inspection_item"

    id = Column(BigInteger, primary_key=True)
    item_code = Column(String(100), nullable=False, unique=True)
    item_name = Column(String(200), nullable=False)


class InspectionTask(DbopsAssetBase):
    __tablename__ = "inspection_task"

    id = Column(BigInteger, primary_key=True)
    task_code = Column(String(100), nullable=False, unique=True)
    task_name = Column(String(200), nullable=False)


class InspectionResult(DbopsAssetBase):
    __tablename__ = "inspection_result"

    id = Column(BigInteger, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("inspection_task.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(BigInteger, ForeignKey("inspection_item.id"), nullable=False)


class BizScoreRule(DbopsAssetBase):
    __tablename__ = "biz_score_rule"

    id = Column(BigInteger, primary_key=True)
    rule_code = Column(String(100), nullable=False, unique=True)
    rule_name = Column(String(200), nullable=False)


class BizScoreResult(DbopsAssetBase):
    __tablename__ = "biz_score_result"

    id = Column(BigInteger, primary_key=True)
    business_system_id = Column(BigInteger, ForeignKey("business_system.id", ondelete="CASCADE"), nullable=False)


class BizScoreResultDetail(DbopsAssetBase):
    __tablename__ = "biz_score_result_detail"

    id = Column(BigInteger, primary_key=True)
    result_id = Column(BigInteger, ForeignKey("biz_score_result.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(BigInteger, ForeignKey("biz_score_rule.id"), nullable=False)


class StagingExcelImport(DbopsAssetBase):
    __tablename__ = "staging_excel_import"

    id = Column(BigInteger, primary_key=True)
    import_batch_id = Column(String(100))
    source_file_name = Column(String(300))
    row_no = Column(Integer)
    system_name = Column(Text)
    platform_category = Column(Text)
    service_scope = Column(Text)
    biz_level = Column(Text)
    business_unit = Column(Text)
    department = Column(Text)
    source_cluster_no = Column(Text)
    cluster_type = Column(Text)
    node_role = Column(Text)
    normalized_node_role = Column(Text)
    normalized_engine_role = Column(Text)
    instance_name = Column(Text)
    port = Column(Text)
    service_name = Column(Text)
    db_size_gb = Column(Text)
    db_type = Column(Text)
    normalized_db_type = Column(Text)
    db_version = Column(Text)
    db_patch = Column(Text)
    os_name = Column(Text)
    os_version = Column(Text)
    ip = Column(Text)
    hostname = Column(Text)
    server_type = Column(Text)
    cpu_cores = Column(Text)
    memory_gb = Column(Text)
    disk_gb = Column(Text)
    business_group = Column(Text)
    country = Column(Text)
    deploy_type = Column(Text)
    provider = Column(Text)
    factory_area = Column(Text)
    room_location = Column(Text)
    dns_name = Column(Text)
    vip = Column(Text)
    host_admin = Column(Text)
    host_admin_contact = Column(Text)
    os_admin = Column(Text)
    os_admin_contact = Column(Text)
    app_owner = Column(Text)
    app_owner_contact = Column(Text)
    business_manager = Column(Text)
    business_manager_contact = Column(Text)
    business_belong_manager = Column(Text)
    dba_owner = Column(Text)
    backup_type = Column(Text)
    local_backup_policy = Column(Text)
    backup_manage_policy = Column(Text)
    remote_backup_location = Column(Text)
    monitor_tag = Column(Text)
    mdr_tag = Column(Text)
    audit_tag = Column(Text)
    db_account = Column(Text)
    db_password_raw = Column(Text)
    os_oracle = Column(Text)
    os_oracle_password_raw = Column(Text)
    os_root = Column(Text)
    os_password_raw = Column(Text)
    raw_payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    imported_at = Column(DateTime, default=datetime.utcnow)


__all__ = [
    "DbopsAssetBase",
    "SystemGroup",
    "BusinessSystem",
    "Contact",
    "BusinessSystemContact",
    "AssetEventHistory",
    "Site",
    "OsVersion",
    "DbType",
    "DbVersion",
    "Server",
    "Cluster",
    "ClusterVip",
    "DbInstance",
    "CollectorRun",
    "CollectorRunResult",
    "TopologyRelation",
    "Tag",
    "ResourceTag",
    "BackupPolicy",
    "InstanceBackupPolicy",
    "InspectionItem",
    "InspectionTask",
    "InspectionResult",
    "BizScoreRule",
    "BizScoreResult",
    "BizScoreResultDetail",
    "StagingExcelImport",
]
