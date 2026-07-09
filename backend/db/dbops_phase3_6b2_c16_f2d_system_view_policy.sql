-- =============================================================================
-- Phase 3.6B2 C16-F2d — AI System View Policy（系统视图白名单）
-- 2026-07-09
--
-- 背景：
-- - 当前 SQL Preview 走 ai_sql_schema_snapshot.allowed_tables 白名单（采集自
--   业务表 + 模板层一刀切排除系统 schema）
-- - DBA 运维场景（查锁 / 查慢 SQL / 查 session）需要访问 §4.1 列出的 DBA 系统
--   视图（V$LOCK / sys.dm_exec_sessions / pg_stat_activity 等）
-- - 本表为 per-instance 显式白名单：默认 enable=false，DBA 显式开启后才允许
--   AI 在该 instance 上查询 policy.allowlist 列出的系统视图
--
-- 设计原则（plan §21.4 / commit handoff 2026-07-09）：
-- 1. 每个 instance 一行（UNIQUE instance_id）
-- 2. 默认 disable（enabled=false）→ 灰度开关，需 DBA 显式开启
-- 3. allowlist 显式列出允许访问的系统视图（与 §4.1 baseline 对齐）
-- 4. denylist 强于 allowlist（同名表 denylist 命中即拒，防御 §5 黑名单）
-- 5. policy_version 配套 §4.1 baseline；后续扩 §4.2 时升 v2 + 增量
--
-- 集成点（commit 2/3 实施）：
-- - ai_schema_snapshot_callback_service.py: snapshot 采集时若 policy 启用，
--   给 allowed_tables 追加 policy.allowlist（force-include）
-- - ai_sql_preview_service.py: Layer 3 AST 校验前加 is_allowed() 闸门
-- - ai_schema_context_service.py: policy 启用时 schema_context 合并
--
-- 回滚：dbops_phase3_6b2_c16_f2d_rollback.sql（DROP TABLE CASCADE）
-- =============================================================================

CREATE TABLE IF NOT EXISTS dbops.ai_system_view_policy (
    id              BIGSERIAL PRIMARY KEY,
    instance_id     BIGINT NOT NULL
                    REFERENCES dbops.db_instance(id) ON DELETE CASCADE,
    db_type_code    VARCHAR(32) NOT NULL,
    policy_version  VARCHAR(32) NOT NULL,
    -- allowlist 形如 ["DBA_OBJECTS", "V$LOCK", "sys.dm_tran_locks",
    --                "pg_catalog.pg_stat_activity"]；每个 dialect 命名规范
    -- 由前端 SystemViewPolicy.vue 渲染时按 db_type_code 过滤
    allowlist       JSONB NOT NULL,
    -- denylist 强于 allowlist；用于防御 §5 黑名单（如 sys.sql_logins 即使
    -- allowlist 误加，denylist 命中即拒）
    denylist        JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- 默认 false；DBA 显式 enable 后 AI 才能访问 allowlist
    enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by      UUID,
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 每个 instance 唯一（一个 instance 一条 policy 行）
    CONSTRAINT uq_ai_system_view_policy_instance UNIQUE (instance_id),

    -- db_type_code 枚举约束（与 C6 / C12 / C16-F3 对齐）
    CONSTRAINT chk_ai_system_view_policy_db_type
        CHECK (db_type_code IN ('POSTGRESQL', 'ORACLE', 'MSSQL')),

    -- allowlist 必须是 JSON 数组且非空
    CONSTRAINT chk_ai_system_view_policy_allowlist_nonempty
        CHECK (jsonb_typeof(allowlist) = 'array'
               AND jsonb_array_length(allowlist) > 0),

    -- denylist 必须是 JSON 数组
    CONSTRAINT chk_ai_system_view_policy_denylist_array
        CHECK (jsonb_typeof(denylist) = 'array')

    -- 元素 trim 非空校验改用 trigger（PG 不允许 CHECK 内 subquery）；
    -- 详见下方 tg_ai_system_view_policy_validate_elements
);

-- 元素级校验 trigger：allowlist / denylist 内每个 string 元素 trim 后非空
-- （PG CHECK 约束不允许 subquery；用 BEFORE INSERT OR UPDATE trigger 兜底）
CREATE OR REPLACE FUNCTION dbops.fn_ai_system_view_policy_validate_elements()
RETURNS TRIGGER AS $$
DECLARE
    elem text;
    list_json jsonb;
BEGIN
    -- 检查 allowlist / denylist 中是否含 trim 后为空的字符串
    FOR list_json IN
        SELECT allowlist FROM (SELECT NEW.allowlist AS allowlist) s
        UNION ALL
        SELECT denylist FROM (SELECT NEW.denylist AS denylist) s
    LOOP
        IF jsonb_typeof(list_json) = 'array' THEN
            FOR elem IN
                SELECT jsonb_array_elements_text(list_json)
            LOOP
                IF elem IS NULL OR length(trim(elem)) = 0 THEN
                    RAISE EXCEPTION 'ai_system_view_policy element must be non-empty string (after trim); got: %', elem;
                END IF;
            END LOOP;
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_ai_system_view_policy_validate_elements ON dbops.ai_system_view_policy;
CREATE TRIGGER tg_ai_system_view_policy_validate_elements
    BEFORE INSERT OR UPDATE ON dbops.ai_system_view_policy
    FOR EACH ROW EXECUTE FUNCTION dbops.fn_ai_system_view_policy_validate_elements();

-- 辅助索引：按 db_type_code 查询（批量种子 / 列表 API）
CREATE INDEX IF NOT EXISTS idx_ai_system_view_policy_db_type
    ON dbops.ai_system_view_policy(db_type_code);

-- 注释（PG 12+ 支持 COMMENT）
COMMENT ON TABLE dbops.ai_system_view_policy IS
    'AI Copilot 系统视图白名单（C16-F2d）。Per-instance 显式 allowlist，默认 disable，需 DBA 显式 enable。§4.1 baseline 70 项。';
COMMENT ON COLUMN dbops.ai_system_view_policy.policy_version IS
    '配套 §4.1 baseline 的版本号（如 2026-07-09-v1）。后续扩 §4.2 时升 v2 + 增量。';
COMMENT ON COLUMN dbops.ai_system_view_policy.allowlist IS
    'JSON 数组，元素为系统视图名（按 db_type 命名规范：Oracle 大写 / MSSQL 小写带 schema / PG 带 pg_catalog./information_schema. 前缀）';
COMMENT ON COLUMN dbops.ai_system_view_policy.denylist IS
    'JSON 数组，强于 allowlist；防御 §5 黑名单（如 sys.sql_logins）。';
COMMENT ON COLUMN dbops.ai_system_view_policy.enabled IS
    '灰度开关；默认 false，需 DBA 显式 enable 后 AI 才能访问 allowlist。';

-- 幂等：dev 库 / 多次跑不报错（IF NOT EXISTS 已保护）
