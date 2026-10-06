--
-- PostgreSQL database dump
--

\restrict Wpdd8x5lOSa3GgJBQCcYdbaIL6pXNmC9OtTT1TK3aOawUivWV4BCWvUkzWktcVn

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vd193_reload_20260912_ready01; Type: SCHEMA; Schema: -; Owner: pickage
--

CREATE SCHEMA vd193_reload_20260912_ready01;


ALTER SCHEMA vd193_reload_20260912_ready01 OWNER TO pickage;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: available_package; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.available_package (
    package_id integer NOT NULL,
    package_name character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.available_package OWNER TO pickage;

--
-- Name: community_snapshot; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.community_snapshot (
    package_id integer NOT NULL,
    snapshot_id uuid NOT NULL,
    payload_version smallint NOT NULL,
    collected_at timestamp with time zone NOT NULL,
    data_status character varying(30) NOT NULL,
    result jsonb NOT NULL,
    CONSTRAINT "CK_COMMUNITY_SNAPSHOT_DATA_STATUS" CHECK (((data_status)::text = ANY ((ARRAY['AVAILABLE'::character varying, 'PARTIAL'::character varying, 'UNVERIFIED_REPOSITORY'::character varying, 'AMBIGUOUS_SCOPE'::character varying, 'UNSUPPORTED_HOST'::character varying, 'NO_DISCUSSION_DATA'::character varying])::text[]))),
    CONSTRAINT "CK_COMMUNITY_SNAPSHOT_PAYLOAD_VERSION" CHECK ((payload_version > 0)),
    CONSTRAINT "CK_COMMUNITY_SNAPSHOT_RESULT_OBJECT" CHECK ((jsonb_typeof(result) = 'object'::text))
);


ALTER TABLE public.community_snapshot OWNER TO pickage;

--
-- Name: COLUMN community_snapshot.package_id; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.community_snapshot.package_id IS '패키지당 최신 결과 한 행만 보관한다(PK). package 삭제 시 함께 지운다';


--
-- Name: COLUMN community_snapshot.snapshot_id; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.community_snapshot.snapshot_id IS '응답 버전 식별과 동시 갱신 결과 구분용. 원문·source ID는 여기 넣지 않는다';


--
-- Name: COLUMN community_snapshot.payload_version; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.community_snapshot.payload_version IS '배포 후 오래된 result JSON 형식을 안전하게 판별한다. 1부터 시작';


--
-- Name: COLUMN community_snapshot.collected_at; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.community_snapshot.collected_at IS '24시간 재사용·7일 제공·매시간 정리 배치 판정의 유일한 기준 시각';


--
-- Name: COLUMN community_snapshot.data_status; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.community_snapshot.data_status IS 'AVAILABLE·PARTIAL·UNVERIFIED_REPOSITORY·AMBIGUOUS_SCOPE·UNSUPPORTED_HOST·NO_DISCUSSION_DATA 중 하나. 일시적 외부 호출 실패·진행 중 상태는 이 테이블에 저장하지 않는다';


--
-- Name: COLUMN community_snapshot.result; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.community_snapshot.result IS '검증된 저장소 식별자·이슈 최대 2개·논의 흐름·대표 메시지·제한 사유. 원문 본문·댓글·prompt·hash는 넣지 않는다';


--
-- Name: dependent_removal_reason; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.dependent_removal_reason (
    package_id integer NOT NULL,
    period character varying(8) NOT NULL,
    removals integer NOT NULL,
    no_replacement integer NOT NULL,
    with_replacement integer NOT NULL,
    dependents integer NOT NULL,
    t1 timestamp without time zone NOT NULL,
    t2 timestamp without time zone NOT NULL,
    CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_COUNTS" CHECK (((removals > 0) AND (no_replacement >= 0) AND (with_replacement >= 0) AND (dependents > 0))),
    CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_DEPENDENTS" CHECK ((dependents <= removals)),
    CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_PERIOD" CHECK (((period)::text = ANY ((ARRAY['1y'::character varying, '3y'::character varying, '5y'::character varying])::text[]))),
    CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_RANGE" CHECK ((t1 < t2)),
    CONSTRAINT "CK_DEPENDENT_REMOVAL_REASON_SPLIT" CHECK (((no_replacement + with_replacement) = removals))
);


ALTER TABLE public.dependent_removal_reason OWNER TO pickage;

--
-- Name: TABLE dependent_removal_reason; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON TABLE public.dependent_removal_reason IS '구간별 이탈 사유 — 대체 동반/대체 없음 (기능-08). 단위는 전이 건수다';


--
-- Name: COLUMN dependent_removal_reason.period; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_removal_reason.period IS '구간 프리셋. 1y · 3y · 5y. dependent_transition 과 같은 값이며 같은 t2 에서 끝난다';


--
-- Name: COLUMN dependent_removal_reason.removals; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_removal_reason.removals IS 'X 를 뺀 전이의 수. 패키지 수가 아니다 — 한 의존자가 여러 번 빼면 여러 건이다';


--
-- Name: COLUMN dependent_removal_reason.no_replacement; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_removal_reason.no_replacement IS '뺀 릴리스에서 아무것도 새로 넣지 않은 전이';


--
-- Name: COLUMN dependent_removal_reason.with_replacement; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_removal_reason.with_replacement IS '뺀 릴리스에서 다른 것을 함께 넣은 전이. 같은 자리의 대체라는 보장은 없다';


--
-- Name: COLUMN dependent_removal_reason.dependents; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_removal_reason.dependents IS 'X 를 뺀 적 있는 의존자 수(중복 접음). removals 와 단위가 다르므로 나누지 말 것';


--
-- Name: COLUMN dependent_removal_reason.t1; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_removal_reason.t1 IS '구간 시작. period 로 정해지는 상수';


--
-- Name: COLUMN dependent_removal_reason.t2; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_removal_reason.t2 IS '구간 끝 = 원천 스냅샷 날짜. 오늘이 아니다';


--
-- Name: dependent_transition; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.dependent_transition (
    package_id integer NOT NULL,
    period character varying(8) NOT NULL,
    kind character varying(16) NOT NULL,
    retained integer NOT NULL,
    inflow integer NOT NULL,
    inflow_new integer NOT NULL,
    outflow integer NOT NULL,
    unobserved integer NOT NULL,
    t1 timestamp without time zone NOT NULL,
    t2 timestamp without time zone NOT NULL,
    unobserved_recent integer,
    unobserved_stale integer,
    unobserved_dormant integer,
    CONSTRAINT "CK_DEPENDENT_TRANSITION_COUNTS" CHECK (((retained >= 0) AND (inflow >= 0) AND (inflow_new >= 0) AND (outflow >= 0) AND (unobserved >= 0))),
    CONSTRAINT "CK_DEPENDENT_TRANSITION_INFLOW_NEW" CHECK ((inflow_new <= inflow)),
    CONSTRAINT "CK_DEPENDENT_TRANSITION_KIND" CHECK (((kind)::text = ANY ((ARRAY['regular'::character varying, 'peer'::character varying, 'optional'::character varying])::text[]))),
    CONSTRAINT "CK_DEPENDENT_TRANSITION_PERIOD" CHECK (((period)::text = ANY ((ARRAY['1y'::character varying, '3y'::character varying, '5y'::character varying])::text[]))),
    CONSTRAINT "CK_DEPENDENT_TRANSITION_RANGE" CHECK ((t1 < t2)),
    CONSTRAINT "CK_DEPENDENT_TRANSITION_UNOBSERVED_PERIOD" CHECK (((unobserved_recent IS NULL) OR ((period)::text = '1y'::text) OR (((period)::text = '3y'::text) AND (unobserved_recent = 0)) OR (((period)::text = '5y'::text) AND (unobserved_recent = 0) AND (unobserved_stale = 0)))),
    CONSTRAINT "CK_DEPENDENT_TRANSITION_UNOBSERVED_SPLIT" CHECK ((((unobserved_recent IS NULL) AND (unobserved_stale IS NULL) AND (unobserved_dormant IS NULL)) OR ((unobserved_recent >= 0) AND (unobserved_stale >= 0) AND (unobserved_dormant >= 0) AND (((unobserved_recent + unobserved_stale) + unobserved_dormant) = unobserved))))
);


ALTER TABLE public.dependent_transition OWNER TO pickage;

--
-- Name: TABLE dependent_transition; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON TABLE public.dependent_transition IS '구간 양 끝의 dependent 선언 집합 비교 (기능-08)';


--
-- Name: COLUMN dependent_transition.period; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.period IS '구간 프리셋. 1y · 3y · 5y';


--
-- Name: COLUMN dependent_transition.kind; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.kind IS '선언 종류. regular · peer · optional';


--
-- Name: COLUMN dependent_transition.inflow_new; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.inflow_new IS '유입 중 T1 때 아직 없던 패키지. inflow 의 부분집합이며 채택이 아니라 생태계 성장';


--
-- Name: COLUMN dependent_transition.unobserved; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.unobserved IS '구간 안에 대표 릴리스가 안 바뀌어 판정할 수 없는 dependent. 유지로 세면 안 된다';


--
-- Name: COLUMN dependent_transition.t1; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.t1 IS '구간 시작. period 로 정해지는 상수';


--
-- Name: COLUMN dependent_transition.t2; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.t2 IS '구간 끝 = 원천 스냅샷 날짜. 오늘이 아니다';


--
-- Name: COLUMN dependent_transition.unobserved_recent; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.unobserved_recent IS '관측불가 중 마지막 대표 릴리스가 t2 기준 3년 안. 3y·5y 구간에서는 정의상 0';


--
-- Name: COLUMN dependent_transition.unobserved_stale; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.unobserved_stale IS '관측불가 중 마지막 대표 릴리스가 t2 기준 3~5년 전. 5y 구간에서는 정의상 0';


--
-- Name: COLUMN dependent_transition.unobserved_dormant; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.dependent_transition.unobserved_dormant IS '관측불가 중 마지막 대표 릴리스가 t2 기준 5년 초과. 사실상 방치된 프로젝트다';


--
-- Name: etl_dataset_current; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.etl_dataset_current (
    dataset character varying(100) NOT NULL,
    execution_id character varying(200) NOT NULL,
    snapshot_at date NOT NULL,
    manifest_sha256 character varying(64) NOT NULL,
    manifest jsonb NOT NULL,
    published_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


ALTER TABLE public.etl_dataset_current OWNER TO pickage;

--
-- Name: TABLE etl_dataset_current; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON TABLE public.etl_dataset_current IS 'DB에 원자적으로 게시한 dataset별 현재 입력. MinIO _current.json과 별도';


--
-- Name: etl_load_attempt; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.etl_load_attempt (
    attempt_id character varying(200) NOT NULL,
    execution_id character varying(200) NOT NULL,
    status character varying(20) NOT NULL,
    phase character varying(50) NOT NULL,
    actual_counts jsonb DEFAULT '{}'::jsonb NOT NULL,
    quality_report jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    completed_at timestamp with time zone,
    validation_contract_sha256 character varying(64),
    CONSTRAINT etl_load_attempt_check CHECK (((((status)::text = 'PREPARING'::text) AND (completed_at IS NULL)) OR (((status)::text <> 'PREPARING'::text) AND (completed_at IS NOT NULL)))),
    CONSTRAINT etl_load_attempt_status_check CHECK (((status)::text = ANY ((ARRAY['PREPARING'::character varying, 'FAILED'::character varying, 'PUBLISHED'::character varying, 'REVERIFIED'::character varying])::text[]))),
    CONSTRAINT etl_load_attempt_validation_contract_sha256_check CHECK (((validation_contract_sha256)::text ~ '^[0-9a-f]{64}$'::text))
);


ALTER TABLE public.etl_load_attempt OWNER TO pickage;

--
-- Name: COLUMN etl_load_attempt.validation_contract_sha256; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.etl_load_attempt.validation_contract_sha256 IS '이번 시도에서 검증한 코드·스키마 계약. 최초 게시 execution.contract_sha256은 보존';


--
-- Name: etl_load_execution; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.etl_load_execution (
    execution_id character varying(200) NOT NULL,
    dataset character varying(100) NOT NULL,
    status character varying(20) NOT NULL,
    snapshot_at date,
    snapshot_timestamp timestamp without time zone,
    curated_run_id character varying(200),
    run_prefix text NOT NULL,
    manifest_sha256 character varying(64) NOT NULL,
    contract_sha256 character varying(64) NOT NULL,
    input_metadata jsonb NOT NULL,
    expected_counts jsonb NOT NULL,
    actual_counts jsonb,
    error_message text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    active_attempt_id character varying(200) NOT NULL,
    CONSTRAINT ck_etl_execution_snapshot_scope CHECK (((((dataset)::text = 'snapshot-reference'::text) AND (snapshot_at IS NULL) AND (snapshot_timestamp IS NULL) AND (curated_run_id IS NULL)) OR (((dataset)::text <> 'snapshot-reference'::text) AND (snapshot_at IS NOT NULL) AND (snapshot_timestamp IS NOT NULL) AND (curated_run_id IS NOT NULL)))),
    CONSTRAINT etl_load_execution_contract_sha256_check CHECK (((contract_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT etl_load_execution_manifest_sha256_check CHECK (((manifest_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT etl_load_execution_status_check CHECK (((status)::text = ANY ((ARRAY['PREPARING'::character varying, 'FAILED'::character varying, 'PUBLISHED'::character varying])::text[])))
);


ALTER TABLE public.etl_load_execution OWNER TO pickage;

--
-- Name: COLUMN etl_load_execution.snapshot_timestamp; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.etl_load_execution.snapshot_timestamp IS 'Curated report 공급자 관측 시각: 원천의 timezone 없는 마이크로초 값 보존';


--
-- Name: etl_snapshot_reference; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.etl_snapshot_reference (
    execution_id character varying(200) NOT NULL,
    dataset character varying(100) DEFAULT 'snapshot-reference'::character varying NOT NULL,
    snapshot_at date NOT NULL,
    snapshot_timestamp timestamp with time zone NOT NULL,
    previous_snapshot_at date,
    interval_days integer GENERATED ALWAYS AS ((snapshot_at - previous_snapshot_at)) STORED,
    CONSTRAINT etl_snapshot_reference_check CHECK ((((snapshot_timestamp AT TIME ZONE 'UTC'::text))::date = snapshot_at)),
    CONSTRAINT etl_snapshot_reference_check1 CHECK (((previous_snapshot_at IS NULL) OR (previous_snapshot_at < snapshot_at))),
    CONSTRAINT etl_snapshot_reference_dataset_check CHECK (((dataset)::text = 'snapshot-reference'::text))
);


ALTER TABLE public.etl_snapshot_reference OWNER TO pickage;

--
-- Name: TABLE etl_snapshot_reference; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON TABLE public.etl_snapshot_reference IS 'Projects 기준 목록의 실행별 날짜/원천 시각/직전 날짜 계보. 지표 준비 완료를 의미하지 않음';


--
-- Name: flyway_schema_history; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.flyway_schema_history (
    installed_rank integer NOT NULL,
    version character varying(50),
    description character varying(200) NOT NULL,
    type character varying(20) NOT NULL,
    script character varying(1000) NOT NULL,
    checksum integer,
    installed_by character varying(100) NOT NULL,
    installed_on timestamp without time zone DEFAULT now() NOT NULL,
    execution_time integer NOT NULL,
    success boolean NOT NULL
);


ALTER TABLE public.flyway_schema_history OWNER TO pickage;

--
-- Name: migration_pair; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.migration_pair (
    from_package_id integer NOT NULL,
    to_package_name character varying(300) NOT NULL,
    dep_kind character varying(16) NOT NULL,
    votes numeric(10,1) NOT NULL,
    co_events integer NOT NULL,
    removal_events integer NOT NULL,
    publisher_months integer NOT NULL,
    dependents integer NOT NULL,
    a_pct numeric(5,2) NOT NULL,
    b_pct numeric(6,4) NOT NULL,
    lift numeric(14,1) NOT NULL,
    share_pct numeric(4,1) NOT NULL,
    share_pm_pct numeric(4,1) NOT NULL,
    bidirectional boolean NOT NULL,
    first_seen date NOT NULL,
    last_seen date NOT NULL,
    snapshot_at date NOT NULL,
    CONSTRAINT "CK_MIGRATION_PAIR_COUNTS" CHECK (((co_events > 0) AND (removal_events > 0) AND (publisher_months > 0) AND (dependents > 0))),
    CONSTRAINT "CK_MIGRATION_PAIR_DEP_KIND" CHECK (((dep_kind)::text = ANY ((ARRAY['regular'::character varying, 'dev'::character varying])::text[]))),
    CONSTRAINT "CK_MIGRATION_PAIR_LOOSE" CHECK (((lift >= (5)::numeric) AND (votes >= (3)::numeric))),
    CONSTRAINT "CK_MIGRATION_PAIR_PCT_RANGE" CHECK (((a_pct >= (0)::numeric) AND (a_pct <= (100)::numeric) AND (b_pct >= (0)::numeric) AND (b_pct <= (100)::numeric) AND (share_pct >= (0)::numeric) AND (share_pct <= (100)::numeric) AND (share_pm_pct >= (0)::numeric) AND (share_pm_pct <= (100)::numeric))),
    CONSTRAINT "CK_MIGRATION_PAIR_RANGE" CHECK ((first_seen <= last_seen)),
    CONSTRAINT "CK_MIGRATION_PAIR_TO_NAME" CHECK (((to_package_name)::text <> ''::text)),
    CONSTRAINT "CK_MIGRATION_PAIR_UNITS" CHECK (((votes <= (co_events)::numeric) AND (co_events <= removal_events)))
);


ALTER TABLE public.migration_pair OWNER TO pickage;

--
-- Name: TABLE migration_pair; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON TABLE public.migration_pair IS '관측된 교체 흐름 — X 를 빼고 Y 를 넣은 쌍 (확장-02). 단위는 쌍이다';


--
-- Name: COLUMN migration_pair.to_package_name; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.to_package_name IS '도착 패키지 이름. package 에 없을 수 있다 — FK 가 아닌 이유는 파일 머리말 참고';


--
-- Name: COLUMN migration_pair.dep_kind; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.dep_kind IS '의존 종류이자 원천. regular=deps.dev 전수 · dev=registry 상위 10만. 모집단이 달라 합치지 않는다';


--
-- Name: COLUMN migration_pair.votes; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.votes IS '한 전이에서 함께 들어온 후보가 k 개면 1/k 씩 나눠 준 표의 합. 건수가 아니다';


--
-- Name: COLUMN migration_pair.co_events; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.co_events IS 'X 를 빼면서 Y 를 넣은 전이 수. votes 와 달리 나누지 않은 건수';


--
-- Name: COLUMN migration_pair.removal_events; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.removal_events IS 'X 를 뺀 전이 수 전체. 이 쌍의 분모다';


--
-- Name: COLUMN migration_pair.publisher_months; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.publisher_months IS '서로 다른 (배포주체, 달) 조합 수. 한 조직의 일괄 변경을 걸러 내는 핵심 값이다';


--
-- Name: COLUMN migration_pair.dependents; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.dependents IS '이 이동을 한 의존자 수(중복 접음)';


--
-- Name: COLUMN migration_pair.a_pct; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.a_pct IS 'co_events / removal_events × 100. X 를 뺀 사람 중 Y 를 넣은 비율';


--
-- Name: COLUMN migration_pair.b_pct; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.b_pct IS '모집단에서 Y 가 추가되는 기준율 × 100. lift 의 분모';


--
-- Name: COLUMN migration_pair.lift; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.lift IS 'a_pct / b_pct. 우연 대비 몇 배인가. **모집단이 다르면 절댓값을 비교할 수 없다**';


--
-- Name: COLUMN migration_pair.share_pct; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.share_pct IS '출발 패키지의 표 합 중 이 도착지 비율. 라벨 필터용이며 화면에는 쓰지 않는다';


--
-- Name: COLUMN migration_pair.share_pm_pct; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.share_pm_pct IS '조직·달 수 기준 점유율. **화면 점유율은 이것을 쓴다**(S15P21A506-136 3번)';


--
-- Name: COLUMN migration_pair.bidirectional; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.bidirectional IS '(Y, X) 쌍도 loose 를 통과한다. 같은 물건의 두 포장(lodash↔lodash-es)일 수 있어 지우지 않고 변종으로 표시한다';


--
-- Name: COLUMN migration_pair.first_seen; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.first_seen IS '이 이동이 처음 관측된 날';


--
-- Name: COLUMN migration_pair.last_seen; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.last_seen IS '마지막으로 관측된 날';


--
-- Name: COLUMN migration_pair.snapshot_at; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.migration_pair.snapshot_at IS '이 회차가 어디까지 본 원천인지. dep_kind 로 정해지는 상수이며 두 원천이 서로 다르다';


--
-- Name: package; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.package (
    package_id integer NOT NULL,
    name character varying(300) NOT NULL,
    repo_url character varying(200)
);


ALTER TABLE public.package OWNER TO pickage;

--
-- Name: package_env; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.package_env (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    module_format character varying(16) NOT NULL,
    types_bundled boolean NOT NULL,
    direct_dependencies integer,
    peer_dependencies integer,
    CONSTRAINT "CK_PACKAGE_ENV_COUNTS" CHECK ((((direct_dependencies IS NULL) OR (direct_dependencies >= 0)) AND ((peer_dependencies IS NULL) OR (peer_dependencies >= 0)))),
    CONSTRAINT "CK_PACKAGE_ENV_MODULE_FORMAT" CHECK (((module_format)::text = ANY ((ARRAY['CJS'::character varying, 'ESM_ONLY'::character varying, 'ESM_CJS'::character varying, 'UNKNOWN'::character varying])::text[])))
);


ALTER TABLE public.package_env OWNER TO pickage;

--
-- Name: TABLE package_env; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON TABLE public.package_env IS '버전별 소비 조건 — 모듈 방식·타입·의존 조건 (기능-11 첫 결과 카드)';


--
-- Name: COLUMN package_env.module_format; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.package_env.module_format IS '어떻게 불러오는가. CJS · ESM_ONLY · ESM_CJS(듀얼) · UNKNOWN(unpublish)';


--
-- Name: COLUMN package_env.types_bundled; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.package_env.types_bundled IS '타입 선언이 패키지에 동봉됐는가. 거짓은 @types 별도 설치를 뜻하며 타입 없음이 아니다';


--
-- Name: COLUMN package_env.direct_dependencies; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.package_env.direct_dependencies IS 'dependencies 선언 수. 전이 포함 아님. NULL 은 unpublish 라 모름이며 0 이 아니다';


--
-- Name: COLUMN package_env.peer_dependencies; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.package_env.peer_dependencies IS 'peerDependencies 선언 수. 사용자가 직접 맞춰야 하는 조건. NULL 은 모름';


--
-- Name: package_snapshot; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.package_snapshot (
    package_id integer NOT NULL,
    snapshot_at date NOT NULL,
    downloads bigint,
    stars integer,
    open_issues integer
);


ALTER TABLE public.package_snapshot OWNER TO pickage;

--
-- Name: package_version_snapshot; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.package_version_snapshot (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0))
)
PARTITION BY RANGE (snapshot_at);


ALTER TABLE public.package_version_snapshot OWNER TO pickage;

--
-- Name: similar_package; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.similar_package (
    package_id integer NOT NULL,
    similar_package_id integer NOT NULL,
    rank integer NOT NULL,
    score double precision NOT NULL,
    model_ver character varying(50) NOT NULL,
    CONSTRAINT "CK_SIMILAR_PACKAGE_RANK" CHECK (((rank >= 1) AND (rank <= 50))),
    CONSTRAINT "CK_SIMILAR_PACKAGE_SELF" CHECK ((package_id <> similar_package_id))
);


ALTER TABLE public.similar_package OWNER TO pickage;

--
-- Name: COLUMN similar_package.rank; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.similar_package.rank IS '순위';


--
-- Name: COLUMN similar_package.score; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.similar_package.score IS '종합 점수(유사도+기타)';


--
-- Name: COLUMN similar_package.model_ver; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.similar_package.model_ver IS '판정 모델 버전';


--
-- Name: snapshot; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.snapshot (
    snapshot_at date DEFAULT '2026-08-31'::date NOT NULL
);


ALTER TABLE public.snapshot OWNER TO pickage;

--
-- Name: COLUMN snapshot.snapshot_at; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.snapshot.snapshot_at IS 'BigQuery의 snapshot 테이블 값을 기준으로 함';


--
-- Name: version; Type: TABLE; Schema: public; Owner: pickage
--

CREATE TABLE public.version (
    version character varying(100) NOT NULL,
    package_id integer NOT NULL,
    published_at timestamp without time zone,
    ordinal bigint DEFAULT 0 NOT NULL,
    description text,
    licenses json,
    deprecated text,
    dependency json DEFAULT '{
        "dependencies": {},
        "peerDependencies": {},
        "optionalDependencies": {}
    }'::json NOT NULL
);


ALTER TABLE public.version OWNER TO pickage;

--
-- Name: COLUMN version.dependency; Type: COMMENT; Schema: public; Owner: pickage
--

COMMENT ON COLUMN public.version.dependency IS '유저에게 의존성 보여주는 용도, 따로 계산할때 쓰진 않음';


--
-- Name: d20220508; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220508 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-05-08'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220508 OWNER TO pickage;

--
-- Name: d20220515; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220515 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-05-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220515 OWNER TO pickage;

--
-- Name: d20220522; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220522 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-05-22'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220522 OWNER TO pickage;

--
-- Name: d20220529; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220529 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-05-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220529 OWNER TO pickage;

--
-- Name: d20220605; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220605 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-06-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220605 OWNER TO pickage;

--
-- Name: d20220613; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220613 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-06-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220613 OWNER TO pickage;

--
-- Name: d20220620; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220620 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-06-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220620 OWNER TO pickage;

--
-- Name: d20220627; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220627 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-06-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220627 OWNER TO pickage;

--
-- Name: d20220704; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220704 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-07-04'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220704 OWNER TO pickage;

--
-- Name: d20220712; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220712 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-07-12'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220712 OWNER TO pickage;

--
-- Name: d20220718; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220718 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-07-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220718 OWNER TO pickage;

--
-- Name: d20220726; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220726 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-07-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220726 OWNER TO pickage;

--
-- Name: d20220801; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220801 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-08-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220801 OWNER TO pickage;

--
-- Name: d20220808; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220808 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-08-08'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220808 OWNER TO pickage;

--
-- Name: d20220815; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220815 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-08-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220815 OWNER TO pickage;

--
-- Name: d20220822; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220822 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-08-22'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220822 OWNER TO pickage;

--
-- Name: d20220829; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220829 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-08-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220829 OWNER TO pickage;

--
-- Name: d20220905; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220905 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-09-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220905 OWNER TO pickage;

--
-- Name: d20220913; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220913 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-09-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220913 OWNER TO pickage;

--
-- Name: d20220919; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220919 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-09-19'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220919 OWNER TO pickage;

--
-- Name: d20220926; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20220926 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-09-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20220926 OWNER TO pickage;

--
-- Name: d20221003; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221003 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-10-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221003 OWNER TO pickage;

--
-- Name: d20221010; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221010 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-10-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221010 OWNER TO pickage;

--
-- Name: d20221017; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221017 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-10-17'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221017 OWNER TO pickage;

--
-- Name: d20221024; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221024 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-10-24'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221024 OWNER TO pickage;

--
-- Name: d20221031; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221031 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-10-31'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221031 OWNER TO pickage;

--
-- Name: d20221107; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221107 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-11-07'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221107 OWNER TO pickage;

--
-- Name: d20221114; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221114 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-11-14'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221114 OWNER TO pickage;

--
-- Name: d20221121; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221121 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-11-21'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221121 OWNER TO pickage;

--
-- Name: d20221128; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221128 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-11-28'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221128 OWNER TO pickage;

--
-- Name: d20221205; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221205 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-12-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221205 OWNER TO pickage;

--
-- Name: d20221212; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221212 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-12-12'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221212 OWNER TO pickage;

--
-- Name: d20221219; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221219 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-12-19'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221219 OWNER TO pickage;

--
-- Name: d20221226; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20221226 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2022-12-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20221226 OWNER TO pickage;

--
-- Name: d20230102; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230102 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-01-02'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230102 OWNER TO pickage;

--
-- Name: d20230109; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230109 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-01-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230109 OWNER TO pickage;

--
-- Name: d20230116; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230116 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-01-16'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230116 OWNER TO pickage;

--
-- Name: d20230123; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230123 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-01-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230123 OWNER TO pickage;

--
-- Name: d20230129; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230129 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-01-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230129 OWNER TO pickage;

--
-- Name: d20230206; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230206 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-02-06'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230206 OWNER TO pickage;

--
-- Name: d20230213; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230213 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-02-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230213 OWNER TO pickage;

--
-- Name: d20230220; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230220 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-02-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230220 OWNER TO pickage;

--
-- Name: d20230227; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230227 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-02-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230227 OWNER TO pickage;

--
-- Name: d20230306; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230306 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-03-06'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230306 OWNER TO pickage;

--
-- Name: d20230313; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230313 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-03-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230313 OWNER TO pickage;

--
-- Name: d20230321; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230321 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-03-21'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230321 OWNER TO pickage;

--
-- Name: d20230327; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230327 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-03-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230327 OWNER TO pickage;

--
-- Name: d20230403; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230403 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-04-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230403 OWNER TO pickage;

--
-- Name: d20230410; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230410 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-04-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230410 OWNER TO pickage;

--
-- Name: d20230417; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230417 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-04-17'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230417 OWNER TO pickage;

--
-- Name: d20230420; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230420 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-04-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230420 OWNER TO pickage;

--
-- Name: d20230501; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230501 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-05-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230501 OWNER TO pickage;

--
-- Name: d20230502; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230502 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-05-02'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230502 OWNER TO pickage;

--
-- Name: d20230508; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230508 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-05-08'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230508 OWNER TO pickage;

--
-- Name: d20230515; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230515 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-05-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230515 OWNER TO pickage;

--
-- Name: d20230522; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230522 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-05-22'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230522 OWNER TO pickage;

--
-- Name: d20230529; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230529 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-05-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230529 OWNER TO pickage;

--
-- Name: d20230605; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230605 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-06-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230605 OWNER TO pickage;

--
-- Name: d20230612; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230612 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-06-12'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230612 OWNER TO pickage;

--
-- Name: d20230620; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230620 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-06-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230620 OWNER TO pickage;

--
-- Name: d20230626; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230626 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-06-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230626 OWNER TO pickage;

--
-- Name: d20230703; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230703 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-07-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230703 OWNER TO pickage;

--
-- Name: d20230710; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230710 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-07-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230710 OWNER TO pickage;

--
-- Name: d20230717; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230717 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-07-17'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230717 OWNER TO pickage;

--
-- Name: d20230724; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230724 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-07-24'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230724 OWNER TO pickage;

--
-- Name: d20230731; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230731 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-07-31'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230731 OWNER TO pickage;

--
-- Name: d20230807; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230807 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-08-07'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230807 OWNER TO pickage;

--
-- Name: d20230814; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230814 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-08-14'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230814 OWNER TO pickage;

--
-- Name: d20230821; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230821 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-08-21'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230821 OWNER TO pickage;

--
-- Name: d20230828; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230828 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-08-28'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230828 OWNER TO pickage;

--
-- Name: d20230904; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230904 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-09-04'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230904 OWNER TO pickage;

--
-- Name: d20230911; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230911 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-09-11'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230911 OWNER TO pickage;

--
-- Name: d20230918; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230918 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-09-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230918 OWNER TO pickage;

--
-- Name: d20230926; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20230926 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-09-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20230926 OWNER TO pickage;

--
-- Name: d20231002; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231002 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-10-02'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231002 OWNER TO pickage;

--
-- Name: d20231009; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231009 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-10-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231009 OWNER TO pickage;

--
-- Name: d20231016; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231016 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-10-16'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231016 OWNER TO pickage;

--
-- Name: d20231023; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231023 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-10-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231023 OWNER TO pickage;

--
-- Name: d20231030; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231030 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-10-30'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231030 OWNER TO pickage;

--
-- Name: d20231106; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231106 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-11-06'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231106 OWNER TO pickage;

--
-- Name: d20231113; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231113 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-11-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231113 OWNER TO pickage;

--
-- Name: d20231120; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231120 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-11-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231120 OWNER TO pickage;

--
-- Name: d20231127; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231127 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-11-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231127 OWNER TO pickage;

--
-- Name: d20231204; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231204 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-12-04'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231204 OWNER TO pickage;

--
-- Name: d20231211; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231211 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-12-11'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231211 OWNER TO pickage;

--
-- Name: d20231218; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231218 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-12-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231218 OWNER TO pickage;

--
-- Name: d20231225; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20231225 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2023-12-25'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20231225 OWNER TO pickage;

--
-- Name: d20240101; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240101 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-01-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240101 OWNER TO pickage;

--
-- Name: d20240108; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240108 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-01-08'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240108 OWNER TO pickage;

--
-- Name: d20240115; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240115 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-01-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240115 OWNER TO pickage;

--
-- Name: d20240122; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240122 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-01-22'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240122 OWNER TO pickage;

--
-- Name: d20240129; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240129 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-01-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240129 OWNER TO pickage;

--
-- Name: d20240205; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240205 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-02-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240205 OWNER TO pickage;

--
-- Name: d20240212; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240212 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-02-12'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240212 OWNER TO pickage;

--
-- Name: d20240219; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240219 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-02-19'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240219 OWNER TO pickage;

--
-- Name: d20240226; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240226 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-02-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240226 OWNER TO pickage;

--
-- Name: d20240304; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240304 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-03-04'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240304 OWNER TO pickage;

--
-- Name: d20240305; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240305 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-03-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240305 OWNER TO pickage;

--
-- Name: d20240311; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240311 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-03-11'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240311 OWNER TO pickage;

--
-- Name: d20240318; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240318 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-03-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240318 OWNER TO pickage;

--
-- Name: d20240325; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240325 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-03-25'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240325 OWNER TO pickage;

--
-- Name: d20240401; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240401 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-04-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240401 OWNER TO pickage;

--
-- Name: d20240409; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240409 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-04-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240409 OWNER TO pickage;

--
-- Name: d20240415; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240415 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-04-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240415 OWNER TO pickage;

--
-- Name: d20240421; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240421 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-04-21'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240421 OWNER TO pickage;

--
-- Name: d20240429; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240429 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-04-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240429 OWNER TO pickage;

--
-- Name: d20240509; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240509 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-05-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240509 OWNER TO pickage;

--
-- Name: d20240513; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240513 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-05-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240513 OWNER TO pickage;

--
-- Name: d20240520; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240520 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-05-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240520 OWNER TO pickage;

--
-- Name: d20240527; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240527 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-05-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240527 OWNER TO pickage;

--
-- Name: d20240603; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240603 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-06-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240603 OWNER TO pickage;

--
-- Name: d20240610; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240610 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-06-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240610 OWNER TO pickage;

--
-- Name: d20240617; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240617 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-06-17'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240617 OWNER TO pickage;

--
-- Name: d20240624; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240624 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-06-24'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240624 OWNER TO pickage;

--
-- Name: d20240701; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240701 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-07-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240701 OWNER TO pickage;

--
-- Name: d20240708; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240708 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-07-08'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240708 OWNER TO pickage;

--
-- Name: d20240709; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240709 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-07-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240709 OWNER TO pickage;

--
-- Name: d20240715; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240715 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-07-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240715 OWNER TO pickage;

--
-- Name: d20240723; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240723 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-07-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240723 OWNER TO pickage;

--
-- Name: d20240729; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240729 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-07-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240729 OWNER TO pickage;

--
-- Name: d20240805; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240805 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-08-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240805 OWNER TO pickage;

--
-- Name: d20240812; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240812 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-08-12'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240812 OWNER TO pickage;

--
-- Name: d20240819; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240819 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-08-19'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240819 OWNER TO pickage;

--
-- Name: d20240829; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240829 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-08-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240829 OWNER TO pickage;

--
-- Name: d20240902; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240902 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-09-02'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240902 OWNER TO pickage;

--
-- Name: d20240909; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240909 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-09-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240909 OWNER TO pickage;

--
-- Name: d20240916; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240916 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-09-16'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240916 OWNER TO pickage;

--
-- Name: d20240923; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240923 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-09-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240923 OWNER TO pickage;

--
-- Name: d20240930; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20240930 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-09-30'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20240930 OWNER TO pickage;

--
-- Name: d20241007; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241007 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-10-07'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241007 OWNER TO pickage;

--
-- Name: d20241014; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241014 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-10-14'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241014 OWNER TO pickage;

--
-- Name: d20241021; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241021 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-10-21'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241021 OWNER TO pickage;

--
-- Name: d20241028; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241028 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-10-28'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241028 OWNER TO pickage;

--
-- Name: d20241104; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241104 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-11-04'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241104 OWNER TO pickage;

--
-- Name: d20241111; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241111 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-11-11'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241111 OWNER TO pickage;

--
-- Name: d20241119; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241119 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-11-19'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241119 OWNER TO pickage;

--
-- Name: d20241125; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241125 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-11-25'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241125 OWNER TO pickage;

--
-- Name: d20241202; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241202 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-12-02'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241202 OWNER TO pickage;

--
-- Name: d20241209; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241209 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-12-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241209 OWNER TO pickage;

--
-- Name: d20241216; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241216 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-12-16'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241216 OWNER TO pickage;

--
-- Name: d20241223; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241223 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-12-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241223 OWNER TO pickage;

--
-- Name: d20241230; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20241230 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2024-12-30'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20241230 OWNER TO pickage;

--
-- Name: d20250106; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250106 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-01-06'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250106 OWNER TO pickage;

--
-- Name: d20250113; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250113 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-01-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250113 OWNER TO pickage;

--
-- Name: d20250120; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250120 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-01-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250120 OWNER TO pickage;

--
-- Name: d20250127; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250127 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-01-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250127 OWNER TO pickage;

--
-- Name: d20250203; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250203 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-02-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250203 OWNER TO pickage;

--
-- Name: d20250210; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250210 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-02-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250210 OWNER TO pickage;

--
-- Name: d20250218; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250218 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-02-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250218 OWNER TO pickage;

--
-- Name: d20250225; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250225 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-02-25'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250225 OWNER TO pickage;

--
-- Name: d20250303; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250303 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-03-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250303 OWNER TO pickage;

--
-- Name: d20250310; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250310 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-03-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250310 OWNER TO pickage;

--
-- Name: d20250318; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250318 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-03-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250318 OWNER TO pickage;

--
-- Name: d20250324; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250324 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-03-24'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250324 OWNER TO pickage;

--
-- Name: d20250331; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250331 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-03-31'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250331 OWNER TO pickage;

--
-- Name: d20250407; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250407 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-04-07'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250407 OWNER TO pickage;

--
-- Name: d20250414; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250414 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-04-14'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250414 OWNER TO pickage;

--
-- Name: d20250422; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250422 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-04-22'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250422 OWNER TO pickage;

--
-- Name: d20250428; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250428 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-04-28'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250428 OWNER TO pickage;

--
-- Name: d20250505; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250505 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-05-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250505 OWNER TO pickage;

--
-- Name: d20250512; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250512 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-05-12'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250512 OWNER TO pickage;

--
-- Name: d20250519; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250519 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-05-19'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250519 OWNER TO pickage;

--
-- Name: d20250526; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250526 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-05-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250526 OWNER TO pickage;

--
-- Name: d20250602; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250602 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-06-02'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250602 OWNER TO pickage;

--
-- Name: d20250609; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250609 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-06-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250609 OWNER TO pickage;

--
-- Name: d20250616; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250616 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-06-16'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250616 OWNER TO pickage;

--
-- Name: d20250623; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250623 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-06-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250623 OWNER TO pickage;

--
-- Name: d20250630; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250630 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-06-30'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250630 OWNER TO pickage;

--
-- Name: d20250707; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250707 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-07-07'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250707 OWNER TO pickage;

--
-- Name: d20250714; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250714 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-07-14'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250714 OWNER TO pickage;

--
-- Name: d20250721; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250721 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-07-21'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250721 OWNER TO pickage;

--
-- Name: d20250728; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250728 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-07-28'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250728 OWNER TO pickage;

--
-- Name: d20250804; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250804 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-08-04'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250804 OWNER TO pickage;

--
-- Name: d20250811; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250811 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-08-11'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250811 OWNER TO pickage;

--
-- Name: d20250818; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250818 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-08-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250818 OWNER TO pickage;

--
-- Name: d20250825; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250825 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-08-25'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250825 OWNER TO pickage;

--
-- Name: d20250901; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250901 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-09-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250901 OWNER TO pickage;

--
-- Name: d20250908; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250908 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-09-08'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250908 OWNER TO pickage;

--
-- Name: d20250915; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250915 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-09-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250915 OWNER TO pickage;

--
-- Name: d20250922; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250922 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-09-22'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250922 OWNER TO pickage;

--
-- Name: d20250929; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20250929 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-09-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20250929 OWNER TO pickage;

--
-- Name: d20251006; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251006 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-10-06'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251006 OWNER TO pickage;

--
-- Name: d20251013; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251013 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-10-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251013 OWNER TO pickage;

--
-- Name: d20251020; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251020 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-10-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251020 OWNER TO pickage;

--
-- Name: d20251027; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251027 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-10-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251027 OWNER TO pickage;

--
-- Name: d20251103; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251103 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-11-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251103 OWNER TO pickage;

--
-- Name: d20251110; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251110 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-11-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251110 OWNER TO pickage;

--
-- Name: d20251117; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251117 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-11-17'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251117 OWNER TO pickage;

--
-- Name: d20251124; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251124 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-11-24'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251124 OWNER TO pickage;

--
-- Name: d20251201; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251201 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-12-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251201 OWNER TO pickage;

--
-- Name: d20251208; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251208 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-12-08'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251208 OWNER TO pickage;

--
-- Name: d20251215; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251215 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-12-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251215 OWNER TO pickage;

--
-- Name: d20251222; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251222 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-12-22'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251222 OWNER TO pickage;

--
-- Name: d20251229; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20251229 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2025-12-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20251229 OWNER TO pickage;

--
-- Name: d20260105; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260105 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-01-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260105 OWNER TO pickage;

--
-- Name: d20260112; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260112 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-01-12'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260112 OWNER TO pickage;

--
-- Name: d20260119; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260119 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-01-19'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260119 OWNER TO pickage;

--
-- Name: d20260126; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260126 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-01-26'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260126 OWNER TO pickage;

--
-- Name: d20260213; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260213 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-02-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260213 OWNER TO pickage;

--
-- Name: d20260216; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260216 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-02-16'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260216 OWNER TO pickage;

--
-- Name: d20260223; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260223 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-02-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260223 OWNER TO pickage;

--
-- Name: d20260302; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260302 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-03-02'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260302 OWNER TO pickage;

--
-- Name: d20260309; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260309 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-03-09'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260309 OWNER TO pickage;

--
-- Name: d20260310; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260310 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-03-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260310 OWNER TO pickage;

--
-- Name: d20260316; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260316 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-03-16'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260316 OWNER TO pickage;

--
-- Name: d20260323; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260323 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-03-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260323 OWNER TO pickage;

--
-- Name: d20260330; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260330 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-03-30'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260330 OWNER TO pickage;

--
-- Name: d20260406; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260406 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-04-06'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260406 OWNER TO pickage;

--
-- Name: d20260413; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260413 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-04-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260413 OWNER TO pickage;

--
-- Name: d20260414; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260414 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-04-14'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260414 OWNER TO pickage;

--
-- Name: d20260420; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260420 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-04-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260420 OWNER TO pickage;

--
-- Name: d20260428; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260428 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-04-28'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260428 OWNER TO pickage;

--
-- Name: d20260505; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260505 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-05-05'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260505 OWNER TO pickage;

--
-- Name: d20260511; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260511 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-05-11'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260511 OWNER TO pickage;

--
-- Name: d20260518; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260518 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-05-18'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260518 OWNER TO pickage;

--
-- Name: d20260601; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260601 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-06-01'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260601 OWNER TO pickage;

--
-- Name: d20260611; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260611 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-06-11'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260611 OWNER TO pickage;

--
-- Name: d20260615; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260615 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-06-15'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260615 OWNER TO pickage;

--
-- Name: d20260623; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260623 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-06-23'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260623 OWNER TO pickage;

--
-- Name: d20260629; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260629 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-06-29'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260629 OWNER TO pickage;

--
-- Name: d20260706; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260706 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-07-06'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260706 OWNER TO pickage;

--
-- Name: d20260713; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260713 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-07-13'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260713 OWNER TO pickage;

--
-- Name: d20260720; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260720 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-07-20'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260720 OWNER TO pickage;

--
-- Name: d20260727; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260727 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-07-27'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260727 OWNER TO pickage;

--
-- Name: d20260803; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260803 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-08-03'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260803 OWNER TO pickage;

--
-- Name: d20260810; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260810 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-08-10'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260810 OWNER TO pickage;

--
-- Name: d20260817; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260817 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-08-17'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260817 OWNER TO pickage;

--
-- Name: d20260824; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260824 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-08-24'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260824 OWNER TO pickage;

--
-- Name: d20260831; Type: TABLE; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE TABLE vd193_reload_20260912_ready01.d20260831 (
    package_id integer NOT NULL,
    version character varying(100) NOT NULL,
    snapshot_at date NOT NULL,
    dependents_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_package_version_snapshot_dependents_nonnegative CHECK ((dependents_count >= 0)),
    CONSTRAINT date_bound CHECK ((snapshot_at = '2026-08-31'::date))
);


ALTER TABLE vd193_reload_20260912_ready01.d20260831 OWNER TO pickage;

--
-- Name: d20220508; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220508 FOR VALUES FROM ('2022-05-08') TO ('2022-05-09');


--
-- Name: d20220515; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220515 FOR VALUES FROM ('2022-05-15') TO ('2022-05-16');


--
-- Name: d20220522; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220522 FOR VALUES FROM ('2022-05-22') TO ('2022-05-23');


--
-- Name: d20220529; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220529 FOR VALUES FROM ('2022-05-29') TO ('2022-05-30');


--
-- Name: d20220605; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220605 FOR VALUES FROM ('2022-06-05') TO ('2022-06-06');


--
-- Name: d20220613; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220613 FOR VALUES FROM ('2022-06-13') TO ('2022-06-14');


--
-- Name: d20220620; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220620 FOR VALUES FROM ('2022-06-20') TO ('2022-06-21');


--
-- Name: d20220627; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220627 FOR VALUES FROM ('2022-06-27') TO ('2022-06-28');


--
-- Name: d20220704; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220704 FOR VALUES FROM ('2022-07-04') TO ('2022-07-05');


--
-- Name: d20220712; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220712 FOR VALUES FROM ('2022-07-12') TO ('2022-07-13');


--
-- Name: d20220718; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220718 FOR VALUES FROM ('2022-07-18') TO ('2022-07-19');


--
-- Name: d20220726; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220726 FOR VALUES FROM ('2022-07-26') TO ('2022-07-27');


--
-- Name: d20220801; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220801 FOR VALUES FROM ('2022-08-01') TO ('2022-08-02');


--
-- Name: d20220808; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220808 FOR VALUES FROM ('2022-08-08') TO ('2022-08-09');


--
-- Name: d20220815; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220815 FOR VALUES FROM ('2022-08-15') TO ('2022-08-16');


--
-- Name: d20220822; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220822 FOR VALUES FROM ('2022-08-22') TO ('2022-08-23');


--
-- Name: d20220829; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220829 FOR VALUES FROM ('2022-08-29') TO ('2022-08-30');


--
-- Name: d20220905; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220905 FOR VALUES FROM ('2022-09-05') TO ('2022-09-06');


--
-- Name: d20220913; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220913 FOR VALUES FROM ('2022-09-13') TO ('2022-09-14');


--
-- Name: d20220919; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220919 FOR VALUES FROM ('2022-09-19') TO ('2022-09-20');


--
-- Name: d20220926; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220926 FOR VALUES FROM ('2022-09-26') TO ('2022-09-27');


--
-- Name: d20221003; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221003 FOR VALUES FROM ('2022-10-03') TO ('2022-10-04');


--
-- Name: d20221010; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221010 FOR VALUES FROM ('2022-10-10') TO ('2022-10-11');


--
-- Name: d20221017; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221017 FOR VALUES FROM ('2022-10-17') TO ('2022-10-18');


--
-- Name: d20221024; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221024 FOR VALUES FROM ('2022-10-24') TO ('2022-10-25');


--
-- Name: d20221031; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221031 FOR VALUES FROM ('2022-10-31') TO ('2022-11-01');


--
-- Name: d20221107; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221107 FOR VALUES FROM ('2022-11-07') TO ('2022-11-08');


--
-- Name: d20221114; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221114 FOR VALUES FROM ('2022-11-14') TO ('2022-11-15');


--
-- Name: d20221121; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221121 FOR VALUES FROM ('2022-11-21') TO ('2022-11-22');


--
-- Name: d20221128; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221128 FOR VALUES FROM ('2022-11-28') TO ('2022-11-29');


--
-- Name: d20221205; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221205 FOR VALUES FROM ('2022-12-05') TO ('2022-12-06');


--
-- Name: d20221212; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221212 FOR VALUES FROM ('2022-12-12') TO ('2022-12-13');


--
-- Name: d20221219; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221219 FOR VALUES FROM ('2022-12-19') TO ('2022-12-20');


--
-- Name: d20221226; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221226 FOR VALUES FROM ('2022-12-26') TO ('2022-12-27');


--
-- Name: d20230102; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230102 FOR VALUES FROM ('2023-01-02') TO ('2023-01-03');


--
-- Name: d20230109; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230109 FOR VALUES FROM ('2023-01-09') TO ('2023-01-10');


--
-- Name: d20230116; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230116 FOR VALUES FROM ('2023-01-16') TO ('2023-01-17');


--
-- Name: d20230123; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230123 FOR VALUES FROM ('2023-01-23') TO ('2023-01-24');


--
-- Name: d20230129; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230129 FOR VALUES FROM ('2023-01-29') TO ('2023-01-30');


--
-- Name: d20230206; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230206 FOR VALUES FROM ('2023-02-06') TO ('2023-02-07');


--
-- Name: d20230213; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230213 FOR VALUES FROM ('2023-02-13') TO ('2023-02-14');


--
-- Name: d20230220; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230220 FOR VALUES FROM ('2023-02-20') TO ('2023-02-21');


--
-- Name: d20230227; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230227 FOR VALUES FROM ('2023-02-27') TO ('2023-02-28');


--
-- Name: d20230306; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230306 FOR VALUES FROM ('2023-03-06') TO ('2023-03-07');


--
-- Name: d20230313; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230313 FOR VALUES FROM ('2023-03-13') TO ('2023-03-14');


--
-- Name: d20230321; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230321 FOR VALUES FROM ('2023-03-21') TO ('2023-03-22');


--
-- Name: d20230327; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230327 FOR VALUES FROM ('2023-03-27') TO ('2023-03-28');


--
-- Name: d20230403; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230403 FOR VALUES FROM ('2023-04-03') TO ('2023-04-04');


--
-- Name: d20230410; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230410 FOR VALUES FROM ('2023-04-10') TO ('2023-04-11');


--
-- Name: d20230417; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230417 FOR VALUES FROM ('2023-04-17') TO ('2023-04-18');


--
-- Name: d20230420; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230420 FOR VALUES FROM ('2023-04-20') TO ('2023-04-21');


--
-- Name: d20230501; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230501 FOR VALUES FROM ('2023-05-01') TO ('2023-05-02');


--
-- Name: d20230502; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230502 FOR VALUES FROM ('2023-05-02') TO ('2023-05-03');


--
-- Name: d20230508; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230508 FOR VALUES FROM ('2023-05-08') TO ('2023-05-09');


--
-- Name: d20230515; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230515 FOR VALUES FROM ('2023-05-15') TO ('2023-05-16');


--
-- Name: d20230522; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230522 FOR VALUES FROM ('2023-05-22') TO ('2023-05-23');


--
-- Name: d20230529; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230529 FOR VALUES FROM ('2023-05-29') TO ('2023-05-30');


--
-- Name: d20230605; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230605 FOR VALUES FROM ('2023-06-05') TO ('2023-06-06');


--
-- Name: d20230612; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230612 FOR VALUES FROM ('2023-06-12') TO ('2023-06-13');


--
-- Name: d20230620; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230620 FOR VALUES FROM ('2023-06-20') TO ('2023-06-21');


--
-- Name: d20230626; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230626 FOR VALUES FROM ('2023-06-26') TO ('2023-06-27');


--
-- Name: d20230703; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230703 FOR VALUES FROM ('2023-07-03') TO ('2023-07-04');


--
-- Name: d20230710; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230710 FOR VALUES FROM ('2023-07-10') TO ('2023-07-11');


--
-- Name: d20230717; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230717 FOR VALUES FROM ('2023-07-17') TO ('2023-07-18');


--
-- Name: d20230724; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230724 FOR VALUES FROM ('2023-07-24') TO ('2023-07-25');


--
-- Name: d20230731; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230731 FOR VALUES FROM ('2023-07-31') TO ('2023-08-01');


--
-- Name: d20230807; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230807 FOR VALUES FROM ('2023-08-07') TO ('2023-08-08');


--
-- Name: d20230814; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230814 FOR VALUES FROM ('2023-08-14') TO ('2023-08-15');


--
-- Name: d20230821; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230821 FOR VALUES FROM ('2023-08-21') TO ('2023-08-22');


--
-- Name: d20230828; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230828 FOR VALUES FROM ('2023-08-28') TO ('2023-08-29');


--
-- Name: d20230904; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230904 FOR VALUES FROM ('2023-09-04') TO ('2023-09-05');


--
-- Name: d20230911; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230911 FOR VALUES FROM ('2023-09-11') TO ('2023-09-12');


--
-- Name: d20230918; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230918 FOR VALUES FROM ('2023-09-18') TO ('2023-09-19');


--
-- Name: d20230926; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230926 FOR VALUES FROM ('2023-09-26') TO ('2023-09-27');


--
-- Name: d20231002; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231002 FOR VALUES FROM ('2023-10-02') TO ('2023-10-03');


--
-- Name: d20231009; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231009 FOR VALUES FROM ('2023-10-09') TO ('2023-10-10');


--
-- Name: d20231016; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231016 FOR VALUES FROM ('2023-10-16') TO ('2023-10-17');


--
-- Name: d20231023; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231023 FOR VALUES FROM ('2023-10-23') TO ('2023-10-24');


--
-- Name: d20231030; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231030 FOR VALUES FROM ('2023-10-30') TO ('2023-10-31');


--
-- Name: d20231106; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231106 FOR VALUES FROM ('2023-11-06') TO ('2023-11-07');


--
-- Name: d20231113; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231113 FOR VALUES FROM ('2023-11-13') TO ('2023-11-14');


--
-- Name: d20231120; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231120 FOR VALUES FROM ('2023-11-20') TO ('2023-11-21');


--
-- Name: d20231127; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231127 FOR VALUES FROM ('2023-11-27') TO ('2023-11-28');


--
-- Name: d20231204; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231204 FOR VALUES FROM ('2023-12-04') TO ('2023-12-05');


--
-- Name: d20231211; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231211 FOR VALUES FROM ('2023-12-11') TO ('2023-12-12');


--
-- Name: d20231218; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231218 FOR VALUES FROM ('2023-12-18') TO ('2023-12-19');


--
-- Name: d20231225; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231225 FOR VALUES FROM ('2023-12-25') TO ('2023-12-26');


--
-- Name: d20240101; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240101 FOR VALUES FROM ('2024-01-01') TO ('2024-01-02');


--
-- Name: d20240108; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240108 FOR VALUES FROM ('2024-01-08') TO ('2024-01-09');


--
-- Name: d20240115; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240115 FOR VALUES FROM ('2024-01-15') TO ('2024-01-16');


--
-- Name: d20240122; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240122 FOR VALUES FROM ('2024-01-22') TO ('2024-01-23');


--
-- Name: d20240129; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240129 FOR VALUES FROM ('2024-01-29') TO ('2024-01-30');


--
-- Name: d20240205; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240205 FOR VALUES FROM ('2024-02-05') TO ('2024-02-06');


--
-- Name: d20240212; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240212 FOR VALUES FROM ('2024-02-12') TO ('2024-02-13');


--
-- Name: d20240219; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240219 FOR VALUES FROM ('2024-02-19') TO ('2024-02-20');


--
-- Name: d20240226; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240226 FOR VALUES FROM ('2024-02-26') TO ('2024-02-27');


--
-- Name: d20240304; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240304 FOR VALUES FROM ('2024-03-04') TO ('2024-03-05');


--
-- Name: d20240305; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240305 FOR VALUES FROM ('2024-03-05') TO ('2024-03-06');


--
-- Name: d20240311; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240311 FOR VALUES FROM ('2024-03-11') TO ('2024-03-12');


--
-- Name: d20240318; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240318 FOR VALUES FROM ('2024-03-18') TO ('2024-03-19');


--
-- Name: d20240325; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240325 FOR VALUES FROM ('2024-03-25') TO ('2024-03-26');


--
-- Name: d20240401; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240401 FOR VALUES FROM ('2024-04-01') TO ('2024-04-02');


--
-- Name: d20240409; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240409 FOR VALUES FROM ('2024-04-09') TO ('2024-04-10');


--
-- Name: d20240415; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240415 FOR VALUES FROM ('2024-04-15') TO ('2024-04-16');


--
-- Name: d20240421; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240421 FOR VALUES FROM ('2024-04-21') TO ('2024-04-22');


--
-- Name: d20240429; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240429 FOR VALUES FROM ('2024-04-29') TO ('2024-04-30');


--
-- Name: d20240509; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240509 FOR VALUES FROM ('2024-05-09') TO ('2024-05-10');


--
-- Name: d20240513; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240513 FOR VALUES FROM ('2024-05-13') TO ('2024-05-14');


--
-- Name: d20240520; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240520 FOR VALUES FROM ('2024-05-20') TO ('2024-05-21');


--
-- Name: d20240527; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240527 FOR VALUES FROM ('2024-05-27') TO ('2024-05-28');


--
-- Name: d20240603; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240603 FOR VALUES FROM ('2024-06-03') TO ('2024-06-04');


--
-- Name: d20240610; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240610 FOR VALUES FROM ('2024-06-10') TO ('2024-06-11');


--
-- Name: d20240617; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240617 FOR VALUES FROM ('2024-06-17') TO ('2024-06-18');


--
-- Name: d20240624; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240624 FOR VALUES FROM ('2024-06-24') TO ('2024-06-25');


--
-- Name: d20240701; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240701 FOR VALUES FROM ('2024-07-01') TO ('2024-07-02');


--
-- Name: d20240708; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240708 FOR VALUES FROM ('2024-07-08') TO ('2024-07-09');


--
-- Name: d20240709; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240709 FOR VALUES FROM ('2024-07-09') TO ('2024-07-10');


--
-- Name: d20240715; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240715 FOR VALUES FROM ('2024-07-15') TO ('2024-07-16');


--
-- Name: d20240723; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240723 FOR VALUES FROM ('2024-07-23') TO ('2024-07-24');


--
-- Name: d20240729; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240729 FOR VALUES FROM ('2024-07-29') TO ('2024-07-30');


--
-- Name: d20240805; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240805 FOR VALUES FROM ('2024-08-05') TO ('2024-08-06');


--
-- Name: d20240812; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240812 FOR VALUES FROM ('2024-08-12') TO ('2024-08-13');


--
-- Name: d20240819; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240819 FOR VALUES FROM ('2024-08-19') TO ('2024-08-20');


--
-- Name: d20240829; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240829 FOR VALUES FROM ('2024-08-29') TO ('2024-08-30');


--
-- Name: d20240902; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240902 FOR VALUES FROM ('2024-09-02') TO ('2024-09-03');


--
-- Name: d20240909; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240909 FOR VALUES FROM ('2024-09-09') TO ('2024-09-10');


--
-- Name: d20240916; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240916 FOR VALUES FROM ('2024-09-16') TO ('2024-09-17');


--
-- Name: d20240923; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240923 FOR VALUES FROM ('2024-09-23') TO ('2024-09-24');


--
-- Name: d20240930; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240930 FOR VALUES FROM ('2024-09-30') TO ('2024-10-01');


--
-- Name: d20241007; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241007 FOR VALUES FROM ('2024-10-07') TO ('2024-10-08');


--
-- Name: d20241014; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241014 FOR VALUES FROM ('2024-10-14') TO ('2024-10-15');


--
-- Name: d20241021; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241021 FOR VALUES FROM ('2024-10-21') TO ('2024-10-22');


--
-- Name: d20241028; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241028 FOR VALUES FROM ('2024-10-28') TO ('2024-10-29');


--
-- Name: d20241104; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241104 FOR VALUES FROM ('2024-11-04') TO ('2024-11-05');


--
-- Name: d20241111; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241111 FOR VALUES FROM ('2024-11-11') TO ('2024-11-12');


--
-- Name: d20241119; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241119 FOR VALUES FROM ('2024-11-19') TO ('2024-11-20');


--
-- Name: d20241125; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241125 FOR VALUES FROM ('2024-11-25') TO ('2024-11-26');


--
-- Name: d20241202; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241202 FOR VALUES FROM ('2024-12-02') TO ('2024-12-03');


--
-- Name: d20241209; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241209 FOR VALUES FROM ('2024-12-09') TO ('2024-12-10');


--
-- Name: d20241216; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241216 FOR VALUES FROM ('2024-12-16') TO ('2024-12-17');


--
-- Name: d20241223; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241223 FOR VALUES FROM ('2024-12-23') TO ('2024-12-24');


--
-- Name: d20241230; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241230 FOR VALUES FROM ('2024-12-30') TO ('2024-12-31');


--
-- Name: d20250106; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250106 FOR VALUES FROM ('2025-01-06') TO ('2025-01-07');


--
-- Name: d20250113; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250113 FOR VALUES FROM ('2025-01-13') TO ('2025-01-14');


--
-- Name: d20250120; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250120 FOR VALUES FROM ('2025-01-20') TO ('2025-01-21');


--
-- Name: d20250127; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250127 FOR VALUES FROM ('2025-01-27') TO ('2025-01-28');


--
-- Name: d20250203; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250203 FOR VALUES FROM ('2025-02-03') TO ('2025-02-04');


--
-- Name: d20250210; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250210 FOR VALUES FROM ('2025-02-10') TO ('2025-02-11');


--
-- Name: d20250218; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250218 FOR VALUES FROM ('2025-02-18') TO ('2025-02-19');


--
-- Name: d20250225; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250225 FOR VALUES FROM ('2025-02-25') TO ('2025-02-26');


--
-- Name: d20250303; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250303 FOR VALUES FROM ('2025-03-03') TO ('2025-03-04');


--
-- Name: d20250310; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250310 FOR VALUES FROM ('2025-03-10') TO ('2025-03-11');


--
-- Name: d20250318; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250318 FOR VALUES FROM ('2025-03-18') TO ('2025-03-19');


--
-- Name: d20250324; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250324 FOR VALUES FROM ('2025-03-24') TO ('2025-03-25');


--
-- Name: d20250331; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250331 FOR VALUES FROM ('2025-03-31') TO ('2025-04-01');


--
-- Name: d20250407; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250407 FOR VALUES FROM ('2025-04-07') TO ('2025-04-08');


--
-- Name: d20250414; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250414 FOR VALUES FROM ('2025-04-14') TO ('2025-04-15');


--
-- Name: d20250422; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250422 FOR VALUES FROM ('2025-04-22') TO ('2025-04-23');


--
-- Name: d20250428; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250428 FOR VALUES FROM ('2025-04-28') TO ('2025-04-29');


--
-- Name: d20250505; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250505 FOR VALUES FROM ('2025-05-05') TO ('2025-05-06');


--
-- Name: d20250512; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250512 FOR VALUES FROM ('2025-05-12') TO ('2025-05-13');


--
-- Name: d20250519; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250519 FOR VALUES FROM ('2025-05-19') TO ('2025-05-20');


--
-- Name: d20250526; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250526 FOR VALUES FROM ('2025-05-26') TO ('2025-05-27');


--
-- Name: d20250602; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250602 FOR VALUES FROM ('2025-06-02') TO ('2025-06-03');


--
-- Name: d20250609; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250609 FOR VALUES FROM ('2025-06-09') TO ('2025-06-10');


--
-- Name: d20250616; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250616 FOR VALUES FROM ('2025-06-16') TO ('2025-06-17');


--
-- Name: d20250623; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250623 FOR VALUES FROM ('2025-06-23') TO ('2025-06-24');


--
-- Name: d20250630; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250630 FOR VALUES FROM ('2025-06-30') TO ('2025-07-01');


--
-- Name: d20250707; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250707 FOR VALUES FROM ('2025-07-07') TO ('2025-07-08');


--
-- Name: d20250714; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250714 FOR VALUES FROM ('2025-07-14') TO ('2025-07-15');


--
-- Name: d20250721; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250721 FOR VALUES FROM ('2025-07-21') TO ('2025-07-22');


--
-- Name: d20250728; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250728 FOR VALUES FROM ('2025-07-28') TO ('2025-07-29');


--
-- Name: d20250804; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250804 FOR VALUES FROM ('2025-08-04') TO ('2025-08-05');


--
-- Name: d20250811; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250811 FOR VALUES FROM ('2025-08-11') TO ('2025-08-12');


--
-- Name: d20250818; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250818 FOR VALUES FROM ('2025-08-18') TO ('2025-08-19');


--
-- Name: d20250825; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250825 FOR VALUES FROM ('2025-08-25') TO ('2025-08-26');


--
-- Name: d20250901; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250901 FOR VALUES FROM ('2025-09-01') TO ('2025-09-02');


--
-- Name: d20250908; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250908 FOR VALUES FROM ('2025-09-08') TO ('2025-09-09');


--
-- Name: d20250915; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250915 FOR VALUES FROM ('2025-09-15') TO ('2025-09-16');


--
-- Name: d20250922; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250922 FOR VALUES FROM ('2025-09-22') TO ('2025-09-23');


--
-- Name: d20250929; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250929 FOR VALUES FROM ('2025-09-29') TO ('2025-09-30');


--
-- Name: d20251006; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251006 FOR VALUES FROM ('2025-10-06') TO ('2025-10-07');


--
-- Name: d20251013; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251013 FOR VALUES FROM ('2025-10-13') TO ('2025-10-14');


--
-- Name: d20251020; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251020 FOR VALUES FROM ('2025-10-20') TO ('2025-10-21');


--
-- Name: d20251027; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251027 FOR VALUES FROM ('2025-10-27') TO ('2025-10-28');


--
-- Name: d20251103; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251103 FOR VALUES FROM ('2025-11-03') TO ('2025-11-04');


--
-- Name: d20251110; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251110 FOR VALUES FROM ('2025-11-10') TO ('2025-11-11');


--
-- Name: d20251117; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251117 FOR VALUES FROM ('2025-11-17') TO ('2025-11-18');


--
-- Name: d20251124; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251124 FOR VALUES FROM ('2025-11-24') TO ('2025-11-25');


--
-- Name: d20251201; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251201 FOR VALUES FROM ('2025-12-01') TO ('2025-12-02');


--
-- Name: d20251208; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251208 FOR VALUES FROM ('2025-12-08') TO ('2025-12-09');


--
-- Name: d20251215; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251215 FOR VALUES FROM ('2025-12-15') TO ('2025-12-16');


--
-- Name: d20251222; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251222 FOR VALUES FROM ('2025-12-22') TO ('2025-12-23');


--
-- Name: d20251229; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251229 FOR VALUES FROM ('2025-12-29') TO ('2025-12-30');


--
-- Name: d20260105; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260105 FOR VALUES FROM ('2026-01-05') TO ('2026-01-06');


--
-- Name: d20260112; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260112 FOR VALUES FROM ('2026-01-12') TO ('2026-01-13');


--
-- Name: d20260119; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260119 FOR VALUES FROM ('2026-01-19') TO ('2026-01-20');


--
-- Name: d20260126; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260126 FOR VALUES FROM ('2026-01-26') TO ('2026-01-27');


--
-- Name: d20260213; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260213 FOR VALUES FROM ('2026-02-13') TO ('2026-02-14');


--
-- Name: d20260216; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260216 FOR VALUES FROM ('2026-02-16') TO ('2026-02-17');


--
-- Name: d20260223; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260223 FOR VALUES FROM ('2026-02-23') TO ('2026-02-24');


--
-- Name: d20260302; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260302 FOR VALUES FROM ('2026-03-02') TO ('2026-03-03');


--
-- Name: d20260309; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260309 FOR VALUES FROM ('2026-03-09') TO ('2026-03-10');


--
-- Name: d20260310; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260310 FOR VALUES FROM ('2026-03-10') TO ('2026-03-11');


--
-- Name: d20260316; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260316 FOR VALUES FROM ('2026-03-16') TO ('2026-03-17');


--
-- Name: d20260323; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260323 FOR VALUES FROM ('2026-03-23') TO ('2026-03-24');


--
-- Name: d20260330; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260330 FOR VALUES FROM ('2026-03-30') TO ('2026-03-31');


--
-- Name: d20260406; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260406 FOR VALUES FROM ('2026-04-06') TO ('2026-04-07');


--
-- Name: d20260413; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260413 FOR VALUES FROM ('2026-04-13') TO ('2026-04-14');


--
-- Name: d20260414; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260414 FOR VALUES FROM ('2026-04-14') TO ('2026-04-15');


--
-- Name: d20260420; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260420 FOR VALUES FROM ('2026-04-20') TO ('2026-04-21');


--
-- Name: d20260428; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260428 FOR VALUES FROM ('2026-04-28') TO ('2026-04-29');


--
-- Name: d20260505; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260505 FOR VALUES FROM ('2026-05-05') TO ('2026-05-06');


--
-- Name: d20260511; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260511 FOR VALUES FROM ('2026-05-11') TO ('2026-05-12');


--
-- Name: d20260518; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260518 FOR VALUES FROM ('2026-05-18') TO ('2026-05-19');


--
-- Name: d20260601; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260601 FOR VALUES FROM ('2026-06-01') TO ('2026-06-02');


--
-- Name: d20260611; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260611 FOR VALUES FROM ('2026-06-11') TO ('2026-06-12');


--
-- Name: d20260615; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260615 FOR VALUES FROM ('2026-06-15') TO ('2026-06-16');


--
-- Name: d20260623; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260623 FOR VALUES FROM ('2026-06-23') TO ('2026-06-24');


--
-- Name: d20260629; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260629 FOR VALUES FROM ('2026-06-29') TO ('2026-06-30');


--
-- Name: d20260706; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260706 FOR VALUES FROM ('2026-07-06') TO ('2026-07-07');


--
-- Name: d20260713; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260713 FOR VALUES FROM ('2026-07-13') TO ('2026-07-14');


--
-- Name: d20260720; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260720 FOR VALUES FROM ('2026-07-20') TO ('2026-07-21');


--
-- Name: d20260727; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260727 FOR VALUES FROM ('2026-07-27') TO ('2026-07-28');


--
-- Name: d20260803; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260803 FOR VALUES FROM ('2026-08-03') TO ('2026-08-04');


--
-- Name: d20260810; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260810 FOR VALUES FROM ('2026-08-10') TO ('2026-08-11');


--
-- Name: d20260817; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260817 FOR VALUES FROM ('2026-08-17') TO ('2026-08-18');


--
-- Name: d20260824; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260824 FOR VALUES FROM ('2026-08-24') TO ('2026-08-25');


--
-- Name: d20260831; Type: TABLE ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260831 FOR VALUES FROM ('2026-08-31') TO ('2026-09-01');


--
-- Name: community_snapshot PK_COMMUNITY_SNAPSHOT; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.community_snapshot
    ADD CONSTRAINT "PK_COMMUNITY_SNAPSHOT" PRIMARY KEY (package_id);


--
-- Name: dependent_removal_reason PK_DEPENDENT_REMOVAL_REASON; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.dependent_removal_reason
    ADD CONSTRAINT "PK_DEPENDENT_REMOVAL_REASON" PRIMARY KEY (package_id, period);


--
-- Name: dependent_transition PK_DEPENDENT_TRANSITION; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.dependent_transition
    ADD CONSTRAINT "PK_DEPENDENT_TRANSITION" PRIMARY KEY (package_id, period, kind);


--
-- Name: migration_pair PK_MIGRATION_PAIR; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.migration_pair
    ADD CONSTRAINT "PK_MIGRATION_PAIR" PRIMARY KEY (from_package_id, dep_kind, to_package_name);


--
-- Name: package PK_PACKAGE; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package
    ADD CONSTRAINT "PK_PACKAGE" PRIMARY KEY (package_id);


--
-- Name: package_env PK_PACKAGE_ENV; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package_env
    ADD CONSTRAINT "PK_PACKAGE_ENV" PRIMARY KEY (package_id, version);


--
-- Name: package_snapshot PK_PACKAGE_SNAPSHOT; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package_snapshot
    ADD CONSTRAINT "PK_PACKAGE_SNAPSHOT" PRIMARY KEY (package_id, snapshot_at);


--
-- Name: similar_package PK_SIMILAR_PACKAGE; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.similar_package
    ADD CONSTRAINT "PK_SIMILAR_PACKAGE" PRIMARY KEY (package_id, similar_package_id);


--
-- Name: snapshot PK_SNAPSHOT; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT "PK_SNAPSHOT" PRIMARY KEY (snapshot_at);


--
-- Name: version PK_VERSION; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.version
    ADD CONSTRAINT "PK_VERSION" PRIMARY KEY (package_id, version);


--
-- Name: community_snapshot UK_COMMUNITY_SNAPSHOT_SNAPSHOT_ID; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.community_snapshot
    ADD CONSTRAINT "UK_COMMUNITY_SNAPSHOT_SNAPSHOT_ID" UNIQUE (snapshot_id);


--
-- Name: package UK_PACKAGE_NAME; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package
    ADD CONSTRAINT "UK_PACKAGE_NAME" UNIQUE (name);


--
-- Name: similar_package UK_SIMILAR_PACKAGE_RANK; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.similar_package
    ADD CONSTRAINT "UK_SIMILAR_PACKAGE_RANK" UNIQUE (package_id, rank);


--
-- Name: available_package available_package_pkey; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.available_package
    ADD CONSTRAINT available_package_pkey PRIMARY KEY (package_id);


--
-- Name: etl_dataset_current etl_dataset_current_pkey; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_dataset_current
    ADD CONSTRAINT etl_dataset_current_pkey PRIMARY KEY (dataset);


--
-- Name: etl_load_attempt etl_load_attempt_execution_id_attempt_id_key; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_load_attempt
    ADD CONSTRAINT etl_load_attempt_execution_id_attempt_id_key UNIQUE (execution_id, attempt_id);


--
-- Name: etl_load_attempt etl_load_attempt_pkey; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_load_attempt
    ADD CONSTRAINT etl_load_attempt_pkey PRIMARY KEY (attempt_id);


--
-- Name: etl_load_execution etl_load_execution_dataset_execution_id_snapshot_at_manifes_key; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_load_execution
    ADD CONSTRAINT etl_load_execution_dataset_execution_id_snapshot_at_manifes_key UNIQUE (dataset, execution_id, snapshot_at, manifest_sha256);


--
-- Name: etl_load_execution etl_load_execution_pkey; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_load_execution
    ADD CONSTRAINT etl_load_execution_pkey PRIMARY KEY (execution_id);


--
-- Name: etl_snapshot_reference etl_snapshot_reference_pkey; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_snapshot_reference
    ADD CONSTRAINT etl_snapshot_reference_pkey PRIMARY KEY (execution_id, snapshot_at);


--
-- Name: flyway_schema_history flyway_schema_history_pk; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.flyway_schema_history
    ADD CONSTRAINT flyway_schema_history_pk PRIMARY KEY (installed_rank);


--
-- Name: package_version_snapshot pk_package_version_snapshot; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package_version_snapshot
    ADD CONSTRAINT pk_package_version_snapshot PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: etl_load_execution uq_etl_execution_dataset; Type: CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_load_execution
    ADD CONSTRAINT uq_etl_execution_dataset UNIQUE (dataset, execution_id);


--
-- Name: d20220508 d20220508_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220508
    ADD CONSTRAINT d20220508_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220515 d20220515_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220515
    ADD CONSTRAINT d20220515_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220522 d20220522_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220522
    ADD CONSTRAINT d20220522_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220529 d20220529_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220529
    ADD CONSTRAINT d20220529_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220605 d20220605_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220605
    ADD CONSTRAINT d20220605_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220613 d20220613_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220613
    ADD CONSTRAINT d20220613_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220620 d20220620_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220620
    ADD CONSTRAINT d20220620_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220627 d20220627_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220627
    ADD CONSTRAINT d20220627_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220704 d20220704_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220704
    ADD CONSTRAINT d20220704_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220712 d20220712_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220712
    ADD CONSTRAINT d20220712_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220718 d20220718_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220718
    ADD CONSTRAINT d20220718_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220726 d20220726_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220726
    ADD CONSTRAINT d20220726_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220801 d20220801_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220801
    ADD CONSTRAINT d20220801_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220808 d20220808_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220808
    ADD CONSTRAINT d20220808_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220815 d20220815_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220815
    ADD CONSTRAINT d20220815_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220822 d20220822_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220822
    ADD CONSTRAINT d20220822_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220829 d20220829_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220829
    ADD CONSTRAINT d20220829_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220905 d20220905_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220905
    ADD CONSTRAINT d20220905_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220913 d20220913_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220913
    ADD CONSTRAINT d20220913_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220919 d20220919_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220919
    ADD CONSTRAINT d20220919_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20220926 d20220926_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20220926
    ADD CONSTRAINT d20220926_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221003 d20221003_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221003
    ADD CONSTRAINT d20221003_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221010 d20221010_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221010
    ADD CONSTRAINT d20221010_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221017 d20221017_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221017
    ADD CONSTRAINT d20221017_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221024 d20221024_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221024
    ADD CONSTRAINT d20221024_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221031 d20221031_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221031
    ADD CONSTRAINT d20221031_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221107 d20221107_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221107
    ADD CONSTRAINT d20221107_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221114 d20221114_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221114
    ADD CONSTRAINT d20221114_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221121 d20221121_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221121
    ADD CONSTRAINT d20221121_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221128 d20221128_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221128
    ADD CONSTRAINT d20221128_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221205 d20221205_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221205
    ADD CONSTRAINT d20221205_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221212 d20221212_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221212
    ADD CONSTRAINT d20221212_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221219 d20221219_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221219
    ADD CONSTRAINT d20221219_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20221226 d20221226_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20221226
    ADD CONSTRAINT d20221226_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230102 d20230102_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230102
    ADD CONSTRAINT d20230102_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230109 d20230109_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230109
    ADD CONSTRAINT d20230109_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230116 d20230116_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230116
    ADD CONSTRAINT d20230116_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230123 d20230123_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230123
    ADD CONSTRAINT d20230123_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230129 d20230129_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230129
    ADD CONSTRAINT d20230129_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230206 d20230206_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230206
    ADD CONSTRAINT d20230206_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230213 d20230213_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230213
    ADD CONSTRAINT d20230213_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230220 d20230220_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230220
    ADD CONSTRAINT d20230220_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230227 d20230227_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230227
    ADD CONSTRAINT d20230227_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230306 d20230306_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230306
    ADD CONSTRAINT d20230306_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230313 d20230313_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230313
    ADD CONSTRAINT d20230313_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230321 d20230321_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230321
    ADD CONSTRAINT d20230321_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230327 d20230327_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230327
    ADD CONSTRAINT d20230327_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230403 d20230403_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230403
    ADD CONSTRAINT d20230403_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230410 d20230410_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230410
    ADD CONSTRAINT d20230410_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230417 d20230417_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230417
    ADD CONSTRAINT d20230417_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230420 d20230420_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230420
    ADD CONSTRAINT d20230420_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230501 d20230501_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230501
    ADD CONSTRAINT d20230501_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230502 d20230502_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230502
    ADD CONSTRAINT d20230502_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230508 d20230508_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230508
    ADD CONSTRAINT d20230508_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230515 d20230515_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230515
    ADD CONSTRAINT d20230515_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230522 d20230522_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230522
    ADD CONSTRAINT d20230522_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230529 d20230529_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230529
    ADD CONSTRAINT d20230529_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230605 d20230605_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230605
    ADD CONSTRAINT d20230605_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230612 d20230612_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230612
    ADD CONSTRAINT d20230612_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230620 d20230620_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230620
    ADD CONSTRAINT d20230620_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230626 d20230626_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230626
    ADD CONSTRAINT d20230626_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230703 d20230703_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230703
    ADD CONSTRAINT d20230703_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230710 d20230710_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230710
    ADD CONSTRAINT d20230710_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230717 d20230717_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230717
    ADD CONSTRAINT d20230717_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230724 d20230724_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230724
    ADD CONSTRAINT d20230724_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230731 d20230731_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230731
    ADD CONSTRAINT d20230731_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230807 d20230807_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230807
    ADD CONSTRAINT d20230807_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230814 d20230814_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230814
    ADD CONSTRAINT d20230814_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230821 d20230821_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230821
    ADD CONSTRAINT d20230821_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230828 d20230828_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230828
    ADD CONSTRAINT d20230828_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230904 d20230904_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230904
    ADD CONSTRAINT d20230904_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230911 d20230911_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230911
    ADD CONSTRAINT d20230911_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230918 d20230918_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230918
    ADD CONSTRAINT d20230918_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20230926 d20230926_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20230926
    ADD CONSTRAINT d20230926_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231002 d20231002_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231002
    ADD CONSTRAINT d20231002_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231009 d20231009_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231009
    ADD CONSTRAINT d20231009_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231016 d20231016_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231016
    ADD CONSTRAINT d20231016_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231023 d20231023_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231023
    ADD CONSTRAINT d20231023_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231030 d20231030_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231030
    ADD CONSTRAINT d20231030_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231106 d20231106_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231106
    ADD CONSTRAINT d20231106_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231113 d20231113_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231113
    ADD CONSTRAINT d20231113_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231120 d20231120_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231120
    ADD CONSTRAINT d20231120_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231127 d20231127_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231127
    ADD CONSTRAINT d20231127_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231204 d20231204_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231204
    ADD CONSTRAINT d20231204_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231211 d20231211_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231211
    ADD CONSTRAINT d20231211_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231218 d20231218_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231218
    ADD CONSTRAINT d20231218_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20231225 d20231225_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20231225
    ADD CONSTRAINT d20231225_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240101 d20240101_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240101
    ADD CONSTRAINT d20240101_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240108 d20240108_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240108
    ADD CONSTRAINT d20240108_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240115 d20240115_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240115
    ADD CONSTRAINT d20240115_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240122 d20240122_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240122
    ADD CONSTRAINT d20240122_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240129 d20240129_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240129
    ADD CONSTRAINT d20240129_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240205 d20240205_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240205
    ADD CONSTRAINT d20240205_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240212 d20240212_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240212
    ADD CONSTRAINT d20240212_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240219 d20240219_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240219
    ADD CONSTRAINT d20240219_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240226 d20240226_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240226
    ADD CONSTRAINT d20240226_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240304 d20240304_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240304
    ADD CONSTRAINT d20240304_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240305 d20240305_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240305
    ADD CONSTRAINT d20240305_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240311 d20240311_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240311
    ADD CONSTRAINT d20240311_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240318 d20240318_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240318
    ADD CONSTRAINT d20240318_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240325 d20240325_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240325
    ADD CONSTRAINT d20240325_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240401 d20240401_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240401
    ADD CONSTRAINT d20240401_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240409 d20240409_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240409
    ADD CONSTRAINT d20240409_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240415 d20240415_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240415
    ADD CONSTRAINT d20240415_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240421 d20240421_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240421
    ADD CONSTRAINT d20240421_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240429 d20240429_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240429
    ADD CONSTRAINT d20240429_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240509 d20240509_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240509
    ADD CONSTRAINT d20240509_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240513 d20240513_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240513
    ADD CONSTRAINT d20240513_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240520 d20240520_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240520
    ADD CONSTRAINT d20240520_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240527 d20240527_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240527
    ADD CONSTRAINT d20240527_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240603 d20240603_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240603
    ADD CONSTRAINT d20240603_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240610 d20240610_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240610
    ADD CONSTRAINT d20240610_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240617 d20240617_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240617
    ADD CONSTRAINT d20240617_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240624 d20240624_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240624
    ADD CONSTRAINT d20240624_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240701 d20240701_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240701
    ADD CONSTRAINT d20240701_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240708 d20240708_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240708
    ADD CONSTRAINT d20240708_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240709 d20240709_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240709
    ADD CONSTRAINT d20240709_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240715 d20240715_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240715
    ADD CONSTRAINT d20240715_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240723 d20240723_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240723
    ADD CONSTRAINT d20240723_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240729 d20240729_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240729
    ADD CONSTRAINT d20240729_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240805 d20240805_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240805
    ADD CONSTRAINT d20240805_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240812 d20240812_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240812
    ADD CONSTRAINT d20240812_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240819 d20240819_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240819
    ADD CONSTRAINT d20240819_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240829 d20240829_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240829
    ADD CONSTRAINT d20240829_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240902 d20240902_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240902
    ADD CONSTRAINT d20240902_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240909 d20240909_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240909
    ADD CONSTRAINT d20240909_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240916 d20240916_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240916
    ADD CONSTRAINT d20240916_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240923 d20240923_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240923
    ADD CONSTRAINT d20240923_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20240930 d20240930_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20240930
    ADD CONSTRAINT d20240930_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241007 d20241007_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241007
    ADD CONSTRAINT d20241007_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241014 d20241014_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241014
    ADD CONSTRAINT d20241014_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241021 d20241021_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241021
    ADD CONSTRAINT d20241021_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241028 d20241028_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241028
    ADD CONSTRAINT d20241028_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241104 d20241104_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241104
    ADD CONSTRAINT d20241104_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241111 d20241111_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241111
    ADD CONSTRAINT d20241111_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241119 d20241119_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241119
    ADD CONSTRAINT d20241119_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241125 d20241125_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241125
    ADD CONSTRAINT d20241125_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241202 d20241202_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241202
    ADD CONSTRAINT d20241202_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241209 d20241209_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241209
    ADD CONSTRAINT d20241209_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241216 d20241216_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241216
    ADD CONSTRAINT d20241216_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241223 d20241223_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241223
    ADD CONSTRAINT d20241223_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20241230 d20241230_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20241230
    ADD CONSTRAINT d20241230_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250106 d20250106_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250106
    ADD CONSTRAINT d20250106_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250113 d20250113_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250113
    ADD CONSTRAINT d20250113_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250120 d20250120_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250120
    ADD CONSTRAINT d20250120_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250127 d20250127_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250127
    ADD CONSTRAINT d20250127_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250203 d20250203_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250203
    ADD CONSTRAINT d20250203_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250210 d20250210_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250210
    ADD CONSTRAINT d20250210_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250218 d20250218_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250218
    ADD CONSTRAINT d20250218_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250225 d20250225_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250225
    ADD CONSTRAINT d20250225_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250303 d20250303_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250303
    ADD CONSTRAINT d20250303_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250310 d20250310_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250310
    ADD CONSTRAINT d20250310_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250318 d20250318_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250318
    ADD CONSTRAINT d20250318_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250324 d20250324_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250324
    ADD CONSTRAINT d20250324_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250331 d20250331_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250331
    ADD CONSTRAINT d20250331_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250407 d20250407_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250407
    ADD CONSTRAINT d20250407_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250414 d20250414_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250414
    ADD CONSTRAINT d20250414_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250422 d20250422_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250422
    ADD CONSTRAINT d20250422_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250428 d20250428_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250428
    ADD CONSTRAINT d20250428_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250505 d20250505_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250505
    ADD CONSTRAINT d20250505_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250512 d20250512_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250512
    ADD CONSTRAINT d20250512_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250519 d20250519_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250519
    ADD CONSTRAINT d20250519_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250526 d20250526_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250526
    ADD CONSTRAINT d20250526_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250602 d20250602_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250602
    ADD CONSTRAINT d20250602_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250609 d20250609_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250609
    ADD CONSTRAINT d20250609_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250616 d20250616_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250616
    ADD CONSTRAINT d20250616_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250623 d20250623_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250623
    ADD CONSTRAINT d20250623_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250630 d20250630_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250630
    ADD CONSTRAINT d20250630_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250707 d20250707_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250707
    ADD CONSTRAINT d20250707_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250714 d20250714_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250714
    ADD CONSTRAINT d20250714_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250721 d20250721_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250721
    ADD CONSTRAINT d20250721_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250728 d20250728_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250728
    ADD CONSTRAINT d20250728_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250804 d20250804_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250804
    ADD CONSTRAINT d20250804_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250811 d20250811_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250811
    ADD CONSTRAINT d20250811_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250818 d20250818_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250818
    ADD CONSTRAINT d20250818_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250825 d20250825_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250825
    ADD CONSTRAINT d20250825_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250901 d20250901_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250901
    ADD CONSTRAINT d20250901_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250908 d20250908_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250908
    ADD CONSTRAINT d20250908_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250915 d20250915_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250915
    ADD CONSTRAINT d20250915_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250922 d20250922_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250922
    ADD CONSTRAINT d20250922_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20250929 d20250929_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20250929
    ADD CONSTRAINT d20250929_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251006 d20251006_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251006
    ADD CONSTRAINT d20251006_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251013 d20251013_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251013
    ADD CONSTRAINT d20251013_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251020 d20251020_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251020
    ADD CONSTRAINT d20251020_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251027 d20251027_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251027
    ADD CONSTRAINT d20251027_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251103 d20251103_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251103
    ADD CONSTRAINT d20251103_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251110 d20251110_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251110
    ADD CONSTRAINT d20251110_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251117 d20251117_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251117
    ADD CONSTRAINT d20251117_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251124 d20251124_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251124
    ADD CONSTRAINT d20251124_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251201 d20251201_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251201
    ADD CONSTRAINT d20251201_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251208 d20251208_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251208
    ADD CONSTRAINT d20251208_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251215 d20251215_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251215
    ADD CONSTRAINT d20251215_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251222 d20251222_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251222
    ADD CONSTRAINT d20251222_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20251229 d20251229_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20251229
    ADD CONSTRAINT d20251229_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260105 d20260105_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260105
    ADD CONSTRAINT d20260105_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260112 d20260112_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260112
    ADD CONSTRAINT d20260112_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260119 d20260119_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260119
    ADD CONSTRAINT d20260119_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260126 d20260126_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260126
    ADD CONSTRAINT d20260126_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260213 d20260213_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260213
    ADD CONSTRAINT d20260213_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260216 d20260216_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260216
    ADD CONSTRAINT d20260216_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260223 d20260223_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260223
    ADD CONSTRAINT d20260223_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260302 d20260302_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260302
    ADD CONSTRAINT d20260302_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260309 d20260309_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260309
    ADD CONSTRAINT d20260309_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260310 d20260310_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260310
    ADD CONSTRAINT d20260310_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260316 d20260316_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260316
    ADD CONSTRAINT d20260316_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260323 d20260323_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260323
    ADD CONSTRAINT d20260323_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260330 d20260330_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260330
    ADD CONSTRAINT d20260330_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260406 d20260406_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260406
    ADD CONSTRAINT d20260406_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260413 d20260413_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260413
    ADD CONSTRAINT d20260413_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260414 d20260414_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260414
    ADD CONSTRAINT d20260414_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260420 d20260420_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260420
    ADD CONSTRAINT d20260420_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260428 d20260428_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260428
    ADD CONSTRAINT d20260428_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260505 d20260505_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260505
    ADD CONSTRAINT d20260505_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260511 d20260511_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260511
    ADD CONSTRAINT d20260511_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260518 d20260518_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260518
    ADD CONSTRAINT d20260518_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260601 d20260601_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260601
    ADD CONSTRAINT d20260601_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260611 d20260611_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260611
    ADD CONSTRAINT d20260611_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260615 d20260615_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260615
    ADD CONSTRAINT d20260615_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260623 d20260623_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260623
    ADD CONSTRAINT d20260623_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260629 d20260629_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260629
    ADD CONSTRAINT d20260629_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260706 d20260706_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260706
    ADD CONSTRAINT d20260706_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260713 d20260713_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260713
    ADD CONSTRAINT d20260713_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260720 d20260720_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260720
    ADD CONSTRAINT d20260720_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260727 d20260727_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260727
    ADD CONSTRAINT d20260727_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260803 d20260803_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260803
    ADD CONSTRAINT d20260803_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260810 d20260810_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260810
    ADD CONSTRAINT d20260810_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260817 d20260817_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260817
    ADD CONSTRAINT d20260817_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260824 d20260824_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260824
    ADD CONSTRAINT d20260824_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: d20260831 d20260831_pkey; Type: CONSTRAINT; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER TABLE ONLY vd193_reload_20260912_ready01.d20260831
    ADD CONSTRAINT d20260831_pkey PRIMARY KEY (package_id, version, snapshot_at);


--
-- Name: flyway_schema_history_s_idx; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX flyway_schema_history_s_idx ON public.flyway_schema_history USING btree (success);


--
-- Name: idx_community_snapshot_collected_at; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX idx_community_snapshot_collected_at ON public.community_snapshot USING btree (collected_at);


--
-- Name: idx_package_name_prefix; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX idx_package_name_prefix ON public.package USING btree (name text_pattern_ops);


--
-- Name: idx_pvs_pkg_snapshot; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX idx_pvs_pkg_snapshot ON ONLY public.package_version_snapshot USING btree (package_id, snapshot_at);


--
-- Name: idx_version_pkg_ordinal; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX idx_version_pkg_ordinal ON public.version USING btree (package_id, ordinal DESC);


--
-- Name: ix_etl_load_attempt_execution; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX ix_etl_load_attempt_execution ON public.etl_load_attempt USING btree (execution_id, created_at);


--
-- Name: ix_etl_load_execution_input; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX ix_etl_load_execution_input ON public.etl_load_execution USING btree (dataset, manifest_sha256, status);


--
-- Name: ix_etl_snapshot_reference_date; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX ix_etl_snapshot_reference_date ON public.etl_snapshot_reference USING btree (snapshot_at);


--
-- Name: ix_package_snapshot_history_date; Type: INDEX; Schema: public; Owner: pickage
--

CREATE INDEX ix_package_snapshot_history_date ON public.package_snapshot USING brin (snapshot_at) WITH (autosummarize='on');


--
-- Name: d20220508_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220508_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220508 USING btree (package_id, snapshot_at);


--
-- Name: d20220515_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220515_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220515 USING btree (package_id, snapshot_at);


--
-- Name: d20220522_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220522_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220522 USING btree (package_id, snapshot_at);


--
-- Name: d20220529_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220529_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220529 USING btree (package_id, snapshot_at);


--
-- Name: d20220605_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220605_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220605 USING btree (package_id, snapshot_at);


--
-- Name: d20220613_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220613_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220613 USING btree (package_id, snapshot_at);


--
-- Name: d20220620_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220620_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220620 USING btree (package_id, snapshot_at);


--
-- Name: d20220627_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220627_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220627 USING btree (package_id, snapshot_at);


--
-- Name: d20220704_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220704_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220704 USING btree (package_id, snapshot_at);


--
-- Name: d20220712_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220712_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220712 USING btree (package_id, snapshot_at);


--
-- Name: d20220718_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220718_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220718 USING btree (package_id, snapshot_at);


--
-- Name: d20220726_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220726_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220726 USING btree (package_id, snapshot_at);


--
-- Name: d20220801_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220801_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220801 USING btree (package_id, snapshot_at);


--
-- Name: d20220808_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220808_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220808 USING btree (package_id, snapshot_at);


--
-- Name: d20220815_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220815_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220815 USING btree (package_id, snapshot_at);


--
-- Name: d20220822_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220822_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220822 USING btree (package_id, snapshot_at);


--
-- Name: d20220829_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220829_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220829 USING btree (package_id, snapshot_at);


--
-- Name: d20220905_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220905_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220905 USING btree (package_id, snapshot_at);


--
-- Name: d20220913_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220913_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220913 USING btree (package_id, snapshot_at);


--
-- Name: d20220919_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220919_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220919 USING btree (package_id, snapshot_at);


--
-- Name: d20220926_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20220926_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20220926 USING btree (package_id, snapshot_at);


--
-- Name: d20221003_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221003_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221003 USING btree (package_id, snapshot_at);


--
-- Name: d20221010_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221010_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221010 USING btree (package_id, snapshot_at);


--
-- Name: d20221017_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221017_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221017 USING btree (package_id, snapshot_at);


--
-- Name: d20221024_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221024_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221024 USING btree (package_id, snapshot_at);


--
-- Name: d20221031_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221031_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221031 USING btree (package_id, snapshot_at);


--
-- Name: d20221107_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221107_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221107 USING btree (package_id, snapshot_at);


--
-- Name: d20221114_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221114_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221114 USING btree (package_id, snapshot_at);


--
-- Name: d20221121_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221121_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221121 USING btree (package_id, snapshot_at);


--
-- Name: d20221128_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221128_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221128 USING btree (package_id, snapshot_at);


--
-- Name: d20221205_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221205_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221205 USING btree (package_id, snapshot_at);


--
-- Name: d20221212_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221212_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221212 USING btree (package_id, snapshot_at);


--
-- Name: d20221219_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221219_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221219 USING btree (package_id, snapshot_at);


--
-- Name: d20221226_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20221226_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20221226 USING btree (package_id, snapshot_at);


--
-- Name: d20230102_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230102_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230102 USING btree (package_id, snapshot_at);


--
-- Name: d20230109_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230109_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230109 USING btree (package_id, snapshot_at);


--
-- Name: d20230116_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230116_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230116 USING btree (package_id, snapshot_at);


--
-- Name: d20230123_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230123_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230123 USING btree (package_id, snapshot_at);


--
-- Name: d20230129_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230129_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230129 USING btree (package_id, snapshot_at);


--
-- Name: d20230206_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230206_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230206 USING btree (package_id, snapshot_at);


--
-- Name: d20230213_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230213_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230213 USING btree (package_id, snapshot_at);


--
-- Name: d20230220_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230220_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230220 USING btree (package_id, snapshot_at);


--
-- Name: d20230227_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230227_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230227 USING btree (package_id, snapshot_at);


--
-- Name: d20230306_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230306_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230306 USING btree (package_id, snapshot_at);


--
-- Name: d20230313_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230313_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230313 USING btree (package_id, snapshot_at);


--
-- Name: d20230321_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230321_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230321 USING btree (package_id, snapshot_at);


--
-- Name: d20230327_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230327_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230327 USING btree (package_id, snapshot_at);


--
-- Name: d20230403_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230403_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230403 USING btree (package_id, snapshot_at);


--
-- Name: d20230410_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230410_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230410 USING btree (package_id, snapshot_at);


--
-- Name: d20230417_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230417_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230417 USING btree (package_id, snapshot_at);


--
-- Name: d20230420_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230420_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230420 USING btree (package_id, snapshot_at);


--
-- Name: d20230501_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230501_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230501 USING btree (package_id, snapshot_at);


--
-- Name: d20230502_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230502_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230502 USING btree (package_id, snapshot_at);


--
-- Name: d20230508_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230508_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230508 USING btree (package_id, snapshot_at);


--
-- Name: d20230515_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230515_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230515 USING btree (package_id, snapshot_at);


--
-- Name: d20230522_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230522_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230522 USING btree (package_id, snapshot_at);


--
-- Name: d20230529_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230529_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230529 USING btree (package_id, snapshot_at);


--
-- Name: d20230605_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230605_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230605 USING btree (package_id, snapshot_at);


--
-- Name: d20230612_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230612_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230612 USING btree (package_id, snapshot_at);


--
-- Name: d20230620_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230620_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230620 USING btree (package_id, snapshot_at);


--
-- Name: d20230626_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230626_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230626 USING btree (package_id, snapshot_at);


--
-- Name: d20230703_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230703_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230703 USING btree (package_id, snapshot_at);


--
-- Name: d20230710_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230710_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230710 USING btree (package_id, snapshot_at);


--
-- Name: d20230717_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230717_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230717 USING btree (package_id, snapshot_at);


--
-- Name: d20230724_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230724_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230724 USING btree (package_id, snapshot_at);


--
-- Name: d20230731_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230731_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230731 USING btree (package_id, snapshot_at);


--
-- Name: d20230807_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230807_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230807 USING btree (package_id, snapshot_at);


--
-- Name: d20230814_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230814_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230814 USING btree (package_id, snapshot_at);


--
-- Name: d20230821_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230821_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230821 USING btree (package_id, snapshot_at);


--
-- Name: d20230828_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230828_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230828 USING btree (package_id, snapshot_at);


--
-- Name: d20230904_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230904_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230904 USING btree (package_id, snapshot_at);


--
-- Name: d20230911_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230911_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230911 USING btree (package_id, snapshot_at);


--
-- Name: d20230918_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230918_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230918 USING btree (package_id, snapshot_at);


--
-- Name: d20230926_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20230926_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20230926 USING btree (package_id, snapshot_at);


--
-- Name: d20231002_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231002_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231002 USING btree (package_id, snapshot_at);


--
-- Name: d20231009_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231009_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231009 USING btree (package_id, snapshot_at);


--
-- Name: d20231016_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231016_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231016 USING btree (package_id, snapshot_at);


--
-- Name: d20231023_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231023_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231023 USING btree (package_id, snapshot_at);


--
-- Name: d20231030_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231030_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231030 USING btree (package_id, snapshot_at);


--
-- Name: d20231106_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231106_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231106 USING btree (package_id, snapshot_at);


--
-- Name: d20231113_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231113_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231113 USING btree (package_id, snapshot_at);


--
-- Name: d20231120_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231120_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231120 USING btree (package_id, snapshot_at);


--
-- Name: d20231127_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231127_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231127 USING btree (package_id, snapshot_at);


--
-- Name: d20231204_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231204_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231204 USING btree (package_id, snapshot_at);


--
-- Name: d20231211_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231211_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231211 USING btree (package_id, snapshot_at);


--
-- Name: d20231218_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231218_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231218 USING btree (package_id, snapshot_at);


--
-- Name: d20231225_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20231225_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20231225 USING btree (package_id, snapshot_at);


--
-- Name: d20240101_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240101_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240101 USING btree (package_id, snapshot_at);


--
-- Name: d20240108_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240108_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240108 USING btree (package_id, snapshot_at);


--
-- Name: d20240115_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240115_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240115 USING btree (package_id, snapshot_at);


--
-- Name: d20240122_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240122_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240122 USING btree (package_id, snapshot_at);


--
-- Name: d20240129_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240129_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240129 USING btree (package_id, snapshot_at);


--
-- Name: d20240205_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240205_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240205 USING btree (package_id, snapshot_at);


--
-- Name: d20240212_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240212_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240212 USING btree (package_id, snapshot_at);


--
-- Name: d20240219_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240219_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240219 USING btree (package_id, snapshot_at);


--
-- Name: d20240226_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240226_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240226 USING btree (package_id, snapshot_at);


--
-- Name: d20240304_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240304_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240304 USING btree (package_id, snapshot_at);


--
-- Name: d20240305_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240305_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240305 USING btree (package_id, snapshot_at);


--
-- Name: d20240311_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240311_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240311 USING btree (package_id, snapshot_at);


--
-- Name: d20240318_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240318_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240318 USING btree (package_id, snapshot_at);


--
-- Name: d20240325_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240325_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240325 USING btree (package_id, snapshot_at);


--
-- Name: d20240401_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240401_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240401 USING btree (package_id, snapshot_at);


--
-- Name: d20240409_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240409_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240409 USING btree (package_id, snapshot_at);


--
-- Name: d20240415_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240415_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240415 USING btree (package_id, snapshot_at);


--
-- Name: d20240421_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240421_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240421 USING btree (package_id, snapshot_at);


--
-- Name: d20240429_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240429_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240429 USING btree (package_id, snapshot_at);


--
-- Name: d20240509_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240509_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240509 USING btree (package_id, snapshot_at);


--
-- Name: d20240513_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240513_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240513 USING btree (package_id, snapshot_at);


--
-- Name: d20240520_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240520_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240520 USING btree (package_id, snapshot_at);


--
-- Name: d20240527_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240527_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240527 USING btree (package_id, snapshot_at);


--
-- Name: d20240603_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240603_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240603 USING btree (package_id, snapshot_at);


--
-- Name: d20240610_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240610_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240610 USING btree (package_id, snapshot_at);


--
-- Name: d20240617_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240617_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240617 USING btree (package_id, snapshot_at);


--
-- Name: d20240624_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240624_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240624 USING btree (package_id, snapshot_at);


--
-- Name: d20240701_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240701_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240701 USING btree (package_id, snapshot_at);


--
-- Name: d20240708_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240708_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240708 USING btree (package_id, snapshot_at);


--
-- Name: d20240709_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240709_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240709 USING btree (package_id, snapshot_at);


--
-- Name: d20240715_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240715_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240715 USING btree (package_id, snapshot_at);


--
-- Name: d20240723_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240723_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240723 USING btree (package_id, snapshot_at);


--
-- Name: d20240729_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240729_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240729 USING btree (package_id, snapshot_at);


--
-- Name: d20240805_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240805_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240805 USING btree (package_id, snapshot_at);


--
-- Name: d20240812_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240812_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240812 USING btree (package_id, snapshot_at);


--
-- Name: d20240819_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240819_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240819 USING btree (package_id, snapshot_at);


--
-- Name: d20240829_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240829_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240829 USING btree (package_id, snapshot_at);


--
-- Name: d20240902_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240902_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240902 USING btree (package_id, snapshot_at);


--
-- Name: d20240909_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240909_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240909 USING btree (package_id, snapshot_at);


--
-- Name: d20240916_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240916_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240916 USING btree (package_id, snapshot_at);


--
-- Name: d20240923_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240923_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240923 USING btree (package_id, snapshot_at);


--
-- Name: d20240930_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20240930_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20240930 USING btree (package_id, snapshot_at);


--
-- Name: d20241007_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241007_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241007 USING btree (package_id, snapshot_at);


--
-- Name: d20241014_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241014_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241014 USING btree (package_id, snapshot_at);


--
-- Name: d20241021_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241021_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241021 USING btree (package_id, snapshot_at);


--
-- Name: d20241028_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241028_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241028 USING btree (package_id, snapshot_at);


--
-- Name: d20241104_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241104_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241104 USING btree (package_id, snapshot_at);


--
-- Name: d20241111_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241111_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241111 USING btree (package_id, snapshot_at);


--
-- Name: d20241119_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241119_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241119 USING btree (package_id, snapshot_at);


--
-- Name: d20241125_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241125_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241125 USING btree (package_id, snapshot_at);


--
-- Name: d20241202_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241202_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241202 USING btree (package_id, snapshot_at);


--
-- Name: d20241209_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241209_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241209 USING btree (package_id, snapshot_at);


--
-- Name: d20241216_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241216_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241216 USING btree (package_id, snapshot_at);


--
-- Name: d20241223_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241223_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241223 USING btree (package_id, snapshot_at);


--
-- Name: d20241230_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20241230_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20241230 USING btree (package_id, snapshot_at);


--
-- Name: d20250106_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250106_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250106 USING btree (package_id, snapshot_at);


--
-- Name: d20250113_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250113_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250113 USING btree (package_id, snapshot_at);


--
-- Name: d20250120_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250120_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250120 USING btree (package_id, snapshot_at);


--
-- Name: d20250127_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250127_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250127 USING btree (package_id, snapshot_at);


--
-- Name: d20250203_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250203_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250203 USING btree (package_id, snapshot_at);


--
-- Name: d20250210_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250210_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250210 USING btree (package_id, snapshot_at);


--
-- Name: d20250218_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250218_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250218 USING btree (package_id, snapshot_at);


--
-- Name: d20250225_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250225_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250225 USING btree (package_id, snapshot_at);


--
-- Name: d20250303_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250303_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250303 USING btree (package_id, snapshot_at);


--
-- Name: d20250310_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250310_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250310 USING btree (package_id, snapshot_at);


--
-- Name: d20250318_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250318_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250318 USING btree (package_id, snapshot_at);


--
-- Name: d20250324_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250324_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250324 USING btree (package_id, snapshot_at);


--
-- Name: d20250331_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250331_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250331 USING btree (package_id, snapshot_at);


--
-- Name: d20250407_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250407_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250407 USING btree (package_id, snapshot_at);


--
-- Name: d20250414_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250414_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250414 USING btree (package_id, snapshot_at);


--
-- Name: d20250422_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250422_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250422 USING btree (package_id, snapshot_at);


--
-- Name: d20250428_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250428_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250428 USING btree (package_id, snapshot_at);


--
-- Name: d20250505_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250505_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250505 USING btree (package_id, snapshot_at);


--
-- Name: d20250512_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250512_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250512 USING btree (package_id, snapshot_at);


--
-- Name: d20250519_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250519_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250519 USING btree (package_id, snapshot_at);


--
-- Name: d20250526_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250526_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250526 USING btree (package_id, snapshot_at);


--
-- Name: d20250602_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250602_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250602 USING btree (package_id, snapshot_at);


--
-- Name: d20250609_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250609_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250609 USING btree (package_id, snapshot_at);


--
-- Name: d20250616_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250616_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250616 USING btree (package_id, snapshot_at);


--
-- Name: d20250623_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250623_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250623 USING btree (package_id, snapshot_at);


--
-- Name: d20250630_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250630_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250630 USING btree (package_id, snapshot_at);


--
-- Name: d20250707_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250707_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250707 USING btree (package_id, snapshot_at);


--
-- Name: d20250714_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250714_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250714 USING btree (package_id, snapshot_at);


--
-- Name: d20250721_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250721_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250721 USING btree (package_id, snapshot_at);


--
-- Name: d20250728_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250728_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250728 USING btree (package_id, snapshot_at);


--
-- Name: d20250804_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250804_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250804 USING btree (package_id, snapshot_at);


--
-- Name: d20250811_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250811_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250811 USING btree (package_id, snapshot_at);


--
-- Name: d20250818_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250818_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250818 USING btree (package_id, snapshot_at);


--
-- Name: d20250825_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250825_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250825 USING btree (package_id, snapshot_at);


--
-- Name: d20250901_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250901_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250901 USING btree (package_id, snapshot_at);


--
-- Name: d20250908_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250908_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250908 USING btree (package_id, snapshot_at);


--
-- Name: d20250915_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250915_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250915 USING btree (package_id, snapshot_at);


--
-- Name: d20250922_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250922_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250922 USING btree (package_id, snapshot_at);


--
-- Name: d20250929_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20250929_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20250929 USING btree (package_id, snapshot_at);


--
-- Name: d20251006_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251006_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251006 USING btree (package_id, snapshot_at);


--
-- Name: d20251013_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251013_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251013 USING btree (package_id, snapshot_at);


--
-- Name: d20251020_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251020_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251020 USING btree (package_id, snapshot_at);


--
-- Name: d20251027_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251027_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251027 USING btree (package_id, snapshot_at);


--
-- Name: d20251103_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251103_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251103 USING btree (package_id, snapshot_at);


--
-- Name: d20251110_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251110_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251110 USING btree (package_id, snapshot_at);


--
-- Name: d20251117_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251117_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251117 USING btree (package_id, snapshot_at);


--
-- Name: d20251124_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251124_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251124 USING btree (package_id, snapshot_at);


--
-- Name: d20251201_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251201_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251201 USING btree (package_id, snapshot_at);


--
-- Name: d20251208_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251208_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251208 USING btree (package_id, snapshot_at);


--
-- Name: d20251215_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251215_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251215 USING btree (package_id, snapshot_at);


--
-- Name: d20251222_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251222_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251222 USING btree (package_id, snapshot_at);


--
-- Name: d20251229_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20251229_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20251229 USING btree (package_id, snapshot_at);


--
-- Name: d20260105_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260105_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260105 USING btree (package_id, snapshot_at);


--
-- Name: d20260112_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260112_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260112 USING btree (package_id, snapshot_at);


--
-- Name: d20260119_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260119_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260119 USING btree (package_id, snapshot_at);


--
-- Name: d20260126_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260126_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260126 USING btree (package_id, snapshot_at);


--
-- Name: d20260213_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260213_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260213 USING btree (package_id, snapshot_at);


--
-- Name: d20260216_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260216_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260216 USING btree (package_id, snapshot_at);


--
-- Name: d20260223_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260223_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260223 USING btree (package_id, snapshot_at);


--
-- Name: d20260302_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260302_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260302 USING btree (package_id, snapshot_at);


--
-- Name: d20260309_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260309_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260309 USING btree (package_id, snapshot_at);


--
-- Name: d20260310_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260310_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260310 USING btree (package_id, snapshot_at);


--
-- Name: d20260316_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260316_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260316 USING btree (package_id, snapshot_at);


--
-- Name: d20260323_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260323_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260323 USING btree (package_id, snapshot_at);


--
-- Name: d20260330_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260330_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260330 USING btree (package_id, snapshot_at);


--
-- Name: d20260406_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260406_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260406 USING btree (package_id, snapshot_at);


--
-- Name: d20260413_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260413_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260413 USING btree (package_id, snapshot_at);


--
-- Name: d20260414_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260414_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260414 USING btree (package_id, snapshot_at);


--
-- Name: d20260420_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260420_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260420 USING btree (package_id, snapshot_at);


--
-- Name: d20260428_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260428_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260428 USING btree (package_id, snapshot_at);


--
-- Name: d20260505_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260505_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260505 USING btree (package_id, snapshot_at);


--
-- Name: d20260511_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260511_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260511 USING btree (package_id, snapshot_at);


--
-- Name: d20260518_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260518_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260518 USING btree (package_id, snapshot_at);


--
-- Name: d20260601_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260601_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260601 USING btree (package_id, snapshot_at);


--
-- Name: d20260611_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260611_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260611 USING btree (package_id, snapshot_at);


--
-- Name: d20260615_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260615_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260615 USING btree (package_id, snapshot_at);


--
-- Name: d20260623_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260623_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260623 USING btree (package_id, snapshot_at);


--
-- Name: d20260629_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260629_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260629 USING btree (package_id, snapshot_at);


--
-- Name: d20260706_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260706_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260706 USING btree (package_id, snapshot_at);


--
-- Name: d20260713_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260713_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260713 USING btree (package_id, snapshot_at);


--
-- Name: d20260720_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260720_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260720 USING btree (package_id, snapshot_at);


--
-- Name: d20260727_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260727_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260727 USING btree (package_id, snapshot_at);


--
-- Name: d20260803_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260803_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260803 USING btree (package_id, snapshot_at);


--
-- Name: d20260810_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260810_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260810 USING btree (package_id, snapshot_at);


--
-- Name: d20260817_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260817_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260817 USING btree (package_id, snapshot_at);


--
-- Name: d20260824_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260824_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260824 USING btree (package_id, snapshot_at);


--
-- Name: d20260831_package_id_snapshot_at_idx; Type: INDEX; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

CREATE INDEX d20260831_package_id_snapshot_at_idx ON vd193_reload_20260912_ready01.d20260831 USING btree (package_id, snapshot_at);


--
-- Name: d20220508_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220508_package_id_snapshot_at_idx;


--
-- Name: d20220508_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220508_pkey;


--
-- Name: d20220515_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220515_package_id_snapshot_at_idx;


--
-- Name: d20220515_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220515_pkey;


--
-- Name: d20220522_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220522_package_id_snapshot_at_idx;


--
-- Name: d20220522_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220522_pkey;


--
-- Name: d20220529_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220529_package_id_snapshot_at_idx;


--
-- Name: d20220529_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220529_pkey;


--
-- Name: d20220605_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220605_package_id_snapshot_at_idx;


--
-- Name: d20220605_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220605_pkey;


--
-- Name: d20220613_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220613_package_id_snapshot_at_idx;


--
-- Name: d20220613_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220613_pkey;


--
-- Name: d20220620_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220620_package_id_snapshot_at_idx;


--
-- Name: d20220620_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220620_pkey;


--
-- Name: d20220627_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220627_package_id_snapshot_at_idx;


--
-- Name: d20220627_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220627_pkey;


--
-- Name: d20220704_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220704_package_id_snapshot_at_idx;


--
-- Name: d20220704_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220704_pkey;


--
-- Name: d20220712_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220712_package_id_snapshot_at_idx;


--
-- Name: d20220712_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220712_pkey;


--
-- Name: d20220718_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220718_package_id_snapshot_at_idx;


--
-- Name: d20220718_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220718_pkey;


--
-- Name: d20220726_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220726_package_id_snapshot_at_idx;


--
-- Name: d20220726_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220726_pkey;


--
-- Name: d20220801_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220801_package_id_snapshot_at_idx;


--
-- Name: d20220801_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220801_pkey;


--
-- Name: d20220808_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220808_package_id_snapshot_at_idx;


--
-- Name: d20220808_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220808_pkey;


--
-- Name: d20220815_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220815_package_id_snapshot_at_idx;


--
-- Name: d20220815_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220815_pkey;


--
-- Name: d20220822_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220822_package_id_snapshot_at_idx;


--
-- Name: d20220822_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220822_pkey;


--
-- Name: d20220829_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220829_package_id_snapshot_at_idx;


--
-- Name: d20220829_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220829_pkey;


--
-- Name: d20220905_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220905_package_id_snapshot_at_idx;


--
-- Name: d20220905_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220905_pkey;


--
-- Name: d20220913_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220913_package_id_snapshot_at_idx;


--
-- Name: d20220913_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220913_pkey;


--
-- Name: d20220919_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220919_package_id_snapshot_at_idx;


--
-- Name: d20220919_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220919_pkey;


--
-- Name: d20220926_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220926_package_id_snapshot_at_idx;


--
-- Name: d20220926_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20220926_pkey;


--
-- Name: d20221003_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221003_package_id_snapshot_at_idx;


--
-- Name: d20221003_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221003_pkey;


--
-- Name: d20221010_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221010_package_id_snapshot_at_idx;


--
-- Name: d20221010_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221010_pkey;


--
-- Name: d20221017_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221017_package_id_snapshot_at_idx;


--
-- Name: d20221017_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221017_pkey;


--
-- Name: d20221024_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221024_package_id_snapshot_at_idx;


--
-- Name: d20221024_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221024_pkey;


--
-- Name: d20221031_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221031_package_id_snapshot_at_idx;


--
-- Name: d20221031_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221031_pkey;


--
-- Name: d20221107_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221107_package_id_snapshot_at_idx;


--
-- Name: d20221107_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221107_pkey;


--
-- Name: d20221114_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221114_package_id_snapshot_at_idx;


--
-- Name: d20221114_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221114_pkey;


--
-- Name: d20221121_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221121_package_id_snapshot_at_idx;


--
-- Name: d20221121_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221121_pkey;


--
-- Name: d20221128_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221128_package_id_snapshot_at_idx;


--
-- Name: d20221128_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221128_pkey;


--
-- Name: d20221205_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221205_package_id_snapshot_at_idx;


--
-- Name: d20221205_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221205_pkey;


--
-- Name: d20221212_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221212_package_id_snapshot_at_idx;


--
-- Name: d20221212_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221212_pkey;


--
-- Name: d20221219_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221219_package_id_snapshot_at_idx;


--
-- Name: d20221219_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221219_pkey;


--
-- Name: d20221226_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221226_package_id_snapshot_at_idx;


--
-- Name: d20221226_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20221226_pkey;


--
-- Name: d20230102_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230102_package_id_snapshot_at_idx;


--
-- Name: d20230102_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230102_pkey;


--
-- Name: d20230109_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230109_package_id_snapshot_at_idx;


--
-- Name: d20230109_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230109_pkey;


--
-- Name: d20230116_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230116_package_id_snapshot_at_idx;


--
-- Name: d20230116_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230116_pkey;


--
-- Name: d20230123_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230123_package_id_snapshot_at_idx;


--
-- Name: d20230123_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230123_pkey;


--
-- Name: d20230129_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230129_package_id_snapshot_at_idx;


--
-- Name: d20230129_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230129_pkey;


--
-- Name: d20230206_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230206_package_id_snapshot_at_idx;


--
-- Name: d20230206_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230206_pkey;


--
-- Name: d20230213_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230213_package_id_snapshot_at_idx;


--
-- Name: d20230213_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230213_pkey;


--
-- Name: d20230220_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230220_package_id_snapshot_at_idx;


--
-- Name: d20230220_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230220_pkey;


--
-- Name: d20230227_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230227_package_id_snapshot_at_idx;


--
-- Name: d20230227_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230227_pkey;


--
-- Name: d20230306_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230306_package_id_snapshot_at_idx;


--
-- Name: d20230306_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230306_pkey;


--
-- Name: d20230313_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230313_package_id_snapshot_at_idx;


--
-- Name: d20230313_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230313_pkey;


--
-- Name: d20230321_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230321_package_id_snapshot_at_idx;


--
-- Name: d20230321_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230321_pkey;


--
-- Name: d20230327_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230327_package_id_snapshot_at_idx;


--
-- Name: d20230327_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230327_pkey;


--
-- Name: d20230403_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230403_package_id_snapshot_at_idx;


--
-- Name: d20230403_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230403_pkey;


--
-- Name: d20230410_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230410_package_id_snapshot_at_idx;


--
-- Name: d20230410_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230410_pkey;


--
-- Name: d20230417_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230417_package_id_snapshot_at_idx;


--
-- Name: d20230417_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230417_pkey;


--
-- Name: d20230420_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230420_package_id_snapshot_at_idx;


--
-- Name: d20230420_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230420_pkey;


--
-- Name: d20230501_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230501_package_id_snapshot_at_idx;


--
-- Name: d20230501_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230501_pkey;


--
-- Name: d20230502_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230502_package_id_snapshot_at_idx;


--
-- Name: d20230502_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230502_pkey;


--
-- Name: d20230508_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230508_package_id_snapshot_at_idx;


--
-- Name: d20230508_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230508_pkey;


--
-- Name: d20230515_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230515_package_id_snapshot_at_idx;


--
-- Name: d20230515_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230515_pkey;


--
-- Name: d20230522_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230522_package_id_snapshot_at_idx;


--
-- Name: d20230522_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230522_pkey;


--
-- Name: d20230529_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230529_package_id_snapshot_at_idx;


--
-- Name: d20230529_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230529_pkey;


--
-- Name: d20230605_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230605_package_id_snapshot_at_idx;


--
-- Name: d20230605_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230605_pkey;


--
-- Name: d20230612_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230612_package_id_snapshot_at_idx;


--
-- Name: d20230612_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230612_pkey;


--
-- Name: d20230620_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230620_package_id_snapshot_at_idx;


--
-- Name: d20230620_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230620_pkey;


--
-- Name: d20230626_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230626_package_id_snapshot_at_idx;


--
-- Name: d20230626_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230626_pkey;


--
-- Name: d20230703_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230703_package_id_snapshot_at_idx;


--
-- Name: d20230703_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230703_pkey;


--
-- Name: d20230710_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230710_package_id_snapshot_at_idx;


--
-- Name: d20230710_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230710_pkey;


--
-- Name: d20230717_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230717_package_id_snapshot_at_idx;


--
-- Name: d20230717_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230717_pkey;


--
-- Name: d20230724_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230724_package_id_snapshot_at_idx;


--
-- Name: d20230724_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230724_pkey;


--
-- Name: d20230731_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230731_package_id_snapshot_at_idx;


--
-- Name: d20230731_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230731_pkey;


--
-- Name: d20230807_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230807_package_id_snapshot_at_idx;


--
-- Name: d20230807_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230807_pkey;


--
-- Name: d20230814_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230814_package_id_snapshot_at_idx;


--
-- Name: d20230814_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230814_pkey;


--
-- Name: d20230821_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230821_package_id_snapshot_at_idx;


--
-- Name: d20230821_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230821_pkey;


--
-- Name: d20230828_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230828_package_id_snapshot_at_idx;


--
-- Name: d20230828_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230828_pkey;


--
-- Name: d20230904_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230904_package_id_snapshot_at_idx;


--
-- Name: d20230904_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230904_pkey;


--
-- Name: d20230911_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230911_package_id_snapshot_at_idx;


--
-- Name: d20230911_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230911_pkey;


--
-- Name: d20230918_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230918_package_id_snapshot_at_idx;


--
-- Name: d20230918_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230918_pkey;


--
-- Name: d20230926_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230926_package_id_snapshot_at_idx;


--
-- Name: d20230926_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20230926_pkey;


--
-- Name: d20231002_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231002_package_id_snapshot_at_idx;


--
-- Name: d20231002_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231002_pkey;


--
-- Name: d20231009_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231009_package_id_snapshot_at_idx;


--
-- Name: d20231009_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231009_pkey;


--
-- Name: d20231016_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231016_package_id_snapshot_at_idx;


--
-- Name: d20231016_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231016_pkey;


--
-- Name: d20231023_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231023_package_id_snapshot_at_idx;


--
-- Name: d20231023_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231023_pkey;


--
-- Name: d20231030_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231030_package_id_snapshot_at_idx;


--
-- Name: d20231030_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231030_pkey;


--
-- Name: d20231106_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231106_package_id_snapshot_at_idx;


--
-- Name: d20231106_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231106_pkey;


--
-- Name: d20231113_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231113_package_id_snapshot_at_idx;


--
-- Name: d20231113_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231113_pkey;


--
-- Name: d20231120_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231120_package_id_snapshot_at_idx;


--
-- Name: d20231120_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231120_pkey;


--
-- Name: d20231127_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231127_package_id_snapshot_at_idx;


--
-- Name: d20231127_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231127_pkey;


--
-- Name: d20231204_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231204_package_id_snapshot_at_idx;


--
-- Name: d20231204_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231204_pkey;


--
-- Name: d20231211_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231211_package_id_snapshot_at_idx;


--
-- Name: d20231211_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231211_pkey;


--
-- Name: d20231218_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231218_package_id_snapshot_at_idx;


--
-- Name: d20231218_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231218_pkey;


--
-- Name: d20231225_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231225_package_id_snapshot_at_idx;


--
-- Name: d20231225_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20231225_pkey;


--
-- Name: d20240101_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240101_package_id_snapshot_at_idx;


--
-- Name: d20240101_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240101_pkey;


--
-- Name: d20240108_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240108_package_id_snapshot_at_idx;


--
-- Name: d20240108_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240108_pkey;


--
-- Name: d20240115_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240115_package_id_snapshot_at_idx;


--
-- Name: d20240115_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240115_pkey;


--
-- Name: d20240122_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240122_package_id_snapshot_at_idx;


--
-- Name: d20240122_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240122_pkey;


--
-- Name: d20240129_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240129_package_id_snapshot_at_idx;


--
-- Name: d20240129_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240129_pkey;


--
-- Name: d20240205_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240205_package_id_snapshot_at_idx;


--
-- Name: d20240205_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240205_pkey;


--
-- Name: d20240212_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240212_package_id_snapshot_at_idx;


--
-- Name: d20240212_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240212_pkey;


--
-- Name: d20240219_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240219_package_id_snapshot_at_idx;


--
-- Name: d20240219_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240219_pkey;


--
-- Name: d20240226_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240226_package_id_snapshot_at_idx;


--
-- Name: d20240226_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240226_pkey;


--
-- Name: d20240304_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240304_package_id_snapshot_at_idx;


--
-- Name: d20240304_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240304_pkey;


--
-- Name: d20240305_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240305_package_id_snapshot_at_idx;


--
-- Name: d20240305_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240305_pkey;


--
-- Name: d20240311_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240311_package_id_snapshot_at_idx;


--
-- Name: d20240311_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240311_pkey;


--
-- Name: d20240318_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240318_package_id_snapshot_at_idx;


--
-- Name: d20240318_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240318_pkey;


--
-- Name: d20240325_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240325_package_id_snapshot_at_idx;


--
-- Name: d20240325_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240325_pkey;


--
-- Name: d20240401_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240401_package_id_snapshot_at_idx;


--
-- Name: d20240401_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240401_pkey;


--
-- Name: d20240409_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240409_package_id_snapshot_at_idx;


--
-- Name: d20240409_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240409_pkey;


--
-- Name: d20240415_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240415_package_id_snapshot_at_idx;


--
-- Name: d20240415_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240415_pkey;


--
-- Name: d20240421_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240421_package_id_snapshot_at_idx;


--
-- Name: d20240421_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240421_pkey;


--
-- Name: d20240429_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240429_package_id_snapshot_at_idx;


--
-- Name: d20240429_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240429_pkey;


--
-- Name: d20240509_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240509_package_id_snapshot_at_idx;


--
-- Name: d20240509_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240509_pkey;


--
-- Name: d20240513_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240513_package_id_snapshot_at_idx;


--
-- Name: d20240513_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240513_pkey;


--
-- Name: d20240520_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240520_package_id_snapshot_at_idx;


--
-- Name: d20240520_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240520_pkey;


--
-- Name: d20240527_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240527_package_id_snapshot_at_idx;


--
-- Name: d20240527_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240527_pkey;


--
-- Name: d20240603_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240603_package_id_snapshot_at_idx;


--
-- Name: d20240603_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240603_pkey;


--
-- Name: d20240610_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240610_package_id_snapshot_at_idx;


--
-- Name: d20240610_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240610_pkey;


--
-- Name: d20240617_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240617_package_id_snapshot_at_idx;


--
-- Name: d20240617_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240617_pkey;


--
-- Name: d20240624_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240624_package_id_snapshot_at_idx;


--
-- Name: d20240624_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240624_pkey;


--
-- Name: d20240701_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240701_package_id_snapshot_at_idx;


--
-- Name: d20240701_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240701_pkey;


--
-- Name: d20240708_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240708_package_id_snapshot_at_idx;


--
-- Name: d20240708_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240708_pkey;


--
-- Name: d20240709_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240709_package_id_snapshot_at_idx;


--
-- Name: d20240709_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240709_pkey;


--
-- Name: d20240715_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240715_package_id_snapshot_at_idx;


--
-- Name: d20240715_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240715_pkey;


--
-- Name: d20240723_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240723_package_id_snapshot_at_idx;


--
-- Name: d20240723_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240723_pkey;


--
-- Name: d20240729_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240729_package_id_snapshot_at_idx;


--
-- Name: d20240729_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240729_pkey;


--
-- Name: d20240805_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240805_package_id_snapshot_at_idx;


--
-- Name: d20240805_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240805_pkey;


--
-- Name: d20240812_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240812_package_id_snapshot_at_idx;


--
-- Name: d20240812_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240812_pkey;


--
-- Name: d20240819_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240819_package_id_snapshot_at_idx;


--
-- Name: d20240819_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240819_pkey;


--
-- Name: d20240829_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240829_package_id_snapshot_at_idx;


--
-- Name: d20240829_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240829_pkey;


--
-- Name: d20240902_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240902_package_id_snapshot_at_idx;


--
-- Name: d20240902_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240902_pkey;


--
-- Name: d20240909_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240909_package_id_snapshot_at_idx;


--
-- Name: d20240909_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240909_pkey;


--
-- Name: d20240916_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240916_package_id_snapshot_at_idx;


--
-- Name: d20240916_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240916_pkey;


--
-- Name: d20240923_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240923_package_id_snapshot_at_idx;


--
-- Name: d20240923_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240923_pkey;


--
-- Name: d20240930_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240930_package_id_snapshot_at_idx;


--
-- Name: d20240930_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20240930_pkey;


--
-- Name: d20241007_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241007_package_id_snapshot_at_idx;


--
-- Name: d20241007_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241007_pkey;


--
-- Name: d20241014_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241014_package_id_snapshot_at_idx;


--
-- Name: d20241014_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241014_pkey;


--
-- Name: d20241021_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241021_package_id_snapshot_at_idx;


--
-- Name: d20241021_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241021_pkey;


--
-- Name: d20241028_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241028_package_id_snapshot_at_idx;


--
-- Name: d20241028_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241028_pkey;


--
-- Name: d20241104_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241104_package_id_snapshot_at_idx;


--
-- Name: d20241104_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241104_pkey;


--
-- Name: d20241111_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241111_package_id_snapshot_at_idx;


--
-- Name: d20241111_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241111_pkey;


--
-- Name: d20241119_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241119_package_id_snapshot_at_idx;


--
-- Name: d20241119_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241119_pkey;


--
-- Name: d20241125_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241125_package_id_snapshot_at_idx;


--
-- Name: d20241125_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241125_pkey;


--
-- Name: d20241202_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241202_package_id_snapshot_at_idx;


--
-- Name: d20241202_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241202_pkey;


--
-- Name: d20241209_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241209_package_id_snapshot_at_idx;


--
-- Name: d20241209_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241209_pkey;


--
-- Name: d20241216_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241216_package_id_snapshot_at_idx;


--
-- Name: d20241216_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241216_pkey;


--
-- Name: d20241223_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241223_package_id_snapshot_at_idx;


--
-- Name: d20241223_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241223_pkey;


--
-- Name: d20241230_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241230_package_id_snapshot_at_idx;


--
-- Name: d20241230_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20241230_pkey;


--
-- Name: d20250106_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250106_package_id_snapshot_at_idx;


--
-- Name: d20250106_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250106_pkey;


--
-- Name: d20250113_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250113_package_id_snapshot_at_idx;


--
-- Name: d20250113_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250113_pkey;


--
-- Name: d20250120_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250120_package_id_snapshot_at_idx;


--
-- Name: d20250120_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250120_pkey;


--
-- Name: d20250127_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250127_package_id_snapshot_at_idx;


--
-- Name: d20250127_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250127_pkey;


--
-- Name: d20250203_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250203_package_id_snapshot_at_idx;


--
-- Name: d20250203_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250203_pkey;


--
-- Name: d20250210_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250210_package_id_snapshot_at_idx;


--
-- Name: d20250210_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250210_pkey;


--
-- Name: d20250218_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250218_package_id_snapshot_at_idx;


--
-- Name: d20250218_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250218_pkey;


--
-- Name: d20250225_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250225_package_id_snapshot_at_idx;


--
-- Name: d20250225_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250225_pkey;


--
-- Name: d20250303_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250303_package_id_snapshot_at_idx;


--
-- Name: d20250303_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250303_pkey;


--
-- Name: d20250310_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250310_package_id_snapshot_at_idx;


--
-- Name: d20250310_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250310_pkey;


--
-- Name: d20250318_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250318_package_id_snapshot_at_idx;


--
-- Name: d20250318_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250318_pkey;


--
-- Name: d20250324_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250324_package_id_snapshot_at_idx;


--
-- Name: d20250324_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250324_pkey;


--
-- Name: d20250331_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250331_package_id_snapshot_at_idx;


--
-- Name: d20250331_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250331_pkey;


--
-- Name: d20250407_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250407_package_id_snapshot_at_idx;


--
-- Name: d20250407_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250407_pkey;


--
-- Name: d20250414_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250414_package_id_snapshot_at_idx;


--
-- Name: d20250414_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250414_pkey;


--
-- Name: d20250422_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250422_package_id_snapshot_at_idx;


--
-- Name: d20250422_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250422_pkey;


--
-- Name: d20250428_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250428_package_id_snapshot_at_idx;


--
-- Name: d20250428_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250428_pkey;


--
-- Name: d20250505_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250505_package_id_snapshot_at_idx;


--
-- Name: d20250505_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250505_pkey;


--
-- Name: d20250512_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250512_package_id_snapshot_at_idx;


--
-- Name: d20250512_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250512_pkey;


--
-- Name: d20250519_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250519_package_id_snapshot_at_idx;


--
-- Name: d20250519_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250519_pkey;


--
-- Name: d20250526_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250526_package_id_snapshot_at_idx;


--
-- Name: d20250526_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250526_pkey;


--
-- Name: d20250602_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250602_package_id_snapshot_at_idx;


--
-- Name: d20250602_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250602_pkey;


--
-- Name: d20250609_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250609_package_id_snapshot_at_idx;


--
-- Name: d20250609_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250609_pkey;


--
-- Name: d20250616_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250616_package_id_snapshot_at_idx;


--
-- Name: d20250616_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250616_pkey;


--
-- Name: d20250623_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250623_package_id_snapshot_at_idx;


--
-- Name: d20250623_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250623_pkey;


--
-- Name: d20250630_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250630_package_id_snapshot_at_idx;


--
-- Name: d20250630_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250630_pkey;


--
-- Name: d20250707_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250707_package_id_snapshot_at_idx;


--
-- Name: d20250707_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250707_pkey;


--
-- Name: d20250714_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250714_package_id_snapshot_at_idx;


--
-- Name: d20250714_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250714_pkey;


--
-- Name: d20250721_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250721_package_id_snapshot_at_idx;


--
-- Name: d20250721_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250721_pkey;


--
-- Name: d20250728_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250728_package_id_snapshot_at_idx;


--
-- Name: d20250728_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250728_pkey;


--
-- Name: d20250804_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250804_package_id_snapshot_at_idx;


--
-- Name: d20250804_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250804_pkey;


--
-- Name: d20250811_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250811_package_id_snapshot_at_idx;


--
-- Name: d20250811_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250811_pkey;


--
-- Name: d20250818_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250818_package_id_snapshot_at_idx;


--
-- Name: d20250818_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250818_pkey;


--
-- Name: d20250825_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250825_package_id_snapshot_at_idx;


--
-- Name: d20250825_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250825_pkey;


--
-- Name: d20250901_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250901_package_id_snapshot_at_idx;


--
-- Name: d20250901_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250901_pkey;


--
-- Name: d20250908_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250908_package_id_snapshot_at_idx;


--
-- Name: d20250908_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250908_pkey;


--
-- Name: d20250915_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250915_package_id_snapshot_at_idx;


--
-- Name: d20250915_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250915_pkey;


--
-- Name: d20250922_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250922_package_id_snapshot_at_idx;


--
-- Name: d20250922_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250922_pkey;


--
-- Name: d20250929_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250929_package_id_snapshot_at_idx;


--
-- Name: d20250929_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20250929_pkey;


--
-- Name: d20251006_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251006_package_id_snapshot_at_idx;


--
-- Name: d20251006_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251006_pkey;


--
-- Name: d20251013_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251013_package_id_snapshot_at_idx;


--
-- Name: d20251013_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251013_pkey;


--
-- Name: d20251020_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251020_package_id_snapshot_at_idx;


--
-- Name: d20251020_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251020_pkey;


--
-- Name: d20251027_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251027_package_id_snapshot_at_idx;


--
-- Name: d20251027_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251027_pkey;


--
-- Name: d20251103_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251103_package_id_snapshot_at_idx;


--
-- Name: d20251103_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251103_pkey;


--
-- Name: d20251110_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251110_package_id_snapshot_at_idx;


--
-- Name: d20251110_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251110_pkey;


--
-- Name: d20251117_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251117_package_id_snapshot_at_idx;


--
-- Name: d20251117_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251117_pkey;


--
-- Name: d20251124_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251124_package_id_snapshot_at_idx;


--
-- Name: d20251124_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251124_pkey;


--
-- Name: d20251201_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251201_package_id_snapshot_at_idx;


--
-- Name: d20251201_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251201_pkey;


--
-- Name: d20251208_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251208_package_id_snapshot_at_idx;


--
-- Name: d20251208_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251208_pkey;


--
-- Name: d20251215_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251215_package_id_snapshot_at_idx;


--
-- Name: d20251215_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251215_pkey;


--
-- Name: d20251222_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251222_package_id_snapshot_at_idx;


--
-- Name: d20251222_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251222_pkey;


--
-- Name: d20251229_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251229_package_id_snapshot_at_idx;


--
-- Name: d20251229_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20251229_pkey;


--
-- Name: d20260105_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260105_package_id_snapshot_at_idx;


--
-- Name: d20260105_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260105_pkey;


--
-- Name: d20260112_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260112_package_id_snapshot_at_idx;


--
-- Name: d20260112_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260112_pkey;


--
-- Name: d20260119_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260119_package_id_snapshot_at_idx;


--
-- Name: d20260119_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260119_pkey;


--
-- Name: d20260126_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260126_package_id_snapshot_at_idx;


--
-- Name: d20260126_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260126_pkey;


--
-- Name: d20260213_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260213_package_id_snapshot_at_idx;


--
-- Name: d20260213_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260213_pkey;


--
-- Name: d20260216_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260216_package_id_snapshot_at_idx;


--
-- Name: d20260216_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260216_pkey;


--
-- Name: d20260223_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260223_package_id_snapshot_at_idx;


--
-- Name: d20260223_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260223_pkey;


--
-- Name: d20260302_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260302_package_id_snapshot_at_idx;


--
-- Name: d20260302_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260302_pkey;


--
-- Name: d20260309_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260309_package_id_snapshot_at_idx;


--
-- Name: d20260309_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260309_pkey;


--
-- Name: d20260310_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260310_package_id_snapshot_at_idx;


--
-- Name: d20260310_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260310_pkey;


--
-- Name: d20260316_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260316_package_id_snapshot_at_idx;


--
-- Name: d20260316_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260316_pkey;


--
-- Name: d20260323_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260323_package_id_snapshot_at_idx;


--
-- Name: d20260323_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260323_pkey;


--
-- Name: d20260330_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260330_package_id_snapshot_at_idx;


--
-- Name: d20260330_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260330_pkey;


--
-- Name: d20260406_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260406_package_id_snapshot_at_idx;


--
-- Name: d20260406_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260406_pkey;


--
-- Name: d20260413_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260413_package_id_snapshot_at_idx;


--
-- Name: d20260413_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260413_pkey;


--
-- Name: d20260414_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260414_package_id_snapshot_at_idx;


--
-- Name: d20260414_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260414_pkey;


--
-- Name: d20260420_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260420_package_id_snapshot_at_idx;


--
-- Name: d20260420_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260420_pkey;


--
-- Name: d20260428_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260428_package_id_snapshot_at_idx;


--
-- Name: d20260428_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260428_pkey;


--
-- Name: d20260505_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260505_package_id_snapshot_at_idx;


--
-- Name: d20260505_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260505_pkey;


--
-- Name: d20260511_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260511_package_id_snapshot_at_idx;


--
-- Name: d20260511_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260511_pkey;


--
-- Name: d20260518_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260518_package_id_snapshot_at_idx;


--
-- Name: d20260518_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260518_pkey;


--
-- Name: d20260601_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260601_package_id_snapshot_at_idx;


--
-- Name: d20260601_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260601_pkey;


--
-- Name: d20260611_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260611_package_id_snapshot_at_idx;


--
-- Name: d20260611_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260611_pkey;


--
-- Name: d20260615_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260615_package_id_snapshot_at_idx;


--
-- Name: d20260615_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260615_pkey;


--
-- Name: d20260623_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260623_package_id_snapshot_at_idx;


--
-- Name: d20260623_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260623_pkey;


--
-- Name: d20260629_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260629_package_id_snapshot_at_idx;


--
-- Name: d20260629_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260629_pkey;


--
-- Name: d20260706_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260706_package_id_snapshot_at_idx;


--
-- Name: d20260706_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260706_pkey;


--
-- Name: d20260713_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260713_package_id_snapshot_at_idx;


--
-- Name: d20260713_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260713_pkey;


--
-- Name: d20260720_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260720_package_id_snapshot_at_idx;


--
-- Name: d20260720_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260720_pkey;


--
-- Name: d20260727_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260727_package_id_snapshot_at_idx;


--
-- Name: d20260727_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260727_pkey;


--
-- Name: d20260803_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260803_package_id_snapshot_at_idx;


--
-- Name: d20260803_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260803_pkey;


--
-- Name: d20260810_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260810_package_id_snapshot_at_idx;


--
-- Name: d20260810_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260810_pkey;


--
-- Name: d20260817_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260817_package_id_snapshot_at_idx;


--
-- Name: d20260817_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260817_pkey;


--
-- Name: d20260824_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260824_package_id_snapshot_at_idx;


--
-- Name: d20260824_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260824_pkey;


--
-- Name: d20260831_package_id_snapshot_at_idx; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.idx_pvs_pkg_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260831_package_id_snapshot_at_idx;


--
-- Name: d20260831_pkey; Type: INDEX ATTACH; Schema: vd193_reload_20260912_ready01; Owner: pickage
--

ALTER INDEX public.pk_package_version_snapshot ATTACH PARTITION vd193_reload_20260912_ready01.d20260831_pkey;


--
-- Name: community_snapshot FK_PACKAGE_COMMUNITY_SNAPSHOT; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.community_snapshot
    ADD CONSTRAINT "FK_PACKAGE_COMMUNITY_SNAPSHOT" FOREIGN KEY (package_id) REFERENCES public.package(package_id) ON DELETE CASCADE;


--
-- Name: dependent_removal_reason FK_PACKAGE_DEPENDENT_REMOVAL_REASON; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.dependent_removal_reason
    ADD CONSTRAINT "FK_PACKAGE_DEPENDENT_REMOVAL_REASON" FOREIGN KEY (package_id) REFERENCES public.package(package_id);


--
-- Name: dependent_transition FK_PACKAGE_DEPENDENT_TRANSITION; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.dependent_transition
    ADD CONSTRAINT "FK_PACKAGE_DEPENDENT_TRANSITION" FOREIGN KEY (package_id) REFERENCES public.package(package_id);


--
-- Name: migration_pair FK_PACKAGE_MIGRATION_PAIR; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.migration_pair
    ADD CONSTRAINT "FK_PACKAGE_MIGRATION_PAIR" FOREIGN KEY (from_package_id) REFERENCES public.package(package_id);


--
-- Name: package_snapshot FK_PACKAGE_PACKAGE_SNAPSHOT; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package_snapshot
    ADD CONSTRAINT "FK_PACKAGE_PACKAGE_SNAPSHOT" FOREIGN KEY (package_id) REFERENCES public.package(package_id);


--
-- Name: similar_package FK_PACKAGE_SIMILAR_PACKAGE; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.similar_package
    ADD CONSTRAINT "FK_PACKAGE_SIMILAR_PACKAGE" FOREIGN KEY (package_id) REFERENCES public.package(package_id);


--
-- Name: similar_package FK_PACKAGE_SIMILAR_PACKAGE_CANDIDATE; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.similar_package
    ADD CONSTRAINT "FK_PACKAGE_SIMILAR_PACKAGE_CANDIDATE" FOREIGN KEY (similar_package_id) REFERENCES public.package(package_id);


--
-- Name: version FK_PACKAGE_VERSION; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.version
    ADD CONSTRAINT "FK_PACKAGE_VERSION" FOREIGN KEY (package_id) REFERENCES public.package(package_id);


--
-- Name: package_snapshot FK_SNAPSHOT_PACKAGE_SNAPSHOT; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package_snapshot
    ADD CONSTRAINT "FK_SNAPSHOT_PACKAGE_SNAPSHOT" FOREIGN KEY (snapshot_at) REFERENCES public.snapshot(snapshot_at);


--
-- Name: package_env FK_VERSION_PACKAGE_ENV; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.package_env
    ADD CONSTRAINT "FK_VERSION_PACKAGE_ENV" FOREIGN KEY (package_id, version) REFERENCES public.version(package_id, version);


--
-- Name: etl_dataset_current etl_dataset_current_dataset_execution_id_snapshot_at_manif_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_dataset_current
    ADD CONSTRAINT etl_dataset_current_dataset_execution_id_snapshot_at_manif_fkey FOREIGN KEY (dataset, execution_id, snapshot_at, manifest_sha256) REFERENCES public.etl_load_execution(dataset, execution_id, snapshot_at, manifest_sha256);


--
-- Name: etl_load_attempt etl_load_attempt_execution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_load_attempt
    ADD CONSTRAINT etl_load_attempt_execution_id_fkey FOREIGN KEY (execution_id) REFERENCES public.etl_load_execution(execution_id);


--
-- Name: etl_snapshot_reference etl_snapshot_reference_dataset_execution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_snapshot_reference
    ADD CONSTRAINT etl_snapshot_reference_dataset_execution_id_fkey FOREIGN KEY (dataset, execution_id) REFERENCES public.etl_load_execution(dataset, execution_id);


--
-- Name: etl_snapshot_reference etl_snapshot_reference_execution_id_previous_snapshot_at_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_snapshot_reference
    ADD CONSTRAINT etl_snapshot_reference_execution_id_previous_snapshot_at_fkey FOREIGN KEY (execution_id, previous_snapshot_at) REFERENCES public.etl_snapshot_reference(execution_id, snapshot_at);


--
-- Name: etl_snapshot_reference etl_snapshot_reference_snapshot_at_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_snapshot_reference
    ADD CONSTRAINT etl_snapshot_reference_snapshot_at_fkey FOREIGN KEY (snapshot_at) REFERENCES public.snapshot(snapshot_at);


--
-- Name: available_package fk_available_package_package; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.available_package
    ADD CONSTRAINT fk_available_package_package FOREIGN KEY (package_id) REFERENCES public.package(package_id) ON DELETE CASCADE;


--
-- Name: etl_load_execution fk_etl_active_attempt; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE ONLY public.etl_load_execution
    ADD CONSTRAINT fk_etl_active_attempt FOREIGN KEY (execution_id, active_attempt_id) REFERENCES public.etl_load_attempt(execution_id, attempt_id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: package_version_snapshot fk_snapshot_package_version_snapshot; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE public.package_version_snapshot
    ADD CONSTRAINT fk_snapshot_package_version_snapshot FOREIGN KEY (snapshot_at) REFERENCES public.snapshot(snapshot_at);


--
-- Name: package_version_snapshot fk_version_package_version_snapshot; Type: FK CONSTRAINT; Schema: public; Owner: pickage
--

ALTER TABLE public.package_version_snapshot
    ADD CONSTRAINT fk_version_package_version_snapshot FOREIGN KEY (package_id, version) REFERENCES public.version(package_id, version);


--
-- PostgreSQL database dump complete
--

\unrestrict Wpdd8x5lOSa3GgJBQCcYdbaIL6pXNmC9OtTT1TK3aOawUivWV4BCWvUkzWktcVn

