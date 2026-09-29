-- 로컬 샘플 데이터. **명령으로 직접 적용한다.**
--
--   docker compose exec postgres psql -U postgres -d pickage -f seed/seed_sample.sql
--
-- 경로 앞에 `/` 를 붙이지 않는다. Git Bash 가 `/seed/...` 를 윈도우 경로로 바꿔 버려서
-- "No such file or directory" 가 난다. 컨테이너의 작업 디렉터리가 `/` 라 상대 경로로도
-- 같은 파일을 가리키고, 이렇게 쓰면 PowerShell 과 Git Bash 에서 같은 명령이 통한다.
--
-- Flyway 마이그레이션이 아니다. 일부러 아니다.
--
--   * 앱이 뜰 때 자동으로 돌면, 남이 이 파일을 고쳐 push 한 것을 내가 pull 한 순간
--     내 로컬 데이터가 말없이 사라진다. 지우는 시점은 사람이 정해야 한다.
--   * resources 밖에 있어서 jar 에 실리지 않는다. 운영에 들어갈 경로가 아예 없다 —
--     Flyway 의 locations 설정에 의존해서 막는 것보다 확실하다.
--   * 체크섬·적용 이력이 없다. "파일을 고쳤는데 기동이 막힌다" 류의 함정이 생기지 않는다.
--
-- 몇 번을 돌려도 결과가 같다. TRUNCATE 로 비우고 다시 넣으므로 이 파일이 곧 시드 상태다.
--
-- ⚠ 이 다섯 테이블은 이 파일이 소유한다. 직접 넣은 데이터를 여기 두지 말 것 —
--   이 명령을 돌리는 순간 사라진다. 살려야 하는 데이터는 다른 곳에 둘 것.
--
-- ⚠ 아래 숫자는 전부 지어낸 값이다. 실측이 아니다.
--   화면과 쿼리를 굴려 보기 위해 형태만 맞춘 데이터이므로 분석의 근거로 쓰지 말 것.

-- 다섯 테이블이 FK 로 묶여 있어 하나씩은 비울 수 없다. 한 번에 비운다.
-- CASCADE 를 쓰지 않는 이유: 나중에 추가된 테이블까지 말없이 같이 비워 버린다.
-- 여기 전부 적어 두면 새 테이블이 생겼을 때 이 파일이 에러로 알려 준다.
-- 2026-09-09: V2 에서 similar_package 가 생겨 목록에 추가했다.
-- 이 파일이 의도대로 동작한 사례다 — 빠져 있는 동안 TRUNCATE 가 FK 오류로 멈춰서
-- "새 테이블이 생겼다" 는 사실이 조용히 지나가지 않았다.
TRUNCATE community_snapshot, dependent_removal_reason, dependent_transition, migration_pair, package_env, similar_package, package_version_snapshot, package_snapshot, available_package, version, package;

-- ⚠ snapshot 만 TRUNCATE 가 아니라 DELETE 다 (2026-09-09, S15P21A506-289).
--
-- V3 가 etl_snapshot_reference.snapshot_at → snapshot 의 FK 를 만들었다. PostgreSQL 의
-- TRUNCATE 는 참조하는 테이블이 **비어 있어도** 같이 지정하지 않으면 거절한다. 목록에
-- etl_snapshot_reference 를 넣으면 시드가 파이프라인의 적재 이력을 지우게 되므로 넣지 않는다.
--
-- DELETE 는 참조가 실제로 있을 때만 FK 위반으로 실패한다. 즉 적재 이력이 있는 DB 에서
-- 이 시드는 조용히 덮어쓰지 않고 에러로 멈춘다.
DELETE FROM snapshot;

-- 모든 스냅샷의 기준일. 다른 표가 전부 이 날짜를 참조한다.
INSERT INTO snapshot (snapshot_at) VALUES
  (DATE '2026-08-24'),
  (DATE '2026-08-31');

INSERT INTO package (package_id, name, repo_url) VALUES
  (1, 'react',    'https://github.com/facebook/react'),
  (2, 'lodash',   'https://github.com/lodash/lodash'),
  (3, 'left-pad', NULL);                                  -- repo_url 이 없는 경우

-- dependency 는 pipeline/preprocessing/curated/transform.py 가 만드는 구조를 그대로 따른다.
--   json_object('dependencies', …, 'peerDependencies', …, 'optionalDependencies', …)
--
-- 의존성이 없는 버전도 세 키를 남기고 각각 {} 를 넣는다. 시드만 최상위에 평평하게 두면
-- dependency->'dependencies' 를 읽는 코드가 시드에서는 아무것도 못 찾고, 반대로 시드에
-- 맞춰 구현하면 실제 적재 데이터를 못 읽는다. 로컬에서 되는 것이 서버에서 안 되는 전형이다.
INSERT INTO version (package_id, version, published_at, ordinal, description, licenses, deprecated, dependency) VALUES
  (1, '18.3.1', TIMESTAMP '2024-04-26 00:00:00', 1,
   'React is a JavaScript library for building user interfaces.', '["MIT"]', NULL,
   '{"dependencies":{"loose-envify":"^1.1.0"},"peerDependencies":{},"optionalDependencies":{}}'),
  (1, '19.0.0', TIMESTAMP '2024-12-05 00:00:00', 2,
   'React is a JavaScript library for building user interfaces.', '["MIT"]', NULL,
   '{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}'),
  (2, '4.17.21', TIMESTAMP '2021-02-20 00:00:00', 1,
   'Lodash modular utilities.', '["MIT"]', NULL,
   '{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}'),
  -- deprecated 가 채워진 행을 하나 둔다. NULL 만 있으면 이 컬럼을 쓰는 코드가 검증되지 않는다.
  (3, '1.3.0', TIMESTAMP '2018-05-17 00:00:00', 1,
   'String left pad', '["WTFPL"]', 'use String.prototype.padStart() instead',
   '{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}');

INSERT INTO package_snapshot (package_id, snapshot_at, downloads, stars, open_issues) VALUES
  (1, DATE '2026-08-24', 25100000, 232000, 760),
  (1, DATE '2026-08-31', 25400000, 232400, 771),
  (2, DATE '2026-08-24', 48900000,  60100, 120),
  (2, DATE '2026-08-31', 49200000,  60150, 118),
  -- 두 기준일 사이에 downloads 가 줄어드는 행. 증가만 가정한 코드를 여기서 걸러 낸다.
  (3, DATE '2026-08-24',  2100000,   1100,  35),
  (3, DATE '2026-08-31',  2050000,   1100,  35);

-- 날짜별 파티션을 **먼저** 만든다.
--
-- V6 (2026-09-14) 가 package_version_snapshot 을 snapshot_at RANGE 파티션 부모로 바꿨다.
-- 새 DB 에는 자식이 하나도 없고, DEFAULT 파티션은 V6 계약이 금지한다. 그래서 이 블록이
-- 없으면 바로 아래 INSERT 가 통째로
--   ERROR: no partition of relation "package_version_snapshot" found for row
-- 로 멈춘다. 2026-09-15 CI 의 R14(공용 시드 전체 실행) 실패가 이것이었다.
--
-- "적재 작업이 [D, D+1) 자식을 준비한 뒤 넣는다" 는 규칙을 시드도 그대로 따르는 것이다 —
-- docs/worklogs/S15P21A506-341/14-constraint-names-and-partitions.md ④ 항목.
--
-- ⚠ 날짜 목록을 여기 적어 두지 않고 방금 넣은 snapshot 에서 읽는다. 두 곳에 적으면
--   스냅샷 날짜를 고칠 때 한쪽만 고쳐 놓고 "왜 또 파티션이 없다고 하지" 를 반복하게 된다.
--   package_version_snapshot.snapshot_at 은 snapshot 을 참조하는 FK 라 이 목록이 곧 전부다.
--
-- ⚠ 이름이 아니라 **실제 부모 연결(pg_inherits)과 범위** 로 있는지 확인한다. 운영에서
--   복원한 DB 는 같은 날짜의 자식을 vd193_reload_… 스키마에 다른 이름으로 갖고 있다.
--   이름만 보고 판단하면 이미 있는 날짜를 또 만들다가 범위 겹침으로 실패한다.
--
-- TRUNCATE 는 자식 파티션을 지우지 않는다. 그래서 두 번째 실행부터는 아무것도 만들지 않고,
-- 이 시드는 몇 번을 돌려도 결과가 같다는 성질을 유지한다.
DO $seed_partition$
DECLARE
    d date;
BEGIN
    -- 아래에서 파티션 경계 문자열을 날짜로 되읽으므로 표기를 고정한다 (V6 와 같은 이유).
    PERFORM set_config('DateStyle', 'ISO, YMD', true);

    FOR d IN SELECT snapshot_at FROM snapshot ORDER BY snapshot_at LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM pg_inherits i
              JOIN pg_class c ON c.oid = i.inhrelid
             WHERE i.inhparent = 'public.package_version_snapshot'::regclass
               AND d >= substring(pg_get_expr(c.relpartbound, c.oid, true)
                                  FROM $bound$FROM \('([0-9-]+)'\)$bound$)::date
               AND d <  substring(pg_get_expr(c.relpartbound, c.oid, true)
                                  FROM $bound$TO \('([0-9-]+)'\)$bound$)::date
        ) THEN
            EXECUTE format(
                'CREATE TABLE public.%I PARTITION OF public.package_version_snapshot '
                'FOR VALUES FROM (%L) TO (%L)',
                'package_version_snapshot_' || to_char(d, 'YYYYMMDD'), d, d + 1);
        END IF;
    END LOOP;
END
$seed_partition$;

INSERT INTO package_version_snapshot (package_id, version, snapshot_at, dependents_count) VALUES
  (1, '18.3.1',  DATE '2026-08-31', 18400),
  (1, '19.0.0',  DATE '2026-08-31',  4200),
  (2, '4.17.21', DATE '2026-08-31', 96500),
  (3, '1.3.0',   DATE '2026-08-31',   310);
