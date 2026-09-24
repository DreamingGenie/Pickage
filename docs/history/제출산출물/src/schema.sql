-- public 스키마의 테이블(파티션 자식 제외)을 ERD 생성기 입력 JSON 한 덩어리로 뽑는다.
-- refresh_inputs.sh 가 Flyway 를 막 적용한 빈 DB 에서 실행한다.
SELECT json_agg(t ORDER BY t.table) FROM (
  SELECT c.relname AS table,
         c.relkind::text AS kind,
         obj_description(c.oid) AS comment,
         (SELECT json_agg(json_build_object(
                   'name', a.attname,
                   'type', format_type(a.atttypid, a.atttypmod),
                   'notnull', a.attnotnull,
                   'default', pg_get_expr(ad.adbin, ad.adrelid),
                   'comment', col_description(c.oid, a.attnum)) ORDER BY a.attnum)
            FROM pg_attribute a
            LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
           WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped) AS columns,
         (SELECT json_agg(json_build_object('name', conname, 'type', contype, 'def', pg_get_constraintdef(oid)))
            FROM pg_constraint WHERE conrelid = c.oid) AS constraints,
         (SELECT json_agg(json_build_object('name', i.relname, 'def', pg_get_indexdef(i.oid)))
            FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
           WHERE x.indrelid = c.oid AND NOT x.indisprimary) AS indexes,
         pg_get_partkeydef(c.oid) AS partkey,
         (SELECT count(*) FROM pg_inherits WHERE inhparent = c.oid) AS partitions
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
     AND c.relname <> 'flyway_schema_history'
) t;
