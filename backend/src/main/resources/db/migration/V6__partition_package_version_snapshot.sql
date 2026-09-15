-- Convert the V1 package_version_snapshot table to a RANGE-partitioned table.
--
-- V1 through V5 are immutable.  This migration is deliberately conservative:
-- an ordinary table is replaced only when it is empty and has the expected V1
-- contract; an already partitioned table is validated and left untouched.
-- No CASCADE is used, so an unexpected dependency aborts the migration.

DO $migration$
DECLARE
    v_table              regclass := to_regclass('public.package_version_snapshot');
    v_relkind            "char";
    v_table_oid           oid;
    v_owner               name;
    v_acl                 aclitem[];
    v_table_comment       text;
    v_package_comment     text;
    v_version_comment     text;
    v_snapshot_comment    text;
    v_dependents_comment  text;
    v_constraint_count    integer;
    v_fk_count             integer;
    v_pk_count             integer;
    v_check_count          integer;
    v_index_count          integer;
    v_valid_index_count    integer;
    v_partstrat             "char";
    v_partattrs             int2vector;
    v_partnatts             integer;
    v_from_date             date;
    v_to_date               date;
    v_child                 record;
BEGIN
    IF v_table IS NULL THEN
        RAISE EXCEPTION
            'V6 requires public.package_version_snapshot from V1';
    END IF;

    -- Freeze the relation before inspecting emptiness and replacing it.  This
    -- prevents a concurrent writer from inserting between the checks and DROP.
    PERFORM set_config('lock_timeout', '5s', true);
    PERFORM set_config('DateStyle', 'ISO, YMD', true);
    LOCK TABLE public.package_version_snapshot IN ACCESS EXCLUSIVE MODE;

    SELECT c.oid, c.relkind, r.rolname, c.relacl,
           obj_description(c.oid, 'pg_class'),
           col_description(c.oid, 1),
           col_description(c.oid, 2),
           col_description(c.oid, 3),
           col_description(c.oid, 4)
      INTO v_table_oid, v_relkind, v_owner, v_acl, v_table_comment,
           v_package_comment, v_version_comment, v_snapshot_comment,
           v_dependents_comment
      FROM pg_class c
      JOIN pg_roles r ON r.oid = c.relowner
     WHERE c.oid = v_table;

    IF v_relkind NOT IN ('r', 'p') THEN
        RAISE EXCEPTION
            'V6 expected an ordinary or partitioned table, found relkind %',
            v_relkind;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid = v_table_oid AND
               (relpersistence <> 'p' OR relispartition)) THEN
        RAISE EXCEPTION 'V6 requires a permanent top-level table';
    END IF;

    -- The four-column contract is checked before either accepting or replacing
    -- the relation.  This also rejects extra columns and dropped columns.
    IF (SELECT count(*) FROM pg_attribute
         WHERE attrelid = v_table_oid AND attnum > 0 AND NOT attisdropped) <> 4
       OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = v_table_oid AND attnum > 0 AND attisdropped)
       OR EXISTS (
            SELECT 1
              FROM (VALUES
                    (1, 'package_id'::name, 'integer'::regtype, true,  false, -1, 0::oid, ''::char, ''::char),
                    (2, 'version'::name,    'character varying'::regtype, true, false, 104, 'default'::regcollation::oid, ''::char, ''::char),
                    (3, 'snapshot_at'::name,'date'::regtype, true,  false, -1, 0::oid, ''::char, ''::char),
                    (4, 'dependents_count'::name, 'integer'::regtype, true, true, -1, 0::oid, ''::char, ''::char)
                   ) expected(attnum, attname, atttypid, attnotnull, has_default, atttypmod, attcollation, attidentity, attgenerated)
              LEFT JOIN pg_attribute a
                ON a.attnum = expected.attnum
               AND a.attrelid = v_table_oid
               AND a.attnum > 0
               AND NOT a.attisdropped
              LEFT JOIN pg_attrdef d
                ON d.adrelid = a.attrelid
               AND d.adnum = a.attnum
             WHERE a.attnum IS NULL
                OR a.attname <> expected.attname
                OR a.atttypid <> expected.atttypid
                OR a.attnotnull <> expected.attnotnull
                OR a.atttypmod <> expected.atttypmod
                OR a.attcollation <> expected.attcollation
                OR a.attidentity <> expected.attidentity
                OR a.attgenerated <> expected.attgenerated
                OR (expected.has_default AND (
                       a.atthasdef IS NOT TRUE
                       OR pg_get_expr(d.adbin, d.adrelid) <> '0'::text
                    ))
                OR (NOT expected.has_default AND a.atthasdef)
       ) THEN
        RAISE EXCEPTION
            'V6 found an unexpected column, nullability, or default contract on %',
            v_table;
    END IF;

    SELECT count(*) FILTER (WHERE contype = 'p'),
           count(*) FILTER (WHERE contype = 'f'),
           count(*) FILTER (WHERE contype = 'c'),
           count(*)
      INTO v_pk_count, v_fk_count, v_check_count, v_constraint_count
      FROM pg_constraint
     WHERE conrelid = v_table_oid
       AND contype IN ('p', 'f', 'c', 'u', 'x');

    IF v_pk_count <> 1 OR v_fk_count <> 2
       OR v_check_count <> (CASE WHEN v_relkind = 'p' THEN 1 ELSE 0 END)
       OR v_constraint_count <> (CASE WHEN v_relkind = 'p' THEN 4 ELSE 3 END)
       OR EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conrelid = v_table_oid
               AND contype IN ('u', 'x')
       ) THEN
        RAISE EXCEPTION
            'V6 found unexpected primary key, foreign key, check, or unique constraints on %',
            v_table;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c JOIN pg_index i ON i.indexrelid = c.conindid
         WHERE c.conrelid = v_table_oid AND c.contype = 'p'
           AND c.conkey = ARRAY[1, 2, 3]::smallint[]
           AND NOT c.condeferrable AND NOT c.condeferred
           AND i.indisvalid AND i.indisready
    ) THEN
        RAISE EXCEPTION 'V6 requires PK (package_id, version, snapshot_at)';
    END IF;

    IF (SELECT count(*) FROM pg_constraint
         WHERE conrelid = v_table_oid AND contype = 'f'
           AND confrelid = 'public.version'::regclass
           AND conkey = ARRAY[1, 2]::smallint[]
           AND confkey = ARRAY[2, 1]::smallint[]
           AND convalidated AND NOT condeferrable AND NOT condeferred
           AND confupdtype = 'a' AND confdeltype = 'a' AND confmatchtype = 's') <> 1
       OR (SELECT count(*) FROM pg_constraint
         WHERE conrelid = v_table_oid AND contype = 'f'
           AND confrelid = 'public.snapshot'::regclass
           AND conkey = ARRAY[3]::smallint[]
           AND confkey = ARRAY[1]::smallint[]
           AND convalidated AND NOT condeferrable AND NOT condeferred
           AND confupdtype = 'a' AND confdeltype = 'a' AND confmatchtype = 's') <> 1 THEN
        RAISE EXCEPTION 'V6 requires validated FKs to version and snapshot';
    END IF;

    IF v_relkind = 'p' THEN
        SELECT partstrat, partattrs, partnatts
          INTO v_partstrat, v_partattrs, v_partnatts
          FROM pg_partitioned_table
         WHERE partrelid = v_table_oid;
        IF v_partstrat <> 'r' OR v_partnatts <> 1
           OR v_partattrs::text <> '3' THEN
            RAISE EXCEPTION
                'V6 requires RANGE partitioning on the single snapshot_at column';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conrelid = v_table_oid AND contype = 'c'
               AND convalidated
               AND NOT connoinherit
               AND pg_get_expr(conbin, conrelid) = '(dependents_count >= 0)'
        ) THEN
            RAISE EXCEPTION 'V6 requires a validated non-negative dependents_count check';
        END IF;

        SELECT count(*),
               count(*) FILTER (
                   WHERE i.indisvalid AND i.indisready AND NOT i.indisunique AND i.indnatts = 2
                     AND i.indpred IS NULL AND i.indexprs IS NULL
                     AND i.indoption::text = '0 0'
                     AND am.amname = 'btree'
                     AND i.indkey::text = '1 3'
               )
          INTO v_index_count, v_valid_index_count
          FROM pg_index i
          JOIN pg_class ic ON ic.oid = i.indexrelid
          JOIN pg_am am ON am.oid = ic.relam
         WHERE i.indrelid = v_table_oid AND NOT i.indisprimary;
        IF v_index_count <> 1 OR v_valid_index_count <> 1 THEN
            RAISE EXCEPTION
                'V6 requires one valid (package_id, snapshot_at) index on %', v_table;
        END IF;

        -- A DEFAULT partition would overlap the date contract used by the
        -- loader.  PostgreSQL prevents overlapping bounds, but this explicit
        -- check also rejects an accidentally broad/default child.
        FOR v_child IN
            SELECT child.oid, child.relispartition, child.relkind,
                   pg_get_expr(child.relpartbound, child.oid, true) AS bound
              FROM pg_inherits i
              JOIN pg_class child ON child.oid = i.inhrelid
             WHERE i.inhparent = v_table_oid
        LOOP
            IF v_child.relispartition IS NOT TRUE
               OR v_child.relkind <> 'r'
               OR EXISTS (SELECT 1 FROM pg_partitioned_table WHERE partrelid = v_child.oid)
               OR v_child.bound !~ $re$^FOR VALUES FROM \('[0-9]{4}-[0-9]{2}-[0-9]{2}'\) TO \('[0-9]{4}-[0-9]{2}-[0-9]{2}'\)$re$ THEN
                RAISE EXCEPTION 'V6 found a child with an invalid RANGE boundary';
            END IF;
            v_from_date := substring(v_child.bound FROM $from$FROM \('([0-9]{4}-[0-9]{2}-[0-9]{2})'\) TO$from$)::date;
            v_to_date := substring(v_child.bound FROM $to$TO \('([0-9]{4}-[0-9]{2}-[0-9]{2})'\)$to$)::date;
            IF v_to_date <> v_from_date + 1 THEN
                RAISE EXCEPTION 'V6 found a child boundary that is not one day: %', v_child.bound;
            END IF;
        END LOOP;
        RETURN;
    END IF;

    -- V1's ordinary table must be empty before it is replaced.  Replacing a
    -- non-empty table would be an implicit destructive migration, so it fails.
    IF EXISTS (SELECT 1 FROM ONLY public.package_version_snapshot LIMIT 1) THEN
        RAISE EXCEPTION
            'V6 refuses to replace non-empty ordinary package_version_snapshot';
    END IF;

    -- Permit the V4 index or no index (V6 creates the required index), but
    -- reject unrelated indexes whose semantics would otherwise be lost.
    SELECT count(*),
           count(*) FILTER (
               WHERE i.indisvalid AND i.indisready AND NOT i.indisunique AND i.indnatts = 2
                 AND i.indpred IS NULL AND i.indexprs IS NULL
                 AND i.indoption::text = '0 0'
                 AND am.amname = 'btree'
                 AND i.indkey::text = '1 3'
           )
      INTO v_index_count, v_valid_index_count
      FROM pg_index i
      JOIN pg_class ic ON ic.oid = i.indexrelid
      JOIN pg_am am ON am.oid = ic.relam
     WHERE i.indrelid = v_table_oid AND NOT i.indisprimary;
    IF v_index_count > 1 OR v_valid_index_count <> v_index_count THEN
        RAISE EXCEPTION 'V6 found an unexpected index on %', v_table;
    END IF;

    IF v_acl IS NOT NULL
       OR EXISTS (SELECT 1 FROM pg_default_acl WHERE
                  defaclrole IN ((SELECT oid FROM pg_roles WHERE rolname = current_user),
                                 (SELECT oid FROM pg_roles WHERE rolname = v_owner))
                  AND defaclobjtype = 'r'
                  AND defaclnamespace IN (0, 'public'::regnamespace))
       OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = v_table_oid AND attacl IS NOT NULL)
       OR EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = v_table_oid AND NOT tgisinternal)
       OR EXISTS (SELECT 1 FROM pg_rewrite WHERE ev_class = v_table_oid)
       OR EXISTS (SELECT 1 FROM pg_class WHERE oid = v_table_oid
                                      AND (relrowsecurity OR relforcerowsecurity OR reloptions IS NOT NULL)) THEN
        RAISE EXCEPTION
            'V6 refuses to replace package_version_snapshot with custom ACL, trigger, rule, RLS, or reloptions';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE confrelid = v_table_oid
           AND conrelid <> v_table_oid
           AND contype = 'f'
    ) THEN
        RAISE EXCEPTION
            'V6 refuses to drop package_version_snapshot because another table references it';
    END IF;

    -- The relation is empty, so replacement is the only supported way to add
    -- PARTITION BY.  DROP TABLE is intentionally without CASCADE; any other
    -- dependency aborts the surrounding Flyway transaction.
    DROP TABLE public.package_version_snapshot;

    CREATE TABLE public.package_version_snapshot (
        package_id       INT NOT NULL,
        version          VARCHAR(100) NOT NULL,
        snapshot_at      DATE NOT NULL,
        dependents_count INT DEFAULT 0 NOT NULL,
        CONSTRAINT PK_PACKAGE_VERSION_SNAPSHOT
            PRIMARY KEY (package_id, version, snapshot_at),
        CONSTRAINT FK_VERSION_PACKAGE_VERSION_SNAPSHOT
            FOREIGN KEY (package_id, version)
            REFERENCES public.version (package_id, version),
        CONSTRAINT FK_SNAPSHOT_PACKAGE_VERSION_SNAPSHOT
            FOREIGN KEY (snapshot_at)
            REFERENCES public.snapshot (snapshot_at),
        CONSTRAINT CK_PACKAGE_VERSION_SNAPSHOT_DEPENDENTS_NONNEGATIVE
            CHECK (dependents_count >= 0)
    ) PARTITION BY RANGE (snapshot_at);

    CREATE INDEX idx_pvs_pkg_snapshot
        ON public.package_version_snapshot (package_id, snapshot_at);

    EXECUTE format('ALTER TABLE public.package_version_snapshot OWNER TO %I', v_owner);

    IF v_table_comment IS NOT NULL THEN
        EXECUTE format('COMMENT ON TABLE public.package_version_snapshot IS %L', v_table_comment);
    END IF;
    IF v_package_comment IS NOT NULL THEN
        EXECUTE format('COMMENT ON COLUMN public.package_version_snapshot.package_id IS %L', v_package_comment);
    END IF;
    IF v_version_comment IS NOT NULL THEN
        EXECUTE format('COMMENT ON COLUMN public.package_version_snapshot.version IS %L', v_version_comment);
    END IF;
    IF v_snapshot_comment IS NOT NULL THEN
        EXECUTE format('COMMENT ON COLUMN public.package_version_snapshot.snapshot_at IS %L', v_snapshot_comment);
    END IF;
    IF v_dependents_comment IS NOT NULL THEN
        EXECUTE format('COMMENT ON COLUMN public.package_version_snapshot.dependents_count IS %L', v_dependents_comment);
    END IF;

END
$migration$;
