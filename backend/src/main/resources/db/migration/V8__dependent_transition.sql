-- 유지·유입·이탈 (S15P21A506-195 계산 → S15P21A506-361 적재·조회)
--
-- "X 를 쓰던 사람들이 이 구간에 어떻게 움직였나". 대상 패키지 하나가 (구간 × 선언 종류)
-- 마다 한 행을 갖는다. 상위 10만 × 3 × 3 = 약 90만 행.
--
-- 요청 경로에 계산이 없다. 배치가 미리 접어 둔 것을 키 조회로 읽을 뿐이다 —
-- similar_package 와 같은 원칙이다. 구간을 프리셋으로 묶은 것이 이것을 가능하게 했다.
-- 임의 날짜를 받으면 요청마다 수천만 행을 집계해야 한다(react 하나가 의존자 19만).
--
-- **범주가 넷인 것이 이 표의 핵심이다.** 받는 쪽은 넷을 모두 화면에 내야 한다.
--   retained   유지     — 구간 안에 릴리스를 내면서도 계속 선언했다
--   inflow     유입     — T1 엔 없고 T2 엔 있다
--   outflow    이탈     — T1 엔 있고 T2 엔 없다
--   unobserved 관측불가 — 양 끝에 선언이 있는데 구간 안에 대표 릴리스가 바뀌지 않았다.
--                         X 를 계속 쓰는지 뺐는지 **알 방법이 없다**
--
-- 관측 불가를 유지로 세면 숫자가 거짓이 된다. 1년 구간에서 전체의 75.3% 가 여기 들어가고,
-- 유지로 세면 유지율이 87.2% 가 아니라 98.8% 로 보인다(2026-09-17 실측).
--
-- inflow_new 는 inflow 의 **부분집합**이다. T1 때 아직 없던 패키지의 유입이라 채택이 아니라
-- 생태계 성장이다. 실측상 유입의 93.8~97.5% 가 여기다 — 합쳐 읽으면 npm 이 커진 것이
-- 그 패키지가 선택받은 것으로 둔갑한다.
--
-- 자세한 계약과 한계(devDependencies 없음·생존 편향·대상 밖)는
-- datasets/dependent_transitions_260917/README.md 에 있다.

CREATE TABLE "dependent_transition" (
    "package_id" INT NOT NULL,
    "period"     VARCHAR(8) NOT NULL,
    "kind"       VARCHAR(16) NOT NULL,
    "retained"   INT NOT NULL,
    "inflow"     INT NOT NULL,
    "inflow_new" INT NOT NULL,
    "outflow"    INT NOT NULL,
    "unobserved" INT NOT NULL,
    "t1"         TIMESTAMP NOT NULL,
    "t2"         TIMESTAMP NOT NULL
);

COMMENT ON TABLE  "dependent_transition"          IS '구간 양 끝의 dependent 선언 집합 비교 (기능-08)';
COMMENT ON COLUMN "dependent_transition"."period" IS '구간 프리셋. 1y · 3y · 5y';
COMMENT ON COLUMN "dependent_transition"."kind"   IS '선언 종류. regular · peer · optional';
COMMENT ON COLUMN "dependent_transition"."inflow_new"
    IS '유입 중 T1 때 아직 없던 패키지. inflow 의 부분집합이며 채택이 아니라 생태계 성장';
COMMENT ON COLUMN "dependent_transition"."unobserved"
    IS '구간 안에 대표 릴리스가 안 바뀌어 판정할 수 없는 dependent. 유지로 세면 안 된다';
-- t1·t2 는 period 로 완전히 결정되므로 값이 중복된다. 별도 표로 빼지 않은 것은 조회가
-- 조인 없이 끝나야 하고(응답에 기준일을 반드시 싣는다 — 기능-08-R02), 90만 행이라 해도
-- 14 MB 남짓이기 때문이다. similar_package 가 model_ver 를 행마다 두는 것과 같은 판단이다.
COMMENT ON COLUMN "dependent_transition"."t1"     IS '구간 시작. period 로 정해지는 상수';
COMMENT ON COLUMN "dependent_transition"."t2"     IS '구간 끝 = 원천 스냅샷 날짜. 오늘이 아니다';

-- 조회는 (package_id, period) 로 들어온다. 비교 대상이 최대 3개이므로 IN 조회다.
-- PK 가 그 순서를 덮으므로 별도 인덱스를 두지 않는다.
ALTER TABLE "dependent_transition"
ADD CONSTRAINT "PK_DEPENDENT_TRANSITION"
PRIMARY KEY ("package_id", "period", "kind");

ALTER TABLE "dependent_transition"
ADD CONSTRAINT "FK_PACKAGE_DEPENDENT_TRANSITION"
FOREIGN KEY ("package_id")
REFERENCES "package" ("package_id");

-- 프리셋 밖의 값이 들어오면 화면이 모르는 구간을 그리게 된다. 프리셋을 늘릴 때는
-- 이 제약과 파이프라인의 PERIOD_YEARS 를 함께 고친다.
ALTER TABLE "dependent_transition"
ADD CONSTRAINT "CK_DEPENDENT_TRANSITION_PERIOD"
CHECK ("period" IN ('1y', '3y', '5y'));

ALTER TABLE "dependent_transition"
ADD CONSTRAINT "CK_DEPENDENT_TRANSITION_KIND"
CHECK ("kind" IN ('regular', 'peer', 'optional'));

-- 네 범주는 사람 수를 센 것이라 음수가 될 수 없다.
ALTER TABLE "dependent_transition"
ADD CONSTRAINT "CK_DEPENDENT_TRANSITION_COUNTS"
CHECK ("retained" >= 0 AND "inflow" >= 0 AND "inflow_new" >= 0
       AND "outflow" >= 0 AND "unobserved" >= 0);

-- 파이프라인의 inflow_new_exceeds_inflow 검산과 같은 규칙을 DB 가 다시 강제한다.
-- 적재 경로가 열을 잘못 짝지으면 여기서 막힌다.
ALTER TABLE "dependent_transition"
ADD CONSTRAINT "CK_DEPENDENT_TRANSITION_INFLOW_NEW"
CHECK ("inflow_new" <= "inflow");

ALTER TABLE "dependent_transition"
ADD CONSTRAINT "CK_DEPENDENT_TRANSITION_RANGE"
CHECK ("t1" < "t2");
