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
TRUNCATE package_version_snapshot, package_snapshot, version, package, snapshot;

-- 모든 스냅샷의 기준일. 다른 표가 전부 이 날짜를 참조한다.
INSERT INTO snapshot (snapshot_at) VALUES
  (DATE '2026-08-24'),
  (DATE '2026-08-31');

INSERT INTO package (package_id, name, repo_url) VALUES
  (1, 'react',    'https://github.com/facebook/react'),
  (2, 'lodash',   'https://github.com/lodash/lodash'),
  (3, 'left-pad', NULL);                                  -- repo_url 이 없는 경우

INSERT INTO version (package_id, version, published_at, ordinal, description, licenses, deprecated, dependency) VALUES
  (1, '18.3.1',  TIMESTAMP '2024-04-26 00:00:00', 1, 'React is a JavaScript library for building user interfaces.', '["MIT"]',   NULL, '{"loose-envify": "^1.1.0"}'),
  (1, '19.0.0',  TIMESTAMP '2024-12-05 00:00:00', 2, 'React is a JavaScript library for building user interfaces.', '["MIT"]',   NULL, '{}'),
  (2, '4.17.21', TIMESTAMP '2021-02-20 00:00:00', 1, 'Lodash modular utilities.',                                   '["MIT"]',   NULL, '{}'),
  -- deprecated 가 채워진 행을 하나 둔다. NULL 만 있으면 이 컬럼을 쓰는 코드가 검증되지 않는다.
  (3, '1.3.0',   TIMESTAMP '2018-05-17 00:00:00', 1, 'String left pad',                                             '["WTFPL"]', 'use String.prototype.padStart() instead', '{}');

INSERT INTO package_snapshot (package_id, snapshot_at, downloads, stars, open_issues) VALUES
  (1, DATE '2026-08-24', 25100000, 232000, 760),
  (1, DATE '2026-08-31', 25400000, 232400, 771),
  (2, DATE '2026-08-24', 48900000,  60100, 120),
  (2, DATE '2026-08-31', 49200000,  60150, 118),
  -- 두 기준일 사이에 downloads 가 줄어드는 행. 증가만 가정한 코드를 여기서 걸러 낸다.
  (3, DATE '2026-08-24',  2100000,   1100,  35),
  (3, DATE '2026-08-31',  2050000,   1100,  35);

INSERT INTO package_version_snapshot (package_id, version, snapshot_at, dependents_count) VALUES
  (1, '18.3.1',  DATE '2026-08-31', 18400),
  (1, '19.0.0',  DATE '2026-08-31',  4200),
  (2, '4.17.21', DATE '2026-08-31', 96500),
  (3, '1.3.0',   DATE '2026-08-31',   310);
