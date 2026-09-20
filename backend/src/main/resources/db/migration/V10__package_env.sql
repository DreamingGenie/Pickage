-- 버전별 핵심 환경 정보 (기능-11-R01)
--
-- 확장 보고서 2페이지의 첫 결과 카드가 읽는 표다. 기능-12(AI 기능 비교)·기능-13(해설) 보다
-- 앞에 놓여, 생성된 문장이 앉을 검증 가능한 바닥을 깐다. 그래서 여기 들어가는 값은 전부
-- npm Registry 원문에서 그대로 읽히거나 원문으로부터 기계적으로 접힌 것이어야 한다.
--
-- 원천은 registry 수집기 09-16 회차(S15P21A506-366)다. 한 행 = 패키지 × 버전.
--
--   module_type + main + exports  ->  module_format
--   types (없으면 typings)         ->  types_bundled
--   Dependencies 길이              ->  direct_dependencies
--   PeerDependencies 길이          ->  peer_dependencies
--
-- **실행 조건(engines)은 이 표에 없다.** 기능-11-R01 은 항목으로 적고 있지만 수집에 포함되지
-- 않았다. 원본 문서를 보존하지 않아 재수집 외에 방법이 없다(상위 10만 약 4시간·73GB).
-- 그 행은 화면에 내지 않는다 — 완료 판단이 "확인된 정보만 표시" 이므로 빈 칸보다 없는 편이 맞다.
--
-- 설치 크기(unpacked_size)와 파일 수도 수집돼 있지만 넣지 않는다. 기능-11-R01 의 항목이
-- 아니고, 그 값은 패키지 자신의 tarball 만 푼 크기여서 의존성이 빠진다. "설치 크기" 로
-- 부르면 65 KB 짜리가 의존 8개를 끌고 오는 경우를 정반대로 말하게 된다.

CREATE TABLE "package_env" (
    "package_id"          INT          NOT NULL,
    "version"             VARCHAR(100) NOT NULL,
    "module_format"       VARCHAR(16)  NOT NULL,
    "types_bundled"       BOOLEAN      NOT NULL,
    "direct_dependencies" INT          NULL,
    "peer_dependencies"   INT          NULL
);

COMMENT ON TABLE "package_env"
    IS '버전별 소비 조건 — 모듈 방식·타입·의존 조건 (기능-11 첫 결과 카드)';

-- 판정은 적재기에서 하고 여기서는 값만 막는다. 순서가 곧 규칙이다.
--
--   1. 의존 네 배열이 전부 NULL(unpublish)      -> UNKNOWN
--   2. exports 안에 import 와 require 가 둘 다   -> ESM_CJS
--   3. module_type = 'module'                   -> ESM_ONLY
--   4. 그 밖                                     -> CJS
--
-- **module_type 이 NULL 인 것은 '모름' 이 아니라 commonjs 기본값이다.** 전수 기준 74.1% 가
-- NULL 이라, 모름으로 읽으면 대부분이 UNKNOWN 이 되어 표가 아무 말도 못 한다.
--
-- 듀얼 판정을 module_type 보다 먼저 보는 이유는, 양쪽을 다 내보내는 패키지가 type 을
-- module 로 적기도 하고 commonjs 로 적기도 하기 때문이다. 순서를 바꾸면 그런 것들이
-- ESM_ONLY 로 떨어져 CJS 프로젝트에서 못 쓰는 것처럼 보인다.
--
-- 타입 전용(@types/*)은 별도 값으로 두지 않았다. 6열만으로는 판정할 수 없다 —
-- main 이 없으면 npm 이 index.js 를 기본값으로 쓰므로 'main 없음'이 'JS 없음'이 아니다.
-- 실측(09-16 shard 5,000행)에서 main 없음 + types 있음 으로 잡은 1,963행 중 22행이
-- chalk·supports-color 처럼 런타임이 있는 패키지였다. 그래서 @types/* 도 CJS 로 떨어진다.
--
-- .mjs/.cjs 확장자로 형식이 갈리는 패키지는 여기서 못 본다. 파일 목록이 없어 type 과
-- exports 만 보기 때문이고, 오판이 아니라 관측 밖이다.
ALTER TABLE "package_env"
ADD CONSTRAINT "CK_PACKAGE_ENV_MODULE_FORMAT"
CHECK ("module_format" IN ('CJS', 'ESM_ONLY', 'ESM_CJS', 'UNKNOWN'));

COMMENT ON COLUMN "package_env"."module_format"
    IS '어떻게 불러오는가. CJS · ESM_ONLY · ESM_CJS(듀얼) · UNKNOWN(unpublish)';

-- types 또는 typings 가 있으면 참. types 만 보면 과소 계상한다 — ajv 는 typings 만 있는
-- 버전이 127개다.
--
-- 거짓의 뜻은 '타입이 없다' 가 아니라 '이 패키지 안에는 없다' 이다. @types/xxx 를 따로
-- 깔면 되므로 화면 문구는 '별도 설치 필요' 여야 한다.
COMMENT ON COLUMN "package_env"."types_bundled"
    IS '타입 선언이 패키지에 동봉됐는가. 거짓은 @types 별도 설치를 뜻하며 타입 없음이 아니다';

-- 개수 둘은 NULL 을 허용한다. unpublish 된 버전은 의존 배열이 통째로 NULL(모름)이고,
-- 0(의존 없음)으로 적으면 거짓이 된다. 같은 실수가 이동쌍 검증에서 641건 과대 계상으로
-- 실제로 났다.
ALTER TABLE "package_env"
ADD CONSTRAINT "CK_PACKAGE_ENV_COUNTS"
CHECK (("direct_dependencies" IS NULL OR "direct_dependencies" >= 0)
       AND ("peer_dependencies" IS NULL OR "peer_dependencies" >= 0));

-- 둘을 한 숫자로 합치지 않는다. dependencies 는 깔면 자동으로 따라오고,
-- peerDependencies 는 사용자가 이미 갖고 있어야 하는 조건이다. 버전이 안 맞으면 설치가
-- 막히거나 경고가 난다 — 합치면 '따라오는 것' 과 '내가 맞춰야 하는 것' 이 섞여 둘 다 못 읽는다.
--
-- 전이 의존이 아니다. express 가 31개라고 나와도 실제로 깔리는 것은 수백 개다. MVP 는
-- 직접 의존만 다룬다(요구사항 명세서 33·76행). 화면 라벨에 '직접' 을 반드시 붙인다.
COMMENT ON COLUMN "package_env"."direct_dependencies"
    IS 'dependencies 선언 수. 전이 포함 아님. NULL 은 unpublish 라 모름이며 0 이 아니다';
COMMENT ON COLUMN "package_env"."peer_dependencies"
    IS 'peerDependencies 선언 수. 사용자가 직접 맞춰야 하는 조건. NULL 은 모름';

-- 조회는 카드가 (package_id, version) 으로 정확히 한 행을 집는다. 비교 대상이 최대 3개라
-- IN 조회이며 PK 가 그 순서를 덮으므로 별도 인덱스를 두지 않는다.
ALTER TABLE "package_env"
ADD CONSTRAINT "PK_PACKAGE_ENV"
PRIMARY KEY ("package_id", "version");

-- version 의 PK 가 (package_id, version) 이라 복합 FK 하나로 붙는다.
-- package_version_snapshot 이 같은 방식으로 붙어 있다.
--
-- registry 수집에는 있는데 version 에 없는 (이름, 버전) 은 붙일 수 없어 적재에서 빠진다.
-- 원천이 둘이기 때문이다 — version 은 deps.dev 스냅샷, 이 표는 registry 회차다.
-- 빠진 수를 조용히 넘기면 '왜 2,073만이 아니지' 가 되므로 적재기가 반드시 보고한다.
ALTER TABLE "package_env"
ADD CONSTRAINT "FK_VERSION_PACKAGE_ENV"
FOREIGN KEY ("package_id", "version")
REFERENCES "version" ("package_id", "version");
