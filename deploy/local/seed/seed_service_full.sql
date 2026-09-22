-- 목업 구동용 시드 — 메인 서비스 6개 테이블.
--
--   docker compose exec postgres psql -U postgres -d pickage -f seed/seed_service_full.sql
--
-- 경로 앞에 `/` 를 붙이지 않는다. Git Bash 가 `/seed/...` 를 윈도우 경로로 바꿔 버려서
-- "No such file or directory" 가 난다. 컨테이너의 작업 디렉터리가 `/` 라 상대 경로로도
-- 같은 파일을 가리키고, 이렇게 쓰면 PowerShell 과 Git Bash 에서 같은 명령이 통한다.
--
-- ⚠ 숫자는 전부 지어낸 값이다. 실측이 아니라 화면과 쿼리를 굴려 보려고 형태만 맞춘 것이므로
--   분석의 근거로 쓰지 말 것. 패키지 이름만 실제 npm 에서 가져왔다.
--
-- ⚠ `seed_sample.sql` · `seed_mock_parity.sql` 과 **같이 쓸 수 없다.** 셋 다 TRUNCATE 로
--   시작하므로 나중에 돌린 쪽만 남는다. 무엇을 보려는지에 따라 하나를 고른다
--   (deploy/local/README.md 의 표).
--
-- 채우는 것은 **메인 서비스 6개 테이블뿐이다.** 적재 추적(etl_load_execution ·
-- etl_load_attempt · etl_dataset_current · etl_snapshot_reference)은 파이프라인이 쓰고 읽는
-- 로깅 계열이라 손대지 않는다. 여기서 지어낸 실행 이력을 넣으면 적재기가 "이미 게시된 입력"
-- 으로 오인할 수 있다.
--
--
-- ## 패키지는 두 갈래다
--
--   * 카탈로그 34개 — 실제 npm 이름. 지표 곡선을 하나씩 정해 두었다. **화면을 보는 용도.**
--   * 채움    288개 — `접두사 + 접미사` 로 만든 이름. **검색창을 채우는 용도.**
--
-- 값은 한 줄씩 적지 않고 계수만 싣고 generate_series 로 만든다. 리터럴로 적으면
-- 322 × 130 = 41,860 행이라 파일이 수 MB 로 불어나고, 값 하나를 고치려 해도 어디를 고쳐야
-- 하는지 알 수 없다. 전부 정수 연산이라 어느 환경에서 돌려도 같은 숫자가 나온다.
--
--
-- ## 일부러 심어 둔 경계 사례
--
-- 목업이 "잘 되는 데이터" 로만 차 있으면, 화면이 실제 데이터에서 처음 깨진다.
--
--   left-pad        repo_url 이 NULL → stars·open_issues 도 NULL ("미확인" 으로 떠야 한다)
--   left-pad        licenses 가 배열이 아니라 JSON 문자열 → 개요 SQL 의 json_typeof 가드
--   node-fetch      최근 3주 downloads 가 NULL → "0회" 가 아니라 "집계 중" 이어야 한다
--   request         최신 버전이 deprecated · downloads 가 계속 줄어든다 · stars 증감이 음수
--   moment          downloads 가 줄어든다
--   rolldown        최근 12주에만 스냅샷이 있다 (신규 패키지 → 시리즈 길이가 다르다)
--   consola         package·version 은 있는데 스냅샷이 하나도 없다 (빈 시리즈)
--   koa · lodash    문자열로 정렬하면 최신 버전이 틀린다 (2.9.0 > 2.15.3 · 4.17.9 > 4.17.21)
--   string_decoder  이름에 `_` 가 있다 (검색의 LIKE ESCAPE 가 없으면 다른 이름까지 걸린다)
--   @hapi/hapi      스코프 이름 (`@` 와 `/` 가 이름 규칙·URL 인코딩을 통과해야 한다)
--
-- 넣지 않은 것 하나 — **version 행이 하나도 없는 패키지.** 개요 SQL 이 latest_ver 를
-- INNER JOIN 하므로 그런 패키지는 응답에서 빠지고 not_found 로 분류된다. 서버는 그 상황을
-- 로그로 경고하지만(PackageService.warnIfSilentlyDropped), 목업 화면에는 "이름을 확인하세요"
-- 로 보여서 데이터가 잘못된 것인지 화면이 잘못된 것인지 구분이 안 된다.
--
--
-- 전체를 한 트랜잭션으로 묶는다.
--   * 중간에 실패하면 아무것도 반영되지 않는다 — 반쯤 채워진 DB 가 남지 않는다.
--   * 아래 임시 테이블의 ON COMMIT DROP 이 의도대로 동작한다. psql 은 문장마다 자동 커밋이라
--     묶지 않으면 CREATE 직후 커밋되며 테이블이 바로 사라진다.
BEGIN;

-- 여섯 테이블이 FK 로 묶여 있어 하나씩은 비울 수 없다. 한 번에 비운다.
-- CASCADE 를 쓰지 않는 이유: 나중에 추가된 테이블까지 말없이 같이 비워 버린다.
-- 여기 전부 적어 두면 새 테이블이 생겼을 때 이 파일이 에러로 알려 준다.
TRUNCATE community_snapshot, dependent_removal_reason, dependent_transition, package_env, similar_package, package_version_snapshot, package_snapshot, available_package, version, package;

-- ⚠ snapshot 만 TRUNCATE 가 아니라 DELETE 다.
--
-- V3 가 etl_snapshot_reference.snapshot_at → snapshot 의 FK 를 만들었다. PostgreSQL 의
-- TRUNCATE 는 참조하는 테이블이 **비어 있어도** 같이 지정하지 않으면 거절한다. 그래서
-- 여기에 etl_snapshot_reference 를 적으면 시드가 파이프라인의 적재 이력을 지우게 된다 —
-- 이 파일이 소유하지 않는 데이터다.
--
-- DELETE 는 참조가 실제로 있을 때만 FK 위반으로 실패한다. 즉 **적재 이력이 있는 DB 에서는
-- 이 시드가 조용히 덮어쓰지 않고 에러로 멈춘다.** 그게 맞는 동작이다.
DELETE FROM snapshot;


-- =========================================================================
-- 1. snapshot — 130주
-- =========================================================================
--
-- 조회 상한(104주)보다 넉넉하다. 상한을 넘겼을 때 V002 가 나가는지, from·to 로 자른 구간이
-- 실제로 짧아지는지를 이 여유분으로 확인한다.
--
-- 마지막 날짜는 2026-08-31 — V1 의 snapshot 기본값과 같은 날이다.
INSERT INTO snapshot (snapshot_at)
SELECT g::date
FROM generate_series(DATE '2026-08-31' - 129 * 7, DATE '2026-08-31', INTERVAL '7 days') AS g;

-- 스냅샷 번호 0..129. 아래 계산은 전부 이 번호를 축으로 쓴다.
-- 날짜로 계산하지 않는 이유는 주 간격이 바뀌어도 곡선 모양이 그대로 유지되게 하려는 것이다.
CREATE TEMP VIEW snap_idx AS
SELECT snapshot_at, (ROW_NUMBER() OVER (ORDER BY snapshot_at) - 1)::int AS i
FROM snapshot;


-- =========================================================================
-- 2. package — 카탈로그 34 + 채움 288
-- =========================================================================
--
-- 카탈로그는 쓰임새별로 4~6개씩 묶여 있다. 비교 화면이 최대 3개를 받으므로(명세 0.1),
-- 같은 묶음에서 3개를 골라야 "비교할 만한 화면" 이 나온다 — express·koa·fastify 처럼.
-- 이 묶음은 아래 similar_package 의 후보 묶음이기도 하다.
INSERT INTO package (package_id, name, repo_url) VALUES
  -- 웹 프레임워크
  ( 1, 'express',        'https://github.com/expressjs/express'),
  ( 2, 'koa',            'https://github.com/koajs/koa'),
  ( 3, 'fastify',        'https://github.com/fastify/fastify'),
  ( 4, '@hapi/hapi',     'https://github.com/hapijs/hapi'),
  ( 5, 'restify',        'https://github.com/restify/node-restify'),
  -- 로깅
  ( 6, 'winston',        'https://github.com/winstonjs/winston'),
  ( 7, 'pino',           'https://github.com/pinojs/pino'),
  ( 8, 'log4js',         'https://github.com/log4js-node/log4js-node'),
  ( 9, 'bunyan',         'https://github.com/trentm/node-bunyan'),
  (34, 'consola',        'https://github.com/unjs/consola'),
  -- 유틸리티
  (10, 'lodash',         'https://github.com/lodash/lodash'),
  (11, 'ramda',          'https://github.com/ramda/ramda'),
  (12, 'underscore',     'https://github.com/jashkenas/underscore'),
  (13, 'left-pad',       NULL),                                        -- 저장소를 못 찾은 경우
  (14, 'string_decoder', 'https://github.com/nodejs/string_decoder'),
  -- 날짜
  (15, 'moment',         'https://github.com/moment/moment'),
  (16, 'dayjs',          'https://github.com/iamkun/dayjs'),
  (17, 'date-fns',       'https://github.com/date-fns/date-fns'),
  (18, 'luxon',          'https://github.com/moment/luxon'),
  -- 테스트
  (19, 'jest',           'https://github.com/jestjs/jest'),
  (20, 'mocha',          'https://github.com/mochajs/mocha'),
  (21, 'vitest',         'https://github.com/vitest-dev/vitest'),
  (22, 'ava',            'https://github.com/avajs/ava'),
  -- 번들러
  (23, 'webpack',        'https://github.com/webpack/webpack'),
  (24, 'rollup',         'https://github.com/rollup/rollup'),
  (25, 'esbuild',        'https://github.com/evanw/esbuild'),
  (26, 'vite',           'https://github.com/vitejs/vite'),
  (27, 'parcel',         'https://github.com/parcel-bundler/parcel'),
  (28, 'rolldown',       'https://github.com/rolldown/rolldown'),      -- 신규
  -- HTTP 클라이언트
  (29, 'axios',          'https://github.com/axios/axios'),
  (30, 'got',            'https://github.com/sindresorhus/got'),
  (31, 'node-fetch',     'https://github.com/node-fetch/node-fetch'),
  (32, 'superagent',     'https://github.com/ladjs/superagent'),
  (33, 'request',        'https://github.com/request/request');        -- deprecated

-- 채움 288개 = 접두사 24 × 접미사 12.
--
-- 접미사를 묶음(group)으로 쓴다. `-plugin` 끼리, `-loader` 끼리 후보가 되므로 유사 패키지
-- 목록이 "그럴듯한 이웃" 으로 채워지고, 자동완성은 접두사로 걸린다.
--
-- 이름 규칙(명세 0.1)을 지킨다 — 소문자·숫자·`- _ . ~` 만. 대문자를 넣으면 서버가 V004 로
-- 거절하므로 검색창에서 아예 조회되지 않는다.
CREATE TEMP TABLE filler_name (
    package_id INT PRIMARY KEY,
    name       TEXT NOT NULL,
    group_id   INT  NOT NULL
) ON COMMIT DROP;

INSERT INTO filler_name (package_id, name, group_id)
SELECT 1000 + (p.ord - 1) * 12 + s.ord,
       p.word || s.word,
       s.ord
FROM (VALUES
        ('react',1),('vue',2),('svelte',3),('angular',4),('next',5),('nuxt',6),
        ('remix',7),('astro',8),('babel',9),('eslint',10),('postcss',11),('tailwind',12),
        ('storybook',13),('cypress',14),('playwright',15),('turbo',16),('redux',17),('apollo',18),
        ('prisma',19),('knex',20),('sequelize',21),('mongoose',22),('gulp',23),('grunt',24)
     ) AS p(word, ord)
CROSS JOIN (VALUES
        ('-plugin',1),('-loader',2),('-config',3),('-utils',4),('-cli',5),('-core',6),
        ('-parser',7),('-types',8),('-helper',9),('-adapter',10),('-preset',11),('-runtime',12)
     ) AS s(word, ord);

INSERT INTO package (package_id, name, repo_url)
SELECT package_id, name, 'https://github.com/pickage-mock/' || name
FROM filler_name;


-- =========================================================================
-- 3. version — 카탈로그
-- =========================================================================
--
-- **ordinal 이 최신 버전의 유일한 기준이다**(명세 0.6). 문자열로 정렬하면 2.9.0 이 2.15.3
-- 보다 뒤로 가고, 그 실수는 에러 없이 화면에 "최신 버전 2.9.0" 으로만 나타난다.
-- koa · lodash · rollup 을 그 함정에 걸리도록 두었다 — 정렬을 잘못 짜면 이 셋이 먼저 틀린다.
--
-- dependency 컬럼은 여기서 넣지 않고 DEFAULT 를 쓴다. DEFAULT 가 이미
-- `dependencies` · `peerDependencies` · `optionalDependencies` 세 키를 빈 객체로 갖고 있어서,
-- `dependency->'dependencies'` 를 읽는 코드가 시드에서만 아무것도 못 찾는 일이 생기지 않는다.
-- 값이 들어 있는 사례는 아래 3-1 에서 몇 개만 채운다.
--
-- licenses 는 JSON 컬럼이다. 대부분 배열이지만 left-pad 만 JSON 문자열로 두었다 —
-- 개요 SQL 의 json_typeof 가드가 없으면 그 한 행 때문에 조회 전체가 실패한다.
INSERT INTO version (package_id, version, published_at, ordinal, description, licenses, deprecated) VALUES
  ( 1, '4.9.0',   TIMESTAMP '2014-09-01 10:00:00', 1, 'Fast, unopinionated, minimalist web framework', '["MIT"]', NULL),
  ( 1, '4.16.4',  TIMESTAMP '2018-10-10 09:12:00', 2, 'Fast, unopinionated, minimalist web framework', '["MIT"]', NULL),
  ( 1, '4.17.3',  TIMESTAMP '2022-02-16 14:03:00', 3, 'Fast, unopinionated, minimalist web framework', '["MIT"]', NULL),
  ( 1, '4.18.2',  TIMESTAMP '2022-10-08 07:41:00', 4, 'Fast, unopinionated, minimalist web framework', '["MIT"]', NULL),
  ( 1, '4.19.2',  TIMESTAMP '2024-03-25 11:20:00', 5, 'Fast, unopinionated, minimalist web framework', '["MIT"]', NULL),
  ( 1, '5.0.0',   TIMESTAMP '2024-09-10 08:00:00', 6, 'Fast, unopinionated, minimalist web framework', '["MIT"]', NULL),
  -- 문자열 정렬이면 2.9.0 이 최신으로 뽑힌다
  ( 2, '2.9.0',   TIMESTAMP '2019-10-17 03:30:00', 1, 'Expressive middleware for node.js using ES2017 async functions', '["MIT"]', NULL),
  ( 2, '2.13.4',  TIMESTAMP '2022-03-04 05:10:00', 2, 'Expressive middleware for node.js using ES2017 async functions', '["MIT"]', NULL),
  ( 2, '2.14.2',  TIMESTAMP '2023-04-26 12:44:00', 3, 'Expressive middleware for node.js using ES2017 async functions', '["MIT"]', NULL),
  ( 2, '2.15.3',  TIMESTAMP '2024-04-15 16:02:00', 4, 'Expressive middleware for node.js using ES2017 async functions', '["MIT"]', NULL),
  ( 3, '3.29.5',  TIMESTAMP '2022-08-08 09:00:00', 1, 'Fast and low overhead web framework, for Node.js', '["MIT"]', NULL),
  ( 3, '4.15.0',  TIMESTAMP '2023-03-24 10:15:00', 2, 'Fast and low overhead web framework, for Node.js', '["MIT"]', NULL),
  ( 3, '4.26.2',  TIMESTAMP '2024-02-26 08:30:00', 3, 'Fast and low overhead web framework, for Node.js', '["MIT"]', NULL),
  ( 3, '5.0.0',   TIMESTAMP '2024-09-17 13:05:00', 4, 'Fast and low overhead web framework, for Node.js', '["MIT"]', NULL),
  ( 4, '20.2.2',  TIMESTAMP '2022-06-14 07:20:00', 1, 'HTTP Server framework', '["BSD-3-Clause"]', NULL),
  ( 4, '21.1.0',  TIMESTAMP '2022-11-30 09:45:00', 2, 'HTTP Server framework', '["BSD-3-Clause"]', NULL),
  ( 4, '21.3.2',  TIMESTAMP '2023-08-21 11:10:00', 3, 'HTTP Server framework', '["BSD-3-Clause"]', NULL),
  ( 4, '21.3.9',  TIMESTAMP '2024-05-07 15:55:00', 4, 'HTTP Server framework', '["BSD-3-Clause"]', NULL),
  ( 5, '8.6.1',   TIMESTAMP '2021-11-02 04:00:00', 1, 'REST framework specifically meant for web service APIs', '["MIT"]', NULL),
  ( 5, '9.0.0',   TIMESTAMP '2023-01-19 06:25:00', 2, 'REST framework specifically meant for web service APIs', '["MIT"]', NULL),
  ( 5, '10.0.0',  TIMESTAMP '2023-09-05 08:40:00', 3, 'REST framework specifically meant for web service APIs', '["MIT"]', NULL),
  ( 5, '11.1.0',  TIMESTAMP '2024-04-02 10:30:00', 4, 'REST framework specifically meant for web service APIs', '["MIT"]', NULL),
  ( 6, '3.3.3',   TIMESTAMP '2020-06-23 02:15:00', 1, 'A logger for just about everything', '["MIT"]', NULL),
  ( 6, '3.8.2',   TIMESTAMP '2022-11-01 09:05:00', 2, 'A logger for just about everything', '["MIT"]', NULL),
  ( 6, '3.11.0',  TIMESTAMP '2023-09-14 13:20:00', 3, 'A logger for just about everything', '["MIT"]', NULL),
  ( 6, '3.13.1',  TIMESTAMP '2024-07-08 07:35:00', 4, 'A logger for just about everything', '["MIT"]', NULL),
  ( 7, '7.11.0',  TIMESTAMP '2022-05-16 05:50:00', 1, 'Super fast, all natural json logger', '["MIT"]', NULL),
  ( 7, '8.11.0',  TIMESTAMP '2023-03-20 08:10:00', 2, 'Super fast, all natural json logger', '["MIT"]', NULL),
  ( 7, '8.21.0',  TIMESTAMP '2024-03-11 09:55:00', 3, 'Super fast, all natural json logger', '["MIT"]', NULL),
  ( 7, '9.3.2',   TIMESTAMP '2024-08-05 11:40:00', 4, 'Super fast, all natural json logger', '["MIT"]', NULL),
  ( 8, '6.4.0',   TIMESTAMP '2022-01-24 03:05:00', 1, 'Port of Log4js to work with node', '["Apache-2.0"]', NULL),
  ( 8, '6.7.1',   TIMESTAMP '2022-11-25 06:30:00', 2, 'Port of Log4js to work with node', '["Apache-2.0"]', NULL),
  ( 8, '6.9.1',   TIMESTAMP '2023-07-31 08:20:00', 3, 'Port of Log4js to work with node', '["Apache-2.0"]', NULL),
  ( 8, '6.10.0',  TIMESTAMP '2024-06-17 10:00:00', 4, 'Port of Log4js to work with node', '["Apache-2.0"]', NULL),
  ( 9, '1.8.12',  TIMESTAMP '2018-05-04 01:20:00', 1, 'a JSON logging library for node.js services', '["MIT"]', NULL),
  -- 최신이 아닌 버전에 deprecated 가 붙은 사례. 카드의 is_deprecated 는 최신 버전만 본다.
  ( 9, '1.8.13',  TIMESTAMP '2021-03-09 04:45:00', 2, 'a JSON logging library for node.js services', '["MIT"]', 'broken dtrace fallback in this release, use 1.8.14 or newer'),
  ( 9, '1.8.14',  TIMESTAMP '2021-09-28 07:10:00', 3, 'a JSON logging library for node.js services', '["MIT"]', NULL),
  ( 9, '1.8.15',  TIMESTAMP '2022-02-11 09:35:00', 4, 'a JSON logging library for node.js services', '["MIT"]', NULL),
  (34, '2.15.3',  TIMESTAMP '2022-03-15 08:00:00', 1, 'Elegant Console Logger', '["MIT"]', NULL),
  (34, '3.2.3',   TIMESTAMP '2023-12-01 09:30:00', 2, 'Elegant Console Logger', '["MIT"]', NULL),
  -- 문자열 정렬이면 4.17.9 가 최신으로 뽑힌다
  (10, '4.17.5',  TIMESTAMP '2018-02-01 12:00:00', 1, 'Lodash modular utilities', '["MIT"]', NULL),
  (10, '4.17.9',  TIMESTAMP '2018-04-24 13:15:00', 2, 'Lodash modular utilities', '["MIT"]', NULL),
  (10, '4.17.15', TIMESTAMP '2019-07-17 14:30:00', 3, 'Lodash modular utilities', '["MIT"]', NULL),
  (10, '4.17.21', TIMESTAMP '2021-02-20 15:45:00', 4, 'Lodash modular utilities', '["MIT"]', NULL),
  (11, '0.27.2',  TIMESTAMP '2021-12-08 06:00:00', 1, 'A practical functional library for JavaScript programmers', '["MIT"]', NULL),
  (11, '0.28.0',  TIMESTAMP '2022-04-19 07:20:00', 2, 'A practical functional library for JavaScript programmers', '["MIT"]', NULL),
  (11, '0.29.1',  TIMESTAMP '2023-06-06 09:40:00', 3, 'A practical functional library for JavaScript programmers', '["MIT"]', NULL),
  (11, '0.30.1',  TIMESTAMP '2024-06-25 11:00:00', 4, 'A practical functional library for JavaScript programmers', '["MIT"]', NULL),
  (12, '1.12.1',  TIMESTAMP '2021-03-30 03:10:00', 1, 'JavaScript is functional programming, batteries included', '["MIT"]', NULL),
  (12, '1.13.1',  TIMESTAMP '2021-06-21 05:25:00', 2, 'JavaScript is functional programming, batteries included', '["MIT"]', NULL),
  (12, '1.13.4',  TIMESTAMP '2022-08-16 07:50:00', 3, 'JavaScript is functional programming, batteries included', '["MIT"]', NULL),
  (12, '1.13.6',  TIMESTAMP '2022-10-04 09:05:00', 4, 'JavaScript is functional programming, batteries included', '["MIT"]', NULL),
  -- licenses 가 배열이 아니다. json_typeof 가드를 지우면 이 행 하나가 개요 조회를 통째로 죽인다.
  (13, '1.1.3',   TIMESTAMP '2016-03-23 02:00:00', 1, 'String left pad', '"WTFPL"', NULL),
  (13, '1.2.0',   TIMESTAMP '2017-06-08 03:30:00', 2, 'String left pad', '"WTFPL"', NULL),
  (13, '1.3.0',   TIMESTAMP '2018-05-17 04:45:00', 3, 'String left pad', '"WTFPL"', NULL),
  -- 라이선스가 2개인 사례. FROM 절에서 펼치면 이 패키지만 2행이 되어 개요 CTE 가 흔들린다.
  (14, '1.1.1',   TIMESTAMP '2017-04-11 01:10:00', 1, 'The string_decoder module from Node core', '["MIT","Apache-2.0"]', NULL),
  (14, '1.2.0',   TIMESTAMP '2018-08-30 02:20:00', 2, 'The string_decoder module from Node core', '["MIT","Apache-2.0"]', NULL),
  (14, '1.3.0',   TIMESTAMP '2019-01-15 03:40:00', 3, 'The string_decoder module from Node core', '["MIT","Apache-2.0"]', NULL),
  (15, '2.24.0',  TIMESTAMP '2019-06-17 05:00:00', 1, 'Parse, validate, manipulate, and display dates', '["MIT"]', NULL),
  (15, '2.27.0',  TIMESTAMP '2020-06-19 06:15:00', 2, 'Parse, validate, manipulate, and display dates', '["MIT"]', NULL),
  (15, '2.29.4',  TIMESTAMP '2022-07-06 08:25:00', 3, 'Parse, validate, manipulate, and display dates', '["MIT"]', NULL),
  (15, '2.30.1',  TIMESTAMP '2023-12-20 10:35:00', 4, 'Parse, validate, manipulate, and display dates', '["MIT"]', NULL),
  (16, '1.10.7',  TIMESTAMP '2021-11-08 04:20:00', 1, '2KB immutable date time library alternative to Moment.js', '["MIT"]', NULL),
  (16, '1.11.5',  TIMESTAMP '2022-08-24 06:40:00', 2, '2KB immutable date time library alternative to Moment.js', '["MIT"]', NULL),
  (16, '1.11.10', TIMESTAMP '2023-10-31 08:55:00', 3, '2KB immutable date time library alternative to Moment.js', '["MIT"]', NULL),
  (16, '1.11.13', TIMESTAMP '2024-08-14 11:15:00', 4, '2KB immutable date time library alternative to Moment.js', '["MIT"]', NULL),
  (17, '2.29.3',  TIMESTAMP '2022-09-13 03:50:00', 1, 'Modern JavaScript date utility library', '["MIT"]', NULL),
  (17, '2.30.0',  TIMESTAMP '2023-05-18 05:30:00', 2, 'Modern JavaScript date utility library', '["MIT"]', NULL),
  (17, '3.6.0',   TIMESTAMP '2024-03-18 07:45:00', 3, 'Modern JavaScript date utility library', '["MIT"]', NULL),
  (17, '4.1.0',   TIMESTAMP '2024-09-16 09:20:00', 4, 'Modern JavaScript date utility library', '["MIT"]', NULL),
  (18, '2.5.2',   TIMESTAMP '2022-12-01 02:30:00', 1, 'Immutable date wrapper', '["Apache-2.0"]', NULL),
  (18, '3.2.1',   TIMESTAMP '2023-01-19 04:10:00', 2, 'Immutable date wrapper', '["Apache-2.0"]', NULL),
  (18, '3.4.4',   TIMESTAMP '2023-11-27 06:25:00', 3, 'Immutable date wrapper', '["Apache-2.0"]', NULL),
  (18, '3.5.0',   TIMESTAMP '2024-07-22 08:40:00', 4, 'Immutable date wrapper', '["Apache-2.0"]', NULL),
  (19, '27.5.1',  TIMESTAMP '2022-02-08 01:05:00', 1, 'Delightful JavaScript Testing', '["MIT"]', NULL),
  (19, '28.1.3',  TIMESTAMP '2022-07-13 03:20:00', 2, 'Delightful JavaScript Testing', '["MIT"]', NULL),
  (19, '29.5.0',  TIMESTAMP '2023-03-06 05:35:00', 3, 'Delightful JavaScript Testing', '["MIT"]', NULL),
  (19, '29.7.0',  TIMESTAMP '2023-09-12 07:50:00', 4, 'Delightful JavaScript Testing', '["MIT"]', NULL),
  (20, '9.2.2',   TIMESTAMP '2022-03-11 02:45:00', 1, 'simple, flexible, fun test framework', '["MIT"]', NULL),
  (20, '10.0.0',  TIMESTAMP '2022-05-01 04:55:00', 2, 'simple, flexible, fun test framework', '["MIT"]', NULL),
  (20, '10.2.0',  TIMESTAMP '2022-12-11 06:15:00', 3, 'simple, flexible, fun test framework', '["MIT"]', NULL),
  (20, '10.7.3',  TIMESTAMP '2024-08-01 08:25:00', 4, 'simple, flexible, fun test framework', '["MIT"]', NULL),
  (21, '0.34.6',  TIMESTAMP '2023-10-17 03:15:00', 1, 'Next generation testing framework powered by Vite', '["MIT"]', NULL),
  (21, '1.2.2',   TIMESTAMP '2024-01-26 05:35:00', 2, 'Next generation testing framework powered by Vite', '["MIT"]', NULL),
  (21, '1.6.0',   TIMESTAMP '2024-05-03 07:45:00', 3, 'Next generation testing framework powered by Vite', '["MIT"]', NULL),
  (21, '2.0.5',   TIMESTAMP '2024-08-09 09:55:00', 4, 'Next generation testing framework powered by Vite', '["MIT"]', NULL),
  (22, '4.3.3',   TIMESTAMP '2022-09-06 01:30:00', 1, 'Node.js test runner that lets you develop with confidence', '["MIT"]', NULL),
  (22, '5.3.1',   TIMESTAMP '2023-06-16 03:40:00', 2, 'Node.js test runner that lets you develop with confidence', '["MIT"]', NULL),
  (22, '6.0.1',   TIMESTAMP '2023-11-24 05:50:00', 3, 'Node.js test runner that lets you develop with confidence', '["MIT"]', NULL),
  (22, '6.1.3',   TIMESTAMP '2024-04-05 07:05:00', 4, 'Node.js test runner that lets you develop with confidence', '["MIT"]', NULL),
  (23, '5.70.0',  TIMESTAMP '2022-03-02 02:10:00', 1, 'Packs ECMAScript/CommonJs/AMD modules for the browser', '["MIT"]', NULL),
  (23, '5.76.0',  TIMESTAMP '2023-02-14 04:20:00', 2, 'Packs ECMAScript/CommonJs/AMD modules for the browser', '["MIT"]', NULL),
  (23, '5.88.2',  TIMESTAMP '2023-07-11 06:30:00', 3, 'Packs ECMAScript/CommonJs/AMD modules for the browser', '["MIT"]', NULL),
  (23, '5.94.0',  TIMESTAMP '2024-08-16 08:45:00', 4, 'Packs ECMAScript/CommonJs/AMD modules for the browser', '["MIT"]', NULL),
  -- 여기도 문자열 정렬 함정 — 4.9.6 이 4.21.2 보다 뒤로 간다
  (24, '2.79.1',  TIMESTAMP '2022-09-16 03:00:00', 1, 'Next-generation ES module bundler', '["MIT"]', NULL),
  (24, '3.29.4',  TIMESTAMP '2023-09-06 05:10:00', 2, 'Next-generation ES module bundler', '["MIT"]', NULL),
  (24, '4.9.6',   TIMESTAMP '2024-01-21 07:25:00', 3, 'Next-generation ES module bundler', '["MIT"]', NULL),
  (24, '4.21.2',  TIMESTAMP '2024-09-01 09:35:00', 4, 'Next-generation ES module bundler', '["MIT"]', NULL),
  (25, '0.14.54', TIMESTAMP '2022-08-09 01:45:00', 1, 'An extremely fast bundler for the web', '["MIT"]', NULL),
  (25, '0.17.19', TIMESTAMP '2023-05-16 03:55:00', 2, 'An extremely fast bundler for the web', '["MIT"]', NULL),
  (25, '0.19.12', TIMESTAMP '2024-02-06 06:05:00', 3, 'An extremely fast bundler for the web', '["MIT"]', NULL),
  (25, '0.23.1',  TIMESTAMP '2024-08-20 08:15:00', 4, 'An extremely fast bundler for the web', '["MIT"]', NULL),
  (26, '3.2.7',   TIMESTAMP '2023-01-10 02:20:00', 1, 'Native-ESM powered web dev build tool', '["MIT"]', NULL),
  (26, '4.5.3',   TIMESTAMP '2024-03-24 04:30:00', 2, 'Native-ESM powered web dev build tool', '["MIT"]', NULL),
  (26, '5.2.11',  TIMESTAMP '2024-05-14 06:40:00', 3, 'Native-ESM powered web dev build tool', '["MIT"]', NULL),
  (26, '5.4.3',   TIMESTAMP '2024-09-03 08:50:00', 4, 'Native-ESM powered web dev build tool', '["MIT"]', NULL),
  (27, '2.6.2',   TIMESTAMP '2022-06-21 01:15:00', 1, 'Blazing fast, zero configuration web application bundler', '["MIT"]', NULL),
  (27, '2.8.3',   TIMESTAMP '2023-01-31 03:25:00', 2, 'Blazing fast, zero configuration web application bundler', '["MIT"]', NULL),
  (27, '2.10.3',  TIMESTAMP '2023-11-14 05:35:00', 3, 'Blazing fast, zero configuration web application bundler', '["MIT"]', NULL),
  (27, '2.12.0',  TIMESTAMP '2024-02-27 07:45:00', 4, 'Blazing fast, zero configuration web application bundler', '["MIT"]', NULL),
  (28, '0.13.0',  TIMESTAMP '2026-06-09 09:00:00', 1, 'Fast Rust bundler for JavaScript', '["MIT"]', NULL),
  (28, '0.14.1',  TIMESTAMP '2026-07-21 10:30:00', 2, 'Fast Rust bundler for JavaScript', '["MIT"]', NULL),
  (29, '0.27.2',  TIMESTAMP '2022-05-14 02:05:00', 1, 'Promise based HTTP client for the browser and node.js', '["MIT"]', NULL),
  (29, '1.4.0',   TIMESTAMP '2023-04-27 04:15:00', 2, 'Promise based HTTP client for the browser and node.js', '["MIT"]', NULL),
  (29, '1.6.8',   TIMESTAMP '2024-03-15 06:25:00', 3, 'Promise based HTTP client for the browser and node.js', '["MIT"]', NULL),
  (29, '1.7.5',   TIMESTAMP '2024-08-22 08:35:00', 4, 'Promise based HTTP client for the browser and node.js', '["MIT"]', NULL),
  (30, '11.8.5',  TIMESTAMP '2022-06-25 01:55:00', 1, 'Human-friendly and powerful HTTP request library for Node.js', '["MIT"]', NULL),
  (30, '12.6.0',  TIMESTAMP '2023-03-08 04:05:00', 2, 'Human-friendly and powerful HTTP request library for Node.js', '["MIT"]', NULL),
  (30, '13.0.0',  TIMESTAMP '2023-08-18 06:15:00', 3, 'Human-friendly and powerful HTTP request library for Node.js', '["MIT"]', NULL),
  (30, '14.4.2',  TIMESTAMP '2024-07-30 08:25:00', 4, 'Human-friendly and powerful HTTP request library for Node.js', '["MIT"]', NULL),
  (31, '2.6.9',   TIMESTAMP '2022-01-18 03:35:00', 1, 'A light-weight module that brings Fetch API to node.js', '["MIT"]', NULL),
  (31, '3.2.10',  TIMESTAMP '2022-09-06 05:45:00', 2, 'A light-weight module that brings Fetch API to node.js', '["MIT"]', NULL),
  (31, '3.3.1',   TIMESTAMP '2023-05-19 07:55:00', 3, 'A light-weight module that brings Fetch API to node.js', '["MIT"]', NULL),
  (31, '3.3.2',   TIMESTAMP '2023-06-13 09:05:00', 4, 'A light-weight module that brings Fetch API to node.js', '["MIT"]', NULL),
  (32, '7.1.6',   TIMESTAMP '2022-08-01 02:25:00', 1, 'elegant and feature rich browser / node HTTP with a fluent API', '["MIT"]', NULL),
  (32, '8.0.9',   TIMESTAMP '2023-02-27 04:35:00', 2, 'elegant and feature rich browser / node HTTP with a fluent API', '["MIT"]', NULL),
  (32, '8.1.2',   TIMESTAMP '2023-09-25 06:45:00', 3, 'elegant and feature rich browser / node HTTP with a fluent API', '["MIT"]', NULL),
  (32, '9.0.2',   TIMESTAMP '2024-05-20 08:55:00', 4, 'elegant and feature rich browser / node HTTP with a fluent API', '["MIT"]', NULL),
  (33, '2.85.0',  TIMESTAMP '2018-03-12 01:00:00', 1, 'Simplified HTTP request client', '["Apache-2.0"]', NULL),
  (33, '2.87.0',  TIMESTAMP '2018-05-21 02:10:00', 2, 'Simplified HTTP request client', '["Apache-2.0"]', NULL),
  (33, '2.88.0',  TIMESTAMP '2018-08-09 03:20:00', 3, 'Simplified HTTP request client', '["Apache-2.0"]', NULL),
  -- 최신 버전이 deprecated 다. 카드의 is_deprecated 가 켜지는 유일한 패키지.
  (33, '2.88.2',  TIMESTAMP '2020-02-11 04:30:00', 4, 'Simplified HTTP request client', '["Apache-2.0"]', 'request has been deprecated, see https://github.com/request/request/issues/3142');


-- 3-1. dependency 예시.
--
-- API v1 은 이 컬럼을 읽지 않는다(유저에게 의존성을 보여주는 용도 — V1 의 컬럼 주석).
-- 그래도 몇 개는 채워 둔다. 전부 빈 객체이면 화면을 붙일 때 "구조가 이런 모양이구나" 를
-- 알 수 없고, 파이프라인이 만드는 세 키 구조(pipeline/curated/transform.py)를 여기서
-- 확인할 수도 없다.
UPDATE version SET dependency = '{"dependencies":{"body-parser":"1.20.2","cookie":"0.6.0","qs":"6.11.0"},"peerDependencies":{},"optionalDependencies":{}}'
WHERE package_id = 1 AND version = '4.19.2';
UPDATE version SET dependency = '{"dependencies":{"koa-compose":"^4.1.0","http-errors":"^1.8.1"},"peerDependencies":{},"optionalDependencies":{}}'
WHERE package_id = 2 AND version = '2.15.3';
UPDATE version SET dependency = '{"dependencies":{},"peerDependencies":{"typescript":">=5.0.0"},"optionalDependencies":{"fsevents":"~2.3.3"}}'
WHERE package_id = 26 AND version = '5.4.3';


-- =========================================================================
-- 4. version — 채움
-- =========================================================================
--
-- 패키지마다 major 1·2·3 세 버전. 자릿수는 package_id 에서 파생시켜 서로 달라 보이게만 한다.
-- ordinal 이 major 와 같아서 최신 버전 규칙이 여기서는 함정에 걸리지 않는다 — 함정은
-- 위 카탈로그(koa · lodash · rollup)에 몰아 두었다.
INSERT INTO version (package_id, version, published_at, ordinal, description, licenses, deprecated)
SELECT f.package_id,
       v.major || '.' || ((f.package_id * v.major) % 9) || '.' || ((f.package_id + v.major) % 5),
       TIMESTAMP '2022-01-10 00:00:00' + ((f.package_id % 40) + v.major * 220) * INTERVAL '1 day',
       v.major,
       f.name || ' — 목업 채움 패키지',
       '["MIT"]'::json,
       NULL
FROM filler_name f
CROSS JOIN (VALUES (1),(2),(3)) AS v(major);


-- =========================================================================
-- 5. 지표 곡선 계수
-- =========================================================================
--
-- 값을 130줄씩 적는 대신 계수만 둔다. 곡선을 바꾸고 싶으면 여기 한 줄만 고치면 된다.
--
--   downloads    = dl_base + dl_step * i + ((i * i) % 11) * 137
--   stars        = st_base + st_step * i + (i % 5)
--   open_issues  = is_base + ((i * 13) % 17) - 8   (0 미만은 0)
--
-- `(i * i) % 11` · `(i * 13) % 17` 은 잔물결이다. 완전한 직선이면 차트가 자로 그은 것처럼
-- 보여서 축·툴팁·구간 자르기가 제대로 도는지 눈으로 확인하기 어렵다.
--
-- 전부 정수 연산인 것이 중요하다. 부동소수를 쓰면 환경에 따라 마지막 자리가 갈려
-- "내 화면과 남의 화면의 숫자가 미세하게 다른" 상태가 된다.
--
--   st_base 가 NULL  → repo_url 이 없어 별·이슈를 관측하지 못하는 패키지 (stars·open_issues NULL)
--   dl_base 가 NULL  → downloads 를 관측하지 못하는 패키지 (지금은 없다)
--   first_i          → 이 번호부터 스냅샷이 생긴다. 신규 패키지는 앞쪽 스냅샷에 행이 없다.
--   dl_null_tail     → 마지막 3주의 downloads 가 NULL. "0회" 가 아니라 "집계 중" 이다.
--   dep_scale        → 의존 수의 크기. 아래 6절의 버전별 곡선이 이 값을 나눠 갖는다.
CREATE TEMP TABLE pkg_curve (
    package_id   INT PRIMARY KEY,
    first_i      INT     NOT NULL DEFAULT 0,
    dl_base      BIGINT,
    dl_step      BIGINT,
    st_base      INT,
    st_step      INT,
    is_base      INT,
    dl_null_tail BOOLEAN NOT NULL DEFAULT FALSE,
    dep_scale    INT     NOT NULL,
    -- 다음 버전이 다 퍼진 뒤에도 이 버전이 남기는 비율(%). 아래 7절에서 쓴다.
    legacy_keep  INT     NOT NULL DEFAULT 0
) ON COMMIT DROP;

INSERT INTO pkg_curve (package_id, first_i, dl_base, dl_step, st_base, st_step, is_base, dl_null_tail, dep_scale) VALUES
  ( 1,   0, 24000000,  42000, 60000, 12, 180, FALSE,  92000),   -- express
  ( 2,   0,   900000,   2600, 34000,  5,  60, FALSE,  12000),   -- koa
  ( 3,   0,  1200000,   8900, 27000, 22,  90, FALSE,   9500),   -- fastify
  ( 4,   0,   400000,    900, 14300,  3,  30, FALSE,   3200),   -- @hapi/hapi
  ( 5,   0,   120000,    210, 10500,  1,  45, FALSE,   1100),   -- restify
  ( 6,   0,  8500000,  21000, 22000,  7, 130, FALSE,  24000),   -- winston
  ( 7,   0,  3100000,  26000, 13000, 16,  70, FALSE,   8800),   -- pino
  ( 8,   0,  2900000,   4100,  5700,  2,  25, FALSE,   4400),   -- log4js
  ( 9,   0,  1300000,    700,  7100,  1, 110, FALSE,   2600),   -- bunyan
  (10,   0, 48000000,  61000, 59000,  9, 120, FALSE, 210000),   -- lodash
  (11,   0,  1600000,   3200, 23600,  4,  55, FALSE,   6300),   -- ramda
  (12,   0,  9700000,   8400, 27200,  2,  40, FALSE,  38000),   -- underscore
  -- repo_url 이 NULL 이라 별·이슈를 볼 수 없다. downloads 는 계속 줄어든다.
  (13,   0,  2100000,  -1900,  NULL,  0, NULL, FALSE,    900),   -- left-pad
  (14,   0, 30000000,  55000,  1900,  1,   8, FALSE,  41000),   -- string_decoder
  (15,   0, 19000000, -14000, 47900,  3, 210, FALSE,  88000),   -- moment (하락)
  (16,   0, 12000000,  39000, 44000, 21, 400, FALSE,  31000),   -- dayjs
  (17,   0, 14000000,  33000, 33000, 14, 150, FALSE,  27000),   -- date-fns
  (18,   0,  6200000,  12000, 15000,  5,  60, FALSE,   9900),   -- luxon
  (19,   0, 19000000,  24000, 43000,  6, 320, FALSE,  64000),   -- jest
  (20,   0,  7300000,   4300, 22400,  2,  90, FALSE,  33000),   -- mocha
  (21,   0,  4800000,  63000, 12000, 34, 280, FALSE,  18000),   -- vitest
  (22,   0,   380000,    400, 20600,  1,  45, FALSE,   2100),   -- ava
  (23,   0, 26000000,  27000, 64000,  8, 190, FALSE,  74000),   -- webpack
  (24,   0, 18000000,  41000, 24800,  6, 130, FALSE,  22000),   -- rollup
  (25,   0, 21000000,  78000, 37000, 25, 170, FALSE,  26000),   -- esbuild
  (26,   0, 15000000,  92000, 66000, 41, 420, FALSE,  35000),   -- vite
  (27,   0,  1100000,    900, 43300,  3, 560, FALSE,   3400),   -- parcel
  -- 신규. 최근 12주에만 스냅샷이 있다 — 시리즈 길이가 다른 상태를 화면이 견디는지 본다.
  (28, 118,    90000,  24000,  8900, 60,  95, FALSE,    400),   -- rolldown
  (29,   0, 41000000,  88000,103000, 18, 230, FALSE, 120000),   -- axios
  (30,   0, 22000000,  12000, 14300,  3,  65, FALSE,   9700),   -- got
  -- 마지막 3주 downloads 가 NULL. 0 으로 그리면 없는 급락이 화면에 생긴다.
  (31,   0, 33000000,   9000,  8700,  2,  40, TRUE,   45000),   -- node-fetch
  (32,   0,  6900000,   2100, 16500,  1,  30, FALSE,  14000),   -- superagent
  -- deprecated. downloads 도 stars 도 줄어든다 — 카드의 증감이 음수로 뜨는 유일한 패키지다.
  -- 증감을 부호 없이 그리거나 절댓값으로 그리는 실수가 여기서 드러난다.
  (33,   0, 24000000, -31000, 25600, -2,  75, FALSE,  52000);   -- request

-- consola(34)는 일부러 넣지 않는다 → 스냅샷이 한 줄도 생기지 않는다.
-- 카드는 뜨는데 추이가 빈 시리즈인 상태이고, 그 이름이 not_found 로 새면 서버가 틀린 것이다.

-- 구버전이 얼마나 오래 남는가.
--
-- 0 이면 다음 버전이 다 퍼진 순간 구버전이 0 이 된다. 그것만 있으면 **모든 패키지의 버전
-- 분포가 최신 2개짜리 파이로 똑같이 나온다** — 비교 화면에서 세 패키지가 같은 그림을 그리고,
-- 조각이 3개 이상일 때의 범례·색상을 검증할 수 없다.
--
-- 실제로는 메이저를 올려도 구버전이 몇 년씩 남는다. 그래서 일부 패키지에만 잔존율을 준다.
-- 남은 패키지(0)는 0 인 행을 계속 만들어 §6 의 `dependents_count > 0` 필터를 검증한다.
UPDATE pkg_curve SET legacy_keep = v.keep FROM (VALUES
    ( 1, 28),   -- express   4.x 가 오래 남는다
    ( 3, 22),   -- fastify
    ( 5, 35),   -- restify
    ( 7, 18),   -- pino
    (15, 30),   -- moment
    (17, 20),   -- date-fns
    (19, 25),   -- jest
    (21, 15),   -- vitest
    (22, 24),   -- ava
    (24, 18),   -- rollup
    (26, 16),   -- vite
    (30, 32),   -- got
    (32, 26),   -- superagent
    (33, 38)    -- request  폐기됐지만 옛 버전이 그대로 물려 있다
) AS v(package_id, keep) WHERE pkg_curve.package_id = v.package_id;

INSERT INTO pkg_curve (package_id, dl_base, dl_step, st_base, st_step, is_base, dep_scale, legacy_keep)
SELECT package_id,
       120000 + (package_id % 37) * 3100,
       220 + (package_id % 11) * 35,
       800 + (package_id % 53) * 21,
       2 + (package_id % 4),
       12 + (package_id % 19),
       600 + (package_id % 29) * 45,
       -- 넷 중 하나는 0 이다. 0 인 행이 남아야 `> 0` 필터가 검증된다.
       (ARRAY[0, 15, 25, 35])[1 + (package_id % 4)]
FROM filler_name;


-- =========================================================================
-- 6. package_snapshot
-- =========================================================================
INSERT INTO package_snapshot (package_id, snapshot_at, downloads, stars, open_issues)
SELECT c.package_id,
       s.snapshot_at,
       CASE WHEN c.dl_base IS NULL                    THEN NULL
            WHEN c.dl_null_tail AND s.i >= 127        THEN NULL
            ELSE c.dl_base + c.dl_step * s.i + ((s.i * s.i) % 11) * 137
       END,
       CASE WHEN c.st_base IS NULL THEN NULL
            ELSE c.st_base + c.st_step * s.i + (s.i % 5)
       END,
       CASE WHEN c.st_base IS NULL THEN NULL
            ELSE GREATEST(0, c.is_base + ((s.i * 13) % 17) - 8)
       END
FROM pkg_curve c
JOIN snap_idx s ON s.i >= c.first_i;


-- =========================================================================
-- 7. package_version_snapshot
-- =========================================================================
--
-- 버전 채택 곡선이다. 한 버전은 나온 뒤 서서히 퍼지다가, **다음 버전이 퍼지는 만큼** 자리를
-- 내준다.
--
--   ad(i, k)  = 채택률 0~100. 자기 차례(start_i)가 오면 주당 3%p 씩 오르고 100 에서 멈춘다.
--   dep(i, k) = dep_scale * ad(i, k) * (100 - ad(i, k+1)) / 10000
--
-- 최신 버전은 아직 오르는 중이라 소수이고, 그 직전 버전이 가장 많고, 더 오래된 버전은
-- 0 이 된다. **실제 npm 의 버전 분포가 이 모양이다** — 최신이 곧바로 다수가 되지 않는다.
--
-- 자리를 내준 뒤의 0 행은 남겨 둔다. §6 SQL 의 `dependents_count > 0` 필터가 실제로 무언가를
-- 걸러 내야 그 조건이 검증된다. 반대로 **아직 나오지 않은 버전의 행은 만들지 않는다** —
-- 0 을 넣으면 "그 주에 아무도 안 썼다" 가 되어, 없는 정보와 관측된 0 이 구분되지 않는다.
--
-- start_i 를 -30 부터 118 까지 펼친다.
--   * 가장 오래된 버전은 -30 — **창이 시작되기 전에 이미 퍼져 있다.** 0 부터 시작하면
--     express 의 의존 수가 2024년에 0 이었다가 올라가는 그래프가 되어, 오래된 패키지가
--     전부 신생 패키지처럼 보인다.
--   * 가장 새 버전은 118 — 마지막 스냅샷(129)까지 12주만 퍼져 채택률이 33% 에서 멈춘다.
--     130 을 쓰면 최신 버전이 0 이 되어 파이가 한 조각만 남는다.
CREATE TEMP TABLE ver_curve ON COMMIT DROP AS
SELECT v.package_id,
       v.version,
       (-30 + (148 * (v.ordinal - 1)) / GREATEST(1, m.max_ord - 1))::int AS start_i,
       LEAD((-30 + (148 * (v.ordinal - 1)) / GREATEST(1, m.max_ord - 1))::int)
            OVER (PARTITION BY v.package_id ORDER BY v.ordinal) AS next_start_i,
       c.dep_scale,
       c.legacy_keep
FROM version v
JOIN (SELECT package_id, MAX(ordinal) AS max_ord FROM version GROUP BY package_id) m
     ON m.package_id = v.package_id
JOIN pkg_curve c ON c.package_id = v.package_id;

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

--
-- 채택률만으로 만들면 버전 합계가 dep_scale 에 딱 붙어 **추이 그래프가 자로 그은 직선**이 된다
-- (한 버전이 잃는 만큼 다음 버전이 그대로 가져가므로). 그래서 두 항을 더한다.
--   * (400 + i) / 400  — 130주에 걸쳐 총량이 1.32배로 완만히 는다.
--   * ripple           — dep_scale 의 ±2.5% 안에서 흔들린다.
--
-- ripple 은 **이미 0 인 행에는 더하지 않는다.** 더하면 "아직 안 나온 버전" 과 "자리를 내준
-- 버전" 이 0 이 아닌 값을 갖게 되어 §6 의 `> 0` 필터가 아무것도 걸러 내지 못한다.
INSERT INTO package_version_snapshot (package_id, version, snapshot_at, dependents_count)
SELECT package_id, version, snapshot_at,
       CASE WHEN base = 0 THEN 0 ELSE GREATEST(1, base + ripple) END
FROM (
    SELECT vc.package_id,
           vc.version,
           s.snapshot_at,
           -- dep_scale 를 numeric 으로 올려 놓고 곱한다. int 로 두면 210000 * 100 * 100 * 529 가
           -- INT 범위를 넘어 "integer out of range" 로 죽는다 — lodash 처럼 큰 값에서만 터진다.
           ROUND(vc.dep_scale::numeric
                 * LEAST(100, GREATEST(0, (s.i - vc.start_i) * 3))
                 * (100 - COALESCE(LEAST(100, GREATEST(0, (s.i - vc.next_start_i) * 3)), 0)
                          * (100 - vc.legacy_keep) / 100)
                 * (400 + s.i)
                 / 4000000.0)::int AS base,
           ((vc.dep_scale / 200) * (((s.i * 7) % 11) - 5))::int AS ripple
    FROM ver_curve vc
    JOIN pkg_curve c  ON c.package_id = vc.package_id
    JOIN snap_idx  s  ON s.i >= c.first_i AND s.i >= vc.start_i
) curve;


-- =========================================================================
-- 8. similar_package
-- =========================================================================
--
-- 아직 조회 경로가 없다(UC4 는 임베딩 파이프라인이 선행 조건). 그래도 채워 둔다 —
-- 화면을 붙일 때 "빈 테이블이라 안 나오는 것" 과 "쿼리가 틀려서 안 나오는 것" 을 구분할 수
-- 있어야 한다.
--
-- 후보는 **같은 쓰임새 묶음** 에서 고른다. express 의 이웃이 dayjs 로 나오면 목업을 보는
-- 사람이 곧바로 "추천이 이상하다" 로 읽는다.
--
-- score 는 순위에서 역산한 값이다. 실제 배치의 점수 공식(cos 유사도 기반 재랭킹)과는
-- 아무 관계가 없다 — model_ver 를 'mock-' 으로 시작하게 둔 이유가 그것이다. 진짜 적재분과
-- 섞이면 이 접두사로 골라낼 수 있다.
CREATE TEMP TABLE pkg_group (
    package_id INT PRIMARY KEY,
    group_id   INT NOT NULL
) ON COMMIT DROP;

INSERT INTO pkg_group (package_id, group_id) VALUES
  ( 1, 1), ( 2, 1), ( 3, 1), ( 4, 1), ( 5, 1),            -- 웹 프레임워크
  ( 6, 2), ( 7, 2), ( 8, 2), ( 9, 2), (34, 2),            -- 로깅
  (10, 3), (11, 3), (12, 3), (13, 3), (14, 3),            -- 유틸리티
  (15, 4), (16, 4), (17, 4), (18, 4),                     -- 날짜
  (19, 5), (20, 5), (21, 5), (22, 5),                     -- 테스트
  (23, 6), (24, 6), (25, 6), (26, 6), (27, 6), (28, 6),   -- 번들러
  (29, 7), (30, 7), (31, 7), (32, 7), (33, 7);            -- HTTP 클라이언트

-- 채움은 접미사가 같은 것끼리(-plugin 은 -plugin 끼리). 묶음이 24개씩이라 rank 상한에
-- 걸리므로 10개에서 자른다.
INSERT INTO pkg_group (package_id, group_id)
SELECT package_id, 100 + group_id FROM filler_name;

INSERT INTO similar_package (package_id, similar_package_id, rank, score, model_ver)
SELECT package_id,
       similar_package_id,
       rank,
       0.94 - rank * 0.035,
       'mock-v1-20260831'
FROM (
    SELECT a.package_id,
           b.package_id AS similar_package_id,
           -- 기준 패키지마다 순서를 섞는다. b.package_id 로만 정렬하면 한 묶음(24개)의
           -- 모든 패키지가 **id 가 작은 같은 10개**를 후보로 갖게 되어, 288개 채움 패키지의
           -- 추천 목록이 전부 똑같아진다.
           --
           -- 곱으로 섞는 이유: `a*37 + b*101` 처럼 더하면 기준이 달라져도 같은 순서를 회전만
           -- 시킨 것이라 후보 집합이 거의 그대로 겹친다.
           ROW_NUMBER() OVER (PARTITION BY a.package_id
                              ORDER BY (a.package_id * b.package_id * 41) % 97,
                                       b.package_id)::int AS rank
    FROM pkg_group a
    JOIN pkg_group b ON b.group_id = a.group_id AND b.package_id <> a.package_id
) ranked
WHERE rank <= 10;

COMMIT;


-- 넣은 결과. 숫자가 예상과 다르면 여기서 바로 드러난다.
SELECT 'snapshot'                 AS table_name, COUNT(*) AS rows FROM snapshot
UNION ALL SELECT 'package',                      COUNT(*) FROM package
UNION ALL SELECT 'version',                      COUNT(*) FROM version
UNION ALL SELECT 'package_snapshot',             COUNT(*) FROM package_snapshot
UNION ALL SELECT 'package_version_snapshot',     COUNT(*) FROM package_version_snapshot
UNION ALL SELECT 'similar_package',              COUNT(*) FROM similar_package
ORDER BY 1;
