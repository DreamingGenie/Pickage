-- Run after restoring all post-data and applying Flyway V6.
-- Catalog checks only: this does not replace row counts, data comparison or API checks.
DO $validate$
DECLARE
    node record;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_partitioned_table
                   WHERE partrelid = 'public.package_version_snapshot'::regclass
                   AND partstrat = 'r' AND partnatts = 1 AND partattrs::text = '3') THEN
        RAISE EXCEPTION 'Expected RANGE(snapshot_at) parent';
    END IF;
    FOR node IN SELECT relid FROM pg_partition_tree('public.package_version_snapshot') LOOP
        IF (SELECT count(*) FROM pg_attribute WHERE attrelid = node.relid AND attnum > 0 AND NOT attisdropped) <> 4
           OR EXISTS (SELECT 1 FROM pg_attribute a JOIN pg_attribute p ON p.attnum = a.attnum
                      LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
                      LEFT JOIN pg_attrdef pd ON pd.adrelid = p.attrelid AND pd.adnum = p.attnum
                      WHERE a.attrelid = node.relid AND p.attrelid = 'public.package_version_snapshot'::regclass
                        AND a.attnum > 0 AND NOT a.attisdropped AND
                        (a.attname <> p.attname OR a.atttypid <> p.atttypid OR a.atttypmod <> p.atttypmod
                         OR a.attnotnull <> p.attnotnull OR a.attcollation <> p.attcollation
                         OR pg_get_expr(ad.adbin,ad.adrelid) IS DISTINCT FROM pg_get_expr(pd.adbin,pd.adrelid))) THEN
            RAISE EXCEPTION 'Child column/default contract differs: %', node.relid;
        END IF;
        IF (SELECT count(*) FROM pg_constraint WHERE conrelid = node.relid AND contype = 'p') <> 1
           OR (SELECT count(*) FROM pg_constraint WHERE conrelid = node.relid AND contype = 'f') <> 2
           OR EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = node.relid AND NOT convalidated)
           OR (SELECT count(*) FROM pg_index WHERE indrelid = node.relid) <> 2
           OR EXISTS (SELECT 1 FROM pg_index WHERE indrelid = node.relid AND (NOT indisvalid OR NOT indisready)) THEN
            RAISE EXCEPTION 'Invalid or missing child constraints/indexes: %', node.relid;
        END IF;
        IF NOT has_table_privilege(node.relid, 'SELECT') THEN
            RAISE EXCEPTION 'Current role cannot query partition: %', node.relid;
        END IF;
    END LOOP;
END $validate$;
SELECT json_build_object('structural_checks', 'PASS', 'data_verified', false,
                        'leaf_partitions', (SELECT count(*) FROM pg_partition_tree('public.package_version_snapshot') WHERE isleaf));
