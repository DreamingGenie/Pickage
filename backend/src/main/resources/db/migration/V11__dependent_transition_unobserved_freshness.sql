-- 관측불가를 마지막 대표 릴리스의 신선도로 분해 (S15P21A506-421)
--
-- V8 의 `unobserved` 한 덩어리에 성격이 다른 둘이 섞여 있다.
--
--   "작년에도 재작년에도 릴리스를 냈는데 마침 이 구간에만 없었다"  — 잠시 쉬는 중
--   "5년째 아무것도 안 나온다"                                    — 사실상 죽은 프로젝트
--
-- 같은 칸에 두면 받는 쪽이 "이 패키지를 쓰는 사람들이 살아 있는가" 를 판단할 수 없다.
-- npm 전수 406만 중 33.8% 가 마지막 릴리스 5년 초과다.
--
-- 분해 기준은 그 의존자의 **마지막 대표 릴리스가 t2 에서 얼마나 떨어져 있는가** 이고,
-- 경계(3년·5년)는 파이프라인이 period 프리셋에서 그대로 가져다 쓴다
-- (`pipeline/duckdb/build_dependent_transitions.py` 의 `FRESHNESS_CUTS`).
--
-- **구간마다 의미 있는 칸이 다르다.** 관측불가는 (t1, t2] 안에 대표 릴리스가 없다는 뜻이고
-- 경계가 구간 길이와 같은 값이므로, 구간이 길수록 앞쪽 칸이 정의상 비어 버린다.
-- 아래 CK_..._UNOBSERVED_PERIOD 가 그것을 강제한다.
--
--   1y   recent(1~3년 전) · stale · dormant 셋 다 나온다
--   3y   recent 는 언제나 0
--   5y   recent·stale 이 언제나 0 이고 dormant = unobserved
--
-- **이 분해는 관측불가를 줄이지 않는다.** 같은 수를 더 잘 설명할 뿐이다.

-- **왜 NOT NULL 이 아닌가 — 배포와 재적재 사이의 창 때문이다.**
--
-- 이 표는 전량 교체로만 갱신된다(pipeline/dependent_transitions/load.py). 그런데 마이그레이션은
-- 백엔드 배포에 붙어 먼저 돌고, 그 시점에 표에는 세 값을 모르는 88만 행이 이미 들어 있다.
--
--   DEFAULT 0 을 주면   → 아래 합계 CHECK 가 그 자리에서 깨진다. CHECK 를 포기하면
--                        "5년 넘게 방치된 의존자가 0명" 이 응답에 실린다. 숫자가 맞아 보여서
--                        틀린 줄 아무도 모르는 종류다
--   NULL 로 두면        → 조회가 "아직 모른다" 를 그대로 내려보낼 수 있다
--
-- OUT_OF_SCOPE 가 0 이 아니라 null 을 주는 것과 같은 판단이다(TransitionsResponse).
-- 재적재가 끝나면 세 값이 모두 채워지고, 그 뒤로 NULL 인 행은 생기지 않는다.
ALTER TABLE "dependent_transition"
    ADD COLUMN "unobserved_recent"  INT,
    ADD COLUMN "unobserved_stale"   INT,
    ADD COLUMN "unobserved_dormant" INT;

COMMENT ON COLUMN "dependent_transition"."unobserved_recent"
    IS '관측불가 중 마지막 대표 릴리스가 t2 기준 3년 안. 3y·5y 구간에서는 정의상 0';
COMMENT ON COLUMN "dependent_transition"."unobserved_stale"
    IS '관측불가 중 마지막 대표 릴리스가 t2 기준 3~5년 전. 5y 구간에서는 정의상 0';
COMMENT ON COLUMN "dependent_transition"."unobserved_dormant"
    IS '관측불가 중 마지막 대표 릴리스가 t2 기준 5년 초과. 사실상 방치된 프로젝트다';

-- **파이프라인에서는 검산이 못 되던 식이 여기서는 의미가 있다** — V9 의 SPLIT 과 같은 이유다.
-- 빌더 안에서는 CASE 가 한 행을 한 칸에만 넣으므로 이 등식이 언제나 참이라 아무것도 잡지
-- 못한다. 그러나 적재 경로는 CSV 를 거쳐 **열 순서로** 들어오므로, 열을 잘못 짝지으면 깨진다.
--
-- 셋 다 NULL 인 경우를 허용하는 것이 위에 적은 배포 창이다. 셋 중 일부만 NULL 인 상태는
-- 허용하지 않는다 — 그건 적재기가 열을 빠뜨렸다는 뜻이다.
ALTER TABLE "dependent_transition"
ADD CONSTRAINT "CK_DEPENDENT_TRANSITION_UNOBSERVED_SPLIT"
CHECK (("unobserved_recent" IS NULL AND "unobserved_stale" IS NULL
        AND "unobserved_dormant" IS NULL)
    OR ("unobserved_recent" >= 0 AND "unobserved_stale" >= 0 AND "unobserved_dormant" >= 0
        AND "unobserved_recent" + "unobserved_stale" + "unobserved_dormant" = "unobserved"));

-- 합계만 보면 **세 열을 서로 바꿔 넣어도 통과한다.** 순서가 어긋나는 사고를 실제로 잡으려면
-- 열마다 다른 성질이 필요한데, 구간별로 비어 있어야 하는 칸이 그것이다.
--
-- 관측불가는 (t1, t2] 안에 대표 릴리스가 없다는 뜻이고 신선도 경계가 구간 길이와 같은 값이므로,
-- 3y 에서 "최근 3년 안" 은 존재할 수 없다. 5y 도 같은 이유로 recent·stale 이 없다.
-- 파이프라인의 `impossible_freshness` 검산과 같은 규칙을 DB 가 다시 강제한다.
--
-- **프리셋이나 신선도 경계를 바꾸면 이 제약도 함께 고친다.** 둘이 어긋나면 적재가 여기서
-- 막히는데, 그때 제약을 지우지 말고 어느 쪽이 맞는지부터 정할 것 — 경계와 구간이 다른 값이면
-- 화면의 "이 기간에 릴리스 없음" 과 분해가 서로 다른 시간을 말하게 된다.
ALTER TABLE "dependent_transition"
ADD CONSTRAINT "CK_DEPENDENT_TRANSITION_UNOBSERVED_PERIOD"
CHECK ("unobserved_recent" IS NULL
    OR ("period" = '1y')
    OR ("period" = '3y' AND "unobserved_recent" = 0)
    OR ("period" = '5y' AND "unobserved_recent" = 0 AND "unobserved_stale" = 0));
