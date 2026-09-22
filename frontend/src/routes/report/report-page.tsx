import { ArrowLeftIcon, FileDownIcon } from 'lucide-react'
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { MAX_NAMES, type PdfJob } from '@/api/types'
import { REPORT_NAMES_PARAM, paths } from '@/app/routes'
import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { UnderlineTabsList, UnderlineTabsTrigger } from '@/components/common/underline-tabs'
import { Tabs, TabsContent } from '@/components/ui/tabs'
import { HandoffButton } from '@/routes/report/_components/handoff-button'
import { PdfExportDialog } from '@/routes/report/_components/pdf-export-dialog'
import { PdfPreviewDialog } from '@/routes/report/_components/pdf-preview-dialog'
import { reportExportReady } from '@/routes/report/_components/report-export-eligibility'
import { useAnalysisRun } from '@/routes/report/_components/use-analysis-run'
import { useReportBasePackage } from '@/routes/report/_components/use-report-base-package'
import {
  DEFAULT_TRANSITION_PERIOD,
  type TransitionPeriod,
} from '@/routes/report/ecosystem/transitions-model'
import { cn } from '@/lib/utils'

/**
 * 탭은 한 번에 하나만 마운트되므로(Radix 기본 동작) 탭 단위로 한 번 더 쪼갠다.
 * 03B 는 나중에 마크다운 렌더러(RAG 결과)를 물게 되므로 특히 분리 이득이 크다.
 */
const EcosystemReportTab = lazy(() =>
  import('@/routes/report/ecosystem/ecosystem-report-tab').then((m) => ({
    default: m.EcosystemReportTab,
  })),
)
const FeatureCompareTab = lazy(() =>
  import('@/routes/report/features/feature-compare-tab').then((m) => ({
    default: m.FeatureCompareTab,
  })),
)
const CommunityReportTab = lazy(() =>
  import('@/routes/report/community/community-report-tab').then((m) => ({
    default: m.CommunityReportTab,
  })),
)

const prefetch = {
  ecosystem: () => import('@/routes/report/ecosystem/ecosystem-report-tab'),
  features: () => import('@/routes/report/features/feature-compare-tab'),
  community: () => import('@/routes/report/community/community-report-tab'),
} as const

export type ReportTab = 'ecosystem' | 'features' | 'community'

/** 주소에서 읽어낸 비교 대상. */
interface ReportNames {
  /** 실제로 조회할 이름. 중복을 지우고 상한까지만 남긴다. */
  names: string[]
  /**
   * 상한을 넘겨 빠진 이름.
   *
   * **버리되 밝힌다.** 조용히 자르면 주소에 네 개가 적혀 있는데 화면에는 세 개만 뜨고,
   * 어느 것이 빠졌는지 알 방법이 없다. 이 화면이 없애려는 실패가 바로 그것이다.
   */
  dropped: string[]
}

/**
 * 주소에서 비교 대상을 읽는다 (`?names=a,b,c`).
 *
 * **없으면 기본 조합으로 대체하지 않는다.** 예전에는 라우터 state 가 없을 때 조용히
 * winston·pino·bunyan 으로 떨어졌다. 공유받은 링크에서 그 일이 일어나면 받는 사람은
 * 보낸 사람과 다른 보고서를 보면서도 화면에 아무 표시가 없다 — 비어 있는 것보다
 * 틀린 것을 맞다고 보여주는 쪽이 나쁘다.
 *
 * 서버가 어차피 같은 규칙으로 검증하므로(0.1) 여기서는 형식까지 보지 않는다.
 * 보내기 전에 줄이는 것만 한다 — 중복 제거와 상한이다. 상한을 넘겨 보내면 V002 로
 * 거절당해 네 요청이 전부 빈다.
 *
 * <h2>두 값을 한 {@code useMemo} 안에서 만든다</h2>
 *
 * 밖에서 잘라내면 렌더마다 새 배열이 나오고, 그 배열이 {@code EcosystemReportTab} 의
 * 질의 키에 그대로 들어가 **끝나지 않는 재조회**가 된다. 같은 memo 결과 안에 두면
 * 호출부에서 구조분해해도 두 배열의 참조가 그대로다.
 */
function useReportNames(raw: string | null): ReportNames {
  return useMemo(() => {
    if (!raw) return { names: [], dropped: [] }
    const cleaned = [
      ...new Set(
        raw
          .split(',')
          .map((name) => name.trim())
          .filter(Boolean),
      ),
    ]
    return { names: cleaned.slice(0, MAX_NAMES), dropped: cleaned.slice(MAX_NAMES) }
  }, [raw])
}

/**
 * 03A / 03B 를 담는 셸.
 *
 * 탭 상태는 로컬 state 로 둔다.
 *
 * 생태계 변화는 사전 집계라 즉시 뜨고, 기능 비교만 분석을 기다린다.
 * 그래서 보고서 전체를 막지 않고 03B 탭 안에서만 대기 화면을 보여준다.
 */
export function ReportPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  /**
   * 비교 대상은 주소가 들고 있다. 새로고침·뒤로가기·공유 링크가 전부 같은 보고서를 연다.
   */
  const { names: packages, dropped } = useReportNames(searchParams.get(REPORT_NAMES_PARAM))
  const { basePackage, conflict: baseConflict } = useReportBasePackage(packages)

  const [tab, setTab] = useState<ReportTab>('ecosystem')
  const run = useAnalysisRun(packages)
  /**
   * PDF·HAND-OFF 버튼이 같이 쓰는 조건(`report-export-eligibility.ts`). 예전엔 이 파일이
   * `pdf-export-dialog.tsx`의 `blockReasonsFor`와 같은 조건을 손으로 다시 적고 있었는데,
   * HAND-OFF(S15P21A506-467)가 같은 조건을 또 필요로 하면서 그 중복을 없앴다.
   */
  const exportReady = reportExportReady(run)

  /**
   * 한 번 방문한 탭은 언마운트하지 않는다(S15P21A506-316).
   *
   * Radix `TabsContent` 기본 동작은 비활성 탭을 DOM 에서 지운다 — 생태계 탭의 구간·버전·
   * 접힘 선택이 전부 로컬 state 라 탭을 오가면 매번 초기화된다. `forceMount` + 수동
   * `hidden` 으로 바꾸되, **아직 한 번도 안 연 탭은 여전히 렌더하지 않는다** — 그래야
   * 방문 전 lazy 청크를 안 받는 기존 코드 스플리팅이 그대로 유지된다.
   *
   * 커뮤니티 탭은 이 때문에 언마운트로 폴링을 멈출 수 없다 — 그래서 `active` prop 을
   * 따로 내려 명시적으로 폴링을 끈다(아래 `CommunityReportTab`).
   */
  const [visited, setVisited] = useState<Set<ReportTab>>(() => new Set(['ecosystem']))
  useEffect(() => {
    setVisited((prev) => (prev.has(tab) ? prev : new Set(prev).add(tab)))
  }, [tab])

  /**
   * PDF 내보내기. 두 모달이 이어진다 — 내보내기(생성)가 닫히고 미리보기가 열린다.
   *
   * 만들어진 보고서를 여기서 들고 있는 이유는, 미리보기를 닫았다가 다시 열 때
   * **문서를 다시 만들지 않기 위해서**다(요구사항 §13.2 · 기능-16-R08).
   */
  const [exporting, setExporting] = useState(false)
  const [preview, setPreview] = useState<PdfJob | null>(null)

  /**
   * 유지·유입·이탈 조회 구간. 원래 `EcosystemReportTab` 로컬 state였지만, PDF 내보내기
   * 다이얼로그(아래)가 "화면이 지금 보는 기간"을 그대로 요청에 실어야 해서 여기로
   * 끌어올렸다(S15P21A506-394) — 안 그러면 화면에서 1y·5y를 보다가 PDF를 내보내도 문서는
   * 서버 기본값(3y)으로 조용히 달라진다. 조회를 쏘는 자리는 여전히 `EcosystemReportTab`
   * 안이다 — 그쪽 주석 참고.
   */
  const [transitionPeriod, setTransitionPeriod] =
    useState<TransitionPeriod>(DEFAULT_TRANSITION_PERIOD)

  /*
    주소에 비교 대상이 없다. 링크가 잘렸거나 `/report/draft` 를 손으로 친 경우다.
    무엇을 보여줄지 정할 근거가 없으므로 지어내지 않고 되돌려 보낸다.
  */
  if (packages.length === 0) {
    return (
      <div className="flex flex-col gap-7">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">비교 보고서</h1>
        </header>
        <EmptyState
          title="어떤 패키지를 비교할지 주소에 없어요"
          description={
            <>
              보고서 주소의 <span className="font-mono">?{REPORT_NAMES_PARAM}=</span> 뒤에 비교할
              패키지가 담겨요. 링크가 잘렸을 수 있으니, 패키지를 다시 골라 주세요.
            </>
          }
          actions={<Button onClick={() => navigate(paths.analyze)}>패키지 고르러 가기</Button>}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-wrap items-start justify-between gap-4">
        {/*
          제목 아래에 비교 대상을 적는다. 예전에는 각 탭의 카드·범례에 나온다고 뺐는데, 공유받은 링크로
          들어온 사람이 무엇을 비교한 보고서인지 탭을 열기 전에는 알 수 없었다.
        */}
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="text-sm font-medium text-primary">비교 보고서</span>
          <h1 className="flex flex-wrap items-baseline gap-x-2 font-mono text-2xl font-bold tracking-tight">
            {packages.map((name, i) => (
              <span key={name} className="flex items-baseline gap-x-2">
                {i > 0 && (
                  <span aria-hidden className="font-sans text-muted-foreground">
                    ·
                  </span>
                )}
                <span title={name} className="max-w-[20ch] truncate">
                  {name}
                </span>
              </span>
            ))}
          </h1>
        </div>

        {/* 되돌아가기. 확정한 선택을 그대로 들고 가서 2단계부터 다시 연다 */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(paths.analyze, { state: { restore: packages } })}
          >
            <ArrowLeftIcon className="size-3.5" aria-hidden />
            비교 대상 바꾸기
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate(paths.analyze)}>
            새 분석
          </Button>
          {/*
            기능-05-R03 — 상단 우측. 보고서 어느 탭에 있든 같은 자리에 있어야 한다.
            기능 비교를 마치기 전에는 흐리게 두되 **누를 수는 있다** — 누르면 내보내기 창이 막힌 이유와
            "기능 비교로 이동" 을 보여 준다. 아예 막으면 왜 안 되는지 알 길이 없다.
          */}
          <Button
            size="sm"
            variant={exportReady ? 'default' : 'outline'}
            aria-describedby={exportReady ? undefined : 'pdf-hint'}
            className={cn(!exportReady && 'text-muted-foreground')}
            onClick={() => setExporting(true)}
          >
            <FileDownIcon className="size-3.5" aria-hidden />
            PDF로 저장
          </Button>
          {/*
            HAND-OFF(S15P21A506-467) — PDF 옆. 같은 자격 조건, 모달은 없다(선택할 구역이
            없어서 확인 화면이 필요 없다). 준비 전에도 눌리는 것까지 PDF 버튼과 같다 —
            이유는 바로 아래 공용 안내 문구가 보여준다.
          */}
          <HandoffButton packages={packages} transitionPeriod={transitionPeriod} run={run} />
        </div>
      </header>

      {!exportReady && (
        <p
          id="pdf-hint"
          className="-mt-3 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground"
        >
          PDF·HAND-OFF에는 기능 비교 결과도 들어가요. 기능 비교를 마치면 내려받을 수 있어요.
          <button
            type="button"
            onClick={() => setTab('features')}
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            기능 비교로 가기
          </button>
        </p>
      )}

      {/*
        주소에 상한을 넘는 이름이 있었다. 탭과 무관한 "주소" 이야기라 페이지 위에 둔다 —
        생태계 탭 안의 "찾지 못한 패키지"(서버가 이름을 못 찾음)와는 다른 사실이고,
        둘이 함께 뜰 수도 있다.
      */}
      {dropped.length > 0 && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          한 번에 {MAX_NAMES}개까지 비교할 수 있어요. 주소에 더 있어서{' '}
          <span className="font-mono text-foreground">{dropped.join(', ')}</span> 는 뺐어요.
        </p>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(v as ReportTab)}>
        {/* 탭 이름 옆에 MVP·확장 같은 범위 표시를 붙이지 않는다 — 기획 시안에서 뺀 항목 */}
        <UnderlineTabsList>
          <UnderlineTabsTrigger value="ecosystem" onMouseEnter={prefetch.ecosystem}>
            생태계 변화
          </UnderlineTabsTrigger>
          <UnderlineTabsTrigger value="features" onMouseEnter={prefetch.features}>
            기능 비교
            {!run.hasCompletedOnce && run.status !== 'RUNNING' && (
              <span className="ml-1.5 rounded-full bg-tone-down px-2 py-0.5 text-sm font-medium text-tone-down-foreground">
                PDF 전에 필요
              </span>
            )}
            {run.status === 'RUNNING' && (
              <>
                <span
                  aria-hidden
                  className="ml-1 inline-block size-1.5 animate-pulse rounded-full bg-foreground/60"
                />
                <span className="sr-only">분석 중</span>
              </>
            )}
          </UnderlineTabsTrigger>
          <UnderlineTabsTrigger value="community" onMouseEnter={prefetch.community}>
            GitHub 커뮤니티
          </UnderlineTabsTrigger>
        </UnderlineTabsList>

        {/*
          세 탭 모두 방문 후에는 `forceMount` 로 마운트를 유지하고 `hidden` 으로만 감춘다
          (위 `visited` 주석). 방문 전에는 아예 렌더하지 않아 lazy 청크를 받지 않는다.
        */}
        {visited.has('ecosystem') && (
          <TabsContent
            value="ecosystem"
            forceMount
            className={cn('pt-7', tab !== 'ecosystem' && 'hidden')}
          >
            <Suspense fallback={<TabFallback />}>
              <EcosystemReportTab
                packages={packages}
                transitionPeriod={transitionPeriod}
                onTransitionPeriodChange={setTransitionPeriod}
              />
            </Suspense>
          </TabsContent>
        )}
        {visited.has('features') && (
          <TabsContent
            value="features"
            forceMount
            className={cn('pt-7', tab !== 'features' && 'hidden')}
          >
            <Suspense fallback={<TabFallback />}>
              <FeatureCompareTab packages={packages} run={run} />
            </Suspense>
          </TabsContent>
        )}
        {visited.has('community') && (
          <TabsContent
            value="community"
            forceMount
            className={cn('pt-7', tab !== 'community' && 'hidden')}
          >
            <Suspense fallback={<TabFallback />}>
              <CommunityReportTab
                basePackage={basePackage}
                baseConflict={baseConflict}
                active={tab === 'community'}
              />
            </Suspense>
          </TabsContent>
        )}
      </Tabs>

      <PdfExportDialog
        open={exporting}
        onOpenChange={setExporting}
        packages={packages}
        transitionPeriod={transitionPeriod}
        run={run}
        onGoToFeatures={() => setTab('features')}
        onPreview={(job) => {
          // 생성 모달을 닫고 미리보기로 넘긴다. 둘이 겹쳐 뜨면 어느 쪽을 닫는 것인지
          // 알 수 없고, 뒤 모달의 포커스 덫에 갇힌다.
          setExporting(false)
          setPreview(job)
        }}
      />
      <PdfPreviewDialog job={preview} onOpenChange={(open) => !open && setPreview(null)} />
    </div>
  )
}

/** 탭 청크를 받는 동안. 화면 구조를 미리 잡아 레이아웃이 튀지 않게 한다. */
function TabFallback() {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-11 w-full max-w-sm" />
      <Skeleton className="h-56 w-full" />
    </div>
  )
}
