-- 관측된 교체 흐름 — 이동쌍 (S15P21A506-136 계산 → S15P21A506-424 적재·조회)
--
-- "X 를 뺀 사람들이 그 자리에 무엇을 넣었나". (출발 패키지 × 도착 이름 × 의존 종류)
-- 하나가 한 행을 갖는다. 약 2.3만 행.
--
-- dependent_removal_reason(V9) 과 **다른 질문에 답한다. 합치면 안 된다.**
--
--   dependent_removal_reason  얼마나 떠났나. 단위 = 전이 건수. 도착지 이름이 없다
--   migration_pair            어디로 갔나.   단위 = 쌍. 도착지 이름이 있다
--
-- V9 의 with_replacement 는 "뺄 때 뭔가 같이 넣었다" 는 수일 뿐 그 자리의 대체라는 보장이
-- 없다(V9 주석). 이 표는 실제로 무엇이 들어왔는지를 (from, to) 짝으로 센다. 두 수는 단위도
-- 모집단도 달라 **더하거나 나누면 안 된다.**
--
-- 화면 문구는 원인·완전한 교체·추천으로 단정하지 않는다. 관측된 흐름일 뿐이다.
--
--
-- ## 적재 기준은 loose 전량이다 (S15P21A506-211 결정 1)
--
-- 빌더의 LOOSE = lift>=5 AND votes>=3 을 그대로 넣는다. strict·recommended 는 **적재
-- 기준이 아니라 API 가 붙이는 배지다.** strict 만 넣으면 화면이 나오는 패키지가 다운로드
-- 상위 1천 중 126개뿐인데, 이동 기록이 있는 패키지는 950개다.
--
-- 하한이 바뀌어도 재적재하지 않기 위해서이기도 하다. strict·recommended 하한은 계산 30분 ·
-- 적재는 그보다 길다. 판단을 API 로 미루면 계산도 적재도 다시 하지 않는다.
--
--
-- ## dep_kind 는 적재기가 부여한다 (S15P21A506-211 결정 3-1)
--
-- 네 데이터셋의 CSV 열 구성이 완전히 같아 구분이 **디렉터리 이름뿐**이다. 빌더를 고쳐 열을
-- 내게 할 일이 아니라, 적재기가 어느 디렉터리에서 읽었는지로 붙인다.
--
--   regular  datasets/migration_pairs_260908/      deps.dev 전수(전이 3,958만)
--   dev      datasets/migration_pairs_dev_260914/  npm registry 상위 10만(전이 726만)
--
-- **모집단이 다르므로 두 종류를 합치거나 votes 를 더하면 안 된다.** lift 의 분모가 그 실행의
-- 모집단 전이 수라 절댓값을 직접 비교할 수도 없다(빌더 36행 주석). 조회는 항상 dep_kind 를
-- 고정하고, 화면은 실행용·개발용을 같은 그림에 겹치지 않는다.
--
-- 도구 계열(eslint·typescript·jest·tslint)은 deps.dev 원천에 개발용 의존 칸이 아예 없어
-- regular 로는 구조적으로 안 보인다. 그래서 dev 가 따로 있다.
--
-- migration_pairs_regular_legacy_260914 은 재분류 과대 계상 12.15% 를 재려고 만든 **대조군이라
-- 적재하지 않는다**(S15P21A506-211 결정 3-2). migration_pairs_regular_260914 는 이탈 비율
-- 보정용이고 .gitignore 에 있어 저장소에 없다 — 적재 입력으로 쓰면 재현되지 않는다.
--
--
-- ## 도착지는 왜 FK 가 아니라 이름인가
--
-- similar_package 는 양쪽 다 package_id FK 다. 이 표는 다르다.
--
-- similar_package 의 후보는 **우리가 고른 것**이라 상세 화면이 반드시 있어야 한다. 이동쌍은
-- **관측된 사실**이라 우리 package 표에 없는 곳으로도 간다. 2026-09-22 로컬 실측에서 도착지
-- 327쌍이 package 에 없었고, 그중 61건은 기본 필터를 통과하면서 출발 패키지의 상위 5 안에
-- 든다(출발 패키지 55개, 점유율 100% 인 것 포함).
--
-- **도착지에 FK 를 걸면 그 55개 패키지는 1위가 통째로 빠진 분포를 보게 된다.** 유일한
-- 도착지가 빠지면 "이동 기록 없음" 으로까지 잘못 읽힌다. 사실을 지우는 쪽이 거짓이 크다.
--
-- 그래서 도착지는 이름으로 둔다. 상세로 링크해야 하면 API 가 name 으로 조인한다 — id 를
-- 적재 시점에 박아 두는 것보다 낫다. 그때그때 최신 package 를 보기 때문이다.
--
-- 출발 쪽은 FK 다. 조회가 package_id 로 들어오므로 package 에 없는 출발 패키지(489쌍)는
-- 어차피 닿지 않는다.

CREATE TABLE "migration_pair" (
    "from_package_id"   INT NOT NULL,
    "to_package_name"   VARCHAR(300) NOT NULL,
    "dep_kind"          VARCHAR(16) NOT NULL,
    "votes"             NUMERIC(10,1) NOT NULL,
    "co_events"         INT NOT NULL,
    "removal_events"    INT NOT NULL,
    "publisher_months"  INT NOT NULL,
    "dependents"        INT NOT NULL,
    "a_pct"             NUMERIC(5,2) NOT NULL,
    "b_pct"             NUMERIC(6,4) NOT NULL,
    "lift"              NUMERIC(14,1) NOT NULL,
    "share_pct"         NUMERIC(4,1) NOT NULL,
    "share_pm_pct"      NUMERIC(4,1) NOT NULL,
    "bidirectional"     BOOLEAN NOT NULL,
    "first_seen"        DATE NOT NULL,
    "last_seen"         DATE NOT NULL,
    "snapshot_at"       DATE NOT NULL
);

COMMENT ON TABLE  "migration_pair"
    IS '관측된 교체 흐름 — X 를 빼고 Y 를 넣은 쌍 (확장-02). 단위는 쌍이다';
COMMENT ON COLUMN "migration_pair"."to_package_name"
    IS '도착 패키지 이름. package 에 없을 수 있다 — FK 가 아닌 이유는 파일 머리말 참고';
COMMENT ON COLUMN "migration_pair"."dep_kind"
    IS '의존 종류이자 원천. regular=deps.dev 전수 · dev=registry 상위 10만. 모집단이 달라 합치지 않는다';
COMMENT ON COLUMN "migration_pair"."votes"
    IS '한 전이에서 함께 들어온 후보가 k 개면 1/k 씩 나눠 준 표의 합. 건수가 아니다';
COMMENT ON COLUMN "migration_pair"."co_events"
    IS 'X 를 빼면서 Y 를 넣은 전이 수. votes 와 달리 나누지 않은 건수';
COMMENT ON COLUMN "migration_pair"."removal_events"
    IS 'X 를 뺀 전이 수 전체. 이 쌍의 분모다';
COMMENT ON COLUMN "migration_pair"."publisher_months"
    IS '서로 다른 (배포주체, 달) 조합 수. 한 조직의 일괄 변경을 걸러 내는 핵심 값이다';
COMMENT ON COLUMN "migration_pair"."dependents"
    IS '이 이동을 한 의존자 수(중복 접음)';
COMMENT ON COLUMN "migration_pair"."a_pct"
    IS 'co_events / removal_events × 100. X 를 뺀 사람 중 Y 를 넣은 비율';
COMMENT ON COLUMN "migration_pair"."b_pct"
    IS '모집단에서 Y 가 추가되는 기준율 × 100. lift 의 분모';
COMMENT ON COLUMN "migration_pair"."lift"
    IS 'a_pct / b_pct. 우연 대비 몇 배인가. **모집단이 다르면 절댓값을 비교할 수 없다**';
COMMENT ON COLUMN "migration_pair"."share_pct"
    IS '출발 패키지의 표 합 중 이 도착지 비율. 라벨 필터용이며 화면에는 쓰지 않는다';
COMMENT ON COLUMN "migration_pair"."share_pm_pct"
    IS '조직·달 수 기준 점유율. **화면 점유율은 이것을 쓴다**(S15P21A506-136 3번)';
COMMENT ON COLUMN "migration_pair"."bidirectional"
    IS '(Y, X) 쌍도 loose 를 통과한다. 같은 물건의 두 포장(lodash↔lodash-es)일 수 있어 지우지 않고 변종으로 표시한다';
COMMENT ON COLUMN "migration_pair"."first_seen" IS '이 이동이 처음 관측된 날';
COMMENT ON COLUMN "migration_pair"."last_seen"  IS '마지막으로 관측된 날';
COMMENT ON COLUMN "migration_pair"."snapshot_at"
    IS '이 회차가 어디까지 본 원천인지. dep_kind 로 정해지는 상수이며 두 원천이 서로 다르다';

-- ## 기준일이 행마다 있는 이유, 그리고 last_seen 이 그것을 넘는 이유
--
-- **두 원천의 기준일이 다르다**(S15P21A506-211 결정 3-4). regular 는 deps.dev 2026-08-31
-- 스냅샷, dev 는 npm registry 수집분이 담은 2026-09-16 까지다. 응답에 기준일을 반드시 싣는
-- 계약(기능-08-R02)이라 조회가 조인 없이 끝나야 해서 행마다 둔다 — dependent_transition 이
-- t1·t2 를 행마다 두는 것과 같은 판단이고, 2.3만 행이라 비용이 없다.
--
-- **last_seen > snapshot_at 인 행이 있다. 오류가 아니다.**
--
--   regular  최대 2026-09-01. deps.dev 추출이 UTC 자정을 세 시간 넘겨 돌아 2026-09-01
--            00:00~02:49 발행분 1,213행이 08-31 파티션에 섞였다(dependent_transitions
--            README §6-5 에 원인과 영향이 실측돼 있다). **사고다**
--   dev      최대 2026-09-16. registry 수집은 스냅샷이 아니라 수집 시점까지의 이력을
--            받아 오므로 그 범위가 곧 자료다(migration_pairs_dev_260914/README.md:164).
--            **정상이다**
--
-- 그래서 CHECK (last_seen <= snapshot_at) 을 두지 않는다. 두면 정상 자료가 막힌다.
-- 대신 적재기가 넘는 행 수를 세어 quality 에 남긴다 — 다음 회차에서 갑자기 늘면 추출이
-- 또 샌 것이다.

-- 조회는 (from_package_id, dep_kind) 로 들어오고 비교 대상이 최대 3개이므로 IN 조회다.
-- PK 선두 두 열이 그 순서를 덮으므로 별도 인덱스를 두지 않는다.
ALTER TABLE "migration_pair"
ADD CONSTRAINT "PK_MIGRATION_PAIR"
PRIMARY KEY ("from_package_id", "dep_kind", "to_package_name");

ALTER TABLE "migration_pair"
ADD CONSTRAINT "FK_PACKAGE_MIGRATION_PAIR"
FOREIGN KEY ("from_package_id")
REFERENCES "package" ("package_id");

-- 원천을 늘릴 때는 이 제약과 적재기의 SOURCES 를 함께 고친다. 모르는 값이 들어오면
-- 화면이 모집단이 다른 둘을 같은 그림에 겹치게 된다.
ALTER TABLE "migration_pair"
ADD CONSTRAINT "CK_MIGRATION_PAIR_DEP_KIND"
CHECK ("dep_kind" IN ('regular', 'dev'));

-- 도착지가 빈 이름이면 화면이 이름 없는 막대를 그린다. 출발 쪽은 FK 가 막아 주지만
-- 도착 쪽은 이름뿐이라 여기서 본다. (자기 자신으로 가는 이동은 CHECK 로 볼 수 없어 —
-- package 를 조인해야 한다 — 적재기가 검산한다.)
ALTER TABLE "migration_pair"
ADD CONSTRAINT "CK_MIGRATION_PAIR_TO_NAME"
CHECK ("to_package_name" <> '');

-- loose 계약(lift>=5 AND votes>=3). 이보다 약한 쌍이 들어오면 적재 입력이 all 이 아닌 것이다.
ALTER TABLE "migration_pair"
ADD CONSTRAINT "CK_MIGRATION_PAIR_LOOSE"
CHECK ("lift" >= 5 AND "votes" >= 3);

-- **여기가 열 밀림을 잡는 자리다.** 빌더 안에서는 같은 CTE 에서 나온 값이라 언제나 참이지만,
-- 적재는 CSV 를 열 순서로 읽으므로 짝을 잘못 지으면 깨진다. V9 의 SPLIT CHECK 와 같은 판단이다.
--
--   votes <= co_events        표는 건수를 1/k 로 나눈 합이라 건수를 넘을 수 없다
--   co_events <= removal_events  X 를 빼면서 Y 를 넣은 전이는 X 를 뺀 전이의 부분집합이다
--
-- 2026-09-22 실측에서 두 데이터셋 23,629행 전부가 이 둘을 지킨다.
ALTER TABLE "migration_pair"
ADD CONSTRAINT "CK_MIGRATION_PAIR_UNITS"
CHECK ("votes" <= "co_events" AND "co_events" <= "removal_events");

-- 건수·조직 수는 0 일 수 없다. 행이 있다는 것 자체가 한 번은 일어났다는 뜻이다.
ALTER TABLE "migration_pair"
ADD CONSTRAINT "CK_MIGRATION_PAIR_COUNTS"
CHECK ("co_events" > 0 AND "removal_events" > 0
       AND "publisher_months" > 0 AND "dependents" > 0);

-- 백분율 열은 0~100 이다. b_pct 는 모집단 기준율이라 실측 최댓값이 0.1065 로 아주 작다.
ALTER TABLE "migration_pair"
ADD CONSTRAINT "CK_MIGRATION_PAIR_PCT_RANGE"
CHECK ("a_pct" >= 0 AND "a_pct" <= 100
       AND "b_pct" >= 0 AND "b_pct" <= 100
       AND "share_pct" >= 0 AND "share_pct" <= 100
       AND "share_pm_pct" >= 0 AND "share_pm_pct" <= 100);

ALTER TABLE "migration_pair"
ADD CONSTRAINT "CK_MIGRATION_PAIR_RANGE"
CHECK ("first_seen" <= "last_seen");
