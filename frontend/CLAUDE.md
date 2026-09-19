# Pickage 프론트엔드 — 작업 기준

**모든 화면 작업 전에 `../docs/Pickage_메뉴구조_IA_0917.md`를 먼저 읽는다.** 데이터·상태·판정 계약은
`../docs/Pickage_기능별_개발_구상안_0917.md`가 기준이다. 두 문서가 코드보다 우선한다.
0915→0917 사이 결정 이력·현재 적용할 계약 요약은 `../docs/Pickage_0915_to_0917_기획변경_상세분석.md`(GitHub 커뮤니티·GMS 요약 구현 완료, 유사후보 데이터 기반 마련, 주간 배치 자동화, Dependents·Downloads 그래프 지수·증감·로그축 압축, Version Share 패키지 탭 범위 정정).

Figma: `fuTQIgzDn8cr6BTwdOlDrx` → 프레임 `Pickage_v2_web-service`(`485:241`)
(구 프레임 `Pickage_v1_web-service`(`220:193`)는 `무덤` Section의 폐기 보관본 — 참고하지 않는다)

## 절대 규칙

문서에서 금지한 것을 화면에 넣지 않는다. 아래는 실수하기 쉬운 항목만 추린 것이고,
전체 목록은 IA 1장·2장과 구상안 1.3·7.2에 있다.

- **금지 용어**: `확인 불가`, `대시보드`, `최고의 대안`, `추천 1위`, `승자` (IA §2)
- **추천·순위·승자 표현 금지.** 어느 쪽이 낫다는 판정을 하지 않는다 (IA §1-12)
- **외부 링크 금지 — 확장 화면(기능 비교·Evidence Drawer·GitHub 커뮤니티) 한정.** 저장소·출처 식별자는 표시 문자열로만, 클릭 가능한 URL 필드 없음 (IA §1-14)
- **색상만으로 의미 전달 금지.** 판정·오류·선택 상태에는 문구나 아이콘을 함께, 키보드 포커스도 제공한다 (IA §1-13)
- **비교 대상은 기준 패키지 포함 최대 3개.** 기준 패키지는 항상 고정 선택(해제 불가)하고, 기준을 제외한 관련 후보 카드 최대 3개는 **전부 미선택 상태**로 노출한다 — 상위 후보 기본 선택은 폐지됨(`DEC-RANK-UI-20260910-01`) (IA §1-2·3, §6.1-4, §6.2, §6.3)
- **버전은 입력 화면에 없다.** 화면-01에 버전 입력·드롭다운·최신 버전 선택을 두지 않는다 (IA §5.2)
- **사용자 선택을 자동 해제하지 않는다.** 4번째 추가는 `MAX_SELECTION_REACHED` (IA §6.3, 구상안 §4.4)

## 판정값 (구상안 7.2)

`verdict`와 `dataStatus`는 다른 축이다. 섞지 않는다.

```
verdict:      SUPPORTED · CONDITIONALLY_SUPPORTED · LIMITED_SUPPORT · UNCONFIRMED · UNSUPPORTED
dataStatus:   COMPLETE · PARTIAL · NO_DATA · COLLECTION_ERROR · CONFLICT · STALE
```

화면 표기: 지원 · 조건부 · 제한적 · 미지원 · 미확인 (구상안 §7.1 표)

- **`UNSUPPORTED`는 공식 부정 근거가 연결됐을 때만.** 자료가 없으면 `UNCONFIRMED`다.
- **미확인은 미지원이 아니다.** 실패색을 쓰지 않고, 무엇을 어디까지 확인했는지 함께 보여준다.
- 비교 가능한 기능이 부족하면 억지 표를 만들지 않고 `COMPARISON_LIMITED` (구상안 8)

## 버전 세 갈래 (구상안 §1.2)

1. 후보 단계 — 버전 없음(카드엔 최신 버전을 참고 metadata로만 표시)
2. Dependency major 선택 — `Total` 또는 선택한 하나 이상의 major 합계, 패키지별 독립
3. Version Share — 버전 선택 상태가 아니라 최신 DB Snapshot 기준일과 major별 분포

**기능 비교 버전은 이 세 갈래와 별개의 축이다.** 확장 기능 내부 상태이며 생태계 화면 상태와
분리한다(구상안 §1.2 끝문장). 2번(Dependency major)을 바꿔도 기능 분석 결과·캐시·판정은
무효화되지 않는다. 전역 분석 버전을 상단에 두지 않고 각 카드 안에 둔다 (IA §7.1).

## 화면 계층

```
서비스 소개(00) → 패키지 입력(01) → 후보 선택(02) → 보고서(03)
                                                    ├ 1. 생태계 변화  Dependency · Activity · Version Share
                                                    ├ 2. 기능 비교    + Evidence Drawer
                                                    ├ 3. GitHub 커뮤니티 [확장]
                                                    └ PDF 내보내기
```

상단 메뉴는 `서비스 소개` / `패키지 분석` 둘뿐. 보고서는 최상위 메뉴가 아니다.

## 기술 스택

| | |
|---|---|
| 빌드 | Vite 8 |
| 라우팅 | React Router **v7** (`createBrowserRouter`) |
| 스타일 | Tailwind **v4** (`@tailwindcss/vite`) |
| UI | shadcn/ui, base color `slate` |
| 서버 상태 | TanStack Query v5, HTTP는 `fetch` (인증이 없어 axios 미채택) |
| 클라 전역 상태 | 없음 — 로컬 state만 |

- **보더 토큰 단일**: `--border` / `--input` = `#dbdee5`. 다른 보더 색 추가 금지.
- **`components/ui/`는 shadcn 원본.** 수정하지 않는다. 변형이 필요하면 `components/common/`에 감싼다.
- **차트는 직접 만든 SVG다**(`components/charts/`). 기하 계산은 `geometry.ts` 가 React·DOM 없이 갖는다 — 렌더러를 바꿔도 이 파일은 그대로 쓴다.
- **새 화면은 `app/router.tsx`에 `lazy`로 추가.** eager import 하나가 초기 청크를 부풀린다.

## 현재 스코프

포함: 00 · 01 · 02 · 03A(생태계) · 03B(기능 비교) · 확장-03(GitHub 커뮤니티)
- PDF(04): 미리보기·다운로드 UI는 구현됨(`S15P21A506-141`). 생성 상태·차단 사유(READY/BLOCKED)
  로직은 미완 — 구상안 §13.2 적격성 계약대로 `S15P21A506-220`에서 마무리한다.
- GitHub 커뮤니티(확장-03): 구현 완료(`S15P21A506-316`, 2026-09-17 확인). `routes/report/community`가
  `report-page.tsx`의 세 번째 lazy tab(`community`)으로 연결돼 있다. 구현계획은
  `../docs/for_community/Pickage_GitHub커뮤니티_구현계획_260908.md`(`S15P21A506-323`).

## 예시 데이터

지어내지 않는다. 구상안 16장의 POC 실측(winston 3.19.0 / pino 10.3.1 / bunyan 1.8.15)과
구상안 본문의 예시 JSON을 쓴다. 불가피하게 만든 값은 화면에 "예시"라고 표시한다.

## 미해결

- 리포트 id 발급 주체 — 현재 서버 발급 가정, 02에서 임시로 `/report/draft` 진입. 비교 대상 자체는
  주소(`?names=`)에 싣는다(`S15P21A506-187`) — id 미발급과는 별개 문제

## 결정 이력

- `DEC-HERO-INPUT-20260919-01`(`S15P21A506-401`): 인트로 히어로의 패키지 입력 필드는 유지한다.
  화면-01(§5.2)과 같은 `PackageSearch` 컴포넌트를 재사용해 접두사 자동완성을 붙였다 — IA
  §4.2도 이 결정에 맞춰 갱신했다. 서버 검증(`/packages/similar`)은 여전히 다음 화면(analyze-page
  1단계)에서 하고, 히어로에서는 형식만 확인한 뒤 prefill로 넘긴다.
- `DEC-WEEKLY-GRID-20260920-01`(`S15P21A506-403`): 기준일 달력(deps.dev 실제 스냅샷 날짜)이 2026-02 이후 월요일 주간이 아니라서
  그래프가 끊기고 Downloads 가 급락했다. **서버가 월요일 격자로 환산해 내려준다** — Downloads 는 구간 합계를 일평균으로
  펼친 주간 합계, Dependents 는 관측 범위 안의 빈 주를 선형 보간. 화면은 이 응답을 그대로 그린다(선 끊김 규칙 `MAX_GAP_DAYS` 는
  Downloads 의 관측 구멍용으로 유지). Dependents 카드는 변화율(지수)로 열고 실제값으로 전환한다(`MetricChart` `defaultScale`).
  세부 규칙은 `../docs/설계_지표별_관측기간_기준일_표시계약_260918.md` §2.
- `DEC-INTRO-HERO-20260920-01`(`S15P21A506-404`): 인트로 히어로는 뷰포트 전폭으로 펴고(`left-1/2 w-screen -translate-x-1/2`,
  가로 넘침은 `AppLayout` 의 `overflow-x-clip` 이 자른다), **`overflow-hidden` 은 배경 도형(`HeroBackdrop`)에만 둔다** — 히어로에
  걸면 자동완성 목록이 잘린다. 히어로 `z-10` 은 `transform` 쌓임 맥락 때문에 필요하다. 문구는 제품 책임자가 정했다: 제목
  `패키지 선택에, 확인할 근거를`, 설명 `유사한 기능을 가진 패키지를 제안하고, …` / `PDF로 다운로드 받아 …`("추천" 이 아니라 "제안" — 서비스는 우열을 권하지 않는다).
  예시로 둘러보기는 `express`·`yaml`·`axios`. 소개 화면 문구는 `Clauses` 로 **절 단위**로 끊어 줄이 마침표·쉼표 뒤에서만 바뀐다.
  2단계 예시의 후보 칩은 카드 폭(container query)에 따라 3등분/2등분해 오른쪽이 비지 않게 한다. 3단계 예시에는 보고서 1페이지의
  Dependents 증감을 넣었다 — 값은 아래 예시 보고서와 같은 계산(`deltaOf`)이다.
- `DEC-REPORT1-LAYOUT-20260920-01`(`S15P21A506-405`): 보고서 1페이지의 조회 기간은 프리셋(`전체 기간·반년·1년·2년·3년`, 기본 전체 기간)
  + 세부 기간이다. 프리셋은 `resolvePreset` 이 **실제 집계 날짜**로 풀어 세부 기간에 채우고, 날짜를 직접 고르면 풀린다. 좌우 열 높이는
  언제나 같다 — 오른쪽이 길면 그래프 카드 둘이 높이를 똑같이 나눠 갖고(`MetricChart` `fill` + `ChartArea`가 늘어난 높이를 재서
  그래프에 넘긴다), 왼쪽이 길면 `PackageCard` 가 늘어나며 안쪽이 세로 중앙이다. 왼쪽 열 `sticky` 는 폐지. 상시 노출 설명 문구는
  공용 `InfoDialog`(ⓘ 모달)로 옮겼다. 화면 용어는 `Dependents` 가 아니라 **의존 수**(`terms.tsx` 한 곳에서 바꾼다). PDF 제목도 같다(백엔드 `ReportHtmlRenderer`). "사용처"·
  "N개 프로젝트가 사용" 처럼 실제 사용량으로 읽히는 말은 쓰지 않는다.
