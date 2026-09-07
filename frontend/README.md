# OSS Shift — Web Service (v1)

Vite + React + TS SPA. Figma `OSS_Shift / OSS_Shift_v1_web-service` 기준.

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
    analyze/input/          01-package-input
    analyze/candidates/     02-candidate-select
    report/
      report-page.tsx       03 셸 (탭)
      ecosystem/            03A
      features/             03B
      _components/          EvidenceDrawer
  components/
    ui/         shadcn 원본 — 건드리지 않음
    common/     Header · Stepper · PackageChip · StatusBadge
    charts/     목업 (LineChartMock · BarChartMock) — props 시그니처 고정
  api/
    client.ts   fetch 래퍼 + ApiError 정규화 (인증이 없어 axios 미채택)
    queries/    useQuery 훅 + queryKeys
    types/      서버 DTO
  lib/          utils.ts · package.ts(입력 파싱)
```

## 확정 규칙

- **보더 토큰 단일**: `--border` / `--input` = `#dbdee5` (`src/index.css`). 다른 보더 색 추가 금지.
- **탭은 로컬 state**. 단 `?evidence=` 쿼리가 있으면 `features` 탭으로 강제하고 근거 드로어를 연다 (`report-page.tsx`).
- **차트는 목업**. 교체 시 `components/charts/mock-chart.tsx`의 `ChartProps` 시그니처 유지.
- 스코프: intro · 01 · 02 · 03A · 03B. **PDF(04) / EXT-03 제외** — `routes/print`, `routes/report/community` 미생성.

## 코드 스플리팅

- **라우트 단위**: intro만 eager(랜딩 첫 페인트), 나머지는 React Router `lazy`. React.lazy 와 달리 라우터가 전환을 붙잡아 주므로 폴백이 깜빡이지 않고, 대기 표시는 `AppLayout`의 `useNavigation`(상단 프로그레스 바 + 본문 디밍)이 담당한다.
- **탭 단위**: Radix Tabs 가 비활성 탭을 언마운트하므로 03A/03B 를 한 번 더 쪼갰다. 탭 트리거 `onMouseEnter` 에서 프리페치하므로 클릭 시점엔 청크가 도착해 있다. 03B 는 나중에 마크다운 렌더러(RAG 결과)를 물게 되므로 분리 이득이 커진다.
- 새 화면을 추가할 땐 `router.tsx` 에 `lazy` 로 넣을 것. eager import 하나가 초기 청크를 다시 부풀린다.

## 미해결

- **리포트 id 발급 주체** — 지금은 서버 발급 가정. 02에서 "리포트 생성" 시 임시로 `/report/draft` 로 진입만 시켜둠.
- **`StatusBadge`의 warn/err 색상** — `ok` 기준으로 파생시킨 값. 디자이너 확인 필요 (`components/common/status-badge.tsx`).
- **`api/types`는 화면에서 역산한 초안**. Spring 스펙 확정 시 이 파일만 교체하면 되도록 화면은 타입에만 의존시킴.

## 참고

- shadcn CLI가 이 환경에서 레지스트리(`ui.shadcn.com`)에 접근하지 못해, `components/ui/*`는 upstream new-york v4 소스를 그대로 옮겨 적었다. 네트워크 되는 환경에서는 `npx shadcn@latest add <name>` 로 정상 추가된다.
