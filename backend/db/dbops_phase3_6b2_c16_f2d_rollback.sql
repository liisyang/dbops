-- C16-F2d 回滚：DROP ai_system_view_policy
-- 注意：CASCADE 会级联删除（如有 FK 引用）

DROP TABLE IF EXISTS dbops.ai_system_view_policy CASCADE;
