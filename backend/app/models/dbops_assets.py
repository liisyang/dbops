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
    collector_items = relationship("CollectorRunItem", back_populates="db_instance")

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
    target_scope = Column(String(32), nullable=False, server_default=text("'db_instance'"))
    db_instance_id = Column(BigInteger, ForeignKey("db_instance.id"))
    server_id = Column(BigInteger, ForeignKey("server.id"))
    job_type = Column(String(64), nullable=False, server_default=text("'ASSET_VERIFY_PORT'"))
    status = Column(String(32), nullable=False, server_default=text("'pending'"))
    item_count = Column(Integer, nullable=False, server_default=text("0"))
    awx_job_id = Column(BigInteger)
    awx_job_url = Column(Text)
    awx_job_template_id = Column(BigInteger)
    awx_job_template_name = Column(String(200))
    target_host = Column(String(255))
    target_port = Column(Integer)
    callback_url = Column(Text)
    requested_by = Column(String(100))
    request_payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    extra_vars = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    batch_run_id = Column(BigInteger, ForeignKey("collector_batch_run.id"))
    dispatch_run_id = Column(BigInteger, ForeignKey("collector_dispatch_run.id"))
    network_zone = Column(String(100))
    awx_instance_group = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    db_instance = relationship("DbInstance", back_populates="collector_runs")
    server = relationship("Server")
    items = relationship("CollectorRunItem", back_populates="collector_run", cascade="all, delete-orphan")
    results = relationship("CollectorRunResult", back_populates="collector_run")
    dispatch_run = relationship("CollectorDispatchRun", foreign_keys=[dispatch_run_id])
    batch_run = relationship("CollectorBatchRun", foreign_keys=[batch_run_id])

    __table_args__ = (
        CheckConstraint(
            "target_scope IN ('db_instance', 'server', 'mixed')",
            name="chk_collector_run_target_scope",
        ),
        CheckConstraint(
            "status IN ('pending', 'launched', 'running', 'success', 'partial_success', 'failed', 'callback_failed', 'timeout', 'canceled')",
            name="chk_collector_run_status",
        ),
        CheckConstraint(
            "item_count >= 0",
            name="chk_collector_run_item_count",
        ),
        CheckConstraint(
            "target_port BETWEEN 1 AND 65535",
            name="chk_collector_run_target_port",
        ),
        Index("idx_collector_run_instance_time", "db_instance_id", created_at.desc()),
        Index("idx_collector_run_server_time", "server_id", created_at.desc()),
        Index("idx_collector_run_awx_job", "awx_job_id"),
        Index("idx_collector_run_status", "status"),
        Index("idx_collector_run_target_scope", "target_scope"),
    )


class CollectorRunItem(DbopsAssetBase):
    __tablename__ = "collector_run_item"

    id = Column(BigInteger, primary_key=True)
    collector_run_id = Column(BigInteger, ForeignKey("collector_run.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String(64), nullable=False)
    item_key = Column(String(255), nullable=False)
    check_code = Column(String(100), nullable=False)
    target_scope = Column(String(32), nullable=False)
    server_id = Column(BigInteger, ForeignKey("server.id"))
    db_instance_id = Column(BigInteger, ForeignKey("db_instance.id"))
    target_host = Column(String(255), nullable=False)
    target_port = Column(Integer, nullable=False)
    protocol = Column(String(20), nullable=False, server_default=text("'tcp'"))
    endpoint_type = Column(String(100))
    port_source = Column(String(50))
    is_required = Column(Boolean, nullable=False, server_default=text("false"))
    timeout_seconds = Column(Integer, nullable=False, server_default=text("5"))
    status = Column(String(32), nullable=False, server_default=text("'pending'"))
    result_status = Column(String(32))
    result_message = Column(Text)
    raw_result = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    collector_run = relationship("CollectorRun", back_populates="items")
    server = relationship("Server")
    db_instance = relationship("DbInstance", back_populates="collector_items")
    result = relationship("CollectorRunResult", back_populates="collector_item", uselist=False)

    __table_args__ = (
        UniqueConstraint("collector_run_id", "item_key", name="uq_collector_run_item_key"),
        CheckConstraint(
            "target_scope IN ('server', 'db_instance')",
            name="chk_collector_run_item_target_scope",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed', 'skipped', 'timeout')",
            name="chk_collector_run_item_status",
        ),
        CheckConstraint(
            "result_status IS NULL OR result_status IN ('verified', 'missing', 'drifted', 'collected', 'failed')",
            name="chk_collector_run_item_result_status",
        ),
        CheckConstraint(
            "target_port BETWEEN 1 AND 65535",
            name="chk_collector_run_item_target_port",
        ),
        Index("idx_collector_run_item_run", "collector_run_id"),
        Index("idx_collector_run_item_scope_instance", "db_instance_id", created_at.desc()),
        Index("idx_collector_run_item_scope_server", "server_id", created_at.desc()),
        Index("idx_collector_run_item_status", "status"),
    )


class CollectorRunResult(DbopsAssetBase):
    __tablename__ = "collector_run_result"

    id = Column(BigInteger, primary_key=True)
    collector_run_id = Column(BigInteger, ForeignKey("collector_run.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String(64), nullable=False)
    collector_run_item_id = Column(BigInteger, ForeignKey("collector_run_item.id", ondelete="CASCADE"))
    item_key = Column(String(255), nullable=False)
    check_code = Column(String(100), nullable=False)
    target_scope = Column(String(32), nullable=False)
    db_instance_id = Column(BigInteger, ForeignKey("db_instance.id"))
    server_id = Column(BigInteger, ForeignKey("server.id"))
    check_type = Column(String(64))
    status = Column(String(32), nullable=False)
    port_reachable = Column(Boolean)
    target_host = Column(String(255), nullable=False)
    target_port = Column(Integer, nullable=False)
    endpoint_type = Column(String(100))
    protocol = Column(String(20))
    port_source = Column(String(50))
    is_required = Column(Boolean)
    error_message = Column(Text)
    result_message = Column(Text)
    awx_job_id = Column(BigInteger)
    checked_by = Column(String(50))
    checked_at = Column(DateTime)
    raw_result = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    collector_run = relationship("CollectorRun", back_populates="results")
    db_instance = relationship("DbInstance", back_populates="collector_results")
    server = relationship("Server")
    collector_item = relationship("CollectorRunItem", back_populates="result")

    __table_args__ = (
        UniqueConstraint("collector_run_id", "item_key", name="uq_collector_run_result_item"),
        UniqueConstraint("collector_run_item_id", name="uq_collector_run_result_item_id"),
        CheckConstraint(
            "status IN ('verified', 'missing', 'drifted', 'collected', 'failed')",
            name="chk_collector_run_result_status",
        ),
        CheckConstraint(
            "target_scope IN ('server', 'db_instance')",
            name="chk_collector_run_result_target_scope",
        ),
        CheckConstraint(
            "target_port BETWEEN 1 AND 65535",
            name="chk_collector_run_result_target_port",
        ),
        Index("idx_collector_run_result_instance_time", "db_instance_id", created_at.desc()),
        Index("idx_collector_run_result_server_time", "server_id", created_at.desc()),
    )


class CollectorCheckDefinition(DbopsAssetBase):
    __tablename__ = "collector_check_definition"

    id = Column(BigInteger, primary_key=True)
    check_code = Column(String(100), nullable=False, unique=True)
    check_name = Column(String(200), nullable=False)
    target_scope = Column(String(32), nullable=False)
    task_type = Column(String(32), nullable=False)
    db_type_code = Column(String(50))
    os_type_code = Column(String(50))
    awx_role = Column(String(100))
    default_timeout_seconds = Column(Integer, nullable=False, server_default=text("5"))
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    config = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "target_scope IN ('server', 'db_instance')",
            name="chk_collector_check_definition_target_scope",
        ),
        CheckConstraint(
            "task_type IN ('PORT_CHECK', 'DB_PORT_DISCOVERY', 'OS_DISCOVERY', 'DB_SQL_COLLECT')",
            name="chk_collector_check_definition_task_type",
        ),
    )


class PortProfile(DbopsAssetBase):
    __tablename__ = "port_profile"

    id = Column(BigInteger, primary_key=True)
    profile_code = Column(String(100), nullable=False, unique=True)
    target_scope = Column(String(50), nullable=False)
    endpoint_type = Column(String(100), nullable=False)
    db_type_code = Column(String(50))
    os_family = Column(String(50))
    protocol = Column(String(10), nullable=False, server_default=text("'tcp'"))
    default_port = Column(Integer, nullable=False)
    is_required = Column(Boolean, nullable=False, server_default=text("true"))
    is_candidate = Column(Boolean, nullable=False, server_default=text("true"))
    is_enabled = Column(Boolean, nullable=False, server_default=text("true"))
    priority = Column(Integer, nullable=False, server_default=text("100"))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "target_scope IN ('server', 'db_instance')",
            name="chk_port_profile_target_scope",
        ),
        CheckConstraint(
            "protocol IN ('tcp', 'udp')",
            name="chk_port_profile_protocol",
        ),
        CheckConstraint(
            "default_port BETWEEN 1 AND 65535",
            name="chk_port_profile_default_port",
        ),
        Index("idx_port_profile_scope", "target_scope"),
        Index("idx_port_profile_db_type", "db_type_code"),
        Index("idx_port_profile_os_family", "os_family"),
        Index("idx_port_profile_enabled", "is_enabled"),
        Index("idx_port_profile_endpoint_type", "endpoint_type"),
    )


class AssetEndpoint(DbopsAssetBase):
    __tablename__ = "asset_endpoint"

    id = Column(BigInteger, primary_key=True)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(BigInteger, nullable=False)
    endpoint_type = Column(String(32), nullable=False, server_default=text("'port'"))
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    protocol = Column(String(20), nullable=False, server_default=text("'tcp'"))
    source = Column(String(32), nullable=False, server_default=text("'cmdb'"))
    expected = Column(Boolean, nullable=False, server_default=text("true"))
    status = Column(String(32), nullable=False, server_default=text("'unknown'"))
    last_seen_at = Column(DateTime)
    last_verify_at = Column(DateTime)
    last_checked_at = Column(DateTime)
    last_run_id = Column(String(64))
    last_item_key = Column(String(255))
    last_message = Column(Text)
    reachable = Column(Boolean)
    port_source = Column(String(50))
    is_required = Column(Boolean, nullable=False, server_default=text("false"))
    evidence = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('server', 'db_instance')",
            name="chk_asset_endpoint_entity_type",
        ),
        CheckConstraint(
            "protocol IN ('tcp', 'udp')",
            name="chk_asset_endpoint_protocol",
        ),
        CheckConstraint(
            "source IN ('cmdb', 'discovered', 'manual')",
            name="chk_asset_endpoint_source",
        ),
        CheckConstraint(
            "status IN ('unknown', 'online', 'offline', 'drifted')",
            name="chk_asset_endpoint_status",
        ),
        CheckConstraint(
            "port BETWEEN 1 AND 65535",
            name="chk_asset_endpoint_port",
        ),
        UniqueConstraint(
            "entity_type", "entity_id", "endpoint_type", "host", "port", "source",
            name="uq_asset_endpoint_identity",
        ),
        Index("idx_asset_endpoint_entity_time", "entity_type", "entity_id", updated_at.desc()),
        Index("idx_asset_endpoint_status", "status"),
    )


class AssetChangeProposal(DbopsAssetBase):
    __tablename__ = "asset_change_proposal"

    id = Column(BigInteger, primary_key=True)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(BigInteger, nullable=False)
    change_type = Column(String(64), nullable=False)
    proposal_type = Column(String(64))
    field_path = Column(String(255))
    old_value = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    new_value = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    current_value = Column(JSONB)
    suggested_value = Column(JSONB)
    confidence = Column(String(20))
    evidence_run_id = Column(String(64))
    source_run_id = Column(String(64))
    source_item_key = Column(String(255))
    evidence = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status = Column(String(32), nullable=False, server_default=text("'pending'"))
    requested_by = Column(String(100))
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    applied_at = Column(DateTime)
    rejected_by = Column(String(100))
    rejected_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('server', 'db_instance')",
            name="chk_asset_change_proposal_entity_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'applied', 'canceled')",
            name="chk_asset_change_proposal_status",
        ),
        Index("idx_asset_change_proposal_entity_time", "entity_type", "entity_id", created_at.desc()),
        Index("idx_asset_change_proposal_status", "status"),
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


class CollectorBatchRun(DbopsAssetBase):
    __tablename__ = "collector_batch_run"

    id = Column(BigInteger, primary_key=True)
    batch_code = Column(String(100), nullable=False, unique=True)
    run_type = Column(String(50), nullable=False)
    target_scope = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, server_default=text("'pending'"))
    total_asset_count = Column(Integer, nullable=False, server_default=text("0"))
    total_item_count = Column(Integer, nullable=False, server_default=text("0"))
    success_item_count = Column(Integer, nullable=False, server_default=text("0"))
    failed_item_count = Column(Integer, nullable=False, server_default=text("0"))
    pending_item_count = Column(Integer, nullable=False, server_default=text("0"))
    running_item_count = Column(Integer, nullable=False, server_default=text("0"))
    skipped_item_count = Column(Integer, nullable=False, server_default=text("0"))
    dispatch_count = Column(Integer, nullable=False, server_default=text("0"))
    request_payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error_message = Column(Text)
    created_by = Column(String(100))
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    dispatches = relationship("CollectorDispatchRun", back_populates="batch_run", cascade="all, delete-orphan")
    collector_runs = relationship("CollectorRun", foreign_keys="CollectorRun.batch_run_id", overlaps="batch_run")

    __table_args__ = (
        CheckConstraint(
            "target_scope IN ('server', 'db_instance')",
            name="chk_collector_batch_run_scope",
        ),
        CheckConstraint(
            "status IN ('pending','dispatching','running','success','partial_success','failed','cancelled')",
            name="chk_collector_batch_run_status",
        ),
        Index("idx_collector_batch_run_status", "status"),
        Index("idx_collector_batch_run_type", "run_type"),
        Index("idx_collector_batch_run_created_at", created_at.desc()),
    )


class CollectorDispatchRun(DbopsAssetBase):
    __tablename__ = "collector_dispatch_run"

    id = Column(BigInteger, primary_key=True)
    dispatch_code = Column(String(100))
    batch_run_id = Column(BigInteger, ForeignKey("collector_batch_run.id", ondelete="CASCADE"), nullable=False)
    collector_run_id = Column(BigInteger, ForeignKey("collector_run.id"))
    network_zone = Column(String(100))
    awx_instance_group = Column(String(100))
    awx_job_template = Column(String(200), nullable=False, server_default=text("'JT_DBOPS_COLLECTOR_GENERIC'"))
    awx_job_template_id = Column(Integer)
    awx_job_id = Column(BigInteger)
    status = Column(String(30), nullable=False, server_default=text("'pending'"))
    item_count = Column(Integer, nullable=False, server_default=text("0"))
    success_item_count = Column(Integer, nullable=False, server_default=text("0"))
    failed_item_count = Column(Integer, nullable=False, server_default=text("0"))
    request_payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error_message = Column(Text)
    credential_strategy = Column(String(50))
    credential_profile_ids = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    credential_group_hash = Column(String(100))
    launched_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    batch_run = relationship("CollectorBatchRun", back_populates="dispatches")
    collector_run = relationship("CollectorRun", foreign_keys=[collector_run_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','launching','launched','running','success','partial_success','failed','cancelled')",
            name="chk_collector_dispatch_run_status",
        ),
        Index("idx_collector_dispatch_batch", "batch_run_id"),
        Index("idx_collector_dispatch_status", "status"),
        Index("idx_collector_dispatch_awx_job", "awx_job_id"),
        Index("idx_collector_dispatch_group", "network_zone", "awx_instance_group"),
    )


class CredentialProfile(DbopsAssetBase):
    """凭证引用 — 只存 AWX credential ID，永不存密码/私钥/Token"""
    __tablename__ = "credential_profile"

    id = Column(BigInteger, primary_key=True)
    profile_code = Column(String(100), nullable=False, unique=True)
    profile_name = Column(String(200), nullable=False)
    credential_type = Column(String(50), nullable=False)
    awx_credential_id = Column(BigInteger)
    awx_credential_name = Column(String(200))
    binding_role = Column(String(50), nullable=False)
    db_type_code = Column(String(50))
    os_family = Column(String(50))
    usage_scope = Column(String(50))
    network_zone = Column(String(100))
    environment = Column(String(50))
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_enabled = Column(Boolean, nullable=False, server_default=text("true"))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    bindings = relationship("CredentialBinding", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "credential_type IN ('ssh_password', 'ssh_key', 'db_password', 'winrm_password', 'api_token')",
            name="chk_credential_profile_type",
        ),
        CheckConstraint(
            "binding_role IN ('os_readonly', 'db_readonly', 'db_monitor', 'db_owner', 'db_admin')",
            name="chk_credential_profile_role",
        ),
        Index("idx_credential_profile_type", "credential_type"),
        Index("idx_credential_profile_role", "binding_role"),
        Index("idx_credential_profile_db_type", "db_type_code"),
        Index("idx_credential_profile_awx_id", "awx_credential_id"),
        Index("idx_credential_profile_enabled", "is_enabled"),
    )


class CredentialBinding(DbopsAssetBase):
    """凭证绑定 — profile → asset 映射，支持优先级解析"""
    __tablename__ = "credential_binding"

    id = Column(BigInteger, primary_key=True)
    binding_code = Column(String(100), nullable=False, unique=True)
    credential_profile_id = Column(BigInteger, ForeignKey("credential_profile.id", ondelete="CASCADE"), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(BigInteger)
    network_zone = Column(String(100))
    binding_role = Column(String(50))
    priority = Column(Integer, nullable=False, server_default=text("100"))
    is_enabled = Column(Boolean, nullable=False, server_default=text("true"))
    extra_attrs = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("CredentialProfile", back_populates="bindings")

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('server', 'db_instance', 'cluster', 'business_system', 'network_zone', 'global')",
            name="chk_credential_binding_target_type",
        ),
        CheckConstraint(
            "priority >= 1 AND priority <= 1000",
            name="chk_credential_binding_priority",
        ),
        Index("idx_credential_binding_profile", "credential_profile_id"),
        Index("idx_credential_binding_target", "target_type", "target_id"),
        Index("idx_credential_binding_zone", "network_zone"),
        Index("idx_credential_binding_enabled", "is_enabled"),
        Index("idx_credential_binding_priority", "priority"),
    )


class AssetFactSnapshot(DbopsAssetBase):
    """资产事实快照 — 一次采集事件一行"""
    __tablename__ = "asset_fact_snapshot"

    id = Column(BigInteger, primary_key=True)
    snapshot_id = Column(String(64), nullable=False, unique=True)
    target_type = Column(String(32), nullable=False)
    target_id = Column(BigInteger, nullable=False)
    source_run_id = Column(String(64))
    source_item_key = Column(String(255))
    check_code = Column(String(100))
    collected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    fact_count = Column(Integer, nullable=False, server_default=text("0"))
    raw_payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime, default=datetime.utcnow)

    values = relationship("AssetFactValue", back_populates="snapshot", cascade="all, delete-orphan")
    drifts = relationship("AssetDriftRecord", back_populates="snapshot", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('server', 'db_instance')",
            name="chk_asset_fact_snapshot_target_type",
        ),
        Index("idx_fact_snapshot_target_time", "target_type", "target_id", collected_at.desc()),
        Index("idx_fact_snapshot_source_run", "source_run_id"),
        Index("idx_fact_snapshot_check_code", "check_code"),
        Index("idx_fact_snapshot_collected_at", collected_at.desc()),
    )


class AssetFactValue(DbopsAssetBase):
    """单个事实键值 — FK → snapshot"""
    __tablename__ = "asset_fact_value"

    id = Column(BigInteger, primary_key=True)
    snapshot_id = Column(BigInteger, ForeignKey("asset_fact_snapshot.id", ondelete="CASCADE"), nullable=False)
    fact_key = Column(String(255), nullable=False)
    fact_value = Column(JSONB)
    fact_type = Column(String(50), nullable=False, server_default=text("'string'"))
    collected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    snapshot = relationship("AssetFactSnapshot", back_populates="values")

    __table_args__ = (
        UniqueConstraint("snapshot_id", "fact_key", name="uq_asset_fact_value_snapshot_key"),
        CheckConstraint(
            "fact_type IN ('string', 'integer', 'float', 'boolean', 'json')",
            name="chk_asset_fact_value_type",
        ),
        Index("idx_fact_value_snapshot", "snapshot_id"),
        Index("idx_fact_value_key", "fact_key"),
    )


class AssetDriftRecord(DbopsAssetBase):
    """漂移检测记录 — 事实 vs 正式资产字段偏差"""
    __tablename__ = "asset_drift_record"

    id = Column(BigInteger, primary_key=True)
    drift_code = Column(String(100), nullable=False, unique=True)
    snapshot_id = Column(BigInteger, ForeignKey("asset_fact_snapshot.id", ondelete="CASCADE"), nullable=False)
    target_type = Column(String(32), nullable=False)
    target_id = Column(BigInteger, nullable=False)
    fact_key = Column(String(255), nullable=False)
    expected_value = Column(JSONB)
    actual_value = Column(JSONB)
    drift_type = Column(String(50), nullable=False, server_default=text("'mismatch'"))
    severity = Column(String(50), nullable=False, server_default=text("'warning'"))
    proposal_id = Column(BigInteger, ForeignKey("asset_change_proposal.id", ondelete="SET NULL"))
    is_resolved = Column(Boolean, nullable=False, server_default=text("false"))
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    snapshot = relationship("AssetFactSnapshot", back_populates="drifts")
    proposal = relationship("AssetChangeProposal", foreign_keys=[proposal_id])

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('server', 'db_instance')",
            name="chk_asset_drift_record_target_type",
        ),
        CheckConstraint(
            "drift_type IN ('mismatch', 'missing', 'extra')",
            name="chk_asset_drift_record_drift_type",
        ),
        CheckConstraint(
            "severity IN ('critical', 'warning', 'info')",
            name="chk_asset_drift_record_severity",
        ),
        Index("idx_asset_drift_target_time", "target_type", "target_id", created_at.desc()),
        Index("idx_asset_drift_snapshot", "snapshot_id"),
        Index("idx_asset_drift_proposal", "proposal_id"),
        Index("idx_asset_drift_resolved", "is_resolved"),
        Index("idx_asset_drift_severity", "severity"),
    )


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
    "CollectorBatchRun",
    "CollectorDispatchRun",
    "CollectorRun",
    "CollectorRunItem",
    "CollectorRunResult",
    "CollectorCheckDefinition",
    "PortProfile",
    "AssetEndpoint",
    "AssetChangeProposal",
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
    "CredentialProfile",
    "CredentialBinding",
    "AssetFactSnapshot",
    "AssetFactValue",
    "AssetDriftRecord",
]
