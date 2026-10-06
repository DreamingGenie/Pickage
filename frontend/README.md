# Pickage — Web Service (v1)

Vite + React + TS SPA. Figma `Pickage_v2_web-service`(`485:241`) 기준. 작업 기준 문서는 `CLAUDE.md` 참고.

## 스택

| | |
|---|---|
| 빌드 | Vite 8 |
| 라우팅 | React Router **v7** (`createBrowserRouter`) |
| 스타일 | Tailwind **v4** (`@tailwindcss/vite`) |
| UI | shadcn/ui, base color `slate` |
| 서버 상태 | TanStack Query v5 (HTTP는 `fetch`) |
| 클라 전역 상태 | 없음 (로컬 state만) |

```bash
npm run dev
npm run build
```

## 구조

```
src/
  app/          router.tsx · providers.tsx · app-layout.tsx · routes.ts(경로 단일 출처)
  routes/
    intro/                  00-service-intro
    analyze/                01-package-input + 02-candidate-select. IA는 별도 화면이지만
                             analyze-page.tsx 하나에서 단계로 아래로 쌓인다(step-card.tsx)
    report/
      report-page.tsx       03 셸 (탭)
      ecosystem/            03A
      features/             03B
      community/            확장-03 GitHub 커뮤니티 (S15P21A506-316)
      _components/          EvidenceDrawer · PDF 내보내기·미리보기 · 분석 실행 훅
  components/
    ui/         shadcn 원본 — 건드리지 않음
    common/     Header · Stepper · PackageChip · StatusBadge · SegmentedControl · LoadingOverlay · InfoDialog(ⓘ 설명 모달)
    charts/     직접 그린 SVG — line-chart · version-share · transition-bars.
                좌표·눈금 계산은 geometry.ts (React·DOM 을 모른다)
  api/
    client.ts   fetch 래퍼 + ApiError 정규화 (인증이 없어 axios 미채택)
    endpoints.ts  엔드포인트 함수. mock 분기가 일어나는 유일한 곳 (VITE_USE_MOCK)
    autocomplete.ts  사전 접두사 검색 + 서버 조회 폴백
    mock/       개발용 mock 응답
    queries/    useQuery 훅 + queryKeys
    types/      서버 DTO
  lib/          utils.ts · package.ts(입력 파싱)
```

## 확정 규칙

- **보더 토큰 단일**: `--border` / `--input` = `#dbdee5` (`src/index.css`). 다른 보더 색 추가 금지.
- **탭은 로컬 state**. 단 `?evidence=` 쿼리가 있으면 `features` 탭으로 강제하고 근거 드로어를 연다 (`report-page.tsx`).
- **차트는 직접 만든 SVG**(`components/charts/`). 기하 계산은 `geometry.ts` 가 React·DOM 없이 갖는다 — 렌더러를 바꿔도 이 파일은 그대로 쓴다.
- 스코프: intro · 01 · 02 · 03A · 03B · 확장-03(GitHub 커뮤니티). PDF(04)는 미리보기·다운로드 UI 구현됨(상태·차단 사유 로직은 미완).
  GitHub 커뮤니티는 구현 완료(`S15P21A506-316`, 2026-09-17) — `routes/report/community` 가 `report-page.tsx` 의 세 번째 lazy 탭이다.
  상세는 `CLAUDE.md` "현재 스코프" 참고.

## 코드 스플리팅

- **라우트 단위**: intro만 eager(랜딩 첫 페인트), 나머지는 React Router `lazy`. React.lazy 와 달리 라우터가 전환을 붙잡아 주므로 폴백이 깜빡이지 않고, 대기 표시는 `AppLayout`의 `useNavigation`(상단 프로그레스 바 + 본문 디밍)이 담당한다.
- **탭 단위**: Radix Tabs 가 비활성 탭을 언마운트하므로 03A·03B·커뮤니티 탭을 한 번 더 쪼갰다. 탭 트리거 `onMouseEnter` 에서 프리페치하므로 클릭 시점엔 청크가 도착해 있다. 03B 는 나중에 마크다운 렌더러(RAG 결과)를 물게 되므로 분리 이득이 커진다.
- 새 화면을 추가할 땐 `router.tsx` 에 `lazy` 로 넣을 것. eager import 하나가 초기 청크를 다시 부풀린다.

## 미해결

- **리포트 id 발급 주체** — 지금은 서버 발급 가정. 02에서 "리포트 생성" 시 임시로 `/report/draft` 로 진입만 시켜둠.
  비교 대상 자체는 주소(`?names=`)에 싣는다(`S15P21A506-187`) — id 미발급과는 별개 문제.
- **`StatusBadge`의 warn/err 색상** — `ok` 기준으로 파생시킨 값. 디자이너 확인 필요 (`components/common/status-badge.tsx`).

## 참고

- shadcn CLI가 이 환경에서 레지스트리(`ui.shadcn.com`)에 접근하지 못해, `components/ui/*`는 upstream new-york v4 소스를 그대로 옮겨 적었다. 네트워크 되는 환경에서는 `npx shadcn@latest add <name>` 로 정상 추가된다.
