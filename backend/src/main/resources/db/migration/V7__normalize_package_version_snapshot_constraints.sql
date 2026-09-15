-- V1-V6 remain immutable. V6 accepts equivalent restored constraints whose
-- names differ from the names in a freshly migrated database. Normalize the
-- parent names by definition, without rebuilding constraints or rewriting rows.
-- Inherited CHECK names follow the parent; child PK/FK names are not a contract.
--
-- A fresh database still has no date partitions. The data-update job must
-- prepare/validate each [D, D+1) child before inserting rows for D; see
-- docs/worklogs/S15P21A506-341/14-constraint-names-and-partitions.md.

DO $normalize$
DECLARE
    parent_oid oid := 'public.package_version_snapshot'::regclass;
    expected record;
    actual record;
    matches oid[];
    constraint_oids oid[] := ARRAY[]::oid[];
    target_names text[] := ARRAY[]::text[];
    position integer;
    conflicting_index oid;
BEGIN
    PERFORM set_config('lock_timeout', '5s', true);
    LOCK TABLE public.package_version_snapshot IN ACCESS EXCLUSIVE MODE;

    IF NOT EXISTS (
        SELECT 1 FROM pg_partitioned_table p JOIN pg_attribute a
          ON a.attrelid = p.partrelid AND a.attname = 'snapshot_at'
         WHERE p.partrelid = parent_oid AND p.partstrat = 'r'
           AND p.partnatts = 1 AND p.partattrs::text = a.attnum::text
    ) THEN
        RAISE EXCEPTION 'V7 requires the V6 RANGE(snapshot_at) parent';
    END IF;

    IF (SELECT count(*) FROM pg_constraint WHERE conrelid = parent_oid) <> 4 THEN
        RAISE EXCEPTION 'V7 requires exactly one PK, two FKs and one CHECK';
    END IF;

    -- Resolve and validate every target before renaming any of them. Names alone
    -- cannot identify a constraint: a known name may hide an unexpected definition.
    FOR expected IN
        SELECT * FROM (VALUES
            ('p', 'pk_package_version_snapshot',
             ARRAY['package_id','version','snapshot_at'], NULL::regclass, NULL::text[]),
            ('f', 'fk_version_package_version_snapshot',
             ARRAY['package_id','version'], 'public.version'::regclass, ARRAY['package_id','version']),
            ('f', 'fk_snapshot_package_version_snapshot',
             ARRAY['snapshot_at'], 'public.snapshot'::regclass, ARRAY['snapshot_at']),
            ('c', 'ck_package_version_snapshot_dependents_nonnegative',
             ARRAY['dependents_count'], NULL::regclass, NULL::text[])
        ) AS contracts(kind, target_name, key_names, referenced_table, referenced_names)
    LOOP
        SELECT array_agg(c.oid) INTO matches
          FROM pg_constraint c
         WHERE c.conrelid = parent_oid AND c.contype::text = expected.kind
           AND c.convalidated AND NOT c.condeferrable AND NOT c.condeferred
           AND c.conparentid = 0
           AND ARRAY(
               SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY k(num, ord)
               JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num
               WHERE NOT a.attisdropped ORDER BY k.ord
           ) = expected.key_names
           AND (expected.kind <> 'f' OR (
               c.confrelid = expected.referenced_table
               AND c.confupdtype = 'a' AND c.confdeltype = 'a' AND c.confmatchtype = 's'
               AND ARRAY(
                   SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY k(num, ord)
                   JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.num
                   WHERE NOT a.attisdropped ORDER BY k.ord
               ) = expected.referenced_names
           ))
           AND (expected.kind <> 'c' OR (
               NOT c.connoinherit AND pg_get_expr(c.conbin, c.conrelid) = '(dependents_count >= 0)'
           ))
           AND (expected.kind <> 'p' OR EXISTS (
               SELECT 1 FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid
               JOIN pg_am am ON am.oid = ic.relam
               WHERE i.indexrelid = c.conindid AND i.indrelid = parent_oid
                 AND i.indisprimary AND i.indisunique AND i.indisvalid AND i.indisready
                 AND i.indimmediate AND i.indnkeyatts = 3 AND i.indnatts = 3
                 AND i.indpred IS NULL AND i.indexprs IS NULL AND am.amname = 'btree'
           ));

        IF coalesce(cardinality(matches), 0) <> 1 THEN
            RAISE EXCEPTION 'V7 missing, ambiguous or invalid constraint for %', expected.target_name;
        END IF;
        SELECT oid, conname, conindid INTO actual FROM pg_constraint WHERE oid = matches[1];
        IF EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = parent_oid AND conname = expected.target_name
                     AND oid <> actual.oid) THEN
            RAISE EXCEPTION 'V7 constraint name collision: %', expected.target_name;
        END IF;
        IF expected.kind = 'p' THEN
            conflicting_index := to_regclass(format('public.%I', expected.target_name));
            IF conflicting_index IS NOT NULL AND conflicting_index <> actual.conindid THEN
                RAISE EXCEPTION 'V7 index/relation name collision: %', expected.target_name;
            END IF;
        END IF;
        constraint_oids := array_append(constraint_oids, actual.oid);
        target_names := array_append(target_names, expected.target_name);
    END LOOP;

    FOR position IN 1..cardinality(constraint_oids) LOOP
        SELECT conname INTO actual FROM pg_constraint WHERE oid = constraint_oids[position];
        IF actual.conname <> target_names[position] THEN
            EXECUTE format('ALTER TABLE public.package_version_snapshot RENAME CONSTRAINT %I TO %I',
                           actual.conname, target_names[position]);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE oid = constraint_oids[position]
                         AND conname = target_names[position] AND convalidated) THEN
            RAISE EXCEPTION 'V7 renamed constraint verification failed: %', target_names[position];
        END IF;
    END LOOP;
END
$normalize$;
