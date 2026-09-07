import { ArrowLeftIcon } from 'lucide-react'
import { Suspense, lazy, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router'

import { paths } from '@/app/routes'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EvidenceDrawer } from '@/routes/report/_components/evidence-drawer'
import { useAnalysisRun } from '@/routes/report/_components/use-analysis-run'

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

const prefetch = {
  ecosystem: () => import('@/routes/report/ecosystem/ecosystem-report-tab'),
  features: () => import('@/routes/report/features/feature-compare-tab'),
} as const

export type ReportTab = 'ecosystem' | 'features'

/**
 * 03A / 03B 를 담는 셸.
 *
 * 탭 상태는 로컬 state 로 둔다. 단 `?evidence=` 가 있으면 features 로 강제한다.
 *
 * 생태계 변화는 사전 집계라 즉시 뜨고, 기능 비교만 분석을 기다린다.
 * 그래서 보고서 전체를 막지 않고 03B 탭 안에서만 대기 화면을 보여준다.
 */
export function ReportPage() {
  const { reportId } = useParams<{ reportId: string }>()
  const navigate = useNavigate()
  const packages = ((useLocation().state as { packages?: string[] } | null)?.packages ?? [
    'winston',
    'pino',
    'bunyan',
  ]) as string[]
  const [searchParams, setSearchParams] = useSearchParams()
  const evidenceId = searchParams.get('evidence')

  /**
   * 탭은 로컬 state 다. 단 `?evidence=` 가 있으면 기능 비교로 강제한다.
   * 동기화 effect 대신 렌더에서 파생시킨다 — 상태가 두 곳에 갈라지지 않는다.
   */
  const [picked, setTab] = useState<ReportTab>('ecosystem')
  const tab: ReportTab = evidenceId ? 'features' : picked
  const run = useAnalysisRun()

  function closeEvidence() {
    const next = new URLSearchParams(searchParams)
    next.delete('evidence')
    setSearchParams(next, { replace: true })
  }

  function openEvidence(id: string) {
    const next = new URLSearchParams(searchParams)
    next.set('evidence', id)
    setSearchParams(next)
    // 드로어를 닫아도 기능 비교 탭에 남아 있도록 선택도 함께 옮긴다.
    setTab('features')
  }

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-wrap items-start justify-between gap-4">
        {/* 비교 패키지는 각 탭의 카드·범례에 이미 나오므로 제목 아래에 또 적지 않는다 */}
        <h1 className="text-2xl font-semibold tracking-tight">분석 결과</h1>

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
        </div>
      </header>

      <Tabs value={tab} onValueChange={(v) => setTab(v as ReportTab)}>
        <TabsList>
          <TabsTrigger value="ecosystem" onMouseEnter={prefetch.ecosystem}>
            생태계 변화
          </TabsTrigger>
          <TabsTrigger value="features" onMouseEnter={prefetch.features}>
            기능 비교
            {run.status !== 'COMPLETED' && (
              <>
                <span
                  aria-hidden
                  className="ml-1 inline-block size-1.5 animate-pulse rounded-full bg-foreground/60"
                />
                <span className="sr-only">분석 중</span>
              </>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="ecosystem" className="pt-7">
          <Suspense fallback={<TabFallback />}>
            <EcosystemReportTab reportId={reportId} />
          </Suspense>
        </TabsContent>
        <TabsContent value="features" className="pt-7">
          <Suspense fallback={<TabFallback />}>
            <FeatureCompareTab run={run} onOpenEvidence={openEvidence} />
          </Suspense>
        </TabsContent>
      </Tabs>

      <EvidenceDrawer evidenceId={evidenceId} onClose={closeEvidence} />
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
