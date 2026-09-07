# OSS Shift 프론트엔드 — 작업 기준

**모든 화면 작업 전에 `docs/OSS_Shift_메뉴구조_IA_0902.md`를 먼저 읽는다.** 데이터·상태·판정 계약은
`docs/OSS_Shift_기능별_개발구상안_0902.md`가 기준이다. 두 문서가 코드보다 우선한다.

Figma: `fuTQIgzDn8cr6BTwdOlDrx` → 섹션 `OSS_Shift` → 프레임 `OSS_Shift_v1_web-service`
(`무덤` 섹션은 무시)

## 절대 규칙

문서에서 금지한 것을 화면에 넣지 않는다. 아래는 실수하기 쉬운 항목만 추린 것이고,
전체 목록은 IA 1장·2장과 구상안 1.3·7.2에 있다.

- **금지 용어**: `확인 불가`, `대시보드`, `최고의 대안`, `추천 1위`, `승자` (IA 2)
- **추천·순위·승자 표현 금지.** 어느 쪽이 낫다는 판정을 하지 않는다 (IA 1.10)
- **외부 링크 금지.** 저장소·출처 식별자는 표시 문자열로만. 클릭 가능한 URL 필드 없음 (IA 1.12, 구상안 10)
- **색상만으로 의미 전달 금지.** 판정·오류·선택 상태에는 문구나 아이콘을 함께 (IA 1.11, 13)
- **비교 대상은 기준 패키지 포함 최대 3개** (IA 1.4)
- **버전은 입력 화면에 없다.** 화면-01에 버전 입력·드롭다운·최신 버전 선택을 두지 않는다 (IA 5.2)
- **사용자 선택을 자동 해제하지 않는다.** 4번째 추가는 `MAX_SELECTION_REACHED` (IA 6.3, 구상안 4.4)

## 판정값 (구상안 7.2)

`verdict`와 `dataStatus`는 다른 축이다. 섞지 않는다.

```
verdict:      SUPPORTED · CONDITIONALLY_SUPPORTED · LIMITED_SUPPORT · UNCONFIRMED · UNSUPPORTED
dataStatus:   COMPLETE · PARTIAL · NO_DATA · COLLECTION_ERROR · CONFLICT · STALE
```

화면 표기: 지원 · 조건부 · 제한적 · 미확인 (IA 9.2)

- **`UNSUPPORTED`는 공식 부정 근거가 연결됐을 때만.** 자료가 없으면 `UNCONFIRMED`다.
- **미확인은 미지원이 아니다.** 실패색을 쓰지 않고, 무엇을 어디까지 확인했는지 함께 보여준다.
- 비교 가능한 기능이 부족하면 억지 표를 만들지 않고 `COMPARISON_LIMITED` (구상안 8)

## 버전 세 갈래 (구상안 1.2)

1. 후보 단계 — 버전 없음
2. Dependency 표시 버전 — `TOTAL` 또는 특정 버전, 패키지별 독립
3. 기능 비교 버전 — 최신 안정 버전 또는 사용자 선택

2번을 바꿔도 기능 분석 결과·캐시·판정은 무효화되지 않는다. 전역 분석 버전을 상단에 두지 않고
각 카드 안에 둔다 (IA 7.1).

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
- **차트는 목업.** 교체 시 `components/charts/mock-chart.tsx`의 `ChartProps` 시그니처 유지.
- **새 화면은 `app/router.tsx`에 `lazy`로 추가.** eager import 하나가 초기 청크를 부풀린다.

## 현재 스코프

포함: 00 · 01 · 02 · 03A(생태계) · 03B(기능 비교)
제외: PDF(04) · GitHub 커뮤니티(확장-03) — `routes/print`, `routes/report/community` 미생성

## 예시 데이터

지어내지 않는다. 구상안 16장의 POC 실측(winston 3.19.0 / pino 10.3.1 / bunyan 1.8.15)과
구상안 본문의 예시 JSON을 쓴다. 불가피하게 만든 값은 화면에 "예시"라고 표시한다.

## 미해결

- 리포트 id 발급 주체 — 현재 서버 발급 가정, 02에서 임시로 `/report/draft` 진입
- `api/types`는 화면에서 역산한 초안 — Spring 스펙 확정 시 이 파일만 교체
- 인트로 히어로의 패키지 입력 필드는 IA 4.2(`패키지 분석 시작` 버튼)와 어긋남 — 결정 필요
