-- ============================================================================
-- Inspection Reports Refactor v5.1 — DDL Migration
-- Branch: feature/phase-3.5-db-readonly-sql-exec
-- Plan:  .claude/plans/inspection-reports-refactor-2026-06-25.md
-- ============================================================================
-- IMPORTANT: Run this ENTIRE script inside a SINGLE PostgreSQL transaction.
-- Do NOT DROP then COMMIT before CREATE.
--
-- Usage:
--   psql "$DATABASE_URL" -f backend/db/dbops_inspection_v5_1.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- Phase 1: DROP existing inspection tables (child → parent order, NO CASCADE)
-- ============================================================================

DROP TABLE IF EXISTS dbops.inspection_result;
DROP TABLE IF EXISTS dbops.inspection_instance_report;
DROP TABLE IF EXISTS dbops.inspection_report;
DROP TABLE IF EXISTS dbops.inspection_task_item;
DROP TABLE IF EXISTS dbops.inspection_task_target;
DROP TABLE IF EXISTS dbops.inspection_schedule;
DROP TABLE IF EXISTS dbops.inspection_task;
DROP TABLE IF EXISTS dbops.inspection_item;

-- ============================================================================
-- Phase 2: CREATE new inspection tables (v5.1 schema)
-- ============================================================================

-- --------------------------------------------------------------------------
-- 2.1 inspection_item
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_item (
    id              BIGSERIAL PRIMARY KEY,
    item_code       VARCHAR(100) NOT NULL,
    item_name       VARCHAR(200) NOT NULL,
    check_code      VARCHAR(100) NOT NULL,
    executor_type   VARCHAR(32),
    target_scope    VARCHAR(32) NOT NULL DEFAULT 'db_instance',
    db_type_code    VARCHAR(32),
    category        VARCHAR(50),
    item_kind       VARCHAR(32) NOT NULL DEFAULT 'state',
    evaluator_type  VARCHAR(32) NOT NULL DEFAULT 'none',
    severity        VARCHAR(20) NOT NULL DEFAULT 'warning',
    weight          INTEGER NOT NULL DEFAULT 10,
    rule_version    VARCHAR(20),
    rule_config     JSONB NOT NULL DEFAULT '{}'::jsonb,
    applicability   JSONB,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    description     TEXT,
    sql_hash        VARCHAR(64),
    rule_hash       VARCHAR(64),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_inspection_item_code UNIQUE (item_code),
    CONSTRAINT chk_inspection_item_target_scope CHECK (target_scope IN ('server', 'db_instance')),
    CONSTRAINT chk_inspection_item_kind CHECK (item_kind IN ('information', 'metric', 'state', 'count', 'composite')),
    CONSTRAINT chk_inspection_item_evaluator CHECK (evaluator_type IN ('none', 'range', 'equals', 'not_equals', 'in', 'not_in', 'boolean', 'status_column')),
    CONSTRAINT chk_inspection_item_severity CHECK (severity IN ('info', 'warning', 'critical'))
);

CREATE INDEX idx_inspection_item_enabled ON dbops.inspection_item (enabled);
CREATE INDEX idx_inspection_item_check_code ON dbops.inspection_item (check_code);
CREATE INDEX idx_inspection_item_db_type ON dbops.inspection_item (db_type_code);
CREATE INDEX idx_inspection_item_category ON dbops.inspection_item (category);

-- --------------------------------------------------------------------------
-- 2.2 inspection_schedule
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_schedule (
    id              BIGSERIAL PRIMARY KEY,
    schedule_code   VARCHAR(100) NOT NULL,
    schedule_name   VARCHAR(200) NOT NULL,
    cron_expr       VARCHAR(100) NOT NULL,
    timezone        VARCHAR(50) NOT NULL DEFAULT 'Asia/Shanghai',
    is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at     TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,
    last_task_id    BIGINT,
    options         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by      VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_inspection_schedule_code UNIQUE (schedule_code)
);

CREATE INDEX idx_inspection_schedule_enabled ON dbops.inspection_schedule (is_enabled);
CREATE INDEX idx_inspection_schedule_next_run ON dbops.inspection_schedule (next_run_at DESC);

-- --------------------------------------------------------------------------
-- 2.3 inspection_task
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_task (
    id              BIGSERIAL PRIMARY KEY,
    task_code       VARCHAR(100) NOT NULL,
    task_name       VARCHAR(200) NOT NULL,
    schedule_id     BIGINT,
    batch_run_id    BIGINT,
    run_type        VARCHAR(50) NOT NULL DEFAULT 'inspection',
    target_scope    VARCHAR(32) NOT NULL DEFAULT 'db_instance',
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
    check_codes     JSONB NOT NULL DEFAULT '[]'::jsonb,
    item_codes      JSONB NOT NULL DEFAULT '[]'::jsonb,
    asset_ids       JSONB NOT NULL DEFAULT '[]'::jsonb,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by      VARCHAR(100),
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_inspection_task_code UNIQUE (task_code),
    CONSTRAINT chk_inspection_task_target_scope CHECK (target_scope IN ('server', 'db_instance')),
    CONSTRAINT chk_inspection_task_status CHECK (status IN ('pending', 'running', 'success', 'partial_success', 'failed', 'cancelled'))
);

CREATE INDEX idx_inspection_task_status_created ON dbops.inspection_task (status, created_at DESC);
CREATE INDEX idx_inspection_task_batch_run ON dbops.inspection_task (batch_run_id);
CREATE INDEX idx_inspection_task_created_at ON dbops.inspection_task (created_at DESC);

-- --------------------------------------------------------------------------
-- 2.4 inspection_task_item — task-level item snapshot
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_task_item (
    id                      BIGSERIAL PRIMARY KEY,
    task_id                 BIGINT NOT NULL,
    inspection_item_id      BIGINT,
    item_code               VARCHAR(100) NOT NULL,
    item_name               VARCHAR(200) NOT NULL,
    check_code              VARCHAR(100) NOT NULL,
    executor_type           VARCHAR(32),
    target_scope            VARCHAR(32) NOT NULL,
    db_type_code            VARCHAR(32),
    category                VARCHAR(50),
    item_kind               VARCHAR(32) NOT NULL,
    evaluator_type          VARCHAR(32) NOT NULL,
    severity                VARCHAR(20) NOT NULL DEFAULT 'warning',
    weight                  INTEGER NOT NULL DEFAULT 10,
    rule_version            VARCHAR(20),
    rule_config_snapshot    JSONB NOT NULL DEFAULT '{}'::jsonb,
    applicability_snapshot  JSONB,
    enabled_snapshot        BOOLEAN NOT NULL DEFAULT TRUE,
    description_snapshot    TEXT,
    sql_hash                VARCHAR(64),
    rule_hash               VARCHAR(64),
    check_order             INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_task_item UNIQUE (task_id, item_code),
    CONSTRAINT fk_task_item_task FOREIGN KEY (task_id) REFERENCES dbops.inspection_task (id) ON DELETE CASCADE,
    CONSTRAINT fk_task_item_inspection_item FOREIGN KEY (inspection_item_id) REFERENCES dbops.inspection_item (id) ON DELETE SET NULL,
    CONSTRAINT chk_task_item_kind CHECK (item_kind IN ('information', 'metric', 'state', 'count', 'composite')),
    CONSTRAINT chk_task_item_evaluator CHECK (evaluator_type IN ('none', 'range', 'equals', 'not_equals', 'in', 'not_in', 'boolean', 'status_column')),
    CONSTRAINT chk_task_item_severity CHECK (severity IN ('info', 'warning', 'critical'))
);

CREATE INDEX idx_task_item_task ON dbops.inspection_task_item (task_id, check_order, id);

-- --------------------------------------------------------------------------
-- 2.5 inspection_task_target — target snapshot with dual state machine
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_task_target (
    id                          BIGSERIAL PRIMARY KEY,
    task_id                     BIGINT NOT NULL,
    target_type                 VARCHAR(32) NOT NULL,
    target_id                   BIGINT NOT NULL,
    target_name_snapshot        VARCHAR(200),
    host_snapshot               VARCHAR(100),
    port_snapshot               INTEGER,
    db_type_code_snapshot       VARCHAR(32),
    business_system_snapshot    VARCHAR(200),
    site_snapshot               VARCHAR(200),
    asset_snapshot              JSONB DEFAULT '{}'::jsonb,
    dispatch_status             VARCHAR(20) NOT NULL DEFAULT 'pending',
    skip_code                   VARCHAR(50),
    skip_reason                 VARCHAR(500),
    execution_status            VARCHAR(20) NOT NULL DEFAULT 'pending',
    collector_run_id            BIGINT,
    attempt_no                  INTEGER NOT NULL DEFAULT 1,
    started_at                  TIMESTAMPTZ,
    finished_at                 TIMESTAMPTZ,
    last_callback_at            TIMESTAMPTZ,
    error_code                  VARCHAR(50),
    error_message               TEXT,
    created_at                  TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_task_target UNIQUE (task_id, target_type, target_id),
    CONSTRAINT fk_task_target_task FOREIGN KEY (task_id) REFERENCES dbops.inspection_task (id) ON DELETE CASCADE,
    CONSTRAINT chk_task_target_type CHECK (target_type IN ('server', 'db_instance')),
    CONSTRAINT chk_dispatch_status CHECK (dispatch_status IN ('pending', 'dispatched', 'dispatch_failed', 'skipped')),
    CONSTRAINT chk_execution_status CHECK (execution_status IN ('pending', 'running', 'success', 'partial_success', 'failed', 'cancelled')),
    CONSTRAINT chk_skip_code CHECK (skip_code IN ('NOT_APPLICABLE', 'POLICY_EXCLUDED', 'ASSET_DISABLED', 'NO_CREDENTIAL', 'USER_CANCELLED', 'DISPATCH_REJECTED', 'UNKNOWN'))
);

CREATE INDEX idx_task_target_task_execution ON dbops.inspection_task_target (task_id, execution_status);
CREATE INDEX idx_task_target_filter_db_type ON dbops.inspection_task_target (task_id, db_type_code_snapshot);
CREATE INDEX idx_task_target_filter_business ON dbops.inspection_task_target (task_id, business_system_snapshot);
CREATE INDEX idx_task_target_filter_site ON dbops.inspection_task_target (task_id, site_snapshot);

-- --------------------------------------------------------------------------
-- 2.6 inspection_result — one row = task_item × task_target
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_result (
    id                      BIGSERIAL PRIMARY KEY,
    task_id                 BIGINT NOT NULL,
    task_item_id            BIGINT NOT NULL,
    task_target_id          BIGINT NOT NULL,
    collector_run_id        BIGINT,
    collector_run_item_id   BIGINT,
    target_type             VARCHAR(32) NOT NULL,
    target_id               BIGINT NOT NULL,
    result_code             VARCHAR(100) NOT NULL,
    execution_status        VARCHAR(32) NOT NULL DEFAULT 'success',
    evaluation_status       VARCHAR(32) NOT NULL DEFAULT 'not_evaluated',
    message                 TEXT,
    evidence                JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempt_no              INTEGER NOT NULL DEFAULT 1,
    received_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_result UNIQUE (task_id, task_item_id, task_target_id),
    CONSTRAINT fk_result_task FOREIGN KEY (task_id) REFERENCES dbops.inspection_task (id) ON DELETE CASCADE,
    CONSTRAINT fk_result_task_item FOREIGN KEY (task_item_id) REFERENCES dbops.inspection_task_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_result_task_target FOREIGN KEY (task_target_id) REFERENCES dbops.inspection_task_target (id) ON DELETE CASCADE,
    CONSTRAINT chk_result_target_type CHECK (target_type IN ('server', 'db_instance')),
    CONSTRAINT chk_execution_status_result CHECK (execution_status IN ('success', 'failed', 'timeout', 'skipped', 'permission_denied', 'connection_failed', 'parse_failed')),
    CONSTRAINT chk_evaluation_status CHECK (evaluation_status IN ('normal', 'warning', 'critical', 'unknown', 'not_evaluated')),
    CONSTRAINT chk_attempt_no_ge_0 CHECK (attempt_no >= 0)
);

CREATE INDEX idx_result_task_target ON dbops.inspection_result (task_id, task_target_id);
CREATE INDEX idx_result_task_item ON dbops.inspection_result (task_id, task_item_id);
CREATE INDEX idx_result_abnormal ON dbops.inspection_result (task_id, evaluation_status, task_target_id)
    WHERE evaluation_status IN ('warning', 'critical', 'unknown');

-- --------------------------------------------------------------------------
-- 2.7 inspection_report — overall report (1:1 with task)
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_report (
    id                      BIGSERIAL PRIMARY KEY,
    report_code             VARCHAR(100) NOT NULL,
    task_id                 BIGINT NOT NULL,
    report_status           VARCHAR(32) NOT NULL DEFAULT 'generating',
    health_level            VARCHAR(32),
    health_score            NUMERIC(5,2),
    total_target_count      INTEGER NOT NULL DEFAULT 0,
    healthy_count           INTEGER NOT NULL DEFAULT 0,
    warning_count           INTEGER NOT NULL DEFAULT 0,
    critical_count          INTEGER NOT NULL DEFAULT 0,
    unknown_count           INTEGER NOT NULL DEFAULT 0,
    not_assessed_count      INTEGER NOT NULL DEFAULT 0,
    normal_item_count       INTEGER NOT NULL DEFAULT 0,
    warning_item_count      INTEGER NOT NULL DEFAULT 0,
    critical_item_count     INTEGER NOT NULL DEFAULT 0,
    unknown_item_count      INTEGER NOT NULL DEFAULT 0,
    collection_failed_count INTEGER NOT NULL DEFAULT 0,
    missing_result_count    INTEGER NOT NULL DEFAULT 0,
    summary                 JSONB DEFAULT '{}'::jsonb,
    rule_engine_version     VARCHAR(50),
    source_data_hash        VARCHAR(64),
    source_result_count     INTEGER NOT NULL DEFAULT 0,
    generated_reason        VARCHAR(32) NOT NULL DEFAULT 'auto',
    generated_by            VARCHAR(100),
    generated_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_report_code UNIQUE (report_code),
    CONSTRAINT uq_report_task UNIQUE (task_id),
    CONSTRAINT fk_report_task FOREIGN KEY (task_id) REFERENCES dbops.inspection_task (id) ON DELETE CASCADE,
    CONSTRAINT chk_report_status CHECK (report_status IN ('generating', 'ready', 'partial', 'failed')),
    CONSTRAINT chk_health_level CHECK (health_level IN ('healthy', 'warning', 'critical', 'unknown', 'not_assessed')),
    CONSTRAINT chk_generated_reason CHECK (generated_reason IN ('auto', 'manual', 'regenerate'))
);

CREATE INDEX idx_report_status_generated ON dbops.inspection_report (report_status, generated_at DESC);

-- --------------------------------------------------------------------------
-- 2.8 inspection_instance_report — per-instance report (N:1 report)
-- --------------------------------------------------------------------------

CREATE TABLE dbops.inspection_instance_report (
    id                      BIGSERIAL PRIMARY KEY,
    report_id               BIGINT NOT NULL,
    task_id                 BIGINT NOT NULL,
    task_target_id          BIGINT NOT NULL,
    target_type             VARCHAR(32) NOT NULL,
    target_id               BIGINT NOT NULL,
    health_level            VARCHAR(32),
    health_score            NUMERIC(5,2),
    normal_count            INTEGER NOT NULL DEFAULT 0,
    warning_count           INTEGER NOT NULL DEFAULT 0,
    critical_count          INTEGER NOT NULL DEFAULT 0,
    unknown_count           INTEGER NOT NULL DEFAULT 0,
    not_evaluated_count     INTEGER NOT NULL DEFAULT 0,
    collection_failed_count INTEGER NOT NULL DEFAULT 0,
    missing_result_count    INTEGER NOT NULL DEFAULT 0,
    summary                 JSONB DEFAULT '{}'::jsonb,
    generated_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_instance_report UNIQUE (report_id, task_target_id),
    CONSTRAINT fk_instance_report_report FOREIGN KEY (report_id) REFERENCES dbops.inspection_report (id) ON DELETE CASCADE,
    CONSTRAINT fk_instance_report_task FOREIGN KEY (task_id) REFERENCES dbops.inspection_task (id) ON DELETE CASCADE,
    CONSTRAINT chk_instance_target_type CHECK (target_type IN ('server', 'db_instance')),
    CONSTRAINT chk_instance_health_level CHECK (health_level IN ('healthy', 'warning', 'critical', 'unknown', 'not_assessed'))
);

CREATE INDEX idx_instance_report_report_health ON dbops.inspection_instance_report (report_id, health_level, health_score);

-- ============================================================================
-- Phase 3: Seed inspection items (Oracle P0 × 5 + SQL Server P0 × 5)
-- ============================================================================

INSERT INTO dbops.inspection_item (item_code, item_name, check_code, executor_type, target_scope, db_type_code, category, item_kind, evaluator_type, severity, weight, rule_version, rule_config, description) VALUES
('ORA_VERSION_INFO', 'Oracle 版本/实例信息', 'DB_BASIC_FACT_COLLECTION', 'db_fact', 'db_instance', 'ORACLE', 'info', 'information', 'none', 'info', 1, '1.0.0',
 '{"schema_version":1,"item_kind":"information","category":"info","evaluator":{"type":"none"},"max_rows":1,"empty_result_policy":"unknown"}',
 '采集 Oracle 实例版本、启动时间、数据库角色等基础信息'),

('ORA_DATABASE_OPEN_MODE', 'Oracle 数据库打开模式', 'DB_ROLE_FACT_COLLECTION', 'db_fact', 'db_instance', 'ORACLE', 'state', 'composite', 'status_column', 'critical', 15, '1.0.0',
 '{"schema_version":1,"item_kind":"composite","category":"state","evaluator":{"type":"status_column","status_column":"result_status","severity_column":"severity","message_column":"message"},"multiple_rows":{"policy":"first","aggregate":null},"empty_result_policy":"unknown"}',
 '检查 Oracle 数据库角色与打开模式是否正常'),

('ORA_TABLESPACE_USAGE', 'Oracle 表空间使用率', 'DB_FACT_COLLECTION', 'db_fact', 'db_instance', 'ORACLE', 'capacity', 'metric', 'range', 'warning', 10, '1.0.0',
 '{"schema_version":1,"item_kind":"metric","category":"capacity","evaluator":{"type":"range","warning":{"gte":80},"critical":{"gte":90}},"value_selector":{"column":"used_pct"},"multiple_rows":{"policy":"each","aggregate":null},"empty_result_policy":"unknown","null_value_policy":"unknown","unit":"%","message_template":"{tablespace_name} 表空间使用率为 {used_pct}%"}',
 '检查永久表空间使用率'),

('ORA_SESSION_USAGE', 'Oracle 会话使用率', 'DB_FACT_COLLECTION', 'db_fact', 'db_instance', 'ORACLE', 'capacity', 'metric', 'range', 'warning', 10, '1.0.0',
 '{"schema_version":1,"item_kind":"metric","category":"capacity","evaluator":{"type":"range","warning":{"gte":80},"critical":{"gte":90}},"value_selector":{"column":"used_pct"},"multiple_rows":{"policy":"first","aggregate":null},"empty_result_policy":"unknown","null_value_policy":"unknown","unit":"%","message_template":"会话使用率为 {used_pct}%"}',
 '检查 Oracle 会话资源使用率'),

('ORA_BLOCKING_SESSION', 'Oracle 阻塞会话', 'DB_FACT_COLLECTION', 'db_fact', 'db_instance', 'ORACLE', 'performance', 'composite', 'status_column', 'critical', 10, '1.0.0',
 '{"schema_version":1,"item_kind":"composite","category":"performance","evaluator":{"type":"status_column","status_column":"result_status","severity_column":"severity","message_column":"message"},"multiple_rows":{"policy":"each","aggregate":null},"empty_result_policy":"normal","max_rows":200}',
 '检查 Oracle 阻塞会话'),

('MSSQL_VERSION_INFO', 'SQL Server 版本/实例信息', 'DB_BASIC_FACT_COLLECTION', 'db_fact', 'db_instance', 'SQLSERVER', 'info', 'information', 'none', 'info', 1, '1.0.0',
 '{"schema_version":1,"item_kind":"information","category":"info","evaluator":{"type":"none"},"max_rows":1,"empty_result_policy":"unknown"}',
 '采集 SQL Server 版本、启动时间等基础信息'),

('MSSQL_DATABASE_STATE', 'SQL Server 数据库状态', 'DB_ROLE_FACT_COLLECTION', 'db_fact', 'db_instance', 'SQLSERVER', 'state', 'composite', 'status_column', 'critical', 15, '1.0.0',
 '{"schema_version":1,"item_kind":"composite","category":"state","evaluator":{"type":"status_column","status_column":"result_status","severity_column":"severity","message_column":"message"},"multiple_rows":{"policy":"each","aggregate":null},"empty_result_policy":"unknown"}',
 '检查 SQL Server 用户数据库状态'),

('MSSQL_DATA_FILE_USAGE', 'SQL Server 数据文件使用率', 'DB_FACT_COLLECTION', 'db_fact', 'db_instance', 'SQLSERVER', 'capacity', 'metric', 'range', 'warning', 10, '1.0.0',
 '{"schema_version":1,"item_kind":"metric","category":"capacity","evaluator":{"type":"range","warning":{"gte":80},"critical":{"gte":90}},"value_selector":{"column":"used_pct"},"multiple_rows":{"policy":"each","aggregate":null},"empty_result_policy":"unknown","null_value_policy":"unknown","unit":"%","message_template":"{logical_file_name} 数据文件使用率为 {used_pct}%"}',
 '检查当前数据库数据文件使用率'),

('MSSQL_LOG_USAGE', 'SQL Server 日志使用率', 'DB_FACT_COLLECTION', 'db_fact', 'db_instance', 'SQLSERVER', 'capacity', 'metric', 'range', 'warning', 10, '1.0.0',
 '{"schema_version":1,"item_kind":"metric","category":"capacity","evaluator":{"type":"range","warning":{"gte":70},"critical":{"gte":90}},"value_selector":{"column":"used_pct"},"multiple_rows":{"policy":"first","aggregate":null},"empty_result_policy":"unknown","unit":"%","message_template":"日志使用率为 {used_pct}%"}',
 '检查当前数据库日志使用率'),

('MSSQL_BLOCKING_REQUEST', 'SQL Server 阻塞请求', 'DB_FACT_COLLECTION', 'db_fact', 'db_instance', 'SQLSERVER', 'performance', 'composite', 'status_column', 'critical', 10, '1.0.0',
 '{"schema_version":1,"item_kind":"composite","category":"performance","evaluator":{"type":"status_column","status_column":"result_status","severity_column":"severity","message_column":"message"},"multiple_rows":{"policy":"each","aggregate":null},"empty_result_policy":"normal","max_rows":200}',
 '检查 SQL Server 阻塞请求');

COMMIT;
