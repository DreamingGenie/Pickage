-- 구간별 이탈 사유 (S15P21A506-378 계산 → S15P21A506-396 적재·조회)
--
-- "X 를 뺀 사람들이 그 자리에 다른 것을 넣었나, 그냥 뺐나". 대상 패키지 하나가 구간마다
-- 한 행을 갖는다. 약 9.9만 행.
--
-- dependent_transition 과 **다른 표다. 합치면 안 된다.**
--
--   dependent_transition   시점 두 개의 선언 집합을 비교한다.  단위 = 패키지 수
--   dependent_removal_reason  연속한 두 릴리스를 처음부터 훑는다. 단위 = 전이 건수
--
-- outflow 는 "T1 엔 쓰고 T2 엔 안 쓰는 패키지가 몇 개인가" 이고 removals 는 "그 사이 빼는
-- 행위가 몇 번 있었나" 다. 한 의존자가 뺐다 넣었다 다시 뺐으면 앞은 1, 뒤는 2다.
-- **같은 응답 객체에 담으면 받는 쪽이 반드시 더하거나 나눈다.** 그래서 조회도 별도
-- 엔드포인트이고 응답에 unit 을 값으로 싣는다 — 주석이 아니라 필드로.
--
-- 왜 이 구분이 필요한가: 화면은 지금 "1,310개가 떠났다" 까지만 말하고 **왜** 는 답하지
-- 못한다. 대체를 동반한 이탈과 아무것도 안 넣은 이탈을 가르면 "버려지고 있다" 와
-- "필요가 없어졌다" 가 갈린다. 실측상 제거 셋 중 둘이 대체 없이 일어나고, 이 비율은
-- 구간과 거의 무관하다 (1y 67.8% · 3y 70.1% · 5y 69.4% · 전 기간 68.1%).
--
-- **적재 범위는 dependent_transition 이 정한다.** 계산 자체는 X 13.2만 종을 내지만
-- (27.4만 행), 그중 유지·유입·이탈 대상 안에 드는 것만 넣는다(4.3만 종 · 9.9만 행).
-- 두 패널이 한 화면에 함께 뜨므로 범위가 다르면 한쪽은 숫자를, 다른 쪽은 "범위 밖"을
-- 말하게 된다 — 2026-09-18 @opentiny/vue-theme-mobile 로 실제로 확인했다.
-- 적재기는 그 목록을 따로 들고 있지 않고 dependent_transition 을 조인해서 얻는다.
-- 목록을 복사해 두면 한쪽만 다시 돌렸을 때 커버리지가 조용히 어긋난다.
--
-- t1·t2 도 같은 이유로 dependent_transition 에서 가져온다. 원천 parquet 에는 이 두 열이
-- 없는데, 여기에 날짜를 다시 적으면 다음 스냅샷에서 한쪽만 고쳐지고 두 지표가 서로 다른
-- 구간을 같은 이름(3y)으로 부르게 된다. 그 어긋남은 검산에 걸리지 않는다 — 각자
-- 내부적으로는 앞뒤가 맞기 때문이다. **이 에픽에서 같은 종류를 이미 두 번 고쳤다.**

CREATE TABLE "dependent_removal_reason" (
    "package_id"       INT NOT NULL,
    "period"           VARCHAR(8) NOT NULL,
    "removals"         INT NOT NULL,
    "no_replacement"   INT NOT NULL,
    "with_replacement" INT NOT NULL,
    "dependents"       INT NOT NULL,
    "t1"               TIMESTAMP NOT NULL,
    "t2"               TIMESTAMP NOT NULL
);

COMMENT ON TABLE  "dependent_removal_reason"
    IS '구간별 이탈 사유 — 대체 동반/대체 없음 (기능-08). 단위는 전이 건수다';
COMMENT ON COLUMN "dependent_removal_reason"."period"
    IS '구간 프리셋. 1y · 3y · 5y. dependent_transition 과 같은 값이며 같은 t2 에서 끝난다';
COMMENT ON COLUMN "dependent_removal_reason"."removals"
    IS 'X 를 뺀 전이의 수. 패키지 수가 아니다 — 한 의존자가 여러 번 빼면 여러 건이다';
COMMENT ON COLUMN "dependent_removal_reason"."no_replacement"
    IS '뺀 릴리스에서 아무것도 새로 넣지 않은 전이';
COMMENT ON COLUMN "dependent_removal_reason"."with_replacement"
    IS '뺀 릴리스에서 다른 것을 함께 넣은 전이. 같은 자리의 대체라는 보장은 없다';
COMMENT ON COLUMN "dependent_removal_reason"."dependents"
    IS 'X 를 뺀 적 있는 의존자 수(중복 접음). removals 와 단위가 다르므로 나누지 말 것';
COMMENT ON COLUMN "dependent_removal_reason"."t1"  IS '구간 시작. period 로 정해지는 상수';
COMMENT ON COLUMN "dependent_removal_reason"."t2"  IS '구간 끝 = 원천 스냅샷 날짜. 오늘이 아니다';

-- 조회는 (package_id, period) 로 들어온다. 비교 대상이 최대 3개이므로 IN 조회다.
-- dependent_transition 과 달리 kind 차원이 없다 — 원천이 선언 종류를 나누지 않는다.
ALTER TABLE "dependent_removal_reason"
ADD CONSTRAINT "PK_DEPENDENT_REMOVAL_REASON"
PRIMARY KEY ("package_id", "period");

ALTER TABLE "dependent_removal_reason"
ADD CONSTRAINT "FK_PACKAGE_DEPENDENT_REMOVAL_REASON"
FOREIGN KEY ("package_id")
REFERENCES "package" ("package_id");

-- 프리셋 밖의 값이 들어오면 화면이 모르는 구간을 그리게 된다. 프리셋을 늘릴 때는
-- 이 제약과 dependent_transition 의 같은 제약, 파이프라인의 PERIODS 를 함께 고친다.
ALTER TABLE "dependent_removal_reason"
ADD CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_PERIOD"
CHECK ("period" IN ('1y', '3y', '5y'));

-- 건수를 센 것이라 음수가 될 수 없다. removals 는 이 표에 행이 있다는 것 자체가
-- "한 번은 빠졌다" 는 뜻이므로 0 일 수 없다 (2026-09-18 실측에서도 0 건이 없다).
ALTER TABLE "dependent_removal_reason"
ADD CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_COUNTS"
CHECK ("removals" > 0 AND "no_replacement" >= 0 AND "with_replacement" >= 0
       AND "dependents" > 0);

-- **파이프라인에서는 검산이 못 되던 식이 여기서는 의미가 있다.**
-- 빌더 안에서는 두 FILTER 가 같은 조건을 갈라 쓰므로 이 등식이 언제나 참이라
-- 아무것도 잡아내지 못한다(S15P21A506-378 에서 그래서 단조성 검산으로 바꿨다).
-- 그러나 적재 경로는 CSV 를 거쳐 열 순서로 들어오므로, 열을 잘못 짝지으면 깨진다.
-- 경계에서 다시 확인하는 값이 있다.
ALTER TABLE "dependent_removal_reason"
ADD CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_SPLIT"
CHECK ("no_replacement" + "with_replacement" = "removals");

-- 한 의존자가 여러 번 뺄 수 있으므로 의존자 수는 전이 건수를 넘을 수 없다.
-- 이 부등식이 두 열의 단위가 다르다는 것을 스키마에 남긴다.
ALTER TABLE "dependent_removal_reason"
ADD CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_DEPENDENTS"
CHECK ("dependents" <= "removals");

ALTER TABLE "dependent_removal_reason"
ADD CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_RANGE"
CHECK ("t1" < "t2");
