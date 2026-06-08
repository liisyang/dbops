BEGIN;
SET search_path TO dbops, public;

CREATE TEMP TABLE tmp_keep_chain AS
SELECT
    i.id AS instance_id,
    i.db_type_id,
    i.db_version_id,
    i.server_id,
    i.cluster_id,
    s.site_id,
    s.os_version_id,
    c.business_system_id
FROM dbops.db_instance i
JOIN dbops.server s ON s.id = i.server_id
JOIN dbops.cluster c ON c.id = i.cluster_id
WHERE i.id = 961;

-- 说明：
-- 1. 保留 961 这条测试资产及其必要依赖链。
-- 2. 保留导入/下拉依赖的基础字典和枚举：system_group、db_type、db_version、site、os_version、contact、backup_policy、inspection_item、biz_score_rule。
-- 3. 仅清理其他资产、运行记录、关系和历史数据。

DELETE FROM dbops.asset_event_history
WHERE NOT (
    (asset_type = 'db_instance' AND asset_id = (SELECT instance_id FROM tmp_keep_chain)) OR
    (asset_type = 'server' AND asset_id = (SELECT server_id FROM tmp_keep_chain)) OR
    (asset_type = 'cluster' AND asset_id = (SELECT cluster_id FROM tmp_keep_chain)) OR
    (asset_type = 'business_system' AND asset_id = (SELECT business_system_id FROM tmp_keep_chain))
);

DELETE FROM dbops.collector_run_result
WHERE db_instance_id <> (SELECT instance_id FROM tmp_keep_chain);

DELETE FROM dbops.collector_run
WHERE db_instance_id <> (SELECT instance_id FROM tmp_keep_chain);

DELETE FROM dbops.topology_relation
WHERE cluster_id <> (SELECT cluster_id FROM tmp_keep_chain)
   OR source_instance_id IS DISTINCT FROM (SELECT instance_id FROM tmp_keep_chain)
   OR target_instance_id IS DISTINCT FROM (SELECT instance_id FROM tmp_keep_chain);

DELETE FROM dbops.resource_tag
WHERE NOT (
    (resource_type = 'db_instance' AND resource_id = (SELECT instance_id FROM tmp_keep_chain)) OR
    (resource_type = 'server' AND resource_id = (SELECT server_id FROM tmp_keep_chain)) OR
    (resource_type = 'cluster' AND resource_id = (SELECT cluster_id FROM tmp_keep_chain)) OR
    (resource_type = 'business_system' AND resource_id = (SELECT business_system_id FROM tmp_keep_chain))
);

DELETE FROM dbops.instance_backup_policy
WHERE instance_id <> (SELECT instance_id FROM tmp_keep_chain);

DELETE FROM dbops.biz_score_result_detail
WHERE result_id NOT IN (
    SELECT id
    FROM dbops.biz_score_result
    WHERE business_system_id = (SELECT business_system_id FROM tmp_keep_chain)
);

DELETE FROM dbops.biz_score_result
WHERE business_system_id <> (SELECT business_system_id FROM tmp_keep_chain);

DELETE FROM dbops.inspection_result
WHERE NOT (
    (target_type = 'db_instance' AND target_id = (SELECT instance_id FROM tmp_keep_chain)) OR
    (target_type = 'server' AND target_id = (SELECT server_id FROM tmp_keep_chain)) OR
    (target_type = 'cluster' AND target_id = (SELECT cluster_id FROM tmp_keep_chain)) OR
    (target_type = 'business_system' AND target_id = (SELECT business_system_id FROM tmp_keep_chain))
);

DELETE FROM dbops.business_system_contact
WHERE business_system_id <> (SELECT business_system_id FROM tmp_keep_chain);

DELETE FROM dbops.cluster_vip
WHERE cluster_id <> (SELECT cluster_id FROM tmp_keep_chain);

DELETE FROM dbops.db_instance
WHERE id <> (SELECT instance_id FROM tmp_keep_chain);

DELETE FROM dbops.cluster
WHERE id <> (SELECT cluster_id FROM tmp_keep_chain);

DELETE FROM dbops.server
WHERE id <> (SELECT server_id FROM tmp_keep_chain);

DELETE FROM dbops.business_system
WHERE id <> (SELECT business_system_id FROM tmp_keep_chain);

COMMIT;
