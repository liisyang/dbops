-- Phase 3.6 C16-5 Commit 6 — dev PG instance 965 (10.134.185.228) dbops_readonly 授权
-- Run as superuser: PGPASSWORD='root123' psql -h 10.134.185.228 -U postgres -d postgres -v ON_ERROR_STOP=1 -f /tmp/commit6_grant_readonly.sql
--
-- 关键事实（实测）:
--   PG 965 没有 dbops database 也没有 dbops schema（计划 §6 premise 错）
--   实际只有 benchdb / jemdb / postgres 3 个 DB
--   DB schema 分布:
--     benchdb.public: pgbench_*
--     benchdb.sbtest: benchuser 拥有，sysbench sbtest*
--     jemdb.public: 1 表
--     postgres.app:    app 拥有，1 表
--     postgres.oggadm: oggadm 拥有
--     postgres.public: 默认空
-- 现有 login: postgres / gdmms / benchuser / app / ogg_capture / oggadm
-- 既 readonly 角色 gdmms 用于 collector；本 commit 新增 dbops_readonly 用于 SQL Copilot end-user.
--
-- 设计：CONNECT 三个 DB（benchdb / jemdb / postgres）+ USAGE 全部用户 schema
--      + SELECT ALL TABLES IN 用户 schema + ALTER DEFAULT PRIVILEGES
--      （未来 postgres / benchuser 等 owner 新建表自动可读）

BEGIN;

-- (1) benchdb
\connect benchdb
GRANT CONNECT ON DATABASE benchdb TO dbops_readonly;
GRANT USAGE ON SCHEMA public, sbtest TO dbops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public  TO dbops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA sbtest  TO dbops_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dbops_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA sbtest GRANT SELECT ON TABLES TO dbops_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE benchuser IN SCHEMA sbtest
    GRANT SELECT ON TABLES TO dbops_readonly;

-- (2) jemdb
\connect jemdb
GRANT CONNECT ON DATABASE jemdb TO dbops_readonly;
GRANT USAGE ON SCHEMA public TO dbops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dbops_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dbops_readonly;

-- (3) postgres（自带 app / oggadm schema）
\connect postgres
GRANT CONNECT ON DATABASE postgres TO dbops_readonly;
GRANT USAGE ON SCHEMA public, app, oggadm TO dbops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public  TO dbops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA app     TO dbops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA oggadm  TO dbops_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dbops_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA app    GRANT SELECT ON TABLES TO dbops_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA oggadm GRANT SELECT ON TABLES TO dbops_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE app    IN SCHEMA app
    GRANT SELECT ON TABLES TO dbops_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE oggadm IN SCHEMA oggadm
    GRANT SELECT ON TABLES TO dbops_readonly;

COMMIT;
